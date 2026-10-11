# 2048 V6 · 高性能计算后端（PyQt5）

> 在 V5.1 稳定成果之上，新增 Reference / NumPy / Numba / C++ (pybind11 Bitboard) 四类计算后端、
> 统一 API、严格等价测试与公平性能基准。V1–V5 源码与正式模型只读；V6 数据独立。

## 快速开始

```powershell
$env:PYTHONNOUSERSITE = "1"
$py = "E:\anaconda3\envs\2048\python.exe"

# 1) 启动 V6（默认后端 auto -> 有 C++ 则用 C++，否则回退 reference）
& $py v6_pyqt_2048_accelerated\v6_pyqt_2048_accelerated.py

# 2) 可选：切换默认后端（也可在 GUI「高级参数 → 计算后端」内切换）
$env:V6_BACKEND = "reference"     # auto|reference|numpy|numba|cpp
```

## 测试

```powershell
cd v6_pyqt_2048_accelerated\tests
& $py -m unittest test_row_table test_backend_equivalence `
                       test_search_equivalence test_gui_integration test_storage_isolation -v
```

## 基准

```powershell
& $py v6_pyqt_2048_accelerated\benchmarks\run_micro.py
& $py v6_pyqt_2048_accelerated\benchmarks\run_search.py
& $py v6_pyqt_2048_accelerated\benchmarks\run_pilot.py --mode smoke
```

## 构建 C++ 内核

见 [solver_backends/bitboard_cpp/BUILD_WINDOWS.md](solver_backends/bitboard_cpp/BUILD_WINDOWS.md)。

## 关键约束

- 不改 2048 规则 / 五策略定义 / 奖励 / 权重 / 随机分布；后端只换**计算**，不换算法。
- 位棋盘遇到 `>= 65536` 的方块**显式拒绝**并回退 reference（不静默截断）。
- V6 **不**训练、不替换 `rl_model.npz`；只读。
- 默认实验规模：Smoke 2 / Pilot 5 / Final-lite 10 局每配置；不跑 100/300 局硬门禁。
- 截图遵循 `docs/GUI_SCREENSHOT_STANDARD.md`；`tools/capture_gui.py --version v6 --scene ...`。
