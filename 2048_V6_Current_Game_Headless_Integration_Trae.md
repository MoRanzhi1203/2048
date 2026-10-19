# 2048 V6 Current-Game Headless Solver Integration — Trae Execution Plan

> Project: `E:\PyQt5_demo\2048`  
> Python: `E:\anaconda3\envs\2048\python.exe`  
> Environment: `PYTHONNOUSERSITE=1`  
> Scope: **V6/V6.2 only**. V1–V5 read-only. No automatic Git commit, no RL retraining, no deletion or overwrite of historical experiments.  
> Execution style: **one complete implementation run**, with phased gates, real tests, reversible changes, and truthful PASS / FAIL / PARTIAL / UNVERIFIED reporting.

## 0. Core decision and non-goals

Implement exactly **three independent V6 presentation/execution modes**:

1. `standard` / 标准 — same existing full animation and normal delay; real-time GUI board.
2. `fast` / 快速 — use the current `extreme` behavior: no move animation, no decorative particles during AI auto-play, zero intentional inter-step wait, GUI board still updated; solver budget unchanged.
3. `background` / 后台求解 — continue the **currently open game**, using a real GUI-free Headless game loop in a separately managed worker process, with infrequent progress messages and no per-move QWidget rendering; solver budget unchanged.

Do **not** introduce an independent experiment game as the default background semantics. Do **not** introduce a task queue, multi-user service, training framework, benchmark farm, or V5/V6 dual-window race. Do not alter V5 code merely because V6 inherits V5 GUI. Keep existing AI algorithm selection, solver strength (快速/标准/强力), and solver mode (自动连走/单步建议) as three separately controlled concepts.

**Important naming**: The old solver-strength drop-down currently labeled `运行方式` with `快速/标准/强力` is NOT the new run-speed selector. Rename that label `求解强度` without changing preset mappings. Rename the old `模式` label `求解模式`, where appropriate. New `运行方式` or `运行速度` has `标准 / 快速 / 后台求解` exclusively. Prefer a visible segmented selector in the main AI panel, not hidden in advanced controls. If width is insufficient, use a compact, clearly labeled arrangement that leaves all modes accessible without ambiguity.

## P0. Reality audit, rollback boundary, and data safety

1. Read actual V6 code, especially `v6_pyqt_2048_accelerated.py`, `v6_speed.py`, `solver_v6.py`, solver panel, model move/history/storage implementation, existing single-instance lock and crash recovery code. Confirm which behavior is in V6 versus inherited V5. Do not assume class or method names solely from this document.
2. Read previous diagnosis and performance evidence under `experiments/v6_2/20261012_v6_only_opt/` when present. Historic observations: V6 GUI modes approximately standard 2.05, former fast 2.34, former extreme 6.62 valid moves/s in ~20-second observations. These are historical, workload-dependent results; not a new speed guarantee. Former extreme `anim_ms` included instant apply, likely persistence; `refresh()` timing does not equal Qt `paintEvent` time.
3. Record a V6 source manifest and current settings/persistence locations, and record read-only V1–V5 source hashes before modification. Protect actual game archives, session JSON, experiments, official RL models, and trained checkpoints. All tests use isolated temporary history/session roots.
4. Archive the former race artifacts already moved to V6 archive; do not restore them to the active runtime. If an unexpected active comparison import exists, remove its runtime reference without deleting its archive.
5. Establish rollback for V6-only edited files and user preferences. Do not auto-commit Git and do not delete existing files to force single-instance admission.

**Gate G0:** real entry points and state transitions identified; protected paths enumerated; V1–V5 read-only baseline captured.

## P1. Three-mode semantic migration and formal GUI integration

1. The original `standard` mode stays exactly the same in normal game use.
2. **Remove the OLD fast-demo behavior**, not merely its label. Reuse the old `extreme` no-animation implementation as the NEW `fast`; make behavior and reporting accurately say `fast`, not `extreme`.
3. Introduce `background` as a third execution mode, not another solver-strength preset.
4. Version persisted settings so old values are migrated exactly once and idempotently:
   - old `standard` -> new `standard`
   - old `extreme` -> new `fast`
   - old `fast` (animated faster-demo) -> new `standard` (safe fallback because its semantics differ from new fast)
   - unknown/broken settings -> `standard`, log the reason
   Use a schema/version indicator so a new `fast` is not repeatedly remapped to `standard` on subsequent launches. Save with safe atomic write, preserve unrelated preferences, test restart persistence.
