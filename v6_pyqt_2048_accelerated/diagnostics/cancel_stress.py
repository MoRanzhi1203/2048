#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 单程序取消/生命周期压力：反复「求解中停止」「求解中热切换算法」「求解中关闭窗口」，
检验协作式取消（threading.Event）、job_id/棋盘签名过期结果丢弃、QThread 回收与
Qt 对象生命周期（是否出现 QThread destroyed while running / 悬空回调 / 崩溃）。

用法：python cancel_stress.py [--cycles 40] [--hold-ms 300] [--out <dir>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V6_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qt_stability_probe import Probe, install_hooks                       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cycles', type=int, default=40)
    ap.add_argument('--hold-ms', type=int, default=300)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    stamp = time.strftime('%Y%m%d_%H%M%S')
    out_dir = args.out or os.path.join(V6_DIR, 'diagnostics', 'runs', '%s_cancel_stress' % stamp)
    os.makedirs(out_dir, exist_ok=True)
    install_hooks(out_dir)
    os.environ['2048_HISTORY_DIR'] = os.path.join(out_dir, 'history_root')

    import v6_pyqt_2048_accelerated as _v6
    _v6.V6_RESULT_DIR = os.path.join(out_dir, 'solver_results')
    _v6.V6_EXPORT_DIR = os.path.join(_v6.V6_RESULT_DIR, 'exports')
    _v6.V6_SESSIONS_FILE = os.path.join(_v6.V6_RESULT_DIR, 'sessions.json')

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    win = _v6.V6MainWindow()
    win.show()
    probe = Probe(win, out_dir)
    probe.attach()

    # 统计过期结果（V5 会通过 _log_step 记录“已忽略过期求解结果”）
    stale = {'count': 0}
    orig_log = win._log_step

    def counting_log(text):
        if '过期求解结果' in text:
            stale['count'] += 1
            probe.log('stale_result_ignored', text=text)
        return orig_log(text)
    win._log_step = counting_log

    strat_idx = [0]
    cycle = [0]

    def do_cycle():
        if cycle[0] >= args.cycles:
            probe.log('cycles_done', cycles=cycle[0], stale_ignored=stale['count'])
            # 最后一击：求解中关闭窗口（检验 QThread 回收 / 悬空回调）
            win.start_new_game()
            win._start_solver()
            probe.log('close_mid_solve_start', **probe.snap())
            QTimer.singleShot(200, finish_close)
            return
        cycle[0] += 1
        if cycle[0] % 10 == 0:
            # 求解中热切换算法（V5 会自增 job_id 并取消在途任务）
            try:
                strat_idx[0] = (strat_idx[0] + 1) % max(1, win.solver_strategy.count())
                win.solver_strategy.setCurrentIndex(strat_idx[0])
                probe.log('hot_switch_strategy', index=strat_idx[0], **probe.snap())
            except Exception as exc:                                   # noqa: BLE001
                probe.log('hot_switch_error', error=repr(exc))
        win.start_new_game()
        win._start_solver()
        probe.log('cycle_start', cycle=cycle[0], **probe.snap())
        QTimer.singleShot(args.hold_ms, stop_cycle)

    def stop_cycle():
        probe.log('cycle_stop_begin', cycle=cycle[0], **probe.snap())
        if getattr(win, '_solver_running', False):
            win._stop_solver('stress')
        probe.log('cycle_stop_end', cycle=cycle[0], **probe.snap())
        QTimer.singleShot(60, do_cycle)

    def finish_close():
        probe.log('closing_mid_solve', **probe.snap())
        ok = True
        try:
            win.close()
        except Exception as exc:                                       # noqa: BLE001
            ok = False
            probe.log('close_error', error=repr(exc))
        probe.log('closed', ok=ok, **probe.snap())
        _v6.V6_SESSIONS_FILE = _v6.V6_SESSIONS_FILE  # noqa: PLW0127
        QTimer.singleShot(300, app.quit)

    QTimer.singleShot(1200, do_cycle)
    app.exec_()
    result = {'out_dir': out_dir, 'cycles': cycle[0], 'stale_ignored': stale['count'],
              'wall_s': round(time.perf_counter() - probe.t0, 3)}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
