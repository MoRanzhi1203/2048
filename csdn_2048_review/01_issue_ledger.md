# 01 问题台账（P1 技术事实核查 + P2/P3 编辑与发布适配）

- 台账基准：`blog/` 下九篇原文（只读），行号指原文。
- 证据：V1–V6 实际源码、`safe_store.py`、`benchmarks/reports/summary.md`、`experiments/report.md`、`cross_mode_e2e.json`、本次复跑测试输出。
- 状态：`FIXED` = 已在 `articles/*.md` 修订；`VERIFIED` = 原文正确、已复核；`HISTORICAL` = 保留历史测量但标注不可复现；`UNVERIFIED` = 无法在当前工作区验证。

## 1 按文章汇总

| 文章 | P0 | P1 | P2 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 01_console_math | 2 | 4 | 3 | 9 |
| 02_history_recovery | 3 | 4 | 3 | 10 |
| 03_pyqt_mvc_undo | 0 | 3 | 5 | 8 |
| 04_animation_render | 2 | 2 | 2 | 6 |
| 05a_solver_algorithms | 0 | 5 | 2 | 7 |
| 05b_ai_workbench | 1 | 3 | 2 | 6 |
| 06a_backends_benchmarks | 0 | 2 | 2 | 4 |
| 06b_headless_process | 1 | 3 | 2 | 6 |
| 06c_cross_mode_handoff | 0 | 2 | 2 | 4 |
| 跨文章 | 0 | 4 | 1 | 5 |
| **合计** | **9** | **32** | **24** | **65** |

## 2 逐项台账

