# V6 Background Continuous Solving and N-Interval Result Delivery — Trae Execution Specification

## 0. Mission and scope

Perform a **single complete execution** against the **actual local V6/V6.2 source**. Do not treat this document as proof that any code has already been changed. First audit existing implementation, reproduce the defect, then repair, test, and report. Preserve V1–V5 (read-only), real saves, RL models, historical experiments and Git history. Do not retrain, delete evidence, or auto-commit.

Project root: `E:\PyQt5_demo\2048`; Python: `E:\anaconda3\envs\2048\python.exe`; environment: `PYTHONNOUSERSITE=1`. Confirm paths and current module names from repository rather than assuming they are unchanged.

**Primary objective:** V6 background AI must continue the **current game** until natural terminal state, user pause/stop, or a separately explicitly configured global budget. It shall deliver the latest **committed** game result to the LEFT board **every N valid moves OR every N milliseconds**, selected as mutually exclusive reporting policies. The report interval is **never** a task termination budget. On pause/stop/natural end/budget completion, deliver and render final committed state, reconcile official save/history, and confirm child-process exit/ownership transitions.

## 1. Confirm current findings; do not silently assume them

Historical evidence:
- V6 GUI presently exposes Standard / Fast (formerly Extreme) / Background; solver strength Fast / Standard / Strong is **independent** of display/run mode.
- Existing background snapshots show active processing (e.g., 60 moves, 62.126 moves/s in a transient display) and board updates on pause, but not proof of safe terminal handoff.
- Older six-move Headless run was reported at 3.57 moves/s including startup; an extrapolated ~90 moves/s **is not** verified throughput.
- The background Worker has had prior stale ownership (`pid=37176`), process lifecycle/IPC bugs, and incomplete GUI end-to-end gates. Do not remove a lock or terminate a process without verified identity.
- Existing Headless state storage did not demonstrate complete official per-move history / undo-redo equivalence; classify this as an **unresolved hard gate** until tests prove otherwise.
- Historical Windows QtCore `0xC0000409` (`FAST_FAIL_FATAL_APP_EXIT` candidate) lacked the precise fatal message. Preserve crash instrumentation. Do not infer an exact Qt object root cause merely from the exception code.

Initial audit list (actual source locations may differ): `v6_background.py`, `v6_speed.py`, `headless/core.py`, `headless/game_loop.py`, `headless/worker_main.py`, `headless/ownership.py`, solver dispatch, GUI state model, save/history and tests. Locate all `200`, `max_steps`, `max_seconds`, `limits`, `resume`, `completed`, `game_over`, and checkpoint-related uses. Provide file:line call chains with evidence before modifying behavior.

## 2. User-facing design: exactly three run modes, two independent reporting policies

Keep **Standard**, **Fast**, **Background**. Do not resurrect the old animated Fast Demo mode or modify V5. Standard preserves native animations and delays; Fast is formerly Extreme (no movement/particle animation, no intentional inter-move delay, GUI updates); Background runs the current game in a Qt-free computing Worker with only periodic snapshot visualization in the GUI.

Keep algorithm selection, solver strength, and solving mode (one-step versus automatic) separate. Changing reporting policy must not change algorithm, search depth, backend, RNG, or save durability.

Under Background controls add:
- Section title: `结果回传`.
- Segmented or radio selection: `定时间` / `定步数` (mutually exclusive).
- `定时间`: N milliseconds; presets 500 / **1000 default** / 2000 / 5000; allow validated custom integer input if existing UI can support it safely. Reject 0, negatives, excessively small intervals; cap the allowed range in one place.
- `定步数`: N successful (effective) AI moves; presets 50 / 100 / **200** / 500 / 1000; optional validated custom integer input.
- Explanatory text: `后台持续求解；达到回传间隔后将已完成的最新棋盘显示在左侧。暂停、停止及结束立即同步。`
- Display both worker's cumulative moves and last successfully rendered revision; show last return age and actual backend/engine. Avoid noisy status panels and high-saturation color.
- Persist mode+N with versioned, idempotent migration without changing older solver-strength presets. Settings changes apply at a safe commit/report boundary without creating a second worker.

## 3. Precise scheduling semantics

Use **one reporting policy only** at a time, not `N steps OR T milliseconds, whichever occurs first`, unless a separate explicitly requested hybrid mode is introduced later.

