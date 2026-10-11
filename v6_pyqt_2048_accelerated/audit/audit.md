# 2048 V6 Phase 0 环境审计报告

> 范围：环境隔离完善、依赖冻结、C++ 编译链验证、v1–v5 兼容性回归、基准准备。
> 本阶段**未**进入 V6 正式优化实现；未改动 v1–v5 逻辑/UI/算法/存档；未改动 `.gitignore`。
> 生成时间：2026-10-11　执行者：Trae Agent

---

## 1. 审计起点（只读基线）

| 项 | 值 |
| --- | --- |
| 仓库 | `E:\PyQt5_demo\2048` |
| Git HEAD | `2f6ca9bda02615fb9710d87a2647d8dfbc9f3ee1` |
| 分支 | `main` |
| HEAD 说明 | `docs(v5): 对齐 V5 现状并精简文档（移除 DPI 门禁与指令文档）` |
| 审前工作区 | 仅 1 个未跟踪文件（用户提供的 V6 指令 md），无已跟踪改动 |

基线快照见 [git_before.txt](git_before.txt)。

---

## 2. Phase 0-A：环境与 Python 路径审计

方法：`conda env list`、`conda config --show envs_dirs`，以及
`python -c "import sys,site,..."` 探针，分别在**设置**与**不设置** `PYTHONNOUSERSITE` 下运行，
原始输出见 [evidence/probe_isolated.json](evidence/probe_isolated.json) 与 [evidence/probe_bare.json](evidence/probe_bare.json)。

| 检查项 | 结论 |
| --- | --- |
| 环境 `2048` 是否存在 | 存在 |
| 实际路径 | `E:\anaconda3\envs\2048`（正确） |
| 解释器 | `E:\anaconda3\envs\2048\python.exe`（`prefix` == 该路径） |
| 版本是否满足基线 | 满足（见 §4 表格） |
| 用户级 site-packages 污染 | **存在**（`C:\Users\MSIPC\AppData\Roaming\Python\Python312\site-packages` 含 numpy/torch/pandas/scipy 等） |
| `PYTHONPATH` / `PYTHONHOME` | 均为空（无污染） |
| 同名环境冲突 | 无（`env list` 中 `2048` 唯一） |
| 环境目录写权限 | **无**（`E:\anaconda3\envs` 及其子目录对当前用户只读+执行） |

**关键事实（探针实测）**

- 设置 `PYTHONNOUSERSITE=1`：`enable_user_site=False`，user-site 不在 `sys.path`，
  `numpy` 来自 `E:\anaconda3\envs\2048\Lib\site-packages`，`import scipy` 报 `ModuleNotFoundError`。
- 不设置：`enable_user_site=True`，user-site 排在环境 site-packages **之前**，
  `numpy`、`scipy` 均从 `C:\...\Roaming\...` 加载（隔离被绕过）。

---

## 3. Phase 0-B：隔离修复

### 3.1 发现的问题

原 `deactivate.d` 脚本**无条件删除** `PYTHONNOUSERSITE`，会破坏调用方进入环境前已有的设置
（例如调用方原本设为 `0`，退出后被抹掉）。

### 3.2 修复内容

按 conda-forge `openssl_*` 脚本同款「保存原值 + 占位标记」模式重写 6 个文件：

| 文件 | 行为 |
| --- | --- |
| `etc/conda/activate.d/env_vars.ps1` / `.bat` / `.sh` | 若未保存过，则记录原值（未设置记 `__UNSET__`）；设置 `PYTHONNOUSERSITE=1` |
| `etc/conda/deactivate.d/env_vars.ps1` / `.bat` / `.sh` | 若存在保存值：原值 `__UNSET__` 则删除变量，否则**恢复原值**；随后清除标记变量 |

### 3.3 验证（ENV-04 / ENV-05）

证据：[evidence/verify_isolation.log](evidence/verify_isolation.log)

| 场景 | 结果 |
| --- | --- |
| `conda run -n 2048` | `PYTHONNOUSERSITE=1`，`ENABLE_USER_SITE=False`，numpy 来自环境 |
| 预先设 `PYTHONNOUSERSITE=0` → activate | 激活期间 `=1`，`ENABLE_USER_SITE=False` |
| 同上 → deactivate | **恢复为 `0`**（非删除），标记变量已清理 |
| 未设置 → activate | 激活期间 `=1` |
| 未设置 → deactivate | **恢复为未设置**，标记变量已清理 |

