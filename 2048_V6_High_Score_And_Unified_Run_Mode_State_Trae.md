# 2048 V6: High-Score Integrity and Unified Solver Mode State

## Role and scope
Execute this work order **end to end** against the actual Windows V6/V6.1/V6.2 repository. Inspect source and logs before changes. This is not a greenfield redesign. Preserve V1-V5 (read only), formal saves, undo/redo history, RNG, model weights, and prior benchmark artifacts. Do not retrain, auto-commit or auto-push. Use `E:\anaconda3\envs\2048\python.exe`, `PYTHONNOUSERSITE=1`. Report real exit codes and unmet gates.

## User-observed symptoms / evidence
1. While background solving, the historical best-score label sometimes becomes equal to the current score. Earlier images included a historical best of 62188; another session showed score=5004 and best=5004. Note: matching scores alone is not proof of corruption for a brand-new isolated save; confirm game identity and record source. The persistent all-time best must never be overwritten by lower current-session score.
2. Starting a background solve, then clicking Standard/Fast, causes the active background task to pause, while switching among other options can leave a task running. Behavior is inconsistent and the selected tab can be mistaken for the execution mode.
3. Standard/Fast have different start/pause/stop/continue controls and semantics from Background. Unify the control surface and behavior, without pretending a solver can be paused mid-uncancellable native call.
4. The top label should say `标准模式运行中`, `快速模式运行中`, `后台求解模式运行中`, respectively, and likewise `已暂停`, `正在停止`, `已完成`, etc.; never show only an ambiguous `运行中` / `已暂停`.

## P0. Read-only audit and reproduction
- Inspect `v6_speed.py`, `v6_background.py`, `V6MainWindow`, shared V5 solver widget adapters, authoritative GameCore, high-score store, `replay_commit`, `FINAL/ACK/EXITED`, background staging checkpoints, and UI summary/metric bindings.
- Trace full high-score read/write chain (current score, current-game max tile, game-scoped best, global persisted best, imported/restored game best); identify paths where background progress or FINAL sets best_score=score, initializes defaults incorrectly, or overwrites global records. Record real file/function/line evidence. Do not confuse maximum TILE with highest SCORE.
- Record current solver state transitions on clicks of each mode while idle/running/paused/stopping, and source of truth for active mode, requested mode, pending mode, UI-selected tab.
- Snapshot **isolated test files** and hashes, no real-saves-as-test-data. Capture before screenshots and preserve repro steps. Do not assume screenshot alone proves best score bug.

## P1. Correct high-score invariants
- Define authoritative semantics: `current_score` is current game's score; `best_score` in top-right is the persisted historical maximum for the correct game/profile/save scope; `max_tile` is the largest tile on the current board and is unrelated to highest score.
- Within one scope, enforce `best_score_new = max(best_score_previous, current_score_new)` for legitimate finalized/committed current-score updates. Background progress snapshots must **never** write the authoritative best-score store: they may render a read-only projected best as `max(persisted_best, committed_background_score)` only when the correct game/profile is confirmed.
- Final handoff must merge best monotonically, transactionally and only once with game/session/revision checks. Protect from stale delayed snapshots, old FINAL, undo/redo rollback, restarting the app, new game, switching solver mode, and worker crash. Existing different save/profile scopes must not be conflated.
- Keep historical highest score independent of board score and undo. If expected past highest 62188 and current 5004 in the same verified scope, top-right must remain 62188. If a new isolated test save starts at 5004, equality is legitimate and must not be mislabeled corruption.
- Never simply set `best_score = current_score` at worker start, snapshot, pause or completion. Do not regenerate high scores from current tiles.

## P2. Unified solver state source
- Build/reuse one V6-only execution coordinator, not three competing controllers. Track: `selected_mode`, `active_mode`, `pending_mode` (optional), `execution_state`, `session_id`, `game_id`, `revision`, `backend_used`, `engine_used`, and last committed snapshot. Keep background IPC ownership as-is; do not run more than one solver on a game.
- Distinguish **mode selection** (the tab the user clicked) from **active execution** (the task really running). Tab selection alone must never silently pause, stop, restart, change Worker ownership, or switch algorithm/search budget. Existing active task continues uninterrupted unless the user explicitly chooses a transition.
- Recommended minimal policy: mode tabs remain selectable while running to inspect another mode, but the existing session keeps its `active_mode`. Display a compact notice `后台求解模式运行中；所选：快速（切换需先暂停或停止）`. Alternative: block tabs while running and show `请先暂停或停止后切换`. Choose ONE consistent behavior after checking existing UX; prefer **selection is non-destructive**, explicit handoff only. Do not treat a selected tab as proof a running task changed engines.
- Actual mode switching must happen at a safe state boundary and must preserve complete board/score/RNG/history/undo/store ownership. Switching an active solver from background to GUI (or vice versa) requires a safe completed checkpoint and verified ownership handoff; if not safely supported, prohibit with a clear message. Never interrupt a native search or forcibly kill a worker just because user clicked a tab.
- All UI properties derive from coordinator state, not an independent background flag, solver_status string or QButton selected state. Reset per-session metrics at proper start; do not reset global high score.

