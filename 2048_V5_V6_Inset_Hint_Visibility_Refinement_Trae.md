# 2048 V5/V6 AI Hint Visibility Refinement — Trae Execution Plan

## Goal and evidence
The latest V6 screenshot displays an AI suggestion of **Up** in the right panel, but the board-side visual indication is scarcely visible. Improve perceptual clarity without adding **any pixel or widget beyond the current board outer boundary**. Apply the same design to V5.1 and V6/V6.1, with V6 inheriting V5's shared overlay where applicable.

## Hard constraints
1. No new content outside the board's existing outer rect; no enlarged board, layout shift, outer glow, external rail, tooltip, badge, triangle, arrow or particle.
2. Do not cover tile faces/numbers. Only draw within the **existing internal border/gutter region**: the actual available band between the board outer edge and tile content. Do not infer it from arbitrary hard-coded offsets.
3. Keep original warm neutral palette, corner radii and board background coherent. No vivid green/gold or thick full-edge contrasting bar.
4. Direction must be distinguishable **in a static screenshot**, with animation as secondary reinforcement. All four directions must be symmetric.
5. Preserve ongoing single-step follow prediction, stale job/board signature rejection, cancellation/stop, auto-play semantics, QThread life cycle and arrow-key routing. Protect V1-V4, saved games and official RL model.

## P0 — Establish geometry and diagnose invisibility
- Inspect actual V4 BoardView paint rect, board background and tile rects; V5 `_SolverHintOverlay` overlay parenting, `geometry()`, stacking and `paintEvent`, V6 inheritance.
- Record global/local board outer rect, interior tile bounding rect, gutter thickness for top/right/bottom/left, corner radius, device pixel ratio, and whether the overlay is occluded by a sibling or clipped.
- Verify the current hint direction is non-null when right panel says Up; check overlay `isVisible`, painting update requests, color alpha, transform, clipping and z-order.
- Preserve an original full-window screenshot and a debug-only geometry diagnostic; keep diagnostics out of production UI.

## P1 — Revised visual design: native inset border emphasis
- **Base layer:** within the already-existing board perimeter/gutter only, make the recommended side subtly darker than its original fill (a low-amplitude warm-grey-brown shift). Never fill or darken the other three sides simply to exaggerate contrast.
- **Focus zone:** centered on the recommended side, cover about **35%–45% of the straight edge length**, with **a clearly defined, matte dark warm-brown core** (`#756052` starting candidate, tune against actual background), feathering over 10%–15% of segment length to naturally rejoin the existing board border.
- **Contrast criterion:** ensure a visible luminance difference from the local board background **in a static 100% screenshot**, aiming for a practical boundary detectable at native-size viewing, but avoid a black, highly saturated or hard-edged stripe. Prefer changing **internal gutter fill** rather than drawing an artificial separate stroke.
- **Do not force 5px stroke** if the gutter is narrower; derive available thickness from actual geometry and reserve at least 1 device pixel clearance from the tile rectangles. Use painter clipping to `boardOuterRect ∩ originalBorderGutter` so all tinted pixels are inside the original board rect and outside all tile rectangles.
- For corners, use existing rounded geometry; the focus zone stays on the straight span, away from corners.
- **Animation:** a restrained 8%–15% brightness modulation or subtle 0.9–1.4s easing in the focus zone. Keep a stable clearly visible base when paused; avoid travelling bright specks and flashes. Respect stop/clear immediately and hidden-window idle CPU.
- If the true border is not sufficient for a legible internal cue, do **not** violate boundary constraints: report geometry and propose an in-board gutter-only adjustment for review rather than silently adding external visuals.

## P2 — State lifecycle
- Only show a hint for the current `job_id` + board signature; clear old hint at accepted human move, before new game/continue, at stop, mode switch, window close, or cancelled/failed task.
- Maintain one shared overlay/animation driver per window; release it on close. Mouse-transparent overlay and no keyboard focus changes.
- V6 must not add a duplicate overlay if V5 is already providing it.

## P3 — Automated verification
1. Deterministic visuals for Up/Down/Left/Right in V5 and V6, both full-window screenshot and cropped board diagnostic **for review only**; capture actual Windows window with native titlebar under the existing screenshot standard.
2. Assert overlay outer bounds do not exceed board outer rect, and color changes occur only inside the pre-existing border/gutter mask; no pixels changed on tile faces/numbers. Use a baseline/difference comparison under a fixed board and state, not unreliable absolute screenshot equality.
3. Geometry tests at different window sizes, sidebar expanded/collapsed, DPI 100% and labelled **controlled simulations** of 125%/150%. Actual DPI remains UNVERIFIED unless tested on real scaled Windows sessions.
4. Functional tests: stable hint for each direction; rapid moves and latest-result-only update; reset/stop/mode switch clear; mouse passthrough; no duplicate repaint timers; arrow-key and single-step-follow regressions.
5. V5 and V6 full relevant test suites, plus targeted stress test for combined Qt test modules if the prior shared QApplication/window cleanup issue persists. Do not call a stuck test PASS; use subprocess timeouts and capture traceback.
6. GUI screenshot gates CAPTURE/STRUCTURE/TEXT cannot substitute for human VISUAL_PASS. Keep VISUAL=UNVERIFIED until the user personally checks.

## P4 — Safety and delivery
- Use `E:\anaconda3\envs\2048\python.exe` with `PYTHONNOUSERSITE=1`; real Windows GUI for screenshots.
- Diff and record source changes, reuse V5 code from V6, avoid editing V1–V4, do not mutate user data, do not retrain or run 100/300 game benchmarks, no automatic git commits.
- Produce concise root-cause explanation of the nearly invisible hint; report measured border/gutter geometry, final selected styling and reason, files changed, test commands and exit codes, all four direction screenshots, failed/unverified gates.
- Work through P0–P4 fully in one pass; stop only for a genuine blocker. Never claim manual visual acceptance on behalf of the user.
