# 2048 V6 — Background UI Simplification and Fixed 1000 ms Reporting

## Trae Agent execution contract

Execute **all phases P0–P7 in one run** against the actual current V6/V6.1/V6.2 source tree. Implement changes, run tests, collect real screenshots and measurements, and report PASS / FAIL / PARTIAL / UNVERIFIED with evidence. Do not stop at advice, pseudocode, or a proposed patch. Do not mark missing visual or end-to-end tests PASS.

**Repository (Windows):** `E:\PyQt5_demo\2048` (verify the actual checkout before editing). **Interpreter:** `E:\anaconda3\envs\2048\python.exe`. Set `PYTHONNOUSERSITE=1` for tests and launches.

**Hard exclusions:** V1–V5 are read-only; do not modify their source, game states or dependencies. Preserve all real game saves, undo/redo history, highest scores, official RL models, and past experiments. Do not retrain RL, run excessive benchmarks, revive V5/V6 dual-window racing, install unrelated dependencies, delete existing staging/checkpoint files without identity checks, or auto-commit/push Git. Work with temporary isolated game-history paths for destructive tests. Do not modify the C++/Numba/NumPy search kernels unless a demonstrated regression specifically requires it.

## Product decision — definitive

V6 offers exactly **three run modes**: `standard` (标准), `fast` (快速; the original no-animation extreme path), and `background` (后台求解; existing true Headless process). Do not change separate **algorithm**, **solve strength** (快速/标准/强力), or **solve mode** (自动连走/单步建议) controls.

**Background reporting has a single fixed period: 1000 milliseconds.** This is a progress/board snapshot cadence, **NOT** a 1000 ms search budget, a 200-step stop condition, or a worker restart interval. Remove exposed N-step/N-time policy controls. Background solving continues with the same game, same RNG and same search settings until game termination, user pause/stop, or an explicitly existing and separately configured safety budget. Do not quietly introduce an artificial total step limit.

## P0 — Inspect and baseline before changes

1. Inspect the real V6 entrypoint, `v6_speed.py`, `v6_background.py`, `headless/game_loop.py`, `headless/worker_main.py`, `headless/ownership.py`, UI files, solver-hint overlay and particle implementation. Locate exactly where the most recent reporting-policy widgets are created and where their preferences/IPC limits are parsed.
2. Confirm the currently launched V6 executable and whether the background supervisor actually instantiates. Check imports and swallowed exceptions at the GUI constructor boundary (including the widgets referenced by `BackgroundPanel`). Do **not** interpret a missing panel as a deliberate design decision if construction failed.
3. Establish a baseline of screenshot, window width/height, scroll reachability, run-state controls, save semantics, active worker identity, and test results. Use a temporary history directory for any test game.
4. Identify which widgets were newly added **solely** for configurable reporting, versus essential existing controls. Do not indiscriminately delete the established solver status/logs or background lifecycle controls.

## P1 — Remove the reporting-configuration clutter

Remove from the V6 formal right-side solver panel:
- The standalone `结果回传` configuration group.
- The N-step/N-time switch, `1000 ms` selector/combobox and any editable interval widgets.
- The report progress/proportion bar (a reporting interval has no meaningful percentage of completion).
- Explanatory text and extra status bars dedicated only to the old reporting selector.
- Duplicate start/status elements introduced by the experimental reporting UI; retain **one** coherent background lifecycle control surface, not two overlapping command sets.

Retain in the established right column: algorithm, solve strength, solve mode, horizontal `标准 / 快速 / 后台求解` mode selector, a single coherent **开始 / 暂停 / 继续 / 停止** control set for background when appropriate, the existing solver status summary, normal history log, advanced options (if originally present), and footer operations (export/details/performance comparison). In standard and fast modes preserve the original start/stop flow. Do not accidentally leave only disabled buttons in background mode or make normal AI solve unreachable.

Consolidate background progress into the **existing** status area, e.g. `后台求解中 · 285步 · 4424分 · 最大512 · 43.9s`. Do not add another panel. Show `1000ms 更新` only if it adds value and fits, without forcing a new row. Use the existing muted beige/brown theme and typography; avoid bright accent colors, tiny clipped text, nested black strips and vertical layout overflow. Allow appropriate text wrapping/ellipsis and preserve access to the bottom buttons at common Windows DPI settings.

