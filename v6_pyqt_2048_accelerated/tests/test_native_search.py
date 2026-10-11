#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6.2 原生搜索门禁（N2/N3/N4）：Rollout / Expectimax / MCTS 的正确性、取消与回退。

覆盖：
- S2 Rollout：原生单次 vs Python 驱动（共享事件流逐位一致）、batch 首元素 == 单次、批量确定性；
- S3 Expectimax：精确模式（prune=False）与 Python reference 决策/数值等价；TT on/off 一致；
  近似配置不冒充（native 拒绝 -> Python 路径）；溢出回退 reference；取消；
- S4 MCTS：与 Python 事件镜像逐步等价（方向/访问数/模拟数）；回传不变量；确定性；
  跨线程取消（验证 C++ 释放 GIL + 轮询取消令牌）。
"""

import os
import sys
import threading
import time
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5_DIR = os.path.join(os.path.dirname(V6_DIR), 'v5_pyqt_2048_solver')
BENCH_DIR = os.path.join(V6_DIR, 'benchmarks')
for _p in (V6_DIR, BENCH_DIR, V5_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import solver_v6 as S                                                   # noqa: E402
from solver_backends import native_api as NA                            # noqa: E402
from solver_backends.dispatch import create_backend, probe_backends     # noqa: E402
from solver_backends.events import SpawnEventStream                     # noqa: E402
import _bench_common as C                                               # noqa: E402

DW = S.DEFAULT_WEIGHTS
WV = NA.weight_vector(DW)

BOARDS = [
    [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]],
    [[2, 2, 4, 4], [8, 8, 16, 16], [32, 32, 64, 64], [128, 128, 256, 256]],
    [[0, 2, 0, 4], [2, 0, 4, 0], [0, 8, 0, 16], [8, 0, 16, 0]],
    [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]],
    [[2, 0, 0, 0], [0, 4, 0, 0], [0, 0, 8, 0], [0, 0, 0, 16]],
]


def cpp_ok():
    return bool(probe_backends().get('cpp', {}).get('available'))


@unittest.skipUnless(cpp_ok(), 'cpp 原生后端不可用')
class NativeRolloutTest(unittest.TestCase):
    """S2：原生 rollout 单次/批量正确性。"""

    def setUp(self):
        self.ref = create_backend('reference')
        self.cpp = create_backend('cpp')

    def test_native_single_matches_python_driver(self):
        for b in BOARDS:
            stream = SpawnEventStream(2048, 8192)
            cell, value, move = stream.as_arrays()
            for depth in (4, 12):
                nat = self.cpp.rollout_events(b, 0, depth, cell, value, move, DW)
                py = C.rollout_py(self.ref, b, 0, depth, stream, [0], DW)
                self.assertAlmostEqual(nat, py, places=9,
                                       msg='rollout 不一致 board=%s depth=%d' % (b[0], depth))

    def test_batch_first_equals_single(self):
        for b in BOARDS:
            stream = SpawnEventStream(7, 8192)
            cell, value, move = stream.as_arrays()
            single = self.cpp.rollout_events(b, 0, 8, cell, value, move, DW)
            batch = self.cpp.rollout_batch(b, 0, 8, 5, cell, value, move, DW)
            self.assertEqual(len(batch), 5)
            self.assertAlmostEqual(batch[0], single, places=9)

    def test_batch_deterministic(self):
        b = BOARDS[1]
        stream = SpawnEventStream(99, 8192)
        cell, value, move = stream.as_arrays()
        a = self.cpp.rollout_batch(b, 0, 10, 8, cell, value, move, DW)
        c = self.cpp.rollout_batch(b, 0, 10, 8, cell, value, move, DW)
        self.assertEqual(a, c)


@unittest.skipUnless(cpp_ok(), 'cpp 原生后端不可用')
class NativeExpectimaxTest(unittest.TestCase):
    """S3：原生 Expectimax 精确等价 / TT / 近似隔离 / 溢出 / 取消。"""

    def setUp(self):
        self.ref = create_backend('reference')
        self.cpp = create_backend('cpp')

    def _native(self, board, depth, **kw):
        req = NA.NativeSearchRequest(board=board, strategy='expectimax', budget_value=depth,
                                     weights=WV, time_limit_ms=30000.0, **kw)
        return NA.run_expectimax(self.cpp, req)

    def test_exact_equivalence_prune_false(self):
        for depth in (1, 2, 3):
            for b in BOARDS:
                py = S._expectimax_decision(self.ref, b, depth, 30.0, DW, prune=False)
                nat = self._native(b, depth, prune=False)
                self.assertEqual(py['best_direction'], nat.best_direction,
                                 'depth=%d board=%s' % (depth, b[0]))
                for d in S.DIRECTIONS:
                    a = py['evaluations'].get(d)
                    c = nat.evaluations.get(d)
                    if a is None or c is None:
                        self.assertEqual(a, c)
                    else:
                        self.assertAlmostEqual(a, c, places=6)

    def test_tt_on_off_identical(self):
        for b in BOARDS:
            a = self._native(b, 4, prune=True, use_tt=True, move_order=True)
            c = self._native(b, 4, prune=True, use_tt=False, move_order=True)
            self.assertEqual(a.best_direction, c.best_direction)
            for d in S.DIRECTIONS:
                va, vc = a.evaluations.get(d), c.evaluations.get(d)
                if va is None or vc is None:
                    self.assertEqual(va, vc)
                else:
                    self.assertAlmostEqual(va, vc, places=6)

    def test_exact_pruned_matches_python(self):
        # prune=True 且 sample_limit=0/prob_cutoff=0 时 Python 也是精确搜索 -> 应与 native 一致
        for b in BOARDS:
            py = S._expectimax_decision(self.ref, b, 3, 30.0, DW, prune=True,
                                        sample_limit=0, prob_cutoff=0.0,
                                        use_tt=True, move_order=True)
            nat = self._native(b, 3, prune=True, use_tt=True, move_order=True)
            self.assertEqual(py['best_direction'], nat.best_direction)

    def test_approximate_config_not_silently_approximated(self):
        req = NA.NativeSearchRequest(board=BOARDS[0], strategy='expectimax', budget_value=3,
                                     weights=WV, time_limit_ms=30000.0, prune=True,
                                     sample_limit=8, prob_cutoff=0.08)
        with self.assertRaises(NA.NativeEngineNotSupported):
            NA.run_expectimax(self.cpp, req)

    def test_overflow_falls_back_to_reference(self):
        ovb = [[32768, 32768, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        res = S.solve(ovb, 'expectimax', backend='cpp', native_search=True,
                      depth=2, prune=False, time_limit=30.0)
        self.assertEqual(res['backend_used'], 'reference')
        self.assertEqual(res['engine_used'], 'reference')
        self.assertIn('BoardOverflow', res['backend_fallback_reason'] or '')

    def test_cancel_token(self):
        tok = NA.CancelToken()
        tok.cancel()
        req = NA.NativeSearchRequest(board=BOARDS[1], strategy='expectimax', budget_value=6,
                                     weights=WV, time_limit_ms=30000.0, cancel_token=tok)
        r = NA.run_expectimax(self.cpp, req)
        self.assertTrue(r.cancelled)


@unittest.skipUnless(cpp_ok(), 'cpp 原生后端不可用')
class NativeMctsTest(unittest.TestCase):
    """S4：原生 MCTS 结构等价 / 不变量 / 确定性 / 取消。"""

    def setUp(self):
        self.ref = create_backend('reference')
        self.cpp = create_backend('cpp')

    def _native(self, board, sims, rd, stream=None, **kw):
        req = NA.NativeSearchRequest(board=board, strategy='mcts', simulations=sims,
                                     rollout_depth=rd, weights=WV, time_limit_ms=30000.0,
                                     events=stream, **kw)
        return NA.run_mcts(self.cpp, req)

    def test_matches_python_event_mirror(self):
        for sims, rd in ((40, 8), (60, 12)):
            for b in BOARDS[:4]:
                nat = self._native(b, sims, rd, stream=SpawnEventStream(2048, 65536))
                mirror = S._mcts_decision_events(self.ref, b, simulations=sims, rollout_depth=rd,
                                                 weights=DW, stream=SpawnEventStream(2048, 65536))
                self.assertEqual(nat.best_direction, mirror['best_direction'])
                self.assertEqual(nat.root_visits, mirror['root_visits'])
                self.assertEqual(nat.root_move_visits, mirror['root_move_visits'])
                self.assertEqual(nat.stats['simulations'], mirror['completed_simulations'])

    def test_backprop_invariants(self):
        for b in BOARDS:
            r = self._native(b, 50, 8, stream=SpawnEventStream(11, 65536))
            self.assertEqual(r.root_visits, r.stats['simulations'])
            if r.best_direction is not None:      # 满盘无可行方向时无 move 子节点
                self.assertEqual(sum(r.root_move_visits.values()), r.root_visits)

    def test_deterministic(self):
        b = BOARDS[2]
        a = self._native(b, 60, 10, stream=SpawnEventStream(5, 65536))
        c = self._native(b, 60, 10, stream=SpawnEventStream(5, 65536))
        self.assertEqual(a.best_direction, c.best_direction)
        self.assertEqual(a.root_move_visits, c.root_move_visits)
        self.assertEqual(a.stats, c.stats)

    def test_solve_returns_legal(self):
        for b in BOARDS:
            r = S.solve(b, 'mcts', backend='cpp', native_search=True, simulations=50,
                        rollout_depth=8, time_limit=30.0)
            legal = S.legal_moves(b)
            if not legal:
                self.assertEqual(r.get('note'), '无可行移动')
                continue
            self.assertIn(r['best_direction'], legal)
            self.assertEqual(r['engine_used'], 'native')

    def test_cross_thread_cancel_returns_quickly(self):
        """验证 C++ 释放 GIL，另一线程置令牌可及时中止（GUI 关闭窗口场景）。"""
        tok = NA.CancelToken()
        box = {}

        def work():
            req = NA.NativeSearchRequest(board=BOARDS[1], strategy='mcts', simulations=200000,
                                         rollout_depth=40, weights=WV, time_limit_ms=120000.0,
                                         cancel_token=tok)
            box['r'] = NA.run_mcts(self.cpp, req)

        t = threading.Thread(target=work)
        t.start()
        time.sleep(0.15)
        tok.cancel()
        t.join(timeout=10.0)
        self.assertFalse(t.is_alive(), '取消后线程未及时退出')
        self.assertTrue(box['r'].cancelled)
        self.assertLess(box['r'].stats['simulations'], 200000)


class FailureInjectionTest(unittest.TestCase):
    """S6.7 失败注入：缺失 .pyd / 非法输入 / 预算不足 / 无模块回退。"""

    def test_cpp_missing_dispatch_falls_back(self):
        from solver_backends import dispatch as D
        saved_mod, saved_err = D._cpp_module, D._cpp_error
        try:
            D._cpp_module = None
            D._cpp_error = 'BUILD_BLOCKED: simulated missing .pyd'
            probe = D.probe_backends()
            self.assertFalse(probe['cpp']['available'])
            be, used, reason = D.get_backend('auto')
            self.assertNotEqual(used, 'cpp')
            self.assertIsNotNone(reason)
        finally:
            D._cpp_module, D._cpp_error = saved_mod, saved_err

    def test_invalid_board_rejected(self):
        res = S.solve([[1, 2], [3, 4]], 'heuristic')
        self.assertIsNotNone(res.get('error'))
        self.assertIsNone(res.get('best_direction'))

    def test_native_engine_not_supported_without_module(self):
        class _Fake:
            pass
        req = NA.NativeSearchRequest(board=BOARDS[0], strategy='expectimax', weights=WV)
        with self.assertRaises(NA.NativeEngineNotSupported):
            NA.run_expectimax(_Fake(), req)

    def test_tiny_budget_still_returns_legal(self):
        r = S.solve(BOARDS[0], 'expectimax', backend='cpp', native_search=True,
                    depth=8, prune=False, time_limit=0.001)
        self.assertIn(r['best_direction'], S.legal_moves(BOARDS[0]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
