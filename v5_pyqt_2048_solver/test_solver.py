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
        # 隔离真实存档目录（在创建窗口之前设置）：
        #   1) 不触碰用户真实存档与单实例锁；
        #   2) 离屏平台下模态弹窗无法关闭，隔离后不会误触发“只读运行”提示。
        os.environ["2048_HISTORY_DIR"] = tempfile.mkdtemp(prefix="v5_test_hist_root_")
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

    def _select_strategy(self, name):
        """按 currentData 查找并选中策略（不再假设下拉框索引与 STRATEGY_ORDER 一致）。"""
        combo = self.w.solver_strategy
        for i in range(combo.count()):
            if combo.itemData(i) == name:
                combo.setCurrentIndex(i)
                pump(self.app, 20)
                self.assertEqual(combo.currentData(), name)
                return i
        raise AssertionError("策略下拉框缺少：%s" % name)

    def _select_mode(self, name):
        combo = self.w.solver_mode
        for i in range(combo.count()):
            if combo.itemData(i) == name:
                combo.setCurrentIndex(i)
                pump(self.app, 20)
                self.assertEqual(combo.currentData(), name)
                return i
        raise AssertionError("模式下拉框缺少：%s" % name)

    # ---- V5.1 布局：左右双栏（UI-01/02/06/08） ----
    def test_window_sizes_by_page(self):
        # 游戏页：进入双栏，宽度应容纳“左游戏区 + 右求解区”，高度在合理范围内
        self.assertGreaterEqual(self.w.width(), self.v5.V5_MIN_WIDTH)
        self.assertGreaterEqual(self.w.height(), self.v5.V5_MIN_H)
        self.assertLessEqual(self.w.height(), self.v5.V5_DEFAULT_H)

    def test_default_two_column_layout(self):
        """T-01/G01：默认左右并排；左为游戏区(holder)，右为求解工作台；底部不重复。"""
        self.assertEqual(self.w.splitter.orientation(), Qt.Horizontal)
        self.assertIs(self.w.splitter.widget(0), self.w.game_holder)
        self.assertIs(self.w.splitter.widget(1), self.w.solver_container)
        self.assertTrue(self.w.game_holder.isAncestorOf(self.w.game_page))
        self.assertIs(self.w.solver_panel.parentWidget(), self.w.solver_container)
        self.assertFalse(self.w.game_page.isAncestorOf(self.w.solver_panel))
        # 展开态右栏宽度合理（默认 400，容差）
        self.assertGreaterEqual(self.w.splitter.sizes()[1], self.v5.SOLVER_W_MIN)

    def test_collapse_hides_solver_and_shrinks_window(self):
        """G02/G03：折叠后完整隐藏右栏容器（splitter 右项=0，无分隔残留），整窗收窄。"""
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertTrue(self.w._solver_collapsed)
        self.assertFalse(self.w.solver_container.isVisible())        # 整体隐藏（含背景/边框/窄条）
        self.assertFalse(self.w.solver_panel.isVisible())
        self.assertEqual(self.w.splitter.sizes()[1], 0)             # 无分隔器残留
        self.assertFalse(self.w.splitter.handle(0).isVisible())     # 分隔条一并隐藏
        # 整窗收窄到纯游戏宽度，无右侧空白或窄条
        self.assertLessEqual(self.w.width(), self.v5.COLLAPSED_WIDTH + 4)
        self.assertEqual(self.w.game_page.width(), self.v5.WINDOW_WIDTH)

    def test_game_buttons_within_board_width(self):
        """G04/G10：四个控制按钮在展开/折叠态都锚定于棋盘宽度内，不散到窗口两端。"""
        def check(tag):
            xs = {name: getattr(self.w, attr).mapTo(
                self.w, getattr(self.w, attr).rect().topLeft()).x()
                for name, attr in (("undo", "undo_button"), ("redo", "redo_button"),
                                   ("ai", "solver_ai_button"), ("new", "new_game_button"))}
            self.assertGreaterEqual(xs["undo"], 0, tag)
            self.assertLess(xs["new"], self.v5.WINDOW_WIDTH, tag)   # 仍在棋盘左栏内
            self.assertLess(xs["ai"], xs["new"], tag)
            return xs
        base = check("expanded")
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertEqual(check("collapsed"), base)                  # 折叠后位置不变
        self.w.resize(1000, self.w.height())                       # 用户折叠态放大
        pump(self.app, 120)
        self.assertEqual(check("collapsed+widen"), base)           # 仍不散开
        self.assertEqual(self.w.game_page.width(), self.v5.WINDOW_WIDTH)
        self.w._toggle_solver()
        pump(self.app, 120)

    def test_restore_geometry_and_width(self):
        """G05：展开恢复折叠前的窗口宽度与右栏宽度（忽略屏幕夹取以验证纯逻辑）。"""
        self.w._clamp_to_screen = lambda g: g
        self.w.resize(self.v5.V5_DEFAULT_WIDTH, self.v5.V5_DEFAULT_H)
        self.w._apply_splitter_sizes()
        pump(self.app, 80)
        before_w = self.w.width()
        before_right = self.w.splitter.sizes()[1]
        self.w._toggle_solver()
        pump(self.app, 100)
        collapsed_w = self.w.width()
        self.assertLess(collapsed_w, before_w)
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertEqual(self.w.width(), before_w)
        self.assertEqual(self.w.splitter.sizes()[1], before_right)

    def test_splitter_width_restored_after_drag(self):
        """G07：展开态拖动分隔条后的右栏宽度，在折叠/展开后仍被恢复。"""
        self.w._clamp_to_screen = lambda g: g
        self.w.resize(1200, self.v5.V5_DEFAULT_H)        # 加宽以便右栏可拖到 >400
        pump(self.app, 60)
        total = self.w.splitter.width()
        self.w.splitter.setSizes([total - 600, 600])     # 用户把右栏拖到 600
        pump(self.app, 80)
        dragged = self.w.splitter.sizes()[1]
        self.assertGreater(dragged, self.v5.SOLVER_W_DEFAULT)
        self.w._toggle_solver()
        pump(self.app, 100)
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertAlmostEqual(self.w.splitter.sizes()[1], dragged, delta=4)

    def test_toggle_20_no_drift(self):
        """G06：连续折叠/展开 20 次无累计尺寸漂移。"""
        self.w._clamp_to_screen = lambda g: g
        self.w.resize(self.v5.V5_DEFAULT_WIDTH, self.v5.V5_DEFAULT_H)
        self.w._apply_splitter_sizes()
        pump(self.app, 80)
        base_w = self.w.width()
        base_sizes = self.w.splitter.sizes()
        for _ in range(20):
            self.w._toggle_solver()
            pump(self.app, 20)
            self.w._toggle_solver()
            pump(self.app, 20)
        self.assertEqual(self.w.width(), base_w)
        self.assertEqual(self.w.splitter.sizes(), base_sizes)

    def test_collapsed_splitter_has_no_right_pane(self):
        """G08：折叠态右栏已整体隐藏，拖动分隔条不会出现右侧空白大栏。"""
        self.w._toggle_solver()
        pump(self.app, 100)
        self.w.splitter.setSizes([400, 500])          # 试图拉出右栏
        pump(self.app, 80)
        self.assertEqual(self.w.splitter.sizes()[1], 0)
        self.assertFalse(self.w.solver_container.isVisible())
        self.w._toggle_solver()
        pump(self.app, 100)

    def test_maximized_collapse_keeps_window(self):
        """G09：最大化时隐藏/展开不强制改变窗口尺寸，仅切换右栏内容。"""
        self.w.isMaximized = lambda: True              # 模拟最大化
        w_before = self.w.width()
        self.w._toggle_solver()
        pump(self.app, 100)
        self.assertTrue(self.w._solver_collapsed)
        self.assertFalse(self.w.solver_container.isVisible())
        self.assertEqual(self.w.width(), w_before)     # 尺寸未被程序化修改
        self.w._toggle_solver()
        pump(self.app, 100)
        self.assertTrue(self.w.solver_container.isVisible())
        self.assertEqual(self.w.width(), w_before)

    def _scan_chevron(self, btn):
        """把按钮渲染到离屏位图，统计 Chevron 箭头色 / 背景色 / 绿色像素。"""
        from PyQt5.QtGui import QColor, QPixmap
        pm = QPixmap(btn.size())
        pm.fill(Qt.transparent)
        btn.render(pm)
        img = pm.toImage()
        arrow = QColor("#8A7662")
        bg = QColor("#F3EDE5")
        n_arrow = n_bg = n_green = 0
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() < 40:
                    continue
                if (abs(c.red() - arrow.red()) <= 30 and
                        abs(c.green() - arrow.green()) <= 30 and
                        abs(c.blue() - arrow.blue()) <= 30):
                    n_arrow += 1
                if (abs(c.red() - bg.red()) <= 8 and
                        abs(c.green() - bg.green()) <= 8 and
                        abs(c.blue() - bg.blue()) <= 8):
                    n_bg += 1
                if c.green() > c.red() + 30 and c.green() > c.blue() + 30:
                    n_green += 1
        return n_arrow, n_bg, n_green

    def test_header_collapse_icon_left_of_title(self):
        """标题栏：Chevron 收起按钮位于标题左侧、紧凑左对齐，动作为向右收起。"""
        v5 = self.v5
        btn = self.w.solver_collapse_btn
        title = self.w.solver_title
        bx = btn.mapTo(self.w, btn.rect().topLeft()).x()
        tx = title.mapTo(self.w, title.rect().topLeft()).x()
        self.assertLess(bx, tx)                          # 按钮在标题左侧
        self.assertLess(tx - bx, 60)                     # 间距紧凑，不分散到两端
        self.assertIsInstance(btn, v5.ChevronToolButton)   # 自定义细线箭头，非系统图标
        self.assertEqual(btn.text(), "")                 # 无文字
        self.assertTrue(btn.icon().isNull())             # 不使用任何图标（含绿色系统图标）
        self.assertEqual(btn.direction(), "right")       # 向右收起
        self.assertEqual(btn.toolTip(), "收起 AI 求解面板")
        # 折叠后该按钮随右栏一起隐藏
        self.w._toggle_solver()
        pump(self.app, 100)
        self.assertFalse(btn.isVisible())

    def test_chevron_button_geometry_and_rendering(self):
        """折叠按钮 26×26 / 圆角 6 / 配色符合规范；箭头 QPainter 绘制且无绿色图标。"""
        from PyQt5.QtGui import QColor
        v5 = self.v5
        btn = self.w.solver_collapse_btn
        self.assertEqual((btn.width(), btn.height()), (26, 26))
        self.assertEqual(v5.COLLAPSE_BTN_SIZE, 26)
        self.assertEqual(v5.COLLAPSE_BTN_RADIUS, 6)
        self.assertEqual(QColor(v5.COLLAPSE_BTN_BG), QColor("#F3EDE5"))
        self.assertEqual(QColor(v5.COLLAPSE_BTN_BORDER), QColor("#CDBEAF"))
        self.assertEqual(QColor(v5.COLLAPSE_ARROW), QColor("#8A7662"))
        self.assertEqual(btn._arrow_color(), QColor("#8A7662"))     # 常态箭头色
        n_arrow, n_bg, n_green = self._scan_chevron(btn)
        self.assertGreater(n_arrow, 0, "未绘制出 #8A7662 Chevron 箭头")
        self.assertGreater(n_bg, 0, "QSS 背景未生效")
        self.assertEqual(n_green, 0, "出现绿色系统图标像素")

    def test_chevron_button_disabled_color(self):
        """Chevron 按钮 disabled 态使用浅灰箭头，启用后恢复常态色。"""
        from PyQt5.QtGui import QColor
        btn = self.w.solver_collapse_btn
        self.assertEqual(btn._arrow_color(), QColor("#8A7662"))
        btn.setEnabled(False)
        self.assertEqual(btn._arrow_color(), QColor("#C3B4A4"))
        btn.setEnabled(True)
        self.assertEqual(btn._arrow_color(), QColor("#8A7662"))

    def test_solver_panel_right_of_game(self):
        """求解面板位于棋盘/按钮的右侧，而不是下方（UI-01）。"""
        panel_left = self.w.solver_panel.mapTo(
            self.w, self.w.solver_panel.rect().topLeft()).x()
        board_right = self.w.board_view.mapTo(
            self.w, self.w.board_view.rect().topRight()).x()
        self.assertGreaterEqual(panel_left, board_right)

    def test_adaptive_height_on_roomy_screen(self):
        """屏幕足够高时：游戏页高度取默认值（不超高）。"""
        self.w._available_height = lambda: 1400
        self.w._grow_for_solver()
        pump(self.app, 60)
        self.assertEqual(self.w.height(), self.v5.V5_DEFAULT_H)

    def test_window_height_never_below_minimum(self):
        """屏幕过矮时窗口也不会低于最小高度（避免控件被压变形/重叠）。"""
        self.w._available_height = lambda: 500
        self.w._grow_for_solver()
        pump(self.app, 60)
        self.assertGreaterEqual(self.w.height(), self.v5.V5_MIN_H)

    def test_no_bottom_duplicate_solver(self):
        """T-02：求解日志唯一，且左游戏页内不再悬挂求解面板（无底部重复区）。"""
        from PyQt5.QtWidgets import QListWidget
        logs = [w for w in self.w.findChildren(QListWidget) if w is self.w.solver_log]
        self.assertEqual(len(logs), 1)
        self.assertFalse(self.w.game_page.isAncestorOf(self.w.solver_panel))

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
        page = self.w.game_page
        row = self.w._find_row_layout(page.layout(), self.w.new_game_button)
        self.assertIsNotNone(row)
        self.assertEqual(row.indexOf(self.w.solver_ai_button),
                         row.indexOf(self.w.new_game_button) - 1)

    def test_solver_panel_widgets_exist(self):
        for attr in ("solver_title", "solver_start_btn", "solver_export_btn",
                     "solver_view_btn", "solver_compare_btn", "solver_status",
                     "solver_progress", "solver_log", "solver_strategy",
                     "solver_depth", "solver_mode", "solver_container",
                     "solver_collapse_btn", "solver_edge_handle",
                     "solver_advanced_toggle", "solver_advanced_body", "solver_metrics"):
            self.assertTrue(hasattr(self.w, attr), attr)
        # 折叠窄条及其按钮已移除（改为整体隐藏容器 + AI 按钮重新打开）
        self.assertFalse(hasattr(self.w, "solver_collapsed_bar"))
        self.assertFalse(hasattr(self.w, "solver_expand_btn"))

    def test_result_actions_present(self):
        """结果操作（导出/查看/对比）位于右栏且可见可用。"""
        for attr in ("solver_export_btn", "solver_view_btn", "solver_compare_btn"):
            btn = getattr(self.w, attr)
            self.assertTrue(btn.isVisible(), attr)
            self.assertTrue(btn.isEnabled(), attr)

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
        self._select_strategy("heuristic")             # 启发式
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
        self._select_strategy("expectimax")            # Expectimax
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
        self._select_strategy("heuristic")
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

    # ---- V5.1：拖动 / 折叠 / 展开 / 状态一致性 ----
    def test_splitter_user_resize(self):
        """T-03：改分隔器尺寸后两栏边界合法，无控件重叠或异常消失。"""
        total = self.w.splitter.width()
        self.w.splitter.setSizes([total - 320, 320])
        pump(self.app, 60)
        sizes = self.w.splitter.sizes()
        self.assertGreater(sizes[0], 0)
        self.assertGreater(sizes[1], 0)
        self.assertTrue(self.w.game_page.isVisible())
        self.assertTrue(self.w.solver_panel.isVisible())
        # 棋盘仍为正方形，未被非等比拉伸
        self.assertEqual(self.w.board_view.width(), self.w.board_view.height())

    def test_solver_collapse_and_expand(self):
        """T-04：折叠后整体隐藏且状态保留；重新展开后宽度/配置/日志一致。"""
        self.w._clamp_to_screen = lambda g: g          # 忽略屏幕夹取以验证纯几何逻辑
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(1)
        self._select_strategy("heuristic")
        self.w.solver_depth.setCurrentIndex(1)
        self.w.on_solver_clicked()
        wait_until(self.app, lambda: not self.w._solver_running)
        log_count = self.w.solver_log.count()
        self.assertGreaterEqual(log_count, 2)
        right_before = self.w.splitter.sizes()[1]
        strategy_before = self.w.solver_strategy.currentData()
        mode_before = self.w.solver_mode.currentData()

        self.w._toggle_solver()
        pump(self.app, 80)
        self.assertTrue(self.w._solver_collapsed)
        self.assertFalse(self.w.solver_container.isVisible())     # 整体隐藏（无背景/边框/窄条）
        self.assertFalse(self.w.solver_panel.isVisible())
        self.assertEqual(self.w.solver_log.count(), log_count)    # 日志不丢

        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertFalse(self.w._solver_collapsed)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertEqual(self.w.solver_log.count(), log_count)    # 展开后日志一致
        self.assertAlmostEqual(self.w.splitter.sizes()[1], right_before, delta=6)
        self.assertEqual(self.w.solver_strategy.currentData(), strategy_before)
        self.assertEqual(self.w.solver_mode.currentData(), mode_before)

    def test_ai_button_reopens_panel_without_solving(self):
        """折叠后点击左侧「AI 求解」只重新展开面板，不自动开始求解。"""
        before = self.w.solver_log.count()
        self.w._toggle_solver()
        pump(self.app, 100)
        self.assertTrue(self.w._solver_collapsed)
        self.assertEqual(self.w.solver_ai_button.text(), "AI 求解")   # 折叠态入口标签
        self.w.solver_ai_button.click()
        pump(self.app, 120)
        self.assertFalse(self.w._solver_collapsed)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertFalse(self.w._solver_running)                       # 未自动开始求解
        self.assertEqual(self.w.solver_log.count(), before)

    def test_ai_button_opens_panel_only_when_expanded(self):
        """展开态「AI 求解」仍只负责打开/聚焦面板，不启动算法（启停交给「开始求解」）。"""
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        before = self.w.solver_log.count()
        self.w.solver_ai_button.click()
        pump(self.app, 120)
        self.assertFalse(self.w._solver_running)                   # 未启动算法
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertEqual(self.w.solver_log.count(), before)
        self.assertEqual(self.w.solver_ai_button.text(), "AI 求解")

    def test_hide_while_solving_via_ai_button_reopens(self):
        """运行中隐藏不停止求解；用 AI 按钮重新展开后任务与状态连续。"""
        self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
        self.w.solver_mode.setCurrentIndex(0)          # 自动连走
        self._select_strategy("mcts")                  # MCTS
        self.w.solver_depth.setCurrentIndex(0)
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: self.w._solver_running, timeout_ms=3000))
        self.w._toggle_solver()                        # 运行中隐藏
        pump(self.app, 120)
        self.assertFalse(self.w.solver_container.isVisible())
        self.assertTrue(self.w._solver_running)        # 隐藏不停止求解
        self.assertEqual(self.w.solver_ai_button.text(), "AI 求解")   # 入口标签恒定
        self.w.solver_ai_button.click()                # 用 AI 按钮重新展开
        pump(self.app, 120)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertTrue(self.w._session is not None or len(self.w._sessions) >= 1)
        if self.w._solver_running:
            self.w._stop_solver("测试结束")             # 停止改用面板方法
            pump(self.app, 120)

    # ---- V5.1：右侧贴边半胶囊把手（EdgeHandle） ----
    def _widget_rect_in_window(self, widget):
        from PyQt5.QtCore import QRect
        top_left = widget.mapTo(self.w, widget.rect().topLeft())
        return QRect(top_left, widget.size())

    def _assert_edge_handle_geometry(self, handle):
        hw, hh, top = self.v5.EDGE_HANDLE_W, self.v5.EDGE_HANDLE_H, self.v5.EDGE_HANDLE_TOP
        self.assertEqual((handle.width(), handle.height()), (hw, hh))
        self.assertEqual(handle.x(), self.w.width() - hw)          # 紧贴宿主内容右缘（无缝隙）
        self.assertEqual(handle.y(), top)                          # 对齐内容区顶部锚点

    def test_edge_handle_visibility_tracks_state(self):
        """贴边把手：展开态隐藏、折叠态显示，反复切换一致。"""
        handle = self.w.solver_edge_handle
        self.assertFalse(handle.isVisible())                       # 初始展开态：隐藏
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertTrue(handle.isVisible())                        # 折叠态：显示
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertFalse(handle.isVisible())                       # 再展开：隐藏

    def test_edge_handle_mounted_outside_solver_container(self):
        """贴边把手挂载在主窗口上，不随 Solver 容器隐藏，且不进入主布局。"""
        handle = self.w.solver_edge_handle
        self.assertIs(handle.parentWidget(), self.w)               # 父级为顶层窗口
        self.assertFalse(self.w.solver_container.isAncestorOf(handle))
        # 不进入主布局：splitter 仍只有左右两栏，把手不在其中
        self.assertEqual(self.w.splitter.count(), 2)
        self.w._toggle_solver()
        pump(self.app, 120)
        self.assertFalse(self.w.solver_container.isVisible())      # 容器整体隐藏
        self.assertTrue(handle.isVisible())                        # 把手仍可见

    def test_edge_handle_geometry_and_chevron(self):
        """把手 22×40、细线左箭头、无系统绿色图标；左侧圆角、右侧直边。"""
        from PyQt5.QtGui import QColor, QPixmap
        handle = self.w.solver_edge_handle
        self.assertIsInstance(handle, self.v5.SolverEdgeHandle)
        self.assertEqual((handle.width(), handle.height()), (self.v5.EDGE_HANDLE_W, self.v5.EDGE_HANDLE_H))
        self.assertEqual(handle.toolTip(), "展开 AI 求解面板")
        self.assertEqual(handle.accessibleName(), "展开 AI 求解面板")
        n_arrow, n_bg, n_green = self._scan_chevron(handle)
        self.assertGreater(n_arrow, 0, "把手未绘制 Chevron 箭头")
        self.assertGreater(n_bg, 0, "把手背景未绘制")
        self.assertEqual(n_green, 0, "把手出现绿色系统图标像素")
        # 形状：右侧直边（无边框、贴右缘为背景色）；左侧圆角（角点非把手背景）；左侧有边框
        pm = QPixmap(handle.size())
        pm.fill(Qt.transparent)
        handle.render(pm)
        img = pm.toImage()
        bg = QColor(self.v5.EDGE_HANDLE_BG)
        border = QColor(self.v5.EDGE_HANDLE_BORDER)
        center = img.pixelColor(handle.width() // 2, handle.height() // 2)
        self.assertLessEqual(self._color_dist(center, bg), 3, "把手中心应为背景色")
        left_mid = img.pixelColor(0, handle.height() // 2)
        self.assertLessEqual(self._color_dist(left_mid, border), 16, "左侧缺少边框")
        right_mid = img.pixelColor(handle.width() - 1, handle.height() // 2)
        self.assertLessEqual(self._color_dist(right_mid, bg), 8, "右侧直边应为背景色")
        self.assertGreater(self._color_dist(right_mid, border), 12, "右侧不应有边框")
        for cx, cy in ((0, 0), (0, handle.height() - 1)):
            corner = img.pixelColor(cx, cy)
            self.assertGreater(self._color_dist(corner, bg), self._color_dist(center, bg) + 5,
                               "左侧角点应为圆角（非把手背景）")

    @staticmethod
    def _color_dist(c, t):
        return max(abs(c.red() - t.red()), abs(c.green() - t.green()), abs(c.blue() - t.blue()))

    def test_edge_handle_reopens_panel_without_solving(self):
        """点击贴边把手重新展开面板，恢复右栏宽度，不启动算法。"""
        before = self.w.solver_log.count()
        self.w._toggle_solver()
        pump(self.app, 120)
        right_before = self.w._solver_saved_sizes[1] if self.w._solver_saved_sizes else None
        self.w.solver_edge_handle.clicked.emit()                   # 模拟点击
        pump(self.app, 150)
        self.assertFalse(self.w._solver_collapsed)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertFalse(self.w.solver_edge_handle.isVisible())    # 展开后隐藏
        self.assertFalse(self.w._solver_running)                   # 未启动算法
        self.assertEqual(self.w.solver_log.count(), before)
        if right_before is not None:
            self.assertGreaterEqual(self.w.splitter.sizes()[1], self.v5.SOLVER_W_MIN)

    def test_edge_handle_repositions_on_resize(self):
        """折叠态改变窗口尺寸后，把手重新贴右缘且不遮挡棋盘/分数卡/底部按钮。"""
        self.w._toggle_solver()
        pump(self.app, 120)
        handle = self.w.solver_edge_handle
        self.assertTrue(handle.isVisible())
        self._assert_edge_handle_geometry(handle)
        # 用户拉宽折叠窗口
        self.w.resize(760, self.w.height())
        pump(self.app, 120)
        self.assertTrue(handle.isVisible())
        self._assert_edge_handle_geometry(handle)
        # 不遮挡棋盘 / 分数卡 / 底部按钮
        handle_rect = handle.geometry()
        for attr in ("board_view", "score_label", "best_label",
                     "undo_button", "redo_button", "solver_ai_button", "new_game_button"):
            other = self._widget_rect_in_window(getattr(self.w, attr))
            self.assertFalse(handle_rect.intersects(other), attr + " 被把手遮挡")
        self.w._toggle_solver()
        pump(self.app, 120)

    def test_edge_handle_hide_while_solving_reopens(self):
        """运行中折叠：把手显示，点击后展开且不停止后台求解。"""
        self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
        self.w.solver_mode.setCurrentIndex(0)
        self._select_strategy("mcts")                  # MCTS
        self.w.solver_depth.setCurrentIndex(0)
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: self.w._solver_running, timeout_ms=3000))
        self.w._toggle_solver()                        # 运行中折叠
        pump(self.app, 120)
        self.assertTrue(self.w.solver_edge_handle.isVisible())
        self.assertTrue(self.w._solver_running)        # 隐藏不停止求解
        self.w.solver_edge_handle.clicked.emit()       # 把手展开
        pump(self.app, 120)
        self.assertFalse(self.w._solver_collapsed)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertTrue(self.w._session is not None or len(self.w._sessions) >= 1)
        if self.w._solver_running:
            self.w._stop_solver("测试结束")
            pump(self.app, 120)

    # ---- V5.1：命名统一 / 入口一致 / 无重复连接 ----
    def test_panel_title_named_ai_solver(self):
        """右侧面板标题与左侧入口统一为「AI 求解」。"""
        self.assertEqual(self.w.solver_title.text(), "AI 求解")
        self.assertEqual(self.w.solver_ai_button.text(), "AI 求解")
        self.assertEqual(self.w.solver_start_btn.text(), "开始求解")   # 启停按钮命名不变

    def test_both_entries_share_open_method(self):
        """左侧「AI 求解」与右侧贴边把手行为一致：均打开面板、不启动算法。"""
        before = self.w.solver_log.count()
        self.w._toggle_solver()
        pump(self.app, 100)
        # 用贴边把手展开
        self.w.solver_edge_handle.clicked.emit()
        pump(self.app, 100)
        self.assertFalse(self.w._solver_collapsed)
        # 再收起，用左侧 AI 按钮展开
        self.w._toggle_solver()
        pump(self.app, 100)
        self.w.solver_ai_button.click()
        pump(self.app, 100)
        self.assertFalse(self.w._solver_collapsed)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertFalse(self.w._solver_running)                 # 两个入口都不启动算法
        self.assertEqual(self.w.solver_log.count(), before)

    def test_no_duplicate_widgets_or_connections_on_toggles(self):
        """连续 20 次折叠/展开：不重复创建 Solver 实例，也不重复连接入口信号。"""
        from PyQt5.QtWidgets import QWidget
        handle = self.w.solver_edge_handle
        ai_btn = self.w.solver_ai_button
        r_handle = handle.receivers(handle.clicked)
        r_ai = ai_btn.receivers(ai_btn.clicked)
        for _ in range(20):
            self.w._toggle_solver()
            pump(self.app, 15)
            self.w._toggle_solver()
            pump(self.app, 15)
        self.assertEqual(len(self.w.findChildren(QWidget, "solverPanel")), 1)
        self.assertEqual(len(self.w.findChildren(QWidget, "solverEdgeHandle")), 1)
        self.assertIs(self.w.solver_edge_handle, handle)         # 同一实例，未重建
        self.assertEqual(handle.receivers(handle.clicked), r_handle)
        self.assertEqual(ai_btn.receivers(ai_btn.clicked), r_ai)

    def test_collapse_during_solve_keeps_running(self):
        """T-05：求解中折叠不影响业务推进，展开后状态一致。"""
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(0)          # 自动连走
        self._select_strategy("expectimax")            # Expectimax
        self.w.solver_depth.setCurrentIndex(0)         # 快速
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(
            self.app, lambda: self.w._solver_running, timeout_ms=3000))
        self.w._toggle_solver()                        # 运行中折叠
        pump(self.app, 120)
        baseline = len(self.w._session["steps"]) if self.w._session else 0
        # 折叠状态下业务应继续推进（或自然结束），worker 不被取消
        wait_until(self.app,
                   lambda: (not self.w._solver_running) or
                   (self.w._session and len(self.w._session["steps"]) > baseline),
                   timeout_ms=6000)
        self.w._toggle_solver()                        # 展开
        pump(self.app, 120)
        self.assertTrue(self.w.solver_panel.isVisible())
        self.assertTrue(self.w._session is not None or len(self.w._sessions) >= 1)
        self.w._stop_solver("测试结束")
        pump(self.app, 120)

    def test_start_stop_single_trigger(self):
        """T-07：开始/停止只触发一次；停止后无残留运行线程。"""
        self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
        self.w.solver_mode.setCurrentIndex(0)          # 自动连走
        self._select_strategy("mcts")                  # MCTS（有搜索耗时）
        before = len(self.w._sessions)
        self.w.on_solver_clicked()
        pump(self.app, 200)
        self.w.on_solver_clicked()                     # 停止
        ok = wait_until(self.app, lambda: not self.w._solver_running and
                        not self.w._solve_in_flight)
        self.assertTrue(ok)
        self.assertEqual(self.w.solver_start_btn.text(), "开始求解")
        self.assertEqual(self.w.solver_ai_button.text(), "AI 求解")
        # 停止后线程被回收（空闲时不存在运行中的 QThread）
        self.assertTrue(self.w._solver_thread is None)
        self.assertGreaterEqual(len(self.w._sessions), before + 1)

    def test_advanced_toggle(self):
        """UI-09：高级参数区可折叠，仅展示真实生效配置。"""
        self.assertFalse(self.w.solver_advanced_body.isVisible())
        self.w.solver_advanced_toggle.setChecked(True)
        pump(self.app, 40)
        self.assertTrue(self.w.solver_advanced_body.isVisible())
        self.assertIn("当前生效配置", self.w.solver_advanced_text.text())
        self.w.solver_advanced_toggle.setChecked(False)
        pump(self.app, 40)
        self.assertFalse(self.w.solver_advanced_body.isVisible())

    def test_metrics_match_model(self):
        """T-11：状态指标与底层真实状态一致。"""
        self._set_grid([[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 0, 0], [0, 0, 0, 0]])
        self.w.model.score = 4321
        self.w.refresh()
        self.w._render_idle_status()
        pump(self.app, 40)
        self.assertEqual(self.w.solver_metrics["score"].text(), "4321")
        self.assertEqual(self.w.solver_metrics["max_tile"].text(), "2048")
        self.assertEqual(self.w.solver_metrics["steps"].text(), "0")

    def test_strategy_change_maps_to_config(self):
        """T-08：切换算法/强度仍映射到原有 solver 配置，无参数偷换。"""
        idx_rl = solver.STRATEGY_ORDER.index("rl")
        self.w.solver_strategy.setCurrentIndex(idx_rl)
        pump(self.app, 20)
        self.assertFalse(self.w.solver_depth.isEnabled())      # RL 无强度
        idx_mcts = solver.STRATEGY_ORDER.index("mcts")
        self.w.solver_strategy.setCurrentIndex(idx_mcts)
        pump(self.app, 20)
        self.assertTrue(self.w.solver_depth.isEnabled())       # MCTS 有强度
        cfg = solver.build_config(self.w.solver_strategy.currentData(),
                                  self.w.solver_depth.currentData())
        self.assertEqual(cfg["strategy"], "mcts")
        self.assertIn("time_limit", cfg)

    # ---- H3：五算法真实身份（currentData 查找，修正“索引 1=Expectimax”误判） ----
    def test_strategy_identity_maps_to_config(self):
        """下拉框 currentData 与五算法配置一一对应；强度可用性与 has_presets 一致。

        历史用例用 setCurrentIndex(1) 当作 Expectimax、setCurrentIndex(2) 当作 MCTS，
        实际索引与 STRATEGY_ORDER 不同（1=rollout、2=expectimax），本用例改为按
        currentData 查找并对五算法身份做逐一校验。
        """
        self.assertEqual(self.w.solver_strategy.count(), len(solver.STRATEGY_ORDER))
        for name in solver.STRATEGY_ORDER:
            self._select_strategy(name)
            self.assertEqual(self.w.solver_strategy.currentData(), name)
            cfg = solver.build_config(self.w.solver_strategy.currentData(),
                                      self.w.solver_depth.currentData())
            self.assertEqual(cfg["strategy"], name)
            self.assertEqual(self.w.solver_depth.isEnabled(), solver.has_presets(name))
        # 显式纠正：Expectimax 有强度、RL 无强度
        self._select_strategy("expectimax")
        self.assertTrue(self.w.solver_depth.isEnabled())
        self._select_strategy("rl")
        self.assertFalse(self.w.solver_depth.isEnabled())

    # ---- H3：求解任务生命周期（job_id / 协作取消 / 过期结果丢弃 / 快速重启 / 关闭） ----
    def test_solver_gui_lifecycle(self):
        grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
        self._set_grid(grid)
        self.w.solver_mode.setCurrentIndex(0)
        self._select_strategy("mcts")

        job0 = self.w._job_id
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: self.w._solver_running, timeout_ms=3000))
        self.assertGreater(self.w._job_id, job0)                     # 每次开始自增

        # 停止：协作式取消（不用 terminate），线程被回收，且不再持有运行中的引用
        self.w.on_solver_clicked()
        ok = wait_until(self.app, lambda: not self.w._solver_running and
                        not self.w._solve_in_flight)
        self.assertTrue(ok)
        self.assertTrue(self.w._solver_thread is None)
        # 未退出线程必须保留有效引用（不得运行中直接置空）
        for t, _wb in self.w._retired_threads:
            self.assertFalse(t.isRunning() and not t.isFinished())

        # 过期结果（旧 job_id）必须被丢弃，棋盘不变、有“已忽略”日志
        self.w._solver_running = True
        before_log = self.w.solver_log.count()
        before_grid = [row[:] for row in self.w.model.grid]
        self.w._on_solver_result(self.w._job_id - 1,
                                 {"best_direction": "left", "best_name": "向左",
                                  "evaluations": {"left": 1.0}, "elapsed_ms": 1.0})
        self.assertEqual(self.w.model.grid, before_grid)
        self.assertGreater(self.w.solver_log.count(), before_log)

        # 棋盘快照校验：job_id 正确但棋盘已变 → 同样丢弃
        before_log = self.w.solver_log.count()
        self.w._job_id += 1
        self.w._board_sig = self.w._board_signature([[2, 2, 0, 0]] * 4)   # 故意不匹配
        self.w._on_solver_result(self.w._job_id,
                                 {"best_direction": "left", "best_name": "向左",
                                  "evaluations": {"left": 1.0}, "elapsed_ms": 1.0})
        self.assertGreater(self.w.solver_log.count(), before_log)
        self.w._solver_running = False
        self.w._shutdown_worker()

        # 快速重启：连续 start/stop/start 稳定，job_id 严格递增
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(0)
        self._select_strategy("mcts")
        ids = []
        for _ in range(2):
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: self.w._solver_running,
                                       timeout_ms=3000))
            ids.append(self.w._job_id)
            self.w.on_solver_clicked()
            wait_until(self.app, lambda: not self.w._solver_running)
        self.assertEqual(ids, sorted(set(ids)))
        self.assertLess(ids[0], ids[1])

        # 运行中关闭窗口：不崩溃，且停止后线程被回收
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.on_solver_clicked()
        wait_until(self.app, lambda: self.w._solver_running, timeout_ms=3000)
        self.w.close()
        pump(self.app, 200)
        self.assertFalse(self.w._solver_running)



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
