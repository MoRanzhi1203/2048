# V5.1 测试矩阵（test_matrix）

> 生成时间：2026-10-11 ｜ 关联改动：Phase H1–H5 ｜ 运行环境：Python 3.12.3 / numpy 1.26.4 / PyQt5 5.15.2

## 1. 测试套件清单与结果（改动后）

| 套件 | 路径 | 用例数 | 结果 | 说明 |
| --- | --- | --- | --- | --- |
| 求解核心 + 界面（v5） | `v5_pyqt_2048_solver/test_solver.py` | 72 | OK | 核心 22 + 界面 50（含 H1-D 输入不变性/随机流隔离、H3 过期结果标志） |
| MCTS 概率/回传 | `tests/test_mcts_chance.py` | 10 | OK | 含新增 `test_mcts_backprop_invariants`、`test_mcts_progressive_widening`、`test_mcts_progressive_widening_keeps_spawn_distribution` |
| Expectimax 精确参考 | `tests/test_expectimax_reference.py` | 10 | OK | 含新增 `test_expectimax_score_weight_root_gain` |
| RL 梯度/符号 | `tests/test_rl_gradients.py` | 8 | OK | 有限差分、价值头符号、共享层回传、采样 |
| RL 工程化 | `tests/test_rl_model_management.py` | 5 | OK | 新增：`test_rl_schema` / `test_rl_holdout_gate` / `test_rl_checkpoint` / `test_rl_inference_cache` / `test_rl_warm_start_resume_is_not_exact` |
| 五算法冒烟 | `tests/test_algorithm_benchmark_smoke.py` | 5 | OK | — |
| 跨版本存档恢复 | `tests/test_cross_version.py` | 41 | OK | v2–v5（含强杀恢复、锁、损坏恢复） |
| 主题化弹窗 | `tests/test_popups.py` | 17 | OK | 无 QMessageBox、DPI 裁切 |
| RL 自学习验证 | `tests/test_rl_selftrain.py` | 11/11 | PASS | 3a/3d 由源码字符串断言改为真实行为断言 |

**运行命令**

```bash
python v5_pyqt_2048_solver/test_solver.py            # 72
python tests/test_mcts_chance.py                     # 10
python tests/test_expectimax_reference.py            # 10
python tests/test_rl_gradients.py                    # 8
python tests/test_rl_model_management.py             # 5
python tests/test_algorithm_benchmark_smoke.py       # 5
python tests/test_cross_version.py                   # 41
python tests/test_popups.py                          # 17
python tests/test_rl_selftrain.py                    # 11 项
```

## 2. 新增/修改用例与目标对应

| 目标（H 阶段） | 对应用例 | 断言要点 |
| --- | --- | --- |
| H1 MCTS 根回传不变量 | `test_mcts_backprop_invariants` | `root_visits == completed == backpropagated`；根各方向访问次数和 == root_visits；sims∈{100,500,1000} × width∈{1,2,4,8,16,32}；width=1 时 `width_limit_rollouts>0` |
| H1 MCTS 渐进加宽 | `test_mcts_progressive_widening` | K(N) 生效；不变量保持；`chance_children ≤ Kmax·chance_nodes` |
| H1 加宽不改变 spawn 分布 | `test_mcts_progressive_widening_keeps_spawn_distribution` | 采样计数 p(2)≈0.9（2000+ 样本，容差 0.03） |
| H1 Expectimax 根口径 | `test_expectimax_score_weight_root_gain` | 根处有合并（gain>0）的盘面 × depth∈{1,2,3} × sw∈{0,0.5,1,2}，与独立精确参考 delta=1e-9 |
| H2 RL schema | `test_rl_schema` | shape/dtype/NaN-Inf 校验；缺 `_schema` 严格拒绝、`load_legacy_model` 接受；`_schema` 错误拒绝 |
| H2 RL holdout 门禁 | `test_rl_holdout_gate` | 三随机数家族互异；同模型自比差=0 且非“显著更优”；更差模型判为不改进；固定 holdout 可复现 |
| H2 RL 检查点 | `test_rl_checkpoint` | 原子写无 .tmp 残留；版本化备份 + 回滚；best/latest 落盘；元数据持久化；诊断字段存在 |
| H3 五算法身份 | `test_strategy_identity_maps_to_config` | 下拉框 `currentData` 与配置逐一对应；强度可用性 == has_presets |
| H3 生命周期 | `test_solver_gui_lifecycle` | job_id 自增；停止后线程回收；过期/棋盘快照不匹配结果被丢弃；快速重启稳定；运行中关窗不崩溃 |
| H3 过期结果不污染新任务 | `test_stale_result_does_not_clear_inflight_flag` | 旧 job_id 的结果/失败到达时，`_solve_in_flight` 保持 True、进度条不被改；仅当前 job_id 才收尾 |
| H1-D 输入不变性 | `test_solver_does_not_mutate_input_grid` | 五策略求解后入参网格逐位不变 |
| H1-D 随机数流隔离 | `test_solver_rng_stream_isolated` | 求解不消费全局 `random` 流；同 seed 的 MCTS 结果可复现 |
| H2.9 RL 推理缓存 | `test_rl_inference_cache` | 同文件二次命中同一对象（不重复读盘）；文件原子替换后自动失效重载；打印 cold/warm 延迟 |
| H2.5 resume 语义 | `test_rl_warm_start_resume_is_not_exact` | warm start 可复现；但与连续训练不逐位一致（确认未恢复 RNG → 非精确续训） |
| H5 RL 过期断言 | `test_rl_selftrain` 3a/3d | 每局恰触发一次参数更新（行为计数）；早停 + best/latest 落盘（真实行为） |

## 3. 预算与未覆盖项（UNVERIFIED）

- **轻量实验预算（本版门禁）**：`H4` 采用默认 **Pilot 5 局/策略**、收口**最多 10 局/策略**（每局 ≤400 步、搜索类 30ms/步）。已执行并归档（见 `report.md` §6 / `runs/<run_id>/results/`）。**不再要求每策略 100 局**。
- **更大样本统计比较（UNVERIFIED，非门禁）**：如需论文级显著性结论，需用户显式要求后另行设计更大样本；轻量结果不得外推为最终排名。
- **GUI 截图的 VISUAL_PASS**：需人工核对图像，自动化不授予（见 report.md 门禁状态）。
