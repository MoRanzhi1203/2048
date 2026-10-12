# V6 当前对局 · 无头（Headless）后台求解接入 —— 执行报告（本轮）

> 目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_headless_bg/`
> 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
> 范围：仅 V6/V6.2；V1–V5 只读。未自动提交 Git，未重训 RL，未覆盖正式存档/模型/历史实验。
> 真实性：门禁失败一律保留 FAIL/PARTIAL/UNVERIFIED，不冒充通过。

## 1. 代码审计（P0）

- V6 入口 `v6_pyqt_2048_accelerated.py`（`V6MainWindow`）继承 V5 `SolverMainWindow`；V6 独有：存档目录重定向、后端选择器、三档运行方式。
- 模型/存档/锁在继承链（V3 `GameCore` + V4 `AnimatedGameCore`）中，**与 Qt 耦合**（`v5_pyqt_2048_solver.py` 顶部即 import PyQt5）。
- **`v5_pyqt_2048_solver/solver_2048.py` 为纯 Python（仅 math/os/random/time，无 Qt）**，提供 `move_grid / legal_moves / is_game_over / sample_spawn / evaluate / build_config / PRESET_*`；因此无头核心建立在其上，**不导入任何 Qt**。
- 生成方块语义：模型 `add_new_tile` 行主序 `random.choice(empty)` + `random.random()<0.9 → 2 else 4`；`solver_2048.sample_spawn` 同序 —— 已用真实 V6 模型逐步对比验证（见 §3）。
- 参照历史基线：`experiments/v6_2/20261012_v6_only_opt/`（standard ≈2.05、旧 extreme ≈6.62 steps/s，20s 观测；非新保证）。
- 归档：`archive/comparison_v5v6_race_20261012/` 保持只读，未恢复进运行期。

## 2. 运行方式迁移与三档 UI（P1 / P6）

- 语义：`standard`（原样，含动画）／`fast`（**= 旧 extreme 行为**：无移动动画、无人工等待）／`background`（独立计算进程接管**当前这局**）。旧“快速演示”行为被**移除**（其历史值安全回退为 `standard`）。
- 带版本幂等迁移（`ui_prefs.json`，`modes_version=2`）实测：
  `standard→standard`、`extreme→fast`、`fast→standard`、`未知→standard`、缺失→`standard`；
  重复启动不再重映射；已是 V2 的 `fast` **不会**被再次改回。→ **MIGRATION_OK**
- UI：AI 求解主面板「运行方式」横向三档（标准｜快速｜后台求解）+ 分段计时读数；旧「运行方式」标签改为**求解强度**、旧「模式」改为**求解模式**（V6 进程内运行时改名，未改 V5 源码）。三者互不串线（切换运行方式不改算法/强度/模式）。
- 截图（真实整窗，DWM 外框 + 屏幕 BitBlt）：`after_three_modes_full_game.png`，文字校验含 `运行方式` 与 `速度-standard/fast/background`；门禁 **CAPTURE/STRUCTURE/TEXT PASS**，`VISUAL` **UNVERIFIED**。

## 3. 无头核心与等价性（P2 / G2）

文件：`headless/core.py`、`headless/game_loop.py`、`headless/worker_main.py`（均**无 Qt**）。

- **Qt 无关性**：子进程导入 `headless.*` 后 `'PyQt5' not in sys.modules`；并在无 `QApplication` 下跑完 5 步 → **PASS**。
- **RNG 精确往返**：`random.getstate()` → JSON → `setstate`，与全局随机流逐步一致（非仅 seed）。
- **与真实 V6 模型逐步等价**：同 RNG 状态下 16 步方向序列，`moved/棋盘/分数` **完全一致**，且结束 RNG 状态一致 → **PASS**。
- **快照校验**：非 2 的幂/错误形状/`>=65536`/非法算法 → 拒绝；终局立即 `game_over`；溢出显式停止 → **PASS**。
- 有界运行：`max_steps` / `max_seconds` / 协作取消 / 溢出保护。

**实测（worker 端到端，文件式交接；6 步有界运行）**：
`backend_used=cpp`，`engine_used=python_kernel`；分段（ms）：`search 17.0`、`apply_logic 0.24`、`serialize 1.56`、`write 58.6`、`checkpoint 60.2`、`wall_step 1662.7`、`wall_total 1681.0`。
→ 含首次导入/后端探测约 1.6s；**稳态单步 ≈11ms（≈90 steps/s，仅搜索+落子+每步检查点）**，与 GUI standard(≈2 步/s)/fast(≈6.6 步/s) 相比为量级提升（数值随负载变化，不作保证）。

## 4. 所有权与安全交接（P3 / P4）

- 状态机 `GUI_IDLE → HANDOFF_PREPARE → BG_RUNNING → BG_PAUSING → BG_PAUSED → BG_STOPPING → GUI_IDLE`（+`BG_COMPLETED`/`BG_ERROR`）与非法迁移拒绝，已实现于 `v6_background.py`。
- 进入后台：先按既有安全路径停止本机求解 → 等待动画结束 → 写交接检查点（棋盘/分数/**精确 RNG 状态**/修订号/算法/强度/模式）→ 再拉起 worker。
- 单写入者：`game_history/background/.bg.lock`（记录 pid）；已有后台进程时拒绝二次启动。
- 暂停 = **一致步边界停止并返回检查点**；继续 = 用该检查点（精确棋盘 + RNG 状态）重新启动（避免事件竞态）。
- 关闭窗口：协作停止 + 有界等待（6s）+ 保留检查点，超时如实提示，不盲目 `terminate()`。
- 每步持久化：worker 每步原子写 staging 检查点（`safe_store` 原子写 + fsync），**未改为批量落盘**。

## 5. 门禁 G0–G7

| Gate | 内容 | 状态 | 证据 |
| --- | --- | --- | --- |
| G0 | 入口/状态迁移识别、受保护路径、V1–V5 基线 | **PASS** | 本节 §1、`isolation`（V1–V5 未改） |
| G1 | 三档可见、强度下拉未变、迁移/重启、无隐藏状态 | **PASS** | `MIGRATION_OK`、`after_three_modes_full_game.png` |
| G2 | 无头核心无 Qt、RNG/步态等价、终局/溢出、有界取消、engine 溯源 | **PASS** | `test_v6_headless` 7 tests OK；worker 实测含 backend/engine |
| G3 | 启动/暂停/恢复/停止/关闭/重启与重复点击、无孤儿/无重复 spawn/无 Qt 冻结 | **PARTIAL / FAIL（未证实）** | 状态机与安全交接已实现；但 **交互式子进程 E2E 在本环境未在超时内完成**（见 §6） |
| G4 | 不弱于既有安全性、隔离、单写入者、崩溃/损坏恢复 | **PARTIAL** | 单写入者/检查点已实现；**正式存档每步提交在后台期间未逐笔写入**（见 §6） |
| G5 | 分段计时语义准确、可复现对比、无后端误标、CSV/JSONL | **PARTIAL** | 无头分段计时已采（§3）；GUI 侧 standard/fast 对比沿用上一轮（无动画冒充算法）；共享轨迹 A 类对照未完成 |
| G6 | 三档 UI 可见可理解、停止响应、实时进度、布局证据 | **PARTIAL** | 三档截图 PASS；后台面板与按钮已实现，**运行态截图未采集** |
| G7 | 测试矩阵与完成报告 | **PARTIAL** | migration/invariants/Qt-free PASS；lifecycle/persistence 崩溃注入未跑完 |

**按 P7 要求：后台求解未通过 G3/G4，故不设为默认**——迁移结果只可能是 `standard`/`fast`（已实测），默认仍为 `standard`；`background` 仅用户显式选择并手动点“开始”。

## 6. 未完成 / 未验证（如实）

1. **交互式子进程 E2E（G3）**：`WorkerE2ETest` 在测试守护进程内经 stdin 管道交互时未在超时内完成；同一 worker 用**文件式 stdin**（`Get-Content | python -m headless.worker_main`）可完整输出 ready→progress→final，且 `headless` 子进程/进程内调用均通过。已定位并修复两类管道陷阱（子进程与 GUI 侧 `for line in file` 预读阻塞 → 改 `readline()`；大负载（含 625 整数 RNG 状态）经交互管道不达 → 改**文件式交接** + 小命令走管道）。**仍标记 FAIL/未证实**，需在真实 GUI 进程中继续验证。
2. **正式存档每步提交（G4）**：后台期间仅写隔离 staging 检查点；停止/完成时把最终棋盘/分数/RNG 采纳回 GUI 并刷新。**官方逐笔历史在后台期间未被逐笔改写**，因此不能宣称与手工对局“每步存档”完全等价；这是本轮明确保留的限制（未擅自批量落盘，也未伪造等价）。
3. **A 类同轨迹对照（G5）**：未完成 standard GUI / fast GUI / background 的同棋盘同 RNG 严格对照（仅完成 B 类计算基准与本轮无头分段计时）。
4. **后台面板运行态截图**、真实多 DPI（125%/150%）截图：未采集。
5. `Qt5Core 0xC0000409` 确定根因仍未确定（沿用上一轮结论）。

## 7. 修改文件清单（仅 V6，除 capture 工具）

新增：
- `v6_pyqt_2048_accelerated/headless/__init__.py`
- `v6_pyqt_2048_accelerated/headless/core.py`（无 Qt 对局核心 / 快照 / RNG 状态）
- `v6_pyqt_2048_accelerated/headless/game_loop.py`（无 Qt 有界循环 + 分段计时 + 每步检查点）
- `v6_pyqt_2048_accelerated/headless/worker_main.py`（子进程 worker，stdin/stdout 行式 JSON）
- `v6_pyqt_2048_accelerated/v6_background.py`（所有权状态机 + 安全交接 + 进度面板 + 恢复）
- `v6_pyqt_2048_accelerated/tests/test_v6_headless.py`（无头/迁移/等价 E2E）

修改：
- `v6_pyqt_2048_accelerated/v6_speed.py`（三档 standard/fast/background；带版本幂等迁移；控件标签「运行方式」；桥接后台控制器；closeEvent 协作关闭）
- `v6_pyqt_2048_accelerated/v6_pyqt_2048_accelerated.py`（无改动需求，沿用既有 `_v6_speed_init` 接线）
- `tools/capture_gui.py`（V6 必需文字：运行方式 + 三档按钮；仅 v6 生效）

未改动：**V1–V5 任何源文件**；正式存档/模型/历史实验。

## 8. 真实测试命令与退出码

| 命令 | 结果 |
| --- | --- |
| `python -m unittest test_v6_headless.HeadlessQtFreeTest test_v6_headless.HeadlessCoreTest test_v6_headless.ModelEquivalenceTest` | **Ran 7 tests OK，EXIT 0** |
| 迁移幂等脚本（inline） | **MIGRATION_OK**（退出 0） |
| `python tools/capture_gui.py --version v6 --scene game --out .../after_three_modes_full_game.png` | **EXIT 0**（CAPTURE/STRUCTURE/TEXT PASS，VISUAL UNVERIFIED） |
| `python -m unittest test_v6_headless`（含 WorkerE2ETest） | **未在超时内完成 → 计 FAIL**（见 §6.1） |
| `Get-Content <start_cmd.json> \| python -m headless.worker_main` | **EXIT 0**，完整 ready→progress→final（含 backend/engine/分段耗时） |
