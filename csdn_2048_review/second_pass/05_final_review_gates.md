# 第二轮最终质量门禁

## 1 交付清单

| 类别 | 路径 | 状态 |
| --- | --- | --- |
| 九篇第二轮定稿 | `csdn_2048_review/second_pass/articles/*.md` | 9 个 ASCII 文件，全部非空 |
| 增量台账 | `second_pass/01_incremental_issue_ledger.md` | 20 项 |
| 逐篇修改说明 | `second_pass/02_article_by_article_changes.md` | 含 452 增 / 317 删 / 105 变更块 |
| 技术一致性 | `second_pass/03_technical_consistency_check.md` | 含 500/1000 源码判定 |
| 发布检查 | `second_pass/04_csdn_publication_checklist.md` | 24 图、标签、摘要、待替换 |
| 图片位置检查 | `second_pass/06_image_position_check.md` | 24 张全部回到正文，附录区 0 |
| 公式排版检查 | `second_pass/07_formula_typesetting_check.md` | 3 篇含公式文章，结构 PASS / 渲染 UNVERIFIED |
| 门禁 | `second_pass/05_final_review_gates.md` | 本文件 |

第一轮 `csdn_2048_review/articles/` 保留未覆盖；`git diff --exit-code -- csdn_2048_review/articles` 返回 0。

## 2 门禁表

| 门禁 | 判定 | 依据 | 限制 |
| --- | --- | --- | --- |
| **SP-G0 输入与文件完整性** | **PASS** | 九篇输入在 P0 已记录 SHA-256（9/9）；第一轮稿无改动（git diff exit 0）；`blog/` 已按用户要求在最后一步同步为最新版 | 原始版仅保留于 Git 历史与第一轮审计记录 |
| **SP-G1 技术事实与源码一致** | **PASS** | 6b 500/1000 以源码为准；20 项增量修复；公式/代码未因润色损坏 | 历史测量仍为 HISTORICAL |
| **SP-G2 公式与代码完整性** | **PARTIAL** | H1/围栏/链接校验通过；`$$` 成对（01=35 对、05a=19 对、05b=3 对）；28 项算法测试 exit 0 | 未逐段执行 GUI/进程片段；CSDN 渲染未验证 |
| **SP-G3 实验与基准溯源** | **PARTIAL** | 6a 表格仍对应 `benchmarks/reports/summary.md`；6c 对应 E2E JSON；RL 对应 `experiments/report.md` | 本轮未重跑基准；提示层像素与 111s 原始日志不在工作区 |
| **SP-G4 跨文章一致性** | **PASS** | 术语三分（运行方式/求解强度/求解模式）、V5 无暂停、导航层级已修正 | CSDN 外链需发布后替换 |
| **SP-G5 CSDN 资源** | **PARTIAL** | 24 张图片全部存在；每篇 7 标签与摘要已给 | 无真实 CSDN URL（UPLOAD_REQUIRED）；在线公式渲染 UNVERIFIED |
| **SP-G6 编辑质量** | **PASS** | 合并短标题、删除重复合并代码、压缩重复布局、补足输入输出/生命周期/比较表；无新增套话 | 第 5b 篇仍保留少量必要 GUI 背景 |
| **SP-G7 文件交付** | **PASS** | 9 篇 + 7 份报告存在且非空；ASCII 文件名；校验脚本 exit 0 | 无 |
| **SP-G8 图片位置** | **PASS** | 24 张图片全部位于正文相关小节；`## 附：整窗截图` 0 处；每图有说明 | 图片 URL 仍待上传 |
| **SP-G9 公式排版** | **PARTIAL** | 块级对齐、长行拆分、符号统一、3 篇符号表完成；结构校验通过 | CSDN 在线 MathJax 渲染 UNVERIFIED |

**总体：PARTIAL**。技术内容与文件交付通过；未通过项全部来自外部依赖（CSDN 图片上传、在线公式渲染）和未重跑的大规模基准，已如实标记。

## 3 实际执行与退出码

| 检查 | 命令 | 结果 | 退出码 |
| --- | --- | --- | ---: |
| 第二轮交付校验 | 内联脚本（H1/围栏/链接/图片/禁用项） | 0 failures | 0 |
| 图片位置校验 | 内联脚本（24 图、附录区、说明文字） | 24/24 正文，附录 0 | 0 |
| 公式结构校验 | 内联脚本（`$$` 成对、环境闭合、符号表） | 01/05a/05b 通过 | 0 |
| 第一轮稿未被覆盖 | `git diff --exit-code -- csdn_2048_review/articles` | 无差异 | 0 |
| 原始博客哈希（同步前） | 与 `_audit/inventory.json` 对比 | 9/9 一致；随后按用户要求同步 `blog/` | 0 |
| 算法三套件 | `python -m unittest test_expectimax_reference test_mcts_chance test_rl_gradients` | `Ran 28 tests / OK` | 0 |
| 合并示例（第一轮） | `solver_2048.move_grid` | `[2,2,2,2]→8` 等 | 0 |
| 第一轮 202 项测试 | 第一轮已逐套件执行 | 95+28+5+5+41+17+11 = 202，全部 exit 0 | 0 |

说明：第二轮是编辑优化，没有修改 V1–V6 代码；本轮只重跑 28 项算法测试作为抽样，未重复执行 95 项 GUI 主套件，沿用第一轮 exit 0 证据。

## 4 自动校验项

- 九篇 H1 各 1 个；代码围栏全为偶数。
- 相对图片/链接在 `second_pass/articles/` 下全部存在。
- 24 个图片引用；无伪造 CSDN URL、无占位图；全部位于正文，附录汇总区 0。
- 公式：`$$` 成对（01=35、05a=19、05b=3）；`aligned/cases` 闭合；3 篇均有符号表。
- `REPORT_INTERVAL_MS = 500` 存在；“当前待发布版本是 500ms”存在；“早期设计目标…已被取代”存在。
- 无“无条件 60FPS”、无“跨文件单次原子提交”。
- `HISTORICAL` 标注仍在；22/22 E2E 与 202 测试证据保留。
- 输出目录与文件名全部 ASCII。

## 5 未验证与遗留

| 项 | 状态 | 处理 |
| --- | --- | --- |
| CSDN 在线公式/表格渲染 | UNVERIFIED | 发布前逐篇预览 |
| 24 张图片 URL | UPLOAD_REQUIRED | 上传后用真实 URL 替换 |
| 第 3 篇 V3 高 DPI | UNVERIFIED | 不写成本次实测 |
| 第 4 篇实际帧率 | UNVERIFIED | 只写目标 tick |
| 第 5b 篇提示层像素数据 | HISTORICAL | 保留标注 |
| 第 5a 篇 `8.5e-14` | HISTORICAL | 本次未重印 |
| 第 6b 篇 111s 原始日志 | HISTORICAL | 据代码注释记录 |

## 6 结论

第二轮完成了要求的增量精修：九篇均为完整可读稿，技术与源码一致，6b 的 500/1000 冲突已按“源码为准、设计目标留痕”收敛；24 张配图已全部移回正文对应小节，公式完成对齐、拆分与符号统一。第一轮稿、V1–V6 源码、存档与模型均未被修改；`blog/` 已按用户要求同步为最新版，未执行 Git 提交或推送。
