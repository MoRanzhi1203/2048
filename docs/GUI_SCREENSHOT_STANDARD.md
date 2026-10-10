# 2048 项目 GUI 截图标准（正式整窗截图）

> 本规范对**整个 2048 仓库的所有版本、所有后续开发任务**长期有效，不限于某一版。
> 适用范围、工具入口与验收门禁均为强制要求；违反本规范的截图不得作为交付物。

---

## 1. 适用范围

以下场景**必须**产出符合本标准的正式整窗截图：

- 启动页截图、游戏页截图
- UI 修改前后对比
- 粒子动画截图（点击 / 持续悬停 / 合并 / 达成 2048）
- 软件运行验证、自动化测试截图
- Bug 复现截图、版本发布截图

涉及 GUI 的任务（界面开发、布局调整、字体配色、粒子效果、GUI Bug 修复与回归）完成前，必须按本规范自检截图。

---

## 2. Windows 原生标题栏（强制）

正式整窗截图**必须**完整包含：

- 左上角应用程序图标
- 窗口标题（本项目为 `2048`）
- 最小化按钮、最大化/还原按钮（含其实际状态）、关闭按钮
- 完整的窗口边框与顶部区域

**禁止**用仅含 Qt 客户区的截图冒充完整窗口截图。
`QWidget.grab()` / `widget.grab()` 只能用于组件级调试，不能作为正式整窗截图。

---

## 3. 字体完整性（强制）

正式截图中所有可见文字必须真实、清晰、完整：

- 中文：副标题「合并数字，拼出 2048」、卡片标题、「分数」「最高分」、按钮文字
- 数字：分数、最高分、棋盘内全部非空数字（如 2/4/8/16/128/512/1024/2048）
- 主标题 `2048`

判定标准：背景、棋盘、按钮、方块配色正常**但文字缺失或呈方块**的截图，一律判定**失败**。

根因备忘（本项目实测）：

- `QT_QPA_PLATFORM=offscreen` 的字体引擎按 1em 方框返回字宽（实测 `QFont.setPixelSize(28)` 时 `'0'` 的 advance = 28px，而真实平台为 17px），导致文字为空白/方块 → **正式截图禁止使用离屏平台**。
- 必须在创建 `QApplication` 之后设置应用字体：`QFont("Microsoft YaHei")` + `setFamilies([...])`，与 `main()` 保持一致。

---

## 4. 正式截图 与 组件级截图

| 类型 | 用途 | 要求 |
|---|---|---|
| **正式整窗截图** | 交付、验收、发布、对比 | 必须含原生标题栏 + 全部文字；通过第 8 节全部门禁 |
| 组件级截图 | 局部控件调试、棋盘绘制、粒子区域验证 | 允许 `QWidget.grab()`、允许裁切；**不得**替代正式截图 |

命名上必须可区分：正式图统一为 `screenshots/full_<scene>.png`；组件图使用独立名称（如 `*_clientarea.png`、`*_detail.png`）。

---

## 5. 截图方式：首选与回退

**首选（正式）**：真实 Windows 桌面窗口捕获。

1. 取得窗口 `HWND`（`int(widget.winId())`）。
2. `AttachThreadInput` + `SetForegroundWindow` 让窗口真前台（后台进程直接置前会被系统拒绝）。
3. 恢复/定位窗口：`ShowWindow(SW_RESTORE)`，`SetWindowPos` 放到主屏可见位置。
4. 取**可见外框**：`DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)`（自动排除 DWM 阴影）；失败回退 `GetWindowRect`。
5. 从**屏幕 DC** `BitBlt(SRCCOPY | CAPTUREBLT)` 抓取该区域。
6. `GetDIBits`(32bpp, top-down) → `QImage(Format_RGB32)` → 无损 PNG。

**备用**：`PrintWindow(PW_RENDERFULLCONTENT)`。仅当首选结果为空/近似纯色时使用，且必须重新走第 8 节门禁。

**禁止**：截图明显不完整（缺标题栏或缺文字）时自动降级为客户区截图并宣称成功。

---

## 6. DPI 与坐标

必须区分四种坐标：Qt 逻辑坐标、Windows 屏幕坐标、图像物理像素、DWM 外框坐标。

- 外框坐标（物理像素）来自 DWM/`GetWindowRect`。
- 控件位置来自 `widget.mapToGlobal()`（逻辑坐标），转图像像素：`round(logical × dpr) - frame_origin`。
- `dpr = widget.devicePixelRatioF()`；实测各缩放档标题栏物理高度均约 **39px**（由系统 DPI 绘制）。
- 验收须覆盖 **100% / 125% / 150%**（`QT_SCALE_FACTOR`）；截图区域不得因 DPI 不一致而裁掉标题栏、边框或底部按钮。
- 可保留极少周围背景，但不得留大面积无关桌面区域。

---

## 7. 渲染稳定性与等待

截图前必须：

1. 窗口已 `show()`/`raise_()`，且 `isVisible()`。
2. 布局与首帧绘制完成，必要时处理事件队列。
3. 采用「**状态检查 + 超时**」而非固定 `sleep`：
   - 等待窗口可见/前台；等待粒子/动画进入目标状态（如 `len(particles) > 0`、`anim["phase"] == "pop"`）。
