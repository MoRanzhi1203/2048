# V6 后台求解 UI 简化 + 固定 1000ms 回传 —— 收口报告（P0–P7）

> 仓库：`E:\PyQt5_demo\2048`；解释器：`E:\anaconda3\envs\2048\python.exe`；`PYTHONNOUSERSITE=1`。
> 仅改 V6；V1–V5 只读；未改正式存档 / RL 模型 / 历史实验；未提交 Git。
> 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_2/20261012_bg_closure/`。
> 未通过项一律 PASS/FAIL/PARTIAL/UNVERIFIED 如实标注，不以单元测试冒充端到端通过。

---

## 0. 结论速览（门禁）

| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| P0 审计 / 后台监督器构造根因 | **PASS** | 根因=控件未导入（见 §1），已修复并有回归测试 |
| P1 报告配置 UI 清理 | **PASS** | 控件已删除（见 §2、§3 截图 3） |
| P2 固定 1000ms 回传 | **PASS（含 1 项 PARTIAL）** | 实测均值 ≈1014ms（见 §4）；长搜索心跳为 PARTIAL |
| P3 左盘只读镜像 + 交接 | **PASS** | 真实 GUI 跑通 running/paused/stopped/ended；正式历史回放测试 |
| P4 三模式观效 | **PASS（自动化）** | 策略与抑制有单测；**4 方向视觉证据 UNVERIFIED** |
| P5 真实 Windows 截图 | **PARTIAL** | 7 张真实整窗图（CAPTURE/STRUCTURE PASS）；**人工目视与 DPI 125/150% UNVERIFIED** |
| P6 功能/安全/性能门禁 | **PARTIAL** | 98 单测 + IPC E2E 全绿；快/后台公平性能对比未跑 |
| P7 报告与安全交付 | **PASS** | 本文件 |

**后台求解保持 EXPERIMENTAL、非默认**（原因见 §8）。

---

## 1. P0 审计与根因

### 1.1 关键根因：后台面板此前**从未真正出现**（静默构造失败）
`v6_background.BackgroundPanel` 使用了 `QComboBox`，但模块顶部**未导入**该控件
（`v6_background.py` 的 `from PyQt5.QtWidgets import ...` 缺 `QComboBox`）。

调用链：
```
v6_speed._v6_speed_init()
  → BackgroundController(self, _v5gui)         # v6_background.py:246(改前)
      → self.panel = BackgroundPanel(self)     # :246
          → QComboBox()                         # :117 → NameError
  → except Exception: self._v6_bg_controller = None   # v6_speed.py:160-161（静默吞掉）
```
因此**真实 V6 GUI 中后台控制器恒为 `None`**：后台按钮、面板、状态全部缺失，`recover_on_start` 也不执行。
诊断实证（改前）：`win._v6_bg_controller = None`，`BackgroundController(win)` 抛
`NameError: name 'QComboBox' is not defined`。

> 这正是契约 P0-2 所述情形：**不能把“面板缺失”当作设计决定**——它是构造失败的后果。

**修复**：补齐控件导入（后续简化中该控件已随 UI 删除，见 §2/§6）。

### 1.2 报告策略控件与解析位置（改前）
| 位置 | 内容 |
| --- | --- |
| `v6_background.py:BackgroundPanel` | `结果回传`标题、`定时间/定步数`切换、`report_combo`、说明文字 |
| `BackgroundPanel.report_policy()` | 产出 `{'mode':'steps','steps':200}` 或 `{'mode':'time','ms':N}` |
| `BackgroundPanel._save_prefs/load_prefs()` | 持久化 `report_mode/report_value/report_prefs_version` |
| `BackgroundController._limits()` | 下发 `report_policy` |
| `headless/game_loop.py:_report_due()` | 按 `mode` 解析时间/步数 |

### 1.3 检查点有限重试（Windows 瞬时锁）现状
改前 `Checkpoint.save` 有界重试（25×20ms）但**未记录**重试次数/耗时，失败仅重抛原异常。
已补：`retries/retry_ms/max_retries_seen/failures` 统计 + 失败时显式上报“次数 + 实际等待 ms”，
并汇入 `run_session` 的 `perf.checkpoint_retry_ms/…count/…failures` 与 `checkpoint_stats`。
**实测该路径真实触发**：本轮时间线运行中 `retries=1, retry_ms=38.6`（见 §5）。

### 1.4 基线
| 项 | 值 |
| --- | --- |
| 默认门禁（改前） | 89 tests OK（skipped=2），EXIT 0 |
| 默认门禁（P0/P1 后） | 94 tests OK（skipped=2），EXIT 0 |
| 默认门禁（UI 简化后） | **98 tests OK（skipped=2），EXIT 0** |

---

## 2. P1 删除的报告配置控件（清单）

从右侧求解面板删除（均为“仅为可配置回传”而新增）：
1. `结果回传` 独立配置分组（标题 `QLabel('结果回传')`）。
2. `定时间 / 定步数` 互斥切换按钮（`btn_time`/`btn_steps`）。
3. `1000 ms` 下拉框 `QComboBox`（`report_combo`）与全部可编辑间隔控件。
4. 说明文字 `QLabel`（“后台持续求解；达到回传间隔后…”）。
5. 面板自带的重复状态黑条 `self.label`（`#2b2622` 深色条）——**进度并入既有 `solver_status` 状态区**。
6. 报告进度/比例条：后台模式下隐藏既有 `solver_progress`（回传间隔无百分比含义）；
   标准/快速保留原“忙态进度条”（原有 AI 求解流程不变）。

