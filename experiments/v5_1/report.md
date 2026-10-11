# 第五版 V5.1 · 算法正确性收口与工程验收报告

> 生成时间：2026-10-11 ｜ 基线 Git HEAD：`701566d` ｜ 未执行 `git commit`
> 运行环境：`E:\anaconda3\python.exe`（Python 3.12.3 / numpy 1.26.4 / PyQt5 5.15.2 / numba 0.60.0 / Windows）
> 原始数据：`experiments/v5_1/results/*.json|*.csv`、`experiments/v5_1/logs/*`、`experiments/v5_1/baseline.json`
> 原则：所有数值来自实际执行；未执行项一律标记 **UNVERIFIED**，不推测补造。
>
> ⚠️ **阅读提示（H7 追加）**：§1–§10 为**历史章节，保持原文**（其中“正式规模 ≥100 局/策略”的提法**已作废**，不再是发布门禁）。**现行结论与门禁以 §11（轻量验收收口）为准**；发布冻结证据见 `experiments/v5_1/release_checks/<run_id>/`。

---

## 0. 结论速览

| Phase | 主题 | 判定 |
| --- | --- | --- |
| H0 | 基线审计与备份 | **PASS** |
| H1 | MCTS 回传 + 渐进加宽 / Expectimax 根口径 | **PASS** |
| H2 | RL 工程（seed 隔离 / 独立门禁 / schema / 检查点） | **PASS** |
| H3 | GUI 安全（job_id / 协作取消 / 线程生命周期） | **PASS** |
| H4 | 性能实验（profiling + smoke 基准 + 消融） | **PARTIAL（探索性 PASS；正式规模 UNVERIFIED）** |
| H5 | 测试与文档 | **PASS**（GUI 视觉门禁 UNVERIFIED，需人工） |

**最终判定：`PARTIAL_PASS`** —— 全部代码正确性/工程性修复 PASS 且有真实证据；性能实验受会话耗时限制仅完成探索性规模（每策略 10 局、有界 horizon），正式规模（≥100 局/策略、完整 horizon）保留可复现脚本但状态 UNVERIFIED；GUI 截图的 VISUAL_PASS 依规范须由人工核对，自动化不授予。

---

## 1. 改动前后文件清单与差异（H0/H5）

### 1.1 改动后哈希（SHA256）

| 文件 | 改动前 | 改动后 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/solver_2048.py` | `6fca44628f295eda…` | `b444044acf7740295921cbe10f3243a0a2e56eadadfd80e8a294dbe32d14d6f4` |
| `v5_pyqt_2048_solver/rl_2048.py` | `d2053dd773037ea8…` | `3f755f718e964ba820f47ce642c2c0aad91b792de701c09b5c5be62acc676892` |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `a2fdff69f5c4f43d…` | `4038b94a68d321398fada1d439b54e9eb221245521a39cc1992323c7de41c23b` |
| `v5_pyqt_2048_solver/test_solver.py` | `578a7f1484e20513…` | `7831dd5200375ff9d0ce232f8f27dc2a74f794a344c41c74351bea3aaa5960b0` |
| `v5_pyqt_2048_solver/功能说明.md` | `333886b…(提交版)` | `69a615aff74ff80b3ce19066045141e32b508cfa7d48313577bde396721862d0` |
| `experiments/benchmark_algorithms.py` | — | `4e22ab407467ab346185954410e09dfbdd1c46ad074f1d8b6182df28c727751c` |
| `experiments/ablation.py` | — | `20fad40ef09dc5a5d81fa4b92a380283538158c133d74e735fed76a3984b059b` |
| `tests/test_mcts_chance.py` | — | `25852b007836431d6f9931112292aa97ae065b4d7e3ca95e3aa1b97b1b87e162` |
| `tests/test_expectimax_reference.py` | — | `13b11ce5035f9949a46212e356ced033c409dae64225ad94c63b46e189b30af8` |
| `tests/test_rl_model_management.py`（新增） | — | `dd6ac19309acca5b54b6a055468d6a9edeb3986e971eb547597edf61cd6945d2` |
| `tests/test_rl_selftrain.py` | — | `d3bef0b0248b7ebe581969c366da398a9e51025d01abc60cdf51d272b0cb4bfd` |

### 1.2 模型保护（哈希未变，验证通过）

| 模型 | SHA256 前 16 位 | 状态 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/rl_model.npz`（正式） | `ee4b370e67676bfb` | **未改** |
| `v5_pyqt_2048_solver/rl_model.candidate.npz` | `ee4b370e67676bfb` | **未改** |
| `v5_pyqt_2048_solver/rl_model.npz.prev.npz` | `724c4eea877421cf` | **未改** |
| `experiments/baseline/rl_model_v1.npz`（V1 基线副本） | 隔离只读 | **未改** |
| 网络张量结构 | W1[128,256] b1[128] W2[4,128] b2[4] Wv[1,128] bv[1]，`_schema=2` | 校验通过 |

