#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强化学习自动玩家（第 5 版 · 对应《第 6 篇》的第 5 类算法）

算法类型（明确）：**on-policy Actor-Critic / REINFORCE（带价值基线 + 熵正则）**，纯 numpy。
    - 特征编码：4×4×16 one-hot（通道 k = 该格指数为 k；k=0 为空格）→ 256 维
    - 网络：256 → 128 → {策略 logits(4), 价值 V(1)}（共享隐藏层）
    - 训练行为策略：**合法动作 masked-softmax 按分布采样**（与策略梯度所用分布一致，无 off-policy 偏差）
    - 推理：masked argmax（确定性、过滤非法方向）
    - 更新（Phase D 修正）：
        * 价值头：dL/dWv = (V-G)·h（此前符号反了，导致价值头朝误差增大方向更新）
        * 共享层：dL/dh = W2ᵀ·dlogits + (V-G)·Wvᵀ（此前漏掉价值头对共享层的回传）
        * 优势按 stop-gradient 处理（标准 actor-critic 实现）
        * 回报归一化/截断 + 全局梯度裁剪 + 非有限值跳过（数值安全）
    - 训练管理（R04/R05）：可选“固定验证集周期评估 + best/latest 双检查点 + patience 早停”，
      并由独立评估门禁决定是否替换正式模型；学习率自适应等属可选后续工作，不强行声称自动改善。

**不引入 DQN 经验回放**：on-policy 算法引入回放需要 off-policy 校正或更换范式，不属于本次修复范围。

用法：
    python rl_2048.py --games 9000 --out rl_model.npz                    # 训练 + 独立评估门禁
    python rl_2048.py --games 9000 --eval-every 500 --patience 4         # 周期评估 + 早停
    python rl_2048.py --eval-only --model rl_model.npz                    # 仅评估
