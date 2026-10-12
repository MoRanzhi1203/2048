#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 后台求解有界性能基准（真实交互式 IPC 管道 + 持续排空 stdout）。

严格分段（互不重叠，来自 worker 的 perf）：
    startup_ms  进程启动 -> ready
    init_ms     start -> 首个 progress（求解器导入/后端探测等一次性开销）
    search_ms   求解器累计
    apply_ms    移动+生成+分数（不含持久化）
    serialize_ms / write_ms / checkpoint_ms(=serialize+write)
    wall_total_ms  worker 内部整个会话墙钟
    ipc：progress 条数 + 每条大小（IPC 仅承载低频进度，不参与逐帧渲染）
吞吐分别给出“含初始化”和“剔除初始化”两种口径，禁止用短程推算长程。
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import time

V6 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V6)
sys.path.insert(0, os.path.join(V6, 'headless'))
sys.path.insert(0, os.path.dirname(V6))

import core                                                          # noqa: E402

PY = sys.executable
BOARD = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]


def run_once(steps, out_dir, tag):
    tmp = os.path.join(out_dir, 'staging')
    os.makedirs(tmp, exist_ok=True)
    snap = core.build_snapshot(BOARD, 0, 0, core.rng_state_to_json(random.getstate()),
                               'bench_%s' % tag, 0, 'expectimax', 'fast')
    sp = os.path.join(tmp, '%s_snap.json' % tag)
    with open(sp, 'w', encoding='utf-8') as f:
        f.write(core.snapshot_to_json(snap))
    ck = os.path.join(tmp, '%s_ck.json' % tag)
    env = dict(os.environ, PYTHONNOUSERSITE='1')
    t_spawn = time.perf_counter()
    proc = subprocess.Popen([PY, '-m', 'headless.worker_main'], cwd=V6, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=open(os.path.join(tmp, '%s_stderr.log' % tag), 'w',
                                        encoding='utf-8'), text=True, bufsize=1)
    lines = []
    threading.Thread(target=lambda: [lines.append(x) for x in iter(proc.stdout.readline, '')],
                     daemon=True).start()

    def wait(kind, timeout):
        t0 = time.time()
        idx = 0
        while time.time() - t0 < timeout:
            while idx < len(lines):
                m = json.loads(lines[idx])
                idx += 1
                if m.get('type') == kind:
                    return m, time.perf_counter()
            if proc.poll() is not None and not lines:
                raise RuntimeError('worker 退出 rc=%s' % proc.returncode)
            time.sleep(0.02)
        raise TimeoutError('wait %s 超时；已收类型=%s；stderr=%s'
                           % (kind, [json.loads(x).get('type') for x in lines],
                              open(os.path.join(tmp, '%s_stderr.log' % tag),
                                   encoding='utf-8').read()[-600:]))

    _, t_ready = wait('ready', 30)
    t_start = time.perf_counter()
    proc.stdin.write(json.dumps({'cmd': 'start', 'snapshot_path': sp,
                                 'limits': {'max_steps': steps, 'max_seconds': 900,
                                            'progress_interval_s': 0.5,
                                            'progress_every_steps': 25},
                                 'backend': 'cpp', 'staging': ck, 'ownership': tmp}) + '\n')
    proc.stdin.flush()
    warm, t_warm = wait('warmed', 600)          # 显式预热（首次 import 求解栈）
    _, t_first = wait('progress', 300)
    final, t_final = wait('final', 900)
    exited, t_exited = wait('exited', 60)
    proc.wait(timeout=30)
    perf = final.get('perf', {})
    n = final.get('steps', steps)
    row = {
        'tag': tag, 'requested_steps': steps, 'steps': n,
        'status': final.get('status'), 'exit_code': proc.returncode,
        'exited_code': exited.get('code'),
        'backend_used': final.get('backend_used'), 'engine_used': final.get('engine_used'),
        'startup_ms': round((t_ready - t_spawn) * 1000, 1),
        'warmup_ms': warm.get('warmup_ms'),
        'init_ms': round((t_first - t_warm) * 1000, 1),
        'harness_wall_ms': round((t_exited - t_spawn) * 1000, 1),
        'worker_wall_total_ms': perf.get('wall_total_ms'),
        'search_ms': perf.get('search_ms'), 'apply_ms': perf.get('apply_logic_ms'),
        'serialize_ms': perf.get('serialize_ms'), 'write_ms': perf.get('write_ms'),
        'checkpoint_ms': perf.get('checkpoint_ms'), 'wall_step_ms': perf.get('wall_step_ms'),
        'progress_msgs': sum(1 for x in lines if '"progress"' in x),
        'steps_per_s_excl_init': round(n / max(1e-9, (perf.get('wall_total_ms', 1) or 1) / 1000.0), 2),
        'steps_per_s_incl_init': round(n / max(1e-9, (t_exited - t_start)), 2),
        'checkpoint_per_step_ms': round((perf.get('checkpoint_ms', 0) or 0) / max(1, n), 3),
        'search_per_step_ms': round((perf.get('search_ms', 0) or 0) / max(1, n), 3),
    }
    return row


def main():
    out_dir = os.path.join(V6, 'experiments', 'v6_2', '20261012_headless_bg')
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    print('warmup ...', flush=True)
    rows.append(run_once(50, out_dir, 'warmup50'))
    for n in (100, 500, 1000):
        print('run %d ...' % n, flush=True)
        rows.append(run_once(n, out_dir, 'n%d' % n))
    with open(os.path.join(out_dir, 'bench_bg_steps.json'), 'w', encoding='utf-8') as f:
        json.dump({'kind': 'v6_bg_steps_bench', 'rows': rows}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, 'bench_bg_steps.csv'), 'w', encoding='utf-8') as f:
        keys = list(rows[0].keys())
        f.write(','.join(keys) + '\n')
        for r in rows:
            f.write(','.join(str(r.get(k, '')) for k in keys) + '\n')
    for r in rows:
        print('  %-9s steps=%-5s %s  %s/%s  warm=%.0fms init=%.0fms search/step=%.2fms '
              'ckpt/step=%.2fms  %.2f steps/s(excl init)  %.2f(incl)  rc=%s'
              % (r['tag'], r['steps'], r['status'], r['backend_used'], r['engine_used'],
                 r['startup_ms'], r['init_ms'], r['search_per_step_ms'],
                 r['checkpoint_per_step_ms'], r['steps_per_s_excl_init'],
                 r['steps_per_s_incl_init'], r['exit_code']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
