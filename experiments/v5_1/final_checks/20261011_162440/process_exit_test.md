# V5.1 · 最终收口：最后窗口关闭后的真实进程退出验证（process_exit_test）

> run: `20261011_162440` ｜ 独立子进程（`subprocess.run(timeout=45)`）｜ 原始输出：`process_exit_test.txt`

## 1. 目的与场景

验证**关闭最后一个窗口后进程真实退出**（事件循环结束、无线程把进程挂住），覆盖两种情形：

- `idle`：空闲时关闭；
- `solving`：**求解进行中**关闭（最易残留求解线程/动画定时器）。

脚本镜像 `main()` 启动方式（`app.exec_()`），窗口以 `QTimer.singleShot` 关闭。

## 2. 实测结果

| 模式 | 子进程退出码 | 墙钟耗时 | `app.exec_()` 返回码 | 结束后线程 | Qt 销毁告警 |
| --- | --- | --- | --- | --- | --- |
| idle | **0** | 1.15s | 0 | 无 | **0** |
| solving（求解中关窗） | **0** | 1.41s | 0 | `solver_thread_alive=False`、`retired=0` | **0** |

关键 stdout：
```
APP_BEGIN mode=idle quitOnLastWindowClosed=True | APP_EXITED exec_code=0 elapsed=0.43s solver_thread_alive=False retired=0
APP_BEGIN mode=solving quitOnLastWindowClosed=True | APP_EXITED exec_code=0 elapsed=0.85s solver_thread_alive=False retired=0
```

## 3. 结论

`PASS`：最后窗口关闭后**进程在 ~1.4s 内真实退出**（退出码 0），无挂起、无残留运行线程、无 Qt 线程销毁告警；求解进行中关窗同样干净退出（`closeEvent` 有界等待回收线程）。