**By steps:** after each atomic successful game move, when `total_committed_moves - last_delivered_moves >= N`, send a complete immutable snapshot representing the latest committed revision. Expected for N=200: at committed move 200, 400, 600... (not a forced stop or restart). Invalid/no-op suggestions do not count as effective moves. Pause/stop/end may return a partial interval (e.g., step 237).

**By time:** use `time.monotonic()` or `time.perf_counter()` to target an interval of N ms. At the deadline send the latest already-committed revision. If a long AI search is in progress, no partially applied move can be exposed. If a periodic heartbeat thread is used, it may send `computing` / unchanged revision to indicate liveness; distinguish this from a new-board report. Never interrupt native search unsafely merely to meet the UI deadline. Measure lateness, and document that N ms is a target, not a hard realtime guarantee.

The game loop continues independently of reporting events. Keep `batch_steps`, `session_steps`, `total_committed_moves`, `max_total_steps` and `time_budget` distinct. A former `max_steps=200` **must be traced** and, when it controls per-run termination incorrectly, changed to an internal batch/report unit or removed. No implicit 200/400/600-step termination. An explicitly configured global limit is a distinct, clearly labeled condition.

Recommended report payload: `protocol_version, message_type, session_id, game_id, worker_pid, sequence, revision, total_committed_moves, board[4][4], score, best_score, max_tile, game_status, backend_requested, backend_used, engine_used, native_skip_reason, timestamp_monotonic, search_metrics, checkpoint_revision, report_reason` (periodic_steps / periodic_time / pause / stop / terminal / explicit_budget / recovery). Ensure board/value bounds and JSON schema validation. Do not insert RNG state in every high-frequency visual report unless needed; final/checkpoint must preserve exact RNG state.

## 4. Render on LEFT board without applying the game twice

Worker is sole authoritative writer while in BG_RUNNING. The GUI is a **read-only observer**: render the validated reported board through a dedicated no-animation presentation API, NOT via `model.apply_move`, `_slide`, spawn, score mutation, game-history write, or undo-record creation on every periodic visual update. The GUI must not replay moves or draw fake transitions. Separate **presentation cache** from the **committed game state** and from archival writes.

All QWidget/QPixmap painting and visual-state application happens on Qt GUI thread. Use bounded queue/Qt queued signal; coalesce intermediate periodic snapshots to newest valid `(session_id, game_id, revision)` (monotonic revision); reject stale/replayed/foreign-session/corrupt messages. Do **not** coalesce away terminal/final/control messages. Show left board + score + max tile + backend progress consistently; include `已同步至第 N 步` or a similar subtle synchronization marker when current display trails worker progress.

Do not refresh on every effective move in Background. Treat GUI paint frequency, dispatch latency, queue depth and worker throughput as separate measurable metrics. Preserve standard/fast visual behavior.

## 5. Pause, resume, stop, terminal: transactional final handoff

Canonical event states: GUI_IDLE, HANDOFF_PREPARE, BG_WARMING, BG_RUNNING, BG_PAUSE_REQUESTED, BG_PAUSED, BG_STOP_REQUESTED, BG_FINALIZING, BG_COMPLETED, BG_ERROR. Every transition validated, idempotent where appropriate, and associated with a `session_id` and revision.

- **Start**: stop/retire in-flight GUI solver and settle any animation at a bounded safe boundary; create complete game snapshot incl. exact RNG state, current game id, score/best, revision, solver config, actual rules; checkpoint durably before handing ownership to Worker. Do not start from a new game.
- **Pause**: finish the current atomic move, persist final pause checkpoint, send `FINAL(status=paused)` with latest board/RNG/history revision. GUI verifies and renders the pause board; offer Resume without re-running the final move. Worker may remain idle with safe ownership or exit and be relaunched from checkpoint; document which approach and make controls consistent.
- **Resume**: continue same game id and monotonic revision/total moves/RNG, preserving solver strength and reporting policy. Do not reset to a 200-step limited task. Handle 199/200/201 moves and consecutive resumes.
- **Stop**: cooperative stop at atomic step boundary, durable final checkpoint, send `FINAL(status=stopped)`, GUI confirms no loss or duplicate commit and renders exact final board. Explicit receipt/ACK must be distinguished from actual Worker `EXITED`, OS exit code, and safe ownership release. A waiting child is not an exited child.
- **Natural game end**: distinguish no legal moves, reaching 2048, or continuing past 2048 according to CURRENT V6 rules/user setting; send forced terminal result even if interval not reached. Render final board, score, best score, cumulative moves, outcome, and restore user controls after ownership release. Don't redefine reaching 2048 as a loss or unconditional stop.
- **Explicit global budget** (if user enabled): report `budget_reached`, with final state, not `game_over`.
- **Crash or restart**: identify worker by PID + OS process creation time + image/command validation + session id + heartbeat; check durable checkpoint before releasing stale owner. Reattach safely or stop via supported control channel. No blind `taskkill /F`, no speculative lock deletion or second writer. Handle PID reuse and stale messages.

