# 03 图片与公式审计（P3 CSDN 发布适配）

- 审计对象：`csdn_2048_review/articles/` 九篇修订稿
- 图片检查：按真实项目路径判断存在性，不使用占位图，不生成伪造 CSDN URL
- 公式检查：结构计数 + 构造清单；CSDN 在线预览不可用，渲染结果标记 `UNVERIFIED`

## 1 图片映射表（全部 `UPLOAD_REQUIRED`）

| # | 文章 | alt | 本地目标 | 文件存在 | 建议上传文件名 | 替换占位符 | CSDN 状态 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `03_pyqt_mvc_undo.md` | 启动页 | `../../v3_pyqt_2048/screenshots/full_start.png` | YES | `full_start.png` | `{{IMG_01}}` | UPLOAD_REQUIRED |
| 2 | `03_pyqt_mvc_undo.md` | 游戏页 | `../../v3_pyqt_2048/screenshots/full_game.png` | YES | `full_game.png` | `{{IMG_02}}` | UPLOAD_REQUIRED |
| 3 | `04_animation_render.md` | 启动页 | `../../v4_pyqt_2048_animated/screenshots/full_start.png` | YES | `full_start.png` | `{{IMG_03}}` | UPLOAD_REQUIRED |
| 4 | `04_animation_render.md` | 合并粒子 | `../../v4_pyqt_2048_animated/screenshots/full_merge.png` | YES | `full_merge.png` | `{{IMG_04}}` | UPLOAD_REQUIRED |
| 5 | `04_animation_render.md` | 游戏页 | `../../v4_pyqt_2048_animated/screenshots/full_game.png` | YES | `full_game.png` | `{{IMG_05}}` | UPLOAD_REQUIRED |
| 6 | `05b_ai_workbench.md` | 开始页 | `../../v5_pyqt_2048_solver/screenshots/full_start.png` | YES | `full_start.png` | `{{IMG_06}}` | UPLOAD_REQUIRED |
| 7 | `05b_ai_workbench.md` | 游戏页（展开态：左侧游戏台 + 右侧 AI 求解工作台） | `../../v5_pyqt_2048_solver/screenshots/full_solver.png` | YES | `full_solver.png` | `{{IMG_07}}` | UPLOAD_REQUIRED |
| 8 | `05b_ai_workbench.md` | 折叠态（整体隐藏右栏，右侧贴边半胶囊把手） | `../../v5_pyqt_2048_solver/screenshots/full_collapsed.png` | YES | `full_collapsed.png` | `{{IMG_08}}` | UPLOAD_REQUIRED |
| 9 | `05b_ai_workbench.md` | 单步建议（棋盘原生边框内的「内嵌明暗轮廓」方向提示） | `../../v5_pyqt_2048_solver/screenshots/full_suggest.png` | YES | `full_suggest.png` | `{{IMG_09}}` | UPLOAD_REQUIRED |
| 10 | `05b_ai_workbench.md` | 自动连走（同样高亮本步方向） | `../../v5_pyqt_2048_solver/screenshots/full_auto.png` | YES | `full_auto.png` | `{{IMG_10}}` | UPLOAD_REQUIRED |
| 11 | `05b_ai_workbench.md` | 结果对比 | `../../v5_pyqt_2048_solver/screenshots/full_results.png` | YES | `full_results.png` | `{{IMG_11}}` | UPLOAD_REQUIRED |
| 12 | `06a_backends_benchmarks.md` | 开始页 | `../../v6_pyqt_2048_accelerated/screenshots/full_start.png` | YES | `full_start.png` | `{{IMG_12}}` | UPLOAD_REQUIRED |
| 13 | `06a_backends_benchmarks.md` | 游戏页（展开态：左游戏台 + 右 AI 求解工作台） | `../../v6_pyqt_2048_accelerated/screenshots/full_solver.png` | YES | `full_solver.png` | `{{IMG_13}}` | UPLOAD_REQUIRED |
| 14 | `06a_backends_benchmarks.md` | 折叠态（贴边半胶囊把手） | `../../v6_pyqt_2048_accelerated/screenshots/full_collapsed.png` | YES | `full_collapsed.png` | `{{IMG_14}}` | UPLOAD_REQUIRED |
| 15 | `06a_backends_benchmarks.md` | 单步建议（原生边框内的方向提示） | `../../v6_pyqt_2048_accelerated/screenshots/full_suggest.png` | YES | `full_suggest.png` | `{{IMG_15}}` | UPLOAD_REQUIRED |
| 16 | `06a_backends_benchmarks.md` | 自动连走（同样高亮本步方向） | `../../v6_pyqt_2048_accelerated/screenshots/full_auto.png` | YES | `full_auto.png` | `{{IMG_16}}` | UPLOAD_REQUIRED |
| 17 | `06b_headless_process.md` | 游戏页（展开态：左游戏台 + 右 AI 运行控制） | `../../v6_pyqt_2048_accelerated/screenshots/full_solver.png` | YES | `full_solver.png` | `{{IMG_17}}` | UPLOAD_REQUIRED |
| 18 | `06b_headless_process.md` | 自动连走（本机快速/标准执行） | `../../v6_pyqt_2048_accelerated/screenshots/full_auto.png` | YES | `full_auto.png` | `{{IMG_18}}` | UPLOAD_REQUIRED |
| 19 | `06b_headless_process.md` | 后台求解运行中（真实 Worker，200+ 步） | `../../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p4_background_running_200plus.png` | YES | `p4_background_running_200plus.png` | `{{IMG_19}}` | UPLOAD_REQUIRED |
| 20 | `06b_headless_process.md` | 后台暂停（FINAL 已采纳并持久化） | `../../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p5_background_paused.png` | YES | `p5_background_paused.png` | `{{IMG_20}}` | UPLOAD_REQUIRED |
| 21 | `06c_cross_mode_handoff.md` | 已暂停并选择快速：主按钮变为“切换至快速模式并继续” | `../../v6_pyqt_2048_accelerated/screenshots/full_handoff_paused.png` | YES | `full_handoff_paused.png` | `{{IMG_21}}` | UPLOAD_REQUIRED |
| 22 | `06c_cross_mode_handoff.md` | 交接中：主按钮“正在切换至后台求解模式…”，操作禁用 | `../../v6_pyqt_2048_accelerated/screenshots/full_handoff_switching.png` | YES | `full_handoff_switching.png` | `{{IMG_22}}` | UPLOAD_REQUIRED |
| 23 | `06c_cross_mode_handoff.md` | 后台暂停并选择标准：可安全切回本机 | `../../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p6_background_paused_selected_standard.png` | YES | `p6_background_paused_selected_standard.png` | `{{IMG_23}}` | UPLOAD_REQUIRED |
| 24 | `06c_cross_mode_handoff.md` | 后台退出、所有权释放后由标准模式继续 | `../../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p7_standard_running_after_background.png` | YES | `p7_standard_running_after_background.png` | `{{IMG_24}}` | UPLOAD_REQUIRED |

