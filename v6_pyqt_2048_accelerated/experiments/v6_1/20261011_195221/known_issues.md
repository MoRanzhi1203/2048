# V6.1 已知问题 / 限制（证据目录）

## 1. 仍未验证（UNVERIFIED）
- **GUI 人工视觉**：四张整窗截图自动门禁 CAPTURE/STRUCTURE/TEXT 均 PASS，但**未人工目视核对**，`VISUAL_PASS=UNVERIFIED`。
- **高 DPI**：未在真实 Windows 125% / 150% 缩放下实测；`DPI_VISUAL=UNVERIFIED`（未修改用户系统设置来伪造通过）。

## 2. 性能限制与不确定性
- **原生 rollout 改变随机序列**：`native_rollout=True` 消费显式事件流（uniform `int(u*n)`），与默认 `random.Random._randbelow` 序列不同 → 同 seed 下动作一致率约 0.48。**分布等价已证**（代表盘均值相对差 <1%），但**不得宣传为“同一序列的纯后端加速”**。故默认关闭，仅在明确接受分布等价替代序列时启用。
- **测量方差**：本机为共享负载，rollout cpp 加速比两次独立运行 2.15×~2.71×（reference 中位 85~107ms）。仅报中位数，不作精确倍数承诺。
- **NumPy 在 4×4 净变慢**：所有策略 5~15× 慢；保留为等价对照/批量用途，不作默认。
- **Numba 仅评估密集受益**：expectimax 约 1.34~1.72×，rollout/mcts 因 Python 驱动与转换开销反而变慢。
- **Expectimax 原生子循环未改造**：剖析显示 cpp 已 2.19~2.31×；主要剩余开销是 Python 侧共享 `_ordered_moves` 编排。是否下沉“move+eval”合并原语留待后续（需独立精确参考门禁），本轮**未做**以避免破坏严格等价门禁。

## 3. 边界行为（已证实、非缺陷）
- 位棋盘/numba 后端遇 ≥65536（含相邻 32768 合并产生 65536）**显式抛 BoardOverflowError** → `solve` 回退 reference 重算（同一算法，非静默替换）。
- `cpp`/`numba` 不可用时 `dispatch` 按 `numba→numpy→reference` 顺序回退到**首个可用后端**并记录原因（若 numpy 可用则用 numpy，而非强制 reference）——行为正确，记录于 `profiles/fallback_chain.json`。

## 4. 本轮修复的两个可重现缺陷
1. `solve` 的 `legal_moves` 预检查在溢出 try/except 之外 → 含 ≥65536 的盘在 cpp 下**直接抛异常**。已修复为同样走溢出回退。
2. `solve` 通用异常安全网在**异常后端**上再次调用 `_heuristic_decision` → 原生异常二次失败并冒泡。已修复为改用 reference 重算并记录 `backend_used/fallback_reason`。

## 5. 范围外（本轮未做，按指令）
- 不重训/不替换 RL 模型；不引入 DQN/GPU/联机/多玩家。
- 未执行每配置 100/300 局的大规模矩阵实验（默认仅 smoke 2 局/策略）。
- 未重构 GUI/会话持久化/通用调度器。