### 1.3 差异说明
详见 [change_log.md](change_log.md)。核心：MCTS `descend()` 显式路径 + 宽度上限不再丢弃回传 + 可选渐进加宽；Expectimax 根补记 `score_weight*gain` + TT 键精确 p；RL 三 seed 家族隔离 + 独立 holdout 门禁（配对 CI）+ schema/NaN 校验 + 原子写/备份/回滚 + `--resume` + 训练诊断；GUI job_id/棋盘快照校验 + 协作式取消 + 线程退休回收；测试与文档同步。

---

## 2. MCTS 根回传不变量真实数值（H1）

盘面 `BOARD_MID=[[2,4,8,16],[32,64,128,256],[512,1024,0,0],[0,0,0,0]]`，`rollout_depth=4`，`seed=7`，`time_limit=10s`。全部满足 `root_visits == completed_simulations == backpropagated_simulations == simulations`，且 `sum(root_move_visits.values()) == root_visits`（自动测试 `test_mcts_backprop_invariants` 覆盖 width∈{1,2,4,8,16,32} × sims∈{100,500,1000}）。

代表性抽样（width=1 与 width=8）：

| width | sims | completed | backpropagated | root_visits | Σroot_move_visits | width_limit_rollouts | 不变式 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 100 | 100 | 100 | 100 | 90 | ✔ |
| 1 | 500 | 500 | 500 | 500 | 500 | 484 | ✔ |
| 1 | 1000 | 1000 | 1000 | 1000 | 1000 | 982 | ✔ |
| 8 | 1000 | 1000 | 1000 | 1000 | 1000 | 100 | ✔ |
| 32 | 1000 | 1000 | 1000 | 1000 | 1000 | 0 | ✔ |

> 修复前行为（见 `known_issues.md`）：宽度上限分支返回无 parent 临时节点，回传在 `parent=None` 处终止 → 计入 completed 但未累加到 root（`root_visits < completed`）。本次修复后上表全部相等。
> 渐进加宽 K(N)=min(Kmax,max(1,ceil(cpw·N^alpha)))，`progressive_widening=True, cpw=1.0, alpha=0.5`：400 模拟下 `chance_children` 177→130、`width_limit_rollouts` 74→152，不变量保持；spawn 分布不变（见下）。
> **spawn 分布不变性**（`test_mcts_progressive_widening_keeps_spawn_distribution`）：渐进加宽下 14279 次 `sample_spawn`，p(2)=0.8987、p(4)=0.1013。

---

## 3. Expectimax 独立精确参考对照（H1）

独立精确参考实现见 `tests/test_expectimax_reference.py`（穷举合法动作 × 全部空位 × {0.9/0.1}，不调用被剪枝的搜索代码）。

**根口径修复对照**（`test_expectimax_score_weight_root_gain`，探针盘面 `[[2,2,4,4],[8,8,16,16],[0,0,0,0],[0,0,0,2]]`，根处存在合并 gain>0）：

| depth | score_weight | 与参考最大误差 |
| --- | --- | --- |
| 1/2/3 | 0.0 | 0.0（≤1e-9） |
| 1/2/3 | 0.5 | 0.0 |
| 1/2/3 | 1.0 | 0.0 |
| 1/2/3 | 2.0 | 0.0 |

> 修复前：该盘面在 score_weight>0 时根漏记 gain，会与参考不一致；原 `BOARDS` 盘面根处无合并（gain=0），掩盖了该缺陷。
> 无损模式（`prune=False`）对全部 `BOARDS` × depth∈{1,2,3} 与参考逐位一致（delta=1e-9）。TT 透明性（`use_tt` on/off）在无/有概率截断两种下均保持（`test_tt_is_transparent_without_cutoff`、`test_tt_transparent_with_cutoff`）。

---

## 4. RL：validation/holdout 隔离与门禁证据（H2）

- **三随机数家族隔离**：训练 `--seed`(默认 2048) / 验证 `--eval-seed`(默认 12345) / 独立门禁 `--holdout-seed`(默认 777777)，CLI 强制三者互异（`test_rl_holdout_gate` 验证互异性与可复现）。
- **独立 holdout 门禁**（`gate_compare`）：在同一批 holdout 环境种子（family=777777+i）上**配对**比较新旧模型，输出配对差值与 bootstrap 95% CI；**仅当 CI 下界 > 0（显著更优）才部署**，否则保持现状。
  - 实测（`test_rl_holdout_gate`）：同一模型自比 → `mean_diff=0.0`、`improved=False`；随机初始化（明显更差）→ `mean_diff<0`、`improved=False`。
