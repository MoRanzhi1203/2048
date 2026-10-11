# V6 已知问题与限制（诚实记录）

## 1. 后端性能的限制
- **NumPy 后端在 4×4 单盘上是净变慢的**：`run_micro` / `run_search` 显示其比 reference 慢约
  5–15×。这是 4×4 规模下 NumPy 调用开销远大于计算量的必然结果。NumPy 后端**保留为等价性对照**
  与批量实验用途，**不作默认后端**。
- **Numba 仅在评估密集场景有收益**：`expectimax(prune=False)` 约 1.4×；`rollout` / `mcts`
  因 Python 驱动循环与每调用转换开销反而变慢。故 Numba 非默认后端。
- **C++ 为当前默认**：`rollout` 3.1×、`expectimax` 2.7×、`mcts` 1.8×（同工作量）。`heuristic`
  单步量级过小（µs 级），后端差异无意义。

## 2. 位棋盘溢出回退
- C++/Numba 后端以 4-bit 指数编码，最大 32768。搜索过程中一旦产生 `>=65536` 的方块，
  会抛 `BoardOverflowError` 并**回退 reference 重算同一决策**（记录在 `backend_fallback_reason`）。
  这是**显式回退**，不是静默截断；但意味着极少数含超大瓦片路径的决策会以 reference 计时。
- 输入棋盘若本身含 `>=65536` 的方块，C++/Numba 后端**直接拒绝**（协议层面）。

## 3. 评估浮点与临界动作
- 参考实现用 `math.log2(value)`，位棋盘后端用整数指数（`log2(2^e)=e` 精确），NumPy 用 `np.log2`。
  三者在本机对 2..32768 取值一致；但在**评估值极接近**的临界局面上，浮点求和顺序差异可能改变
  动作排序，从而在 rollout/mcts 中出现罕见的结果分叉。已在同工作量基准中把动作一致率作为指标
  监控（当前为 1.0）。

## 4. 统计与结论边界
- 小样本对局（Smoke 2 / Pilot 5 / Final-lite 10 局每配置）**仅作工程回归**，
  **不足**以宣称算法强弱、胜率显著或后端优劣。未做显著性检验。
- 400 步未自然结束记为 `TRUNCATED`，不与 `FINISHED` 的分数混同比较。

## 5. 未完成的验证
- **GUI 视觉**：四状态截图 `CAPTURE/STRUCTURE/TEXT` 自动 PASS，但 `VISUAL_PASS=UNVERIFIED`
  （需人工核对图像后加 `--visual-confirm` 授予）。
- **高 DPI**：`DPI_VISUAL=UNVERIFIED`（未在真实 Windows 125%/150% 缩放下实测）。
- 未执行每配置 100/300 局的大规模对局实验（非本轮默认要求）。

## 6. 环境相关
- 构建/测试需专用环境 `E:\anaconda3\envs\2048`（`PYTHONNOUSERSITE=1`）。
- C++ 扩展已随仓库提供已构建产物 `bitboard_cpp.cp312-win_amd64.pyd`；若 ABI/平台不匹配，
  `dispatch` 会标记 `cpp=BUILD_BLOCKED` 并回退 reference，按 `BUILD_WINDOWS.md` 重建即可。
