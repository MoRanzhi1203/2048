# V6.1 人工视觉核对清单（GUI_VISUAL / DPI）

> 状态：**UNVERIFIED**（未经人工目视核对，未加 `--visual-confirm`）。
> 规则：自动 `CAPTURE/STRUCTURE/TEXT=PASS` **不等于** `VISUAL_PASS`；须人工核对图像后方可授予。

## 待核对截图（真实 Windows 整窗，screen BitBlt + DWM 外框）

| 场景 | 文件 | 门禁（自动） |
| --- | --- | --- |
| start | `v6_pyqt_2048_accelerated/screenshots/full_start.png` | CAPTURE/STRUCTURE/TEXT=PASS |
| game | `v6_pyqt_2048_accelerated/screenshots/full_game.png` | CAPTURE/STRUCTURE/TEXT=PASS |
| solver | `v6_pyqt_2048_accelerated/screenshots/full_solver.png` | CAPTURE/STRUCTURE/TEXT=PASS |
| collapsed | `v6_pyqt_2048_accelerated/screenshots/full_collapsed.png` | CAPTURE/STRUCTURE/TEXT=PASS |

原始采集记录：`gui_capture.jsonl`（含 `frame_xywh`、`dpr`、`has_titlebar`、`texts`、`variance`、`not_blank` 等）。

## 人工核对项（逐条打勾后由人工授予 VISUAL_PASS）

- [ ] 含 Windows 原生标题栏：左上角软件图标、标题 `2048 V6 …`、最小化/最大化/关闭按钮、完整边框。
- [ ] 无裁切（顶部标题栏完整，四边外框可见）。
- [ ] 文字完整清晰：中文（按钮/标签/标题）、数字（分数/最大瓦片/棋盘数字），无方块/缺字。
- [ ] 启动页：主标题、副标题、分数/最高分、两个按钮文字齐全。
- [ ] 游戏页：棋盘与瓦片配色正常、数字清晰。
- [ ] 求解页：左右双栏、策略/深度/模式控件、开始求解按钮、日志区可见。
- [ ] 折叠态：右栏整体隐藏、贴边半胶囊把手可见，棋盘区完整。
- [ ] 无后期合成/加字/隐藏 UI 的痕迹。

## 高 DPI（125% / 150%）

- [ ] 在真实 125% 缩放整窗截图并核对文字与布局（**未测试 → 保持 UNVERIFIED**）。
- [ ] 在真实 150% 缩放整窗截图并核对文字与布局（**未测试 → 保持 UNVERIFIED**）。

> 说明：本轮**未**修改用户系统 DPI 设置来伪造通过；DPI 项保持 `UNVERIFIED`。