- **schema/兼容**（`test_rl_schema`）：shape/dtype/NaN-Inf 校验生效；缺 `_schema` 的 V1 模型严格加载**拒绝**、`load_legacy_model` **接受**；`_schema` 不匹配拒绝。
- **检查点**（`test_rl_checkpoint`）：原子写无 `.tmp` 残留、版本化备份 + 回滚、best/latest 落盘、训练元数据持久化、训练诊断字段齐备。
- **模型保护**：本次**未重训、未替换**正式模型（哈希 `ee4b370e…` 未变）；`test_rl_model_management` 结束时校验正式模型哈希不变。

训练诊断示例（`train(games=20)`）：`episode_len≈119`、`grad_norm≈0.011`、`entropy≈1.18`、`value_mse≈0.55`、`grad_clip_ratio=0.0`。

---

## 5. 全部测试套件统计（H5）

| 套件 | 用例数 | 结果 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 69 | OK |
| `tests/test_mcts_chance.py` | 10 | OK |
| `tests/test_expectimax_reference.py` | 10 | OK |
| `tests/test_rl_gradients.py` | 8 | OK |
| `tests/test_rl_model_management.py`（新增） | 3 | OK |
| `tests/test_algorithm_benchmark_smoke.py` | 5 | OK |
| `tests/test_cross_version.py` | 41 | OK（v2–v5） |
| `tests/test_popups.py` | 17 | OK |
| `tests/test_rl_selftrain.py` | 11/11 | PASS（3a/3d 改为真实行为断言） |

**合计：unittest 105 条 + 自定义 69 条 = 174 条，全部通过；无跳过、无失败。** 详见 [test_matrix.md](test_matrix.md)。

---

## 6. 五算法基准与消融数据（H4）

> ⚠️ **规模与 horizon 说明**：受会话耗时限制，基准为 **每策略 10 局、每局步数上限 600（有界 horizon）**；消融更小。有界 horizon 会截断对局、压低分数与最大瓦片，**与历史无界基准（每局 ≤2000 步）不可直接比较**。因此本节结论一律标记为**探索性**；正式规模（≥100 局/策略、完整 horizon）为 **UNVERIFIED**。

### 6.1 两套预算分离（10 局/策略）

**equal_time（每步搜索类 50ms；rollout 8×8；heuristic/rl 常数时间）**
原始数据：`results/benchmark_equal_time_10g_smoke_et_20261011_054006.json/.csv`（耗时 545.9s）

| strategy | avg | median | P10/P90 | std | ci95(avg) | max tile | avg ms | P95 ms | P99 ms | sims avg | 超时 | 非法 | 异常 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expectimax | 10696.0 | 10728 | 10404/10920 | 215.0 | (10561.2, 10822.0) | 1024 | 33.571 | 51.040 | 51.552 | — | 0 | 0 | 0 |
| rollout | 10601.6 | 10470 | 10396/10852 | 204.4 | (10473.2, 10727.2) | 1024 | 13.932 | 21.426 | 31.731 | — | 0 | 0 | 0 |
| heuristic | 8415.2 | 9088 | 3228/10844 | 2469.3 | (6780.8, 9794.0) | 1024 | 0.229 | 0.483 | 0.754 | — | 0 | 0 | 0 |
| mcts | 7820.0 | 7288 | 3440/10408 | 2051.2 | (6482.8, 8955.2) | 1024 | 50.542 | 51.439 | 52.002 | **89** | 491 | 0 | 0 |
| rl | 1496.4 | 1242 | 756/1800 | 899.5 | (1052.4, 2102.0) | 256 | 2.121 | 4.677 | 5.939 | — | 0 | 0 | 0 |

配对差值（同 seed，相对 heuristic）：rollout +2186.4 ci95[678.0, 3832.0]；expectimax +2280.8 ci95[761.2, 3874.4]；mcts −595.2 ci95[−2252.8, 1170.8]；rl −6918.8 ci95[−8356.8, −5404.4]。

**default preset（fast）**
原始数据：`results/benchmark_default_10g_smoke_default_fast_20261011_054715.json/.csv`（耗时 361.5s）

| strategy | avg | median | P10/P90 | std | ci95(avg) | max tile | avg ms | P95 ms | P99 ms | sims avg | 异常 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expectimax | 10125.2 | 10748 | 8152/10860 | 992.1 | (9466.8, 10642.4) | 1024 | 7.920 | 14.083 | 19.706 | — | 0 |
| rollout | 10318.8 | 10720 | 7088/10868 | 1097.0 | (9549.6, 10769.6) | 1024 | 17.760 | 31.001 | 38.414 | — | 0 |
| heuristic | 8415.2 | 9088 | 3228/10844 | 2469.3 | (6780.8, 9794.0) | 1024 | 0.255 | 0.529 | 0.685 | — | 0 |
| mcts | 8094.0 | 7320 | 5712/10452 | 1691.2 | (7095.2, 9164.4) | 1024 | 39.169 | 57.613 | 69.576 | **60** | 0 |
| rl | 1496.4 | 1242 | 756/1800 | 899.5 | (1052.4, 2102.0) | 256 | 2.020 | 3.436 | 5.331 | — | 0 |

