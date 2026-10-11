# V5.1 已知问题与遗留项（known_issues）

> 生成时间：2026-10-11 ｜ 关联改动：Phase H0–H5

## A. 已修复（本版收口）

| 编号 | 问题 | 影响 | 修复 | 证据 |
| --- | --- | --- | --- | --- |
| H1-MCTS | `descend()` 在触发 `max_chance_width` 时返回**无 parent 的临时节点**，回传沿 `parent=None` 终止 | 宽度上限触发的 simulation 计入 completed 但**未累加到 root**，MCTS 估值有偏 | 改为返回**显式 root→leaf 路径**，沿路径回传；宽度上限时直接对采样局面 rollout 后回传 | `test_mcts_backprop_invariants`：width=1、sims=100/500/1000 下 root_visits==completed==backprop |
| H1-EXP | Expectimax 根节点**漏记 `score_weight·本步合并分`** | 声明 score_weight>0 时根与内部 MAX 节点口径不一致；原测试盘面无根合并，掩盖问题 | 根节点改为 `score_weight*gain + chance_node(...)` | `test_expectimax_score_weight_root_gain`：maxErr=0（1e-9 容差） |
| H1-TT | TT 键对路径概率做 `round(p,9)` 近似 | 概率截断下不同 p 可能被误判为同一上下文而错误复用 | 改为**精确浮点 p** 作键（更细分，不会错误命中） | `test_tt_transparent_with_cutoff` 仍透明 |
| H2-SEED | 门禁与验证共用 seed=12345 | 门禁非独立，可能过拟合验证集 | 训练/验证/门禁三随机数家族隔离，CLI 强制互异 | `test_rl_holdout_gate` |
| H2-GATE | 门禁仅比较均值，无显著性判据 | 噪声下可能误部署 | 独立 holdout 同批种子配对差值 + bootstrap 95% CI，**CI 下界>0 才部署**，否则保持现状 | `test_rl_holdout_gate` |
| H2-SCHEMA | `load_model` 不校验 `_schema`/dtype/NaN | 损坏或旧模型可能被静默加载 | 校验 shape/dtype/有限性；旧版走专用兼容路径 | `test_rl_schema` |
| H2-DISK | 无原子写/备份/回滚；`--init`/`--resume` 未区分 | 写入中断可能损坏正式模型 | 原子写（tmp+replace）、版本化备份、回滚、`--resume` | `test_rl_checkpoint` |
| H3-JOB | worker 结果无身份/棋盘校验 | 停止后重启可能被旧结果污染棋盘 | job_id + 任务运行态 + 棋盘快照三重校验 | `test_solver_gui_lifecycle` |
| H3-THREAD | `_shutdown_worker` 在未退出时 `quit()+wait(1500)` 后直接置空引用 | 线程仍运行但引用丢失，存在失控风险 | 协作式取消（threading.Event）+ 退休列表保留引用，待 finished 回收；不用 terminate | `test_solver_gui_lifecycle` |
| H3-TEST | `test_solver.py` 用索引 1 当 Expectimax、2 当 MCTS | 用例名不副实 | 改为 `currentData` 查找 + 新增身份用例 | `test_strategy_identity_maps_to_config` |
| H5-ASSERT | `test_rl_selftrain` 3a/3d 依赖过期源码字符串 | 断言随重构漂移 | 改为真实行为断言 | 11/11 PASS |
| H2-RESUME | `--resume` 帮助文本宣称“保留元数据与 RNG 进度”，实际仅恢复权重+元数据（未恢复 RNG）；且读取 `--out` 而非 `.latest.npz` 检查点 | 语义误导，可能被误当“精确断点续训”；续训起点非 latest | 改为**warm start** 明确措辞（不恢复 RNG/优化器状态），优先读取 `.latest.npz` 检查点；新增确定性测试固化该语义 | `test_rl_warm_start_resume_is_not_exact` |
| H2-CACHE | RL 推理每次 solve 都 `load_model` 重新读 `.npz`（profiling 中约占 RL 单步耗时 74%） | RL 单步延迟被磁盘 I/O 主导 | 规范化路径 + 文件身份 `(size, mtime_ns)` 的可失效模型缓存；模型原子替换后自动失效重载 | `test_rl_inference_cache`（cold≈2.75ms → warm≈0.10ms，仅缓存命中断言，不作全链路加速比结论） |
| H3-STALE | `_on_solver_result`/`_on_solver_failed` 在判定 `job_id` **之前**即清零 `_solve_in_flight` 与进度条 | 过期结果会污染新任务的在途状态（幽灵态） | 先做 job_id / 运行态 / 棋盘快照校验，全部通过后才收尾状态 | `test_stale_result_does_not_clear_inflight_flag` |
| H4-CLI | 基准脚本缺 `--time-budget-ms` 与 `--seed` 别名；逐局无 FINISHED/TRUNCATED 标记 | 无法表达轻量化固定时间预算；截断局与自然终局混淆 | 增补参数别名与统一时间预算覆盖；逐局记录 `status`，汇总区分 finished/truncated | 轻量基准 JSON/CSV |
| H1-INVAR | 缺“输入不变性”“随机数流隔离”确定性测试 | H1-D 覆盖缺口 | 新增两条确定性测试（五策略不修改入参网格；求解不消费全局 `random` 流） | `test_solver_does_not_mutate_input_grid`、`test_solver_rng_stream_isolated` |

## B. 遗留 / 未完成（如实标注）

1. **更大样本统计（UNVERIFIED，非本版门禁）**：本版 H4 已按**轻量预算**完成（Pilot 5 局/策略、收口 10 局/策略，每局 ≤400 步、搜索类 30ms/步）。不再要求“每策略 100 局”。若用户后续显式要求论文级统计比较，才另行设计更大样本；届时不得复用本轻量结果做显著性结论。
2. **RL 能力边界**：仍为无经验回放、无超参自适应的 on-policy 实现；长期训练不保证单调提升（见 `test_rl_selftrain` 3b 实测波动）。
3. **MCTS 默认仍为固定宽度**：渐进加宽为可选开关（默认关闭）以保持既有默认行为；是否切换默认需更多消融证据。
4. **Expectimax 采样 + TT 组合为近似**：采样节点缓存会复用某次子样的估计，属近似（已在文档 5.4 标注）；`prune=False` 为严格精确路径。
5. **截图人工视觉门禁**：自动化不授予 VISUAL_PASS；若未人工核对，状态为 UNVERIFIED。

## C. 明确不做（避免越界）

- 不引入 DQN/PPO，不引入经验回放（on-policy 需 off-policy 校正）。
- 不替换性能后端（无 Numba/C++ Bitboard 后端切换，纯 Python/NumPy 生产路径保持不变）。
- 不改动 v2–v4 的算法与界面行为；不改动游戏核心规则与既有 UI/粒子参数。
