#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 跨运行方式交接真实 GUI E2E 取证脚本（仓库外临时脚本）。

流程（真实 Windows 窗口 + 真实求解线程 + 真实 Headless Worker）：
    标准运行→暂停→切快速继续→暂停→切后台继续(跑到 >=200 步)→暂停
    →切标准继续→暂停→切快速跑到 200 步→停止
每一步断言：执行模式、真实 engine/session、棋盘/分数/最高分/game_id/撤销栈/RNG。
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
import tempfile
import time
import traceback

ROOT = r'e:\PyQt5_demo\2048'
V6 = os.path.join(ROOT, 'v6_pyqt_2048_accelerated')
for p in (V6, os.path.join(V6, 'headless'), ROOT, os.path.join(ROOT, 'v5_pyqt_2048_solver')):
    if p not in sys.path:
        sys.path.insert(0, p)

EVID = os.environ.get('EVID_DIR') or tempfile.mkdtemp(prefix='v6_handoff_evid_')
os.makedirs(EVID, exist_ok=True)
TMP = tempfile.mkdtemp(prefix='v6_handoff_probe_')
os.environ['2048_HISTORY_DIR'] = os.path.join(TMP, 'history')
os.environ['PYTHONNOUSERSITE'] = '1'

from PyQt5.QtCore import Qt                                    # noqa: E402
from PyQt5.QtGui import QFont                                  # noqa: E402
from PyQt5.QtWidgets import QApplication                       # noqa: E402

QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
app = QApplication(sys.argv[:1])

import v6_pyqt_2048_accelerated as M                           # noqa: E402
import v6_speed as sp                                          # noqa: E402
import ownership as own                                        # noqa: E402
import core                                                    # noqa: E402

sp.PREFS_PATH = os.path.join(TMP, 'ui_prefs.json')

spec = importlib.util.spec_from_file_location('capmod', os.path.join(ROOT, 'tools', 'capture_gui.py'))
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)

CHECKS = []
SHOTS = []
LOG = []


def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    LOG.append(line)
    print(line, flush=True)


def check(cid, ok, detail):
    CHECKS.append({'id': cid, 'ok': bool(ok), 'detail': detail})
    log('%s %s — %s' % ('PASS' if ok else 'FAIL', cid, detail))


def pump(ms=80):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        watch()
        time.sleep(0.004)


LAST = {'gid': None, 'over': None}


def watch():
    win = globals().get('WIN_REF')
    if win is None:
        return
    gid = win.model.game_id
    over = bool(win.model.game_over)
    if LAST['gid'] is None:
        LAST['gid'], LAST['over'] = gid, over
        return
    if gid != LAST['gid']:
        log('WATCH 正式 game_id 变化：%s -> %s（score=%s over=%s）'
            % (LAST['gid'], gid, win.model.score, over))
        LAST['gid'] = gid
    if over != LAST['over']:
        log('WATCH game_over: %s -> %s（game=%s score=%s）'
            % (LAST['over'], over, gid, win.model.score))
        LAST['over'] = over


def wait(cond, timeout_s, step_ms=40):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        watch()
        try:
            if cond():
                return True
        except Exception:                                     # noqa: BLE001
            pass
        time.sleep(step_ms / 1000.0)
    return False


def state(win):
    m = win.model
    return {'grid': [row[:] for row in m.grid], 'score': int(m.score),
            'best': int(m.best_score), 'game_id': m.game_id,
            'undo': len(m.undo_stack),
            'rng': core.rng_state_to_json(random.getstate()),
            'active': getattr(win, '_v6_active_mode', None),
            'speed': getattr(win, '_v6_speed', None),
            'solver_running': bool(getattr(win, '_solver_running', False)),
            'local_paused': bool(getattr(win, '_v6_local_paused', False)),
            'job_id': getattr(win, '_job_id', None)}


def shot(win, name):
    try:
        hwnd = int(win.winId())
        cap.prepare_window(hwnd)
        cap.pump(app, 260)
        if not cap.is_window_on_top(hwnd):
            cap.force_foreground(hwnd)
            cap.pump(app, 180)
        frame, src = cap.visible_frame_rect(hwnd)
        img, grab = cap.capture_frame(hwnd, frame)
        path = os.path.join(EVID, name)
        ok = bool(not img.isNull() and img.save(path, 'PNG'))
        SHOTS.append({'name': name, 'path': path, 'ok': ok, 'frame_from': src,
                      'grab': grab, 'size': [img.width(), img.height()]})
        log('截图 %s ok=%s' % (name, ok))
        return ok
    except Exception as exc:                                  # noqa: BLE001
        SHOTS.append({'name': name, 'ok': False, 'error': repr(exc)})
        log('截图失败 %s: %r' % (name, exc))
        return False


