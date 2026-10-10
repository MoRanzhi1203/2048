#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048 求解算法核心（第 5 版）

与界面完全解耦：只对 4×4 网格（list[list[int]]）做纯函数运算，可单独导入测试。

包含：
    - 棋盘机制：移动 / 合并 / 胜负判定（与 v3 GameCore 的规则保持一致）
    - 启发式评估：空格 / 单调性 / 平滑度 / 合并潜力 / 最大块在角落
    - 两种策略：
        * heuristic   单步贪心（一次性取评估值最高的方向，代价极低）
        * expectimax  对“随机新方块”做期望分支的搜索（迭代加深 + 时间预算）
    - 超时机制：超过 time_limit 立即回退到已完成的深度，绝不长时间卡死
    - 异常安全：solve() 内部捕获异常，返回带 error 字段的结构化结果

对外主入口：
    solve(grid, strategy='expectimax', depth=4, time_limit=0.3, weights=None) -> dict
"""

import math
import time

DIRECTIONS = ('up', 'down', 'left', 'right')
DIRECTION_NAMES = {'up': '向上', 'down': '向下', 'left': '向左', 'right': '向右'}

# 策略与深度预设（界面下拉框直接使用这些 key）
STRATEGIES = {'heuristic': '启发式', 'expectimax': 'Expectimax'}
DEPTH_PRESETS = {
    'fast':   {'label': '快速', 'depth': 3, 'time_limit': 0.10},
    'normal': {'label': '标准', 'depth': 4, 'time_limit': 0.30},
    'strong': {'label': '强力', 'depth': 5, 'time_limit': 0.80},
}

# 启发式权重（可调；数值参考常见 Expectimax 2048 实现）
DEFAULT_WEIGHTS = {
    'empty': 2.7,          # 空格数
    'monotonicity': 1.0,   # 单调性
    'smoothness': 0.10,    # 平滑度
    'merge': 1.0,          # 合并潜力（相邻可合并对数）
    'corner': 0.30,        # 最大块在角落
}

# 单次求解的硬上限（即使调用方传入更大的 time_limit，也不会超过它）
MAX_TIME_LIMIT = 2.0


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


# =====================================================================
# 启发式评估
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
# 策略一：启发式单步贪心
# =====================================================================
def _heuristic_decision(grid, weights=None):
    start = time.time()
    evaluations = {}
    best_dir = None
    best_value = -float('inf')
    for d in DIRECTIONS:
        new_grid, _, moved = move_grid(grid, d)
        if not moved:
            evaluations[d] = None
            continue
        value = evaluate(new_grid, weights)
        evaluations[d] = value
        if value > best_value:
            best_value = value
            best_dir = d
    return {
        'strategy': 'heuristic',
        'best_direction': best_dir,
        'best_name': DIRECTION_NAMES.get(best_dir, ''),
        'evaluations': evaluations,
        'depth_reached': 1,
        'nodes': len(DIRECTIONS),
        'elapsed_ms': round((time.time() - start) * 1000.0, 3),
        'timed_out': False,
        'error': None,
    }


# =====================================================================
# 策略二：Expectimax（迭代加深 + 时间预算 + 异常安全）
# =====================================================================
def _expectimax_decision(grid, max_depth, time_limit, weights=None):
    start = time.time()
    ctx = {'nodes': 0, 'timed_out': False}

    def expired():
        return (time.time() - start) > time_limit

    def max_node(g, depth):
        if depth <= 0:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        if expired():
            ctx['timed_out'] = True
            ctx['nodes'] += 1
            return evaluate(g, weights)

        best = -float('inf')
        any_move = False
        for d in DIRECTIONS:
            new_grid, _, moved = move_grid(g, d)
            if not moved:
                continue
            any_move = True
            value = chance_node(new_grid, depth - 1)
            if value > best:
                best = value
            if ctx['timed_out']:
                break
        if not any_move:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        return best

    def chance_node(g, depth):
        if depth <= 0:
            ctx['nodes'] += 1
            return evaluate(g, weights)
        cells = empty_cells(g)
        if not cells:
            ctx['nodes'] += 1
            return evaluate(g, weights)

        total = 0.0
        size = len(g)
        for (i, j) in cells:
            for value, prob in ((2, 0.9), (4, 0.1)):
                if expired():
                    ctx['timed_out'] = True
                    ctx['nodes'] += 1
                    return evaluate(g, weights)
                child = [row[:] for row in g]
                child[i][j] = value
                total += prob * max_node(child, depth - 1)
        return total / len(cells)

    # 迭代加深：先完成浅层，超时则保留“最后一个完整跑完的深度”的结果
    best_result = None
    reached = 0
    for d in range(1, max_depth + 1):
        if expired():
            ctx['timed_out'] = True
            break
        evaluations = {}
        best_dir = None
        best_value = -float('inf')
        completed = True
        for direction in DIRECTIONS:
            new_grid, gain, moved = move_grid(grid, direction)
            if not moved:
                evaluations[direction] = None
                continue
            value = chance_node(new_grid, d - 1)
            if ctx['timed_out']:
                completed = False
                break
            evaluations[direction] = value
            if value > best_value:
                best_value = value
                best_dir = direction
        if completed and best_dir is not None:
            reached = d
            best_result = {
                'strategy': 'expectimax',
                'best_direction': best_dir,
                'best_name': DIRECTION_NAMES.get(best_dir, ''),
                'evaluations': evaluations,
                'depth_reached': reached,
                'nodes': ctx['nodes'],
                'elapsed_ms': round((time.time() - start) * 1000.0, 3),
                'timed_out': False,
                'error': None,
            }
        else:
            # 本层没跑完（超时）：不用它；若连第一层都没跑完则退化为贪心
            if best_result is None and best_dir is not None:
                best_result = {
                    'strategy': 'expectimax',
                    'best_direction': best_dir,
                    'best_name': DIRECTION_NAMES.get(best_dir, ''),
                    'evaluations': evaluations,
                    'depth_reached': 0,
                    'nodes': ctx['nodes'],
                    'elapsed_ms': round((time.time() - start) * 1000.0, 3),
                    'timed_out': True,
                    'error': None,
                }
            break
        if expired():
            ctx['timed_out'] = True
            break

    if best_result is None:
        fallback = _heuristic_decision(grid, weights)
        fallback.update({
            'strategy': 'expectimax',
            'timed_out': True,
            'depth_reached': 0,
            'elapsed_ms': round((time.time() - start) * 1000.0, 3),
        })
        return fallback

    best_result['timed_out'] = bool(ctx['timed_out'])
    best_result['nodes'] = ctx['nodes']
    best_result['elapsed_ms'] = round((time.time() - start) * 1000.0, 3)
    return best_result


# =====================================================================
# 对外主入口
# =====================================================================
def solve(grid, strategy='expectimax', depth=4, time_limit=0.3, weights=None):
    """
    计算当前局面下的最佳方向。

    :param grid: 4×4 网格（list[list[int]]）
    :param strategy: 'heuristic' | 'expectimax'
    :param depth: Expectimax 最大搜索深度（ply），超时会自动回退
    :param time_limit: 单次求解时间预算（秒），硬上限 MAX_TIME_LIMIT
    :param weights: 自定义启发式权重
    :return: 结构化结果 dict：
        {strategy, best_direction, best_name, evaluations, depth_reached,
         nodes, elapsed_ms, timed_out, error}
    """
    try:
        grid = _normalize(grid)
    except Exception as exc:                                    # noqa: BLE001
        return _error_result(strategy, '非法棋盘：%s' % exc)

    if not legal_moves(grid):
        return {
            'strategy': strategy,
            'best_direction': None,
            'best_name': '',
            'evaluations': {},
            'depth_reached': 0,
            'nodes': 0,
            'elapsed_ms': 0.0,
            'timed_out': False,
            'error': None,
            'note': '无可行移动',
        }

    time_limit = max(0.001, min(float(time_limit), MAX_TIME_LIMIT))

    try:
        if strategy == 'heuristic':
            return _heuristic_decision(grid, weights)
        return _expectimax_decision(grid, int(depth), time_limit, weights)
    except Exception as exc:                                    # noqa: BLE001
        # 求解异常绝不能影响界面：返回可用的兜底结果 + error 说明
        fallback = _heuristic_decision(grid, weights)
        fallback['error'] = '%s: %s' % (type(exc).__name__, exc)
        return fallback


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
        'strategy': strategy,
        'best_direction': None,
        'best_name': '',
        'evaluations': {},
        'depth_reached': 0,
        'nodes': 0,
        'elapsed_ms': 0.0,
        'timed_out': False,
        'error': message,
    }


if __name__ == '__main__':
    demo = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
    for strategy in ('heuristic', 'expectimax'):
        print(strategy, solve(demo, strategy=strategy, depth=4, time_limit=0.3))
