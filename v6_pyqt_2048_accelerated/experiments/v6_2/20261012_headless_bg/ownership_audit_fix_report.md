# V6 后台求解「已有进程持有本局」专项审计与修复

> 日期：2026-10-12　范围：仅 V6；V1–V5 只读；未自动提交 Git；未重训 RL。
> 证据目录：`v6_pyqt_2048_accelerated/game_history/background/`（`_repair_evidence.json`、`released.json`）

## 1. 根因（证据链）

审计时读取 `game_history/background/.bg.lock`：
```json
{"pid": 37176, "game_id": "20261012_170526_bg", "started_at": "2026-10-12 17:05:26"}
```
- `Get-Process -Id 37176` → **NOT ALIVE**；进程身份查询 `create_time/image` 均为 null（进程不存在）。
- 同目录存在该会话的 `_handoff.json`(17:05:26) / `_resume.json`(17:05:34) / `_checkpoint.json`(17:05:39)，
  说明当时确实跑过后台会话（开始→暂停→继续→每步检查点）。
- **结论：不是“后台进程真遗留”，也不是“GUI 未重连”，而是「进程已退出但所有权记录没有清理」的 stale lock。**
  触发路径：当时 GUI 被**强制结束**（未走 `closeEvent`）→ GUI 侧 `_cleanup_worker()`（旧实现里唯一删除锁的路径）未执行 →
  worker 结束后无人清理 `owner/lock` → 下次启动被“已有进程持有”拒绝。
  次要放大因素：旧实现把锁写在 GUI 侧、且 worker 退出时不清理；无启动期恢复/GC。

附带发现（一并清理，均已按身份验证）：3 个我此前诊断遗留的 **空闲** `python -m headless.worker_main`
孤儿进程（16:11/16:17/16:25 启动，父进程已退出）。它们不持有任何对局所有权，但证明“孤儿 worker”确会发生。

## 2. 修复（源码）

新增 `headless/ownership.py`（**无 Qt**）：所有权/心跳/控制/恢复，含：
- **身份验证（禁止仅凭 PID）**：pid 存活 + `GetProcessTimes` 创建时间一致（PID 复用判定）+ 镜像名一致 + 心跳新鲜（默认 20s）+ session_id 一致；状态 `absent/alive/stale/malformed`。
- **安全释放**：`release_stale()` 释放前**二次校验**（记录未变、仍非 alive、session 可选匹配），随后写 `released.json` 释放标记再删除；对 `alive` 一律拒绝释放。
- **检查点选择**：`latest_checkpoint()` 取最新且可解析的 `*_checkpoint/_resume/_handoff.json`（损坏自动跳过）。

`headless/worker_main.py`：
- worker 作为**唯一写者**：启动时写 `owner.json`（含 pid/创建时间/镜像/session_id）+ 每进度刷新心跳；
- `finally` 中释放 `owner.json`/`heartbeat.json`（正常/异常退出都清理）；
- 新增**低频(200ms)控制文件轮询**，使 GUI 重启后仍可**重连并停止/暂停**（只处理新写入记录，忽略 `running` 状态写入）。

`v6_background.py`：
- `recover_on_start()`：启动时审计所有权 → `alive` 则**重连**（显示进度、可停止/暂停）；`stale/malformed` 则**原子释放 + 按最新有效检查点恢复当前棋盘**；`absent` 无动作。
- `stop/pause` 优先管道、无管道回落控制文件；`resume` 支持 worker 已退出时用暂停点重新拉起（精确棋盘 + RNG）。
- 关闭默认行为：协作停止 → 有界等待（管道 + owner 消失双路判定）→ 释放所有权；**超时返回 False 并明确提示**，不静默强杀（`kill()` 仅最后手段）。

`v6_speed.py`：`_v6_speed_init()` 末调用 `ctl.recover_on_start()`（V6 启动即恢复）。

## 3. 一致性与恢复测试（真实退出码）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 所有权/心跳/恢复/worker 生命周期 | `python -m unittest test_v6_ownership` | **Ran 12 tests OK，EXIT 0**（2.2s） |
| 真实修复动作 | 修复脚本（`_repair_evidence.json`） | 释放 legacy 锁 pid=37176（**pid not alive + 二次复验**），新格式 owner 状态 = `absent`，最新检查点 = `20261012_170526_bg_checkpoint.json` |
| 孤儿 worker 清理 | 逐 PID 校验命令行后停止 | 3 个 `-m headless.worker_main` 已停止；**身份不匹配者一律不杀**；终态无残留 python 进程 |

覆盖的用例：不存在 / 仅 PID 不可信（记录创建时间+镜像） / PID 复用（创建时间不符） / 心跳超时 / malformed /
活动 owner 拒绝释放 / session 不匹配拒绝释放 / 释放后状态为空 + 释放标记 / 最新检查点选择 / 损坏检查点跳过 /
worker 写 owner 并在退出时释放所有权。

## 4. 尚未完成 / 未验证（如实）

- **GUI 内端到端**（在真实窗口中点 开始/暂停/继续/停止/关闭、重连后点停止）**本轮未跑完**：仅完成无 Qt 的模块级与 worker 级验证；GUI 侧 `recover_on_start` / `_watch_heartbeat` / `closeEvent` 仍未在真实窗口交互下取证。
- **崩溃注入矩阵**（进程异常消失、检查点损坏后 GUI 恢复、磁盘错误、锁超时边界）仅覆盖了其中一部分（进程消失/损坏检查点已测）。
- 旧的 `.bg.lock` 兼容清理仍在 `_cleanup_worker` 中保留（仅清理遗留文件），新逻辑统一走 `owner.json`。
- `Qt5Core 0xC0000409` 根因仍不确定（与前几轮一致）。

## 5. 修改文件
- 新增：`headless/ownership.py`、`tests/test_v6_ownership.py`
- 修改：`headless/worker_main.py`、`v6_background.py`、`v6_speed.py`
- 未改动：V1–V5 任何源文件、正式存档本体、RL 模型
