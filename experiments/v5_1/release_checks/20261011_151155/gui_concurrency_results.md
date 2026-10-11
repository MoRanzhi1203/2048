# V5.1 · H7 GUI 并发 / 取消 / 线程生命周期压力测试记录

> run: `20261011_151155` ｜ 平台：Windows ｜ 解释器：`E:\anaconda3\python.exe` ｜ Qt：5.15.10
> 说明：本文件记录**实际执行**结果；未采集项标 `NOT_MEASURED`。自动化测试均为离屏（`QT_QPA_PLATFORM=offscreen`）。

## 1. 覆盖场景与对应测试

| # | 场景 | 对应测试 | 实测结果 |
| --- | --- | --- | --- |
| 1 | 求解启动后立即停止 | `test_start_stop_single_trigger`、`test_solver_gui_lifecycle` | PASS |
| 2 | 未返回前 快速停止→启动新任务 | `test_solver_gui_lifecycle`（快速重启）、`test_stop_restart_stress_10x_no_thread_leak`（×10） | PASS |
| 3 | 旧任务 `solved`/`failed` 在新任务进行中才返回 | `test_stale_result_does_not_clear_inflight_flag` | PASS：旧 job_id 结果/失败均被丢弃，`_solve_in_flight` 保持 True、进度条不被改动 |
| 4 | 求解中窗口关闭 | `test_solver_gui_lifecycle`（运行中 `close()`） | PASS：不崩溃，线程回收 |
| 5 | 求解中折叠/展开右栏、拖动 splitter、改窗口大小 | `test_collapse_during_solve_keeps_running`、`test_hide_while_solving_via_ai_button_reopens`、`test_edge_handle_hide_while_solving_reopens`、`test_splitter_user_resize` | PASS |
| 6 | 单步建议 / 自动连走 模式切换 | `test_single_step_suggestion`、`test_auto_solving_runs_and_records` | PASS |
| 7 | 重复停止/重启 10 次 | `test_stop_restart_stress_10x_no_thread_leak` | PASS（见 §2） |
| 8 | 连续求解 + 随机关闭 最小压力 | `test_solver_gui_lifecycle` 末段（运行中关窗） | PASS |

## 2. 10× 停止/重启 压力实测数字

命令：

```bash
python v5_pyqt_2048_solver/test_solver.py __main__.SolverGuiTest.test_stop_restart_stress_10x_no_thread_leak
```

| 指标 | 实测 |
| --- | --- |
| 启动次数 | 10 |
| 取消次数 | 10 |
| job_id 序列 | 严格递增、无重复（断言通过） |
| 已接受结果 | 0（均在返回前被停止，符合预期） |
| 丢弃的旧结果 | 0（本压力场景无旧结果到达） |
| 活跃退休线程（结束后） | 0 |
| `_solver_thread` / `_solver_worker`（结束后） | 均为 `None`（已回收） |
| 采集到的 Qt 运行期消息 | 6 条，**全部为** `QFontDatabase: Cannot find font directory ...`（离屏字体路径提示，无害） |
| 危险告警（`Destroyed while thread is still running` / `QThread: Destroyed` / `QObject::~QObject`） | **0 条** |
| 异常/失败栈 | 无 |
| 用例耗时 | 约 2.1–2.4s |

> `qInstallMessageHandler` 在用例期间捕获全部 Qt 消息，故“无危险告警”为**直接观测**，非推测。

## 3. 代码不变量核对（对照当前源码）

- `_on_solver_result` / `_on_solver_failed`：**先**校验 `_solver_running` → `job_id == _job_id` → 棋盘快照，**后**才清零 `_solve_in_flight` 与进度条（`v5_pyqt_2048_solver.py` L1428–L1487）。过期信号不会清掉新任务状态。
- 自动连走：`_ai_apply` 先校验方向对当前棋盘合法，非法则 `_finish_solver`（不进入动画），旧棋盘结果在 `_on_solver_result` 阶段已被棋盘签名拦截。
- 取消：`_start_solver` 生成 `threading.Event` 取消令牌，`SolverWorker.solve` 在调用前后检查；**并发结论限定为“协作式取消 + 有界 `time_limit`”**——`QThread.quit()` 不会中断正在执行的同步槽，故不宣称“即时中断”。
- 线程回收：`_shutdown_worker` 在 `wait()` 超时时将线程/worker 移入 `_retired_threads` 并保留引用，`finished` 后 `_collect_retired` 回收；**从不调用 `QThread.terminate()`**（全文件无 `terminate(` 调用）。
- 关闭：`closeEvent` → `_stop_solver(silent=True)`（触发 `_finalize_session` → `_shutdown_worker`）→ `super().closeEvent` → `_shutdown_worker()`（幂等）。

## 4. 结论

`GUI_CONCURRENCY_PASS`：场景 1–8 均有自动化证据，10× 压力下无 Qt 线程/对象失控告警、无线程泄漏、job_id 严格递增。

`无阻塞缺陷`。可采集指标全部采集；无 `NOT_MEASURED` 项。
