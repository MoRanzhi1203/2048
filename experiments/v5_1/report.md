# 第五版 V5.1 · 算法正确性收口与工程验收报告

> 生成时间：2026-10-11 ｜ 基线 Git HEAD：`701566d` ｜ 未执行 `git commit`
> 运行环境：`E:\anaconda3\python.exe`（Python 3.12.3 / numpy 1.26.4 / PyQt5 5.15.2 / numba 0.60.0 / Windows）
> 原始数据：`experiments/v5_1/results/*.json|*.csv`、`experiments/v5_1/logs/*`、`experiments/v5_1/baseline.json`
> 原则：所有数值来自实际执行；未执行项一律标记 **UNVERIFIED**，不推测补造。

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
