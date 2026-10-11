# V6.2 能力矩阵（capability matrix）

> run_id `20261012_051008`；基线 HEAD `d9efa4e1187f761f3fb69026c090f7a92dc2a052`
> （V6 改动前）；`bitboard_cpp` 扩展在 V6.2 重新构建，`.pyd` SHA256 =
> `3AF643073EE9A6777A75DA2EE5F80AB0DEE682C7A5E5249B84202EAD65D25172`。
> 状态：EXISTING（改动前已存在）/ PARTIAL（部分）/ MISSING（不存在）/ NEW（V6.2 新增）。

## 1. C++ Bitboard 原语

| 能力 | 状态 | 位置 |
| --- | --- | --- |
| 65536 行查表 + 4 方向 move（4bit 指数，>=65536 显式拒绝） | EXISTING | `solver_backends/bitboard_cpp/bitboard.cpp` `Tables::Tables` / `move_bb` |
| 启发式评估（指数域，等价 V5 口径） | EXISTING | `bitboard.cpp` `evaluate_bb` |
| legal_moves / is_game_over / encode / decode | EXISTING | `bitboard.cpp` / `bindings.cpp` |
| batch_move（一次跨边界多盘） | EXISTING | `bindings.cpp` `batch_move` |

## 2. 原生 Rollout

| 能力 | 状态 | 位置 |
| --- | --- | --- |
| 单次原生 rollout（消费显式事件流） | EXISTING | `bitboard.cpp` `rollout_events` |
| 批量原生 rollout（共享游标一次调用） | EXISTING（V6.1 内核） | `bitboard.cpp` `rollout_batch` + `bindings.cpp` `rollout_batch` |
| Python 侧接入（`native_rollout` 受控 Flag → `rollout_batch`） | EXISTING / 本轮验证 | `solver_v6.py` `_rollout_decision` |
| 事件流语义等价（native single == Python 驱动） | NEW 证据 | `tests/test_native_search.py::NativeRolloutTest` |

## 3. 原生整树搜索（V6.2 新增）

| 能力 | 状态 | 位置 |
| --- | --- | --- |
| C++ 原生 Expectimax 整树（Max/Chance 递归，精确模式） | **NEW** | `bitboard_cpp/search.cpp` `expectimax_exact` + `search.hpp` |
| Transposition Table（紧凑键：bb + depth + 节点类型） | **NEW** | `search.cpp` `TTKey` / `ex_max` / `ex_chance` |
| C++ 原生 MCTS 整树（P/C 双层节点、UCT、渐进加宽、事件流采样） | **NEW** | `search.cpp` `mcts_events` / `mcts_descend` / `mcts_rollout` |
| 取消令牌（协作式，跨线程原子语义） | **NEW** | `search.cpp` `ex_poll` / `mcts_poll` + `bindings.cpp` `make_cancel` |
| 时间预算停止（墙钟） | **NEW** | `search.cpp` `now_ms` + 每模拟/每批次检查 |
| GIL 释放（长循环跨边界只进一次） | **NEW** | `bindings.cpp` `py::gil_scoped_release` |
| 溢出检测（>=65536 -> 整次决策回退 reference） | **NEW（native 层）** | `search.cpp` 置 `overflow` → `solver_v6.py` 抛 `BoardOverflowError` |

## 4. 契约与适配层

| 能力 | 状态 | 位置 |
| --- | --- | --- |
| `NativeSearchRequest` / `NativeSearchResult` 契约 | **NEW** | `solver_backends/native_api.py` |
| `CancelToken`（threading.Event） | **NEW** | `solver_backends/native_api.py` |
| 引擎调用适配（扩展 -> 结果对象） | **NEW** | `native_api.run_expectimax` / `run_mcts` |
| 快速事件流（NumPy Generator + 缓存） | **NEW** | `solver_backends/events.py` `NumpySpawnEventStream` / `mcts_event_stream` |
| MCTS 事件镜像（逐次等价性验证用） | **NEW** | `solver_v6.py` `_mcts_decision_events` |
| `engine_used` 字段（native / python_kernel / reference） | **NEW** | `solver_v6.py` `solve` / `_native_*_decision` |

## 5. 逐项对照（V6.2 指令 S0.2 要求）

| 能力 | 状态 | 备注 |
| --- | --- | --- |
| primitive move/evaluate | EXISTING | 沿用，未改动语义 |
| native single rollout | EXISTING | 语义未改 |
| batch rollout | EXISTING | V6.1 有内核但未接入 → 本轮完成接入与验证 |
| native expectimax | **MISSING → NEW** | 原为 Python 每次 `backend.move()`，现为 C++ 整树 |
| native mcts | **MISSING → NEW** | 原为 Python 循环，现为 C++ 整树 |
| cancel/progress | PARTIAL → NEW | 原仅时间预算；现新增协作式取消令牌 + 时间预算 |
| transposition table | PARTIAL → NEW | 原仅 Python expectimax；现 native 精确模式带 TT |
| GIL release | MISSING → NEW | native 长循环释放 GIL |

## 6. 仍未实现 / 边界（不冒充完成）

- native Expectimax **近似模式**（空位采样 `sample_limit`、概率截断 `prob_cutoff`）未在 C++ 实现；
  收到近似配置时 `native_api.run_expectimax` 抛 `NativeEngineNotSupported`，由 `solver_v6._run_strategy`
  自动走 Python 路径（不静默近似）。GUI 默认 `normal` 预设即为近似模式，故 expectimax 默认仍走 Python。
- native MCTS **随机序列与 V5 `random.Random` 不同**（改用显式事件流）。算法结构/UCT/回传不变量一致，
  但同 seed 不保证与 V5 逐次动作相同；按 S4 要求以「分布 / 合法性 / 固定时间完成模拟数」比较。
- 无并行 MCTS、无 CUDA/GPU/AVX2、无新 GUI（遵守 S5 边界）。
- `rl` 未训练、未转换模型；仍以 V5 正式模型 NumPy 推理为基线。
- 多 DPI 真实 125%/150% GUI 视觉：本任务未涉及 GUI 改动，保持既有 UNVERIFIED（见报告）。
