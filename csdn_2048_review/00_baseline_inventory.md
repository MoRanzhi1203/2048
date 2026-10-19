# 00 基线盘点（P0）

- 盘点时间：2026-10-20
- 工作区：`E:\PyQt5_demo\2048`
- 输入：`blog/` 下九篇 Markdown 原文（只读）
- 文件名说明：任务清单中的第 1–5 篇带有 `(1)` 后缀；当前工作区的实际文件**没有** `(1)`。按篇名精确匹配到 `blog/` 下的实际文件，路径与哈希见下表；未做重命名。
- 输出：`csdn_2048_review/articles/` 九篇完整修订稿（ASCII 文件名）
- 原始文件在修订前后均计算 SHA-256，见下表；本报告不修改原文。

## 1 九篇输入清单与哈希

| # | ASCII 输出名 | 原始文件名 | 行数 | 字节 | SHA-256（原文） |
| ---: | --- | --- | ---: | ---: | --- |
| 1 | `01_console_math.md` | `第1篇 · Python 实现：从数学模型到完整控制台版《2048》游戏.md` | 714 | 18645 | `235eb61e81b7bc82261066d27116e2a6e503fb502be458f44c922e9c7ff4e7b6` |
| 2 | `02_history_recovery.md` | `第2篇 · 如何实现带历史记录功能的控制台2048游戏.md` | 501 | 19469 | `7cd06d6ff0966e56e9a0c0d48f9cc9339110d6a8f5af59e677d37783156a024d` |
| 3 | `03_pyqt_mvc_undo.md` | `第3篇 · 使用 PyQt5 实现 2048 桌面版游戏：MVC 架构与撤销和重做.md` | 481 | 21604 | `29e8c1e7987647c0ee91eca0636b21ce0f03e32bab7e87ef0c5e4e629e35f034` |
| 4 | `04_animation_render.md` | `第4篇 · 使用 PyQt5 实现 2048：平滑动画与性能优化.md` | 358 | 16301 | `26373fbd07d279e5b44d63af667c955acdc764e3e9c021991d707b378d2436e7` |
| 5 | `05a_solver_algorithms.md` | `第5篇（上）· 使用 PyQt5 实现 2048 算法求解版：五类搜索算法内核.md` | 624 | 33848 | `423be681a5d3277eff06c0a24c58a2306e52e18a75f23e70e37fe9f0d2ccc3d9` |
| 6 | `05b_ai_workbench.md` | `第5篇（下）· 使用 PyQt5 实现 2048 算法求解版：双栏 AI 求解工作台与交互.md` | 557 | 36544 | `0238cc7217c40853d56813c466e6c1477582338aad2b2807f9d4b8dfbc6f412b` |
| 7 | `06a_backends_benchmarks.md` | `第6篇（上）· 使用 PyQt5 实现 2048 高性能计算版：四类计算后端与公平基准.md` | 323 | 20055 | `f3070baf4692039c219568b164628c3ac4ebb15590dad002d121af0954271713` |
| 8 | `06b_headless_process.md` | `第6篇（中）· 使用 PyQt5 实现 2048 高性能计算版：无头后台求解与三档运行模式.md` | 366 | 19309 | `4c299fc6e5b164c58d11fee28a3d40920cce795e5c2a0edb8c7fa07e2ae76ef3` |
| 9 | `06c_cross_mode_handoff.md` | `第6篇（下）· 使用 PyQt5 实现 2048 高性能计算版：统一运行控制与跨模式安全交接.md` | 419 | 20459 | `c36463efa6950f45201109e1ec49fa3fa3f9d54eb2fb999cfe7dd46e7df03d6b` |

## 2 结构统计

| ASCII | H1–H4 标题数 | 代码围栏 | 围栏语言 | 数学块（块级/行内） | 图片 | 相对链接 |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| `01_console_math` | 38 | 8 | python, txt | 36 / 12 | 0 | 1 |
| `02_history_recovery` | 8 | 5 | python | 0 / 0 | 0 | 1 |
| `03_pyqt_mvc_undo` | 29 | 14 | bash, css, python, txt | 0 / 0 | 2 | 2 |
| `04_animation_render` | 13 | 14 | bash, python | 0 / 0 | 3 | 1 |
| `05a_solver_algorithms` | 22 | 19 | python | 19 / 157 | 0 | 2 |
| `05b_ai_workbench` | 19 | 21 | bash, python | 3 / 42 | 6 | 2 |
| `06a_backends_benchmarks` | 17 | 6 | python | 0 / 0 | 5 | 2 |
| `06b_headless_process` | 15 | 9 | json, python | 0 / 0 | 4 | 2 |
| `06c_cross_mode_handoff` | 18 | 10 | json, python | 0 / 0 | 4 | 9 |

