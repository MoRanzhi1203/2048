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
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver'))

import core                                                          # noqa: E402
import game_loop                                                     # noqa: E402
import safe_store                                                    # noqa: E402

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


class CheckpointRetryTest(unittest.TestCase):
    """P0：Windows 瞬时锁（PermissionError）有界重试的成功路径与失败上报 / 实际耗时记录。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='v6_ckpt_retry_')
        self.path = os.path.join(self.dir, 'ck.json')
        self._orig = game_loop._store.atomic_write_json

    def tearDown(self):
        game_loop._store.atomic_write_json = self._orig

    def test_bounded_retry_records_attempts_and_time(self):
        calls = {'n': 0}
        orig = self._orig

        def flaky(path, payload):
            calls['n'] += 1
            if calls['n'] <= 3:
                raise PermissionError('WinError 32 瞬时占用')
            return orig(path, payload)

        game_loop._store.atomic_write_json = flaky
        ck = game_loop.Checkpoint(self.path)
        ck.RETRY_SLEEP_S = 0.001
        ck.save({'ok': 1})
        self.assertEqual(calls['n'], 4, '应为 3 次瞬时锁失败 + 第 4 次成功')
        st = ck.stats()
        self.assertEqual(st['retries'], 3)
        self.assertGreater(st['retry_ms'], 0.0, '必须记录重试的实际等待耗时')
        self.assertEqual(st['failures'], 0)
        self.assertTrue(os.path.exists(self.path))

    def test_exhaustion_reports_failure_with_context(self):
        def always_locked(path, payload):
            raise PermissionError('WinError 5 持续占用')

        game_loop._store.atomic_write_json = always_locked
        ck = game_loop.Checkpoint(self.path)
        ck.MAX_RETRIES = 4
        ck.RETRY_SLEEP_S = 0.001
        with self.assertRaises(IOError) as cm:
            ck.save({'ok': 1})
        msg = str(cm.exception)
        self.assertIn('4 次', msg, '失败必须显式上报尝试次数')
        self.assertIn('ms', msg, '失败必须显式上报实际耗时')
        self.assertEqual(ck.stats()['failures'], 1)
        self.assertEqual(ck.stats()['retries'], 4)

    def test_run_session_surfaces_checkpoint_stats(self):
        st = core.rng_state_to_json(random.getstate())
        snap = core.build_snapshot(BOARD, 0, 0, st, 'g', 0, 'expectimax', 'fast')
        ck = game_loop.Checkpoint(os.path.join(self.dir, 'run_ck.json'))
        r = game_loop.run_session(snap, {'max_total_steps': 3}, checkpoint=ck)
        self.assertEqual(r['steps'], 3)
        self.assertIsNotNone(r['checkpoint_stats'])
        self.assertIn('checkpoint_retry_ms', r['perf'])
        self.assertEqual(r['perf']['checkpoint_retry_count'], 0)


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


class BackgroundHistoryEquivalenceTest(unittest.TestCase):
    """P1 / G4：后台方向序列回放后，官方逐笔历史 / 撤销重做 / RNG / 持久化与正常对局等价。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix='v6_bg_hist_')
        os.environ['2048_HISTORY_DIR'] = cls._tmp
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('2048_HISTORY_DIR', None)

    def setUp(self):
        import v6_pyqt_2048_accelerated as M
        self.win = M.V6MainWindow()
        self.model = self.win.model
        self.model.start_new_game()               # 建立“当前官方对局”（含 history.csv）
        self.model.grid = [row[:] for row in BOARD]
        self.model.score = 0
        self._base_rows = len(self.model.history_rows)
        self._base_best = int(getattr(self.model, 'best_score', 0))

    def tearDown(self):
        try:
            self.win.close()
        except Exception:                                          # noqa: BLE001
            pass

    def test_replay_reproduces_official_history_and_undo(self):
        import v6_background as bg
        steps = 12
        random.seed(20261012)
        handoff_rng = random.getstate()
        snap = core.build_snapshot([row[:] for row in BOARD], 0, 0,
                                   core.rng_state_to_json(handoff_rng), 'g', 0,
                                   'expectimax', 'fast')
        r = game_loop.run_session(snap, {'max_total_steps': steps})
        dirs = r['directions']
        final = r['snapshot']
        self.assertEqual(len(dirs), steps)

        # 按正常对局语义回放（单一写入者＝官方模型）；回放期不落盘，校验后单次提交
        bg.replay_commit(self.model, dirs,
                         start_rng_state_json=core.rng_state_to_json(handoff_rng),
                         cursor=0, base_grid=BOARD)
        bg.persist_official(self.model)

        # 棋盘 / 分数 / 最高分 / 完整 RNG 与后台快照一致
        self.assertEqual([row[:] for row in self.model.grid], final['board'])
        self.assertEqual(self.model.score, final['score'])
        self.assertEqual(self.model.best_score, max(self._base_best, final['score']))
        self.assertEqual(core.rng_state_to_json(random.getstate()), final['rng_state'])

        # 官方逐笔历史：每步 2 行（方向 + 添加新方块）
        self.assertEqual(len(self.model.history_rows), self._base_rows + 2 * steps)
        self.assertEqual(self.model.history_count, len(self.model.history_rows))

        # 撤销 / 重做栈与正常对局一致
        self.assertEqual(len(self.model.undo_stack), steps)
        self.assertTrue(self.model.can_undo())
        self.assertTrue(self.model.undo())
        self.assertTrue(self.model.can_redo())
        self.assertTrue(self.model.redo())
        self.assertEqual([row[:] for row in self.model.grid], final['board'])

        # 正式持久化（原子写）：game_state.json 内容 = 最终官方状态
        gdir = os.path.join(self.model.history_dir, self.model.game_id)
        st_path = os.path.join(gdir, 'game_state.json')
        self.assertTrue(os.path.exists(st_path))
        ok, state, err = safe_store.read_json(st_path)
        self.assertTrue(ok, 'game_state.json 不可读：%s' % err)
        self.assertEqual(state['grid'], final['board'])
        self.assertEqual(state['score'], final['score'])
        self.assertTrue(os.path.exists(os.path.join(gdir, 'history.csv')))

    def test_background_controller_is_wired(self):
        """旧后台四按钮已移除；统一「AI 运行控制」控件必须存在且回传固定 500ms。"""
        ctl = getattr(self.win, '_v6_bg_controller', None)
        self.assertIsNotNone(ctl, 'V6 后台控制器未接线：后台求解在真实 GUI 中将不可用')
        panel = getattr(ctl, 'panel', None)
        self.assertIsNotNone(panel, '后台占位面板缺失')
        # 旧后台四按钮/报告配置必须已移除（避免第二套控制）
        for gone in ('btn_start', 'btn_pause', 'btn_resume', 'btn_stop', 'btn_time',
                     'btn_steps', 'report_combo', '_set_mode', 'load_prefs', 'label'):
            self.assertFalse(hasattr(panel, gone), '旧后台控件未移除：%s' % gone)
        # 统一模块控件存在
        for name in ('v6_run_primary', 'v6_run_stop', 'v6_run_summary'):
            self.assertTrue(hasattr(self.win, name), '缺少统一控件 %s' % name)
        self.assertEqual(len(getattr(self.win, 'v6_speed_buttons', {})), 3,
                         '应只有标准/快速/后台求解三个可见档位')
        self.assertEqual(panel.report_policy(), {'mode': 'time', 'ms': 500})

    def test_unified_controls_dispatch_background(self):
        """统一主/停按钮必须正确路由到后台控制器 start/pause/resume/stop。"""
        ctl = self.win._v6_bg_controller
        calls = []
        saved = {n: getattr(ctl, n) for n in ('start', 'pause', 'resume', 'stop')}
        try:
            for n in saved:
                setattr(ctl, n, (lambda name: (lambda *a, **k: calls.append(name)))(n))
            self.win._v6_apply_tier('background', persist=False)
            ctl.state = 'GUI_IDLE'
            self.win._v6_on_run_primary()
            ctl.state = 'BG_RUNNING'
            self.win._v6_on_run_primary()
            ctl.state = 'BG_PAUSED'
            self.win._v6_on_run_primary()
            self.win._v6_on_run_stop()
            self.assertEqual(calls, ['start', 'pause', 'resume', 'stop'],
                             '统一按钮未正确接线到后台控制器')
            # 停止交接中：主按钮禁用并显示“正在停止”，防重复触发
            ctl.state = 'BG_STOPPING'
            self.win._v6_sync_run_controls()
            self.assertFalse(self.win.v6_run_primary.isEnabled())
            self.assertEqual(self.win.v6_run_primary.text(), '正在停止')
        finally:
            for n, fn in saved.items():
                setattr(ctl, n, fn)
            ctl.state = 'GUI_IDLE'
            self.win._v6_apply_tier('standard', persist=False)

    def test_standard_primary_reflects_solver_state(self):
        """标准/快速：主按钮随 _solver_running 在“开始求解/停止”之间切换，停止按钮隐藏。"""
        win = self.win
        win._v6_apply_tier('standard', persist=False)
        win._solver_running = False
        win._v6_sync_run_controls()
        self.assertEqual(win.v6_run_primary.text(), '开始求解')
        self.assertTrue(win.v6_run_stop.isHidden(), '标准模式不应显示独立停止按钮')
        win._solver_running = True
        win._v6_sync_run_controls()
        self.assertEqual(win.v6_run_primary.text(), '停止')
        win._solver_running = False
        win._v6_sync_run_controls()
        self.assertEqual(win.v6_run_primary.text(), '开始求解')

    def test_worker_launch_uses_no_window_flags(self):
        """Windows：worker 子进程必须 CREATE_NO_WINDOW（否则出现多余空白 python 窗口）。"""
        import subprocess as sp
        ctl = self.win._v6_bg_controller
        captured = {}

        class _Pipe:
            def readline(self):
                return ''

        class _P:
            pid = 1
            stdin = None
            stdout = _Pipe()

            def poll(self):
                return 0

        orig = sp.Popen
        saved_proc = ctl.proc
        sp.Popen = lambda args, **kw: (captured.update(kw) or _P())
        try:
            ok, err = ctl._launch_worker()
        finally:
            sp.Popen = orig
            ctl.proc = saved_proc
            ctl._close_stderr()
        self.assertTrue(ok, err)
        if os.name == 'nt':
            self.assertIn('creationflags', captured)
            self.assertEqual(captured['creationflags'], sp.CREATE_NO_WINDOW)
            self.assertIn('startupinfo', captured)

    def test_resume_clears_final_gate_and_resets_segment(self):
        """暂停后继续：必须清除 `_final_seen` 并重置方向游标，否则新 progress 全被丢弃。"""
        ctl = self.win._v6_bg_controller
        tmp = tempfile.mkdtemp(prefix='v6_resume_')
        path = os.path.join(tmp, 'resume.json')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        sent = []
        saved = {'_send': ctl._send, 'proc': ctl.proc, 'state': ctl.state,
                 'paused': ctl._paused_snapshot_path, 'final': ctl._final_seen,
                 'cursor': ctl._session_cursor}

        class _P:
            def poll(self):
                return None

        try:
            ctl._send = lambda msg: (sent.append(msg) or True)
            ctl.proc = _P()
            ctl._paused_snapshot_path = path
            ctl.state = 'BG_PAUSED'
            ctl._final_seen = True
            ctl._session_cursor = 88
            ctl.resume()
            self.assertFalse(ctl._final_seen, '恢复后必须清除终态门，否则 progress 被丢弃')
            self.assertEqual(ctl._session_cursor, 0)
            self.assertEqual(ctl.state, 'BG_RUNNING')
            self.assertTrue(any(m.get('cmd') == 'start' for m in sent), '恢复未发送 start')
        finally:
            ctl._send = saved['_send']
            ctl.proc = saved['proc']
            ctl.state = saved['state']
            ctl._paused_snapshot_path = saved['paused']
            ctl._final_seen = saved['final']
            ctl._session_cursor = saved['cursor']

    def test_bg_progress_updates_both_areas_and_logs_once(self):
        """同一 PROGRESS 必须同时刷新顶部摘要与下方 solver_status/metrics，并按 revision 去重日志。"""
        win = self.win
        win._solver_running = False
        win._v6_bg_log_key = None
        p = {'revision': 7, 'steps': 123, 'score': 456, 'max_tile': 64,
             'steps_per_s': 12.5, 'backend_used': 'cpp', 'engine_used': 'python_kernel',
             'elapsed_s': 3.2, 'render_age_ms': 120}
        win._v6_apply_bg_progress(p)
        self.assertIn('123', win.solver_status.text())
        self.assertIn('456', win.solver_status.text())
        self.assertEqual(win.solver_metrics['steps'].text(), '123')
        self.assertEqual(win.solver_metrics['score'].text(), '456')
        self.assertEqual(win.solver_metrics['max_tile'].text(), '64')
        self.assertEqual(win.solver_metrics['elapsed'].text(), '3.2s')
        n1 = win.solver_log.count()
        self.assertGreaterEqual(n1, 1)
        win._v6_apply_bg_progress(dict(p))                 # 同 revision：不重复写日志
        self.assertEqual(win.solver_log.count(), n1)
        win._v6_apply_bg_progress(dict(p, revision=8))     # 新 revision：追加一条
        self.assertEqual(win.solver_log.count(), n1 + 1)

    def test_mode_effects_policy(self):
        """P4：standard 粒子开；fast/background 粒子在发射前抑制；background 方向光静态。"""
        import v6_speed as sp
        win = self.win
        layer = getattr(win.board_view, '_particle_layer', None)
        self.assertIsNotNone(layer, '棋盘缺少粒子绘制层')
        ov = getattr(win, '_hint_overlay', None)
        self.assertIsNotNone(ov, '缺少方向提示层')

        self.assertFalse(sp.MODE_PARAMS['standard']['particles_off'])
        self.assertTrue(sp.MODE_PARAMS['fast']['particles_off'])
        self.assertTrue(sp.MODE_PARAMS['background']['particles_off'])
        self.assertTrue(sp.MODE_PARAMS['fast']['flow'])
        self.assertFalse(sp.MODE_PARAMS['background']['flow'])

        win._v6_apply_tier('standard', persist=False)
        self.assertFalse(getattr(layer.emit_zones_from, '_v6_noop', False))
        self.assertTrue(ov.flow_enabled)

        win._v6_apply_tier('fast', persist=False)
        self.assertTrue(getattr(layer.emit_zones_from, '_v6_noop', False), 'fast 粒子未抑制')
        self.assertTrue(getattr(layer.emit_from, '_v6_noop', False))
        self.assertTrue(ov.flow_enabled, 'fast 必须保留动态方向光')

        win._v6_apply_tier('background', persist=False)
        self.assertTrue(getattr(layer.emit_zones_from, '_v6_noop', False))
        self.assertFalse(ov.flow_enabled, 'background 方向光必须静态（停流光计时器）')

        win._v6_apply_tier('standard', persist=False)      # 复原，避免影响其他用例

    def test_drain_coalesces_progress_to_newest(self):
        """一次排空只渲染最新一帧（避免连续闪过好几批步长切片）。"""
        ctl = self.win._v6_bg_controller
        rendered = []
        orig = ctl._render_snapshot
        ctl._render_snapshot = lambda m: rendered.append(m.get('revision'))
        try:
            ctl._reset_session_tracking()
            ctl._game_id = 'sess'
            ctl.state = 'BG_RUNNING'
            for rev in (1, 2, 3, 4, 5):
                ctl._q.put(json.dumps({'type': 'progress', 'game_id': 'sess', 'revision': rev,
                                       'total_committed_moves': rev, 'board': [[0] * 4] * 4,
                                       'score': 0}))
            ctl._q.put(json.dumps({'type': 'progress', 'game_id': 'sess', 'revision': 9,
                                   'total_committed_moves': 9, 'board': [[0] * 4] * 4,
                                   'score': 0}))
            ctl._on_drain()
        finally:
            ctl._render_snapshot = orig
            ctl.state = 'GUI_IDLE'
            ctl._game_id = None
        self.assertEqual(rendered, [9], '同一批排空只应渲染最新一帧')

    def test_new_session_resets_revision_tracking(self):
        """跨会话 revision 跟踪必须重置（否则第二次开始前盘会把新帧当过期帧丢弃）。"""
        ctl = self.win._v6_bg_controller
        ctl._rendered_revision = 500
        ctl._adopted_revision = 600
        ctl._last_render_step = 77
        ctl._final_seen = True
        ctl._reset_session_tracking()
        self.assertEqual(ctl._rendered_revision, -1)
        self.assertEqual(ctl._adopted_revision, -1)
        self.assertEqual(ctl._last_render_step, 0)
        self.assertFalse(ctl._final_seen)

    def test_replay_defers_disk_writes_until_single_commit(self):
        """P0 根因回归：回放期间不得逐笔落盘（曾致 Qt 主线程暂停卡死 ~111s）。"""
        import v6_background as bg
        import safe_store
        steps = 20
        board = [row[:] for row in BOARD]
        random.seed(4242)
        rng = random.getstate()
        snap = core.build_snapshot(board, 0, 0, core.rng_state_to_json(rng), 'g', 0,
                                   'expectimax', 'fast')
        r = game_loop.run_session(snap, {'max_total_steps': steps})
        writes = {'csv': 0, 'json': 0}
        oc, oj = safe_store.atomic_write_csv, safe_store.atomic_write_json

        def _c(*a, **k):
            writes['csv'] += 1
            return oc(*a, **k)

        def _j(*a, **k):
            writes['json'] += 1
            return oj(*a, **k)

        safe_store.atomic_write_csv, safe_store.atomic_write_json = _c, _j
        try:
            stats = {}
            bg.replay_commit(self.model, r['directions'],
                             start_rng_state_json=core.rng_state_to_json(rng),
                             cursor=0, base_grid=board, stats=stats)
            self.assertEqual(writes['csv'], 0, '回放期间不得逐笔写 history.csv')
            self.assertEqual(writes['json'], 0, '回放期间不得逐笔写存档 JSON')
            self.assertGreater(stats.get('suppressed_io_calls', 0), 0,
                               '应统计到被抑制的逐笔落盘调用')
            bg.persist_official(self.model)              # 校验后单次提交
            self.assertGreaterEqual(writes['csv'], 1)
            self.assertGreaterEqual(writes['json'], 1)
        finally:
            safe_store.atomic_write_csv, safe_store.atomic_write_json = oc, oj

    def test_replay_refuses_when_model_mutated(self):
        import v6_background as bg
        board_before = [row[:] for row in self.model.grid]
        # 模拟后台运行期间模型被并发写者改动：必须拒绝回放（保持单一写入者）
        bg.replay_commit(self.model, ['left'], base_grid=board_before)   # 合法
        with self.assertRaises(RuntimeError):
            bg.replay_commit(self.model, ['left'], base_grid=board_before)  # 已偏离基准


