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


    def test_hint_overlay_shared_renderer_and_ab_border(self):
        """V6 复用 V5 渲染器；A+B 不越出外轮廓/不覆盖瓦片/其他三边不变；A 亮区 65–80%；B 在内部间隙。"""
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainterPath, QImage, QColor
        import numpy as np
        import v4_pyqt_2048_animated as v4
        ov = self.w._hint_overlay
        self.assertIsNotNone(ov, 'V6 未继承到提示高亮层')
        self.assertIn('v5_pyqt_2048_solver', type(ov).__module__,
                      'V6 应复用 V5 的统一实现，不得复制分叉渲染器')
        W, PAD, R = v4.BOARD_SIDE, v4.BOARD_PADDING, v4.BOARD_RADIUS
        SZ, GP = v4.TILE_SIZE, v4.TILE_GAP
        outer = QPainterPath(); outer.addRoundedRect(QRectF(0, 0, W, W), R, R)
        inner = QPainterPath(); inner.addRoundedRect(
            QRectF(PAD, PAD, W - 2 * PAD, W - 2 * PAD), max(0.0, R - PAD), max(0.0, R - PAD))
        X, Y = np.meshgrid(np.arange(W) + 0.5, np.arange(W) + 0.5)
        step = SZ + GP
        tile = np.zeros((W, W), bool)
        for rr in range(4):
            for cc in range(4):
                x0 = PAD + cc * step; y0 = PAD + rr * step
                tile |= (X >= x0 + 1) & (X < x0 + SZ - 1) & (Y >= y0 + 1) & (Y < y0 + SZ - 1)
        gc = [PAD + SZ + GP / 2.0 + k * step for k in range(3)]
        vgap = np.zeros((W, W), bool); hgap = np.zeros((W, W), bool)
        for c in gc:
            vgap |= (X >= c - GP / 2.0) & (X < c + GP / 2.0)
            hgap |= (Y >= c - GP / 2.0) & (Y < c + GP / 2.0)
        interior = (X >= PAD + 1) & (X < W - PAD - 1) & (Y >= PAD + 1) & (Y < W - PAD - 1)
        gaps = (vgap | hgap) & interior
        bands = {'up': Y < PAD, 'down': Y >= W - PAD, 'left': X < PAD, 'right': X >= W - PAD}
        corner = ((X < PAD) | (X >= W - PAD)) & ((Y < PAD) | (Y >= W - PAD))
        for d in ('up', 'down', 'left', 'right'):
            self.w._show_hint(d)
            pump(self.app, 90)
            img = QImage(ov.width(), ov.height(), QImage.Format_ARGB32_Premultiplied)
            img.fill(QColor(0, 0, 0, 0))
            ov.render(img)
            H, Wd = img.height(), img.width()
            arr = np.frombuffer(img.constBits().asstring(img.byteCount()),
                                dtype=np.uint8).reshape(H, Wd, 4)
            alpha = arr[:, :, 3].astype(np.int32)
            ys, xs = np.where(alpha > 0)
            self.assertGreater(len(xs), 0, 'V6 %s 无着色' % d)
            for x, y in zip(xs[::9], ys[::9]):
                self.assertTrue(outer.intersects(QRectF(int(x), int(y), 1.0, 1.0)),
                                'V6 %s 越出棋盘外轮廓' % d)
            self.assertEqual(int(((alpha > 0) & tile).sum()), 0, 'V6 %s 覆盖瓦片' % d)
            other = np.zeros((H, Wd), bool)
            for s, bm in bands.items():
                if s != d:
                    other |= bm
            other &= ~corner
            self.assertEqual(int((alpha[other] > 0).sum()), 0, 'V6 %s 其他三边被改动' % d)
            off = max(1, int(PAD * 0.4))
            if d == 'up':
                prof = alpha[off, :]
            elif d == 'down':
                prof = alpha[H - 1 - off, :]
            elif d == 'left':
                prof = alpha[:, off]
            else:
                prof = alpha[:, Wd - 1 - off]
            thr = 0.5 * float(prof.max())
            idx = np.where(prof >= thr)[0]
            self.assertGreater(len(idx), 0, 'V6 %s A 层暖白缺失' % d)
            ext = int(idx.max() - idx.min() + 1)
            L = H if d in ('left', 'right') else Wd
            self.assertGreaterEqual(ext / L, 0.65, 'V6 %s 暖白亮区过短' % d)
            self.assertLessEqual(ext / L, 0.80, 'V6 %s 暖白亮区过长' % d)
            self.assertGreater(int(((alpha > 0) & gaps).sum()), 0, 'V6 %s B 层流光缺失' % d)
        self.w._clear_hint()
        pump(self.app, 40)


    def test_hint_flow_three_channels_all_directions(self):
        """V6 继承 V5 的 B 层三通道实现：四方向三条缝隙均有流光，无永久空通道，朝目标边运动。"""
        import numpy as np
        import v4_pyqt_2048_animated as v4
        from PyQt5.QtGui import QImage, QColor
        ov = self.w._hint_overlay
        self.assertIn('v5_pyqt_2048_solver', type(ov).__module__)
        self.assertEqual(int(ov._STREAK_COUNT), 3, 'V6 应使用三条通道')
        centers = ov._gap_centers()
        self.assertEqual(len(centers), 3, '_gap_centers 必须返回三条内部缝隙')
        step = v4.TILE_SIZE + v4.TILE_GAP
        expect = [v4.BOARD_PADDING + v4.TILE_SIZE + v4.TILE_GAP / 2.0 + k * step for k in range(3)]
        for c, e in zip(centers, expect):
            self.assertAlmostEqual(c, e, places=6)
        lo = v4.BOARD_PADDING + 2
        for d in ('up', 'down', 'left', 'right'):
            self.w._show_hint(d)
            pump(self.app, 80)
            mins = [10 ** 9, 10 ** 9, 10 ** 9]
            for _ in range(6):
                pump(self.app, 150)
                img = QImage(ov.width(), ov.height(), QImage.Format_ARGB32_Premultiplied)
                img.fill(QColor(0, 0, 0, 0))
                ov.render(img)
                H, Wd = img.height(), img.width()
                a = np.frombuffer(img.constBits().asstring(img.byteCount()),
                                  dtype=np.uint8).reshape(H, Wd, 4)[:, :, 3].astype(np.int32)
                for k, c in enumerate(centers):
                    cc = int(round(c))
                    if d in ('up', 'down'):
                        band = a[lo:H - lo, max(0, cc - 4):cc + 5]
                    else:
                        band = a[max(0, cc - 4):cc + 5, lo:Wd - lo]
                    mins[k] = min(mins[k], int((band > 0).sum()))
            self.assertTrue(all(m > 0 for m in mins),
                            'V6 %s 存在永久空通道: %s' % (d, mins))
        for d in ('up', 'down', 'left', 'right'):
            for i in range(3):
                ys = []
                for tt in (0.0, 0.25, 0.5, 0.75, 0.95):
                    ov._phase = (tt - i / 3.0) % 1.0
                    items, _ = ov._flow_items(float(ov.width()), float(ov.height()), d)
                    head = items[i][1]
                    ys.append(head[1] if d in ('up', 'down') else head[0])
                if d in ('down', 'right'):
                    self.assertTrue(all(ys[j] <= ys[j + 1] + 1e-6 for j in range(len(ys) - 1)),
                                    'V6 %s 通道%d 未朝目标边运动' % (d, i))
                else:
                    self.assertTrue(all(ys[j] >= ys[j + 1] - 1e-6 for j in range(len(ys) - 1)),
                                    'V6 %s 通道%d 未朝目标边运动' % (d, i))
        ov._phase = 0.0
        self.w._clear_hint()
        pump(self.app, 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)
