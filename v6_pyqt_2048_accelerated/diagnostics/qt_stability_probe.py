#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 单程序稳定性探针：在**真实 V6 正式 GUI** 内自动连走，采集 QThread / SolverWorker /
定时器 / 异步取消 / 动画完成信号 / Qt 对象生命周期 的时间线证据，用于复现并诊断
Qt5Core.dll 0xC0000409（qFatal/abort）类间歇崩溃。

用法：
    python qt_stability_probe.py --seconds 60 --strategy expectimax --preset-index 1
                               [--step-delay-ms 0] [--steps 400] [--tag demo]

要点：
- **只读复用** V6 GUI；不改动 V6/V5 源码（探针以 monkeypatch 方式包裹实例方法）。
- 通过 `2048_HISTORY_DIR` 重定向到探针独立目录，不触碰真实存档。
- 安装 faulthandler 与自定义 sys.excepthook（记录栈，且避免 PyQt5 槽异常直接 abort）。
- 结束时正常 close()；崩溃时由 faulthandler/excepthook/Windows 事件日志取证。
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
import time
import traceback

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (V6_DIR, REPO_ROOT, os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WRAPPED = ('_request_decision', '_on_solver_result', '_on_solver_failed', '_record_step',
           '_on_animation_finished', '_ai_apply', '_ensure_worker', '_shutdown_worker',
           '_retire_thread', '_collect_retired', '_finish_solver', '_stop_solver', 'on_move')


def install_hooks(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    fh = open(os.path.join(out_dir, 'faulthandler.log'), 'a', encoding='utf-8')
    faulthandler.enable(file=fh)

    def hook(etype, value, tb):
        text = ''.join(traceback.format_exception(etype, value, tb))
        with open(os.path.join(out_dir, 'excepthook.log'), 'a', encoding='utf-8') as f:
            f.write(text + '\n')
        sys.stderr.write(text)
        sys.stderr.flush()
    sys.excepthook = hook


class Probe:
    def __init__(self, window, out_dir):
        self.w = window
        self.t0 = time.perf_counter()
        self.steps = 0
        self.last_progress = time.perf_counter()
        self.stalls = 0
        self.path = os.path.join(out_dir, 'timeline.jsonl')

    def log(self, kind, **fields):
        rec = {'t_s': round(time.perf_counter() - self.t0, 4), 'kind': kind}
        rec.update(fields)
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def snap(self):
        w = self.w
        d = {}
        try:
            th = getattr(w, '_solver_thread', None)
            d['thread_running'] = bool(th.isRunning()) if th is not None else None
            d['worker'] = 'set' if getattr(w, '_solver_worker', None) is not None else None
            d['retired'] = len(getattr(w, '_retired_threads', []) or [])
            d['in_flight'] = bool(getattr(w, '_solve_in_flight', False))
            d['solver_running'] = bool(getattr(w, '_solver_running', False))
            d['job_id'] = getattr(w, '_job_id', None)
            c = getattr(w, '_solver_cancel', None)
            d['cancel_set'] = bool(c.is_set()) if c is not None else None
            bv = getattr(w, 'board_view', None)
            d['animating'] = bool(bv.is_animating()) if bv is not None else None
            d['steps'] = self.steps
        except Exception as exc:                                # noqa: BLE001
            d['snap_err'] = repr(exc)
        return d

    def attach(self):
        for name in WRAPPED:
            self._wrap(name)
        self.log('probe_attached', pid=os.getpid())

    def _wrap(self, name):
        w = self.w
        orig = getattr(w, name, None)
        if orig is None:
            return

        def wrapped(*a, **k):
            self.log('enter:' + name, **self.snap())
            try:
                r = orig(*a, **k)
            except Exception as exc:                            # noqa: BLE001
                self.log('raise:' + name, error=repr(exc), where=traceback.format_exc()[-400:])
                raise
            self.log('exit:' + name, **self.snap())
            return r
        setattr(w, name, wrapped)

    def note_step(self):
        self.steps += 1
        self.last_progress = time.perf_counter()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=60.0)
    ap.add_argument('--steps', type=int, default=100000)
    ap.add_argument('--strategy', default='expectimax')
    ap.add_argument('--strategy-index', type=int, default=None)
    ap.add_argument('--preset-index', type=int, default=1)
    ap.add_argument('--step-delay-ms', type=int, default=None)
    ap.add_argument('--speed-tier', default=None, choices=['standard', 'fast', 'extreme'])
    ap.add_argument('--out', default=None)
    ap.add_argument('--tag', default='probe')
    args = ap.parse_args(argv)

    stamp = time.strftime('%Y%m%d_%H%M%S')
    out_dir = args.out or os.path.join(V6_DIR, 'diagnostics', 'runs', '%s_%s' % (stamp, args.tag))
    os.makedirs(out_dir, exist_ok=True)
    install_hooks(out_dir)
    os.environ['2048_HISTORY_DIR'] = os.path.join(out_dir, 'history_root')

    if args.speed_tier:
        import v6_speed as _speed
        prefs = _speed.load_prefs()
        prefs['speed_tier'] = args.speed_tier
        _speed.save_prefs(prefs)

    import v6_pyqt_2048_accelerated as _v6
    import v5_pyqt_2048_solver as _v5gui
    # 会话/导出也重定向到探针目录，避免写入 V6 生产 solver_results
    _v6.V6_RESULT_DIR = os.path.join(out_dir, 'solver_results')
    _v6.V6_EXPORT_DIR = os.path.join(_v6.V6_RESULT_DIR, 'exports')
    _v6.V6_SESSIONS_FILE = os.path.join(_v6.V6_RESULT_DIR, 'sessions.json')
    if args.step_delay_ms is not None:
        _v5gui.STEP_DELAY_MS = int(args.step_delay_ms)

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    win = _v6.V6MainWindow()
    win.show()
    probe = Probe(win, out_dir)
    probe.attach()
    probe.log('window_shown', size=[win.width(), win.height()],
              step_delay_ms=_v5gui.STEP_DELAY_MS, out_dir=out_dir)

    # 步数计数：包裹 _record_step 后计数（原方法已被 attach 包裹，这里再套一层计数）
    orig_record = win._record_step

    def counting_record(*a, **k):
        r = orig_record(*a, **k)
        probe.note_step()
        return r
    win._record_step = counting_record

    state = {'done': False, 'exit_code': 0}

    def do_close():
        probe.log('closing_window', **probe.snap())
        win.close()
        QTimer.singleShot(250, app.quit)

    def finish(reason):
        if state['done']:
            return
        state['done'] = True
        probe.log('finishing', reason=reason, **probe.snap())
        try:
            if getattr(win, '_solver_running', False):
                win._stop_solver('probe_finish')
        except Exception as exc:                                # noqa: BLE001
            probe.log('finish_stop_error', error=repr(exc))
        probe.log('stopped', **probe.snap())
        QTimer.singleShot(350, do_close)

    def start():
        try:
            idx = args.strategy_index
            if idx is None:
                idx = win.solver_strategy.findData(args.strategy)
            if idx is not None and idx >= 0:
                win.solver_strategy.setCurrentIndex(idx)
            if args.preset_index is not None:
                win.solver_depth.setCurrentIndex(args.preset_index)
            i = win.solver_mode.findData('auto')
            if i >= 0:
                win.solver_mode.setCurrentIndex(i)
            probe.log('configured', strategy=win.solver_strategy.currentData(),
                      preset=win.solver_depth.currentData(), mode=win.solver_mode.currentData())
        except Exception as exc:                                # noqa: BLE001
            probe.log('configure_error', error=repr(exc))
        win.start_new_game()
        win._start_solver()
        probe.log('solver_started', **probe.snap())

    QTimer.singleShot(1200, start)

    watchdog = QTimer()

    def tick():
        elapsed = time.perf_counter() - probe.t0
        if probe.steps >= args.steps or elapsed >= args.seconds:
            watchdog.stop()
            probe.log('limit_reached', steps=probe.steps, wall_s=round(elapsed, 3))
            finish('limit')
            return
        if time.perf_counter() - probe.last_progress > 8.0:
            probe.stalls += 1
            probe.log('stall', steps=probe.steps, **probe.snap())
            probe.last_progress = time.perf_counter()

    watchdog.timeout.connect(tick)
    watchdog.start(500)
    app.exec_()
    probe.log('app_exited', steps=probe.steps)
    t = getattr(win, '_v6_t', {}) or {}
    tiers = getattr(win, '_v6_speed', None)
    out = {'out_dir': out_dir, 'steps': probe.steps,
           'wall_s': round(time.perf_counter() - probe.t0, 3),
           'stalls': probe.stalls, 'speed_tier': tiers,
           'search_ms': round(t.get('search_ms', 0.0), 1),
           'anim_ms': round(t.get('anim_ms', 0.0), 1),
           'wait_ms': round(t.get('wait_ms', 0.0), 1),
           'render_ms': round(t.get('render_ms', 0.0), 1),
           'steps_per_s': round(probe.steps / max(1e-6, time.perf_counter() - probe.t0), 3)}
    print(json.dumps(out, ensure_ascii=False))
    return state['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
