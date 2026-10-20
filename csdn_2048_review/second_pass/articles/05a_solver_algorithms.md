# 第5篇（上）· 使用 PyQt5 实现 2048 算法求解版：五类搜索算法内核

第 3 篇建立了 PyQt5 桌面版与 MVC 架构，第 4 篇补齐了平滑动画与渲染优化，两篇解决的是"2048 能不能玩"。本文转向另一个问题：给定一个 $4\times4$ 局面，如何计算出一个可靠的方向。该问题可以形式化为带随机性的序贯决策问题（stochastic sequential decision problem）：评估函数刻画对当前局面的估值，搜索策略决定向前展望的深度。内容较多，本文（上篇）只讨论求解内核，界面集成与交互留待下篇。

求解器被抽象为一层不依赖 PyQt 的纯逻辑：它只接收 $4\times4$ 网格并返回结构化决策结果，因而可独立导入、独立测试、独立跑基准。在此之上按同一口径描述五类策略，从单步贪心的启发式，到对随机生成块求期望的 Expectimax，再到把模拟组织成树的 MCTS，最后到以一次前向完成决策的策略网络。全文顺序为：先给出问题形式化与符号约定，再定义棋盘算子与评估函数，随后逐类给出策略的定义、递推、算法描述、关键实现与复杂度边界，最后汇报正确性验证与工程约束。

> 下篇（第 5 篇下）讨论如何把该求解器装进可拖动、可折叠的双栏工作台，并打磨方向键路由、单步跟随与方向提示等交互。

---

## 1 问题形式化

### 1.1 状态、动作与转移

将 2048 建模为元组 $(\mathcal{S}, \mathcal{A}, T, P_{\text{spawn}}, r, \gamma, \mathcal{S}_{\text{term}})$。

状态 state 为 $s\in\mathcal{S}$，即 $4\times4$ 网格，元素 $s_{ij}\in\{0,2,4,8,\dots\}$；取值非零时为 2 的幂，$s_{ij}=0$ 表示空格。空格集合及其基数记为
$$
E(s)=\{(i,j)\mid s_{ij}=0\},\qquad E=|E(s)|.
$$

动作 action 空间为 $\mathcal{A}=\{\text{up},\text{down},\text{left},\text{right}\}$。状态 $s$ 下能够引起盘面变化的动作构成合法动作集
$$
A(s)=\{a\in\mathcal{A}\mid T(s,a)\neq s\}.
$$

确定性转移 transition（移动与合并）$T(s,a)$ 表示在方向 $a$ 上滑动并合并后的盘面。合并遵循"每个方块在一次移动中至多参与一次合并"，因此 $[2,2,2,2]\to[4,4]$ 而非 $[8]$。本次移动的合并得分记为 $g(s,a)$。

随机转移 $P_{\text{spawn}}$ 发生在玩家动作之后：系统在空格中均匀选取一个格，并按固定分布生成数值，
$$
\Pr[\text{选中格}(i,j)]=\frac{1}{E},\qquad \Pr[v=2]=0.9,\quad \Pr[v=4]=0.1.
$$
一次完整回合的联合转移因而为 $s'\leftarrow P_{\text{spawn}}(T(s,a))$。

### 1.2 即时奖励与终止

即时奖励 reward 取本步合并得分，$r(s,a)=g(s,a)$，其数值等于本次**由合并产生的新方块**数值之和；随机补出的 2/4 不计分。终止 termination 条件为 $A(s)=\varnothing$，即既无空格又四邻无相同数字。拼出 2048 在界面上会提示胜利，但游戏可以继续，搜索也不以 2048 作为终止条件。策略的目标是最大化折扣累计回报
$$
G_t=\sum_{k=0}^{\infty}\gamma^{k}r_{t+k},\qquad \gamma\in(0,1].
$$
求解器中 $\gamma$ 仅在强化学习中使用（默认 0.98）；其余搜索策略直接以累计合并分叠加终局估值作为优化目标。

### 1.3 符号约定

全文统一使用下表符号。

| 符号 | 含义 | 实现或参数名 |
| --- | --- | --- |
| $s$ | 状态，$4\times4$ 网格 | `grid` |
| $a$ | 动作，方向枚举 | `direction` |
| $A(s)$ | 合法动作集合 | `legal_moves(grid)` |
| $T(s,a)$ | 确定性移动与合并后的盘面 | `move_grid` |
| $g(s,a)$ | 本步合并得分 | `move_grid` 返回的 `gained` |
| $E(s)$、$E$ | 空格集合与空格数 | `empty_cells` |
| $p_v$ | 生成数值 $v$ 的概率 | `sample_spawn`（$p_2=0.9$，$p_4=0.1$） |
| $V(s)$ | 启发式评估函数 | `evaluate` |
| $f_i$、$w_i$ | 特征与权重 | `_monotonicity` 等、`DEFAULT_WEIGHTS` |
| $\pi$ | 策略 | `solver_2048` / `rl_2048` |
| $\gamma$ | 折扣因子 | `gamma`（强化学习默认 0.98） |
| $G_t$ | 折扣累计回报 return | `returns` |
| $Q(s,a)$ | 动作价值 | rollout 均值、UCT 的 $\text{total}/\text{visits}$ |
| $b(s)$ | 价值基线 | 价值头输出 $V(s)$ |
| $H$ | 策略熵 | `entropy` |
| $p$ | 根到节点的路径概率 | `tt_key`/`chance_node` 的 `p` |
| $c$、$K(N)$ | UCT 探索常数、机会节点渐进加宽宽度 | `c=1.4`、`chance_width` |

