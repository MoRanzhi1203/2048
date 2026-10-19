# 2048 V6: Background Window, Resume, and Solver Status Integration

## Scope and execution mode
Execute P0-P7 in one pass on the actual Windows project at `E:\PyQt5_demo\2048`. This is a focused V6/V6.2 bug fix, not a redesign. V1-V5 are read-only. Preserve all real saves, undo/redo history, RNG states, RL models and previous experiment evidence. Use `E:\anaconda3\envs\2048\python.exe` with `PYTHONNOUSERSITE=1`. No retraining, unrelated refactors, automatic Git commit or push. Report actual test exit codes and PASS/PARTIAL/FAIL/UNVERIFIED.

## Evidence from current screenshots
1. Selecting/starting background solving displays a second blank top-level Windows window titled `python` alongside the main V6 game. This is unintended.
2. During background solving, progress appears in the compact upper AI control summary (e.g. ~120 steps, ~78.481 steps/s), but the original result/status group under the start button still shows old text, zero step counts, stale previous score/maximum tile, and a previous “warming completed” notice.
3. After pausing and clicking resume, the user observes that the background solve no longer continues transmitting parameters/results. Verify whether `RESUME` is sent, acknowledged, and followed by new progress revisions; do not presume the mechanism.
4. Standard mode shows its existing status group updating normally, establishing the expected visual behavior.

## P0: Capture baseline and verify actual causes
- Locate the real code for V6 entry/main, background launcher and worker (`v6_background.py`, `headless/worker_main.py`, `headless/game_loop.py`), unified AI control panel, `v6_speed.py`, original `solver_status`, metric labels and historical log, IPC reader/drainer, `FINAL/ACK/EXITED`, checkpoint and ownership.
- Identify exactly who creates the blank `python` window: subprocess creation flags / `STARTUPINFO` / console allocation; accidental `QApplication`/`QWidget` in the worker; a duplicate V6 main; or an external test/helper. On Windows verify its PID, parent PID, executable, command line and window handle. Do not kill an unidentified process.
- Log timeline with monotonic time, PID, session_id, game_id, revision, backend_used, engine_used, state and effective algorithm preset at START, PAUSE, PAUSED, RESUME, ACK, PROGRESS, FINAL, EXITED, owner-release. Capture UI screenshots before modifying.
- Audit whether old progress callbacks still target legacy V5 widgets while new V6 callbacks only update the compact summary; identify duplicated state caches or reset-to-zero logic.

## P1: Invisible background worker, no extra window
- Ensure the headless Worker is a subprocess without a visible console, GUI or secondary top-level window. Use Windows `subprocess.CREATE_NO_WINDOW` or `STARTUPINFO` with `STARTF_USESHOWWINDOW`/`SW_HIDE` as appropriate for the actual executable and architecture. If necessary prefer `pythonw.exe` only after proving stderr, exit codes and diagnostics remain reliable. Keep stdin/stdout/stderr IPC operational and logs captured in a bounded diagnostic file.
- The Worker must not instantiate QApplication/QWidget, display a message box, or import a module with GUI side effects. Use guarded `if __name__ == '__main__'` entry points, especially with Windows multiprocessing spawn.
- Only the existing V6 main window is visible while a single worker runs. Preserve ability to stop and reap the child, obtain return code, and inspect error logs. No globally hiding all Python windows and no broad taskkill.

## P2: Correct pause and resume (same game, same parameters)
- Define transition contract: IDLE -> STARTING -> RUNNING -> PAUSE_REQUESTED -> PAUSED -> RESUME_REQUESTED -> RUNNING, with STOP_REQUESTED -> FINAL_COMMIT -> EXITED as needed. `PAUSED` is entered only after worker confirmation, safe checkpoint and authority/state checks; clicking pause is not itself proof of PAUSED.
- Resume must reuse the last committed checkpoint for this session/game: board, score, best/max tile, full RNG state, turn count, version/revision, algorithm, solver-strength preset, search-budget options, backend selection, owner token and official history. No new board, RNG reseed, implicit algorithm switch, loss of search parameters or repeated last move.
- If pause is implemented by terminating a worker at a step boundary, RESUME may spawn a replacement Worker only after the previous worker is confirmed exited and ownership has been transferred atomically. If a live worker is retained, send explicit RESUME and require ACK. Do not mix both strategies implicitly.
- Restore reporting clock after resume: fixed time policy 1000ms, and monotonic progress revision/total steps over the pause boundary; no stale queue or dead QTimer. New PROGRESS must arrive and update the GUI. Ensure RUNNING control enables Pause/Stop, PAUSED enables Resume/Stop.
- Guard duplicate clicks, cross-session messages, late FINAL and PID reuse. Never block the Qt main thread waiting for IPC or historical replay; use asynchronous, bounded transitions with explicit error handling.

