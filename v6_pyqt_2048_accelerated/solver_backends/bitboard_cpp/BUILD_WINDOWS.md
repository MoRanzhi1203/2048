# V6 C++ Bitboard 后端 · Windows 构建说明

本目录是 2048 V6 的 C++20 / pybind11 / 64-bit Bitboard 内核。指数编码：0=空格，
1..15 对应 2..32768；**方块达到 65536（指数 16）时后端显式抛 `BoardOverflowError` 并回退到
reference**，绝不静默截断。

## 1. 前置条件（Phase 0 已验证 READY）

| 组件 | 本机（实测） |
| --- | --- |
| MSVC | VS 2022 BuildTools，`cl.exe` 14.40.33807（Hostx64/x64） |
| Windows SDK | 10.0.22621.0 |
| CMake | 3.28.1 |
| pybind11 | 3.1.0（`E:\anaconda3\envs\2048\Lib\site-packages\pybind11`） |
| Python | 3.12.3（`E:\anaconda3\envs\2048\python.exe`，64bit） |

> `cl.exe` 不在 PATH，使用 **Visual Studio 生成器** 时 CMake 会自动定位，无需手动 `vcvars64.bat`。

## 2. 构建（Release）

在仓库根目录执行（PowerShell）：

```powershell
$env:PYTHONNOUSERSITE = "1"
$py  = "E:\anaconda3\envs\2048\python.exe"
$src = "e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated\solver_backends\bitboard_cpp"
$build = "$env:TEMP\v6_bb_build"

# 配置（绑定专用环境的 Python 与 pybind11）
$pbd = & $py -c "import pybind11;print(pybind11.get_cmake_dir())"
& "D:\CMake\bin\cmake.exe" -S $src -B $build -G "Visual Studio 17 2022" -A x64 `
    -Dpybind11_DIR="$pbd" -DPYBIND11_FINDPYTHON=ON -DPython_EXECUTABLE="$py"

# 编译
& "D:\CMake\bin\cmake.exe" --build $build --config Release

# 安装扩展（放入 Python 包目录，供 solver_backends 导入）
Copy-Item "$build\Release\bitboard_cpp.cp312-win_amd64.pyd" `
          "$src\bitboard_cpp.cp312-win_amd64.pyd" -Force
```

> 说明：CMake 已自动 `-Dpybind11_DIR`（未提供时从当前 Python 的 pybind11 包探测）。
> 源码使用 UTF-8 中文注释/字符串，CMake 已追加 MSVC 的 `/utf-8`。

## 3. 独立自测（不依赖 Python）

```powershell
& "$build\Release\bitboard_tests.exe"     # 期望输出 ALL TESTS PASSED，退出码 0
```

## 4. 验证导入与规则一致

```powershell
$env:PYTHONNOUSERSITE = "1"
& $py -c "import sys; sys.path.insert(0, r'e:\PyQt5_demo\2048\v6_pyqt_2048_accelerated'); import solver_backends.bitboard_cpp as p; m=p.load_extension(); print(m.available())"
```

再运行等价性测试（65536 行表 + 10,000 随机盘）：

```powershell
& $py -m unittest test_row_table test_backend_equivalence -v   # 在 v6_pyqt_2048_accelerated\tests 下
```

## 5. 失败时的诚实回退

若未安装 MSVC / CMake / pybind11，或平台不匹配、导入失败：
`solver_backends.dispatch` 会记录 `cpp` 后端为 `BUILD_BLOCKED`（附原因），
`solver_v6.solve` 自动回退到 reference，**不影响手动游戏与五策略**，也不伪造 C++ 速度数据。
