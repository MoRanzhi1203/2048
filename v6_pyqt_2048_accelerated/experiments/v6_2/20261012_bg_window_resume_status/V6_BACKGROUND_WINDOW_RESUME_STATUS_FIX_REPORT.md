# V6 后台：多余窗口 / 暂停继续 / 求解状态同步 —— 修复报告（P0–P7）

> 仓库：`E:\PyQt5_demo\2048`；解释器：`E:\anaconda3\envs\2048\python.exe`；`PYTHONNOUSERSITE=1`。
> 仅改 V6；V1–V5 只读；未改正式存档 / RL 模型；**未 Git 提交**。
> 证据：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_bg_window_resume_status/`。

---

## 1. 三个问题的确定根因（file:line 证据 + 实测）

### 问题 1：后台启动后出现额外空白 `python` 窗口
存在**两个独立来源**，本轮都已修复：

1. **Worker 控制台窗口**：`v6_background._launch_worker()` 用 `subprocess.Popen([sys.executable, '-m',
   'headless.worker_main'], ...)` 且**未设置 `CREATE_NO_WINDOW`**。当 GUI 由无控制台的
   `pythonw`/快捷方式启动时，子进程 `python.exe` 会新建一个可见控制台。
   **实测**（`worker_window_probe.json`，父进程 `pythonw.exe`）：
   - 无 flag：worker 可见窗口 `[{class: ConsoleWindowClass, title: ...python.exe}]`
   - `CREATE_NO_WINDOW`：`[]`
2. **空白 Qt 顶层窗口**：统一改造后 `BackgroundPanel` 已不再插入任何布局（无父窗口），
   但 `BackgroundController.on_mode_changed()` 仍执行 `self.panel.setVisible(True)`，把空的
   `QWidget` 提升为独立顶层窗口（标题 `pythonw`）。
   **实测**（修复前 `v6_visible_windows` 有 2 个：V6 主窗口 + `pythonw`；修复后仅 1 个）。

### 问题 2：暂停后点“继续”无法稳定恢复回传
`BackgroundController.resume()` 只发送 `start`，**未清除 `_final_seen`**。暂停 FINAL 已把
`_final_seen=True`，`_on_msg` 对 `progress` 的第一条守卫就是 `if self._final_seen: return`，
于是恢复后的所有周期回传被当成“终态后迟到帧”丢弃 → 界面无新进展。
另外：`resume` 未重置方向游标/交接基准，恢复段 FINAL 的正式历史回放会错位；
`total_committed_moves` 在恢复段从 1 重新计数（不单调）。

### 问题 3：顶部摘要更新、下方既有状态/分数/步数/日志长期不变
`_v6_sync_run_controls()` 只刷新顶部紧凑摘要；下方既有
`solver_status` 仅在 `_show()` 写一段纯文本，`solver_metrics`（步数/动作/评估/分数/最大块/耗时）
与 `solver_log` **从未由后台回传更新**，因此停留在标准模式/上一次求解的旧值（含 0 与旧分数）。
`exited` 消息还会用“进程已退出”覆盖已结算的最终状态。

---

## 2. 修改内容

### P1 无窗口 Worker（`v6_background.py`）
- `_launch_worker()`：Windows 下加 `creationflags=subprocess.CREATE_NO_WINDOW` +
  `STARTUPINFO(STARTF_USESHOWWINDOW, SW_HIDE)`；stdin/stdout 管道不变。
- stderr 改为**有界诊断文件** `game_history/background/worker_stderr.log`（每次启动截断），
  退出/清理时关闭句柄；保留 `error`/`exited`/退出码链路。
- `on_mode_changed()`：不再 `panel.setVisible(True)`（空占位面板永不显示）。

### P2 暂停/继续（`v6_background.py` + `headless/game_loop.py`）
- `resume()`：校验暂停点文件存在；`_transition('BG_RUNNING')` 后
  **`_final_seen=False`**、`_session_cursor=0`、`_session_base_grid=当前棋盘`、`_fresh_handoff=False`；
  发送 `start`（补 `native_search`）并校验发送结果，失败 → `BG_ERROR`（不再假 RUNNING）。
- `game_loop.run_session()`：引入 `base_steps = snapshot.revision`；
  `total_committed_moves / step / sequence` 使用 `base_steps + steps`，`_last_delivered=base_steps`，
  预算判定改用累计步数 → 恢复段步数/revision 单调；本段吞吐仍用 session steps。

### P3 单一状态源（`v6_speed.py` + `v6_background.py`）
- 新增 `_v6_apply_bg_progress(p)`：**同一次回传**同时更新
  顶部摘要（`_v6_sync_run_controls`）+ 下方 `solver_status`（HTML）+ `solver_metrics`
  （steps/action/eval/score/max_tile/elapsed，未知显示 `—`）+ 日志（按 revision 去重）。
- 新增 `_v6_apply_bg_final(msg)`：PAUSED/STOPPED/COMPLETED/GAME_OVER/ERROR 一次收敛两块区域。
- 切到后台时仅重置**上一求解会话**指标（不动真实游戏分数/最高分）。
- `exited` 在正常收尾后不再覆盖已结算状态（只写日志）。
- 周期快照仍只读渲染（不 `apply_move`、不生成方块），未新增面板/按钮。

---

## 3. 真实 Windows 进程与窗口证据（P5-1）

`lifecycle_5rounds.json`（pythonw 启动，模拟无控制台 GUI）：

| 检查 | 结果 |
| --- | --- |
| V6 顶层窗口 | **1 个**：`2048 V6 · 后端=自动(reference)`（Qt5152QWindowIcon） |
| 额外 `pythonw` 空白窗口 | **0**（修复前存在） |
| 控制台窗口（ConsoleWindowClass） | **0** |
| 每轮 worker 可见窗口 | **0 / 0 / 0 / 0 / 0** |
| worker PID（5 轮） | 23400 / 36916 / …（每轮独立，退出后无残留） |

## 4. 暂停→继续 IPC 时间线（P5-2，连续 5 轮）

| 轮 | resume 后首个新 progress | revision 单调 | steps 单调 | 暂停态 | 最终 | owner | worker 退出 |
| ---: | ---: | --- | --- | --- | --- | --- | --- |
| 1 | 167.4 ms | 23→36→55 | ✔ | BG_PAUSED | stopped | absent | ✔ |
| 2 | 195.1 ms | ✔ | ✔ | BG_PAUSED | stopped | absent | ✔ |
| 3 | 190.3 ms | ✔ | ✔ | BG_PAUSED | stopped | absent | ✔ |
| 4 | 203.5 ms | ✔ | ✔ | BG_PAUSED | stopped | absent | ✔ |
| 5 | 201.0 ms | ✔ | ✔ | BG_PAUSED | stopped | absent | ✔ |

- `start_ms` ≈ 266–438 ms；`pause_ms` ≈ 60–172 ms；`render_age_ms` 0–0.4 ms。
- 恢复段 `total_committed_moves` 从暂停 revision 继续（不再重置为 1）。

## 5. 双区域同步示例（同一次 PROGRESS）

```
顶部摘要 : 后台 · 运行中 · 步 23 · 43.0 步/秒 / 分数 168 · 最大 32 · 后端 cpp
下方状态 : 状态：后台求解中　步数 23　分数 168
           最大瓦片 32　43.0 步/秒　引擎 cpp / python_kernel　rev 23　同步延迟 0ms