"""

import argparse
import hashlib
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
FEAT_DIM = 16 * 16
HIDDEN = 128
N_ACTIONS = len(DIRECTIONS)
MODEL_SCHEMA = 2        # 存档/模型结构版本（校验用）


# =====================================================================
# 特征编码 / 网络
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
    """只对合法方向做 softmax（非法方向概率为 0）。dtype 跟随 logits（便于有限差分验证）。"""
    probs = np.zeros(N_ACTIONS, dtype=np.asarray(logits).dtype)
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


def sample_action(probs, legal_idx, rng):
    """按策略分布抽样合法动作（训练行为策略 = 策略梯度所用分布，避免 off-policy 偏差）。"""
    if not legal_idx:
        return None
    weights = [max(1e-12, float(probs[i])) for i in legal_idx]
    return rng.choices(legal_idx, weights=weights, k=1)[0]


def choose(net, grid, rng=None, epsilon=0.0):
    """推理：masked argmax（确定性；epsilon 参数仅为旧接口兼容，不再用于训练）。"""
    legal = _legal_idx(grid)
    if not legal:
        return None
    if rng is not None and epsilon > 0 and rng.random() < epsilon:
        return DIRECTIONS[rng.choice(legal)]
    _, logits, _ = _forward(net, encode(grid))
    probs = masked_probs(logits, legal)
    return DIRECTIONS[int(np.argmax(probs))]


# =====================================================================
# 梯度（可被有限差分独立验证）
# =====================================================================
def compute_gradients(net, x, legal_idx, action_idx, target, entropy_beta=0.0):
    """单样本梯度（与 train() 使用完全相同的目标与符号约定）。

    目标（优势按 stop-gradient 处理，标准 actor-critic）：
        L = -(G - V0)·logπ(a) + 0.5·(V - G)^2 - β·H(π)
    其中 V0 为更新前的价值（常量）。返回 (grads, value, probs)。
    """
    h, logits, value = _forward(net, x)
    probs = masked_probs(logits, legal_idx)
    adv = float(target) - value                       # 优势（stop-gradient）

    dlogits = probs.copy()
    dlogits[action_idx] -= 1.0
    dlogits *= adv                                    # dL/dlogits（策略项）
    if entropy_beta > 0:
        nz = probs[probs > 0]
        entropy = float(-(nz * np.log(nz)).sum())
        dlogits += entropy_beta * (probs * (np.log(probs + 1e-9) + entropy))

    dv = value - float(target)                        # dL/dV = (V - G)（价值项）

    grads = {}
    grads['W2'] = np.outer(dlogits, h)
    grads['b2'] = dlogits.copy()
    # 共享隐藏层：策略头 + 价值头 两部分都要回传（Phase D / R02 修复）
    dh = net['W2'].T @ dlogits + dv * net['Wv'].reshape(-1)
    dh = dh * (h > 0)                                 # ReLU 掩码
    grads['W1'] = np.outer(dh, x)
    grads['b1'] = dh.copy()
    # 价值头：(V-G)·h（Phase D / R01 修复）
    grads['Wv'] = (dv * h).reshape(1, -1)
    grads['bv'] = np.array([dv], dtype=np.float32)
    return grads, value, probs


def apply_update(net, grads, lr):
    """net += lr * (-grad)（对 L 做梯度下降），带全局梯度裁剪。"""
    total = math.sqrt(sum(float((g * g).sum()) for g in grads.values()))
    scale = (5.0 / total) if total > 5.0 else 1.0
    for k, g in grads.items():
        net[k] = (net[k] + lr * (-g * scale)).astype(np.float32)
    return total, scale


# =====================================================================
# 模型存取（含 schema 与形状校验）
# =====================================================================
def save_model(net, path):
    np.savez(path, **{k: v for k, v in net.items()}, _schema=np.array([MODEL_SCHEMA]))


def load_model(path):
    with np.load(path) as data:
        net = {k: data[k].astype(np.float32) for k in data.files if not k.startswith('_')}
    expect = {'W1': (HIDDEN, FEAT_DIM), 'b1': (HIDDEN,), 'W2': (N_ACTIONS, HIDDEN),
              'b2': (N_ACTIONS,), 'Wv': (1, HIDDEN), 'bv': (1,)}
    for k, shape in expect.items():
        if k not in net or tuple(net[k].shape) != shape:
            raise ValueError('模型结构与当前网络不匹配：%s 期望 %s' % (k, shape))
    return net


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# =====================================================================
# 自对弈（on-policy 采样）
# =====================================================================
def _new_game(rng):
    grid = [[0] * 4 for _ in range(4)]
    for _ in range(2):
        grid = _solver.spawn(grid, rng)
    return grid


def _play_one(net, rng, max_moves=1000):
    """自对弈一局；返回 (轨迹, 最终分数)。轨迹元素：(state_enc, legal_idx, action_idx, reward)。

    行为策略 = 网络当前的 masked-softmax 分布（按分布抽样），与策略梯度所用分布一致。
    """
    grid = _new_game(rng)
    traj = []
    score = 0
    for _ in range(max_moves):
        legal = _legal_idx(grid)
        if not legal:
            break
        state_enc = encode(grid)
        _, logits, _ = _forward(net, state_enc)
        action = sample_action(masked_probs(logits, legal), legal, rng)
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
# 训练（REINFORCE + 价值基线 + 熵正则；可选 best/latest + 早停）
# =====================================================================
def train(games=300, lr=3e-3, gamma=0.98, entropy_beta=2e-3, seed=2048,
          progress=True, max_moves=1000, init=None,
          eval_every=0, eval_games=30, eval_seed=12345, patience=0):
    """训练；返回 (net, stats)。

    eval_every>0 时每隔若干局在**固定验证 seed** 上评估一次（与训练 RNG 独立），
    维护 best/latest 双检查点，并按 patience 早停；返回的 net 为 best（若启用评估）。
    """
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    net = {k: v.copy() for k, v in init.items()} if init else init_net(np_rng)
    scores = []
    history = []
    best_net = None
    best_eval = -float('inf')
    since_improve = 0
    stopped_early = False
    ran = 0

    for gi in range(1, games + 1):
        ran = gi
        traj, score = _play_one(net, rng, max_moves)
        scores.append(score)
        if traj:
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
            returns = np.clip(returns, -5.0, 5.0)

            acc = {k: np.zeros_like(net[k]) for k in net}
            for (state_enc, legal, action, _reward), g in zip(traj, returns):
                grads, _v, _p = compute_gradients(net, state_enc, legal, action,
                                                  float(g), entropy_beta)
                for k in acc:
                    acc[k] += grads[k]
            if all(np.all(np.isfinite(g)) for g in acc.values()):
                n = float(len(returns))
                apply_update(net, {k: acc[k] / n for k in acc}, lr)

        if eval_every and gi % eval_every == 0:
            ev = evaluate(net, games=eval_games, seed=eval_seed)   # 固定验证集（独立 RNG）
            history.append({'game': gi, 'avg': ev[0], 'best': ev[1], 'max_tile': ev[2]})
            if ev[0] > best_eval:
                best_eval = ev[0]
                best_net = {k: v.copy() for k, v in net.items()}
                since_improve = 0
            else:
                since_improve += 1
                if patience and since_improve >= patience:
                    stopped_early = True
                    if progress:
                        print('  早停：连续 %d 次验证未提升（best=%.1f）' % (patience, best_eval),
                              flush=True)
                    break

        if progress and gi % max(1, games // 10) == 0:
            recent = scores[-max(1, games // 10):]
            msg = ('  game %5d/%d  平均分=%.1f  近%d局均值=%.1f'
                   % (gi, games, sum(scores) / len(scores), len(recent),
                      sum(recent) / len(recent)))
            if history:
                msg += '  验证均值=%.1f' % history[-1]['avg']
            print(msg, flush=True)

    latest = {k: v.copy() for k, v in net.items()}
    chosen = best_net if best_net is not None else latest
    stats = {'games': ran, 'avg_score': sum(scores) / max(1, len(scores)),
             'best_score': max(scores) if scores else 0,
             'best_eval': None if best_net is None else round(best_eval, 2),
             'history': history, 'stopped_early': stopped_early,
             'patience_used': since_improve}
    return chosen, stats


def evaluate(net, games=20, seed=1234, max_moves=1000):
    """用贪心策略跑若干局，返回 (平均分, 最高分, 最大瓦片)。固定 seed → 可复现验证集。"""
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


# =====================================================================
# CLI（训练 + 独立评估门禁：新模型未优于旧模型时不覆盖）
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description='2048 强化学习（on-policy 策略梯度）自对弈训练')
    ap.add_argument('--games', type=int, default=300)
    ap.add_argument('--lr', type=float, default=3e-3)
    ap.add_argument('--gamma', type=float, default=0.98)
    ap.add_argument('--entropy-beta', type=float, default=2e-3)
    ap.add_argument('--seed', type=int, default=2048)
    ap.add_argument('--out', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--init', default=None, help='从已有模型继续训练（增量）')
    ap.add_argument('--eval-every', type=int, default=0, help='每 N 局在固定验证集评估一次（0=关闭）')
    ap.add_argument('--eval-games', type=int, default=30)
    ap.add_argument('--eval-seed', type=int, default=12345)
    ap.add_argument('--patience', type=int, default=0, help='验证连续未提升多少次后早停（0=关闭）')
    ap.add_argument('--eval-only', action='store_true')
    ap.add_argument('--model', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--force', action='store_true', help='跳过独立评估门禁直接覆盖 --out')
    args = ap.parse_args()

    if args.eval_only:
        net = load_model(args.model)
        avg, best, tile = evaluate(net, games=max(args.eval_games, 50), seed=args.eval_seed)
        print('评估：平均分=%.1f  最高分=%d  最大瓦片=%d' % (avg, best, tile))
        return

    init_net_ = load_model(args.init) if args.init else None
    print('开始自对弈训练：局数=%d lr=%s gamma=%s 评估间隔=%s 早停=%s%s'
          % (args.games, args.lr, args.gamma, args.eval_every or 'off', args.patience or 'off',
             '（增量，基于 %s）' % os.path.basename(args.init) if args.init else ''))
    net, stats = train(games=args.games, lr=args.lr, gamma=args.gamma,
                       entropy_beta=args.entropy_beta, seed=args.seed,
                       init=init_net_, eval_every=args.eval_every,
                       eval_games=args.eval_games, eval_seed=args.eval_seed,
                       patience=args.patience)

    # 候选模型先落盘到隔离路径
    cand = os.path.join(os.path.dirname(args.out) or '.', 'rl_model.candidate.npz')
    save_model(net, cand)
    new_eval = evaluate(net, games=max(args.eval_games, 50), seed=args.eval_seed)

    # 独立评估门禁：只有不劣于旧模型才替换正式模型
    if os.path.exists(args.out) and not args.force:
        old = load_model(args.out)
        old_eval = evaluate(old, games=max(args.eval_games, 50), seed=args.eval_seed)
        print('旧模型评估：均值=%.1f 最大瓦片=%d ｜ 新模型评估：均值=%.1f 最大瓦片=%d'
              % (old_eval[0], old_eval[2], new_eval[0], new_eval[2]))
        if new_eval[0] < old_eval[0]:
            print('门禁：新模型未优于旧模型 → 保留旧模型（候选存于 %s）' % os.path.basename(cand))
            print('训练统计：', {k: v for k, v in stats.items() if k != 'history'})
            return
        prev = args.out + '.prev.npz'
        if not os.path.exists(prev):
            import shutil
            shutil.copy2(args.out, prev)
        print('门禁：新模型优于旧模型（+%.1f）→ 替换正式模型（旧模型备份 %s）'
              % (new_eval[0] - old_eval[0], os.path.basename(prev)))

    import shutil
    shutil.copy2(cand, args.out)
    print('正式模型已更新：%s（SHA256=%s）' % (args.out, file_hash(args.out)[:16]))
    print('新模型评估：均值=%.1f 最高分=%d 最大瓦片=%d' % new_eval)
    print('训练统计：', {k: v for k, v in stats.items() if k != 'history'})


if __name__ == '__main__':
    main()