---

## 2 系统结构与棋盘机制

### 2.1 分层结构与纯逻辑约束

求解器沿用第 3、4 篇的 MVC 思路，但把"智能"单独抽成一层。目录结构如下：

```
v5_pyqt_2048_solver/
├── v5_pyqt_2048_solver   # GUI 主程序：双栏工作台 + 求解面板 + 后台线程/并发安全
├── solver_2048           # 求解算法核心（纯逻辑，不依赖 PyQt，可独立运行）
├── rl_2048               # 强化学习：numpy 策略/价值网络 + 自对弈训练 / 独立门禁
├── rl_model.npz             # 正式模型（candidate / .prev.npz 为候选与备份；缺失时仅该策略提示未训练）
├── solver_results/          # 求解会话历史 sessions.json（原子保存 + .bak 回滚）
├── screenshots/             # 整窗截图（capture_gui 统一入口生成）
└── test_solver           # 测试：算法核心 + 界面集成 + 并发生命周期
```

各层职责如下表。

| 层 | 模块 | 职责 |
| --- | --- | --- |
| Model | `v4.AnimatedGameCore`（一行不改） | 棋盘、合并、得分、存档、撤销重做、动画过渡 |
| Solver | `solver_2048` | 只对 `list[list[int]]` 网格做纯函数运算：评估、搜索、决策 |
| View | 第 4 版 `BoardView` / `ParticleOverlay`（一行不改） | 棋盘渲染与粒子动画 |
| Controller | `SolverMainWindow`（继承第 4 版 `MainWindow`） | 组织双栏布局、启动后台求解、刷新状态与日志 |

关键约束是 `solver_2048` 不导入 PyQt。它可像第 1、2 篇那样被单独导入、单独测试、单独跑基准实验；v5 仅通过 `sys.path` 子类化扩展第 4 版，界面零回归。对外主入口保持兼容签名：

```python
# 纯逻辑：给定局面与策略，返回一个决策结果
result = solver.solve(grid, strategy='expectimax', depth=4, time_limit=0.3)
print(result['best_direction'], result['evaluations'], result['elapsed_ms'])
```

### 2.2 移动与合并算子

对 $T(s,a)$ 的实现要求与 `v3 GameCore` 规则完全一致，即每个方块在一次移动中最多参与一次合并。单行向左的滑动与合并由 `slide_line` 完成，四个方向通过"转置加翻转"统一归约到该算子。

```python
def slide_line(line):
    """单行向左合并：返回 (新行, 本行得分)。"""
    size = len(line)
    compressed = [v for v in line if v != 0]        # 压缩非零
    merged = []
    gained = 0
    i = 0
    while i < len(compressed):
        if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
            value = compressed[i] * 2               # 相邻相同则合并，一次只合并一对
            merged.append(value)
            gained += value
            i += 2
        else:
            merged.append(compressed[i])
            i += 1
    merged += [0] * (size - len(merged))            # 右侧补零
    return merged, gained
```

`slide_line` 对应确定性转移 $T$ 的行级算子，返回值中的 `gained` 即即时奖励 $g(s,a)$。`move_grid(grid, direction)` 对上下方向先转置、对右方向先翻转，逐行调用 `slide_line` 后还原，从而得到 $T(s,a)$ 与 $g(s,a)$；`legal_moves` 与 `is_game_over` 分别实现 $A(s)$ 与终止判定。这些函数是后续所有搜索策略的公共地基。

---

## 3 启发式评估函数

### 3.1 线性评估模型

搜索算法的叶子节点需要估值函数。求解器采用线性组合模型
$$
V(s)=\sum_{i} w_i\,f_i(s),
$$
其中 $f_i$ 为局面特征，$w_i$ 为对应权重。基线权重与两个默认关闭的可选特征由 `DEFAULT_WEIGHTS` 给出。

```python
DEFAULT_WEIGHTS = {
    'empty': 2.7,          # 空格数
    'monotonicity': 1.0,   # 单调性
    'smoothness': 0.10,    # 平滑度
    'merge': 1.0,          # 合并潜力（相邻可合并对数）
    'corner': 0.30,        # 最大块在角落
    'snake': 0.0,          # 蛇形位置权重（默认关闭）
    'danger': 0.0,         # 危险度惩罚（默认关闭）
}
```

| 特征 $f_i$ | 默认权重 $w_i$ | 含义 |
| --- | --- | --- |
| `empty` | 2.7 | 空格数量 |
| `monotonicity` | 1.0 | 行/列的单调程度（$f\le 0$，越接近 0 越单调） |
| `smoothness` | 0.10 | 相邻非空块 $\log_2$ 差值之和（取负，$f\le 0$） |
| `merge` | 1.0 | 相邻相等对数，即合并潜力 |
| `corner` | 0.30 | 最大块位于四角时的 $\log_2$ 奖励 |
| `snake` | 0.0 | 蛇形路径权重位，默认关闭 |
| `danger` | 0.0 | 危险度惩罚，默认关闭 |

