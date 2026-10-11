# V5.1 · H8 收口：真实停止耗时分段定位（stop_latency_breakdown）

> run: `20261011_160625` ｜ 平台：Windows ｜ 离屏 Qt ｜ 解释器：`E:\anaconda3\python.exe`
> 方法：在**真实求解在途**时，用实例方法包装对 `_stop_solver / _finalize_session / _save_sessions / _shutdown_worker` 分段计时。
> 原始输出：`stop_latency_raw.txt`（修复前）、`stop_latency_after_fix.txt`（修复后）。

## 1. 结论（先给根因）

**约 950–1000ms 的停止耗时来自 `_save_sessions`（会话历史写盘），与线程/`_shutdown_worker` 无关。**

分段实测（修复前，mcts 在途）：

| 分段 | 耗时 |
| --- | --- |
| `_stop_solver` 总计 | **961ms** |
| └ `_finalize_session` | 960ms |
| &nbsp;&nbsp;&nbsp;└ `_save_sessions` | **959ms** |
| &nbsp;&nbsp;&nbsp;└ `_shutdown_worker` | **1.3ms** |
| 其余（按钮/指标/状态） | ~1ms |

`_shutdown_worker` 仅 ~1ms，说明**并非线程回收**造成；耗时几乎全部在 `_save_sessions`。

## 2. 为什么 `_save_sessions` 这么慢

- 本地会话历史文件 `v5_pyqt_2048_solver/solver_results/sessions.json`（**gitignored 运行期数据**，38 会话 / 11463 步）达 **3.1MB**。
- 原实现 `json.dump(self._sessions, f, ensure_ascii=False, indent=2)` 对大对象是**流式小写入**，实测：

| 写法 | 耗时 | 文件大小 |
| --- | --- | --- |
| `json.dump(..., indent=2)`（原） | **537ms** | 3,119,693 B |
| `f.write(json.dumps(..., indent=2))` | 436ms | 3,119,693 B |
| `f.write(json.dumps(..., separators=(',',':')))`（新） | **94ms** | 1,796,990 B |

> 每次停止都会**全量重写**历史文件，故耗时随历史线性增长；与选择哪种算法无关（expectimax/strong 同样 ~436ms）。

## 3. 最小修复

`v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` · `_save_sessions`：改为**紧凑序列化 + 单次大写入**：

```python
f.write(json.dumps(self._sessions, ensure_ascii=False, separators=(",", ":")))
```

- 输出仍为**标准 JSON**，`_load_sessions`（`json.load`）完全兼容；未改数据结构与保留策略。
- 未改动算法、未新增线程、未改模型。

## 4. 修复前后对比（真实在途停止）

| 算法/预设 | 修复前 stop_total | 修复后 stop_total | `_save_sessions` | `_shutdown_worker` |
| --- | --- | --- | --- | --- |
| mcts/strong | **961ms** | **677ms** | 959→**140ms** | 1.3→536ms |
| expectimax/strong | ~437ms | **~1ms** | 435→**~95ms** | ~1ms |

说明：修复前 `_save_sessions` 的 959ms **恰好覆盖**了 mcts 的 rollout 计算完成，导致 `_shutdown_worker` 只剩 1ms；修复后写盘变快，`_shutdown_worker` 才真正命中仍在运行的 worker，付出**有界**的 `SOLVER_STOP_WAIT_MS=500ms` 等待。因此 mcts 停止总时长 = 快写盘(~140) + 有界线程等待(~536) ≈ 677ms，**不再随历史增长 1s**。

## 5. 残留与建议

- `_save_sessions` 仍是**同步全量重写**，耗时随历史线性增长（紧凑后 ~94ms@1.8MB）。彻底消除需将持久化移出 GUI 线程或改为增量存储 —— **建议列入 V5.2**（本轮不做，避免在稳定性收口中引入新的持久化并发风险）。
- 未改动用户 `solver_results/` 历史数据。
