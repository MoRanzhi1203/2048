# AGENTS.md —— 2048 项目级 Agent 规则

本文件是 2048 仓库的**项目级长期约束**，对所有版本、所有后续 Agent 会话生效。
细则见 [docs/GUI_SCREENSHOT_STANDARD.md](docs/GUI_SCREENSHOT_STANDARD.md)（**必须阅读**）。

---

## GUI 截图与视觉验收强制规范（长期有效，不得绕过）

1. **适用范围**：整个 2048 项目，不受版本限制。凡涉及启动页/游戏页/UI 改动对比/粒子效果/运行验证/自动化测试/Bug 复现/版本发布的截图，一律适用。
2. **必须包含 Windows 原生标题栏**：左上角软件图标、窗口标题 `2048`、最小化/最大化/关闭按钮、完整边框。禁止用仅含 Qt 客户区的截图冒充完整窗口截图；`QWidget.grab()` 只能用于组件级调试。
3. **不得丢失文字**：中文、数字、按钮文字、分数、棋盘数字、标题必须真实清晰完整。背景/棋盘正常但文字缺失或成方块的截图，判定失败。
4. **首选真实 Windows GUI 捕获**：以 `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` 取可见外框，再从屏幕 DC `BitBlt` 抓取。**禁止**默认使用 `QT_QPA_PLATFORM=offscreen` 或 `QWidget.grab()` 的结果充当正式验收截图。
5. **必须通过完整性验证**：`CAPTURE_PASS` → `STRUCTURE_PASS` → `TEXT_PASS` → `VISUAL_PASS` → `GUI_SCREENSHOT_PASS`。文件存在不等于合格；结构通过不等于文字通过。**未验证项标记 `UNVERIFIED`，不得标记 PASS**。
6. **不合格截图不得交付**：必须修复截图流程或重新捕获；无法完成时明确报告阻塞原因。
7. **GUI 任务完成前必须自检**：任何 GUI 相关改动（布局、字体、配色、粒子、Bug 修复、回归）在宣布完成前，都要按本规范出图并核对门禁。
8. **禁止伪造验证**：不得用历史截图冒充最新版本、不得后期添加文字/合成标题栏、不得为截图临时隐藏 UI 元素、不得未检查图片就宣称完整、不得未执行测试就标记 PASS。
9. **跨版本一致**：正式截图统一走 `tools/capture_gui.py`（`--version v3|v4`）。新增 GUI 版本需在该工具 `VERSIONS` 表登记后再截图。无 GUI 或缺少可运行环境的版本标记 `UNVERIFIED`。
10. **本规范持续有效**：后续版本与新 Agent 会话仍须执行，用户无需再次提醒「截图不要丢文字、不要裁掉标题栏」。

---

## 统一截图入口

```bash
python tools/capture_gui.py --version v4 --scene start|game|hover|merge
python tools/capture_gui.py --version v3 --scene start|game
# 人工核对图像后再授予 VISUAL_PASS
python tools/capture_gui.py --version v4 --scene start --visual-confirm
```

成功打印 JSON（含 `gates`）并返回 0；失败打印 `error`/`traceback` 并返回非 0。
正式图命名固定为各版本 `screenshots/full_<scene>.png`。

---

## 其他既有约定（简）

- 游戏核心逻辑（规则、随机生成、分数、存档、撤销重做）与既有 UI/粒子参数，非任务明确要求不得改动。
- 中间脚本、草稿、调试产物放在仓库之外；正式产物放在对应版本目录。
- 不提交运行时对局存档（`game_history/` 已忽略）。
