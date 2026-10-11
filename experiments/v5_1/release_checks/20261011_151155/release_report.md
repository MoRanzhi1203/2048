# V5.1 · H7 发布前专项验收与稳定基线冻结报告

> run: `20261011_151155` ｜ 基线 Git HEAD：`3e6381a` ｜ 平台：Windows ｜ 解释器：`E:\anaconda3\python.exe`
> 原则：所有结果来自实际执行；未执行/未人工确认项标 `UNVERIFIED`/`NOT_MEASURED`，不虚报。

## 1. H7 门禁总表

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| `H7_BASELINE_PASS` | **PASS** | git/HEAD、关键源码、模型哈希、AGENTS/rules/截图规范均已核验；证据目录已建 |
| `GUI_AUTOMATED_VISUAL_PASS` | **PASS** | start/game/solver/collapsed 四场景整窗截图 CAPTURE+STRUCTURE+TEXT 全通过 |
| `MANUAL_VISUAL_STATUS` | **UNVERIFIED** | 无人类目视确认 → 保持 `VISUAL_UNVERIFIED`（见 `manual_visual_checklist.md`） |
| `GUI_CONCURRENCY_PASS` | **PASS** | 场景 1–8 有自动化证据；10× 压力 0 危险告警/0 泄漏（见 `gui_concurrency_results.md`） |
| `EXPERIMENT_REPORT_PASS` | **PASS** | 原始 JSON/CSV 与文档一致；截断标记正确（见 `benchmark_audit.md`） |
| `TESTS_PASS` | **PASS** | 180/180，0 失败，0 跳过（`test_results.txt`/`test_summary.json`） |
| `NO_BLOCKING_FAILURES` | **PASS** | 本轮未发现阻塞缺陷 |

## 2. 交付状态（按指令要求分别输出）

| 状态 | 值 |
| --- | --- |
| `V5_1_CODE_PASS` | **PASS** |
| `V5_1_GUI_VISUAL` | **UNVERIFIED**（需人工目视 4 张整窗截图） |
| `V5_1_THREAD_SAFETY` | **PASS** |
| `V5_1_RELEASE_READY` | **PARTIAL_PASS**（代码/线程/实验/测试均 PASS；仅人工视觉未确认 → 待人工确认后可升为 PASS） |

## 3. 文件修改表（本轮 H7）

| 路径 | 根因/目的 | 修改 | 对应测试 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | H7-2 需 10× 停止/重启压力覆盖 | 新增 `test_stop_restart_stress_10x_no_thread_leak`（qInstallMessageHandler 捕获 Qt 消息；断言无失控告警/无泄漏/job_id 递增） | 该用例 PASS；test_solver 73 OK |
| `experiments/v5_1/report.md` | H7-3 修订“100 局硬门禁”过期措辞 | 顶部追加阅读提示（§1–§10 历史保留；以 §11 为准） | benchmark_audit |
| `screenshots/full_{start,game,solver,collapsed}.png` | H7-1 提供整窗视觉证据 | 真实桌面重新捕获 | CAPTURE/STRUCTURE/TEXT PASS |
| `experiments/v5_1/release_checks/20261011_151155/*` | H7-4 冻结证据 | 新建 14 个证据文件 | 见本目录 |

> 本轮**未修改任何算法源码**，未重训/替换模型（详见 `changed_files.md`）。

## 4. 测试实际数量、失败数、命令

| 套件 | 数量 | 结果 | 耗时 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 73 | OK | 66.9s |
| `tests/test_expectimax_reference.py` | 10 | OK | 2.8s |
| `tests/test_mcts_chance.py` | 10 | OK | 22.7s |
| `tests/test_rl_gradients.py` | 8 | OK | 8.8s |
| `tests/test_rl_model_management.py` | 5 | OK | 6.0s |
| `tests/test_algorithm_benchmark_smoke.py` | 5 | OK | 4.5s |
| `tests/test_cross_version.py` | 41 | PASS | — |
| `tests/test_popups.py` | 17 | PASS | — |
| `tests/test_rl_selftrain.py` | 11 | PASS | — |

**合计 180（unittest 111 + 自定义 69），失败 0，跳过 0。** 命令见 `test_summary.json` / `test_results.txt`。

