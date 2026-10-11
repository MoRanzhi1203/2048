# V5.1 · H8 收口：人工视觉核对清单（manual_visual_checklist）

> run: `20261011_160625` ｜ 状态：**`VISUAL_UNVERIFIED` / `DPI_VISUAL_UNVERIFIED`**（需人类目视；脚本不得授予 PASS）

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

## 3. 真实 Windows 125% / 150% 缩放步骤（需人工）

> 本机当前 100%（DPR=1.0）；**在未人工执行且还原系统设置前，`V5_1_DPI_VISUAL=UNVERIFIED`**。

1. Windows 设置 → 系统 → 显示 → 缩放：设为 **125%**、再设 **150%**。
2. 运行 `python v5_pyqt_2048_solver/v5_pyqt_2048_solver.py`，重做第 2 节 1–6 项。
3. 记录：实际 DPR、显示分辨率、截图尺寸、观察结果。
4. **完成后将缩放还原为原值**。

（受控 `QT_SCALE_FACTOR` 模拟已验证 dpr=1.25/1.5 下可正常构建与折叠往返，但**不等于**真实多 DPI 人工视觉。）

## 4. 人工确认方式

```bash
python tools/capture_gui.py --version v5 --scene start --visual-confirm   # game/solver/collapsed 同理
```

确认后由**人**将本文件状态改为 `VISUAL_PASS`；此前保持 `UNVERIFIED`。
