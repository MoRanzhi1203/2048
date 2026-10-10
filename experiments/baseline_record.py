#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase A：记录第五版求解基线（可复现）。

做什么：
    1. 把当前正式模型 rl_model.npz 复制到 experiments/baseline/ 作为隔离基线（不覆盖原文件）；
    2. 记录 SHA256、权重形状、旧模型在固定评估 seed 下的表现；
    3. 记录环境（Python/NumPy 版本）、算法代码版本（git HEAD）、约定与预算语义。
输出：experiments/baseline/baseline.json（可复现、可对比）。
"""

import hashlib
import json
import os
import platform
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
OUT = os.path.join(ROOT, "experiments", "baseline")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import numpy as np                                                 # noqa: E402
import rl_2048 as rl                                               # noqa: E402
import solver_2048 as solver                                       # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def eval_net(net, games=200, seed=20260101):
    """固定 seed 的多局评估：均值/中位数/最高/达成率。"""
    import random
    rng = random.Random(seed)
    scores, tiles = [], []
    hit512 = hit1024 = hit2048 = 0
    for _ in range(games):
        grid = rl._new_game(rng)
        score = 0
        for _ in range(2000):
            if solver.is_game_over(grid):
                break
            d = rl.choose(net, grid, rng, epsilon=0.0)
            if d is None:
                break
            ng, gain, moved = solver.move_grid(grid, d)
            if not moved:
                break
            grid = solver.spawn(ng, rng)
            score += gain
        mt = solver.max_tile(grid)
        scores.append(score)
        tiles.append(mt)
        hit512 += mt >= 512
        hit1024 += mt >= 1024
        hit2048 += mt >= 2048
    scores.sort()
    n = len(scores)
    return {
        "games": n, "seed": seed,
        "avg": round(sum(scores) / n, 2),
        "median": scores[n // 2],
        "best": scores[-1],
        "max_tile": max(tiles),
        "hit512_rate": round(hit512 / n, 4),
        "hit1024_rate": round(hit1024 / n, 4),
        "hit2048_rate": round(hit2048 / n, 4),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(V5, "rl_model.npz")
    dst = os.path.join(OUT, "rl_model_v1.npz")
    rec = {
        "phase": "A",
        "generated_by": "experiments/baseline_record.py",
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
    }
    if os.path.exists(src):
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        rec["official_model_path"] = os.path.relpath(src, ROOT)
        rec["official_model_sha256"] = sha256(src)
        rec["baseline_copy_path"] = os.path.relpath(dst, ROOT)
        rec["baseline_copy_sha256"] = sha256(dst)
        net = rl.load_model(src)
        rec["weight_shapes"] = {k: list(v.shape) for k, v in net.items()}
        rec["baseline_eval"] = eval_net(net, games=200, seed=20260101)
        print("旧模型 SHA256:", rec["official_model_sha256"])
        print("权重形状:", rec["weight_shapes"])
        print("基线评估(200局):", rec["baseline_eval"])
    else:
        rec["official_model_path"] = None
        print("未找到 rl_model.npz（记为缺失）")

    rec["budget_semantics"] = {
        "heuristic": "无预算（单步贪心）",
        "rollout": "次数预算 rollouts × rollout_depth（无墙钟）",
        "expectimax": "时间预算 time_limit（软：迭代加深 + 硬上限 MAX_TIME_LIMIT=2.0s）",
        "mcts": "模拟次数 + 时间预算 双上限",
        "rl": "一次前向，无搜索预算",
    }
    rec["chance_model"] = {
        "spawn": "每个空位等概率 1/E；值 2 概率 0.9，值 4 概率 0.1",
        "order": "玩家先移动(得合并分) -> 再生成新块 -> 进入下一玩家回合",
    }
    with open(os.path.join(OUT, "baseline.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    print("已写出:", os.path.join(OUT, "baseline.json"))


if __name__ == "__main__":
    main()