保留（既有右键）：算法、求解强度、求解模式、`标准/快速/后台求解` 三档选择器、
**唯一一套** `开始/暂停/继续/停止` 后台控制、既有求解状态区、日志区、高级参数、底部导出/详情/性能对比。

`BackgroundPanel` 现仅含 4 个生命周期按钮；`report_policy()` 返回固定 `{'mode':'time','ms':1000}`。

---

## 3. P5 真实 Windows 整窗截图

采集方式：`DwmGetWindowAttribute(EXTENDED_FRAME_BOUNDS)` 取外框 + 屏幕 DC `BitBlt`
（复用 `tools/capture_gui.py` 的 `visible_frame_rect/capture_frame`），**非 offscreen / 非 grab()**。
全部 `frame_src=dwm`、`grab_src=screen-bitblt`，尺寸 908×759（含原生标题栏）。

| 文件 | 场景 | 关键校验 |
| --- | --- | --- |
| `screenshots/v6_std.png` | 标准模式：左盘 + 右面板 | variance 47.2 / 277 色 |
| `screenshots/v6_fast.png` | 快速模式：无合并粒子路径 | variance 44.9 / 286 色 |
| `screenshots/v6_bg_idle.png` | 后台（未启动）：**无“结果回传”配置区** | variance 50.0 / 297 色 |
| `screenshots/v6_bg_running.png` | 后台运行中（已应用 ~1000ms 快照） | state=BG_RUNNING, rev=13 |
| `screenshots/v6_bg_paused.png` | 后台暂停（强制同步） | state=BG_PAUSED |
| `screenshots/v6_bg_stopped.png` | 后台停止（强制同步 FINAL） | status=stopped |
| `screenshots/v6_bg_ended.png` | 自然终局 | status=game_over |

> “改前”说明：由于 §1.1 的构造失败，旧的 `结果回传` 区块**从未在真实窗口中渲染**，
> 故不存在可对比的“改前截图”；改前真实状态=后台面板缺失（`_v6_bg_controller=None`）。

CAPTURE/STRUCTURE：**PASS**（外框来源、非空、非纯色已程序化校验）。
TEXT/VISUAL 人工目视：**UNVERIFIED**。DPI 125%/150%：**UNVERIFIED**（未在真实缩放环境采集）。

---

## 4. P2/P6 固定 1000ms 回传 —— 真实时间线

**真实 headless worker（cpp 后端）实测**（`p2_timeline.json`，9s 窗口，`report_policy={'mode':'time','ms':1000}`）：

| 报告 | 时间(s) | revision | steps | reason |
| ---: | ---: | ---: | ---: | --- |
| 1 | 1.082 | – | – | periodic_time |
| … | … | … | … | periodic_time |

回传间隔（ms）：`[1082, 947, 990, 1013, 1014, 1028, 1022]` → **均值 ≈1014 ms**，样本 7。
**连续求解到 415 步**仅因“收到 stop”才结束 → **不存在 200/400 步因回传而终止**。
`final_status=stopped`，`reason=stop`，`exit_code=0`，`exited_code=0`；
`backend_used=cpp`，`engine_used=python_kernel`（**未**冒充 C++ 原生整树）。
`checkpoint_stats={retries:1, retry_ms:38.6, failures:0}`。

**真实 V6 GUI 内**（`p5_screenshots.json.timeline`）：`periodic_time` 回传，revision 单调递增
（13→25→33），左盘按最新已提交快照刷新；间隔受单步搜索时长影响（见 §7 局限）。

`REPORT_INTERVAL_MS` 为**单一内部来源**；GUI 不暴露/不持久化 N 步/N 时间；旧偏好
`report_mode/report_value` 经**版本化幂等迁移**清除（`ReportPrefsMigrationTest` 通过）。

> **后续变更（用户明确指令，优先级最高）**：固定周期已是 **500ms，且永不改回 1000ms**。
> 上文 1000ms 仅为本轮历史记录；以当前源码为准。

---

## 5. P3 左盘只读镜像与交接

- 周期快照经 `_render_snapshot` → `board_view.render(board)` **无动画只读**刷新，
  不 `apply_move`、不再生成方块、不追加历史；按 `revision` 严格递增合并过期帧、丢弃跨会话/过期消息。