## 3 标题树（原文）

### `01_console_math`

第1篇 · Python 实现：从数学模型到完整控制台版《2048》游戏（L1）
  1 模块 1：状态表示与初始化（L23）
    1.1 模块 1 - 数学模型（L25）
      1.1.1 状态矩阵定义（L27）
      1.1.2 游戏全局状态（L47）
      1.1.3 随机生成新方块（L60）
    1.2 模块 1 - 代码实现（L81）
    1.3 模块 1 - 逻辑说明（L118）
    1.4 初始状态可视化示例（L132）
  2 模块 2：方块移动与合并（L149）
    2.1 模块 2 - 数学模型（L151）
      2.1.1 单行压缩与合并（L153）
      2.1.2 四个方向的移动矩阵（L177）
    2.2 模块 2 - 代码实现（L201）
    2.3 模块 2 - 逻辑说明（L260）
    2.4 示意矩阵变化（L268）
  3 模块 3：胜负判断与游戏结束检测（L294）
    3.1 模块 3 - 数学模型（L296）
      3.1.1 胜利条件（L298）
      3.1.2 游戏结束条件（L310）
      3.1.3 重置游戏（L330）
    3.2 模块 3 - 代码实现（L350）
    3.3 模块 3 - 逻辑说明（L394）
  4 模块 4：控制台显示与用户界面（L412）
    4.1 模块 4 - 数学模型（L414）
      4.1.1 棋盘显示矩阵（L416）
      4.1.2 操作与状态提示（L433）
    4.2 模块 4 - 代码实现（L463）
    4.3 模块 4 - 逻辑说明（L496）
    4.4 界面设计（L513）
  5 模块 5：主循环与用户交互（L542）
    5.1 游戏主循环（L544）
    5.2 模块 5 - 代码实现（L566）
    5.3 模块 5 - 逻辑说明（L612）
  6 模块 6：程序入口与启动（L623）
    6.1 模块 6 - 代码实现（L625）
    6.2 模块 6 - 逻辑说明（L679）
  7 小结（L689）

### `02_history_recovery`

第2篇 · 如何实现带历史记录功能的控制台2048游戏（L1）
  1 游戏历史记录管理（L15）
  2 游戏状态保存与加载（L140）
  3 游戏历史记录查看与管理（L222）
  4 游戏退出与数据更新（L282）
  5 启动续玩与主循环（L347）
  6 示例文件内容（L427）
  7 小结（L492）

### `03_pyqt_mvc_undo`

第3篇 · 使用 PyQt5 实现 2048 桌面版游戏：MVC 架构与撤销和重做（L1）
  1 为什么需要 MVC（L11）
  2 Model：与原版无异的游戏核心（L27）
    2.1 关键点（L31）
    2.2 代码实现（合并核心）（L37）
    2.3 方向抽象（L63）
  3 View：用 QGridLayout + QLabel 绘制棋盘（L88）
    3.1 关键点（L92）
    3.2 代码实现（方块渲染）（L98）
    3.3 界面效果（L190）
  4 Controller：键盘事件与按钮（L211）
    4.1 关键点（L215）
    4.2 键盘事件（L221）
    4.3 状态刷新（L256）
  5 撤销和重做：基于状态快照栈（L291）
    5.1 关键点（L295）
    5.2 代码实现（L302）
  6 与历史记录功能打通（L362）
    6.1 启动页设计（L364）
  7 界面视觉规范与高 DPI 适配（L376）
    7.1 把样式收敛成常量（L380）
    7.2 两个页面的布局与尺寸（L394）
    7.3 键盘可达：又踩了一次"方向键失效"（L401）
    7.4 高 DPI 适配（L424）
    7.5 界面截图（L435）
  8 运行说明（L445）
    8.1 环境依赖（L447）
    8.2 运行与操作（L453）
  9 小结（L466）

### `04_animation_render`

