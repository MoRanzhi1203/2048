# 2048 V6.2 — Hybrid Native Search Upgrade | Trae One-Pass Execution Plan

> 文件名使用 ASCII；正文 UTF-8。执行根目录：`E:\PyQt5_demo\2048`。建议把本文件置于仓库根目录供 Trae 通过 `@` 引用。此文档为**待执行指令**，不是已经完成的测试报告。

## 0. 任务定位与不可变约束

你是该项目的 Trae Agent。**一次性完整执行下面 S0→S9**，按门禁推进，遇到正确性失败立即停止该阶段的性能推广，保留证据并回退到可工作的 Reference/C++ 原语路径；可以继续执行独立的诊断与安全测试，但不得带病开启默认加速。禁止用猜测替代实际源码与数据。

- 目标架构：**Python + PyQt5 GUI/调度/研究训练，NumPy/Numba 数值原型，C++20 + pybind11 原生搜索，Reference 作为权威语义实现**。在现有 V6/V6.1 上增量升级，建议标记开发里程碑 V6.2；**不要另起 GUI**，不要改 V1–V4。V5 是正确性参照/共享渲染来源，原则上只读；除有确凿跨版本缺陷且明确登记才考虑修改，优先只在 V6 隔离实现。
- 旧版本源代码、`game_history/`、`solver_results/`、会话 JSON、锁、截图、实验、`.pyd`、PyTorch/NumPy 正式 RL 权重为受保护资产：记录基线哈希，不删除/清空/重置/覆盖；临时测试必须使用独立 `TEMP` 存档目录，严禁共享真实用户目录。**不得训练 RL**、不得默认执行每配置 100/300 局游戏、不得自动 git commit/push。
- 固定环境：`E:\anaconda3\envs\2048\python.exe`，`PYTHONNOUSERSITE=1`。核查实际 MSVC/CMake/pybind11 可用性，构建指令参照现有 `solver_backends/bitboard_cpp/BUILD_WINDOWS.md`，不要凭空指定路径。
- 旧正确性约束：C++ 64-bit Bitboard 使用每格 4-bit 指数，出现 **65536 或更高方块** 必须检测溢出并对**整次决策**安全回退；不得截断。保留 V5/V6 MCTS Chance 节点及统计回传不变量、Expectimax 参考语义、GUI QThread `job_id` 与 board signature、单步建议常驻跟随、方向键路由、右栏折叠以及存档隔离。
- 原始版本快照（需要重新实测，不得当成本轮结果）：曾报告固定工作量 C++ 原语后端相对 Reference 的 Rollout 3.09×、Expectimax 2.67×、MCTS 1.84×；一次小规模本地探测启用 `native_rollout` 后有收益，但**未证明所有随机配置等价，也不能直接全面设默认**。最新日志声称 `native_rollout` 默认关闭、`rollout_batch` 已有内核但未接入、Expectimax/MCTS 搜索循环仍在 Python。逐项核实。

## S0 — 冻结现场与代码审计（必须先做）

1. 执行 `git status --short`、`git rev-parse HEAD`、关键文件 SHA256，保存 Python/Numba/NumPy/pybind11/compiler/`.pyd` 版本及 `dispatch.probe_backends()` 运行结果。记录 V5/V6 模块实际 import 路径、是否多实例、历史目录解析、模型权重哈希。
2. 阅读 `solver_v6.py`、`solver_backends/dispatch.py`、Reference/NumPy/Numba/C++ 后端、`bitboard.cpp/.hpp/bindings.cpp/tests.cpp`、既有 benchmark 和 tests。生成**现状能力矩阵**：primitive move/evaluate、native single rollout、batch rollout、native expectimax、native mcts、cancel/progress、transposition table、GIL release，逐项标记 EXISTING / PARTIAL / MISSING / UNKNOWN，并附实际函数位置。
3. 从原始 benchmark CSV/JSON 复核历史速度、预算、seed、warmup、调用口径；区分 microkernel、fixed-work、time-budget 与游戏烟测。旧日志叙述不替代原始数据。记录当前 UI 后端 `auto` 的**逐策略**选择与实际 `backend_used`、fallback reason。
4. 不改历史 benchmark、用户持久化数据。新证据存 `v6_pyqt_2048_accelerated/experiments/v6_2/<run_id>/`；`run_id` 按本机时间/唯一标识生成，不能覆盖旧证据。

**S0 门禁**：确认真实能力、扩展可加载、基线可复现；无法确认则先输出阻塞点并转到安全修复。

