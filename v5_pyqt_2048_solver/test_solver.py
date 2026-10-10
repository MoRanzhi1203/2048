#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 5 版（算法求解版）测试用例

分两部分：
    1. SolverCoreTest —— 求解算法核心（纯逻辑，无 Qt 依赖）
    2. SolverGuiTest  —— 界面集成（第 4 版界面不变 + 求解面板/入口/单步/连走/导出/异常安全）

运行：
    python v5_pyqt_2048_solver/test_solver.py            # 全部用例
    python v5_pyqt_2048_solver/test_solver.py SolverCoreTest   # 只跑核心
"""

import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # 界面测试用离屏平台（不弹窗、不抢焦点）

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import solver_2048 as solver                                    # noqa: E402


# =====================================================================
# 一、求解算法核心
# =====================================================================
class SolverCoreTest(unittest.TestCase):

    def test_slide_line_merge_rules(self):
        self.assertEqual(solver.slide_line([2, 2, 2, 2])[0], [4, 4, 0, 0])
        self.assertEqual(solver.slide_line([2, 2, 4, 0])[0], [4, 4, 0, 0])
        self.assertEqual(solver.slide_line([4, 4, 8, 8])[0], [8, 16, 0, 0])
        self.assertEqual(solver.slide_line([2, 0, 0, 2])[0], [4, 0, 0, 0])
        self.assertEqual(solver.slide_line([2, 4, 2, 4])[0], [2, 4, 2, 4])   # 不合并
        self.assertEqual(solver.slide_line([2, 2, 2, 2])[1], 8)              # 得分 = 4+4

    def test_move_grid_directions(self):
        grid = [[2, 0, 0, 2], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        left, _, moved = solver.move_grid(grid, 'left')
        self.assertTrue(moved)
        self.assertEqual(left[0], [4, 0, 0, 0])
        right, _, _ = solver.move_grid(grid, 'right')
        self.assertEqual(right[0], [0, 0, 0, 4])

        col = [[2, 0, 0, 0], [2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        up, _, _ = solver.move_grid(col, 'up')
        self.assertEqual([up[i][0] for i in range(4)], [4, 0, 0, 0])
        down, _, _ = solver.move_grid(col, 'down')
        self.assertEqual([down[i][0] for i in range(4)], [0, 0, 0, 4])

    def test_move_grid_no_change(self):
        grid = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        _, _, moved = solver.move_grid(grid, 'left')      # 已靠左，不应判定为移动
        self.assertFalse(moved)

    def test_game_over_and_legal_moves(self):
        over = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
        self.assertTrue(solver.is_game_over(over))
        self.assertEqual(solver.legal_moves(over), [])
        not_over = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        self.assertFalse(solver.is_game_over(not_over))
        self.assertIn('left', solver.legal_moves(not_over))

    def test_evaluate_prefers_empty(self):
        empty_ish = [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        crowded = [[2, 4, 8, 16], [4, 8, 16, 32], [8, 16, 32, 64], [16, 32, 64, 2]]
        self.assertGreater(solver.evaluate(empty_ish), solver.evaluate(crowded))

    def test_solve_heuristic_returns_legal_move(self):
        grid = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        result = solver.solve(grid, strategy='heuristic')
        self.assertIsNone(result['error'])
        self.assertIn(result['best_direction'], solver.legal_moves(grid))
        self.assertEqual(result['strategy'], 'heuristic')

    def test_solve_expectimax_returns_legal_move(self):
        grid = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        result = solver.solve(grid, strategy='expectimax', depth=3, time_limit=0.3)
        self.assertIsNone(result['error'])
        self.assertIn(result['best_direction'], solver.legal_moves(grid))
        self.assertGreaterEqual(result['depth_reached'], 1)
        self.assertLess(result['elapsed_ms'], 3000)

    def test_solve_respects_time_limit(self):
        grid = [[2, 4, 8, 16], [32, 64, 128, 256], [0, 0, 0, 0], [0, 0, 2, 4]]
        start = time.time()
        result = solver.solve(grid, strategy='expectimax', depth=6, time_limit=0.15)
        elapsed = time.time() - start
        self.assertLess(elapsed, 1.5)                     # 硬约束：不会长时间卡死
        self.assertIn(result['best_direction'], solver.legal_moves(grid))

    def test_solve_deterministic(self):
        grid = [[2, 4, 8, 16], [0, 32, 64, 128], [0, 0, 0, 0], [0, 0, 0, 2]]
        a = solver.solve(grid, strategy='expectimax', depth=3, time_limit=0.3)
        b = solver.solve(grid, strategy='expectimax', depth=3, time_limit=0.3)
        self.assertEqual(a['best_direction'], b['best_direction'])

    def test_solve_game_over_grid(self):
        over = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
        result = solver.solve(over, strategy='expectimax', depth=3, time_limit=0.2)
        self.assertIsNone(result['best_direction'])
        self.assertIsNone(result['error'])
        self.assertEqual(result.get('note'), '无可行移动')

    def test_solve_invalid_grid_returns_error(self):
        result = solver.solve([[2, 4], [8]], strategy='heuristic')   # 非方阵
        self.assertIsNotNone(result['error'])
        self.assertIsNone(result['best_direction'])

    # ---- 五类策略统一检查（启发式 / rollout / Expectimax / MCTS / RL）----
    def test_all_strategies_return_legal_move(self):
        grid = [[2, 4, 8, 16], [32, 64, 128, 256], [0, 512, 1024, 0], [0, 0, 2, 4]]
        legal = solver.legal_moves(grid)
        self.assertTrue(legal)
        for strategy in ('heuristic', 'rollout', 'expectimax', 'mcts'):
            cfg = solver.build_config(strategy, 'fast')
            cfg['time_limit'] = 0.15
            result = solver.solve(grid, **cfg)
            self.assertIsNone(result['error'], strategy)
            self.assertIn(result['best_direction'], legal, strategy)
            self.assertEqual(result['strategy'], strategy)

    def test_rollout_deterministic(self):
        grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
        a = solver.solve(grid, strategy='rollout', rollouts=12, rollout_depth=12)
        b = solver.solve(grid, strategy='rollout', rollouts=12, rollout_depth=12)
        self.assertEqual(a['best_direction'], b['best_direction'])

    def test_mcts_deterministic_and_bounded(self):
        grid = [[2, 4, 8, 16], [0, 0, 32, 64], [0, 0, 0, 0], [0, 0, 2, 0]]
        start = time.time()
        a = solver.solve(grid, strategy='mcts', simulations=200, time_limit=0.2)
        self.assertLess(time.time() - start, 2.0)
        self.assertIn(a['best_direction'], solver.legal_moves(grid))
        b = solver.solve(grid, strategy='mcts', simulations=200, time_limit=0.2)
        self.assertEqual(a['best_direction'], b['best_direction'])

    def test_expectimax_pruning_deterministic_and_effective(self):
        grid = [[2, 4, 8, 16], [32, 64, 0, 0], [0, 0, 0, 0], [0, 2, 0, 0]]
        on = solver.solve(grid, strategy='expectimax', depth=4, time_limit=0.5, prune=True)
        on2 = solver.solve(grid, strategy='expectimax', depth=4, time_limit=0.5, prune=True)
        off = solver.solve(grid, strategy='expectimax', depth=4, time_limit=0.5, prune=False)
        self.assertEqual(on['best_direction'], on2['best_direction'])       # 剪枝后仍确定
        self.assertIn(on['best_direction'], solver.legal_moves(grid))
        self.assertIn(off['best_direction'], solver.legal_moves(grid))
        self.assertTrue(on.get('pruned'))
        self.assertGreaterEqual(on.get('tt_entries', 0), 1)                 # 转置表生效

    def test_expectimax_pruning_timeout_still_returns_move(self):
        grid = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2, 4], [0, 0, 8, 16]]
        start = time.time()
        result = solver.solve(grid, strategy='expectimax', depth=8, time_limit=0.12)
        self.assertLess(time.time() - start, 1.5)
        self.assertIn(result['best_direction'], solver.legal_moves(grid))

    def test_rl_without_model_reports_error(self):
        import os as _os
        grid = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        result = solver.solve(grid, strategy='rl',
                              model_path=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                                       'no_such_model.npz'))
        self.assertIsNotNone(result['error'])
        self.assertIn('模型', result['error'])

    def test_rl_with_model_returns_legal_move(self):
        import os as _os
        path = solver.RL_MODEL_PATH
        if not _os.path.exists(path):
            self.skipTest('尚无 RL 模型（请先运行 rl_2048.py 训练）')
        grid = [[2, 4, 8, 16], [32, 64, 128, 256], [0, 512, 0, 0], [0, 0, 2, 0]]
        a = solver.solve(grid, strategy='rl')
        b = solver.solve(grid, strategy='rl')
        self.assertIsNone(a['error'])
        self.assertIn(a['best_direction'], solver.legal_moves(grid))
        self.assertEqual(a['best_direction'], b['best_direction'])          # 确定性

    def test_config_api(self):
        for strategy in solver.STRATEGY_ORDER:
            self.assertIn(strategy, solver.STRATEGIES)
            cfg = solver.build_config(strategy, 'normal')
            self.assertEqual(cfg['strategy'], strategy)
            self.assertTrue(solver.describe_config(cfg))
        self.assertTrue(solver.has_presets('mcts'))
        self.assertFalse(solver.has_presets('heuristic'))
        self.assertFalse(solver.has_presets('rl'))

    def test_unknown_strategy_returns_error(self):
        grid = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        result = solver.solve(grid, strategy='not-a-strategy')
        self.assertIsNotNone(result['error'])


# =====================================================================
# 二、界面集成
# =====================================================================
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    _QT_OK = True
except Exception:                                                # noqa: BLE001
    _QT_OK = False


def pump(app, ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_until(app, cond, timeout_ms=4000):
    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


@unittest.skipUnless(_QT_OK, "需要 PyQt5")
class SolverGuiTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        cls.app = QApplication.instance() or QApplication(sys.argv[:1])
        import v5_pyqt_2048_solver as v5
        cls.v5 = v5

    def setUp(self):
        # 结果目录重定向到临时目录，避免污染真实 solver_results/
        tmp = tempfile.mkdtemp(prefix="v5_test_results_")
        self.v5.RESULT_DIR = tmp
        self.v5.EXPORT_DIR = os.path.join(tmp, "exports")
        self.v5.SESSIONS_FILE = os.path.join(tmp, "sessions.json")
        self.w = self.v5.SolverMainWindow()
        # 重定向存档，避免污染真实对局目录
        self.w.model.history_dir = tempfile.mkdtemp(prefix="v5_test_hist_")
        self.w.start_new_game()
        self.w.show()
        pump(self.app, 120)

    def tearDown(self):
        try:
            self.w.close()
        except Exception:                                        # noqa: BLE001
            pass
        pump(self.app, 60)

    def _set_grid(self, grid):
        self.w.model.grid = [row[:] for row in grid]
        self.w.board_view.render(self.w.model.grid)
        self.w.refresh()

    # ---- 界面结构：第 4 版界面保持，新增入口与面板 ----
    def test_window_sizes_by_page(self):
        # 游戏页：不低于第 4 版高度、不超过期望整窗高度，宽度与第 4 版一致
        self.assertGreaterEqual(self.w.height(), self.v5.WINDOW_HEIGHT)
        self.assertLessEqual(self.w.height(), self.v5.V5_WINDOW_HEIGHT)
        self.assertEqual(self.w.width(), self.v5.WINDOW_WIDTH)

    def test_adaptive_height_on_roomy_screen(self):
        """屏幕足够高时：整窗 = 期望高度（886），面板 = 214。"""
        self.w._available_height = lambda: 1200
        self.w._grow_for_solver()
        pump(self.app, 60)
        self.assertEqual(self.w.height(), self.v5.V5_WINDOW_HEIGHT)
        self.assertEqual(self.w.solver_panel.height(), self.v5.PANEL_H)

    def test_adaptive_height_on_short_screen(self):
        """屏幕偏矮时：窗口自适应变矮、面板变矮并转为内部滚动，且原布局不被压坏。"""
        self.w._available_height = lambda: 800
        self.w._grow_for_solver()
        pump(self.app, 60)
        self.assertEqual(self.w.height(), 800 - self.v5.TITLEBAR_RESERVE)
        self.assertEqual(self.w.solver_panel.height(),
                         self.w.height() - self.v5.WINDOW_HEIGHT)
        # 原控件仍是“顶部锚定、不重叠”：按钮在棋盘下方
        board_bottom = self.w.board_view.mapTo(
            self.w, self.w.board_view.rect().bottomLeft()).y()
        undo_top = self.w.undo_button.mapTo(
            self.w, self.w.undo_button.rect().topLeft()).y()
        self.assertGreater(undo_top, board_bottom)

    def test_adaptive_height_never_below_layout_minimum(self):
        """屏幕过矮时窗口也不会低于布局最小高度（避免控件被压变形/重叠）。"""
        self.w._available_height = lambda: 600
        self.w._grow_for_solver()
        pump(self.app, 60)
        page = self.w.stack.widget(1)
        self.assertGreaterEqual(self.w.height(), page.minimumSizeHint().height())

    def test_panel_scrollable_area_exists(self):
        self.assertTrue(hasattr(self.w, "solver_scroll"))
        self.assertIsNotNone(self.w.solver_scroll.widget())   # 滚动内容存在

    def test_centered_at_launch_when_fits(self):
        """屏幕放得下时，启动窗口应居中于可用区域。"""
        scr = self.w.screen() or self.app.primaryScreen()
        av = scr.availableGeometry()
        fg = self.w.frameGeometry()
        if fg.height() <= av.height() and fg.width() <= av.width():
            self.assertLessEqual(abs(fg.center().x() - av.center().x()), 4)
            self.assertLessEqual(abs(fg.center().y() - av.center().y()), 4)

    def test_user_moved_detection(self):
        """程序化移动不标记为“用户拖动”；真实 move() 才标记。"""
        self.w._user_moved = False
        self.w._safe_move(50, 60)
        pump(self.app, 20)
        self.assertFalse(self.w._user_moved)
        self.w.move(70, 80)
        pump(self.app, 20)
        self.assertTrue(self.w._user_moved)

    def test_ai_button_inserted_before_new_game(self):
        page = self.w.stack.widget(1)
        row = self.w._find_row_layout(page.layout(), self.w.new_game_button)
        self.assertIsNotNone(row)
        self.assertEqual(row.indexOf(self.w.solver_ai_button),
                         row.indexOf(self.w.new_game_button) - 1)

    def test_solver_panel_widgets_exist(self):
        for attr in ("solver_title", "solver_start_btn", "solver_export_btn",
                     "solver_view_btn", "solver_compare_btn", "solver_status",
                     "solver_progress", "solver_log", "solver_strategy",
                     "solver_depth", "solver_mode"):
            self.assertTrue(hasattr(self.w, attr), attr)

    def test_solver_panel_below_board_and_buttons(self):
        """求解面板必须位于棋盘与按钮行“下方”，且不覆盖上方原有控件。"""
        panel = self.w.solver_log.parentWidget()
        board_bottom = self.w.board_view.mapTo(
            self.w, self.w.board_view.rect().bottomLeft()).y()
        undo_bottom = self.w.undo_button.mapTo(
            self.w, self.w.undo_button.rect().bottomLeft()).y()
        panel_top = panel.mapTo(self.w, panel.rect().topLeft()).y()
        self.assertGreaterEqual(panel_top, board_bottom)
        self.assertGreaterEqual(panel_top, undo_bottom)

    def test_original_widgets_same_as_v4(self):
        """原界面控件的位置/尺寸与第 4 版逐项一致（顶部锚定，不受加高影响）。"""
        import v4_pyqt_2048_animated as v4
        w4 = v4.MainWindow()
        w4.show()
        w4.stack.setCurrentIndex(1)          # 切到游戏页，确保其布局已激活
        pump(self.app, 120)
        try:
            for attr in ("board_view", "undo_button", "redo_button", "new_game_button",
                         "score_label", "best_label"):
                a = getattr(self.w, attr)
                b = getattr(w4, attr)
                self.assertEqual(
                    a.mapTo(self.w, a.rect().topLeft()).y(),
                    b.mapTo(w4, b.rect().topLeft()).y(), attr + " 纵向位置")
                self.assertEqual(a.width(), b.width(), attr + " 宽度")
                self.assertEqual(a.height(), b.height(), attr + " 高度")
        finally:
            w4.close()
            pump(self.app, 60)

    # ---- 第 4 版原有功能保持可用 ----
    def test_manual_move_still_works(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.on_move('left')
        self.assertTrue(wait_until(self.app, lambda: not self.w.board_view.is_animating()))
        self.assertEqual(self.w.model.grid[0][0], 4)

    def test_manual_move_blocked_while_solving(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w._solver_running = True
        try:
            self.w.on_move('left')            # 求解期间：应被忽略
        finally:
            self.w._solver_running = False
        self.assertEqual(self.w.model.grid[0][0], 2)

    # ---- 单步建议 ----
    def test_single_step_suggestion(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(1)          # 单步建议
        self.w.solver_strategy.setCurrentIndex(0)      # 启发式
        self.w.on_solver_clicked()
        ok = wait_until(self.app, lambda: not self.w._solver_running and not self.w._solve_in_flight)
        self.assertTrue(ok)
        # 未自动走子
        self.assertEqual(self.w.model.grid[0][0], 2)
        self.assertGreaterEqual(self.w.solver_log.count(), 2)

    # ---- 自动连走 ----
    def test_auto_solving_runs_and_records(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(0)          # 自动连走
        self.w.solver_strategy.setCurrentIndex(1)      # Expectimax
        self.w.solver_depth.setCurrentIndex(0)         # 快速
        sessions_before = len(self.w._sessions)
        self.w.on_solver_clicked()
        # 等待至少走完一步（自动连走会驱动真实棋盘）
        self.assertTrue(wait_until(
            self.app,
            lambda: self.w._session is not None and len(self.w._session["steps"]) >= 1,
            timeout_ms=6000))
        self.w.on_solver_clicked()                     # 停止
        pump(self.app, 200)
        self.assertGreaterEqual(len(self.w._sessions), sessions_before + 1)
        self.assertGreater(len(self.w._sessions[-1]["steps"]), 0)

    # ---- 导出 / 查看 / 对比 ----
    def test_export_and_compare(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(1)
        self.w.solver_strategy.setCurrentIndex(0)
        self.w.on_solver_clicked()
        wait_until(self.app, lambda: not self.w._solver_running)
        session = self.w._sessions[-1]
        paths = self.w._export_session(session)
        self.assertTrue(os.path.exists(paths["json"]))
        self.assertTrue(os.path.exists(paths["csv"]))
        rows = [self.v5.session_rows(s) for s in self.w._sessions]
        cmp_path = self.w.export_comparison(rows)
        self.assertTrue(os.path.exists(cmp_path))

    # ---- 异常安全：求解抛异常不影响界面 ----
    def test_solver_exception_is_contained(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        original = solver.solve

        def boom(*_a, **_k):
            raise RuntimeError("intentional failure")

        solver.solve = boom
        try:
            self.w.solver_mode.setCurrentIndex(1)
            self.w.on_solver_clicked()
            ok = wait_until(self.app, lambda: not self.w._solver_running and
                            not self.w._solve_in_flight)
        finally:
            solver.solve = original
        self.assertTrue(ok)
        # 界面仍在、可继续手动操作
        self.w.on_move('left')
        self.assertTrue(wait_until(self.app, lambda: not self.w.board_view.is_animating()))


def main():
    argv = sys.argv[1:]
    loader = unittest.TestLoader()
    if argv:
        suite = unittest.TestSuite(loader.loadTestsFromName(a) for a in argv)
    else:
        suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
