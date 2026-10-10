#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048 求解算法核心（第 5 版）

与界面完全解耦：只对 4×4 网格（list[list[int]]）做纯函数运算，可单独导入测试。

包含 5 类策略（对应《第 6 篇：经典算法求解 2048》的讲解顺序）：
    1) heuristic   规则 / 启发式策略（monotonicity、smoothness、max-in-corner …，单步贪心）
    2) rollout     贪心模拟 / 随机模拟（lookahead with rollout，低成本）
    3) expectimax  带期望的 minimax（对随机新方块做期望分支，含剪枝）
    4) mcts        Monte Carlo Tree Search（UCT + 渐进加宽 + rollout 截断）
    5) rl          强化学习（策略/价值网络，见 rl_2048.py；需先训练出模型）

统一能力：
    - 时间预算 / 迭代加深：超时立即回退到已完成结果，绝不长时间卡死
    - 剪枝：见 PRUNE 说明（转置表 / 空位采样 / 累积概率截断 / 移动排序 / 渐进加宽）
    - 确定性：同一局面 + 同参数 → 同结果（内部 RNG 使用固定种子）
    - 异常安全：solve() 内部捕获异常，返回带 error 字段的结构化结果

对外主入口（兼容旧签名）：
    solve(grid, strategy='expectimax', depth=4, time_limit=0.3, weights=None, **options) -> dict
    build_config(strategy, preset) -> dict        # 供界面下拉框使用
    describe_config(config) -> str