## S1 — 建立公平且可重复的原生搜索契约

定义一个稳定的 `NativeSearchRequest` / `NativeSearchResult`（可采用 Python dataclass + pybind11 转换，不要求引入框架）：

- 输入：`board`、`strategy`、`budget_type`（固定 rollout/节点数/深度/时间）、`budget_value`、完整评估权重与规则、`seed`/明确的随机事件流、取消令牌、可选统计开关；所有决策语义参数必须显式，禁止偷偷沿用不同默认值。
- 输出：`best_direction`、`score`、`legal_moves`（必要时）、`completed_work`、`node_count`、`rollouts`、`elapsed_ms`、`backend_requested/used`、`engine_used`（native / Python kernel / reference）、`fallback_reason`、`cancelled`、`board_signature`、`job_id`（外围填充）。时间类统计不得混入评估函数值。
- 特别处理随机数：仅 seed 相同不保证 Python/C++ 随机序列相同。为**强等价测试**提供预生成 `spawn_events`/`move_events` 或共享明确定义的 RNG；对非确定性实验报告统计差异而不是假报逐步相等。规定 tie-break 方向顺序与浮点容差。
- 避免跨语言来回调用：一次决策尽可能一次 pybind11 请求；对 batch 使用单次批量调用。C++ native long loop 释放 GIL，取消令牌采用线程安全原子量；禁止跨线程直接更新 Qt 组件。
- 保留 Python Reference 完整路径与选择方式。优化新增为可关闭 Feature Flag，**默认是否启用由 S7 基准决定**。

**S1 门禁**：现有 `solve(...)` 调用兼容、错误类型可分辨、旧数据模型不变，测试覆盖所有 result 字段及异常。

## S2 — Rollout：先用已有原生能力，之后批量接入

1. 先审计 `native_rollout` 的真实输入输出、何时禁用、是否重用评估器与合法动作判定、随机生成 2/4 比例、策略随机性、计分与终止条件；**禁止为了加速改变策略语义**。
2. 若已有原生单次 rollout 函数，优先通过受控 Flag 接入，在 Python、Numba 和 cpp 中对齐工作量；凡不支持的 policy / 特殊配置，应明确 fallback，不得 silently 改用 random。
3. 若已有 `rollout_batch`，核查原接口再接入根动作批量模拟，减少 Python→C++ 调用频率；明确每根动作分配的样本数、随机数流、初始棋盘及事件重放，绝不能将批量数和总次数混淆。必要时以批次为单位检查取消和发布进度。
4. 对溢出、异常、取消：整个求解结果标记 fallback；若原生部分已消费 RNG，Reference 重算必须从**原始请求的 RNG/事件起点**重新开始，否则结果无可比性。
5. 实测 native single vs batch 与 Python/Numba 路径。要求原生计算速度改善必须体现在**包含封装开销的端到端调用**，不以单个 C++ primitive 数字替代。

**S2 门禁**：确定性共享事件完全等价；随机实验多种 seed 下统计合理；异常回退、取消、预算、输出元数据正确。

## S3 — Expectimax：C++ 原生整树优先

在新增原生搜索模块中实现 Max/Chance 节点完整递归，而不是在 Python 每个子节点调用一次 `backend.move()`：

- Max 节点严格沿用现有合法动作、终局、启发式评估、搜索深度含义和并列方向处理；Chance 节点按真实空格数量、2/4 概率加权；没有合法动作/空格时语义由 Reference 决定。
- 必须对 `prune=False` 无近似版本首先做到数值/决策等价；任何 probability cutoff、sampling、beam pruning 作为独立模式实验，不能把近似加速与精确结果直接合并比较。
- 可选 `transposition table`：采用紧凑 Bitboard 键 + 剩余深度 + 节点类型 + 评估器/参数版本 + 概率裁剪配置等完整语义键；如使用缓存容量限制或替换策略，记录命中率/碰撞/内存，并验证缓存 on/off 输出一致。
- 设计递归/内存上限、按节点批次轮询取消令牌、释放 GIL、抛异常安全销毁。评估一致性要覆盖所有允许的 tile 值；65536 边界必须回退。
- 在固定棋盘 corpus 上比较各深度、分支、Chance 概率、tie-break、score tolerance、visited nodes。深度和节点数的定义如不同，先对齐再计时。

**S3 门禁**：无近似模式确定性等价、异常/溢出/取消均通过，超预算内存被界定；不通过保持 Python Expectimax 默认。

## S4 — MCTS：最后迁移，重点保护统计语义