`snake` 与 `danger` 为可选增强特征，默认权重为 0，因此不改变既有行为；仅在消融实验证明有效时才建议开启。

### 3.2 各特征的定义

以 $\ell(v)=\log_2 v\ (v>0)$，$\ell(0)=0$。

空位数：$f_{\text{empty}}(s)=|E(s)|$。

单调性：对每一行 $i$，把相邻 $\log_2$ 差拆成递增与递减两个分量，
$$
\begin{aligned}
\text{inc}_i&=\sum_{j=1}^{3}\min\bigl(0,\ \ell(s_{ij})-\ell(s_{i,j+1})\bigr),\\
\text{dec}_i&=\sum_{j=1}^{3}\min\bigl(0,\ \ell(s_{i,j+1})-\ell(s_{ij})\bigr).
\end{aligned}
$$
一行（或一列）的贡献取 $\max(\text{inc},\text{dec})$，其值不大于 0，越接近 0 表示越单调；行列合计为
$$
f_{\text{mono}}(s)=\sum_{i=1}^{4}\max(\text{inc}_i,\text{dec}_i)+\sum_{j=1}^{4}\max(\text{inc}^j,\text{dec}^j).
$$

平滑度：对相邻（右与下）且均非零的格子对取 $\log_2$ 差值绝对值之和，再取负，
$$
f_{\text{smooth}}(s)=-\sum_{(u,v)}|\ell(s_u)-\ell(s_v)|.
$$

合并潜力：相邻（右与下）且数值相等且非零的格子对计数，
$$
f_{\text{merge}}(s)=\#\{(u,v)\mid s_u=s_v\neq 0\}.
$$

角落：当最大值位于四角时给出 $\log_2$ 奖励，否则为 0，
$$
(i^*,j^*)=\arg\max_{i,j}s_{ij},\qquad
f_{\text{corner}}(s)=
\begin{cases}
\ell(s_{i^*j^*}), & (i^*,j^*)\in\{(0,0),(0,3),(3,0),(3,3)\},\\
0, & \text{otherwise}.
\end{cases}
$$

可选特征以相同口径计入：$f_{\text{snake}}(s)=100\cdot\frac{\sum_k 2^{-k}\ell(s_{\text{snake}(k)})}{\sum_k 2^{-k}\cdot 15}$，其中 $\text{snake}(k)$ 为自左上角出发的逐行蛇形路径第 $k$ 格；$f_{\text{danger}}(s)=-60\,(1-E/16)-0.6\cdot(\text{相邻非零异值对数})$。

### 3.3 实现与对应

`evaluate` 直接实现上述线性组合；`evaluate_features` 输出各分项，用于解释决策依据。

```python
def evaluate(grid, weights=None):
    """启发式综合打分：权重 · 特征。分数越高代表局面越好。"""
    w = weights or DEFAULT_WEIGHTS
    score = (w['empty'] * len(empty_cells(grid))
             + w['monotonicity'] * _monotonicity(grid)
             + w['smoothness'] * _smoothness(grid)
             + w['merge'] * _merge_potential(grid)
             + w['corner'] * _max_in_corner(grid))
    if w.get('snake', 0.0):
        score += w['snake'] * _snake_value(grid)
    if w.get('danger', 0.0):
        score += w['danger'] * _danger_penalty(grid)
    return score
```

各特征函数与公式逐项对应。`_monotonicity` 即 $f_{\text{mono}}$：

```python
def _monotonicity(grid):
    """行 / 列上“单调递减或单调递增”的程度，越接近 0 越好。"""
    size = len(grid)
    total = 0.0
    for i in range(size):
        inc = dec = 0.0
        for j in range(size - 1):
            a, b = _log2(grid[i][j]), _log2(grid[i][j + 1])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        total += max(inc, dec)

        inc = dec = 0.0
        for j in range(size - 1):
            a, b = _log2(grid[j][i]), _log2(grid[j + 1][i])
            if a > b:
                dec += b - a
            else:
                inc += a - b
        total += max(inc, dec)
    return total
```

核心逻辑是逐行逐列累加 $\min(0,\cdot)$ 分量并取 $\max$，对应 $f_{\text{mono}}$ 中的 $\max(\text{inc},\text{dec})$ 项。`_smoothness` 实现对 $f_{\text{smooth}}$，仅统计相邻非空格并将差值累减：

```python
def _smoothness(grid):
    """相邻非空块的 log2 差值之和（取负），越接近 0 越平滑。"""
    size = len(grid)
    total = 0.0
    for i in range(size):
        for j in range(size):
            if grid[i][j] == 0:
                continue
            v = _log2(grid[i][j])
            if j + 1 < size and grid[i][j + 1] != 0:
                total -= abs(v - _log2(grid[i][j + 1]))
            if i + 1 < size and grid[i + 1][j] != 0:
                total -= abs(v - _log2(grid[i + 1][j]))
    return total
```

`_merge_potential` 与 `_max_in_corner` 分别为 $f_{\text{merge}}$ 与 $f_{\text{corner}}$ 的实现，前者统计相邻相等对数，后者在最大块落入四角时返回 $\ell(\max s)$：

