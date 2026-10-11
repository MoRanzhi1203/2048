# V5/V6 AI 推荐方向「可见度细化」交付报告（P0–P4）

- 环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`
- HEAD：`bbfb86a`（本轮**未提交**）；V1–V4、存档、RL 模型、既有测试证据均未改动
- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`

## P0 几何与“几乎不可见”的根因（实测）
- 几何（实测）：棋盘逻辑 `434×434`，`dpr=1.0`；`gutter/边框厚度 = BOARD_PADDING = 10px`，`圆角 = 9px`；overlay 父级 = `BoardView`，`geometry=(0,0,434,434)`，位于子控件栈顶（**未被遮挡**，`isVisible()` 正常）。
- 旧实现（上一版）经“基线 vs 有提示”像素差测量：
  - `changed ≈ 2580` 像素；**平均 |ΔLum| 仅 21.6**（≈8.5%），**峰值仅 43.7**；且方向为**变亮**（背景 lum 175 → 提示 196.6）。
  - 叠加因素：着色仅 10px 厚（约占棋盘边长 2.3%）、长度 60% 且峰值区窄，静态下**对比不足**。
- **根因结论**：提示确实绘制且未被遮挡，但“浅色低对比 + 窄峰值 + 60% 宽渐隐”使其在静态截图中几乎不可辨。

## P1 修订视觉：原生边框内嵌核心高亮
- **Base 层**：仅目标侧整条边框低幅度加深（`_BASE_ALPHA=0.12`，哑光深暖棕）——其余三边不变。
- **Focus 层**：沿边中间约 **44%**（`_CORE_A0/A1 = 0.28/0.72`），两端各**羽化 10%**（平台 0.38–0.62），**哑光深暖棕核心 `#756052`**（`_CORE_RGB=(117,96,82)`），峰值 `_CORE_ALPHA=0.84`。
- **对比**：静态 100% 下核心 ΔLum 峰值 ≈ **65–67**（对底色 175），明显可辨且非黑非高饱和、非硬边（羽化）。
- **几何约束**：`clip = 外轮廓圆角矩形(0,0,434,434,r=9) − 内边界(10,10,414,414)`；着色带厚 `pad − 1`（与瓦片留 **≥1 逻辑像素**间隙）。
- **动画（次要）**：核心亮度受控脉动 `±0.07`（≈±8%），周期约 2s，无位移光点/闪烁；`hideEvent`/`set_direction(None)` 立即停表。
- 未新增任何外侧光轨/箭头/光晕/徽标；未改变棋盘几何、圆角、边距与布局。

## P0/P1 实测（真实控件渲染，numpy 量化）
| 指标 | 旧实现 | 新实现 | 判据 |
| --- | --- | --- | --- |
| 平均 \|ΔLum\| | 21.6 | **27.0–28.7** | ≥12 |
| 峰值 \|ΔLum\| | 43.7 | **64.8–67.0** | 明显可辨 |
| 核心长度 | ~60%（浅） | **41.6–41.9%** | 35–45% |
| 与瓦片间隙 | — | **1 设备像素** | ≥1 |
| 其他三边变化 | 0 | **0** | 0 |
| DPR 1.0 / 受控 1.5× | — | **均 PASS** | 均需 PASS |

## P2 状态生命周期
- 仅在 `_on_solver_result` 通过 `job_id` + 棋盘签名校验后显示；手动走子即清除旧提示；停止 / 新游戏 / 继续 / **切换模式（本轮新增 `solver_mode.currentIndexChanged → _clear_hint`）** / 游戏结束 / 关闭窗口均清除；撤销/重做在求解中仍被屏蔽。
- 单一 overlay + 单一动画驱动；关闭时 `_detach_arrow_router` 移除过滤器、`hideEvent` 停表；V6 继承 V5，**未重复挂载**。

## P3 自动化验证（命令与退出码）
| 运行 | 数量 | 退出码 |
| --- | --- | --- |
| V5 `test_solver`（含边框/核心/定时器用例） | 91 | 0 |
| V6 完整回归（6 模块） | 40 | 0 |
| 独立边界脚本 DPR 1.0 | 4 方向 PASS | 0 |
| 独立边界脚本 `QT_SCALE_FACTOR=1.5`（**受控模拟**） | 4 方向 PASS | 0 |
| 真实整窗截图 12 场景 | CAPTURE/STRUCTURE/TEXT 全 True | 0 |

## P4 交付物
- 修改文件：`v5_pyqt_2048_solver/v5_pyqt_2048_solver.py`（`_SolverHintOverlay` 视觉重写 + 模式切换清除）、`v5_pyqt_2048_solver/test_solver.py`（更新度量用例）、`v6_pyqt_2048_accelerated/tests/test_arrow_keys.py`（同步度量）。
- 截图：`v6|v5/screenshots/full_suggest_{up,down,left,right}.png`；V6 标准 `full_start/game/solver/collapsed.png`。
- 对照图：[hint_border_directions_v6.png](computer://e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated\experiments\v6_1\20261011_195221\hint_border_directions_v6.png)、[hint_border_directions_v5.png](computer://e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated\experiments\v6_1\20261011_195221\hint_border_directions_v5.png)
- 采集记录：[gui_capture_hint_border_v2.jsonl](computer://e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated\experiments\v6_1\20261011_195221\gui_capture_hint_border_v2.jsonl)（12 条，全部自动门禁 PASS）。

## 门禁
`V5_HINT_RENDER=PASS` · `V6_HINT_RENDER=PASS` · `BORDER_CONTAINMENT=PASS` · `FOLLOW_HINT_STATE=PASS` · `KEYBOARD_REGRESSION=PASS` · `GUI_AUTOMATED=PASS` · **`GUI_VISUAL=UNVERIFIED`** · **`DPI_VISUAL=UNVERIFIED`**

## 失败/未验证 / 遗留
- `GUI_VISUAL`、`DPI_VISUAL` 保持 `UNVERIFIED`：需人工目视真实截图；125%/150% 仅做**受控模拟**，非真实系统缩放会话。
- 采集偶发瞬时不稳（一次 `titlebar_icon_visible=False` 波动）已通过“重试至三态 PASS”消除；最终 12/12 PASS。
- 若人工仍觉可辨识度不足：可再提高 `_CORE_ALPHA` 或加深 `_CORE_RGB`（仍限边框内），**不会**新增边框外元素。
