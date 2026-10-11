# V6.1 审计报告（H9-0 / H9-7）

- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`
- git HEAD（前/后一致，未提交）：`0296ab2fb515a5c3fa9aa95ba7e5e631c954e97d`（main）
- 解释器：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`

## 1. 变更前后文件清单（仅 V6；V1–V5 未改动）

| 文件 | 变更 | 说明 |
| --- | --- | --- |
| `solver_backends/bitboard_cpp/bitboard.cpp` | 修改 | `rollout_events` 空位枚举改为**行主序(左→右)**，与 Python `empty_cells` 一致（原为位序/列右→左，导致原生 rollout 无法等价） |
| `solver_backends/bitboard_cpp/bindings.cpp` | 新增 | 绑定 `rollout_batch`：一次调用完成“一组 rollout”，共享事件流游标 |
| `solver_backends/bitboard_cpp/bitboard_cpp.cp312-win_amd64.pyd` | 重编译 | MSVC2022 + CMake + pybind11 3.1 Release；`bitboard_tests` 全通过；SHA256 `3c1b41647680ba004094be7dfd744210cd8be8baef9edc03c4a20435608cf89`（旧 `50ad7588…`） |
| `solver_backends/bitboard_cpp_backend.py` | 修改 | 新增 `supports_native_rollout=True` 与 `rollout_events/rollout_batch` 薄适配层 |
| `solver_backends/api.py` | 修改 | `BackendBase.supports_native_rollout=False`（协议默认） |
| `solver_v6.py` | 修改 | ① rollout 支持可选 `native_rollout`（薄适配，默认关闭）；② 修复溢出预检查未回退；③ 修复通用异常安全网误用异常后端；④ `backend='auto'` 分策略默认（heuristic/rl→reference，rollout/expectimax/mcts→cpp，避免“cpp 全局一刀切”） |

源文件 SHA256 前后对照见 `source_hash_before.json` / `source_hash_after.json` / `changed_files_v6_1.json`。

> 说明：`tools/capture_gui.py` 的 `v6` 登记为**上一版 V6 已存在**，本轮未再改动（`source_hash` 前后一致）。本轮也未改动任何测试文件（未通过修改断言掩盖缺陷）。

## 2. 模型哈希（前后一致，只读）

| 模型 | SHA256 前缀（前=后） |
| --- | --- |
| `v5_pyqt_2048_solver/rl_model.npz` | 见 `model_hash_before.json` == `model_hash_after.json` |
| `rl_model.candidate.npz` | 同上 |
| `rl_model.npz.prev.npz` | 同上 |
| `experiments/baseline/rl_model_v1.npz` | 同上 |

未训练、未替换、未重命名任何模型。

## 3. git 状态

- `git_before.txt` / `git_after.txt` 对比：HEAD 不变，branch 不变；未执行任何 `add/commit/push/tag`。
- 未跟踪项仅本轮新增的指令文档与本证据目录（`experiments/v6_1/`）。

## 4. 后端源文件哈希

- `solver_backends/{api,dispatch,reference,numpy_core,numba_core,events}.py`：本轮**未修改**（`unchanged`）。
- `bitboard_cpp/{bitboard.cpp,bindings.cpp}`：已修改并重编译（见 §1）。
- 新旧 pyd 均在证据链中登记（`source_hash_*`）。

## 5. 版本隔离审计（详见 `storage_isolation.json`）

- 真实 V1–V5 目录（`v5/solver_results`、`v5|v4|v3/game_history`、`.instance.lock`）在隔离测试前后：**无新增/删除/内容变更**（全部 `ok=true`）。
- 四份模型 SHA256 前后一致。
- 隔离子进程以唯一 `2048_HISTORY_DIR=<temp>` 运行完整 GUI 生命周期，写入全部落在 `<temp>/v6` 与 V6 自身 `solver_results/`。
- **V6 一侧显式隔离了 V5 模块级 `RESULT_DIR/SESSIONS_FILE`**（V6MainWindow 覆写 `_load_sessions/_save_sessions/_export_session/export_comparison`），不仅限于存档目录；测试证据见 `storage_isolation.json` 的 `isolated_writes`。

## 6. 结论

- 变更集中在 V6 计算后端与求解调度的**可重现缺陷修复**与**原生 rollout 可选加速**；未改变五策略数学语义、GUI 视觉架构、RL 模型与 V1–V5 代码。
- 所有“未人工视觉确认”的项保持 `UNVERIFIED`；未伪造任何 PASS。
