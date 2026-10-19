# 04 技术证据与基准溯源（P1/P5）

## 1 环境

| 项 | 值 |
| --- | --- |
| Python | `E:\anaconda3\envs\2048\python.exe`（3.12.3） |
| 环境变量 | `PYTHONNOUSERSITE=1` |
| 系统 | Windows 10（10.0.19042） |
| 仓库 | `E:\PyQt5_demo\2048` |
| 证据日期 | 2026-10-20 |
| Git | 未提交、未推送（按要求） |

## 2 合并规则与计分（实跑）

命令：

```bash
E:\anaconda3\envs\2048\python.exe -
# 导入 solver_2048.move_grid，打印四行测试
```

输出（exit 0）：

```text
[2, 2, 2, 2] -> [4, 4, 0, 0] gained= 8 moved= True
[2, 0, 2, 4] -> [4, 4, 0, 0] gained= 4 moved= True
[4, 4, 4, 4] -> [8, 8, 0, 0] gained= 16 moved= True
[2, 2, 4, 4] -> [4, 8, 0, 0] gained= 12 moved= True
```

用途：修正第 1 篇“得分求和口径”，并作为 `[2,2,2,2]` 最多一次合并的实证。

## 3 测试复跑与退出码

### 3.1 第 5 篇相关（共 202 条）

| 命令 | 目录 | 结果 | 退出码 |
| --- | --- | --- | ---: |
| `python -m unittest test_solver` | `v5_pyqt_2048_solver/` | `Ran 95 tests in 82.635s` / `OK` | 0 |
| `python -m unittest test_expectimax_reference test_mcts_chance test_rl_gradients` | `tests/` | `Ran 28 tests in 19.362s` / `OK` | 0 |
| `python -m unittest test_rl_model_management` | `tests/` | `Ran 5 tests` / `OK` | 0 |
| `python -m unittest test_algorithm_benchmark_smoke` | `tests/` | `Ran 5 tests` / `OK` | 0 |
| `python test_cross_version.py` | `tests/` | `41/41 通过，0 失败` | 0 |
| `python test_popups.py` | `tests/` | `17/17 通过` | 0 |
| `python test_rl_selftrain.py` | `tests/` | `11/11 通过`（其中 2 项为“已确认未实现”，如实计为自检通过） | 0 |

合计 **95 + 28 + 5 + 5 + 41 + 17 + 11 = 202**。原文“202 条全部通过”由此从笼统表述升级为可追溯的逐套件结果。

### 3.2 关键数值（本次输出）

- MCTS spawn 分布：`n=20000`，`p(2)=0.9013`，`p(4)=0.0987`，空位最大相对偏差 `0.92%`。
- RL 梯度有限差分最大相对偏差：`3.06e-08`（beta=0.0 与 0.002 两次一致）。
- RL 推理缓存：`cold=2.587ms warm=0.1541ms`（仅加载路径，不代表完整 solve 加速）。
- 五算法 smoke：各 80 步，`err=0`（heuristic 0.219ms、rollout 7.222ms、expectimax 2.928ms、mcts 19.593ms、rl 0.715ms，p95 见日志）。

### 3.3 第 6 篇跨模式 E2E

- 文件：`v6_pyqt_2048_accelerated/experiments/v6_2/20261020_cross_mode_handoff/cross_mode_e2e.json`
- 结果：`ok=true`，`checks=22`，失败 0；进程退出码 0；8 张真实桌面截图。
- 关键断言：后台 217 步、本机 202 步、累计 419 步；暂停点官方棋盘/分数与 Worker 终态一致；全局 RNG 与 Worker 逐位一致；最高分夹具 62188 全程不回退。
- 单元矩阵：`tests/test_v6_cross_mode.py` 15 项 OK；8 种暂停切换 + 4 项扩展。

### 3.4 第 6 篇后端与基准

- 原始汇总：`v6_pyqt_2048_accelerated/benchmarks/reports/summary.md`（微基准、同工作量、同墙钟分开）。
- 固定棋盘集：`boards.jsonl`（48 盘，sha256 校验）；种子固定；算法规则复用冻结 V5。
- 本次评审**未重跑基准**（耗时且不影响文稿事实核对），表格数值按原始记录保留：
  - 微基准：`move_all_dirs` 22.99→13.26µs，`legal_moves` 105.71→6.20µs，`rollout_py_d40` 6925.3→493.3µs。
  - 同工作量：rollout 107.68→34.80ms（3.09×），expectimax 16.14→6.04ms（2.67×），MCTS 37.34→20.32ms（1.84×）；动作一致率 1.0（限定测试集）。
  - 同墙钟 smoke：2 局/算法、200 步上限，全部 `TRUNCATED`，不作自然终局比较。
- 结论限定：C++ 默认后端有真实端到端收益；NumPy 在 4×4 单盘上反而更慢。

## 4 RL 模型指标溯源

来源：`experiments/report.md`。

| 模型 | 平均分 | 最高分 | 最大瓦片 | 备注 |
| --- | ---: | ---: | ---: | --- |
| 正式 `rl_model.npz` | 2267.4 | 6780 | 512 | Phase D 修正后 best 检查点 |
| 旧模型备份 | 1445.7 | 5520 | 512 | 固定验证集 50 局，seed=12345，贪心 |
| 纯随机参照 | ≈1170–1200 | — | — | 同口径 |

第 5a 篇保留这些数值，并明确“RL 仍是无经验回放、无自适应超参的 on-policy 实现”。

## 5 500ms vs 1000ms

| 口径 | 值 | 证据 |
| --- | ---: | --- |
| 当前生产实现 | **500ms** | `v6_background.py`：`REPORT_INTERVAL_MS = 500`；`report_prefs_version=3` |
| 早期计划/旧文档 | 1000ms | 已被当前实现取代，不作为现状 |
| 回传语义 | 仅展示频率 | 不参与搜索、终止或预算 |

处理：第 6 篇（中）增加“版本口径”说明，明确以 500ms 为准；未修改代码去迎合旧文档。

## 6 HISTORICAL / UNVERIFIED 清单

| 项 | 原因 | 处理 |
| --- | --- | --- |
| 第 5a 篇 `8.5e-14` 最大误差 | 当前测试只断言 `TOL=1e-9`，未打印该值 | 保留为历史记录，注明本次未重印 |
| 第 5a 篇 `14279` 次采样 | 本次复跑为 `n=20000` | 更新为本次值，保留历史值对照 |
| 第 5b 篇提示层像素/ΔE/ΔL/通道/耗时 | 原始实验目录已在仓库清理中移除 | 整节加 `HISTORICAL / UNVERIFIED` 口径 |
| 第 5b 篇 3 档 DPR 越界=0 | 同上 | 纳入 HISTORICAL 口径 |
| 第 3 篇 V3 高 DPI 三档 | V3 无 DPI 截图/自动断言 | 改为适配建议，标记 UNVERIFIED |
| 第 4 篇实际帧率 | 无逐帧墙钟统计 | 改称“16ms 目标 tick”，不声称 60FPS |
| CSDN 公式/图片渲染 | 无 CSDN 预览环境与真实上传 URL | 结构检查通过；渲染与 URL 均 UNVERIFIED/UPLOAD_REQUIRED |

## 7 未执行项

- 未重跑微基准/搜索基准/同墙钟对局（仅核对原始报告，避免长时间占用机器）。
- 未训练或替换任何 RL 模型。
- 未修改 V1–V6 源码、正式存档或实验数据。
- 未做 Git 提交或推送。
