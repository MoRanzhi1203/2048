# V6 右侧「AI 运行控制」统一改造 —— 收口报告（P0–P7）

> 仓库：`E:\PyQt5_demo\2048`；解释器：`E:\anaconda3\envs\2048\python.exe`；`PYTHONNOUSERSITE=1`。
> 仅改 V6；V1–V5 只读；未改正式存档 / RL 模型；**未 Git 提交**。
> 证据：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_run_control_unify/`。

---

## P0 审计：旧控件 → 新控件映射

| 旧控件 | 旧位置/职责 | 本轮处理 |
| --- | --- | --- |
| `v6_speed_buttons`（标准/快速/后台求解） | 原「运行方式」标题行 | **保留**，移入统一模块（唯一可见三档） |
| `v6_timing_label`（纯黑 `#2b2622` 大块） | 三档下方，3 行分段计时 | **替换**为紧凑浅米灰 `v6_run_summary`（≤2 行；详细分段仍保留在 tooltip） |
| `solver_start_btn`（浅色大按钮） | V5 控制行（开始求解↔停止） | **隐藏**；逻辑复用 `on_solver_clicked`，入口合并到 `v6_run_primary` |
| `solver_progress`（8px 进度条） | V5 控制行 | **隐藏**（回传间隔无百分比含义） |
| `BackgroundPanel` 四按钮（start/pause/resume/stop） | 后台专用按钮行 | **移除**；信号迁移到 `v6_run_primary`（start/pause/resume）与 `v6_run_stop`（stop） |
| `solver_status` | 既有状态区 | **保留**；后台低频状态文本仍写此处 |
| `solver_metrics` / `solver_log` / 高级参数 / 导出·详情·性能对比 | 既有右栏 | **全部保留**，未删除数据 |

`BackgroundPanel` 现仅保留 `report_policy()` 与 `_sync_buttons()` 转发（轻量占位，无第二套按钮）。

---

## P1 布局合并

统一模块（`objectName=v6RunControl`，沿用 `_make_solver_group` 卡片样式）自上而下：

1. 标题 `AI 运行控制`（暖棕、12px、加粗）
2. `标准` / `快速` / `后台求解` 三档（唯一可见）
3. 紧凑性能摘要（浅米灰 `#efe7db` + `#d8ccbc` 描边，圆角 6px，≤2 行）
4. 唯一一套操作：`开始求解/暂停/继续`（暖棕主按钮）+ `停止`（米白描边）

移除原“纯黑大统计块 ↔ 独立浅色大按钮”的视觉割裂；后台模式不再额外插入按钮行。
未新增高饱和颜色，沿用 V6 暖灰/米白/棕色体系。

---

## P2 唯一控制状态源（状态矩阵）

| 运行方式 | 状态 | 主按钮 | 停止按钮 |
| --- | --- | --- | --- |
| 标准 / 快速 | 未运行 | 开始求解 | 隐藏 |
| 标准 / 快速 | 运行中 | 停止（V5 无暂停，不造无效按钮） | 隐藏 |
| 后台 | `GUI_IDLE/BG_COMPLETED/BG_ERROR` | 开始求解 | 显示（禁用） |
| 后台 | `HANDOFF_PREPARE` | 开始中…（禁用） | 禁用 |
| 后台 | `BG_RUNNING` | 暂停 | 启用 |
| 后台 | `BG_PAUSING` | 暂停中…（禁用） | 禁用 |
| 后台 | `BG_PAUSED` | 继续 | 启用 |
| 后台 | `BG_STOPPING` | 正在停止（禁用，防重复触发） | 禁用 |

- 标准/快速复用 V5 `on_solver_clicked()`（开始↔停止），**不新建求解状态**。
- 后台复用同一 `BackgroundController` 的 `start/pause/resume/stop`；旧四按钮信号完整迁移。
- `_v6_sync_run_controls()` 是唯一刷新入口；在档位切换、`_update_solver_buttons`、后台状态变化、
  周期回传时调用。信号仅在创建时连接一次（无重复连接）。

---

## P3 性能摘要重排

- 最多两行：`运行状态 · 有效步数 · 累计耗时 · 步/秒 · 实际后端`（后台另显示分数/最大块）。
- **未运行时不把历史计时当当前耗时**：标准/快速未运行时显示“未运行”；已停止标注“已停止（上次 N 步）/当前未在计时”。
- 详细分段（搜索/动画/等待/渲染）保留在摘要 `tooltip`；`性能对比` 与 `查看详情` 入口原样保留。

---

## P4 模式行为不变

- 标准：动画 + 合并粒子 + 动态方向光（A/B）。
- 快速：无移动动画、无合并粒子、保留动态方向光。
- 后台：无逐步动画/合并粒子；方向光静态（无流光计时器）；Worker 唯一写入者；
  GUI 周期快照仅无动画只读渲染，不 `apply_move`、不生成方块；暂停/停止/自然结束强制 FINAL。
- **回传周期说明**：本轮保持当前源码的 **500ms**（沿用你上一轮“改为 500ms”的明确指令）；
  任务文档 P4 写“固定 1000ms”，两者存在差异。若需 1000ms，仅需将
  `v6_background.REPORT_INTERVAL_MS` 改回 1000（单一常量），不影响本 UI 改造。

---

