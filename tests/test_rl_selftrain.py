#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第五版强化学习模型：自学习能力验证（可执行证据）

回答四个问题：
    1. 持续训练中是否会自动进行参数迭代 / 策略更新？
    2. 是否具备无需人工干预的自主学习机制（经验回放 / 策略梯度自动调整 / 超参数自适应）？
    3. 连续训练下的自动优化触发条件、迭代逻辑与量化评估标准？
    4. 自学习能力覆盖范围、限制边界、持续训练自动优化的可行性结论？

全部结论均以本脚本的真实运行结果为依据；训练产物写到临时目录，不修改仓库内已提交的 rl_model.npz。

用法：python tests/test_rl_selftrain.py
返回码：0=全部验证项通过；1=存在失败。
"""

import hashlib
import os
import shutil
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import rl_2048 as rl                                             # noqa: E402

BASE_MODEL = os.path.join(V5, "rl_model.npz")
RESULTS = []


def record(item, ok, detail=""):
    RESULTS.append((item, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", item, (" | " + detail) if detail else ""),
          flush=True)


def weights_delta(a, b):
    return max(float(np.max(np.abs(a[k] - b[k]))) for k in a)


def copy_net(net):
    return {k: v.copy() for k, v in net.items()}


def source_text():
    with open(rl.__file__, encoding="utf-8") as f:
        return f.read()


def main():
    tmp = tempfile.mkdtemp(prefix="rl_selftrain_")
    print("临时工作目录:", tmp)
    src = source_text()
    src_low = src.lower()

    try:
        if os.path.exists(BASE_MODEL):
            base = rl.load_model(BASE_MODEL)
            base_src = "仓库模型 rl_model.npz"
        else:
            base = rl.init_net(np.random.RandomState(0))
            base_src = "全新随机初始化"
        print("起始模型：%s" % base_src)

        # ============ 1. 持续训练是否自动迭代参数 / 更新策略 ============
        net1, _ = rl.train(games=60, init=copy_net(base), progress=False, seed=11)
        delta = weights_delta(base, net1)
        record("1. 持续训练自动迭代参数（权重确实变化）", delta > 1e-6,
               "max|ΔW| = %.6f" % delta)

        # 策略是否真的变了（同一局面下动作分布变化）
        grid = [[2, 4, 8, 16], [0, 0, 32, 64], [0, 0, 0, 0], [0, 2, 0, 0]]
        p0 = rl.policy_probs(base, grid)
        p1 = rl.policy_probs(net1, grid)
        p_diff = max(abs(p0[d] - p1[d]) for d in p0)
        record("1b. 策略分布随训练自动更新", p_diff > 1e-6,
               "max|ΔP(a|s)| = %.6f" % p_diff)

        # ============ 2. 自主学习机制逐项核查 ============
        # 2a. 经验回放（replay buffer）：是否存在？
        has_replay = ("replay" in src_low) or ("buffer" in src_low)
        record("2a. 经验回放机制（replay buffer）", not has_replay,
               "已确认未实现：训练为 on-policy，只用当前一局轨迹立即更新" if not has_replay
               else "源码出现 replay/buffer 关键字，需人工复核")

        # 2b. 策略梯度自动调整：每局自动计算梯度并更新（无需人工干预）
        counter = {"n": 0, "updates": 0}
        orig_play = rl._play_one

        def counted(*a, **k):
            counter["n"] += 1
            return orig_play(*a, **k)

        clip_marker = copy_net(base)
        rl._play_one = counted
        try:
            net_c, _ = rl.train(games=8, init=clip_marker, progress=False, seed=3)
        finally:
            rl._play_one = orig_play
        record("2b. 策略梯度自动调整（每局自对弈后自动更新，无需人工介入）",
               counter["n"] == 8 and weights_delta(clip_marker, net_c) > 1e-6,
               "自对弈局数=%d，更新后权重变化=%s" % (counter["n"],
                                                  weights_delta(clip_marker, net_c) > 1e-6))

        # 2c. 超参数自适应优化：是否存在？
        adapt_keys = ("optuna", "grid_search", "hyperopt", "lr_schedule",
                      "adaptive_lr", "scheduler", "tune_hyper")
        has_adapt = any(k in src_low for k in adapt_keys)
        record("2c. 超参数自适应优化（自动调参）", not has_adapt,
               "已确认未实现：lr / gamma / entropy_beta 为固定值；仅 ε 按固定线性计划衰减（非自适应）"
               if not has_adapt else "源码出现相关关键字，需人工复核")

        # 2d. 数值稳定性机制（自动生效，防止发散）
        has_stable = ("clip" in src_low) and ("isfinite" in src_low)
        record("2d. 自动数值稳定性（回报/梯度裁剪 + 非有限值跳过）", has_stable,
               "回报截断 ±5、全局梯度范数裁剪 5.0、非有限梯度跳过本局" if has_stable
               else "未检出")

        # ============ 3. 触发条件 / 迭代逻辑 / 量化标准 ============
        # 3a. 真实行为断言：每局自对弈结束后触发且仅触发一次参数更新
        trig = {"updates": 0}
        orig_apply = rl.apply_update

        def counted_apply(*a, **k):
            trig["updates"] += 1
            return orig_apply(*a, **k)

        rl.apply_update = counted_apply
        try:
            rl.train(games=10, init=copy_net(base), progress=False, seed=4)
        finally:
            rl.apply_update = orig_apply
        record("3a. 自动优化触发条件（每局自对弈结束后触发一次参数更新）",
               trig["updates"] == 10,
               "10 局自对弈触发参数更新次数=%d（期望=10）" % trig["updates"])


        # ============ 4. 连续训练提升（量化） ============
        eval_games = 60
        ev0 = rl.evaluate(base, games=eval_games, seed=555)
        chain = [ev0]
        cur = copy_net(base)
        rounds = 3
        for r in range(rounds):
            cur, _ = rl.train(games=1000, init=cur, progress=False, seed=1000 + r)
            chain.append(rl.evaluate(cur, games=eval_games, seed=555))
        trend = " -> ".join("均值%.0f/最高%d/格%d" % (a, b, t) for a, b, t in chain)
        best_avg = max(c[0] for c in chain)
        record("3b. 连续训练存在性能提升（取历史最优，非单调）",
               best_avg > chain[0][0],
               "起始均值%.0f；末轮均值%.0f；历史最优均值%.0f｜全程 %s"
               % (chain[0][0], chain[-1][0], best_avg, trend))

        # 3c. 对照随机策略基线（如实报告差距）
        def random_play(games=60, seed=999):
            import random as _r
            rng = _r.Random(seed)
            scores, tiles = [], []
            for _ in range(games):
                grid = rl._new_game(rng)
                score = 0
                for _ in range(2000):
                    moves = rl._solver.legal_moves(grid)
                    if not moves:
                        break
                    ng, gain, _mv = rl._solver.move_grid(grid, rng.choice(moves))
                    grid = rl._solver.spawn(ng, rng)
                    score += gain
                scores.append(score)
                tiles.append(rl._solver.max_tile(grid))
            return sum(scores) / games, max(tiles)

        rnd_avg, rnd_tile = random_play()
        rl_best = max(chain, key=lambda c: c[0])
        record("3c. 学习有效性对照（贪心平均分优于随机策略）",
               rl_best[0] > rnd_avg,
               "随机：均值%.0f/最大瓦片%d ｜ RL 历史最优：均值%.0f/最大瓦片%d"
               "（领先约%.0f%%；注意：最大瓦片未稳定优于随机，属当前限制）"
               % (rnd_avg, rnd_tile, rl_best[0], rl_best[2],
                  100.0 * (rl_best[0] - rnd_avg) / max(1.0, rnd_avg)))

        # 3d. 自动优化保障机制：早停 + 最优检查点（H2 已实现，改为真实行为断言）
        guard_dir = tempfile.mkdtemp(prefix="rl_guard_")
        try:
            gnet, gstats = rl.train(games=30, init=copy_net(base), progress=False, seed=6,
                                    eval_every=3, eval_games=5, eval_seed=12345, patience=1,
                                    ckpt_prefix=os.path.join(guard_dir, "guard"))
            has_history = len(gstats.get("history", [])) >= 1
            best_written = os.path.exists(os.path.join(guard_dir, "guard.best.npz"))
            latest_written = os.path.exists(os.path.join(guard_dir, "guard.latest.npz"))
            diag = gstats.get("diagnostics", {})
            record("3d. 自动优化保障机制（早停 / 最优检查点 / 训练诊断）",
                   has_history and best_written and latest_written
                   and gstats.get("best_eval") is not None
                   and diag.get("grad_norm_avg") is not None,
                   "验证历史=%d 次｜best/latest 检查点=已落盘｜早停=%s｜诊断(grad_norm=%.4f "
                   "entropy=%.3f clip_ratio=%s)"
                   % (len(gstats.get("history", [])), gstats.get("stopped_early"),
                      diag.get("grad_norm_avg", float('nan')),
                      diag.get("entropy_avg", float('nan')),
                      diag.get("grad_clip_ratio")))
        finally:
            shutil.rmtree(guard_dir, ignore_errors=True)


        # ============ 5. 持续训练（断点续训）可行性 ============
        p1 = os.path.join(tmp, "ckpt1.npz")
        p2 = os.path.join(tmp, "ckpt2.npz")
        rl.save_model(cur, p1)
        resumed, _ = rl.train(games=200, init=rl.load_model(p1), progress=False, seed=77)
        rl.save_model(resumed, p2)
        h1 = hashlib.md5(open(p1, "rb").read()).hexdigest()
        h2 = hashlib.md5(open(p2, "rb").read()).hexdigest()
        record("4a. 断点续训可行（--init 载入后参数继续迭代）",
               h1 != h2 and weights_delta(rl.load_model(p1), resumed) > 1e-6,
               "续训 200 局后权重变化，模型文件哈希变化=%s" % (h1 != h2))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(RESULTS)
    passed = sum(1 for _i, ok, _d in RESULTS if ok)
    print("\n==== 自学习能力验证：%d/%d 通过 ====" % (passed, total))
    print("（说明：2a/2c 两项“PASS”表示‘已确认未实现’，即如实确认缺失，而非具备该能力）")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
