# V5.1 · 最终收口：人工视觉与真实 DPI 核对清单（manual_visual_checklist）

> run: `20261011_162440` ｜ 状态：**`VISUAL_PASS`（人类已目视确认）** / **`DPI_VISUAL_UNVERIFIED`**
> 说明：4 张整窗截图由**人**目视核对并通过（随后以 `capture_gui.py --visual-confirm` 授予）；真实 125%/150% 多 DPI 仍为 UNVERIFIED（见 `dpi_real_attempt.md`）。

## 1. 四张整窗截图（本轮重新捕获，真实工具输出）

| 场景 | 路径 | 尺寸 | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- | --- |
| START | `v5_pyqt_2048_solver/screenshots/full_start.png` | 502×711 | PASS | PASS | PASS | **PASS（人工确认）** |
| GAME | `v5_pyqt_2048_solver/screenshots/full_game.png` | 908×759 | PASS | PASS | PASS | **PASS（人工确认）** |
| SOLVER_EXPANDED | `v5_pyqt_2048_solver/screenshots/full_solver.png` | 908×759 | PASS | PASS | PASS | **PASS（人工确认）** |
| SOLVER_COLLAPSED | `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 502×759 | PASS | PASS | PASS | **PASS（人工确认）** |

原始门禁：`gui_capture.jsonl`（`has_titlebar=true`、`text_rendered=true`）。

## 2. 逐条目视确认项

1. **START**：原生标题栏/图标/最小化最大化关闭完整；按钮与文字无缺字/方块。
2. **GAME**：棋盘未被右栏遮挡；计分区、撤销/重做/新游戏/AI 求解入口排列合理。
3. **SOLVER_EXPANDED**：算法选择、策略/模式、开始求解/导出/查看/对比、进度与结果区合理；折叠箭头方向正确；低饱和配色。
4. **SOLVER_COLLAPSED**：整栏收起但**贴边把手始终可见可点击**，不过宽、不抢焦点、不遮棋盘。
5. 命名语义：「AI 求解」/「算法求解」/贴边把手清晰、不重复；键盘 Tab 可达、回车/空格可展开。

## 3. 真实 Windows 125% / 150% 缩放（需人工，改后须还原）

1. Windows 设置 → 系统 → 显示 → 缩放：设 **125%**、再设 **150%**。
2. 运行 `python v5_pyqt_2048_solver/v5_pyqt_2048_solver.py`，重做第 2 节各项。
3. 记录实际 DPR、分辨率、截图尺寸、观察结果；**完成后还原系统缩放**。

> 未执行上述真实步骤前，`V5_1_DPI_VISUAL=UNVERIFIED`；受控 `QT_SCALE_FACTOR` 模拟不等价于真实多 DPI。

## 4. 人工确认方式

```bash
python tools/capture_gui.py --version v5 --scene start --visual-confirm   # game/solver/collapsed 同理
```

由**人**确认后将本文件状态改为 `VISUAL_PASS`。
