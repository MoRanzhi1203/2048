# 2048 V6 交付报告（G0–G9 门禁）

> V6 = 基于 V5.1 稳定成果的 NumPy / Numba / C++ Bitboard 高性能架构升级。
> 本文所有结论均可由 `audit/`、`benchmarks/reports/`、`tests/`、`screenshots/` 下的原始证据复现。

## 一、版本范围 / 工作树保护

- **V1–V5 源码、`test_solver.py`、`tests/`、`tools/`(除新增 v6 条目)、四份 RL 模型、全部真实存档：未修改。**
  git 前后一致（[audit/git_v6_before.txt](audit/git_v6_before.txt) / [audit/git_v6_after.txt](audit/git_v6_after.txt)）：
  `HEAD=2f6ca9b`，工作区仅 ` M tools/capture_gui.py`（新增 v6 登记，+9 行）与未跟踪的 V6 目录。
- **V6 增删改**：见 [changed_files.md](changed_files.md)（全部为 V6 新增 + capture_gui 的 v6 登记）。
- V6 数据落点：`v6_pyqt_2048_accelerated/{game_history,solver_results,screenshots}`；通过
  `2048_HISTORY_DIR` 使 v3/v4/v5 继承链的存档目录也重定向到 V6 目录内。
- 未执行任何 git commit/push/tag。

## 二、V5 基线核验（工作区**重跑**）

- unittest **113** 项通过（test_solver 80 + expectimax 10 + mcts 10 + rl_gradients 8 +
  rl_model_management 5），另 4 个脚本套件（algorithm_benchmark_smoke / cross_version /
  popups / rl_selftrain）PASS；**0 失败 / 0 跳过**。详见 [audit/audit_v0.md](audit/audit_v0.md)。
- 未按上传文档宣称的“187”硬编码；以重跑真实数量为准。

## 三、V6 正确性

- **规则/行表**（[tests/test_row_table.py](tests/test_row_table.py)）：65536 个 16-bit 行状态，
  NumPy / Numba / C++ 三种行表与冻结 V5 `slide_line` **逐项一致（结果行、得分、溢出标志 0 mismatch）**。
- **随机棋盘**（[tests/test_backend_equivalence.py](tests/test_backend_equivalence.py)）：
  Reference vs Numba/C++ 10,000 盘×4 方向 + legal；Reference vs NumPy 10,000 盘(左移)+1,000 盘(4 方向)；
  评估函数 Reference vs C++/Numba 10,000 盘、vs NumPy 2,000 盘；**全部一致**。
- **协议边界**：非 4×4 / 非 2 的幂 / 布尔 / 负数 / 浮点 / NaN 均被拒绝；入参不被修改；
  `>=65536` 参考可表示、位棋盘后端显式拒绝（含“相邻 32768 合并溢出”）。
- **搜索等价**（[tests/test_search_equivalence.py](tests/test_search_equivalence.py)）：
  heuristic / rollout(固定 seed) / expectimax(prune=False) / mcts(固定 seed) 在四后端下 best_direction
  一致且与 V5 一致；MCTS 回传不变量 `root_visits==completed==backpropagated` 成立；RL 返回合法动作。
- **失败示例**：无（所有等价用例 0 mismatch）。过程中发现 1 处“rollout 触达 65536 时误退化为
  heuristic”的问题，已改为**显式回退 reference 重算**（见第四节）。

## 四、后端状态（BUILD / PARITY / AVAILABLE）

| 后端 | AVAILABLE | BUILD | PARITY（vs reference） |
| --- | --- | --- | --- |
| reference | ✅ | 纯 Python（无需构建） | 基准 |
| numpy | ✅ | 纯 Python（numpy 1.26.4） | ✅ 65536 行表 + 随机盘一致 |
| numba | ✅ | nopython（5 个签名，cache=True） | ✅ 一致 |
| cpp | ✅ | MSVC 2022 + CMake 3.28 + pybind11 3.1 Release | ✅ 一致；溢出显式拒绝 |

C++ 产物 SHA256：`50ad758805d0a9ba5356ba8f04c6c197d8f1f2c8f54712ed18c5785d229b825c`。

## 五、微基准结果（`benchmarks/reports/micro_*`）

冷启动(ms)：reference 2.6 / numpy 5.5 / numba 38.0 / cpp 11.8。
热态每单位中位耗时见 [benchmarks/reports/summary.md](benchmarks/reports/summary.md) 第 1 节：
cpp 相对 reference：legal_moves ~17×、evaluate ~7.2×、rollout(d40) ~14×；NumPy 在 4×4 上净变慢（5–15×）。

## 六、搜索与小游戏

