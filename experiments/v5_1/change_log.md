# V5.1 改动日志（change_log）

> 时间：2026-10-11 ｜ 基线 Git HEAD：`701566d` ｜ 未执行 `git commit`（按任务要求）

## 1. 改动文件清单

### 1.1 源码（行为修复）

| 文件 | 改动内容 |
| --- | --- |
| `v5_pyqt_2048_solver/solver_2048.py` | MCTS：`descend()` 改为返回显式 root→leaf 路径；宽度上限不再构造无 parent 临时节点；新增统计 `completed_simulations/backpropagated_simulations/root_visits/root_move_visits/width_limit_rollouts`；新增可选渐进加宽 `progressive_widening/cpw/alpha`（K(N)=min(Kmax,max(1,ceil(cpw·N^alpha)))）。Expectimax：根节点补记 `score_weight*gain`；TT 键改用精确路径概率 p。`solve()` 透传新参数。 |
| `v5_pyqt_2048_solver/rl_2048.py` | 新增 `validate_net/load_legacy_model/load_meta/versioned_backup/rollback_model`；`save_model` 支持 `_meta` + 原子写；`load_model` 校验 `_schema/shape/dtype/NaN-Inf`；`train()` 增加训练诊断与 best/latest 检查点落盘；新增 `seed_family/play_for_seed/eval_on_seeds/bootstrap_ci/gate_compare`；三随机数家族隔离；CLI 增加 `--holdout-seed/--gate-games/--resume`。 |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `SolverWorker` 信号改为携带 `job_id`；`solveRequested` 改携带 `(job_id, grid, config, cancel_event)`；新增 `_board_signature`、job_id/棋盘快照校验；`_shutdown_worker` 改为协作式取消 + 退休列表（不丢弃未退出线程引用）；`_start_solver` 自增 `_job_id`；`_request_decision` 生成取消令牌与快照。 |

### 1.2 测试（新增/修正）

| 文件 | 改动 |
| --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 新增 `_select_strategy/_select_mode`；把 5 处“索引 1=Expectimax / 2=MCTS”的误用改为 `currentData` 查找；新增 `test_strategy_identity_maps_to_config`、`test_solver_gui_lifecycle`。 |
| `tests/test_mcts_chance.py` | 新增 `test_mcts_backprop_invariants`、`test_mcts_progressive_widening`、`test_mcts_progressive_widening_keeps_spawn_distribution`。 |
| `tests/test_expectimax_reference.py` | 新增 `test_expectimax_score_weight_root_gain`（根处有合并的探针盘面）。 |
| `tests/test_rl_model_management.py` | **新增文件**：`test_rl_schema`、`test_rl_holdout_gate`、`test_rl_checkpoint`。 |
| `tests/test_rl_selftrain.py` | 3a/3d 由过期源码字符串断言改为真实行为断言。 |

### 1.3 实验与文档

| 文件 | 改动 |
| --- | --- |
| `experiments/benchmark_algorithms.py` | 逐移动记录 P10/P90/P99、实际模拟次数、hit4096；`summarize` 增列；新增 `--out-dir/--seed-base/--max-moves/--profile`。 |
| `experiments/ablation.py` | MCTS 增加渐进加宽变体、启发式增加 snake+danger 组合；新增 `--out-dir/--seed-base`。 |
| `v5_pyqt_2048_solver/功能说明.md` | 更新 MCTS（回传不变量 + 渐进加宽）、Expectimax（根口径 + TT 精确 p）、RL（三家族/门禁/schema/检查点/诊断/--resume）。 |
| `experiments/v5_1/*` | baseline.json、report.md、change_log.md、test_matrix.md、known_issues.md、results/、logs/（本次新建）。 |

### 1.4 明确保持不动

