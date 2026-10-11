# V5.1 · H8 变更文件清单（changed_files）

> run: `20261011_153920` ｜ 基线 HEAD：`ddbf0e5` ｜ 对照 `git_before.txt` / `git_after.txt`

## 1. 本轮（H8）修改的**已跟踪**文件

| 文件 | 根因 | 修改 | 关联测试 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | **H8-2.6 实测缺陷**：`_shutdown_worker` 默认 `wait(3000)` 在 worker 处于同步计算时阻塞 GUI 主线程约 3s（C01 实测 `stop_block=3011ms`） | 新增常量 `SOLVER_STOP_WAIT_MS=500` / `SOLVER_CLOSE_WAIT_MS=3500`；`_shutdown_worker` 默认改短等待（超时转 retired 异步回收）；新增 `_wait_retired(timeout_ms)` 供关闭路径有界等待“当前+retired”线程；`closeEvent` 增加对 retired 线程的有界等待 | C01（3011→507ms）、C04、`test_solver_gui_lifecycle`、`test_stop_restart_stress_10x_no_thread_leak` |
| `v5_pyqt_2048_solver/test_solver.py` | 需在途取消确定性验证 | 新增 `import threading`、阻塞式 solver 夹具（`_install_blocking_solver`/`_restore_blocking_solver`/`_wait_threads_quiet`）与 C01–C06 六个用例；`tearDown` 保证释放阻塞并恢复 `solver.solve` | 79 test_solver 全 OK |
| `v5_pyqt_2048_solver/screenshots/full_start.png`、`full_game.png`、`full_solver.png`、`full_collapsed.png` | H8-3 四场景整窗截图 | 真实桌面重新捕获 | CAPTURE/STRUCTURE/TEXT PASS |

**未修改**：算法核心（`solver_2048.py`）、RL（`rl_2048.py`）、v1–v4、游戏规则、五算法默认参数、`tools/capture_gui.py`。

## 2. 本轮新增的**未跟踪**证据目录

- `experiments/v5_1/final_checks/20261011_153920/`：`environment.json`、`git_before.txt`、`git_after.txt`、`model_hash_before.json`、`model_hash_after.json`、`source_audit.md`、`inflight_cancellation_results.md/.json`、`h8_inflight_run.txt`、`h8_thread_tests_after_fix.txt`、`h8_lifecycle_orders.txt`、`gui_capture.jsonl`、`gui_capture_summary.json`、`gui_layout_audit.md`、`manual_visual_checklist.md`、`h8_dpi_sim.txt`、`benchmark_consistency.md`、`test_results.txt`、`test_summary.json`、`regression_summary.txt`、`release_lock_report.md`、`release_gates.json`。
- `experiments/v5_1/final_checks/LATEST.txt`。

## 3. 既有未提交/未跟踪（非本轮，保留不动）

- `2048_V5_1_*.md` 三份任务指令（未跟踪）。
- H7 证据 `experiments/v5_1/release_checks/` 与 `runs/` 已于提交 `ddbf0e5` 进入版本库。

> 未执行 `git commit`/`push`/`reset`/`clean`/`checkout`；未改动任务前工作区既有改动。