共 24 张图片。全部文件存在；因没有真实 CSDN 上传结果，CSDN 链接一律留空并标记 `UPLOAD_REQUIRED`，禁止伪造 CDN 地址。`{{IMG_nn}}` 只是发布时的定位占位符，**不要**原样发布到 CSDN。

## 2 图片说明

- 第 1、2 篇没有图片；其余七篇使用仓库内真实截图。
- V3/V4/V5 截图为各版本 `screenshots/full_*.png`；V6 另含 `experiments/v6_2/20261020_cross_mode_handoff/` 下的真实 E2E 阶段图。
- 截图门禁口径：`CAPTURE / STRUCTURE / TEXT` 可自动判定，`VISUAL_PASS` 需人工核对；未核对不写 PASS。
- 上传后在 CSDN 编辑器中逐张替换本地路径即可；alt 文本已写成可直接使用的图注。

## 3 公式结构统计

| 文章 | 块级公式（`$$` 对） | 行内公式 | 使用构造 |
| --- | ---: | ---: | --- |
| `01_console_math.md` | 36 | 30 | bmatrix, cases, sum, times |
| `02_history_recovery.md` | 0 | 0 | — |
| `03_pyqt_mvc_undo.md` | 0 | 0 | — |
| `04_animation_render.md` | 0 | 0 | — |
| `05a_solver_algorithms.md` | 19 | 163 | cases, argmax, sum, frac, times |
| `05b_ai_workbench.md` | 3 | 42 | lfloor, sum, times |
| `06a_backends_benchmarks.md` | 0 | 0 | sum |
| `06b_headless_process.md` | 0 | 0 | sum |
| `06c_cross_mode_handoff.md` | 0 | 0 | sum |

## 4 CSDN 公式渲染检查

检查项：
- 定界符成对：`$$` 数量为偶数；行内 `$...$` 未跨行。
- 复杂构造：`\begin{bmatrix}`、`\begin{cases}`、`\arg\max`、`\lfloor`、`\sum`、`\frac`。
- 表格内公式：`|` 已转义或避免出现在公式中，防止 Markdown 表格截断。
- 代码围栏不包含未转义的 `$`，避免被误判为公式。

结论：静态结构检查通过；**CSDN 在线渲染结果 `UNVERIFIED`**（本次无 CSDN 预览环境）。建议发布前在 CSDN 编辑器逐篇预览以下高风险构造：
- 第 1 篇的矩阵与分段函数；
- 第 5a 篇的 Expectimax/UCT 递推与 `\arg\max`；
- 第 6c 篇的 Markdown 表格与状态机代码块混排。

## 5 链接检查

- 相对链接（上一篇/下一篇/系列导航）按 `articles/` 目录解析，目标为 `blog/` 下的中文文件名；在本地仓库可点击。
- 发布到 CSDN 时，相对链接不会生效，需要替换为已发布文章的真实 URL；未发布前保留为本地链接并在系列报告中登记占位。
- 本报告不生成任何未经验证的外链。
