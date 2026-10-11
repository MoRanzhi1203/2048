# V5.1 · H8-1 在途取消确定性验证报告（inflight_cancellation_results）

> run: `20261011_153920` ｜ 平台：Windows ｜ 离屏 Qt（`QT_QPA_PLATFORM=offscreen`）｜ 解释器：`E:\anaconda3\python.exe`
> 夹具：**started-event(`entered`) + release-event 同步屏障** + watchdog(15s)；`monkeypatch solver.solve`，`tearDown` 保证恢复（不污染正式逻辑）。
> 证据：`h8_inflight_run.txt`（修复前）、`h8_thread_tests_after_fix.txt`（修复后 + 既有并发用例）。

## 1. 取消的四个层级（明确区分，不合并成“已取消”）

| 层级 | 含义 | 实测 |
| --- | --- | --- |
| `CANCEL_REQUESTED` | GUI 置 `threading.Event` | 主线程即时 |
| `RESULT_DISCARDED` | worker 返回时检测到 token → 不 emit | C01/C02/C03 验证 |
| `COMPUTATION_EXITED` | `solver.solve` 因**有界预算**返回 | 内部**无**取消轮询（`solver_2048.py` 全文 0 命中 `cancel`）→ 最坏≈`time_limit`（≤`MAX_TIME_LIMIT=2.0s`） |
| `THREAD_CLEANED` | `quit()`+有界 `wait`；超时转 retired，`finished` 后回收 | C04/C05 验证，`live_threads=0` |

> **不宣称“即时协作式取消”**：算法内部（MCTS/Expectimax/Rollout）**不检查取消令牌**，其可终止性来自有界执行预算 + GUI 侧结果丢弃 + 线程安全回收。未新增取消轮询（无证据表明需要，且避免改动算法决策正确性）。

## 2. C01–C06 实测结果

| 场景 | 触发时序 | entered_compute | 关键实测 | 结果 |
| --- | --- | --- | --- | --- |
| **C01** | 进入计算→停止→放行旧计算 | ✅ | `stop_block` **3011ms→507ms（修复后）**；棋盘不变；结果不落地；无幽灵任务 | PASS |
| **C02** | 旧进入计算→停止→启动新任务→旧 `solved` 迟到 | ✅ | 迟到 solved 被丢弃；新任务 `_solve_in_flight` 保持 True；进度条/board_sig 未被污染 | PASS |
| **C03** | 同 C02 的旧 `failed` 迟到 | ✅ | 旧 failed 被丢弃；新任务运行态不变；未弹旧任务错误 | PASS |
| **C04** | 进入计算→关闭窗口→放行旧任务 | ✅ | 线程最终结束；引用持续到完成；**QThread 销毁告警 0** | PASS |
| **C05** | 连续 10 次在途取消 | ✅×10 | `job_ids=[1..10]` 单调唯一；`solver_calls=10`；`live_threads=0` | PASS |
| **C06** | 在途求解中折叠/展开×3 + 拖 splitter + 缩放 + 切模式 | ✅ | 无重复提交（`calls` 不变）、`job_id` 稳定、无重复自动落子、贴边把手展开入口可用 | PASS |

**合计 6/6 PASS，失败 0。** C02/C03 用 `Qt.DirectConnection` 探针在 **worker 线程内**确认 `solved`/`failed` 已 emit（杜绝“假定已启动”），随后主线程未 `processEvents`，使 queued 信号**真实迟到**后再投递。

## 3. H8-2 最小修复与前后对比（证据支撑）

**根因（实测）**：`_shutdown_worker` 默认 `wait(3000)` 在 worker 仍处于同步计算时会**阻塞 GUI 主线程约 3s**（C01 `stop_block=3011ms`）——违反 H8-2.6。

**最小修复**（`v5_pyqt_2048_solver.py`）：
- 新增常量 `SOLVER_STOP_WAIT_MS=500`（交互停止短等待）、`SOLVER_CLOSE_WAIT_MS=3500`（关闭有界等待）；
- `_shutdown_worker` 默认改为 `SOLVER_STOP_WAIT_MS`（超时转 retired 异步回收，语义不变）；
- 新增 `_wait_retired(timeout_ms)`：**仅关闭路径**对“当前 + 全部 retired”线程做有界等待（超时保留引用，绝不 terminate/丢弃）；
- `closeEvent` 增加对 retired 线程的有界等待。

**修复前后**：

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| C01 交互停止阻塞 GUI | 3011ms | **507ms** |
| 真实求解在途停止阻塞 | （同默认 3s 上限） | expectimax 363/460ms、mcts 946/1016ms |
| C04 关闭线程销毁告警 | 0 | 0 |
| 既有 lifecycle/stale/stress | PASS | PASS |

> `mcts` 停止时长（~1.0s）高于常量 500ms，来自 Qt 线程退出与事件投递开销叠加；仍远低于修复前的 3s 上限，且**不随计算时间线性增长**（不再等待整段 `time_limit`）。

## 4. 未采集项（NOT_MEASURED，如实标注）

- 逐事件（cancel/exit/thread-exit/cleanup）纳秒级时间戳：夹具为人工阻塞，逐事件时间戳不代表真实搜索循环，故未采集。
- GUI 主线程毫秒级卡顿采样：仅记录 `stop_block` 时长。

**门禁：`INFLIGHT_CANCEL_SAFETY_PASS`**（6/6 场景有实际证据；取消/迟到信号/线程关闭均验证）。