- 同工作量搜索（`run_search`）：cpp vs reference rollout **3.09×**、expectimax(prune=False d3) **2.67×**、
  mcts(60 sims) **1.84×**；动作一致率 **1.0**。固定工作量（非固定墙钟）。
- 同墙钟预算小样本（`run_pilot --mode smoke`，2 局/算法，max_moves=200，20ms/步）：
  全部 `TRUNCATED`（步数上限），分数见 summary 第 3 节；cpp rollout 平均步耗时 29.08ms vs reference 79.85ms。
  明确标注：小样本仅工程回归，不作显著性结论；`TRUNCATED` 不与 `FINISHED` 混比。

## 七、GUI 状态

- 四状态整窗截图（含原生标题栏）：`screenshots/full_{start,game,solver,collapsed}.png`。
  自动门禁 `CAPTURE_PASS / STRUCTURE_PASS / TEXT_PASS` 均 **true**（见各截图的 capture JSON 记录）。
- `VISUAL_PASS = UNVERIFIED`（需人工核对图像后加 `--visual-confirm` 授予）；`DPI_VISUAL = UNVERIFIED`。
- QThread 真实链路：reference 与 cpp 后端各跑通一次“开始→单步建议→停止”。
- 折叠/展开 20 次无异常；两种入口（左「AI 求解」按钮 / 贴边把手）均只展开、不自动求解。
- 存档隔离：会话原子保存 + `.bak` 回退、导出落到 V6 目录；未写 v1–v5 目录；未创建/覆盖模型。

## 八、推荐默认后端

**默认 = `cpp`（不可用或遇到 >=65536 时回退 reference）**。依据：正确性门禁全 PASS + 端到端延迟显著改善
（2.7–3.1×）+ 构建可复现 + 溢出可显式回退 + 内存可接受。详见
[benchmarks/backend_default.json](benchmarks/backend_default.json)。NumPy/Numba 保留为对照/可选，不默认。

## 九、G0–G9 门禁表

| 门禁 | 验证范围 | 结果 | 证据 |
| --- | --- | --- | --- |
| G0 SOURCE_AUDIT | 工作区隔离、V5 文档/源码差异、哈希 | **PASS** | audit/audit_v0.md, audit/v5_sha256.json |
| G1 RULE_EQUIVALENCE | 65536 行表、≥10,000 单盘、超界、生成事件 | **PASS** | tests/test_row_table.py, tests/test_backend_equivalence.py |
| G2 ALGORITHM_EQUIVALENCE | Expectimax 参考、MCTS 回传、RL、合法动作 | **PASS** | tests/test_search_equivalence.py |
| G3 NUMBA_BUILD | nopython 编译、正确性、冷/热态 | **PASS** | micro 报告 cold_init_ms, numba.nopython_signatures |
| G4 CPP_BUILD | Windows C++20 pybind11 编译、导入、规则一致 | **PASS** | BUILD_WINDOWS.md, bitboard_tests, cpp 行表/随机盘一致 |
| G5 MICRO_BENCH | 相同接口/批量频率、初始化/转换成本 | **PASS** | benchmarks/reports/micro_* |
| G6 SEARCH_BENCH | 同工作量与同时间预算区分 | **PASS** | benchmarks/reports/search_*, pilot_smoke_* |
| G7 GUI_AND_ISOLATION | 双栏 GUI、QThread、数据路径、截图与隔离 | **PARTIAL_PASS**（自动 PASS；`VISUAL=UNVERIFIED`） | screenshots/*, tests/test_gui_integration.py, tests/test_storage_isolation.py |
| G8 REPORT | 原始输出、机器参数、统计限制、文档 | **PASS** | 本报告 + 功能说明/README/known_issues/summary |
| G9 RELEASE_CANDIDATE | 后端选择有证据；人工视觉独立透明 | **PARTIAL_PASS**（视觉待人工确认） | backend_default.json |

> 说明：**未标注 `FULL_BACKENDS_PASS`** 以外的不实结论；C++ 构建成功故非 `BUILD_BLOCKED`。
> 未进行人工目视 → `GUI_VISUAL=UNVERIFIED`；未实测高 DPI → `DPI_VISUAL=UNVERIFIED`。未捏造 PASS。

## 十、未完成 / 后续

- GUI 人工视觉确认与高 DPI 实测（`UNVERIFIED`）。
- 每配置 100/300 局的大规模对局实验（**非本轮默认要求**，未执行）。
- MCTS/Expectimax 原生整树搜索、批量 rollout 接入算法主循环（见 [future_roadmap.md](future_roadmap.md)）。
- 本地双人 / 人机 / 联网对战（明确不在本轮范围）。