## P3. Single set of control buttons for all three modes
- Reuse the existing unified `AI 运行控制` group; the same location has `开始求解`, `暂停`, `继续`, `停止` with buttons shown/enabled by a single state matrix. Remove duplicated BackgroundPanel controls without removing their actual signals or lifecycle logic. No disabled dummy controls pretending to support pause.
- IDLE/COMPLETED/STOPPED: `开始求解` enabled. RUNNING: `暂停` (if a safe pause is supported) and `停止` enabled. PAUSE_REQUESTED: `正在暂停…` no duplicate request. PAUSED: `继续` and `停止` enabled. STOP_REQUESTED: `正在停止…` no duplicate request. ERROR: safe retry only after cleanup and owner validation.
- Standard and Fast must gain **functional** pause/resume using a safe step boundary: stop scheduling the next AI request, let any in-flight computation return or cancel cooperatively, hold the next-step result carefully, resume from exact state without duplicate moves/spawns. Stop releases resources only after safe handoff. Do not block GUI event loop via waits, sleeps, join or large synchronous replay.
- On paused state, the board, RNG, current score, undo history and solver settings must not change until an explicit resume or stop/handoff. Changing solve strength or algorithm during a live task should either be deferred clearly or disabled—not silently applied mid-step.
- Background retains fixed **1000ms** progress reports; FINAL on pause/stop/game-over is immediate at next safe boundary, with validated FINAL/ACK/EXITED and owner-release semantics. Snapshot-only GUI paint must never call `apply_move` or spawn tiles.

## P4. Mode-qualified status and UI
- Show precise state text in unified control group and existing status metrics, e.g. `标准模式运行中`, `快速模式运行中`, `后台求解模式运行中`, `后台求解模式已暂停`, `快速模式正在停止`, `标准模式已完成`.
- When `selected_mode != active_mode`, clearly show `当前执行：后台求解模式运行中｜已选择：快速（未切换）`. A selected button must not change the active-mode badge. Avoid overlarge new banners or duplicate status panels.
- Align compact summary and detailed panel/log to the same session/revision. Keep actual backend/engine honest (`cpp/python_kernel` is NOT C++ native tree search). The `best_score` displayed in the header must be authoritative global/scope-high score, not an in-flight Worker score field.
- Standard retains animations, merge particles and direction hint; Fast suppresses merge particles and motion animations but retains dynamic direction hint; Background suppresses merge particles, uses fixed 1000ms board mirror, and renders a valid static direction hint only when semantically justified. Keep original four-by-four board dimensions unchanged.
- Keep existing low-saturation warm-gray V6 styling, one compact control block, no return-policy selectors or extra debug panels.

## P5. Safety and regression tests (mandatory)
1. Best-score invariants: previous best=62188 and current score traverses 0 -> 5004 -> 36820; top-right remains 62188; surpassing best once updates it; stale revision, late final, undo, new game, restart, isolated profile, and worker crash cannot reduce it. Assert store bytes/records not just screen labels.
2. Run-mode matrix: for each of Standard/Fast/Background, start -> running -> pause -> paused -> resume -> running -> stop -> idle and natural game over; verify buttons, mode-specific status text, and absence of duplicate timers/signals/worker process.
3. Cross-tab cases: select Fast while Background is RUNNING; select Standard while BG_PAUSED; select BG while Fast RUNNING; select Fast while Standard RUNNING; repeat rapid clicks. No silent pause, invisible continued execution, reset, double writer or stale signal.
4. For explicit supported handoff, assert board/score/best/RNG/revision/history exactness. For unsupported handoff, assert clear blocking and unchanged active session. Capture ordered IPC / QThread time-lines.
5. BG snapshot @ 1000ms (approximately, with long-step caveat); 200/400+ steps without auto stop; final result and history correctness; `FINAL/ACK/EXITED` and owner validation; hard failure remains FAIL.
6. Windows V6 real GUI screenshots: three modes idle/running/paused/stopped, tabs selected but different active mode, highest score retention, restart persistence; 125/150% DPI and compact/full sidebar if available. Manually unverified items = UNVERIFIED.
7. Re-run complete V6 unittest and explicit IPC E2E; preserve actual command lines, stdout/stderr, exit codes, PASS/FAIL/PARTIAL/UNVERIFIED. Measure UI max event-loop pause under standard/fast pause and background ownership adoption; no synchronous bulk replay in GUI thread.

## P6. Execution discipline
- Implement P0 -> P1 -> P2/P3 -> P4 -> P5 one at a time with failing regression tests first. Prefer isolated V6 adapter/core modifications; no V1-V5 changes. Avoid wholesale state-machine rewrites if present classes can be consolidated.
- Do not change native search algorithms, Rollout/Expectimax/MCTS budgets, RNG rules, GUI board size, scoring, formal persistence contracts or Git state without necessity.
- If a gate fails or a safe mode handoff cannot be completed, keep the original task running safely, make the limitation visible and mark the corresponding gate FAIL/PARTIAL; do not disguise it as PASS.

## P7. Final delivery
Deliver a Chinese report with: (a) verified root causes, (b) changed files/functions, (c) old/new mode state transition table, (d) best-score scope and persistence proof, (e) full three-mode button behavior and status wording, (f) raw test results/exit codes and GUI screenshots, (g) remaining failures and recommended next step. No automatic Git commit/push.
