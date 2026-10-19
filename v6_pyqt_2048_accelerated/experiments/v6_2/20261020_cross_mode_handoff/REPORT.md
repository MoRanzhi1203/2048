# V6 跨运行方式安全交接（暂停后切换并继续）— 实施与验证报告

- 日期：2026-10-20
- 仓库：`e:\PyQt5_demo\2048`，分支 `main`，基线提交 `8c6d96f`
- 环境：`E:\anaconda3\envs\2048\python.exe`（3.12.3，`PYTHONNOUSERSITE=1`），Windows 10 19042
- 改动文件：`v6_pyqt_2048_accelerated/v6_speed.py`、`v6_pyqt_2048_accelerated/v6_background.py`、
  `v6_pyqt_2048_accelerated/tests/test_v6_cross_mode.py`（新增）、`tools/capture_gui.py`（新增 V6 交接场景）
- 未执行 git commit；V1–V5 未修改；正式存档 / RL 模型 / 历史实验未被写入（全部重定向到临时目录）

## 1. 总体结论

| 门禁 | 结果 |
| --- | --- |
| P0 根因定位（可复现、可证伪） | PASS |
| P1 统一交互语义 | PASS |
| P2 标准 ↔ 快速交接 | PASS |
| P3 标准/快速 ↔ 后台交接（单一写者） | PASS |
| P4 按钮/文案矩阵 | PASS |
| P5 数据正确性（最高分/RNG/game_id/撤销栈/迟到消息） | PASS |
| P6 强制测试矩阵（8 种暂停切换 + 4 项扩展） | PASS |
| P7 V6 unittest + IPC E2E + 跨模式测试 | PASS |
| 完整窗口截图（CAPTURE/STRUCTURE/TEXT） | PASS（5/5 场景） |
| 截图像素级人工目视（VISUAL_PASS） | **UNVERIFIED**（需人工核对，未擅自标记 PASS） |

## 2. P0 根因（确切分支，不是按钮文案问题）

1. **暂停态的“继续”完全绕过新选择**
   - 旧 `_v6_on_run_primary()` 先取 `ctl = self._v6_bg()`；后台 `BG_PAUSED` 时**无条件** `ctl.resume()`。
   - 本机分支 `elif self._v6_local_paused: self._v6_resume_local()`，同样不看 `_v6_selected_mode`。
   - 结论：暂停后点“继续”必然恢复**原执行模式**。
2. **`_v6_selected_mode` 只在会话结束后消费**
   - 旧逻辑仅由 `_v6_apply_selected_if_idle()` 应用；它只在 `not running` / `st GUI_IDLE` 时调用。
   - 暂停（`BG_PAUSED`、`_v6_local_paused`）仍属于“活动会话”，因此选择**永远等不到生效**，
     必须等旧会话自然结束或用户停止——这正是“只有旧会话结束后才生效”的原因。
3. **根本不存在跨引擎交接路径**
   - 本机暂停态没有“把当前正式对局交给 Headless Worker”的流程；
   - 后台暂停态也没有“让 Worker 退出并释放所有权，再由本机继续”的流程；
   - 旧“切走”只依赖 `BackgroundController.on_mode_changed()` 的隐式 `stop()`，
     在活动会话期间还会主动跳过，于是既不切换也不停止。
4. **后台启动未确认所有权**
   - 旧 `_await_idle_and_spawn()` 在 `Popen` 成功后**立即** `_transition('BG_RUNNING')`，
     没有校验 `owner.json` 的 pid/会话，不满足“确认 Worker 接管后才进入运行中”的 P3 要求。
5. **UI 状态源只看执行引擎**
   - 旧 `_v6_sync_run_controls()` 只按当前引擎状态出文案，没有“已暂停 + 已选择其它模式”的第四种状态。

## 3. 修复设计（代码）

### 3.1 唯一执行状态源

`v6_speed.py` 新增：

- `_v6_effective_active()`：`_v6_active_mode` → 本机 `_solver_running` → 后台控制器状态，
  统一得出“真正在执行的模式”（空闲为 `None`）。
