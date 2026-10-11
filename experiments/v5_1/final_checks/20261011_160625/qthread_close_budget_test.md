# V5.1 · H8 收口：独立子进程 QThread 关闭预算验证（qthread_close_budget_test）

> run: `20261011_160625` ｜ 独立子进程运行（新 Python 进程）｜ 原始输出：`subprocess_close_raw.txt`

## 1. 目的

验证：当运行中的求解线程**超过** `SOLVER_CLOSE_WAIT_MS=3500ms` 关闭等待预算仍未结束时，**运行中的 QThread 不会被提前销毁**（引用被保留、可在关闭后继续观测、最终自然结束、进程正常退出且无 Qt 销毁告警）。

## 2. 方法

独立子进程脚本（离屏 Qt）：
1. monkeypatch `solver.solve` 为**阻塞 8s**（> 3500ms 预算），并记录 `entered_compute`；
2. GUI 启动求解 → 等待 `entered_compute=True`；
3. 关闭窗口（`closeEvent`：短停 500ms + 关闭有界等待 3500ms，超预算后保留引用）；
4. 关闭返回后检查线程是否仍存活（证明未被销毁）；
5. 放行旧任务，令其自然结束；
6. 观察退出码与 stderr 中的 Qt 告警。

## 3. 实测结果

```
SUBPROC SOLVER_CLOSE_WAIT_MS=3500 entered_compute=True
SUBPROC close_ms=4028 thread_alive_after_close=True retired_running=[True]
SUBPROC after_release still_running=[False]
SUBPROC EXIT_OK
EXIT_CODE=0
QT_DESTROY_WARNINGS=0
```

| 检查项 | 结果 |
| --- | --- |
| 真实进入计算 | `entered_compute=True` |
| 关闭耗时（含 500+3500 有界等待） | 4028ms（**超预算**，因任务阻塞 8s） |
| 关闭后线程对象仍存活可观测 | `thread_alive_after_close=True`（**未被提前销毁**） |
| 关闭后 retired 线程仍在运行（重试保留） | `retired_running=[True]` |
| 放行后线程自然结束 | `still_running=[False]` |
| 子进程退出码 | **0** |
| `QThread: Destroyed while thread is still running` 告警 | **0** |

## 4. 结论

`PASS`：超过 3500ms 关闭预算时，运行中的 QThread **未被提前销毁**（引用持续保留、可观测、随后自然结束），进程退出码 0，**无任何 Qt 线程销毁告警**。全程未使用 `QThread.terminate()`。
