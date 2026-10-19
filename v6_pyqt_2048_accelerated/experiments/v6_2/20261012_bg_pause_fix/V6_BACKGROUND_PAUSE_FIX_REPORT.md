# V6 后台求解「暂停导致 Windows 未响应」——根因定位与修复报告（P0–P6）

> 仓库：`E:\PyQt5_demo\2048`；解释器：`E:\anaconda3\envs\2048\python.exe`；`PYTHONNOUSERSITE=1`。
> 仅改 V6；V1–V5 只读；未改正式存档 / RL 模型；未 Git 提交。
> 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_bg_pause_fix/`。

---

## 1. 确定根因（P0，含实测与栈证据）

**根因**：后台暂停时，GUI 在 **Qt 主线程**上对 Worker 的方向序列做**逐笔正式回放**，而官方模型
每条 `apply_move` 都触发 **2 次 `record_move`** → **全量重写 `history.csv`** + **`save_game_state`**
（`json.dumps` + 临时文件 + fsync + `.bak` 备份）；另有 `best_score.json`/`index.json` 写入。
N 步即 ~N×2 次同步落盘，主线程被长时间独占 → 窗口显示“未响应”。

**faulthandler 栈证据（改前，暂停瞬间）**：
```
Thread 0x0000ae14 (most recent call first):
  json/encoder._iterencode (json.dumps)
  safe_store.py:55 atomic_write_json
  v3_pyqt_2048_with_history.py:302 save_game_state
  v3_pyqt_2048_with_history.py:242 record_move
  v4_pyqt_2048_animated.py:335 apply_move
  v6_background.py replay_commit
  v6_background.py _replay_commit
  v6_background.py _adopt
  v6_background.py _on_msg          (type=final)
  v6_background.py _on_drain        (QTimer，GUI 主线程)
