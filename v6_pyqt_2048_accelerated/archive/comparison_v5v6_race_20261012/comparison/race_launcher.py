#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5.1 ↔ V6.2 双窗口实时竞赛启动协调器。

职责：
    - 创建独立竞赛会话目录（V6 experiments/race/<session_id>/，不触碰生产存档）；
    - 启动两个**独立进程**（V5 侧 / V6 侧），各自独立存档目录、会话文件与单实例锁；
    - 在真实 Windows 桌面上把两个窗口**左右并排**摆放（Win32 SetWindowPos，优先工作区）；
    - 提供 start / pause / resume / step / stop / reset / close / summary 独立操作；
    - （可选）前台运行协调循环：A 模式推进步进屏障、监测上限、结束时写汇总。

用法示例：
    python race_launcher.py start  --mode B --max-steps 20  --auto-exit
    python race_launcher.py start  --mode A --max-steps 200 --foreground
    python race_launcher.py summary --session-dir <dir>
    python race_launcher.py stop    --session-dir <dir>
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (_HERE, V6_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import race_protocol as P                                              # noqa: E402

PYTHON = os.environ.get('V6_PYTHON') or r'E:\anaconda3\envs\2048\python.exe'
RACE_ROOT = os.path.join(V6_DIR, 'experiments', 'race')


# ------------------------------------------------------------ Win32 摆放
class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]


def _user32():
    return ctypes.windll.user32


def find_top_windows(pid):
    u = _user32()
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _lparam):
        wpid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n > 0:
                r = RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                area = max(0, r.right - r.left) * max(0, r.bottom - r.top)
                found.append((area, hwnd))
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    found.sort(reverse=True)                     # 取面积最大的可见顶层窗口
    return [h for _a, h in found]


def work_area():
    u = _user32()
    r = RECT()
    SPI_GETWORKAREA = 0x0030
    if u.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
        return (r.left, r.top, r.right, r.bottom)
    return (0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1))


def move_window(hwnd, x, y, w, h):
    u = _user32()
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    u.SetWindowPos(hwnd, 0, int(x), int(y), int(w), int(h), SWP_NOZORDER | SWP_NOACTIVATE)


def get_rect(hwnd):
    r = RECT()
    _user32().GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def place_side_by_side(pid_left, pid_right, retries=40, interval=0.25):
    """等待两个窗口出现并左右并排；返回实际几何信息。"""
    hl = hr = None
    for _ in range(retries):
        if hl is None:
            ws = find_top_windows(pid_left)
            hl = ws[0] if ws else None
        if hr is None:
            ws = find_top_windows(pid_right)
            hr = ws[0] if ws else None
        if hl and hr:
            break
        time.sleep(interval)
    if not (hl and hr):
        return {'placed': False, 'reason': 'window_not_found',
                'left_found': bool(hl), 'right_found': bool(hr)}
    wa_l, wa_t, wa_r, wa_b = work_area()
    lx, ly, lw, lh = get_rect(hl)
    rx, ry, rw, rh = get_rect(hr)
    move_window(hl, wa_l, wa_t, lw, lh)               # 左窗口贴左
    move_window(hr, wa_r - rw, wa_t, rw, rh)          # 右窗口贴右
    overlap = (wa_l + lw) - (wa_r - rw)               # >0 表示两窗重叠像素
    return {
        'placed': True,
        'work_area': [wa_l, wa_t, wa_r, wa_b],
        'left': {'hwnd': int(hl), 'pid': pid_left, 'x': wa_l, 'y': wa_t, 'w': lw, 'h': lh},
        'right': {'hwnd': int(hr), 'pid': pid_right, 'x': wa_r - rw, 'y': wa_t, 'w': rw, 'h': rh},
        'overlap_px': int(overlap),
        'no_truncation': True,
        'note': '窗口保持各自设计尺寸，不做缩放，避免截断标题栏/棋盘/按钮；overlap_px>0 表示屏幕偏窄时右侧略覆盖左侧。',
    }