def main():
    font = QFont('Microsoft YaHei', 10)
    if hasattr(font, 'setFamilies'):
        font.setFamilies(['Microsoft YaHei', 'Microsoft YaHei UI', 'SimHei'])
    app.setFont(font)
    if hasattr(M, 'build_app_icon'):
        app.setWindowIcon(M.build_app_icon())

    win = M.V6MainWindow()
    globals()['WIN_REF'] = win
    win.resize(900, 720)
    win.show()
    pump(500)

    # 真实 GUI 状态初始化：正式 game、棋盘、最高分、算法/强度/模式
    win.model.start_new_game()
    win.model.grid = [[2, 4, 8, 0], [16, 32, 64, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    win.model.score = 628
    win.model.best_score = 62188
    win.model.undo_stack.clear()
    win.model.redo_stack.clear()
    win.model.record_move('初始状态(测试盘面)')       # 让正式历史从该盘面开始（可审计）
    win.model.save_game_state()
    win.model.update_index()
    win.model.save_best_score()
    win.refresh()
    win.stack.setCurrentIndex(1)
    for combo, data in ((win.solver_strategy, 'heuristic'), (win.solver_depth, 'fast'),
                        (win.solver_mode, 'auto')):
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    win._v6_backend = 'reference'
    win._v6_apply_tier('standard', persist=False)

    ctl = win._v6_bg_controller
    ctl._staging_dir = os.path.join(TMP, 'bg_staging')
    ctl.state = 'GUI_IDLE'
    ctl.proc = None
    ctl._game_id = None
    ctl._last_result = None
    ctl._last_progress = None
    win._v6_active_mode = None
    win._v6_handoff = None
    win._v6_speed = 'standard'
    win._v6_sync_run_controls()
    pump(200)

    # ---- 取证插桩：谁在暗中新开局 / 谁在再次启动后台（用于定位异常路径）----
    _orig_new_game = win.start_new_game
    _orig_primary = win._v6_on_run_primary
    _orig_ctl_start = ctl.start

    def _trace(tag):
        import traceback
        stack = [ln.strip() for ln in traceback.format_stack()[:-2]][-6:]
        log('TRACE %s <- %s' % (tag, ' | '.join(stack)))

    def _new_game():
        _trace('start_new_game(game_id_before=%s)' % win.model.game_id)
        return _orig_new_game()

    def _primary():
        _trace('on_run_primary(active=%s speed=%s)'
               % (win._v6_active_mode, win._v6_speed))
        return _orig_primary()

    def _ctl_start(*a, **k):
        _trace('ctl.start(snapshot=%s)' % bool(k.get('snapshot')))
        return _orig_ctl_start(*a, **k)

    win.start_new_game = _new_game
    win._v6_on_run_primary = _primary
    ctl.start = _ctl_start

    game_id = win.model.game_id
    best0 = int(win.model.best_score)
    check('setup', best0 == 62188 and int(win.model.score) == 628,
          '初始最高分=%s 当前分=%s game=%s' % (best0, win.model.score, game_id))

    # ---------------- A. 标准运行 → 暂停 ----------------
    win._v6_start_local()
    ok = wait(lambda: win._v6_t.get('steps', 0) >= 2, 25)
    check('A1_standard_running', ok and win._v6_active_mode == 'standard'
          and win._solver_running, '标准本机求解真实运行（steps=%s job=%s）'
          % (win._v6_t.get('steps'), win._job_id))
    win._v6_on_run_primary()                      # 运行中 → 暂停
    ok = wait(lambda: win._v6_local_paused and not win._v6_local_pausing, 15)
    st_pauseA = state(win)
    check('A2_standard_paused', ok and win._v6_active_mode == 'standard'
          and win.v6_run_primary.text() == '继续',
          '已暂停：%s，步=%s，job=%s' % (win.v6_run_badge.text(),
                                       win._v6_t.get('steps'), win._job_id))

    # ---------------- B. 标准暂停 → 快速继续 ----------------
    win._v6_on_speed_clicked('fast')
    pump(120)
    check('B1_selection_recorded', win._v6_selected_mode == 'fast'
          and win._v6_speed == 'standard' and win._v6_active_mode == 'standard'
          and win.v6_run_primary.text() == '切换至快速模式并继续',
          '选项卡=%s，执行=%s，按钮=%s' % (win._v6_selected_mode, win._v6_active_mode,
                                        win.v6_run_primary.text()))
    shot(win, 'p1_standard_paused_selected_fast.png')
    steps_at = win._v6_t.get('steps', 0)
    win._v6_on_run_primary()
    ok = wait(lambda: win._v6_active_mode == 'fast' and win._v6_t.get('steps', 0) >= steps_at + 3, 25)
    check('B2_fast_running_after_handoff', ok and win._v6_speed == 'fast'
          and win._solver_running and win._v6_anim_off,
          '快速本机求解继续：步 %s→%s，job=%s，anim_off=%s'
          % (steps_at, win._v6_t.get('steps'), win._job_id, win._v6_anim_off))
    check('B3_preserved', int(win.model.best_score) >= 62188 and win.model.game_id == game_id,
          '最高分=%s（>=62188），game=%s 未变' % (win.model.best_score, win.model.game_id))
    shot(win, 'p2_fast_running_after_handoff.png')

    # ---------------- C. 快速暂停 → 后台继续（跑到 >=200 步） ----------------
    win._v6_on_run_primary()
    ok = wait(lambda: win._v6_local_paused, 15)
    check('C1_fast_paused', ok and win._v6_active_mode == 'fast', '快速模式已暂停')
    win._v6_on_speed_clicked('background')
    pump(120)
    check('C2_bg_selection', win._v6_selected_mode == 'background'
          and win.v6_run_primary.text() == '切换至后台求解模式并继续',
          '按钮=%s' % win.v6_run_primary.text())
    shot(win, 'p3_fast_paused_selected_background.png')

    score_before_bg = int(win.model.score)
    win._v6_on_run_primary()
    ok = wait(lambda: ctl.state == 'BG_RUNNING', 60)
    check('C3_worker_took_over', ok and win._v6_active_mode == 'background'
          and not win._solver_running, 'Worker state=%s pid=%s session=%s active=%s'
          % (ctl.state, getattr(ctl.proc, 'pid', None), ctl._game_id,
             win._v6_active_mode))
    owner = own.owner_status(ctl._staging_dir)
    check('C4_ownership', owner.get('state') == 'alive'
          and int((owner.get('record') or {}).get('pid', -1)) == int(ctl.proc.pid),
          'owner=%s pid=%s' % (owner.get('state'), (owner.get('record') or {}).get('pid')))
    ok = wait(lambda: (ctl._last_progress or {}).get('steps', 0) >= 200, 120)
    prog = ctl._last_progress or {}
    check('C5_background_200_steps', ok and int(prog.get('steps') or 0) >= 200,
          '后台真实步数=%s 分数=%s 最大=%s 后端=%s 引擎=%s'
          % (prog.get('steps'), prog.get('score'), prog.get('max_tile'),
             prog.get('backend_used'), prog.get('engine_used')))
    check('C6_background_progress_monotonic',
          int(prog.get('score') or 0) >= score_before_bg,
          '后台分数 %s >= 交接前 %s' % (prog.get('score'), score_before_bg))
    shot(win, 'p4_background_running_200plus.png')

    win._v6_on_run_primary()                      # 后台运行 → 暂停
    ok = wait(lambda: ctl.state == 'BG_PAUSED', 30)
    pump(400)
    res = ctl._last_result or {}
    snap = res.get('snapshot') or {}
    adopted = {'board': [row[:] for row in win.model.grid],
               'score': int(win.model.score),
               'rng': core.rng_state_to_json(random.getstate())}
    check('C7_background_paused_adopted', ok and adopted['board'] == snap.get('board')
          and adopted['score'] == int(snap.get('score') or -1),
          '暂停后官方棋盘/分数与 Worker 终态一致（rev=%s steps=%s）'
          % (snap.get('revision'), res.get('total_committed_moves')))
    worker_rng = snap.get('rng_state') or {}
    check('C8_paused_rng_identical',
          (worker_rng.get('keys') or []) == (adopted['rng'].get('keys') or [])
          and worker_rng.get('version') == adopted['rng'].get('version'),
          '暂停点全局 RNG 与 Worker 精确一致（version=%s）' % worker_rng.get('version'))
    check('C9_best_not_regressed', int(win.model.best_score) >= 62188
          and win.model.game_id == game_id,
          '最高分=%s，正式 game=%s' % (win.model.best_score, win.model.game_id))
    shot(win, 'p5_background_paused.png')

    # ---------------- D. 后台暂停 → 标准继续 ----------------
    bg_best = int(win.model.best_score)
    bg_undo = len(win.model.undo_stack)
    win._v6_on_speed_clicked('standard')
    pump(120)
    check('D1_bg_selection', win._v6_selected_mode == 'standard'
          and win.v6_run_primary.text() == '切换至标准模式并继续',
          '按钮=%s' % win.v6_run_primary.text())
    shot(win, 'p6_background_paused_selected_standard.png')
    old_pid = getattr(ctl.proc, 'pid', None)
    win._v6_on_run_primary()
    ok = wait(lambda: win._v6_active_mode == 'standard' and win._solver_running, 30)
    owner2 = own.owner_status(ctl._staging_dir)
    proc_done = ctl.proc is None or ctl.proc.poll() is not None
    check('D2_local_took_over', ok and proc_done and owner2.get('state') != 'alive',
          'active=%s running=%s worker_pid=%s exited=%s owner=%s'
          % (win._v6_active_mode, win._solver_running, old_pid, proc_done,
             owner2.get('state')))
    check('D3_preserved_after_bg', int(win.model.best_score) >= bg_best
          and win.model.game_id == game_id and len(win.model.undo_stack) >= bg_undo,
          '最高分 %s→%s，game=%s，撤销栈 %s→%s'
          % (bg_best, win.model.best_score, win.model.game_id, bg_undo,
             len(win.model.undo_stack)))
    shot(win, 'p7_standard_running_after_background.png')

    # ---------------- E. 标准暂停 → 快速继续，再跑 200 步 ----------------
    win._v6_on_run_primary()
    ok = wait(lambda: win._v6_local_paused, 15)
    win._v6_on_speed_clicked('fast')
    win._v6_on_run_primary()
    ok = wait(lambda: win._v6_active_mode == 'fast' and win._solver_running, 20)
    start_steps = win._v6_t.get('steps', 0)
    ok2 = wait(lambda: win._v6_t.get('steps', 0) >= start_steps + 200, 180)
    check('E1_fast_200_local_steps', ok and ok2,
          '快速本机连续求解 200 步：%s→%s（job=%s）'
          % (start_steps, win._v6_t.get('steps'), win._job_id))
    check('E2_best_monotonic', int(win.model.best_score) >= 62188
          and win.model.game_id == game_id,
          '最高分=%s game=%s' % (win.model.best_score, win.model.game_id))
    shot(win, 'p8_fast_running_200_steps.png')

    win._v6_on_run_stop()
    pump(300)
    check('E3_stopped', not win._solver_running and win._v6_active_mode is None,
          '停止后 active=%s running=%s' % (win._v6_active_mode, win._solver_running))

    total_moves = int(prog.get('total_committed_moves') or prog.get('steps') or 0)
    check('E4_total_over_400', total_moves + (win._v6_t.get('steps') or 0) >= 400,
          '后台 %s 步 + 本机 %s 步 = %s（累计>=400）'
          % (total_moves, win._v6_t.get('steps'), total_moves + win._v6_t.get('steps', 0)))

    summary = {
        'ok': all(c['ok'] for c in CHECKS),
        'checks': CHECKS,
        'screenshots': SHOTS,
        'log': LOG,
        'environment': {'python': sys.executable, 'tmp': TMP,
                        'platform': app.platformName(),
                        'history_dir': os.environ.get('2048_HISTORY_DIR'),
                        'backend': win._v6_backend},
        'final': state(win),
    }
    with open(os.path.join(EVID, 'cross_mode_e2e.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(EVID, 'cross_mode_e2e.log'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG))

    try:
        ctl.shutdown(timeout=5)
    except Exception:                                         # noqa: BLE001
        pass
    win.hide()
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    try:
        rc = main()
    except Exception:                                         # noqa: BLE001
        traceback.print_exc()
        with open(os.path.join(EVID, 'cross_mode_e2e_crash.txt'), 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())
        rc = 2
    raise SystemExit(rc)
