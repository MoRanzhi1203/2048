#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C++ Bitboard 后端的 Python 适配层（把 pybind11 扩展映射到统一 Backend 协议）。"""

from __future__ import annotations

from .api import (BackendBase, BoardOverflowError, InvalidBoardError, DIRECTIONS,
                  LIMIT_TILE)


def _flatten(board):
    return [int(board[r][c]) for r in range(4) for c in range(4)]


def _unflatten(flat):
    return [[int(flat[r * 4 + c]) for c in range(4)] for r in range(4)]


class CppBitboardBackend(BackendBase):
    name = 'cpp'
    kind = 'cpp'
    supports_batch = True
    supports_native_rollout = True

    def __init__(self, mod):
        if mod is None:
            raise RuntimeError('bitboard_cpp 扩展未构建')
        self.m = mod

    def available(self):
        return True, 'bitboard_cpp (C++20/pybind11, 4bit 指数)'

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps['row_table'] = True
        caps['row_table_entries'] = 65536
        caps['max_tile_exp'] = int(self.m.MAX_EXP)
        caps['rejects_oversize_tile'] = True
        return caps

    # ---- 单盘原语 ----
    def move(self, board, direction):
        if direction not in DIRECTIONS:
            raise InvalidBoardError('未知方向：%r' % (direction,))
        try:
            nv, score, changed = self.m.move(_flatten(board), direction)
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))
        return _unflatten(nv), int(score), bool(changed)

    def legal_moves(self, board):
        try:
            return tuple(self.m.legal_moves(_flatten(board)))
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))

    def evaluate(self, board, weights=None):
        from .numpy_core import _weight_array
        w = _weight_array(weights).tolist()
        try:
            return float(self.m.evaluate(_flatten(board), w))
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))

    def evaluate_features(self, board):
        from .numpy_core import NumpyBackend
        return NumpyBackend().evaluate_features(board)

    def empty_cells(self, board):
        return [(r, c) for r in range(4) for c in range(4) if board[r][c] == 0]

    def is_game_over(self, board):
        for r in range(4):
            for c in range(4):
                if board[r][c] == 0:
                    return False
        for r in range(4):
            for c in range(3):
                if board[r][c] == board[r][c + 1]:
                    return False
        for c in range(4):
            for r in range(3):
                if board[r][c] == board[r + 1][c]:
                    return False
        return True

    def sample_spawn(self, board, rng, value=None):
        cells = self.empty_cells(board)
        if not cells:
            return [row[:] for row in board], None, 0
        i, j = rng.choice(cells)
        if value is None:
            value = 2 if rng.random() < 0.9 else 4
        nb = [row[:] for row in board]
        nb[i][j] = value
        return nb, (i, j), value

    # ---- 批量（一次性跨边界） ----
    def batch_move(self, boards, direction):
        flats = [_flatten(b) for b in boards]
        try:
            outs, scores, changed = self.m.batch_move(flats, direction)
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))
        return [(_unflatten(o), int(s), bool(ch)) for o, s, ch in zip(outs, scores, changed)]

    # ---- 原生整段 rollout（把完整 N 步模拟下沉到 C++，消费显式事件流） ----
    def rollout_events(self, board, gained, depth, cell_ev, value_ev, move_ev, weights=None):
        """单次 rollout：与 Python 事件流驱动 rollout_py 在同一事件流下逐位一致。"""
        from .numpy_core import _weight_array
        w = _weight_array(weights).tolist()
        try:
            return float(self.m.rollout_events(_flatten(board), int(gained), int(depth),
                                               cell_ev, value_ev, move_ev, w))
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))

    def rollout_batch(self, board, gained, depth, n_rollouts,
                      cell_ev, value_ev, move_ev, weights=None):
        """一次 API 调用完成一组 rollout（共享事件流游标），降低跨边界调用次数。"""
        from .numpy_core import _weight_array
        w = _weight_array(weights).tolist()
        try:
            return [float(x) for x in self.m.rollout_batch(
                _flatten(board), int(gained), int(depth), int(n_rollouts),
                cell_ev, value_ev, move_ev, w)]
        except self.m.BoardOverflowError as e:
            raise BoardOverflowError(str(e))