配对差值：rollout +1903.6 ci95[30.4, 3766.4]；expectimax +1710.0 ci95[−178.0, 3634.4]；mcts −321.2 ci95[−1813.6, 1261.6]；rl −6918.8 ci95[−8356.8, −5404.4]。

> 观测（探索性）：有界 horizon 下 rollout/expectimax 明显优于 heuristic；mcts 与 heuristic 无显著差异；RL 在当前（分布外）seed 家族上偏弱（最大瓦片 256）。**未做正式显著性结论。**

### 6.2 MCTS 消融（固定宽度 vs 渐进加宽；6 局/变体，300 步，0.05s）
原始数据：`results/ablation_mcts_6g_20261011_060614.json`

| 变体 | avg | ci95(avg) | avg ms | sims avg |
| --- | --- | --- | --- | --- |
| sims=50 | 4372.7 | (3833.3, 4704.0) | 28.154 | — |
| sims=200 | 4552.0 | (4527.3, 4575.3) | 50.534 | — |
| sims=800 | 4622.0 | (4542.0, 4706.7) | 50.554 | — |
| width=2 | 4689.3 | (4605.3, 4770.0) | 50.497 | — |
| width=4 | 4554.7 | (4527.3, 4582.0) | 50.515 | — |
| c=0.5 | 4322.7 | (3859.3, 4569.3) | 50.514 | — |
| c=3.0 | 4632.0 | (4540.0, 4734.7) | 50.538 | — |
| **pw cpw=1.0 a=0.5** | 4634.7 | (4558.0, 4719.3) | 50.529 | — |
| **pw cpw=0.5 a=0.5** | 4598.0 | (4542.7, 4669.3) | 50.519 | — |

0.05s 预算下各变体几乎每步超时（timeouts≈1800），返回 best-so-far；配对差值与 sims=50 相比 CI 均跨 0 → 探索性下无显著差异。**修复前后**的差异不由“胜率”体现，而由 §2 的回传不变量体现（修复前宽度上限触发即丢失回传）。

### 6.3 Heuristic 特征消融（20 局/变体，600 步）
原始数据：`results/ablation_heuristic_20g_20261011_054759.json`（baseline avg=8923.8）

| 变体 | 差值均值 | ci95 | 结论 |
| --- | --- | --- | --- |
| −monotonicity | −4372.4 | [−5553.2, −3041.4] | 关键特征（显著） |
| −merge | −2954.4 | [−4250.8, −1703.2] | 关键特征（显著） |
| +danger(1.0) | +1224.6 | [282.6, 2168.0] | 单项有效（显著） |
| +snake(1.0) | +669.0 | [−314.8, 1685.8] | 不显著 |
| +snake+danger | +320.4 | [−1028.4, 1558.0] | 组合不显著 |
| −empty | +500.8 | [−597.0, 1568.0] | 不显著 |
| −corner | +654.4 | [−200.2, 1476.4] | 不显著 |
| −smoothness | −357.4 | [−1224.4, 539.4] | 不显著 |

> 默认权重**未改动**（snake/danger 默认仍 0.0）；本消除仅用于评估，未据此修改生产权重。

### 6.4 Rollout 续玩策略消融（6 局/变体，300 步）
原始数据：`results/ablation_rollout_6g_20261011_055318.json`（random avg=4630.0）

| 变体 | 差值均值 | ci95 | 平均 ms |
| --- | --- | --- | --- |
| biased eps=0.3 | −4.7 | [−106.0, 108.0] | 28.05 |
| biased eps=0.1 | +26.0 | [−95.3, 108.7] | 33.07 |
| biased eps=0.0 | −48.0 | [−160.7, 62.7] | 35.58 |
| rollouts=4 | −14.0 | [−137.3, 119.3] | 6.80 |
| rollouts=24 | +68.7 | [−82.0, 208.7] | 39.58 |
| depth=6 | +48.0 | [−46.7, 142.7] | 8.06 |
| depth=12 | −45.3 | [−180.0, 106.0] | 15.08 |

> 有界 300 步 + 6 局下全部差异 CI 跨 0：**未观察到显著差异**（探索性）。random 与 heuristic_biased 在等步数下得分相近但 biased 每步更慢（28–36ms vs 10ms）。