metrics  : steps=23  score=168  max_tile=32  elapsed=0.5s
日志     : [后台] rev 23 · 步 23 · 分数 168 · 最大 32 · 43.0 步/秒（同 revision 去重）
最终     : 状态：后台求解已停止　步数 64　分数 536 / 最终棋盘已同步；最大瓦片 64
```

## 6. 截图（真实整窗，DWM + BitBlt）

`screenshots/`：`wr_idle.png`、`wr_running.png`、`wr_paused.png`、`wr_resumed.png`、`wr_stopped.png`
（均 `ok=true`，908×759 左右，含原生标题栏）。
**人工目视：UNVERIFIED**；**DPI 125%/150%：UNVERIFIED**。

## 7. 门禁（真实退出码）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **111 tests OK（skipped=3），EXIT 0** |
| `V6_RUN_IPC_E2E=1 … WorkerOwnershipLifecycleTest WorkerE2ETest` | **3 tests OK，EXIT 0** |
| 残留进程 | 无 V6 / worker 残留 |

新增/加强用例：
- `test_worker_launch_uses_no_window_flags`（断言 `CREATE_NO_WINDOW` + STARTUPINFO）
- `test_resume_clears_final_gate_and_resets_segment`（继续必须清除终态门、重置游标、发送 start）
- `test_bg_progress_updates_both_areas_and_logs_once`（双区域同源 + 日志按 revision 去重）
- `test_resumed_session_keeps_monotonic_total_steps`（恢复段累计步数单调）

## 8. 门禁结论

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| P0 基线/根因 | **PASS** | 控制台/HWND 枚举 + 代码链 |
| P1 无多余窗口 | **PASS** | 1 个 V6 窗口；worker 0 可见窗口；console 0 |
| P2 暂停/继续 | **PASS** | 5/5 轮新 revision、步数单调、owner/进程收敛 |
| P3 单一状态源 | **PASS** | 顶部/下方/metrics/日志同源；未知显示 — |
| P4 1000ms/终态同步 | **PASS（周期保持 500ms，见下）** | 首帧第 1 步、暂停/停止强制 FINAL |
| P5 测试与截图 | **PARTIAL** | E2E + 截图完成；人工目视/DPI 125·150% **UNVERIFIED** |
| P6 回归/回滚 | **PASS** | 111 单测 + 3 IPC E2E；无残留；V1–V5 未改 |
| P7 报告 | **PASS** | 本文件 |

### 关于回传周期（重要差异）
任务文档写“固定 1000ms”，但**上一轮你明确要求并已提交为 500ms**（`REPORT_INTERVAL_MS=500`）。
本轮为“修复三个问题”，未改动该产品决策，保持 **500ms**；如确认要回到 1000ms，
只需把 `v6_background.REPORT_INTERVAL_MS` 改为 1000 并跑迁移（单点常量）。

## 9. 修改文件
- `v6_pyqt_2048_accelerated/v6_background.py`
- `v6_pyqt_2048_accelerated/v6_speed.py`
- `v6_pyqt_2048_accelerated/headless/game_loop.py`
- `v6_pyqt_2048_accelerated/tests/test_v6_headless.py`
- `v6_pyqt_2048_accelerated/tests/test_v6_report_policy.py`

## 10. 剩余风险
- 后台仍为 EXPERIMENTAL（沿用既有判定）；高 DPI 与人工视觉未验证。
- 暂停常驻 worker 仍按“下一条 start 恢复”策略，不新起进程；重连场景走 `_spawn_worker_from`。
- 恢复段吞吐按本段计算，跨暂停的长期平均吞吐需另做统计。