# ------------------------------------------------------------ 启动
def _spawn(session_dir, cfg, side, script_name):
    env = dict(os.environ)
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONFAULTHANDLER'] = '1'      # 致命信号（含 Windows 访问冲突）时 dump Python 栈
    env['V6_RACE_SESSION'] = session_dir
    env['2048_HISTORY_DIR'] = P.side_history_root(session_dir, side)
    if side == 'v6':
        env['V6_BACKEND'] = str((cfg.get('v6_override') or {}).get('backend', 'auto'))
    script = os.path.join(_HERE, script_name)
    creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    log_path = os.path.join(session_dir, 'proc_%s.log' % side)
    logf = open(log_path, 'a', encoding='utf-8', errors='replace')
    proc = subprocess.Popen([PYTHON, script], cwd=V6_DIR, env=env,
                            creationflags=creationflags, close_fds=True,
                            stdout=logf, stderr=subprocess.STDOUT)
    proc._race_log = logf
    return proc


def _pid_alive(pid):
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259
    except Exception:                                       # noqa: BLE001
        return False


def action_start(args):
    session_id = args.session_id or time.strftime('%Y%m%d_%H%M%S') + '_' + args.mode
    session_dir = args.session_dir or os.path.join(RACE_ROOT, session_id)
    os.makedirs(session_dir, exist_ok=True)

    algorithm = dict(P.DEFAULT_SESSION['algorithm'])
    if args.strategy:
        algorithm['strategy'] = args.strategy
    if args.depth is not None:
        algorithm['depth'] = int(args.depth)
    if args.time_limit is not None:
        algorithm['time_limit'] = float(args.time_limit)
    v6_override = {}
    if args.v6_native:
        v6_override['native_search'] = True
        algorithm['depth'] = int(args.depth if args.depth is not None else 3)
        algorithm['prune'] = False
        algorithm['time_limit'] = float(args.time_limit if args.time_limit is not None else 10.0)
    if args.fixed_work:
        algorithm['prune'] = False
        algorithm['sample_limit'] = 0
        algorithm['prob_cutoff'] = 0.0
        if algorithm.get('time_limit', 0.3) < 5.0:
            algorithm['time_limit'] = 30.0
    if args.v6_backend:
        v6_override['backend'] = args.v6_backend

    cfg = P.build_session(session_id, mode=args.mode, seed=args.seed,
                          max_steps=args.max_steps, max_seconds=args.max_seconds,
                          auto_exit=args.auto_exit, algorithm=algorithm,
                          v6_override=v6_override, step_interval_ms=args.step_interval_ms,
                          particles=args.particles)
    P.write_json(P.session_paths(session_dir)['session'], cfg)
    P.write_control(session_dir, cmd='start', step_index=1)

    procs = {}
    for side, script in (('v5', 'race_window_v5.py'), ('v6', 'race_window_v6.py')):
        procs[side] = _spawn(session_dir, cfg, side, script)

    placement = place_side_by_side(procs['v5'].pid, procs['v6'].pid)
    launch = {
        'session_id': session_id, 'session_dir': session_dir, 'mode': args.mode,
        'seed': args.seed, 'algorithm': algorithm, 'v6_override': v6_override,
        'auto_exit': args.auto_exit, 'max_steps': args.max_steps,
        'max_seconds': args.max_seconds, 'started_at': P.now_iso(),
        'pids': {s: procs[s].pid for s in procs}, 'placement': placement,
        'python': PYTHON,
    }
    P.write_json(P.session_paths(session_dir)['launch'], launch)
    print(json.dumps(launch, ensure_ascii=False, indent=2), flush=True)

    if args.foreground:
        run_coordinator(session_dir, cfg)
    return 0


