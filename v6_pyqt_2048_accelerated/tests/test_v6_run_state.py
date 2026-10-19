#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 最高分完整性 + 统一运行状态机回归（P1/P2/P3）。

覆盖：
- 后台周期快照绝不能把 Worker 的 best_score/score 写进“最高分”；
- 最高分持久化单调不减；
- 运行中切换选项卡是**非破坏性**的（不暂停/停止/重启活动任务）；
- 会话结束后才做一次安全交接；
- 标准/快速/后台共用同一套 开始/暂停/继续/停止 与模式限定文案；
- 标准/快速在安全步边界暂停、保留在途结果、恢复不重复落子。
"""

import os
import sys
import tempfile
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (V6_DIR, os.path.join(V6_DIR, 'headless'), REPO_ROOT,
           os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')):
    sys.path.insert(0, _p)

BOARD = [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2]]
BEST = 62188


class V6RunStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix='v6_run_state_')
        cls._old_hist = os.environ.get('2048_HISTORY_DIR')
        os.environ['2048_HISTORY_DIR'] = cls._tmp
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        if cls._old_hist is None:
            os.environ.pop('2048_HISTORY_DIR', None)
        else:
            os.environ['2048_HISTORY_DIR'] = cls._old_hist

    def setUp(self):
        import v6_pyqt_2048_accelerated as M
        self.win = M.V6MainWindow()
        self.win.model.start_new_game()
        self.win.model.grid = [row[:] for row in BOARD]
        self.win.model.score = 0
        self.win.model.best_score = BEST
        self.win.refresh()
        self.win._v6_apply_tier('standard', persist=False)
        self.win._solver_mode = 'auto'
        self.win._solver_running = False
        self.win._v6_active_mode = None
        self.win._v6_local_paused = False
        self.win._v6_local_pausing = False
        self.win._v6_paused_result = None

    def tearDown(self):
        try:
            ctl = getattr(self.win, '_v6_bg_controller', None)
            if ctl is not None:
                ctl.state = 'GUI_IDLE'
                ctl._cleanup_worker()
        except Exception:                                            # noqa: BLE001
            pass
        try:
            self.win.close()
        except Exception:                                            # noqa: BLE001
            pass

    # ------------------------------------------------------------ P1 最高分
    def test_background_snapshot_cannot_overwrite_best(self):
        """Worker 回传 best==score==5004 时，右上角必须保持权威 62188。"""
        self.win._v6_apply_tier('background', persist=False)
        ctl = self.win._v6_bg_controller
        ctl._rendered_revision = -1
        ctl._render_snapshot({
            'board': [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            'score': 5004, 'best_score': 5004, 'revision': 1, 'step': 1})
        self.assertIn(str(BEST), self.win.best_label.text())
        self.assertNotIn('5004', self.win.best_label.text())
        self.assertEqual(int(self.win.model.best_score), BEST)

    def test_best_store_is_monotonic(self):
        model = self.win.model
        model.save_best_score()
        model.score = 5004
        model.save_best_score()
        self.assertEqual(int(model.best_score), BEST)
        model.score = 70000
        model._sync_best_score()
        self.assertEqual(int(model.best_score), 70000)
        model.score = 100
        model._sync_best_score()
        self.assertEqual(int(model.best_score), 70000)

    # ------------------------------------------------------------ P2 非破坏性切换
    def test_tab_selection_does_not_pause_or_stop_background(self):
        w = self.win
        w._v6_apply_tier('background', persist=False)
        ctl = w._v6_bg_controller
        ctl.state = 'BG_RUNNING'
        w._v6_active_mode = 'background'
        calls = []
        saved = {n: getattr(ctl, n) for n in ('start', 'pause', 'resume', 'stop')}
        try:
            for n in saved:
                setattr(ctl, n, (lambda name: (lambda *a, **k: calls.append(name)))(n))
            w._v6_on_speed_clicked('fast')
            self.assertEqual(calls, [], '切换选项卡不得暂停/停止/重启后台 Worker')
            self.assertEqual(ctl.state, 'BG_RUNNING')
            self.assertEqual(w._v6_speed, 'background', '执行模式不得被选项卡改变')
            self.assertEqual(w._v6_selected_mode, 'fast')
            self.assertIn('已选择：快速', w.v6_run_summary.text())
            self.assertIn('后台求解模式', w.v6_run_badge.text())
        finally:
            for n, fn in saved.items():
                setattr(ctl, n, fn)
            ctl.state = 'GUI_IDLE'
            w._v6_active_mode = None
            w._v6_selected_mode = None

    def test_selected_tab_applies_after_session_ends(self):
        w = self.win
        w._v6_apply_tier('background', persist=False)
        ctl = w._v6_bg_controller
        ctl.state = 'BG_RUNNING'
        w._v6_active_mode = 'background'
        w._v6_on_speed_clicked('fast')
        ctl.state = 'GUI_IDLE'
        w._v6_active_mode = None
        w._v6_sync_run_controls()
        for _ in range(8):
            self.app.processEvents()
        self.assertEqual(w._v6_speed, 'fast')
        self.assertIsNone(w._v6_selected_mode)

    def test_tab_click_while_idle_applies_immediately(self):
        w = self.win
        w._v6_bg_controller.state = 'GUI_IDLE'
        w._v6_active_mode = None
        w._solver_running = False
        w._v6_on_speed_clicked('fast')
        self.assertEqual(w._v6_speed, 'fast')

    # ------------------------------------------------------------ P3 统一控制矩阵
    def test_local_control_matrix(self):
        w = self.win
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '开始求解')
        self.assertTrue(w.v6_run_stop.isHidden())
        self.assertIn('标准模式未运行', w.v6_run_badge.text())

        w._solver_running = True
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '暂停')
        self.assertFalse(w.v6_run_stop.isHidden())
        self.assertTrue(w.v6_run_stop.isEnabled())
        self.assertIn('标准模式运行中', w.v6_run_badge.text())
        self.assertIn('标准模式运行中', w.v6_run_summary.text())

        w._v6_local_paused = True
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '继续')
        self.assertIn('标准模式已暂停', w.v6_run_badge.text())

        w._v6_local_paused = False
        w._v6_local_pausing = True
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '正在暂停…')
        self.assertFalse(w.v6_run_primary.isEnabled())

        w._v6_local_pausing = False
        w._solver_running = False
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '开始求解')
        self.assertTrue(w.v6_run_stop.isHidden())

    def test_fast_mode_running_wording(self):
        w = self.win
        w._v6_apply_tier('fast', persist=False)
        w._solver_running = True
        w._v6_sync_run_controls()
        self.assertIn('快速模式运行中', w.v6_run_badge.text())
        self.assertIn('快速模式运行中', w.v6_run_summary.text())

    def test_background_control_matrix(self):
        w = self.win
        w._v6_apply_tier('background', persist=False)
        ctl = w._v6_bg_controller
        ctl.state = 'BG_RUNNING'
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '暂停')
        self.assertIn('后台求解模式运行中', w.v6_run_badge.text())
        self.assertTrue(w.v6_run_stop.isEnabled())
        ctl.state = 'BG_PAUSED'
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '继续')
        self.assertIn('后台求解模式已暂停', w.v6_run_badge.text())
        ctl.state = 'BG_STOPPING'
        w._v6_sync_run_controls()
        self.assertEqual(w.v6_run_primary.text(), '正在停止')
        self.assertFalse(w.v6_run_primary.isEnabled())
        self.assertFalse(w.v6_run_stop.isEnabled())
        ctl.state = 'GUI_IDLE'

    # ------------------------------------------------------------ 标准/快速安全暂停
    def test_local_pause_holds_inflight_result_and_resumes(self):
        w = self.win
        w._solver_running = True
        w._v6_active_mode = 'standard'
        w._job_id = 7
        w._solve_in_flight = True
        w._board_sig = None
        applied = []
        orig = w._ai_apply
        w._ai_apply = lambda d: applied.append(d)
        try:
            w._v6_on_run_primary()                 # 请求暂停（有在途计算）
            self.assertTrue(w._v6_local_pausing)
            self.assertEqual(w.v6_run_primary.text(), '正在暂停…')
            w._on_solver_result(7, {'best_direction': 'left'})
            self.assertEqual(applied, [], '暂停期间不得落子')
            self.assertTrue(w._v6_local_paused)
            self.assertEqual(w.v6_run_primary.text(), '继续')
            w._v6_on_run_primary()                 # 继续：复用暂存结果
            self.assertEqual(applied, ['left'])
            self.assertFalse(w._v6_local_paused)
        finally:
            w._ai_apply = orig
            w._solver_running = False
            w._v6_active_mode = None
            w._v6_local_paused = False
            w._v6_local_pausing = False
            w._v6_paused_result = None

    def test_paused_local_does_not_request_next_step(self):
        w = self.win
        w._solver_running = True
        w._v6_local_paused = True
        w._solve_in_flight = False
        emitted = []
        w.solveRequested.connect(lambda *a: emitted.append(a))
        w._request_decision()
        self.assertEqual(emitted, [])
        w._v6_local_paused = False
        w._solver_running = False


if __name__ == '__main__':
    unittest.main(verbosity=2)
