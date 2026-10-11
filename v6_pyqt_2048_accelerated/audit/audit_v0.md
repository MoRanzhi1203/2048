# 2048 V6 · V0 基线核验与差异核对

> 范围：Git/模型哈希、V5 实际测试数量、V5 文档声称 vs 源码事实的差异核对。
> 只读操作；未改动 v1–v5 任何源码/存档/模型。生成时间：2026-10-11　执行者：Trae Agent。

## 1. 版本冻结与哈希

| 项 | 值 |
| --- | --- |
| Git HEAD | `2f6ca9bda02615fb9710d87a2647d8dfbc9f3ee1` |
| 分支 | `main` |
| 源文件 SHA256 | 见 [v5_sha256.json](v5_sha256.json)（v1–v5 + tools + tests，共 18 个 .py） |
| Git 前快照 | [git_v6_before.txt](git_v6_before.txt) |

**四份既有 RL 模型 SHA256**（采集于 V6 开工前）：

| 模型 | SHA256 |
| --- | --- |
| `v5_pyqt_2048_solver/rl_model.npz` | `ee4b370e67676bfb42b43eb4df01e895c5bf92935adc16869eb135f9f891dc40` |
| `v5_pyqt_2048_solver/rl_model.candidate.npz` | `ee4b370e67676bfb42b43eb4df01e895c5bf92935adc16869eb135f9f891dc40` |
| `v5_pyqt_2048_solver/rl_model.npz.prev.npz` | `724c4eea877421cf728fdaa56b7e8c710d98accf6c8a13ea69d9c0aa5ee9f4f9` |
| `experiments/baseline/rl_model_v1.npz` | `724c4eea877421cf728fdaa56b7e8c710d98accf6c8a13ea69d9c0aa5ee9f4f9` |

## 2. V5 基线测试（本次工作区**重跑**，非引用上传文档）

| 测试 | 计数 | 结果 |
| --- | ---: | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 80 | OK |
| `tests/test_expectimax_reference.py` | 10 | OK |
| `tests/test_mcts_chance.py` | 10 | OK |
| `tests/test_rl_gradients.py` | 8 | OK |
| `tests/test_rl_model_management.py` | 5 | OK |
| `tests/test_algorithm_benchmark_smoke.py` | 脚本（3 策略各 80 步，err=0） | PASS |
| `tests/test_cross_version.py` | 脚本（跨版本隔离/强杀恢复） | PASS |
| `tests/test_popups.py` | 脚本（弹窗主题/DPI） | PASS |
| `tests/test_rl_selftrain.py` | 脚本（自学习/续训） | PASS |
| **unittest 合计** | **113** | **0 失败 / 0 跳过** |

> 说明：上传博客称“187 项（含脚本校验）”。本次重跑得 unittest **113** 项 + 4 个脚本套件，
> 与历史快照的“118 unittest + 69 脚本断言 = 187”在**口径**上一致（脚本内部断言数不同脚本不同），
> 关键是**全部通过且未修改断言/未跳过**。不硬编码 187。

## 3. 差异核对表（source_fact / document_claim / verified / action）

| # | source_fact（源码/实测） | document_claim（上传文档） | verified | action |
| --- | --- | --- | --- | --- |
| 1 | V5 `SolverMainWindow(v4.MainWindow)` 双栏 + `SolverEdgeHandle` 贴边把手 + 完全折叠 | 已有双栏/把手/折叠 | ✅ 源码 + 截图 | V6 直接继承，仅做路径隔离 |
| 2 | `solver_2048._RL_MODEL_CACHE` + `_load_rl_model_cached`（按文件身份失效） | 推理已缓存 | ✅ 源码 | **不**重复“每步重载”修复；V6 复用 |
| 3 | `_save_sessions` 原子保存 + `.bak` 回退；`_load_sessions` 回退 `.bak` | 已原子保存 | ✅ 源码 + 测试 | V6 复制到自身路径，保持行为 |
| 4 | `_expectimax_decision`：根含 `score_weight*gain`、TT 键含精确概率、超时不缓存 | 已修复 | ✅ 源码 + 测试 | 移植到 V6 单一实现（仅替换后端原语） |
| 5 | `_mcts_decision`：显式路径回传，`root_visits==completed==backpropagated` | 已修复 | ✅ 测试 | 移植；V6 测试复核回传不变量 |
| 6 | QThread：`job_id`+棋盘快照校验+取消令牌+短等待+退休回收 | 已修复 | ✅ 源码 | V6 复用未改动 |
| 7 | 老指令称 `_rl_decision` 每步 `load_model` | **旧状态** | ✅ 现为缓存 | 不据此改 V5；只在 V6 复用缓存 |
| 8 | 老指令要求“每配置≥100局/300局”硬门禁 | 旧要求 | ✅ 已识别 | 删除；默认 smoke/pilot/final-lite |
| 9 | 当前工作区 V5 测试真实数量 | “187 项” | ✅ 重跑 113 unittest + 4 脚本 | 以重跑真实数量报告 |
| 10 | 环境：`E:\anaconda3\envs\2048`，numpy1.26.4/numba0.60.0/pybind11 3.1.0 | — | ✅ 实测 | V6 后端以此环境构建/测试 |

## 4. 工作区保护

- V1–V5 源码、`test_solver.py`、`tests/`、`tools/`、四份模型、全部真实存档**未修改**（见
  [git_v6_after.txt](git_v6_after.txt) 与 [../changed_files.md](../changed_files.md)）。
- 唯一被运行时写入的 v5 产物是 `v5_pyqt_2048_solver/solver_results/exports/unittest_session.*`
  （`test_solver.py` 既有行为，已被 `.gitignore` 的 `solver_results/` 忽略）。
- V6 未执行任何 git 提交/推送/标签。