- `_v6_is_paused(active)`：本机要求 `running && local_paused && !local_pausing`；
  后台要求 `ctl.state == 'BG_PAUSED'`（**暂停中不算**）。
- `_v6_handoff = {'from','to','phase'}`：交接期间禁用主按钮、停止按钮与三个选项卡，
  `_v6_on_run_primary/_v6_on_run_stop/_v6_on_speed_clicked` 全部提前返回（禁止并发 Worker）。

### 3.2 三种交接路径

| 路径 | 行为 |
| --- | --- |
| 标准 ↔ 快速 | 丢弃 `_v6_paused_result`、`_job_id += 1`、清方向提示 → `_v6_apply_tier(dst)`（动画/粒子/步间等待）→ 同一 `_session` 从当前棋盘 `_request_decision()` |
| 本机 → 后台 | 先从**当前一致状态**建快照（board/score/best/RNG + `handoff` 元数据）→ Worker 登记所有权并 pid 匹配后才回调 `_v6_on_bg_started()` → 此时才静默结束本机会话 |
| 后台 → 本机 | 校验 `BG_PAUSED` 且终态已采纳（必要时补一次正式回放）→ `drain_for_handoff()` 发 `quit` 并等待“进程退出 + owner 非 alive” → `_game_id=None`/`_final_seen=True` → `_v6_start_local()` |

失败路径：`_v6_handoff_fail()` / `_v6_on_bg_start_failed()` 只清交接标记、恢复选项卡勾选，
保留原暂停会话与可恢复检查点，并明确显示“XX模式切换失败，原会话保持暂停”。

### 3.3 后台控制器

`v6_background.py`：

- `start(snapshot=None, handoff_meta=None)`：交接路径**不再先停本机会话**；失败可完整回退。
- `_await_ownership()`：轮询 `owner.json`，`state=alive && pid 匹配` 才 `_confirm_running()`；
  超时 / 提前退出 → `_fail_start()`（清理半启动进程 + 回调失败）。
- `_write_handoff_record()`：写 `handoff_<session>.json`，记录 from/to、正式 game_id、新 session_id、pid。
- `drain_for_handoff(on_done)`：`quit` → 有界等待进程退出与所有权释放 → 才允许本机启动。
- 迟到消息：`final` 增加“已收尾会话”与“game_id 不匹配”双门禁；`progress` 原门禁保留。
- `_build_snapshot()` 会话 id 增加毫秒后缀，避免同一秒内连续交接重名。

### 3.4 P4 按钮/文案矩阵

| 运行状态 | 主按钮 | 停止 |
| --- | --- | --- |
| 运行中 | 暂停 | 可用 |
| 正在暂停 | 正在暂停…（禁用） | 禁用 |
| 已暂停，未变更模式 | 继续 | 可用 |
| 已暂停，已变更模式 | 切换至XX并继续 | 可用 |
| 交接中 | 正在切换至XX…（禁用） | 禁用 |
| 交接成功 | XX模式运行中（徽标） | 可用 |
| 交接失败 | 恢复原模式“继续”，状态区显示“XX模式切换失败” | 可用 |

选项卡禁用期：交接中；其余时间仅“记录选择”，徽标始终显示真实执行模式。
禁用态主按钮配色由浅底浅字改为 `#e3d8ca / #8a7b6c`，保证“正在切换至…”文字可读（截图文字门禁通过）。

## 4. P6 强制测试矩阵（真实结果）

见 `pause_switch_matrix.json`（8 种组合 + 4 项扩展，全部 PASS）。
其中 8 种组合在 `tests/test_v6_cross_mode.py` 中逐项断言；真实 GUI E2E 另覆盖：

- A：标准真实运行 → 安全暂停；
- B：切快速继续（active=fast、anim_off=True、job+1）；
- C：切后台继续并真实跑到 217 步（owner=alive、pid 匹配、500ms 回传）；
- C7/C8：暂停采纳后官方棋盘/分数与 Worker 终态一致，**全局 RNG 与 Worker 逐位一致**；
- D：后台暂停 → 标准继续（Worker 退出、owner=absent，本机只启动一次）；
- E：再切快速连续 200 步；累计 419 步（≥400）；最高分全程 62188 不回退。

