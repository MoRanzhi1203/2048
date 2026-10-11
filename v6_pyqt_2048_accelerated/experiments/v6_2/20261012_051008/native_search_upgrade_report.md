# 2048 V6.2 — 原生搜索（Hybrid Native Search）升级报告

> run_id：`20261012_051008`　执行根：`E:\PyQt5_demo\2048`　日期：2026-10-12
> 基线 HEAD（改动前）：`d9efa4e1187f761f3fb69026c090f7a92dc2a052`
> 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_051008/`
> 说明：本文件为**真实执行结果**，非计划或模拟输出。

---

## 1. 根因与目标

V6/V6.1 已有 C++ Bitboard 原语（move/evaluate/legal）与原生 `rollout_events`/`rollout_batch` 内核，
但**整棵搜索树仍在 Python**：Expectimax 每到一个子节点就跨边界调用一次 `backend.move()`，
MCTS 的 selection/expansion/rollout/backprop 全在 Python。跨语言往返（pybind11）与 Python 解释器
开销成为主瓶颈，而 C++ 的一次 4×4 位棋盘操作只需亚微秒级。

V6.2 目标：在**不推翻现有架构**（GUI/调度/后端协议/Reference 语义）的前提下，把
① 原生 Rollout 单次与批量化接入、② 原生 Expectimax 整树、③ 原生 MCTS 整树依次下沉到 C++，
并以真实基准决定「每个策略默认走哪条路径」，全部带正确性/取消/回退门禁。

## 2. 逐阶段实现

### S1 契约（`solver_backends/native_api.py`，新增）
- `NativeSearchRequest` / `NativeSearchResult` 显式声明：budget_type/value、权重向量、seed、
  time_limit、score_weight、prune/use_tt/move_order/sample_limit/prob_cutoff、
  simulations/rollout_depth/uct_c/max_chance_width/progressive_widening/cpw/alpha、
  cancel_token、event_seed。
- `CancelToken` 基于 `threading.Event`；C++ 在释放 GIL 的长循环中按批次重新获取 GIL 后回调
  `is_cancelled()`。
- 结果字段区分 `backend_requested/backend_used/engine_used/fallback_reason/cancelled/overflow/board_signature`。

### S2 Rollout（接入 + 验证）
- 原生单次 `rollout_events` 与批量 `rollout_batch` 已存在；Python 侧 `native_rollout` Flag 走 `rollout_batch`。
- 本轮补充**逐位等价证据**：同一事件流下 `rollout_events` == Python 驱动 `rollout_py`（误差 < 1e-9）；
  `rollout_batch[0]` == 单次 `rollout_events`（同一游标起点）；批量确定性重复一致。
- 关键实测发现：**每次调用都传入整段事件数组的拷贝开销极大**。40 次单独 `rollout_events`
  耗时 ≈61.9ms（≈1.55ms/次），而一次 `rollout_batch(40)` 仅 0.161ms（≈4µs/次）→ 约 **385x** 差距。
  结论：必须批量化（或缓存数组），否则原生原语的收益被封装开销吞掉。

### S3 原生 Expectimax（`bitboard_cpp/search.cpp` 新增 `expectimax_exact`）
- Max/Chance 完整递归，语义对齐 Python `_expectimax_decision(prune=False)`：DIRECTIONS 顺序、
  严格 `>` 并列处理、Chance 按真实空格数与 0.9/0.1 加权、叶子用 `evaluate_bb`（指数域等价）。
- 可选**精确 TT**（键 = `bb + depth + 节点类型`），迭代加深共享 TT；`use_tt` on/off 结果一致。
- 迭代加深 + 时间预算 + 取消轮询（每 1024 节点查时间、按 `cancel_poll` 查取消）。
- **近似模式（空位采样 / 概率截断）不实现**：收到即抛 `NativeEngineNotSupported`，自动走 Python 路径，
  绝不把近似结果冒充精确。

### S4 原生 MCTS（`bitboard_cpp/search.cpp` 新增 `mcts_events`）
- P（玩家）/ C（机会）双层节点对象池；selection=UCT、expansion、simulation（rollout）、backprop 全在 C++。
- 随机事件全部来自显式事件流：spawn 消费 `(cell[i], value[i])`、选向消费 `move[i]`，单游标 `i = cursor % n`；
  与 Python 事件镜像 `_mcts_decision_events` **逐步同源**，可跨语言逐位比对。
- 渐进加宽（progressive widening）、`max_chance_width`、时间预算、协作式取消、溢出检测。
- 单线程确定性；无并行（遵守 S5 边界）。

### S5 边界
- `heuristic`/`rl` 保持 reference 与既有实现；Numba 保留 nopython 路径；不引入 CUDA/GPU/AVX2/多线程/新 GUI；
  不训练、不转换 RL 模型。

### S6–S9 见第 4–6 节。

## 3. 修改文件与核心 diff

| 文件 | 变更 |
| --- | --- |
| `solver_backends/bitboard_cpp/search.hpp` | **新增**：`ExpectimaxParams`/`MctsParams`/`SearchOut`/`SearchStats` 与两个引擎声明 |
| `solver_backends/bitboard_cpp/search.cpp` | **新增**：`expectimax_exact`（含 TT）、`mcts_events`（含事件流/取消/渐进加宽） |
| `solver_backends/bitboard_cpp/bindings.cpp` | +113 行：`native_expectimax` / `native_mcts` 绑定、`pack_out`、`make_cancel`、`gil_scoped_release` |
| `solver_backends/bitboard_cpp/bitboard.hpp` | +10 行：导出 `cell_exp` / `set_exp`（供 search.cpp 复用） |
| `solver_backends/bitboard_cpp/bitboard.cpp` | -9 行：移除重复的 `cell_exp`/`set_exp`（改在头文件） |
| `solver_backends/bitboard_cpp/CMakeLists.txt` | 编译单元加入 `search.cpp`（模块 + 自测可执行文件） |
| `solver_backends/native_api.py` | **新增**：契约、取消令牌、引擎调用适配 |
| `solver_backends/events.py` | +49 行：`NumpySpawnEventStream` 与带缓存的 `mcts_event_stream` |
| `solver_v6.py` | +267 行：`_native_expectimax_decision` / `_native_mcts_decision` / `_native_expectimax_applicable` / `_mcts_decision_events`；`_run_strategy` 分派；`engine_used` 落盘 |
| `tests/test_native_search.py` | **新增**：18 个原生搜索/失败注入测试 |
| `benchmarks/run_native_bench.py` | **新增**：公平基准脚本 |
| `.../bitboard_cpp.cp312-win_amd64.pyd` | 重新构建（191488 → 234496 bytes） |

核心 diff 全文：`git_diff_tracked.patch`；改动清单与新增文件哈希：`changed_files.txt`。

核心思路（bindings.cpp）：
```cpp
CancelFn cb = make_cancel(cancel_token);          // 释放 GIL 后按批次回调取消令牌
{ py::gil_scoped_release rel;                     // 长循环整体释放 GIL
  expectimax_exact(bb, p, w.data(), &out, &st, cb, cancel_poll); }
