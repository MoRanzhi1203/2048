#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 基准公共工具：固定棋盘加载、计时、后端迭代、公共事件流 rollout 驱动。

所有基准脚本共用本模块，保证“相同接口、相同批量频率、相同棋盘集”的可比性。
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import statistics
import sys
import time

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(BENCH_DIR)
REPO_ROOT = os.path.dirname(V6_DIR)

if V6_DIR not in sys.path:
    sys.path.insert(0, V6_DIR)

from solver_backends.events import SpawnEventStream, pick_cell_index, pick_tile_value  # noqa: E402
from solver_backends.dispatch import probe_backends, create_backend                    # noqa: E402
from solver_backends.api import BoardOverflowError                                     # noqa: E402


def load_boards(path=None):
    path = path or os.path.join(BENCH_DIR, 'boards.jsonl')
    with open(path, 'rb') as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    boards = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    return boards, sha


def boards_sha_expected():
    with open(os.path.join(BENCH_DIR, 'boards.sha256'), 'r', encoding='ascii') as f:
        return f.read().strip()


def make_backend(name):
    """创建后端；不可用返回 None。"""
    try:
        return create_backend(name)
    except Exception:                                       # noqa: BLE001
        return None


def timing(fn, warmup=3, repeat=30):
    """返回每次迭代的耗时样本（ns）。gc 关闭，warm-up 与测量分离。"""
    for _ in range(warmup):
        fn()
    samples = []
    gc.disable()
    try:
        for _ in range(repeat):
            t0 = time.perf_counter_ns()
            fn()
            samples.append(time.perf_counter_ns() - t0)
    finally:
        gc.enable()
    return samples


def stats(samples):
    if not samples:
        return {}
    s = sorted(samples)
    n = len(s)
    return {
        'n': n,
        'mean_ns': statistics.fmean(samples),
        'median_ns': statistics.median(samples),
        'std_ns': statistics.pstdev(samples) if n > 1 else 0.0,
        'min_ns': s[0],
        'max_ns': s[-1],
        'p95_ns': s[min(n - 1, int(round(0.95 * (n - 1))))],
    }


def rollout_py(backend, board, gained, depth, stream, cursor, weights, max_tile_guard=1 << 15):
    """通用 Python 驱动的 rollout（消费公共事件流）——reference/numpy/numba/cpp 共用同一驱动。

    事件消费顺序与 C++ `rollout_events` 完全一致：每步先 (u_cell,u_value) 生成，再 u_move 选向。
    """
    g = board
    score = gained
    for _ in range(depth):
        if backend.is_game_over(g):
            break
        cells = backend.empty_cells(g)
        if not cells:
            break
        uc = stream.cell[cursor[0] % stream.n]
        uv = stream.value[cursor[0] % stream.n]
        cursor[0] += 1
        idx = pick_cell_index(uc, len(cells))
        i, j = cells[idx]
        val = pick_tile_value(uv)
        g = [row[:] for row in g]
        g[i][j] = val
        if backend.is_game_over(g):
            break
        moves = backend.legal_moves(g)
        if not moves:
            break
        um = stream.move[cursor[0] % stream.n]
        cursor[0] += 1
        mi = int(um * len(moves))
        if mi >= len(moves):
            mi = len(moves) - 1
        if mi < 0:
            mi = 0
        try:
            g, gain, _ = backend.move(g, moves[mi])
        except BoardOverflowError:
            break
        score += gain
    return score + backend.evaluate(g, weights)


def ts_run_dir(out_root, prefix):
    ts = time.strftime('%Y%m%d_%H%M%S')
    d = os.path.join(out_root, '%s_%s' % (prefix, ts))
    os.makedirs(d, exist_ok=True)
    return d, ts


def write_json_csv(run_dir, stem, meta, rows, csv_header, csv_rows):
    with open(os.path.join(run_dir, stem + '.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    import csv as _csv
    with open(os.path.join(run_dir, stem + '.csv'), 'w', encoding='utf-8', newline='') as f:
        w = _csv.writer(f)
        w.writerow(csv_header)
        w.writerows(csv_rows)
    return os.path.join(run_dir, stem + '.json')


def env_meta():
    import platform
    return {
        'python': sys.executable,
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'cpu_count': os.cpu_count(),
        'thread_env': {k: os.environ.get(k) for k in
                       ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS',
                        'NUMEXPR_NUM_THREADS')},
    }


def backend_availability():
    return {k: {'available': v['available'], 'reason': v['reason'], 'kind': v['kind']}
            for k, v in probe_backends().items()}
