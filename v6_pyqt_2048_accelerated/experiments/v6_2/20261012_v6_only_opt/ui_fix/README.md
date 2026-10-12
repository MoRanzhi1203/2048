# V6 界面修复记录：三档「运行速度」进入 AI 求解主面板

日期：2026-10-12　范围：**仅 V6**（V1–V5 只读，未改动任何 V1–V5 源文件）

## 1. 问题
三档运行速度控件此前被放入 `solver_advanced_body`（折叠的「高级参数」内），**在主面板不可见**。

## 2. 控件创建与布局位置（修复后）

| 控件 | 创建位置 | 布局位置 |
| --- | --- | --- |
| 「运行速度」分组 `v6_speed_panel` | `v6_speed.py::_v6_install_speed_panel()` | **AI 求解主面板** `solver_panel` 的 `QVBoxLayout`，紧跟参数表单 `solverGroup` 之后（成为第 3 个区块，位于「开始求解」运行区之上） |
| 三档按钮 `v6_speed_buttons`（标准/快速/极限） | 同上（`QPushButton` 可选中 + `QButtonGroup` 互斥） | 分组内 `QHBoxLayout`（横向三档），紧随「运行速度」标签 |
| 分段计时读数 `v6_timing_label` | 同上 | 分组内第二行 |

实测主面板布局顺序（`solver_panel.layout()` 逐项）：
`['QHBoxLayout'(头部), 'solverGroup'(算法/求解强度/求解模式), 'v6SpeedPanel'(运行速度), 'QHBoxLayout'(开始求解/进度), 'solverGroup'(状态), ...]`
→ **运行速度已位于主面板**，不再藏在高级参数。

## 3. 三项职责隔离（互不越界、互不串线）

| 控件 | 新名称 | 只影响 |
| --- | --- | --- |
| `solver_depth`（原「运行方式」） | **求解强度** | 算法参数（搜索深度 / 预算 / 强度）；选项与内部映射**完全保留** |
| `solver_mode`（原「模式」） | **求解模式** | 自动连走 / 单步建议 |
| `v6_speed`（新增） | **运行速度** | 动画开关 / 步间等待 / UI 指标刷新频率 |

- 标签改名在 **V6 进程内运行时**完成（`_v6_rename_solver_labels()` 遍历参数表单 QLabel），**不改 V5 源码**；选项、内部参数映射与行为不变。
- 校验：切换速度前后 `solver_depth.currentData()=='normal'`、`solver_mode.currentData()=='auto'`、`solver_strategy` 均不变。

## 4. 运行中切换：下一步边界安全生效
`_v6_on_speed_clicked()`：若 `_solver_running` 为真，仅记录 `_v6_pending_tier`（计时面板提示“下一步切换为 X”），
在 `_record_step()`（步边界）由 `_v6_apply_pending_tier()` 落实；`_start_solver()` 前也会先落实挂起切换。
**切换过程不创建任何 QTimer/QThread**（仅改模块常量与标志位），故不会产生重复定时器、重复线程或旧求解结果问题。

## 5. 修复前后截图（真实 Windows 整窗，DWM 外框 + 屏幕 BitBlt）

| 文件 | 场景 | 门禁 |
| --- | --- | --- |
| `before_full_game.png` | game | CAPTURE_PASS / STRUCTURE_PASS / TEXT_PASS / VISUAL 未验证 |
| `after_full_game.png` | game | CAPTURE_PASS / STRUCTURE_PASS / TEXT_PASS；文字校验新增 `运行速度=0.2725`、`速度-standard=0.059`、`速度-fast=0.0596`、`速度-extreme=0.0638` |

两图均含原生标题栏（`has_titlebar=true`、图标与最小化/最大化/关闭可见）、尺寸 `908×759`、无文字缺失。
`VISUAL_PASS` 保持 **UNVERIFIED**（需人工目视核对）。

## 6. 真实测试与退出码

| 项目 | 命令 | 退出码 |
| --- | --- | --- |
| 布局/改名/持久化/串线/边界切换校验 | `python %TEMP%\v6_2_tools\ui_fix_check.py` | **0**（CHECK_PASS） |
| V6 全量回归 | `python -m unittest discover -s tests` | **0**（Ran 62 tests, OK） |
| V6 整窗截图门禁 | `python tools/capture_gui.py --version v6 --scene game --out ...after_full_game.png` | **0** |

`ui_fix_check.py` 关键断言：表单标签 = `['算法','求解强度','求解模式']`；速度按钮父级 = `solverPanel`；
三档切换 → `step_delay 70/10/0`、`anim_off false/false/true`、`prefs` 同步写入；
运行中点击 → `pending='extreme'` 且当前仍为 `standard`，边界应用后生效；新窗口重启读到 `fast` → **CHECK_PASS**。

## 7. 产物
- 截图与日志：`experiments/v6_2/20261012_v6_only_opt/ui_fix/`
- 工具增强：`tools/capture_gui.py` 新增 V6 专属必需文字（运行速度 + 三档按钮），仅当窗口存在 `v6_speed_panel` 时生效（不影响 v3/v4/v5）

## 8. 未验证项
- **VISUAL_PASS**：三档按钮的观感/配色/与面板整体协调度需人工目视确认（保持 UNVERIFIED）。
- 未做真实多 DPI（125%/150%）下的三档速度与截图验证。
- 未在“单步建议”模式下逐档实测计时数字（其分段计时在单步模式下不构成连续连走，数值语义不同）。