A report of `FINAL` is **not sufficient** to claim completion. Finalization requires correct official state/history, GUI acknowledgment, observed process lifecycle (`exited` and exit code if process ends), and proper ownership semantics. For a deliberately paused resident worker, explicitly record that Worker remains alive instead of claiming it exited.

## 6. Official save, undo/redo, and per-move history (hard release gate)

Audit existing V6 GUI persistence format and exact durability guarantees; determine whether normal gameplay commits each move. Isolated `staging` checkpoints alone do not prove equivalent official save/history/undo/redo behavior. Extract and reuse a Qt-free commit/repository layer if needed; avoid writing two incompatible sources of truth. The Worker (or a single dedicated serializer with enforced exclusivity) must commit every authoritative move according to the verified normal-game semantics before advertising that revision as committed.

Verify persisted content: game id, grid, score, best score, RNG full internal state, move number/revision, undo/redo, per-move history and game statistics. Reopening a saved game, manually playing one move after stopping, undoing and redoing must remain correct. Fault-inject crashes before/after atomic rename/fsync and during GUI/Worker handoff; demonstrate an unambiguous latest-valid-revision recovery policy. Do not weaken durability to boost throughput without separate explicit permission.

**Fail-closed:** if official-history or ownership integrity tests are not passing, keep Background labeled EXPERIMENTAL and block or isolate its use on a real production save; do not label it stable or set it as default.

## 7. Startup and native backend correctness

Native `backend='cpp'` primitives does **not** imply `engine_used='native'`. Capture requested/actual backend, engine and fallback cause. Preserve Python Reference/NumPy/Numba and existing Native routes; no new RL training or algorithm rewrite. Cold-start import/probe may take substantial time; instrument `ready/ack/warming/warmed/first_solve_start/first_solve_end` separately, with bounded diagnostic timeouts and thread dumps on suspect stalls. Prior 7.9KB IPC-limit hypothesis was disproved by size sweep; do not reintroduce it. Read both stdout and stderr asynchronously and continuously to avoid pipe backpressure, keep seq/ack/terminal ordering unambiguous, and do not silently swallow a fatal exception.

Do not broadly import every backend if it adds unnecessary 100s startup to the selected algorithm; measure and warm only the chosen path, with explicit progress states and fallbacks. Preserve Qt fatal capture logs (and WER where available); do not conflate Qt fatal crashes with Headless computation stalls.

## 8. Performance comparison protocol: 1000 ms versus 200 moves

Purpose: compare **reporting policies** under the same algorithms and reproducible game trajectories — not compare solver strength or silently swap backend.

Four bounded configurations with fixed game seeds/config and verified equivalent move trajectory where feasible:
A. Fast GUI (no animation; per-move live paint) — user-facing baseline.
B. Background with periodic board reporting every **1000 ms**.
C. Background with periodic board reporting every **200 committed moves**.
D. Background compute-only/no periodic board rendering (instrumented reference, not the main user mode).

Use identical solver, strength, backend_used/engine_used, checkpoint durability, starting board/RNG, maximum run budget for tests, and recording scope. Execute sequentially for performance fairness; never infer gains from two concurrently running GUI instances. If game finishes before 200 moves or other interval, the forced terminal report counts separately and is not a periodic event. For exact-200/400 boundary tests use deterministic controlled test states/fakes rather than falsifying normal gameplay.

