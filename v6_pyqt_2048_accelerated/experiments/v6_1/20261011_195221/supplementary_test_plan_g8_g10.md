# V6.1 补充测试计划：G8（GUI 视觉 / DPI）与 G10（发布就绪）

- 关联门禁：`release_gates.json` → `G8_GUI_VISUAL_AND_DPI = UNVERIFIED`，`G10_V6_1_RELEASE_READY = PARTIAL_PASS`
- 唯一阻塞项：**G8**（其余 G0–G7、G9 已 PASS）
- 解释器：`E:\anaconda3\envs\2048\python.exe`；`$env:PYTHONNOUSERSITE=1`
- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`
- 规范依据：`docs/GUI_SCREENSHOT_STANDARD.md`、`AGENTS.md`、V6.1 指令 §H9-6.5 / §9

> 状态规则（不得违反）：自动 `CAPTURE/STRUCTURE/TEXT=PASS` **不等于** `VISUAL_PASS`；未人工目视不得授予 `VISUAL_PASS`。真实 125%/150% 未测则保持 `UNVERIFIED`，**不得修改用户系统 DPI 设置来伪造通过**，不得用历史图/后期加字/合成标题栏冒充。

---

## 一、目标与范围

| 编号 | 目标 | 当前 | 关闭条件 |
| --- | --- | --- | --- |
| G8-a | GUI 人工视觉核对 | UNVERIFIED | 人工逐图核对 4 张整窗截图并授予 `VISUAL_PASS` |
| G8-b | 高 DPI（125%/150%） | UNVERIFIED | 见 §三（方案 A/B/C 三选一，含决策留痕） |
| G10 | 发布就绪 | PARTIAL_PASS | G8-a 通过 +（G8-b 通过 或 按规范判定 DPI 非门禁并留痕）+ §四复核 |

范围仅限 V6 GUI 的**视觉与 DPI 验证**；不改动五策略语义、后端、存档隔离（相关项已 PASS）。若验证中发现缺陷需改代码，改动后**必须重跑受影响测试与受影响场景的截图**（见 §四.3）。

## 二、G8-a 人工视觉核对（唯一可授予 VISUAL_PASS 的路径）

### 2.1 前置：重新生成当前代码的整窗截图（若自上次采集后有 UI 改动）
```powershell
$env:PYTHONNOUSERSITE="1"; cd e:\PyQt5_demo\2048
foreach ($s in @('start','game','solver','collapsed')) {
  python tools/capture_gui.py --version v6 --scene $s --settle-ms 400
}
```
- 产物：`v6_pyqt_2048_accelerated/screenshots/full_{start,game,solver,collapsed}.png`
- 采集记录：追加/覆盖 `gui_capture.jsonl`（须含 `grab=screen-bitblt`、`frame_from=dwm`、`has_titlebar=true`、`texts_ok=true`）。

### 2.2 人工逐图核对（人工执行，非 Agent 自动判定）
逐张打开 PNG，按 `manual_visual_checklist.md` 勾选：
1. 含 **Windows 原生标题栏**：左上角软件图标、标题 `2048 V6 …`、最小化/最大化/关闭按钮、完整边框。
2. **无裁切**：顶部标题栏完整、四边外框可见、底部按钮未被裁。
3. **文字完整清晰**：中文（按钮/标签/标题）、数字（分数/最大瓦片/棋盘数字）无缺字/方块。
4. 各场景要素：启动页（主/副标题、分数与最高分、两个按钮）；游戏页（棋盘与瓦片配色、数字）；求解页（左右双栏、策略/深度/模式、开始求解、日志区）；折叠态（右栏隐藏、贴边半胶囊把手、棋盘完整）。
5. 无后期合成/加字/临时隐藏 UI 的痕迹。

### 2.3 授予 VISUAL_PASS（人工确认后执行）
```powershell
$env:PYTHONNOUSERSITE="1"; cd e:\PyQt5_demo\2048
foreach ($s in @('start','game','solver','collapsed')) {
  python tools/capture_gui.py --version v6 --scene $s --visual-confirm
}
```
- 判据：`gui_capture.jsonl` 中 4 条记录的 `gates.VISUAL_PASS == true` 且 `gates.GUI_SCREENSHOT_PASS == true`。
- 若某图任一勾选项不通过 → 记 FAIL，附原图与说明，**禁止**以 `--visual-confirm` 强行通过。

### 2.4 验收产物
- `gui_capture.jsonl`（含 `--visual-confirm` 后的 4 条记录）
- `manual_visual_checklist.md`（勾选留痕，注明核对人与时间）

## 三、G8-b 高 DPI（125% / 150%）——三选一，须留痕

> 规范 `docs/GUI_SCREENSHOT_STANDARD.md` §6：**100% 为必测基线**；125%/150% **为可选、不作为发布门禁**。`QT_SCALE_FACTOR` 受控缩放**必须标注为“受控模拟”，不等于真实系统多 DPI**。

### 方案 A（推荐/合规）：真实系统 DPI 采集
前提：在**独立会话/机器**上把 Windows 显示缩放真正设为 125% 与 150%（**不是**修改本机用户设置来伪造）。
```powershell
# 在 125% 缩放的会话中：
$env:PYTHONNOUSERSITE="1"; cd e:\PyQt5_demo\2048
python tools/capture_gui.py --version v6 --scene game --out screenshots\dpi_1.25_real.png
# 在 150% 缩放的会话中：
python tools/capture_gui.py --version v6 --scene game --out screenshots\dpi_1.5_real.png
```
- 判据：捕获记录 `dpr` ≈ 1.25 / 1.5；标题栏、文字、按钮完整不裁切；人工目视通过。
- 产物：`dpi_1.25_real.png`、`dpi_1.5_real.png` + 对应 `gui_capture` 记录。

### 方案 B（受控模拟，须标注）：`QT_SCALE_FACTOR`
```powershell
$env:PYTHONNOUSERSITE="1"; $env:QT_SCALE_FACTOR="1.5"
python tools/capture_gui.py --version v6 --scene game --out screenshots\dpi_1.5_simulated.png
```
- 判据：`dpr` ≈ 1.5；文字不裁切、窗口落屏内、控件不重叠（与 `tests/test_popups.py` 1.5x 用例一致）。
- **输出须命名为 `*_simulated`**，门禁记为 `DPI_CONTROLLED_SIMULATION=PASS`，**不得**记为真实 DPI `PASS`。

### 方案 C（判定非门禁，留痕）
若沿用 V5.1 决策（`experiments/v5_1/known_issues.md` §D）与 `GUI_SCREENSHOT_STANDARD` §6，认定 DPI 非发布门禁：
- 在 `release_gates.json` 写明 `G8b=NOT_A_GATE`、依据文件与决策人；
- 保持真实多 DPI `UNVERIFIED`（不谎报）。

### G8-b 关闭判据
- 方案 A：真实 125%+150% 均人工通过 → `DPI_VISUAL=PASS`；或
- 方案 B：受控模拟通过且如实标注 → `DPI_CONTROLLED_SIMULATION=PASS`（真实 DPI 仍 UNVERIFIED）；或
- 方案 C：`NOT_A_GATE` 决策留痕。

## 四、G10 发布就绪（PARTIAL_PASS → PASS）

### 4.1 阻塞依赖
- G10 仅在 **G8-a = PASS** 且 **G8-b = PASS / 受控模拟 PASS / NOT_A_GATE（留痕）** 后可评估。

### 4.2 剩余必需复核（在宣称 PASS 前重跑并留存原始输出）
1. **可复现构建**（若涉及 pyd/后端改动后）：`bitboard_tests.exe` 输出 `ALL TESTS PASSED`；`python -c "import solver_backends.bitboard_cpp as p; p.load_extension().available()"`。
2. **回归**：V6 5 套件 32 项 + V5 `test_solver` 80 项（`tests.log` / `v5_regression.log`），退出码 0。
3. **截图与文本门禁**：4 场景 `CAPTURE/STRUCTURE/TEXT=PASS`。
4. **报告一致性**：`final_report.md`、`release_gates.json`、`gui_capture.jsonl`、`manual_visual_checklist.md` 状态互相一致（禁止 `capture=PASS` 冒充 `VISUAL_PASS`）。

### 4.3 变更联动规则
- 验证期若修改任何代码/UI：受影响场景截图**必须重新采集**，`source_hash_after.json` / `git_after.txt` 必须刷新，并重跑受影响测试；否则不得更新门禁。

### 4.4 G10 关闭判据
- `release_gates.json`：G0–G9 全 PASS（G8 达关闭判据），`G10 = PASS`，`mandatory_gate_result` 全部 PASS。

## 五、反伪造与状态规则（硬约束）

1. 禁止以 `QWidget.grab()` / `QT_QPA_PLATFORM=offscreen` 结果充当正式整窗截图。
2. 禁止历史截图冒充最新版本；禁止后期加字/合成标题栏；禁止为截图临时隐藏 UI。
3. 未人工核对 → `VISUAL_PASS=UNVERIFIED`；未真实多 DPI → `DPI_VISUAL=UNVERIFIED`。**不得越级 PASS**。
4. 每条门禁须附：实际命令、退出码、样本数、证据路径、状态。
5. `QT_SCALE_FACTOR` 结果只能记为受控模拟。

## 六、执行清单（勾选）

- [ ] G8-a-1 重新采集 4 场景整窗截图（CAPTURE/STRUCTURE/TEXT=PASS）
- [ ] G8-a-2 人工逐图核对 `manual_visual_checklist.md` 全部勾选项
- [ ] G8-a-3 `--visual-confirm` 授予并核对 `VISUAL_PASS=true`
- [ ] G8-b 选定方案 A/B/C 并产出对应证据/决策留痕
- [ ] G10-1 复核可复现构建（bitboard_tests / 导入）
- [ ] G10-2 重跑 V6(32)+V5(80) 回归
- [ ] G10-3 报告一致性核对
- [ ] G10-4 更新 `release_gates.json`（G8→PASS 或记录 NOT_A_GATE；G10→PASS）

## 七、风险与回退
- 无真实 125%/150% 环境 → 走方案 B/C，如实标注，不谎报。
- 人工核对发现视觉缺陷 → 记 FAIL + 原图，回归到修复，再全流程重跑。
- 任何一步无法完成 → 保持对应项 `UNVERIFIED`，`G10` 维持 `PARTIAL_PASS`，不得强行置 PASS。
