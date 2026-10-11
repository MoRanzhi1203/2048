# V6 基准汇总（Backend Microbenchmark 与 Solver End-to-End 分开报告，禁止混合排名）

> 所有数据来自 `benchmarks/reports/` 下的时间戳原始目录（JSON + CSV）。
> 固定棋盘集：`boards.jsonl`（48 盘，sha256 校验）；算法规则复用冻结 V5；种子固定。
> 结论限定为**工程回归 / 探索性小样本**，不作统计显著性结论。

## 1. 内核微基准（`run_micro.py`，reports/micro_*）

median 每单位耗时（µs；越小越好），相同棋盘集与相同调用频率：

| 内核 | reference | numpy | numba | cpp | cpp vs ref |
| --- | ---: | ---: | ---: | ---: | ---: |
| move_all_dirs | 22.99 | 652.07 | 22.05 | 13.26 | 1.73× |
| legal_moves | 105.71 | 2673.76 | 70.29 | 6.20 | 17.0× |
| evaluate | 98.21 | 860.70 | 12.80 | 13.60 | 7.2× |
| batch_move_left | 20.02 | 408.86 | 16.43 | 12.30 | 1.63× |
| rollout_py_d10 | 1721.8 | 28980.3 | 1574.2 | 247.5 | 6.96× |
| rollout_py_d20 | 4831.9 | 36462.3 | 2966.7 | 362.1 | 13.3× |
| rollout_py_d40 | 6925.3 | 86999.2 | 5987.8 | 493.3 | 14.0× |

冷启动（首次编译/构建，ms）：reference 2.6｜numpy 5.5｜numba 38.0｜cpp 11.8。

**结论**：NumPy 在 4×4 单盘上净变慢（保留为等价对照与批量用途）；Numba 仅评估类受益；
C++ 在 legal/evaluate/rollout 上显著更快。

## 2. 搜索同工作量对照（`run_search.py`，reports/search_*）

固定工作量（prune=False / 固定 rollouts / 固定 simulations），median 每决策耗时与动作一致率：

| 算法 | reference | numpy | numba | cpp | cpp 加速 | 动作一致率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| heuristic | ~0 | 2.13ms | ~0 | ~0 | — | 1.0 |
| rollout(20×16) | 107.68ms | 1140.54ms | 220.80ms | 34.80ms | **3.09×** | 1.0 |
| expectimax(prune=False,d3) | 16.14ms | 77.66ms | 11.28ms | 6.04ms | **2.67×** | 1.0 |
| mcts(60 sims) | 37.34ms | 655.92ms | 121.24ms | 20.32ms | **1.84×** | 1.0 |

**结论**：C++ 后端在计算密集策略上取得真实端到端收益；所有配置动作与 reference 一致（1.0）。

## 3. 同墙钟预算小样本对局（`run_pilot.py --mode smoke`，reports/pilot_smoke_*）

Smoke 2 局/算法，max_moves=200，单步预算 20ms，环境规则用冻结 V5：

| 策略 | 后端 | 均分 | 最大瓦片 | 结束 | 平均步耗时 |
| --- | --- | ---: | ---: | --- | ---: |
| heuristic | reference / cpp | 2566 / 2566 | 256 | TRUNCATED×2 | 1.92 / 1.92 ms |
| rollout | reference / cpp | 2530 / 2530 | 256 | TRUNCATED×2 | 79.85 / **29.08** ms |
| expectimax | reference / cpp | 2514 / 2636 | 256 | TRUNCATED×2 | 21.47 / 15.91 ms |
| mcts | reference / cpp | 2526 / 2558 | 256 | TRUNCATED×2 | 22.81 / 22.11 ms |
| rl | reference / cpp | 2356 / 2356 | 256 | TRUNCATED×2 | 3.70 / 3.29 ms |

**说明**：所有对局在 200 步上限被 `TRUNCATED`（Smoke 上限较低），分数不作自然终局比较。
expectimax 分数在不同后端不同，是「同墙钟预算 ≠ 同计算量」（cpp 更快→搜索更深）的预期结果。

## 4. 默认后端选型

**默认 = `cpp`（不可用时回退 reference）**。依据（见 `benchmarks/backend_default.json`）：
正确性门禁全 PASS ＋ 含转换/调用成本的端到端延迟显著改善（2.7–3.1×）＋ 构建可复现 ＋
溢出可显式回退 ＋ 内存（~0.9MB 行表）可接受。NumPy/Numba 保留为对照与可选加速器，不做默认。

## 5. 复现

```powershell
$env:PYTHONNOUSERSITE="1"
& python v6_pyqt_2048_accelerated\benchmarks\run_micro.py
& python v6_pyqt_2048_accelerated\benchmarks\run_search.py
& python v6_pyqt_2048_accelerated\benchmarks\run_pilot.py --mode smoke
```
