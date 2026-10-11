#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase F2：消融实验（Expectimax 剪枝 / MCTS 加宽与 UCT / 启发式特征 / Rollout 续玩策略）

统一协议：同一批 seed、同一局数、环境与求解器随机流分离；每变体报告均值/中位数/标准差/
达成率/95% CI 与（相对基线的）同 seed 配对差值 CI。默认 smoke 规模，正式结论需加大 --games。

用法：
    python experiments/ablation.py --suite expectimax --games 10
    python experiments/ablation.py --suite mcts --games 10
    python experiments/ablation.py --suite heuristic --games 20
    python experiments/ablation.py --suite rollout --games 10
    python experiments/ablation.py --suite all --games 10
"""

import argparse
import datetime
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "experiments"))

import benchmark_algorithms as B                                 # noqa: E402
import solver_2048 as S                                        # noqa: E402


# ---------------------------------------------------------------------
# 变体定义
# ---------------------------------------------------------------------
def suite_expectimax():
    # 深度/时间对所有变体保持一致（对照公平）；depth=2 + 0.1s 保证 smoke 规模可完成。
    base = {"depth": 2, "time_limit": 0.1}
    return "expectimax", [
        ("none(精确)", dict(base, prune=False)),
        ("TT", dict(base, use_tt=True, prob_cutoff=0.0, sample_limit=0)),
        ("TT+sample", dict(base, use_tt=True, prob_cutoff=0.0, sample_limit=4)),
        ("TT+cutoff", dict(base, use_tt=True, prob_cutoff=0.02, sample_limit=0)),
        ("full", dict(base, use_tt=True, prob_cutoff=0.02, sample_limit=4)),
    ]


def suite_mcts():
    # 统一 0.05s 时间预算（smoke 可承受）；次数/宽度为自变量。
    # 说明：H1 已修复“宽度上限触发时丢弃回传”的错误，并新增渐进加宽 K(N)。
    base = {"time_limit": 0.05, "rollout_depth": 8}
    return "mcts", [
        ("sims=50", dict(base, simulations=50, max_chance_width=8, c=1.4)),
        ("sims=200", dict(base, simulations=200, max_chance_width=8, c=1.4)),
        ("sims=800", dict(base, simulations=800, max_chance_width=8, c=1.4)),
        ("width=2", dict(base, simulations=200, max_chance_width=2, c=1.4)),
        ("width=4", dict(base, simulations=200, max_chance_width=4, c=1.4)),
        ("c=0.5", dict(base, simulations=200, max_chance_width=8, c=0.5)),
        ("c=3.0", dict(base, simulations=200, max_chance_width=8, c=3.0)),
        ("pw cpw=1.0 a=0.5", dict(base, simulations=200, max_chance_width=8,
                                  progressive_widening=True, cpw=1.0, alpha=0.5)),
        ("pw cpw=0.5 a=0.5", dict(base, simulations=200, max_chance_width=8,
                                  progressive_widening=True, cpw=0.5, alpha=0.5)),
    ]


def suite_heuristic():
    w = dict(S.DEFAULT_WEIGHTS)
    def wm(**kw):
        d = dict(w)
        d.update(kw)
        return d
    return "heuristic", [
        ("baseline", {}),
        ("-empty", {"weights": wm(empty=0.0)}),
        ("-monotonicity", {"weights": wm(monotonicity=0.0)}),
        ("-smoothness", {"weights": wm(smoothness=0.0)}),
        ("-merge", {"weights": wm(merge=0.0)}),
        ("-corner", {"weights": wm(corner=0.0)}),
        ("+snake(1.0)", {"weights": wm(snake=1.0)}),
        ("+danger(1.0)", {"weights": wm(danger=1.0)}),
        ("+snake+danger", {"weights": wm(snake=1.0, danger=1.0)}),
    ]


def suite_rollout():
    # smoke 规模：biased 策略每步要做多次启发式评估，rollout 次数/深度取小值以便在可接受时间内完成。
    base = {"rollouts": 6, "rollout_depth": 8}
    return "rollout", [
        ("random", dict(base, rollout_policy="random")),
        ("biased eps=0.3", dict(base, rollout_policy="heuristic_biased", rollout_epsilon=0.3)),
        ("biased eps=0.1", dict(base, rollout_policy="heuristic_biased", rollout_epsilon=0.1)),
        ("biased eps=0.0", dict(base, rollout_policy="heuristic_biased", rollout_epsilon=0.0)),
        ("rollouts=4", dict(base, rollout_policy="random", rollouts=4)),
        ("rollouts=24", dict(base, rollout_policy="random", rollouts=24)),
        ("depth=6", dict(base, rollout_policy="random", rollout_depth=6)),
        ("depth=12", dict(base, rollout_policy="random", rollout_depth=12)),
    ]


SUITES = {"expectimax": suite_expectimax, "mcts": suite_mcts,
          "heuristic": suite_heuristic, "rollout": suite_rollout}


# ---------------------------------------------------------------------
def run_variant(strategy, name, kwargs, seeds, max_moves=B.MAX_MOVES):
    rows = []
    for sd in seeds:
        rows.append(B.play_game_with(strategy, sd, kwargs, max_moves=max_moves,
                                     preset=name, budget="ablation"))
    return rows


def main():
    ap = argparse.ArgumentParser(description="消融实验")
    ap.add_argument("--suite", choices=list(SUITES) + ["all"], default="all")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--seed-base", type=int, default=2000)
    ap.add_argument("--out-dir", default=B.RESULTS_DIR,
                    help="结果目录（V5.1 用 experiments/v5_1/results）")
    ap.add_argument("--max-moves", type=int, default=B.MAX_MOVES,
                    help="每局最大步数上限（有界 horizon，用于控制实验耗时）")
    args = ap.parse_args()

    suites = list(SUITES) if args.suite == "all" else [args.suite]
    seeds = [args.seed_base + i for i in range(args.games)]
    out = {"meta": B.env_meta(), "games": args.games, "seeds": seeds,
           "max_moves": args.max_moves, "suites": {}}

    for suite in suites:
        strategy, variants = SUITES[suite]()
        print("\n=== 消融：%s（%d 局/变体，seed=%d..%d） ==="
              % (suite, args.games, seeds[0], seeds[-1]))
        all_rows = []
        for name, kwargs in variants:
            t0 = time.time()
            rows = run_variant(strategy, name, kwargs, seeds, args.max_moves)
            all_rows.extend(rows)
            st = B.summarize(rows)[strategy]
            print("  %-16s avg=%7.1f median=%6.1f std=%6.1f ci95=%-16s tile=%4d h512=%5.1f%% "
                  "avgMs=%6.3f p95=%7.3f (%.0fs)"
                  % (name, st["avg"], st["median"], st["std"], str(st["ci95_avg"]),
                     st["max_tile"], 100 * st["hit512_rate"], st["move_avg_ms"],
                     st["move_p95_ms"], time.time() - t0), flush=True)
            print("                  总耗时=%.1fs 超时=%d 非法=%d 异常=%d"
                  % (st["total_decision_s"], st["timeouts"], st["invalid_moves"],
                     st["exceptions"]))
            out["suites"].setdefault(suite, {})[name] = {
                "kwargs": {k: (v if not isinstance(v, dict) else "weights") for k, v in kwargs.items()},
                "summary": st, "rows": rows}

        # 相对第一个变体的配对差值
        base_name = variants[0][0]
        by_variant = {}
        for r in all_rows:
            by_variant.setdefault(r["preset"], {})[r["seed"]] = r["score"]
        print("  -- 配对差值（相对 %s）--" % base_name)
        for name, _kw in variants[1:]:
            d = B.paired_diff_ci(by_variant[name], by_variant[base_name])
            if d:
                print("    %-16s mean=%+8.1f ci95=%s n=%d"
                      % (name, d["mean_diff"], d["ci95"], d["n"]))

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.join(args.out_dir, "ablation_%s_%dg_%s" % (args.suite, args.games, stamp))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n消融原始数据：%s.json" % base)


if __name__ == "__main__":
    main()
