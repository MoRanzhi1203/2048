# V5.1 · 最后一次最小范围发布收口报告（final_report）

> run: `20261011_162440` ｜ 基线 HEAD：`d810c09` ｜ 平台：Windows ｜ 解释器：`E:\anaconda3\python.exe`
> 原则：只修实际确认问题；保持紧凑 JSON 与全部历史；不改五算法核心/正式 RL 模型/V2–V4；不重跑多局基准；未自动提交 Git。所有结果来自实际执行。

## 1. 修复差异

| 文件 | 方法 | 根因 | 修改 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | `_save_sessions` / `_load_sessions` | 直接覆盖写主文件：写入中断产生半截 JSON，`_load_sessions` 返回 `[]` → **全部历史丢失** | tmp+`fsync` → 旧文件转存 `.bak` → `os.replace` 同盘原子替换；加载失败回退 `.bak`；失败清理 `.tmp`、保留原文件 |
| `v5_pyqt_2048_solver/test_solver.py` | 新增 `test_sessions_atomic_save_and_rollback` | 缺原子保存/回滚覆盖 | 故障注入用例（80 条） |

输出仍为**紧凑标准 JSON**，未引入大规模存储架构，未改变历史数据结构。

## 2. 故障注入证据

`atomic_save_rollback.md`：
- 首次保存 → 单行紧凑、无 `.tmp`；
- 覆盖前生成 `.bak` 回滚点；
- **故障A**（主文件写坏）→ 由 `.bak` 回滚读取，不丢历史；
- **故障B**（`os.replace` 注入 OSError）→ 主文件**逐字节不变**、无 `.tmp` 残留、仍可读。
命令与日志：`test_results.txt` / `affected_tests.txt`。

## 3. 真实进程退出验证

`process_exit_test.md`（独立子进程，timeout=45s）：

| 模式 | 退出码 | 墙钟 | 结束后线程 | Qt 告警 |
| --- | --- | --- | --- | --- |
| idle | **0** | 1.15s | 无 | **0** |
| solving（求解中关窗） | **0** | 1.41s | `solver_thread_alive=False`、`retired=0` | **0** |

→ 关闭最后窗口后进程**真实退出**，无挂起、无残留线程。

## 4. GUI

四场景整窗截图（`full_start/game/solver/collapsed.png`）重新捕获：CAPTURE/STRUCTURE/TEXT **PASS**；**人类目视确认全部通过 → `V5_1_GUI_VISUAL=PASS`**（已 `--visual-confirm`，证据 `gui_visual_confirm.jsonl`）。

## 5. 测试与模型

| 套件 | 数量 | 结果 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 80 | OK |
| `tests/test_popups.py` | 17 | PASS |
| `tests/test_cross_version.py` | 41 | PASS |
| `tests/test_rl_model_management.py` | 5 | OK |

模型 SHA256 前后一致：`rl_model=ee4b370e67676bfb…`、`candidate=ee4b370e67676bfb…`、`prev=724c4eea877421cf…`、`baseline=724c4eea877421cf…`（`EQUAL_TO_BEFORE=True`）。用户真实 `solver_results/sessions.json` 未改动（38 会话，有效）。

## 6. 最终发布状态（八项门禁）

| # | 门禁 | 状态 |
| --- | --- | --- |
| 1 | V5_1_CODE_PASS | **PASS** |
| 2 | V5_1_INFLIGHT_CANCEL | **PASS** |
| 3 | V5_1_THREAD_SAFETY | **PASS** |
| 4 | V5_1_GUI_AUTOMATED | **PASS** |
| 5 | V5_1_GUI_VISUAL | **PASS**（人工确认） |
| 6 | V5_1_MODEL_INTEGRITY | **PASS** |
| 7 | V5_1_TESTS | **PASS** |
| 8 | **V5_1_RELEASE_READY** | **PASS** |

**结论**：全部发布硬门禁 PASS → **`V5_1_RELEASE_READY = PASS`**。未自动创建 tag/提交/推送。
