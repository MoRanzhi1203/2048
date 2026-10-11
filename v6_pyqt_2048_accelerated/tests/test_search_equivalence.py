#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2/G2 门禁：五策略在四后端下的搜索结果等价，并与冻结 V5 一致。

- heuristic / rollout（固定 seed）/ expectimax(prune=False 固定深度) / mcts（固定 seed+sims）
  在 reference/numpy/numba/cpp 下的 best_direction 必须一致，并与 V5 原实现一致；
- MCTS 回传不变量：root_visits == completed_simulations == backpropagated_simulations。
"""

import os
import sys
import unittest

V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5_DIR = os.path.join(os.path.dirname(V6_DIR), 'v5_pyqt_2048_solver')
for p in (V6_DIR, V5_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import solver_v6 as V6                                          # noqa: E402
import solver_2048 as V5                                       # noqa: E402

BOARDS = [
    [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]],
    [[2, 2, 4, 4], [8, 8, 16, 16], [32, 32, 64, 64], [128, 128, 256, 256]],
    [[0, 2, 0, 4], [2, 0, 4, 0], [0, 8, 0, 16], [8, 0, 16, 0]],
    [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]],
    [[2, 0, 0, 0], [0, 4, 0, 0], [0, 0, 8, 0], [0, 0, 0, 16]],
]
BACKENDS = ('reference', 'numpy', 'numba', 'cpp')


def available_backends():
    st = V6.backend_status()
    return [b for b in BACKENDS if st.get(b, {}).get('available')]


class SearchEquivalenceTest(unittest.TestCase):

    def _all_same(self, strategy, cfg, v5_cfg=None):
        backs = available_backends()
        for b in BOARDS:
            dirs = []
            for be in backs:
                res = V6.solve(b, strategy, backend=be, **cfg)
                dirs.append(res.get('best_direction'))
            self.assertTrue(all(d == dirs[0] for d in dirs),
                            '%s 后端结果不一致：%s (%s)' % (strategy, dirs, b))
            if v5_cfg is not None:
                v5 = V5.solve(b, strategy, **v5_cfg)
                self.assertEqual(dirs[0], v5.get('best_direction'),
                                 '%s 与 V5 不一致：%s vs %s' % (strategy, dirs[0],
                                                              v5.get('best_direction')))

    def test_heuristic(self):
        self._all_same('heuristic', {}, {})

    def test_rollout(self):
        cfg = dict(rollouts=8, rollout_depth=8, seed=2048)
        self._all_same('rollout', cfg, cfg)

    def test_expectimax_noprune(self):
        cfg = dict(depth=2, prune=False, time_limit=30.0, seed=2048)
        self._all_same('expectimax', cfg, cfg)

    def test_mcts(self):
        cfg = dict(simulations=40, rollout_depth=8, time_limit=30.0, seed=7)
        self._all_same('mcts', cfg, cfg)

    def test_mcts_backprop_invariant(self):
        for b in BOARDS:
            res = V6.solve(b, 'mcts', backend='reference', simulations=40,
                           rollout_depth=8, time_limit=30.0, seed=7)
            if res.get('best_direction') is None:
                continue
            self.assertEqual(res['root_visits'], res['completed_simulations'])
            self.assertEqual(res['completed_simulations'],
                             res['backpropagated_simulations'])
            self.assertEqual(res['root_visits'], sum(res['root_move_visits'].values()))

    def test_rl_returns_legal(self):
        res = V6.solve(BOARDS[0], 'rl', backend='reference')
        if res.get('error'):
            self.skipTest('RL 模型不可用：%s' % res['error'])
        legal = V5.legal_moves(BOARDS[0])
        self.assertIn(res['best_direction'], legal)


if __name__ == '__main__':
    unittest.main(verbosity=2)
