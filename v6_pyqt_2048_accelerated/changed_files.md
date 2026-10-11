# V6 变更文件清单

> 全部为**新增**，位于 `v6_pyqt_2048_accelerated/`；未修改 v1–v5 源码/存档/模型。
> 运行时目录 `game_history/`、`solver_results/` 已被 `.gitignore` 忽略，未列入下表（非交付物）。

## A. 新增（V6 交付文件）

| 路径 | 字节 |
| --- | ---: |
| `v6_pyqt_2048_accelerated/README.md` | 1735 |
| `v6_pyqt_2048_accelerated/audit/audit.md` | 16507 |
| `v6_pyqt_2048_accelerated/audit/audit_v0.md` | 4423 |
| `v6_pyqt_2048_accelerated/audit/conda_list.txt` | 2228 |
| `v6_pyqt_2048_accelerated/audit/cpp_binary_sha256.json` | 110 |
| `v6_pyqt_2048_accelerated/audit/cpp_toolchain.json` | 3209 |
| `v6_pyqt_2048_accelerated/audit/environment.json` | 2801 |
| `v6_pyqt_2048_accelerated/audit/environment.yml` | 1121 |
| `v6_pyqt_2048_accelerated/audit/evidence/cpp_build_test.log` | 1029 |
| `v6_pyqt_2048_accelerated/audit/evidence/fix_isolation2.log` | 659 |
| `v6_pyqt_2048_accelerated/audit/evidence/probe_bare.json` | 1920 |
| `v6_pyqt_2048_accelerated/audit/evidence/probe_isolated.json` | 1753 |
| `v6_pyqt_2048_accelerated/audit/evidence/smoke_gate.log` | 645 |
| `v6_pyqt_2048_accelerated/audit/evidence/verify_isolation.log` | 689 |
| `v6_pyqt_2048_accelerated/audit/git_before.txt` | 512 |
| `v6_pyqt_2048_accelerated/audit/git_v6_after.txt` | 411 |
| `v6_pyqt_2048_accelerated/audit/git_v6_before.txt` | 810 |
| `v6_pyqt_2048_accelerated/audit/gui_capture.jsonl` | 6060 |
| `v6_pyqt_2048_accelerated/audit/model_hash_after.json` | 454 |
| `v6_pyqt_2048_accelerated/audit/os_cpu.txt` | 180 |
| `v6_pyqt_2048_accelerated/audit/phase0_tests.log` | 1216 |
| `v6_pyqt_2048_accelerated/audit/pip_check.txt` | 34 |
| `v6_pyqt_2048_accelerated/audit/pip_freeze.txt` | 265 |
| `v6_pyqt_2048_accelerated/audit/screenshots_sha256.json` | 511 |
| `v6_pyqt_2048_accelerated/audit/v5_sha256.json` | 3823 |
| `v6_pyqt_2048_accelerated/audit/v6_tests.log` | 493 |
| `v6_pyqt_2048_accelerated/benchmarks/_bench_common.py` | 4940 |
| `v6_pyqt_2048_accelerated/benchmarks/backend_default.json` | 1248 |
| `v6_pyqt_2048_accelerated/benchmarks/baseline_manifest.json` | 2926 |
| `v6_pyqt_2048_accelerated/benchmarks/benchmark_spec.md` | 4207 |
| `v6_pyqt_2048_accelerated/benchmarks/boards.jsonl` | 10055 |
| `v6_pyqt_2048_accelerated/benchmarks/boards.sha256` | 65 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/micro_20261011_190432/micro.csv` | 36722 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/micro_20261011_190432/micro.json` | 14056 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/phase0_smoke_20261011_183959/smoke.csv` | 2028 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/phase0_smoke_20261011_183959/smoke.json` | 2288 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/pilot_smoke_20261011_191951/pilot.csv` | 1253 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/pilot_smoke_20261011_191951/pilot.json` | 11082 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/search_20261011_191723/search.csv` | 719 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/search_20261011_191723/search.json` | 6700 |
| `v6_pyqt_2048_accelerated/benchmarks/reports/summary.md` | 3678 |
| `v6_pyqt_2048_accelerated/benchmarks/run_micro.py` | 6256 |
| `v6_pyqt_2048_accelerated/benchmarks/run_pilot.py` | 7230 |
| `v6_pyqt_2048_accelerated/benchmarks/run_search.py` | 5577 |
| `v6_pyqt_2048_accelerated/benchmarks/smoke_gate.py` | 6729 |
| `v6_pyqt_2048_accelerated/changed_files.md` | 8738 |
| `v6_pyqt_2048_accelerated/future_roadmap.md` | 1566 |
| `v6_pyqt_2048_accelerated/known_issues.md` | 2669 |
| `v6_pyqt_2048_accelerated/report.md` | 7491 |
| `v6_pyqt_2048_accelerated/screenshots/full_collapsed.png` | 27280 |
| `v6_pyqt_2048_accelerated/screenshots/full_game.png` | 50412 |
| `v6_pyqt_2048_accelerated/screenshots/full_solver.png` | 61514 |
| `v6_pyqt_2048_accelerated/screenshots/full_start.png` | 36828 |
| `v6_pyqt_2048_accelerated/solver_backends/__init__.py` | 917 |
| `v6_pyqt_2048_accelerated/solver_backends/api.py` | 6474 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/BUILD_WINDOWS.md` | 2696 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/CMakeLists.txt` | 853 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/__init__.py` | 1144 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/bindings.cpp` | 4865 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/bitboard.cpp` | 9516 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/bitboard.hpp` | 2308 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/bitboard_cpp.cp312-win_amd64.pyd` | 186368 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp/tests.cpp` | 3435 |
| `v6_pyqt_2048_accelerated/solver_backends/bitboard_cpp_backend.py` | 3512 |
| `v6_pyqt_2048_accelerated/solver_backends/dispatch.py` | 5874 |
| `v6_pyqt_2048_accelerated/solver_backends/events.py` | 2176 |
| `v6_pyqt_2048_accelerated/solver_backends/numba_core.py` | 11979 |
| `v6_pyqt_2048_accelerated/solver_backends/numpy_core.py` | 10350 |
| `v6_pyqt_2048_accelerated/solver_backends/reference.py` | 2680 |
| `v6_pyqt_2048_accelerated/solver_v6.py` | 27115 |
| `v6_pyqt_2048_accelerated/tests/test_backend_equivalence.py` | 8127 |
| `v6_pyqt_2048_accelerated/tests/test_gui_integration.py` | 2952 |
| `v6_pyqt_2048_accelerated/tests/test_row_table.py` | 2784 |
| `v6_pyqt_2048_accelerated/tests/test_search_equivalence.py` | 3641 |
| `v6_pyqt_2048_accelerated/tests/test_storage_isolation.py` | 3715 |
| `v6_pyqt_2048_accelerated/v6_pyqt_2048_accelerated.py` | 9835 |
| `v6_pyqt_2048_accelerated/功能说明.md` | 4901 |