### 6.5 Expectimax 剪枝消融（4 局/变体，200 步，depth=2）
原始数据：`results/ablation_expectimax_4g_20261011_060624.json`

| 变体 | avg | 差值 vs 精确 | ci95 | avg ms |
| --- | --- | --- | --- | --- |
| none(精确) | 2567.0 | 0 | — | 2.685 |
| TT | 2567.0 | 0.0 | [0.0, 0.0] | 3.138 |
| TT+sample | 2590.0 | +23.0 | [−97.0, 136.0] | 1.936 |
| TT+cutoff | 2567.0 | 0.0 | [0.0, 0.0] | 2.251 |
| full | 2590.0 | +23.0 | [−97.0, 136.0] | 1.459 |

> **TT 与精确结果完全一致**（差值 0.0），实证 TT 透明；sample/cutoff 为近似且样本少，差异不显著（探索性）。

### 6.6 Profiling（瓶颈识别）
原始数据：`logs/profiling.txt`（`--profile`，固定盘面，每策略 5 次 solve 的 cProfile）

| 策略 | 总耗时(5 次) | 主要热点（cumtime） |
| --- | --- | --- |
| heuristic | 0.002s | move_grid/slide_line |
| rollout | 0.121s | `builtins.len` 0.014s、move_grid 0.099s |
| expectimax | 0.196s | `evaluate` 0.166s → `_monotonicity` 0.074s；move_grid 0.128s |
| mcts | 0.254s | `rollout` 0.205s → `move_grid` 0.177s → `slide_line` 0.121s |
| rl | 0.045s | **`load_model`→`numpy.load` 磁盘读 0.029s（占 ~74%）** |

> 结论：搜索类瓶颈集中在 `move_grid/slide_line/evaluate(_monotonicity)`（均在 `solver_2048.py`）；**RL 单步耗时主要由每次 solve 重新加载模型（磁盘 IO）主导**——已记入 `known_issues.md`（本次未改，避免行为/一致性风险）。
> 性能后端：仓库**不存在** Numba/C++ Bitboard 生产后端切换路径，纯 Python/NumPy 为唯一生产后端，未被替换（未做不公平替换）。

---

## 7. GUI 运行与截图门禁状态（H3/H5）

**自动化测试**：`test_solver.py` 69 条全通过（含 H3 新增 `test_strategy_identity_maps_to_config`、`test_solver_gui_lifecycle`：job_id 自增、停止后线程回收、过期/棋盘快照不匹配结果丢弃、快速重启、运行中关窗）。

**截图门禁**（真实 Windows 桌面捕获，`screen-bitblt` + DWM 外框）：

| 场景 | 文件 | CAPTURE | STRUCTURE | TEXT | VISUAL | GUI_SCREENSHOT |
| --- | --- | --- | --- | --- | --- | --- |
| start | `v5_pyqt_2048_solver/screenshots/full_start.png` | PASS | PASS | PASS | **UNVERIFIED** | false |
| game | `.../full_game.png` | PASS | PASS | PASS | **UNVERIFIED** | false |
| solver | `.../full_solver.png` | PASS | PASS | PASS | **UNVERIFIED** | false |

> 完整窗口（含原生标题栏/图标/最小化最大化关闭）与全部文字均通过校验；**VISUAL_PASS 依规范须人工核对图像，自动化未授予**（`GUI_SCREENSHOT_PASS=false`，禁止自动化自授予人工视觉确认）。

---

## 8. 未通过项 / 未运行项 / 后续处理

| 项 | 状态 | 处理 |
| --- | --- | --- |
| 正式规模基准（≥100 局/策略、完整 2000 步 horizon） | **UNVERIFIED** | 脚本就绪：`python experiments/benchmark_algorithms.py --games 100 --budget {default,equal_time} --out-dir experiments/v5_1/results`；需较长机器时间，未在本次完成 |
| Pilot（30 局/策略） | **UNVERIFIED** | 同上，`--games 30` |
| GUI 截图的 VISUAL_PASS | **UNVERIFIED** | 需人工核对 `screenshots/full_*.png` 后 `--visual-confirm` |
| RL 模型磁盘加载优化 | 遗留（已记录） | 见 known_issues §B2，另行评估缓存策略 |
| MCTS 渐进加宽是否设为默认 | 遗留 | 需更多消融证据，当前保持默认固定宽度 |

**不得以推测补造结果**：上述未跑项均未产出任何“跑分/置信区间/截图结论”，仅提供可复现命令。

---

## 9. 复现命令汇总

