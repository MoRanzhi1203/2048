# 项目规则（Trae 自动加载）

> 本文件位于 `.trae/rules/`，由 Trae 作为项目规则自动加载。完整约束见根目录 [AGENTS.md](../../AGENTS.md)
> 与 [docs/GUI_SCREENSHOT_STANDARD.md](../../docs/GUI_SCREENSHOT_STANDARD.md)。

## GUI 截图与视觉验收（强制）

1. 本项目所有 GUI 截图任务（启动页/游戏页/UI 对比/粒子效果/运行验证/回归/发布）都必须遵守 `docs/GUI_SCREENSHOT_STANDARD.md`。
2. 正式截图必须是**完整窗口**：含 Windows 原生标题栏、左上角软件图标、最小化/最大化/关闭按钮与完整边框。禁止用仅客户区截图冒充；`QWidget.grab()` 仅限组件级调试。
3. 正式截图**不得丢失任何文字**（中文、数字、按钮文字、分数、棋盘数字、标题）。
4. 首选**真实 Windows 桌面捕获**（DWM 可见外框 + 屏幕 DC BitBlt）；禁止以 `QT_QPA_PLATFORM=offscreen` 或 `QWidget.grab()` 的结果充当正式验收截图。
5. 统一入口：`python tools/capture_gui.py --version v4|v3 --scene <scene>`；正式图命名 `screenshots/full_<scene>.png`。
6. 验收门禁：`CAPTURE_PASS` → `STRUCTURE_PASS` → `TEXT_PASS` → `VISUAL_PASS` → `GUI_SCREENSHOT_PASS`；**未验证标记 UNVERIFIED，不得标记 PASS**；不合格截图不得交付。
7. 禁止伪造：不得用历史截图冒充、不得后期加文字或合成标题栏、不得为截图隐藏 UI、不得未检查图片即宣称完整。
8. 新增 GUI 版本需在 `tools/capture_gui.py` 的 `VERSIONS` 中登记后再截图；无 GUI 或缺少可运行环境的版本标记 UNVERIFIED。