## B. 修改（V6 适配，仅新增 v6 条目）

| 路径 | 修改 |
| --- | --- |
| `tools/capture_gui.py` | 在 `VERSIONS` 中登记 `v6`（复用 v5 场景/文字清单），未改动 v3/v4/v5 条目 |

## C. 模型哈希（前后一致）

| 模型 | SHA256 |
| --- | --- |
| `v5_pyqt_2048_solver/rl_model.npz` | `ee4b370e67676bfb42b43eb4df01e895c5bf92935adc16869eb135f9f891dc40` |
| `v5_pyqt_2048_solver/rl_model.candidate.npz` | `ee4b370e67676bfb42b43eb4df01e895c5bf92935adc16869eb135f9f891dc40` |
| `v5_pyqt_2048_solver/rl_model.npz.prev.npz` | `724c4eea877421cf728fdaa56b7e8c710d98accf6c8a13ea69d9c0aa5ee9f4f9` |
| `experiments/baseline/rl_model_v1.npz` | `724c4eea877421cf728fdaa56b7e8c710d98accf6c8a13ea69d9c0aa5ee9f4f9` |

## D. 截图 SHA256

| 文件 | SHA256 |
| --- | --- |
| `v6_pyqt_2048_accelerated/screenshots/full_collapsed.png` | `6846c34c1a4f328df8f51447d8c11f951f39e2b01755c9a739a6b29ea8bf4535` |
| `v6_pyqt_2048_accelerated/screenshots/full_game.png` | `15822b3ee2c551fc18f49f70ea066922f7c963d719b11839774631145000ae15` |
| `v6_pyqt_2048_accelerated/screenshots/full_solver.png` | `d26d19e9bcfc0f9512b88ad2bcb0c752924fbb91e04676f99c0f93848b43cd35` |
| `v6_pyqt_2048_accelerated/screenshots/full_start.png` | `9ab3365454f3316821d45c580174cd8937a48f238969c56bebadcf2bac98011d` |

## E. C++ 产物 SHA256

- `bitboard_cpp.cp312-win_amd64.pyd`: `50ad758805d0a9ba5356ba8f04c6c197d8f1f2c8f54712ed18c5785d229b825c`

## git status（工作区）

```
M tools/capture_gui.py
?? "2048_V6_\345\237\272\344\272\216V5_1\347\250\263\345\256\232\347\211\210_\351\253\230\346\200\247\350\203\275\345\220\216\347\253\257\344\270\216\345\205\254\345\271\263\345\237\272\345\207\206_Trae\346\233\264\346\226\260\345\256\214\346\225\264\346\214\207\344\273\244.md"
?? v6_pyqt_2048_accelerated/
```
