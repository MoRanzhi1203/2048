# 第二轮 CSDN 发布检查清单

## 1 文件与格式

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 九篇文件 | PASS | `second_pass/articles/` 下 9 个 ASCII 文件，全部非空 |
| H1 | PASS | 每篇恰好 1 个 H1（排除代码块内 `#` 注释） |
| 代码围栏 | PASS | 每篇围栏数量为偶数，语言标识保留 |
| 公式 | PASS（结构） | `$$` 成对：01=35 对、05a=19 对、05b=3 对，其余 0；CSDN 在线渲染 `UNVERIFIED` |
| 图片引用 | PASS（本地） | 24 张，全部在真实项目中存在，且全部位于正文对应小节；CSDN 上传 `UPLOAD_REQUIRED` |
| 图片位置 | PASS | `## 附：整窗截图` 0 处；每图有说明；详见 `06_image_position_check.md` |
| 公式排版 | PARTIAL | 对齐/拆分/符号表完成；CSDN 渲染 `UNVERIFIED`；详见 `07_formula_typesetting_check.md` |
| 上下篇链接 | PASS（本地） | 已按 `second_pass/articles/` 层级改为 `../../../blog/...` |
| 术语 | PASS | V5“运行方式=强度”与 V6“三档运行”已分开说明 |
| 6b 500/1000 | PASS | 以 500ms 为当前发布值，1000ms 标为已被取代的设计目标 |

## 2 图片分布与发布状态

| 文章 | 图片数 | 本地检查 | CSDN 状态 |
| --- | ---: | --- | --- |
| 01_console_math | 0 | — | — |
| 02_history_recovery | 0 | — | — |
| 03_pyqt_mvc_undo | 2 | 存在 | UPLOAD_REQUIRED |
| 04_animation_render | 3 | 存在 | UPLOAD_REQUIRED |
| 05a_solver_algorithms | 0 | — | — |
| 05b_ai_workbench | 6 | 存在 | UPLOAD_REQUIRED |
| 06a_backends_benchmarks | 5 | 存在 | UPLOAD_REQUIRED |
| 06b_headless_process | 4 | 存在 | UPLOAD_REQUIRED |
| 06c_cross_mode_handoff | 4 | 存在 | UPLOAD_REQUIRED |
| **合计** | **24** | 全部存在 | 待上传 |

逐图映射（本地路径、alt、建议文件名、`{{IMG_nn}}` 占位符）见第一轮 `../03_image_and_formula_audit.md`；第二轮未新增或替换任何图片，已将全部图片从文末汇总区移回正文对应小节，不写入伪造的 CSDN CDN 地址。具体位置见 `06_image_position_check.md`。

发布时：

1. 在 CSDN 编辑器上传对应图片；
2. 用真实 URL 替换 Markdown 中的相对路径；
3. 删除 `{{IMG_nn}}` 这类仅用于定位的占位符，不原样发布。

## 3 标题、标签与摘要

| 文章 | 建议标题 | 7 个标签 | 精简摘要 |
| --- | --- | --- | --- |
| 01 | 从零实现 2048（一）：数学模型与控制台版 Python 实现 | Python、2048、游戏开发、控制台、数据结构、算法入门、单元测试 | 用状态矩阵、合并算子与随机生成实现可运行的控制台 2048，并给出计分与终止条件的精确口径。 |
| 02 | 从零实现 2048（二）：CSV/JSON 历史、原子存档与断点续玩 | Python、2048、数据持久化、JSON、CSV、断点续玩、存档 | 以 `safe_store` 为例说明 CSV/JSON 的原子写、备份回退、活档管理与跨文件一致性边界。 |
| 03 | 从零实现 2048（三）：PyQt5 + MVC、撤销重做与高 DPI | PyQt5、2048、MVC、桌面应用、撤销重做、QWidget、高DPI | 用 MVC 把规则与渲染解耦，以状态快照实现撤销/重做，并处理焦点与高 DPI。 |
| 04 | 从零实现 2048（四）：QPainter 平滑动画、粒子与渲染优化 | PyQt5、2048、动画、QPainter、QTimer、性能优化、粒子效果 | 记录每步过渡信息，用静态背景缓存 + 双阶段插值实现平滑动画，并说明时间轴与帧率边界。 |
| 05a | 从零实现 2048（五上）：启发式、Rollout、Expectimax、MCTS 与 RL | 2048、算法、Expectimax、MCTS、强化学习、启发式搜索、Python | 逐类给出五类求解策略的递推、代码与预算，并区分计算成本、搜索质量与训练/推理。 |
| 05b | 从零实现 2048（五下）：双栏 AI 工作台、QThread 并发与方向提示 | PyQt5、2048、QThread、并发编程、AI求解、交互设计、事件过滤器 | 把求解内核嵌入双栏工作台：任务身份、快照校验、停止语义、方向键路由与边框内提示。 |
| 06a | 从零实现 2048（六上）：NumPy/Numba/C++ Bitboard 与公平基准 | 2048、PyQt5、C++扩展、pybind11、NumPy、Numba、性能基准 | 四个后端共用一套协议，位棋盘显式处理溢出，并用分层基准区分原语、搜索与对局质量。 |
| 06b | 从零实现 2048（六中）：无头 Worker、所有权与 500ms 回传 | 2048、Python、多进程、Headless、进程通信、断点恢复、性能优化 | 用无 Qt Worker 接管后台求解：IPC、所有权、检查点、500ms 回传、FINAL 回放与暂停恢复。 |
| 06c | 从零实现 2048（六下）：跨模式安全交接与状态一致性 | 2048、状态机、并发控制、数据一致性、PyQt5、跨进程、工程质量 | 用一个状态机管理三档运行方式，解决暂停后跨模式继续、单一写者与数据一致性。 |

## 4 待替换清单

| 项 | 数量 | 处理 |
| --- | ---: | --- |
| 图片相对路径 | 24 | 上传后替换为真实 CSDN URL |
| 上下篇/系列链接 | 九篇文末 | 文章发布后替换为真实 URL；未发布前保留本地链接 |
| 公式在线渲染 | 3 篇含公式 | 发布前在 CSDN 编辑器逐篇预览 |
| 代码高亮语言 | 全部代码块 | 已标注 `python/text/json/csv/css/bash` 等 |

## 5 发布顺序

01 → 02 → 03 → 04 → 05a → 05b → 06a → 06b → 06c。每篇发布后回填上一篇/下一篇 URL；06b 的 500ms 说明不要删改，它是当前源码口径。

## 6 未验证事项

- CSDN 在线预览不可用：公式/表格渲染 `UNVERIFIED`。
- 24 张图片尚未上传：URL `UPLOAD_REQUIRED`。
- 第 3 篇 V3 高 DPI、第 4 篇实际帧率、第 5b 篇提示层像素、第 5a 篇 `8.5e-14`、第 6b 篇 111s 原始日志均为 `HISTORICAL/UNVERIFIED`，发布时不要改写成“本次实测”。
