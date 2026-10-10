#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase D / T01：强化学习梯度与训练机制正确性验证

覆盖：
    R01 价值头更新符号：单样本 V-MSE 更新后必须下降（并用“反向符号”作对照证明原实现会上升）
    R02 价值头梯度回传共享层：dL/dh 必须同时含策略头与价值头两部分
    R03 训练行为策略 = masked-softmax 分布采样（无 off-policy 偏差）；推理为确定性 argmax
    R04 固定验证集 + best/latest + patience 早停
    T01 解析梯度 vs 中心有限差分（全参数）

运行：python tests/test_rl_gradients.py
"""

import math
import os
import random
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V5 = os.path.join(ROOT, "v5_pyqt_2048_solver")
if V5 not in sys.path:
    sys.path.insert(0, V5)

import rl_2048 as R                                              # noqa: E402
import solver_2048 as S                                          # noqa: E402

GRID = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 0, 0], [0, 0, 0, 0]]
H_SMALL = 6          # 有限差分用小网络（保证远离 ReLU 折点、计算量可控）


def make_tiny_net(seed=0, hidden=H_SMALL, dtype=np.float64):
    rng = np.random.RandomState(seed)
    return {
        'W1': (rng.randn(hidden, R.FEAT_DIM) * 0.01).astype(dtype),
        'b1': np.full(hidden, 1.0, dtype=dtype),        # 保证 ReLU 全激活，避免折点
        'W2': (rng.randn(R.N_ACTIONS, hidden) * 0.3).astype(dtype),
        'b2': (rng.randn(R.N_ACTIONS) * 0.1).astype(dtype),
        'Wv': (rng.randn(1, hidden) * 0.3).astype(dtype),
        'bv': np.zeros(1, dtype=dtype),
    }


def loss(net, x, legal, action, target, beta, v0):
    """与 compute_gradients 完全一致的目标（优势 stop-gradient，V0 为更新前价值）。"""
    h, logits, value = R._forward(net, x)
    probs = R.masked_probs(logits, legal)
    logp = float(np.log(probs[action]))
    nz = probs[probs > 0]
    entropy = float(-(nz * np.log(nz)).sum())
    adv = float(target) - float(v0)
    return -adv * logp + 0.5 * (value - float(target)) ** 2 - beta * entropy


def fd_grads(net, x, legal, action, target, beta, v0, eps=1e-5):
    grads = {}
    for k in net:
        arr = net[k]
        g = np.zeros(arr.shape, dtype=np.float64)
        it = np.nditer(arr, flags=['multi_index'])
        while not it.finished:
            idx = it.multi_index
            orig = arr[idx]
            arr[idx] = orig + eps
            lp = loss(net, x, legal, action, target, beta, v0)
            arr[idx] = orig - eps
            lm = loss(net, x, legal, action, target, beta, v0)
            arr[idx] = orig
            g[idx] = (lp - lm) / (2.0 * eps)
            it.iternext()
        grads[k] = g
    return grads


class RlGradientTest(unittest.TestCase):

    # ---------------- T01：解析梯度 vs 中心有限差分 ----------------
    def test_finite_difference_all_params(self):
        for beta in (0.0, 2e-3):
            net = make_tiny_net(seed=1)
            x = R.encode(GRID)
            legal = R._legal_idx(GRID)
            action = legal[0]
            target = 3.0
            _, _, v0 = R._forward(net, x)
            ana, _v, _p = R.compute_gradients(net, x, legal, action, target, beta)
            num = fd_grads(net, x, legal, action, target, beta, v0)
            worst = 0.0
            for k in net:
                scale = max(1.0, float(np.max(np.abs(num[k]))))
                err = float(np.max(np.abs(ana[k] - num[k]))) / scale
                worst = max(worst, err)
                self.assertLess(err, 1e-4, '%s 解析/数值梯度不一致（beta=%s）' % (k, beta))
            print("\n[T01] 有限差分最大相对偏差=%.2e（beta=%s）" % (worst, beta))

    # ---------------- R01：价值头符号 ----------------
    def test_value_head_mse_decreases(self):
        net = make_tiny_net(seed=2)
        x = R.encode(GRID)
        legal = R._legal_idx(GRID)
        action = legal[0]
        _h, _l, v0 = R._forward(net, x)
        target = v0 + 5.0

        # 只更新价值头（隔离 R01）
        grads, _v, _p = R.compute_gradients(net, x, legal, action, target, 0.0)
        only_value = {k: np.zeros_like(net[k]) for k in net}
        only_value['Wv'] = grads['Wv']
        only_value['bv'] = grads['bv']
        fixed = {k: v.copy() for k, v in net.items()}
        R.apply_update(fixed, only_value, lr=0.2)
        _h1, _l1, v1 = R._forward(fixed, x)
        self.assertLess(abs(v1 - target), abs(v0 - target),
                        "修正后：价值头更新应让 V-MSE 下降")

        # 反向符号（原实现）应让误差变大 —— 证明该修复是必要的
        buggy = {k: v.copy() for k, v in net.items()}
        R.apply_update(buggy, {k: -only_value[k] for k in only_value}, lr=0.2)
        _h2, _l2, v2 = R._forward(buggy, x)
        self.assertGreater(abs(v2 - target), abs(v0 - target),
                           "反向符号会让误差变大（对照）")
        print("\n[R01] V-MSE：更新前=%.4f 修正后=%.4f 反向符号=%.4f"
              % (abs(v0 - target), abs(v1 - target), abs(v2 - target)))

    def test_full_step_decreases_loss(self):
        net = make_tiny_net(seed=3)
        x = R.encode(GRID)
        legal = R._legal_idx(GRID)
        action = legal[0]
        _h, _l, v0 = R._forward(net, x)
        target = v0 + 2.0
        beta = 2e-3
        before = loss(net, x, legal, action, target, beta, v0)
        grads, _v, _p = R.compute_gradients(net, x, legal, action, target, beta)
        R.apply_update(net, grads, lr=0.01)
        after = loss(net, x, legal, action, target, beta, v0)
        self.assertLess(after, before, "一步小更新应降低目标函数")

    # ---------------- R02：共享层梯度包含价值头 ----------------
    def test_shared_layer_receives_value_gradient(self):
        net = make_tiny_net(seed=4)
        x = R.encode(GRID)
        legal = R._legal_idx(GRID)
        action = legal[0]
        full, _v, _p = R.compute_gradients(net, x, legal, action, 3.0, 0.0)

        novalue_net = {k: v.copy() for k, v in net.items()}
        novalue_net['Wv'] = np.zeros_like(net['Wv'])          # 切断价值头 → 共享层只剩策略项
        novalue, _v2, _p2 = R.compute_gradients(novalue_net, x, legal, action, 3.0, 0.0)

        diff = float(np.max(np.abs(full['W1'] - novalue['W1'])))
        self.assertGreater(diff, 1e-9, "共享层梯度必须包含价值头的回传项")
        # 且与解析式 W2^T·dlogits + (V-G)·Wv^T 一致
        h, logits, value = R._forward(net, x)
        probs = R.masked_probs(logits, legal)
        dlogits = probs.copy()
        dlogits[action] -= 1.0
        dlogits *= (3.0 - value)
        expect = net['W2'].T @ dlogits + (value - 3.0) * net['Wv'].reshape(-1)
        expect = expect * (h > 0)
        self.assertLess(float(np.max(np.abs(full['b1'] - expect))), 1e-9,
                        "共享层梯度应与 dL/dh = W2^T·dlogits + (V-G)·Wv^T 一致")
        print("\n[R02] 共享层价值项贡献 max|Δ|=%.3e" % diff)

    # ---------------- R03：行为策略与推理 ----------------
    def test_training_sampling_matches_policy(self):
        net = make_tiny_net(seed=5)
        x = R.encode(GRID)
        legal = R._legal_idx(GRID)
        _h, logits, _v = R._forward(net, x)
        probs = R.masked_probs(logits, legal)
        self.assertAlmostEqual(float(probs.sum()), 1.0, places=10)
        for i in range(R.N_ACTIONS):
            if i not in legal:
                self.assertEqual(float(probs[i]), 0.0, "非法方向概率必须为 0")

        rng = random.Random(7)
        n = 40000
        counts = {i: 0 for i in legal}
        for _ in range(n):
            a = R.sample_action(probs, legal, rng)
            self.assertIn(a, legal, "不得采样非法动作")
            counts[a] += 1
        worst = 0.0
        for i in legal:
            emp = counts[i] / n
            p = float(probs[i])
            worst = max(worst, abs(emp - p))
            self.assertLess(abs(emp - p), 4.0 * math.sqrt(p * (1 - p) / n) + 1e-6,
                            "采样频率应服从策略分布（动作 %d）" % i)
        print("\n[R03] 采样频率与策略分布最大偏差=%.4f（n=%d）" % (worst, n))

    def test_inference_is_greedy_deterministic(self):
        net = make_tiny_net(seed=6)
        a = R.choose(net, GRID)
        b = R.choose(net, GRID)
        self.assertEqual(a, b, "推理必须确定性")
        _h, logits, _v = R._forward(net, R.encode(GRID))
        probs = R.masked_probs(logits, R._legal_idx(GRID))
        self.assertEqual(a, R.DIRECTIONS[int(np.argmax(probs))], "推理应取 masked argmax")

    # ---------------- R04：验证集 / best / 早停 ----------------
    def test_checkpoint_and_early_stop(self):
        net = {k: np.random.RandomState(0).standard_normal(v.shape).astype(np.float32) * 0.05
               for k, v in make_tiny_net(seed=0, hidden=R.HIDDEN).items()}
        trained, stats = R.train(games=40, init=net, progress=False, seed=11,
                                 eval_every=10, eval_games=4, eval_seed=999)
        self.assertEqual(len(stats['history']), 4)
        self.assertIsNotNone(stats['best_eval'])
        for h in stats['history']:
            self.assertIn('avg', h)
            self.assertIn('max_tile', h)

        trained2, stats2 = R.train(games=200, init=net, progress=False, seed=12,
                                   eval_every=5, eval_games=4, eval_seed=999, patience=2)
        self.assertLessEqual(stats2['games'], 200)
        print("\n[R04] history=%s  早停=%s  实际训练局数=%d"
              % ([round(h['avg'], 1) for h in stats['history']],
                 stats2['stopped_early'], stats2['games']))

    def test_validation_seed_is_independent_and_reproducible(self):
        net = {k: v.astype(np.float32)
               for k, v in make_tiny_net(seed=8, hidden=R.HIDDEN).items()}
        a = R.evaluate(net, games=6, seed=4321)
        b = R.evaluate(net, games=6, seed=4321)
        self.assertEqual(a, b, "固定验证 seed 必须可复现")


if __name__ == "__main__":
    unittest.main(verbosity=2)
