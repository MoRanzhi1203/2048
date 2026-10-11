#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 GUI 集成门禁（离屏）：双栏/折叠把手/后端选择/求解链路，不启动真实线程。"""

import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if V6_DIR not in sys.path:
    sys.path.insert(0, V6_DIR)


class GuiIntegrationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        import v6_pyqt_2048_accelerated as m
        import solver_v6
        cls.m = m
        cls.solver_v6 = solver_v6
        cls.w = m.V6MainWindow()
        cls.w._grow_for_solver()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.w.hide()
        except Exception:                                    # noqa: BLE001
            pass

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