### 3.4 统一启动约定（未新增脚本）

仓库 `tools/` 下**不存在**等效启动脚本，因此按「优先采用标准启动方式」执行，不新增包装脚本：

```powershell
# 推荐
conda activate 2048 ; python --version
conda run -n 2048 python --version
# 直接使用解释器时必须显式隔离
$env:PYTHONNOUSERSITE = "1" ; & E:\anaconda3\envs\2048\python.exe --version
```

> 说明：未采用 `sitecustomize.py`。它虽能让「直接路径调用」也自动隔离，但会引入**隐藏副作用**
> （对所有子进程生效、难排查、与 conda 激活机制重叠），收益不足，故不使用。

### 3.5 过程中的一次失败（如实记录）

首次写入的 `.ps1` 含中文注释，而 PowerShell 5 以 ANSI 读取 `-File` 脚本，导致注释乱码并吞掉换行，
`.ps1` 出现 `Unexpected token '}'` 语法错误、激活路径隔离未生效。
改用**纯 ASCII** 内容重写后通过。相关环境脚本保持 ASCII 以避免编码风险。

---

## 4. Phase 0-C：依赖冻结与环境快照

产出目录：`v6_pyqt_2048_accelerated/audit/`

| 文件 | 内容 |
| --- | --- |
| [environment.json](environment.json) | python/隔离状态/sys.path/模块路径/平台/CPU/线程环境/qt |
| [conda_list.txt](conda_list.txt) | `conda list -p E:\anaconda3\envs\2048` |
| [pip_freeze.txt](pip_freeze.txt) | `pip freeze`（`PYTHONNOUSERSITE=1`，仅环境内 10 项，无 user-site 泄漏） |
| [pip_check.txt](pip_check.txt) | `No broken requirements found.` |
| [environment.yml](environment.yml) | `conda env export`（含 pip 段） |
| [os_cpu.txt](os_cpu.txt) | OS / CPU / 核心数 |
| [git_before.txt](git_before.txt) | Git HEAD / 分支 / 状态 / diff |

**冻结版本（实测，非引用历史）**

| 组件 | 版本 | 加载位置（截断） |
| --- | --- | --- |
| Python | 3.12.3 (conda-forge, MSC v.1938 64bit) | `E:\anaconda3\envs\2048\python.exe` |
| NumPy | 1.26.4 | `envs\2048\Lib\site-packages\numpy` |
| Numba | 0.60.0 | 同上 |
| llvmlite | 0.43.0 | 同上 |
| PyQt5 / Qt | 5.15.10 / 5.15.2 | 同上 |
| pybind11 | 3.1.0 | 同上 |
| pip / setuptools / wheel | 26.2.1 / 84.0.0 / 0.48.0 | 同上 |

平台：Windows 10 Pro 10.0.19042（x64）｜CPU：i7-11800H，8 核 / 16 逻辑处理器。
线程环境变量 `OMP/MKL/NUMBA/NUMEXPR_NUM_THREADS` **均未设置**（依赖库默认）。

> `pip freeze` 不是唯一复现手段：同时保留 `conda list`、`environment.yml`、`environment.json` 与 `boards.sha256`。

---

## 5. Phase 0-D：C++ 编译链

详见 [cpp_toolchain.json](cpp_toolchain.json)；原始构建/测试日志见 [evidence/cpp_build_test.log](evidence/cpp_build_test.log)。

| 组件 | 状态 |
| --- | --- |
| MSVC cl.exe | `D:\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.40.33807\bin\Hostx64\x64\cl.exe`（**不在 PATH**，需先 `vcvars64.bat`） |
| VS Build Tools | 2022 17.10.5（在 D 盘，非 C 盘） |
| Windows SDK | 10.0.22621.0（x64 `um` 库存在） |
| CMake | `D:\CMake\bin\cmake.exe` 3.28.1 |
| Ninja | `D:\...\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe` |
| pybind11 | 3.1.0（include / cmake_dir 可用） |
| Python 开发文件 | `Include\Python.h`、`libs\python312.lib`（x64） |
| 架构一致性 | MSVC HostX64/x64 == Python 64bit == pybind11，**一致** |
| 仓库既有构建脚本 | 无 |

