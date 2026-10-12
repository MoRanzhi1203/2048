#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6「后台求解」GUI 侧监督器：所有权状态机 + 安全交接 + 低频进度 + 恢复。

约束（对齐 P3/P4/P6）：
    - 唯一写者：同一局只允许 1 个 worker（staging 目录下 `.bg.lock` 记录 pid）；
    - 状态机：GUI_IDLE -> HANDOFF_PREPARE -> BG_RUNNING -> BG_PAUSING -> BG_PAUSED
              -> BG_STOPPING -> GUI_IDLE，另有 BG_COMPLETED / BG_ERROR；
    - 进入后台前：等待动画结束、按既有安全路径停止本机 SolverWorker，再写交接检查点；
    - 进度仅只读展示，**不驱动**权威棋盘；过期消息（game_id/修订号不匹配）直接丢弃；
    - 每步持久化由 worker 写入隔离 staging 检查点（不覆盖正式存档）；
    - 关闭窗口：协作停止 + 有界等待 + 保留检查点，不盲目 terminate 存储事务。

只读复用 V5/V6 GUI 与模型；不改动 V5 源码。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

from PyQt5.QtCore import QObject, Qt, QTimer
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = _HERE
REPO_ROOT = os.path.dirname(V6_DIR)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(V6_DIR, 'headless'))

import core                                                          # noqa: E402
import ownership as own                                              # noqa: E402
import safe_store as _store                                          # noqa: E402

_EMPTY = 'GUI_IDLE'
_TRANSITIONS = {
    'GUI_IDLE': {'HANDOFF_PREPARE'},
    'HANDOFF_PREPARE': {'BG_RUNNING', 'GUI_IDLE', 'BG_ERROR'},
    'BG_RUNNING': {'BG_PAUSING', 'BG_STOPPING', 'BG_COMPLETED', 'BG_ERROR'},
    'BG_PAUSING': {'BG_PAUSED', 'BG_ERROR'},
    'BG_PAUSED': {'BG_RUNNING', 'BG_STOPPING', 'GUI_IDLE', 'BG_ERROR'},
    'BG_STOPPING': {'GUI_IDLE', 'BG_ERROR'},
    'BG_COMPLETED': {'GUI_IDLE'},
    'BG_ERROR': {'GUI_IDLE'},
}

_BTN_QSS = (
    'QPushButton { background:#3a332d; color:#e2d7c7; border:1px solid #5a5048;'
    ' border-radius:4px; padding:4px 10px; font-size:11px; }'
    'QPushButton:hover { background:#463d35; }'
    'QPushButton:disabled { color:#7a6f63; border-color:#453d36; }')