# ------------------------------------------------------------ 协调循环
def run_coordinator(session_dir, cfg):
    """前台协调：A 模式推进步进；监测上限/进程退出；结束时写汇总。"""
    t0 = time.time()
    max_seconds = float(cfg.get('max_seconds') or 180)
    max_steps = int(cfg.get('max_steps') or 200)
    interval_min_ms = int(cfg.get('step_interval_ms') or 900)
    launch = P.read_json(P.session_paths(session_dir)['launch'], default={}) or {}
    pids = launch.get('pids') or {}
    last_advance = 0.0
    dead = {}
    try:
        while True:
            h5 = P.read_json(P.side_hud_path(session_dir, 'v5'), default={}) or {}
            h6 = P.read_json(P.side_hud_path(session_dir, 'v6'), default={}) or {}
            s5 = int(h5.get('steps') or 0)
            s6 = int(h6.get('steps') or 0)
            for side, pid in pids.items():
                if side not in dead and not _pid_alive(pid):
                    dead[side] = {'pid': pid, 'alive': False, 'detected_at': P.now_iso()}
                    print(json.dumps({'event': 'process_exited', 'side': side, 'pid': pid},
                                     ensure_ascii=False), flush=True)
            if cfg.get('mode') == 'A':
                nxt = min(s5, s6) + 1
                if nxt > P.read_control(session_dir).get('step_index', 0):
                    if (time.time() - last_advance) * 1000.0 >= interval_min_ms:
                        P.write_control(session_dir, step_index=nxt)
                        last_advance = time.time()
            done5 = bool(h5.get('game_over')) or s5 >= max_steps or 'v5' in dead
            done6 = bool(h6.get('game_over')) or s6 >= max_steps or 'v6' in dead
            if (done5 and done6) or (time.time() - t0) > max_seconds + 30:
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    if dead:
        launch['process_exit'] = dead
        P.write_json(P.session_paths(session_dir)['launch'], launch)
    summary = P.write_summary(session_dir)
    print(json.dumps({'summary_path': P.session_paths(session_dir)['summary_json'],
                      'dead': dead,
                      'sides': summary['sides']}, ensure_ascii=False, indent=2), flush=True)
    return summary


# ------------------------------------------------------------ 控制
def action_control(args):
    d = args.session_dir
    if not d or not os.path.isdir(d):
        print(json.dumps({'error': 'session_dir 不存在：%s' % d}, ensure_ascii=False))
        return 2
    if args.action == 'summary':
        s = P.write_summary(d)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    if args.action == 'step':
        cur = int(P.read_control(d).get('step_index', 0))
        P.write_control(d, step_index=cur + 1, note='manual step')
    elif args.action == 'close':
        P.write_control(d, cmd='quit')          # 关闭对比会话：让两侧窗口自行 close()
    else:
        P.write_control(d, cmd=args.action)
    print(json.dumps({'action': args.action, 'session_dir': d,
                      'control': P.read_control(d)}, ensure_ascii=False, indent=2))
    return 0


# ------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description='V5↔V6 双窗口竞赛启动协调器')
    sub = ap.add_subparsers(dest='action', required=True)

    s = sub.add_parser('start', help='启动两个独立进程并左右并排')
    s.add_argument('--mode', default='B', choices=['A', 'B', 'C'])
    s.add_argument('--seed', type=int, default=2048)
    s.add_argument('--max-steps', type=int, default=200)
    s.add_argument('--max-seconds', type=float, default=180.0)
    s.add_argument('--strategy', default='expectimax')
    s.add_argument('--depth', type=int, default=None)
    s.add_argument('--time-limit', type=float, default=None)
    s.add_argument('--v6-native', action='store_true', help='V6 侧启用 native_search（整树）')
    s.add_argument('--fixed-work', action='store_true',
                   help='固定工作量对照：prune=False 且不采样/不截断（同深度、同步数）')
    s.add_argument('--v6-backend', default=None, help='V6 侧后端 reference/numpy/numba/cpp/auto')
    s.add_argument('--step-interval-ms', type=int, default=900)
    s.add_argument('--auto-exit', action='store_true', help='达到上限后自动关闭窗口（冒烟测试用）')
    s.add_argument('--particles', action='store_true',
                   help='保留粒子特效（默认竞赛态关闭以降低渲染压力；两侧始终一致）')
    s.add_argument('--foreground', action='store_true', help='前台运行协调循环并写汇总')
    s.add_argument('--session-id', default=None)
    s.add_argument('--session-dir', default=None)

    for a in ('pause', 'resume', 'stop', 'reset', 'close', 'step', 'summary'):
        c = sub.add_parser(a, help='对已有会话执行 %s' % a)
        c.add_argument('--session-dir', required=True)

    args = ap.parse_args()
    if args.action == 'start':
        return action_start(args)
    return action_control(args)


if __name__ == '__main__':
    sys.exit(main())
