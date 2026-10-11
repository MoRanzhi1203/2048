# V5.1 · H7 轻量实验数据核对（benchmark_audit）

> run: `20261011_151155` ｜ 原始数据优先，文档与原始数据冲突时以原始数据为准。

## 1. 源文件与参数核对

| 数据集 | 源文件 | budget | 局数/策略 | max_moves | time_budget_ms | seed_base | elapsed_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pilot | `experiments/v5_1/runs/v5_1_20261011_141048/results/benchmark_equal_time_5g_pilot30ms_20261011_143855.json` | equal_time | 5 | 400 | 30.0 | 1000 | 144.9 |
| Final | `experiments/v5_1/runs/v5_1_20261011_141048/results/benchmark_equal_time_10g_final10gms_20261011_144459.json` | equal_time | 10 | 400 | 30.0 | 1000 | 327.0 |

✅ 与 `report.md` §11.7 声明的“Pilot 5 局 / Final 10 局、400 步、30ms”一致。逐局字段含 `status(FINISHED/TRUNCATED)`、`moves`、`max_moves`、`score`、`seed`、`timeouts`、`move_*_ms`、`sims_avg`。

## 2. 汇总数字与文档一致性

Final（10 局/策略）原始 `summary` 与 `report.md` §11.7 表格逐行一致：

| strategy | avg | median | p10/p90 | max_tile | avgMs | p95Ms | p99Ms | simsAvg | fin/tr | timeouts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expectimax | 6062.8 | 6150 | 5764/6212 | 512 | 29.380 | 32.232 | 36.551 | — | 0/10 | 3381 |
| heuristic | 5784.4 | 6072 | 3228/6200 | 512 | 0.273 | 0.530 | 0.655 | — | 1/9 | 0 |
| mcts | 5825.2 | 6148 | 3236/6188 | 512 | 30.897 | 33.713 | 55.682 | 35.9 | 1/9 | 3863 |
| rl | 1496.4 | 1242 | 756/1800 | 256 | 0.751 | 1.112 | 1.495 | — | 10/0 | 0 |
| rollout | 6168.0 | 6162 | 6140/6204 | 512 | 21.687 | 78.643 | 116.740 | — | 0/10 | 0 |

Pilot（5 局/策略）同样与文档一致（rollout 6183.2 / mcts 6168.0 / expectimax 6132.8 / heuristic 6002.4 / rl 1688.0）。`exceptions=0`、`invalid_moves=0` 全部策略。

## 3. 终局 / 截断语义（关键）

- `expectimax / rollout`：**10 局全部 TRUNCATED**（达到 400 步上限仍可走）；`mcts / heuristic`：各 **1 局自然终局 / 9 局截断**；`rl`：**10 局全部 FINISHED**（自然结束，步数 100–330）。
- ⚠️ **400 步截断分 ≠ 自然终局得分**：搜索类得分被上限压低，**不得**与 RL 的自然终局得分直接比较，更不得据此发布五算法最终强弱排名或显著性结论。
- RL 在分布外 seed 家族（1000–1009，训练/验证/门禁家族之外）表现偏弱（最大瓦片 256），属预期，不代表其能力上限。

## 4. 每步超时语义

`expectimax`（depth=4, 30ms）与 `mcts`（simulations=100000, 30ms）在本预算下**几乎每步超时**（timeouts=3381 / 3863 ≈ 步数），返回 **best-so-far**；这是**固定时间预算**实验的正常表现，非缺陷。`mcts` 实际完成 `sims_avg≈35.9`。若需“计划模拟次数跑满”，须用固定 simulations + 充足时间预算（本轮未做，避免与固定时间实验混用）。

## 5. 缓存延迟口径（防止误读）

`test_rl_inference_cache` 的 `cold≈2.752ms → warm≈0.0997ms` 仅指**模型加载（磁盘读）**路径：命中缓存后不再读盘。**不得**表述为“RL 完整 solve 提速 27 倍”。RL 单步 solve 仍包含前向推理等开销（本轮实测 avgMs≈0.75ms/步，本身就是缓存后的端到端结果）。

## 6. 过期措辞修订

- “每算法 100 局为发布硬门禁”**已作废**：`report.md` 顶部已加 H7 阅读提示，§11.8 明示无遗留 100 局门禁；`known_issues.md` §B1、`test_matrix.md` §3、`README.md` 均已表述为“不再要求 100 局”。
- 历史章节 §1–§10 保持原文，未改写为新实验。

## 7. 结论

`EXPERIMENT_REPORT_PASS`：数据与文档一致、截断标记正确、无数字冲突；未发现缺失的原始证据。