## P5 布局验收（真实 Windows 整窗截图）

采集：`DwmGetWindowAttribute(EXTENDED_FRAME_BOUNDS)` + 屏幕 DC `BitBlt`，非 offscreen / 非 grab。
窗口 906×720，截图 908×759（含原生标题栏）。文件名 ASCII。

| 文件 | 场景 |
| --- | --- |
| `screenshots/rc_standard_idle.png` | 标准 · 未运行 |
| `screenshots/rc_fast_idle.png` | 快速 · 未运行 |
| `screenshots/rc_background_idle.png` | 后台 · 未运行（无独立回传配置） |
| `screenshots/rc_background_running.png` | 后台 · 运行中（摘要刷新） |
| `screenshots/rc_background_paused.png` | 后台 · 已暂停 |
| `screenshots/rc_background_stopped.png` | 后台 · 已停止 |

程序化布局校验（`run_control_screenshots.json`）：3 个档位按钮、`v6_run_primary/stop/summary` 均存在；
旧 `solver_start_btn`/`solver_progress` 均隐藏；主按钮文案 `开始求解`。
**人工目视：UNVERIFIED**；**DPI 125%/150%：UNVERIFIED**（未在真实缩放环境采集）。

---

## P6 功能门禁（真实退出码）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **107 tests OK（skipped=3），EXIT 0** |
| `V6_RUN_IPC_E2E=1 … WorkerOwnershipLifecycleTest WorkerE2ETest` | **3 tests OK，EXIT 0** |

新增/更新用例：
- `test_background_controller_is_wired`：旧后台四按钮已移除 + 统一控件存在 + 回传固定 500ms。
- `test_unified_controls_dispatch_background`：主按钮按状态路由 start/pause/resume，停止按钮 → stop；
  `BG_STOPPING` 时主按钮禁用且显示“正在停止”（防重复触发）。
- `test_standard_primary_reflects_solver_state`：标准/快速主按钮随 `_solver_running` 切换，停止按钮隐藏。

覆盖：标准/快速开始-停止、后台开始/暂停/继续/停止、快速切换、后台单写入者、Worker 退出与所有权清理、
最终棋盘与存档恢复（既有用例）、Qt 主线程无长任务（沿用延迟落盘 + 单次提交）。

---

## P7 门禁结论

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| P0 审计/映射 | **PASS** | §P0 映射表，未盲删逻辑 |
| P1 布局合并 | **PASS** | 统一模块；旧黑块/大按钮/后台四按钮消除 |
| P2 唯一状态源 | **PASS** | §P2 矩阵 + 3 项接线回归 |
| P3 摘要重排 | **PASS** | ≤2 行；未运行不冒充当前耗时；详情保留 |
| P4 模式行为 | **PASS** | 粒子/方向光/单写入者/500ms 回传不变 |
| P5 布局验收 | **PARTIAL** | 6 张真实整窗图 + 程序化校验 PASS；人工目视与 125/150% DPI **UNVERIFIED** |
| P6 功能门禁 | **PASS** | 107 单测 + 3 IPC E2E，EXIT 0 |
| P7 报告 | **PASS** | 本文件 |

**遗留**：后台仍标记 EXPERIMENTAL（沿用既有判定）；高 DPI 与人工视觉未验证。

---

## 修改文件

| 文件 | 变更 |
| --- | --- |
| `v6_pyqt_2048_accelerated/v6_speed.py` | 统一「AI 运行控制」模块（三档 + 摘要 + 主/停按钮）；唯一状态源与刷新；旧按钮隐藏；摘要重排 |
| `v6_pyqt_2048_accelerated/v6_background.py` | 移除 `BackgroundPanel` 四按钮（改为状态转发）；新增 `_last_progress` 供摘要 |
| `v6_pyqt_2048_accelerated/tests/test_v6_headless.py` | 更新接线回归 + 新增统一控制/标准状态用例 |

未改 V1–V5、搜索内核、正式存档与 RL 模型；未执行 Git 提交或推送。

---

## 11. P5 布局/缩放验收补充（100% / 125% / 150%）

受控缩放（`QT_SCALE_FACTOR`）下真实整窗采集 + 程序化几何检查
（`dpi/layout_scale_*.json`，截图 `dpi/screenshots/rc_*_s*.png`）：

| 缩放 | DPR | 窗口(逻辑) | 模块高 | 模块底 | 日志高 | 底部按钮底 / 窗口高 | 溢出 | 重叠 |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| 100% | 1.00 | 906×720 | 153 | 319 | 163–179 | 702 / 720 | 无 | 无 |
| 125% | 1.25 | 906×720 | 149 | 315 | 173–189 | 702 / 720 | 无 | 无 |
| 150% | 1.50 | 906×672 | 149 | 315 | 125–141 | 654 / 672 | 无 | 无 |

- `v6_run_primary/v6_run_stop/v6_run_summary` 均在窗口内；摘要与操作行无重叠；
  标准模式的停止按钮隐藏（几何相交不计）。
- 日志区未被压到 0（125–189px）；导出/查看详情/性能对比始终可见且不被裁切。
- 旧 `solver_start_btn/solver_progress` 三档缩放均隐藏。
- **真实 Windows 125%/150% 系统 DPI 仍为 UNVERIFIED**（本轮为受控缩放）；人工目视为 UNVERIFIED。
