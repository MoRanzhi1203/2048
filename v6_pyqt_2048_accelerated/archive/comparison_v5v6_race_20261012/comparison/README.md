# V5.1 ↔ V6.2 双窗口实时 AI 求解对比（comparison）

在**真实 Windows 桌面**上同时启动 **V5.1** 与 **V6.2** 两个**独立 PyQt5 进程**，左右并排、
各自独立存档/会话/单实例锁，自动连走同一初始棋盘并实时对比搜索性能。

本目录**不修改 V5/V6 源码**：两侧窗口分别以子类复用
`v5_pyqt_2048_solver.SolverMainWindow` 与 `v6_pyqt_2048_accelerated.V6MainWindow`，
仅叠加竞速协调（种子/初始棋盘、控制文件、计时、HUD、上限）。

## 一键启动

```powershell
$env:PYTHONNOUSERSITE = "1"
cd e:\PyQt5_demo\2048
python v6_pyqt_2048_accelerated\comparison\race_launcher.py start `
    --mode B --max-steps 200 --max-seconds 180
```

默认 **模式 B 自由竞速**、Expectimax 标准参数（depth=4, time_limit=0.3）、种子 2048、
最多 200 步或 180 秒。窗口保持打开供人工观察（不加 `--auto-exit`）。

## 三种模式

| 模式 | 说明 |
| --- | --- |
| `--mode A` | 同步逐步：由协调器按步进屏障推进（`--step-interval-ms` 控制最小间隔） |
| `--mode B` | 自由竞速（默认）：两侧各按自身动画/求解速度连走 |
| `--mode C` | 固定工作量：`--fixed-work` 等价（prune=False，不采样/不截断，同深度同步数） |

## 常用参数

```
--strategy expectimax            # 算法（默认 expectimax）
--depth N / --time-limit S       # 覆写深度 / 单步时间预算（两侧一致）
--fixed-work                     # 固定工作量对照（prune=False, 无采样/截断）
--v6-native                      # V6 侧 native_search=True（C++ 整树），报告 engine_used=native
--v6-backend reference|cpp|...   # V6 侧计算后端（默认 auto）
--seed 2048                      # 可复现种子（两侧一致）
--max-steps 200 --max-seconds 180
--auto-exit                      # 达到上限后自动关窗（冒烟/脚本化用）
--foreground                     # 前台协调：A 模式推进步进，结束写汇总
--particles                      # 保留粒子特效（默认竞赛态关闭以降低渲染压力；两侧始终一致）
```

## 会话控制（对已有会话操作）

```powershell
$L = "v6_pyqt_2048_accelerated\comparison\race_launcher.py"
python $L pause   --session-dir <dir>
python $L resume  --session-dir <dir>
python $L step    --session-dir <dir>     # A 模式手动推进一步
python $L stop    --session-dir <dir>
python $L reset   --session-dir <dir>
python $L close   --session-dir <dir>     # 关闭对比会话（两侧窗口自行 close）
python $L summary --session-dir <dir>     # 生成/刷新 race_summary.json + .csv
```

## 产出（均在 `experiments/race/<session_id>/`，ASCII 文件名、UTF-8）

- `session.json` / `control.json` / `launch.json`（含 pids 与并排几何）
- `side_v5.jsonl` / `side_v6.jsonl`（逐步：方向、solver_ms、wall_search_ms、nodes、
  backend_used、engine_used、分数、最大瓦片、墙钟）
- `hud_v5.json` / `hud_v6.json`（最新指标快照：avg/p95、累计搜索/动画/调度、sims、状态）
- `race_summary.json` / `race_summary.csv`（汇总 + 是否同初始棋盘 + 首个分叉步骤）
- `proc_v5.log` / `proc_v6.log`（子进程 stdout/stderr）
- `excepthook.log`（若有槽函数异常：记录栈，且不触发 PyQt5 abort）
- `race_desktop.png`（真实桌面整屏截图，人工核对并排）

## 数据隔离（不触碰生产存档）

每侧通过 `2048_HISTORY_DIR=<session>/history/<side>` 重定向：V5 落 `<...>/v5/v5`、
V6 落 `<...>/v6/v6`，各自独立单实例锁；**不写入 v1–v5 的 `game_history/`**。
初始棋盘用「共享种子 + 进程内 `random.seed()` + 内存注入」复现，不经任何生产存档。

## 已知环境问题

本机存在**间歇性 Qt5 原生 abort**（事件日志：模块 `Qt5Core.dll`、异常码 `0xc0000409`），
在本任务开始前（例如 2026-10-12 02:56）就已出现；两侧窗口由同一 Qt 运行时承载，故可能偶发
一侧进程退出。已做缓解：竞赛态默认关闭粒子层、放宽步间停顿、安装自定义 `sys.excepthook`
（避免 PyQt5 槽异常触发 abort 并把栈写入 `excepthook.log`）。协调器会检测进程退出并如实记录。