第4篇 · 使用 PyQt5 实现 2048：平滑动画与性能优化（L1）
  1 总思路：Model 不动，换掉 View（L11）
  2 Model：只补"过渡信息"（L30）
    2.1 逐行合并时输出"去向"（L34）
    2.2 覆盖 `_slide`：行内下标 → 棋盘坐标（L67）
  3 View：分层渲染 + 逐帧插值（L124）
    3.1 静态背景层：只画一次，缓存成 pixmap（L128）
    3.2 动画层：滑行 → 合并/新生（L151）
  4 Controller：输入节流与收尾（L223）
  5 性能要点（L301）
  6 运行与操作（L313）
  7 效果（L329）
  8 小结（L347）

### `05a_solver_algorithms`

第5篇（上）· 使用 PyQt5 实现 2048 算法求解版：五类搜索算法内核（L1）
  1 问题形式化（L11）
    1.1 状态、动作与转移（L13）
    1.2 即时奖励与终止（L35）
    1.3 符号约定（L43）
  2 系统结构与棋盘机制（L69）
    2.1 分层结构与纯逻辑约束（L71）
    2.2 移动与合并算子（L103）
  3 启发式评估函数（L132）
    3.1 线性评估模型（L134）
    3.2 各特征的定义（L166）
    3.3 实现与对应（L203）
  4 五类求解策略（L303）
    4.1 启发式：单步贪心（L317）
    4.2 贪心模拟：rollout（L350）
    4.3 Expectimax：对随机出块求期望（L413）
    4.4 MCTS：树结构与渐进加宽（L480）
    4.5 强化学习：策略梯度（L542）
  5 正确性与工程边界（L599）
    5.1 验证方法（L601）
    5.2 可复现性、异常兜底与时间预算（L605）
  6 小结（L617）

### `05b_ai_workbench`

第5篇（下）· 使用 PyQt5 实现 2048 算法求解版：双栏 AI 求解工作台与交互（L1）
  1 并发模型与线程生命周期（L15）
  2 V5.1 界面：左右双栏「AI 求解工作台」（L100）
  3 折叠与贴边把手（L151）
  4 交互与工作流（L227）
    4.1 方向键的统一路由（L229）
    4.2 单步建议的常驻跟随（L268）
    4.3 求解进行中的算法热切换（L296）
  5 AI 方向提示：原生边框内的「内嵌明暗轮廓」+ 三通道流光（L323）
    5.1 需求与几何约束（L327）
    5.2 第一代方案：沿边暖白与背景的低对比（L351）
    5.3 第二代方案：三段式内嵌明暗轮廓（L363）
    5.4 光栅化约束：DestinationIn 与抗锯齿裁剪不可同时使用（L388）
    5.5 流光层：三通道、短梭形与朝目标边汇聚（L409）
    5.6 自动连走方向提示（L423）
  6 测试与验收（L429）
  7 性能与复杂度（L491）
  8 小结（L528）
  附：整窗截图（L545）

### `06a_backends_benchmarks`

第6篇（上）· 使用 PyQt5 实现 2048 高性能计算版：四类计算后端与公平基准（L1）
  1 为什么需要 V6：V5 的瓶颈在哪（L23）
  2 架构：一个调度器 + 四个后端（L43）
  3 统一后端协议：同一个棋盘，四种内部表示（L74）
  4 位棋盘：4-bit 指数编码与"溢出必须显式拒绝"（L96）
  5 选择与回退：不静默换算法（L117）
  6 等价性：逐位一致（L141）
  7 公平基准：把"同工作量"和"同墙钟"分开（L164）
    7.1 内核微基准（median 每单位耗时，µs，越小越好）（L173）
    7.2 同工作量搜索（median 每决策耗时）（L197）
    7.3 同墙钟预算小样本（工程回归，不作为显著性结论）（L208）
    7.4 一个可选的原生 rollout（L226）
  8 默认后端：用证据选 `cpp`（L232）
  9 GUI 与数据：怎么在不动 V5 的前提下换心脏（L246）
  10 门禁与验收边界（L265）
  11 小结（L292）
  附：整窗截图（L309）

### `06b_headless_process`

