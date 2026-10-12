# V6 后台求解 · 稳定性专项收口报告（本轮）

> 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`。范围：仅 V6；V1–V5 只读；未提交 Git；未重训 RL。
> 真实性：未通过的门禁保留 FAIL/PARTIAL；未用短程推算长程吞吐。

## 1. P0 根因证据（先证伪再定因）

**(a) 证伪“7.9KB 管道负载 / for-line 预读”假说**（按负载扫描，交互式管道）：

| 负载字节 | 普通 `python -c` 子进程回显 | 真实 `headless.worker_main`（ping） |
| --- | --- | --- |
| 16 / 1024 / 4096 | 全部原样回显 | — |
| 8192 | 回显 8192 | pong=True（8178B） |
| 16384 / 65536 / 131072 | 全部原样回显 | pong=True（16370B / 65522B） |

→ 管道可正常承载 **≥131KB**；**负载大小不是原因**（上轮报告的“7.9KB 不达”判断**予以更正**）。

**(b) 真正导致“交互式 E2E 超时”的原因（已定位）**

1. **一次性重导入发生在 worker 首次求解内**：以 `V6_WORKER_DUMP=1` 触发 `faulthandler.dump_traceback_later` 抓栈，卡点为
   `numpy/__init__.py → numpy/core → …`，调用链：
   `worker_main.main → game_loop.run_session → solver_v6.solve → solver_backends/api.py:validate_board → api.py:_cell_int → import numpy`。
   即首个 `solve()` 里触发 numpy 冷导入，耗时超过测试/基准的超时阈值 → 表现为“无 progress”。
   把预热显式化后（`warming`/`warmed`）可达 `warmed`，但**首个 solve 仍未在 300s 内返回**，下一个高度可疑点是由 `probe_backends` 触发的 **numba 冷导入**（未最终确证）。
2. **子进程侧 `for line in sys.stdin` 预读阻塞** → start 命令不被处理（已改为 `readline()`）。
3. **父进程侧 `for line in proc.stdout` 预读阻塞** → 进度消息延迟到达（诊断脚本中已改 `readline()`）。
4. **管道背压**：父进程不持续排空 stdout 时，worker 会阻塞在进度写入 → 表现为挂起（测试已加 drain 线程）。
5. **控制文件 watcher 覆写 `last_cmd`** → 收到 stop 后 worker 不退出（已限定只处理新写入的 stop/pause/quit）。

## 2. P1 协议（已统一）

worker→GUI：`ready / ack / warming / warmed / progress / final / exited / error / pong`；
GUI→worker：`start / pause / stop / quit / ping`。
- 每条 worker 消息带 **`seq`**（单调递增，`_SEQ` 加锁）；控制命令返回 **`ack`**；
- **FINAL 之后必须等到 `exited`（含 code）+ 进程 `returncode` + `owner.json` 消失**，测试已断言（`WorkerE2ETest` 尾部）。
- **STOP 与 PAUSE 不再混淆**：`pause` → FINAL(status=`paused`) 且进程保活等待恢复；`stop` → FINAL(status=`stopped`) 且进程**退出**（`last_cmd=='stop'` 分支）。

## 3. P2 所有权（已加固并实测）

- 身份 = pid **存活** + `GetProcessTimes` 创建时间一致（PID 复用判定）+ 镜像名 + 心跳新鲜(≤20s) + `session_id`。
- 释放 = **释放前二次校验**（记录未变、仍非 alive、可选 session 匹配）→ 写 `released.json` 标记 → 删除；`alive` 一律拒绝。
- 本轮真实修复：验证 `pid 37176` 已不存在（二次复验）后原子释放 legacy `.bg.lock`（证据 `_repair_evidence.json` / `released.json`）；3 个孤儿 `-m headless.worker_main`（命令行验证身份）停止，**身份不匹配者未强杀**。
- 唯一写者：`owner.json` 与心跳由 **worker** 持有并在 `finally` 释放；GUI 只读校验。

## 4. P3 存档一致性 —— **FAIL（未通过）**

- **事实**：`headless/core.py` 只维护棋盘/分数/最高分/RNG/修订号；**不产生**正式对局的**逐笔历史记录与撤销/重做栈**（V3/V4 模型的 `record_move`/`undo_stack` 语义）。
- 因此后台每步 staging 检查点**无法等于**正式存档的每步提交（棋盘/分数/RNG 可一致，历史与撤销栈缺失）。
- 按既定规则：**正式历史一致性未通过 → 后台功能不得标记为“正式稳定”**。本轮据此对 GUI 文案标注“预热/实验性”，并维持后台**非默认**。
- 未重复建设不兼容格式：staging 复用 `safe_store` 原子写 + 与正式同源的 `solver_2048` 规则；Qt-free 存储抽取**未完成**（需下一轮）。

## 5. P4 测试与基准（真实退出码）

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 所有权/心跳/恢复/worker 生命周期 | `python -m unittest test_v6_ownership` | **Ran 12 tests OK，EXIT 0** |
| 无头核心（Qt-free/等价/迁移等，除交互 worker） | `python -m unittest test_v6_headless.HeadlessQtFreeTest HeadlessCoreTest ModelEquivalenceTest` | **Ran 7 tests OK，EXIT 0** |
| 有界性能基准（warmup + 100/500/1000） | `python benchmarks/run_bg_steps_bench.py` | **EXIT 1 — FAIL（超时）**：截至超时仅收到 `['ready','ack','warming','warmed']`，即**首个 solve 未在 300s 内返回**；日志 `experiments/v6_2/20261012_headless_bg/staging/*_stderr.log` |
| 交互式 IPC E2E（`WorkerE2ETest`） | 同上文件 | 本轮**未复跑完成**（受同一首解阻塞影响）→ 计 FAIL |

→ **未获得 100/500/1000 步真实吞吐数据**；明确**不以 6 步推算的 ~90 步/s 作为正式结论**。

## 6. P5 门禁 G0–G7（沿用并更新）

| Gate | 状态 | 依据 |
| --- | --- | --- |
| G0 入口/状态/基线 | **PASS** | 源码审计 |
| G1 三档可见/迁移/重启 | **PASS** | `MIGRATION_OK`（上轮）+ 截图 |
| G2 无头核心无 Qt/等价/终局/溢出 | **PASS** | 7 tests OK |
| G3 生命周期（启停/暂停/恢复/关窗/重启/崩溃） | **FAIL** | 交互 E2E 与基准超时；仅模块级通过 |
| G4 存档安全/隔离/单写者/崩溃恢复 | **PARTIAL**（正式历史一致性 **FAIL**） | 见 §4 |
| G5 分段计时/可复现基准 | **PARTIAL** | 仅无 Qt 分段可用；100/500/1000 未完成 |
| G6 三档 UI/进度/停止响应 | **PARTIAL** | 预热文案已加；运行态截图未取 |
| G7 测试矩阵与报告 | **PARTIAL** | 见 §5 |

**后台仍不默认启用**（`ui_prefs.json` 目前为 `background` 是用户界面选择所致；建议改回 `standard`）。

## 7. 修改文件（本轮）
- `headless/worker_main.py`：`seq`/`ack`/`exited`；`warming`/`warmed` 显式预热；`V6_WORKER_DUMP` 诊断；控制 watcher 只处理新 stop/pause/quit。
- `v6_background.py`：`_on_msg` 处理 `warming/warmed/ack/exited`（显示预热与退出码+所有权状态）。
- `tests/test_v6_headless.py`：drain 线程 + `_read_until` 缓冲化 + FINAL→exited→exit code→所有权释放 断言 + `ownership` 传参。
- `benchmarks/run_bg_steps_bench.py`（新增）：有界 100/500/1000 步分段基准（含预热口径）。
- 未改动 V1–V5、正式存档本体、RL 模型。

## 8. 遗留风险
1. **首解冷导入（numpy/numba）阻塞**：需在 worker 启动时**预导入全部后端**（含 numba）或在 GUI 侧提供“预热”状态与更长超时；否则后台首次启动体验即“卡住”。
2. 正式历史/撤销栈与后台不一致（P3 FAIL）。
3. G3/G4 未通过 → 后台保持实验性、非默认。
4. `Qt5Core 0xC0000409` 根因未定。