- **正式存档等价（新）**：后台结束时用 worker 的 `directions` 经**官方模型** `apply_move`
  逐步**回放**（`v6_background.replay_commit`），从而生成与正常对局一致的
  `history.csv`（每步 2 行）、撤销/重做栈、`game_state.json`（原子写 + `.bak`）、index/best_score；
  RNG 与 worker 快照逐位一致。测试 `test_replay_reproduces_official_history_and_undo` 验证。
- 单一写入者：回放前校验模型棋盘与会话基准一致，偏离则**拒绝回放**（`test_replay_refuses_when_model_mutated`）。
- 暂停/继续/停止/自然终局：真实 GUI 已跑通（§3 截图 4–7），停止返回 `stopped`、自然结束 `game_over`。
- 崩溃恢复：检查点含 `directions`，可结合交接快照 RNG 回放恢复（已编码，**端到端注入测试未覆盖 → PARTIAL**）。

---

## 6. P4 三模式观效（矩阵）

| 行为 | 标准 | 快速 | 后台 |
| --- | --- | --- | --- |
| 移动/合并动画 | 原样 | 关 | 关 |
| 合并粒子 | 原样 | **关（分配前抑制）** | **关（分配前抑制）** |
| 方向高亮 A | 开 | 开 | 开（报告/终局刷新） |
| 方向流光 B | 原样动态 | **保留动态** | **静态（停流光计时器）** |
| 棋盘显示 | 每步动画 | 每步瞬时 | 每 1000ms / 终局立即 |

实现（V6-only，不改 V4/V5 源码）：`v6_speed.MODE_PARAMS` 增 `particles_off/flow`；
`_v6_apply_effects()` 在 `emit_from/emit_zones_from` **入口**置空（抑制发生在对象分配/计时调度之前）
并清理残留粒子；对继承的方向层调用 `set_flow_enabled()`（后台=False 且清除可能过期的“下一步建议”）。
证据：`test_mode_effects_policy`（standard 未抑制 + fast/background 抑制 + background `flow_enabled=False`）PASS。

---

## 7. P6 测试与性能

| 命令 | 结果 |
| --- | --- |
| `python -m unittest discover -s .`（cwd=`tests`） | **98 tests OK（skipped=2），EXIT 0** |
| `V6_RUN_IPC_E2E=1 python -m unittest test_v6_ownership.WorkerOwnershipLifecycleTest test_v6_headless.WorkerE2ETest -v` | **2 tests OK，EXIT 0**（`WorkerE2ETest` 1.3s，此前为超时 FAIL） |
| 新增单测 | 检查点重试遥测 3、正式历史回放 2、面板接线 1、模式观效 1、偏好迁移 2 |

性能：本轮**未**执行“快速 GUI vs 后台（1000ms）”同起点公平对比 → **PARTIAL**；
不引用历史 `62 步/秒` 作为新结论。真机为 Windows 本机（未采集 CPU/内存峰值）。

---

## 8. 局限与遗留（PARTIAL/UNVERIFIED）

- **PARTIAL**：单次搜索 >1000ms 时未发送独立“computing”心跳（仅在下一步边界回传）；契约 P2-3 的
  心跳项未实现。
- **PARTIAL**：崩溃恢复回放路径已编码但缺端到端故障注入用例。
- **PARTIAL**：快速 GUI vs 后台 1000ms 的公平性能对比未跑。
- **UNVERIFIED**：截图人工目视确认、DPI 125%/150%、4 方向 A/B 视觉证据。
- **原因**：G3/G4 未完全闭环 ⇒ **后台求解保持 EXPERIMENTAL、不作默认**。

---

## 9. 修改文件清单

| 文件 | 变更 |
| --- | --- |
| `v6_pyqt_2048_accelerated/v6_background.py` | P0 补控件导入；P1 `BackgroundPanel` 简化（删结果回传组/N步N时间/下拉/说明/黑条）；`_show` 并入 `solver_status`；`on_mode_changed` 后台隐藏 `solver_progress`；`REPORT_INTERVAL_MS=1000`；`replay_commit`（正式历史回放）+ 恢复回放 |
| `v6_pyqt_2048_accelerated/v6_speed.py` | P2 偏好迁移到固定 1000ms；P4 `MODE_PARAMS` 增 `particles_off/flow` + `_v6_apply_effects()` |
| `v6_pyqt_2048_accelerated/headless/game_loop.py` | P0 检查点重试统计/失败上报；采集 `directions` 并入检查点与终态 |
| `v6_pyqt_2048_accelerated/tests/test_v6_headless.py` | 新增检查点重试、正式历史回放、面板接线、模式观效、偏好迁移用例 |

未改：V1–V5、`solver_backends/*` 内核、C++/Numba/NumPy 搜索内核、正式存档与 RL 模型；未 Git 提交。

---

## 10. V1–V5 与数据安全声明

未修改 V1–V5 任何源文件、存档目录或依赖；未改动真实对局存档、最高分、撤销/重做历史、
`rl_model.npz` 与历史实验数据；破坏性 GUI 测试全程使用隔离的临时 `2048_HISTORY_DIR`。
**未执行任何 Git 提交或推送。**