将 selection/expansion/simulation/backprop 与 Chance 随机事件节点转到 C++，树节点用连续数组/稳定索引或对象池（禁止无证据的复杂并行）。

- 对照现有 V5 修复：**玩家决策节点与机会节点严格区分**；Chance 节点按真实概率抽样或正确枚举；UCT 计算、未访问节点处理、胜负/收益的归一化、访问次数增加次数、回传路径不得重复计数。
- 先实现**单线程确定性**版本。固定模拟轨迹 / 强制事件流下逐步验证 selection、tree expansion、rollout、backprop 的中间统计；加单独的结构性不变量断言。
- `rollout_batch` 可用于仿真阶段，但不能在统计回传时错误地给所有祖先增加相同的重复计数；明确 batch 统计映射关系。没有结构正确性之前不得上并行 MCTS。
- 保留根节点无可行方向、零预算、立即取消、非有限评估值、溢出与内存预算的处理。
- 对真实随机 MCTS：优先比较分布、得分、合法性、固定时间完成模拟数；若 RNG 和采样事件不相同，不得假称与 Reference 逐次动作完全相同。

**S4 门禁**：Chance/Backprop 不变量、确定性轨迹、长时间取消、内存上限、GUI 线程安全全部通过；否则仍用现有 Python MCTS + C++ primitives。

## S5 — 保留的技术路线边界

- `heuristic`：保留 C++ primitive/Reference 后端，不为了“全 C++”强行重写小控制层；按端到端收益选择。
- `rl`：**不训练、不转换正式模型**，继续以当前 NumPy 推理为可靠基线。PyTorch/ONNX Runtime 仅作为后续独立研究备选，不为本次增加额外运行依赖。
- Numba：保留 nopython 路径和缓存预热；用于快速实现新的评估函数与批量实验，不以 NumPy 向量化替代 4×4 标量 Bitboard 高速内核。
- 本轮不引入 CUDA、GPU、AVX2 强制指令集、多线程共享 MCTS 或新 GUI；有实际瓶颈证据才能单独开实验，不混入 S2–S4 的公平测量。

## S6 — 完整测试矩阵和回退门禁

必须按层验证，列出**每项真实测试命令、测试数、耗时与退出码**：

1. Primitive：现有 65536 行表穷举、≥10000 随机棋盘、4 方向合法性及评估数值；NumPy/Numba/CPP/Reference 一致性；4-bit exponent 溢出拒绝或整次重算。
2. Rollout：合法动作、精确固定事件重放、样本预算、随机性、score、一键取消、批量余数、重复 seed、跨边界溢出以及 fallback 后的结果和元数据。
3. Expectimax：深度 0/1/2/3/可承受的更深层、Chance 2/4 权重、cache on/off、近似模式隔离、多个 tie、边缘盘/死局；对齐 Reference 输出。
4. MCTS：Chance 节点结构、UCT、访问数/总收益、更新一次原则、确定性事件路径、模拟预算、长时间取消、内存释放。
5. GUI：现有 V5/V6 QThread job_id/signature 回归、按键焦点独占棋盘、单步建议跟随、停止/新游戏/右栏展开折叠、旧结果丢弃。测试 `solve` 中途关闭并重新打开，避免 `QThread destroyed while running`。GUI 视觉自动门禁与人工视觉分开记录。
6. 隔离：在测试前后核对 V1–V5 所有受保护目录存在性/文件哈希/mtime/新锁/新增意外目录；不用 git status 代替真实文件系统检查。测试导入期不得修改全局 `2048_HISTORY_DIR`；窗口必须 close 并卸载事件过滤器，避免此前 unittest 多窗口模态锁卡住。
7. 失败注入：cpp `.pyd` 缺失/版本不匹配、随机输入非法、人工取消、原生异常、board overflow、OOM/预算不足；均可回退 Reference 且不会卡死 GUI、破坏存档或产生错误决策。

任何一致性失败：保存 seed/棋盘/路径/输入/输出和最小复现，禁用该 native engine 的默认开关，Reference 可用才算安全回退 PASS。

## S7 — 公平性能基准、选择默认后端

**分两类正式基准；不得用不同语义或工作量比较：**

