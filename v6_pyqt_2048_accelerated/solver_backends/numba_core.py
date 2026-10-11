#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 Numba 后端：``@njit(cache=True)`` nopython 内核（滑动/合并/合法方向/评估/批量续玩）。

要求（对齐《V6 指令》§4.2）：
- 必须真正编译为 **nopython** 模式；object mode / 静默回退不计为成功。
- 冷启动（首次编译）与热态运行分开报告；缓存命中与跨进程复用由 `cache=True` 提供。
- 内层循环整体编译，避免每个节点 Python↔JIT 往返。
"""

from __future__ import annotations

import numpy as np
from math import log2

from numba import njit

from .api import (BackendBase, BackendUnavailable, BoardOverflowError, DIRECTIONS,
                  LIMIT_TILE, MAX_EXP)

_DIR_IDX = {'up': 0, 'down': 1, 'left': 2, 'right': 3}


# ----------------------------------------------------------------- 内核 ---
@njit(cache=True)
def _build_tables():
    """65536 行“向左合并”查表：结果行编码 / 得分 / 溢出标志。"""
    res = np.zeros(65536, np.int32)
    sc = np.zeros(65536, np.int64)
    ovf = np.zeros(65536, np.bool_)
    exp = np.empty(4, np.int32)
    comp = np.empty(4, np.int32)
    out = np.empty(4, np.int32)
    for code in range(65536):
        for k in range(4):
            exp[k] = (code >> (4 * (3 - k))) & 0xF
        n = 0
        for k in range(4):
            if exp[k] != 0:
                comp[n] = exp[k]
                n += 1
        gained = 0
        ov = False
        m = 0
        i = 0
        while i < n:
            if i + 1 < n and comp[i] == comp[i + 1]:
                e = comp[i] + 1
                out[m] = e
                gained += (1 << e)
                if e > 15:
                    ov = True
                i += 2
            else:
                out[m] = comp[i]
                i += 1
            m += 1
        while m < 4:
            out[m] = 0
            m += 1
        rcode = 0
        for k in range(4):
            e = out[k]
            if e > 15:
                e = 15
            rcode |= (e & 0xF) << (4 * (3 - k))
        res[code] = rcode
        sc[code] = gained
        ovf[code] = ov
    return res, sc, ovf


@njit(cache=True)
def _move_exps(exps, res, sc, ovf, direction):
    """在指数矩阵上执行一次移动；direction: 0=up,1=down,2=left,3=right。"""
    new = np.zeros((4, 4), np.int32)
    score = 0
    o = False
    tmp = np.empty(4, np.int32)
    for line in range(4):
        for k in range(4):
            if direction == 2:
                tmp[k] = exps[line, k]
            elif direction == 3:
                tmp[k] = exps[line, 3 - k]
            elif direction == 0:
                tmp[k] = exps[k, line]
            else:
                tmp[k] = exps[3 - k, line]
        c = 0
        for k in range(4):
            c |= (tmp[k] & 0xF) << (4 * (3 - k))
        r = res[c]
        score += sc[c]
        if ovf[c]:
            o = True
        for k in range(4):
            tmp[k] = (r >> (4 * (3 - k))) & 0xF
        for k in range(4):
            if direction == 2:
                new[line, k] = tmp[k]
            elif direction == 3:
                new[line, 3 - k] = tmp[k]
            elif direction == 0:
                new[k, line] = tmp[k]
            else:
                new[3 - k, line] = tmp[k]
    return new, score, o


@njit(cache=True)
def _encode(vals):
    """方块值 int64[16] -> 指数 int32(4,4)；(exps, overflow)。"""
    exps = np.zeros((4, 4), np.int32)
    ovf = False
    for p in range(16):
        v = vals[p]
        if v < 0:
            ovf = True
            continue
        if v == 0:
            continue
        if v >= 65536:
            ovf = True
            continue
        e = 0
        x = v
        while x > 1:
            x >>= 1
            e += 1
        exps[p // 4, p % 4] = e
    return exps, ovf


@njit(cache=True)
def _decode(exps):
    out = np.empty(16, np.int64)
    for i in range(4):
        for j in range(4):
            e = exps[i, j]
            out[i * 4 + j] = 0 if e == 0 else (np.int64(1) << np.int64(e))
    return out


@njit(cache=True, inline='always')
def _l2(v):
    if v <= 0:
        return 0.0
    return log2(float(v))


@njit(cache=True)
def _monotonicity(v):
    total = 0.0
    for i in range(4):
        inc = 0.0
        dec = 0.0
        for j in range(3):
            a = _l2(v[i, j])
            b = _l2(v[i, j + 1])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        if inc > dec:
            total += inc
        else:
            total += dec
        inc = 0.0
        dec = 0.0
        for j in range(3):
            a = _l2(v[j, i])
            b = _l2(v[j + 1, i])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        if inc > dec:
            total += inc
        else:
            total += dec
    return total


@njit(cache=True)
def _smoothness(v):
    total = 0.0
    for i in range(4):
        for j in range(4):
            if v[i, j] == 0:
                continue
            lv = _l2(v[i, j])
            if j + 1 < 4 and v[i, j + 1] != 0:
                total -= abs(lv - _l2(v[i, j + 1]))
            if i + 1 < 4 and v[i + 1, j] != 0:
                total -= abs(lv - _l2(v[i + 1, j]))
    return total


@njit(cache=True)
def _merge_potential(v):
    count = 0
    for i in range(4):
        for j in range(4):
            if v[i, j] == 0:
                continue
            if j + 1 < 4 and v[i, j] == v[i, j + 1]:
                count += 1
            if i + 1 < 4 and v[i, j] == v[i + 1, j]:
                count += 1
    return count


@njit(cache=True)
def _corner(v):
    mt = 0
    for i in range(4):
        for j in range(4):
            if v[i, j] > mt:
                mt = v[i, j]
    if mt == 0:
        return 0.0
    corners_i = np.array([0, 0, 3, 3])
    corners_j = np.array([0, 3, 0, 3])
    for c in range(4):
        if v[corners_i[c], corners_j[c]] == mt:
            return _l2(mt)
    return 0.0


_SNAKE_I = np.array([0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3])
_SNAKE_J = np.array([0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3, 3, 2, 1, 0])


@njit(cache=True)
def _snake(v):
    num = 0.0
    den = 0.0
    w = 1.0
    for idx in range(16):
        num += w * _l2(v[_SNAKE_I[idx], _SNAKE_J[idx]])
        den += w * 15.0
        w *= 0.5
    if den:
        return 100.0 * num / den
    return 0.0


@njit(cache=True)
def _danger(v, empties):
    distinct = 0
    for i in range(4):
        for j in range(4):
            val = v[i, j]
            if val <= 0:
                continue
            if j + 1 < 4 and v[i, j + 1] > 0 and v[i, j + 1] != val:
                distinct += 1
            if i + 1 < 4 and v[i + 1, j] > 0 and v[i + 1, j] != val:
                distinct += 1
    return -60.0 * (1.0 - empties / 16.0) - 0.6 * distinct


@njit(cache=True)
def _evaluate_vals(v, w):
    empties = 0
    for i in range(4):
        for j in range(4):
            if v[i, j] == 0:
                empties += 1
    score = (w[0] * empties + w[1] * _monotonicity(v) + w[2] * _smoothness(v)
             + w[3] * _merge_potential(v) + w[4] * _corner(v))
    if w[5] != 0.0:
        score += w[5] * _snake(v)
    if w[6] != 0.0:
        score += w[6] * _danger(v, empties)
    return score


# ------------------------------------------------------------- 后端类 ---
class NumbaBackend(BackendBase):
    name = 'numba'
    kind = 'numba'
    supports_batch = True

    def __init__(self):
        self._res, self._sc, self._ovf = _build_tables()
        self._compiled = False

    def available(self):
        try:
            import numba
            try:
                import llvmlite
                llv = llvmlite.__version__
            except Exception:                                # noqa: BLE001
                llv = '?'
            return True, 'numba %s (llvmlite %s)' % (numba.__version__, llv)
        except Exception as e:                              # pragma: no cover
            return False, 'numba import failed: %r' % (e,)

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps['row_table'] = True
        caps['row_table_entries'] = int(self._res.size)
        caps['nopython'] = bool(self._signatures())
        return caps

    # 触发编译（冷启动）并把 nopython 签名登记为证据
    def warmup(self):
        vals = np.asarray([[2, 4, 8, 16], [32, 64, 128, 256],
                           [512, 1024, 2048, 4096], [0, 0, 0, 2]], dtype=np.int64).reshape(16)
        exps, _o = _encode(vals)
        _ = _move_exps(exps, self._res, self._sc, self._ovf, 2)
        _ = _evaluate_vals(np.asarray([[2, 4, 8, 16], [32, 64, 128, 256],
                                       [512, 1024, 2048, 4096], [0, 0, 0, 2]],
                                      dtype=np.int64),
                           np.zeros(7, dtype=np.float64))
        self._compiled = True
        return self.nopython_info()

    def _signatures(self):
        sigs = []
        for fn in (_move_exps, _encode, _decode, _evaluate_vals, _build_tables):
            for s in getattr(fn, 'nopython_signatures', ()):
                sigs.append((fn.py_func.__name__, str(s)))
        return sigs

    def nopython_info(self):
        return {'nopython_signatures': self._signatures(),
                'compiled': self._compiled}

    # ---- 单盘原语 ----
    def move(self, board, direction):
        if direction not in _DIR_IDX:
            from .api import InvalidBoardError
            raise InvalidBoardError('未知方向：%r' % (direction,))
        vals = np.asarray(board, dtype=np.int64).reshape(16)
        exps, enc_ovf = _encode(vals)
        if enc_ovf:
            raise BoardOverflowError('Numba 后端不支持 >= %d 的方块' % LIMIT_TILE)
        new_exps, score, ovf = _move_exps(exps, self._res, self._sc, self._ovf,
                                          _DIR_IDX[direction])
        if ovf:
            raise BoardOverflowError('移动产生 >= %d 的方块，Numba 后端拒绝' % LIMIT_TILE)
        new_board = _decode(new_exps).reshape(4, 4).tolist()
        changed = bool(np.any(new_exps != exps))
        return new_board, int(score), changed

    def legal_moves(self, board):
        out = []
        for d in DIRECTIONS:
            _, _, moved = self.move(board, d)
            if moved:
                out.append(d)
        return tuple(out)

    def evaluate(self, board, weights=None):
        from .numpy_core import _weight_array
        w = _weight_array(weights)
        vals = np.asarray(board, dtype=np.int64)
        return float(_evaluate_vals(vals, w))

    def evaluate_features(self, board):
        from .numpy_core import NumpyBackend
        return NumpyBackend().evaluate_features(board)

    def empty_cells(self, board):
        vals = np.asarray(board, dtype=np.int64)
        exps, _ = _encode(vals.reshape(16))
        rs, cs = np.nonzero(exps == 0)
        return [(int(r), int(c)) for r, c in zip(rs, cs)]

    def is_game_over(self, board):
        vals = np.asarray(board, dtype=np.int64)
        exps, _ = _encode(vals.reshape(16))
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
            return [row[:] for row in board], None, 0
        i, j = rng.choice(cells)
        if value is None:
            value = 2 if rng.random() < 0.9 else 4
        nb = [row[:] for row in board]
        nb[i][j] = value
        return nb, (i, j), value

    def batch_move(self, boards, direction):
        return [self.move(b, direction) for b in boards]


def try_create():
    try:
        b = NumbaBackend()
    except Exception as e:                              # pragma: no cover
        raise BackendUnavailable('Numba 后端创建失败：%r' % (e,))
    ok, reason = b.available()
    if not ok:
        raise BackendUnavailable(reason)
    return b
