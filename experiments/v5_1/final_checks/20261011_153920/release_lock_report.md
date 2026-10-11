# V5.1 · H8 最终稳定性优化与发布锁定报告（release_lock_report）

> run: `20261011_153920` ｜ 基线 HEAD：`ddbf0e5` ｜ 平台：Windows ｜ 解释器：`E:\anaconda3\python.exe`
> 原则：所有结果来自实际执行；未执行/未人工确认项标 `UNVERIFIED`，不虚报。

## 1. H8 门禁表

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| `H8_BASELINE_PASS` | **PASS** | git/HEAD、源码审计、模型哈希、证据目录 |
| `INFLIGHT_CANCEL_SAFETY_PASS` | **PASS** | C01–C06 6/6（真实进入计算 + 迟到信号） |
| `GUI_THREAD_LIFECYCLE_PASS` | **PASS** | 无销毁告警/无泄漏；3 组不同顺序 OK |
| `H8_TESTS_PASS` | **PASS** | 186/186，失败 0，跳过 0 |
| `H8_MODEL_IMMUTABLE_PASS` | **PASS** | 四模型 SHA256 前后一致 |
| `H8_BENCHMARK_REUSE_PASS` | **PASS** | 历史轻量实验未重跑、与文档一致 |

## 2. 九项独立发布门禁

| # | 门禁 | 状态 |
| --- | --- | --- |
| 1 | `V5_1_CODE_PASS` | **PASS** |
| 2 | `V5_1_INFLIGHT_CANCEL` | **PASS** |
| 3 | `V5_1_THREAD_SAFETY` | **PASS** |
| 4 | `V5_1_GUI_AUTOMATED` | **PASS** |
| 5 | `V5_1_GUI_VISUAL` | **UNVERIFIED** |
| 6 | `V5_1_DPI_VISUAL` | **UNVERIFIED** |
| 7 | `V5_1_MODEL_INTEGRITY` | **PASS** |
| 8 | `V5_1_TESTS` | **PASS** |
| 9 | `V5_1_RELEASE_READY` | **PARTIAL_PASS**（人工视觉未确认） |

## 3. 本轮真实修改与根因

| 文件 | 根因 | 修改 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` | 停止时 `wait(3000)` 阻塞 GUI 主线程约 3s（实测 3011ms） | 短等待常量 + `_wait_retired` + 关闭有界等待 |
| `v5_pyqt_2048_solver/test_solver.py` | 缺真正“运行中取消”确定性覆盖 | 阻塞式夹具 + C01–C06（79 条） |
| 四张整窗截图 | H8-3 视觉证据 | 真实桌面重捕获 |

**未修改**：算法核心、RL、v1–v4、游戏规则、默认参数。

## 4. 在途取消（C01–C06）摘要

| 场景 | entered_compute | 关键结果 |
| --- | --- | --- |
| C01 停止在算 | ✅ | `stop_block` **3011ms→507ms**；棋盘不变；结果不落地 |
| C02 旧 solved 迟到 | ✅ | 被丢弃；新任务在途标志保持 |
| C03 旧 failed 迟到 | ✅ | 被丢弃；新任务运行态不变 |
| C04 关闭在算 | ✅ | 线程最终结束；**QThread 销毁告警 0** |
| C05 10× 在途取消 | ✅×10 | job_id `1..10` 唯一；`live_threads=0` |
| C06 UI 操作在途 | ✅ | 无重复提交/落子；展开入口可用 |

详见 `inflight_cancellation_results.md/.json`。

## 5. 线程安全修复（H8-2）前后

| 指标 | 前 | 后 |
| --- | --- | --- |
| C01 交互停止阻塞 GUI | 3011ms | **507ms** |
| 真实求解在途停止 | ~3s 上限 | expectimax 363/460ms、mcts 946/1016ms |
| C04 关闭线程销毁告警 | 0 | 0 |
| terminate 使用 | 无 | 无 |

## 6. GUI 四场景截图（实际路径）

`v5_pyqt_2048_solver/screenshots/full_start.png`、`full_game.png`、`full_solver.png`、`full_collapsed.png`（均为真实桌面整窗，CAPTURE/STRUCTURE/TEXT PASS，**VISUAL=UNVERIFIED**）。

## 7. DPI

100% 真实捕获通过（dpr=1.0）；125%/150% 受控 Qt 模拟通过（dpr=1.25/1.50，`h8_dpi_sim.txt`）；**真实多 DPI 人工视觉 `UNVERIFIED`**。

## 8. 测试

186/186 通过（test_solver 79 + 其余 8 套），失败 0，跳过 0；另 3 组不同顺序 lifecycle 各 4/4 OK。命令与证据见 `test_summary.json` / `test_results.txt`。

## 9. 模型完整性（SHA256 前后一致）

`rl_model.npz=ee4b370e67676bfb…`、`candidate=ee4b370e67676bfb…`、`prev=724c4eea877421cf…`、`baseline/rl_model_v1.npz=724c4eea877421cf…`。`EQUAL_TO_BEFORE=True`。

## 10. 剩余风险 / 发布建议

- **可冻结** `v5.1-stable-candidate`（代码稳定候选）：代码/取消/线程/自动化视觉/模型/测试全部 PASS。
- **正式发布** 需先完成两项人工确认（见 `manual_visual_checklist.md`）：① 目视 4 张整窗截图后 `--visual-confirm`；② 真实 125%/150% 缩放走查。完成后 `V5_1_RELEASE_READY` 方可升为 PASS。
- 建议延至 **V5.2/V6**：RL 迭代（回放/自适应）、C++ bitboard 后端、公平统计扩样、本地/联机多人。
- 本轮未自动创建 tag/提交/推送。