## 5. GUI 线程压力测试（场景 + 真实结果）

- 覆盖场景 1–8（启动即停、快速停→重启、旧结果在新任务中返回、求解中关窗、折叠/拖动/改窗、单步↔连走切换、10× 停止重启、连续求解+随机关闭）。
- **10× 压力实测**：启动 10 / 取消 10；job_id 严格递增无重复；结束后 `_solver_thread=None`、`_solver_worker=None`、活跃退休线程 0；采集 Qt 消息 6 条**全部为字号字体路径提示**，**危险告警 0 条**；无异常栈。
- **取消语义如实标注**：`threading.Event` 协作式取消 + 有界 `time_limit`；`QThread.quit()` 不中断运行中的同步槽 → 不宣称“即时中断”。`_shutdown_worker` 在 `wait()` 超时时保留引用并在 `finished` 后回收；全文件无 `terminate()`。

详见 `gui_concurrency_results.md`。

## 6. 模型文件执行前后 SHA256（是否一致）

| 模型 | before | after | 一致 |
| --- | --- | --- | --- |
| `v5_pyqt_2048_solver/rl_model.npz` | `ee4b370e67676bfb…` | `ee4b370e67676bfb…` | ✅ |
| `v5_pyqt_2048_solver/rl_model.candidate.npz` | `ee4b370e67676bfb…` | `ee4b370e67676bfb…` | ✅ |
| `v5_pyqt_2048_solver/rl_model.npz.prev.npz` | `724c4eea877421cf…` | `724c4eea877421cf…` | ✅ |
| `experiments/baseline/rl_model_v1.npz` | `724c4eea877421cf…` | `724c4eea877421cf…` | ✅ |

`EQUAL_TO_BEFORE = True`（`model_hash_before.json` vs `model_hash_after.json`）。未重训、未替换。

## 7. 轻量 benchmark 数据核验与截断解释

- Pilot：5 局/策略、400 步、30ms、seed_base=1000（144.9s）；Final：10 局/策略、400 步、30ms（327.0s）。原始 JSON 与 `report.md` §11.7 数字逐行一致。
- **截断语义**：expectimax/rollout 全 10 局 TRUNCATED；mcts/heuristic 各 1 FINISHED / 9 TRUNCATED；rl 全 10 局 FINISHED。**400 步截断分 ≠ 自然终局得分，不得据此做五算法最终排名/显著性结论**。
- 每步超时：expectimax(3381)/mcts(3863) 在 30ms 预算下近乎每步超时并返回 best-so-far（固定时间实验的正常表现）。
- 缓存口径：`cold 2.752ms→warm 0.0997ms` 仅指**模型加载**路径，**不得**解读为完整 solve 提速 27×。

详见 `benchmark_audit.md`。

## 8. 未完成 / 需人工确认项

| 项 | 状态 | 位置 |
| --- | --- | --- |
| 4 张整窗截图人工目视 | **UNVERIFIED** | `v5_pyqt_2048_solver/screenshots/full_{start,game,solver,collapsed}.png`（清单见 `manual_visual_checklist.md`） |
| 更大样本统计比较 | UNVERIFIED（非 H7 门禁） | 需用户显式要求另行设计 |
| 真实桌面 DPI 125%/150% 视觉 | 未专门捕获 | 环境可用时可加；本机 DPR=1.0 |

## 9. 结论与冻结建议

- **可以冻结第五版 V5.1 稳定基线（代码维度）**：`V5_1_CODE_PASS` + `V5_1_THREAD_SAFETY` + `TESTS_PASS(180/180)` + `EXPERIMENT_REPORT_PASS` + 模型哈希不变。
- **发布就绪为 `PARTIAL_PASS`**：唯一缺口是**人工视觉确认**。人工核对 4 张整窗截图后，运行 `capture_gui.py --visual-confirm` 并更新 `manual_visual_checklist.md`，即可升为 `V5_1_RELEASE_READY = PASS`。
- **建议延至 V5.2 / V6**：RL 能力增强（经验回放/超参自适应）、MCTS 默认策略消融后再定、更大样本统计与显著性设计、真实多 DPI 视觉回归。