```bash
# 正确性测试
python v5_pyqt_2048_solver/test_solver.py
python tests/test_mcts_chance.py
python tests/test_expectimax_reference.py
python tests/test_rl_gradients.py
python tests/test_rl_model_management.py
python tests/test_algorithm_benchmark_smoke.py
python tests/test_cross_version.py
python tests/test_popups.py
python tests/test_rl_selftrain.py

# 性能实验（探索性规模，已跑）
python experiments/benchmark_algorithms.py --games 10 --budget equal_time --max-moves 600 --seed-base 1000 --out-dir experiments/v5_1/results --tag smoke_et
python experiments/benchmark_algorithms.py --games 10 --budget default --speed fast --max-moves 600 --seed-base 1000 --out-dir experiments/v5_1/results --tag smoke_default_fast
python experiments/benchmark_algorithms.py --profile
python experiments/ablation.py --suite heuristic --games 20 --max-moves 600 --out-dir experiments/v5_1/results
python experiments/ablation.py --suite rollout  --games 6  --max-moves 300 --out-dir experiments/v5_1/results
python experiments/ablation.py --suite mcts     --games 6  --max-moves 300 --out-dir experiments/v5_1/results
python experiments/ablation.py --suite expectimax --games 4 --max-moves 200 --out-dir experiments/v5_1/results

# 正式规模（UNVERIFIED，需长时运行）
python experiments/benchmark_algorithms.py --games 100 --budget equal_time --out-dir experiments/v5_1/results

# GUI 截图门禁
python tools/capture_gui.py --version v5 --scene start|game|solver
```

---

## 10. 最终判定

**`PARTIAL_PASS`**
- H0–H3、H5：**PASS**（全部有真实执行证据；模型保护、旧 API/界面可用、v2–v4 未改）。
- H4：**探索性 PASS**（profiling + 两套预算 smoke + 四组消融，均来自真实执行）；**正式规模 UNVERIFIED**。
- GUI 视觉门禁：**UNVERIFIED**（需人工核对，自动化不授予）。

---

## 11. 轻量验收收口（run `v5_1_20261011_141048`，基线 Git HEAD `6dfea64`）

> 上级指令：`2048_V5_1_完整修复与轻量验收_Trae指令.md`。本节为 H0→H6 的**补充收口**：审计并修复新发现的真实问题，按**轻量预算**（Pilot 5 / 收口 10 局每策略，**不再要求 100 局**）完成实验与验收。上文 §1–§10 为上一轮历史，保持原文。

### 11.1 本轮真实修改文件与根因

| 文件 | 根因 | 关键差异 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | H3.2：`_on_solver_result/_on_solver_failed` 先清零 `_solve_in_flight` 再校验 job_id | 改为**先校验（运行态/job_id/棋盘快照）后收尾**，过期结果不再污染新任务状态 |
| `v5_pyqt_2048_solver/solver_2048.py` | H2.9：RL 推理每步 `load_model` 重读 `.npz` | 新增 `_rl_file_identity` + `_load_rl_model_cached`（键=规范化路径+`(size,mtime_ns)`，原子替换自动失效） |
| `v5_pyqt_2048_solver/rl_2048.py` | H2.5：`--resume` 宣称“保留 RNG 进度”，实为仅恢复权重 | 改为明确的 **warm start** 文案；优先读取 `.latest.npz` 检查点 |
| `experiments/benchmark_algorithms.py` | H4：缺 `--time-budget-ms`/`--seed`，无终局标记 | 增补参数与预算覆盖；逐局 `status=FINISHED/TRUNCATED` 与 `max_moves`；汇总区分 |
| `v5_pyqt_2048_solver/test_solver.py` | H1-D/H3 覆盖缺口 | 新增输入不变性、随机流隔离、过期结果不清零在途标志（69→72） |
| `tests/test_rl_model_management.py` | H2.9/H2.5 覆盖缺口 | 新增推理缓存（正确性+替换失效+cold/warm）、warm-start 非精确续训（3→5） |

**模型保护**：`rl_model.npz=ee4b370e67676bfb`、`rl_model.candidate.npz=ee4b370e67676bfb`、`rl_model.npz.prev.npz=724c4eea877421cf`、`experiments/baseline/rl_model_v1.npz=724c4eea877421cf` —— **前后一致，未重训、未替换**。

### 11.2 H0–H6 状态表

| Phase | 主题 | 判定 | 依据 |
| --- | --- | --- | --- |
| H0 | 审计与基线冻结 | **PASS** | `runs/v5_1_20261011_141048/{baseline.json,environment.json,baseline_tests.txt}` |
| H1 | 五算法核心正确性 | **PASS** | 确定性测试 + 下方 11.3/11.4 实测 |
| H2 | RL 管线与独立验收 | **PASS** | schema/legacy/holdout/checkpoint/cache/resume 测试全过；模型哈希不变 |
| H3 | GUI 并发/生命周期/右栏 | **PASS** | 72 条（含生命周期/过期结果/竞态）；整窗截图 CAPTURE/STRUCTURE/TEXT 通过 |
| H4 | 轻量实验预算 | **PASS** | Pilot 5 局 + 收口 10 局，逐局存档（见 11.7） |
| H5 | 测试修正与文档一致性 | **PASS** | 全测试通过；README/功能说明/report/test_matrix/known_issues 已同步 |
| H6 | 专项收口 | **PASS** | 见 11.8 |
| — | GUI 截图视觉 | **UNVERIFIED** | 需人工核对图像，自动化不授予 |