5. Insert a **visible three-option control** adjacent to algorithm and strength controls. The selection itself must not mutate the algorithm, evaluation weights, search depth, time budget, number of rollouts, or RNG parameters. Selected and running/applied mode should be distinguishable if a change is pending.
6. During an active solver run, change mode only at a legal handoff boundary. Do not terminate a live solver QThread unsafely, invoke board mutation twice, or leave a stale `QTimer.singleShot` job. For background transitions, drain/cancel outstanding solver and animation effects, then transfer ownership atomically. If safe hot switching cannot be proven, explicitly require pause or stop before entering/leaving background and disable unsafe controls with explanation.
7. Do not let `background` silently start a new game. A `single` hint request cannot silently turn into unlimited auto-play; provide an explicit interaction contract: for current-game background **auto-play only**; if in single mode, ask to switch to auto or disable background selection.

**Gate G1:** all three modes visible in the V6 normal app; strength dropdown unchanged; legacy migration/restart works; no hidden or duplicate mode state.

## P2. Minimal Headless core — current game, no QApplication

Build a small reusable **pure game-loop module** within V6 (e.g., `headless/game_loop.py`) with no imports of `QApplication`, `QWidget`, `QTimer`, GUI subclasses or GUI paint routines. Import only existing game-state and solver pieces needed for game rules and solving, or extract a minimal V6-specific adapter if the inherited model has GUI/storage side effects. Reuse existing solver APIs; do not rewrite solver algorithms.

A per-step loop must:

1. Accept an immutable initial snapshot of the current 4x4 grid, score, game status, relevant best score/metadata, **exact RNG state**, per-game identifier, monotonically increasing game revision, and solver algorithm/options. If there is a state version or game-rule flag, carry it as well. Serialize/restore Python `random` state losslessly (or use a dedicated explicitly documented engine RNG with verified equivalence); do not assume passing only `seed` recreates the current RNG position. Use a safe structured serialization, not untrusted pickle from arbitrary files.
2. Validate snapshot shape, tile encoding, score, revision, and legal transitions before launch. **65536+ tile/Bitboard overflow** must use the established safe fallback, never silently corrupt the board.
3. Repeatedly compute an AI decision using the existing V6 solver and its exact selected algorithm/strength/backend policy. Validate direction is legal, commit one legal move and exactly one normal 2/4 spawn using the correct probabilities and deterministic state. Ensure correct score, move counter, terminal detection, and optional achievement state. No extra RNG draws may be introduced by GUI polling or serialization.
4. Enforce `max_steps`, elapsed wall time, memory limit/guard (where supported), search-time budget, and explicit cooperative cancel requests. Use a default bounded run; never leave an unbounded runaway task.
5. Emit progress snapshots at controlled frequency (starting target 250–500ms or a limited number of steps), never per frame, containing session ID, revision, step, score, max tile, backend_used, engine_used, reason for fallback, pure search time, wall time, actual valid moves/s, last committed checkpoint, status and error information. Progress is informational; it must NOT mutate the authoritative GUI board.
6. Return full final state (including RNG state and revision), a status (`completed`, `paused`, `stopped`, `game_over`, `error`), and performance totals. Use the same rules as standard/fast; a stand-alone headless game-loop correctness test must pass without Qt initialization.

A worker process is acceptable as a **thin isolated executor** (e.g., stdlib `multiprocessing` with Windows `spawn` or `subprocess` plus minimal JSON/pipe IPC). Only one active worker is allowed for the current game. The GUI remains responsive; no direct QWidget access from the worker. Do not build a general RPC framework, distributed service, queue, or auto-restart farm.

**Gate G2:** headless core imports/runs without Qt GUI; seeded/replayed equivalent transitions; correct terminal/overflow handling; bounded cancellation; output includes actual engine provenance.

## P3. Authoritative game ownership and safe GUI handoff

Adopt a precise state machine:

`GUI_IDLE -> HANDOFF_PREPARE -> BG_RUNNING -> BG_PAUSING -> BG_PAUSED -> BG_STOPPING -> GUI_IDLE`

Add `BG_COMPLETED` and `BG_ERROR` terminal paths. Validate transitions; reject repeated start, double pause, stop-after-close, and stale callback delivery.

