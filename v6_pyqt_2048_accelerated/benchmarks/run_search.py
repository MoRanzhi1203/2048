#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 搜索同工作量对照：相同算法、相同固定工作量、相同棋盘集。

固定工作量（不用时间预算，避免“跑得更久=更深”混淆）：
- heuristic：单步贪心
- rollout：固定 rollouts×depth
- expectimax：prune=False 固定深度（完全枚举）
- mcts：固定 simulations（时间上限放宽，保证跑满）

记录：每次求解耗时、节点计数、与 reference 的动作一致率、评估值偏差、节点/秒。
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bench_common as C                                       # noqa: E402
import solver_v6 as V6                                          # noqa: E402

ALGOS = {
    'heuristic': dict(),
    'rollout': dict(rollouts=20, rollout_depth=16, seed=2048),
    'expectimax_noprune_d3': dict(depth=3, prune=False, time_limit=30.0, seed=2048),
    'mcts_sims60': dict(simulations=60, rollout_depth=12, time_limit=30.0, seed=2048),
}
BACKENDS = ('reference', 'numpy', 'numba', 'cpp')


def run_one(boards, backend, strategy, cfg):
    times = []
    dirs = []
    nodes = []
    evals = []
    for b in boards:
        board = b['board']
        res = V6.solve(board, strategy, backend=backend, **cfg)
        times.append(res.get('elapsed_ms', 0.0))
        dirs.append(res.get('best_direction'))
        nodes.append(res.get('nodes', 0))
        ev = res.get('evaluations') or {}
        d = res.get('best_direction')
        evals.append(ev.get(d) if d else None)
    return times, dirs, nodes, evals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(C.BENCH_DIR, 'reports'))
    ap.add_argument('--backends', default='reference,numpy,numba,cpp')
    args = ap.parse_args()

    boards, sha = C.load_boards()
    exp_sha = C.boards_sha_expected()
    run_dir, ts = C.ts_run_dir(args.out_dir, 'search')
    avail = C.backend_availability()

    results = []
    csv_rows = []
    for algo, cfg in ALGOS.items():
        ref = None
        for backend in [b.strip() for b in args.backends.split(',') if b.strip()]:
            if not avail.get(backend, {}).get('available'):
                results.append({'algorithm': algo, 'backend': backend,
                                'status': 'UNAVAILABLE'})
                continue
            times, dirs, nodes, evals = run_one(boards, backend, algo.split('_')[0]
                                                if algo.split('_')[0] in
                                                ('heuristic', 'rollout', 'expectimax', 'mcts')
                                                else algo, cfg)
            if backend == 'reference':
                ref = (times, dirs, nodes, evals)
            agree = None
            eval_dev = None
            if ref is not None and backend != 'reference':
                n = len(dirs)
                agree = sum(1 for a, b in zip(dirs, ref[1]) if a == b) / n
                devs = [abs(a - b) for a, b in zip(evals, ref[3])
                        if a is not None and b is not None]
                eval_dev = (statistics.fmean(devs) if devs else None)
            med = statistics.median(times)
            med_nodes = statistics.median(nodes)
            node_per_ms = (med_nodes / med) if med > 0 else None
            row = {
                'algorithm': algo, 'backend': backend,
                'median_ms_per_solve': round(med, 4),
                'mean_ms_per_solve': round(statistics.fmean(times), 4),
                'median_nodes': med_nodes,
                'nodes_per_ms': round(node_per_ms, 2) if node_per_ms else None,
                'action_agreement_vs_ref': round(agree, 4) if agree is not None else 1.0,
                'mean_eval_dev_vs_ref': round(eval_dev, 4) if eval_dev is not None else 0.0,
                'n_boards': len(boards),
            }
            if ref is not None:
                row['speedup_vs_ref'] = round(statistics.median(ref[0]) / med, 3) if med > 0 else None
            results.append(row)
            csv_rows.append([algo, backend, row['median_ms_per_solve'],
                             row.get('speedup_vs_ref'), row['median_nodes'],
                             row['action_agreement_vs_ref']])

    meta = {
        'kind': 'search_same_workload',
        'run_id': ts,
        'boards_count': len(boards),
        'boards_sha256_match': exp_sha == sha,
        'fixed_workload': {k: v for k, v in ALGOS.items()},
        'backend_availability': avail,
        'note': '固定工作量（非固定墙钟）：prune=False / 固定 rollouts / 固定 simulations',
        'env': C.env_meta(),
        'results': results,
    }
    C.write_json_csv(run_dir, 'search', meta, results,
                     ['algorithm', 'backend', 'median_ms', 'speedup', 'median_nodes',
                      'action_agreement'], csv_rows)

    print('run_dir=', run_dir)
    for r in results:
        if r.get('status') == 'UNAVAILABLE':
            print('  %-24s %-9s UNAVAILABLE' % (r['algorithm'], r['backend']))
        else:
            print('  %-24s %-9s median=%8.3fms speedup=%s nodes=%s agree=%s' % (
                r['algorithm'], r['backend'], r['median_ms_per_solve'],
                r.get('speedup_vs_ref'), r['median_nodes'], r['action_agreement_vs_ref']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
