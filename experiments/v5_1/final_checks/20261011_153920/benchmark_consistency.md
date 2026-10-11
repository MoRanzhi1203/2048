# V5.1 · H8-4 轻量实验一致性核对（benchmark_consistency）

> run: `20261011_153920` ｜ 本轮**只核对不重跑**（H7 Final/Pilot 原始 JSON/CSV 为准）。

## 1. 源文件与汇总核对

| 数据集 | 源文件 | 局数/策略 | max_moves | time_budget_ms | FINISHED/TRUNCATED |
| --- | --- | --- | --- | --- | --- |
| Pilot | `experiments/v5_1/runs/v5_1_20261011_141048/results/benchmark_equal_time_5g_pilot30ms_*.json` | 5 | 400 | 30 | exp 0/5、heu 0/5、mcts 0/5、rl 5/0、rollout 0/5 |
| Final | `experiments/v5_1/runs/v5_1_20261011_141048/results/benchmark_equal_time_10g_final10gms_*.json` | 10 | 400 | 30 | exp 0/10、heu 1/9、mcts 1/9、rl 10/0、rollout 0/10 |

核对结论：与 `experiments/v5_1/report.md` §11.7（H7 已核对，`benchmark_audit.md`）**逐行一致**；`exceptions=0`、`invalid_moves=0`。本轮**未新增/未重跑任何基准**。

## 2. 截断与 30ms 预算解释（不得误读）

- **400 步截断分 ≠ 自然终局得分**：搜索类（expectimax/rollout 全截断；mcts/heuristic 各 1 局自然终局）得分被上限压低，**不得**与 `rl`（10/10 自然终局）直接比较，更不得据此发布五算法最终排名/显著性结论。
- **30ms 到时间为预算行为，非异常超时**：`expectimax`(depth=4,30ms)/`mcts`(simulations=100000,30ms) 近乎每步触发 `timed_out` 并返回 best-so-far，属**固定时间实验**的正常表现；`mcts` 实际完成 `sims_avg≈36`。
- 缓存口径：`cold 2.752ms→warm 0.0997ms` 仅指**模型加载**路径，非完整 solve 提速。

## 3. 门禁

`H8_BENCHMARK_REUSE_PASS`：历史轻量实验记录未被覆盖、未被重跑，与文档一致；截断/预算语义正确。无新增虚假基准。
