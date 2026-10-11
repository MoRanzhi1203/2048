#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 Reference 后端：冻结的 V5 行为适配器（**只读**复用 v5_pyqt_2048_solver/solver_2048.py）。

这是所有等价性判定的**对照基准**：它直接调用 V5 的纯 Python 实现，不做任何重写，
因此 V6 的 NumPy / Numba / C++ 内核都以它为准绳，而 reference 自身不参与“被加速”。

注意：本模块**不**用待测的 NumPy/Numba/C++ 函数构造 oracle；oracle 始终是 V5 源码。
"""

from __future__ import annotations

import os
import sys

from .api import BackendBase, MAX_EXP

_V6_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_V6_HERE))
_V5_DIR = os.path.join(_REPO_ROOT, 'v5_pyqt_2048_solver')

if _V5_DIR not in sys.path:
    sys.path.insert(0, _V5_DIR)

import solver_2048 as _v5            # noqa: E402  (冻结的 V5 参考实现)


class ReferenceBackend(BackendBase):
    name = 'reference'
    kind = 'python'
    supports_batch = False

    def __init__(self):
        self._v5 = _v5
        self.source = os.path.join('v5_pyqt_2048_solver', 'solver_2048.py')

    def available(self):
        return True, 'v5_pyqt_2048_solver/solver_2048.py (frozen reference)'

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps['source'] = self.source
        caps['rejects_oversize_tile'] = False     # 参考实现支持任意大数值（Python int）
        return caps

    # V5 的 DIRECTIONS / 权重 / 特征口径直接沿用，保证数值一致
    DIRECTIONS = _v5.DIRECTIONS
    DEFAULT_WEIGHTS = _v5.DEFAULT_WEIGHTS

    def move(self, board, direction):
        new_grid, gained, moved = self._v5.move_grid(board, direction)
        return new_grid, gained, moved

    def legal_moves(self, board):
        return tuple(self._v5.legal_moves(board))

    def evaluate(self, board, weights=None):
        return float(self._v5.evaluate(board, weights))

    def evaluate_features(self, board):
        return self._v5.evaluate_features(board)

    def empty_cells(self, board):
        return self._v5.empty_cells(board)

    def is_game_over(self, board):
        return bool(self._v5.is_game_over(board))

    def sample_spawn(self, board, rng, value=None):
        return self._v5.sample_spawn(board, rng, value)


# 供测试/基准直接使用的行级参考（V5 slide_line，作用于“方块值”列表）
def reference_slide_line(line):
    """V5 单行向左合并参考：返回 (新行, 得分)。"""
    return _v5.slide_line(line)


def reference_move_grid(board, direction):
    return _v5.move_grid(board, direction)


def v5_module():
    return _v5
