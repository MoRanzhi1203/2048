# 第五版 · 五算法正确性修复与实验报告

> 生成时间：2026-10-11　运行环境：`E:\anaconda3\python.exe`（Python 3.12.3 / numpy 1.26.4 / Windows 10）
> 说明：Phase A 基线记录脚本当时使用的环境为 Python 3.9.21 / numpy 2.0.2（见 `baseline/baseline.json`）。
> 原始数据：`experiments/results/*.json|*.csv`、`experiments/baseline/*`。本报告数值均来自实际执行输出，未执行的项标记 UNVERIFIED。

---

## 1. Phase A：可复现基线

| 项 | 值 |
| --- | --- |
| 正式模型路径 | `v5_pyqt_2048_solver/rl_model.npz` |
| 旧模型 SHA256 | `724c4eea…f2f9`（完整：724c4eea877421cf728fdaa56b7e8c710d98accf6c8a13ea69d9c0aa5ee9f4f9） |
| 基线隔离副本 | `experiments/baseline/rl_model_v1.npz`（SHA256 同上） |
| 网络结构 | W1[128,256] b1[128] W2[4,128] b2[4] Wv[1,128] bv[1] |
| 旧模型评估（200 局, seed=20260101） | 平均 1601.38 / 中位 1444 / 最高 6020 / 最大瓦片 512 / 达成 512 率 1.5% |
| 机会模型 | 每空位等概率 1/E；值 2 概率 0.9、值 4 概率 0.1；顺序=先移动取合并分→再生成→下一玩家回合 |

保护措施：复制而非覆盖旧模型；测试与实验均把历史目录重定向到临时目录，未写入真实 `game_history/`；未执行 `git commit`。

---

## 2. 五算法统一基准（Phase F1，equal_time，5 局/策略，smoke）

命令：`python experiments/benchmark_algorithms.py --budget equal_time --games 5 --tag smoke`
原始数据：`results/benchmark_equal_time_5g_smoke_20261011_021516.json / .csv`　总耗时 602.1s。

| strategy | avg | median | std | ci95(avg) | max tile | hit512% | avgMs | p95Ms | timeouts | invalid | exceptions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expectimax | 30464.8 | 32764 | 10973.0 | (21101.6, 40224.8) | 4096 | 100% | 35.58 | 51.30 | 0 | 0 | 0 |
| rollout | 21198.4 | 16252 | 7014.1 | (15464.8, 27756.8) | 2048 | 100% | 22.16 | 43.31 | 0 | 0 | 0 |
| heuristic | 13673.6 | 7800 | 9659.7 | (6648.0, 23425.6) | 2048 | 100% | 0.479 | 0.897 | 0 | 0 | 0 |
| mcts | 12221.6 | 14844 | 4725.5 | (7416.8, 15380.0) | 1024 | 80% | 50.75 | 52.09 | 0 | 0 | 0 |
| rl | 1688.0 | 1052 | 1195.7 | (908.0, 2812.8) | 256 | 0% | 2.099 | 3.706 | 0 | 0 | 0 |

配对差值（同 seed，相对 heuristic）：rollout **+7524.8** ci95[1543.2, 12484.8]；expectimax **+16791.2** ci95[−2187.2, 32874.4]；mcts −1452.0 ci95[−9193.6, 6092.0]；rl **−11985.6** ci95[−20648.0, −5597.6]。

> 样本量为 5 局（探索性，未达 §F1 的 ≥10 smoke / ≥100 正式规模），故不对“显著差异”下强结论；仅作方向性比较。RL 在此对局 seed 家族（1000–1004）与训练/验证 seed 不同，得分偏低属分布外表现。

---

## 3. 消融实验（Phase F2）

### 3.1 Heuristic（12 局/变体，seed 2000–2011）— `results/ablation_heuristic_12g_20261011_021708.json`
baseline 平均 12269.7。逐项移除 / 新增（配对差值 ci95）：

| 变体 | 差值均值 | ci95 | 结论 |
| --- | --- | --- | --- |
| −monotonicity | −6715.3 | [−9975.7, −3040.3] | 关键特征（显著） |
| −merge | −6234.0 | [−9895.7, −2473.7] | 关键特征（显著） |
| +snake(1.0) | +6981.7 | [408.0, 13677.3] | 新增特征有效（显著） |
| +danger(1.0) | +5685.0 | [475.3, 11725.3] | 新增特征有效（显著） |
| −empty | −1317.3 | [−4136.3, 1383.7] | 不显著 |
| −corner | +1049.0 | [−3217.7, 5690.3] | 不显著 |
| −smoothness | −535.3 | [−3544.7, 2231.0] | 不显著 |

### 3.2 Rollout（3 局/变体）— `results/ablation_rollout_3g_20261011_024327.json`
random 平均 17946.7。