4. 通过 `is_window_on_top()`（`WindowFromPoint`）确认未被遮挡；被遮挡则再置前一次。
5. 稳定等待默认 300ms（`--settle-ms` 可调）。

---

## 8. 质量门禁（验收）

文件存在 ≠ 截图合格；结构通过 ≠ 文字通过；文字通过 ≠ 与目标界面一致。

| 门禁 | 含义 | 判定 |
|---|---|---|
| `CAPTURE_PASS` | PNG 生成且可解码 | 保存成功 + `QImage` 非空 |
| `STRUCTURE_PASS` | 窗口结构完整 | 外框高度 > 客户区高度（含标题栏）且非空白、窗口未被遮挡、图标可见（彩色像素 > 20）、控制按钮可见（字形像素 > 15） |
| `TEXT_PASS` | 文字真实可见 | 主标题区域暗像素占比 > 0.03，且≥7 个必需文字元素对比度 > 0.01 |
| `VISUAL_PASS` | 与目标界面一致 | **需人工视觉核验**；未核验标记 `UNVERIFIED`，不得标记 PASS。工具加 `--visual-confirm` 才授予 |
| `GUI_SCREENSHOT_PASS` | 全部必须项通过 | 上述四项全部为真 |

**未验证的项目一律标记 `UNVERIFIED`，不得标记 PASS。**

---

## 9. PNG 与命名

- 格式：无损 **PNG**，不得做影响文字清晰度的压缩/缩放。
- 命名：正式整窗图 `screenshots/full_<scene>.png`。
- 场景名建议：`start` / `game` / `hover` / `merge`。
- 归档位置：跟随所属版本目录，如 `v4_pyqt_2048_animated/screenshots/`、`v3_pyqt_2048/screenshots/`。

---

## 10. 常见错误与排查

| 现象 | 根因 | 处理 |
|---|---|---|
| 文字缺失/方块 | 用了 `QT_QPA_PLATFORM=offscreen` | 改在真实 Windows 平台运行截图 |
| 无标题栏 | 用了 `QWidget.grab()` | 改用屏幕 DC + DWM 外框捕获 |
| 顶部被裁一点 | 用了 `GetWindowRect`（含阴影/边框误差） | 改用 `DWMWA_EXTENDED_FRAME_BOUNDS` |
| 截图是黑的/桌面 | 窗口被遮挡或在屏幕外 | `prepare_window()` 置前并移到主屏可见位置 |
| 位置整体偏移 | 逻辑坐标未乘 `dpr` | 按第 6 节换算 |
| 只截到 `ParticleOverlay` | 直接抓控件 | 抓整个窗口外框 |

---

## 11. 失败处理流程

1. 门禁失败 → **不得交付**该截图。
2. 按第 10 节定位根因；修复截图流程或重试捕获（最多 3 次）。
3. 仍失败 → 在交付结果中明确报告**阻塞原因**与已尝试的手段，标记该项 `UNVERIFIED`。
4. 禁止用「后期加文字」「合成标题栏」「临时隐藏 UI 元素」「历史截图冒充」等方式掩盖问题。

---

## 12. 跨版本统一规则

- 统一入口：`tools/capture_gui.py`，通过 `--version` 选择版本。
- 已登记版本：
  - `v4` = 第 4 版动画版（`v4_pyqt_2048_animated`），场景 `start|game|hover|merge`
  - `v3` = 第 3 版 MVC/撤销重做（`v3_pyqt_2048`），场景 `start|game`
- 新增 GUI 版本时，在 `VERSIONS` 中登记「模块目录 / 模块名 / 可用场景 / 出图目录」后再截图。
- 无 GUI 的版本（控制台版等）不适用本规范；确实缺少可运行环境的版本标记 `UNVERIFIED`，不得推断通过。

### 统一入口用法

```bash
# 成功：打印 JSON（含 gates），退出码 0；失败：打印 error/traceback，退出码非 0
python tools/capture_gui.py --version v4 --scene start
python tools/capture_gui.py --version v4 --scene game
python tools/capture_gui.py --version v4 --scene hover
python tools/capture_gui.py --version v4 --scene merge
python tools/capture_gui.py --version v3 --scene start
python tools/capture_gui.py --version v3 --scene game
# 人工核对图像后授予 VISUAL_PASS
python tools/capture_gui.py --version v4 --scene start --visual-confirm
```

退出码：`0` 通过（CAPTURE/STRUCTURE/TEXT 全通过）｜`2` 场景不合法｜`3` 非 Windows 平台（含 offscreen）｜`4` 捕获为空｜`5` 保存失败｜`6` 门禁未通过｜`7` 运行异常。

---

## 13. 已实测基线（2026-10，100% DPI）

| 项目 | 实测值 |
|---|---|
| 窗口外框 | 502 × 711 px（客户区 500 × 672） |
| 标题栏高度 | 39 px |
| 图标彩色像素 | 165 ～ 213 |
| 控制按钮字形像素 | 24 ～ 108 |
| 125% / 150% 外框 | 627 × 879 / 752 × 1047（标题栏仍 39 px） |
| 截图写入存档 | 无（历史目录重定向到临时目录，且不调用 `close()`；实测 MD5 前后一致） |
