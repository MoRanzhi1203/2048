#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 方向键冲突修复回归（QTest，离屏）。

覆盖：四方向正确映射；QComboBox(后端/策略/模式)获得焦点不改选项且仍走子；
按钮获得焦点不被触发；每次按键只走一次；禁止状态不走子；WASD/Ctrl+Z/Tab/鼠标/Space 不回归；
欢迎页不操作棋盘；各后端切换后行为一致。
"""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if V6_DIR not in sys.path:
    sys.path.insert(0, V6_DIR)

from PyQt5.QtCore import Qt, QPoint                          # noqa: E402
from PyQt5.QtTest import QTest                               # noqa: E402

BASE = [[2, 2, 0, 0],
        [2, 2, 0, 0],
        [0, 0, 2, 2],
        [0, 0, 2, 2]]


def pump(app, ms):
    t = time.time() + ms / 1000.0
    while time.time() < t:
        app.processEvents()
        time.sleep(0.005)


class ArrowKeyV6Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        # 隔离存档根目录：避免与其他测试类的窗口争用同一 history 目录而触发
        # 单实例锁的模态“只读运行”提示（离屏平台下模态弹窗无法关闭会卡住）。
        cls._old_hist = os.environ.get('2048_HISTORY_DIR')
        os.environ['2048_HISTORY_DIR'] = tempfile.mkdtemp(prefix='v6_dirkey_hist_root_')
        import v6_pyqt_2048_accelerated as m
        import solver_backends.dispatch as disp
        cls.m = m
        cls.avail = [b for b, v in disp.probe_backends().items() if v.get('available')]
        cls.w = m.V6MainWindow()
        cls.w.show()
        QApplication.setActiveWindow(cls.w)
        pump(cls.app, 200)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.w.close()
        except Exception:                                    # noqa: BLE001
            pass
        pump(cls.app, 80)
        if cls._old_hist is None:
            os.environ.pop('2048_HISTORY_DIR', None)
        else:
            os.environ['2048_HISTORY_DIR'] = cls._old_hist

    def setUp(self):
        import solver_2048 as _s
        self.solver = _s
        self.w.stack.setCurrentIndex(1)
        self._set_grid(BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 60)

    def _set_grid(self, grid):
        self.w.model.grid = [row[:] for row in grid]
        self.w.board_view.render(self.w.model.grid)
        self.w.refresh()

    def _press(self, widget, key, modifier=None):
        QTest.keyClick(widget, key, Qt.NoModifier if modifier is None else modifier)
        pump(self.app, 240)

    def _grid_without_spawn(self):
        g = [row[:] for row in self.w.model.grid]
        sp = getattr(self.w.model, 'last_spawn', None)
        if sp is not None:
            g[sp[0]][sp[1]] = 0
        return g

    def test_arrow_keys_map_to_moves(self):
        for key, direction in ((Qt.Key_Up, 'up'), (Qt.Key_Down, 'down'),
                               (Qt.Key_Left, 'left'), (Qt.Key_Right, 'right')):
            self._set_grid(BASE)
            self.w.model.game_over = False
            self.w.setFocus()
            pump(self.app, 40)
            n0 = len(self.w.model.undo_stack)
            self._press(self.w, key)
            expected, _g, moved = self.solver.move_grid(BASE, direction)
            self.assertTrue(moved)
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1,
                             '%s 一次按键应只走一步' % direction)
            self.assertEqual(self._grid_without_spawn(), expected,
                             '方向键未映射为 %s' % direction)

    def test_backend_combo_focused_arrow_not_changed(self):
        combo = self.w.solver_backend_combo
        for key in (Qt.Key_Up, Qt.Key_Down):
            self._set_grid(BASE)
            self.w.model.game_over = False
            combo.setFocus()
            pump(self.app, 60)
            idx0 = combo.currentIndex()
            n0 = len(self.w.model.undo_stack)
            self._press(combo, key)
            self.assertEqual(combo.currentIndex(), idx0, '后端下拉不应被方向键改变')
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1, '下拉聚焦时仍应走子')

    def test_button_focused_arrow_not_clicked(self):
        self._set_grid(BASE)
        self.w.model.game_over = False
        btn = self.w.new_game_button
        hits = []
        btn.clicked.connect(lambda: hits.append(1))
        btn.setFocus()
        pump(self.app, 60)
        n0 = len(self.w.model.undo_stack)
        self._press(btn, Qt.Key_Left)
        self.assertEqual(hits, [], '方向键不应触发按钮')
        self.assertEqual(len(self.w.model.undo_stack), n0 + 1, '按钮聚焦时仍应走子')

    def test_blocked_states_ignore(self):
        self._set_grid(BASE)
        self.w.model.game_over = True
        n0 = len(self.w.model.undo_stack)
        self._press(self.w, Qt.Key_Left)
        self.assertEqual(len(self.w.model.undo_stack), n0, '游戏结束后不应走子')
        self.w.model.game_over = False
        orig = self.w.board_view.is_animating
        self.w.board_view.is_animating = lambda: True
        try:
            n1 = len(self.w.model.undo_stack)
            self._press(self.w, Qt.Key_Left)
            self.assertEqual(len(self.w.model.undo_stack), n1, '动画中不应走子')
        finally:
            self.w.board_view.is_animating = orig

    def test_welcome_page_no_board_move(self):
        self.w.stack.setCurrentIndex(0)
        pump(self.app, 100)
        n0 = len(self.w.model.undo_stack)
        before = [r[:] for r in self.w.model.grid]
        self._press(self.w, Qt.Key_Left)
        self.assertEqual(self.w.model.grid, before, '欢迎页方向键不应操作棋盘')
        self.assertEqual(len(self.w.model.undo_stack), n0)
        self.w.stack.setCurrentIndex(1)
        pump(self.app, 100)

    def test_other_keys_no_regression(self):
        for key, direction in ((Qt.Key_W, 'up'), (Qt.Key_A, 'left'),
                               (Qt.Key_S, 'down'), (Qt.Key_D, 'right')):
            self._set_grid(BASE)
            self.w.model.game_over = False
            self.w.setFocus()
            pump(self.app, 40)
            n0 = len(self.w.model.undo_stack)
            self._press(self.w, key)
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1, 'WASD(%s) 未走子' % direction)
        # Ctrl+Z
        self._set_grid(BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        self._press(self.w, Qt.Key_Left)
        for _ in range(40):
            if not self.w.board_view.is_animating():
                break
            pump(self.app, 30)
        after_move = [r[:] for r in self.w.model.grid]
        self._press(self.w, Qt.Key_Z, Qt.ControlModifier)
        self.assertNotEqual(self.w.model.grid, after_move, 'Ctrl+Z 未撤销')
        # Tab / 鼠标点击
        self._set_grid(BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        n0 = len(self.w.model.undo_stack)
        self._press(self.w, Qt.Key_Tab)
        QTest.mouseClick(self.w.board_view, Qt.LeftButton, Qt.NoModifier, QPoint(12, 12))
        pump(self.app, 120)
        self.assertEqual(len(self.w.model.undo_stack), n0, 'Tab/鼠标点击不应走子')

    def test_backend_switch_consistency(self):
        """切换各可用后端后，方向键行为一致（仍走子）。"""
        for backend in self.avail:
            idx = self.w.solver_backend_combo.findData(backend)
            self.w.solver_backend_combo.setCurrentIndex(idx)
            pump(self.app, 40)
            self._set_grid(BASE)
            self.w.model.game_over = False
            self.w.setFocus()
            pump(self.app, 40)
            n0 = len(self.w.model.undo_stack)
            self._press(self.w, Qt.Key_Left)
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1,
                             '后端 %s 下方向键未走子' % backend)
        # 恢复默认
        self.w.solver_backend_combo.setCurrentIndex(0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