E2E 结果：`cross_mode_e2e.json`，`ok=true`，22/22 检查通过，8 张实时截图，退出码 0。

## 5. 测试与门禁

### 5.1 V6 unittest（逐模块独立进程，避免环境变量互相污染）

| 模块 | 用例 | 结果 |
| --- | --- | --- |
| test_v6_cross_mode（新增） | 15 | OK |
| test_v6_run_state | 10 | OK |
| test_v6_headless | 26 | OK（skip 2） |
| test_v6_ownership | 12 | OK（skip 1） |
| test_v6_report_policy | 11 | OK |
| test_gui_integration | 9 | OK |
| test_arrow_keys | 9 | OK |
| test_storage_isolation | 5 | OK |
| test_backend_equivalence | 12 | OK |
| test_search_equivalence | 6 | OK |
| test_native_search | 18 | OK |
| test_row_table | 3 | OK |

合计 136 项，0 失败，3 跳过；原始日志见 `tests/`，退出码见 `tests/summary.txt`。

> 说明：若把多个 GUI 测试模块放进**同一进程**串行执行，`test_storage_isolation` 会因前序模块
> 遗留的 `2048_HISTORY_DIR` 而误报（既有测试隔离问题）。本次按项目约定逐模块运行，全部通过。

### 5.2 截图门禁（真实 Windows 整窗，DWM 外框 + 屏幕 BitBlt）

| 场景 | CAPTURE | STRUCTURE | TEXT | VISUAL | 文件 |
| --- | --- | --- | --- | --- | --- |
| game | PASS | PASS | PASS | UNVERIFIED | `screenshots/full_game.png` |
| solver | PASS | PASS | PASS | UNVERIFIED | `screenshots/full_solver.png` |
| auto | PASS | PASS | PASS | UNVERIFIED | `screenshots/full_auto.png` |
| handoff_paused | PASS | PASS | PASS | UNVERIFIED | `screenshots/full_handoff_paused.png` |
| handoff_switching | PASS | PASS | PASS | UNVERIFIED | `screenshots/full_handoff_switching.png` |

所有场景均为完整窗口（含原生标题栏/图标/最小化最大化关闭），文字对比度校验通过；
`VISUAL_PASS` 必须由人工核对后加 `--visual-confirm` 授予，本次**保持 UNVERIFIED**，
因此 `GUI_SCREENSHOT_PASS` 记为 **PARTIAL（待人工目视）**，不冒充 PASS。
原始门禁 JSON 见 `gui/capture_*.json`。

## 6. 关键证据文件

- `cross_mode_e2e.json` / `cross_mode_e2e.log` / `probe_stdout.log`：22 项真实 GUI E2E 检查与轨迹
- `pause_switch_matrix.json`：8 种暂停切换 + 4 项扩展矩阵
- `tests/`：12 个模块的 unittest 原始日志与退出码汇总
- `gui/capture_*.json`：5 个场景的截图门禁原始输出
- `screenshots/`：5 张完整窗口截图
- `p1…p8*.png`：E2E 各阶段真实桌面截图（暂停+已选择、切换后运行、后台 200+ 步、后台暂停、切回标准等）
- `probe_script.py`：E2E 探针脚本副本（原始运行位置在 `%TEMP%`）
- `run1/`、`run2/`：中间取证（保留用于根因审计）。run1 暴露“交接未确认所有权”的时序问题；
  run2 加入 trace 后证明：暂停确实冻结本机求解，异常来自**测试盘面过快终局**（后台 1 秒内
  跑到 303 步 game over）。最终根目录一次运行使用稀疏测试盘面，22/22 全通过。

## 7. 限制与后续

- VISUAL_PASS 尚未人工确认（本次 Agent 不替代人工目视结论）。
- `config/ui_prefs.json` 为运行期偏好，探针运行会写入；本次已恢复为基线值（`run_mode=standard`），避免把测试偏好带入仓库。
- 后台回传周期仍固定 500ms（单一来源 `REPORT_INTERVAL_MS`），未恢复任何 N 步/N 时间 UI。
- 未重训 RL、未修改 V1–V5、未自动提交 Git。
