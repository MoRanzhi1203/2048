#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 门禁：随机棋盘上四后端与原 V5 参考的规则等价 + 协议边界。

抽样规模（"廉价单步规则测试"，非整局对局）：
- 参考 vs Numba / C++ ：10,000 个随机棋盘 × 4 方向 + legal_moves
- 参考 vs NumPy      ：10,000 个随机棋盘 × 左移（+ 1,000 盘 × 4 方向 + legal）
- 评估函数          ：参考 vs C++/Numba 10,000 盘；参考 vs NumPy 2,000 盘
"""

import copy
import os
import random
import sys
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5_DIR = os.path.join(os.path.dirname(V6_DIR), 'v5_pyqt_2048_solver')
for p in (V6_DIR, V5_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from solver_backends.reference import ReferenceBackend                      # noqa: E402
from solver_backends.numpy_core import NumpyBackend                         # noqa: E402
from solver_backends.api import (validate_board, InvalidBoardError,         # noqa: E402
                                 BoardOverflowError, DIRECTIONS)

N_FULL = 10000
N_SMALL = 1000
N_EVAL_NUMPY = 2000


def gen_boards(n, seed=20260001, max_exp=12):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        b = [[0] * 4 for _ in range(4)]
        cells = [(i, j) for i in range(4) for j in range(4)]
        rng.shuffle(cells)
        k = rng.randint(4, 16)          # 4..16 个非空格（覆盖近死局）
        for (i, j) in cells[:k]:
            b[i][j] = 1 << rng.randint(1, max_exp)
        out.append(b)
    return out


class BackendEquivalenceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ref = ReferenceBackend()
        cls.npy = NumpyBackend()
        cls.num = None
        cls.cpp = None
        try:
            from solver_backends.numba_core import NumbaBackend
            cls.num = NumbaBackend()
            cls.num.warmup()
        except Exception:                                            # noqa: BLE001
            cls.num = None
        try:
            import solver_backends.bitboard_cpp as pkg
            mod = pkg.load_extension()
            if mod is not None:
                from solver_backends.bitboard_cpp_backend import CppBitboardBackend
                cls.cpp = CppBitboardBackend(mod)
        except Exception:                                            # noqa: BLE001
            cls.cpp = None

    def _compare_move_fulldirs(self, other, label, boards):
        bad = 0
        for b in boards:
            for d in DIRECTIONS:
                try:
                    r = self.ref.move(b, d)
                except BoardOverflowError:
                    continue
                try:
                    o = other.move(b, d)
                except BoardOverflowError:
                    bad += 1
                    continue
                if r != o:
                    bad += 1
                    if bad <= 3:
                        print('%s move mismatch %s %s -> %s vs %s' % (label, b, d, r, o))
        self.assertEqual(bad, 0, '%s 与参考 move 不一致' % label)

    def test_numba_full(self):
        if self.num is None:
            self.skipTest('numba 不可用')
        boards = gen_boards(N_FULL, seed=11)
        self._compare_move_fulldirs(self.num, 'numba', boards)
        for b in boards:
            self.assertEqual(self.ref.legal_moves(b), tuple(self.num.legal_moves(b)),
                             'numba legal_moves 不一致')

    def test_cpp_full(self):
        if self.cpp is None:
            self.skipTest('cpp 扩展未构建')
        boards = gen_boards(N_FULL, seed=12)
        self._compare_move_fulldirs(self.cpp, 'cpp', boards)
        for b in boards:
            self.assertEqual(self.ref.legal_moves(b), tuple(self.cpp.legal_moves(b)),
                             'cpp legal_moves 不一致')

    def test_numpy_left_full(self):
        boards = gen_boards(N_FULL, seed=13)
        bad = 0
        for b in boards:
            if self.ref.move(b, 'left') != self.npy.move(b, 'left'):
                bad += 1
        self.assertEqual(bad, 0, 'numpy left move 不一致')

    def test_numpy_alldirs_small(self):
        boards = gen_boards(N_SMALL, seed=14)
        self._compare_move_fulldirs(self.npy, 'numpy', boards)
        for b in boards:
            self.assertEqual(self.ref.legal_moves(b), tuple(self.npy.legal_moves(b)))

    def test_evaluate_equivalence(self):
        boards = gen_boards(N_FULL, seed=15)
        for b in boards:
            e0 = self.ref.evaluate(b)
            if self.cpp is not None:
                self.assertAlmostEqual(e0, self.cpp.evaluate(b), places=6)
            if self.num is not None:
                self.assertAlmostEqual(e0, self.num.evaluate(b), places=6)
        for b in boards[:N_EVAL_NUMPY]:
            self.assertAlmostEqual(self.ref.evaluate(b), self.npy.evaluate(b), places=6)

    def test_input_not_mutated(self):
        b = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2048, 4096], [0, 0, 0, 2]]
        for backend in (self.ref, self.npy, self.num, self.cpp):
            if backend is None:
                continue
            snap = copy.deepcopy(b)
            backend.move(b, 'up')
            backend.evaluate(b)
            backend.legal_moves(b)
            self.assertEqual(b, snap, '%s 修改了入参' % backend)


class ProtocolBoundaryTest(unittest.TestCase):

    def test_reject_non_4x4(self):
        with self.assertRaises(InvalidBoardError):
            validate_board([[0] * 4 for _ in range(3)])
        with self.assertRaises(InvalidBoardError):
            validate_board([[0] * 4 for _ in range(4)] + [[]])

    def test_reject_non_power_of_two(self):
        b = [[0] * 4 for _ in range(4)]
        b[0][0] = 6
        with self.assertRaises(InvalidBoardError):
            validate_board(b)

    def test_reject_bool_negative_float_nan(self):
        b = [[0] * 4 for _ in range(4)]
        b[0][0] = True
        with self.assertRaises(InvalidBoardError):
            validate_board(b)
        b[0][0] = -2
        with self.assertRaises(InvalidBoardError):
            validate_board(b)
        b[0][0] = 2.5
        with self.assertRaises(InvalidBoardError):
            validate_board(b)
        b[0][0] = float('nan')
        with self.assertRaises(InvalidBoardError):
            validate_board(b)

    def test_accept_powers_of_two(self):
        b = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2048, 4096], [8192, 16384, 32768, 0]]
        out = validate_board(b)
        self.assertEqual(out, b)

    def test_overflow_behavior(self):
        """参考支持 >=65536，位棋盘后端必须显式拒绝（不静默截断）。"""
        big = [[65536, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        ref = ReferenceBackend()
        nxt, score, moved = ref.move(big, 'left')
        self.assertEqual(nxt[0][0], 65536)                 # 参考可表示
        try:
            import solver_backends.bitboard_cpp as pkg
            mod = pkg.load_extension()
        except Exception:                                   # noqa: BLE001
            mod = None
        if mod is not None:
            from solver_backends.bitboard_cpp_backend import CppBitboardBackend
            cpp = CppBitboardBackend(mod)
            with self.assertRaises(BoardOverflowError):
                cpp.move(big, 'left')

    def test_merge_result_overflow_rejected(self):
        """相邻两个 32768 合并 -> 65536，位棋盘后端必须拒绝。"""
        b = [[32768, 32768, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        try:
            import solver_backends.bitboard_cpp as pkg
            mod = pkg.load_extension()
        except Exception:                                   # noqa: BLE001
            mod = None
        if mod is not None:
            from solver_backends.bitboard_cpp_backend import CppBitboardBackend
            cpp = CppBitboardBackend(mod)
            with self.assertRaises(BoardOverflowError):
                cpp.move(b, 'left')


if __name__ == '__main__':
    unittest.main(verbosity=2)
