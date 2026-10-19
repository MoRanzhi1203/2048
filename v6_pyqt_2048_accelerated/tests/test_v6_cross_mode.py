#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 跨运行方式安全交接（暂停后切换并继续）专项测试。

覆盖 P1–P6 的核心语义：
- 八种“暂停 → 切换/继续”组合（标准/快速/后台两两组合）；
- 运行中切换选项卡只记录选择，绝不打断原会话；
- 交接中重复点击被拒绝；交接失败保留原暂停会话；
- 交接不改棋盘 / 分数 / 历史最高分 / RNG / 撤销栈 / 正式 game_id；
- 后台交接必须确认 Worker 退出并释放所有权，旧会话迟到消息一律丢弃。
"""

import os
import random
import sys
import tempfile
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (V6_DIR, os.path.join(V6_DIR, 'headless'), REPO_ROOT,
           os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')):
    sys.path.insert(0, _p)

BOARD = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2048, 4096], [0, 0, 0, 0]]
BEST = 62188


class CrossModeHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix='v6_cross_mode_')
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
        import v6_speed as sp
        self._saved_save_prefs = sp.save_prefs
        sp.save_prefs = lambda _p: True            # 测试不落盘偏好
        self.win = M.V6MainWindow()
        self.win.model.start_new_game()
        self.win.model.grid = [row[:] for row in BOARD]
        self.win.model.score = 628
        self.win.model.history_rows = []
        self.win.model.history_count = 0
        self.win.model.best_score = BEST
        self.win.model.undo_stack.clear()
        self.win.model.redo_stack.clear()
        self.win.refresh()
        self.win._v6_apply_tier('standard', persist=False)
        self.win._solver_mode = 'auto'
        self.win.solver_mode.setCurrentIndex(max(0, self.win.solver_mode.findData('auto')))
        self.win._solver_running = False
        self.win._v6_active_mode = None
        self.win._v6_local_paused = False
        self.win._v6_local_pausing = False
        self.win._v6_paused_result = None
        self.win._v6_handoff = None
        self.win._job_id = 40
        self.ctl = self.win._v6_bg_controller
        self.ctl._staging_dir = tempfile.mkdtemp(prefix='bg_', dir=self._tmp)
        self.ctl.state = 'GUI_IDLE'
        self.ctl.proc = None
        self.ctl._last_result = None
        self.ctl._last_progress = None
        self.ctl._game_id = None
        self.win._v6_sync_run_controls()

    def tearDown(self):
        import v6_speed as sp
        sp.save_prefs = self._saved_save_prefs
        try:
            self.ctl.state = 'GUI_IDLE'
            self.ctl._cleanup_worker()
        except Exception:                                            # noqa: BLE001
            pass
        try:
            self.win.close()
        except Exception:                                            # noqa: BLE001
            pass

    # ------------------------------------------------------------ 工具
    def _pause_local(self, mode):
        self.win._v6_apply_tier(mode, persist=False)
        self.win._solver_running = True
        self.win._v6_active_mode = mode
        self.win._v6_local_paused = True
        self.win._v6_local_pausing = False
        self.win._solve_in_flight = False
        self.win._job_id = 41
        self.win._v6_sync_run_controls()

    def _pause_background(self):
        self.win._v6_apply_tier('background', persist=False)
        self.win._v6_active_mode = 'background'
        self.win._solver_running = False
        self.ctl.state = 'BG_PAUSED'
        self.ctl._last_result = {'status': 'paused', 'snapshot': self._snapshot(),
                                 'directions': [], 'total_committed_moves': 0}
        self.ctl._last_progress = {'steps': 0, 'score': 628, 'max_tile': 4096,
                                   'steps_per_s': 0, 'backend_used': 'cpp'}
        self.win._v6_sync_run_controls()

    def _snapshot(self):
        import core
        return core.build_snapshot(
            [row[:] for row in self.win.model.grid], int(self.win.model.score),
            int(self.win.model.best_score),
            core.rng_state_to_json(random.getstate()), 'bg_sess_1', 0,
            self.win.solver_strategy.currentData(),
            self.win.solver_depth.currentData(), 'auto')

    def _state(self):
        m = self.win.model
        return {'grid': [row[:] for row in m.grid], 'score': int(m.score),
                'best': int(m.best_score), 'game_id': m.game_id,
                'undo': len(m.undo_stack), 'rng': random.getstate()}

    def _assert_preserved(self, before):
        now = self._state()
        self.assertEqual(now['grid'], before['grid'])
        self.assertEqual(now['score'], before['score'])
        self.assertEqual(now['best'], BEST, '跨模式交接不得影响历史最高分')
        self.assertEqual(now['game_id'], before['game_id'], '正式 game_id 必须保持')
        self.assertEqual(now['undo'], before['undo'], '撤销栈必须保持')
        self.assertEqual(now['rng'], before['rng'], 'RNG 状态必须保持')

    # ------------------------------------------------------------ 1/2/4：本机互切
    def test_standard_paused_resume_same_mode(self):
        self._pause_local('standard')
        calls = []
        self.win._request_decision = lambda: calls.append('req')
        self.win._v6_on_run_primary()
        self.assertEqual(calls, ['req'])
        self.assertEqual(self.win._v6_active_mode, 'standard')
        self.assertFalse(self.win._v6_local_paused)
        self.assertIn('标准模式运行中', self.win.v6_run_badge.text())

    def test_standard_paused_switch_to_fast(self):
        self._pause_local('standard')
        before = self._state()
        req = []
        self.win._request_decision = lambda: req.append(1)
        self.win._v6_on_speed_clicked('fast')
        self.assertEqual(self.win.v6_run_primary.text(), '切换至快速模式并继续')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(self.win._v6_speed, 'fast')
        self.assertEqual(self.win._v6_active_mode, 'fast')
        self.assertFalse(self.win._v6_local_paused)
        self.assertTrue(self.win._v6_anim_off, '快速模式必须关闭走子动画')
        self.assertTrue(self.win._v6_particles_off, '快速模式必须抑制合并粒子')
        self.assertEqual(self.win._job_id, 42, '新执行段必须递增 job，旧结果失效')
        self.assertEqual(req, [1], '切换后应在同一棋盘立即继续')
        self.assertIn('快速模式运行中', self.win.v6_run_badge.text())

    def test_fast_paused_switch_to_standard(self):
        self._pause_local('fast')
        before = self._state()
        self.win._request_decision = lambda: None
        self.win._v6_on_speed_clicked('standard')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(self.win._v6_active_mode, 'standard')
        self.assertFalse(self.win._v6_anim_off)
        self.assertFalse(self.win._v6_particles_off)
        self.assertIn('标准模式运行中', self.win.v6_run_badge.text())

    # ------------------------------------------------------------ 3/5：本机 → 后台
    def _fake_bg_start(self, captured, confirm=True):
        def _start(snapshot=None, handoff_meta=None):
            captured['snapshot'] = snapshot
            captured['meta'] = handoff_meta
            self.ctl.state = 'HANDOFF_PREPARE'
            self.ctl._game_id = snapshot['game_id']
            if confirm:
                self.ctl._confirm_running(handoff_meta)
            return True
        return _start

    def test_standard_paused_switch_to_background(self):
        self._pause_local('standard')
        before = self._state()
        captured = {}
        self.ctl.start = self._fake_bg_start(captured)
        self.win._v6_on_speed_clicked('background')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(self.win._v6_speed, 'background')
        self.assertEqual(self.win._v6_active_mode, 'background')
        self.assertFalse(self.win._solver_running, 'Worker 接管后本机会话必须收尾')
        self.assertEqual(self.ctl.state, 'BG_RUNNING')
        snap = captured['snapshot']
        self.assertEqual(snap['board'], before['grid'])
        self.assertEqual(snap['score'], before['score'])
        self.assertEqual(snap['best_score'], BEST)
        self.assertEqual(captured['meta']['model_game_id'], before['game_id'])
        self.assertNotEqual(snap['game_id'], before['game_id'],
                            '后台使用新的执行会话 id，但必须通过 handoff 关联正式对局')
        self.assertEqual(snap['handoff']['model_game_id'], before['game_id'])
        self.assertEqual(captured['meta']['from'], 'standard')
        self.assertEqual(captured['meta']['to'], 'background')
        self.assertIn('handoff', snap, '快照必须记录前后会话交接关系')
        self.assertIn('后台求解模式运行中', self.win.v6_run_badge.text())
        self.assertEqual(self.win.v6_run_primary.text(), '暂停')

    def test_fast_paused_switch_to_background(self):
        self._pause_local('fast')
        before = self._state()
        captured = {}
        self.ctl.start = self._fake_bg_start(captured)
        self.win._v6_on_speed_clicked('background')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(self.win._v6_active_mode, 'background')
        self.assertEqual(self.ctl.state, 'BG_RUNNING')
        self.assertEqual(captured['meta']['from'], 'fast')

    def test_background_start_failure_keeps_paused_local(self):
        self._pause_local('standard')
        before = self._state()
        captured = {}
        self.ctl.start = self._fake_bg_start(captured, confirm=False)
        self.win._v6_on_speed_clicked('background')
        self.win._v6_on_run_primary()
        self.assertIsNotNone(self.win._v6_handoff, '等待接管期间必须处于交接态')
        self.assertEqual(self.win.v6_run_primary.text(), '正在切换至后台求解模式…')
        self.assertFalse(self.win.v6_run_primary.isEnabled())
        self.assertFalse(self.win.v6_run_stop.isEnabled())
        self.win._v6_on_bg_start_failed('模拟 Worker 未接管', captured['meta'])
        self._assert_preserved(before)
        self.assertEqual(self.win._v6_active_mode, 'standard')
        self.assertTrue(self.win._v6_local_paused, '失败后原会话必须保持暂停')
        self.assertIsNone(self.win._v6_handoff)
        self.assertEqual(self.win.v6_run_primary.text(), '继续')
        self.assertIn('标准模式已暂停', self.win.v6_run_badge.text())
        self.assertIn('失败', self.win.solver_status.text())

    # ------------------------------------------------------------ 6/7/8：后台 → 本机 / 后台继续
    def _fake_drain(self, ok=True, reason='stub'):
        def _drain(on_done, deadline_s=8.0):
            if ok:
                self.ctl.state = 'GUI_IDLE'
            on_done(ok, reason)
        return _drain

    def _fake_start_local(self):
        calls = []
        state = {'id': 100}

        def _start():
            calls.append(1)
            state['id'] += 1
            self.win._job_id = state['id']
            self.win._solver_running = True
            self.win._v6_local_paused = False
            self.win._v6_local_pausing = False
        self.win._start_solver = _start
        return calls

    def test_background_paused_switch_to_standard(self):
        self._pause_background()
        before = self._state()
        self.ctl.drain_for_handoff = self._fake_drain()
        started = self._fake_start_local()
        self.win._v6_on_speed_clicked('standard')
        self.assertEqual(self.win.v6_run_primary.text(), '切换至标准模式并继续')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(started, [1], '本机求解器必须且只能启动一次')
        self.assertEqual(self.win._v6_active_mode, 'standard')
        self.assertEqual(self.win._v6_speed, 'standard')
        self.assertTrue(self.win._solver_running)
        self.assertIsNone(self.ctl._game_id, '旧后台会话 id 必须失效，迟到消息丢弃')
        self.assertTrue(self.ctl._final_seen)
        self.assertIn('标准模式运行中', self.win.v6_run_badge.text())

    def test_background_paused_switch_to_fast(self):
        self._pause_background()
        before = self._state()
        self.ctl.drain_for_handoff = self._fake_drain()
        started = self._fake_start_local()
        self.win._v6_on_speed_clicked('fast')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(started, [1])
        self.assertEqual(self.win._v6_active_mode, 'fast')
        self.assertTrue(self.win._v6_anim_off)
        self.assertTrue(self.win._v6_particles_off)
        self.assertIn('快速模式运行中', self.win.v6_run_badge.text())

    def test_background_paused_resume_background(self):
        self._pause_background()
        calls = []
        self.ctl.resume = lambda: calls.append('resume')
        self.win._v6_on_run_primary()
        self.assertEqual(calls, ['resume'])
        self.assertEqual(self.win._v6_active_mode, 'background')

    def test_background_drain_failure_keeps_paused(self):
        self._pause_background()
        before = self._state()
        started = self._fake_start_local()
        self.ctl.drain_for_handoff = self._fake_drain(False, '所有权释放超时')
        self.win._v6_on_speed_clicked('fast')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(started, [], '交接失败不得启动本机求解器')
        self.assertEqual(self.win._v6_active_mode, 'background')
        self.assertIsNone(self.win._v6_handoff)
        self.assertIn('后台求解模式已暂停', self.win.v6_run_badge.text())
        self.assertIn('失败', self.win.solver_status.text())

    # ------------------------------------------------------------ 9：运行中非破坏性
    def test_tab_switch_while_local_running_is_non_destructive(self):
        self.win._v6_apply_tier('standard', persist=False)
        self.win._solver_running = True
        self.win._v6_active_mode = 'standard'
        self.win._v6_sync_run_controls()
        self.win._v6_on_speed_clicked('fast')
        self.win._v6_on_speed_clicked('background')
        self.assertEqual(self.win._v6_speed, 'standard', '运行中不得改变执行模式')
        self.assertEqual(self.win._v6_active_mode, 'standard')
        self.assertTrue(self.win._solver_running)
        self.assertEqual(self.win._v6_selected_mode, 'background')
        self.assertEqual(self.win.v6_run_primary.text(), '暂停')
        self.assertIn('标准模式运行中', self.win.v6_run_badge.text())
        self.assertIn('已选择：后台求解模式', self.win.v6_run_summary.text())

    # ------------------------------------------------------------ 10：重复点击
    def test_duplicate_clicks_during_handoff_are_rejected(self):
        self._pause_local('standard')
        captured = {}
        start_calls = []

        def _start(snapshot=None, handoff_meta=None):
            start_calls.append(1)
            captured['meta'] = handoff_meta
            self.ctl.state = 'HANDOFF_PREPARE'
            return True
        self.ctl.start = _start
        self.win._v6_on_speed_clicked('background')
        self.win._v6_on_run_primary()
        self.assertEqual(start_calls, [1])
        self.win._v6_on_run_primary()             # 交接中重复点击
        self.win._v6_on_run_stop()                # 交接中停止
        self.win._v6_on_speed_clicked('fast')     # 交接中再次切档
        self.assertEqual(start_calls, [1], '交接中不得并发创建 Worker')
        self.assertEqual(self.win._v6_handoff['to'], 'background')
        self.assertEqual(self.win._v6_speed, 'standard')
        self.assertTrue(self.win._v6_local_paused)
        self.win._v6_on_bg_start_failed('超时', captured['meta'])

    # ------------------------------------------------------------ 11：数据正确性
    def test_handoff_preserves_rng_and_best_over_200_steps(self):
        """200 步连续落子 + 交接：最高分不回退、RNG 状态逐位保持。"""
        model = self.win.model
        random.seed(20261020)
        # 200 步正常对局语义（可能中途游戏结束，最多 200 步）
        for _ in range(200):
            if model.game_over:
                break
            legal = [d for d in ('up', 'down', 'left', 'right')]
            random.shuffle(legal)
            for d in legal:
                if model.apply_move(d):
                    break
        self.assertGreaterEqual(int(model.best_score), BEST)
        best_after_play = int(model.best_score)
        self._pause_local('standard')
        before = self._state()
        self.win._request_decision = lambda: None
        self.win._v6_on_speed_clicked('fast')
        self.win._v6_on_run_primary()
        self._assert_preserved(before)
        self.assertEqual(int(model.best_score), best_after_play, '交接后最高分不得回退')

    # ------------------------------------------------------------ 12：迟到的旧会话消息
    def test_late_final_from_old_session_is_dropped(self):
        self._pause_background()
        self.ctl._game_id = 'new_session'
        model_before = [row[:] for row in self.win.model.grid]
        self.ctl._on_msg({'type': 'final', 'status': 'completed',
                          'snapshot': {'game_id': 'old_session', 'board': [[0] * 4] * 4,
                                       'score': 0, 'rng_state': None},
                          'directions': [], 'total_committed_moves': 5})
        self.assertEqual([row[:] for row in self.win.model.grid], model_before,
                         '旧会话迟到终态不得覆盖官方棋盘')
        self.assertNotEqual(self.ctl._last_result.get('snapshot', {}).get('game_id')
                            if self.ctl._last_result else None, 'old_session')

    def test_final_after_handoff_cleanup_is_dropped(self):
        """后台→本机交接后，旧 Worker 的 final 即使 game_id 已清空也不得被采纳。"""
        self._pause_background()
        before = self._state()
        self.ctl.state = 'GUI_IDLE'
        self.ctl._final_seen = True
        self.ctl._game_id = None
        self.ctl._on_msg({'type': 'final', 'status': 'game_over',
                          'snapshot': {'game_id': 'bg_sess_1',
                                       'board': [[2] * 4] * 4, 'score': 99999,
                                       'rng_state': core_rng()},
                          'directions': [], 'total_committed_moves': 400})
        self._assert_preserved(before)


def core_rng():
    import core
    return core.rng_state_to_json(random.getstate())


if __name__ == '__main__':
    unittest.main(verbosity=2)
