#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase F / T02 冒烟：五算法统一入口的合法性、可完成性、资源上界与种子可复现

覆盖（§9）：
    - 五策略都能在统一入口返回合法方向或明确错误；
    - 每策略都能完成一局（有界步数），无异常 / 无非法移动；
    - 单步决策时间有上界（资源上界）；
    - 固定 seed 结果可复现；
    - 非法棋盘返回结构化错误而不是抛异常。

运行：python tests/test_algorithm_benchmark_smoke.py
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "v5_pyqt_2048_solver"))
sys.path.insert(0, os.path.join(ROOT, "experiments"))

import benchmark_algorithms as B                                 # noqa: E402
import solver_2048 as S                                         # noqa: E402

STRATEGIES = list(getattr(S, "STRATEGY_ORDER",
                          ["heuristic", "rollout", "expectimax", "mcts", "rl"]))
BOARD = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 0, 0], [0, 0, 0, 0]]
# 冒烟用的轻量参数（避免测试过慢）
SMOKE_KWARGS = {
    "heuristic": {},
    "rollout": {"rollouts": 4, "rollout_depth": 6},
    "expectimax": {"depth": 2, "time_limit": 0.02},
    "mcts": {"simulations": 40, "time_limit": 0.02, "rollout_depth": 6},
    "rl": {},
}


class AlgorithmSmokeTest(unittest.TestCase):

    def test_all_strategies_legal_or_clear_error(self):
        legal = S.legal_moves(BOARD)
        for strat in STRATEGIES:
            res = S.solve(BOARD, strategy=strat, seed=7, **SMOKE_KWARGS[strat])
            if res.get("error"):
                self.assertEqual(strat, "rl", "%s 不应报错：%s" % (strat, res["error"]))
                print("\n[smoke] %s: 明确错误（模型缺失，符合预期）" % strat)
                continue
            self.assertIn(res["best_direction"], legal, "%s 返回非法方向" % strat)
            self.assertGreaterEqual(res["elapsed_ms"], 0.0)

    def test_each_strategy_can_finish_a_game(self):
        for strat in STRATEGIES:
            row = B.play_game_with(strat, 4242, SMOKE_KWARGS[strat], max_moves=80)
            print("\n[smoke] %-11s moves=%3d score=%5d tile=%4d avg=%.3fms p95=%.3fms err=%s"
                  % (strat, row["moves"], row["score"], row["max_tile"],
                     row["move_avg_ms"], row["move_p95_ms"], row["exceptions"]))
            if strat == "rl" and row["error"]:
                continue
            self.assertEqual(row["exceptions"], 0, "%s 出现异常：%s" % (strat, row["error"]))
            self.assertEqual(row["invalid_moves"], 0, "%s 出现非法移动" % strat)
            self.assertGreaterEqual(row["moves"], 1, "%s 一步都没走" % strat)
            self.assertLess(row["total_decision_ms"], 60000, "%s 决策耗时超上界" % strat)

    def test_seed_reproducible(self):
        # 注意：带“墙钟时间预算”的搜索（其完成深度/模拟次数取决于机器速度）本身不保证
        # 逐位复现；可复现性只对“由次数/深度约束”的配置成立。这里用后者验证。
        deterministic = {
            "rollout": {"rollouts": 6, "rollout_depth": 8},
            "expectimax": {"depth": 2, "time_limit": 30.0},
            "mcts": {"simulations": 40, "time_limit": 30.0, "rollout_depth": 6},
        }
        for strat, kwargs in deterministic.items():
            a = B.play_game_with(strat, 99, kwargs, max_moves=40)
            b = B.play_game_with(strat, 99, kwargs, max_moves=40)
            self.assertEqual((a["score"], a["moves"], a["max_tile"]),
                             (b["score"], b["moves"], b["max_tile"]),
                             "%s 固定 seed 应可复现" % strat)

    def test_invalid_grid_returns_structured_error(self):
        res = S.solve([[1, 2], [3]], strategy="heuristic")
        self.assertIsNotNone(res.get("error"))
        self.assertIsNone(res.get("best_direction"))

    def test_no_legal_move_returns_note(self):
        full = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
        res = S.solve(full, strategy="heuristic")
        self.assertIsNone(res.get("best_direction"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
