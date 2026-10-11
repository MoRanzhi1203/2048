# H9-0 基线与原始证据冻结清单（V6.1）

- 证据目录：`v6_pyqt_2048_accelerated/experiments/v6_1/20261011_195221/`
- 冻结时间：2026-10-11 19:52（本地）
- git HEAD：`0296ab2fb515a5c3fa9aa95ba7e5e631c954e97d`（branch=main）
- git status（改动前）：仅两个未跟踪的指令 md 文档；无已跟踪文件改动
- 解释器：`E:\anaconda3\envs\2048\python.exe`（Python 3.12.3），`PYTHONNOUSERSITE=1`
- 环境：numpy 1.26.4 / numba 0.60.0 / llvmlite 0.43.0；Windows-10-10.0.19042；16 逻辑核
- 本轮前置哈希：`source_hash_before.json`（27 文件）、`model_hash_before.json`（4 模型）、`environment.json`

## 1. 历史加速倍数 → 原始数据溯源

历史 `report.md`/`benchmarks/reports/summary.md` 声称的加速倍数，逐条对应原始运行目录：

| 声称 | 原始数据文件 | 批次时间 | 关键参数 | 后端编译 | 样本 |
| --- | --- | --- | --- | --- | --- |
| micro：cpp legal ~17× / evaluate ~7.2× / rollout(d40) ~14× | `benchmarks/reports/micro_20261011_190432/{micro.json,micro.csv}` | 2026-10-11 19:04 | boards.jsonl(48)、warmup=3、repeat=30、seed=20482048 | pyd `50ad7588…` | 48 盘 × 30 次 |
| 搜索：rollout 3.09× / expectimax 2.67× / mcts 1.84×，动作一致率 1.0 | `benchmarks/reports/search_20261011_191723/search.json` | 2026-10-11 19:17 | rollout(20×16,seed2048)、expectimax(prune=False,d3)、mcts(60sims,rd12) | 同上 | 48 盘/配置 |
| 同墙钟 smoke：rollout cpp 步耗时 29.08ms vs ref 79.85ms | `benchmarks/reports/pilot_smoke_20261011_191951/pilot.json` | 2026-10-11 19:19 | smoke 2 局/策略、max_moves=200、20ms/步 | 同上 | 2 局/配置 |
| Phase0 冒烟 | `benchmarks/reports/phase0_smoke_20261011_183959/smoke.json` | 2026-10-11 18:39 | — | 同上 | — |

- 以上四批均由**同一 pyd（SHA256 `50ad758805d0a9ba5356ba8f04c6c197d8f1f2c8f54712ed18c5785d229b825c`）**产生，参数与棋盘集 SHA 在各自 JSON 中可核（boards sha256 `538807f3…`）。**可溯源，故本轮将其作为“历史基线”对照，但不直接沿用为最终结论。**
- 关于“MCTS cpp 曾慢于 reference”的旧说法：**在当前工作区的历史原始数据中找不到对应底层记录**（`search_20261011_191723` 中 mcts cpp=1.837× 为正向）。该旧说法标记 **UNVERIFIED**，不作为本轮依据；本轮以**重新实测**（见 H9-4）为准。
- 历史 `backend_default.json` 的“cpp 全局默认”→ 本轮改为**分策略**（`backend_policy_v6_1.json`），旧文件保留不覆盖。

## 2. 本轮冻结的实际状态（改动前）

- 四后端均可用：reference（纯 Python，冻结 V5 `solver_2048.py`）、numpy、numba（nopython，cache=True）、cpp（MSVC2022 + CMake + pybind11 3.1，pyd 已构建，SHA `50ad7588…`）。
- 既有测试：V6 5 个测试模块共 **32 项全部通过**（本机重跑，见 `tests.log`）。
- 关键文件 SHA256 见 `source_hash_before.json`；V5 模型 4 份 SHA256 见 `model_hash_before.json`。
- 已知结构性事实（本轮复核确认）：
  1. C++ 暴露 `rollout_events`（原生整段 rollout）但**未被任何 Python 代码调用**（死接口）；且其空位枚举顺序为位序（列右→左），与 Python `empty_cells`（行主序左→右）**不一致**，故原位不可用于等价替换。
  2. `solver_v6.solve` 的 `legal_moves` 预检查在溢出 try/except 之外 → 含 ≥65536 的棋盘会让 cpp 路径**直接抛异常**而非回退。
  3. `solve` 的通用异常安全网在**发生异常的后端**上再次调用 `_heuristic_decision` → 原生异常会二次失败并冒泡。
  以上 2、3 为本轮定位到的**可重现缺陷**，已在 H9-3/H9-1 中最小修复（见 `audit.md`）。

## 3. 证据文件索引

- `git_before.txt` / `environment.json` / `model_hash_before.json` / `source_hash_before.json`（本清单配套）
- 后续：`correctness_results.json`、`profiles/`、`benchmarks/`、`backend_policy_v6_1.json`、`storage_isolation.json`、`gui_capture.jsonl`、`release_gates.json`、`final_report.md`、`audit.md`、`git_after.txt`、`*_hash_after.json`
