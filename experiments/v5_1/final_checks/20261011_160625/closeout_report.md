# V5.1 · H8 剩余问题最终专项收口报告（closeout_report）

> run: `20261011_160625` ｜ 基线 HEAD：`f145f5f` ｜ 平台：Windows ｜ 解释器：`E:\anaconda3\python.exe`
> 本轮仅做 H8 剩余三项；未重跑多局基准，未改动算法/RL/模型，未自动提交 Git。

## 1. 三项任务结论速览

| # | 任务 | 结论 |
| --- | --- | --- |
| 1 | 分段计时定位 MCTS 停止 ~950–1000ms | **根因 = `_save_sessions`（会话历史全量写盘），非线程**。已最小修复：959ms→140ms |
| 2 | 子进程验证关闭预算超时下 QThread 不被提前销毁 | **PASS**：线程存活可观测、退出码 0、Qt 销毁告警 0 |
| 3 | 复核四张整窗截图 + 真实 125%/150% 缩放 | 四图 CAPTURE/STRUCTURE/TEXT PASS；**VISUAL / DPI_VISUAL = UNVERIFIED**（无人工确认） |

## 2. 任务1：停止耗时分段定位与修复

真实在途停止分段（修复前，mcts/strong）：`_stop_solver=961ms`，其中 `_save_sessions=959ms`、`_shutdown_worker=1.3ms`。

**根因**：`_save_sessions` 用 `json.dump(..., indent=2)` **全量流式重写** 3.1MB / 11463 步的会话历史（gitignored 运行期数据），单次 537–959ms，直接拖慢 GUI 停止路径；与线程无关，且随历史线性增长。

**最小修复**（1 行，输出仍为标准 JSON，`_load_sessions` 兼容）：
```python
f.write(json.dumps(self._sessions, ensure_ascii=False, separators=(",", ":")))
```

**效果**：`_save_sessions` 959ms → **140ms**（@3.1MB）；mcts 停止总计 961ms → **677ms**（= 快写盘 ~140 + 有界线程等待 ~536）；expectimax 停止 → **~1ms**。详见 `stop_latency_breakdown.md`。

> 残留：仍是同步全量重写（紧凑后 ~94–140ms）。彻底消除需异步/增量持久化 → 建议 V5.2。

## 3. 任务2：独立子进程关闭预算验证

方法：子进程内 mock `solver.solve` 阻塞 8s（> `SOLVER_CLOSE_WAIT_MS=3500`），启动求解→进入计算→关闭窗口→观察。

实测：`close_ms=4028`、`thread_alive_after_close=True`（**未被提前销毁**）、`retired_running=[True]`、放行后自然结束、**EXIT_CODE=0**、**QT_DESTROY_WARNINGS=0**。详见 `qthread_close_budget_test.md`。

## 4. 任务3：截图与 DPI 复核

- 四场景整窗截图已**重新捕获**：`full_start/game/solver/collapsed.png`，均含原生标题栏，CAPTURE/STRUCTURE/TEXT PASS。
- 真实 Windows 125%/150%：本机 100%（DPR=1.0），未在真实缩放下人工验证 → **`V5_1_DPI_VISUAL=UNVERIFIED`**；`manual_visual_checklist.md` 给出可操作步骤。
- **`V5_1_GUI_VISUAL=UNVERIFIED`**（脚本不授予）。

## 5. 测试与模型

- `test_solver.py` **79 OK**；`test_popups.py` **17/17**；`test_cross_version.py` **41/41**（受影响范围回归）。详见 `affected_tests.txt`。
- 模型 SHA256 前后一致：`rl_model=ee4b370e67676bfb`、`candidate=ee4b370e67676bfb`、`prev=724c4eea877421cf`、`baseline=724c4eea877421cf`。`EQUAL_TO_BEFORE=True`。

## 6. 九项发布门禁

| # | 门禁 | 状态 |
| --- | --- | --- |
| 1 | V5_1_CODE_PASS | **PASS** |
| 2 | V5_1_INFLIGHT_CANCEL | **PASS** |
| 3 | V5_1_THREAD_SAFETY | **PASS** |
| 4 | V5_1_GUI_AUTOMATED | **PASS** |
| 5 | V5_1_GUI_VISUAL | **UNVERIFIED** |
| 6 | V5_1_DPI_VISUAL | **UNVERIFIED** |
| 7 | V5_1_MODEL_INTEGRITY | **PASS** |
| 8 | V5_1_TESTS | **PASS** |
| 9 | V5_1_RELEASE_READY | **PARTIAL_PASS** |

## 7. 未完成 / 建议

- 人工目视四张整窗截图后 `--visual-confirm`；真实 125%/150% 走查（还原系统设置）。
- V5.2：会话持久化异步/增量；RL 迭代；C++ bitboard；统计扩样；本地/联机多人。
- 未自动 commit/push/tag（用户确认后再操作）。