### 11.3 MCTS 根回传不变量（真实数字）

盘面 `[[2,4,8,16],[32,64,128,256],[512,1024,0,0],[0,0,0,0]]`，`rollout_depth=4`，`seed=7`。width∈{1,2,4,8,16,32} × sims∈{100,500,1000} 全部满足：

`root_visits == completed_simulations == backpropagated_simulations == sum(root_move_visits)`

代表性抽样：

| width | sims | completed | backprop | root_visits | Σroot_move_visits | width_limit_rollouts |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1000 | 1000 | 1000 | 1000 | 1000 | 984 |
| 4 | 1000 | 1000 | 1000 | 1000 | 1000 | 693 |
| 8 | 1000 | 1000 | 1000 | 1000 | 1000 | 126 |
| 32 | 1000 | 1000 | 1000 | 1000 | 1000 | 0 |

> 渐进加宽下 spawn 分布不变：n=14279，p(2)=0.8987、p(4)=0.1013（`test_mcts_progressive_widening_keeps_spawn_distribution`）。

### 11.4 Expectimax 独立精确参考（最大误差）

探针含根处合并（gain>0）：`[[2,2,4,4],[8,8,16,16],[0,0,0,0],[0,0,0,2]]`，depth∈{1,2,3} × score_weight∈{0,0.5,1,2} 对照独立穷举参考：

**最大绝对误差 = 8.527e-14**（≈0；远优于 1e-9 容差）。TT 在启用/未启用概率截断两种情形均透明（`test_tt_is_transparent_without_cutoff`、`test_tt_transparent_with_cutoff`）。

### 11.5 RL 验证结果（H2）

- schema/legacy：shape/dtype/NaN-Inf 校验生效；缺 `_schema` 严格拒绝、`load_legacy_model` 接受。
- 检查点：原子写无 `.tmp` 残留；best/latest 落盘；版本化备份 + 回滚；元数据持久化。
- holdout 门禁：三随机数家族互异；同模型自比 `mean_diff=0`、`improved=False`；更差模型判为不改进。
- **推理缓存（H2.9）**：cold≈**2.752ms** → warm≈**0.0997ms**（仅证明消除重复磁盘读，不作全链路加速比）。
- **resume 语义（H2.5）**：`test_rl_warm_start_resume_is_not_exact` 固化“warm start（可复现）但与连续训练不逐位一致 → 非精确断点续训”。
- **正式模型 SHA256 前后对照**：`ee4b370e67676bfb`（未变）。

### 11.6 GUI 并发/退出/折叠/截图（H3/H5）

- 自动化：`test_solver.py` **72 条全过**；含 `test_solver_gui_lifecycle`（job_id 自增/协作取消/线程回收/快速重启/运行中关窗）与新增 `test_stale_result_does_not_clear_inflight_flag`。
- 截图（**真实 Windows 桌面捕获**，`screen-bitblt` + DWM 外框）：

| 场景 | 文件 | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- |
| start | `v5_pyqt_2048_solver/screenshots/full_start.png` | PASS | PASS | PASS | **UNVERIFIED** |
| game | `v5_pyqt_2048_solver/screenshots/full_game.png` | PASS | PASS | PASS | **UNVERIFIED** |
| solver | `v5_pyqt_2048_solver/screenshots/full_solver.png` | PASS | PASS | PASS | **UNVERIFIED** |

> 三者均含原生标题栏/图标/控制按钮与完整文字（`has_titlebar=true, text_rendered=true`）。**VISUAL_PASS 需人工核对，自动化不授予**。

### 11.7 轻量实验实测（H4）

统一参数：`equal_time` 预算 + `--time-budget-ms 30`、`--max-moves 400`、`--seed 1000`（配对环境种子）。**截断（TRUNCATED）得分不等于最终对局得分。**

**Pilot（5 局/策略，耗时 145.0s）** — `results/benchmark_equal_time_5g_pilot30ms_20261011_143855.{json,csv}`

