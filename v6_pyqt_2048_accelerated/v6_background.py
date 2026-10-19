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

# 结果回传周期：**固定内部常量**（单一来源，当前 500ms）。它不是搜索预算、不是步数终止条件，
# 也不是 worker 重启间隔；后台求解在整局内持续，直到终局 / 用户暂停 / 停止 / 显式预算。
REPORT_INTERVAL_MS = 500


_DEFERRED_IO_METHODS = ('_write_history_file', 'save_game_state', 'save_best_score', 'update_index')


class _DeferredModelIO:
    """回放期抑制模型**逐笔**落盘，结束后由调用方**单次**提交。

    仅延后磁盘 I/O；内存语义（grid/score/best_score/history_rows/history_count/undo_stack）
    完全不变，正式存档安全级别不变（仍是一次原子写）。这是“暂停时 GUI 卡死”的根因修复：
    原实现每一步都触发 record_move→全量重写 history.csv 且 save_game_state→json.dumps+fsync，
    536 步即 1072 次 CSV + 1486 次 JSON 同步写，阻塞 Qt 主线程 ~111s。
    """

    def __init__(self, model):
        self.model = model
        self.saved = {}
        self.calls = 0

    def __enter__(self):
        for name in _DEFERRED_IO_METHODS:
            fn = getattr(self.model, name, None)
            if fn is None:
                continue
            self.saved[name] = fn
            setattr(self.model, name, self._noop)
        return self

    def _noop(self, *_a, **_k):
        self.calls += 1
        return None

    def __exit__(self, *_exc):
        for name, fn in self.saved.items():
            try:
                setattr(self.model, name, fn)
            except Exception:                                        # noqa: BLE001
                pass
        return False


def persist_official(model):
    """校验通过后，**单次**提交正式历史 / 存档 / 最高分 / 索引（原子写）。"""
    wrote = 0
    for name in _DEFERRED_IO_METHODS:
        fn = getattr(model, name, None)
        if callable(fn):
            try:
                fn()
                wrote += 1
            except Exception:                                        # noqa: BLE001
                pass
    return wrote


def replay_commit(model, directions, start_rng_state_json=None, cursor=0, base_grid=None,
                  defer_persistence=True, stats=None):
    """把 worker 的有效方向序列按**正常对局语义**回放到官方模型（Qt-free，可直接单测）。

    等价性依据：`tests/test_v6_headless.ModelEquivalenceTest` 已证明 `core.apply_move`
    与官方模型 `apply_move` 在相同起点 RNG 下逐位一致（棋盘 / 分数 / 生成方块 / RNG 消费）。
    因此逐步回放可产出与正常对局完全相同的官方逐笔历史（history.csv）、撤销/重做栈、
    game_state.json（原子写 + .bak 备份）与 index / best_score 持久化 —— 权威写入者
    始终是官方模型（单一写者）。

    ``defer_persistence=True``（默认）时，回放期间**不落盘**，仅内存构建历史/撤销；
    调用方需在校验通过后调用 :func:`persist_official` 做**单次**提交。

    :param start_rng_state_json: 首次回放用的**交接基准** RNG（None 表示 RNG 已就位）。
    :param cursor: 已回放过的方向数（仅回放增量，避免重复提交）。
    :param base_grid: 会话基准棋盘；若模型已偏离则拒绝回放（防并发写者）。
    :param stats: 可选 dict，写入 ``moves`` / ``suppressed_io_calls`` 便于观测。
    :returns: 新的 cursor
    """
    import random as _random
    if base_grid is not None and [row[:] for row in model.grid] != [list(r) for r in base_grid]:
        raise RuntimeError('模型棋盘在后台运行期间被改动，拒绝回放（保持单一写入者）')
    if start_rng_state_json is not None:
        _random.setstate(core.rng_state_from_json(start_rng_state_json))
    delta = list(directions)[cursor:]
    if stats is not None:
        stats['moves'] = len(delta)
    if defer_persistence:
        with _DeferredModelIO(model) as io:
            for d in delta:
                model.apply_move(d)
        if stats is not None:
            stats['suppressed_io_calls'] = io.calls
    else:
        for d in delta:
            model.apply_move(d)
    return len(directions)


