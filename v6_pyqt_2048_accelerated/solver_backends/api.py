#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 统一后端协议、错误类型与棋盘校验。

设计目标（对齐《V6 指令》§2 / §3）：
- 外部棋盘一律接受 Python ``list[list[int]]``（也接受 tuple / 只读 ndarray），内部可实现为
  NumPy ndarray、整型 row lookup 或 64-bit bitboard。
- 严格校验为 4×4，取值只能是 0 或 2 的整数次幂；拒绝 NaN、布尔、负数、非整数、超界。
- 所有公开 move API 返回 ``(new_board, merge_score, changed)``；**绝不修改入参**。

本模块只定义协议与校验，不依赖 V5 / NumPy / Numba / C++，保证可在任何后端缺失时导入。
"""

from __future__ import annotations

DIRECTIONS = ('up', 'down', 'left', 'right')

# 64-bit bitboard 用 4bit 指数编码：0=空格，1..15 对应 2..32768。
# 指数 16（值 65536）及更大无法用 4bit 表示 —— 位棋盘后端必须显式拒绝并回退。
MAX_EXP = 15
MAX_BITBOARD_TILE = 1 << MAX_EXP          # 32768：位棋盘可表示的最大方块
LIMIT_TILE = 1 << (MAX_EXP + 1)           # 65536：达到/超过即视为“超界”


class BackendError(Exception):
    """后端相关错误基类。"""


class BackendUnavailable(BackendError):
    """后端不可用（未安装依赖 / 未构建 / 平台不匹配）。"""


class InvalidBoardError(BackendError):
    """外部棋盘不满足协议（维度 / 取值 / 类型）。"""


class BoardOverflowError(BackendError):
    """棋盘出现位棋盘后端无法表示的方块（>= 65536），必须显式回退。"""


def is_power_of_two(v: int) -> bool:
    return v > 0 and (v & (v - 1)) == 0


def _cell_int(v):
    """把单个单元格转换为 Python int；拒绝 bool / 浮点 / NaN / 负数 / 非整数。

    性能关键：**纯 Python int / float 走快路径且不导入 numpy**。
    仅当取值不是内置类型（可能来自 numpy 等）时才懒导入 numpy 做精确判定。
    这消除了“普通 list[list[int]] 棋盘也会触发 numpy 冷导入”的启动卡顿。
    """
    if isinstance(v, bool):
        raise InvalidBoardError('棋盘取值不允许布尔值：%r' % (v,))
    if isinstance(v, int):
        return v                                     # 最常见路径：不导入 numpy
    if isinstance(v, float):
        if v != v:                                    # NaN
            raise InvalidBoardError('棋盘取值不允许 NaN')
        if v != int(v):
            raise InvalidBoardError('棋盘取值必须为整数，收到 %r' % (v,))
        return int(v)
    try:
        import numpy as _np
        if isinstance(v, _np.bool_):
            raise InvalidBoardError('棋盘取值不允许布尔值：%r' % (v,))
        if isinstance(v, _np.floating):
            if not _np.isfinite(v):
                raise InvalidBoardError('棋盘取值不允许 NaN/Inf')
            if float(v) != int(v):
                raise InvalidBoardError('棋盘取值必须为整数，收到 %r' % (v,))
            return int(v)
        if isinstance(v, _np.integer):
            return int(v)
    except ImportError:                                # pragma: no cover
        pass
    raise InvalidBoardError('棋盘取值必须为 int，收到 %r' % (v,))


def validate_board(board, size: int = 4):
    """校验外部棋盘并返回**独立拷贝**的 ``list[list[int]]``。

    规则：恰好 size×size；每个取值是 0 或 2 的整数次幂；拒绝 NaN/布尔/负数/非整数。
    返回值为新对象，调用方可放心修改而不会影响入参（避免共享数组误修改）。
    """
    if board is None:
        raise InvalidBoardError('棋盘为 None')
    try:
        rows = list(board)
    except TypeError:
        raise InvalidBoardError('棋盘不可迭代：%r' % (type(board),))
    if len(rows) != size:
        raise InvalidBoardError('棋盘必须为 %d 行，收到 %d 行' % (size, len(rows)))

    out = []
    for r, row in enumerate(rows):
        try:
            cells = list(row)
        except TypeError:
            raise InvalidBoardError('第 %d 行不可迭代' % r)
        if len(cells) != size:
            raise InvalidBoardError('第 %d 行必须为 %d 列，收到 %d 列' % (r, size, len(cells)))
        new_row = []
        for c, v in enumerate(cells):
            iv = _cell_int(v)
            if iv < 0:
                raise InvalidBoardError('棋盘取值不允许负数：第 %d 行第 %d 列 = %r' % (r, c, iv))
            if iv != 0 and not is_power_of_two(iv):
                raise InvalidBoardError(
                    '棋盘取值必须为 0 或 2 的整数次幂：第 %d 行第 %d 列 = %r' % (r, c, iv))
            new_row.append(iv)
        out.append(new_row)
    return out


def board_key(board) -> tuple:
    """棋盘的可哈希键（用于 TT / 去重），输入须为已校验的 list[list[int]]。"""
    return tuple(tuple(row) for row in board)


class BackendBase:
    """后端协议的最小子集与默认（纯 Python）能力声明。

    后端实现只需覆盖自己真正加速的方法；未覆盖的会抛出 BackendUnavailable 由 dispatch 处理。
    """

    name = 'base'
    kind = 'python'          # python | numpy | numba | cpp
    supports_batch = False
    supports_native_rollout = False   # 原生整段 rollout（消费显式事件流）是否可用

    def available(self):     # -> (bool, reason)
        raise NotImplementedError

    def capabilities(self) -> dict:
        return {
            'name': self.name,
            'kind': self.kind,
            'supports_batch': bool(self.supports_batch),
            'max_tile_exp': MAX_EXP,
            'rejects_oversize_tile': self.kind in ('numba', 'cpp'),
        }

    # --- 单盘原语（子类实现） ---
    def move(self, board, direction):            # -> (new_board, score, changed)
        raise BackendUnavailable('%s 未实现 move' % self.name)

    def legal_moves(self, board):                # -> tuple[str]
        raise BackendUnavailable('%s 未实现 legal_moves' % self.name)

    def evaluate(self, board, weights=None):     # -> float
        raise BackendUnavailable('%s 未实现 evaluate' % self.name)

    def evaluate_features(self, board):          # -> dict
        raise BackendUnavailable('%s 未实现 evaluate_features' % self.name)

    def empty_cells(self, board):                # -> list[(r,c)]
        raise BackendUnavailable('%s 未实现 empty_cells' % self.name)

    def is_game_over(self, board):               # -> bool
        raise BackendUnavailable('%s 未实现 is_game_over' % self.name)

    def sample_spawn(self, board, rng, value=None):   # -> (new_board, cell, value)
        raise BackendUnavailable('%s 未实现 sample_spawn' % self.name)
