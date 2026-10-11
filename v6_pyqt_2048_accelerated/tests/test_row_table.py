#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 门禁：65536 个 16-bit 行状态的合并/得分/溢出，对照冻结 V5 参考。

覆盖：参考行逻辑(slide_line) 与 NumPy 行表、Numba 行表、C++ 行表逐项一致；
溢出标志与“含相邻 32768”一致。
"""

import os
import sys
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5_DIR = os.path.join(os.path.dirname(V6_DIR), 'v5_pyqt_2048_solver')
for p in (V6_DIR, V5_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import solver_2048 as V5                                             # noqa: E402
from solver_backends.numpy_core import _LEFT_RESULT, _LEFT_SCORE, _LEFT_OVERFLOW  # noqa: E402


def _expected_row(code):
    """由冻结 V5 slide_line 计算参考结果行编码/得分/溢出（col0=最高 nibble）。"""
    exps = [(code >> (4 * (3 - k))) & 0xF for k in range(4)]
    vals = [0 if e == 0 else (1 << e) for e in exps]
    merged, gained = V5.slide_line(vals)
    ov = any(v >= 65536 for v in merged)
    out_exps = [0 if v == 0 else (v.bit_length() - 1) for v in merged]
    ecode = (out_exps[0] << 12) | (out_exps[1] << 8) | (out_exps[2] << 4) | out_exps[3]
    return ecode, gained, ov


def _check_tables(test, results, scores, overflow, label):
    mismatch = 0
    ovf_mismatch = 0
    for code in range(65536):
        ecode, gained, ov = _expected_row(code)
        if bool(overflow[code]) != ov:
            ovf_mismatch += 1
        if ov:
            continue
        if int(results[code]) != ecode or int(scores[code]) != gained:
            mismatch += 1
            if mismatch <= 3:
                print('%s row mismatch code=%d' % (label, code))
    test.assertEqual(ovf_mismatch, 0, '%s 溢出标志不一致' % label)
    test.assertEqual(mismatch, 0, '%s 行表结果/得分不一致' % label)


class RowTableTest(unittest.TestCase):

    def test_numpy_row_table(self):
        self.assertEqual(_LEFT_RESULT.size, 65536)
        _check_tables(self, _LEFT_RESULT, _LEFT_SCORE, _LEFT_OVERFLOW, 'numpy')

    def test_numba_row_table(self):
        from solver_backends.numba_core import NumbaBackend
        be = NumbaBackend()
        _check_tables(self, be._res, be._sc, be._ovf, 'numba')

    def test_cpp_row_table(self):
        try:
            import solver_backends.bitboard_cpp as pkg
            mod = pkg.load_extension()
        except Exception as e:                                       # noqa: BLE001
            self.skipTest('cpp 扩展未构建：%s' % e)
        if mod is None:
            self.skipTest('cpp 扩展未构建（.pyd 缺失）')
        lr, lsc, lov = mod.row_left()
        _check_tables(self, lr, lsc, lov, 'cpp')


if __name__ == '__main__':
    unittest.main(verbosity=2)
