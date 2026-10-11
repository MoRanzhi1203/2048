#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 内核微基准（不玩整局）：相同棋盘集、相同接口、相同批量频率。

对照项：encode/decode 隐含在 move 中；move(4 方向) / legal_moves / evaluate /
公共事件流 rollout(10/20/40) / 批量 move。冷启动（JIT/构建）与热态分开报告。
所有后端共用同一驱动与同一棋盘集（boards.jsonl，sha256 校验）。
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bench_common as C                                       # noqa: E402
from solver_backends.api import BoardOverflowError              # noqa: E402
from solver_backends.events import SpawnEventStream             # noqa: E402

BACKENDS = ('reference', 'numpy', 'numba', 'cpp')
WEIGHTS = None            # None = 各后端统一使用 V5 默认权重（口径一致）


def _safe_move(be, board, d, counter):
    try:
        return be.move(board, d)
    except BoardOverflowError:
        counter['overflow'] += 1
        return board, 0, False


def build_kernels(be, boards, stream, depth):
    """返回 {kernel_name: (fn, units_per_iteration)}。"""
    over = {'overflow': 0}

    def move_all_dirs():
        for b in boards:
            for d in ('up', 'down', 'left', 'right'):
                _safe_move(be, b['board'], d, over)

    def legal():
        for b in boards:
            try:
                be.legal_moves(b['board'])
            except BoardOverflowError:
                over['overflow'] += 1

    def evaluate():
        for b in boards:
            try:
                be.evaluate(b['board'], None)
            except BoardOverflowError:
                over['overflow'] += 1

    def batch_move():
        flats = [b['board'] for b in boards]
        if be.name == 'cpp':
            try:
                be.batch_move(flats, 'left')
                return
            except BoardOverflowError:
                over['overflow'] += 1
                return
        for b in flats:
            _safe_move(be, b, 'left', over)

    def rollout(d):
        def fn():
            for b in boards:
                cursor = [0]
                try:
                    C.rollout_py(be, b['board'], 0, d, stream, cursor, WEIGHTS)
                except BoardOverflowError:
                    over['overflow'] += 1
        return fn

    return {
        'move_all_dirs': (move_all_dirs, len(boards) * 4),
        'legal_moves': (legal, len(boards)),
        'evaluate': (evaluate, len(boards)),
        'batch_move_left': (batch_move, len(boards)),
        'rollout_py_d10': (rollout(10), len(boards)),
        'rollout_py_d20': (rollout(20), len(boards)),
        'rollout_py_d40': (rollout(40), len(boards)),
    }, over


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(C.BENCH_DIR, 'reports'))
    ap.add_argument('--warmup', type=int, default=3)
    ap.add_argument('--repeat', type=int, default=30)
    ap.add_argument('--backends', default='reference,numpy,numba,cpp')
    ap.add_argument('--seed', type=int, default=20482048)
    args = ap.parse_args()

    boards, sha = C.load_boards()
    exp_sha = C.boards_sha_expected()
    stream = SpawnEventStream(args.seed, 200000)

    run_dir, ts = C.ts_run_dir(args.out_dir, 'micro')
    rows = []
    csv_rows = []
    cold = {}
    avail = C.backend_availability()

    for name in args.backends.split(','):
        name = name.strip()
        if name not in BACKENDS:
            continue
        if not avail.get(name, {}).get('available'):
            rows.append({'backend': name, 'status': 'UNAVAILABLE',
                         'reason': avail.get(name, {}).get('reason')})
            continue

        t0 = C.time.perf_counter_ns()
        be = C.create_backend(name)
        # 冷启动：触发首次编译/首次表构建
        if hasattr(be, 'warmup'):
            be.warmup()
        else:
            _safe_move(be, boards[0]['board'], 'left', {'overflow': 0})
            be.evaluate(boards[0]['board'], None)
        cold[name] = round((C.time.perf_counter_ns() - t0) / 1e6, 3)

        kernels, over = build_kernels(be, boards, stream, 10)
        for kname, (fn, units) in kernels.items():
            samples = C.timing(fn, args.warmup, args.repeat)
            st = C.stats(samples)
            per_unit = st['median_ns'] / max(1, units)
            rows.append({
                'backend': name, 'kernel': kname, 'units_per_iteration': units,
                'median_ns_per_iteration': st['median_ns'],
                'median_ns_per_unit': per_unit,
                'stats': st, 'overflow_skips': over['overflow'],
            })
            for i, s in enumerate(samples):
                csv_rows.append([name, kname, i, s])

    meta = {
        'kind': 'micro',
        'run_id': ts,
        'boards_count': len(boards),
        'boards_sha256_expected': exp_sha,
        'boards_sha256_actual': sha,
        'boards_sha256_match': exp_sha == sha,
        'warmup': args.warmup, 'repeat': args.repeat, 'seed': args.seed,
        'cold_init_ms': cold,
        'backend_availability': avail,
        'timing_boundary': 'warm-up 与测量分离；gc 在测量期间关闭；冷启动单列 cold_init_ms',
        'note': 'reference/numpy/numba/cpp 共用同一驱动与棋盘集；rollout 使用公共事件流',
        'env': C.env_meta(),
        'results': rows,
    }
    json_path = C.write_json_csv(run_dir, 'micro', meta, rows,
                                 ['backend', 'kernel', 'iteration', 'duration_ns'], csv_rows)

    print('run_dir=', run_dir)
    for r in rows:
        if 'kernel' in r:
            print('  %-9s %-16s median=%.2f us/iter  %.4f us/unit' % (
                r['backend'], r['kernel'], r['median_ns_per_iteration'] / 1000.0,
                r['median_ns_per_unit'] / 1000.0))
        else:
            print('  %-9s %s (%s)' % (r['backend'], r.get('status'), r.get('reason')))
    print('cold_init_ms=', cold)
    print('RESULT=' + ('OK' if meta['boards_sha256_match'] else 'FAIL:boards_sha'))
    return 0 if meta['boards_sha256_match'] else 1


if __name__ == '__main__':
    sys.exit(main())
