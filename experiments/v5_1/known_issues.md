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

## B. 遗留 / 未完成（如实标注）

1. **正式规模性能实验未完成（UNVERIFIED）**：本会话仅完成 profiling 与部分 smoke 基准；每策略 ≥100 局、完整对局 horizon 的正式基准未跑完。脚本已就绪（`experiments/benchmark_algorithms.py --out-dir experiments/v5_1/results`），不得以推测补造。
2. **RL 推理每次 solve 重新加载模型（磁盘 IO 瓶颈）**：profiling 显示 rl 策略单步耗时约 **74% 来自 `load_model` → `numpy.load` 磁盘读**（0.039s 中约 0.029s）。未在本次修改（属行为/性能改动，需单独评估缓存策略与一致性），仅记录。
3. **RL 能力边界**：仍为无经验回放、无超参自适应的 on-policy 实现；长期训练不保证单调提升（见 `test_rl_selftrain` 3b 实测波动）。
4. **MCTS 默认仍为固定宽度**：渐进加宽为可选开关（默认关闭）以保持既有默认行为；是否切换默认需更多消融证据。
5. **期待性（expectimax）采样 + TT 组合为近似**：采样节点缓存会复用某次子样的估计，属近似（已在文档 5.4 标注）；`prune=False` 为严格精确路径。
6. **截图人工视觉门禁**：自动化不授予 VISUAL_PASS；若未人工核对，状态为 UNVERIFIED。

## C. 明确不做（避免越界）

- 不引入 DQN/PPO，不引入经验回放（on-policy 需 off-policy 校正）。
- 不替换性能后端（无 Numba/C++ Bitboard 后端切换，纯 Python/NumPy 生产路径保持不变）。
- 不改动 v2–v4 的算法与界面行为；不改动游戏核心规则与既有 UI/粒子参数。