```python
def _merge_potential(grid):
    """相邻可合并对数（越多越好）。"""
    size = len(grid)
    count = 0
    for i in range(size):
        for j in range(size):
            if grid[i][j] == 0:
                continue
            if j + 1 < size and grid[i][j] == grid[i][j + 1]:
                count += 1
            if i + 1 < size and grid[i][j] == grid[i + 1][j]:
                count += 1
    return count


def _max_in_corner(grid):
    """最大块位于四角时给出 log2(最大值) 奖励，否则 0。"""
    mt = max_tile(grid)
    if mt == 0:
        return 0.0
    size = len(grid)
    corners = {(0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)}
    for (i, j) in corners:
        if grid[i][j] == mt:
            return _log2(mt)
    return 0.0
```

---

## 4 五类求解策略

五类策略在"展望深度"与"单步代价"上形成连续谱系，统一按"定义与递推、算法描述、关键实现、复杂度与边界"组织。

| 策略（key） | 决策准则 | 强度参数 | 单步代价 |
| --- | --- | --- | --- |
| 启发式 `heuristic` | 对四个方向各走一步，取估值最高者 | 无 | < 1ms |
| 贪心模拟 `rollout` | 每方向做 $N$ 次随机续玩，取平均收益 | 次数 / 深度 | 低 |
| Expectimax `expectimax` | 对随机新块做期望分支的 minimax | 深度 / 时间 / 剪枝 | 中 |
| MCTS `mcts` | UCT 选择 + 渐进加宽 + rollout 截断 | 模拟次数 / 时间 | 中 |
| 强化学习 `rl` | 策略与价值网络的一次前向 | 无 | 极快 |

强度下拉框（快速 / 标准 / 强力）只对有参数的 2/3/4 生效，其余自动置灰；`PRESET` 表给出各档参数。

### 4.1 启发式：单步贪心

定义与递推。单步贪心在合法动作上最大化"移动后静态估值加即时合并分"，
$$
a^*(s)=\arg\max_{a\in A(s)}\bigl[V(T(s,a))+\lambda\,g(s,a)\bigr].
$$
实现 `_heuristic_decision` 取 $\lambda=0$，仅比较移动后的 $V(T(s,a))$；带即时合并分的同口径单步目标由后文 Expectimax 的 MAX 节点以系数 `score_weight` 给出。

算法描述。对四个方向逐一执行 $T$，若盘面未发生变化则跳过；对移动后的盘面计算 $V$ 并保留最大者作为决策。

关键实现。

```python
def _heuristic_decision(grid, weights=None):
    start = time.time()
    evaluations = {}
    best_dir, best_value = None, -float('inf')
    for d in DIRECTIONS:
        new_grid, _, moved = move_grid(grid, d)
        if not moved:
            evaluations[d] = None
            continue
        value = evaluate(new_grid, weights)
        evaluations[d] = value
        if value > best_value:
            best_value, best_dir = value, d
    return _result('heuristic', best_dir, evaluations, 1, len(DIRECTIONS), start)
```

核心逻辑是 `move_grid` 产生 $T(s,a)$、`moved` 判定 $a\in A(s)$、`evaluate` 给出 $V(\cdot)$，三者分别对应定义中的三个符号。

复杂度与边界。每次决策执行 $|\mathcal{A}|=4$ 次移动与评估，为常数级，单步耗时低于 1ms。当 $A(s)=\varnothing$ 时，`solve` 在入口处提前返回"无可行移动"；非法方向以 `evaluations[d]=None` 标记。

### 4.2 贪心模拟：rollout

定义与递推。对每个候选动作先执行一次 $T$ 得到即时合并分 $g(s,a)$，随后从该盘面出发做 $N$ 次随机续玩，以蒙特卡洛均值估计动作价值
$$
Q(s,a)\approx \frac{1}{N}\sum_{n=1}^{N}\Bigl[\sum_{t=1}^{H}g_t^{(n)}+V\bigl(s_H^{(n)}\bigr)\Bigr],
$$
其中 $H$ 为续玩深度上限，终局以估值 $V$ 截断，四次方向取 $Q$ 最大者。

算法描述。对每个合法方向，先移动得到 $(T(s,a),g(s,a))$；重复 $N$ 次：按策略采样续玩直到深度上限或终局；累计合并分并叠加终局估值；对 $N$ 个样本取均值与标准误；选择均值最大的方向。

关键实现。单次续玩的核心循环如下：

```python
def _rollout_score(grid_after_move, gained, depth, weights, rng,
                   policy='random', epsilon=0.2):
    g = grid_after_move
    score = gained                       # 先计入候选动作自身的合并分
    for _ in range(depth):
        if is_game_over(g):
            break
        g = spawn(g, rng)                # 随机生成新方块
        if is_game_over(g):
            break
        moves = legal_moves(g)
        if not moves:
            break
        if policy == 'heuristic_biased' and rng.random() >= epsilon:
            best, best_v = moves[0], -float('inf')
            for cand in moves:
                ng, _gn, _m = move_grid(g, cand)
                val = evaluate(ng, weights)
                if val > best_v:
                    best_v, best = val, cand
            move = best
        else:
            move = rng.choice(moves)
        g, gain, _ = move_grid(g, move)
        score += gain
    return score + evaluate(g, weights)  # 累计得分 + 终局启发式估值
```

