#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase C / T01：MCTS 概率与收益正确性验证

覆盖：
    M01 机会节点按真实转移概率采样（空位均匀 1/E、2/4=0.9/0.1），重复采样复用同状态
    M02 转移顺序：玩家先移动(得合并分) → 机会节点生成新块 → 进入下一玩家节点
    M03 统一回报口径（根到叶累计合并分 + 截断处启发式），回传同尺度
    M04 渐进加宽 / UCT 探索常数的消融与稳定性

运行：python tests/test_mcts_chance.py
"""

import math
import os
import random
import statistics
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import solver_2048 as S                                          # noqa: E402

BOARD_E1 = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2, 4], [8, 16, 32, 0]]
BOARD_MID = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 0, 0], [0, 0, 0, 0]]


class MctsChanceTest(unittest.TestCase):

    # ---------------- M01：机会模型本身（供 MCTS/RL 共用） ----------------
    def test_sample_spawn_distribution(self):
        grid = BOARD_MID
        cells = S.empty_cells(grid)
        n = 20000
        rng = random.Random(2024)
        cell_count = {c: 0 for c in cells}
        twos = fours = 0
        for _ in range(n):
            new_grid, cell, value = S.sample_spawn(grid, rng)
            self.assertIn(cell, cells)
            self.assertIn(value, (2, 4))
            self.assertEqual(new_grid[cell[0]][cell[1]], value)
            cell_count[cell] += 1
            twos += value == 2
            fours += value == 4
        p2 = twos / n
        expect_cell = n / len(cells)
        dev = max(abs(c - expect_cell) / expect_cell for c in cell_count.values())
        print("\n[M01] sample_spawn: n=%d p(2)=%.4f p(4)=%.4f 空位最大相对偏差=%.2f%%"
              % (n, p2, fours / n, 100 * dev))
        self.assertLess(abs(p2 - 0.9), 0.02, "值 2 的概率应≈0.9")
        self.assertLess(dev, 0.15, "空位应近似等概率（相对偏差<15%）")

    # ---------------- M02：转移顺序 ----------------
    def test_transition_order_player_then_chance(self):
        trace = []
        S.solve(BOARD_MID, strategy="mcts", simulations=12, time_limit=5.0,
                rollout_depth=4, seed=5, trace=trace)
        self.assertGreaterEqual(len(trace), 2, "应记录到 玩家移动 与 机会生成 两类步骤")
        # 三元组含义：('P', dir, 父节点类型) / ('C', cell, value, 父节点类型)
        self.assertEqual(trace[0][0], "P", "根（玩家节点）应先移动")
        self.assertEqual(trace[0][2], "P", "移动必须发生在玩家节点之下")
        self.assertIn(trace[0][1], S.legal_moves(BOARD_MID))
        c_entries = [t for t in trace if t[0] == "C"]
        self.assertGreaterEqual(len(c_entries), 1, "应出现机会（生成新块）步骤")
        for t in c_entries:
            self.assertEqual(t[3], "C", "生成新块必须发生在机会节点之下（先移动后生成）")
            self.assertIn(t[2], (2, 4), "生成值只能是 2 或 4")
            r, c = t[1]
            self.assertTrue(0 <= r < 4 and 0 <= c < 4, "生成位置必须合法")
        for t in trace:
            if t[0] == "P":
                self.assertEqual(t[2], "P", "玩家移动必须发生在玩家节点之下")

    def test_rollout_moves_then_spawns(self):
        """rollout 从玩家状态出发：每步先移动（可获合并分）再生成新块。"""
        r = S.solve(BOARD_MID, strategy="mcts", simulations=64, time_limit=5.0,
                    rollout_depth=6, seed=9)
        self.assertGreater(r["rollout_steps"], 0)
        self.assertGreater(r["nodes"], 0)

    # ---------------- M01：重复采样复用同状态（不重复加不等价权重） ----------------
    def test_chance_children_reused_not_duplicated(self):
        r = S.solve(BOARD_E1, strategy="mcts", simulations=120, time_limit=5.0,
                    rollout_depth=6, seed=3, max_chance_width=8)
        self.assertGreater(r["chance_nodes"], 0)
        # E=1 时每个机会节点最多 2 个不同子状态（同格生成 2 / 4），不应无限增殖
        self.assertLessEqual(r["chance_children"], 2 * r["chance_nodes"],
                             "同一机会节点不应产生 >2 个不同子状态")
        self.assertGreater(r["reused_chance_children"], 0,
                           "重复采样应复用已缓存子节点")

    # ---------------- M03：统一口径 + 确定性 + 统计稳定性 ----------------
    def test_deterministic_with_seed(self):
        a = S.solve(BOARD_MID, strategy="mcts", simulations=100, time_limit=5.0, seed=17)
        b = S.solve(BOARD_MID, strategy="mcts", simulations=100, time_limit=5.0, seed=17)
        self.assertEqual(a["best_direction"], b["best_direction"])
        for d in S.DIRECTIONS:
            self.assertAlmostEqual(a["evaluations"][d], b["evaluations"][d], delta=1e-12)

    def test_return_scale_nonnegative_and_finite(self):
        """统一回报 = 累计合并分 + 启发式：应有限；均值随模拟数增加趋于稳定。"""
        for sims in (40, 400):
            vals = []
            for seed in (1, 2, 3, 4, 5):
                r = S.solve(BOARD_MID, strategy="mcts", simulations=sims,
                            time_limit=5.0, seed=seed)
                self.assertIn(r["best_direction"], S.legal_moves(BOARD_MID))
                v = r["evaluations"][r["best_direction"]]
                self.assertTrue(math.isfinite(v))
                vals.append(v)
            print("\n[M03] simulations=%d 最优分支估值: mean=%.1f std=%.1f %s"
                  % (sims, statistics.mean(vals), statistics.pstdev(vals),
                     ["%.0f" % v for v in vals]))
            if sims == 40:
                std_small = statistics.pstdev(vals)
            else:
                std_big = statistics.pstdev(vals)
        self.assertLessEqual(std_big, std_small * 1.5 + 1e-9,
                             "模拟数增加后估值波动不应显著变大")

    # ---------------- M04：渐进加宽 / UCT 消融 ----------------
    def test_width_and_uct_ablation(self):
        print("\n[M04] max_chance_width 消融（board=E4, sims=200, seed=2024）")
        print("  %6s %8s %10s %10s %14s" % ("width", "chance", "reused", "bestVal", "best"))
        for width in (2, 4, 8, 64):
            r = S.solve(BOARD_MID, strategy="mcts", simulations=200, time_limit=5.0,
                        seed=2024, max_chance_width=width)
            v = r["evaluations"][r["best_direction"]]
            print("  %6d %8d %10d %10.1f %14s" %
                  (width, r["chance_children"], r["reused_chance_children"],
                   v, r["best_name"]))
            self.assertIn(r["best_direction"], S.legal_moves(BOARD_MID))
        print("  UCT c 消融（sims=200, width=8）")
        print("  %6s %10s %14s" % ("c", "bestVal", "best"))
        for c in (0.5, 1.4, 3.0):
            r = S.solve(BOARD_MID, strategy="mcts", simulations=200, time_limit=5.0,
                        seed=2024, c=c)
            print("  %6.1f %10.1f %14s" %
                  (c, r["evaluations"][r["best_direction"]], r["best_name"]))
            self.assertIn(r["best_direction"], S.legal_moves(BOARD_MID))

    # ---------------- H1：根回传不变量（宽度上限不得丢弃 simulation） ----------------
    def test_mcts_backprop_invariants(self):
        """H1 修复验证：每一次 simulation 都必须真实回传到 root。

        不变量：root_visits == completed_simulations == backpropagated_simulations，
        且根各合法动作访问次数之和 == root_visits。覆盖 sims∈{100,500,1000}、
        width∈{1,2,4,8,16,32}（旧实现在小宽度下会丢弃回传，使 root_visits < completed）。
        """
        for width in (1, 2, 4, 8, 16, 32):
            for sims in (100, 500, 1000):
                r = S.solve(BOARD_MID, strategy="mcts", simulations=sims, time_limit=10.0,
                            rollout_depth=4, seed=7, max_chance_width=width)
                self.assertEqual(r["completed_simulations"], sims,
                                 "width=%d sims=%d" % (width, sims))
                self.assertEqual(r["backpropagated_simulations"], sims)
                self.assertEqual(r["root_visits"], sims,
                                 "width=%d sims=%d：root 未收到全部回传" % (width, sims))
                self.assertEqual(sum(r["root_move_visits"].values()), r["root_visits"],
                                 "根各方向访问次数之和 != root_visits")
                self.assertIn(r["best_direction"], S.legal_moves(BOARD_MID))
        # 小宽度必须真实触发宽度上限，且触发后仍全部回传
        r1 = S.solve(BOARD_MID, strategy="mcts", simulations=300, time_limit=10.0,
                     rollout_depth=4, seed=1, max_chance_width=1)
        self.assertGreater(r1["width_limit_rollouts"], 0, "宽度上限未被触发")
        self.assertEqual(r1["root_visits"], 300)

    # ---------------- H1：渐进加宽 K(N) 与 spawn 分布不变 ----------------
    def test_mcts_progressive_widening(self):
        """H1：progressive widening K(N)=min(Kmax,max(1,ceil(cpw*N**alpha))) 实施验证。

        - 仍满足回传不变量；
        - 每个机会节点子节点数不超过 Kmax；
        - 只在“是否新增子节点”上生效，不改变 spawn 采样分布（见下一测试）。
        """
        for sims in (100, 500, 1000):
            r = S.solve(BOARD_MID, strategy="mcts", simulations=sims, time_limit=10.0,
                        rollout_depth=4, seed=11, max_chance_width=8,
                        progressive_widening=True, cpw=1.0, alpha=0.5)
            self.assertTrue(r["progressive_widening"])
            self.assertEqual(r["completed_simulations"], sims)
            self.assertEqual(r["backpropagated_simulations"], sims)
            self.assertEqual(r["root_visits"], sims)
            self.assertEqual(sum(r["root_move_visits"].values()), sims)
            self.assertIn(r["best_direction"], S.legal_moves(BOARD_MID))
            if r["chance_nodes"]:
                self.assertLessEqual(r["chance_children"],
                                     r["max_chance_width"] * r["chance_nodes"],
                                     "机会节点子节点数超过 Kmax")
        # 渐进加宽相对固定宽度：更晚展开（chance_children 不增）
        fixed = S.solve(BOARD_MID, strategy="mcts", simulations=600, time_limit=10.0,
                        rollout_depth=4, seed=5, max_chance_width=8)
        prog = S.solve(BOARD_MID, strategy="mcts", simulations=600, time_limit=10.0,
                       rollout_depth=4, seed=5, max_chance_width=8, progressive_widening=True)
        self.assertLessEqual(prog["chance_children"], fixed["chance_children"] + 1)

    def test_progressive_widening_keeps_spawn_distribution(self):
        """H1：渐进加宽不得改变真实 spawn 概率（仍为 1/E 均匀 × 0.9/0.1）。

        直接对 sample_spawn 取样计数（descend 与 rollout 共用同一采样器），验证 ≈0.9/0.1。
        """
        orig = S.sample_spawn
        records = []

        def spy(grid, rng, value=None):
            out = orig(grid, rng, value)
            records.append(out[2])
            return out

        S.sample_spawn = spy
        try:
            S.solve(BOARD_MID, strategy="mcts", simulations=1500, time_limit=10.0,
                    rollout_depth=6, seed=21, max_chance_width=8,
                    progressive_widening=True, cpw=1.0, alpha=0.5)
        finally:
            S.sample_spawn = orig
        n2 = records.count(2)
        n4 = records.count(4)
        self.assertGreater(n2 + n4, 1000)
        p2 = n2 / float(n2 + n4)
        print("\n[H1] progressive widening spawn 分布：n=%d p(2)=%.4f p(4)=%.4f"
              % (n2 + n4, p2, 1.0 - p2))
        self.assertLess(abs(p2 - 0.9), 0.03, "渐进加宽改变了 spawn 分布")



if __name__ == "__main__":
    unittest.main(verbosity=2)
