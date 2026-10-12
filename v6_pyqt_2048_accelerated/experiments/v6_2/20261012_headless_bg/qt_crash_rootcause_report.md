# Qt5Core 0xC0000409 崩溃根因排查（本轮结论）

> 日期：2026-10-12　环境：`E:\anaconda3\envs\2048\python.exe`（对比 `E:\anaconda3\envs\pyqt`）
> 结论口径：**已证实的**与**仍未证实的**分开陈述，不越界下结论。

## 1. 已证实的事实（来自 Windows 事件日志 + WER，非推测）

Windows 事件日志共 16 条同族崩溃，**签名完全一致**：

| 字段 | 值 |
| --- | --- |
| 故障模块 | `Qt5Core.dll` 版本 5.15.2.0，时间戳 0x5fa4dd3b |
| 故障模块路径 | `<env>\Lib\site-packages\PyQt5\Qt5\bin\Qt5Core.dll` |
| 异常代码 | `0xc0000409`（STATUS_STACK_BUFFER_OVERRUN 编号，实际含义见下） |
| **异常数据** | **`0x0000000000000007`** |
| 异常偏移 | **`0x00000000000204e8`（16 次全部相同）** |
| 应用程序 | `python.exe`（3.12.3150.1013） |

关键判读：
1. `__fastfail` 的**参数 = 7 = `FAST_FAIL_FATAL_APP_EXIT`**。
   → 这不是内存越界、也不是 GS/stack-cookie 破坏（那会是 2/3/4），而是进程**主动 `abort()`**。
2. 触发指令位于 **Qt5Core 内部固定偏移 `0x204e8`**（16 次一致）→ 命中 Qt 自身的**致命退出路径**
   （`qt_message_fatal` / `QMessageLogger::fatal` → `abort()`），即**某处调用了 `qFatal()`**。
3. 崩溃分布在**两个不同的 conda 环境**（`envs\2048`、`envs\pyqt`）与**多个日期**
   （2026-10-10 22:42/22:43、2026-10-12 01:58–05:57），其中 10-10 与 10-12 01:58–02:01
   **早于本项目的任何改动**。
   → **这是环境级 Qt 5.15.2 致命退出，不是 V6 代码引入，也不是 2048 项目独有**。

**因此可以排除**：内存破坏、栈溢出、Qt 版本不匹配（两个环境都是 5.15.2）、本项目新增代码导致。

## 2. 仍未证实（本轮未取得决定性证据）

- **具体是哪一条 `qFatal` 消息**：崩溃时子进程 stderr/日志为空。
  原因：Qt 在 Windows 上致命消息默认走 `OutputDebugString`，**未安装 `qInstallMessageHandler` 时无人接收**；
  且 `faulthandler` 无法捕获 `__fastfail`。
- 两个主要候选（**都未被证实或排除**）：
  (a) PyQt5「槽函数抛出未捕获 Python 异常 → 调 `qFatal()`」路径（PyQt5 默认行为）；
  (b) Qt 内部致命断言，如 `QThread: Destroyed while thread is still running`、
      `QThread::wait: Thread tried to wait on itself`、`QObject` 跨线程 parent 等。
- 观察倾向（**弱证据，不作结论**）：单程序诊断（401 步自动连走 + 40 轮取消压力 + 关窗）**从未复现**；
  已记录的崩溃全部落在**同时运行两个 Qt GUI 进程**的时段（2026-10-12 05:45–05:57 双窗口竞赛）。
  → 更可能与「多 Qt 进程并发 + 线程/QThread 生命周期」相关，但**样本不足以下定论**。

## 3. 本轮交付：让「下一次崩溃」直接给出根因

新增 `diagnostics/qt_fatal_capture.py`（V6 专用，已接入 `v6_pyqt_2048_accelerated.py:main()`，默认常开）：
- **`qInstallMessageHandler`**：把 Qt 全部消息写入 `diagnostics/qt_crash/qt_messages.log`；
  **致命消息（`QtFatalMsg`）会带 `<<<QTFATAL>>>` 标记，并在 abort 之前把 Python 全线程栈一并落盘**；
- `faulthandler.enable(all_threads=True)` → `faulthandler.log`；
- `sys.excepthook` / `threading.excepthook` / `sys.unraisablehook` 兜底记录（覆盖候选 (a)）。

已验证可用（真实运行）：
```
installed -> ...\Temp\qtcap_xxx
status: {'installed': True, 'messages': 1}
[17:49:31] WARNING  QObject::startTimer: Timers cannot have negative intervals
```

关闭方式：`V6_QT_CAPTURE=0`；改目录：`V6_QT_CAPTURE_DIR=<dir>`。

## 4. 下一步（复现即定位）

1. 保持 `V6_QT_CAPTURE=1` 常开运行；**重点复现当时的条件**：同时运行 2 个 Qt GUI 进程并持续自动连走/频繁创建销毁定时器与线程。
2. 复现后直接读取 `diagnostics/qt_crash/qt_messages.log` 中 `<<<QTFATAL>>>` 后紧跟的文本与线程栈：
   - 若是 Python 栈 → 属于候选 (a)，按栈修对应槽函数（V6 侧加 try/except 或改用自有 excepthook；本模块已提供）。
   - 若是 Qt 文本（如 `QThread: Destroyed while thread is still running`）→ 属于候选 (b)，
     按 `_shutdown_worker` / `_retire_thread` / 定时器归属对象生命周期加固。
3. 若仍无法复现：在 Qt 消息为空的前提下，可改用 **WER 本地转储**（`LocalDumps` 注册表）
   抓 minidump，用 `cdb`/WinDbg 解析 `0x204e8` 的调用栈——这需要 Windbg 环境（当前未具备，标 UNVERIFIED）。

## 5. 本轮修改文件
- 新增 `v6_pyqt_2048_accelerated/diagnostics/qt_fatal_capture.py`
- 修改 `v6_pyqt_2048_accelerated/v6_pyqt_2048_accelerated.py`（`main()` 安装取证，5 行）
- 未改动 V1–V5；未提交 Git；未重训 RL。

## 6. 风险与边界
- 该崩溃**不影响**结论“V6 单程序稳定”：单程序侧仍未复现；但**多进程并发场景下仍可能触发**，
  且根因文本尚缺。
- 取证模块常开会写少量日志（单文件上限 4MB，超过自动滚动为 `.1`），不影响游戏逻辑与存档。