核心逻辑对应递推式：`score` 累计 $\sum_t g_t$，返回值末尾的 `evaluate(g, weights)` 对应截断项 $V(s_H)$。

`_rollout_decision` 负责配对与统计。`paired=True` 时各候选方向共用同一随机数序列：

```python
for d, after_move, gain in _ordered_moves(grid, weights, order=True):
    if paired:
        rng = random.Random(seed)                 # 共同随机数：候选间共享序列
    else:
        idx = DIRECTIONS.index(d)
        rng = random.Random((seed * 1000003 + idx * 7919) & 0xFFFFFFFF)
    sims = [_rollout_score(after_move, gain, max(1, rollout_depth),
                           weights, rng, policy, epsilon)
            for _ in range(max(1, rollouts))]
    mean = sum(sims) / len(sims)
    ...
```

核心逻辑是共同随机数（common random numbers）：配对模式下各候选在同一随机序列下模拟，使候选间比较主要反映动作本身差异而非采样噪声，配对差分的方差小于独立模拟。`policy='random'` 为纯随机续玩基线；`policy='heuristic_biased'` 时以概率 $1-\epsilon$（代码判定 `rng.random() >= epsilon`）走启发式最优方向，否则随机，默认 $\epsilon=0.2$。

复杂度与边界。单次决策代价为 $O(|A|\cdot N\cdot H)$，属低成本档；结果在 `details` 中给出各方向的 `mean/std/se/n`，供基准脚本报告置信区间。`rollouts` 默认 20、`rollout_depth` 默认 16。

### 4.3 Expectimax：对随机出块求期望

定义与递推。搜索树显式分为两类节点。MAX 节点（玩家）在所有合法动作上取最大
$$
V_M(s,d,p)=\max_{a\in A(s)}\bigl[\lambda\,g(s,a)+V_C\bigl(T(s,a),\,d-1,\,p\bigr)\bigr];
$$
CHANCE 节点（系统）在空位上对 $\{2,4\}$ 求概率加权期望
$$
\begin{aligned}
V_C(s,d,p)={}&\frac{1}{E}\sum_{(i,j)\in E(s)}\Bigl[\\
&0.9\,V_M\bigl(s^{(2)}_{ij},d-1,\,p\cdot\tfrac{1}{E}\cdot0.9\bigr)\\
&+0.1\,V_M\bigl(s^{(4)}_{ij},d-1,\,p\cdot\tfrac{1}{E}\cdot0.1\bigr)\Bigr],
\end{aligned}
$$
其中 $s^{(v)}_{ij}$ 表示在空格 $(i,j)$ 生成数值 $v$ 后的盘面。叶子在 $d\le 0$ 或超时时回落为 $V(s)$。路径概率按 $p_{\text{child}}=p\cdot\frac{1}{E}\cdot p_v$ 向下传递，且在 MAX 节点不被重置为 1，否则会丢失上下文。系数 $\lambda=$ `score_weight` 默认 0.0，即不含即时合并分，与经典 Expectimax 一致；调大后搜索更偏向即时合并收益。根节点与内部 MAX 节点采用同一目标函数（根从 $p=1$ 起步）。

算法描述。以迭代加深组织：对 $d=1,2,\dots,\text{max\_depth}$ 逐层求解，每层对合法动作求 $V_M$；若整层在时间预算内完成则更新当前最优并进入下一层，否则回退到已完成深度的结果。四类剪枝在子树展开之前生效。

关键实现。MAX 节点在移动排序下取最大：

```python
for _d, new_grid, gain in _ordered_moves(g, weights, order=(bool(prune) and move_order)):
    any_move = True
    value = score_weight * gain + chance_node(new_grid, depth - 1, p)
    if value > best:
        best = value
```

核心逻辑对应 $V_M$ 递推：`score_weight * gain` 为 $\lambda g(s,a)$，`chance_node` 为 $V_C$。CHANCE 节点实现期望分支与概率截断：

```python
inv_e = 1.0 / total_cells
total = 0.0
for (i, j) in cells_used:                      # cells_used 为全部空位或均匀子样
    p_cell = p * inv_e
    child2 = [row[:] for row in g]; child2[i][j] = 2
    if use_cutoff and (p_cell * 0.9) < prob_cutoff:
        total += 0.9 * leaf(child2)            # 概率权重保留，子树用启发式外推
    else:
        total += 0.9 * max_node(child2, depth - 1, p_cell * 0.9)
    child4 = [row[:] for row in g]; child4[i][j] = 4
    if use_cutoff and (p_cell * 0.1) < prob_cutoff:
        total += 0.1 * leaf(child4)
    else:
        total += 0.1 * max_node(child4, depth - 1, p_cell * 0.1)
result = total / len(cells_used)               # 采样时用子样均值（期望的无偏估计）
```

核心逻辑对应 $V_C$ 递推：`p_cell = p * inv_e` 与因子 $0.9/0.1$ 共同实现 $p_{\text{child}}=p\cdot(1/E)\cdot p_v$；求和后除以 `len(cells_used)` 即取期望。转置表键在启用概率截断时额外包含路径概率 $p$：

