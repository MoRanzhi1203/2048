# V6 最高分完整性与统一运行模式状态 —— 交付报告

> 仅改 V6（`v6_speed.py`、`v6_background.py`、1 个既有测试 + 新增 1 个测试文件）；V1–V5 只读；
> 未改正式存档契约 / RL 模型 / 搜索算法；未 Git 提交。
> 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_highscore_runstate/`。

## 1. 确认的根因（源码 + 实测）

### 1.1 后台求解时“最高分 = 当前分数”
`v6_background._render_snapshot()` 每帧把 Worker 快照里的 `best_score` 直接画到右上角，
缺失时还回退到 `score`：

```python
self.win._render_score(self.win.best_label, '最高分',
                       msg.get('best_score', msg.get('score')))
```

Worker 的 `best_score` 是**该后台会话自身的累计最高**（起始即当前分数），因此会把
“当前分数”显示成“历史最高分”。实测复现：快照 `best=score=5004`。

### 1.2 运行中切换选项卡导致隐式暂停/停止
`_v6_on_speed_clicked()` 只判断 `_solver_running`（本机求解标志）；后台运行时该标志为
`False`，于是立即 `_v6_apply_tier()` → `BackgroundController.on_mode_changed()` →
`if not want_bg and self.state in (...): self.stop()`，活动 Worker 被隐式停止/暂停。
另有一个“步边界落实挂起档位”的旧机制（`_v6_apply_pending_tier`），会在对局中途改变
执行模式，同样违反“选项卡 ≠ 执行模式”。

### 1.3 三模式控制语义不一致
标准/快速主按钮是“开始求解 ↔ 停止”，后台是“开始/暂停/继续 + 停止”；
状态徽标只显示笼统的“运行中/已暂停”，未标明实际执行模式。

## 2. 修改文件与函数

| 文件 | 函数/位置 | 修改 |
| --- | --- | --- |
| `v6_background.py` | `_render_snapshot` | 最高分只读 `model.best_score`（权威持久化），**绝不**用 Worker 快照 |
| `v6_background.py` | `on_mode_changed` | “切走即停止”仅在无活动会话时允许 |
| `v6_background.py` | `_transition` | 每次后台状态迁移同步可见控制区 |
| `v6_background.py` | `_await_idle_and_spawn` / `resume` / `recover_on_start` | 设置 `win._v6_active_mode='background'` |
| `v6_background.py` | `_finish_to_idle` | 清除 `_v6_active_mode` |
| `v6_speed.py` | `_v6_speed_init` | 新增 `_v6_selected_mode/_v6_active_mode/_v6_local_paused/_v6_local_pausing/_v6_paused_result` |
| `v6_speed.py` | `_v6_on_speed_clicked` / `_v6_apply_pending_tier` | 活动会话中仅记录“已选择”，**非破坏性**；不再中途切档 |
| `v6_speed.py` | `_v6_bg` / `_v6_session_active` / `_v6_active_label` | 以 `active_mode` 路由控制与文案 |
| `v6_speed.py` | `_v6_start_local` / `_v6_request_local_pause` / `_v6_resume_local` / `_v6_stop_local` | 标准/快速安全步边界暂停/继续/停止 |
| `v6_speed.py` | `_request_decision` / `_on_solver_result` | 暂停后不请求下一步；在途结果**暂存不落子**，恢复优先复用 |
| `v6_speed.py` | `_v6_on_run_primary` / `_v6_on_run_stop` | 三模式唯一一套 开始/暂停/继续/停止 |
| `v6_speed.py` | `_v6_sync_run_controls` | 单一状态矩阵 + 模式限定徽标；会话结束做一次安全交接 |
| `v6_speed.py` | `_v6_apply_selected_if_idle` | 运行中选中的选项卡在空闲后生效（一次） |
| `v6_speed.py` | `_v6_update_timing_label` | 模式限定摘要 + `当前执行｜已选择（未切换）` |
| `v6_speed.py` | `_v6_apply_bg_progress` / `_v6_apply_bg_final` | 模式限定状态文案；终态清除 active_mode |
| `tests/test_v6_headless.py` | `test_standard_primary_reflects_solver_state` | 更新为新矩阵（暂停/继续） |
| `tests/test_v6_run_state.py` | 新增 10 项 | 最高分/非破坏切档/控制矩阵/安全暂停 |

## 3. 新旧状态迁移对照

| 场景 | 旧行为 | 新行为 |
| --- | --- | --- |
| 后台 RUNNING 时点“快速” | 立即切档并 `stop()` 后台 | 只记录“已选择：快速”，Worker 继续；显示 `当前执行：后台求解模式｜已选择：快速模式（未切换）` |
| 标准 RUNNING 时点“后台求解” | 标记 pending，步边界隐式切档 | 仅记录选择；暂停/停止后才交接 |
| 标准/快速 RUNNING | 主按钮“停止”，无暂停 | 主按钮“暂停” + 独立“停止” |
| 标准/快速 暂停 | 不支持 | 安全步边界暂停；在途结果暂存，不落子 |
| 徽标 | `运行中 / 已暂停` | `标准模式运行中 / 快速模式运行中 / 后台求解模式运行中 / …已暂停 / …正在停止` |
| 后台进度 | 右上角最高分被 Worker `best_score` 覆盖 | 只显示权威 `model.best_score` |

**控制矩阵**（三模式共用）：

| 状态 | 主按钮 | 停止 | 徽标示例 |
| --- | --- | --- | --- |
| 空闲 | 开始求解（启用） | 隐藏 | `快速模式未运行` |
| 运行中 | 暂停（启用） | 显示/启用 | `标准模式运行中` |
| 暂停请求中 | 正在暂停…（禁用） | 启用 | `标准模式正在暂停` |
| 已暂停 | 继续（启用） | 启用 | `快速模式已暂停` |
| 停止请求中 | 正在停止（禁用） | 禁用 | `后台求解模式正在停止` |
| 完成/停止/出错 | 开始求解（启用） | 隐藏 | `后台求解模式已结束/已停止/出错` |

## 4. 最高分作用域与持久化证据（真实 GUI，隔离存档）

- 作用域：`current_score` = 当前局分数；`best_score` = 该存档目录 `best_score.json`
  的历史最高（跨会话、单调不减）；`max_tile` 与最高分无关。
- 进度快照只写分数标签，不写 `model.best_score`，也不触发 `save_best_score`。
- 最终交接仍走 `replay_commit → persist_official`（单写入者、原子提交），
  `_sync_best_score` 保证 `best = max(best, score)`。

实测（`ui_states.json` / `long_run.json`）：

| 场景 | 当前分数 | 最高分标签/模型/文件 |
| --- | ---: | --- |
| Worker 快照 `best=score=5004` | 5004 | **62188 / 62188 / —** |
| 后台第 271 步运行中 | 4228 | 62188 |
| 停止并采纳最终状态（分数 4392） | 4392 | **62188 / 62188 / 62188** |

停止后：`undo_depth=281`、`history_rows=563`（=2×281+1），无残留 worker。

## 5. 真实 Windows 整窗截图（908×759，DWM + BitBlt）

`screenshots/`：
- `hs_best_retention.png`（快照 best=5004 时右上角仍为 62188）
- `hs_standard_running.png`（标准模式运行中）
- `hs_standard_paused.png`（标准模式已暂停）
- `hs_fast_running.png`（快速模式运行中）
- `hs_bg_running_selected_fast.png`（后台运行中 + 已选择快速，未切换）
- `hs_bg_paused.png`（后台求解模式已暂停）
- `hs_bg_250plus.png`（后台 271 步仍在运行，未自动停止）

## 6. 门禁（真实退出码）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **121 tests OK（skipped=3），EXIT 0** |
| `V6_RUN_IPC_E2E=1 … WorkerOwnershipLifecycleTest WorkerE2ETest` | **3 tests OK，EXIT 0** |
| `python -m unittest test_v6_run_state` | **10 tests OK，EXIT 0** |
| `python -m unittest test_v6_headless` | **26 tests OK（skipped=2），EXIT 0** |
| 后台持续运行 | **271 步仍 `BG_RUNNING`**，无 200/400 自动停止 |
| 残留进程 | 无 |

## 7. 遗留 / 未验证

- **1000ms vs 500ms**：任务书写“后台固定 1000ms”，但用户在 2026-10-12 明确要求
  **“永远不改回 1000ms”**，当前为 **500ms**。本轮保持 500ms；对应“1000ms 门禁”按
  用户指令视为 **N/A（by design）**，实测回传仍按固定 500ms 单调 latest 帧。
- **真实系统 DPI 125%/150%**：UNVERIFIED（此前仅受控 `QT_SCALE_FACTOR` 验收）。
- **人工目视**（配色/密度/文案观感）：UNVERIFIED。
- **跨模式实时交接**：不支持“搜索中直接换引擎”；按规范以“暂停/停止后生效 + 明确提示”
  实现（安全优先），未强行中断原生搜索。
- 本轮未测 CPU/内存峰值；后台仍标记 EXPERIMENTAL。