- 游戏核心规则（`slide_line/move_grid/is_generate_over/legal_moves`）、启发式默认权重、v2–v4 算法与界面。
- 正式模型 `rl_model.npz`（哈希不变，未重训）；`rl_model.candidate.npz` / `rl_model.npz.prev.npz` 未改。
- 未执行 `git commit`。

## 2. 兼容性说明

- `solve()` 旧签名与返回结构保持兼容；新增字段为**追加**（`completed_simulations` 等）。
- `rl_2048.load_model` 默认严格（旧版需 `load_legacy_model` 或 `allow_legacy=True`）；仓库正式模型含 `_schema=2`，GUI 与既有调用不受影响。
- GUI 信号签名变更仅限 v5 内部（工作线程 ↔ 主窗口），对外接口不变。

## 3. 完整哈希

改动后文件 SHA256（前 16 位）见 [report.md](report.md) 第 1 节“改动后哈希”。

---

## 4. 轻量验收补充改动（run `v5_1_20261011_141048`）

> 上级指令：`2048_V5_1_完整修复与轻量验收_Trae指令.md`；基线 Git HEAD `6dfea64`（上一节 V5.1 修复已提交）。
> 本次为 H0→H6 的补充收口：修复审计中**新发现**的 3 个真实问题，并补齐 H1-D/H4 覆盖缺口。

| 文件 | 改动内容 | 根因 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `_on_solver_result` / `_on_solver_failed` **先做 job_id/运行态/棋盘快照校验，通过后才**清零 `_solve_in_flight` 与进度条 | H3.2：原实现先清零后校验，过期结果会污染新任务在途状态 |
| `v5_pyqt_2048_solver/solver_2048.py` | 新增 `_rl_file_identity` + `_load_rl_model_cached`（RL 推理模型缓存，键=规范化路径+`(size,mtime_ns)`，文件替换自动失效）；`_rl_decision` 改用缓存 | H2.9：原每步 `load_model` 重新读盘，RL 单步耗时被 I/O 主导 |
| `v5_pyqt_2048_solver/rl_2048.py` | `--resume` 帮助与打印改为明确的 **warm start** 语义（仅恢复权重/元数据，不恢复 RNG/优化器状态）；优先读取 `.latest.npz` 检查点 | H2.5：原文案宣称“保留 RNG 进度”，属虚假精确续训声明 |
| `experiments/benchmark_algorithms.py` | 新增 `--seed`（`--seed-base` 别名）与 `--time-budget-ms`（统一覆盖搜索类每步预算）；逐局新增 `status`（FINISHED/TRUNCATED）与 `max_moves`；`summarize` 与表格增加 finished/truncated | H4：接口缺参 + 截断局与终局未区分 |
| `v5_pyqt_2048_solver/test_solver.py` | 新增 `test_solver_does_not_mutate_input_grid`、`test_solver_rng_stream_isolated`、`test_stale_result_does_not_clear_inflight_flag`（69→72） | H1-D / H3 覆盖缺口 |
| `tests/test_rl_model_management.py` | 新增 `test_rl_inference_cache`、`test_rl_warm_start_resume_is_not_exact`（3→5） | H2.9 / H2.5 覆盖缺口 |
| `experiments/v5_1/report.md`、`test_matrix.md`、`known_issues.md` | 同步轻量预算（Pilot 5 / 收口 10，不再要求 100 局）、新修复项与测试计数 | H5.4 文档一致性 |

**本次明确不动**：游戏核心规则与启发式默认权重、v2–v4 行为、正式 RL 模型（`rl_model.npz` 等哈希未变，未重训）；未执行 `git commit`。

**本次改动后源码 SHA256（前 16 位）**：`solver_2048.py=ab8e23ce221d343e`、`rl_2048.py=16c29226d6a744ae`、`v5_pyqt_2048_solver.py=0cdf074c931d2917`、`test_solver.py=fa7a09b1d5134abe`、`benchmark_algorithms.py=c9659d40f20933ea`、`tests/test_rl_model_management.py=d7bd5ed83f0eadd4`。