## P2 — Fixed 1000 ms snapshot reporting, continuous solve

1. Make the effective reporting policy internal and constant: `REPORT_INTERVAL_MS = 1000` (one authoritative source). Worker/GUI messages may retain compatibility with older fields where necessary, but the public GUI must not expose or persist choice of `steps` or arbitrary `time` intervals.
2. On config load migrate legacy values (`report_policy`, `report_steps`, `report_interval_ms` and similar inspected keys) to **effective fixed 1000 ms**. Perform versioned, idempotent migration; do not let stale UI prefs silently reactivate an N-step policy. Keep unrelated preferences untouched.
3. Use `time.monotonic()` or `perf_counter()` for scheduling. Every approximately 1000 ms of background runtime, send the latest **fully committed** snapshot (board, score, max tile, total effective steps, backend/engine actually used, game/session ID, monotonically increasing revision, timestamp, running state). If a single search lasts more than 1000 ms, send a heartbeat/working indication and apply the latest safe snapshot at the next step boundary; do not interrupt a partial search or fabricate a move.
4. Treat the 1000 ms period as a reporting target, not a hard real-time promise under CPU load. Avoid drift/large backlogs. Coalesce outdated progress frames; render at most the newest valid snapshot. Never block the worker waiting for every intermediate Qt frame.
5. Remove any `max_steps=200` / `max_total_steps=200` misuse if it is actually tied to reporting. Preserve optional **explicit total budget** semantics if they already exist separately. A report must not automatically move the session to completed, paused or stopped. No fresh worker process should be spawned per report.
6. Keep actual `backend_used`, `engine_used` and fallback reason honest; never label `cpp / python_kernel` as C++ Native entire-tree search.

## P3 — Left board updates and final-state handoff

1. During `background`, the Headless worker is the only authoritative writer of the current game. The GUI is a **read-only display mirror** until safe ownership handback. Prevent manual arrow moves, undo/redo, new game, load/save operations and conflicting hotkeys from mutating the same game while Worker owns it; explain disabled controls in existing UI, not a large extra text block.
2. On valid periodic progress, the Qt main thread performs a **direct no-animation render** of the latest committed board on the **left 4×4 board**, updates the header score/record and existing solver summary, without `model.apply_move()`, spawning a random tile again, or appending the same move to history. Validate `session_id`, `game_id`, `revision`, board shape/values and monotonic steps. Reject stale, duplicate and cross-session messages.
3. **Pause**: stop advancing at a safe step boundary, persist the exact checkpoint, force an immediate latest snapshot/handback and left-board update, set PAUSED; retain resume support.
4. **Continue**: resume the exact same game/RNG/history at the next move, not a new game, not another fixed 200-step task. No duplicate last move and no duplicate active worker.
5. **Stop**: request cooperative termination, persist final committed state, send FINAL, check GUI ACK, wait for worker process exit and release verified ownership; force immediate final left-board render. Do not claim STOPPED just because a request was sent. Do not blindly kill a PID or delete a live lock.
6. **Natural game end / configured overall budget**: bypass the 1000ms interval and force FINAL immediately. Render the true final board and end reason; honor the existing 2048 victory/continue policy. If IPC or worker crashes, recover only from a verified checkpoint and distinguish last persisted state from uncommitted progress.
7. **Official save semantics are a gate**: confirm the same board, score, best score, full RNG state, move history, undo/redo, reload and crash recovery as normal V6. Do not report background as stable if official per-move history remains incomplete. Avoid a fallback that displays a correct board while silently writing a divergent official save; fail visibly and keep the mode EXPERIMENTAL until resolved.

## P4 — Three-mode effects policy without changing V1–V5

| Behavior | Standard | Fast | Background |
|---|---|---|---|
| Move/merge animation | Original | Off | Off |
| Merge particles / merge bounce | Original | Off | Off |
| AI target-edge direction highlight (A) | On | On | On, refreshed on report/FINAL |
| Interior 3-channel directional flowing light (B) | Original animation | Preserve animation | Static state only, **no running flow timer** |
| Board display | Per step, animated | Per step, instantaneous | Snapshot every 1000ms / immediate FINAL |