class ReportPrefsMigrationTest(unittest.TestCase):
    """P2：旧报告偏好（N 步 / N 时间）必须迁移为固定内部周期（当前 500ms），幂等且不影响其它偏好。"""

    def test_legacy_report_policy_migrates_to_fixed_interval(self):
        import v6_speed as sp
        prefs = {'report_mode': 'steps', 'report_value': 200,
                 'run_mode': 'fast', 'modes_version': sp.PREFS_VERSION}
        out, changed, _reason = sp.migrate_prefs(prefs)
        self.assertTrue(changed)
        self.assertEqual(out.get('report_interval_ms'), 500)
        self.assertNotIn('report_mode', out, '旧 N 步策略未被移除')
        self.assertNotIn('report_value', out)
        self.assertEqual(out.get('run_mode'), 'fast', '不应改动无关偏好（运行方式）')

    def test_migration_is_idempotent(self):
        import v6_speed as sp
        prefs = {'report_prefs_version': 3, 'report_interval_ms': 500,
                 'run_mode': 'standard', 'modes_version': sp.PREFS_VERSION}
        out, changed, _reason = sp.migrate_prefs(dict(prefs))
        self.assertFalse(changed, '已迁移的偏好不应再次触发迁移')
        self.assertEqual(out.get('report_interval_ms'), 500)


