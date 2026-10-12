#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 后台求解工作进程 —— **不导入任何 Qt**；以 stdin/stdout 行式 JSON 与 GUI 通信。

启动（由 GUI 侧 supervisor 以子进程方式拉起）：
    python -m headless.worker_main            # 或 python <该文件路径>

协议（每行一个 JSON 对象）：
    GUI -> 进程: {"cmd":"start","snapshot":{...},"limits":{...},"backend":..,"native_search":..,
                  "staging":"<checkpoint 文件路径>"}
                 {"cmd":"pause"}  {"cmd":"resume"}  {"cmd":"stop"}  {"cmd":"ping"}
    进程 -> GUI: {"type":"ready","pid":..}
                 {"type":"progress", ...}
                 {"type":"final","status":"completed|paused|stopped|game_over|error", ...}
                 {"type":"pong"}
                 {"type":"error","error":"..."}

设计约束：
    - 只允许一个活动 worker（由 GUI 侧单写入者锁保证）；
    - 每步持久化到 staging 检查点（与既有每步存档同安全级别）；
    - 暂停返回检查点，继续用**精确棋盘 + RNG 状态**从暂停点继续（不回到初始种子）。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import core                                                          # noqa: E402
import game_loop                                                     # noqa: E402
import ownership as own                                              # noqa: E402


_SEQ = {'n': 0, '_lock': threading.Lock()}


def _emit(obj):
    with _SEQ['_lock']:
        _SEQ['n'] += 1
        obj = dict(obj)
        obj.setdefault('seq', _SEQ['n'])
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


class Control:
    def __init__(self):
        self.cancelled = False
        self.paused = False
        self.quit = False
        self.last_cmd = None
        self.resume_event = threading.Event()
        self.lock = threading.Lock()

    def on_cmd(self, cmd):
        with self.lock:
            self.last_cmd = cmd
            if cmd in ('stop', 'pause'):
                self.cancelled = True
                self.resume_event.set()
            elif cmd == 'quit':
                self.quit = True
                self.resume_event.set()
            elif cmd == 'ping':
                pass
        return cmd


def _reader(ctl, state):
    # 注意：管道上 `for line in sys.stdin` 会因预读缓冲阻塞，必须用 readline() 逐行取。
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _emit({'type': 'error', 'error': '非法命令 JSON'})
            continue
        cmd = msg.get('cmd')
        if cmd == 'ping':
            _emit({'type': 'pong'})
            continue
        state['commands'].append(msg)
        ctl.on_cmd(cmd)
        if cmd in ('start', 'pause', 'stop', 'quit'):
            _emit({'type': 'ack', 'cmd': cmd})       # 每条控制命令显式回执（含 seq）


def _control_watcher(ctl, staging):
    """低频（200ms）轮询控制文件：便于 GUI 重启后**重连**并停止/暂停本 worker。

    这是有界低频轮询（非自旋），用于“GUI 无管道时的重连控制”。
    """
    seen = None
    while not ctl.quit:
        try:
            rec = own.read_control(staging)
            if rec:
                key = (rec.get('at'), rec.get('cmd'))
                if key != seen:                       # 只处理“新写入”的控制记录
                    seen = key
                    cmd = rec.get('cmd')
                    if cmd in ('stop', 'pause', 'quit'):   # 忽略 'running' 等状态写入
                        ctl.on_cmd(cmd)
        except Exception:                                     # noqa: BLE001
            pass
        time.sleep(0.2)


