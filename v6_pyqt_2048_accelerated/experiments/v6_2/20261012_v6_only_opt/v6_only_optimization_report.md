# V6/V6.2 单程序优化报告（本轮）

> 目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_v6_only_opt/`
> 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
> 说明：本文件为**真实执行结果**。未通过的项一律保留 FAIL/UNVERIFIED，不冒充通过。

---

## 0. 本轮范围与归档

- **停止**并**安全归档**「V5.1↔V6.2 双窗口并排竞赛 / V5 界面改造 / 竞赛 HUD / 进程协调」方向：
  - 代码：`v6_pyqt_2048_accelerated/comparison/` → `archive/comparison_v5v6_race_20261012/comparison/`
  - 数据：`v6_pyqt_2048_accelerated/experiments/race/` → `.../race_experiments/`
  - 说明：`archive/comparison_v5v6_race_20261012/ARCHIVE_NOTE.md`（只移动，未删除/未覆盖）
- 本轮**只优化 V6/V6.2**；V1–V5 全部保持只读（未修改任何 V1–V5 源文件）。

## 1. P1 稳定性诊断（单程序复现）

**方法**：在**真实 V6 正式 GUI** 内自动连走，探针以 monkeypatch 包裹实例方法并记录时间线
（不改 V6/V5 源码），隔离存档与会话；安装 `faulthandler` 与自定义 `sys.excepthook`。
脚本：`diagnostics/qt_stability_probe.py`、`diagnostics/cancel_stress.py`。

**结果**（`diagnostics_summary.json`，原始时间线在 `diagnostics/runs/`）：

| 运行 | 规模 | raises | 过期结果 | 退休线程峰值 | excepthook/faulthandler 输出 | 退出 |
| --- | --- | --- | --- | --- | --- | --- |
| t1 自动连走 | 98 步 / 46s | 0 | 0 | 0 | 无 | 正常 |
| t2 自动连走 | 113 步 / 61s | 0 | 0 | 0 | 无 | 正常 |
| t3 自动连走 | 190 步 / 121s | 0 | 0 | 0 | 无 | 正常 |
| 取消/生命周期压力 | 40 轮求解中停止 + 每 10 轮热切换算法 + 求解中关窗 | 0 | 0 | 0 | 无 | 正常 |

- 累计 **401 步**真实自动连走 + 40 轮取消压力，**未复现** `Qt5Core.dll 0xC0000409`。
- 关键不变量实测成立：`_shutdown_worker` 每次都在预算内回收线程（`max_retired=0`）；
  无「QThread destroyed while running」；无过期作业结果驱动棋盘；无被 `is_animating()` 丢弃的决策；无槽异常。
- 该崩溃签名的**原始记录**（Windows 事件日志）为 `Qt5Core.dll` / `0xc0000409` / 偏移 `0x204e8`，
  且在**本任务开始前**（2026-10-12 02:56）已出现过一次；本轮崩溃记录均出现在**两个 Qt GUI 进程并发**
  （双窗口竞赛）期间。

**结论（不越界）**：现有证据**不支持**“V6 单程序自身存在必然的 QThread/取消/生命周期缺陷”这一判断；
崩溃更可能与**同时运行多个 Qt GUI 进程**相关。**未取得崩溃转储（dump）或 Qt 致命信息文本，故不宣布确定根因**；
单程序复现为 FAIL（未能复现），需要多进程 Qt 或 Qt 内部状态才能稳定触发的假设仍属未证实。

## 2. P2 V6 三档运行速度（可持久化）

**实现**：新增 `v6_speed.py`（`V6SpeedMixin`），V6 入口以 `V6MainWindow(V6SpeedMixin, SolverMainWindow)`
最小接线；**不改 V5/V6 既有源码文件逻辑**。UI 在「高级参数」内新增「运行速度」下拉；选择持久化到
`config/ui_prefs.json`（ASCII 名、UTF-8）。

| 档位 | 走子动画 | 步间等待 | 指标刷新 |
| --- | --- | --- | --- |
| 标准展示 standard | 开 | 70ms | 每步 |
| 快速演示 fast | 开 | 10ms | 每 2 步 |
| 极限性能 extreme | **关** | **0ms** | 每 8 步（批量更新） |

极限性能的推进仍由 **0ms 定时器逐轮驱动**（每轮一次有界决策），**非主线程死循环**，故停止/暂停/重置可即时响应。

**分段计时**（`perf_counter`，累计 ms）：搜索（发起决策→收到结果）/ 动画（落子→动画结束）/
固定等待（动画结束→下一次发起）/ 渲染（`refresh` 调用累计）/ 总耗时 / 步数。实测（每次 20s，Expectimax normal）：

| 档位 | 步数 | steps/s | 搜索累计 | 动画累计 | 等待累计 | 渲染累计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| standard | 42 | 2.05 | 1047 | 14534 | 3200 | 2.7 |
| fast | 49 | 2.34 | 1442 | 16836 | 1053 | 3.0 |
| extreme | **136** | **6.62** | 4846 | 10623 | 3134 | 11.5 |

- 极限档相对标准档 **≈3.2x** 步进吞吐，并**完全去除动画等待**（anim 由 ~346ms/步 降到 ~78ms/步）。
- 说明（诚实标注）：extreme 下「动画」段实际是**关闭动画后的立即落子路径（含模型逐子持久化/fsync）**，
  并非动画开销；`渲染`段仅计 `refresh()/render()` 调用本身，**不含 Qt 后续 paintEvent 绘制**；
  故 extreme 的瓶颈落在**模型每步存档 fsync**（V3/V4 模型行为，只读，不改动）。

## 3. P3 原生搜索收口

- Rollout 批量化：`native_rollout` 经 `rollout_batch` 一次跨边界完成 N 次；结果新增
  `engine_used='native_rollout'`（**明确区别于 native 整树**），非 native 时为 `python_kernel`。
- Expectimax 适配范围：仅精确语义（prune=False 或 sample_limit/prob_cutoff=0）走 native；
  近似配置**显式回退**并写入 `native_skip_reason`（不再静默）。
- MCTS：`native_search=True` 且后端非 cpp 时记录 `native_skip_reason='backend!=cpp'`。
- auto 后端与反馈：结果稳定携带 `backend_requested/backend_used/backend_fallback_reason/engine_used`；
  溢出→整次回退 reference；缺 .pyd→BUILD_BLOCKED→回退（既有测试覆盖）。
- **明确回退**：native 不可用或未通过的路径一律回退 Python/reference，并带原因字段。

## 4. P4 公平基准（隔离、顺序、无动画混入）

`benchmarks/run_native_bench.py`（同棋盘集/同工作量/同事件流；预热后 7 轮；记录 median/p95、
吞吐、决策一致率、Python 峰值、进程峰值工作集、实际 engine）：原始见
`bench_fixed_work.{json,csv}`、`bench_time_budget.{json,csv}`、`benchmark_metadata.json`。

固定工作量（中位 ms，12/8/6 盘）：

| 算法/变体 | reference | numba | python_kernel_cpp | native | 一致率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| rollout 20×16 | 988.3 | 1683.2 | 265.6 | **97.9**(native_rollout_batch) | 0.33（随机源不同，如实报告） |
| expectimax 精确 d3 | 111.6 | 98.7 | 62.0 | **10.8** | 1.0 |
| expectimax 精确 d4 | — | — | 463.6 | **14.7** | 1.0 |

往返开销（同一事件流）：`native_batch` 0.111ms / 40 次（2.77µs/次） vs 单次循环 30.85ms →
批量约 **277x** 更省封装开销。

固定墙钟（中位停止延迟 / 完成量）：

| 算法/变体 | 20ms | 50ms | 100ms | 停止延迟 | 合法率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| expectimax python_kernel（深度） | 3.0 | 3.0 | 4.0 | +1.5~1.9ms | 1.0 |
| expectimax native（深度） | 5.0 | 5.0 | 6.0 | +2.1~3.5ms | 1.0 |
| mcts python 事件镜像（模拟数） | 60.0 | 90.5 | 231.0 | +406~425ms | 1.0 |
| mcts native（模拟数） | **4919** | **11375** | **23783** | +1.8~3.6ms | 1.0 |

> 基准仅比较**算法耗时**，不含任何 GUI 动画时间。

## 5. P5 四阶段回归门禁

| 阶段 | 内容 | 真实命令/证据 | 结果 |
| --- | --- | --- | --- |
| 1 稳定性 | 单程序自动连走 + 取消/生命周期压力 | `diagnostics/qt_stability_probe.py` / `cancel_stress.py` | 401 步 + 40 轮压力 **PASS**；**0xC0000409 单程序复现 FAIL（未复现）** |
| 1 回归 | V5 既有测试（只读） | `v5_pyqt_2048_solver: python -m unittest test_solver` | 见 `tests_v5.log`（EXIT 见 test_results） |
| 1 回归 | V6 全量 | `v6_pyqt_2048_accelerated: python -m unittest discover -s tests` | **62 tests OK**（`tests_v6.log`） |
| 1 回归 | V6 原生搜索 | `python -m unittest test_native_search` | 18 tests OK |
| 1 构建 | C++ 自测 | `bitboard_tests.exe` | ALL TESTS PASSED（上一轮，本轮未改 C++） |
| 2 三档速度 | 三档分段计时 | `diagnostics/runs/*tier*` | **PASS**（见 §2，各自 `stalls=0`） |
| 3 原生搜索 | 正确性/回退/engine 标注 | `test_native_search` + 本轮 patch | **PASS** |
| 4 公平基准 | 固定工作量 + 固定时间 | `bench_fixed_work.*` / `bench_time_budget.*` | **PASS**（见 §4） |

## 6. 本轮修改清单

| 文件 | 变更 |
| --- | --- |
| `v6_speed.py` | **新增**：三档速度、分段计时、持久化、极限档无动画立即落子 |
| `v6_pyqt_2048_accelerated.py` | 继承 `V6SpeedMixin`；`init_ui` 末调用 `_v6_speed_init()`（+2 行） |
| `solver_v6.py` | rollout 增加 `engine_used='native_rollout'`；expectimax/mcts 在 native 未用时写入 `native_skip_reason` |
| `benchmarks/run_native_bench.py` | 记录 `engine_used/backend_used/peak_ws_mb` |
| `diagnostics/qt_stability_probe.py` | **新增**：单程序稳定性探针（不改 V6/V5 源码） |
| `diagnostics/cancel_stress.py` | **新增**：取消/生命周期压力 |
| `archive/comparison_v5v6_race_20261012/` | **归档**：comparison 代码 + race 实验数据 + ARCHIVE_NOTE.md |

> 未改动 V1–V5 任何源文件；未改动 C++ 原生内核（本轮）。

## 7. 未验证 / 风险（明示）

- **UNVERIFIED**：`Qt5Core.dll 0xC0000409` 的**确定根因**（单程序未复现，无 dump）。
- **UNVERIFIED**：真实多 DPI（125%/150%）下的三档速度与视觉。
- **UNVERIFIED**：extreme 档「渲染」段不含 paintEvent；其真实瓶颈为模型逐子 fsync（未做磁盘级隔离测量）。
- **已知副作用**：三档速度会写入 `config/ui_prefs.json`，GUI 测试可能受其影响而变快（不影响断言）。
- 人工视觉确认（三档速度观感、HUD 布局）保持 **UNVERIFIED**。