"""

import math
import os
import random
import time

DIRECTIONS = ('up', 'down', 'left', 'right')
DIRECTION_NAMES = {'up': '向上', 'down': '向下', 'left': '向左', 'right': '向右'}

# 单次求解的硬上限（即使调用方传入更大的 time_limit，也不会超过它）
MAX_TIME_LIMIT = 2.0

# 默认随机种子：保证「同局面 + 同参数」结果确定（便于复现与测试）
DEFAULT_SEED = 2048

# =====================================================================
# 策略注册表（界面下拉框直接使用这些 key / 文案 / 顺序）
# =====================================================================
STRATEGY_ORDER = ('heuristic', 'rollout', 'expectimax', 'mcts', 'rl')
STRATEGIES = {
    'heuristic': '启发式',
    'rollout': '贪心模拟',
    'expectimax': 'Expectimax',
    'mcts': 'MCTS',
    'rl': '强化学习',
}

PRESET_LABELS = {'fast': '快速', 'normal': '标准', 'strong': '强力'}
PRESET_ORDER = ('fast', 'normal', 'strong')

# 每种策略的强度预设（空 dict 表示该策略无可调参数）
STRATEGY_PRESETS = {
    'heuristic': {
        'fast': {}, 'normal': {}, 'strong': {},
    },
    'rollout': {
        'fast':   {'rollouts': 8,  'rollout_depth': 10},
        'normal': {'rollouts': 20, 'rollout_depth': 16},
        'strong': {'rollouts': 40, 'rollout_depth': 24},
    },
    'expectimax': {
        'fast':   {'depth': 3, 'time_limit': 0.10, 'prune': True, 'sample_limit': 6},
        'normal': {'depth': 4, 'time_limit': 0.30, 'prune': True, 'sample_limit': 8},
        'strong': {'depth': 6, 'time_limit': 0.80, 'prune': True, 'sample_limit': 10},
    },
    'mcts': {
        'fast':   {'simulations': 60,  'time_limit': 0.10, 'rollout_depth': 10},
        'normal': {'simulations': 200, 'time_limit': 0.30, 'rollout_depth': 16},
        'strong': {'simulations': 600, 'time_limit': 0.80, 'rollout_depth': 24},
    },
    'rl': {
        'fast': {}, 'normal': {}, 'strong': {},
    },
}

# 需要“强度”参数的策略（界面上仅这些策略启用强度下拉框）
PARAMETRIC_STRATEGIES = ('rollout', 'expectimax', 'mcts')

# 剪枝默认参数（Expectimax）
PRUNE_DEFAULTS = {
    'use_tt': True,        # 转置表：相同局面+深度直接复用估值
    'sample_limit': 8,     # 空位采样的上限（空位多于它时只取这些，控制分支爆炸）
    'prob_cutoff': 0.08,   # 累积概率截断：路径概率低于它且已较深时用启发式估值外推
    'move_order': True,    # 移动排序：先探索启发式估值高的方向（利于早停与根节点比较）
}

# 启发式权重（可调；数值参考常见 Expectimax 2048 实现）
DEFAULT_WEIGHTS = {
    'empty': 2.7,          # 空格数
    'monotonicity': 1.0,   # 单调性
    'smoothness': 0.10,    # 平滑度
    'merge': 1.0,          # 合并潜力（相邻可合并对数）
    'corner': 0.30,        # 最大块在角落
}

RL_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rl_model.npz')


# =====================================================================
# 棋盘机制（规则与 v3 GameCore 一致：每次移动每个方块最多参与一次合并）
# =====================================================================
def empty_cells(grid):
    """返回所有空格坐标列表 [(r, c), ...]"""
    return [(i, j) for i, row in enumerate(grid)
            for j, v in enumerate(row) if v == 0]


def max_tile(grid):
    return max((max(row) for row in grid), default=0)


def is_game_over(grid):
    """无空格且四邻无相同数字 => 结束"""
    if empty_cells(grid):
        return False
    size = len(grid)
    for i in range(size):
        for j in range(size):
            if j + 1 < size and grid[i][j] == grid[i][j + 1]:
                return False
            if i + 1 < size and grid[i][j] == grid[i + 1][j]:
                return False
    return True


def slide_line(line):
    """单行向左合并：返回 (新行, 本行得分)。"""
    size = len(line)
    compressed = [v for v in line if v != 0]
    merged = []
    gained = 0
    i = 0
    while i < len(compressed):
        if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
            value = compressed[i] * 2
            merged.append(value)
            gained += value
            i += 2
        else:
            merged.append(compressed[i])
            i += 1
    merged += [0] * (size - len(merged))
    return merged, gained


def move_grid(grid, direction):
    """在网格副本上执行一次移动，返回 (新网格, 获得分数, 是否移动)。不修改入参。"""
    size = len(grid)
    work = [list(row) for row in grid]
    if direction in ('up', 'down'):
        work = [list(row) for row in zip(*work)]

    gained = 0
    for i in range(size):
        row = work[i][::-1] if direction in ('right', 'down') else work[i]
        new_row, g = slide_line(row)
        if direction in ('right', 'down'):
            new_row.reverse()
        work[i] = new_row
        gained += g

    if direction in ('up', 'down'):
        work = [list(row) for row in zip(*work)]

    moved = work != [list(row) for row in grid]
    return work, gained, moved


def legal_moves(grid):
    """返回当前可执行（会发生移动）的方向列表"""
    result = []
    for d in DIRECTIONS:
        _, _, moved = move_grid(grid, d)
        if moved:
            result.append(d)
    return result


def spawn(grid, rng, value=None):
    """在随机空位生成一个新方块（90% 2 / 10% 4）；返回新网格（不修改入参）。"""
    cells = empty_cells(grid)
    if not cells:
        return [row[:] for row in grid]
    i, j = rng.choice(cells)
    if value is None:
        value = 2 if rng.random() < 0.9 else 4
    new_grid = [row[:] for row in grid]
    new_grid[i][j] = value
    return new_grid


# =====================================================================
# 启发式评估（权重 · 单元特征）
# =====================================================================
def _log2(v):
    return 0.0 if v <= 0 else math.log2(v)


def _monotonicity(grid):
    """行 / 列上“单调递减或单调递增”的程度，越接近 0 越好。"""
    size = len(grid)
    total = 0.0
    for i in range(size):
        inc = dec = 0.0
        for j in range(size - 1):
            a, b = _log2(grid[i][j]), _log2(grid[i][j + 1])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        total += max(inc, dec)

        inc = dec = 0.0
        for j in range(size - 1):
            a, b = _log2(grid[j][i]), _log2(grid[j + 1][i])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        total += max(inc, dec)
    return total


def _smoothness(grid):
    """相邻非空块的 log2 差值之和（取负），越接近 0 越平滑。"""
    size = len(grid)
    total = 0.0
    for i in range(size):
        for j in range(size):
            if grid[i][j] == 0:
                continue
            v = _log2(grid[i][j])
            if j + 1 < size and grid[i][j + 1] != 0:
                total -= abs(v - _log2(grid[i][j + 1]))
            if i + 1 < size and grid[i + 1][j] != 0:
                total -= abs(v - _log2(grid[i + 1][j]))
    return total


def _merge_potential(grid):
    """相邻可合并对数（越多越好）。"""
    size = len(grid)
    count = 0
    for i in range(size):
        for j in range(size):
            if grid[i][j] == 0:
                continue
            if j + 1 < size and grid[i][j] == grid[i][j + 1]:
                count += 1
            if i + 1 < size and grid[i][j] == grid[i + 1][j]:
                count += 1
    return count


def _max_in_corner(grid):
    """最大块位于四角时给出 log2(最大值) 奖励，否则 0。"""
    mt = max_tile(grid)
    if mt == 0:
        return 0.0
    size = len(grid)
    corners = {(0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)}
    for (i, j) in corners:
        if grid[i][j] == mt:
            return _log2(mt)
    return 0.0


def evaluate(grid, weights=None):
    """启发式综合打分：权重 · 特征。分数越高代表局面越好。"""
    w = weights or DEFAULT_WEIGHTS
    return (w['empty'] * len(empty_cells(grid))
            + w['monotonicity'] * _monotonicity(grid)
            + w['smoothness'] * _smoothness(grid)
            + w['merge'] * _merge_potential(grid)
            + w['corner'] * _max_in_corner(grid))


def evaluate_features(grid):
    """返回各特征分项，便于在界面上解释“为什么这么走”。"""
    return {
        'empty': len(empty_cells(grid)),
        'monotonicity': round(_monotonicity(grid), 3),
        'smoothness': round(_smoothness(grid), 3),
        'merge': _merge_potential(grid),
        'corner': round(_max_in_corner(grid), 3),
        'max_tile': max_tile(grid),
    }


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


def _ordered_moves(grid, weights, order=True):
    """返回 (方向, 移动后网格, 获得分数) 列表；order=True 时按单步启发式估值降序。"""
    items = []
    for d in DIRECTIONS:
        new_grid, gain, moved = move_grid(grid, d)
        if moved:
            items.append((d, new_grid, gain))
    if order:
        items.sort(key=lambda it: evaluate(it[1], weights), reverse=True)
    return items


# =====================================================================
# 策略一：规则 / 启发式（单步贪心）
# =====================================================================
def _heuristic_decision(grid, weights=None):
    start = time.time()
    evaluations = {}
    best_dir, best_value = None, -float('inf')
    for d in DIRECTIONS:
        new_grid, _, moved = move_grid(grid, d)
        if not moved:
            evaluations[d] = None
            continue
        value = evaluate(new_grid, weights)
        evaluations[d] = value
        if value > best_value:
            best_value, best_dir = value, d
    return _result('heuristic', best_dir, evaluations, 1, len(DIRECTIONS), start)


# =====================================================================
# 策略二：贪心模拟 / 随机模拟（lookahead with rollout，低成本）
# =====================================================================
def _rollout_score(grid_after_move, gained, depth, weights, rng):
    """从“移动后、尚未生成新块”的盘面做一次随机 rollout，返回累计收益。"""
    g = grid_after_move
    score = gained
    for _ in range(depth):
        if is_game_over(g):
            break
        g = spawn(g, rng)                     # 随机生成新方块
        if is_game_over(g):
            break
        moves = legal_moves(g)
        if not moves:
            break
        g, gain, _ = move_grid(g, rng.choice(moves))
        score += gain
    return score + evaluate(g, weights)        # 累计得分 + 终局启发式估值


def _rollout_decision(grid, rollouts=20, rollout_depth=16, weights=None, seed=DEFAULT_SEED):
    start = time.time()
    rng = random.Random(seed)
    nodes = 0
    evaluations = {}
    best_dir, best_value = None, -float('inf')
    for d, after_move, gain in _ordered_moves(grid, weights, order=True):
        total = 0.0
        for _ in range(max(1, rollouts)):
            total += _rollout_score(after_move, gain, max(1, rollout_depth), weights, rng)
            nodes += 1
        value = total / max(1, rollouts)
        evaluations[d] = value
        if value > best_value:
            best_value, best_dir = value, d
    return _result('rollout', best_dir, evaluations, max(1, rollout_depth), nodes, start,
                   extra={'rollouts': rollouts})


# =====================================================================
# 策略三：Expectimax（迭代加深 + 时间预算 + 剪枝）
# =====================================================================
def _expectimax_decision(grid, max_depth, time_limit, weights=None, prune=True,
                         sample_limit=None, use_tt=True, prob_cutoff=None,
                         move_order=True, seed=DEFAULT_SEED):
    """带期望分支的搜索；prune=True 时启用四类剪枝（见 PRUNE_DEFAULTS）。

    剪枝思路：
        1) 转置表(TT)：相同盘面 + 相同剩余深度只算一次（去重，收益最大）；
        2) 空位采样：空位多于 sample_limit 时，只按固定种子随机取 sample_limit 个位置
           展开（分支从 2E 降到 2·sample_limit），是有偏但可控的近似；
        3) 累积概率截断：沿路径累积概率 < prob_cutoff 的深层子树，直接用启发式估值外推；
        4) 移动排序：max 节点先探索启发式估值高的方向，配合时间预算优先得到好结果。
    """
    start = time.time()
    ctx = {'nodes': 0, 'timed_out': False}
    tt = {}
    rng = random.Random(seed)
    if sample_limit is None:
        sample_limit = PRUNE_DEFAULTS['sample_limit']
    if prob_cutoff is None:
        prob_cutoff = PRUNE_DEFAULTS['prob_cutoff']

    def expired():
        return (time.time() - start) > time_limit

    def key(g, depth, kind):
        return (tuple(tuple(row) for row in g), depth, kind)

    def max_node(g, depth):
        if depth <= 0:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        if expired():
            ctx['timed_out'] = True
            ctx['nodes'] += 1
            return evaluate(g, weights)
        if prune and use_tt:
            k = key(g, depth, 'max')
            hit = tt.get(k)
            if hit is not None:
                return hit

        best = -float('inf')
        any_move = False
        for _d, new_grid, _gain in _ordered_moves(g, weights, order=(prune and move_order)):
            any_move = True
            value = chance_node(new_grid, depth - 1, 1.0)
            if value > best:
                best = value
            if ctx['timed_out']:
                break
        if not any_move:
            best = evaluate(g, weights)
        if prune and use_tt:
            tt[key(g, depth, 'max')] = best
        return best

    def chance_node(g, depth, path_prob):
        if depth <= 0:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        if prune and path_prob < prob_cutoff:
            ctx['nodes'] += 1
            return evaluate(g, weights)          # 概率过低的深层分支：启发式外推
        if expired():
            ctx['timed_out'] = True
            ctx['nodes'] += 1
            return evaluate(g, weights)

        cells = empty_cells(g)
        if not cells:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        if prune and use_tt:
            k = key(g, depth, 'chance')
            hit = tt.get(k)
            if hit is not None:
                return hit

        if prune and len(cells) > sample_limit:
            cells = rng.sample(cells, sample_limit)   # 空位采样（位置剪枝）

        total = 0.0
        for (i, j) in cells:
            for value, prob in ((2, 0.9), (4, 0.1)):
                if expired():
                    ctx['timed_out'] = True
                    ctx['nodes'] += 1
                    return evaluate(g, weights)
                child = [row[:] for row in g]
                child[i][j] = value
                total += prob * max_node(child, depth - 1)
                if prune and path_prob * prob < prob_cutoff:
                    # 该分支后续会被截断：用启发式估值近似其子价值，避免继续展开
                    continue
        result = total / len(cells)
        if prune and use_tt:
            tt[key(g, depth, 'chance')] = result
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
        for direction, new_grid, _gain in _ordered_moves(grid, weights, order=(prune and move_order)):
            value = chance_node(new_grid, d - 1, 1.0)
            if ctx['timed_out']:
                completed = False
                break
            evaluations[direction] = value
            if value > best_value:
                best_value, best_dir = value, direction
        for direction in DIRECTIONS:                 # 非法方向补 None，保持结构一致
            evaluations.setdefault(direction, None)

        if completed and best_dir is not None:
            reached = d
            best_result = _result('expectimax', best_dir, evaluations, reached,
                                  ctx['nodes'], start, extra={'pruned': bool(prune)})
        else:
            if best_result is None and best_dir is not None:
                best_result = _result('expectimax', best_dir, evaluations, 0,
                                      ctx['nodes'], start, timed_out=True,
                                      extra={'pruned': bool(prune)})
            break
        if expired():
            ctx['timed_out'] = True
            break

    if best_result is None:
        fallback = _heuristic_decision(grid, weights)
        fallback.update({'strategy': 'expectimax', 'timed_out': True, 'depth_reached': 0,
                         'elapsed_ms': round((time.time() - start) * 1000.0, 3),
                         'pruned': bool(prune)})
        return fallback

    best_result['timed_out'] = bool(ctx['timed_out'])
    best_result['nodes'] = ctx['nodes']
    best_result['elapsed_ms'] = round((time.time() - start) * 1000.0, 3)
    if prune:
        best_result['tt_entries'] = len(tt)
    return best_result


# =====================================================================
# 策略四：MCTS（UCT + 渐进加宽 + rollout 截断）
# =====================================================================
class _MCTSNode(object):
    __slots__ = ('grid', 'is_max', 'parent', 'move', 'children', 'visits',
                 'value', 'untried')

    def __init__(self, grid, is_max, parent=None, move=None, untried=None):
        self.grid = grid
        self.is_max = is_max
        self.parent = parent
        self.move = move
        self.children = []
        self.visits = 0
        self.value = 0.0
        self.untried = untried


def _mcts_decision(grid, simulations=200, time_limit=0.3, rollout_depth=16,
                   weights=None, seed=DEFAULT_SEED, c=1.4, max_chance_width=8):
    """UCT 搜索：max 节点用 UCB1 选择，chance 节点均匀采样（无偏估计期望）。

    剪枝/近似：
        - 渐进加宽：chance 节点最多展开 max_chance_width 个“空位×数值”子节点；
        - rollout 截断：模拟深度上限 rollout_depth；
        - 模拟次数 + 时间双预算。
    """
    start = time.time()
    rng = random.Random(seed)
    nodes_counter = {'n': 0}

    def ucb(parent, child):
        if child.visits == 0:
            return float('inf')
        return child.value / child.visits + c * math.sqrt(
            math.log(max(1, parent.visits)) / child.visits)

    def select(node):
        while True:
            if node.is_max:
                if node.untried:
                    d = node.untried.pop(0)
                    child_grid, _gain, _moved = move_grid(node.grid, d)
                    child = _MCTSNode(child_grid, False, node, d, untried=None)
                    node.children.append(child)
                    return child
                if not node.children:
                    return node
                node = max(node.children, key=lambda ch: ucb(node, ch))
            else:
                # chance 节点：均匀采样子节点（无偏估计期望）
                if len(node.children) < max_chance_width:
                    cells = empty_cells(node.grid)
                    if not cells:
                        return node
                    i, j = rng.choice(cells)
                    value = 2 if rng.random() < 0.9 else 4
                    child_grid = [row[:] for row in node.grid]
                    child_grid[i][j] = value
                    child = _MCTSNode(child_grid, True, node, None,
                                      untried=_ordered_dirs(child_grid, weights))
                    node.children.append(child)
                    return child
                return rng.choice(node.children)

    def rollout(node):
        g = node.grid
        score = 0.0
        for _ in range(max(1, rollout_depth)):
            if is_game_over(g):
                break
            moves = legal_moves(g)
            if not moves:
                break
            g, gain, _ = move_grid(g, rng.choice(moves))
            score += gain
            g = spawn(g, rng)
        return score + evaluate(g, weights)

    root = _MCTSNode([row[:] for row in grid], True, untried=_ordered_dirs(grid, weights))
    sims = 0
    while sims < max(1, simulations) and (time.time() - start) <= time_limit:
        leaf = select(root)
        value = rollout(leaf)
        nodes_counter['n'] += 1
        node = leaf
        while node is not None:
            node.visits += 1
            node.value += value
            node = node.parent
        sims += 1

    evaluations = {}
    best_dir, best_value = None, -float('inf')
    for child in root.children:
        if child.visits == 0:
            continue
        mean = child.value / child.visits
        evaluations[child.move] = mean
        if mean > best_value:
            best_value, best_dir = mean, child.move
    for d in DIRECTIONS:
        evaluations.setdefault(d, None)

    timed_out = sims < max(1, simulations)
    return _result('mcts', best_dir, evaluations, rollout_depth, nodes_counter['n'], start,
                   timed_out=timed_out, extra={'simulations': sims})


def _ordered_dirs(grid, weights):
    """max 节点的候选移动顺序（启发式降序），用作 MCTS 的优先展开顺序。"""
    return [d for d, _g, _gain in _ordered_moves(grid, weights, order=True)]


# =====================================================================
# 策略五：强化学习（策略/价值网络，模型由 rl_2048.py 训练）
# =====================================================================
def _rl_decision(grid, model_path=None, weights=None):
    path = model_path or RL_MODEL_PATH
    start = time.time()
    if not os.path.exists(path):
        return _result('rl', None, {}, 0, 0, start,
                       error='未找到强化学习模型（%s）。请先运行 train_rl_2048.py 训练。'
                             % os.path.basename(path))
    try:
        import rl_2048                                   # 延迟导入（仅 RL 需要 numpy）
        net = rl_2048.load_model(path)
    except Exception as exc:                             # noqa: BLE001
        return _result('rl', None, {}, 0, 0, start,
                       error='加载强化学习模型失败：%s' % exc)

    probs = rl_2048.policy_probs(net, grid)              # {direction: probability}
    moves = legal_moves(grid)
    evaluations = {}
    best_dir, best_p = None, -1.0
    for d in DIRECTIONS:                                 # 固定顺序 -> 平局确定性
        if d not in moves:
            evaluations[d] = None
            continue
        p = float(probs.get(d, 0.0))
        evaluations[d] = round(p, 6)
        if p > best_p:
            best_p, best_dir = p, d
    return _result('rl', best_dir, evaluations, 1, len(DIRECTIONS), start,
                   extra={'model': os.path.basename(path)})


# =====================================================================
# 对外主入口
# =====================================================================
def solve(grid, strategy='expectimax', **options):
    """
    计算当前局面下的最佳方向。

    :param grid: 4×4 网格（list[list[int]]）
    :param strategy: heuristic | rollout | expectimax | mcts | rl
    :param options: 策略参数（depth / time_limit / simulations / rollouts / weights …）
    :return: 结构化结果 dict：
        {strategy, best_direction, best_name, evaluations, depth_reached,
         nodes, elapsed_ms, timed_out, error, …}
    """
    try:
        grid = _normalize(grid)
    except Exception as exc:                                    # noqa: BLE001
        return _error_result(strategy, '非法棋盘：%s' % exc)

    weights = options.get('weights')

    if not legal_moves(grid):
        return {
            'strategy': strategy, 'best_direction': None, 'best_name': '',
            'evaluations': {}, 'depth_reached': 0, 'nodes': 0,
            'elapsed_ms': 0.0, 'timed_out': False, 'error': None,
            'note': '无可行移动',
        }

    try:
        if strategy == 'heuristic':
            return _heuristic_decision(grid, weights)
        if strategy == 'rollout':
            return _rollout_decision(
                grid,
                rollouts=int(options.get('rollouts', 20)),
                rollout_depth=int(options.get('rollout_depth', 16)),
                weights=weights,
                seed=int(options.get('seed', DEFAULT_SEED)))
        if strategy == 'expectimax':
            time_limit = max(0.001, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT))
            return _expectimax_decision(
                grid, int(options.get('depth', 4)), time_limit, weights,
                prune=bool(options.get('prune', True)),
                sample_limit=options.get('sample_limit'),
                prob_cutoff=options.get('prob_cutoff'),
                seed=int(options.get('seed', DEFAULT_SEED)))
        if strategy == 'mcts':
            time_limit = max(0.001, min(float(options.get('time_limit', 0.3)), MAX_TIME_LIMIT))
            return _mcts_decision(
                grid,
                simulations=int(options.get('simulations', 200)),
                time_limit=time_limit,
                rollout_depth=int(options.get('rollout_depth', 16)),
                weights=weights,
                seed=int(options.get('seed', DEFAULT_SEED)))
        if strategy == 'rl':
            return _rl_decision(grid, model_path=options.get('model_path'), weights=weights)
        return _error_result(strategy, '未知策略：%s' % strategy)
    except Exception as exc:                                    # noqa: BLE001
        # 求解异常绝不能影响界面：返回可用的兜底结果 + error 说明
        fallback = _heuristic_decision(grid, weights)
        fallback['strategy'] = strategy
        fallback['error'] = '%s: %s' % (type(exc).__name__, exc)
        return fallback


def build_config(strategy, preset):
    """按（策略, 强度）生成 solve() 的参数字典（供界面下拉框直接使用）。"""
    params = dict(STRATEGY_PRESETS.get(strategy, {}).get(preset, {}))
    config = {'strategy': strategy}
    config.update(params)
    return config


def has_presets(strategy):
    """该策略是否存在可调强度（决定界面“强度”下拉框是否可用）。"""
    return strategy in PARAMETRIC_STRATEGIES


def describe_config(config):
    """把配置翻译成简短中文描述（用于界面状态与日志）。"""
    strategy = config.get('strategy')
    if strategy == 'heuristic':
        return '单步贪心'
    if strategy == 'rollout':
        return 'rollout×%s' % config.get('rollouts', '?')
    if strategy == 'expectimax':
        return '深度=%s%s' % (config.get('depth', '?'),
                             '/剪枝' if config.get('prune', True) else '')
    if strategy == 'mcts':
        return '模拟=%s' % config.get('simulations', '?')
    if strategy == 'rl':
        return '策略网络'
    return str(strategy)


def _normalize(grid):
    """校验并规范化网格：必须是方阵、数值为非负整数"""
    if not grid or not isinstance(grid, (list, tuple)):
        raise ValueError('网格为空')
    size = len(grid)
    result = []
    for row in grid:
        if not isinstance(row, (list, tuple)) or len(row) != size:
            raise ValueError('网格必须是方阵')
        result.append([int(v) for v in row])
    return result


def _error_result(strategy, message):
    return {
        'strategy': strategy, 'best_direction': None, 'best_name': '',
        'evaluations': {}, 'depth_reached': 0, 'nodes': 0,
        'elapsed_ms': 0.0, 'timed_out': False, 'error': message,
    }


if __name__ == '__main__':
    demo = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
    for _s in STRATEGY_ORDER:
        _cfg = build_config(_s, 'normal')
        _cfg['time_limit'] = 0.3
        print('%-11s %s' % (_s, solve(demo, **_cfg)))
