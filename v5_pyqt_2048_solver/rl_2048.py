#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强化学习自动玩家（第 5 版 · 对应《第 5 篇》的第 5 类算法）

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
import json
import math
import os
import random
import shutil
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import solver_2048 as _solver                                   # noqa: E402

DIRECTIONS = _solver.DIRECTIONS
FEAT_DIM = 16 * 16
HIDDEN = 128
N_ACTIONS = len(DIRECTIONS)
MODEL_SCHEMA = 2        # 当前存档/模型结构版本（校验用）
LEGACY_SCHEMA = 1       # 旧版(V1，无 _schema 字段)模型，走专用兼容加载路径

# 三个随机数家族（H2）：训练 / 验证 / 独立门禁（holdout）互不相同
DEFAULT_TRAIN_SEED = 2048
DEFAULT_VALID_SEED = 12345
DEFAULT_HOLDOUT_SEED = 777777

EXPECTED_SHAPES = {
    'W1': (HIDDEN, FEAT_DIM), 'b1': (HIDDEN,), 'W2': (N_ACTIONS, HIDDEN),
    'b2': (N_ACTIONS,), 'Wv': (1, HIDDEN), 'bv': (1,),
}


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
# 模型存取（schema / 形状 / dtype / 有限性校验；原子写 + 版本化备份 + 回滚）
# =====================================================================
def validate_net(net, source='模型'):
    """检查权重 shape / dtype / NaN-Inf；返回归一化（float32）后的 net 副本。"""
    out = {}
    for k, shape in EXPECTED_SHAPES.items():
        if k not in net:
            raise ValueError('%s 缺少张量：%s' % (source, k))
        arr = np.asarray(net[k])
        if tuple(arr.shape) != shape:
            raise ValueError('%s 张量 %s 形状不符：期望 %s，实际 %s'
                             % (source, k, shape, tuple(arr.shape)))
        if not np.issubdtype(arr.dtype, np.floating):
            raise ValueError('%s 张量 %s dtype 非浮点：%s' % (source, k, arr.dtype))
        if not np.all(np.isfinite(arr)):
            raise ValueError('%s 张量 %s 含 NaN/Inf' % (source, k))
        out[k] = arr.astype(np.float32)
    return out


def save_model(net, path, meta=None):
    """把网络写入 path（含 _schema；可选 _meta 训练元数据）。"""
    payload = {k: np.asarray(v) for k, v in net.items()}
    payload['_schema'] = np.array([MODEL_SCHEMA])
    if meta is not None:
        payload['_meta'] = np.array(json.dumps(meta, ensure_ascii=False))
    tmp = path + '.tmp.npz'
    np.savez(tmp, **payload)
    os.replace(tmp, path)                      # 原子替换（同文件系统）


def _read_npz(path):
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


def load_model(path, allow_legacy=False, source=None):
    """严格加载当前 schema 模型；缺 _schema 的旧模型需 allow_legacy=True（专用兼容路径）。"""
    src = source or os.path.basename(path)
    raw = _read_npz(path)
    if '_schema' in raw:
        schema = int(np.asarray(raw['_schema']).reshape(-1)[0])
        if schema != MODEL_SCHEMA:
            raise ValueError('%s 的 _schema=%d 与当前版本 %d 不符' % (src, schema, MODEL_SCHEMA))
    else:
        if not allow_legacy:
            raise ValueError('%s 缺少 _schema（疑似旧版 V%d 模型）；'
                             '请改用 load_legacy_model() 或 allow_legacy=True'
                             % (src, LEGACY_SCHEMA))
    net = {k: v for k, v in raw.items() if not k.startswith('_')}
    return validate_net(net, source=src)


def load_legacy_model(path):
    """专用兼容加载路径：读取旧版(V1，无 _schema)模型，校验形状后返回 float32 网络。"""
    return load_model(path, allow_legacy=True, source='旧版模型(%s)' % os.path.basename(path))


def load_meta(path):
    """读取模型内嵌训练元数据（无则返回 {}）。"""
    try:
        raw = _read_npz(path)
    except (OSError, ValueError):
        return {}
    if '_meta' not in raw:
        return {}
    try:
        return json.loads(str(np.asarray(raw['_meta']).reshape(-1)[0]))
    except (ValueError, TypeError):
        return {}


def versioned_backup(path):
    """原子替换前的版本化备份：返回备份路径（文件不存在则返回 None）。"""
    if not os.path.exists(path):
        return None
    stamp = time.strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak.%s.npz' % (path, stamp)
    shutil.copy2(path, bak)
    return bak


