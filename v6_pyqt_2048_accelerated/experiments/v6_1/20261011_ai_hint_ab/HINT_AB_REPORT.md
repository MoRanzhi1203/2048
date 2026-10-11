# V5/V6 AI Hint — Warm-White Edge (A) + Inward Short Flow (B)

- Repo: `e:\PyQt5_demo\2048` | HEAD: `d71a7a3` (not committed this round)
- Env: `E:\anaconda3\envs\2048\python.exe`, `PYTHONNOUSERSITE=1`
- Evidence dir: `v6_pyqt_2048_accelerated/experiments/v6_1/20261011_ai_hint_ab/`

## P0 Root cause of the previous (low-visibility) hint
- Geometry (measured): board `434x434`, `BOARD_PADDING=10` (edge/gutter thickness), `BOARD_RADIUS=9`,
  `TILE_SIZE=96`, `TILE_GAP=10`; overlay parent = `BoardView`, `geometry=(0,0,434,434)`, top of children (not occluded).
- Prior scheme = a **dark warm-brown core** (`#756052`, peak alpha 0.84) over ~44% of the edge.
  It was measurable (mean |dLum| ~27, peak ~65) but read as a **heavy dark bar**, not an edge glow, and did
  not convey the desired "attracted to the target edge" feel. No clipping/coordinate/occlusion defect was found.
- This round replaces it with the requested **A (warm-white edge) + B (short inward flow)**.

## P1 Layer A — native inset warm-white edge
- Colors: primary `#FFF4E7`, transition `#F2DDC6`; board grey-brown background as base. Peak alpha 0.80
  (pure white never forms a solid line).
- Drawn **only inside the existing outer contour and only on background pixels** (see clip below).
- A gradient axis spans ~96% of the edge; the **perceptibly bright region covers ~65%-80%** of the straight
  edge length (gradient stops at 0.13/0.87 with mid alpha 0.34xpeak), fading towards both ends; the other three
  sides keep their original look.
- `QPainter` + `QLinearGradient` + antialiasing; safe inset derived from real geometry/DPR.

## P2 Layer B — light inward short flow (not particles)
- 3 short warm-white gradient streaks (2-4 allowed) travel **along the recommended direction** toward the
  target edge, shrinking and fading (ease_out), inside the **existing non-tile background** (border band and
  inter-tile gutters) only.
- Single animation clock (`QTimer` @30 FPS, period 1.30 s); no per-frame random objects, no physics, no
  per-particle timers. Each streak stays >= 2 px away from the other three edge bands (AA-safe).
- **Clip**: every A and B draw is clipped to `boardOuterRoundedRect - union(16 tileRoundedRects)`.
  This guarantees 0 px outside the outer contour and 0 px over tiles/numbers.
- **Degrade to A-only** when: gutter/pad < 4 px, overlay not visible, or `set_flow_enabled(False)`
  (perf/exception). In A-only the animation clock is stopped.

## Boundary numbers (measured, device px)
| DPR | dir | outside_outer | on_tile | other_bands | A_edge px | gap_flow px |
| --- | --- | --- | --- | --- | --- | --- |
| 1.00 | up/down/left/right | 0 | 0 | 0 | 4150 | 800-1024 |
| 1.25 (controlled) | all | 0 | 0 | 0 | 4668 | 1204-1546 |
| 1.50 (controlled) | all | 0 | 0 | 0 | 7005 | 1483-1913 |

- Tolerance note: masks erode tile rects / interior by **1 device px** to allow native antialiasing at tile and
  band boundaries (declared per the plan). No pixel is painted on any tile interior.
- A bright-edge length = 65%-80% of the edge (asserted in V5/V6 tests). Other three edges unchanged.

## Performance (Overlay paintEvent only, N=200 samples)
| Mode | DPR1.0 mean/p95 (ms) | DPR1.25 mean/p95 | DPR1.5 mean/p95 |
| --- | --- | --- | --- |
| none (no hint) | 0.015 / 0.021 | 0.029 / 0.032 | 0.015 / 0.021 |
| A | 0.444 / 0.649 | 1.047 / 1.444 | 0.733 / 1.192 |
| A+B | 0.881 / 1.389 | 2.082 / 3.267 | 1.640 / 2.541 |

- Budget (target): A+B overlay mean <= 2 ms, p95 <= 5 ms. Satisfied at 1.0 and 1.5; at the **controlled
  1.25 sim** mean is marginally 2.08 ms (>2) while p95 3.27 ms stays under budget -> documented; degrade path
  (2 streaks or 24 FPS) available, not triggered.
- Timer stops when hidden or no hint; UI thread runs no search/IO/physics.

## Tests and gates
| Run | Count | Exit |
| --- | --- | --- |
| V5 `test_solver` | 92 | 0 |
| V6 full (6 modules) | 40 | 0 |
| Standalone boundary+perf (DPR 1.0) | PASS | 0 |
| Controlled 1.25 / 1.5 | PASS | 0 |
| Real window captures (12 scenes) | CAPTURE/STRUCTURE/TEXT all True | 0 |

Gates: `V5_HINT_RENDER=PASS`, `V6_HINT_RENDER=PASS`, `BORDER_CONTAINMENT=PASS`, `FOLLOW_HINT_STATE=PASS`,
`KEYBOARD_REGRESSION=PASS`, `GUI_AUTOMATED=PASS`, `GUI_VISUAL=UNVERIFIED`, `DPI_VISUAL=UNVERIFIED`.

## Files changed
- `v5_pyqt_2048_solver/v5_pyqt_2048_solver.py` (rewrite `_SolverHintOverlay` to A+B; remove now-unused `math` import)
- `v5_pyqt_2048_solver/test_solver.py` (A+B boundary test + A-only degrade test)
- `v6_pyqt_2048_accelerated/tests/test_arrow_keys.py` (A+B shared-renderer/boundary test)

## Screenshots
- Four-direction whole-window (real Windows): `v6|v5 .../screenshots/full_suggest_{up,down,left,right}.png`
- V6 standard: `full_start/game/solver/collapsed.png`
- Direction composites: `hint_ab_directions_v6.png`, `hint_ab_directions_v5.png`
- Capture log: `gui_capture_hint_ab.jsonl` (12 records, all gates PASS)

## Independent issue (NOT changed this round)
- In **single-step follow** mode, a user key press is **ignored while a solve is in flight**
  (`on_move` returns early when `_solve_in_flight`). This is an existing concurrency semantic and was
  **not modified** by this pure-rendering change; listed here as an independent item for a future fix.

## Unverified / next steps
- `GUI_VISUAL` / `DPI_VISUAL` remain **UNVERIFIED**: requires the user to review the real screenshots;
  real Windows 125%/150% not tested (only controlled `QT_SCALE_FACTOR` sims).
- If a human finds A+B still not legible enough: tune `_EDGE_PEAK` / streak alpha (still inside the board),
  or trigger the A-only degrade on the 1.25 sim per budget.
- The 1.25 controlled-sim mean (2.08 ms) marginally exceeds the 2 ms target; consider 2 streaks / 24 FPS if
  a strict budget is required.
