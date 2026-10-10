#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强化学习自动玩家（第 5 版 · 对应《第 6 篇》的第 5 类算法）

实现：**小型策略/价值网络（MLP）+ 自对弈策略梯度（REINFORCE + 价值基线 + 熵正则）**，纯 numpy：
    - 特征编码：4×4×16 的 one-hot（通道 k 表示该格指数为 k；k=0 为空格）
    - 网络：256 → 128 → {策略 logits(4), 价值 v(1)}
    - 训练：自对弈采样 + 回报归一化 + 优势 = 回报 − 价值基线 + 熵正则（ε-greedy 探索）
    - 推理：对合法方向做 masked-softmax，取概率最大者（确定性）

用法：
    python rl_2048.py --games 300 --out rl_model.npz     # 训练并保存模型
    python rl_2048.py --eval-only --model rl_model.npz   # 用已有模型评估

说明：这是教学/演示级的“可跑通、可复现”RL 流程；要更强需要更多自对弈与更大的网络。
"""

import argparse
import math
import os
import random
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import solver_2048 as _solver                                   # noqa: E402

DIRECTIONS = _solver.DIRECTIONS
FEAT_DIM = 16 * 16                                              # 4×4 格 × 16 个指数通道
HIDDEN = 128
N_ACTIONS = len(DIRECTIONS)


# =====================================================================
# 特征编码
# =====================================================================
def encode(grid):
    """4×4×16 one-hot → 长度 256 的向量（指数 0 表示空格）。"""
    x = np.zeros((4, 4, 16), dtype=np.float32)
    for i in range(4):
        for j in range(4):
            v = grid[i][j]
            k = 0 if v <= 0 else min(15, int(round(math.log2(v))))
            x[i, j, k] = 1.0
    return x.reshape(-1)


# =====================================================================
# 网络
# =====================================================================
def init_net(np_rng):
    scale1 = math.sqrt(2.0 / FEAT_DIM)
    scale2 = math.sqrt(2.0 / HIDDEN)
    return {
        'W1': (np_rng.standard_normal((HIDDEN, FEAT_DIM)) * scale1).astype(np.float32),
        'b1': np.zeros(HIDDEN, dtype=np.float32),
        'W2': (np_rng.standard_normal((N_ACTIONS, HIDDEN)) * scale2).astype(np.float32),
        'b2': np.zeros(N_ACTIONS, dtype=np.float32),
        'Wv': (np_rng.standard_normal((1, HIDDEN)) * scale2).astype(np.float32),
        'bv': np.zeros(1, dtype=np.float32),
    }


def _forward(net, x):
    h = np.maximum(net['W1'] @ x + net['b1'], 0.0)
    logits = net['W2'] @ h + net['b2']
    value = float((net['Wv'] @ h + net['bv'])[0])
    return h, logits, value


def masked_probs(logits, legal_idx):
    """只对合法方向做 softmax（非法方向概率为 0）。"""
    probs = np.zeros(N_ACTIONS, dtype=np.float32)
    if not legal_idx:
        return probs
    allowed = logits[legal_idx]
    allowed = allowed - allowed.max()
    exp = np.exp(allowed)
    exp = exp / exp.sum()
    for pos, idx in enumerate(legal_idx):
        probs[idx] = exp[pos]
    return probs


def _legal_idx(grid):
    return [DIRECTIONS.index(d) for d in _solver.legal_moves(grid)]


def policy_probs(net, grid):
    """返回 {direction: 概率}（仅合法方向有非零值，用于界面展示）。"""
    _, logits, _ = _forward(net, encode(grid))
    probs = masked_probs(logits, _legal_idx(grid))
    return {DIRECTIONS[i]: float(probs[i]) for i in range(N_ACTIONS)}


def choose(net, grid, rng, epsilon=0.0):
    """按 ε-greedy 选择方向；贪心时取概率最大者（平局按固定顺序，确保确定性）。"""
    legal = _legal_idx(grid)
    if not legal:
        return None
    if epsilon > 0 and rng.random() < epsilon:
        return DIRECTIONS[rng.choice(legal)]
    _, logits, _ = _forward(net, encode(grid))
    probs = masked_probs(logits, legal)
    return DIRECTIONS[int(np.argmax(probs))]


# =====================================================================
# 保存 / 加载
# =====================================================================
def save_model(net, path):
    np.savez(path, **{k: v for k, v in net.items()})


def load_model(path):
    with np.load(path) as data:
        return {k: data[k].astype(np.float32) for k in data.files}


# =====================================================================
# 自对弈
# =====================================================================
def _new_game(rng):
    grid = [[0] * 4 for _ in range(4)]
    for _ in range(2):
        grid = _solver.spawn(grid, rng)
    return grid


def _play_one(net, rng, epsilon, max_moves=1000):
    """自对弈一局；返回 (轨迹, 最终分数)。轨迹元素：(state_enc, legal_idx, action_idx, reward)。"""
    grid = _new_game(rng)
    traj = []
    score = 0
    for _ in range(max_moves):
        legal = _legal_idx(grid)
        if not legal:
            break
        state_enc = encode(grid)                    # 记录“动作前”的状态
        if epsilon > 0 and rng.random() < epsilon:
            action = rng.choice(legal)
        else:
            _, logits, _ = _forward(net, state_enc)
            action = int(np.argmax(masked_probs(logits, legal)))
        new_grid, gain, moved = _solver.move_grid(grid, DIRECTIONS[action])
        if not moved:
            break
        grid = _solver.spawn(new_grid, rng)
        traj.append((state_enc, legal, action, gain))
        score += gain
        if _solver.is_game_over(grid):
            break
    return traj, score


# =====================================================================
# 训练（REINFORCE + 价值基线 + 熵正则）
# =====================================================================
def train(games=300, lr=3e-3, gamma=0.98, entropy_beta=2e-3,
          eps_start=0.35, eps_end=0.05, seed=2048, progress=True, max_moves=1000,
          init=None):
    """自对弈策略梯度训练；init 传入已有权重可继续训练（增量训练）。"""
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    net = {k: v.copy() for k, v in init.items()} if init else init_net(np_rng)
    scores = []

    for gi in range(games):
        epsilon = eps_start + (eps_end - eps_start) * (gi / max(1, games - 1))
        traj, score = _play_one(net, rng, epsilon, max_moves)
        scores.append(score)
        if not traj:
            continue

        # 折扣回报（从后往前）
        returns = []
        running = 0.0
        for _s, _li, _a, reward in reversed(traj):
            running = reward + gamma * running
            returns.append(running)
        returns.reverse()
        returns = np.asarray(returns, dtype=np.float32)
        if returns.std() > 1e-6:
            returns = (returns - returns.mean()) / (returns.std() + 1e-6)
        else:
            returns = returns - returns.mean()
        returns = np.clip(returns, -5.0, 5.0)          # 回报截断（数值安全）

        gW1 = np.zeros_like(net['W1']); gb1 = np.zeros_like(net['b1'])
        gW2 = np.zeros_like(net['W2']); gb2 = np.zeros_like(net['b2'])
        gWv = np.zeros_like(net['Wv']); gbv = np.zeros_like(net['bv'])

        for (state_enc, legal, action, _reward), g in zip(traj, returns):
            h, logits, value = _forward(net, state_enc)
            probs = masked_probs(logits, legal)
            adv = float(np.clip(g, -5.0, 5.0)) - float(np.clip(value, -50.0, 50.0))

            # --- 价值头：回归到回报 ---
            gWv += adv * h.reshape(1, -1)
            gbv += adv

            # --- 策略头：软策略梯度（下降方向 = 负的优势加权对数似然）---
            dlogits = probs.copy()
            dlogits[action] -= 1.0
            dlogits *= adv

            # --- 熵正则（鼓励探索）：最大化 H 等价于最小化 -H ---
            if entropy_beta > 0:
                nz = probs[probs > 0]
                entropy = float(-(nz * np.log(nz)).sum())
                dlogits += entropy_beta * (probs * (np.log(probs + 1e-9) + entropy))

            gW2 += np.outer(dlogits, h)
            gb2 += dlogits
            dh = net['W2'].T @ dlogits
            dh[h <= 0] = 0.0
            gW1 += np.outer(dh, state_enc)
            gb1 += dh

        n = float(len(returns))
        grads = [gW1, gb1, gW2, gb2, gWv, gbv]
        if not all(np.all(np.isfinite(x)) for x in grads):
            continue                                   # 出现非有限值：跳过本局更新
        total = math.sqrt(sum(float((x * x).sum()) for x in grads))
        if total > 5.0:                                # 全局梯度裁剪（数值安全）
            scale = 5.0 / total
            grads = [x * scale for x in grads]
        gW1, gb1, gW2, gb2, gWv, gbv = grads
        net['W1'] += lr * (-gW1 / n); net['b1'] += lr * (-gb1 / n)
        net['W2'] += lr * (-gW2 / n); net['b2'] += lr * (-gb2 / n)
        net['Wv'] += lr * (-gWv / n); net['bv'] += lr * (-gbv / n)

        if progress and (gi + 1) % max(1, games // 10) == 0:
            recent = scores[-max(1, games // 10):]
            print('  game %4d/%d  平均分=%.1f  近%d局均值=%.1f'
                  % (gi + 1, games, sum(scores) / len(scores), len(recent),
                     sum(recent) / len(recent)), flush=True)

    stats = {'games': games, 'avg_score': sum(scores) / max(1, len(scores)),
             'best_score': max(scores) if scores else 0}
    return net, stats


def evaluate(net, games=20, seed=1234, max_moves=1000):
    """用贪心策略跑若干局，返回 (平均分, 最高分, 最大瓦片)。"""
    rng = random.Random(seed)
    scores, tiles = [], []
    for _ in range(games):
        grid = _new_game(rng)
        score = 0
        for _ in range(max_moves):
            if _solver.is_game_over(grid):
                break
            d = choose(net, grid, rng, epsilon=0.0)
            if d is None:
                break
            new_grid, gain, moved = _solver.move_grid(grid, d)
            if not moved:
                break
            grid = _solver.spawn(new_grid, rng)
            score += gain
        scores.append(score)
        tiles.append(_solver.max_tile(grid))
    return sum(scores) / max(1, len(scores)), max(scores), max(tiles)


def main():
    ap = argparse.ArgumentParser(description='2048 强化学习（策略梯度）自对弈训练')
    ap.add_argument('--games', type=int, default=300, help='自对弈局数')
    ap.add_argument('--lr', type=float, default=3e-3)
    ap.add_argument('--gamma', type=float, default=0.98)
    ap.add_argument('--seed', type=int, default=2048)
    ap.add_argument('--out', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--init', default=None, help='从已有模型继续训练（增量训练）')
    ap.add_argument('--eval-only', action='store_true')
    ap.add_argument('--model', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--eval-games', type=int, default=20)
    args = ap.parse_args()

    if args.eval_only:
        net = load_model(args.model)
        avg, best, tile = evaluate(net, games=args.eval_games, seed=args.seed)
        print('评估：平均分=%.1f  最高分=%d  最大瓦片=%d' % (avg, best, tile))
        return

    print('开始自对弈训练：局数=%d  lr=%s  gamma=%s%s'
          % (args.games, args.lr, args.gamma,
             '（增量，基于 %s）' % os.path.basename(args.init) if args.init else ''))
    init_net_ = load_model(args.init) if args.init else None
    net, stats = train(games=args.games, lr=args.lr, gamma=args.gamma, seed=args.seed,
                       init=init_net_)
    save_model(net, args.out)
    avg, best, tile = evaluate(net, games=args.eval_games, seed=args.seed)
    print('训练完成：自对弈平均分=%.1f；评估(贪心) 平均分=%.1f 最高分=%d 最大瓦片=%d'
          % (stats['avg_score'], avg, best, tile))
    print('模型已保存：%s' % args.out)


if __name__ == '__main__':
    main()