1. Before entering background: wait for current animation to complete (or finish the current committed transition safely); cancel/wait for a pending SolverWorker by the established safe path. Disable manual move, undo, redo, new game, history load, and conflicting algorithm/strength changes while background owns the game. Save a **handoff checkpoint** that contains board, score, RNG state, revision, and selected solver settings.
2. The worker is the **sole author** of the running board. GUI may render progress **only as a read-only summary**, not mutate the live game every 250ms. If a board preview is desired, rate-limit it to read-only data, never treat preview as committed state.
3. A pause must request a stop at a consistent step boundary and return a checkpoint. Resume must use the exact board and RNG state, not the initial seed. A stop or completion must commit and validate the final snapshot before re-enabling manual controls. Any late message with mismatched session ID or revision is discarded.
4. Closing the GUI while BG is running must have explicit behavior, not an orphan silently writing to the same game archive. Prefer cooperative stop, bounded wait, durable checkpoint, then close. If a deadline is exceeded, preserve existing durable checkpoint and report failure; do not blindly `terminate()` during a storage transaction. Provide a recoverable on-next-launch notice.
5. Game over, process death, IPC timeout, and invalid/corrupted checkpoint must result in clear state and recoverability. Normal game history and highest-score semantics must be reconciled without duplicate moves or new-game side effects.
6. Process/IPC supervision should stay minimal: 1 worker handle, 1 command pipe/queue, throttled event receiver, 1 watchdog; asynchronous read integrated with Qt safely on the GUI thread. No spin-polling loops.

**Gate G3:** start/pause/resume/stop/close/relaunch and double-click stress; no stale board, no duplicate spawn, no orphan worker, no Qt freeze, no archive collision.

## P4. Persistence: preserve user game safety and avoid infrastructure overbuild

The default background mode is **current-game safe mode**, not a training/experimental mode. Preserve at least the existing user-visible crash-recovery guarantee. Determine what current V6 guarantees by inspecting real code; do not quietly weaken it.

1. Take a consistent checkpoint at handoff. Use an isolated temporary staging area scoped to game/session under V6, with exclusive ownership and atomic replace plus checksums/schema validation where appropriate. Do not write competing ordinary GUI and background state files concurrently.
2. Define and test durability exactly. If existing semantics require recoverability after **every committed move**, keep every-step durable commits initially; only optimize after actual `apply_move`, serialize, write, flush/fsync, and Qt rendering costs are measured. A time-based checkpoint every N steps cannot be called equivalent to every-move persistence.
3. Optional **separate later** experiments may test checkpoint batching, but not as default. Any optional acceleration must disclose the worst-case lost-progress bound and must never overwrite real official game archives when safety is reduced. Avoid creating two GUI-visible persistence options in this round.
4. Crash/restart tests: kill only a disposable test worker after durable checkpoint (never a user process); replay state and RNG; compare game invariants. Also test corrupted checkpoint, duplicate revision, disk full/permission error, interrupted atomic replace, and resume after pause.
5. Reuse existing history/session mechanism as much as possible. Changes in inherited V1–V5 storage code are disallowed; if adaptation is required, implement it in V6 without changing old-source behavior.

**Gate G4:** safety no worse than existing V6; archival isolation and single-writer guarantee; crash recovery and corruption tests pass, otherwise background mode must not become default.

## P5. Accurate performance measurement and backend integrity

Measure separate, non-overlapping timing intervals in both GUI and background:

- `search_ms`: solver elapsed time, actual `backend_used`/`engine_used` and fallback reasons.
- `apply_logic_ms`: move + spawn + score/update **exclusive of persistence** where instrumentable.
- `serialize_ms`, `file_write_ms`, `flush_fsync_ms`: durable persistence segments, otherwise explicitly label the combined span rather than guessing.
- `gui_animation_ms` (0 in fast/background), `gui_paint_ms` (Qt actual paint timing; distinguish paint CPU from wall elapsed), `intentional_delay_ms`, `event_dispatch_ms`, `ipc_ms` (background).
- `wall_step_ms` and full game wall time; include idle waits and worker launch/setup overhead in end-to-end figures.

Do **not** call old extreme `anim_ms` an animation number when it includes `apply_move` and state writes. `refresh()` duration is **not** equivalent to `paintEvent` duration. If segments overlap, explicitly declare overlap and do not sum them as exclusive parts.

Run two classes of benchmark:

A. **Same game trajectory**: fixed initial board, exact RNG replay/state, same algorithm/strength/solver budgets, same decision provenance, standard GUI vs new fast GUI vs background safe mode. If decisions differ, stop the strict trajectory comparison and report first divergent revision; do not compare different paths as equal work.

B. **Compute-only**: sequential, isolated fixed boards/budgets across Reference, NumPy/Numba, C++ primitives, C++ Native, reusing V6 existing `run_native_bench.py`; track median/P95, actual nodes/simulations, decision legality/consistency, time, and process Private Bytes/working set. Do not run simultaneous GUI race.