class BackgroundPanel(QWidget):
    """后台生命周期按钮已并入统一「AI 运行控制」模块（见 v6_speed）。

    这里仅保留控制器需要的轻量占位与状态同步入口：``_sync_buttons`` 把状态变化
    转发给窗口的统一控制模块，避免出现第二套按钮（原 4 按钮已移除）。
    """

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.hide()

    def report_policy(self):
        """固定内部周期结果回传（单一来源；不向用户暴露任何间隔选择）。"""
        return {'mode': 'time', 'ms': REPORT_INTERVAL_MS}

    def _sync_buttons(self, state):
        win = getattr(self.controller, 'win', None)
        fn = getattr(win, '_v6_sync_run_controls', None)
        if callable(fn):
            try:
                fn()
            except Exception:                                    # noqa: BLE001
                pass


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
        self._game_id = None
        self._snapshot_path = None
        self._checkpoint_path = None
        self._adopted_revision = -1
        self._paused_snapshot_path = None
        self._staging_dir = os.path.join(V6_DIR, 'game_history', 'background')
        self._last_result = None
        self._last_progress = None
        self._stderr_file = None
        self._rendered_revision = -1
        # 正式历史回放（Headless ↔ 官方存档等价）：交接基准 RNG + 会话方向游标/基准棋盘
        self._handoff_rng_json = None
        self._fresh_handoff = False
        self._session_cursor = 0
        self._session_base_grid = None
        # P1 单调时钟分段埋点（GUI 侧）+ 终态保护
        self._perf = {}
        self._final_seen = False
        self._last_render_step = 0
        self._last_render_t = time.perf_counter()
        self.panel = BackgroundPanel(self)
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
        # 统一可见控制区的唯一状态源：任何后台状态迁移都同步一次
        try:
            fn = getattr(self.win, '_v6_sync_run_controls', None)
            if callable(fn):
                fn()
        except Exception:                                            # noqa: BLE001
            pass
        return True

    def _show(self, text, kind='info'):
        """把后台状态写入**既有求解状态区**（不再新增独立状态栏/黑条）。"""
        lbl = getattr(self.win, 'solver_status', None)
        if lbl is not None:
            try:
                lbl.setText(text)
                return
            except Exception:                                        # noqa: BLE001
                pass

    def _mark(self, name, **extra):
        """单调时钟（perf_counter）分段埋点；供 P1 取证与收口报告使用。"""
        try:
            self._perf.setdefault(name, []).append(dict(t=time.perf_counter(), **extra))
        except Exception:                                            # noqa: BLE001
            pass

    def pause_perf(self):
        """返回 GUI 侧分段埋点字典（只读用途）。"""
        return self._perf

    # ------------------------------------------------------------ 模式
    def on_mode_changed(self, mode):
        want_bg = mode == 'background'
        # 注意：BackgroundPanel 已无可见控件且不再插入布局；**禁止** setVisible(True)，
        # 否则它会成为独立顶层窗口（第二个空白 Qt 窗口）。
        try:
            self.panel.setVisible(False)
        except Exception:                                            # noqa: BLE001
            pass
        # 后台模式隐藏“求解忙态进度条”（回传间隔无百分比含义，避免无意义进度条）
        prog = getattr(self.win, 'solver_progress', None)
        if prog is not None:
            try:
                prog.setVisible(not want_bg)
            except Exception:                                        # noqa: BLE001
                pass
        cta = getattr(self.win, 'solver_start_btn', None)
        if cta is not None:
            cta.setEnabled(not want_bg)
            cta.setToolTip('“后台求解”运行方式下请使用下方后台按钮'
                           if want_bg else '开始求解')
        # 仅在没有活动会话时允许“切走=停止”；活动期间的选项卡切换必须是非破坏性的；
        # 跨模式交接（_v6_handoff）期间一律由交接流程独占控制，绝不被模式切换顺带停止。
        if (getattr(self.win, '_v6_handoff', None) is None
                and not want_bg and self.state in ('BG_RUNNING', 'BG_PAUSED', 'HANDOFF_PREPARE')
                and getattr(self.win, '_v6_active_mode', None) is None):
            self.stop()

    def is_active(self):
        return self.state in ('HANDOFF_PREPARE', 'BG_RUNNING', 'BG_PAUSING', 'BG_PAUSED',
                              'BG_STOPPING')

    # ------------------------------------------------------------ 启动
    def start(self, snapshot=None, handoff_meta=None):
        """启动后台求解。

        :param snapshot: 非空表示**跨模式交接**（调用方已把原会话停在安全边界）。
        此时**不得**先停掉原会话：新 Worker 只有在成功接管所有权后才由调用方收尾，
        否则交接失败会丢失原暂停会话。
        :param handoff_meta: 交接元数据（原/新模式、正式游戏 id、会话性别名等），
        会写入快照与 staging 交接记录，便于审计“前后会话”关系。
        :returns: bool（是否已受理；最终成败由 ``_confirm_running/_fail_start`` 异步收敛）
        """
        if not self._transition('HANDOFF_PREPARE'):
            return False
        if self.win.solver_mode.currentData() != 'auto':
            self._show('后台求解仅支持“自动连走”；请先把求解模式切到自动连走。')
            self._transition('GUI_IDLE')
            return False
        if own.owner_status(self._staging_dir)['state'] == 'alive':
            st = own.owner_status(self._staging_dir)
            self._show('已有活动的后台求解（pid=%s，session=%s）持有本局；请先停止。'
                       % ((st.get('record') or {}).get('pid'),
                          (st.get('record') or {}).get('session_id')))
            self._transition('GUI_IDLE')
            return False
        meta = dict(handoff_meta or {})
        if snapshot is not None:
            ok, err = self._spawn_worker(snapshot)
            if not ok:
                self._fail_start('后台进程启动失败：%s' % err, meta)
                return False
            self._await_ownership(time.monotonic() + 8.0, meta)
            return True
        # 1) 安全交接：停本机求解 + 等动画结束
        if getattr(self.win, '_solver_running', False):
            self.win._stop_solver('后台接管')
        self._await_idle_and_spawn(deadline=time.time() + 6.0, meta=meta)
        return True

    def _await_idle_and_spawn(self, deadline, meta=None):
        bv = getattr(self.win, 'board_view', None)
        animating = bool(bv.is_animating()) if bv is not None else False
        if animating and time.time() < deadline:
            QTimer.singleShot(80, lambda: self._await_idle_and_spawn(deadline, meta))
            return
        try:
            snap = self._build_snapshot(handoff_meta=meta)
        except Exception as exc:                                       # noqa: BLE001
            self._fail_start('交接快照失败：%s' % exc, meta)
            return
        ok, err = self._spawn_worker(snap)
        if not ok:
            self._fail_start('后台进程启动失败：%s' % err, meta)
            return
        # 关键：不立即宣告运行中；必须先确认 Worker 已登记所有权（单一写者）
        self._await_ownership(time.monotonic() + 8.0, meta)

    def _await_ownership(self, deadline, meta=None):
        """确认新 Worker 真正接管游戏所有权（owner.json + pid 匹配）后才进入 BG_RUNNING。"""
        proc = self.proc
        if proc is None:
            self._fail_start('后台进程未创建', meta)
            return
        st = own.owner_status(self._staging_dir)
        rec = st.get('record') or {}
        if st.get('state') == 'alive' and int(rec.get('pid', -1)) == int(proc.pid):
            self._confirm_running(meta)
            return
        code = proc.poll()
        if code is not None:
            self._fail_start('后台进程在接管所有权前退出（exit=%s）' % code, meta)
            return
        if time.monotonic() >= deadline:
            self._fail_start('等待后台 Worker 接管所有权超时（owner=%s）' % st.get('state'), meta)
            return
        QTimer.singleShot(50, lambda: self._await_ownership(deadline, meta))

    def _confirm_running(self, meta=None):
        if not self._transition('BG_RUNNING'):
            return
        self.win._v6_active_mode = 'background'
        self._write_handoff_record(meta)
        # 先让窗口完成本轮交接收尾（应用新模式效果），再写最终状态文案
        fn = getattr(self.win, '_v6_on_bg_started', None)
        if callable(fn):
            try:
                fn(dict(meta or {}))
            except Exception:                                        # noqa: BLE001
                pass
        self._show('后台求解已接管本局（pid=%s，session=%s）；进度固定 %dms 低频回传。'
                   % (self.proc.pid if self.proc is not None else '?', self._game_id,
                      REPORT_INTERVAL_MS))

    def _fail_start(self, reason, meta=None):
        """启动/交接失败：清理半启动 Worker，明确回报，绝不静默进入错误模式。"""
        self._mark('BG_START_FAILED', reason=str(reason))
        self._show('后台求解启动失败：%s' % reason)
        self._transition('BG_ERROR')
        self._cleanup_worker()
        fn = getattr(self.win, '_v6_on_bg_start_failed', None)
        if callable(fn):
            try:
                fn(str(reason), dict(meta or {}))
            except Exception:                                        # noqa: BLE001
                pass

    def _write_handoff_record(self, meta):
        """写一次交接记录（from/to、正式 game_id、新 session_id），建立前后会话关系。"""
        if not meta:
            return
        rec = dict(meta)
        rec.update({'session_id': self._game_id,
                    'at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'pid': self.proc.pid if self.proc is not None else None})
        try:
            os.makedirs(self._staging_dir, exist_ok=True)
            _store.atomic_write_json(
                os.path.join(self._staging_dir, 'handoff_%s.json' % (self._game_id or 'bg')),
                rec)
        except Exception:                                            # noqa: BLE001
            pass

    def drain_for_handoff(self, on_done, deadline_s=8.0):
        """后台 → 本机交接：请求 Worker 退出，确认其释放所有权后再回调。

        暂停态下 Worker 常驻等待 ``start``；这里发 ``quit`` 让它协作退出。
        只有在“进程已退出 + owner 非 alive”后才 ``on_done(True, ...)``，
        保证本机求解器启动时不会有第二个写者。
        """
        t0 = time.monotonic()
        if self.state not in ('HANDOFF_PREPARE', 'BG_RUNNING', 'BG_PAUSING', 'BG_PAUSED',
                              'BG_STOPPING'):
            self._cleanup_worker()
            on_done(True, 'already_idle')
            return
        if self.proc is not None and self.proc.poll() is None:
            self._signal('quit')
        else:
            own.write_control(self._staging_dir, 'quit')

        def poll():
            proc_done = self.proc is None or self.proc.poll() is not None
            st = own.owner_status(self._staging_dir).get('state')
            if proc_done and st != 'alive':
                self._cleanup_worker()
                on_done(True, 'released')
                return
            if time.monotonic() - t0 >= deadline_s:
                on_done(False, '等待后台 Worker 释放所有权超时（owner=%s，proc_done=%s）'
                        % (st, proc_done))
                return
            QTimer.singleShot(60, poll)

        QTimer.singleShot(0, poll)

    def _build_snapshot(self, handoff_meta=None):
        model = self.win.model
        # 会话 id 必须唯一：跨模式连续交接可能在同一秒内发生两次
        game_id = '%s_%03d_bg' % (time.strftime('%Y%m%d_%H%M%S'),
                                  int(time.time() * 1000) % 1000)
        board = [row[:] for row in model.grid]
        snap = core.build_snapshot(
            board, int(model.score), int(getattr(model, 'best_score', model.score)),
            core.rng_state_to_json(__import__('random').getstate()), game_id, 0,
            self.win.solver_strategy.currentData(),
            self.win.solver_depth.currentData(),
            self.win.solver_mode.currentData())
        if handoff_meta:
            # 快照内显式记录交接来源（可审计的前后会话关系；不参与规则计算）
            snap['handoff'] = dict(handoff_meta)
        # 交接基准：正式历史回放必须从此处的棋盘 + 全局 RNG 逐步重放（等价于正常对局）。
        self._handoff_rng_json = snap['rng_state']
        self._fresh_handoff = True
        return snap

    def _lock_path(self):
        return os.path.join(self._staging_dir, '.bg.lock')

    def _read_lock_pid(self):
        try:
            return json.load(open(self._lock_path(), encoding='utf-8')).get('pid')
        except Exception:                                             # noqa: BLE001
            return '?'

    def _reset_session_tracking(self):
        """新会话开始：重置**跨会话**的展示/采纳 revision 跟踪与终态标记。

        修复：此前未重置，导致“第二次开始后台求解”时新会话 revision 从 0 起，
        却被上一会话的高位 `_rendered_revision/_adopted_revision` 当作过期帧全部丢弃，
        表现为“开始后长时间前盘无数据，随后突然闪过几帧”。
        """
        self._rendered_revision = -1
        self._adopted_revision = -1
        self._last_render_step = 0
        self._last_render_t = time.perf_counter()
        self._final_seen = False
        self._last_progress = None

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
        self._session_cursor = 0
        self._session_base_grid = [row[:] for row in self.win.model.grid]
        self._reset_session_tracking()
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
        self._session_cursor = 0
        self._session_base_grid = [row[:] for row in self.win.model.grid]
        self._reset_session_tracking()
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

    def _close_stderr(self):
        f = getattr(self, '_stderr_file', None)
        self._stderr_file = None
        if f is not None and f not in (subprocess.DEVNULL, None):
            try:
                f.close()
            except Exception:                                        # noqa: BLE001
                pass

    def _launch_worker(self):
        # 独占写者：由 **worker 自身**写入 owner.json（含 pid/创建时间）+ 心跳；GUI 只读校验。
        # Windows 关键：必须 CREATE_NO_WINDOW。否则从**无控制台**的 GUI 进程启动 python.exe
        # 会新建一个可见的空白控制台窗口（即“多余的 python 窗口”根因）。
        env = dict(os.environ, PYTHONNOUSERSITE='1')
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = si
        # 有界诊断日志：每次启动截断 worker stderr（不丢诊断，不弹窗）
        stderr = subprocess.DEVNULL
        try:
            os.makedirs(self._staging_dir, exist_ok=True)
            self._close_stderr()
            self._stderr_file = open(os.path.join(self._staging_dir, 'worker_stderr.log'),
                                     'w', encoding='utf-8', errors='replace')
            stderr = self._stderr_file
        except OSError:
            self._stderr_file = None
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-m', 'headless.worker_main'], cwd=V6_DIR, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                text=True, bufsize=1, **kwargs)
        except Exception as exc:                                      # noqa: BLE001
            self._close_stderr()
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
            self._mark('PAUSE_REQUESTED', channel=how, steps=self._last_render_step)
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
            # 启动期重连：活动执行模式以 Worker 为准（选项卡同步为后台）
            self.win._v6_active_mode = 'background'
            self.win._v6_speed = 'background'
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

    def _handoff_rng_for(self, game_id):
        """从暂存目录的交接快照读取基准 RNG（崩溃恢复回放用，找不到返回 None）。"""
        try:
            names = ['%s_handoff.json' % game_id] if game_id else []
            names += [fn for fn in os.listdir(self._staging_dir)
                      if fn.endswith('_handoff.json') and (not game_id or fn.startswith(game_id))]
            for fn in names:
                c = os.path.join(self._staging_dir, fn)
                if os.path.exists(c):
                    with open(c, 'r', encoding='utf-8') as f:
                        return json.load(f).get('rng_state')
        except Exception:                                              # noqa: BLE001
            return None
        return None

    def _restore_from_checkpoint(self, ck):
        if not ck:
            return '未找到可用检查点，棋盘保持当前状态。'
        path, data = ck
        try:
            snap = core.snapshot_from_json(data['snapshot']) if isinstance(
                data.get('snapshot'), str) else core.validate_snapshot(data.get('snapshot'))
            directions = data.get('directions')
            base_rng = self._handoff_rng_for(data.get('game_id')) if directions else None
            if directions and base_rng:
                # 崩溃恢复：从交接基准 RNG + 模型当前（=最后官方存档）状态逐步回放，
                # 生成与正常对局一致的官方历史/撤销栈，而非仅覆盖棋盘。
                self._handoff_rng_json = base_rng
                self._fresh_handoff = True
                self._session_cursor = 0
                self._session_base_grid = [row[:] for row in self.win.model.grid]
                self._adopt(snap, directions)
                return ('已按最新有效检查点**回放**恢复官方存档：步 %s，分数 %s，rev %s（%s）'
                        % (data.get('steps'), snap.get('score'), snap.get('revision'),
                           os.path.basename(path)))
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
        if not os.path.exists(self._paused_snapshot_path):
            self._show('暂停点文件缺失，无法继续')
            return
        if not self._transition('BG_RUNNING'):
            return
        self.win._v6_active_mode = 'background'
        # 继续**同一局**：revision 继续单调（不清零），新回传段从暂停点接管。
        # 关键修复：暂停时已置 `_final_seen=True`；若不清除，恢复后的所有 progress 都会被
        # 当作“终态后迟到帧”丢弃，表现为“继续后不再回传”。同时重置方向游标/交接基准，
        # 供恢复段 FINAL 的正式历史回放（只回放新段，不重复历史）。
        self._final_seen = False
        self._session_cursor = 0
        self._session_base_grid = [row[:] for row in self.win.model.grid]
        self._fresh_handoff = False
        self._mark('RESUME_REQUESTED', steps=self._last_render_step,
                   revision=self._rendered_revision)
        if self.proc is None or self.proc.poll() is not None:
            # 重连场景：worker 已退出（暂停=步边界停止），用暂停点重新拉起
            ok, err = self._spawn_worker_from(self._paused_snapshot_path)
            if not ok:
                self._show('恢复失败：%s' % err)
                self._transition('BG_ERROR')
                return
        else:
            sent = self._send({'cmd': 'start', 'snapshot_path': self._paused_snapshot_path,
                               'limits': self._limits(),
                               'backend': getattr(self.win, '_v6_backend', None),
                               'native_search': bool(getattr(self.win, '_v6_native', False)),
                               'staging': self._checkpoint_path,
                               'ownership': self._staging_dir})
            if not sent:
                self._show('恢复失败：Worker 管道不可用')
                self._transition('BG_ERROR')
                return
        self.panel._sync_buttons(self.state)

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
            # 最高分只来自权威持久化存储（model.best_score）：
            # 绝不能用 Worker 快照里的 best_score/score 覆盖，否则会把“当前分数”
            # 显示成“历史最高分”（P0 已复现：快照 best==score==5004）。
            self.win._render_score(self.win.best_label, '最高分',
                                   int(getattr(self.win.model, 'best_score', 0)))
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
        try:
            self._mark('OWNER_RELEASED',
                       state=own.owner_status(self._staging_dir).get('state'))
        except Exception:                                            # noqa: BLE001
            pass
        self.proc = None
        self._close_stderr()
        self.state = _EMPTY
        if self.panel is not None:
            self.panel._sync_buttons(_EMPTY)

    # ------------------------------------------------------------ 消息
    def _on_drain(self):
        """排空消息队列：控制/终态按序处理，**progress 仅保留 revision 最新的一帧**。

        这样每次排空只刷新一次左侧棋盘，避免“一次涌入多帧时连续闪过好几批步长切片”。
        """
        latest = None
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
            if msg.get('type') == 'progress':
                rev = int(msg.get('revision', -1))
                if latest is None or rev > int(latest.get('revision', -1)):
                    latest = msg
                continue
            self._on_msg(msg)          # final / exited / error / warmed 等按序处理
        if latest is not None:
            self._on_msg(latest)       # 每批只渲染最新已提交帧

    def _on_msg(self, msg):
        kind = msg.get('type')
        if kind == 'warming':
            self._show('后台求解预热中：首次导入求解栈（numpy/pybind/numba）可能耗时数十秒…')
            return
        if kind == 'warmed':
            self._show('后台求解预热完成（%.0f ms），开始求解…' % (msg.get('warmup_ms') or 0))
            return
        if kind == 'ack':
            self._mark('WORKER_ACK', cmd=msg.get('cmd'), seq=msg.get('seq'))
            return
        if kind == 'exited':
            self._worker_exit_code = msg.get('code')
            self._mark('WORKER_EXITED', code=msg.get('code'))
            st = own.owner_status(self._staging_dir)
            if self.state in ('BG_RUNNING', 'BG_ERROR'):
                self._show('后台进程已退出：exit=%s；所有权状态=%s'
                           % (msg.get('code'), st.get('state')))
            else:
                # 正常收尾后不要再覆盖已结算的结果状态；把退出信息写入日志即可
                try:
                    fn = getattr(self.win, '_log_step', None)
                    if callable(fn):
                        fn('[后台] worker 已退出 exit=%s，所有权=%s'
                           % (msg.get('code'), st.get('state')))
                except Exception:                                    # noqa: BLE001
                    pass
            # 暂停/停止期 worker 协作退出：收敛状态机（不能停在 BG_STOPPING/BG_PAUSED）
            if self.state in ('BG_PAUSED', 'BG_PAUSING', 'BG_STOPPING'):
                self._finish_to_idle('后台求解已结束（worker 已退出 exit=%s）' % msg.get('code'))
            elif self.state == 'BG_RUNNING':
                self._transition('BG_ERROR')
                self._cleanup_worker()
                self._show('后台进程意外退出：exit=%s' % msg.get('code'))
            return
        if kind == 'progress':
            if self._final_seen:
                return                                                # 终态后忽略迟到进度
            if self.state in ('BG_PAUSING', 'BG_STOPPING'):
                return                                                # 已请求暂停/停止：等 FINAL 强制同步
            if msg.get('game_id') != getattr(self, '_game_id', None):
                return                                                # 过期消息：丢弃
            rev = int(msg.get('revision', -1))
            if rev < self._adopted_revision:
                return
            self._render_snapshot(msg)                            # 无动画只读刷新左侧棋盘
            self._last_progress = {
                'revision': int(msg.get('revision', -1)),
                'steps': msg.get('total_committed_moves') or msg.get('step'),
                'score': msg.get('score'), 'max_tile': msg.get('max_tile'),
                'steps_per_s': msg.get('steps_per_s'),
                'backend_used': msg.get('backend_used'),
                'engine_used': msg.get('engine_used'),
                'elapsed_s': round((msg.get('wall_ms') or 0) / 1000.0, 2),
                'render_age_ms': round((time.perf_counter() - self._last_render_t) * 1000.0, 1)}
            # 同一状态源：顶部摘要 + 下方 solver_status/metrics/log 一次更新
            fn = getattr(self.win, '_v6_apply_bg_progress', None)
            if callable(fn):
                try:
                    fn(self._last_progress)
                except Exception:                                    # noqa: BLE001
                    pass
            else:                                                    # 兜底（无统一方法时）
                self.panel._sync_buttons(self.state)
                ck = msg.get('last_checkpoint') or {}
                self._show(
                    '后台求解 %s｜步 %s｜分数 %s｜最大 %s｜%s 步/秒\n引擎 %s / %s｜回传=%s｜检查点 步%s rev%s'
                    % (msg.get('status'), msg.get('step'), msg.get('score'),
                       msg.get('max_tile'), msg.get('steps_per_s'), msg.get('backend_used'),
                       msg.get('engine_used'), msg.get('report_reason'),
                       ck.get('steps'), ck.get('revision')))
        elif kind == 'final':
            # 已被收尾/交接放弃的会话：迟到终态一律丢弃（不得二次采纳官方棋盘/历史）
            if self._final_seen and self.state in ('GUI_IDLE', 'BG_COMPLETED', 'BG_ERROR'):
                try:
                    fn = getattr(self.win, '_log_step', None)
                    if callable(fn):
                        fn('[后台] 已丢弃已收尾会话的迟到终态（state=%s）' % self.state)
                except Exception:                                    # noqa: BLE001
                    pass
                return
            # 跨模式交接后旧 Worker 的迟到终态一律丢弃（不得二次采纳官方棋盘/历史）
            gid = (msg.get('snapshot') or {}).get('game_id')
            if gid and self._game_id and gid != self._game_id:
                try:
                    fn = getattr(self.win, '_log_step', None)
                    if callable(fn):
                        fn('[后台] 已丢弃旧会话迟到终态（session=%s ≠ %s）'
                           % (gid, self._game_id))
                except Exception:                                    # noqa: BLE001
                    pass
                return
            self._final_seen = True
            self._last_result = msg
            self._mark('GUI_FINAL_RECEIVED', status=msg.get('status'),
                       steps=msg.get('total_committed_moves'),
                       directions=len(msg.get('directions') or []))
            self._adopt(msg.get('snapshot'), msg.get('directions'))
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
            fn = getattr(self.win, '_v6_apply_bg_final', None)
            if callable(fn):
                try:
                    fn(msg)
                except Exception:                                    # noqa: BLE001
                    pass
        elif kind == 'error':
            self._transition('BG_ERROR')
            self._show('后台进程错误：%s' % msg.get('error'))

    def _finish_to_idle(self, text):
        self._transition('GUI_IDLE')
        self.win._v6_active_mode = None
        self._cleanup_worker()
        self._show(text)

    def _replay_commit(self, directions):
        """把 worker 方向序列回放到官方模型（**仅内存**构建历史/撤销，不逐笔落盘）。"""
        start_rng = self._handoff_rng_json if self._fresh_handoff else None
        stats = {}
        self._mark('REPLAY_START', directions=len(directions))
        t0 = time.perf_counter()
        self._session_cursor = replay_commit(
            self.win.model, directions, start_rng_state_json=start_rng,
            cursor=self._session_cursor, base_grid=self._session_base_grid, stats=stats)
        self._mark('REPLAY_END', ms=round((time.perf_counter() - t0) * 1000.0, 1),
                   moves=stats.get('moves'), suppressed_io=stats.get('suppressed_io_calls'))
        self._fresh_handoff = False

    def _adopt(self, snap, directions=None):
        """把后台最终/暂停快照采纳为 GUI 权威状态。

        优先走**正式历史回放**（生成官方逐笔历史 / 撤销栈 / 持久化，与正常对局等价）；
        回放不可用或校验不一致时，退回只读网格采纳并显式告警（后台保持 EXPERIMENTAL）。
        """
        if not snap:
            return
        if directions:
            try:
                self._replay_commit(directions)
                model = self.win.model
                if ([row[:] for row in model.grid] == [list(r) for r in snap['board']]
                        and int(model.score) == int(snap['score'])):
                    # RNG 已随回放推进到与 worker 一致；无需再 setstate。
                    if hasattr(model, 'game_over'):
                        model.game_over = bool(snap.get('game_over'))
                    t_s = time.perf_counter()
                    persist_official(model)      # 单次原子提交（历史/存档/最高分/索引）
                    self._mark('SAVE_COMMIT',
                               ms=round((time.perf_counter() - t_s) * 1000.0, 1),
                               history_rows=len(getattr(model, 'history_rows', [])),
                               undo_depth=len(getattr(model, 'undo_stack', [])))
                    self.win.refresh()           # 单次棋盘刷新（GUI 主线程短时状态采纳）
                    self._adopted_revision = int(snap.get('revision', -1))
                    return
                self._show('警告：正式历史回放结果与后台快照不一致，已退回只读采纳'
                           '（后台仍为实验性，勿用于正式存档）。')
            except Exception as exc:                                  # noqa: BLE001
                self._show('警告：正式历史回放失败（%s），已退回只读采纳（后台仍为实验性）。'
                           % exc)
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