第6篇（中）· 使用 PyQt5 实现 2048 高性能计算版：无头后台求解与三档运行模式（L1）
  1 为什么把求解搬出 GUI（L15）
  2 三档运行方式：先定语义，再谈实现（L33）
  3 无头核心：不导入任何 Qt（L63）
  4 进程协议：一行一个 JSON（L101）
  5 所有权：单一写者不是口头约定（L139）
  6 检查点：每步可恢复，而不是"最后存一次"（L169）
  7 500ms 回传：固定周期，单一来源（L200）
  8 FINAL 采纳：不是覆盖棋盘，而是回放历史（L222）
  9 状态机：把"正在暂停"和"已暂停"分开（L258）
  10 启动期恢复：GUI 重启之后（L288）
  11 踩过的坑（工程复盘）（L300）
  12 验收与边界（L315）
  13 小结（L336）
  附：整窗截图（L355）

### `06c_cross_mode_handoff`

第6篇（下）· 使用 PyQt5 实现 2048 高性能计算版：统一运行控制与跨模式安全交接（L1）
  1 问题：三种执行模式带来的"状态爆炸"（L15）
  2 三个状态变量与"真实执行模式"（L35）
  3 交互语义：一张矩阵说清（L80）
  4 运行中切选项卡：非破坏性（L104）
  5 安全步边界暂停（L124）
  6 跨模式交接：三条路径（L150）
    6.1 标准 ↔ 快速：同一会话，换调度（L154）
    6.2 本机 → 后台：先确认接管，再结束本机（L180）
    6.3 后台 → 本机：等旧写者真正退出（L202）
  7 单一写者：为什么"进程起来了"不等于"接管了"（L231）
  8 数据一致性：四个"不许变"（L275）
  9 失败与回退：保留可恢复的暂停（L302）
  10 真实 GUI E2E：22 项检查（L315）
  11 测试矩阵：8 种暂停切换 + 4 项扩展（L333）
  12 门禁与未验证项（L360）
  13 小结（L379）
  附：整窗截图（L408）


## 4 图片引用与目标存在性

