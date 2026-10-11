# V5.1 · H8 收口：人工视觉核对清单（manual_visual_checklist）

> run: `20261011_160625` ｜ 状态：**`VISUAL_UNVERIFIED`**（需人类目视；脚本不得授予 PASS）

## 1. 四张整窗截图（真实工具输出，本轮重新捕获）

| 场景 | 路径 | 尺寸 | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- | --- |
| START | `v5_pyqt_2048_solver/screenshots/full_start.png` | 502×711 | PASS | PASS | PASS | **UNVERIFIED** |
| GAME | `v5_pyqt_2048_solver/screenshots/full_game.png` | 908×759 | PASS | PASS | PASS | **UNVERIFIED** |
| SOLVER_EXPANDED | `v5_pyqt_2048_solver/screenshots/full_solver.png` | 908×759 | PASS | PASS | PASS | **UNVERIFIED** |
| SOLVER_COLLAPSED | `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 502×759 | PASS | PASS | PASS | **UNVERIFIED** |

原始门禁 JSON：`gui_capture.jsonl`（`has_titlebar=true`、`text_rendered=true`）。

## 2. 逐条目视确认项

1. **START**：原生标题栏/图标/最小化最大化关闭完整；按钮与文字无缺字/方块。
2. **GAME**：棋盘未被右栏遮挡；计分区、撤销/重做/新游戏/AI 求解入口排列合理。
3. **SOLVER_EXPANDED**：算法选择、策略/模式、开始求解/导出/查看/对比、进度与结果区合理；折叠箭头方向正确；低饱和配色。
4. **SOLVER_COLLAPSED**：整栏收起但**贴边把手始终可见可点击**，不过宽、不抢焦点、不遮棋盘。
5. 命名语义：「AI 求解」/「算法求解」/贴边把手清晰、不重复。
6. 键盘/焦点：Tab 可达把手，回车/空格可展开。

## 3. 人工确认方式

```bash
python tools/capture_gui.py --version v5 --scene start --visual-confirm   # game/solver/collapsed 同理
```

确认后由**人**将本文件状态改为 `VISUAL_PASS`；此前保持 `UNVERIFIED`。