class BackgroundPanel(QWidget):
    """后台求解进度条 + 开始/暂停/继续/停止 + 「结果回传」策略（定时间/定步数，互斥）。"""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        self.label = QLabel('后台求解未启动')
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            'background:#2b2622; color:#f3ead9; border:1px solid #5a5048; border-radius:6px;'
            ' padding:5px 8px; font-family:Consolas,Menlo,monospace; font-size:11px;')
        box.addWidget(self.label)

        # ---- 结果回传（与算法/强度/求解模式完全独立；N 绝不是终止预算）----
        title = QLabel('结果回传')
        title.setStyleSheet('color:#8f8175; font-size:12px;')
        box.addWidget(title)
        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.btn_time = QPushButton('定时间')
        self.btn_steps = QPushButton('定步数')
        for b in (self.btn_time, self.btn_steps):
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                'QPushButton { background:#3a332d; color:#e2d7c7; border:1px solid #5a5048;'
                ' border-radius:4px; padding:4px 10px; font-size:11px; }'
                'QPushButton:checked { background:#c9a227; color:#241d15; font-weight:bold; }')
            seg.addWidget(b)
        box.addLayout(seg)
        self.report_combo = QComboBox()
        box.addWidget(self.report_combo)
        hint = QLabel('后台持续求解；达到回传间隔后将已完成的最新棋盘显示在左侧。暂停、停止及结束立即同步。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color:#8f8175; font-size:11px;')
        box.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_start = QPushButton('开始')
        self.btn_pause = QPushButton('暂停')
        self.btn_resume = QPushButton('继续')
        self.btn_stop = QPushButton('停止')
        for b in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            b.setStyleSheet(_BTN_QSS)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(24)
            row.addWidget(b)
        box.addLayout(row)
        self.btn_start.clicked.connect(controller.start)
        self.btn_pause.clicked.connect(controller.pause)
        self.btn_resume.clicked.connect(controller.resume)
        self.btn_stop.clicked.connect(controller.stop)
        self.btn_time.clicked.connect(lambda: self._set_mode('time', persist=True))
        self.btn_steps.clicked.connect(lambda: self._set_mode('steps', persist=True))
        self.report_combo.currentIndexChanged.connect(lambda _i: self._on_value_changed())
        self._mode = 'time'
        self._set_mode('time', persist=False)
        self._sync_buttons(_EMPTY)

    TIME_PRESETS = (500, 1000, 2000, 5000)
    STEP_PRESETS = (50, 100, 200, 500, 1000)

    def _set_mode(self, mode, persist=True):
        self._mode = 'steps' if mode == 'steps' else 'time'
        presets = self.STEP_PRESETS if self._mode == 'steps' else self.TIME_PRESETS
        self.report_combo.blockSignals(True)
        self.report_combo.clear()
        for v in presets:
            self.report_combo.addItem(('%d 步' % v) if self._mode == 'steps' else ('%d ms' % v), v)
        self.report_combo.setCurrentIndex(presets.index(200 if self._mode == 'steps' else 1000))
        self.report_combo.blockSignals(False)
        self.btn_time.setChecked(self._mode == 'time')
        self.btn_steps.setChecked(self._mode == 'steps')
        if persist:
            self._save_prefs()

    def _on_value_changed(self):
        self._save_prefs()

    def report_policy(self):
        v = self.report_combo.currentData()
        if self._mode == 'steps':
            return {'mode': 'steps', 'steps': max(1, int(v or 200))}
        return {'mode': 'time', 'ms': max(50, int(v or 1000))}

    def _save_prefs(self):
        try:
            import v6_speed as _s
            prefs = _s.load_prefs()
            prefs['report_mode'] = self._mode
            prefs['report_value'] = int(self.report_combo.currentData() or 0)
            prefs['report_prefs_version'] = 1
            _s.save_prefs(prefs)
        except Exception:                                            # noqa: BLE001
            pass

    def load_prefs(self):
        """带版本的幂等加载：缺省 定时间 1000ms；非法值回退默认。"""
        try:
            import v6_speed as _s
            prefs = _s.load_prefs()
            mode = prefs.get('report_mode')
            value = prefs.get('report_value')
            if int(prefs.get('report_prefs_version') or 0) < 1:
                # 首次迁移：沿用旧的后台进度节流参数（0.45s/20 步）→ 规范化为 定时间 500ms
                mode, value = 'time', 500
                prefs['report_mode'], prefs['report_value'] = mode, value
                prefs['report_prefs_version'] = 1
                _s.save_prefs(prefs)
            if mode not in ('time', 'steps'):
                mode, value = 'time', 1000
            allowed = self.STEP_PRESETS if mode == 'steps' else self.TIME_PRESETS
            if value not in allowed:
                value = 200 if mode == 'steps' else 1000
            self._mode = mode
            presets = allowed
            self.report_combo.blockSignals(True)
            self.report_combo.clear()
            for v in presets:
                self.report_combo.addItem(('%d 步' % v) if mode == 'steps' else ('%d ms' % v), v)
            self.report_combo.setCurrentIndex(presets.index(value))
            self.report_combo.blockSignals(False)
            self.btn_time.setChecked(mode == 'time')
            self.btn_steps.setChecked(mode == 'steps')
        except Exception:                                            # noqa: BLE001
            pass

    def _sync_buttons(self, state):
        running = state in ('HANDOFF_PREPARE', 'BG_RUNNING')
        paused = state == 'BG_PAUSED'
        self.btn_start.setEnabled(state in (_EMPTY, 'BG_COMPLETED', 'BG_ERROR'))
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(paused)
        self.btn_stop.setEnabled(running or paused)