| ID | 文章 | 位置 | 原文摘录 | 问题类型 | 证据 | 级别 | 修订/处理 | 验证 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1-01 | 01 | 文末系列导航 | “本篇是系列第 1 篇（共 7 篇）” | 事实/导航 | 实际为 6 篇、9 个文件（第 5/6 篇分上中下） | P1 | 改为“系列共 6 篇、9 个文件” | 全系列文件计数 | FIXED |
| A1-02 | 01 | §2.1.1 合并规则 | “分数更新为 … ∑ 合并的方块 s_j” | 公式歧义 | V1 `_merge_line`；`solver_2048.move_grid` 实测 `[2,2,2,2]→gained=8`、`[2,0,2,4]→4`、`[2,4,8,16]→0` | P0 | 明确“只计合并产生的新方块”，补三行示例表 | 纯逻辑内核复跑，exit 0 | FIXED |
| A1-03 | 01 | §3.1.2 终止条件 | “∀i,j<4: s_{i,j}≠s_{i,j+1} 且 s_{j,i}≠s_{j+1,i}” | 索引越界/符号错误 | V1 `check_game_over` 的循环边界 | P0 | 拆成水平 j=1..3、垂直 i=1..3 两条公式 | 与源码逐行对照 | FIXED |
| A1-04 | 01 | 开头/导入 | 仅注释“Windows 键盘”，正文未声明平台 | 平台范围 | `msvcrt`、`cls`；`clear` 分支无对应输入实现 | P1 | 增加平台范围说明与移植要求 | 源码导入与调用路径 | FIXED |
| A1-05 | 01 | §3.1.3 | `S_0' = S_0 + P_1 + P_2` 未定义 P | 公式完整性 | V1 `add_new_tile` 两次 | P1 | 定义 P 为单非零元稀疏矩阵 | 逻辑核对 | FIXED |
| A1-06 | 01 | 全文 | “模块 1/数学模型/代码实现/逻辑说明”重复嵌套 | 结构/冗余 | 阅读节奏被切断 | P2 | 合并为 8 个主题节，删除重复小标题与分隔线 | 标题树复核 | FIXED |
| A1-07 | 01 | §1 代码块 | `def __init__` 无类上下文 | 可读性/可运行性 | 片段省略 class 行 | P2 | 明确“省略 class 行” | 阅读核对 | FIXED |
| A1-08 | 01 | §3.1 | “won”与“结束”未区分 | 语义 | V1 `check_win` 只置位，不终止 | P1 | 说明胜利提示可继续，真正终止是 game_over | 源码 | FIXED |
| A1-09 | 01 | §5/小结 | `best_score` 只在重置时更新 | 语义不完整 | V1 `run()` 每次成功移动后也做 max | P2 | 补充“整局单调不减” | 源码 | FIXED |
| A2-01 | 02 | §2 代码 | 正文声称原子写，片段用 `open(state_file,'w')+json.dump` | 技术事实错误 | V2 `save_game_state` 使用 `_store.atomic_write_json` + 有效主文件备份 | P0 | 整段替换为真实实现 | 源码逐行核对 | FIXED |
| A2-02 | 02 | §1 代码/正文 | “CSV 追加逐步轨迹”（直接 append） | 技术事实错误 | V2 `record_move` 累积 `history_rows` 后 `atomic_write_csv` 整文件替换 | P0 | 改为“逻辑逐步、物理原子重写”，说明写放大 | 源码 | FIXED |
| A2-03 | 02 | §2 正文 | 暗示恢复后逐位续玩 | 过度承诺 | `game_state.json` 无 RNG 状态 | P0 | 明确只恢复棋盘/分数，不保证后续随机序列 | 字段核对 | FIXED |
| A2-04 | 02 | 开头/§2 | “可靠存档”未限定跨文件事务 | 边界缺失 | JSON/CSV/index 各自原子，非同一事务 | P1 | 增加跨文件一致性限制 | `safe_store` 实现 | FIXED |
| A2-05 | 02 | §3 代码 | 只按 `is_completed` 选活档 | 幽灵档风险 | V2 `get_last_unfinished_game` 还要求状态文件存在 | P1 | 替换为带 `_has_state` 的实现 | 源码 | FIXED |
| A2-06 | 02 | §2 代码 | 直接 `json.load`，无校验/回退 | 可靠性 | V2 `load_json_validated` + `.bak` + 自愈 | P1 | 替换实现并说明 `.bak` 可能落后一步 | 源码 | FIXED |
| A2-07 | 02 | 多处 | 宽泛 `except ...: pass` | 可观测性 | V2 仅捕获 `OSError`；加载错误写入 `last_load_error` | P1 | 说明错误处理边界，避免“静默成功”叙事 | 源码 | FIXED |
| A2-08 | 02 | §5 `run()` | 退出未释放锁 | 生命周期 | V2 退出路径 `release_lock()` | P2 | 补入代码块 | 源码 | FIXED |
| A2-09 | 02 | §1 | “唯一 ID 基于时间戳” | 过度承诺 | 微秒时间戳，顺序单机足够，非 UUID 保证 | P2 | 改为“微秒级、非跨进程唯一保证” | 源码 | FIXED |
| A2-10 | 02 | §6 示例 | `game_state.json` 缺 schema/version/history_count | 示例与实现不一致 | `wrap_state()` 写入 schema/version；状态含 history_count | P2 | 补齐字段 | 源码 | FIXED |
| A3-01 | 03 | §5 快照 | 未说明快照不含 RNG | 过度承诺 | V3 `_snapshot()` 字段列表 | P1 | 增加“不保证后续随机序列”说明 | 源码 | FIXED |
| A3-02 | 03 | §7.4 | “100%/125%/150% 逐一断言” | 证据不足 | V3 无 DPI 截图/自动断言；V4 有 dpi 截图 | P1 | 改为适配建议，V3 标记 UNVERIFIED | 文件清单 | FIXED |
| A3-03 | 03 | §6.1 | “为后续第 7 篇准备样本” | 陈旧引用 | 系列为 6 篇 | P2 | 改为“后续训练/离线分析” | 系列结构 | FIXED |
| A3-04 | 03 | §4.1 | “在窗口层捕获按键更稳妥”（绝对化） | 表述绝对 | 第 5 篇改用应用内事件过滤器 | P2 | 改为“本项目选择”，说明替代方案 | 两版源码 | FIXED |
| A3-05 | 03 | §5 结尾 | 未说明撤销对最高分的影响 | 语义缺失 | `undo/redo` 调用 `_sync_best_score`，只升不降 | P1 | 增加单调性说明 | 源码 | FIXED |
| A3-06 | 03 | §2.1/§6 | “record_move 四列” | 事实核对 | V3 CSV 表头四列；每步写两行（移动 + 添加） | P2 | 保留并补充“两步写两行” | 源码 | VERIFIED |
| A3-07 | 03 | §1/§3 | MVC 职责、434×434 几何 | 事实核对 | V3 常量与 `refresh()` 实现 | P2 | 保留 | 源码 | VERIFIED |
| A3-08 | 03 | §7.5 截图 | 本地截图引用 | 资源 | 两个目标文件存在 | P2 | 保留，增加 CSDN 上传提示 | 文件检查 | VERIFIED |
| A4-01 | 04 | §3.2/§5 | “~60FPS”“固定 16ms（≈60FPS）” | 过度承诺 | `FRAME_INTERVAL=16` 只是目标 tick；`t += interval` 会漂移；无实测 FPS | P0 | 全文改为“16ms 目标 tick”，增加时间口径限制 | 源码 | FIXED |
| A4-02 | 04 | §8 小结 | “脏矩形”“局部重绘” | 技术事实错误 | `BoardView.update()` 重绘整个控件；无逐瓦片脏矩形 | P0 | 改为“整块棋盘重绘”，脏矩形列为未来方案 | 源码 | FIXED |
| A4-03 | 04 | §5 | “两个版本视觉完全一致” | 未验证 | 无逐像素比对 | P1 | 改为“使用同一套常量；未自动比对” | 证据清单 | FIXED |
| A4-04 | 04 | §8 | “Model 一行不改” | 表述易误解 | `AnimatedGameCore` 继承并覆盖 `_slide/add_new_tile` | P2 | 改为“父类不改，子类补充过渡信息” | 源码 | FIXED |
| A4-05 | 04 | §3.2/§4 | 双阶段、反向回放、粒子 | 事实核对 | `MOVE_DURATION/POP_DURATION`、`animate_undo`、`ParticleOverlay` | P1 | 保留 | 源码 | VERIFIED |
| A4-06 | 04 | §6 | 存档目录隔离 | 事实核对 | V4 使用自己的 `game_history/` | P2 | 保留 | 源码 | VERIFIED |
| A5a-01 | 05a | §1.2 | “reward 等于本次新生成方块数值之和” | 术语歧义 | 随机补块不计分；计分来自合并产生的方块 | P1 | 明确“合并产生”，随机补块不计 | 源码/实测 | FIXED |
| A5a-02 | 05a | §1.2 | “实践中将 2048 视为成功终止” | 过度概括 | 界面提示胜利但可继续；搜索不以 2048 终止 | P1 | 改为“非搜索终止条件” | 源码 | FIXED |
| A5a-03 | 05a | §4.3/§5.1 | “最大绝对误差约 8.5e-14” | 证据不可复核 | 当前测试只断言 `TOL=1e-9`，未打印该值 | P1 | 保留为历史记录，标注“本次未重印” | 测试源码 | HISTORICAL |
| A5a-04 | 05a | §4.4/§5.1 | “14279 次采样 p(2)=0.8987” | 数据过期 | 本次复跑 `n=20000 p(2)=0.9013 p(4)=0.0987` | P1 | 更新为本次值，保留历史值对照 | 测试输出 | FIXED |
| A5a-05 | 05a | §4.4 | “18 组确定性测试” | 事实核对 | 6 widths × 3 sims | P2 | 保留 | 测试源码 | VERIFIED |
| A5a-06 | 05a | §5.2 | RL 2267.4 / 旧模型 1445.7 | 事实核对 | `experiments/report.md` 表格 | P1 | 保留 | 报告文件 | VERIFIED |
| A5a-07 | 05a | §1.3 | gamma=0.98、DEFAULT_SEED=2048、MAX_TIME_LIMIT=2.0 | 事实核对 | `rl_2048.py`、`solver_2048.py` | P2 | 保留 | 源码 | VERIFIED |
| A5b-01 | 05b | §6 | “202 条用例全部通过”无退出码/范围 | 证据不足 | 本次逐套件复跑：95+28+5+5+41+17+11=202，全部 exit 0 | P0 | 改写为复跑表与命令 | 实跑日志 | FIXED |
| A5b-02 | 05b | §5.2-5.6 | 像素/ΔE/通道/耗时具体数值 | 证据不可复现 | 原实验目录已清理，当前无原始日志 | P1 | 增加 HISTORICAL/UNVERIFIED 口径 | 文件清单 | HISTORICAL |
| A5b-03 | 05b | §1 | QThread 取消/有界返回 | 事实核对 | `SolverWorker` 前后检查取消；算法不做轮询 | P1 | 保留并强调“非即时中断” | 源码 | VERIFIED |
| A5b-04 | 05b | §6 命令 | 把脚本式自检当作 unittest | 口径 | `test_popups/test_rl_selftrain/test_cross_version` 为脚本 | P2 | 明确区分并给真实运行方式 | 源码/实跑 | FIXED |
| A5b-05 | 05b | §5.4 | “3 档 DPR 越界计数为 0” | 证据不足 | 原实验目录已清理 | P1 | 纳入 HISTORICAL 口径 | 文件清单 | HISTORICAL |
| A5b-06 | 05b | §2-§4 | 与第 3/4 篇重复解释 GUI 结构 | 冗余 | 两篇同讲棋盘/焦点 | P2 | 保留必要上下文，删除重复展开（局部） | 编辑复核 | PARTIAL |
| A6a-01 | 06a | §7.2 | “动作一致率 1.0”未限定范围 | 过度外推 | 固定 48 盘/固定种子/指定参数 | P1 | 增加适用范围 | 基准报告 | FIXED |
| A6a-02 | 06a | §7 | 数值未标来源 | 可追溯性 | `benchmarks/reports/summary.md` | P1 | 增加来源与“未重跑”说明 | 报告文件 | FIXED |
| A6a-03 | 06a | §7.1-7.3 | 微基准/同工作量/同墙钟表 | 事实核对 | 与 summary.md 逐项一致 | P2 | 保留 | 文件比对 | VERIFIED |
| A6a-04 | 06a | §4/§7.4 | 原生 rollout 不作为已部署能力 | 事实核对 | 默认关闭、未接主循环 | P2 | 保留 | 源码 | VERIFIED |
| A6b-01 | 06b | §7 | 500ms vs 1000ms | 文档/实现冲突 | `v6_background.REPORT_INTERVAL_MS=500`；1000ms 为早期计划 | P0 | 增加版本口径说明，以 500ms 为准 | 源码 | FIXED |
| A6b-02 | 06b | §4 | “readline 才能保证发一条收一条” | 过度承诺 | `readline()` 无数据时仍阻塞；非阻塞来自协议 | P1 | 改为“避免迭代器预读，不保证不阻塞” | 源码/协议 | FIXED |
| A6b-03 | 06b | §8 | `persist_official` “一次原子提交” | 跨文件事务误解 | 四次独立原子写 | P1 | 改为“按文件原子，非跨文件事务” | 源码 | FIXED |
| A6b-04 | 06b | §6 | 检查点重试只写“有界” | 失败路径缺失 | 重试耗尽抛 `IOError` → error 终态 | P1 | 补充失败语义 | 源码 | FIXED |
| A6b-05 | 06b | §8/§11 | 111s 卡死、536 步写放大 | 历史证据 | `_DeferredModelIO` 代码注释记录 | P2 | 标注“据代码注释记录” | 源码注释 | HISTORICAL |
| A6b-06 | 06b | §4 | CREATE_NO_WINDOW vs 第二个 Qt 窗口 | 事实核对 | `_launch_worker` 的 startupinfo；`BackgroundPanel` 禁止显示 | P2 | 保留 | 源码 | VERIFIED |
| A6c-01 | 06c | §8/§10 | 62188 被当作真实最高分 | 夹具说明缺失 | E2E 固定测试盘面 | P1 | 明确为测试夹具 | JSON | FIXED |
| A6c-02 | 06c | §10 | 22/22 无原始文件/退出码 | 证据不足 | `cross_mode_e2e.json` ok=true、checks=22、exit 0 | P1 | 补充路径与退出码 | 文件 | FIXED |
| A6c-03 | 06c | §11 | 8 种切换/15 项测试 | 事实核对 | `test_v6_cross_mode` 15 tests OK；矩阵 8 行 | P2 | 保留 | 实跑/文件 | VERIFIED |
| A6c-04 | 06c | §12 | VISUAL_PASS | 未验证 | 需人工目视 | P2 | 保留 UNVERIFIED | 规范 | UNVERIFIED |
| X-01 | 跨 | 导航 | 第 1 篇写“共 7 篇”；第 2/4 篇下一篇无链接 | 导航一致性 | 实际 6 篇 9 文件 | P1 | 统一为 6 篇/9 文件，补齐相对链接 | 全量链接检查 | FIXED |
| X-02 | 跨 | 术语 | V5“运行方式”=强度；V6“运行方式”=标准/快速/后台 | 版本混淆 | V5 GUI/V6 改名逻辑 | P1 | 在 02 报告与 06a 导航中明确；不篡改历史版本 | 源码/文档 | FIXED |
| X-03 | 跨 | 图片 | 全部为仓库相对路径 | CSDN 适配 | 无真实 CSDN URL | P1 | 保留本地路径 + `UPLOAD_REQUIRED` 映射表 | 03 报告 | PARTIAL |
| X-04 | 跨 | 公式 | `$$`/`bmatrix`/`cases`/`argmax` | CSDN 渲染未验证 | 无 CSDN 预览环境 | P1 | 结构检查通过；渲染标记 UNVERIFIED | 03 报告 | UNVERIFIED |
| X-05 | 跨 | 文风 | “本文将/本节将/可以看到”等套话 | 编辑质量 | P2 编辑规范 | P2 | 第 1/2 篇已删；其余按需删减 | 文本扫描 | PARTIAL |

## 3 说明

- 原文件未被覆盖；所有修订发生在 `csdn_2048_review/articles/`。
- 没有编造任何实验数值、截图或 CSDN 图片 URL；无法复现的测量统一标注 `HISTORICAL/UNVERIFIED`。
- 代码修正以实际源码为准；文章中的历史版本差异通过“版本口径”说明，而不是改写历史。
