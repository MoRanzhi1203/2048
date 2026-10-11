# V5.1 · H8-0 源码与所有权审计（source_audit）

> run: `20261011_153920` ｜ HEAD: `ddbf0e5` ｜ 只读审计，未修改源码。

## 1. 线程与所有权模型（主线程 / worker 线程）

| 组件 | 线程 | 所有权 / 说明 |
| --- | --- | --- |
| `SolverMainWindow`（含 `_request_decision`/`_on_solver_result`/`_on_solver_failed`/`_stop_solver`/`_shutdown_worker`/`closeEvent`） | **GUI 主线程** | 所有 QWidget 状态只在此线程读写 |
| `SolverWorker`（`solve` 槽） | **worker QThread** | 由 `_ensure_worker()` 创建并经 `moveToThread`；`solved`/`failed` 跨线程信号（AutoConnection→Queued）投递回主线程 |
| `threading.Event` 取消令牌 | 跨线程共享 | `_start_solver` 创建；`SolverWorker.solve` 前后读取（`is_set()`） |
| `solver.solve(...)`（纯函数式搜索） | 在 worker 线程内同步执行 | 无 QWidget 访问；内部无取消轮询（见 §3） |

调用链：`on_solver_clicked → _start_solver → _request_decision →(signal solveRequested)→ SolverWorker.solve → solver.solve → solved/failed →(queued)→ _on_solver_result/_on_solver_failed`。

停止链：`on_solver_clicked → _stop_solver → _finalize_session → _shutdown_worker`（置取消令牌 → 断开请求连接 → `quit()+wait(3000)` → 未退出则转入 `_retired_threads` 并由 `finished → _collect_retired` 回收；**不使用 `terminate()`**）。

关闭链：`closeEvent → _stop_solver(silent=True) → super().closeEvent → _shutdown_worker()`。

## 2. 关键不变量（对照当前源码）

- `_on_solver_result` / `_on_solver_failed`：**先**校验 `_solver_running` → `job_id == _job_id` → 棋盘快照，**后**才清零 `_solve_in_flight`/进度条（`v5_pyqt_2048_solver.py` L1428–1487）。✅ 已满足 H8-2.1。
- 一次有效求解最多一次自动落子：`_request_decision` 在 `_solve_in_flight` 为真时直接返回；动画期间 `board_view.is_animating()` 亦会拦截。
- `job_id` 每次 `_start_solver` 单调自增（L1398）；`_board_sig` 记录发起时棋盘快照（L1420）。

## 3. 算法内部取消能力审计（H8-1.4 前置）

对 `solver_2048.py` 全文检索 `cancel`/`cancel_event`/`threading`：**无任何匹配**（`grep` 0 命中）。即 **MCTS / Expectimax / Rollout 内部循环不检查取消令牌**，不具备线程内协作式中途停止能力。

- 其可终止性来自**有界执行预算**：三者均以 `time_limit`（经 `solve()` 夹取到 `MAX_TIME_LIMIT=2.0s`）或有界 `simulations`/`rollouts` 收敛，并在超时返回 best-so-far（见 `_mcts_decision` 的 `while ... and (time.time()-start)<=time_limit`、`_expectimax_decision` 的 `expired()`）。
- 因此本轮**不宣称“即时协作式取消”**。可接受的层级定义（H8-1.4）：
  - `CANCEL_REQUESTED`：GUI 置 `threading.Event`（立即，主线程）；
  - `RESULT_DISCARDED`：worker 返回时检测到 token → 不 emit `solved`（结果不落地）；
  - `COMPUTATION_EXITED`：`solver.solve` 因**有界预算**返回（最坏 ≈ `time_limit`）；
  - `THREAD_CLEANED`：线程 quit/finished/回收。
- **未新增取消轮询**：本轮无证据表明需要改动算法评估/搜索决策；保持算法行为不变（符合禁止事项）。

## 4. 待验证风险（交由 H8-1/H8-2 实测）

1. `_shutdown_worker` 在 worker 仍处于同步计算时 `wait(3000)` 会**阻塞 GUI 主线程**最长达 3s（H8-2.6 关注点）——需实测其真实阻塞时长。
2. 迟到信号（queued 投递）是否可能污染新任务状态——需用 started/release 屏障确定性验证。
3. 关闭窗口时若计算未退出，是否会出现 `QThread: Destroyed while thread is still running`。

## 5. 模型哈希（H8-0，未变）

`rl_model.npz = ee4b370e67676bfb…`、`candidate = ee4b370e67676bfb…`、`prev = 724c4eea877421cf…`、`baseline/rl_model_v1.npz = 724c4eea877421cf…`（详见 `model_hash_before.json`）。
