#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 NumPy 后端：以 16-bit 行查表 + NumPy 向量化实现 4×4 的等价运算。

设计取舍（对齐《V6 指令》§4.1）：4×4 单盘很小，不做无意义的多重向量化；
滑动/合并用 65536 行查表（一次性构建）＋整型 row lookup，评估特征用 NumPy 逐项实现。
指数编码 1..15 对应 2..32768；指数 0=空格；合并产生指数 >=16（值 65536）时显式拒绝。
"""

from __future__ import annotations

import numpy as np

from .api import (BackendBase, BoardOverflowError, InvalidBoardError, DIRECTIONS,
                  MAX_EXP, LIMIT_TILE, weight_list)

# 方向 -> 索引（与 api.DIRECTIONS 顺序一致）
_DIR_IDX = {d: i for i, d in enumerate(DIRECTIONS)}


def _build_left_tables():
    """构建 65536 行“向左合并”查表：结果行编码、合并得分、是否溢出（指数 >15）。"""
    results = np.zeros(65536, dtype=np.int64)
    scores = np.zeros(65536, dtype=np.int64)
    overflow = np.zeros(65536, dtype=bool)
    for code in range(65536):
        exps = [(code >> (4 * (3 - k))) & 0xF for k in range(4)]
        comp = [e for e in exps if e != 0]
        out = []
        gained = 0
        i = 0
        while i < len(comp):
            if i + 1 < len(comp) and comp[i] == comp[i + 1]:
                e = comp[i] + 1
                out.append(e)
                gained += (1 << e)
                if e > MAX_EXP:
                    overflow[code] = True
                i += 2
            else:
                out.append(comp[i])
                i += 1
        out += [0] * (4 - len(out))
        rcode = 0
        for k in range(4):
            e = out[k]
            if e > 0xF:                        # 溢出时仅占位，正确性由 overflow 标记
                e = 0xF
            rcode |= (e & 0xF) << (4 * (3 - k))
        results[code] = rcode
        scores[code] = gained
    return results, scores, overflow


_LEFT_RESULT, _LEFT_SCORE, _LEFT_OVERFLOW = _build_left_tables()

# 反转向量：把 4 个 nibble 顺序颠倒（用于 right / down）
_REV = np.array([0x000F, 0x00F0, 0x0F00, 0xF000], dtype=np.int64)


def _reverse_codes(codes):
    """以 nibble 为单位反转每个 16-bit 行编码。"""
    return (((codes & 0x000F) << 12) | ((codes & 0x00F0) << 4)
            | ((codes & 0x0F00) >> 4) | ((codes & 0xF000) >> 12))


def _to_exps(board):
    """方块值 4×4 -> 指数 4×4（int64）。调用前须已校验 board。"""
    a = np.asarray(board, dtype=np.int64)
    exps = np.zeros((4, 4), dtype=np.int64)
    nz = a > 0
    if np.any(a >= LIMIT_TILE):
        raise BoardOverflowError('NumPy 后端不支持 >= %d 的方块' % LIMIT_TILE)
    # 2 的整数次幂 -> 指数 = bit_length-1（位运算，避免 log2 浮点边界误差）
    iv = a[nz]
    exps[nz] = np.array([int(v).bit_length() - 1 for v in iv], dtype=np.int64)
    return exps


def _from_exps(exps):
    """指数 4×4 -> 方块值 list[list[int]]（指数 0 = 空格 = 0）。"""
    vals = np.where(exps == 0, 0, np.left_shift(np.int64(1), exps))
    return vals.tolist()


def _row_codes(exps):
    return ((exps[:, 0] << 12) | (exps[:, 1] << 8) | (exps[:, 2] << 4) | exps[:, 3])


def _decode_codes(codes):
    return np.stack([(codes >> 12) & 0xF, (codes >> 8) & 0xF,
                     (codes >> 4) & 0xF, codes & 0xF], axis=1)


class NumpyBackend(BackendBase):
    name = 'numpy'
    kind = 'numpy'
    supports_batch = True

    def available(self):
        return True, 'numpy %s' % np.__version__

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps['row_table'] = True
        caps['row_table_entries'] = int(_LEFT_RESULT.size)
        return caps

    # ---- 单盘原语 ----
    def move(self, board, direction):
        exps = _to_exps(board)
        if direction not in _DIR_IDX:
            raise InvalidBoardError('未知方向：%r' % (direction,))
        d = direction
        codes = _row_codes(exps)
        ovf = False
        if d in ('left', 'right'):
            use = codes if d == 'left' else _reverse_codes(codes)
            ovf = bool(_LEFT_OVERFLOW[use].any())
            new_codes = _LEFT_RESULT[use]
            gained = int(_LEFT_SCORE[use].sum())
            if d == 'right':
                new_codes = _reverse_codes(new_codes)
            new_exps = _decode_codes(new_codes)
        else:
            texps = exps.T.copy()
            tcodes = _row_codes(texps)
            use = tcodes if d == 'up' else _reverse_codes(tcodes)
            ovf = bool(_LEFT_OVERFLOW[use].any())
            new_codes = _LEFT_RESULT[use]
            gained = int(_LEFT_SCORE[use].sum())
            if d == 'down':
                new_codes = _reverse_codes(new_codes)
            new_exps = _decode_codes(new_codes).T
        if ovf:
            raise BoardOverflowError('移动产生 >= %d 的方块，NumPy 后端拒绝' % LIMIT_TILE)
        new_board = _from_exps(new_exps)
        changed = bool(np.any(new_exps != exps))
        return new_board, gained, changed

    def legal_moves(self, board):
        out = []
        for d in DIRECTIONS:
            _, _, moved = self.move(board, d)
            if moved:
                out.append(d)
        return tuple(out)

    def evaluate(self, board, weights=None):
        w = _weight_array(weights)
        exps = _to_exps(board)
        return float(_evaluate_exps(exps, w))

    def evaluate_features(self, board):
        exps = _to_exps(board)
        vals = np.where(exps == 0, 0, np.left_shift(np.int64(1), exps))
        return {
            'empty': int((exps == 0).sum()),
            'monotonicity': round(_monotonicity(vals), 3),
            'smoothness': round(_smoothness(vals), 3),
            'merge': int(_merge_potential(vals)),
            'corner': round(_corner(vals), 3),
            'max_tile': int(vals.max()),
        }

    def empty_cells(self, board):
        exps = _to_exps(board)
        rs, cs = np.nonzero(exps == 0)
        return [(int(r), int(c)) for r, c in zip(rs, cs)]

    def is_game_over(self, board):
        exps = _to_exps(board)
        if (exps == 0).any():
            return False
        if (exps[:, :-1] == exps[:, 1:]).any():
            return False
        if (exps[:-1, :] == exps[1:, :]).any():
            return False
        return True

    def sample_spawn(self, board, rng, value=None):
        cells = self.empty_cells(board)
        if not cells:
            new_board = [row[:] for row in board]
            return new_board, None, 0
        i, j = rng.choice(cells)
        if value is None:
            value = 2 if rng.random() < 0.9 else 4
        new_board = [row[:] for row in board]
        new_board[i][j] = value
        return new_board, (i, j), value

    # ---- 批量 ----
    def batch_move(self, boards, direction):
        return [self.move(b, direction) for b in boards]


# --------------------------------------------------------------- 评估 ---
def _weight_array(weights):
    """把权重 dict 转成定长 float64 数组（缺省用 V5 默认值）。

    权重列表构造复用 ``api.weight_list``（numpy-free、单一来源）；此处仅做数组化。
    """
    return np.array(weight_list(weights), dtype=np.float64)


def _log2_vals(vals):
    out = np.zeros(vals.shape, dtype=np.float64)
    nz = vals > 0
    out[nz] = np.log2(vals[nz].astype(np.float64))
    return out


def _monotonicity(vals):
    L = _log2_vals(vals)
    total = 0.0
    for axis in (1, 0):
        d = np.diff(L, axis=axis)                      # a - b
        pos = np.clip(d, 0.0, None)
        neg = np.clip(-d, 0.0, None)
        total += float(np.sum(np.maximum(-neg.sum(axis=axis), -pos.sum(axis=axis))))
    return total


def _smoothness(vals):
    L = _log2_vals(vals)
    total = 0.0
    # 水平相邻
    dh = np.abs(L[:, 1:] - L[:, :-1])
    mh = (vals[:, 1:] != 0) & (vals[:, :-1] != 0)
    total -= float(dh[mh].sum())
    # 垂直相邻
    dv = np.abs(L[1:, :] - L[:-1, :])
    mv = (vals[1:, :] != 0) & (vals[:-1, :] != 0)
    total -= float(dv[mv].sum())
    return total


def _merge_potential(vals):
    n = 0
    n += int(((vals[:, 1:] == vals[:, :-1]) & (vals[:, 1:] != 0)).sum())
    n += int(((vals[1:, :] == vals[:-1, :]) & (vals[1:, :] != 0)).sum())
    return n


def _corner(vals):
    mt = int(vals.max())
    if mt == 0:
        return 0.0
    for (i, j) in ((0, 0), (0, 3), (3, 0), (3, 3)):
        if int(vals[i, j]) == mt:
            return float(np.log2(mt))
    return 0.0


def _evaluate_exps(exps, w):
    vals = np.where(exps == 0, 0, np.left_shift(np.int64(1), exps))
    score = (w[0] * float((exps == 0).sum())
             + w[1] * _monotonicity(vals)
             + w[2] * _smoothness(vals)
             + w[3] * float(_merge_potential(vals))
             + w[4] * _corner(vals))
    # snake / danger 默认权重 0，保持 baseline 行为不变
    if w[5]:
        score += w[5] * _snake_value(vals)
    if w[6]:
        score += w[6] * _danger_penalty(exps, vals)
    return score


_SNAKE_ORDER = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 3), (1, 2), (1, 1), (1, 0),
                (2, 0), (2, 1), (2, 2), (2, 3), (3, 3), (3, 2), (3, 1), (3, 0)]


def _snake_value(vals):
    L = _log2_vals(vals)
    num = den = 0.0
    for idx, (i, j) in enumerate(_SNAKE_ORDER):
        w = 0.5 ** idx
        num += w * float(L[i, j])
        den += w * 15.0
    return 100.0 * num / den if den else 0.0


def _danger_penalty(exps, vals):
    empties = int((exps == 0).sum())
    distinct = 0
    distinct += int(((vals[:, 1:] != vals[:, :-1]) & (vals[:, 1:] != 0)
                     & (vals[:, :-1] != 0)).sum())
    distinct += int(((vals[1:, :] != vals[:-1, :]) & (vals[1:, :] != 0)
                     & (vals[:-1, :] != 0)).sum())
    return -60.0 * (1.0 - empties / 16.0) - 0.6 * distinct
