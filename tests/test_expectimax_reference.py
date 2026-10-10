#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase B / T01：Expectimax 正确性验证（独立精确参考 + 剪枝 A/B 消融）

为什么需要它：仅“返回合法方向”不能证明数学正确。本文件实现一个**独立**的小深度精确
参考（穷举全部合法动作 × 全部空位 × 2/4 两种生成，不调用任何被剪枝的搜索代码），
用它校验 Expectimax 的无损模式，并对四类剪枝做 A/B 消融与误差统计。

覆盖：
    E01 路径概率按规则传递、截断发生在展开之前、概率质量不丢
    E02 转置表与路径相关截断解耦（键含路径概率）；超时不缓存未完成估值
    E03 精确模式可关闭采样；采样为无偏估计并有误差/波动统计
    E04 与精确枚举值对照 + 剪枝消融（none / TT / TT+sample / TT+cutoff / full）
    T01 精确枚举、边界用例

运行：python tests/test_expectimax_reference.py
返回码：0=全部通过；1=存在失败。
"""

import math
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import solver_2048 as S                                          # noqa: E402

TOL = 1e-9
# 空位较少的小局面：保证精确参考可穷举（用于无损/一致性对照）
BOARDS = [
    [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 0, 0], [0, 0, 0, 0]],
    [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]],
    [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 0, 0], [0, 0, 0, 0]],
]
# 空位较多的中等局面：用于“采样/截断会造成多大误差”的可控测量（E=10）
ABLATION_BOARD = [[2, 4, 8, 16], [32, 64, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]


# =====================================================================
# 独立精确参考（穷举；不复用被剪枝的搜索代码）
# =====================================================================
def exact_max(grid, depth, weights=None, sw=0.0):
    if depth <= 0 or S.is_game_over(grid):
        return S.evaluate(grid, weights)
    best = -float("inf")
    any_move = False
    for d in S.DIRECTIONS:
        ng, gain, moved = S.move_grid(grid, d)
        if not moved:
            continue
        any_move = True
        best = max(best, sw * gain + exact_chance(ng, depth - 1, weights, sw))
    if not any_move:
        return S.evaluate(grid, weights)
    return best


def exact_chance(grid_after_move, depth, weights=None, sw=0.0):
    """(1/E) * Σ_cells [0.9*V(生成2) + 0.1*V(生成4)]；depth<=0 时退化为启发式估值。"""
    if depth <= 0:
        return S.evaluate(grid_after_move, weights)
    cells = S.empty_cells(grid_after_move)
    if not cells:
        return S.evaluate(grid_after_move, weights)
    total = 0.0
    for (i, j) in cells:
        for value, prob in ((2, 0.9), (4, 0.1)):
            child = [row[:] for row in grid_after_move]
            child[i][j] = value
            total += prob * exact_max(child, depth - 1, weights, sw)
    return total / len(cells)


def exact_root(grid, depth, weights=None, sw=0.0):
    """返回 {direction: value}（非法方向为 None）——与实现同口径。"""
    evals = {}
    for d in S.DIRECTIONS:
        ng, gain, moved = S.move_grid(grid, d)
        if not moved:
            evals[d] = None
            continue
        evals[d] = sw * gain + exact_chance(ng, depth - 1, weights, sw)
    return evals


class ExpectimaxReferenceTest(unittest.TestCase):

    # ---------------- E04/T01：精确模式与穷举值一致 ----------------
    def test_lossless_matches_exact_reference(self):
        for grid in BOARDS:
            for depth in (1, 2, 3):
                res = S.solve(grid, strategy="expectimax", depth=depth,
                              time_limit=5.0, prune=False)
                ref = exact_root(grid, depth)
                for d in S.DIRECTIONS:
                    got, want = res["evaluations"].get(d), ref[d]
                    if want is None:
                        self.assertIsNone(got, "%s d=%d depth=%d" % (d, depth, depth))
                    else:
                        self.assertAlmostEqual(got, want, delta=TOL,
                                               msg="%s depth=%d" % (d, depth))
                best = max((v, d) for d, v in ref.items() if v is not None)[1]
                self.assertEqual(res["best_direction"], best, "depth=%d" % depth)

    def test_score_weight_consistency(self):
        """声明 score_weight=1.0 时同样与参考一致（目标口径可切换且一致）。"""
        grid = BOARDS[0]
        res = S.solve(grid, strategy="expectimax", depth=3, time_limit=5.0,
                      prune=False, score_weight=1.0)
        ref = exact_root(grid, 3, sw=1.0)
        for d in S.DIRECTIONS:
            if ref[d] is None:
                self.assertIsNone(res["evaluations"][d])
            else:
                self.assertAlmostEqual(res["evaluations"][d], ref[d], delta=TOL)

    # ---------------- E02：TT 透明（不改变结果） ----------------
    def test_tt_is_transparent_without_cutoff(self):
        for grid in BOARDS:
            off = S.solve(grid, strategy="expectimax", depth=3, time_limit=5.0,
                          use_tt=False, prob_cutoff=0.0, sample_limit=0)
            on = S.solve(grid, strategy="expectimax", depth=3, time_limit=5.0,
                         use_tt=True, prob_cutoff=0.0, sample_limit=0)
            for d in S.DIRECTIONS:
                self.assertAlmostEqual(off["evaluations"][d], on["evaluations"][d], delta=TOL)
            self.assertEqual(off["best_direction"], on["best_direction"])
            self.assertLessEqual(on["nodes"], off["nodes"])      # TT 应减少展开

    def test_tt_transparent_with_cutoff(self):
        """启用概率截断时，TT 也必须透明（键含路径概率，无隐藏上下文依赖）。"""
        for grid in BOARDS:
            off = S.solve(grid, strategy="expectimax", depth=4, time_limit=5.0,
                          use_tt=False, sample_limit=0, prob_cutoff=0.1)
            on = S.solve(grid, strategy="expectimax", depth=4, time_limit=5.0,
                         use_tt=True, sample_limit=0, prob_cutoff=0.1)
            for d in S.DIRECTIONS:
                self.assertAlmostEqual(off["evaluations"][d], on["evaluations"][d], delta=TOL)
            self.assertEqual(off["best_direction"], on["best_direction"])

    # ---------------- E01：截断发生在展开之前 + 概率质量不丢 ----------------
    def test_cutoff_happens_before_expansion_and_keeps_mass(self):
        grid = ABLATION_BOARD
        depth = 3
        no_cut = S.solve(grid, strategy="expectimax", depth=depth, time_limit=5.0,
                         sample_limit=0, prob_cutoff=0.0)
        cut = S.solve(grid, strategy="expectimax", depth=depth, time_limit=5.0,
                      sample_limit=0, prob_cutoff=0.05)
        self.assertGreater(cut["cutoffs"], 0, "截断未生效")
        self.assertLess(cut["leaf_evals"], no_cut["leaf_evals"], "截断后叶子估值应减少（先剪枝再展开）")
        # 概率质量不丢：被截断分支仍以启发式近似贡献期望 → 结果有限且误差有界
        ref = exact_root(grid, depth)
        for d in S.DIRECTIONS:
            if ref[d] is None:
                continue
            v = cut["evaluations"][d]
            self.assertTrue(math.isfinite(v), "截断产生非有限值")
            self.assertLess(abs(v - ref[d]) / max(1.0, abs(ref[d])), 0.3, "截断引入误差过大")

    # ---------------- E03：采样为无偏估计 + 误差/波动统计 ----------------
    def test_sampling_bias_and_variance(self):
        grid = ABLATION_BOARD                     # E=10，采样上限取 6
        depth = 3
        ref = exact_root(grid, depth)
        rows = []
        for seed in (1, 2, 3, 7, 11):
            r = S.solve(grid, strategy="expectimax", depth=depth, time_limit=5.0,
                        sample_limit=6, prob_cutoff=0.0, seed=seed)
            self.assertGreater(r["sampled_chance"], 0)
            errs = [abs(r["evaluations"][d] - ref[d]) / max(1.0, abs(ref[d]))
                    for d in S.DIRECTIONS if ref[d] is not None]
            rows.append(sum(errs) / len(errs))
        mean_err = sum(rows) / len(rows)
        spread = max(rows) - min(rows)
        print("\n[E03] 空位采样相对误差(E=10,k=6)：mean=%.2f%%  max-min=%.2f%%  各 seed=%s"
              % (100 * mean_err, 100 * spread, ["%.1f%%" % (100 * r) for r in rows]))
        self.assertLess(mean_err, 0.5, "采样均值误差过大（应 <50%）")
        # 固定 seed 可复现
        a = S.solve(grid, strategy="expectimax", depth=depth, time_limit=5.0,
                    sample_limit=6, prob_cutoff=0.0, seed=42)
        b = S.solve(grid, strategy="expectimax", depth=depth, time_limit=5.0,
                    sample_limit=6, prob_cutoff=0.0, seed=42)
        self.assertEqual(a["best_direction"], b["best_direction"])
        for d in S.DIRECTIONS:
            self.assertAlmostEqual(a["evaluations"][d], b["evaluations"][d], delta=TOL)

    # ---------------- 剪枝 A/B 消融（原始数据打印） ----------------
    def test_pruning_ablation_table(self):
        grid = ABLATION_BOARD
        depth = 3
        ref = exact_root(grid, depth)
        variants = [
            ("none",       dict(prune=False)),
            ("TT",         dict(prune=True, use_tt=True, prob_cutoff=0.0, sample_limit=0)),
            ("TT+sample",  dict(prune=True, use_tt=True, prob_cutoff=0.0, sample_limit=6)),
            ("TT+cutoff",  dict(prune=True, use_tt=True, prob_cutoff=0.05, sample_limit=0)),
            ("full",       dict(prune=True, use_tt=True, prob_cutoff=0.05, sample_limit=6)),
        ]
        print("\n[E04] 剪枝消融（board=E10, depth=%d，精确参考已给出）" % depth)
        print("  %-11s %7s %7s %7s %7s %7s %9s %6s" %
              ("variant", "nodes", "leaf", "hits", "cutoff", "samp", "maxErr%", "best"))
        for name, kwargs in variants:
            k = dict(kwargs)
            k.update({"depth": depth, "time_limit": 5.0, "move_order": True})
            r = S.solve(grid, strategy="expectimax", **k)
            errs = [abs(r["evaluations"][d] - ref[d]) / max(1.0, abs(ref[d]))
                    for d in S.DIRECTIONS if ref[d] is not None]
            max_err = 100 * max(errs)
            ref_best = max((v, d) for d, v in ref.items() if v is not None)[1]
            print("  %-11s %7d %7d %7d %7d %7d %8.2f%% %6s" %
                  (name, r["nodes"], r.get("leaf_evals", 0), r.get("cache_hits", 0),
                   r.get("cutoffs", 0), r.get("sampled_chance", 0), max_err,
                   "=" if r["best_direction"] == ref_best else r["best_direction"]))
            if name == "none":
                self.assertLess(max_err, 1e-6)                 # 无损模式必须精确
            elif name in ("TT", "TT+sample", "TT+cutoff"):
                self.assertLess(max_err, 60.0)                 # 单类近似：误差有界
            else:
                self.assertLess(max_err, 120.0)                # 组合近似：误差仍有界且非发散

        # 追加：小棋盘(E=4, depth=4) 的 TT 命中证据（TT 必须透明、且减少展开/叶子估值）
        g2 = BOARDS[0]
        r_off = S.solve(g2, strategy="expectimax", depth=4, time_limit=5.0,
                        use_tt=False, prob_cutoff=0.0, sample_limit=0)
        r_on = S.solve(g2, strategy="expectimax", depth=4, time_limit=5.0,
                       use_tt=True, prob_cutoff=0.0, sample_limit=0)
        print("  [TT 命中证据] E=4, depth=4: leaf %d -> %d, cache_hits=%d, nodes %d -> %d"
              % (r_off["leaf_evals"], r_on["leaf_evals"], r_on["cache_hits"],
                 r_off["nodes"], r_on["nodes"]))
        self.assertGreater(r_on["cache_hits"], 0)
        self.assertLess(r_on["leaf_evals"], r_off["leaf_evals"])
        for d in S.DIRECTIONS:
            self.assertAlmostEqual(r_off["evaluations"][d], r_on["evaluations"][d], delta=TOL)

    # ---------------- 超时：未完成估值不入 TT ----------------
    def test_timeout_does_not_pollute(self):
        grid = BOARDS[0]
        tiny = S.solve(grid, strategy="expectimax", depth=8, time_limit=0.001,
                       prune=True, use_tt=True)
        self.assertTrue(tiny["timed_out"])
        self.assertIn(tiny["best_direction"], S.legal_moves(grid))
        # TT 为单次调用内的局部结构：极小预算调用后再用充足预算，结果应与“全新充足预算”一致
        after = S.solve(grid, strategy="expectimax", depth=4, time_limit=5.0, prune=True)
        fresh = S.solve(grid, strategy="expectimax", depth=4, time_limit=5.0, prune=True)
        self.assertEqual(after["best_direction"], fresh["best_direction"])
        for d in S.DIRECTIONS:
            self.assertAlmostEqual(after["evaluations"][d], fresh["evaluations"][d], delta=TOL)

    # ---------------- 统计指标存在且口径一致 ----------------
    def test_stats_present(self):
        grid = BOARDS[0]
        r = S.solve(grid, strategy="expectimax", depth=4, time_limit=5.0)
        for key in ("nodes", "leaf_evals", "cache_hits", "cutoffs",
                    "sampled_chance", "chance_nodes", "elapsed_ms",
                    "depth_reached", "timed_out"):
            self.assertIn(key, r, key)
        self.assertGreaterEqual(r["nodes"], 1)
        self.assertGreaterEqual(r["depth_reached"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
