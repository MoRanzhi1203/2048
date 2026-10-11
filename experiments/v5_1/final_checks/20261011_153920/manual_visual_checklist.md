# V5.1 · H8 人工视觉核对清单（manual_visual_checklist）

> run: `20261011_153920` ｜ 状态：**`VISUAL_UNVERIFIED`**
> 需**人类**目视核对；任何脚本/自动化**不得**授予 `VISUAL_PASS`。

## 1. 整窗截图索引（真实工具输出）

| 场景 | 路径 | 尺寸 |
| --- | --- | --- |
| START | `v5_pyqt_2048_solver/screenshots/full_start.png` | 502×711 |
| GAME | `v5_pyqt_2048_solver/screenshots/full_game.png` | 908×759 |
| SOLVER_EXPANDED | `v5_pyqt_2048_solver/screenshots/full_solver.png` | 908×759 |
| SOLVER_COLLAPSED | `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 502×759 |

原始门禁 JSON：`gui_capture.jsonl`（CAPTURE/STRUCTURE/TEXT 均 PASS）。

## 2. 逐条目视确认项

1. **START**：原生标题栏/图标/最小化最大化关闭完整；「继续上一局 / 开始新游戏」文字无缺字、无方块。
2. **GAME**：棋盘**未被右栏遮挡**；计分区、撤销/重做/新游戏/**AI 求解**入口排列与间距合理。
3. **SOLVER_EXPANDED**：算法选择、策略/模式、开始求解/导出/查看/对比、进度与结果区合理；**折叠箭头方向正确**；低饱和配色。
4. **SOLVER_COLLAPSED**：侧栏按规则收起，**始终有可发现且可点击的展开入口**（贴边把手不过宽、不抢焦点、不遮棋盘）。
5. **命名语义**：「AI 求解」按钮、右栏「算法求解」标题、贴边把手命名清晰、视觉不重复。
6. **键盘/焦点**：Tab 可达贴边把手，「回车/空格」可展开；焦点态可见。

## 3. 人工确认方式

对视通过后（由**人**）执行：

```bash
python tools/capture_gui.py --version v5 --scene start --visual-confirm   # game/solver/collapsed 同理
```

并将本文件状态改为 `VISUAL_PASS`。**在此之前保持 UNVERIFIED。**
