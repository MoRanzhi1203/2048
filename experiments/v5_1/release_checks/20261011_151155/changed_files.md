# V5.1 · H7 变更文件清单（changed_files）

> run: `20261011_151155` ｜ 基线 HEAD：`3e6381a`（`git_before.txt` / `git_after.txt`）
> 区分：**本轮（H7）新增/修改** 与 **既有未跟踪/未提交** 项。

## 1. 本轮（H7）修改的**已跟踪**文件

| 文件 | 类型 | 根因/目的 | 对应验证 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 新增用例 | H7-2：新增 `test_stop_restart_stress_10x_no_thread_leak`（10× 停止/重启 + Qt 消息捕获），73 条 | 该用例 PASS；全套 73 OK |
| `experiments/v5_1/report.md` | 文档 | H7-3：顶部追加“§1–§10 为历史、100 局门禁作废、以 §11 为准”的阅读提示（不改写历史正文） | benchmark_audit |
| `v5_pyqt_2048_solver/screenshots/full_start.png` | 截图 | H7-1：以真实桌面重新捕获（整窗） | CAPTURE/STRUCTURE/TEXT PASS |
| `v5_pyqt_2048_solver/screenshots/full_game.png` | 截图 | 同上 | 同上 |
| `v5_pyqt_2048_solver/screenshots/full_solver.png` | 截图 | 同上 | 同上 |
| `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 截图 | 同上（新增折叠态证据） | 同上 |

> **本轮未修改任何算法源码**（`solver_2048.py`/`rl_2048.py`/`v5_pyqt_2048_solver.py` 相对 HEAD 无改动）；未重训、未替换任何模型。

## 2. 本轮（H7）新增的**未跟踪**证据目录

- `experiments/v5_1/release_checks/20261011_151155/`：本文件、`environment.json`、`git_before.txt`、`git_after.txt`、`model_hash_before.json`、`model_hash_after.json`、`test_results.txt`、`test_summary.json`、`regression_summary.txt`、`gui_capture.jsonl`、`gui_concurrency_results.md`、`manual_visual_checklist.md`、`benchmark_audit.md`、`release_report.md`。

## 3. 既有未提交 / 未跟踪（非本轮改动，保留不动）

- `experiments/v5_1/runs/`（上一轮 H0–H6 的轻量实验与基线证据，未纳入 Git）。
- `2048_V5_1_完整修复与轻量验收_Trae指令.md`、`2048_V5_1_H7_发布前专项验收与稳定基线冻结_Trae完整指令.md`（任务指令，未跟踪）。
- 上一轮 H0–H6 的源码/测试/文档修复已随提交 `3e6381a` 进入版本库，本轮无重复改动。

> 未执行任何 `git commit` / `reset --hard` / `clean -fd` / 强制 checkout。
