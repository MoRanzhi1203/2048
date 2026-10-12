#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 无头（Headless）当前对局核心 —— **不导入任何 Qt / GUI**。

依赖：仅标准库 + `solver_2048`（纯 Python，无 Qt）与 `solver_v6`（计算层，无 Qt）。
规则与 V6 正式程序一致：
    - 移动/合并/得分：`solver_2048.move_grid`（与 V3/V4/V5 模型同规则）
    - 生成新方块：`solver_2048.sample_spawn`（行主序空位 + `rng.choice` + `rng.random()<0.9`），
      与模型 `add_new_tile` 的抽取顺序一致（90% 生成 2，10% 生成 4）
    - 随机数：使用**显式 Random 实例**，其状态可从 `random.getstate()` 无损往返，
      确保后台求解基于“当前真实 RNG 位置”，而不是只传 seed
"""

from __future__ import annotations

import json
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
V5_DIR = os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')
for _p in (V5_DIR, V6_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import solver_2048 as S                                              # noqa: E402  (纯 Python)

SNAPSHOT_SCHEMA = 1
MAX_TILE_LIMIT = 65536          # >= 该值：位棋盘/规则安全上限，需回退


class SnapshotError(ValueError):
    """快照非法（形状/编码/分数/修订号/状态版本）。"""


# ------------------------------------------------------------------ RNG 状态
def rng_state_to_json(state):
    """`random.getstate()` -> JSON 可序列化结构（无损）。"""
    version, keys, gauss = state
    return {'version': int(version), 'keys': list(keys), 'gauss_next': gauss}


def rng_state_from_json(data):
    return (int(data['version']), tuple(int(k) for k in data['keys']), data.get('gauss_next'))


def make_rng(state_json=None, seed=None):
    rng = random.Random()
    if state_json is not None:
        rng.setstate(rng_state_from_json(state_json))
    elif seed is not None:
        rng.seed(int(seed))
    return rng


# ------------------------------------------------------------------ 棋盘工具
def validate_board(board, size=4):
    if not isinstance(board, (list, tuple)) or len(board) != size:
        raise SnapshotError('棋盘行数非法：%r' % (board,))
    out = []
    for row in board:
        if not isinstance(row, (list, tuple)) or len(row) != size:
            raise SnapshotError('棋盘列数非法：%r' % (row,))
        r = []
        for v in row:
            if isinstance(v, bool) or not isinstance(v, int):
                raise SnapshotError('方块取值非法（须为整数）：%r' % (v,))
            if v != 0 and (v & (v - 1)) != 0:
                raise SnapshotError('方块不是 2 的幂：%r' % (v,))
            if v < 0 or v >= MAX_TILE_LIMIT:
                raise SnapshotError('方块超出安全上限 %d：%r' % (MAX_TILE_LIMIT, v))
            r.append(int(v))
        out.append(r)
    return out


def empty_cells(board):
    n = len(board)
    return [(i, j) for i in range(n) for j in range(n) if board[i][j] == 0]


def max_tile(board):
    return max((max(r) for r in board), default=0)


def is_game_over(board):
    return S.is_game_over(board)


def legal_moves(board):
    return S.legal_moves(board)


def overflow_risk(board):
    """是否存在 >= 65536 的合并风险（需要整体回退 reference）。"""
    return max_tile(board) >= MAX_TILE_LIMIT


# ------------------------------------------------------------------ 单步
def spawn(board, rng):
    """生成一个新方块；返回 (new_board, (i,j), value)（不改入参）。"""
    return S.sample_spawn(board, rng)


def apply_move(board, direction, rng):
    """执行一次移动 + 恰好一次生成；返回 dict（不改入参）。

    返回：{board, gained, moved, spawn, spawn_pos, score_delta}
    """
    new_board, gained, moved = S.move_grid(board, direction)
    if not moved:
        return {'board': [row[:] for row in board], 'gained': 0, 'moved': False,
                'spawn': None, 'spawn_pos': None}
    spawned, pos, value = spawn(new_board, rng)
    return {'board': spawned, 'gained': int(gained), 'moved': True,
            'spawn': value, 'spawn_pos': list(pos) if pos else None}


# ------------------------------------------------------------------ 快照
def build_snapshot(board, score, best_score, rng_state_json, game_id, revision,
                   algorithm, strength, solver_mode='auto', state_version=SNAPSHOT_SCHEMA,
                   game_over=False):
    return {
        'schema': SNAPSHOT_SCHEMA,
        'state_version': int(state_version),
        'game_id': str(game_id),
        'revision': int(revision),
        'board': validate_board(board),
        'score': int(score),
        'best_score': int(best_score),
        'game_over': bool(game_over),
        'rng_state': rng_state_json,
        'algorithm': str(algorithm),
        'strength': str(strength),
        'solver_mode': str(solver_mode),
    }


def validate_snapshot(snap):
    if not isinstance(snap, dict):
        raise SnapshotError('快照不是字典')
    if int(snap.get('schema', -1)) != SNAPSHOT_SCHEMA:
        raise SnapshotError('快照 schema 不匹配：%r' % snap.get('schema'))
    if 'rng_state' not in snap or not isinstance(snap['rng_state'], dict):
        raise SnapshotError('缺少可序列化的 RNG 状态')
    rng_state_from_json(snap['rng_state'])          # 校验能还原
    board = validate_board(snap.get('board'))
    if int(snap.get('score', 0)) < 0:
        raise SnapshotError('分数为负')
    if int(snap.get('revision', -1)) < 0:
        raise SnapshotError('修订号非法')
    if snap['algorithm'] not in S.STRATEGY_ORDER:
        raise SnapshotError('未知算法：%r' % snap['algorithm'])
    if snap['strength'] not in S.PRESET_ORDER:
        raise SnapshotError('未知求解强度：%r' % snap['strength'])
    out = dict(snap)
    out['board'] = board
    return out


def snapshot_to_json(snap):
    return json.dumps(snap, ensure_ascii=False, separators=(',', ':'))


def snapshot_from_json(text):
    return validate_snapshot(json.loads(text))


# ------------------------------------------------------------------ 求解选项
def solver_options(strategy, strength, backend=None, native_search=False, seed=None):
    """复用 V5 `build_config` 生成与 GUI 完全一致的参数（算法/强度），再叠加后端选择。"""
    opts = dict(S.build_config(strategy, strength))
    if backend:
        opts['backend'] = backend
    if native_search:
        opts['native_search'] = True
    if seed is not None:
        opts['seed'] = int(seed)
    return opts