_IPC_E2E = os.environ.get('V6_RUN_IPC_E2E') == '1'


@unittest.skipUnless(_IPC_E2E, 'IPC E2E（需 V6_RUN_IPC_E2E=1）：会真实拉起 worker 子进程并读写'
                               '暂存检查点，为保持默认门禁快速/确定性而默认跳过，可单独运行取证。'
                               '（原首解冷启动卡死已修复：cpp 求解路径不再冷导入 numpy）')
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
        # 用稀疏棋盘（仅两块低值方块）确保本局足够长，稳定覆盖 pause→resume→stop。
        # 若用接近终局的满盘，AI 可能在两次周期回传之间就走到终局，导致协议流程无法覆盖。
        e2e_board = [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2]]
        snap = core.build_snapshot(e2e_board, 0, 0, core.rng_state_to_json(random.getstate()),
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
        # Windows：worker 每步用 os.replace 原子覆盖检查点；读侧若与此竞争会瞬时
        # PermissionError。读侧必须重试（不能长时间持有句柄），否则会与 worker 的原子写互相加锁。
        ok, ck, err = False, None, None
        for _ in range(50):
            ok, ck, err = safe_store.read_json(staging)
            if ok:
                break
            time.sleep(0.02)
        self.assertTrue(ok, '检查点持续不可读：%s' % (err,))
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


    def test_stop_while_paused_exits_worker(self):
        """P3 回归：暂停后常驻 worker 必须响应 stop 并协作退出（此前会被忽略）。"""
        import ownership as own
        tmp = tempfile.mkdtemp(prefix='v6_paused_stop_')
        staging = os.path.join(tmp, 'bg_checkpoint.json')
        proc = self._spawn()
        self._read_until(proc, 'ready')
        snap = core.build_snapshot([[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 2]], 0, 0,
                                   core.rng_state_to_json(random.getstate()), 'ps', 0,
                                   'expectimax', 'fast')
        sp = os.path.join(tmp, 'snap.json')
        with open(sp, 'w', encoding='utf-8') as f:
            f.write(core.snapshot_to_json(snap))
        m0 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'start', 'snapshot_path': sp,
                                     'limits': {'max_total_steps': None, 'max_seconds': None,
                                                'report_policy': {'mode': 'time', 'ms': 300}},
                                     'backend': 'cpp', 'staging': staging,
                                     'ownership': tmp}) + '\n')
        proc.stdin.flush()
        self._read_until(proc, 'warmed', timeout=300, since=m0)
        self._read_until(proc, 'progress', timeout=120, since=m0)
        m1 = self._mark(proc)
        proc.stdin.write(json.dumps({'cmd': 'pause'}) + '\n')
        proc.stdin.flush()
        paused = self._read_until(proc, 'final', timeout=120, since=m1)
        self.assertIn(paused['status'], ('paused', 'stopped'))
        proc.stdin.write(json.dumps({'cmd': 'stop'}) + '\n')
        proc.stdin.flush()
        t0 = time.time()
        while time.time() - t0 < 60 and proc.poll() is None:
            time.sleep(0.05)
        proc.wait(timeout=30)
        self.assertEqual(proc.returncode, 0, '暂停常驻期 stop 未使 worker 退出')
        for _ in range(100):
            if own.owner_status(tmp)['state'] != 'alive':
                break
            time.sleep(0.02)
        self.assertNotEqual(own.owner_status(tmp)['state'], 'alive', '退出后所有权未释放')


if __name__ == '__main__':
    unittest.main(verbosity=2)
