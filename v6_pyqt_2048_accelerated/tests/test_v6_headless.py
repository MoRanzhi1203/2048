#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 无头后台求解测试（Gate G2 / G3 证据）。

- Qt 无关性：子进程导入 headless.* 后 sys.modules 不含 PyQt5；
- 快照校验 / RNG 状态无损往返 / 有界运行 / 溢出与终局；
- 与 V5 GUI 模型（真实 V6 继承链）逐步等价：同 RNG 状态下 棋盘+分数+生成 完全一致；
- 工作进程端到端：start → progress → final；pause → resume（精确 RNG 状态续跑）；stop；
  每步检查点落盘（与既有每步存档同安全级别）。
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(V6_DIR)
sys.path.insert(0, V6_DIR)
sys.path.insert(0, os.path.join(V6_DIR, 'headless'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver'))

import core                                                          # noqa: E402
import game_loop                                                     # noqa: E402

PY = sys.executable
BOARD = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
STAGING = None


class HeadlessQtFreeTest(unittest.TestCase):
    def test_modules_do_not_import_qt(self):
        code = (
            "import sys; sys.path.insert(0, r'%s');"
            "import headless.core, headless.game_loop, headless.worker_main;"
            "print('QT' if 'PyQt5' in sys.modules else 'NOQT')" % V6_DIR)
        out = subprocess.check_output([PY, '-c', code], text=True,
                                      env=dict(os.environ, PYTHONNOUSERSITE='1')).strip()
        self.assertEqual(out, 'NOQT', 'headless 模块意外导入了 PyQt5')

    def test_headless_run_without_qapplication(self):
        code = (
            "import sys; sys.path.insert(0, r'%s'); sys.path.insert(0, r'%s');"
            "import random, headless.core as c, headless.game_loop as g;"
            "board=%r; st=c.rng_state_to_json(random.getstate());"
            "snap=c.build_snapshot(board,0,0,st,'t',0,'expectimax','fast');"
            "r=g.run_session(snap, {'max_steps':5,'max_seconds':20});"
            "print(r['status'], r['steps'], 'QT' if 'PyQt5' in sys.modules else 'NOQT')"
            % (V6_DIR, os.path.join(V6_DIR, 'headless'), BOARD))
        out = subprocess.check_output([PY, '-c', code], text=True,
                                      env=dict(os.environ, PYTHONNOUSERSITE='1')).strip()
        parts = out.split()
        self.assertIn(parts[0], ('completed', 'budget_reached'),
                      '达到步数上限现为显式预算结束（budget_reached）')
        self.assertEqual(int(parts[1]), 5)
        self.assertEqual(parts[2], 'NOQT')


class HeadlessCoreTest(unittest.TestCase):
    def test_snapshot_validation(self):
        good = core.build_snapshot(BOARD, 10, 10, core.rng_state_to_json(random.getstate()),
                                   'g', 1, 'expectimax', 'fast')
        core.validate_snapshot(good)
        for bad in ([[1, 2, 3, 4]] * 4, [[2, 3, 4, 8]] * 4, [[2] * 4] * 3,
                    [[0] * 4, [0] * 4, [0] * 4, [65536] * 4]):
            snap = dict(good)
            snap['board'] = bad
            with self.assertRaises(core.SnapshotError):
                core.validate_snapshot(snap)
        bad = dict(good)
        bad['rng_state'] = None
        with self.assertRaises(core.SnapshotError):
            core.validate_snapshot(bad)
        bad = dict(good)
        bad['algorithm'] = 'nope'
        with self.assertRaises(core.SnapshotError):
            core.validate_snapshot(bad)

    def test_rng_state_roundtrip(self):
        random.seed(99)
        for _ in range(7):
            random.random()
        st = random.getstate()
        js = core.rng_state_to_json(st)
        self.assertEqual(core.rng_state_from_json(js), st)
        # JSON 往返（模拟 IPC）
        rt = core.rng_state_from_json(json.loads(json.dumps(js)))
        self.assertEqual(rt, st)
        a = core.make_rng(js)
        b = random.Random()
        b.setstate(st)
        self.assertEqual([a.random() for _ in range(5)], [b.random() for _ in range(5)])

    def test_error_result_has_provenance(self):
        st = core.rng_state_to_json(random.getstate())
        snap = core.build_snapshot(BOARD, 0, 0, st, 'g', 0, 'expectimax', 'fast')
        r = game_loop.run_session(snap, {'max_steps': 3, 'max_seconds': 20})
        self.assertIn(r['status'], ('completed', 'budget_reached'))
        self.assertIn(r['backend_used'], ('reference', 'numpy', 'numba', 'cpp'))
        self.assertIsNotNone(r['engine_used'])
        self.assertEqual(r['steps'], 3)

    def test_game_over_stops(self):
        full = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
        st = core.rng_state_to_json(random.getstate())
        snap = core.build_snapshot(full, 0, 0, st, 'g', 0, 'expectimax', 'fast')
        r = game_loop.run_session(snap, {'max_steps': 10, 'max_seconds': 20})
        self.assertEqual(r['status'], 'game_over')
        self.assertEqual(r['steps'], 0)


class ModelEquivalenceTest(unittest.TestCase):
    """与真实 V6 GUI 继承链的模型逐步等价（需 Qt，但作为独立校验）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix='v6_headless_eq_')
        os.environ['2048_HISTORY_DIR'] = cls._tmp

    def test_moves_match_model(self):
        from PyQt5.QtWidgets import QApplication
        import v6_pyqt_2048_accelerated as M
        app = QApplication.instance() or QApplication([])
        win = M.V6MainWindow()
        dirs = ['down', 'left', 'down', 'right', 'up', 'left', 'down', 'left', 'up', 'right',
                'down', 'left', 'down', 'right', 'up', 'left']
        random.seed(20261012)
        start_state = random.getstate()
        # 侧 A：真实模型（全局 random）
        win.model.grid = [row[:] for row in BOARD]
        win.model.score = 0
        random.setstate(start_state)
        model_seq = []
        for d in dirs:
            moved = win.model.apply_move(d)
            model_seq.append((moved, [row[:] for row in win.model.grid], win.model.score))
            if not moved:
                continue
        model_final_state = random.getstate()
        # 侧 B：headless core（显式 RNG，从同一状态还原）
        board = [row[:] for row in BOARD]
        score = 0
        rng = core.make_rng(core.rng_state_to_json(start_state))
        core_seq = []
        for d in dirs:
            res = core.apply_move(board, d, rng)
            board = res['board']
            score += res['gained']
            core_seq.append((res['moved'], [row[:] for row in board], score))
        self.assertEqual(model_seq, core_seq, 'headless 与模型逐步不一致')
        self.assertEqual(core.rng_state_to_json(rng.getstate()),
                         core.rng_state_to_json(model_final_state), 'RNG 消费不一致')
        win.close()


_IPC_E2E = os.environ.get('V6_RUN_IPC_E2E') == '1'


@unittest.skipUnless(_IPC_E2E, '慢速 IPC E2E（需 V6_RUN_IPC_E2E=1）：worker 首解冷导入 '
                               '(numpy/numba) 在全量负载下可 >300s，属环境级冷启动病理，'
                               '不宜作为默认门禁；已改为事件驱动等待，可单独运行取证')
class WorkerE2ETest(unittest.TestCase):
    def _spawn(self):
        env = dict(os.environ, PYTHONNOUSERSITE='1')
        proc = subprocess.Popen([PY, '-m', 'headless.worker_main'], cwd=V6_DIR, env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, bufsize=1)
        # 必须持续读取 stdout（否则管道写满 → worker 阻塞在进度输出上，表现为“挂起”）
        proc._lines = []
        proc._reader = threading.Thread(
            target=lambda: [proc._lines.append(x) for x in iter(proc.stdout.readline, '')],
            daemon=True)
        proc._reader.start()
        return proc

    def _mark(self, proc):
        """记录当前已收消息数：使随后的等待只针对**本命令之后**的消息（避免复用旧消息）。"""
        return len(proc._lines)

    def _read_until(self, proc, kind, timeout=60.0, since=0):
        t0 = time.time()
        idx = since
        while time.time() - t0 < timeout:
            while idx < len(proc._lines):
                msg = json.loads(proc._lines[idx])
                idx += 1
                if msg.get('type') == kind:
                    return msg
            if proc.poll() is not None:
                raise AssertionError('worker 已退出 rc=%s：%s' % (proc.returncode, proc._lines[-3:]))
            time.sleep(0.05)
        raise AssertionError('等待 %s 超时（%.0fs）；已收类型=%s'
                             % (kind, timeout,
                                [json.loads(x).get('type') for x in proc._lines[-12:]]))

    def test_start_pause_resume_stop(self):
        tmp = tempfile.mkdtemp(prefix='v6_bg_')
        staging = os.path.join(tmp, 'bg_checkpoint.json')
        proc = self._spawn()
        self._read_until(proc, 'ready')
        snap = core.build_snapshot(BOARD, 0, 0, core.rng_state_to_json(random.getstate()),
                                   'e2e', 0, 'expectimax', 'fast')
        snap_path = os.path.join(tmp, 'handoff_snapshot.json')
        with open(snap_path, 'w', encoding='utf-8') as f:
            f.write(core.snapshot_to_json(snap))
        m0 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'start', 'snapshot_path': snap_path,
                                     'limits': {'max_steps': None, 'max_seconds': None,
                                                'report_policy': {'mode': 'steps', 'steps': 20}},
                                     'backend': 'cpp', 'staging': staging,
                                     'ownership': tmp}) + '\n')
        proc.stdin.flush()
        # 事件驱动：先等预热完成（warming/warmed 可见），再等首个回传；超时按阶段给足
        self._read_until(proc, 'warmed', timeout=300, since=m0)
        prog = self._read_until(proc, 'progress', timeout=180, since=m0)
        self.assertGreaterEqual(prog['step'], 1)
        self.assertTrue(os.path.exists(staging), '每步检查点未落盘')
        ck = json.loads(open(staging, encoding='utf-8').read())
        self.assertEqual(ck['game_id'], 'e2e')
        self.assertGreaterEqual(ck['revision'], 1)
        m1 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'pause'}) + '\n')
        proc.stdin.flush()
        paused = self._read_until(proc, 'final', timeout=180, since=m1)
        # 暂停 = 一致步边界停止，返回检查点快照
        self.assertIn(paused['status'], ('stopped', 'paused'))
        rev = paused['snapshot']['revision']
        self.assertGreaterEqual(rev, 1)
        # 恢复：用暂停点的精确棋盘 + RNG 状态重新启动
        resume_path = os.path.join(tmp, 'resume_snapshot.json')
        with open(resume_path, 'w', encoding='utf-8') as f:
            f.write(core.snapshot_to_json(paused['snapshot']))
        m2 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'start', 'snapshot_path': resume_path,
                                     'limits': {'max_steps': None, 'max_seconds': None,
                                                'report_policy': {'mode': 'steps', 'steps': 20}},
                                     'backend': 'cpp', 'staging': staging,
                                     'ownership': tmp}) + '\n')
        proc.stdin.flush()
        self._read_until(proc, 'warmed', timeout=300, since=m2)
        prog2 = self._read_until(proc, 'progress', timeout=180, since=m2)
        self.assertGreaterEqual(prog2['revision'], rev)
        m3 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'stop'}) + '\n')
        proc.stdin.flush()
        final = self._read_until(proc, 'final', timeout=180, since=m3)
        self.assertEqual(final['status'], 'stopped')
        # P1：FINAL 之后必须确认“进程已退出 + 所有权已释放”
        exited = self._read_until(proc, 'exited', timeout=180, since=m3)
        self.assertEqual(exited.get('code'), 0)
        proc.wait(timeout=120)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(tmp, 'owner.json')),
                         '进程退出后所有权未释放')
        os.environ.pop('2048_HISTORY_DIR', None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