| 变体 | 差值均值 | ci95 | avgMs |
| --- | --- | --- | --- |
| rollouts=24 | +15656.0 | [10784.0, 20228.0] | 49.79 |
| biased eps=0.1 | +9100.0 | [1388.0, 15256.0] | 41.78 |
| biased eps=0.0 | +4238.7 | [−10080.0, 22028.0] | 44.90 |
| depth=6 | +2453.3 | [−4152.0, 9120.0] | 10.45 |
| biased eps=0.3 | +1204.0 | [−316.0, 4056.0] | 34.55 |
| depth=12 | −3837.3 | [−11216.0, 3712.0] | 20.69 |
| rollouts=4 | −5750.7 | [−13012.0, 4820.0] | 8.97 |

### 3.3 Expectimax（3 局/变体，depth=2, time_limit=0.1）— `results/ablation_expectimax_3g_20261011_024402.json`

| 变体 | avg | ci95 |
| --- | --- | --- |
| none(精确) | 8870.7 | (5560.0, 12872.0) |
| TT | 8870.7 | (5560.0, 12872.0) |
| TT+cutoff | 8870.7 | (5560.0, 12872.0) |
| TT+sample | 25530.7 | (7336.0, 36640.0) |
| full | 25530.7 | (7336.0, 36640.0) |

配对差值（相对 none）：TT **+0.0**、TT+cutoff **+0.0** → **TT 无损**（估值逐位一致）；采样在 smoke 下差异大但样本不足（3 局，std≈13000）。

### 3.4 MCTS（3 局/变体，time_limit=0.05）— `results/ablation_mcts_3g_20261011_025546.json`
sims=50 平均 11837.3。

| 变体 | 差值均值 | ci95 | avgMs | timeouts |
| --- | --- | --- | --- | --- |
| width=2 | +3446.7 | [−2344.0, 12700.0] | 50.46 | 2659 |
| width=4 | +2032.0 | [−5556.0, 11980.0] | 50.48 | 2402 |
| c=3.0 | +1414.7 | [−4096.0, 9576.0] | 50.56 | 2350 |
| c=0.5 | −1765.3 | [−8820.0, 4240.0] | 50.53 | 1902 |
| sims=200 | −2398.7 | [−5816.0, −12.0] | 50.58 | 1724 |
| sims=800 | −5830.7 | [−8868.0, −12.0] | 50.62 | 1295 |

注：时间预算固定 0.05s/步，超时计数高；在硬时间预算下“增大 simulations”并不提升（反而因每模拟更贵而更早超时），需在“固定 simulations、无时间预算”下复测才能下结论。

---

## 4. Expectimax 剪枝统计（Phase B，来自 `test_expectimax_reference.py` 诊断输出）

剪枝 A/B（board E=10，depth=3，与独立精确参考对比）：

| variant | nodes | leaf | cache_hits | cutoffs | sampled | maxErr% | best |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none(精确) | 40 | 179 | 0 | 0 | 0 | 0.00% | = |
| TT | 40 | 179 | 0 | 0 | 0 | 0.00% | = |
| TT+sample | 24 | 113 | 0 | 0 | 4 | 0.99% | = |
| TT+cutoff | 20 | 130 | 0 | 40 | 0 | 2.52% | = |
| full | 12 | 81 | 0 | 24 | 4 | 1.66% | = |

- TT 命中证据（E=4, depth=4）：leaf 867→491，cache_hits=37。
- 空位采样相对误差（E=10, k=6）：均值 3.65%，跨 seed 波动 2.47%，各 seed [3.0, 3.7, 3.4, 5.3, 2.8]%。

---

## 5. MCTS 机会节点 / 收益统计（Phase C，来自 `test_mcts_chance.py`）

- `sample_spawn` n=20000：p(2)=0.9013，p(4)=0.0987；空位落点最大相对偏差 0.92%。
- 统一回报尺度：sims=40 最优分支估值 mean 43.4 / std 7.2；sims=400 mean 57.4 / std 10.0。
- 加宽消融（board E4, sims=200, seed=2024）：width 2→chance 20 / reused 90 / bestVal 39.5；4→41/119/54.7；8→96/282/57.3；64→98/302/74.3。
- UCT c 消融（sims=200, width=8）：c=0.5→57.3；c=1.4→57.3；c=3.0→67.4。

---

## 6. RL 梯度正确性（Phase D，来自 `test_rl_gradients.py`）

- [T01/R01] 中心有限差分最大相对偏差 **3.06e-08**（entropy_beta=0 与 0.002 一致）。
- [R01] 单样本 V-MSE：更新前 5.0000 → 修正后 **2.2972**；反向符号 → 7.7028（证明符号已纠正）。
- [R02] 共享层价值项贡献 max|Δ| = **1.217**（价值梯度确实回传隐藏层）。
- [R03] 采样频率与策略分布最大偏差 **0.0016**（n=40000）。
- [R04] 验证曲线 history=[1108,1108,1108,1631]，早停=True，实际训练 15 局。

---

## 7. RL 新旧模型对照（独立评估门禁）