| ASCII | alt | 目标 | 本地存在 | 备注 |
| --- | --- | --- | --- | --- |
| `03_pyqt_mvc_undo` | 启动页 | `../v3_pyqt_2048/screenshots/full_start.png` | YES | 需上传 CSDN 或保留本地路径 |
| `03_pyqt_mvc_undo` | 游戏页 | `../v3_pyqt_2048/screenshots/full_game.png` | YES | 需上传 CSDN 或保留本地路径 |
| `04_animation_render` | 启动页 | `../v4_pyqt_2048_animated/screenshots/full_start.png` | YES | 需上传 CSDN 或保留本地路径 |
| `04_animation_render` | 合并粒子 | `../v4_pyqt_2048_animated/screenshots/full_merge.png` | YES | 需上传 CSDN 或保留本地路径 |
| `04_animation_render` | 游戏页 | `../v4_pyqt_2048_animated/screenshots/full_game.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 开始页 | `../v5_pyqt_2048_solver/screenshots/full_start.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 游戏页（展开态：左侧游戏台 + 右侧 AI 求解工作台） | `../v5_pyqt_2048_solver/screenshots/full_solver.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 折叠态（整体隐藏右栏，右侧贴边半胶囊把手） | `../v5_pyqt_2048_solver/screenshots/full_collapsed.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 单步建议（棋盘原生边框内的「内嵌明暗轮廓」方向提示） | `../v5_pyqt_2048_solver/screenshots/full_suggest.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 自动连走（同样高亮本步方向） | `../v5_pyqt_2048_solver/screenshots/full_auto.png` | YES | 需上传 CSDN 或保留本地路径 |
| `05b_ai_workbench` | 结果对比 | `../v5_pyqt_2048_solver/screenshots/full_results.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06a_backends_benchmarks` | 开始页 | `../v6_pyqt_2048_accelerated/screenshots/full_start.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06a_backends_benchmarks` | 游戏页（展开态：左游戏台 + 右 AI 求解工作台） | `../v6_pyqt_2048_accelerated/screenshots/full_solver.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06a_backends_benchmarks` | 折叠态（贴边半胶囊把手） | `../v6_pyqt_2048_accelerated/screenshots/full_collapsed.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06a_backends_benchmarks` | 单步建议（原生边框内的方向提示） | `../v6_pyqt_2048_accelerated/screenshots/full_suggest.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06a_backends_benchmarks` | 自动连走（同样高亮本步方向） | `../v6_pyqt_2048_accelerated/screenshots/full_auto.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06b_headless_process` | 游戏页（展开态：左游戏台 + 右 AI 运行控制） | `../v6_pyqt_2048_accelerated/screenshots/full_solver.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06b_headless_process` | 自动连走（本机快速/标准执行） | `../v6_pyqt_2048_accelerated/screenshots/full_auto.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06b_headless_process` | 后台求解运行中（真实 Worker，200+ 步） | `../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p4_background_running_200plus.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06b_headless_process` | 后台暂停（FINAL 已采纳并持久化） | `../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p5_background_paused.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06c_cross_mode_handoff` | 已暂停并选择快速：主按钮变为“切换至快速模式并继续” | `../v6_pyqt_2048_accelerated/screenshots/full_handoff_paused.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06c_cross_mode_handoff` | 交接中：主按钮“正在切换至后台求解模式…”，操作禁用 | `../v6_pyqt_2048_accelerated/screenshots/full_handoff_switching.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06c_cross_mode_handoff` | 后台暂停并选择标准：可安全切回本机 | `../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p6_background_paused_selected_standard.png` | YES | 需上传 CSDN 或保留本地路径 |
| `06c_cross_mode_handoff` | 后台退出、所有权释放后由标准模式继续 | `../v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/p7_standard_running_after_background.png` | YES | 需上传 CSDN 或保留本地路径 |

共 24 个图片引用。所有目标均按真实项目路径检查，未发现缺失。

## 5 外链与相对链接

| ASCII | 类型 | 文本 | 目标 | 存在 |
| --- | --- | --- | --- | --- |
| `01_console_math` | 相对 | 第 2 篇 · 如何实现带历史记录功能的控制台2048游戏 | `第2篇%20·%20如何实现带历史记录功能的控制台2048游戏.md` | YES |
| `02_history_recovery` | 相对 | 第 1 篇 · Python 实现：从数学模型到完整控制台版《2048》游戏 | `第1篇%20·%20Python%20实现：从数学模型到完整控制台版《2048》游戏.md` | YES |
| `03_pyqt_mvc_undo` | 相对 | 第 2 篇 · 如何实现带历史记录功能的控制台2048游戏 | `第2篇%20·%20如何实现带历史记录功能的控制台2048游戏.md` | YES |
| `03_pyqt_mvc_undo` | 相对 | 第 4 篇 · 使用 PyQt5 实现 2048：平滑动画与性能优化 | `第4篇%20·%20使用%20PyQt5%20实现%202048：平滑动画与性能优化.md` | YES |
| `04_animation_render` | 相对 | 第 3 篇 · 使用 PyQt5 实现 2048 桌面版游戏：MVC 架构与撤销和重做 | `第3篇%20·%20使用%20PyQt5%20实现%202048%20桌面版游戏：MVC%20架构与撤销和重做.md` | YES |
| `05a_solver_algorithms` | 相对 | 第 4 篇 · 使用 PyQt5 实现 2048：平滑动画与性能优化 | `第4篇%20·%20使用%20PyQt5%20实现%202048：平滑动画与性能优化.md` | YES |
| `05a_solver_algorithms` | 相对 | 第 5 篇（下）· 使用 PyQt5 实现 2048 算法求解版：双栏 AI 求解工作台与交互 | `第5篇（下）·%20使用%20PyQt5%20实现%202048%20算法求解版：双栏%20AI%20求解工作台与交互.md` | YES |
| `05b_ai_workbench` | 相对 | 第 5 篇（上）· 使用 PyQt5 实现 2048 算法求解版：五类搜索算法内核 | `第5篇（上）·%20使用%20PyQt5%20实现%202048%20算法求解版：五类搜索算法内核.md` | YES |
| `05b_ai_workbench` | 相对 | 第 6 篇（上）· 使用 PyQt5 实现 2048 高性能计算版：四类计算后端与公平基准 | `第6篇（上）·%20使用%20PyQt5%20实现%202048%20高性能计算版：四类计算后端与公平基准.md` | YES |
| `06a_backends_benchmarks` | 相对 | 第 5 篇（下）· 使用 PyQt5 实现 2048 算法求解版：双栏 AI 求解工作台与交互 | `第5篇（下）·%20使用%20PyQt5%20实现%202048%20算法求解版：双栏%20AI%20求解工作台与交互.md` | YES |
| `06a_backends_benchmarks` | 相对 | 第 6 篇（中）· 使用 PyQt5 实现 2048 高性能计算版：无头后台求解与三档运行模式 | `第6篇（中）·%20使用%20PyQt5%20实现%202048%20高性能计算版：无头后台求解与三档运行模式.md` | YES |
| `06b_headless_process` | 相对 | 第 6 篇（上）· 使用 PyQt5 实现 2048 高性能计算版：四类计算后端与公平基准 | `第6篇（上）·%20使用%20PyQt5%20实现%202048%20高性能计算版：四类计算后端与公平基准.md` | YES |
| `06b_headless_process` | 相对 | 第 6 篇（下）· 使用 PyQt5 实现 2048 高性能计算版：统一运行控制与跨模式安全交接 | `第6篇（下）·%20使用%20PyQt5%20实现%202048%20高性能计算版：统一运行控制与跨模式安全交接.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 6 篇（中）· 使用 PyQt5 实现 2048 高性能计算版：无头后台求解与三档运行模式 | `第6篇（中）·%20使用%20PyQt5%20实现%202048%20高性能计算版：无头后台求解与三档运行模式.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 1 篇 | `第1篇%20·%20Python%20实现：从数学模型到完整控制台版《2048》游戏.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 2 篇 | `第2篇%20·%20如何实现带历史记录功能的控制台2048游戏.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 3 篇 | `第3篇%20·%20使用%20PyQt5%20实现%202048%20桌面版游戏：MVC%20架构与撤销和重做.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 4 篇 | `第4篇%20·%20使用%20PyQt5%20实现%202048：平滑动画与性能优化.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 5 篇（上） | `第5篇（上）·%20使用%20PyQt5%20实现%202048%20算法求解版：五类搜索算法内核.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 5 篇（下） | `第5篇（下）·%20使用%20PyQt5%20实现%202048%20算法求解版：双栏%20AI%20求解工作台与交互.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 6 篇（上） | `第6篇（上）·%20使用%20PyQt5%20实现%202048%20高性能计算版：四类计算后端与公平基准.md` | YES |
| `06c_cross_mode_handoff` | 相对 | 第 6 篇（中） | `第6篇（中）·%20使用%20PyQt5%20实现%202048%20高性能计算版：无头后台求解与三档运行模式.md` | YES |

外部链接：无。

## 6 实际核对的源码与证据

| 版本 | 关键源码 | 用途 |
| --- | --- | --- |
| V1 | `v1_console_2048/v1_console_2048.py` | 合并、随机生成、胜负判定、控制台输入 |
| V2 | `v2_console_2048_with_history/v2_console_2048_with_history.py`、`safe_store.py` | CSV/JSON 存档、索引、原子写与回滚 |
| V3 | `v3_pyqt_2048/v3_pyqt_2048_with_history.py` | GameCore、快照撤销、434×434 几何 |
| V4 | `v4_pyqt_2048_animated/v4_pyqt_2048_animated.py` | 过渡信息、双阶段动画、粒子层 |
| V5 | `v5_pyqt_2048_solver/solver_2048.py`、`v5_pyqt_2048_solver.py`、`rl_2048.py` | 五策略、QThread、方向键路由、提示层 |
| V6 | `v6_pyqt_2048_accelerated/*`、`headless/*`、`solver_backends/*` | 四后端、无头 Worker、所有权、运行状态机 |

实验证据：
- `experiments/report.md`：RL 模型验证集 2267.4 / 旧模型 1445.7
- `v5_pyqt_2048_solver/功能说明.md`：梯度偏差 ≈3e-8、模型加载 cold/warm
- `v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/cross_mode_e2e.json`：22/22 E2E
- `v6_pyqt_2048_accelerated/benchmarks/reports/`：微基准/搜索/同墙钟原始 CSV/JSON

## 7 建议发布顺序

1. `01_console_math.md`
2. `02_history_recovery.md`
3. `03_pyqt_mvc_undo.md`
4. `04_animation_render.md`
5. `05a_solver_algorithms.md`
6. `05b_ai_workbench.md`
7. `06a_backends_benchmarks.md`
8. `06b_headless_process.md`
9. `06c_cross_mode_handoff.md`

## 8 缺失与阻断

- 九篇输入全部找到；无 BLOCKED。
- 交付前未发现缺失图片或断链。
- CSDN 在线预览不可用，公式渲染标记 UNVERIFIED。