## P3: One canonical solver view model for both visual areas
- Use one `SolverRunState` (or equivalent canonical current-session state) to feed both the compact 'AI 运行控制' summary and the existing result/status panel below. Do not create another black bar or extra big card.
- For background START/PROGRESS/PAUSED/RESUMED/STOPPED/COMPLETED/ERROR, update the existing `solver_status` and current metrics labels for steps, action/direction (distinguish last executed from next recommended), evaluation if genuinely available, current score, highest tile, elapsed, throughput, backend and engine. Unknown values should display `—`, not manufactured zero or stale data.
- On switching to background, reset only previous solver-session counters, not the actual game score or best score. The existing result panel must reflect the active backend session and current left-hand board snapshot rather than data from a previous standard/fast solve.
- Keep existing logs in the original log widget and show periodic compact entries without every-step flood. Deduplicate by (session_id, revision); coalesce old snapshots, apply only newer ones. GUI main thread only updates UI.
- Background snapshot is read-only for the game model: never apply moves or generate random tiles from a progress callback. Safely adopt authoritative state and history on stop/pause/final according to existing ownership protocol.
- When selected, background mode shows one unified lifecycle control set; retain standard/fast interactions and control semantics. No duplicate buttons or separate bulky reporting panel.

## P4: Fixed 1000ms reporting and final synchronization
- Preserve fixed 1000ms report period; do not reintroduce N-step/N-time selectors. This is a reporting target, not an overall task deadline or 200-step limit.
- Each valid progress snapshot is rendered on the LEFT board without slide/merge/particle animation, along with consistent score, max tile, current revision and the result panel. Qt updates via main thread only; ignore repeated/cross-game/out-of-order snapshots.
- Pause, Stop, game over and resource budget completion must force a final committed snapshot independently of the 1000ms clock; return accurate RNG/history and show final board. Do not show 'stopped' before worker exit / ownership safe release has been verified.
- Keep particles disabled in fast and background; preserve their respective direction-light policies, avoiding stale last-move direction presented as a future recommendation. Standard continues original visuals.

## P5: Tests that would catch all 3 regressions
1. Windows real GUI + worker: start background, ensure exactly one V6 game window and no blank `python` top-level window. Identify active child PID and command-line; verify hidden/console-free process retains pipes/logging.
2. Real background lifecycle from sparse deterministic board: START -> at least two valid PROGRESS -> PAUSE -> confirmed PAUSED -> RESUME -> at least two newer PROGRESS -> STOP -> FINAL -> worker EXITED -> owner absent. Repeat at least 5 times with no leftover workers.
3. Pause/resume at around 199/200/201 steps and beyond 400; artificial bounded solver/worker if natural game-over occurs early. No automatic 200-step termination, no restarted random sequence or repeated move.
4. Compare before/after pause: same game_id and immutable algorithm/preset/backend, valid checkpoint, strictly increasing effective total steps on resumed progress, and monotonic revision. Include rapid button presses and stop-during-warmup.
5. For each PROGRESS, assert main board, compact summary and original solver metrics refer to same session/revision/score/max tile; allow explicit display-lag label where UI is deliberately asynchronous. Reject old messages.
6. Validate background natural completion, crash recovery, formal history/undo/redo and RNG preservation in isolated temp save dir. Do not use production saves for stress tests.
7. Standard and fast modes still update original status panel, logs and controls; no extra worker windows. Check animation policy.
8. Windows at normal DPI and controlled 125%/150%: capture before/after screenshots in idle/running/paused/resumed/finished states; ensure the right control panel remains visually compact and legible.
9. Record search, checkpoint, IPC, report-to-paint and pause-to-resume latency separately; log UI event-loop stall max. Check stderr/Qt crash logs. A screenshot alone never substitutes for E2E.

## P6: Gates and rollback
- Run full V6 unit tests and explicitly enabled IPC E2E suites; report commands, count, skips and actual exit codes. Do not treat optional tests skipped as passed.
- Hard blockers: second visible window persists, resume produces no new revision, result panel is stale/zero during active background solving, GUI freezes, corrupted/duplicated history, owner leak, or SAVE/RNG mismatch.
- If unsafe, keep background experimental/non-default and preserve working standard/fast. Do not mask with silent fallback or forced termination.
- Ensure only V6 files changed; verify V1–V5 hashes/diff and preserve real saves/models.

## P7: Final delivery
Provide: root cause per issue (with file/line evidence), precise modifications, process tree and HWND visibility check, resume IPC timeline, synchronized UI data examples, screenshot paths, real test exits, speed/latency costs, gate table PASS/PARTIAL/FAIL/UNVERIFIED, and remaining risks. Complete implementation and tests in one run; do not stop after recommendations.