```python
def tt_key(g, depth, kind, p):
    if use_cutoff:
        return (state_key(g), depth, kind, p)  # 含精确路径概率，避免误命中
    return (state_key(g), depth, kind)
```

四类机制按精确与近似严格区分。

| 机制 | 分类 | 做法 |
| --- | --- | --- |
| `prune=False` | 精确 | 穷举全部动作 × 全部空位 × $\{2,4\}$，与独立参考实现逐位一致（测试容差 1e-9） |
| 转置表 TT | 无损（可开关） | 键含 `(盘面, 剩余深度, 节点类型)`；启用概率截断时额外含精确路径概率 $p$ |
| 空位采样 `sample_limit` | 近似 | 空位超过上限时用无放回均匀子样的均值估计期望（无偏、有方差，固定种子可复现） |
| 概率截断 `prob_cutoff` | 近似 | 分支概率 $p\cdot(1/E)\cdot p_v$ 低于阈值时不再展开，子树用启发式外推，概率权重完整保留 |
| 移动排序 `move_order` | 次序启发 | 时间预算下优先探索估值高的方向，不改变完全搜索结果 |

默认剪枝参数为 `use_tt=True`、`sample_limit=8`、`prob_cutoff=0.08`、`move_order=True`。

复杂度与边界。分支随深度呈指数增长，因此以"迭代加深加时间预算"约束成本，超时导致的未完成子树不写入转置表。完全搜索（`prune=False`）作为正确性基准：在一个根处必然发生合并的盘面上取 `depth ∈ {1,2,3}`、`score_weight ∈ {0,0.5,1,2}`，与一份不调用任何剪枝代码的独立穷举参考逐位对照，测试容差为 `1e-9`；历史记录中的最大绝对误差约 `8.5e-14`（本次复核未重新打印该具体数值，仅确认通过）。启用与未启用概率截断两种情形下，转置表均保持透明。

### 4.4 MCTS：树结构与渐进加宽

定义与递推。搜索树节点显式区分 PLAYER 与 CHANCE 两类。选择阶段以 UCT 平衡利用与探索，子节点 $j$ 在其父节点中的选择值为
$$
\text{UCT}(j)=\frac{\text{total\_return}(j)}{\text{visits}(j)}+c\sqrt{\frac{\ln N(\text{parent})}{\text{visits}(j)}},
$$
$\text{visits}(j)=0$ 的子节点值取 $+\infty$ 以优先访问；默认 $c=1.4$。机会节点宽度上限支持固定与渐进加宽两种模式：
$$
K(N)=\min\bigl(K_{\max},\ \max(1,\ \lceil c_{pw}\,N^{\alpha}\rceil)\bigr),
$$
$N$ 为该机会节点的已访问次数，默认 $K_{\max}=8$、$c_{pw}=1.0$、$\alpha=0.5$，$N=0$ 时 $K=1$。

算法描述。每次模拟沿树自根向下，PLAYER 节点先移动（获得合并分），随后 CHANCE 节点按真实分布采样新块；触达宽度上限时不再新增节点，而是对采样出的真实局面直接 rollout；模拟结束把同一回报沿显式路径回传到根。回报口径统一为"根到叶或截断点的累计合并分加截断处启发式估值"，使所有候选动作在同一尺度下比较。

关键实现。UCT 与渐进加宽：

```python
def ucb(parent, child):
    if child.visits == 0:
        return float('inf')
    return child.total_return / child.visits + c * math.sqrt(
        math.log(max(1, parent.visits)) / child.visits)


def chance_width(node):
    if not progressive:
        return kmax                                  # 固定宽度
    n = max(1, node.visits)
    k = int(math.ceil(cpw * (n ** alpha)))
    return max(1, min(kmax, k))                       # K(N)=min(Kmax,max(1,ceil(cpw*N**alpha)))
```

触达宽度上限时对真实采样局面 rollout 并沿路径回传，而不是构造无 parent 的临时节点：

```python
child = node.child_index.get(key)
if child is None:
    if len(node.children) >= chance_width(node):
        stats['width_limit_rollouts'] += 1
        return child_grid, 'P', path, acc            # path 含 root，保证回传
    child = _MCTSNode(child_grid, 'P', node, None, ...)
    ...
```

回传时沿整条路径累加同一回报：

```python
leaf_grid, leaf_kind, path, acc = descend(root)
value = rollout(leaf_grid, leaf_kind, acc)
for n in path:
    n.visits += 1
    n.total_return += value
```

核心逻辑是 `path` 显式包含 root，从而保证每次模拟都能回传到根，维持不变量
$$
\begin{aligned}
\text{root\_visits}&=\text{completed}=\text{backpropagated}\\
&=\sum_{a}\text{root\_move\_visits}(a).
\end{aligned}
$$
该不变量在 `width ∈ {1,2,4,8,16,32}` 与 `simulations ∈ {100,500,1000}` 的 18 组确定性测试中全部成立，结果中直接暴露 `completed_simulations / backpropagated_simulations / root_visits / root_move_visits / width_limit_rollouts / timed_out` 等自检字段。

