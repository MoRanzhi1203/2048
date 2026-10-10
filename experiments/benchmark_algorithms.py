#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase F1：五算法公平基准（同 seed 家族、独立环境/求解器随机流、可复现）

协议要点：
    - 同一批 seed 下，五算法从相同生成规则独立开局；
    - **环境随机数与求解器内部随机数分离**（env_rng 负责生成新块，solver seed 只影响搜索）；
    - 两套预算：`default`（各策略默认强度）与 `equal_time`（等单步时间预算）；
    - 每局记录 strategy / preset / seed / final score / max tile / moves /
      hit_512/1024/2048 / total decision time / per-move avg/median/p95 /
      timeouts / invalid moves / exceptions；
    - 汇总：均值、中位数、标准差、达成率、bootstrap 95% CI；同 seed 配对差值 CI；
    - 输出 CSV + JSON 原始数据，不触碰真实存档（game_history/）。

用法：
    python experiments/benchmark_algorithms.py --games 10                     # smoke
    python experiments/benchmark_algorithms.py --games 100 --budget default     # 正式
    python experiments/benchmark_algorithms.py --games 10 --strategies heuristic,rollout
"""

import argparse
import datetime
import json
import os
import platform
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import numpy as np                                                # noqa: E402
import solver_2048 as S                                           # noqa: E402

RESULTS_DIR = os.path.join(ROOT, "experiments", "results")
DEFAULT_STRATEGIES = ["heuristic", "rollout", "expectimax", "mcts", "rl"]
MAX_MOVES = 2000


# ---------------------------------------------------------------------
# 预算配置
# ---------------------------------------------------------------------
def budget_kwargs(strategy, budget, speed="normal"):
    """返回该策略在本实验下的求解参数。"""
    if budget == "default":
        return S.build_config(strategy, speed)
    if budget == "equal_time":
        # 等单步时间预算：搜索类统一 50ms；rollout 用固定次数+深度（时间量级可比）；
        # heuristic / rl 无搜索预算（常数时间），如实标注。
        if strategy == "expectimax":
            return {"depth": 4, "time_limit": 0.05}
        if strategy == "mcts":
            return {"simulations": 100000, "time_limit": 0.05, "rollout_depth": 8}
        if strategy == "rollout":
            return {"rollouts": 8, "rollout_depth": 8}
        return {}
    raise ValueError("未知预算：%s" % budget)


# ---------------------------------------------------------------------
# 统计助手
# ---------------------------------------------------------------------
def bootstrap_ci(values, n=2000, alpha=0.05, seed=20260101):
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    m = len(values)
    means = []
    for _ in range(n):
        means.append(sum(values[rng.randrange(m)] for _ in range(m)) / m)
    means.sort()
    lo = means[int((alpha / 2) * n)]
    hi = means[int((1 - alpha / 2) * n) - 1]
    return (round(lo, 2), round(hi, 2))


def paired_diff_ci(a_by_seed, b_by_seed, n=2000, alpha=0.05, seed=7):
    """同 seed 配对差值 (A-B) 的均值与 bootstrap CI。"""
    keys = sorted(set(a_by_seed) & set(b_by_seed))
    if not keys:
        return None
    diffs = [a_by_seed[k] - b_by_seed[k] for k in keys]
    rng = random.Random(seed)
    m = len(diffs)
    means = sorted(sum(diffs[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return {"n": m, "mean_diff": round(sum(diffs) / m, 2),
            "ci95": [means[int((alpha / 2) * n)], means[int((1 - alpha / 2) * n) - 1]]}


# ---------------------------------------------------------------------
# 单局对战
# ---------------------------------------------------------------------
def play_game(strategy, seed, budget, speed="normal", max_moves=MAX_MOVES):
    """跑一局；环境随机数与求解器随机数分离。返回该局的指标 dict。"""
    return play_game_with(strategy, seed, budget_kwargs(strategy, budget, speed),
                          max_moves=max_moves,
                          preset=speed if budget == "default" else "equal_time",
                          budget=budget)


def play_game_with(strategy, seed, solve_kwargs, max_moves=MAX_MOVES,
                   preset="custom", budget="custom"):
    """用给定求解参数跑一局（供基准与消融共用）。"""
    env_rng = random.Random(seed)                 # 环境：生成新块
    solver_seed = (seed * 2 + 1) & 0x7FFFFFFF     # 求解器内部随机数（与 env 分离）
    kwargs = dict(solve_kwargs)

    grid = [[0] * 4 for _ in range(4)]
    for _ in range(2):
        grid = S.spawn(grid, env_rng)

    score = 0
    moves = 0
    times = []
    timeouts = 0
    invalid = 0
    exceptions = 0
    error_msg = None

    for _ in range(max_moves):
        if S.is_game_over(grid):
            break
        t0 = time.perf_counter()
        try:
            res = S.solve(grid, strategy=strategy, seed=solver_seed + moves, **kwargs)
        except Exception as exc:                  # noqa: BLE001
            exceptions += 1
            error_msg = str(exc)
            break
        times.append((time.perf_counter() - t0) * 1000.0)
        if res.get("error"):
            error_msg = res["error"]
            exceptions += 1
            break
        if res.get("timed_out"):
            timeouts += 1
        d = res.get("best_direction")
        if d is None:
            invalid += 1
            break
        new_grid, gain, moved = S.move_grid(grid, d)
        if not moved:
            invalid += 1
            break
        grid = S.spawn(new_grid, env_rng)
        score += gain
        moves += 1

    times_sorted = sorted(times)
    def pct(p):
        if not times_sorted:
            return 0.0
        idx = min(len(times_sorted) - 1, int(p * len(times_sorted)))
        return round(times_sorted[idx], 3)

    tile = S.max_tile(grid)
    return {
        "strategy": strategy, "preset": preset,
        "budget": budget, "seed": seed, "score": score, "max_tile": tile,
        "moves": moves,
        "hit_512": int(tile >= 512), "hit_1024": int(tile >= 1024),
        "hit_2048": int(tile >= 2048),
        "total_decision_ms": round(sum(times), 2),
        "move_avg_ms": round(sum(times) / len(times), 3) if times else 0.0,
        "move_median_ms": pct(0.5), "move_p95_ms": pct(0.95),
        "timeouts": timeouts, "invalid_moves": invalid, "exceptions": exceptions,
        "error": error_msg,
    }


# ---------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------
def summarize(rows):
    """按策略汇总：均值/中位数/标准差/达成率/95% CI。"""
    out = {}
    for strat in sorted({r["strategy"] for r in rows}):
        rs = [r for r in rows if r["strategy"] == strat]
        scores = [r["score"] for r in rs]
        n = len(scores)
        out[strat] = {
            "games": n,
            "avg": round(sum(scores) / n, 2),
            "median": statistics.median(scores),
            "std": round(statistics.pstdev(scores), 2) if n > 1 else 0.0,
            "best": max(scores),
            "ci95_avg": bootstrap_ci(scores),
            "max_tile": max(r["max_tile"] for r in rs),
            "hit512_rate": round(sum(r["hit_512"] for r in rs) / n, 4),
            "hit1024_rate": round(sum(r["hit_1024"] for r in rs) / n, 4),
            "move_avg_ms": round(sum(r["move_avg_ms"] for r in rs) / n, 3),
            "move_p95_ms": round(max(r["move_p95_ms"] for r in rs), 3),
            "total_decision_s": round(sum(r["total_decision_ms"] for r in rs) / 1000.0, 2),
            "timeouts": sum(r["timeouts"] for r in rs),
            "invalid_moves": sum(r["invalid_moves"] for r in rs),
            "exceptions": sum(r["exceptions"] for r in rs),
            "moves_avg": round(sum(r["moves"] for r in rs) / n, 1),
        }
    return out


def run_benchmark(strategies, games, budget, speed="normal", seeds=None,
                  progress=True):
    seeds = seeds or [1000 + i for i in range(games)]
    rows = []
    for strat in strategies:
        for sd in seeds:
            row = play_game(strat, sd, budget, speed)
            rows.append(row)
            if progress:
                print("  [%s] seed=%d score=%d tile=%d moves=%d avg=%.2fms"
                      % (strat, sd, row["score"], row["max_tile"], row["moves"],
                         row["move_avg_ms"]), flush=True)
    return rows


def env_meta(model_path=None):
    meta = {
        "generated_by": "experiments/benchmark_algorithms.py",
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "solver_module_sha256": S.__file__,
    }
    mp = model_path or os.path.join(V5, "rl_model.npz")
    if os.path.exists(mp):
        import hashlib
        h = hashlib.sha256(open(mp, "rb").read()).hexdigest()
        meta["rl_model"] = os.path.basename(mp)
        meta["rl_model_sha256"] = h
    return meta


def main():
    ap = argparse.ArgumentParser(description="五算法公平基准")
    ap.add_argument("--games", type=int, default=10, help="每个策略的局数（smoke=10，正式建议>=100）")
    ap.add_argument("--budget", choices=["default", "equal_time"], default="default")
    ap.add_argument("--speed", choices=["fast", "normal", "strong"], default="normal")
    ap.add_argument("--strategies", default=",".join(DEFAULT_STRATEGIES))
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    strategies = [s for s in args.strategies.split(",") if s]
    print("基准开始：策略=%s 局数/策略=%d 预算=%s 强度=%s"
          % (strategies, args.games, args.budget, args.speed))
    t0 = time.time()
    rows = run_benchmark(strategies, args.games, args.budget, args.speed)
    summary = summarize(rows)
    meta = env_meta()
    meta.update({"budget": args.budget, "speed": args.speed, "games_per_strategy": args.games,
                 "elapsed_s": round(time.time() - t0, 1)})

    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = ("_" + args.tag) if args.tag else ""
    base = os.path.join(RESULTS_DIR, "benchmark_%s_%dg%s_%s" % (args.budget, args.games, tag, stamp))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
    with open(base + ".csv", "w", encoding="utf-8") as f:
        cols = list(rows[0].keys())
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r[c]) for c in cols) + "\n")

    print("\n=== 汇总（%s, %d 局/策略） ===" % (args.budget, args.games))
    print("  %-11s %8s %8s %7s %9s %7s %8s %7s %9s %6s"
          % ("strategy", "avg", "median", "std", "ci95", "tile", "h512%", "avgMs", "p95Ms", "err"))
    for strat, st in summary.items():
        print("  %-11s %8.1f %8.1f %7.1f %9s %7d %7.1f%% %7.3f %9.3f %6d"
              % (strat, st["avg"], st["median"], st["std"], str(st["ci95_avg"]),
                 st["max_tile"], 100 * st["hit512_rate"], st["move_avg_ms"],
                 st["move_p95_ms"], st["exceptions"]))

    # 配对差值（以第一个策略为基准）
    if len(strategies) > 1:
        base_s = strategies[0]
        by_seed = {}
        for r in rows:
            by_seed.setdefault(r["strategy"], {})[r["seed"]] = r["score"]
        print("\n  配对差值（相对 %s，同 seed）:" % base_s)
        for strat in strategies[1:]:
            d = paired_diff_ci(by_seed[strat], by_seed[base_s])
            if d:
                print("    %-11s mean=%+8.1f  ci95=%s  n=%d"
                      % (strat, d["mean_diff"], d["ci95"], d["n"]))

    print("\n原始数据：%s.json / %s.csv" % (base, base))
    print("耗时 %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()

