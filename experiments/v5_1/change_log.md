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