- 固定工作量：相同棋盘集、评估器、预算与 tie-break、random-event trace（适用时）；分别运行 Reference / Python+CPP primitives / Numba / Native single / Native batch / Native full-tree。预热 Numba JIT 与 native caches，单独记录 cold/warm，重复至少 7 轮，报告 median、p95、节点/秒、工作完成量、pybind11 往返次数和内存峰值。
- 固定墙钟时间：相同 20/50/100ms 等有意义预算时，报告实际完成工作量、停止延迟、合法决策率及决策质量指标。仅少量对局（例如每配置 2/5/10 局且限制最大步数）做烟测；结果标明 TRUNCATED，**不推出胜率排名**。
- CPU/线程条件、编译选项、单/多进程、随机种子、机器环境、真实 Windows vs offscreen 必须写入原始 JSON/CSV；不得把性能探索和正式 GUI 截图采集重叠运行而污染结果。
- 为每算法建立策略选择表：`heuristic`、`rollout`、`expectimax`、`mcts`、`rl` 分别选择当前最优稳定实现；**即使 native 可以运行也不能未经证据默认开启**。对于低预算，保留轻量 Reference/Numba/CPP primitive 路径，防止 native 启动/封装开销反而更慢。
- 若 native 相较基线无稳定端到端收益，或正确性/取消/内存未通过，不升级默认；报告明确原因。保存 `before/after` 同一语义性能表、原始记录和复现命令。

## S8 — 运行期接口、发布与稳定性

- 原生引擎调用必须位于现有 worker，GUI 主线程只收信号；维护 `job_id` 和棋盘签名双重过期结果校验。`backend_requested`, `backend_used`, `engine_used`, `fallback_reason` 在 GUI 详情、日志和导出一致，不混淆“使用 cpp primitive”和“native full search”。
- 对超出 native 可表示范围的状态和缺失 `.pyd`：**直接选择 Reference 全量求解**；不能从部分已计算的 native 搜索树接着算并伪装成同一次确定性搜索。
- C++ 支持 cooperative cancellation；关闭窗口有界等待沿用现有 V5/V6 契约，禁止强制终止不安全线程、悬空回调。GUI 性能基准不得在主线程做大量实验。
- 使用原有存档原子写入与隔离逻辑，发布时不要迁移旧存档。为旧项目配置文件保持向后兼容；新策略/配置有明确版本字段及降级规则。
- 如本轮只完成 Rollout 和 Expectimax，MCTS 可以标记 `PARTIAL` 且继续使用安全旧路径，**不可将未完成工作笼统标记 PASS**。如安全测试失败，保留诊断产物和正常工作的旧实现。

## S9 — 最终交付、门禁与真实报告

在新的 V6.2 专属实验目录内交付：

- `baseline_manifest.json`：HEAD、源码/模型/用户数据目录哈希、环境、后端探测。
- `capability_matrix.md`：已存在/新增/未实现能力，具体源码位置。
- `test_results.json`、`test_commands.txt`、`failures/`：真实命令、测试数量、退出码和最小复现。
- `bench_fixed_work.csv`、`bench_time_budget.csv`、`benchmark_metadata.json`：公平基准原始结果。
- `backend_policy.json`：每个策略的推荐后端、触发条件与回退。
- `isolation_before_after.json`：真实旧版数据文件系统隔离结果。
- `native_search_upgrade_report.md`：根因、逐阶段实现、修改文件和核心 diff、正确性、搜索性能、GUI/存档验证、剩余风险、未验证项。

**建议发布门禁：**

| Gate | 条件 |
|---|---|
| N0 | 环境、源码/模型基线冻结且证据完整 |
| N1 | Reference 与 CPP primitive 既有等价性通过 |
| N2 | Native Rollout fixed-events/batch/异常与取消通过 |
| N3 | Native Expectimax 精确版/缓存/概率/异常通过 |
| N4 | Native MCTS Chance/UCT/Backprop/取消通过（若未实现则 PARTIAL，不设默认） |
| N5 | 公平 fixed-work/time-budget 原始基准完整 |
| N6 | 每策略默认选择有实测依据；失败回退可复现 |
| N7 | V5/V6 既有测试、GUI worker/焦点/提示与关闭无回归 |
| N8 | V1–V5 代码、存档、模型、锁文件无意外修改 |
| N9 | 源码、构建、报告与可重现命令齐全；发布声明与真实门禁一致 |
| N10 | 自动 GUI 截图结构/文本、人工视觉、真实多 DPI 分栏报告，未经人工确认的项目为 UNVERIFIED |

最后用简洁中文回复：完成了什么（区分新旧）、**真实**构建/测试结果、固定工作量前后数据、建议策略后端、异常回退、旧版隔离、门禁 PASS/PARTIAL/FAIL/UNVERIFIED，以及所有证据的绝对路径。不得把“计划”或“模拟输出”写成已执行事实，不得擅自提交 Git。
