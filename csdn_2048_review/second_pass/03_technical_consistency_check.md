# 第二轮技术一致性核查

## 1 重点：6b 的 500ms 与 1000ms

### 1.1 源码事实

| 检查点 | 文件/位置 | 当前值 | 结论 |
| --- | --- | --- | --- |
| 回传周期常量 | `v6_pyqt_2048_accelerated/v6_background.py:61` | `REPORT_INTERVAL_MS = 500` | 当前实现为 500ms |
| 回传策略 | 同文件 `:168-170` | `{'mode': 'time', 'ms': REPORT_INTERVAL_MS}` | 定时回传，单一来源 |
| 会话限制 | 同文件 `:522-525` | `progress_interval_s: 0.5` 仅心跳/检查点提示 | 不是第二个可配置周期 |
| 偏好文件 | `v6_pyqt_2048_accelerated/config/ui_prefs.json` | `report_prefs_version: 3`、`report_interval_ms: 500` | 迁移后为 500ms |
| 旧 UI | 已移除 | 无 N 步/N 时间选择器 | 500ms 不暴露给用户 |

### 1.2 冲突判定

- **当前待发布版本 = 500ms**。这是源码常量、偏好文件与迁移版本三者一致的结果。
- **1000ms = 早期设计目标**，已被当前实现取代。它不是“另一个生产值”，也没有在代码中作为默认值存在。
- 第二轮没有修改 `REPORT_INTERVAL_MS`，没有改偏好文件，也没有把文章改成 1000ms 来“统一文稿”。
- 文章的处理方式是：在 §7 保留版本口径说明，在 §7.1 用来源矩阵明确“以源码为准”，并在结论中写明“当前待发布版本是 500ms”。

### 1.3 为什么不能反过来写

如果按旧设计目标把文章写成 1000ms，会与读者实际运行得到的 500ms 行为不符；如果为了迎合文章把代码改成 1000ms，则违反“不得改源码”的限制。唯一诚实的处理是：**代码事实优先，设计目标留痕**。

## 2 逐篇源码对应

| 文章 | 核心技术主张 | 对应源码/证据 | 第二轮是否改动代码/公式 | 状态 |
| --- | --- | --- | --- | --- |
| 01 | 合并、计分、随机 90/10、胜负、主循环 | `v1_console_2048/v1_console_2048.py`；`solver_2048.move_grid` 实跑 | 否 | VERIFIED |
| 02 | 原子写、`.bak` 回退、CSV 重写、活档、RNG 缺失 | `v2_console_2048_with_history.py`、`safe_store.py` | 否 | VERIFIED |
| 03 | MVC、434×434、快照 undo/redo、最高分单调 | `v3_pyqt_2048_with_history.py`、`v4` 常量 | 删除重复 `_merge_line` 展示代码（语义不变） | VERIFIED |
| 04 | 双阶段动画、16ms 目标 tick、粒子、整控件重绘 | `v4_pyqt_2048_animated.py`（`MOVE_DURATION/POP_DURATION/FRAME_INTERVAL`） | 否 | VERIFIED |
| 05a | 五类算法、评估函数、预算、MCTS 不变量、RL | `v5_pyqt_2048_solver/solver_2048.py`、`rl_2048.py`、`tests/` | 否 | VERIFIED + HISTORICAL |
| 05b | QThread、`job_id`、快照校验、提示层、折叠 | `v5_pyqt_2048_solver.py`、`test_solver.py` | 否 | VERIFIED + HISTORICAL |
| 06a | 四后端、Bitboard、回退、基准分层 | `solver_backends/*`、`benchmarks/reports/summary.md` | 否 | VERIFIED |
| 06b | 无头 Worker、IPC、所有权、检查点、500ms、FINAL | `headless/*`、`v6_background.py` | 否 | VERIFIED |
| 06c | 三档模式、暂停、跨模式交接、单一写者 | `v6_speed.py`、`v6_background.py`、`cross_mode_e2e.json` | 否 | VERIFIED + VISUAL UNVERIFIED |

## 3 术语一致性

| 术语 | V5 含义 | V6 含义 | 文中处理 |
| --- | --- | --- | --- |
| 运行方式 | 求解强度（快速/标准/强力） | 标准/快速/后台求解 | 5b 明确写“V5 的运行方式=强度”；6a/6b/6c 明确 V6 三档 |
| 求解强度 | 同 V5 运行方式 | 改名后的算法参数档位 | 6a 说明“运行时改名，选项不变” |
| 求解模式 | 自动连走 / 单步建议 | 同 V5 | 6b 说明后台只支持自动连走 |
| 暂停 | 无 | 安全步边界暂停 | 5b 明确 V5 无暂停；6b/6c 描述 V6 |
| 单一写者 | 同进程任务身份 | 进程级 owner + 心跳 | 5b 与 6b/6c 分层说明，不混用 |

## 4 公式与代码完整性

- 第二轮没有修改任何数学公式；`$$` 数量为偶数（01: 72、05a: 38、05b: 6，其余 0）。
- 01 的合并示例、03 的 `_slide`、04 的 `_tick`、05a 的递推、06b 的状态机代码块均保留。
- 03 删除的是与第 1 篇重复的 `_merge_line` 代码块，`_slide` 仍调用 Model 中的同名方法，语义未变。
- 代码围栏成对；相对链接/图片在 `second_pass/articles/` 下均存在（校验 exit 0）。

## 5 测试与证据

- 第一轮已复跑 202 项测试，全部 exit 0（95+28+5+5+41+17+11）。
- 第二轮未重跑全部 GUI/算法套件，避免重复占用；执行了交付校验（见 05 门禁）与链接/公式结构检查。
- 6c 的 22/22 E2E 与 62188 夹具说明保留；6a 的基准数值仍来自 `benchmarks/reports/summary.md`，未新增实验。
- 未验证项：CSDN 在线公式渲染、CSDN 图片 URL、V3 DPI、V4 实际帧率、5b 提示层像素数据、5a `8.5e-14`、6b 111s 原始日志。

## 6 结论

第二轮没有引入新的技术主张，所有新增内容都是对第一轮已核实事实的结构化重述或边界说明。唯一的高风险冲突（6b 500/1000）已按源码事实收敛，并保留了设计演进记录。