```

**改前实测（536 有效步暂停，`pause_before_fix.json`）**：

| 指标 | 改前 |
| --- | --- |
| REPLAY 耗时（主线程） | **110,969 ms** |
| 暂停期文件写入 | **1072 次 CSV + 1486 次 JSON** |
| 其中 JSON 耗时 / CSV 耗时 | 69,227 ms / 8,403 ms |
| GUI 主线程最大心跳间隔 | **111,009 ms（≈111s 无响应）** |
| 暂停总墙钟（请求→PAUSED） | 111,055 ms |

结论：**不是** Worker 未响应 PAUSE（GUI 侧 407ms 内即收到 FINAL），而是 **GUI 主线程同步逐笔持久化**。

---

## 2. 最小安全修复（P2）

核心：**把“回放计算”和“落盘”解耦**——回放期间只构建内存历史/撤销，**不逐笔落盘**；
校验通过后由 GUI 主线程做**单次原子提交** + **单次棋盘刷新**。

`v6_background.py` 新增：
- `_DeferredModelIO`：回放期临时将 `_write_history_file / save_game_state / save_best_score /
  update_index` 置为 no-op（**仅延后 I/O，内存语义完全不变**），并统计被抑制的写入次数。
- `persist_official(model)`：校验通过后**单次**提交上述四项（原子写）。
- `replay_commit(..., defer_persistence=True, stats=None)`：默认延后落盘。

保持：单一写入者（回放前校验模型棋盘=会话基准，偏离即拒绝）、完整 RNG、撤销/重做、
异常恢复、原子提交与失败回退（校验不一致则退回只读采纳并告警，后台仍为 EXPERIMENTAL）。

### 附带修复的第二个缺陷（P3）
暂停后 Worker 处于**常驻等待**（设计如此）；此时 GUI 的「停止」被 Worker 的等待循环**忽略**，
导致状态停在 `BG_STOPPING` 且进程不退出。
- `headless/worker_main.py`：等待循环对 `stop`/`quit` 都**协作退出**（不再吞掉停止）。
- `v6_background.py`：收到 `exited` 时若处于 `BG_PAUSED/BG_PAUSING/BG_STOPPING` → 收敛到 `GUI_IDLE`。

### P1 分段埋点
`BackgroundController._mark()`（`perf_counter` 单调时钟）记录：
`PAUSE_REQUESTED / WORKER_ACK(pause) / GUI_FINAL_RECEIVED / REPLAY_START / REPLAY_END(含 moves 与
被抑制写入数) / SAVE_COMMIT(含 history_rows/undo_depth/耗时) / WORKER_EXITED / OWNER_RELEASED`，
并记录主线程 ID、方向数量、历史行数、写入次数与耗时（`ctl.pause_perf()`）。
窗口若不响应，仍由 `faulthandler` + Qt fatal 取证（本轮栈即由此获得）。

### P4 终态保护
`_final_seen`：收到 FINAL 后忽略后续迟到进度帧，低 revision 快照不得覆盖终态；
周期快照仍为无动画只读刷新（不 `apply_move`/不生成方块/不写历史）；1000ms 回传不变。

---

## 3. 修复前后对比（P5，真实 GUI）

| 有效步数 | REPLAY 改前 | REPLAY 改后 | SAVE_COMMIT(单次) | 采纳总计 | GUI 最大阻塞(改后) | 暂停墙钟(改后) | 暂停期写入(改后) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 77 | — | 9.5 ms | 43.4 ms | 53.7 ms | 91.8 ms | 148.3 ms | 1 CSV / 3 JSON |
| 221 | — | 22.8 ms | 100.9 ms | 124.4 ms | 160.1 ms | 236.5 ms | 1 / 3 |
| 536 | **110,969 ms** | 58.1 ms | 256.4 ms | 315.3 ms | 340.0 ms | 407.7 ms | 1 / 3 |
| 1028 | — | 251.4 ms | 180.5 ms | 432.9 ms | 469.9 ms | 530.5 ms | 1 / 3 |

- **1000 步暂停实测**：REPLAY **251 ms**、单次提交 **181 ms**、GUI 最大阻塞 **470 ms**、
  暂停墙钟 **531 ms**（改前 536 步即 111 s）。
- 暂停期写入由 **1072 CSV + 1486 JSON** 降至 **1 CSV + 3 JSON**。
- 抽样 P50/P95（暂停墙钟，4 样本）：P50 ≈ 322 ms，P95 ≈ 531 ms；GUI 最大阻塞 ≤ 470 ms。
- 撤销/历史正确：`undo_depth == 有效步数`，`history_rows == 2×步数 + 1`。

> 说明：CPU/内存峰值与崩溃注入未采集（见 §5 UNVERIFIED）。

---

## 4. 门禁与测试（P6）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **100 tests OK（skipped=3），EXIT 0** |
| `V6_RUN_IPC_E2E=1 python -m unittest test_v6_ownership.WorkerOwnershipLifecycleTest test_v6_headless.WorkerE2ETest -v` | **3 tests OK，EXIT 0** |
| 新增回归 | 回放期零逐笔落盘（`test_replay_defers_disk_writes_until_single_commit`） |
| 新增回归 | 暂停常驻期 `stop` 必须使 worker 退出（`test_stop_while_paused_exits_worker`） |
| 保持 | 正式历史/撤销/RNG 等价（`test_replay_reproduces_official_history_and_undo`） |

修复过程中发现 3 个既有方向提示用例因**用户持久化 `run_mode=background`** 而失败
（非本修复引入的功能回归：标准档 A/B 由 `test_mode_effects_policy` 验证正常）。
已使 `ArrowKeyV6Test` / `GuiIntegrationTest` **确定性地运行在标准档**（`persist=False`），
并令迁移 v2 清理历史 `report_mode/report_value` 残留键。修复后门禁 100 项全绿。

---

## 5. 门禁结论

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| P0 根因 | **PASS** | faulthandler 栈 + 111 s/1072+1486 次写入实测 |
| P1 分段埋点 | **PASS** | `pause_perf()` 全链路标记（见 §3 表） |
| P2 主线程不再逐笔持久化 | **PASS** | 回放 0 落盘；单次提交；`test_replay_defers_*` |
| P3 PAUSE 语义 | **PASS** | 1000 步暂停 531 ms 内到 PAUSED；补修 stop-while-paused |
| P4 1000ms 回传/终态保护 | **PASS** | `_final_seen`；周期无动画只读；回传仍 1000ms |
| P5 真实 GUI 实测 | **PARTIAL** | 50/200/500/1000 步暂停实测已有；**崩溃注入、CPU/内存峰值、修复后新截图 UNVERIFIED** |
| P6 全量回归 | **PASS** | 100 单测 + 3 IPC E2E 全绿，真实退出码 0 |
| 粒子/方向光不回归 | **PASS** | `test_mode_effects_policy` + 方向提示用例全绿 |

**遗留**：后台求解仍标记 **EXPERIMENTAL**（官方逐笔历史/崩溃恢复的端到端注入用例仍为 PARTIAL）。
**UNVERIFIED**：修复后 GUI 暂停截图、DPI 缩放、CPU/内存峰值、>4 样本 P95。

---

## 6. 修改文件

| 文件 | 变更 |
| --- | --- |
| `v6_pyqt_2048_accelerated/v6_background.py` | `_DeferredModelIO`/`persist_official`；`replay_commit` 延后落盘；`_mark`/`pause_perf` 埋点；`_final_seen` 终态保护；`exited` 状态收敛 |
| `v6_pyqt_2048_accelerated/v6_speed.py` | 报告偏好迁移 v2（固定 1000ms + 清理残留键） |
| `v6_pyqt_2048_accelerated/headless/worker_main.py` | 暂停常驻期响应 `stop`/`quit` 协作退出 |
| `v6_pyqt_2048_accelerated/tests/test_v6_headless.py` | 新增回放零落盘、stop-while-paused 回归 |
| `v6_pyqt_2048_accelerated/tests/test_v6_report_policy.py` | 新增“暂停/停止后不再发周期回传”确定性用例 |
| `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` | 确定性标准档隔离 |
| `v6_pyqt_2048_accelerated/tests/test_gui_integration.py` | 确定性标准档隔离 |

未改 V1–V5、搜索内核、正式存档与 RL 模型；**未执行任何 Git 提交或推送**。
清理常驻 worker 时一律走**受支持的控制通道**（`control.json: quit`），未盲目 `taskkill`。

---

## 7. 追加修复：暂停后仍触发 1000ms 回传

**根因**：暂停/停止请求常在 `solve()` 搜索期间到达；该轮仍提交当前原子步，并在**步末**执行
周期回传检查——此时取消标志已置位，但旧代码只在**下一轮循环首**检查，故多发一帧周期回传；
GUI 在 `BG_PAUSING` 期间也仍渲染这类在途帧。

**修复**：
- `headless/game_loop.py`：周期回传前先判定 `cancel()`/`pause()`；已请求则**不发周期回传**，
  直接进入停止/暂停终态并强制 FINAL（仍完成当前原子步，不中断搜索）。
- `v6_background.py`：`BG_PAUSING/BG_STOPPING` 期间丢弃在途 `progress`（等 FINAL 强制同步）。

**真实 worker 验证**（`pause_reporting_verify.json`）：
- 运行中回传间隔 `[997.5, 1008.2, 1001.1, 1005.5] ms`（固定 1000ms）；
- **暂停 ACK 之后到 FINAL 之间的 progress = 0**；
- 暂停请求 → FINAL **6 ms**；`final_status=stopped`、`exit_code=0`；
- 持续求解到 567+ 步（越过 200/400，未因回传停止）。

**回归**：全量 **102 tests OK（skipped=3），EXIT 0**；IPC E2E **3 tests OK，EXIT 0**；
新增确定性用例 `test_no_periodic_report_after_pause_requested_mid_solve` /
`..._stop_requested_mid_solve`。

---

## 8. 追加修复：开始后台后前盘长时间无数据 / 第二次开始收不到数据

### 8.1 启动时间线实测（首次会话，`bg_start_timeline.json`）
| 事件 | 相对 START |
| --- | ---: |
| ready（子进程就绪） | 249 ms |
| warming → warmed（预热） | 249 → 249.5 ms（**warmup 31.3 ms**） |
| 首次 progress / 前盘首帧 | **1370 ms**（41 步） |
| 后续回传 | 1372/2372/3375/4374… 每 ~1000 ms |
| 停止 → FINAL → exited | 20121 / 20450 ms |

结论：**首次启动无逻辑卡死**；空窗主要来自“首帧要等满 1000ms”+ 子进程启动 ~250ms。

### 8.2 复现：第二次开始后台时前盘收不到数据（`bg_restart_repro.json`，修复前）
| 会话 | worker 发出的 progress | 实际渲染 | 起始现状 |
| --- | ---: | ---: | --- |
| 第 1 次 | 3 | **3** | rendered=-1 / adopted=-1 |
| 第 2 次 | 3 | **0** | rendered=122 / admitted=155 |

**根因**：`_rendered_revision` 与 `_adopted_revision` 是**跨会话**残留。新会话 revision 从 0 起，
被上一会话的高位值当作“过期帧”全部丢弃（`rev <= _rendered_revision` / `rev < _adopted_revision`），
直到新 revision 超过旧值才突然渲染几帧——正是“长时间等待后闪过几个步骤切片”。

### 8.3 修复
1. `v6_background._reset_session_tracking()`：每次 spawn（含 resume）重置
   `_rendered_revision/_adopted_revision/_last_render_step/_last_render_t/_final_seen`。
2. `headless/game_loop.py`：时间策略**首步完成即回传一帧**（`_bootstrap`），随后恢复固定 1000ms；
   步数策略仍保持严格整数倍语义。

### 8.4 修复后复测（同一脚本）
- 第 2 次会话：progress 4 → **renders 4**（修复前 0）。
- 首帧 = **revision 1 / 第 1 步**（修复前首帧 1370ms、且第二次永不显示）。

### 8.5 回归
- 全量门禁：**104 tests OK（skipped=3），EXIT 0**
- 显式 IPC E2E：**3 tests OK，EXIT 0**
- 新增用例：`test_new_session_resets_revision_tracking`、
  `test_time_policy_reports_first_step_bootstrap`。

---

## 9. 回传优化：固定 500ms + 每批只渲染最新帧

**变更**：
1. `v6_background.REPORT_INTERVAL_MS: 1000 → 500`（仍为单一内部来源）；偏好迁移 **v3**
   （`report_prefs_version=3`、`report_interval_ms=500`，清理旧 `report_mode/report_value`）。
2. `BackgroundController._on_drain()`：一次排空时**只保留 revision 最大的一帧 progress** 渲染，
   控制/终态消息仍按序处理。避免“一次涌入多帧时连续闪过好几批步长切片”。

**真实 worker 实测**（`report_500ms_verify.json`）：
- 8 次回传，间隔 `[505.5, 504.7, 509.0, 507.7, 501.6, 508.5, 514.7] ms`，均值 **507.4 ms**；
- revision / steps **严格递增** → 每次都是**最新已提交帧**；
- 回传 `max_tile` 与 `board` 最大值一致；首帧 revision=1（首步立即回传）；退出码 0。

**回归**：全量 **105 tests OK（skipped=3），EXIT 0**；IPC E2E **3 tests OK，EXIT 0**；
新增 `test_drain_coalesces_progress_to_newest`（断言一次排空只渲染最新一帧）。
> 已运行的旧 GUI 需重启后才会加载 500ms 常量与迁移 v3。

---

## 10. 确认：500ms 回传下未再出现“未响应”

真实 GUI 实测（`report_500ms_gui_check.json`，隔离存档）：

| 指标 | 数值 |
| --- | --- |
| 回传策略 | `{'mode': 'time', 'ms': 500}` |
| 8s 运行内前盘刷新 | 16 帧（≈500ms/帧，首帧第 1 步） |
| 单帧无动画渲染耗时 | 0.03 – 0.54 ms |
| **运行期 GUI 主线程最大阻塞** | **47.9 ms** |
| 暂停回放（301 方向） | **23.4 ms** |
| 暂停墙钟（请求→PAUSED） | 145.7 ms |
| **含暂停的 GUI 主线程最大阻塞** | **128.3 ms** |
| 结束状态 | `GUI_IDLE`（worker 已退出，无遗留进程） |

对比故障基线：536 步暂停曾阻塞 **111,009 ms**（Windows 未响应）。现 500ms 模式下运行期 ≤48ms、
暂停期 ≤129ms，**远低于 Windows“未响应”判定阈值（约 5s）**。
**结论：未响应问题已解决，且未因回传频率加倍（1000→500ms）而回归。**
