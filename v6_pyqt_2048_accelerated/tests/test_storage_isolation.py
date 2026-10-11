#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 存档/会话隔离门禁（离屏，不触碰真实存档）。

验证：
- V6 的 game_history / solver_results 落在 V6 目录下，且不写入 v1–v5 目录；
- 会话采用原子保存 + `.bak` 回退（损坏主文件时回滚）；
- 导出写入 V6 的 exports 目录；
- V6 不创建/不覆盖正式 RL 模型。
"""

import json
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if V6_DIR not in sys.path:
    sys.path.insert(0, V6_DIR)


class StorageIsolationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        import v6_pyqt_2048_accelerated as m
        cls.m = m
        cls.w = m.V6MainWindow()

    @classmethod
    def tearDownClass(cls):
        # 必须**完整关闭**窗口（而非只 hide）：closeEvent 会释放单实例锁并移除方向键事件过滤器，
        # 否则遗留窗口会占用存档锁，令后续测试类的窗口进入只读并弹出模态提示（离屏下卡死）。
        try:
            cls.w.close()
        except Exception:                                    # noqa: BLE001
            pass
        try:
            for _ in range(3):
                cls.app.processEvents()
        except Exception:                                    # noqa: BLE001
            pass

    def test_paths_under_v6(self):
        m = self.m
        self.assertTrue(m.V6_RESULT_DIR.startswith(V6_DIR))
        self.assertTrue(m.V6_EXPORT_DIR.startswith(V6_DIR))
        self.assertTrue(m.V6_SESSIONS_FILE.startswith(V6_DIR))
        self.assertTrue(m.V6_HISTORY_DIR.startswith(V6_DIR))
        self.assertTrue(self.w.model.history_dir.startswith(V6_DIR),
                        'V6 存档目录未落在 V6 目录：%s' % self.w.model.history_dir)

    def test_session_atomic_save_and_bak(self):
        m = self.m
        w = self.w
        w._sessions = [{'id': 'a', 'steps': []}]
        w._save_sessions()
        self.assertTrue(os.path.exists(m.V6_SESSIONS_FILE))
        with open(m.V6_SESSIONS_FILE, encoding='utf-8') as f:
            first = json.load(f)
        self.assertEqual(first[0]['id'], 'a')
        # 第二次保存 -> 旧主文件转存 .bak
        w._sessions = [{'id': 'a', 'steps': []}, {'id': 'b', 'steps': []}]
        w._save_sessions()
        self.assertTrue(os.path.exists(m.V6_SESSIONS_FILE + '.bak'))
        with open(m.V6_SESSIONS_FILE, encoding='utf-8') as f:
            second = json.load(f)
        self.assertEqual(len(second), 2)

    def test_corrupt_primary_falls_back_to_bak(self):
        m = self.m
        w = self.w
        w._sessions = [{'id': 'x', 'steps': []}]
        w._save_sessions()                    # 生成 .bak（若已有主文件）
        w._sessions = [{'id': 'y', 'steps': []}]
        w._save_sessions()                    # 现在 .bak = x, main = y
        with open(m.V6_SESSIONS_FILE, 'w', encoding='utf-8') as f:
            f.write('{ this is not json')
        loaded = w._load_sessions()
        self.assertTrue(loaded, '损坏主文件时未回退到 .bak')
        self.assertEqual(loaded[0]['id'], 'x')

    def test_export_under_v6(self):
        m = self.m
        w = self.w
        sess = {'id': 'unit_export', 'steps': [
            {'step': 1, 'name': '向左', 'eval': 1.0, 'depth_reached': 4,
             'timed_out': False, 'score': 10, 'max_tile': 4, 'elapsed_ms': 3.0}]}
        paths = w._export_session(sess)
        self.assertTrue(paths['json'].startswith(m.V6_EXPORT_DIR))
        self.assertTrue(os.path.exists(paths['json']))
        self.assertTrue(os.path.exists(paths['csv']))

    def test_no_v6_model_override(self):
        # V6 不创建自己的模型文件（只读 V5 正式模型）
        self.assertFalse(os.path.exists(os.path.join(V6_DIR, 'rl_model.npz')),
                         'V6 不应创建/覆盖模型文件')


if __name__ == '__main__':
    unittest.main(verbosity=2)
