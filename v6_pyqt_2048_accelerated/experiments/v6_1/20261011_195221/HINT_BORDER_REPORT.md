# V5.1 / V6.1：AI 推荐方向「原生边框内嵌高亮」交付报告（A0–A4）

- 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
- HEAD：`bbfb86a`（本轮**未提交**）；V1–V4 源码、存档、RL 模型、既有测试证据均未改动
- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`

## A0 基线审计
- V6 直接继承 V5：`V6MainWindow(_v5gui.SolverMainWindow)`；提示高亮层 `_SolverHintOverlay` 定义在 V5，**单点实现、无分叉**。
- 棋盘几何（v4，只读）：`BOARD_SIDE=434`、`BOARD_PADDING=10`、`BOARD_RADIUS=9`、`COLOR_BOARD=#bbada0`；原边框像素厚度 = `BOARD_PADDING` = 10px。
- 旧实现（本轮废弃）：外侧/内侧“高亮带 + 大三角箭头”，违反最终方案（禁止大三角/箭头/外侧元素）。
- 基线哈希：`v5_pyqt_2048_solver.py` `58AA2914…`；`v4_pyqt_2048_animated.py` `DBF23917…`（v4 未改）。

## A1 视觉修复（原生边框内嵌式局部高亮）
仅改 V5 `_SolverHintOverlay`（V6 继承）：
1. **精确裁剪**：`border = 外轮廓圆角矩形(0,0,434,434,r=9) − 内边界矩形(10,10,414,414)`；`setClipPath(border)`，所有高亮像素**必须**落在原边框区域内。
2. **局部长度**：沿边方向仅高亮中间 **60%**（`_EDGE_SPAN=0.60`），用 `QLinearGradient` 做“两端渐隐”（5 档 bell：0→0、0.22→0.42·peak、0.5→peak、0.78→0.42·peak、1→0），无矩形端头/拼接线。
3. **厚度**：渐变轴沿边、垂直方向恒定 ⇒ 恰好填满该边原边框厚度（10px），不新增任何厚度。
4. **配色**：高亮色 = 原边框色 `#bbada0` 的派生亮色（`lighter(145)`，暖灰），峰值不透明度 0.62；不使用纯绿/亮金/高饱和色。
5. **极轻流动**（辅助）：`_FLOW_AMP=0.04` 缓慢移动亮度中心；`QTimer`(90ms) 仅重绘提示层自身；`hideEvent`/`set_direction(None)` 立即停表。
6. 保持 `WA_TransparentForMouseEvents`；四方向几何对称（左右与上下等宽等长）；按控件实时尺寸计算，不缓存全局坐标。

## A2 状态衔接（跟随预测一致性）
- 手动走子开始即清除旧高亮；仅在 `_on_solver_result` 通过 `job_id` 与棋盘签名校验后 `_show_hint(方向)`；停止/新游戏/继续/游戏结束/关闭均 `_clear_hint()`；撤销/重做在求解中仍被屏蔽。
- 未发现与本轮视觉相关的直接缺陷；未改动求解控制器与并发语义。

## A3 针对性测试
- 独立边界脚本（离屏，DPI 感知）：四方向 **outside_border=0**、目标边有高亮、其他三边 0、沿边长度 59.9–60.1%。
  - DPR 1.0：PASS；`QT_SCALE_FACTOR=1.5`（**受控模拟**）：PASS（设备像素 651×651，仍全部在边框内）。
- V5 `test_solver`：**91 项 PASS**（含新增 `test_hint_overlay_within_native_border`、`test_hint_overlay_clear_stops_timer`）。
- V6：`test_arrow_keys` **8 项 PASS**（含新增 `test_hint_overlay_shared_renderer_and_border`）；V6 完整回归 **40 项 PASS**。
- 命令均设有界等待；未出现卡顿或线程告警。

## A4 证据交付（真实窗口截图）
- 四方向整窗截图（真实 Windows，screen BitBlt + DWM 外框）：
  `v6_.../screenshots/full_suggest_{up,down,left,right}.png`、
  `v5_.../screenshots/full_suggest_{up,down,left,right}.png`。
- V6 标准整窗：`full_start/game/solver/collapsed.png`（并 `full_suggest.png`）。
- 四方向对照图（真实控件渲染裁剪，2×2）：`hint_border_directions_v6.png`、`hint_border_directions_v5.png`。
- 采集记录：`gui_capture_hint_border.jsonl`（12 条）。
- 影响文件清单：`v5_pyqt_2048_solver/v5_pyqt_2048_solver.py`（高亮层重写 + `math`/`QLinearGradient` 导入）、`v5_pyqt_2048_solver/test_solver.py`（+2 用例）、`v6_pyqt_2048_accelerated/tests/test_arrow_keys.py`（+1 用例）、`tools/capture_gui.py`（新增 4 个方向 suggest 场景 + 参数化，保持 `suggest` 兼容）。

## 门禁状态
| 门禁 | 状态 | 依据 |
| --- | --- | --- |
| V5_HINT_RENDER | **PASS** | `test_hint_overlay_within_native_border` + 边界脚本 |
| V6_HINT_RENDER | **PASS** | 继承 V5；`test_hint_overlay_shared_renderer_and_border`（断言渲染器来自 v5） |
| BORDER_CONTAINMENT | **PASS** | 四方向 `outside_border=0`（DPR1.0 与受控 1.5×） |
| FOLLOW_HINT_STATE | **PASS** | 清除/停表/状态回归用例 |
| KEYBOARD_REGRESSION | **PASS** | V5 91 + V6 40 全通过（含方向键路由用例） |
| GUI_AUTOMATED | **PASS** | 12 场景 `CAPTURE/STRUCTURE/TEXT=PASS` |
| GUI_VISUAL | **UNVERIFIED** | 未人工目视（模拟输入 ≠ 人工视觉 PASS） |
| DPI_VISUAL | **UNVERIFIED** | 真实 125%/150% 未测；仅受控 `QT_SCALE_FACTOR` 模拟 |

## 剩余问题 / 风险
- **可辨识性需人工评估**：原边框较薄（10px），峰值亮度若不足需人工确认；未擅自加粗边框（遵循空间约束）。
- **真实高 DPI 与人工视觉**保持 `UNVERIFIED`，需人工在真实 125%/150% 下查看截图后授予。
- 极轻流动为可选辅助，已限制在提示层内、隐藏即停表。