**最小 pybind11 扩展验证**：模块 `p0_testmod` 成功编译为 `p0_testmod.cp312-win_amd64.pyd`，
从专用 Python 导入成功，**16/16 断言通过**：int 传参、u64（`2**64-1`/`2**63`）无截断、64 位移位、
64 位棋盘 encode/decode 往返、C++ 内 2048 行合并语义（`0x1111→0x22`、`0x0211→0x22`、`0x2221→0x231`）、
u64 元组返回。**结论：工具链 READY。**

> 诚实记录：首次运行有 **1 条测试期望值写错**（`move_row_left(0x2221)` 误写为 `0x31`）。
> 按 2048 规则手算应为 `0x231`（`[2,4,4,4]→[2,8,4,0]`），**C++ 源码未改**，未降低任何断言强度。
> 编译产物（`.pyd/.obj/.lib`）与源码均在系统临时目录，未写入仓库或游戏目录。

---

## 6. Phase 0-E：v1–v5 兼容性回归

命令（全部在专用环境、隔离开启、GUI 离屏）：

```powershell
$env:PYTHONNOUSERSITE = "1"
$env:QT_QPA_PLATFORM = "offscreen"
& E:\anaconda3\envs\2048\python.exe <test>
```

汇总见 [phase0_tests.log](phase0_tests.log)（原始逐项日志：系统临时目录 `p0_2048\tests\`）。

| 测试文件 | 计数 | 结果 |
| --- | ---: | --- |
| `v5_pyqt_2048_solver/test_solver.py` | 80 | OK |
| `tests/test_expectimax_reference.py` | 10 | OK |
| `tests/test_mcts_chance.py` | 10 | OK |
| `tests/test_rl_gradients.py` | 8 | OK |
| `tests/test_rl_model_management.py` | 5 | OK |
| `tests/test_algorithm_benchmark_smoke.py` | 5 | OK |
| `tests/test_rl_selftrain.py` | 11 | SCRIPT PASS |
| `tests/test_popups.py` | 17 | SCRIPT PASS |
| `tests/test_cross_version.py` | 41 | SCRIPT PASS |
| **总计** | **187**（118 unittest + 69 脚本校验） | **0 失败 / 0 跳过** |

与历史 187 项记录**数量一致**（该 187 仅为历史快照，非本次硬编码目标）。
测试入口未变化；未修改任何断言、未删除/跳过用例。

**存档影响（TEST-03）**

- 五个 `game_history/` 目录**无任何本时段写入**（按修改时间筛查）。
- `v5_pyqt_2048_solver/solver_results/exports/` 被 `test_solver.py` 导出用例写入
  `unittest_session.json` / `.csv` —— 这是该用例的**既有行为**（两文件均被 `.gitignore` 的 `solver_results/` 忽略），非本阶段新增行为。
- 真实最高分/历史对局/历史实验基线**未被修改**。

---

## 7. Phase 0-F：公平基准准备

规范：[../benchmarks/benchmark_spec.md](../benchmarks/benchmark_spec.md)｜清单：[../benchmarks/baseline_manifest.json](../benchmarks/baseline_manifest.json)

- 固定棋盘集合：`boards.jsonl`（6 组 × 8 = 48 盘，种子 20482048），
  sha256 `538807f3030b0bc924a4294db46b4bad274492297f13d80ae135d099a65811e7`，校验文件 `boards.sha256`。
  组别：`empty_ge10 / empty_5_9 / empty_le4 / near_death / symmetric / high_tiles`。
  编码：`cells` 为指数 0–15，`board` 为方块值（V5 内核输入）。**不使用任何用户存档。**
- 两类基准**分开报告**：Backend Microbenchmark 与 Solver End-to-End，禁止混合排名；
  明确「相同墙钟 ≠ 相同计算量」。
- 最小 smoke gate：`benchmarks/smoke_gate.py` 可运行，输出 `RESULT=OK`，
  报告见 `benchmarks/reports/phase0_smoke_20261011_183959/`（`smoke.json` + `smoke.csv`）。
  reference 后端可用；numpy / numba / cpp 如实标记 `available=false` 并给出原因。
- 本次 smoke **仅记录 reference 基线**，**不**声称任何 V6 加速。

---

## 8. Phase 0-G：环境目录权限审计（仅审计，未修改）

| 项 | 值 |
| --- | --- |
| `E:\anaconda3\envs` ACL | `Users:(OI)(CI)(RX)`；`Administrators:F`；`SYSTEM:F` |
| `E:\anaconda3\envs\2048` ACL | 同上（继承） |
| Owner | `BUILTIN\Administrators` |
| 当前用户写测试 | **拒绝**（`Access to the path ... is denied`） |

**结论：维持现状。** 本阶段需要的写操作已通过必要的 UAC 提权完成，未改动任何 ACL。

若后续希望减少提权次数，可考虑**仅对专用环境**的最小授权方案（本阶段**未执行**，需另行授权）：

```powershell
# 1) 先保存原 ACL（必须）
icacls E:\anaconda3\envs\2048 /save C:\Users\MSIPC\AppData\Local\Temp\acl_2048_before.txt /T
# 2) 仅对该目录授予当前用户修改权限（不影响父目录与其他环境）
icacls E:\anaconda3\envs\2048 /grant "MSI\MSIPC:(OI)(CI)M"
```

安全影响：该目录内任意代码（含第三方包 `setup.py`/构建脚本）将以当前用户身份可写；
建议仍需保留人工确认流程。回滚：`icacls E:\anaconda3\envs\2048 /restore C:\...\acl_2048_before.txt`。

---

## 9. 修改文件清单

**A. 仓库内（全部为新增，位于 V6 目录，未触碰 v1–v5 与 `.gitignore`）**

| 路径 | 原因 | 内容 | 验证 |
| --- | --- | --- | --- |
| `v6_pyqt_2048_accelerated/audit/audit.md` | 本报告 | 环境审计 | — |
| `v6_pyqt_2048_accelerated/audit/environment.json` | 冻结环境 | 版本/路径/隔离/平台 | 与实测一致 |
| `v6_pyqt_2048_accelerated/audit/conda_list.txt` | 冻结环境 | conda 包清单 | — |
| `v6_pyqt_2048_accelerated/audit/pip_freeze.txt` | 冻结环境 | pip 清单 | 仅 10 项，无 user-site |
| `v6_pyqt_2048_accelerated/audit/pip_check.txt` | 依赖一致性 | pip check | No broken requirements |
| `v6_pyqt_2048_accelerated/audit/environment.yml` | 复现 | conda env export | — |
| `v6_pyqt_2048_accelerated/audit/os_cpu.txt` | 机器信息 | OS/CPU/核数 | — |
| `v6_pyqt_2048_accelerated/audit/git_before.txt` | 基线 | git 状态 | — |
| `v6_pyqt_2048_accelerated/audit/cpp_toolchain.json` | C++ 报告 | 工具链 + 最小扩展结果 | 16/16 断言 PASS |
| `v6_pyqt_2048_accelerated/audit/phase0_tests.log` | 测试证据 | 187 项汇总 | 0 失败 |
| `v6_pyqt_2048_accelerated/audit/evidence/*` | 证据 | 探针/隔离/构建/smoke 日志 | — |
| `v6_pyqt_2048_accelerated/benchmarks/benchmark_spec.md` | 基准规范 | 公平基准约定 | — |
| `v6_pyqt_2048_accelerated/benchmarks/baseline_manifest.json` | 基准清单 | 固定条件/后端状态 | — |
| `v6_pyqt_2048_accelerated/benchmarks/boards.jsonl` + `boards.sha256` | 固定棋盘集 | 48 盘 + 哈希 | sha 校验通过 |
| `v6_pyqt_2048_accelerated/benchmarks/smoke_gate.py` | 最小 smoke gate | 可运行 | `RESULT=OK` |
| `v6_pyqt_2048_accelerated/benchmarks/reports/phase0_smoke_20261011_183959/*` | 运行产物 | JSON+CSV | — |

**B. 仓库外（conda 环境内，非项目文件）**

| 路径 | 修改 |
| --- | --- |
| `E:\anaconda3\envs\2048\etc\conda\activate.d\env_vars.{ps1,bat,sh}` | 重写为「保存原值」模式（Phase 0-B 修复） |
| `E:\anaconda3\envs\2048\etc\conda\deactivate.d\env_vars.{ps1,bat,sh}` | 重写为「恢复原值」模式（修复无条件删除缺陷） |

**C. 未修改**：v1–v5 源码/存档/模型/截图、`tests/`、`tools/`、`experiments/` 既有记录、`.gitignore`、系统 PATH、其他 conda 环境、用户级 site-packages、全局 pip 配置。

---

## 10. Gate 判定

| Gate | 验收内容 | 结果 | 证据 |
| --- | --- | --- | --- |
| ENV-01 | 专用环境路径正确 | **PASS** | §2，`environment.json` |
| ENV-02 | 核心依赖版本正确 | **PASS** | §4 |
| ENV-03 | 模块路径来自专用环境 | **PASS** | `probe_isolated.json` |
| ENV-04 | 用户级 site-packages 隔离生效 | **PASS** | §3.3 |
| ENV-05 | Conda 激活/退出行为正确（含恢复原值） | **PASS** | `evidence/verify_isolation.log` |
| ENV-06 | 环境基线已冻结 | **PASS** | §4 文件清单 |
| CPP-01 | MSVC 工具链可用 | **PASS** | `cpp_toolchain.json` |
| CPP-02 | Python 开发环境正确 | **PASS** | `Python.h` + `python312.lib`（x64） |
| CPP-03 | pybind11 最小扩展编译成功 | **PASS** | `evidence/cpp_build_test.log` |
| CPP-04 | `.pyd` 正确加载 | **PASS** | 同上 |
| CPP-05 | 64 位数据传递正确 | **PASS** | 16/16 断言 |
| TEST-01 | v1–v5 兼容性回归通过 | **PASS** | §6，187 项 0 失败 |
| TEST-02 | Numba nopython 编译通过 | **PASS** | §6 前序；环境内 `numba 0.60.0` |
| TEST-03 | 正式存档未被修改 | **PASS** | §6 存档影响；`game_history` 无写入 |
| BENCH-01 | 公平基准规则已确立 | **PASS** | `benchmark_spec.md` |
| BENCH-02 | 最小基准 smoke gate 可运行 | **PASS** | `RESULT=OK` |
| GIT-01 | 工作区无本次产生的非预期改动 | **PASS** | 仅新增 `v6_pyqt_2048_accelerated/` |

> 说明：Numba 目前在 Phase 0 仅验证「可导入且 nopython 编译成功」（前序检查 + 环境内版本确认）；
> V6 的 Numba 内核本身尚未实现，属后续阶段。

---

## 11. 下一阶段建议（不提前实施）

1. **V6-V1 独立应用骨架**：建立 `v6_pyqt_2048_accelerated/` 的 launcher 与 `solver_backends/api.py`、
   `reference.py`，显式注入 `RESULT_DIR/SESSIONS_FILE/game_history` 以隔离 V5 路径，并断言关键模块 `__file__`。
2. **V6-V2 规则等价门禁**：65536 行表穷举 + ≥10000 随机单盘等价（对照冻结 reference）。
3. **V6-V3 NumPy/Numba**：先 NumPy 等价内核，再 Numba `@njit(cache=True)` nopython，报告冷/热态。
4. **V6-V4 C++ Bitboard**：使用已确认的构建链（`vcvars64.bat` + CMake/Ninja 或 setuptools），
   指数范围 0–15；≥65536（指数 16）必须显式拒绝并回退。
5. **前置条件**：向专用环境安装新包仍需 UAC 提权（§8）；如需频繁迭代可再评估最小 ACL 授权。
6. **观察项**：`v5_pyqt_2048_solver/solver_results/exports/unittest_session.*` 会被 `test_solver.py`
   持续覆写（gitignored）；V6 基准产物目录是否需要加入 `.gitignore` 留待 V6 实施时决定。