def main():
    if os.environ.get('V6_WORKER_DUMP') == '1':
        import faulthandler
        faulthandler.dump_traceback_later(20, repeat=True)   # 诊断：定期 dump 各线程栈
    _emit({'type': 'ready', 'pid': os.getpid()})
    ctl = Control()
    state = {'commands': []}
    threading.Thread(target=_reader, args=(ctl, state), daemon=True).start()

    def cancel_cb():
        return ctl.cancelled

    ownership = None
    try:
        # 支持多轮：start -> (running -> final) -> start(恢复) -> ... -> quit
        while True:
            snapshot = None
            limits, backend, native_search, staging = {}, None, False, None
            while snapshot is None:
                with ctl.lock:
                    if ctl.quit:
                        return 0
                if not state['commands']:
                    time.sleep(0.02)
                    continue
                msg = state['commands'].pop(0)
                cmd = msg.get('cmd')
                if cmd == 'quit':
                    return 0
                if cmd != 'start':
                    continue
                snap = msg.get('snapshot')
                path = msg.get('snapshot_path')
                if snap is None and path:
                    with open(path, 'r', encoding='utf-8') as f:
                        snap = json.load(f)
                if snap is None:
                    _emit({'type': 'error', 'error': 'start 未提供 snapshot/snapshot_path'})
                    continue
                snapshot = snap
                limits = msg.get('limits') or {}
                backend = msg.get('backend')
                native_search = bool(msg.get('native_search'))
                staging = msg.get('staging')
                ownership = msg.get('ownership') or staging
            with ctl.lock:
                ctl.cancelled = False
            if ownership:
                # 先登记所有权 + 心跳，再预热：避免“长时间预热被误判为 worker 失效/未接管”
                own.write_owner(ownership, os.getpid(), snapshot['game_id'])
                own.write_control(ownership, 'running')
                threading.Thread(target=_control_watcher, args=(ctl, ownership),
                                 daemon=True).start()
            # 显式预热：首次 import solver_v6 会触发 numpy/pybind 一次性导入（可能数十秒），
            # 必须让它可见，否则 GUI/测试会误判为“卡死”。
            _emit({'type': 'warming', 'game_id': snapshot['game_id'],
                   'note': '首次导入求解栈并按所选算法/后端预热（可能较慢）'})
            _t_warm = time.perf_counter()
            warm_phases = []
            try:
                import solver_v6
                # 只预热**所选算法 + 所选后端**的路径：避免无关后端（如 numba）冷导入拖死首解
                _p0 = time.perf_counter()
                solver_v6.solve([[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 2, 2]],
                                snapshot['algorithm'], backend=backend)
                warm_phases.append({'phase': 'solve_warmup',
                                    'ms': round((time.perf_counter() - _p0) * 1000.0, 1)})
            except Exception as exc:                                  # noqa: BLE001
                warm_phases.append({'phase': 'solve_warmup_error', 'error': repr(exc)})
            _emit({'type': 'warmed', 'game_id': snapshot['game_id'],
                   'warmup_ms': round((time.perf_counter() - _t_warm) * 1000.0, 1),
                   'warm_phases': warm_phases})

            def _progress(p, _own=ownership):
                if _own:
                    try:
                        own.touch_heartbeat(_own, os.getpid(), p.get('game_id'),
                                            p.get('revision'), p.get('step'),
                                            p.get('score'), p.get('wall_ms'))
                    except Exception:                             # noqa: BLE001
                        pass
                return _emit(p)

            try:
                ckpt = game_loop.Checkpoint(staging) if staging else None
                result = game_loop.run_session(
                    snapshot, limits, checkpoint=ckpt,
                    progress_cb=_progress, cancel=cancel_cb,
                    solver_backend=backend, native_search=native_search)
                _emit({'type': 'final', **result})
                terminal = result['status'] not in ('stopped', 'paused')
                if result['status'] == 'stopped' and ctl.last_cmd == 'stop':
                    return 0                      # 显式 stop：终结并退出
                if terminal:
                    return 0
            except Exception as exc:                                  # noqa: BLE001
                _emit({'type': 'error', 'error': '%s: %s' % (type(exc).__name__, exc)})
                return 1
    finally:
        # 正常退出 / 异常退出都释放所有权（避免“进程已退出但所有权未清理”）
        if ownership:
            try:
                if os.path.exists(own.owner_path(ownership)):
                    rec = own.read_owner(ownership) or {}
                    if int(rec.get('pid', -1)) == os.getpid():
                        os.remove(own.owner_path(ownership))
                if os.path.exists(own.heartbeat_path(ownership)):
                    os.remove(own.heartbeat_path(ownership))
            except OSError:
                pass


if __name__ == '__main__':
    try:
        code = main()
    finally:
        try:
            _emit({'type': 'exited', 'code': 0})     # 退出前显式通告（GUI 据此确认进程终止）
        except Exception:                                        # noqa: BLE001
            pass
    raise SystemExit(code)
