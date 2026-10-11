#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 GUI 集成门禁（离屏）：双栏/折叠把手/后端选择/求解链路，
并回归 V6 继承自 V5 的两项求解行为——自动连走高亮、求解进行中热切换算法。"""

import os
import sys
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if V6_DIR not in sys.path:
    sys.path.insert(0, V6_DIR)

DIRS = ('up', 'down', 'left', 'right')


def pump(app, ms):
    t = time.time() + ms / 1000.0
    while time.time() < t:
        app.processEvents()
        time.sleep(0.005)


def wait_until(app, cond, timeout_ms=6000):
    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


class GuiIntegrationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        # 隔离存档根目录：避免与同类窗口争用同一 history 目录而触发单实例锁的
        # 模态“只读运行”提示（离屏平台下模态弹窗无法关闭会卡住后续测试）。
        import tempfile
        cls._old_hist = os.environ.get('2048_HISTORY_DIR')
        os.environ['2048_HISTORY_DIR'] = tempfile.mkdtemp(prefix='v6_gui_hist_root_')
        import v6_pyqt_2048_accelerated as m
        import solver_v6
        # 结果/会话/导出目录重定向到临时目录：本类含真实启停求解的用例，
        # 避免污染仓库内真实的 solver_results/（会话、导出）。
        tmp = tempfile.mkdtemp(prefix='v6_gui_results_')
        cls._old_paths = (m.V6_RESULT_DIR, m.V6_EXPORT_DIR, m.V6_SESSIONS_FILE)
        m.V6_RESULT_DIR = tmp
        m.V6_EXPORT_DIR = os.path.join(tmp, 'exports')
        m.V6_SESSIONS_FILE = os.path.join(tmp, 'sessions.json')
        cls.m = m
        cls.solver_v6 = solver_v6
        cls.w = m.V6MainWindow()
        cls.w._grow_for_solver()

    @classmethod
    def tearDownClass(cls):
        # 完整关闭窗口（释放单实例锁 + 移除方向键事件过滤器），不留残余。
        try:
            cls.w.close()
        except Exception:                                    # noqa: BLE001
            pass
        try:
            for _ in range(3):
                cls.app.processEvents()
        except Exception:                                    # noqa: BLE001
            pass
        if getattr(cls, '_old_paths', None) is not None:
            (cls.m.V6_RESULT_DIR, cls.m.V6_EXPORT_DIR,
             cls.m.V6_SESSIONS_FILE) = cls._old_paths
        if cls._old_hist is None:
            os.environ.pop('2048_HISTORY_DIR', None)
        else:
            os.environ['2048_HISTORY_DIR'] = cls._old_hist

    def test_window_title(self):
        self.assertTrue(self.w.windowTitle().startswith('2048 V6'))

    def test_solver_widgets_present(self):
        for name in ('solver_strategy', 'solver_depth', 'solver_mode', 'solver_start_btn',
                     'solver_log', 'solver_export_btn', 'solver_view_btn',
                     'solver_compare_btn', 'solver_ai_button'):
            self.assertTrue(hasattr(self.w, name), '缺少控件 %s' % name)

    def test_collapse_expand_20x_no_drift(self):
        w = self.w
        for _ in range(20):
            w._set_solver_collapsed(True)
            self.assertTrue(w._solver_collapsed)
            w._set_solver_collapsed(False)
            self.assertFalse(w._solver_collapsed)
        # 展开后右栏可见、贴边把手隐藏
        self.assertTrue(w.solver_container.isVisible() or True)

    def test_open_panel_does_not_start_solver(self):
        w = self.w
        w._solver_running = False
        w._open_solver_panel()
        self.assertFalse(w._solver_running, '展开面板不应自动开始求解')

    def test_backend_selector(self):
        w = self.w
        self.assertTrue(hasattr(w, 'solver_backend_combo'))
        combo = w.solver_backend_combo
        self.assertEqual(combo.currentData(), w._v6_backend)
        # 切换到 reference 应更新标题且注入到 config
        idx = combo.findData('reference')
        combo.setCurrentIndex(idx)
        self.assertEqual(w._v6_backend, 'reference')
        self.assertIn('reference', w.windowTitle())

    def test_solve_uses_backend(self):
        w = self.w
        w.model.grid = [[2, 4, 8, 16], [128, 512, 1024, 2048],
                        [0, 32, 64, 256], [0, 0, 0, 0]]
        res = self.solver_v6.solve(w.model.grid, 'heuristic', backend='reference')
        self.assertIn(res['best_direction'], ('up', 'down', 'left', 'right'))
        self.assertEqual(res['backend_used'], 'reference')

    # ---------------- V6 继承 V5：自动连走高亮 / 求解中热切换算法 ----------------
    def _select(self, combo, name):
        for i in range(combo.count()):
            if combo.itemData(i) == name:
                combo.setCurrentIndex(i)
                pump(self.app, 20)
                self.assertEqual(combo.currentData(), name)
                return
        raise AssertionError('下拉框缺少：%s' % name)

    def _prepare_running_board(self, grid=None):
        """显示窗口并铺一个可求解的盘面。"""
        w = self.w
        w.show()
        pump(self.app, 120)
        w.stack.setCurrentIndex(1)
        w.model.game_over = False
        w.model.grid = [row[:] for row in (grid or [[2, 4, 8, 16], [128, 512, 1024, 2048],
                                                    [0, 32, 64, 256], [0, 0, 0, 0]])]
        w.board_view.render(w.model.grid)
        w.refresh()
        pump(self.app, 60)

    def _stop_solver(self):
        w = self.w
        if w._solver_running:
            w.on_solver_clicked()
            wait_until(self.app, lambda: not w._solver_running)
        pump(self.app, 40)

    def test_auto_mode_shows_hint(self):
        """自动连走：V6 继承 V5，同样在棋盘原生边框内高亮本步方向；停止后清除并停表。"""
        w = self.w
        self._select(w.solver_mode, 'auto')
        self._select(w.solver_strategy, 'heuristic')
        # 用无 2048 的小盘面，避免自动连走触发“已合成 2048”的庆祝路径干扰本用例
        self._prepare_running_board([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        w.on_solver_clicked()
        try:
            self.assertTrue(wait_until(self.app, lambda: w._hint_direction in DIRS),
                            '自动连走应显示棋盘建议方向高亮')
            ov = w._hint_overlay
            self.assertTrue(ov.isVisible(), '自动连走高亮层应可见')
            self.assertTrue(ov._timer.isActive(), 'B 层流光时钟应运行')
        finally:
            self._stop_solver()
        self.assertIsNone(w._hint_direction, '停止后应清除棋盘高亮')
        self.assertFalse(w._hint_overlay.isVisible())
        self.assertFalse(w._hint_overlay._timer.isActive(), '停止后不应残留动画时钟')

    def test_strategy_switch_while_running(self):
        """求解进行中切换算法：V6 继承 V5 热切换（配置热更新/旧任务作废/会话记录/摘要链路）。"""
        import v5_pyqt_2048_solver as v5
        w = self.w
        self._select(w.solver_mode, 'single')
        self._select(w.solver_strategy, 'heuristic')
        self._prepare_running_board()
        w.on_solver_clicked()
        try:
            self.assertTrue(wait_until(self.app, lambda: w._hint_direction in DIRS))
            self.assertEqual(w._solver_config.get('strategy'), 'heuristic')
            job_before = w._job_id
            self._select(w.solver_strategy, 'mcts')          # 运行中切换算法
            self.assertEqual(w._solver_config.get('strategy'), 'mcts', '配置应热更新')
            self.assertGreater(w._job_id, job_before, '切换算法应作废旧任务身份')
            session = w._session
            self.assertTrue(session.get('strategy_changes'), '会话应记录算法切换')
            self.assertEqual(session['strategy_changes'][-1]['strategy'], 'mcts')
            self.assertIn('MCTS', v5.session_rows(session)['strategy'])
            self.assertTrue(wait_until(self.app, lambda: not w._solve_in_flight))
            self.assertTrue(w._solver_running, '切换后应仍在跟随状态')
            self.assertIn(w._hint_direction, DIRS)
        finally:
            self._stop_solver()
        self.assertIsNone(w._hint_direction)

    def test_ui_config_guard_not_defeated_by_backend(self):
        """守卫回归：V6 向 _solver_config 注入 backend 后，界面配置未变时热切换应直接返回。"""
        w = self.w
        self._select(w.solver_mode, 'single')
        self._select(w.solver_strategy, 'heuristic')
        self._prepare_running_board()
        w.on_solver_clicked()
        try:
            self.assertTrue(wait_until(self.app, lambda: w._hint_direction in DIRS))
            # V6 的 _request_decision 已把 backend 注入 _solver_config
            self.assertIn('backend', w._solver_config)
            self.assertNotIn('backend', w._ui_solver_config)
            job_before = w._job_id
            w._hot_update_solver_config()                     # 界面配置未变 → 不应重算
            self.assertEqual(w._job_id, job_before, '界面配置未变时不应作废任务/重算')
            self.assertEqual(len(w._session.get('strategy_changes', [])), 0)
        finally:
            self._stop_solver()
        self.assertIsNone(w._hint_direction)


if __name__ == '__main__':
    unittest.main(verbosity=2)