def rollback_model(path, backup):
    """回滚：用版本化备份覆盖正式模型。"""
    if not backup or not os.path.exists(backup):
        raise ValueError('回滚失败：备份不存在 %s' % backup)
    shutil.copy2(backup, path)
    return path


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
def train(games=300, lr=3e-3, gamma=0.98, entropy_beta=2e-3, seed=DEFAULT_TRAIN_SEED,
          progress=True, max_moves=1000, init=None,
          eval_every=0, eval_games=30, eval_seed=DEFAULT_VALID_SEED, patience=0,
          ckpt_prefix=None, meta=None):
    """训练；返回 (net, stats)。

    eval_every>0 时每隔若干局在**固定验证 seed** 上评估一次（与训练 RNG 独立），
    仅由验证分数选择 best 检查点，并按 patience 早停；返回的 net 为 best（若启用评估）。
    训练诊断（H2）：每局记录 episode_len / grad_norm / clip_scale / entropy / value_mse，
    并在 stats['diagnostics'] 汇总（均值 + 裁剪比例）。
    ckpt_prefix 非空时，落盘 best/latest 两个检查点（含 _schema 与训练元数据）。
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
    diag = {'episode_len': [], 'grad_norm': [], 'clip_scale': [], 'entropy': [],
            'value_mse': [], 'mean_return': []}

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
            ent_sum = 0.0
            vmse_sum = 0.0
            nstep = 0
            for (state_enc, legal, action, _reward), g in zip(traj, returns):
                grads, v, probs = compute_gradients(net, state_enc, legal, action,
                                                    float(g), entropy_beta)
                for k in acc:
                    acc[k] += grads[k]
                nz = probs[probs > 0]
                if nz.size:
                    ent_sum += float(-(nz * np.log(nz)).sum())
                vmse_sum += float((v - float(g)) ** 2)
                nstep += 1
            if all(np.all(np.isfinite(g)) for g in acc.values()):
                n = float(len(returns))
                total, scale = apply_update(net, {k: acc[k] / n for k in acc}, lr)
                diag['episode_len'].append(len(traj))
                diag['grad_norm'].append(float(total / n))
                diag['clip_scale'].append(float(scale))
                diag['entropy'].append(ent_sum / max(1, nstep))
                diag['value_mse'].append(vmse_sum / max(1, nstep))
                diag['mean_return'].append(float(returns.mean()))

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
            if diag['grad_norm']:
                msg += '  |g|=%.3f  熵=%.3f' % (diag['grad_norm'][-1], diag['entropy'][-1])
            print(msg, flush=True)

    latest = {k: v.copy() for k, v in net.items()}
    chosen = best_net if best_net is not None else latest

    def _avg(xs):
        return round(sum(xs) / len(xs), 4) if xs else None
    clip_ratio = (round(sum(1 for s in diag['clip_scale'] if s < 1.0)
                        / float(len(diag['clip_scale'])), 4) if diag['clip_scale'] else None)
    stats = {'games': ran, 'avg_score': sum(scores) / max(1, len(scores)),
             'best_score': max(scores) if scores else 0,
             'best_eval': None if best_net is None else round(best_eval, 2),
             'history': history, 'stopped_early': stopped_early,
             'patience_used': since_improve,
             'train_seed': seed, 'valid_seed': eval_seed,
             'diagnostics': {'episode_len_avg': _avg(diag['episode_len']),
                             'grad_norm_avg': _avg(diag['grad_norm']),
                             'entropy_avg': _avg(diag['entropy']),
                             'value_mse_avg': _avg(diag['value_mse']),
                             'mean_return_avg': _avg(diag['mean_return']),
                             'grad_clip_ratio': clip_ratio}}

    if ckpt_prefix:
        ckpt_meta = dict(meta or {})
        ckpt_meta.update({'games': ran, 'lr': lr, 'gamma': gamma,
                          'entropy_beta': entropy_beta, 'train_seed': seed,
                          'valid_seed': eval_seed, 'best_eval': stats['best_eval'],
                          'stopped_early': stopped_early})
        save_model(latest, ckpt_prefix + '.latest.npz', ckpt_meta)
        save_model(best_net if best_net is not None else latest,
                   ckpt_prefix + '.best.npz', ckpt_meta)
    return chosen, stats


# ---------------------------------------------------------------------
# 评估 / 独立门禁（H2：训练 / 验证 / holdout 三个随机数家族分离）
# ---------------------------------------------------------------------
def seed_family(base, n):
    """由基 seed 生成 n 个独立环境种子（同一家族的连续种子）。"""
    return [int(base) + i for i in range(n)]


def play_for_seed(net, seed, max_moves=1000):
    """在给定环境种子上跑一局贪心评估；返回 (score, max_tile)。"""
    rng = random.Random(seed)
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
    return score, _solver.max_tile(grid)


def eval_on_seeds(net, seeds, max_moves=1000):
    """在显式的一批环境种子上评估，返回 [(score, max_tile), ...]（供配对比较）。"""
    return [play_for_seed(net, sd, max_moves) for sd in seeds]


def evaluate(net, games=20, seed=DEFAULT_VALID_SEED, max_moves=1000):
    """用贪心策略在 seed 家族上跑 games 局，返回 (平均分, 最高分, 最大瓦片)。"""
    rows = eval_on_seeds(net, seed_family(seed, games), max_moves)
    scores = [r[0] for r in rows]
    tiles = [r[1] for r in rows]
    return sum(scores) / max(1, len(scores)), (max(scores) if scores else 0), \
        (max(tiles) if tiles else 0)


def bootstrap_ci(values, n=2000, alpha=0.05, seed=20260101):
    """bootstrap 95% CI（与基准脚本一致的实现）。"""
    if not values:
        return (float('nan'), float('nan'))
    rng = random.Random(seed)
    m = len(values)
    means = sorted(sum(values[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return (round(means[int((alpha / 2) * n)], 2),
            round(means[int((1 - alpha / 2) * n) - 1], 2))


def gate_compare(old_net, new_net, games=50, holdout_seed=DEFAULT_HOLDOUT_SEED,
                 max_moves=1000):
    """独立 holdout 门禁：同一批环境种子配对比较新旧模型，返回差值 + bootstrap CI。

    部署判据（保守）：配对差值 (new-old) 的 95% CI 下界 > 0 才认为“显著更优”；
    否则视为差异不足，保持现有正式模型（不强行部署）。
    """
    seeds = seed_family(holdout_seed, games)
    old_rows = eval_on_seeds(old_net, seeds, max_moves)
    new_rows = eval_on_seeds(new_net, seeds, max_moves)
    diffs = [n[0] - o[0] for n, o in zip(new_rows, old_rows)]
    mean_diff = sum(diffs) / max(1, len(diffs))
    ci = bootstrap_ci(diffs)
    old_avg = sum(r[0] for r in old_rows) / max(1, len(old_rows))
    new_avg = sum(r[0] for r in new_rows) / max(1, len(new_rows))
    return {
        'games': games, 'holdout_seed': holdout_seed,
        'seed_range': [seeds[0], seeds[-1]],
        'old_avg': round(old_avg, 2), 'new_avg': round(new_avg, 2),
        'mean_diff': round(mean_diff, 2), 'ci95': list(ci),
        'old_max_tile': max(r[1] for r in old_rows),
        'new_max_tile': max(r[1] for r in new_rows),
        'improved': bool(ci[0] > 0.0),
    }


# =====================================================================
# CLI（训练 + 独立 holdout 门禁：差异不足时保持正式模型，不强行部署）
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description='2048 强化学习（on-policy 策略梯度）自对弈训练')
    ap.add_argument('--games', type=int, default=300)
    ap.add_argument('--lr', type=float, default=3e-3)
    ap.add_argument('--gamma', type=float, default=0.98)
    ap.add_argument('--entropy-beta', type=float, default=2e-3)
    ap.add_argument('--seed', type=int, default=DEFAULT_TRAIN_SEED, help='训练随机数家族种子')
    ap.add_argument('--out', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--init', default=None, help='从指定模型初始化权重（新一轮训练）')
    ap.add_argument('--resume', action='store_true',
                    help='从 --out 的 latest 检查点续训（保留元数据与 RNG 进度）')
    ap.add_argument('--eval-every', type=int, default=0, help='每 N 局在固定验证集评估一次（0=关闭）')
    ap.add_argument('--eval-games', type=int, default=30)
    ap.add_argument('--eval-seed', type=int, default=DEFAULT_VALID_SEED,
                    help='验证随机数家族种子（仅用于 best 选择）')
    ap.add_argument('--holdout-seed', type=int, default=DEFAULT_HOLDOUT_SEED,
                    help='独立门禁(holdout)随机数家族种子（仅用于新旧模型替换判据）')
    ap.add_argument('--gate-games', type=int, default=50, help='独立门禁评估局数')
    ap.add_argument('--patience', type=int, default=0, help='验证连续未提升多少次后早停（0=关闭）')
    ap.add_argument('--eval-only', action='store_true')
    ap.add_argument('--model', default=os.path.join(_HERE, 'rl_model.npz'))
    ap.add_argument('--force', action='store_true', help='跳过独立门禁直接覆盖 --out')
    args = ap.parse_args()

    if args.eval_only:
        net = load_model(args.model)
        avg, best, tile = evaluate(net, games=max(args.eval_games, 50), seed=args.eval_seed)
        print('评估（验证家族 seed=%d）：平均分=%.1f  最高分=%d  最大瓦片=%d'
              % (args.eval_seed, avg, best, tile))
        return

    # 三个随机数家族必须互不相同（训练 / 验证 / holdout）
    families = {args.seed, args.eval_seed, args.holdout_seed}
    if len(families) < 3:
        raise SystemExit('错误：训练(--seed) / 验证(--eval-seed) / 门禁(--holdout-seed) '
                         '必须使用互不相同的随机数家族种子：%s' % sorted(families))

    # 初始化权重：--resume 优先（从 --out 续训），否则 --init，否则全新初始化
    resume_meta = {}
    if args.resume:
        if not os.path.exists(args.out):
            raise SystemExit('错误：--resume 需要已存在的 --out 模型：%s' % args.out)
        init_net_ = load_model(args.out, allow_legacy=True)
        resume_meta = load_meta(args.out)
        print('断点续训：基于 %s（历史元数据 games=%s best_eval=%s）'
              % (os.path.basename(args.out), resume_meta.get('games'),
                 resume_meta.get('best_eval')))
    elif args.init:
        init_net_ = load_model(args.init, allow_legacy=True)
        print('增量训练：基于 %s' % os.path.basename(args.init))
    else:
        init_net_ = None

    print('开始自对弈训练：局数=%d lr=%s gamma=%s 评估间隔=%s 早停=%s ｜ seed: train=%d valid=%d holdout=%d'
          % (args.games, args.lr, args.gamma, args.eval_every or 'off', args.patience or 'off',
             args.seed, args.eval_seed, args.holdout_seed))

    ckpt_prefix = os.path.splitext(args.out)[0]
    net, stats = train(games=args.games, lr=args.lr, gamma=args.gamma,
                       entropy_beta=args.entropy_beta, seed=args.seed,
                       init=init_net_, eval_every=args.eval_every,
                       eval_games=args.eval_games, eval_seed=args.eval_seed,
                       patience=args.patience, ckpt_prefix=ckpt_prefix,
                       meta={'resumed_from': os.path.basename(args.out) if args.resume else None})

    validate_net(net, source='候选模型')                      # 落盘前再校验一次
    cand = os.path.join(os.path.dirname(args.out) or '.', 'rl_model.candidate.npz')
    save_model(net, cand, meta={'train_seed': args.seed, 'valid_seed': args.eval_seed,
                                'holdout_seed': args.holdout_seed, 'games': stats['games'],
                                'best_eval': stats['best_eval']})

    # 独立 holdout 门禁：同一批独立环境种子配对比较新旧模型
    if os.path.exists(args.out) and not args.force:
        old = load_model(args.out, allow_legacy=True)
        gate = gate_compare(old, net, games=max(args.gate_games, 50),
                            holdout_seed=args.holdout_seed)
        print('独立门禁（holdout seed=%d，%d 局配对）：旧均值=%.1f 新均值=%.1f '
              '差值=%.2f CI95=%s 显著更优=%s'
              % (gate['holdout_seed'], gate['games'], gate['old_avg'], gate['new_avg'],
                 gate['mean_diff'], gate['ci95'], gate['improved']))
        if not gate['improved']:
            print('门禁：差异不足（CI 下界未 >0）→ 保持现有正式模型，不部署候选（候选存于 %s）'
                  % os.path.basename(cand))
            print('训练统计：', {k: v for k, v in stats.items() if k != 'history'})
            return
        bak = versioned_backup(args.out)                      # 版本化备份后再原子替换
        print('门禁：候选显著更优（+%.2f，CI95=%s）→ 原子替换正式模型；旧模型备份=%s'
              % (gate['mean_diff'], gate['ci95'],
                 os.path.basename(bak) if bak else '无'))

    save_model(net, args.out, meta={'train_seed': args.seed, 'valid_seed': args.eval_seed,
                                    'holdout_seed': args.holdout_seed, 'games': stats['games'],
                                    'best_eval': stats['best_eval']})
    print('正式模型已更新：%s（SHA256=%s）' % (args.out, file_hash(args.out)[:16]))
    print('训练统计：', {k: v for k, v in stats.items() if k != 'history'})
    print('训练诊断：', stats['diagnostics'])


if __name__ == '__main__':
    main()