复杂度与边界。单步代价由模拟次数与 rollout 深度共同决定，默认 `simulations=200`、`time_limit=0.3`、`rollout_depth=16`。渐进加宽只限制"是否新增缓存子节点"，不改变采样的真实转移分布；本次复核的 `test_mcts_chance` 输出为 $n=20000$、$p(2)=0.9013$、$p(4)=0.0987$，与固定宽度一致（历史记录中 $n=14279$ 时 $p(2)=0.8987$、$p(4)=0.1013$，量级一致）。超过时间预算时 `timed_out = completed < total`，仍返回已完成部分的决策。

### 4.5 强化学习：策略梯度

定义与递推。策略 $\pi_\theta(a\mid s)$ 由参数化网络给出，目标为最大化期望回报并叠加熵正则，
$$
\begin{aligned}
\nabla_\theta J(\theta)={}&\mathbb{E}\bigl[\nabla_\theta\log\pi_\theta(a\mid s)\,\bigl(G-b(s)\bigr)\bigr]\\
&+\beta\,\nabla_\theta H\bigl(\pi_\theta(\cdot\mid s)\bigr),
\end{aligned}
$$
其中基线 $b(s)$ 取价值头输出（REINFORCE 加价值基线）。实现中的单样本损失与优势为
$$
\begin{aligned}
L&=-(G-V_0)\log\pi(a)+\tfrac{1}{2}(V-G)^2-\beta H,\\
\text{adv}&=G-V_0.
\end{aligned}
$$
$V_0$ 为更新前价值并作 stop-gradient 处理。

特征与网络的对应关系：状态 $s$ 经 $4\times4\times16$ one-hot 编码（通道 $k$ 表示该格指数为 $k$，$k=0$ 为空格）展平为 256 维，网络为 $256\to128\to\{\text{策略 logits}(4),\ V(1)\}$，共享隐藏层。动作分布为 masked-softmax，仅在 $A(s)$ 上归一化，非法方向概率为 0。

算法描述。训练时按 masked-softmax 分布采样动作，行为分布与策略梯度所用分布一致，故无 off-policy 偏差；每局收集轨迹后计算折扣回报、归一化并截断到 $[-5,5]$，反向传播累加梯度并做全局裁剪；推理时用 masked argmax，方向顺序固定以保证平局确定性。

关键实现。特征编码、前向与梯度：

```python
def encode(grid):
    """4×4×16 one-hot → 长度 256 的向量（指数 0 表示空格）。"""
    x = np.zeros((4, 4, 16), dtype=np.float32)
    for i in range(4):
        for j in range(4):
            v = grid[i][j]
            k = 0 if v <= 0 else min(15, int(round(math.log2(v))))
            x[i, j, k] = 1.0
    return x.reshape(-1)


def _forward(net, x):
    h = np.maximum(net['W1'] @ x + net['b1'], 0.0)
    logits = net['W2'] @ h + net['b2']
    value = float((net['Wv'] @ h + net['bv'])[0])
    return h, logits, value
```

核心逻辑对应网络结构：`W1`（$128\times256$）与 `b1` 为共享隐藏层，`W2`/`b2` 产生策略 logits，`Wv`/`bv` 产生标量价值 $V$。梯度计算中，优势与熵项构造 logits 梯度，价值项经共享层回传：

```python
adv = float(target) - value                       # 优势（stop-gradient）
dlogits = probs.copy()
dlogits[action_idx] -= 1.0
dlogits *= adv                                    # 策略项 dL/dlogits
if entropy_beta > 0:
    nz = probs[probs > 0]
    entropy = float(-(nz * np.log(nz)).sum())
    dlogits += entropy_beta * (probs * (np.log(probs + 1e-9) + entropy))
dv = value - float(target)                        # 价值项 dL/dV
```

核心逻辑对应损失 $L$：`dlogits *= adv` 为 REINFORCE 项 $\nabla\log\pi\cdot(G-V_0)$，熵分支对应 $-\beta H$ 的梯度，`dv` 对应 $\tfrac12(V-G)^2$。梯度正确性以中心有限差分逐参数验证，最大相对偏差约 3e-8。

复杂度与边界。一次决策仅需一次前向，复杂度约 $O(256\cdot128+128\cdot4)$，为极快档。模型以 `_schema=2` 记录结构版本，加载时校验 `_schema`、权重形状、dtype 与 NaN/Inf；旧版（V1，无 `_schema`）走专用兼容路径 `load_legacy_model()`，严格加载会明确拒绝，缺失模型时该策略返回带有 `error` 字段的结果。求解热路径以"规范化路径加文件身份 `(size, mtime_ns)`"为键缓存模型，被原子替换后自动失效重载，实测模型加载 cold≈2.75ms 降到 warm≈0.10ms，该数值仅指缓存命中的加载路径，不代表完整 solve 的加速比。

### 4.6 统一比较：预算、成本、质量与训练

五类策略不是简单的“强弱排序”，而是不同资源约束下的选择：