class BackgroundController(QObject):
    def __init__(self, win, v5gui=None):
        super().__init__(win)
        self.win = win
        self.v5gui = v5gui
        self.state = _EMPTY
        self.proc = None
        self._q = queue.Queue()
        self._reader = None
        self._session_seq = 0
        self._adopted_revision = -1
        self._paused_snapshot_path = None
        self._staging_dir = os.path.join(V6_DIR, 'game_history', 'background')
        self._last_result = None
        self._rendered_revision = -1
        self._last_render_step = 0
        self._last_render_t = time.perf_counter()
        self.panel = BackgroundPanel(self)
        try:
            self.panel.load_prefs()
        except Exception:                                            # noqa: BLE001
            pass
        self._drain = QTimer(self)
        self._drain.timeout.connect(self._on_drain)
        self._drain.start(120)

    # ------------------------------------------------------------ 状态机
    def _transition(self, new_state):
        if new_state == self.state:
            return True
        if new_state not in _TRANSITIONS.get(self.state, set()):
            self._show('非法状态迁移被拒绝：%s -> %s' % (self.state, new_state))
            return False
        self.state = new_state
        if self.panel is not None:
            self.panel._sync_buttons(new_state)
        return True

    def _show(self, text, kind='info'):
        self.panel.label.setText(text)

    # ------------------------------------------------------------ 模式
    def on_mode_changed(self, mode):
        want_bg = mode == 'background'
        self.panel.setVisible(want_bg)
        cta = getattr(self.win, 'solver_start_btn', None)
        if cta is not None:
            cta.setEnabled(not want_bg)
            cta.setToolTip('“后台求解”运行方式下请使用下方后台按钮'
                           if want_bg else '开始求解')
        if not want_bg and self.state in ('BG_RUNNING', 'BG_PAUSED', 'HANDOFF_PREPARE'):
            self.stop()

    def is_active(self):
        return self.state in ('HANDOFF_PREPARE', 'BG_RUNNING', 'BG_PAUSING', 'BG_PAUSED',
                              'BG_STOPPING')

    # ------------------------------------------------------------ 启动
    def start(self):
        if not self._transition('HANDOFF_PREPARE'):
            return
        if self.win.solver_mode.currentData() != 'auto':
            self._show('后台求解仅支持“自动连走”；请先把求解模式切到自动连走。')
            self._transition('GUI_IDLE')
            return
        if own.owner_status(self._staging_dir)['state'] == 'alive':
            st = own.owner_status(self._staging_dir)
            self._show('已有活动的后台求解（pid=%s，session=%s）持有本局；请先停止。'
                       % ((st.get('record') or {}).get('pid'),
                          (st.get('record') or {}).get('session_id')))
            self._transition('GUI_IDLE')
            return
        # 1) 安全交接：停本机求解 + 等动画结束
        if getattr(self.win, '_solver_running', False):
            self.win._stop_solver('后台接管')
        self._await_idle_and_spawn(deadline=time.time() + 6.0)

    def _await_idle_and_spawn(self, deadline):
        bv = getattr(self.win, 'board_view', None)
        animating = bool(bv.is_animating()) if bv is not None else False
        if animating and time.time() < deadline:
            QTimer.singleShot(80, lambda: self._await_idle_and_spawn(deadline))
            return
        try:
            snap = self._build_snapshot()
        except Exception as exc:                                       # noqa: BLE001
            self._show('交接失败：%s' % exc)
            self._transition('BG_ERROR')
            return
        ok, err = self._spawn_worker(snap)
        if not ok:
            self._show('后台进程启动失败：%s' % err)
            self._transition('BG_ERROR')
            return
        self._transition('BG_RUNNING')
        self._show('后台求解已启动（pid=%s）；进度低频刷新。' % self.proc.pid)

    def _build_snapshot(self):
        model = self.win.model
        game_id = time.strftime('%Y%m%d_%H%M%S_bg')
        board = [row[:] for row in model.grid]
        snap = core.build_snapshot(
            board, int(model.score), int(getattr(model, 'best_score', model.score)),
            core.rng_state_to_json(__import__('random').getstate()), game_id, 0,
            self.win.solver_strategy.currentData(),
            self.win.solver_depth.currentData(),
            self.win.solver_mode.currentData())
        return snap

    def _lock_path(self):
        return os.path.join(self._staging_dir, '.bg.lock')

    def _read_lock_pid(self):
        try:
            return json.load(open(self._lock_path(), encoding='utf-8')).get('pid')
        except Exception:                                             # noqa: BLE001
            return '?'

    def _spawn_worker(self, snap):
        os.makedirs(self._staging_dir, exist_ok=True)
        self._session_seq += 1
        self._game_id = snap['game_id']
        self._snapshot_path = os.path.join(self._staging_dir,
                                           '%s_handoff.json' % snap['game_id'])
        self._checkpoint_path = os.path.join(self._staging_dir,
                                             '%s_checkpoint.json' % snap['game_id'])
        with open(self._snapshot_path, 'w', encoding='utf-8') as f:
            f.write(core.snapshot_to_json(snap))
        return self._launch_worker()

    def _spawn_worker_from(self, snapshot_path):
        """用已存在的快照文件拉起 worker（暂停恢复 / 重连恢复用）。"""
        os.makedirs(self._staging_dir, exist_ok=True)
        self._session_seq += 1
        base = os.path.basename(snapshot_path)
        for suf in ('_resume.json', '_handoff.json', '.json'):
            if base.endswith(suf):
                base = base[:-len(suf)]
                break
        self._game_id = base
        self._snapshot_path = snapshot_path
        self._checkpoint_path = os.path.join(self._staging_dir, '%s_checkpoint.json' % base)
        return self._launch_worker()

    def _limits(self):
        """会话上限与回传策略分离：默认**不设步数上限**（由终局/停止决定），
        仅保留明确的写盘节流；回传间隔来自「结果回传」策略（定时间/定步数）。"""
        return {
            'report_policy': self.panel.report_policy(),
            'max_total_steps': None,        # 不再隐式 200 步终止
            'time_budget_s': None,          # 无隐式 180s 终止（用户可停）
            'progress_interval_s': 0.5,     # 仅用于心跳/检查点刷新提示
            'progress_every_steps': 25,
        }

    def _launch_worker(self):
        # 独占写者：由 **worker 自身**写入 owner.json（含 pid/创建时间）+ 心跳；GUI 只读校验
        env = dict(os.environ, PYTHONNOUSERSITE='1')
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-m', 'headless.worker_main'], cwd=V6_DIR, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1)
        except Exception as exc:                                      # noqa: BLE001
            return False, repr(exc)
        self._start_reader()
        self._send({'cmd': 'start', 'snapshot_path': self._snapshot_path,
                    'limits': self._limits(),
                    'backend': getattr(self.win, '_v6_backend', None),
                    'native_search': bool(getattr(self.win, '_v6_native', False)),
                    'staging': self._checkpoint_path,
                    'ownership': self._staging_dir})
        return True, None

    def _start_reader(self):
        def rd():
            # 必须用 readline()：管道上 `for line in file` 会因预读缓冲而延迟/阻塞
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self._q.put(line)
            self._q.put(None)
        self._reader = threading.Thread(target=rd, daemon=True)
        self._reader.start()

    def _send(self, msg):
        if self.proc is None or self.proc.stdin is None:
            return False
        try:
            self.proc.stdin.write(json.dumps(msg) + '\n')
            self.proc.stdin.flush()
            return True
        except Exception:                                             # noqa: BLE001
            return False

    # ------------------------------------------------------------ 控制
    def _signal(self, cmd):
        """优先走管道；无管道（GUI 重启后重连）则回落到控制文件（worker 低频轮询）。"""
        if self.proc is not None and self._send({'cmd': cmd}):
            return 'pipe'
        own.write_control(self._staging_dir, cmd)
        return 'control-file'

    def pause(self):
        if self._transition('BG_PAUSING'):
            how = self._signal('pause')
            self._show('正在请求暂停（下一步边界生效，通道=%s）…' % how)

    def stop(self):
        if self.state in ('HANDOFF_PREPARE',):
            self._transition('GUI_IDLE')
            return
        if self._transition('BG_STOPPING'):
            how = self._signal('stop')
            self._show('正在停止后台求解（通道=%s）…' % how)

    # ------------------------------------------------------------ 启动期恢复
    def recover_on_start(self):
        """V6 启动时的安全恢复：身份匹配且活动则重连；否则原子释放过期所有权并恢复棋盘。"""
        st = own.owner_status(self._staging_dir)
        state = st.get('state')
        if state == 'absent':
            return {'state': 'absent'}
        rec = st.get('record') or {}
        if state == 'alive':
            self._reconnected = True
            self._game_id = rec.get('session_id')
            self.state = 'BG_RUNNING'
            self.panel._sync_buttons('BG_RUNNING')
            self._show('已重连活动中的后台求解：pid=%s，session=%s，心跳 %ss 前\n'
                       '（GUI 重启后无管道；可“停止”以协作结束）'
                       % (rec.get('pid'), rec.get('session_id'), st.get('heartbeat_age_s')))
            self._watch_timer = QTimer(self)
            self._watch_timer.timeout.connect(self._watch_heartbeat)
            self._watch_timer.start(1200)
            return st
        rel = own.release_stale(self._staging_dir,
                                reason='startup: %s' % st.get('reason'))
        if rel.get('released'):
            ck = own.latest_checkpoint(self._staging_dir)
            msg = self._restore_from_checkpoint(ck)
            self._show('已安全释放过期后台所有权（原因：%s）。%s' % (st.get('reason'), msg))
        else:
            self._show('过期所有权释放被拒绝：%s' % rel.get('reason'))
        return st

    def _restore_from_checkpoint(self, ck):
        if not ck:
            return '未找到可用检查点，棋盘保持当前状态。'
        path, data = ck
        try:
            snap = core.snapshot_from_json(data['snapshot']) if isinstance(
                data.get('snapshot'), str) else core.validate_snapshot(data.get('snapshot'))
            self._adopt(snap)
            return ('已按最新有效检查点恢复棋盘：步 %s，分数 %s，rev %s（%s）'
                    % (data.get('steps'), snap.get('score'), snap.get('revision'),
                       os.path.basename(path)))
        except Exception as exc:                                       # noqa: BLE001
            return '检查点不可用（%s），棋盘保持当前状态。' % exc

    def _watch_heartbeat(self):
        st = own.owner_status(self._staging_dir)
        if st.get('state') == 'alive':
            hb = st.get('heartbeat') or {}
            self._show('后台求解运行中：步 %s，分数 %s，rev %s（心跳 %ss 前）｜pid %s'
                       % (hb.get('step'), hb.get('score'), hb.get('revision'),
                          st.get('heartbeat_age_s'), (st.get('record') or {}).get('pid')))
            return
        # owner 消失（正常停止/崩溃）→ 结束等待并恢复
        try:
            self._watch_timer.stop()
        except Exception:                                              # noqa: BLE001
            pass
        ck = own.latest_checkpoint(self._staging_dir)
        msg = self._restore_from_checkpoint(ck)
        if self.state == 'BG_PAUSING':
            self._paused_snapshot_path = ck[0] if ck else None
            self.state = 'BG_PAUSED'
            self.panel._sync_buttons('BG_PAUSED')
            self._show('已暂停并恢复棋盘。%s' % msg)
        else:
            self._transition('GUI_IDLE')
            self._cleanup_worker()
            self._show('后台求解已结束。%s' % msg)

    # ------------------------------------------------------------ 关闭 / 清理
    def resume(self):
        if not self._paused_snapshot_path or self.state != 'BG_PAUSED':
            self._show('无可恢复的暂停点')
            return
        if self._transition('BG_RUNNING'):
            if self.proc is None or self.proc.poll() is not None:
                # 重连场景：worker 已退出（暂停=步边界停止），用暂停点重新拉起
                ok, err = self._spawn_worker_from(self._paused_snapshot_path)
                if not ok:
                    self._show('恢复失败：%s' % err)
                    self._transition('BG_ERROR')
                    return
            else:
                self._send({'cmd': 'start', 'snapshot_path': self._paused_snapshot_path,
                            'limits': self._limits(),
                            'backend': getattr(self.win, '_v6_backend', None),
                            'staging': self._checkpoint_path,
                            'ownership': self._staging_dir})

    def _render_snapshot(self, msg):
        """周期快照 → 左侧棋盘**无动画**刷新（只读展示，不 apply_move / 不改权威状态）。

        - 合并过期进度：仅当 revision 严格递增才渲染；
        - 绘制全部在 Qt 主线程（本方法由 GUI 线程的 QTimer 排空调用）；
        - 不写历史/不改 model.score，权威提交只在 FINAL 采纳。
        """
        board = msg.get('board')
        if not board:
            return
        rev = int(msg.get('revision', -1))
        if rev <= self._rendered_revision:
            return
        self._rendered_revision = rev
        self._last_render_t = time.perf_counter()
        bv = getattr(self.win, 'board_view', None)
        if bv is not None and hasattr(bv, 'render'):
            bv.render([list(r) for r in board])
        try:
            self.win._render_score(self.win.score_label, '分数', msg.get('score'))
            self.win._render_score(self.win.best_label, '最高分',
                                   msg.get('best_score', msg.get('score')))
        except Exception:                                            # noqa: BLE001
            pass
        self._last_render_step = msg.get('step')

    def shutdown(self, timeout=6.0):
        """关闭窗口/退出：协作停止 + 有界等待 + 保留检查点（不静默强杀）。"""
        if not self.is_active():
            self._cleanup_worker()
            return True
        self._signal('stop')
        t0 = time.time()
        while time.time() - t0 < timeout and self.proc is not None and self.proc.poll() is None:
            time.sleep(0.05)
        ok = self.proc is not None and self.proc.poll() is not None
        if not ok:
            # 无管道（重连）时等待 owner 消失
            while time.time() - t0 < timeout + 3.0:
                if own.owner_status(self._staging_dir)['state'] != 'alive':
                    ok = True
                    break
                time.sleep(0.1)
        if not ok and self.proc is not None:
            self._signal('quit')
            try:
                self.proc.wait(timeout=3)
                ok = True
            except Exception:                                         # noqa: BLE001
                ok = False
        if not ok:
            # 明确失败：保留检查点与所有权，交由下次启动的恢复流程处理
            return False
        self._cleanup_worker()
        return True

    def _cleanup_worker(self):
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()                # 仅作最后手段；正常路径已协作退出
        except Exception:                                             # noqa: BLE001
            pass
        # worker 已退出时，若所有权仍标记为本进程派生的 worker，则由 GUI 兜底释放
        try:
            st = own.owner_status(self._staging_dir)
            if st['state'] in ('stale', 'malformed'):
                own.release_stale(self._staging_dir, reason='gui cleanup after worker exit')
        except Exception:                                             # noqa: BLE001
            pass
        try:
            if os.path.exists(self._lock_path()):
                os.remove(self._lock_path())    # 兼容清理：旧版遗留锁文件
        except OSError:
            pass
        self.proc = None
        self.state = _EMPTY
        if self.panel is not None:
            self.panel._sync_buttons(_EMPTY)

    # ------------------------------------------------------------ 消息
    def _on_drain(self):
        while True:
            try:
                line = self._q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            self._on_msg(msg)

    def _on_msg(self, msg):
        kind = msg.get('type')
        if kind == 'warming':
            self._show('后台求解预热中：首次导入求解栈（numpy/pybind/numba）可能耗时数十秒…')
            return
        if kind == 'warmed':
            self._show('后台求解预热完成（%.0f ms），开始求解…' % (msg.get('warmup_ms') or 0))
            return
        if kind == 'ack':
            return
        if kind == 'exited':
            self._worker_exit_code = msg.get('code')
            st = own.owner_status(self._staging_dir)
            self._show('后台进程已退出：exit=%s；所有权状态=%s'
                       % (msg.get('code'), st.get('state')))
            return
        if kind == 'progress':
            if msg.get('game_id') != getattr(self, '_game_id', None):
                return                                                # 过期消息：丢弃
            rev = int(msg.get('revision', -1))
            if rev < self._adopted_revision:
                return
            self._render_snapshot(msg)                            # 无动画只读刷新左侧棋盘
            age_ms = (time.perf_counter() - self._last_render_t) * 1000.0
            ck = msg.get('last_checkpoint') or {}
            self._show(
                '后台求解 %s｜步 %s（已同步至第 %s 步，%.0f ms 前）｜分数 %s｜最大 %s｜%s 步/秒\n'
                '引擎 %s / %s｜回传=%s｜检查点 步%s rev%s'
                % (msg.get('status'), msg.get('step'), self._last_render_step, age_ms,
                   msg.get('score'), msg.get('max_tile'), msg.get('steps_per_s'),
                   msg.get('backend_used'), msg.get('engine_used'),
                   msg.get('report_reason'), ck.get('steps'), ck.get('revision')))
        elif kind == 'final':
            self._last_result = msg
            self._adopt(msg.get('snapshot'))
            status = msg.get('status')
            if status == 'stopped' and self.state in ('BG_PAUSING', 'BG_STOPPING'):
                if self.state == 'BG_PAUSING':
                    self._paused_snapshot_path = os.path.join(
                        self._staging_dir, '%s_resume.json' % getattr(self, '_game_id', 'bg'))
                    try:
                        with open(self._paused_snapshot_path, 'w', encoding='utf-8') as f:
                            f.write(core.snapshot_to_json(msg['snapshot']))
                    except Exception:                                 # noqa: BLE001
                        self._paused_snapshot_path = None
                    self.state = 'BG_PAUSED'
                    self.panel._sync_buttons('BG_PAUSED')
                    self._show('已暂停（步 %s，分数 %s）｜可点“继续”从精确 RNG 状态恢复'
                               % (msg.get('steps'), msg['snapshot'].get('score')))
                else:
                    self._finish_to_idle('后台求解已停止')
            elif status == 'completed':
                self._transition('BG_COMPLETED')
                self._show('后台求解完成：步 %s，分数 %s' % (msg.get('steps'),
                                                            msg['snapshot'].get('score')))
                self._cleanup_worker()
            elif status == 'game_over':
                self._transition('BG_COMPLETED')
                self._show('后台求解结束：游戏结束（分数 %s）' % msg['snapshot'].get('score'))
                self._cleanup_worker()
            elif status == 'error':
                self._transition('BG_ERROR')
                self._show('后台求解出错：%s' % msg.get('reason'))
                self._cleanup_worker()
        elif kind == 'error':
            self._transition('BG_ERROR')
            self._show('后台进程错误：%s' % msg.get('error'))

    def _finish_to_idle(self, text):
        self._transition('GUI_IDLE')
        self._cleanup_worker()
        self._show(text)

    def _adopt(self, snap):
        """把后台最终/暂停快照采纳为 GUI 权威棋盘（含精确 RNG 状态）。"""
        if not snap:
            return
        try:
            import random
            self.win.model.grid = [row[:] for row in snap['board']]
            self.win.model.score = int(snap['score'])
            if hasattr(self.win.model, 'game_over'):
                self.win.model.game_over = bool(snap.get('game_over'))
            random.setstate(core.rng_state_from_json(snap['rng_state']))
            self.win.refresh()
            self._adopted_revision = int(snap.get('revision', -1))
        except Exception as exc:                                      # noqa: BLE001
            self._show('采纳后台棋盘失败：%s' % exc)
