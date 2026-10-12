#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G2 证据：会话上限与「结果回传策略」解耦（进程内、确定性受控状态）。

说明（重要）：真实对局会在 200/400 步**之前自然终局**，故边界测试不能依赖“一定能走满”。
按规范用**受控假体**（固定合法方向、棋盘不变但 moved=True、is_game_over=False）构造
确定性长轨迹，专门验证“**回传间隔 N 绝不是终止预算**”这一协议语义。
"""

import os
import random
import sys
import time
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V6_DIR)
sys.path.insert(0, os.path.join(V6_DIR, 'headless'))
sys.path.insert(0, os.path.dirname(V6_DIR))

import core                                                          # noqa: E402
import game_loop                                                     # noqa: E402
import solver_v6                                                     # noqa: E402

BOARD = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
_ORIG = {}


def _patch_fakes():
    _ORIG.update({'legal': core.legal_moves, 'apply': core.apply_move,
                  'over': core.is_game_over, 'solve': solver_v6.solve})
    core.legal_moves = lambda b: ['left']
    core.apply_move = lambda b, d, rng: {'board': [r[:] for r in b], 'gained': 0,
                                         'moved': True, 'spawn': None, 'spawn_pos': None}
    core.is_game_over = lambda b: False
    solver_v6.solve = lambda board, strategy, **kw: {
        'best_direction': 'left', 'elapsed_ms': 0.01, 'backend_used': 'cpp',
        'engine_used': 'python_kernel'}


def _unpatch():
    core.legal_moves, core.apply_move = _ORIG['legal'], _ORIG['apply']
    core.is_game_over, solver_v6.solve = _ORIG['over'], _ORIG['solve']


class ReportPolicyTest(unittest.TestCase):
    def setUp(self):
        _patch_fakes()

    def tearDown(self):
        _unpatch()

    def _snap(self, tag):
        return core.build_snapshot(BOARD, 0, 0, core.rng_state_to_json(random.getstate()),
                                   tag, 0, 'expectimax', 'fast')

    def _run(self, limits, **kw):
        reports = []
        res = game_loop.run_session(self._snap('rp'), limits,
                                    progress_cb=lambda p: reports.append(p) or True,
                                    solver_backend='cpp', **kw)
        return res, reports

    def test_steps_policy_reports_at_exact_multiples_and_budget_ends_run(self):
        limits = {'report_policy': {'mode': 'steps', 'steps': 200},
                  'max_total_steps': 401, 'time_budget_s': None}
        res, reports = self._run(limits)
        self.assertEqual([r['step'] for r in reports], [200, 400],
                         '回传应严格发生在 N 的整数倍（N 不是终止预算）')
        self.assertEqual(res['status'], 'budget_reached')
        self.assertEqual(res['report_reason'], 'explicit_budget')
        self.assertEqual(res['steps'], 401)

    def test_steps_boundary_199_200_201_stop(self):
        state = {'n': 0}

        def cancel():
            state['n'] += 1
            return state['n'] > 205
        res, reports = self._run({'report_policy': {'mode': 'steps', 'steps': 200},
                                  'max_total_steps': None}, cancel=cancel)
        self.assertEqual([r['step'] for r in reports], [200])
        self.assertEqual(res['status'], 'stopped')
        self.assertEqual(res['report_reason'], 'stop')
        self.assertGreaterEqual(res['steps'], 200)

    def test_steps_boundary_399_400_401(self):
        state = {'n': 0}

        def cancel():
            state['n'] += 1
            return state['n'] > 405
        res, reports = self._run({'report_policy': {'mode': 'steps', 'steps': 200},
                                  'max_total_steps': None}, cancel=cancel)
        self.assertEqual([r['step'] for r in reports], [200, 400])
        # cancel 在步首判定：会多走若干步后才停止，故只需确认越过 400 且非 200/400 处被截断
        self.assertGreaterEqual(res['steps'], 401)
        self.assertEqual(res['status'], 'stopped')

    def test_no_implicit_cutoff_without_any_budget(self):
        state = {'n': 0}

        def cancel():
            state['n'] += 1
            return state['n'] > 260
        res, _ = self._run({'report_policy': {'mode': 'steps', 'steps': 200},
                            'max_total_steps': None, 'time_budget_s': None}, cancel=cancel)
        self.assertGreater(res['steps'], 200, '不得在 200 步自动结束')
        self.assertNotEqual(res['status'], 'completed')

    def test_pause_returns_final_with_rng(self):
        state = {'n': 0}

        def pause():
            state['n'] += 1
            return state['n'] > 250
        res, reports = self._run({'report_policy': {'mode': 'steps', 'steps': 200},
                                  'max_total_steps': None}, pause=pause)
        self.assertEqual(res['status'], 'paused')
        self.assertEqual(res['report_reason'], 'pause')
        self.assertTrue(res['snapshot']['rng_state'], 'FINAL 必须带精确 RNG 状态')
        self.assertEqual([r['step'] for r in reports], [200])

    def test_time_policy_reports_by_clock(self):
        limits = {'report_policy': {'mode': 'time', 'ms': 250},
                  'max_total_steps': None, 'time_budget_s': 1.2}
        t0 = time.perf_counter()
        res, reports = self._run(limits)
        self.assertEqual(res['status'], 'budget_reached')
        self.assertGreaterEqual(len(reports), 2, '1.2s 内按 250ms 目标应回传 ≥2 次')
        walls = [r['wall_ms'] for r in reports]
        self.assertEqual(walls, sorted(walls), '报告墙钟应单调')
        self.assertLess(time.perf_counter() - t0, 30)

    def test_real_game_ends_naturally_before_200(self):
        """回归说明：真实规则下可能在 200 步前自然终局，这属于正常终局而非回传截断。"""
        _unpatch()
        try:
            res = game_loop.run_session(self._snap('real'),
                                        {'report_policy': {'mode': 'steps', 'steps': 200},
                                         'max_total_steps': 401}, solver_backend='cpp')
            self.assertIn(res['status'], ('game_over', 'budget_reached', 'stopped'))
            self.assertNotEqual(res.get('report_reason'), 'periodic_steps')
        finally:
            _patch_fakes()


if __name__ == '__main__':
    unittest.main(verbosity=2)
