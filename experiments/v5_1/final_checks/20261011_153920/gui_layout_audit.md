# V5.1 · H8-3 右侧栏布局 / 键盘可达性审计（gui_layout_audit）

> run: `20261011_153920` ｜ 平台：Windows ｜ 真实整窗桌面截图

## 1. 设计保持（未回退）

保持 V5.1 左右双栏：左游戏台（`game_holder`）+ 右“算法求解”工作台（`solver_container`）+ 水平 `QSplitter` + 折叠态贴边半胶囊把手（`solver_edge_handle`）。**未改为底部堆叠面板**，未移除折叠后的独立展开入口。

## 2. 四场景整窗截图（真实工具输出）

| 场景 | 路径 | 尺寸 | dpr | CAPTURE | STRUCTURE | TEXT | VISUAL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| start | `v5_pyqt_2048_solver/screenshots/full_start.png` | 502×711 | 1.0 | PASS | PASS | PASS | **UNVERIFIED** |
| game | `v5_pyqt_2048_solver/screenshots/full_game.png` | 908×759 | 1.0 | PASS | PASS | PASS | **UNVERIFIED** |
| solver | `v5_pyqt_2048_solver/screenshots/full_solver.png` | 908×759 | 1.0 | PASS | PASS | PASS | **UNVERIFIED** |
| collapsed | `v5_pyqt_2048_solver/screenshots/full_collapsed.png` | 502×759 | 1.0 | PASS | PASS | PASS | **UNVERIFIED** |

原始 JSON：`gui_capture.jsonl`；汇总：`gui_capture_summary.json`。四图均含原生标题栏/图标/控制按钮与完整文字（`has_titlebar=true`、`text_rendered=true`）。

## 3. 自动化交互专项（对应测试全部 PASS）

| 检查项 | 测试 | 结果 |
| --- | --- | --- |
| 展开→折叠→展开 ≥5 次、无累积漂移 | `test_toggle_20_no_drift`（20 次） | PASS |
| 箭头方向 / 几何 / 渲染 | `test_chevron_button_geometry_and_rendering`、`test_chevron_button_disabled_color`、`test_edge_handle_geometry_and_chevron` | PASS |
| 折叠后贴边控件**直接重新展开** | `test_edge_handle_reopens_panel_without_solving`、`test_edge_handle_visibility_tracks_state`、`test_edge_handle_mounted_outside_solver_container` | PASS |
| AI 求解按钮职责不与右栏标题混淆 | `test_ai_button_reopens_panel_without_solving`、`test_ai_button_opens_panel_only_when_expanded`、`test_panel_title_named_ai_solver`、`test_both_entries_share_open_method` | PASS |
| splitter 拖动 / 宽度恢复 | `test_splitter_user_resize`、`test_splitter_width_restored_after_drag` | PASS |
| 窗口小→大→小 / 最小尺寸 / 自适应高度 | `test_window_sizes_by_page`、`test_adaptive_height_on_roomy_screen`、`test_window_height_never_below_minimum` | PASS |
| 最大化折叠 / 折叠后无右栏 | `test_maximized_collapse_keeps_window`、`test_collapsed_splitter_has_no_right_pane` | PASS |
| 活跃求解中折叠/展开不清任务、无新计算 | `test_h8_c06_ui_ops_during_inflight` | PASS |
| 键盘可达性（把手回车/空格） | `SolverEdgeHandle.keyPressEvent`（Enter/Space）+ `test_edge_handle_geometry_and_chevron` | PASS（自动化）；**人工键盘走查 UNVERIFIED** |

## 4. 结论

- `V5_1_GUI_AUTOMATED=PASS`（四场景截图门禁 + 交互测试全通过）。
- `V5_1_GUI_VISUAL=UNVERIFIED`（人工未核对）。