Particle emitter suppression must happen **before allocation/timer scheduling** for fast/background, not merely by setting particle alpha to zero. Do not accidentally turn off direction light via a blanket `animations_enabled=False`. Preserve the existing exact 3 interior gap channels (not 2), within the original board rounded perimeter, without covering tile numbers. Respect dynamic versus static direction semantics: a *last executed move* is not necessarily the *next recommended move*. Do not show a stale or misleading next-move recommendation. Stop the hint animation timer in background, while allowing a static edge indicator when the snapshot actually supports the directional meaning.

Do not alter board geometry, tile sizes, board margins or existing V5 overlay code. Apply V6-only controls to inherited widgets. Clean old merge-particle objects on mode changes and prevent duplicate QTimers/QThreads.

## P5 — Layout and Windows screenshot acceptance

Produce **real screenshots from the running program**, not generated mockups, of:
1. V6 standard right panel and left board.
2. V6 fast mode: no merge particles, direction hint retained.
3. V6 background selected before start: **no standalone report configuration**.
4. V6 background actively running: 1000ms reports applied on left board and compact status.
5. V6 background paused, stopped and naturally ended: authoritative final board shown.

Check 100%, 125%, 150% DPI where controllable, normal/resized window and right-panel scroll. Verify no clipped status strips, hidden stop button, empty duplicate panel, horizontal overflow or bottom controls rendered off-screen. If high-DPI testing cannot be carried out on a real Windows environment, record UNVERIFIED rather than fake screenshots. Screenshot filenames must be ASCII-only.

## P6 — Functional, safety and performance gates

Use actual V6 interpreter and isolated game data. At a minimum verify:

- `standard/fast/background` mode switching, mode preference migration, no regression of algorithm strength or solve mode.
- Background fixed interval ~1000ms in controlled test; no visible N-interval controls; repeated report timestamps, rev, step, left-board score and max tile consistent.
- Continuous solve crosses 200/400 effective steps *without stopping due to reporting*. If natural game over occurs earlier, use an explicit deterministic test fixture for boundary coverage rather than alter 2048 rules.
- Pause at step boundaries; resume twice; stop at arbitrary point; natural end; UI close/reopen; session/PID identity, lock release, checkpoint retrieval, stale-event drop, FINAL/ACK/EXITED.
- Complete official save history and undo/redo semantics. Confirm no loss of RNG state, duplicate history records or unwarranted override of a real user save. Inject failures into checkpoint writes, IPC and worker exit; respect bounded retries and surface persistent failure.
- Standard retains particles, fast/background allocate and emit **zero** merge particles. All 4 AI directions are checked for edge/A and B three-channel geometry; background does not keep the B animation clock active.
- Run existing V6 unit regression and explicit IPC E2E tests; record commands, counts, skip reasons and true exit codes. Default-skipped IPC tests do **not** count as pass.
- Record comparable sequential runs of V6 fast GUI vs background (fixed 1000ms), with same initial board/RNG and same solver settings as far as possible. Disclose limitations when trajectories diverge. Separate solver, model, storage, IPC, GUI paint, initialization and total wall-clock timings. Do not promise a speedup target or reuse earlier 62 steps/s as new measurement.

**No code-only signoff**: a successful unit suite does not substitute for real background-GUI lifecycle verification. Keep unverified G3/G4 gates marked PARTIAL/FAIL/UNVERIFIED and background marked EXPERIMENTAL until fixed.

## P7 — Final report and safe delivery

Output in Chinese, with:
1. Actual baseline, discovered root causes, exact changed files/lines and why.
2. Before/after right-panel screenshot comparison; list each reporting UI component removed, confirm the 1000ms value is internal-only and that the original solver controls remain accessible.
3. Actual 1000ms report timeline (`time`, `session`, `revision`, `steps`, `score`, `rendered/dropped`) and final-state screenshots.
4. Mode-effect matrix with automated particle/timer evidence and 4-direction visual evidence.
5. Worker/IPC lifecycle results, checkpoint/official-history/undo/RNG evidence, failures and recovery results.
6. Performance breakdown, tested hardware/config, true commands/exit codes, PASS / FAIL / PARTIAL / UNVERIFIED gates, remaining risks.
7. Explicit statement that V1–V5, real saved games and RL models were not modified; no auto Git commit.

If a phase cannot be completed safely, stop destructive changes in that phase, keep existing formally reliable standard/fast path operational, and report the blocker without misrepresenting completion.