return pack_out(out, st, "native_expectimax");    // 一次 pybind11 往返完成整次决策
```

## 4. 正确性（S6 测试矩阵 / 门禁 N1–N4）

| 层 | 证据 | 结果 |
| --- | --- | --- |
| Primitive 65536 行表 / 四后端一致性 | `test_row_table`、`test_backend_equivalence` | PASS |
| Rollout 逐位等价 + 批量 | `NativeRolloutTest`（3） | PASS（误差 < 1e-9） |
| Expectimax 精确等价 | 方向 18/18 一致，`max_eval_dev = 0.0`；`test_exact_equivalence_prune_false` | PASS |
| Expectimax TT on/off | `test_tt_on_off_identical` | PASS（一致） |
| 近似配置不冒充 | `test_approximate_config_not_silently_approximated` | PASS（抛 NotSupported） |
| MCTS 结构逐步等价 | `test_matches_python_event_mirror`（方向/访问数/模拟数全等，8/8） | PASS |
| MCTS 回传不变量 | `test_backprop_invariants`（root_visits==sims==backprop，move_visits 求和==root） | PASS |
| 取消 | 预取消立即返回；**跨线程 150ms 后取消**（GIL 释放验证）线程及时退出 | PASS |
| 溢出回退 | 32768+32768 → 整次决策回退 reference，`backend_used=reference` | PASS |
| 失败注入 | 缺 `.pyd` 模拟、非法棋盘、无模块、极小预算 | PASS |
| GUI 回归 | `test_arrow_keys`、`test_gui_integration` | PASS |
| 隔离 | `test_storage_isolation` + 真实文件系统哈希复核 | PASS |

汇总：**V6 `unittest discover` 62 tests OK（EXIT 0）**；**V5 `test_solver` 95 tests OK（EXIT 0）**；
C++ `bitboard_tests.exe` ALL TESTS PASSED。详见 `test_results.json`、`tests_v6.log`、`tests_v5.log`。

## 5. 性能（S7 公平基准，固定工作量 + 固定墙钟）

固定工作量（同棋盘集、同评估器、同 tie-break；预热后重复 7 轮，中位数 ms）：

| 算法 / 变体 | reference | numba | python_kernel_cpp | native（整树） |
| --- | ---: | ---: | ---: | ---: |
| rollout（20×16） | 1845.36 | 2350.29 | 451.47 | **197.26**（native_rollout_batch） |
| expectimax 精确 d3（8 盘） | 165.52 | 135.42 | 100.94 | **16.09** |
| expectimax 精确 d4（6 盘） | — | — | 666.27 | **30.13** |

- Expectimax 精确 d3：native 相对 reference **≈10.3x**、相对 python_kernel **≈6.3x**；动作一致率 **1.0**。
- Expectimax 精确 d4：native 相对 python_kernel **≈22x**；动作一致率 **1.0**。
- Rollout：native 相对 reference 约 9x（reference 中位数轮间波动大，单轮曾 934ms），相对 python_kernel ≈2.3x；
  动作一致率 0.33（**随机源不同**，如实报告，不宣称等价）。
- 往返开销：batch 4µs/次 vs 单次调用 1547µs/次（≈385x）。

固定墙钟预算（中位停止延迟 = 实际耗时 − 预算）：

| 算法 / 变体 | 20ms 完成量 | 50ms | 100ms | 停止延迟 | 合法率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| expectimax python_kernel（深度） | 3 | 3 | 4 | +2~3ms | 1.0 |
| expectimax native（深度） | **5** | **5** | **5.5** | +4ms | 1.0 |
| mcts python 事件镜像（模拟数） | 31.5 | 63 | 61 | +600~1200ms | 1.0 |
| mcts native（模拟数） | **2621.5** | **10174.5** | **10598.5** | +3.4~6.5ms | 1.0 |

结论：同 20ms 预算下 native MCTS 完成约 2621 次模拟（Python 事件镜像约 31，≈83x），且停止延迟仅数毫秒，
Python 镜像因单次模拟成本高而延迟数百毫秒。以上均标 TRUNCATED，不据此推出胜率排名。

> 修复记录：首轮基准暴露「每次求解重建 65536 事件流」造成 native MCTS 在 20ms 预算下多花 ~48ms。
> 新增 `NumpySpawnEventStream` + 按 (seed,size) 缓存的 `mcts_event_stream` 后，停止延迟降到 +3~6ms。

## 6. 默认后端决策（N6，详见 `backend_policy.json`）

| 策略 | 默认后端 | 引擎 | native 建议 | 依据 |
| --- | --- | --- | --- | --- |
| heuristic | reference | reference | off | 量级极小，无收益 |
| rollout | cpp | python_kernel | off（`native_rollout` 可选） | cpp 原语 4x 且动作一致率 1.0；native 改随机源，默认保持对局行为 |
| expectimax | cpp | python_kernel（近似预设）/ native（精确） | 精确模式启用 | native 精确 10x~/22x 且一致率 1.0；近似模式 native 未实现，自动走 Python |
| mcts | cpp | native（推荐）/ python_kernel | 推荐开启 | 同预算完成模拟数 ≈83x，回传不变量/合法/取消均通过 |
| rl | reference（NumPy 推理） | reference | n/a | 不训练、不转换模型 |

`native_search` 为**显式可关闭 Feature Flag，默认 False**：既有默认求解语义与 62 个 V6 测试断言不变；
需要加速的实验/面板显式传 `native_search=True`。这符合「不强行全部启用 C++」。

## 7. 运行期与回退（S8）

- native 调用一次往返完成整树，释放 GIL，取消令牌跨线程轮询；GUI 主线程只收信号的设计未改动。
- 溢出：native 检测到 >=65536 置 `overflow` → `solve` 抛 `BoardOverflowError` → 整次决策回退 reference 重算
  （不从半棵 native 树继续，也不伪装成同一次确定性搜索）。
- 缺 `.pyd`：`probe_backends` 标记 `BUILD_BLOCKED`，`get_backend` 回退 numba→numpy→reference。
- 事件流缓存按 seed 命中，避免时间预算模式下重复生成。

## 8. 隔离（N8 / S6.6）

`isolation_before_after.json`：V1–V5 源码哈希、`rl_model.npz`、各版本 `game_history/`、`solver_results/`
真实文件系统复核 → **`isolation_pass = true`，`unexpected_changes = []`**。
本轮改动全部落在 `v6_pyqt_2048_accelerated/`；未删除/清空/覆盖任何受保护资产；未提交 Git。

## 9. 剩余风险与未验证项

- **Rollout native 随机源差异**：native 用事件流、Python 用 `random.Random`，同 seed 不保证逐次动作相同
  （一致率 0.33）。故 `native_rollout` 默认关闭；如需默认启用需另行确认对局可接受性。
- **MCTS 随机实现差异**：native MCTS 用事件流，与 V5 `random.Random` 序列不同；按 S4 以分布/合法性/
  完成模拟数比较，未宣称逐次等价。默认关闭以免改变既有对局，仅在显式 `native_search=True` 时启用。
- **native Expectimax 不含近似模式**：GUI 默认 `normal` 预设（`sample_limit=8`,`prob_cutoff=0.08`）仍走 Python；
  native 只在精确模式接入。
- **C++ 树内存未插桩**：Python `tracemalloc` 只覆盖 Python 侧分配（见 `bench_fixed_work.json` 的 `py_peak_kb`）。
  原生树内存受 `simulations×rollout_depth` 与 chance 宽度约束，但未做精确峰值测量 → 标注未验证。
- **GUI 视觉**：本轮**无 GUI/视觉改动**，未重新出整窗截图；GUI 正确性仅由自动化回归
  （`test_arrow_keys`/`test_gui_integration`）覆盖。`GUI_VISUAL` 沿用既有 **UNVERIFIED**（无新视觉声明）。
- **多 DPI（125%/150%）**：本轮未涉及，保持 UNVERIFIED。
- 基准机器为单机、单进程、默认线程环境；`reference` 轮间波动较大（尤其 rollout），已用中位数并注明。

## 10. 门禁状态（N0–N10）

| Gate | 条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| N0 | 环境/源码/模型基线冻结且证据完整 | **PASS** | `baseline_manifest.json` |
| N1 | Reference 与 CPP primitive 既有等价性通过 | **PASS** | `test_row_table`/`test_backend_equivalence` 于 62 tests 内 |
| N2 | Native Rollout fixed-events/batch/异常与取消通过 | **PASS** | `NativeRolloutTest`、`test_cancel_token` |
| N3 | Native Expectimax 精确版/缓存/概率/异常通过 | **PASS** | `NativeExpectimaxTest`（精确等价 dev=0） |
| N4 | Native MCTS Chance/UCT/Backprop/取消通过 | **PASS** | `NativeMctsTest`（结构等价 + 不变量 + 跨线程取消） |
| N5 | 公平 fixed-work/time-budget 原始基准完整 | **PASS** | `bench_fixed_work.*`、`bench_time_budget.*` |
| N6 | 每策略默认选择有实测依据；失败回退可复现 | **PASS** | `backend_policy.json` |
| N7 | V5/V6 既有测试、GUI worker/焦点/提示与关闭无回归 | **PASS** | V6 62 OK；V5 95 OK |
| N8 | V1–V5 代码、存档、模型、锁文件无意外修改 | **PASS** | `isolation_before_after.json`（pass=true） |
| N9 | 源码、构建、报告与可重现命令齐全；声明与门禁一致 | **PASS** | 本报告 + `test_commands.txt` + `capability_matrix.md` |
| N10 | 自动 GUI 截图结构/文本 + 人工视觉 + 真实多 DPI | **PARTIAL / UNVERIFIED** | 本轮无 GUI 改动，未出图；沿用既有 UNVERIFIED，无新视觉声明 |

**未通过/未验证项明确标注**：N10 为 PARTIAL（无 GUI 改动即无新视觉证据；不冒充 PASS）；C++ 树内存峰值未测量；
真实多 DPI 视觉未测。

## 11. 复现

见 `test_commands.txt`。核心复现：

```powershell
$env:PYTHONNOUSERSITE="1"
cd e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated
python -m unittest discover -s tests          # 62 OK
cd ..\v5_pyqt_2048_solver; python -m unittest test_solver   # 95 OK
cd ..; python v6_pyqt_2048_accelerated\benchmarks\run_native_bench.py `
    --out-dir v6_pyqt_2048_accelerated\experiments\v6_2\20261012_051008 --repeats 7 --max-boards 12
```
