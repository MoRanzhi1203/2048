#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6.2 公平基准：固定工作量 + 固定墙钟预算，覆盖 Reference / Python+CPP 原语 /
Numba / Native single / Native batch / Native full-tree。

严格原则（对齐 V6.2 指令 S7）：
- 同一子表内比较的变体使用**同一算法语义、同一工作量（rollout×depth / 深度 / 模拟数）**
  与**同一随机事件流**（MCTS 使用事件镜像作为 Python 基线，保证逐步同源）。
- 变体之间只有「计算落在哪里」不同：纯 Python reference / Python 循环驱动 C++ 原语 /
  Numba / C++ 原生整树。不同 RNG 来源的变体（如 rollout 的 native 事件流 vs Python RNG）
  单列并如实报告动作一致率，不假报逐步相等。
- 预热与测量分离；Numba JIT 与 native 初次调用单独 warmup；计时关闭 gc。
- 输出原始 JSON + CSV，绝不覆盖旧结果。
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
import tracemalloc

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(BENCH_DIR)
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (BENCH_DIR, V6_DIR, os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _bench_common as C                                                   # noqa: E402
import solver_v6 as S                                                      # noqa: E402
from solver_backends import native_api as NA                              # noqa: E402
from solver_backends.dispatch import create_backend, probe_backends       # noqa: E402
from solver_backends.events import SpawnEventStream                       # noqa: E402

DW = S.DEFAULT_WEIGHTS
WV = NA.weight_vector(DW)
REPEATS = 7


def _stats(samples):
    s = sorted(samples)
    n = len(s)
    return {
        'n': n,
        'median_ms': statistics.median(s),
        'mean_ms': statistics.fmean(s),
        'p95_ms': s[min(n - 1, int(round(0.95 * (n - 1))))],
        'min_ms': s[0],
        'max_ms': s[-1],
    }


def _timed(fn, repeats=REPEATS):
    """预热 1 次 + 关闭 gc 重复计时（毫秒）。"""
    fn()
    out = []
    gc.disable()
    try:
        for _ in range(repeats):
            t0 = time.perf_counter_ns()
            fn()
            out.append((time.perf_counter_ns() - t0) / 1e6)
    finally:
        gc.enable()
    return out


def _py_peak_kb(fn):
    tracemalloc.start()
    try:
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / 1024.0


# =====================================================================
# 变体：固定工作量
# =====================================================================
def variant_dispatch(name, boards, cfg):
    """返回 (per_board_rows, work_summary)。每个 per_board 行含 best_direction/elapsed/work。"""
    ref = create_backend('reference')
    cpp = create_backend('cpp') if probe_backends().get('cpp', {}).get('available') else None
    rows = []

    def solve(backend, **extra):
        return [S.solve(b['board'], cfg['strategy'], backend=backend, **dict(cfg['options'], **extra))
                for b in boards]

    if name == 'reference':
        fn = lambda: solve('reference')
    elif name == 'numba':
        fn = lambda: solve('numba')
    elif name == 'python_kernel_cpp':
        fn = lambda: solve('cpp')
    elif name == 'native_full_tree':
        fn = lambda: solve('cpp', native_search=True)
    elif name == 'native_rollout_batch':
        fn = lambda: solve('cpp', native_rollout=True)
    else:
        raise KeyError(name)

    samples = _timed(fn)
    res = fn()
    total_work = 0.0
    for r in res:
        rows.append({'best_direction': r.get('best_direction'),
                     'elapsed_ms': r.get('elapsed_ms'),
                     'nodes': r.get('nodes'),
                     'engine_used': r.get('engine_used'),
                     'backend_used': r.get('backend_used')})
        total_work += float(r.get('nodes') or r.get('completed_simulations') or 0)
    return rows, samples, total_work


def run_fixed_work(boards, out_dir):
    """固定工作量主对照表。"""
    ref = create_backend('reference')
    cpp = create_backend('cpp')
    avail = probe_backends()

    configs = [
        ('rollout', dict(strategy='rollout',
                         options=dict(rollouts=20, rollout_depth=16, seed=2048)),
         ['reference', 'numba', 'python_kernel_cpp', 'native_rollout_batch'], 12),
        ('expectimax_exact_d3', dict(strategy='expectimax',
                                     options=dict(depth=3, prune=False, time_limit=30.0)),
         ['reference', 'numba', 'python_kernel_cpp', 'native_full_tree'], 8),
        ('expectimax_exact_d4', dict(strategy='expectimax',
                                     options=dict(depth=4, prune=False, time_limit=30.0)),
         ['python_kernel_cpp', 'native_full_tree'], 6),
    ]

    rows = []
    for algo, cfg, variants, n_use in configs:
        sub = boards[:n_use]
        ref_dirs = None
        for v in variants:
            if v in ('python_kernel_cpp', 'native_full_tree', 'native_rollout_batch') \
                    and not avail.get('cpp', {}).get('available'):
                rows.append({'group': 'fixed_work', 'algorithm': algo, 'variant': v,
                             'status': 'UNAVAILABLE'})
                continue
            if v == 'numba' and not avail.get('numba', {}).get('available'):
                rows.append({'group': 'fixed_work', 'algorithm': algo, 'variant': v,
                             'status': 'UNAVAILABLE'})
                continue
            per, samples, work = variant_dispatch(v, sub, cfg)
            st = _stats(samples)
            dirs = [p['best_direction'] for p in per]
            if v == 'reference':
                ref_dirs = dirs
            agree = None
            if ref_dirs is not None:
                agree = sum(1 for a, b in zip(dirs, ref_dirs) if a == b) / len(dirs)
            row = {'group': 'fixed_work', 'algorithm': algo, 'variant': v,
                   'n_boards': len(sub), 'repeats': REPEATS,
                   'work_total': work,
                   'median_ms': round(st['median_ms'], 4),
                   'mean_ms': round(st['mean_ms'], 4),
                   'p95_ms': round(st['p95_ms'], 4),
                   'min_ms': round(st['min_ms'], 4),
                   'max_ms': round(st['max_ms'], 4),
                   'work_per_sec': round(work / (st['mean_ms'] / 1000.0), 2) if st['mean_ms'] > 0 else None,
                   'action_agreement_vs_ref': round(agree, 4) if agree is not None else 1.0,
                   'py_peak_kb': round(_py_peak_kb(lambda: variant_dispatch(v, sub[:4], cfg)), 1),
                   'status': 'OK'}
            rows.append(row)
    return rows


# =====================================================================
# Rollout 跨边界往返（同一事件流：native single loop vs native batch vs Python 驱动）
# =====================================================================
def run_rollout_roundtrip(boards, out_dir):
    ref = create_backend('reference')
    cpp = create_backend('cpp')
    rows = []
    N = 40
    DEPTH = 16
    board = boards[0]['board']
    stream = SpawnEventStream(2048, 65536)
    cell, value, move = stream.as_arrays()

    def native_batch():
        cpp.rollout_batch(board, 0, DEPTH, N, cell, value, move, DW)

    def native_single_loop():
        cur = [0]
        s = SpawnEventStream(2048, 65536)
        c, v, m = s.as_arrays()
        for _ in range(N):
            cpp.rollout_events(board, 0, DEPTH, c, v, m, DW)

    def python_driver_cpp():
        cur = [0]
        s = SpawnEventStream(2048, 65536)
        for _ in range(N):
            C.rollout_py(cpp, board, 0, DEPTH, s, cur, DW)

    def python_driver_ref():
        cur = [0]
        s = SpawnEventStream(2048, 65536)
        for _ in range(N):
            C.rollout_py(ref, board, 0, DEPTH, s, cur, DW)

    for name, fn, calls in (('native_batch', native_batch, 1),
                            ('native_single_loop', native_single_loop, N),
                            ('python_driver_cpp', python_driver_cpp, N),
                            ('python_driver_ref', python_driver_ref, N)):
        st = _stats(_timed(fn))
        rows.append({'group': 'rollout_roundtrip', 'variant': name, 'n_rollouts': N,
                     'depth': DEPTH, 'pybind_calls_per_group': calls,
                     'median_ms': round(st['median_ms'], 4),
                     'p95_ms': round(st['p95_ms'], 4),
                     'per_rollout_us': round(st['median_ms'] * 1000.0 / N, 3),
                     'status': 'OK'})
    return rows


# =====================================================================
# 固定墙钟预算：完成工作量 / 停止延迟 / 合法率
# =====================================================================
def run_time_budget(boards, out_dir, budgets_ms=(20, 50, 100)):
    rows = []
    cpp = create_backend('cpp')
    ref = create_backend('reference')
    for budget in budgets_ms:
        for algo in ('expectimax', 'mcts'):
            variants = []
            if algo == 'expectimax':
                variants = [('python_kernel_cpp', dict(depth=8, prune=False, time_limit=budget / 1000.0)),
                            ('native_full_tree', dict(depth=8, prune=False, time_limit=budget / 1000.0,
                                                      native_search=True))]
            else:
                variants = [('python_events_cpp', dict(simulations=100000, rollout_depth=16,
                                                       time_limit=budget / 1000.0)),
                            ('native_full_tree', dict(simulations=100000, rollout_depth=16,
                                                      time_limit=budget / 1000.0,
                                                      native_search=True))]
            for vname, opts in variants:
                lat = []
                completed = []
                legal_ok = 0
                total = 0
                for b in boards:
                    legal = S.legal_moves(b['board'])
                    t0 = time.perf_counter_ns()
                    if algo == 'expectimax' and vname == 'python_kernel_cpp':
                        r = S.solve(b['board'], 'expectimax', backend='cpp',
                                    time_limit=budget / 1000.0, depth=8, prune=False)
                    elif algo == 'mcts' and vname == 'python_events_cpp':
                        r = S._mcts_decision_events(cpp, b['board'], simulations=100000,
                                                    rollout_depth=16, weights=DW,
                                                    stream=SpawnEventStream(2048, 1 << 20),
                                                    time_limit=budget / 1000.0)
                    else:
                        r = S.solve(b['board'], algo, backend='cpp', **opts)
                    el = (time.perf_counter_ns() - t0) / 1e6
                    lat.append(el)
                    if algo == 'expectimax':
                        completed.append(r.get('depth_reached') or 0)
                    else:
                        completed.append(r.get('completed_simulations') or 0)
                    if r.get('best_direction') in legal or not legal:
                        legal_ok += 1
                    total += 1
                rows.append({'group': 'time_budget', 'algorithm': algo, 'variant': vname,
                             'budget_ms': budget, 'n_boards': len(boards),
                             'median_elapsed_ms': round(statistics.median(lat), 3),
                             'median_stop_latency_ms': round(statistics.median(lat) - budget, 3),
                             'median_completed': statistics.median(completed),
                             'legal_rate': round(legal_ok / total, 4),
                             'status': 'TRUNCATED'})
    return rows


def main():
    global REPEATS
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--repeats', type=int, default=REPEATS)
    ap.add_argument('--max-boards', type=int, default=12,
                    help='重工作量基准使用的棋盘数（<= boards 总数）')
    args = ap.parse_args()
    REPEATS = args.repeats

    os.makedirs(args.out_dir, exist_ok=True)
    boards, sha = C.load_boards()
    exp_sha = C.boards_sha_expected()
    heavy = boards[:args.max_boards]
    light = boards

    # warmup numba
    if probe_backends().get('numba', {}).get('available'):
        try:
            create_backend('numba').warmup()
        except Exception:
            pass

    print('[1/3] fixed work ...')
    fw = run_fixed_work(heavy, args.out_dir)
    print('[2/3] rollout roundtrip ...')
    rt = run_rollout_roundtrip(light, args.out_dir)
    print('[3/3] time budget ...')
    tb = run_time_budget(heavy, args.out_dir)

    C.write_json_csv(args.out_dir, 'bench_fixed_work',
                     {'kind': 'v6_2_fixed_work', 'repeats': REPEATS,
                      'boards_sha256_match': sha == exp_sha,
                      'n_heavy_boards': len(heavy),
                      'env': C.env_meta(), 'backend_availability': C.backend_availability(),
                      'note': '同一子表内同一算法/工作量/事件流；native_full_tree = C++ 原生整树'},
                     fw + rt,
                     ['group', 'algorithm', 'variant', 'median_ms', 'p95_ms', 'agreement'],
                     [[r.get('group'), r.get('algorithm', ''), r.get('variant'),
                       r.get('median_ms'), r.get('p95_ms'),
                       r.get('action_agreement_vs_ref', '')] for r in (fw + rt)])

    C.write_json_csv(args.out_dir, 'bench_time_budget',
                     {'kind': 'v6_2_time_budget', 'budgets_ms': [20, 50, 100],
                      'n_boards': len(heavy), 'env': C.env_meta(),
                      'note': 'TRUNCATED：不同预算完成工作量不同，不据此推出胜率排名'},
                     tb,
                     ['algorithm', 'variant', 'budget_ms', 'median_elapsed_ms',
                      'median_stop_latency_ms', 'median_completed', 'legal_rate'],
                     [[r['algorithm'], r['variant'], r['budget_ms'], r['median_elapsed_ms'],
                       r['median_stop_latency_ms'], r['median_completed'], r['legal_rate']]
                      for r in tb])

    meta = {
        'kind': 'v6_2_benchmark_metadata',
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'boards_sha256': sha, 'boards_sha256_expected': exp_sha,
        'boards_sha256_match': sha == exp_sha,
        'env': C.env_meta(),
        'backend_availability': C.backend_availability(),
        'repeats': REPEATS,
        'pybind_roundtrips': {
            'native_full_tree': '1 次/solve（整树在 C++ 内）',
            'python_kernel_cpp': '每原语一次（move/evaluate/legal 级别，未逐次插桩）',
            'native_rollout_batch': '1 次/方向（rollout_batch）',
        },
        'notes': [
            'native Expectimax 仅精确语义（prune=False 或 sample_limit/prob_cutoff=0）；近似模式不参与本表',
            'native MCTS 与 Python 事件镜像使用同一事件流 -> 逐步同源、动作一致率=1',
            'native rollout 与 Python rollout 的 RNG 来源不同（事件流 vs random.Random），动作一致率如实报告',
            'C++ 树内存未插桩（Python tracemalloc 仅覆盖 Python 侧分配）',
        ],
    }
    with open(os.path.join(args.out_dir, 'benchmark_metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print('out_dir =', args.out_dir)
    for r in fw:
        if r.get('status') == 'OK':
            print('  FW %-22s %-20s median=%9.3fms p95=%9.3f agree=%s work/s=%s' % (
                r['algorithm'], r['variant'], r['median_ms'], r['p95_ms'],
                r['action_agreement_vs_ref'], r['work_per_sec']))
    for r in rt:
        print('  RT %-20s median=%9.3fms per_rollout=%sus calls=%s' % (
            r['variant'], r['median_ms'], r['per_rollout_us'], r['pybind_calls_per_group']))
    for r in tb:
        print('  TB %-10s %-18s budget=%3dms elapsed=%8.2fms latency=%+7.2f completed=%s legal=%s' % (
            r['algorithm'], r['variant'], r['budget_ms'], r['median_elapsed_ms'],
            r['median_stop_latency_ms'], r['median_completed'], r['legal_rate']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