Historic measured baseline: prior V6 `standard` ≈2.05 steps/s; old `extreme` now `fast` ≈6.62 steps/s under specific 20s tests. Not guaranteed current baseline. Headless speedup must be **measured**, not promised. Run enough bounded trials to report variability, including warmups, environment/backend config and per-test exit codes. Avoid high-volume unconstrained tournaments.

**Gate G5:** measurement fields semantically accurate, reproducible comparisons, no backend mislabeling, source CSV/JSONL + summarized P50/P95 / throughput / resource peaks.

## P6. Scoped GUI/UX completion

1. V6 AI panel main controls in logical order: 算法, 求解强度 (快速/标准/强力), 求解模式 (自动连走/单步建议), 运行方式 [标准 | 快速 | 后台求解]. Main CTA and current mode/status consistent with selection.
2. Background active state: compact progress strip with step, score, max tile, step/s, current engine, last checkpoint, running/paused/stopped. Buttons: 开始/暂停/继续/停止; show errors without blocking the Qt event loop. A mode switch alone must not unexpectedly begin solving or destroy the game.
3. Do not leave a stale animation overlay/particle timer active when entering fast/background. Avoid blocking/repainting on every background move.
4. Style matches the current V6; restrained colors, no extra floating windows, no full redesign or additional modal dialog for every progress event. No change to V5 GUI.
5. Real Windows GUI screenshots: three modes visible, mode switch stopped/running, UI responsiveness, algorithm-strength independence, collapsed/expanded algorithm panel if applicable, 100%/125%/150% controlled DPI when practical. Explicitly mark untested views `UNVERIFIED`.

**Gate G6:** visible and understandable 3-mode UI, responsive stop, live progress, accessibility and layout verified with evidence.

## P7. Test matrix and completion report

Mandatory automated tests:

- **Migration**: old `standard`, old `fast`, old `extreme`, new versioned `fast`, invalid values; repeated startup idempotence.
- **Game invariants**: equal initial state and RNG-state roundtrip; same moves/spawns/scores; legal moves; terminal; large-tile safe fallback.
- **Lifecycle**: start/start, pause/resume many times, stop at in-flight solve, close during background, background failure, worker death, stalled IPC, repeated UI mode switching.
- **Persistence**: ownership and checkpoint revision; simulated crash/restore; corrupt data; disk error; archived history and official model isolation.
- **Metrics**: no claim that instant apply is animation, no false paint timing, actual backend+engine path visible; bounded queue and no unbounded CPU wakeup.
- **Performance**: GUI standard / GUI fast / Headless safe under repeatable rules, plus sequential compute-only backend benchmarks.
- **Regression**: V6 full suite; V5 source hash unchanged and optional read-only regression; no edits V1–V5; no RL retraining.

Exit codes must be preserved. Do not rewrite FAIL as PASS to meet a schedule. If a planned stage fails, block default background enablement and supply a safe rollback path, but continue independent read-only diagnostics/reporting. Do not auto commit.

**Final response from Trae must include:**

1. Current codebase audit; updated architecture and exact modified file list.
2. Legacy preference migration result and visible three-mode screenshots.
3. Proof Headless does not initialize QWidget/QApplication; step-state and RNG equivalence.
4. Owner-state lifecycle, pause/resume/close behavior and recovery evidence.
5. Official storage safety, single-writer and crash-injection results.
6. Each mode's measured steps/s, search/apply/persistence/paint/IPC/wall breakdown, P50/P95, CPU & process-memory peak, actual `backend_used`/`engine_used`.
7. All test commands, actual counts/exit codes and gate states G0–G7 (PASS/FAIL/PARTIAL/UNVERIFIED).
8. Any unresolved Qt crash root-cause uncertainty and genuine manual verification items.
9. Explicit confirmation V1–V5 were not changed, real game history/model unaffected, no training, no auto Git commit.

## Suggested one-turn Trae instruction

Read and execute **all P0–P7** in `@2048_V6_Current_Game_Headless_Integration_Trae.md` in one complete pass. This replaces the earlier larger three-mode/dual-window plans. Limit modifications to V6, retain the currently open game's board and exact RNG state in background, use the existing solver core, guarantee safe ownership transfer and checkpointed recovery, preserve solver strength independently of execution mode, and validate with actual test exit codes and reproducible comparisons. No V5/race work, no unrelated architecture expansion.
