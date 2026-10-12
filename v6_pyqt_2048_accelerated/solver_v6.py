#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 统一求解调度（五策略兼容适配 + 计算后端选择）。

设计：五类策略的**搜索算法只实现一份**，通过 ``backend`` 原语（move/legal/evaluate/
empty/game_over/sample_spawn）驱动；reference 后端的原语即冻结的 V5 实现，
因此“换后端”只改变底层计算，不改变算法本身（便于严格等价对照）。

对外签名保持与 V5 一致：``solve(grid, strategy='expectimax', **options)``；
新增可选 ``backend`` 与结果字段 ``backend_requested/backend_used/backend_fallback_reason``，
不破坏老界面/导出解析。
"""

from __future__ import annotations

import math
import os
import random
import sys
import time

_V6_DIR_SELF = os.path.dirname(os.path.abspath(__file__))
if _V6_DIR_SELF not in sys.path:
    sys.path.insert(0, _V6_DIR_SELF)

from solver_backends import api as _api                        # noqa: E402
from solver_backends.dispatch import get_backend, probe_backends   # noqa: E402
from solver_backends.events import SpawnEventStream            # noqa: E402

# 复用 V5 的常量与 RL 实现（只读）
_V5_DIR = os.path.join(os.path.dirname(_V6_DIR_SELF), 'v5_pyqt_2048_solver')
if _V5_DIR not in sys.path:
    sys.path.insert(0, _V5_DIR)
import solver_2048 as _v5                                     # noqa: E402

DIRECTIONS = _v5.DIRECTIONS
DIRECTION_NAMES = _v5.DIRECTION_NAMES
STRATEGY_ORDER = _v5.STRATEGY_ORDER
STRATEGIES = _v5.STRATEGIES
PRESET_LABELS = _v5.PRESET_LABELS
PRESET_ORDER = _v5.PRESET_ORDER
STRATEGY_PRESETS = _v5.STRATEGY_PRESETS
PARAMETRIC_STRATEGIES = _v5.PARAMETRIC_STRATEGIES
DEFAULT_WEIGHTS = _v5.DEFAULT_WEIGHTS
PRUNE_DEFAULTS = _v5.PRUNE_DEFAULTS
MAX_TIME_LIMIT = _v5.MAX_TIME_LIMIT
DEFAULT_SEED = _v5.DEFAULT_SEED

build_config = _v5.build_config
has_presets = _v5.has_presets
describe_config = _v5.describe_config
evaluate_features = _v5.evaluate_features
# 供 GUI 复用的规则级只读封装（与 V5 完全一致；不做后端分派）
legal_moves = _v5.legal_moves
empty_cells = _v5.empty_cells
is_game_over = _v5.is_game_over
max_tile = _v5.max_tile

# V6 RL 模型读取：默认只读 V5 正式模型（绝不写入/替换 V5 模型）
V5_RL_MODEL_PATH = _v5.RL_MODEL_PATH
V6_DIR = os.path.dirname(os.path.abspath(__file__))
V6_RL_MODEL_PATH = os.path.join(V6_DIR, 'rl_model.npz')


def rl_model_path():
    """V6 优先读自己的模型副本（若有）；否则只读 V5 正式模型。"""
    if os.path.exists(V6_RL_MODEL_PATH):
        return V6_RL_MODEL_PATH
    return V5_RL_MODEL_PATH


# =====================================================================
# 结果构造
# =====================================================================
def _result(strategy, best_dir, evaluations, depth_reached, nodes, start,
            timed_out=False, error=None, extra=None):
    data = {
        'strategy': strategy,
        'best_direction': best_dir,
        'best_name': DIRECTION_NAMES.get(best_dir, ''),
        'evaluations': evaluations,
        'depth_reached': depth_reached,
        'nodes': nodes,
        'elapsed_ms': round((time.time() - start) * 1000.0, 3),
        'timed_out': bool(timed_out),
        'error': error,
    }
    if extra:
        data.update(extra)
    return data


def _ordered_moves(backend, grid, weights, order=True):
    items = []
    for d in DIRECTIONS:
        new_grid, gain, moved = backend.move(grid, d)
        if moved:
            items.append((d, new_grid, gain))
    if order:
        items.sort(key=lambda it: backend.evaluate(it[1], weights), reverse=True)
    return items


def _ordered_dirs(backend, grid, weights):
    return [d for d, _g, _gain in _ordered_moves(backend, grid, weights, order=True)]


# =====================================================================
# 策略一：启发式（单步贪心）
# =====================================================================
def _heuristic_decision(backend, grid, weights=None):
    start = time.time()
    evaluations = {}
    best_dir, best_value = None, -float('inf')
    for d in DIRECTIONS:
        new_grid, _, moved = backend.move(grid, d)
        if not moved:
            evaluations[d] = None
            continue
        value = backend.evaluate(new_grid, weights)
        evaluations[d] = value
        if value > best_value:
            best_value, best_dir = value, d
    return _result('heuristic', best_dir, evaluations, 1, len(DIRECTIONS), start)


# =====================================================================
# 策略二：贪心模拟 / rollout
# =====================================================================
def _rollout_score(backend, grid_after_move, gained, depth, weights, rng,
                   policy='random', epsilon=0.2):
    g = grid_after_move
    score = gained
    for _ in range(depth):
        if backend.is_game_over(g):
            break
        g = backend.sample_spawn(g, rng)[0]
        if backend.is_game_over(g):
            break
        moves = backend.legal_moves(g)
        if not moves:
            break
        if policy == 'heuristic_biased' and rng.random() >= epsilon:
            best, best_v = moves[0], -float('inf')
            for cand in moves:
                ng, _gn, _m = backend.move(g, cand)
                val = backend.evaluate(ng, weights)
                if val > best_v:
                    best_v, best = val, cand
            move = best
        else:
            move = rng.choice(moves)
        g, gain, _ = backend.move(g, move)
        score += gain
    return score + backend.evaluate(g, weights)


def _rollout_decision(backend, grid, rollouts=20, rollout_depth=16, weights=None,
                      seed=DEFAULT_SEED, policy='random', epsilon=0.2, paired=True,
                      native_rollout=False):
    start = time.time()
    weights = weights or DEFAULT_WEIGHTS
    nodes = 0
    evaluations = {}
    details = {}
    best_dir, best_value = None, -float('inf')
    # 原生整段 rollout（可选）：仅 random 策略且后端声明支持时启用；
    # 同一显式事件流下与 Python 驱动逐位一致（见 benchmarks/verify_rollout_events）。
    native = (bool(native_rollout) and policy == 'random'
              and getattr(backend, 'supports_native_rollout', False))
    for d, after_move, gain in _ordered_moves(backend, grid, weights, order=True):
        if paired:
            dir_seed = int(seed)
        else:
            idx = DIRECTIONS.index(d)
            dir_seed = (seed * 1000003 + idx * 7919) & 0xFFFFFFFF
        n_roll = max(1, rollouts)
        if native:
            stream = SpawnEventStream(dir_seed, max(4096, n_roll * max(1, rollout_depth) * 4))
            cell_ev, value_ev, move_ev = stream.as_arrays()
            sims = backend.rollout_batch(after_move, gain, max(1, rollout_depth),
                                         n_roll, cell_ev, value_ev, move_ev, weights)
            nodes += len(sims)
        else:
            rng = random.Random(dir_seed)
            sims = []
            for _ in range(n_roll):
                sims.append(_rollout_score(backend, after_move, gain, max(1, rollout_depth),
                                           weights, rng, policy, epsilon))
                nodes += 1
        mean = sum(sims) / len(sims)
        var = sum((x - mean) ** 2 for x in sims) / max(1, len(sims) - 1)
        evaluations[d] = mean
        details[d] = {'mean': round(mean, 3), 'std': round(math.sqrt(var), 3),
                      'se': round(math.sqrt(var / len(sims)), 3), 'n': len(sims)}
        if mean > best_value:
            best_value, best_dir = mean, d
    return _result('rollout', best_dir, evaluations, max(1, rollout_depth), nodes, start,
                   extra={'rollouts': rollouts, 'policy': policy, 'paired': bool(paired),
                          'epsilon': epsilon if policy == 'heuristic_biased' else None,
                          'native_rollout': bool(native),
                          # 原生整段 rollout（rollout_batch）属于「native 原语批量化」，
                          # 不等于 native 整树搜索，故单独标注，绝不冒充 native full-tree。
                          'engine_used': 'native_rollout' if native else 'python_kernel',
                          'details': details})



# =====================================================================
# 策略三：Expectimax（迭代加深 + 时间预算 + 剪枝）
# =====================================================================
def _expectimax_decision(backend, grid, max_depth, time_limit, weights=None, prune=True,
                         sample_limit=None, use_tt=True, prob_cutoff=None,
                         move_order=True, seed=DEFAULT_SEED, score_weight=0.0):
    start = time.time()
    ctx = {'nodes': 0, 'leaf': 0, 'cache_hits': 0, 'cutoffs': 0,
           'sampled_chance': 0, 'chance_nodes': 0, 'timed_out': False}
    tt = {}
    rng = random.Random(seed)
    if sample_limit is None:
        sample_limit = PRUNE_DEFAULTS['sample_limit']
    if prob_cutoff is None:
        prob_cutoff = PRUNE_DEFAULTS['prob_cutoff']
    use_cutoff = bool(prune) and bool(prob_cutoff) and prob_cutoff > 0.0
    use_sample = bool(prune) and bool(sample_limit) and sample_limit > 0
    use_tt = bool(prune) and bool(use_tt)

    def expired():
        return (time.time() - start) > time_limit

    def leaf(g):
        ctx['leaf'] += 1
        return backend.evaluate(g, weights)

    def state_key(g):
        return tuple(tuple(row) for row in g)

    def tt_key(g, depth, kind, p):
        if use_cutoff:
            return (state_key(g), depth, kind, p)
        return (state_key(g), depth, kind)

    def max_node(g, depth, p):
        if depth <= 0:
            return leaf(g)
        if expired():
            ctx['timed_out'] = True
            return leaf(g)
        key = None
        if use_tt:
            key = tt_key(g, depth, 'M', p)
            hit = tt.get(key)
            if hit is not None:
                ctx['cache_hits'] += 1
                return hit
        ctx['nodes'] += 1
        best = -float('inf')
        any_move = False
        for _d, new_grid, gain in _ordered_moves(backend, g, weights,
                                                 order=(bool(prune) and move_order)):
            any_move = True
            value = score_weight * gain + chance_node(new_grid, depth - 1, p)
            if value > best:
                best = value
            if ctx['timed_out']:
                break
        if not any_move:
            best = leaf(g)
        if use_tt and key is not None and not ctx['timed_out']:
            tt[key] = best
        return best

    def chance_node(g, depth, p):
        if depth <= 0:
            return leaf(g)
        if expired():
            ctx['timed_out'] = True
            return leaf(g)
        cells = backend.empty_cells(g)
        if not cells:
            return leaf(g)
        ctx['chance_nodes'] += 1
        key = None
        if use_tt:
            key = tt_key(g, depth, 'C', p)
            hit = tt.get(key)
            if hit is not None:
                ctx['cache_hits'] += 1
                return hit

        total_cells = len(cells)
        cells_used = cells
        if use_sample and total_cells > sample_limit:
            cells_used = rng.sample(cells, sample_limit)
            ctx['sampled_chance'] += 1

        inv_e = 1.0 / total_cells
        total = 0.0
        for (i, j) in cells_used:
            p_cell = p * inv_e
            child2 = [row[:] for row in g]
            child2[i][j] = 2
            if use_cutoff and (p_cell * 0.9) < prob_cutoff:
                ctx['cutoffs'] += 1
                total += 0.9 * leaf(child2)
            else:
                total += 0.9 * max_node(child2, depth - 1, p_cell * 0.9)
            child4 = [row[:] for row in g]
            child4[i][j] = 4
            if use_cutoff and (p_cell * 0.1) < prob_cutoff:
                ctx['cutoffs'] += 1
                total += 0.1 * leaf(child4)
            else:
                total += 0.1 * max_node(child4, depth - 1, p_cell * 0.1)
            if ctx['timed_out']:
                break
        result = total / len(cells_used)
        if use_tt and key is not None and not ctx['timed_out']:
            tt[key] = result
        return result

    best_result = None
    reached = 0
    for d in range(1, max_depth + 1):
        if expired():
            ctx['timed_out'] = True
            break
        evaluations = {}
        best_dir, best_value = None, -float('inf')
        completed = True
        for direction, new_grid, gain in _ordered_moves(backend, grid, weights,
                                                        order=(bool(prune) and move_order)):
            value = score_weight * gain + chance_node(new_grid, d - 1, 1.0)
            if ctx['timed_out']:
                completed = False
                break
            evaluations[direction] = value
            if value > best_value:
                best_value, best_dir = value, direction
        for direction in DIRECTIONS:
            evaluations.setdefault(direction, None)

        stats = {'pruned': bool(prune), 'tt_entries': len(tt),
                 'cache_hits': ctx['cache_hits'], 'cutoffs': ctx['cutoffs'],
                 'sampled_chance': ctx['sampled_chance'],
                 'chance_nodes': ctx['chance_nodes'], 'leaf_evals': ctx['leaf']}
        if completed and best_dir is not None:
            reached = d
            best_result = _result('expectimax', best_dir, evaluations, reached,
                                  ctx['nodes'], start, extra=dict(stats))
        else:
            if best_result is None and best_dir is not None:
                best_result = _result('expectimax', best_dir, evaluations, 0,
                                      ctx['nodes'], start, timed_out=True, extra=dict(stats))
            break
        if expired():
            ctx['timed_out'] = True
            break

    if best_result is None:
        fallback = _heuristic_decision(backend, grid, weights)
        fallback.update({'strategy': 'expectimax', 'timed_out': True, 'depth_reached': 0,
                         'elapsed_ms': round((time.time() - start) * 1000.0, 3),
                         'pruned': bool(prune), 'cache_hits': ctx['cache_hits'],
                         'cutoffs': ctx['cutoffs'], 'sampled_chance': ctx['sampled_chance'],
                         'chance_nodes': ctx['chance_nodes'], 'leaf_evals': ctx['leaf']})
        return fallback

    best_result['timed_out'] = bool(ctx['timed_out'])
    best_result['nodes'] = ctx['nodes']
    best_result['elapsed_ms'] = round((time.time() - start) * 1000.0, 3)
    best_result['tt_entries'] = len(tt)
    best_result['cache_hits'] = ctx['cache_hits']
    best_result['cutoffs'] = ctx['cutoffs']
    best_result['sampled_chance'] = ctx['sampled_chance']
    best_result['chance_nodes'] = ctx['chance_nodes']
    best_result['leaf_evals'] = ctx['leaf']
    return best_result


# =====================================================================
# 策略四：MCTS（UCT + 渐进加宽 + rollout 截断）
# =====================================================================
class _MCTSNode(object):
    __slots__ = ('grid', 'kind', 'parent', 'move', 'edge_gain', 'children',
                 'child_index', 'untried', 'visits', 'total_return')

    def __init__(self, grid, kind, parent=None, move=None, untried=None, edge_gain=0.0):
        self.grid = grid
        self.kind = kind
        self.parent = parent
        self.move = move
        self.edge_gain = edge_gain
        self.children = []
        self.child_index = {}
        self.untried = untried
        self.visits = 0
        self.total_return = 0.0


def _mcts_decision(backend, grid, simulations=200, time_limit=0.3, rollout_depth=16,
                   weights=None, seed=DEFAULT_SEED, c=1.4, max_chance_width=8,
                   trace=None, progressive_widening=False, cpw=1.0, alpha=0.5):
    start = time.time()
    rng = random.Random(seed)
    kmax = max(1, int(max_chance_width))
    progressive = bool(progressive_widening)
    stats = {'tree_nodes': 0, 'chance_nodes': 0, 'chance_children': 0,
             'rollout_steps': 0, 'reused_children': 0, 'no_spawn_leaves': 0,
             'width_limit_rollouts': 0}

    def ucb(parent, child):
        if child.visits == 0:
            return float('inf')
        return child.total_return / child.visits + c * math.sqrt(
            math.log(max(1, parent.visits)) / child.visits)

    def chance_width(node):
        if not progressive:
            return kmax
        n = max(1, node.visits)
        k = int(math.ceil(cpw * (n ** alpha)))
        return max(1, min(kmax, k))

    def rollout(g, kind, acc):
        if kind == 'C':
            g = backend.sample_spawn(g, rng)[0]
        for _ in range(max(1, rollout_depth)):
            if backend.is_game_over(g):
                break
            moves = backend.legal_moves(g)
            if not moves:
                break
            g, gain, _ = backend.move(g, rng.choice(moves))
            acc += gain
            g = backend.sample_spawn(g, rng)[0]
            stats['rollout_steps'] += 1
        return acc + backend.evaluate(g, weights)

    def descend(root_node):
        node = root_node
        acc = 0.0
        path = []
        while True:
            path.append(node)
            if node.kind == 'P':
                if node.untried:
                    d = node.untried.pop(0)
                    child_grid, gain, _moved = backend.move(node.grid, d)
                    child = _MCTSNode(child_grid, 'C', node, d, untried=None, edge_gain=gain)
                    node.children.append(child)
                    stats['tree_nodes'] += 1
                    stats['chance_nodes'] += 1
                    if trace is not None:
                        trace.append(('P', d, node.kind))
                    path.append(child)
                    return child.grid, child.kind, path, acc + gain
                if not node.children:
                    return node.grid, node.kind, path, acc
                nxt = max(node.children, key=lambda ch: ucb(node, ch))
                acc += nxt.edge_gain
                node = nxt
            else:
                cells = backend.empty_cells(node.grid)
                if not cells:
                    stats['no_spawn_leaves'] += 1
                    return node.grid, node.kind, path, acc
                child_grid, cell, value = backend.sample_spawn(node.grid, rng)
                if trace is not None:
                    trace.append(('C', cell, value, node.kind))
                key = tuple(tuple(row) for row in child_grid)
                child = node.child_index.get(key)
                if child is None:
                    if len(node.children) >= chance_width(node):
                        stats['width_limit_rollouts'] += 1
                        return child_grid, 'P', path, acc
                    child = _MCTSNode(child_grid, 'P', node, None,
                                      untried=_ordered_dirs(backend, child_grid, weights))
                    node.children.append(child)
                    node.child_index[key] = child
                    stats['tree_nodes'] += 1
                    stats['chance_children'] += 1
                else:
                    stats['reused_children'] += 1
                node = child

    root = _MCTSNode([row[:] for row in grid], 'P',
                     untried=_ordered_dirs(backend, grid, weights))
    total = max(1, simulations)
    completed = 0
    backpropagated = 0
    while completed < total and (time.time() - start) <= time_limit:
        leaf_grid, leaf_kind, path, acc = descend(root)
        value = rollout(leaf_grid, leaf_kind, acc)
        for n in path:
            n.visits += 1
            n.total_return += value
        backpropagated += 1
        completed += 1

    evaluations = {}
    root_move_visits = {}
    best_dir, best_value = None, -float('inf')
    for child in root.children:
        if child.visits == 0:
            continue
        mean = child.total_return / child.visits
        evaluations[child.move] = mean
        root_move_visits[child.move] = child.visits
        if mean > best_value:
            best_value, best_dir = mean, child.move
    for d in DIRECTIONS:
        evaluations.setdefault(d, None)
        root_move_visits.setdefault(d, 0)

    timed_out = completed < total
    return _result('mcts', best_dir, evaluations, rollout_depth, stats['tree_nodes'], start,
                   timed_out=timed_out,
                   extra={'simulations': completed,
                          'completed_simulations': completed,
                          'backpropagated_simulations': backpropagated,
                          'root_visits': root.visits,
                          'root_move_visits': root_move_visits,
                          'width_limit_rollouts': stats['width_limit_rollouts'],
                          'rollout_depth': rollout_depth,
                          'chance_nodes': stats['chance_nodes'],
                          'chance_children': stats['chance_children'],
                          'reused_chance_children': stats['reused_children'],
                          'rollout_steps': stats['rollout_steps'],
                          'max_chance_width': kmax,
                          'progressive_widening': progressive,
                          'cpw': cpw, 'alpha': alpha, 'uct_c': c})


# =====================================================================
# 原生整树搜索（V6.2）：C++ native Expectimax / MCTS（可关闭的加速路径）
# =====================================================================
def _native_expectimax_applicable(options):
    """native 精确 Expectimax 仅适用于「无空位采样、无概率截断」的精确语义配置。"""
    prune = bool(options.get('prune', True))
    if not prune:
        return True
    sample_limit = options.get('sample_limit')
    prob_cutoff = options.get('prob_cutoff')
    if sample_limit is None:
        sample_limit = PRUNE_DEFAULTS['sample_limit']
    if prob_cutoff is None:
        prob_cutoff = PRUNE_DEFAULTS['prob_cutoff']
    return not (sample_limit and sample_limit > 0) and not (prob_cutoff and prob_cutoff > 0.0)


def _native_expectimax_decision(be, grid, options, weights):
    from solver_backends import native_api as NA
    start = time.time()
    prune = bool(options.get('prune', True))
    req = NA.NativeSearchRequest(
        board=[list(r) for r in grid], strategy='expectimax',
        budget_type=NA.BUDGET_DEPTH, budget_value=int(options.get('depth', 4)),
        weights=NA.weight_vector(weights or DEFAULT_WEIGHTS),
        seed=int(options.get('seed', DEFAULT_SEED)),
        time_limit_ms=max(1.0, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT) * 1000.0),
        score_weight=float(options.get('score_weight', 0.0)),
        prune=prune,
        use_tt=prune and bool(options.get('use_tt', True)),
        move_order=prune and bool(options.get('move_order', True)),
        sample_limit=0, prob_cutoff=0.0,
        cancel_token=options.get('cancel_token'))
    r = NA.run_expectimax(be, req)
    if r.overflow:
        raise _api.BoardOverflowError('native Expectimax 遇到 >=65536 方块，整次决策回退 reference')
    res = _result('expectimax', r.best_direction, r.evaluations, r.depth_reached, r.node_count,
                  start, timed_out=r.timed_out,
                  extra={'pruned': prune, 'tt_entries': None,
                         'cache_hits': r.stats.get('cache_hits'), 'cutoffs': 0,
                         'sampled_chance': 0, 'chance_nodes': r.stats.get('chance_nodes'),
                         'leaf_evals': r.stats.get('leaf_evals'),
                         'engine_used': 'native', 'board_signature': r.board_signature,
                         'cancelled': r.cancelled})
    return res


def _native_mcts_decision(be, grid, options, weights):
    from solver_backends import native_api as NA
    start = time.time()
    sims = int(options.get('simulations', 200))
    rdepth = int(options.get('rollout_depth', 16))
    req = NA.NativeSearchRequest(
        board=[list(r) for r in grid], strategy='mcts',
        budget_type=NA.BUDGET_ROLLOUTS, budget_value=sims,
        weights=NA.weight_vector(weights or DEFAULT_WEIGHTS),
        seed=int(options.get('seed', DEFAULT_SEED)),
        time_limit_ms=max(1.0, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT) * 1000.0),
        simulations=sims, rollout_depth=rdepth,
        uct_c=float(options.get('c', 1.4)),
        max_chance_width=int(options.get('max_chance_width', 8)),
        progressive_widening=bool(options.get('progressive_widening', False)),
        cpw=float(options.get('cpw', 1.0)), alpha=float(options.get('alpha', 0.5)),
        cancel_token=options.get('cancel_token'))
    r = NA.run_mcts(be, req)
    if r.overflow:
        raise _api.BoardOverflowError('native MCTS 遇到 >=65536 方块，整次决策回退 reference')
    res = _result('mcts', r.best_direction, r.evaluations, rdepth,
                  r.stats.get('tree_nodes', 0), start, timed_out=r.timed_out,
                  extra={'simulations': r.stats.get('simulations'),
                         'completed_simulations': r.stats.get('simulations'),
                         'backpropagated_simulations': r.stats.get('simulations'),
                         'root_visits': r.root_visits,
                         'root_move_visits': r.root_move_visits,
                         'width_limit_rollouts': r.stats.get('width_limit_rollouts'),
                         'rollout_depth': rdepth,
                         'chance_nodes': r.stats.get('chance_nodes'),
                         'chance_children': r.stats.get('chance_children'),
                         'reused_chance_children': r.stats.get('reused_children'),
                         'rollout_steps': r.stats.get('rollout_steps'),
                         'max_chance_width': int(options.get('max_chance_width', 8)),
                         'progressive_widening': bool(options.get('progressive_widening', False)),
                         'cpw': float(options.get('cpw', 1.0)),
                         'alpha': float(options.get('alpha', 0.5)),
                         'uct_c': float(options.get('c', 1.4)),
                         'engine_used': 'native', 'board_signature': r.board_signature,
                         'cancelled': r.cancelled})
    return res


def _mcts_decision_events(backend, grid, simulations=200, rollout_depth=16, weights=None,
                          seed=DEFAULT_SEED, c=1.4, max_chance_width=8,
                          progressive_widening=False, cpw=1.0, alpha=0.5, stream=None,
                          time_limit=0.3):
    """事件流驱动的 Python MCTS 镜像 —— **仅用于与 C++ native_mcts 的逐步等价性验证**。

    消费规则与 native 完全一致：单游标；每次 spawn 用同一游标取 (cell[i], value[i])，
    每次选向用同一游标取 move[i]（i = cursor % n）。不使用 Python RNG，故可跨语言逐位比对。
    """
    start = time.time()
    weights = weights or DEFAULT_WEIGHTS
    kmax = max(1, int(max_chance_width))
    progressive = bool(progressive_widening)
    if stream is None:
        stream = SpawnEventStream(int(seed), 65536)
    cur = [0]

    def spawn_pair():
        i = cur[0] % stream.n
        cur[0] += 1
        return stream.cell[i], stream.value[i]

    def next_move_u():
        i = cur[0] % stream.n
        cur[0] += 1
        return stream.move[i]

    def sample_spawn(g):
        cells = backend.empty_cells(g)
        if not cells:
            return g
        uc, uv = spawn_pair()
        idx = min(len(cells) - 1, int(uc * len(cells)))
        i, j = cells[idx]
        ng = [row[:] for row in g]
        ng[i][j] = 4 if uv >= 0.9 else 2
        return ng

    stats = {'tree_nodes': 0, 'chance_nodes': 0, 'chance_children': 0, 'rollout_steps': 0,
             'reused_children': 0, 'no_spawn_leaves': 0, 'width_limit_rollouts': 0}

    def ucb(parent, child):
        if child.visits == 0:
            return float('inf')
        return child.total_return / child.visits + c * math.sqrt(
            math.log(max(1, parent.visits)) / child.visits)

    def chance_width(node):
        if not progressive:
            return kmax
        n = max(1, node.visits)
        return max(1, min(kmax, int(math.ceil(cpw * (n ** alpha)))))

    def rollout(g, kind, acc):
        if kind == 'C':
            g = sample_spawn(g)
        for _ in range(max(1, rollout_depth)):
            if backend.is_game_over(g):
                break
            moves = backend.legal_moves(g)
            if not moves:
                break
            um = next_move_u()
            mi = min(len(moves) - 1, int(um * len(moves)))
            g, gain, _m = backend.move(g, moves[mi])
            acc += gain
            g = sample_spawn(g)
            stats['rollout_steps'] += 1
        return acc + backend.evaluate(g, weights)

    def descend(root_node):
        node = root_node
        acc = 0.0
        path = []
        while True:
            path.append(node)
            if node.kind == 'P':
                if node.untried:
                    d = node.untried.pop(0)
                    child_grid, gain, _moved = backend.move(node.grid, d)
                    child = _MCTSNode(child_grid, 'C', node, d, untried=None, edge_gain=gain)
                    node.children.append(child)
                    stats['tree_nodes'] += 1
                    stats['chance_nodes'] += 1
                    path.append(child)
                    return child.grid, child.kind, path, acc + gain
                if not node.children:
                    return node.grid, node.kind, path, acc
                nxt = max(node.children, key=lambda ch: ucb(node, ch))
                acc += nxt.edge_gain
                node = nxt
            else:
                cells = backend.empty_cells(node.grid)
                if not cells:
                    stats['no_spawn_leaves'] += 1
                    return node.grid, node.kind, path, acc
                child_grid = sample_spawn(node.grid)
                key = tuple(tuple(row) for row in child_grid)
                child = node.child_index.get(key)
                if child is None:
                    if len(node.children) >= chance_width(node):
                        stats['width_limit_rollouts'] += 1
                        return child_grid, 'P', path, acc
                    child = _MCTSNode(child_grid, 'P', node, None,
                                      untried=_ordered_dirs(backend, child_grid, weights))
                    node.children.append(child)
                    node.child_index[key] = child
                    stats['tree_nodes'] += 1
                    stats['chance_children'] += 1
                else:
                    stats['reused_children'] += 1
                node = child

    root = _MCTSNode([row[:] for row in grid], 'P',
                     untried=_ordered_dirs(backend, grid, weights))
    total = max(1, simulations)
    completed = 0
    backpropagated = 0
    while completed < total and (time.time() - start) <= time_limit:
        leaf_grid, leaf_kind, path, acc = descend(root)
        value = rollout(leaf_grid, leaf_kind, acc)
        for n in path:
            n.visits += 1
            n.total_return += value
        backpropagated += 1
        completed += 1

    evaluations = {}
    root_move_visits = {}
    best_dir, best_value = None, -float('inf')
    for child in root.children:
        if child.visits == 0:
            continue
        mean = child.total_return / child.visits
        evaluations[child.move] = mean
        root_move_visits[child.move] = child.visits
        if mean > best_value:
            best_value, best_dir = mean, child.move
    for d in DIRECTIONS:
        evaluations.setdefault(d, None)
        root_move_visits.setdefault(d, 0)

    return _result('mcts', best_dir, evaluations, rollout_depth, stats['tree_nodes'], start,
                   timed_out=completed < total,
                   extra={'simulations': completed,
                          'completed_simulations': completed,
                          'backpropagated_simulations': backpropagated,
                          'root_visits': root.visits,
                          'root_move_visits': root_move_visits,
                          'width_limit_rollouts': stats['width_limit_rollouts'],
                          'rollout_depth': rollout_depth,
                          'chance_nodes': stats['chance_nodes'],
                          'chance_children': stats['chance_children'],
                          'reused_chance_children': stats['reused_children'],
                          'rollout_steps': stats['rollout_steps'],
                          'max_chance_width': kmax,
                          'progressive_widening': progressive,
                          'cpw': cpw, 'alpha': alpha, 'uct_c': c,
                          'engine_used': 'python_events_mirror'})


# =====================================================================
# 策略五：强化学习（复用 V5 的 rl_2048，只读模型）
# =====================================================================
def _rl_decision(grid, model_path=None, weights=None):
    path = model_path or rl_model_path()
    start = time.time()
    if not os.path.exists(path):
        return _result('rl', None, {}, 0, 0, start,
                       error='未找到强化学习模型（%s）。' % os.path.basename(path))
    try:
        import rl_2048
        net = _v5._load_rl_model_cached(path, rl_2048.load_model)
    except Exception as exc:                                # noqa: BLE001
        return _result('rl', None, {}, 0, 0, start,
                       error='加载强化学习模型失败：%s' % exc)

    probs = rl_2048.policy_probs(net, grid)
    moves = _v5.legal_moves(grid)
    evaluations = {}
    best_dir, best_p = None, -1.0
    for d in DIRECTIONS:
        if d not in moves:
            evaluations[d] = None
            continue
        p = float(probs.get(d, 0.0))
        evaluations[d] = round(p, 6)
        if p > best_p:
            best_p, best_dir = p, d
    return _result('rl', best_dir, evaluations, 1, len(DIRECTIONS), start,
                   extra={'model': os.path.basename(path), 'model_path': path})


# =====================================================================
# 对外主入口
# =====================================================================
def _error_result(strategy, message):
    return {
        'strategy': strategy, 'best_direction': None, 'best_name': '',
        'evaluations': {}, 'depth_reached': 0, 'nodes': 0,
        'elapsed_ms': 0.0, 'timed_out': False, 'error': message,
    }


def _run_strategy(be, grid, strategy, options, weights):
    """在给定后端上执行指定策略（纯函数，不做回退）。"""
    native_search = bool(options.get('native_search', False))
    if strategy == 'heuristic':
        return _heuristic_decision(be, grid, weights)
    if strategy == 'rollout':
        return _rollout_decision(
            be, grid,
            rollouts=int(options.get('rollouts', 20)),
            rollout_depth=int(options.get('rollout_depth', 16)),
            weights=weights,
            seed=int(options.get('seed', DEFAULT_SEED)),
            policy=str(options.get('rollout_policy', 'random')),
            epsilon=float(options.get('rollout_epsilon', 0.2)),
            paired=bool(options.get('paired', True)),
            native_rollout=bool(options.get('native_rollout', False)))
    if strategy == 'expectimax':
        # V6.2 原生整树（仅在精确语义配置下启用；近似模式不冒充精确结果）
        if (native_search and getattr(be, 'kind', '') == 'cpp'
                and _native_expectimax_applicable(options)):
            return _native_expectimax_decision(be, grid, options, weights)
        time_limit = max(0.001, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT))
        res = _expectimax_decision(
            be, grid, int(options.get('depth', 4)), time_limit, weights,
            prune=bool(options.get('prune', True)),
            sample_limit=options.get('sample_limit'),
            use_tt=bool(options.get('use_tt', True)),
            prob_cutoff=options.get('prob_cutoff'),
            move_order=bool(options.get('move_order', True)),
            seed=int(options.get('seed', DEFAULT_SEED)),
            score_weight=float(options.get('score_weight', 0.0)))
        if native_search:
            res['engine_used'] = 'python_kernel' if be.kind in ('numpy', 'numba', 'cpp') else 'reference'
            res['native_skip_reason'] = (
                'backend!=cpp' if getattr(be, 'kind', '') != 'cpp'
                else 'approximate config (sample_limit/prob_cutoff) 不受 native 精确引擎支持')
        return res
    if strategy == 'mcts':
        if native_search and getattr(be, 'kind', '') == 'cpp':
            return _native_mcts_decision(be, grid, options, weights)
        time_limit = max(0.001, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT))
        res = _mcts_decision(
            be, grid,
            simulations=int(options.get('simulations', 200)),
            time_limit=time_limit,
            rollout_depth=int(options.get('rollout_depth', 16)),
            weights=weights,
            seed=int(options.get('seed', DEFAULT_SEED)),
            c=float(options.get('c', 1.4)),
            max_chance_width=int(options.get('max_chance_width', 8)),
            trace=options.get('trace'),
            progressive_widening=bool(options.get('progressive_widening', False)),
            cpw=float(options.get('cpw', 1.0)),
            alpha=float(options.get('alpha', 0.5)))
        if native_search:
            res['engine_used'] = 'python_kernel' if be.kind in ('numpy', 'numba', 'cpp') else 'reference'
            res['native_skip_reason'] = 'backend!=cpp'
        return res
    if strategy == 'rl':
        return _rl_decision(grid, model_path=options.get('model_path'), weights=weights)
    return _error_result(strategy, '未知策略：%s' % strategy)


def solve(grid, strategy='expectimax', backend='auto', **options):
    """计算最佳方向；``backend`` 指定计算后端（auto/reference/numpy/numba/cpp）。

    位棋盘后端在搜索过程中遇到 >=65536 的方块会显式拒绝（BoardOverflowError），
    此时**显式回退到通用正确实现(reference)** 重算同一决策，并记录 backend_fallback_reason，
    绝不静默替换算法或截断数值。
    """
    backend_requested = backend
    try:
        grid = _api.validate_board(grid)
    except Exception as exc:                                # noqa: BLE001
        res = _error_result(strategy, '非法棋盘：%s' % exc)
        res['backend_requested'] = backend_requested
        res['backend_used'] = None
        res['engine_used'] = None
        return res

    weights = options.get('weights')
    # 分策略默认（H9-4）：对无端到端收益的策略（heuristic/rl）auto 走 reference，
    # 避免“cpp 全局一刀切”；rollout/expectimax/mcts 仍读 backend_default.json（cpp）。
    resolved = backend
    if backend in (None, 'auto') and strategy in ('heuristic', 'rl'):
        resolved = 'reference'
    be, backend_used, fallback_reason = get_backend(resolved, allow_fallback=True)

    try:
        no_moves = not be.legal_moves(grid)
    except _api.BoardOverflowError as ovf:
        # 预检查也要走同一溢出回退：位棋盘后端遇到 >=65536 时显式回退 reference（非静默替换）
        be, backend_used = get_backend('reference', allow_fallback=True)[0], 'reference'
        fallback_reason = 'BoardOverflow(%s) -> reference' % ovf
        no_moves = not be.legal_moves(grid)

    if no_moves:
        data = {
            'strategy': strategy, 'best_direction': None, 'best_name': '',
            'evaluations': {}, 'depth_reached': 0, 'nodes': 0,
            'elapsed_ms': 0.0, 'timed_out': False, 'error': None,
            'note': '无可行移动',
            'backend_requested': backend_requested,
            'backend_used': backend_used,
            'backend_fallback_reason': fallback_reason,
            'engine_used': 'none',       # 无可行方向：未执行任何搜索
            'backend_metrics': {'kind': be.kind},
        }
        return data

    try:
        res = _run_strategy(be, grid, strategy, options, weights)
    except _api.BoardOverflowError as ovf:
        # 位棋盘后端无法表示 >=65536：显式回退到参考实现重算（同一算法，非静默替换）
        be, backend_used = get_backend('reference', allow_fallback=True)[0], 'reference'
        fallback_reason = 'BoardOverflow(%s) -> reference' % ovf
        try:
            res = _run_strategy(be, grid, strategy, options, weights)
        except Exception as exc:                            # noqa: BLE001
            res = _heuristic_decision(be, grid, weights)
            res['strategy'] = strategy
            res['error'] = '%s: %s' % (type(exc).__name__, exc)
    except Exception as exc:                                # noqa: BLE001
        # 后端原语/原生调用异常：安全网必须改用 reference 重算，绝不在异常后端上二次失败；
        # 记录真实 backend_used/fallback_reason，不静默替换算法语义。
        be, backend_used = get_backend('reference', allow_fallback=True)[0], 'reference'
        fallback_reason = '%s(%s) -> reference' % (type(exc).__name__, exc)
        res = _heuristic_decision(be, grid, weights)
        res['strategy'] = strategy
        res['error'] = '%s: %s' % (type(exc).__name__, exc)

    res['backend_requested'] = backend_requested
    res['backend_used'] = backend_used
    res['backend_fallback_reason'] = fallback_reason
    # engine_used：区分「native 整树搜索」/「Python 搜索内核驱动后端原语」/「reference」
    if not res.get('engine_used'):
        if backend_used == 'reference' or getattr(be, 'kind', '') == 'python':
            res['engine_used'] = 'reference'
        else:
            res['engine_used'] = 'python_kernel'
    res.setdefault('board_signature', tuple(tuple(row) for row in grid))
    res['backend_metrics'] = {
        'kind': be.kind,
        'nodes': res.get('nodes'),
        'elapsed_ms': res.get('elapsed_ms'),
    }
    return res


def backend_status():
    """返回四后端可用性（供 GUI/报告展示）。"""
    return probe_backends()
