# V5.1 · 最终收口：sessions.json 原子保存与故障回滚（atomic_save_rollback）

> run: `20261011_162440` ｜ 解释器：`E:\anaconda3\python.exe`
> 相关代码：`v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` · `_load_sessions` / `_save_sessions`

## 1. 确认的缺陷

原 `_save_sessions` 直接 `open(SESSIONS_FILE, "w")` **覆盖写主文件**：若写入中断（崩溃/断电/磁盘错误），主文件会被截断成**半截 JSON**；而 `_load_sessions` 遇 `json.JSONDecodeError` 直接 `return []` → **用户全部求解历史丢失**。

## 2. 最小修复（保持紧凑 JSON 格式与全部历史数据，不引入新存储架构）

- 保存：`tmp 写入(+flush+fsync) → 旧主文件 os.replace 转存 .bak → os.replace(tmp, 主文件)`（同盘原子替换；`.bak` 为回滚点，均为重命名，无数据拷贝）。
- 失败：任一步异常 → 清理 `.tmp`，**主文件/`.bak` 保持不变**（自动回滚，不产生坏文件）。
- 读取：主文件缺失/损坏时回退 `.bak`；均不可用才返回 `[]`。
- 输出仍为**紧凑标准 JSON**（`separators=(",",":")`），`_load_sessions` 兼容，未改变存储规模/目录结构。

## 3. 故障注入证据（`test_sessions_atomic_save_and_rollback`，实际执行）

| 步骤 | 注入/操作 | 断言 | 结果 |
| --- | --- | --- | --- |
| 1 | 首次保存 | 文件为**单行紧凑 JSON**；无 `.tmp` 残留 | PASS |
| 2 | 再次保存 | 生成 `.bak` 回滚点；主文件含 2 会话 | PASS |
| 3 | **故障A**：主文件写坏成 `{"半截"` | `_load_sessions` 由 `.bak` **回滚读取**（非空、返回 1 会话） | PASS |
| 4 | **故障B**：`os.replace` 注入 `OSError` | 主文件**逐字节不变**；无 `.tmp` 残留；仍可正常读取 | PASS |

命令：`python v5_pyqt_2048_solver/test_solver.py __main__.SolverGuiTest.test_sessions_atomic_save_and_rollback` → `Ran 1 test … OK`，日志含 `[H9] sessions atomic save + rollback: PASS (compact=True, bak_rollback=True, fault_safe=True)`。

## 4. 数据保护

- 测试全部在隔离临时目录进行；用户真实 `v5_pyqt_2048_solver/solver_results/sessions.json` **未改动**（38 会话 / 3,119,693 B，前后一致、有效）。
- 未改变历史会话内容、字段或截断格式。
