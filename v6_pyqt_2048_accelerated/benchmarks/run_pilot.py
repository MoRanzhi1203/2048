#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 同墙钟预算的小样本对局基准（smoke 2 / pilot 5 / final-lite 10）。

固定“环境”（初始棋盘、随机生成、规则）由 V5 冻结实现提供，只有**求解后端**变化；
交错运行顺序，记录自然结束(FINISHED)/截断(TRUNCATED)/单步预算触达(TIME_BUDGET_REACHED)
与异常，小样本仅作工程回归，不作显著性结论。
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bench_common as C                                       # noqa: E402
import solver_v6 as V6                                          # noqa: E402
import solver_2048 as ENV                                       # noqa: E402  (环境规则)

MODES = {
    'smoke': dict(games=2, max_moves=200, time_budget_ms=20),
    'pilot': dict(games=5, max_moves=400, time_budget_ms=30),
    'final-lite': dict(games=10, max_moves=400, time_budget_ms=30),
}
DEFAULT_STRATEGIES = 'heuristic,rollout,expectimax,mcts,rl'
DEFAULT_BACKENDS = 'reference,cpp'


def play_game(backend, strategy, base_cfg, seed, max_moves, time_budget_ms):
    rng = random.Random(seed)
    grid = [[0] * 4 for _ in range(4)]
    for _ in range(2):
        grid = ENV.spawn(grid, rng)
    score = 0
    steps = 0
    budget_hits = 0
    errors = 0
    step_ms = []
    status = 'TRUNCATED'
    for _ in range(max_moves):
        if ENV.is_game_over(grid):
            status = 'FINISHED'
            break
        cfg = dict(base_cfg)
        cfg.pop('strategy', None)                  # strategy 作为位置参数传入
        cfg['time_limit'] = time_budget_ms / 1000.0
        t0 = time.perf_counter()
        try:
            res = V6.solve(grid, strategy, backend=backend, **cfg)
        except Exception:                                   # noqa: BLE001
            errors += 1
            status = 'ERROR'
            break
        step_ms.append((time.perf_counter() - t0) * 1000.0)
        if res.get('error'):
            errors += 1
            status = 'ERROR'
            break
        if res.get('timed_out'):
            budget_hits += 1
        d = res.get('best_direction')
        if not d:
            status = 'FINISHED'
            break
        ng, gain, moved = ENV.move_grid(grid, d)
        if not moved:
            status = 'FINISHED'
            break
        grid = ENV.spawn(ng, rng)
        score += gain
        steps += 1
    return {
        'score': score, 'steps': steps, 'max_tile': ENV.max_tile(grid),
        'status': status, 'time_budget_reached': budget_hits, 'errors': errors,
        'avg_step_ms': round(statistics.fmean(step_ms), 3) if step_ms else 0.0,
        'p95_step_ms': round(sorted(step_ms)[min(len(step_ms) - 1, int(0.95 * (len(step_ms) - 1)))], 3) if step_ms else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='smoke', choices=sorted(MODES))
    ap.add_argument('--out-dir', default=os.path.join(C.BENCH_DIR, 'reports'))
    ap.add_argument('--strategies', default=DEFAULT_STRATEGIES)
    ap.add_argument('--backends', default=DEFAULT_BACKENDS)
    ap.add_argument('--games', type=int, default=None)
    ap.add_argument('--max-moves', type=int, default=None)
    ap.add_argument('--time-budget-ms', type=float, default=None)
    ap.add_argument('--seed', type=int, default=20482048)
    args = ap.parse_args()

    m = dict(MODES[args.mode])
    if args.games:
        m['games'] = args.games
    if args.max_moves:
        m['max_moves'] = args.max_moves
    if args.time_budget_ms:
        m['time_budget_ms'] = args.time_budget_ms

    avail = C.backend_availability()
    strategies = [s for s in args.strategies.split(',') if s.strip()]
    backends = [b for b in args.backends.split(',') if b.strip()]

    run_dir, ts = C.ts_run_dir(args.out_dir, 'pilot_%s' % args.mode)
    rows = []
    csv_rows = []
    # 交错运行：按 (game_index, strategy, backend) 轮转，避免后端间的系统时序偏差
    for strategy in strategies:
        base_cfg = dict(V6.build_config(strategy, 'normal'))
        base_cfg.pop('time_limit', None)
        for g in range(m['games']):
            seed = args.seed + 1000 * g
            for backend in backends:
                if not avail.get(backend, {}).get('available'):
                    rows.append({'strategy': strategy, 'backend': backend,
                                 'status': 'UNAVAILABLE'})
                    continue
                r = play_game(backend, strategy, base_cfg, seed, m['max_moves'],
                              m['time_budget_ms'])
                r.update({'strategy': strategy, 'backend': backend, 'game': g, 'seed': seed,
                          'max_moves': m['max_moves'], 'time_budget_ms': m['time_budget_ms']})
                rows.append(r)
                csv_rows.append([strategy, backend, g, seed, r['score'], r['max_tile'],
                                 r['steps'], r['status'], r['time_budget_reached'],
                                 r['avg_step_ms']])

    # 聚合
    summary = {}
    for strategy in strategies:
        for backend in backends:
            rs = [r for r in rows if r.get('strategy') == strategy
                  and r.get('backend') == backend and 'score' in r]
            if not rs:
                continue
            summary['%s|%s' % (strategy, backend)] = {
                'games': len(rs),
                'mean_score': round(statistics.fmean([r['score'] for r in rs]), 1),
                'median_score': statistics.median([r['score'] for r in rs]),
                'max_tile': max(r['max_tile'] for r in rs),
                'finished': sum(1 for r in rs if r['status'] == 'FINISHED'),
                'truncated': sum(1 for r in rs if r['status'] == 'TRUNCATED'),
                'errors': sum(r['errors'] for r in rs),
                'mean_avg_step_ms': round(statistics.fmean([r['avg_step_ms'] for r in rs]), 3),
                'total_budget_hits': sum(r['time_budget_reached'] for r in rs),
            }

    meta = {
        'kind': 'pilot_games', 'mode': args.mode, 'run_id': ts,
        'params': m, 'strategies': strategies, 'backends': backends,
        'backend_availability': avail,
        'note': '环境规则用冻结 V5；仅求解后端变化。小样本仅作工程回归，不作显著性结论。',
        'env': C.env_meta(),
        'summary': summary,
        'rows': rows,
    }
    C.write_json_csv(run_dir, 'pilot', meta, rows,
                     ['strategy', 'backend', 'game', 'seed', 'score', 'max_tile',
                      'steps', 'status', 'budget_hits', 'avg_step_ms'], csv_rows)
    print('run_dir=', run_dir)
    for key, s in summary.items():
        print('  %-22s games=%d mean=%s median=%s maxTile=%s FIN=%d TRUNC=%d err=%d step=%.2fms' % (
            key, s['games'], s['mean_score'], s['median_score'], s['max_tile'],
            s['finished'], s['truncated'], s['errors'], s['mean_avg_step_ms']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
