# V5.1 · H7 人工视觉核对清单（manual_visual_checklist）

> run: `20261011_151155` ｜ 版本：v5（算法求解版）
> 状态：**VISUAL_UNVERIFIED** —— 需**人类**目视核对下方截图；脚本不得自动提升为 `VISUAL_PASS`。

## 1. 截图索引（完整窗口，含原生标题栏）

命令：

```bash
python tools/capture_gui.py --version v5 --scene start|game|solver|collapsed
```

| 场景 | 文件路径 | 分辨率 | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- | --- |
| START 初始界面 | `v5_pyqt_2048_solver/screenshots/full_start.png` | 502×711 | PASS | PASS | PASS | **UNVERIFIED** |
| GAME 正常棋盘 | `v5_pyqt_2048_solver/screenshots/full_game.png` | 908×759 | PASS | PASS | PASS | **UNVERIFIED** |
| SOLVER_EXPANDED 右栏展开 | `v5_pyqt_2048_solver/screenshots/full_solver.png` | 908×759 | PASS | PASS | PASS | **UNVERIFIED** |
| SOLVER_COLLAPSED 右栏折叠 | `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 502×759 | PASS | PASS | PASS | **UNVERIFIED** |

> 抓捕方式：真实 Windows 桌面 `screen-bitblt` + DWM 外框（`has_titlebar=true`、`titlebar_icon_visible=true`、`titlebar_controls_visible=true`）；文本经像素比校验 `text_rendered=true`、`texts_ok=true`。原始 JSON 见同目录 `gui_capture.jsonl`。

## 2. 待人工确认项（逐条目视）

请对以上四张**整窗**截图逐图确认：

1. **START**：原生标题栏/图标/最小化最大化关闭按钮完整；「继续上一局 / 开始新游戏」按钮与全部文字清晰无缺字、无方块。
2. **GAME**：棋盘**未被右侧栏遮挡**；计分区、撤销、重做、新游戏、**AI 求解**入口排列合理、间距一致。
3. **SOLVER_EXPANDED**：右栏含算法选择、策略/模式、开始求解/导出/查看/对比、进度与结果区；**折叠箭头方向正确**；按钮文字与主题低饱和配色一致。
4. **SOLVER_COLLAPSED**：整个侧栏按规则收起，**始终存在可发现且可点击的展开入口**（贴边把手）；把手不过宽、不抢焦点、不遮挡主棋盘。
5. **命名语义**：「AI 求解」按钮、右栏「算法求解」标题、贴边把手命名清晰、视觉不重复。
6. **低饱和/焦点/键盘可达性**：主题配色不刺眼；焦点态与键盘可达性合理。

## 3. 人工确认方式

核对通过后，可执行（由**人**决定）：

```bash
python tools/capture_gui.py --version v5 --scene start --visual-confirm
# 对 game / solver / collapsed 同理
```

并将本文件状态改为 `VISUAL_PASS`。**在人工确认前，本项保持 `VISUAL_UNVERIFIED`。**