评估口径：`rl_2048.py --eval-only`（≥50 局，seed=12345，贪心）。

| 模型 | 平均分 | 最高分 | 最大瓦片 | SHA256 前 16 |
| --- | --- | --- | --- | --- |
| 修复后正式模型 `rl_model.npz` | **2267.4** | 6780 | 512 | `EE4B370E67676BFB` |
| 旧模型备份 `rl_model.npz.prev.npz` | 1445.7 | 5520 | 512 | `724C4EEA877421CF` |
| Phase A 基线副本 | 1445.7 | 5520 | 512 | `724C4EEA877421CF` |

提升 **+821.7（+56.8%）**；门禁通过→替换正式模型，旧模型保存为 `.prev.npz`。候选模型落盘于 `rl_model.candidate.npz`。

---

## 8. 测试与 GUI 回归（Phase G）

| 套件 | 结果 | 说明 |
| --- | --- | --- |
| `v5_pyqt_2048_solver/test_solver.py` | **37/37** | 算法核心 + v5 界面集成 |
| `tests/test_popups.py` | **17/17** | v2–v5 弹窗主题化/DPI |
| `tests/test_cross_version.py` | **41/41** | v2–v5 存档/恢复/隔离/强杀 |
| `tests/test_expectimax_reference.py` | **9/9** | 精确枚举对照 + 剪枝 A/B |
| `tests/test_mcts_chance.py` | **7/7** | 机会概率/顺序/复用/回报 |
| `tests/test_rl_gradients.py` | **8/8** | 有限差分/符号/共享层/采样 |
| `tests/test_algorithm_benchmark_smoke.py` | **5/5** | 五策略合法/可完成/可复现 |
| `tests/test_rl_selftrain.py` | **9/11** | 见 §9（2 项陈旧静态检查） |

### GUI 正式整窗截图（`tools/capture_gui.py --version v5`）

| scene | 文件 | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- |
| start | `screenshots/full_start.png` | PASS | PASS | PASS | UNVERIFIED |
| game | `screenshots/full_game.png` | PASS | PASS | PASS | UNVERIFIED |
| solver | `screenshots/full_solver.png` | PASS | PASS | PASS | UNVERIFIED |
| suggest | `screenshots/full_suggest.png` | PASS | PASS | PASS | UNVERIFIED |
| gameover | `screenshots/full_gameover.png` | PASS | PASS | PASS | UNVERIFIED |
| export | `screenshots/full_export.png` | PASS | PASS | PASS | UNVERIFIED |
| results | `screenshots/full_results.png` | PASS | PASS | PASS | UNVERIFIED |
| recover | `screenshots/full_recover.png` | PASS | PASS | PASS | UNVERIFIED |

均为 DWM 可见外框整窗捕获（含原生标题栏 39px、左上角彩色图标 ≥205px、最小/最大/关闭按钮），文字对比度校验全部 >0.01。**VISUAL_PASS 需人工核对图像后加 `--visual-confirm` 授予；未确认前记 UNVERIFIED，`GUI_SCREENSHOT_PASS=false`。**

---

## 9. 失败项 / 未验证项

| 项 | 状态 | 原因 | 复现命令 |
| --- | --- | --- | --- |
| `test_rl_selftrain.py` 3a | FAIL（陈旧静态检查） | 断言源码含 `for gi in range(games)` 与 `net['W2'] += lr`；Phase D 重写训练循环与更新函数后字符串不再匹配，非功能回归 | `python tests/test_rl_selftrain.py` |
| `test_rl_selftrain.py` 3d | FAIL（陈旧静态检查） | 原断言“无早停/最优检查点/replay 关键字”以证明缺失；Phase D 已加入 `patience`/best checkpoint，断言语义被超越 | `python tests/test_rl_selftrain.py` |
| 五算法基准样本量 | 探索性 | 5 局 < §F1 建议 ≥10 smoke；正式 ≥100 局未跑（耗时） | `python experiments/benchmark_algorithms.py --games 100 --budget default` |
| GUI VISUAL_PASS | UNVERIFIED | 需人工核对图像，代理不代替人工授予 | `python tools/capture_gui.py --version v5 --scene start --visual-confirm` |
| 正式默认强度基准 | 未执行 | 时间预算过大 | `python experiments/benchmark_algorithms.py --games 10 --budget default` |

---

## 10. 统计口径

- 均值/中位数/标准差按局统计；95% CI 用 bootstrap（n=2000, seed=20260101）；配对差值用同 seed 的 (各策略 − 基线) 的 bootstrap CI。
- 环境随机数与求解器内部随机数分离：`env_rng` 负责生成新块，solver seed 只影响搜索。
- 计数型配置（heuristic / rollout / rl 及固定 simulations 的 MCTS、关闭时间预算的 Expectimax）固定种子逐位可复现；含墙钟时间预算者不保证逐位复现。
- 所有实验把历史目录重定向到临时目录，未污染真实存档；未执行 `git commit`。