| 策略 | 预算/终止 | 单步成本 | 是否需要训练 | 质量证据（现有） | 适用场景 |
| --- | --- | --- | --- | --- | --- |
| 启发式 | 无搜索预算 | 4 次移动 + 4 次评估 | 否 | 作为单步基线；无独立胜率实验 | 实时建议、兜底 |
| Rollout | 次数 `N` × 深度 `H` | $O(|A|NH)$ | 否 | 固定种子可复现；基准中报告均值/标准误 | 低成本前瞻 |
| Expectimax | 深度 + 时间预算 | 指数级，靠 TT/采样/截断控制 | 否 | 完全搜索与独立参考对照（容差 1e-9） | 追求决策质量 |
| MCTS | 模拟次数 + 时间预算 | 每次模拟一次树下行 + rollout | 否 | 回传不变量、固定宽度/渐进加宽测试 | 长时规划、可中断 |
| RL | 一次前向 | $O(256\cdot128+128\cdot4)$ | **是**（离线训练） | 固定验证集 50 局、seed=12345 的平均分 2267.4 | 极低延迟推理 |

需要区分三件事：

- **预算**决定“允许算多久”，不等于“算得更好”；同墙钟预算下不同后端的搜索深度可能不同，分数不可直接横比。
- **决策成本**是单步耗时，**搜索质量**是决策后的局面表现；前者可用微基准测量，后者需要固定棋盘集、种子与终局口径。
- **训练与推理**只属于 RL：训练成本在离线自对弈，推理只是一次前向；其余四类策略没有训练阶段。

因此本系列不把“某个后端更快”写成“某个策略更强”，也不把 smoke 小样本的分数当作质量排名。

## 5 正确性与工程边界

### 5.1 验证方法

正确性以与独立参考逐位对照的方式验证，而非依赖主观观察。Expectimax 的完全搜索与一份独立穷举参考逐位比较（测试容差 `1e-9`；历史记录最大绝对误差约 `8.5e-14`）；MCTS 的回传不变量 `root_visits == completed == backpropagated` 成立，根各合法动作访问次数之和等于 `root_visits`；机会节点采样分布与理论一致，本次复核 $n=20000$ 时 $p(2)=0.9013$、$p(4)=0.0987$；策略网络梯度以中心有限差分逐参数核对，本次复核最大相对偏差 $3.06\times10^{-8}$（与代码注释中的 ≈3e-8 一致）。

复核命令（`PYTHONNOUSERSITE=1`）：

```bash
python -m unittest test_expectimax_reference test_mcts_chance test_rl_gradients
# Ran 28 tests in 19.362s — OK（exit 0）
```

### 5.2 可复现性、异常兜底与时间预算

可复现性。内核使用固定种子（`DEFAULT_SEED=2048`）。由次数或深度约束的配置（启发式、贪心模拟、强化学习，以及显式固定次数的 MCTS 与关闭时间预算的 Expectimax）在固定种子下可逐位复现；一旦引入墙钟时间预算，其完成深度或模拟次数取决于机器负载，因而只保证同参数同机器下结果稳定可用，不保证逐位复现。

异常兜底。`solve` 在入口处规范化并校验网格，非法棋盘返回带 `error` 的结构化结果；内部任何异常均被捕获，回退到启发式决策并附上 `error` 说明，保证求解失败不影响界面。

时间预算。单次求解的时间上限受 `MAX_TIME_LIMIT=2.0` 约束，即使调用方传入更大值也不会超过；搜索以迭代加深或模拟次数上限配合时间预算，超时立即回退到已完成结果，超时导致的未完成子树不写入转置表。

并行与确定性边界。求解在后台线程执行，主线程只负责动画与刷新；纯逻辑内核的搜索各次调用之间不共享可变状态，唯一的进程级状态是模型缓存，其以文件身份为键、在模型原子替换后自动失效，不引入跨调用不确定性。强化学习为无经验回放、无超参自适应的 on-policy 实现：本仓库 `rl_model.npz` 在固定验证集（50 局，seed=12345，贪心）上平均分 2267.4、最大瓦片 512，同口径下旧模型为 1445.7，作为参照纯随机走子平均分约 1170 至 1200；要显著提升需要补齐回放、自适应超参或更大的网络与更多自对弈。

---

## 6 小结

本文把"会算"自下而上拆为四层。几何全部由第 4 版的只读常量推导，四个方向归约为"左移加变换"，规则与渲染彻底解耦。评估函数把局面质量映射为实数：空格数、单调性、平滑度、合并潜力与最大块在角五项均可解释，权重可调、可消融。五类策略沿展望深度排列：启发式（单步贪心）、贪心模拟（随机续玩估计长期收益）、Expectimax（对随机出块求期望）、MCTS（把模拟组织成树）与强化学习（一次前向），越靠后越强、代价也越高。正确性由与独立参考逐位对照、回传不变量与采样分布统计共同支撑，而非主观观察。由于 `solver_2048` 不导入 PyQt，该内核可被单独导入、单独测试、单独跑基准实验。

---
**上一篇**：[第 4 篇 · 使用 PyQt5 实现 2048：平滑动画与性能优化](../../../blog/第4篇%20·%20使用%20PyQt5%20实现%202048：平滑动画与性能优化.md)

**下一篇**：[第 5 篇（下）· 使用 PyQt5 实现 2048 算法求解版：双栏 AI 求解工作台与交互](../../../blog/第5篇（下）·%20使用%20PyQt5%20实现%202048%20算法求解版：双栏%20AI%20求解工作台与交互.md)
