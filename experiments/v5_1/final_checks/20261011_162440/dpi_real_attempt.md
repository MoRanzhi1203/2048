# V5.1 · 真实多 DPI（125%/150%）尝试记录与结论（dpi_real_attempt）

> run: `20261011_162440` ｜ 结论：**`V5_1_DPI_VISUAL = UNVERIFIED`**（自动化在本机无法可靠切换并生效；系统状态未被改动）

## 1. 尝试路径与实际证据

| 路径 | 操作 | 观测结果 |
| --- | --- | --- |
| A. 会话逻辑 DPI 覆盖 | `SystemParametersInfoW(SPI_SETLOGICALDPIOVERRIDE, {0,1}, …, SPIF_UPDATEINIFILE\|SPIF_SENDCHANGE)` | `GetDeviceCaps(LOGPIXELSX)` 恒为 **96**；`capture_gui dpr` 恒为 **1.0** → 对 Qt（DPI-aware）无效果 |
| B. 设置 → 系统 → 显示 → 缩放 | 经电脑控制展开下拉并选择「125% (推荐)」 | `dpr` 仍为 **1.0**；随后“缩放与布局”控件从可访问树消失；**注册表 `PerMonitorSettings` 各 `DpiValue` 与操作前逐项一致** → 未生效、未改动 |
| C. 辅助功能 `select` 动作 | 重新进入“显示”页后再取树 | 缩放控件未再出现（本机/多显示器环境下该控件不可通过自动化操作） |

## 2. 系统未被改动的证据

- `HKCU\Control Panel\Desktop\PerMonitorSettings\*` 的 `DpiValue` 在操作前后**完全相同**（0x0 / 0xffffffff / 0x1 / 0x4 / 0xfffffffe 等）。
- `HKCU\Control Panel\Desktop\Win8DpiScaling = 0`（未设自定义缩放）。
- 新启动的 Qt 应用 `devicePixelRatio = 1.0`（100%）。
- 结论：**本机缩放仍为原值 100%**，无副作用。

## 3. 为何保持 UNVERIFIED

- 无法在**真实 125%/150% 系统缩放**下取得整窗截图（自动化既不能生效切换，也无图像通道可供人工在此环节核对）。
- 受控 `QT_SCALE_FACTOR` 模拟（dpr 1.25/1.5，此前已验证可正常构建与折叠往返）**不等于**真实 Windows 多 DPI 人工视觉，不得据此授予 PASS。

## 4. 人工完成步骤（最短）

1. `设置 → 系统 → 显示 → 缩放` 设为 **125%**（提示注销时按需**注销/重新登录**使其完全生效）。
2. 运行 `python v5_pyqt_2048_solver/v5_pyqt_2048_solver.py`，核对：文字无裁切/重叠、棋盘与右栏不挤压、贴边把手位置正确、四场景正常。
3. 截图：`python tools/capture_gui.py --version v5 --scene game --out <自定义路径>`（记录实际 `dpr`）。
4. 重复步骤 1–3 于 **150%**。
5. **把缩放还原为原值（100%）**。

> 完成并人工核对后，可将 `V5_1_DPI_VISUAL` 记为 `PASS`。