Measure: cold startup/warming, first-result delay, pure search, board/apply, serialization/write/fsync, IPC send/receive, GUI paint, periodic snapshot count/bytes, effective moves per second, total game time, CPU, native memory peak, average/P95 (and if possible P99) reporting latency and stop latency. Use `perf_counter` timestamps with clearly defined non-overlapping time spans. Do NOT double-count checkpoint totals with their write/serialize subcomponents. Report that 62.126 moves/s was a transient screenshot reading; previous ~90 moves/s extrapolation from six moves is not a benchmark.

When GUI board updates every 1000ms, a historical transient 62.126 moves/s would visually correspond to ~62 moves per update; with every 200 moves it would be ~3.22s/update. These are illustrations only, **not measured current performance**. Benchmark with warmed 100/500/1000 valid moves only when feasible; enforce an explicit safe time cap and preserve incomplete/terminated cases as such.

## 9. Execution phases and gates

P0 / G0 — Source audit + baseline and safety snapshot. Verify V1–V5 hashes/readonly, official files backed up with hashes and test paths isolated. Find exact 200-step source and reproduce current behavior; no changes yet.

P1 / G1 — Normalize reporting policy and UI (`定时间 N毫秒` or `定步数 N步`) without modifying solver strength. Migration + validation + persistence tests.

P2 / G2 — Decouple session and report/batch budgets. Unit tests on 200/201/400/401 effective moves; time trigger tests with injected monotonic clock; correct natural terminal behavior.

P3 / G3 — Validated snapshot stream and left-board rendering. Replay/order/foreign session, coalescing, Qt main-thread enforcement, no GUI writes while Worker owns board; real screenshot proving updates while Worker continues.

P4 / G4 — Resume / pause / stop / terminal handoff, official-history/undo-redo, RNG and single-writer ownership; clean Worker `FINAL→ACK→EXITED/paused-resident` semantics; crash and restart tests. Hard gate.

P5 / G5 — Cold/warm, first-solve, protocol and resource diagnostics with real exit codes; retain Qt fatal capture. No blind timeout increase.

P6 / G6 — Sequential 1000ms-vs-200-moves-vs-fast-GUI fair tests; collect raw CSV/JSONL, proper units and unavailable metrics; real screenshots from V6.

P7 / G7 — Full V6 regression, safe restore/rollback, release report and manual Windows checks. Gates PASS/FAIL/PARTIAL/UNVERIFIED independently. Any G3/G4 fail => background stays experimental and not default.

Mandatory boundary matrix:
- N steps = 10, 50, 200, 1000; steps 199/200/201, 399/400/401, repeated Resume, stop before report, game ends before report.
- N time = 250, 500, 1000, 2000ms; long single search >N, monotonic-clock injection, no finished move, IPC backlog/out-of-order/duplicate reports.
- Start/pause/resume/stop/close/reopen, worker natural exit, abnormal worker death, GUI crash, legacy stale lock, PID reuse, ownership conflict, checkpoint corruption, disk write failures.
- Full official save / latest valid revision, history/undo/redo, best score, exact RNG, overflow/high-tile support, max score and victory flow.
- UI: standard and fast unchanged; left board visually updates from real background snapshots; immediately finalizes on natural end and stop. Verify no line clipping on standard Windows DPI and user-selected scaled DPI.

## 10. Final evidence and reporting format

At minimum return:
1. Root cause of 200-step cutoff, with exact code location and verified fix.
2. Before/after user interface snapshots and timing-policy values.
3. Changed file list and descriptions; V1–V5 hash/diff evidence.
4. Full run timeline with session/revision/total-moves and report reasons (every 1000ms vs 200 moves).
5. 4 scenarios: N=1000ms, N=200 moves, forced pause/stop, natural terminal; prove LEFT board always displays correct latest committed state at each boundary.
6. Verified formal save/history/undo/RNG guarantees and injected-failure recovery evidence.
7. Raw sequential benchmark CSV/JSONL, medians, averages, P95 and comparison against Fast GUI; cold/warm separated.
8. Actual Windows Worker PID, process start identity, stop/exit codes, ownership release, Qt logs, remaining risks.
9. G0–G7 summary with reasons and explicit FAIL/PARTIAL/UNVERIFIED; give safe rollback path. Never present an unfinished phase as PASS.

Do not resume V5/V6 dual-window race development. Do not add unrelated queue systems, training frameworks, new model libraries, parallel MCTS, or additional gameplay modes in this iteration.
