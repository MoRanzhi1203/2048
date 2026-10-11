# 2048 V6.1 最终报告：原生搜索性能、基准审计与版本隔离收口

- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`
- 解释器：`E:\anaconda3\envs\2048\python.exe`（Python 3.12.3、numpy 1.26.4、numba 0.60.0、llvmlite 0.43.0），`PYTHONNOUSERSITE=1`
- git HEAD（前=后）：`0296ab2f…`（main），**未提交/推送**
- 最终状态：**PARTIAL_PASS**（全部强制门禁通过；仅人工视觉/DPI = UNVERIFIED）

---

## 一、实际修改（仅 V6，共 6 个文件）

| 文件 | 类型 | 变更 |
| --- | --- | --- |
| `solver_backends/bitboard_cpp/bitboard.cpp` | 修复 | `rollout_events` 空位枚举改为**行主序(左→右)**，与 Python `empty_cells` 对齐 |
| `solver_backends/bitboard_cpp/bindings.cpp` | 新增 | 绑定 `rollout_batch`（一次调用完成一组 rollout） |
| `solver_backends/bitboard_cpp/bitboard_cpp.cp312-win_amd64.pyd` | 重编译 | Release 重编译；`bitboard_tests` 全通过；SHA `3c1b4164…`（旧 `50ad7588…`） |
| `solver_backends/bitboard_cpp_backend.py` | 新增 | `supports_native_rollout=True` + `rollout_events/rollout_batch` 薄适配层 |
| `solver_backends/api.py` | 新增 | `BackendBase.supports_native_rollout=False` 协议默认 |
| `solver_v6.py` | 修改 | ① 可选 `native_rollout`；② 修复溢出预检查未回退；③ 修复异常安全网误用异常后端；④ `auto` 分策略默认（heuristic/rl→reference，rollout/expectimax/mcts→cpp） |

V1–V5 源码、四份 RL 模型、`tools/capture_gui.py`、全部测试文件：**未改动**。前后 SHA256 对照见 `changed_files_v6_1.json`。

## 二、原因（定位依据）

H9-2 有界剖析（`profiles/search_profile.json`，分层取样，接口调用计数 + cProfile）显示：

- **rollout（cpp）单盘约 3,800 次后端原语调用**；Python 侧 `_flatten/_unflatten` 与纯 Python 的 `empty_cells/is_game_over/sample_spawn` 占显著开销——即“节点级 Python↔原生频繁边界”是热点。
- C++ 已暴露原生整段 rollout `rollout_events`，但**从未被任何 Python 代码调用**（死接口），且其空位顺序与 Python 不一致 → 不可直接等价替换。
- 两个**可重现缺陷**（见 known_issues §4）：溢出预检查未回退、异常安全网误用异常后端。

## 三、前后实测

### 3.1 内核微基准（`benchmarks/micro.csv`，48 盘、warmup=3/repeat=30，中位 µs/迭代→每单位）

| 内核 | reference | numpy | numba | cpp | cpp/ref |
| --- | ---: | ---: | ---: | ---: | ---: |
| move_all_dirs | 1722.9 | 56520.2 | 3461.5 | 1397.8 | 1.23× |
| legal_moves | 3473.0 | 35798.4 | 3028.3 | 208.4 | **16.67×** |
| evaluate | 3108.6 | 11262.3 | 434.8 | 412.3 | **7.54×** |
| batch_move_left | 525.8 | 4314.1 | 769.3 | 301.2 | 1.75× |
| rollout_py_d40 | 106550.4 | 911551.9 | 172314.8 | 26491.8 | **4.02×** |

冷启动(ms)：reference 1.36 / numpy 3.92 / numba 26.85 / cpp 7.67。

### 3.2 固定工作量搜索（`benchmarks/search_fixed_work.csv`，48 盘，同算法/同工作量，动作一致率以 reference 为基准）

| 算法 | reference 中位 | cpp 中位 | cpp 加速 | 动作一致率 |
| --- | ---: | ---: | ---: | ---: |
| rollout(20×16) | 85.39ms | 31.49ms | **2.71×** | 1.00 |
| rollout + native_rollout | （同上） | 11.92ms | **7.16×** | 0.48（分布等价，见 §四） |
| expectimax(prune=False,d3) | 16.27ms | 7.44ms | **2.19×** | 1.00 |
| mcts(60 sims) | 41.14ms | 20.56ms | **2.00×** | 1.00 |
| heuristic | <0.05ms | <0.05ms | — | 1.00 |

> numba：expectimax 1.72×（评估密集）；rollout/mcts 反而更慢（0.34/0.38×）。numpy 全策略净慢（0.07~0.13×）。
> **方差说明**：本机共享负载，rollout cpp 两次独立运行 2.15×~2.71×（reference 中位 85~107ms）；仅报中位数，不作精确倍数承诺。历史（19:17 批次）曾报 rollout 3.09× / expectimax 2.67× / mcts 1.84×，量级一致。

### 3.3 固定墙钟小样本（`benchmarks/time_budget_smoke.csv`，smoke 2 局/策略，max_moves=200，20ms/步）

全部 `TRUNCATED`（步数上限，仅工程回归，不作显著性结论）：rollout ref 步均 90.3ms vs cpp 37.3ms；heuristic/expectimax/mcts/rl 后端差异小或相当。

## 四、数学等价证明

- **65536 行表**：numpy/cpp 与冻结 V5 `slide_line` 逐项一致：非溢出 64,769 行 **0 mismatch**，溢出标志 **0 mismatch**（767 溢出行按官方口径跳过行结果、单独校验标志）。
- **随机棋盘**：10,000 盘 × 4 方向 + legal，reference vs cpp/numba **0 mismatch**。
- **协议边界**：非 4×4 / 非 2 幂 / 布尔 / 负数 / 浮点 / NaN 全部拒收；入参不被原地修改。
- **五策略等价**：heuristic/rollout(固定 seed)/expectimax(prune=False)/mcts(固定 seed)/rl 的 `best_direction` 跨四后端一致且与 V5 一致；MCTS 不变量 `root_visits == completed == backpropagated == Σroot_move_visits` 成立。
- **原生 rollout 等价（同事件流）**：C++ `rollout_events` 与 Python 事件流驱动在同一 `SpawnEventStream`、同起点下 **141 次比较 0 mismatch（max_abs_diff=0.0）**（`profiles/rollout_events_equivalence.json`）。
- **原生 rollout 分布等价（随机模式）**：三代表盘多种子下 native vs reference 均值相对差 0.15% / 0.97% / 0.18%，标准差相当（`profiles/native_rollout_distribution.json`）。
- **权重/口径**：`_weight_array` 与 C++ `evaluate_bb` 权重顺序 `[empty,monotonicity,smoothness,merge,corner,snake,danger]` 一致；评估 10,000 盘 6 位小数一致。

## 五、回退结果（`correctness_results.json` / `profiles/fallback_chain.json`）

| 场景 | 结果 |
| --- | --- |
| 盘含 ≥65536（cpp） | 预检查即回退：`backend_used=reference`，reason 含 `BoardOverflow`（**修复前会直接抛异常**） |
| 相邻 32768 合并→65536 | cpp 显式抛 `BoardOverflowError`（不静默截断） |
| cpp/numba 不可用 | 按 `numba→numpy→reference` 回退首个可用后端并记录真实原因 |
| 原生调用异常 | 安全网改用 reference 重算；`backend_used=reference`、记录 `error`，**不崩溃**（修复前会二次失败冒泡） |

## 六、版本隔离（`storage_isolation.json`）

- 真实 V1–V5 目录（`v5/solver_results`、`v5|v4|v3/game_history`、`.instance.lock`）前后快照：**无新增/删除/内容变更**（全部 `ok=true`）。
- 四份模型 SHA256 前后一致。
- 隔离子进程（唯一 `2048_HISTORY_DIR=<temp>`）完成 导入→构造窗口→新游戏→走子→AI 单步(cpp)→折叠/展开→保存→导出→关闭→退出，返回码 0；写入全部落在 `<temp>/v6` 与 V6 `solver_results/`。
- **V6 一侧显式隔离 V5 模块级 `RESULT_DIR/SESSIONS_FILE`**（覆写会话/导出的加载保存），非仅存档次目录。

## 七、GUI / QThread / 回归

- **测试**：V6 32 项（含 GUI 集成/存档隔离/后端等价/搜索等价）**全通过**；V5 只读套件 `test_solver` **80 项全通过**。见 `tests.log` / `v5_regression.log`。
- **QThread**：源码无 `QThread.terminate()`（仅“不使用”注释）；V5 既有 H7-2/C03/C04/C06 线程与取消测试通过。
- **降级链**：cpp/numba 不可用、原生异常、溢出、后端缺失均能报真实 `backend_used/fallback_reason` 并返回合法结果（§五）。
- **整窗截图**（真实 Windows，screen BitBlt + DWM 外框）：`full_start/game/solver/collapsed.png` 四场景，`CAPTURE/STRUCTURE/TEXT=PASS`；`VISUAL/DPI=UNVERIFIED`（`gui_capture.jsonl`）。

## 八、门禁（`release_gates.json`）

| 门禁 | 状态 |
| --- | --- |
| G0 SOURCE_BASELINE | PASS |
| G1 RULE_AND_ALGO_PARITY | PASS |
| G2 NATIVE_HOTPATH | PASS |
| G3 SEARCH_BENCH_FAIRNESS | PASS |
| G4 FALLBACK_AND_OVERFLOW | PASS |
| G5 STORAGE_ISOLATION | PASS |
| G6 GUI_QTHREAD | PASS |
| G7 GUI_AUTOMATED | PASS |
| G8 GUI_VISUAL_AND_DPI | UNVERIFIED |
| G9 REPORT_INTEGRITY | PASS |
| G10 V6_1_RELEASE_READY | **PARTIAL_PASS** |

## 九、每策略后端推荐（`backend_policy_v6_1.json`）

| 策略 | 推荐 | 依据 |
| --- | --- | --- |
| heuristic | reference | 单步 <50µs，后端差异无意义 |
| rollout | **cpp**（2.15~2.71×，一致率 1.0） | 可选 `native_rollout`（7.16×，分布等价、序列不同，默认关闭） |
| expectimax | **cpp**（2.19~2.31×；numba 1.34~1.72× 可选） | 动作一致率 1.0 |
| mcts | **cpp**（2.00~2.69×） | 树结构保持 Python，仅换原语；回传不变量保持 |
| rl | reference | 前向网络由 V5 `rl_2048` 提供，后端不参与其数值 |

> **不得统一宣传为“C++ 全部最快”**：heuristic/rl 无端到端收益，维持 reference；numpy 全策略更慢；numba 仅 expectimax 受益。旧版 `backend_default.json` 保留为对照，未覆盖。

## 十、遗留事项

- GUI 人工视觉核对与真实 125%/150% DPI 实测（保持 `UNVERIFIED`）。
- Expectimax 原生子循环（“move+eval”合并原语）下沉——需独立精确参考门禁，本轮未做。
- 每配置 100/300 局大规模对局实验——按指令**未执行**。
- 本轮**未**重训 RL、未重构 UI、未修改旧版本、未自动 git 提交。
