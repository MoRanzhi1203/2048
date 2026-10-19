# 06 最终质量门禁（P5）

## 1 交付清单

| 类别 | 文件 | 状态 |
| --- | --- | --- |
| 基线 | `00_baseline_inventory.md` | 已生成 |
| 台账 | `01_issue_ledger.md` | 已生成（65 项） |
| 系列结构 | `02_series_structure_and_navigation.md` | 已生成 |
| 图片/公式 | `03_image_and_formula_audit.md` | 已生成（24 张图片） |
| 技术证据 | `04_technical_evidence_and_benchmarks.md` | 已生成 |
| 变更摘要 | `05_change_summary.md` | 已生成 |
| 门禁 | `06_final_quality_gates.md` | 本文件 |
| 九篇正文 | `articles/01…09`（9 个 ASCII 文件） | 全部非空、完整修订稿 |

## 2 门禁表

| 门禁 | 判定 | 依据 | 未通过/限制 |
| --- | --- | --- | --- |
| **G0 INPUT_INTEGRITY** | **PASS** | 九篇输入按 SHA-256 盘点；评审前后哈希一致；原文件未被覆盖 | 无 |
| **G1 FACT_AND_CODE** | **PASS** | 9 项 P0 全部修订：合并计分、终止条件、V2 原子写/CSV、RNG 限制、60FPS、脏矩形、202 测试、500/1000ms | 历史测量（8.5e-14、14279、提示层像素、111s）保留并标注 HISTORICAL |
| **G2 FORMULA_AND_SNIPPETS** | **PARTIAL** | 公式结构检查通过（`$$` 成对、矩阵/分段函数/argmax）；合并示例用纯逻辑内核实跑；代码围栏成对 | 未逐段执行所有代码片段（GUI/进程片段需要环境）；CSDN 公式渲染未验证 |
| **G3 BENCHMARK_PROVENANCE** | **PARTIAL** | 6a 表格逐项对应 `benchmarks/reports/summary.md`；6c E2E 对应 `cross_mode_e2e.json`；RL 指标对应 `experiments/report.md` | 本次未重跑微基准/对局；5b 提示层像素数据原始日志已不在工作区 |
| **G4 CROSS_ARTICLE** | **PASS** | 版本职责、术语、导航统一；第 1 篇“7 篇”已改；第 2/4 篇补齐链接；V5/V6“运行方式”差异明确 | CSDN 外链需发布后替换 |
| **G5 CSDN_ASSETS** | **PARTIAL** | 24 张图片全部存在并映射；公式结构检查通过 | 无真实 CSDN URL（`UPLOAD_REQUIRED`）；在线渲染 `UNVERIFIED` |
| **G6 EDITORIAL_QUALITY** | **PASS** | 第 1/2 篇删除嵌套“模块/数学模型/代码实现/逻辑说明”和多余分隔线；全文去除绝对化性能/可靠性表述；保留公式、代码与实验数据 | 第 5b 篇与第 3/4 篇仍有少量 GUI 背景重复（已局部精简） |
| **G7 FILE_DELIVERY** | **PASS** | 9 篇正文 + 7 份报告存在且非空；输出文件名 ASCII；围栏/本地链接校验通过 | 无 |

**总体结论：PARTIAL**。原因不是技术内容缺失，而是两类外部依赖无法在当前环境完成：CSDN 图片上传与公式在线渲染。所有无法验证的项目均显式标记，不用 PASS 冒充。

## 3 实际执行命令与退出码

| 检查 | 命令 | 结果 | 退出码 |
| --- | --- | --- | ---: |
| 交付校验 | `python %TEMP%\csdn_validate.py` | 见 `_audit/validation.log` | 0（修复后） |
| 合并示例 | `python -`（导入 `solver_2048`） | `[2,2,2,2]→8`、`[2,0,2,4]→4`、`[2,4,8,16]→0` | 0 |
| V5 主套件 | `python -m unittest test_solver` | `Ran 95 tests / OK` | 0 |
| 算法三套件 | `python -m unittest test_expectimax_reference test_mcts_chance test_rl_gradients` | `Ran 28 tests / OK` | 0 |
| RL 模型管理 | `python -m unittest test_rl_model_management` | `Ran 5 tests / OK` | 0 |
| 算法冒烟 | `python -m unittest test_algorithm_benchmark_smoke` | `Ran 5 tests / OK` | 0 |
| 跨版本 | `python test_cross_version.py` | `41/41 通过` | 0 |
| 弹窗 | `python test_popups.py` | `17/17 通过` | 0 |
| 自对弈 | `python test_rl_selftrain.py` | `11/11 通过` | 0 |

测试合计 202 条，全部 exit 0。

## 4 自动校验项

- 9 篇正文均存在且 >1 KB；6 份报告存在且 >500 B；`06` 为本文件。
- 输出目录与 `articles/` 下文件名全部为 ASCII。
- 每篇恰好一个 H1（排除代码块内的 `#` 注释）。
- 代码围栏数量为偶数。
- 全部相对图片/链接在真实项目中存在（按 `articles/` 解析）。
- 原文 SHA-256 与 `_audit/inventory.json` 一致。
- 禁止项扫描：无“共 7 篇”“第 7 篇”“REPORT_INTERVAL_MS = 1000”“无条件 60FPS”“跨文件单次原子提交”。
- 必需项：6b 含 `REPORT_INTERVAL_MS = 500` 与 500/1000 说明；6c 含 `22/22`；5b 含 `202`；2 含 `atomic_write_json` 与 `random.getstate`；1 含 `[2,2,2,2]`；4 含“整块棋盘重绘”；3 报告含 `UPLOAD_REQUIRED`。

## 5 结论与后续

- 技术事实错误已优先修复；无法复核的测量没有删除，也没有伪装成新结果。
- 九篇均保留原有核心技术内容（公式、代码、实验表、截图引用），并补上可追溯的证据口径。
- 发布前只剩两类动作：上传 24 张图片并替换 URL；在 CSDN 编辑器逐篇预览公式与表格。
- V1–V6 源码、正式存档、RL 模型与九篇原文均未修改；未执行 Git 提交或推送。