| strategy | avg | median | p10/p90 | ci95(avg) | max tile | avgMs | p95Ms | simsAvg | 异常 | Fin/Tr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rollout | 6183.2 | 6188 | 6148/6204 | (6162.4, 6204.0) | 512 | 13.454 | 22.760 | — | 0 | 0/5 |
| mcts | 6168.0 | 6184 | 6084/6188 | (6124.0, 6202.4) | 512 | 30.566 | 31.702 | 55 | 0 | 0/5 |
| expectimax | 6132.8 | 6196 | 5896/6196 | (6016.0, 6204.0) | 512 | 27.600 | 31.165 | — | 0 | 0/5 |
| heuristic | 6002.4 | 5960 | 5828/6048 | (5898.4, 6115.2) | 512 | 0.212 | 0.345 | — | 0 | 0/5 |
| rl | 1688.0 | 1052 | 756/1636 | (908.0, 2883.2) | 256 | 0.835 | 1.521 | — | 0 | 5/0 |

**收口（10 局/策略，耗时 327.1s）** — `results/benchmark_equal_time_10g_final10gms_20261011_144459.{json,csv}`

| strategy | avg | median | p10/p90 | std | ci95(avg) | max tile | avgMs | p95Ms | p99Ms | simsAvg | 异常 | Fin/Tr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rollout | 6168.0 | 6162 | 6140/6204 | 23.9 | (6154.0, 6182.8) | 512 | 21.687 | 78.643 | 116.740 | — | 0 | 0/10 |
| expectimax | 6062.8 | 6150 | 5764/6212 | 165.2 | (5956.0, 6157.6) | 512 | 29.380 | 32.232 | 36.551 | — | 0 | 0/10 |
| mcts | 5825.2 | 6148 | 3236/6188 | 869.1 | (5232.4, 6154.8) | 512 | 30.897 | 33.713 | 55.682 | 36 | 0 | 1/9 |
| heuristic | 5784.4 | 6072 | 3228/6200 | 860.1 | (5192.4, 6120.8) | 512 | 0.273 | 0.530 | 0.655 | — | 0 | 1/9 |
| rl | 1496.4 | 1242 | 756/1800 | 899.5 | (1052.4, 2102.0) | 256 | 0.751 | 1.112 | 1.495 | — | 0 | 10/0 |

配对差值（相对 heuristic，同 seed）：rollout +383.6 [34.8, 980.0]；expectimax +278.4 [−113.6, 923.6]；mcts +40.8 [−843.6, 893.6]；rl −4288.0 [−4918.0, −3443.2]。

> **解释限制**：400 步上限使搜索类多数对局被 **TRUNCATED**（非自然终局），其得分不能与 RL 的**自然终局**直接比较；RL 在分布外 seed 家族上明显偏弱（最大瓦片 256）。10 局样本仅报 CI，**不作显著性/最终排名结论**。消融实验（heuristic/rollout/mcts/expectimax，非 RL 路径）沿用上一轮结果，本收口未复跑；本轮唯一源码变更（RL 推理缓存）不影响这些非 RL 策略。

### 11.8 H6 专项复核

- 并发：过期结果到达时 `_solve_in_flight`/进度条保持不变（新增测试固化）；停止/关窗/重启压力用例通过。
- 生命周期：线程 finished 通知 + 退休列表回收；关窗后 `_solver_running` 归位、无线程泄漏。
- RL：best/latest 独立落盘；warm start 不恢复 RNG（已固化）；正式模型哈希未变。
- 算法：Expectimax 有合并棋盘与独立参考一致（≤8.5e-14）；MCTS 回传全覆盖平权与 spawn 概率不变量成立。
- 预算：默认 5 局、收口 10 局/策略；**无任何遗留的“每策略 100 局”运行门禁**。

### 11.9 未验证项与需人工操作

| 项 | 状态 | 说明 |
| --- | --- | --- |
| GUI 截图 VISUAL_PASS | **UNVERIFIED** | 需人工核对 `full_start/game/solver.png`，确认后 `--visual-confirm` |
| 更大样本统计比较 | **UNVERIFIED（非门禁）** | 轻量预算不升级为 100 局；如用户显式要求再另行设计 |

### 11.10 本轮最终门禁

| 门禁 | 结果 |
| --- | --- |
| `CORE_CORRECTNESS_PASS` | **PASS** |
| `RL_PIPELINE_PASS` | **PASS** |
| `GUI_RUNTIME_PASS` | **PASS** |
| `BENCHMARK_LIGHT_PASS` | **PASS** |
| `TESTS_PASS` | **PASS**（unittest 110 + 自定义 69 = 179，全部通过、0 失败、0 跳过） |
| `DOCS_PASS` | **PASS** |
| `NO_BLOCKING_FAILURES` | **PASS** |
| `VISUAL_VERIFIED` | **UNVERIFIED**（需人工；不影响上述代码门禁） |

**本轮结论：`V5_1_FINAL_PASS`**（代码与工程门禁全部通过；唯一 UNVERIFIED 为需人工授予的截图视觉确认，按规范不计入代码门禁）。

