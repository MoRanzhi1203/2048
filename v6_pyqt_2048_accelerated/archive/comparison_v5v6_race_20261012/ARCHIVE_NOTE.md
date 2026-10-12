# ARCHIVE · V5.1↔V6.2 双窗口并排竞赛（已冻结，仅存档）

**归档日期**：2026-10-12
**归档原因**：用户决定停止「V5 正式界面改造 / 双窗口并排竞赛 / 竞赛 HUD / 进程协调」方向；
后续只对 V6/V6.2 正式程序做单程序优化，V1–V5 全部只读。

## 内容（全部为只读存档，未删除、未覆盖）

| 目录 | 内容 |
| --- | --- |
| `comparison/` | 竞速工具源码：`race_protocol.py`（会话/控制/汇总协议）、`race_common.py`（RaceMixin + HUD）、`race_window_v5.py` / `race_window_v6.py`（以子类复用 V5/V6 GUI，未改动其源码）、`race_launcher.py`（启动协调器 + Win32 左右并排 + 控制命令）、`README.md` |
| `race_experiments/` | 全部竞赛会话原始数据：`session.json` / `control.json` / `launch.json` / `side_v5.jsonl` / `side_v6.jsonl` / `hud_*.json` / `race_summary.*` / `proc_*.log` / 桌面截图 |

## 归档时已确认的结论（供后续参考，不构成本轮结论）

- 两个进程均能独立启动、左右并排（工作区 1536×824，两窗各 739×614，无重叠），各自独立存档目录与单实例锁。
- 初始棋盘一致（seed=2048 → `[[0,0,0,0],[0,0,2,0],[0,2,0,0],[0,0,0,0]]`）；
  在未崩溃区间内，两侧 `direction/score/max_tile` 逐步一致（未出现算法分叉）。
- 单侧平均搜索耗时（Expectimax normal, depth=4, time_limit=0.3）：
  V5 纯 Python reference ≈ 43–47ms；V6 cpp primitives ≈ 18.7–19.7ms（约 2.3x）。
- **重要环境问题**：存在间歇性 Qt 原生 abort（事件日志：模块 `Qt5Core.dll`，异常码 `0xc0000409`，
  偏移 `0x204e8`）；该签名的崩溃在**本任务开始前**（2026-10-12 02:56）即已出现，
  故判定为既有环境问题而非本方向引入；仍需在 V6 单程序内进一步复现与诊断（见本轮 P1）。

## 恢复方式

如需重启该方向：把 `comparison/` 放回 `v6_pyqt_2048_accelerated/`，并按 `comparison/README.md` 运行
`race_launcher.py start`。注意其依赖 `2048_HISTORY_DIR` 重定向与 `V6_RACE_SESSION`。
