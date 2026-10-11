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
import threading
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

    def test_solver_does_not_mutate_input_grid(self):
        """H1-D 输入不变性：五策略都不得就地修改调用方传入的棋盘。"""
        grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
        snapshot = [row[:] for row in grid]
        for strategy in solver.STRATEGY_ORDER:
            cfg = solver.build_config(strategy, 'fast')
            cfg['time_limit'] = 0.05
            solver.solve(grid, **cfg)
            self.assertEqual(grid, snapshot, "策略 %s 修改了输入棋盘" % strategy)

    def test_solver_rng_stream_isolated(self):
        """H1-D 随机数流隔离：求解不得消费全局 random 流；同种子可复现。"""
        import random
        grid = [[2, 4, 8, 16], [0, 32, 64, 128], [0, 0, 0, 0], [0, 0, 0, 2]]
        before = random.getstate()
        for strategy in solver.STRATEGY_ORDER:
            cfg = solver.build_config(strategy, 'fast')
            cfg['time_limit'] = 0.05
            solver.solve(grid, **cfg)
        self.assertEqual(random.getstate(), before, "求解消费了全局随机数流")
        # 同局面的 MCTS/rollout 在相同 seed 下结果确定（内部 RNG 由 seed 驱动）
        a = solver.solve(grid, strategy='mcts', simulations=100, time_limit=0.3, seed=11)
        b = solver.solve(grid, strategy='mcts', simulations=100, time_limit=0.3, seed=11)
        self.assertEqual(a['best_direction'], b['best_direction'])

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
        self._blocking_ctrl = None                # H8-1 可阻塞 solver 夹具状态

    def tearDown(self):
        self._restore_blocking_solver()            # 任何失败都保证释放阻塞并恢复 solver.solve
        try:
            self.w.close()
        except Exception:                                        # noqa: BLE001
            pass
        pump(self.app, 60)

    # ================= H8-1：在途取消确定性夹具（started/release 屏障） =================
    def _install_blocking_solver(self, hold=15.0):
        """把 solver.solve 替换为**可控阻塞**版本（仅本用例有效，tearDown 保证恢复）。

        - 进入计算后立即 set('entered') 供测试线程确认“worker 已真实进入计算阶段”；
        - 测试通过 set('release') 放行，用于制造迟到的 solved/failed；
        - 内置 watchdog（hold 秒）避免任何断言失败把测试锁死。
        """
        import solver_2048 as _s
        ctrl = {'entered': threading.Event(), 'release': threading.Event(),
                'returned': threading.Event(), 'entered_at': None, 'returned_at': None,
                'calls': 0, 'raise_exc': None, 'orig': _s.solve}

        def _blocking(grid, strategy='expectimax', **options):
            ctrl['calls'] += 1
            ctrl['entered_at'] = time.perf_counter()
            ctrl['entered'].set()
            if not ctrl['release'].wait(hold):
                raise TimeoutError('blocking solver watchdog (test fixture)')
            ctrl['returned_at'] = time.perf_counter()
            ctrl['returned'].set()
            if ctrl['raise_exc'] is not None:
                raise ctrl['raise_exc']
            return {'strategy': strategy, 'best_direction': 'left', 'best_name': '向左',
                    'evaluations': {'up': None, 'down': None, 'left': 1.0, 'right': None},
                    'depth_reached': 1, 'nodes': 1, 'elapsed_ms': 0.0,
                    'timed_out': False, 'error': None}

        _s.solve = _blocking
        self._blocking_ctrl = ctrl
        return ctrl

    def _restore_blocking_solver(self):
        import solver_2048 as _s
        ctrl = getattr(self, '_blocking_ctrl', None)
        if ctrl is not None:
            ctrl['release'].set()
            _s.solve = ctrl['orig']
            self._blocking_ctrl = None

    def _wait_threads_quiet(self, timeout_ms=6000):
        return wait_until(
            self.app,
            lambda: self.w._solver_thread is None and not self.w._solver_running
            and not self.w._solve_in_flight
            and not any(t.isRunning() for t, _w in self.w._retired_threads),
            timeout_ms)

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

    # ---- 单步建议（常驻跟随预测） ----
    def test_single_step_suggestion(self):
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self.w.solver_mode.setCurrentIndex(1)          # 单步建议（常驻跟随）
        self._select_strategy("heuristic")             # 启发式
        self.w.on_solver_clicked()
        # 给出建议后**保持待命**（不再自动停止）
        ok = wait_until(self.app, lambda: not self.w._solve_in_flight
                        and self.w.solver_log.count() >= 2)
        self.assertTrue(ok)
        self.assertTrue(self.w._solver_running, "单步建议应常驻跟随，不再给一次就停")
        self.assertEqual(self.w.model.grid[0][0], 2)   # 未自动走子
        self.assertIn(self.w._hint_direction, ("up", "down", "left", "right"))  # 棋盘高亮建议
        self.assertGreaterEqual(self.w.solver_log.count(), 2)
        # 停止跟随：清除高亮并结算会话
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: not self.w._solver_running
                                   and not self.w._solve_in_flight))
        self.assertIsNone(self.w._hint_direction, "停止后应清除棋盘高亮")

    def test_auto_mode_also_shows_hint(self):
        """自动连走：同样在棋盘原生边框内高亮本步建议方向；停止后清除高亮并停表。"""
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self._select_mode("auto")                      # 自动连走
        self._select_strategy("heuristic")             # 启发式
        self.w.on_solver_clicked()
        ok = wait_until(self.app, lambda: self.w._hint_direction in
                        ("up", "down", "left", "right"))
        self.assertTrue(ok, "自动连走应显示棋盘建议方向高亮")
        ov = self.w._hint_overlay
        self.assertIsNotNone(ov)
        self.assertTrue(ov.isVisible(), "自动连走高亮层应可见")
        # 停止：清除高亮并停下动画时钟
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: not self.w._solver_running))
        pump(self.app, 60)
        self.assertIsNone(self.w._hint_direction, "停止后应清除棋盘高亮")
        self.assertFalse(ov.isVisible())
        self.assertFalse(ov._timer.isActive(), "停止后不应残留动画时钟")

    def test_strategy_switch_while_running(self):
        """求解进行中切换算法：配置热更新、旧任务作废、会话记录切换、后续按新算法计算。"""
        self._set_grid([[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]])
        self._select_mode("single")                    # 单步建议（常驻跟随）
        self._select_strategy("heuristic")
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: self.w._hint_direction in
                                   ("up", "down", "left", "right")))
        self.assertEqual(self.w._solver_config.get("strategy"), "heuristic")
        job_before = self.w._job_id
        uniq_before = len(self.w._sessions)
        # 运行中切换算法
        self._select_strategy("mcts")
        self.assertEqual(self.w._solver_config.get("strategy"), "mcts", "配置应热更新")
        self.assertEqual(len(self.w._sessions), uniq_before, "不应切断/新建会话")
        self.assertGreater(self.w._job_id, job_before, "切换算法应作废旧任务身份")
        session = self.w._session
        self.assertTrue(session.get("strategy_changes"), "会话应记录算法切换")
        self.assertEqual(session["strategy_changes"][-1]["strategy"], "mcts")
        self.assertIn("MCTS", self.v5.session_rows(session)["strategy"])
        self.assertGreaterEqual(self.w.solver_log.count(), 1)
        self.assertIn("切换算法", self.w.solver_log.item(self.w.solver_log.count() - 1).text())
        # 在途计算期间再次切换：应作废在途结果并立即按新算法重算
        self.assertTrue(self.w._solve_in_flight, "MCTS 应在途计算中")
        inflight_token = self.w._solver_cancel
        job2 = self.w._job_id
        self._select_strategy("heuristic")
        self.assertEqual(self.w._solver_config.get("strategy"), "heuristic")
        self.assertGreater(self.w._job_id, job2, "在途切换同样应作废旧任务身份")
        self.assertTrue(inflight_token.is_set(), "在途计算的取消令牌应被置位（作废旧算法结果）")
        self.assertEqual(len(session["strategy_changes"]), 2)
        # 新算法给出建议后仍处于跟随状态
        self.assertTrue(wait_until(self.app, lambda: not self.w._solve_in_flight))
        self.assertTrue(self.w._solver_running)
        self.assertIn(self.w._hint_direction, ("up", "down", "left", "right"))
        self.w.on_solver_clicked()                     # 停止
        self.assertTrue(wait_until(self.app, lambda: not self.w._solver_running))
        self.assertIsNone(self.w._hint_direction)

    def test_single_mode_follows_user_moves(self):
        """跟随预测：单步建议给出建议后，用户走子会自动重算下一步最优解。"""
        self._set_grid([[2, 2, 4, 0], [0, 4, 8, 0], [0, 0, 16, 0], [0, 0, 0, 2]])
        self.w.solver_mode.setCurrentIndex(1)
        self._select_strategy("heuristic")
        self.w.on_solver_clicked()
        self.assertTrue(wait_until(self.app, lambda: not self.w._solve_in_flight
                                   and self.w.solver_log.count() >= 2), "首次建议未给出")
        self.assertTrue(self.w._solver_running)
        n1 = self.w.solver_log.count()
        # 用户走一步（left 合法：2,2 合并）
        self.w.on_move("left")
        # 走子动画结束后应自动再算一次并记录新建议
        self.assertTrue(wait_until(self.app, lambda: self.w.solver_log.count() > n1,
                                   timeout_ms=6000), "走子后未自动重算下一步")
        self.assertTrue(self.w._solver_running, "跟随预测应持续待命")
        self.w.on_solver_clicked()
        wait_until(self.app, lambda: not self.w._solver_running)

    # ================= 方向键冲突修复（QTest 回归） =================
    _DIRKEY_BASE = [[2, 2, 0, 0],
                    [2, 2, 0, 0],
                    [0, 0, 2, 2],
                    [0, 0, 2, 2]]      # 四个方向都合法

    def _dirkey_press(self, widget, key, modifier=None):
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        QTest.keyClick(widget, key, Qt.NoModifier if modifier is None else modifier)
        pump(self.app, 240)

    def _grid_without_spawn(self):
        g = [row[:] for row in self.w.model.grid]
        sp = getattr(self.w.model, "last_spawn", None)
        if sp is not None:
            g[sp[0]][sp[1]] = 0
        return g

    def test_dirkey_maps_to_four_moves(self):
        """四方向键正确映射为 up/down/left/right，且一次按键只走一步。"""
        from PyQt5.QtCore import Qt
        for key, direction in ((Qt.Key_Up, "up"), (Qt.Key_Down, "down"),
                               (Qt.Key_Left, "left"), (Qt.Key_Right, "right")):
            self._set_grid(self._DIRKEY_BASE)
            self.w.model.game_over = False
            self.w.setFocus()
            pump(self.app, 40)
            n0 = len(self.w.model.undo_stack)
            self._dirkey_press(self.w, key)
            expected, _g, moved = solver.move_grid(self._DIRKEY_BASE, direction)
            self.assertTrue(moved, "%s 在测试棋盘上本应合法" % direction)
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1,
                             "%s 一次按键应只走一步" % direction)
            self.assertEqual(self._grid_without_spawn(), expected,
                             "方向键未正确映射为 %s" % direction)

    def test_dirkey_combo_focused_keeps_option(self):
        """QComboBox 获得焦点时，方向键不得改变选项，且仍应走子。"""
        from PyQt5.QtCore import Qt
        combo = self.w.solver_strategy
        combo.setCurrentIndex(1)
        for key in (Qt.Key_Up, Qt.Key_Down):
            self._set_grid(self._DIRKEY_BASE)
            self.w.model.game_over = False
            combo.setFocus()
            pump(self.app, 60)
            idx0 = combo.currentIndex()
            n0 = len(self.w.model.undo_stack)
            self._dirkey_press(combo, key)
            self.assertEqual(combo.currentIndex(), idx0, "方向键不应改变下拉选项")
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1,
                             "下拉聚焦时方向键仍应走子")

    def test_dirkey_button_focused_not_clicked(self):
        """QPushButton 获得焦点时，方向键不得触发按钮，且仍应走子。"""
        from PyQt5.QtCore import Qt
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = False
        btn = self.w.new_game_button
        hits = []
        btn.clicked.connect(lambda: hits.append(1))
        btn.setFocus()
        pump(self.app, 60)
        n0 = len(self.w.model.undo_stack)
        self._dirkey_press(btn, Qt.Key_Left)
        self.assertEqual(hits, [], "方向键不应触发按钮点击")
        self.assertEqual(len(self.w.model.undo_stack), n0 + 1, "按钮聚焦时方向键仍应走子")

    def test_dirkey_blocked_states_ignore(self):
        """游戏结束 / 动画中 / AI 求解中：方向键不得走子。"""
        from PyQt5.QtCore import Qt
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = True
        n0 = len(self.w.model.undo_stack)
        self._dirkey_press(self.w, Qt.Key_Left)
        self.assertEqual(len(self.w.model.undo_stack), n0, "游戏结束后方向键不应走子")
        self.w.model.game_over = False
        orig = self.w.board_view.is_animating
        self.w.board_view.is_animating = lambda: True          # 受控模拟“动画中”
        try:
            n1 = len(self.w.model.undo_stack)
            self._dirkey_press(self.w, Qt.Key_Left)
            self.assertEqual(len(self.w.model.undo_stack), n1, "动画中方向键不应走子")
        finally:
            self.w.board_view.is_animating = orig
        self.w._solver_running = True
        self.w._solver_mode = "auto"
        try:
            n2 = len(self.w.model.undo_stack)
            self._dirkey_press(self.w, Qt.Key_Left)
            self.assertEqual(len(self.w.model.undo_stack), n2, "AI 求解中方向键不应走子")
        finally:
            self.w._solver_running = False

    def test_dirkey_invalid_move_no_spawn_no_history(self):
        """无效移动不得生成随机方块或新增历史。"""
        from PyQt5.QtCore import Qt
        grid = [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        self._set_grid(grid)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        n0 = len(self.w.model.undo_stack)
        before = [r[:] for r in self.w.model.grid]
        self._dirkey_press(self.w, Qt.Key_Up)                  # up 非法（仅首列一格且已在顶部）
        self.assertEqual(self.w.model.grid, before, "无效移动不应改变棋盘")
        self.assertEqual(len(self.w.model.undo_stack), n0, "无效移动不应新增历史")

    def test_dirkey_welcome_page_no_board_move(self):
        """欢迎页方向键不操作棋盘（保持原生、不落到隐藏棋盘）。"""
        from PyQt5.QtCore import Qt
        self.w.stack.setCurrentIndex(0)
        pump(self.app, 100)
        n0 = len(self.w.model.undo_stack)
        before = [r[:] for r in self.w.model.grid]
        self._dirkey_press(self.w, Qt.Key_Left)
        self.assertEqual(self.w.model.grid, before, "欢迎页方向键不应操作棋盘")
        self.assertEqual(len(self.w.model.undo_stack), n0)
        self.w.stack.setCurrentIndex(1)
        pump(self.app, 100)

    def test_dirkey_other_keys_no_regression(self):
        """WASD / Ctrl+Z / Ctrl+Y / Tab / 鼠标点击 / Enter-Space 不回归。"""
        from PyQt5.QtCore import Qt, QPoint
        from PyQt5.QtTest import QTest
        for key, direction in ((Qt.Key_W, "up"), (Qt.Key_A, "left"),
                               (Qt.Key_S, "down"), (Qt.Key_D, "right")):
            self._set_grid(self._DIRKEY_BASE)
            self.w.model.game_over = False
            self.w.setFocus()
            pump(self.app, 40)
            n0 = len(self.w.model.undo_stack)
            self._dirkey_press(self.w, key)
            self.assertEqual(len(self.w.model.undo_stack), n0 + 1, "WASD(%s) 未走子" % direction)
        # Ctrl+Z 撤销
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        self._dirkey_press(self.w, Qt.Key_Left)
        wait_until(self.app, lambda: not self.w.board_view.is_animating(), 2000)
        after_move = [r[:] for r in self.w.model.grid]
        self._dirkey_press(self.w, Qt.Key_Z, Qt.ControlModifier)
        self.assertNotEqual(self.w.model.grid, after_move, "Ctrl+Z 未撤销")
        # Tab / Shift+Tab 只移动焦点
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        n0 = len(self.w.model.undo_stack)
        self._dirkey_press(self.w, Qt.Key_Tab)
        self._dirkey_press(self.w, Qt.Key_Backtab)
        self.assertEqual(len(self.w.model.undo_stack), n0, "Tab/Shift+Tab 不应走子")
        # 鼠标点击棋盘不触发行走
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = False
        pump(self.app, 40)
        n0 = len(self.w.model.undo_stack)
        QTest.mouseClick(self.w.board_view, Qt.LeftButton, Qt.NoModifier, QPoint(12, 12))
        pump(self.app, 120)
        self.assertEqual(len(self.w.model.undo_stack), n0, "鼠标点击不应走子")
        # Space 仍能激活按钮（原生）
        btn = self.w.new_game_button
        hits = []
        btn.clicked.connect(lambda: hits.append(1))
        btn.setFocus()
        pump(self.app, 60)
        QTest.keyClick(btn, Qt.Key_Space)
        pump(self.app, 120)
        self.assertEqual(len(hits), 1, "Space 应仍能激活按钮")

    def test_dirkey_release_and_auto_repeat(self):
        """KeyRelease 不走子；连续 KeyPress（自动重复）每次至多走一步。"""
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        self._set_grid(self._DIRKEY_BASE)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        n0 = len(self.w.model.undo_stack)
        QTest.keyRelease(self.w, Qt.Key_Left)
        pump(self.app, 200)
        self.assertEqual(len(self.w.model.undo_stack), n0, "KeyRelease 不应走子")
        grid = [[2, 2, 2, 2], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
        self._set_grid(grid)
        self.w.model.game_over = False
        self.w.setFocus()
        pump(self.app, 40)
        m0 = len(self.w.model.undo_stack)
        QTest.keyPress(self.w, Qt.Key_Left)
        pump(self.app, 240)
        m1 = len(self.w.model.undo_stack)
        self.assertLessEqual(m1 - m0, 1, "一次 KeyPress 只应走一步")
        QTest.keyPress(self.w, Qt.Key_Left)
        pump(self.app, 240)
        m2 = len(self.w.model.undo_stack)
        self.assertLessEqual(m2 - m1, 1, "自动重复每次至多走一步")

    # ================= AI 推荐方向：原生边框内嵌高亮（渲染/边界） =================
    def _hint_overlay_image(self):
        from PyQt5.QtGui import QImage, QColor
        ov = self.w._hint_overlay
        img = QImage(ov.width(), ov.height(), QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        ov.render(img)
        return img

    @staticmethod
    def _border_paths():
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainterPath
        import v4_pyqt_2048_animated as v4
        W, PAD, R = v4.BOARD_SIDE, v4.BOARD_PADDING, v4.BOARD_RADIUS
        outer = QPainterPath(); outer.addRoundedRect(QRectF(0, 0, W, W), R, R)
        inner = QPainterPath(); inner.addRoundedRect(
            QRectF(PAD, PAD, W - 2 * PAD, W - 2 * PAD), max(0.0, R - PAD), max(0.0, R - PAD))
        return outer, inner, W, PAD

    @staticmethod
    def _hint_masks(W, PAD):
        """瓦片掩码（内缩 1px 容差）、内部背景间隙掩码、四条边带掩码。"""
        import numpy as np
        import v4_pyqt_2048_animated as v4
        H = W
        X, Y = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
        step = v4.TILE_SIZE + v4.TILE_GAP
        tile = np.zeros((H, W), bool)
        for rr in range(4):
            for cc in range(4):
                x0 = PAD + cc * step; y0 = PAD + rr * step; s = v4.TILE_SIZE
                tile |= (X >= x0 + 1) & (X < x0 + s - 1) & (Y >= y0 + 1) & (Y < y0 + s - 1)
        gc = [PAD + v4.TILE_SIZE + v4.TILE_GAP / 2.0 + k * step for k in range(3)]
        vgap = np.zeros((H, W), bool); hgap = np.zeros((H, W), bool)
        for c in gc:
            vgap |= (X >= c - v4.TILE_GAP / 2.0) & (X < c + v4.TILE_GAP / 2.0)
            hgap |= (Y >= c - v4.TILE_GAP / 2.0) & (Y < c + v4.TILE_GAP / 2.0)
        interior = (X >= PAD + 1) & (X < W - PAD - 1) & (Y >= PAD + 1) & (Y < H - PAD - 1)
        gaps = (vgap | hgap) & interior
        bands = {'up': Y < PAD, 'down': Y >= H - PAD, 'left': X < PAD, 'right': X >= W - PAD}
        corner = ((X < PAD) | (X >= W - PAD)) & ((Y < PAD) | (Y >= H - PAD))
        return tile, gaps, bands, corner

    def test_hint_overlay_within_native_border(self):
        """A+B：着色不越出外轮廓、不覆盖瓦片、其他三边不变；A 亮区占边 72%–82%；
        A 横截面为“外侧深色隔离槽 + 中部奶油暖白亮面 + 内侧暖杏过渡”的明暗轮廓分离；B 出现在内部间隙。"""
        from PyQt5.QtCore import Qt, QRectF
        import numpy as np
        outer, inner, W, PAD = self._border_paths()
        tile, gaps, bands, corner = self._hint_masks(W, PAD)
        ov = self.w._hint_overlay
        self.assertIsNotNone(ov, '未挂载提示高亮层')
        self.assertTrue(ov.testAttribute(Qt.WA_TransparentForMouseEvents), '提示层应鼠标透传')
        for d in ('up', 'down', 'left', 'right'):
            self.w._show_hint(d)
            pump(self.app, 90)
            img = self._hint_overlay_image()
            H, Wd = img.height(), img.width()
            arr = np.frombuffer(img.constBits().asstring(img.byteCount()),
                                dtype=np.uint8).reshape(H, Wd, 4)
            alpha = arr[:, :, 3].astype(np.int32)
            ys, xs = np.where(alpha > 0)
            self.assertGreater(len(xs), 0, '%s 无着色像素' % d)
            for x, y in zip(xs[::9], ys[::9]):
                self.assertTrue(outer.intersects(QRectF(int(x), int(y), 1.0, 1.0)),
                                '%s 着色越出棋盘外轮廓' % d)
            self.assertEqual(int(((alpha > 0) & tile).sum()), 0, '%s 覆盖瓦片像素' % d)
            other = np.zeros((H, Wd), bool)
            for s, bm in bands.items():
                if s != d:
                    other |= bm
            other &= ~corner                            # 角块同属两条边，单独排除
            self.assertEqual(int((alpha[other] > 0).sum()), 0, '%s 其他三边被改动' % d)
            # A 明亮识别区：取边框带外 1/3 处单线剖面（避开靠瓦片的过渡边界），测半高连续长度
            off = max(1, int(PAD * 0.4))
            if d == 'up':
                prof = alpha[off, :]
            elif d == 'down':
                prof = alpha[H - 1 - off, :]
            elif d == 'left':
                prof = alpha[:, off]
            else:
                prof = alpha[:, Wd - 1 - off]
            thr = 0.5 * float(prof.max())
            idx = np.where(prof >= thr)[0]
            self.assertGreater(len(idx), 0, '%s A 层暖白缺失' % d)
            ext = int(idx.max() - idx.min() + 1)
            L = H if d in ('left', 'right') else Wd
            self.assertGreaterEqual(ext / L, 0.72, '%s 暖白亮区过短' % d)
            self.assertLessEqual(ext / L, 0.82, '%s 暖白亮区过长' % d)
            # 三段式横截面：外侧深色隔离槽（offset≈1）须显著暗于中部主亮面（offset≈4）
            cx, cy = Wd // 2, H // 2
            if d == 'up':
                gpx, fpx = arr[1, cx], arr[off, cx]
            elif d == 'down':
                gpx, fpx = arr[H - 2, cx], arr[H - 1 - off, cx]
            elif d == 'left':
                gpx, fpx = arr[cy, 1], arr[cy, off]
            else:
                gpx, fpx = arr[cy, Wd - 2], arr[cy, Wd - 1 - off]
            # Format_ARGB32_Premultiplied 内存序为 BGRA：index 2=R、index 3=A
            self.assertGreater(int(gpx[3]), 0, '%s 外侧隔离槽缺失' % d)
            self.assertGreater(int(fpx[3]), 0, '%s 主亮面缺失' % d)
            self.assertGreaterEqual(int(fpx[2]) - int(gpx[2]), 60,
                                    '%s 外侧隔离槽未与主亮面形成明暗分离' % d)
            self.assertGreater(int(((alpha > 0) & gaps).sum()), 0, '%s B 层流光缺失' % d)
        self.w._clear_hint()
        pump(self.app, 40)

    def test_hint_flow_degrade_a_only(self):
        """降级：flow_enabled=False → 仅 A（无内部流光），且停下动画时钟。"""
        import numpy as np
        outer, inner, W, PAD = self._border_paths()
        tile, gaps, bands, corner = self._hint_masks(W, PAD)
        ov = self.w._hint_overlay
        ov.set_flow_enabled(False)
        try:
            self.w._show_hint('up')
            pump(self.app, 90)
            self.assertFalse(ov._timer.isActive(), 'A-only 不应运行动画时钟')
            img = self._hint_overlay_image()
            arr = np.frombuffer(img.constBits().asstring(img.byteCount()),
                                dtype=np.uint8).reshape(img.height(), img.width(), 4)
            alpha = arr[:, :, 3].astype(np.int32)
            self.assertEqual(int(((alpha > 0) & gaps).sum()), 0, 'A-only 仍出现内部流光')
            self.assertGreater(int((alpha[bands['up']] > 0).sum()), 0, 'A-only 缺失边缘高亮')
        finally:
            ov.set_flow_enabled(True)
            self.w._clear_hint()
            pump(self.app, 40)

    def test_hint_flow_three_channels_all_directions(self):
        """B 层三通道修复：四方向三条内部缝隙均出现流光，多相位无永久空通道；每通道朝目标边运动。"""
        import numpy as np
        import v4_pyqt_2048_animated as v4
        ov = self.w._hint_overlay
        self.assertEqual(int(ov._STREAK_COUNT), 3, 'B 层应使用三条通道')
        centers = ov._gap_centers()
        self.assertEqual(len(centers), 3, '_gap_centers 必须返回三条内部缝隙（禁止截取前两条）')
        step = v4.TILE_SIZE + v4.TILE_GAP
        expect = [v4.BOARD_PADDING + v4.TILE_SIZE + v4.TILE_GAP / 2.0 + k * step for k in range(3)]
        for c, e in zip(centers, expect):
            self.assertAlmostEqual(c, e, places=6, msg='通道中心须由常量推导，不得写死绝对坐标')
        lo = v4.BOARD_PADDING + 2
        for d in ('up', 'down', 'left', 'right'):
            self.w._show_hint(d)
            pump(self.app, 80)
            mins = [10 ** 9, 10 ** 9, 10 ** 9]
            for _ in range(6):
                pump(self.app, 150)
                img = self._hint_overlay_image()
                H, Wd = img.height(), img.width()
                a = np.frombuffer(img.constBits().asstring(img.byteCount()),
                                  dtype=np.uint8).reshape(H, Wd, 4)[:, :, 3].astype(np.int32)
                for k, c in enumerate(centers):
                    cc = int(round(c))
                    if d in ('up', 'down'):
                        band = a[lo:H - lo, max(0, cc - 4):cc + 5]
                    else:
                        band = a[max(0, cc - 4):cc + 5, lo:Wd - lo]
                    mins[k] = min(mins[k], int((band > 0).sum()))
            self.assertTrue(all(m > 0 for m in mins),
                            '%s 存在永久空通道（每条通道应始终有流光）: %s' % (d, mins))
        for d in ('up', 'down', 'left', 'right'):
            for i in range(3):
                ys = []
                for tt in (0.0, 0.25, 0.5, 0.75, 0.95):
                    ov._phase = (tt - i / 3.0) % 1.0
                    items, _ = ov._flow_items(float(ov.width()), float(ov.height()), d)
                    head = items[i][1]
                    ys.append(head[1] if d in ('up', 'down') else head[0])
                if d in ('down', 'right'):
                    self.assertTrue(all(ys[j] <= ys[j + 1] + 1e-6 for j in range(len(ys) - 1)),
                                    '%s 通道%d 未朝目标边运动: %s' % (d, i, ys))
                else:
                    self.assertTrue(all(ys[j] >= ys[j + 1] - 1e-6 for j in range(len(ys) - 1)),
                                    '%s 通道%d 未朝目标边运动: %s' % (d, i, ys))
        ov._phase = 0.0
        self.w._clear_hint()
        pump(self.app, 40)

    def test_hint_overlay_clear_stops_timer(self):
        """清除/隐藏循环：停止计时器、无残留绘制（防残留 QTimer）。"""
        ov = self.w._hint_overlay
        self.w._show_hint('left')
        pump(self.app, 60)
        self.assertTrue(ov.isVisible())
        self.w._clear_hint()
        pump(self.app, 40)
        self.assertFalse(ov.isVisible())
        self.assertFalse(ov._timer.isActive())
        for _ in range(5):
            self.w._show_hint('up'); pump(self.app, 20)
            self.w._clear_hint(); pump(self.app, 20)
        self.assertFalse(ov.isVisible())
        self.assertFalse(ov._timer.isActive())

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
        # 单步建议为常驻跟随：等首次建议给出后显式停止以结算会话
        wait_until(self.app, lambda: not self.w._solve_in_flight
                   and self.w.solver_log.count() >= 2)
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
        # 单步建议为常驻跟随：等首次建议给出（不再自动停止）
        wait_until(self.app, lambda: not self.w._solve_in_flight
                   and self.w.solver_log.count() >= 2)
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
        self.w.on_solver_clicked()                                 # 停止常驻跟随
        wait_until(self.app, lambda: not self.w._solver_running)

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

    def test_stale_result_does_not_clear_inflight_flag(self):
        """H3：过期（job_id 不匹配）结果/失败不得在被判定前清零新任务的 _solve_in_flight。"""
        grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
        self._set_grid(grid)
        self.w._solver_running = True
        self.w._solver_mode = "single"
        self.w._job_id = 5
        self.w._board_sig = self.w._board_signature(grid)
        self.w.solver_progress.setRange(0, 0)              # 模拟“忙态”进度条
        self.w._solve_in_flight = True                     # 新任务在途

        # 旧 job_id 的结果到达 → 丢弃，且不得清零在途标志 / 改回进度条
        self.w._on_solver_result(3, {"best_direction": "left", "best_name": "向左",
                                     "evaluations": {"left": 1.0}, "elapsed_ms": 1.0})
        self.assertTrue(self.w._solve_in_flight, "过期结果清零了新任务的在途标志")
        self.assertEqual(self.w.solver_progress.maximum(), 0, "过期结果改动了进度条")

        # 旧 job_id 的失败到达 → 同样不得清零
        self.w._on_solver_failed(3, "旧任务异常")
        self.assertTrue(self.w._solve_in_flight, "过期失败清零了新任务的在途标志")

        # 当前 job_id 的结果才允许收尾
        self.w._on_solver_result(5, {"best_direction": "left", "best_name": "向左",
                                     "evaluations": {"left": 1.0}, "elapsed_ms": 1.0})
        self.assertFalse(self.w._solve_in_flight)
        self.w._solver_running = False
        self.w._shutdown_worker()

    def test_stop_restart_stress_10x_no_thread_leak(self):
        """H7-2：连续停止/重启 10 次——无 QThread 告警、无线程泄漏、job_id 严格递增。

        通过 qInstallMessageHandler 捕获 Qt 运行期消息，断言不出现
        “Destroyed while thread is still running” 等线程失控告警。
        """
        from PyQt5.QtCore import qInstallMessageHandler
        captured = []

        def _handler(_mode, _ctx, msg):
            captured.append(str(msg))

        old = qInstallMessageHandler(_handler)
        try:
            self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
            self.w.solver_mode.setCurrentIndex(1)                 # 单步建议（避免自动走子干扰）
            self._select_strategy("mcts")
            ids = []
            for _ in range(10):
                self.w.on_solver_clicked()                        # 启动
                self.assertTrue(wait_until(self.app, lambda: self.w._solver_running,
                                           timeout_ms=3000), "第 %d 次未能启动" % (len(ids) + 1))
                ids.append(self.w._job_id)
                self.w.on_solver_clicked()                        # 立即停止
                self.assertTrue(wait_until(
                    self.app,
                    lambda: not self.w._solver_running and not self.w._solve_in_flight,
                    timeout_ms=4000), "第 %d 次停止未收敛" % len(ids))
            self.assertEqual(len(ids), 10)
            self.assertEqual(ids, sorted(set(ids)), "job_id 必须严格递增且不重复")
            # 线程回收：主引用为空，退休列表内线程均已结束
            self.assertIsNone(self.w._solver_thread)
            self.assertIsNone(self.w._solver_worker)
            for t, _wb in self.w._retired_threads:
                self.assertFalse(t.isRunning(), "存在未结束的退休线程")
            running = [t for t, _w in self.w._retired_threads if t.isRunning()]
            bad = [m for m in captured
                   if ("Destroyed while thread is still running" in m
                       or "QThread: Destroyed" in m
                       or "QObject::~QObject" in m)]
            print("\n[H7-2] 启动次数=%d 取消次数=%d 活跃退休线程=%d 采集Qt消息=%d 危险告警=%s"
                  % (len(ids), len(ids), len(running), len(captured), bad))
            print("[H7-2] 采集到的 Qt 消息样例（用于确认无失控告警）：%s"
                  % (" | ".join(captured[:6]) if captured else "无"))
            self.assertEqual(bad, [], "出现 Qt 线程/对象失控告警：%s" % bad)
        finally:
            qInstallMessageHandler(old)
            self.w._solver_running = False
            self.w._shutdown_worker()

    # ================= H8-1：C01–C06 在途取消确定性场景（started/release 屏障） =================
    def test_h8_c01_stop_while_in_compute(self):
        """C01：worker 确认进入计算 → 停止 → 放行旧计算：棋盘不变、结果不落地、无幽灵任务。"""
        ctrl = self._install_blocking_solver()
        try:
            grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
            self._set_grid(grid)
            self.w.solver_mode.setCurrentIndex(1)
            self._select_strategy("mcts")
            before = [row[:] for row in self.w.model.grid]
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000),
                            "worker 未进入计算阶段")
            t_cancel = time.perf_counter()
            self.w.on_solver_clicked()                    # 在途停止
            stop_block_ms = (time.perf_counter() - t_cancel) * 1000.0
            ctrl['release'].set()                         # 放行旧计算
            self.assertTrue(self._wait_threads_quiet(8000), "线程未在预算内回收")
            self.assertEqual(self.w.model.grid, before, "取消后棋盘被改变（不应发生）")
            self.assertFalse(self.w._solver_running)
            self.assertFalse(self.w._solve_in_flight)
            print("\n[C01] entered=True stop_block=%.0fms solver_calls=%d" % (stop_block_ms, ctrl['calls']))
        finally:
            self._restore_blocking_solver()
            self.w._shutdown_worker()

    def test_h8_c02_late_solved_from_old_task(self):
        """C02：旧任务进入计算 → 停止 → 启动新任务 → 旧 solved 迟到投递：不得污染新任务。"""
        ctrl = self._install_blocking_solver()
        try:
            self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
            self.w.solver_mode.setCurrentIndex(1)
            self._select_strategy("mcts")
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000))
            job1 = self.w._job_id
            worker1 = self.w._solver_worker
            emitted = threading.Event()
            worker1.solved.connect(lambda j, r: emitted.set(), Qt.DirectConnection)  # worker 线程内确认 emit
            ctrl['release'].set()                          # 放行 task1 计算
            self.assertTrue(ctrl['returned'].wait(3.0), "_solve 未返回")
            self.assertTrue(emitted.wait(3.0), "worker 未 emit solved")
            # 此间未 processEvents，queued solved(job1) 尚未投递到主线程
            ctrl['release'].clear()                        # 让 task2 继续阻塞在计算中
            ctrl['entered'].clear()
            self.w.on_solver_clicked()                     # 停止 task1
            self.w.on_solver_clicked()                     # 启动 task2
            job2 = self.w._job_id
            self.assertNotEqual(job1, job2)
            self.assertTrue(self.w._solve_in_flight, "task2 未在途")
            before_log = self.w.solver_log.count()
            self.assertTrue(wait_until(self.app, lambda: self.w.solver_log.count() > before_log, 3000),
                            "迟到的旧 solved 未被识别/忽略")
            self.assertTrue(self.w._solve_in_flight, "旧 solved 清零了新任务 _solve_in_flight")
            print("\n[C02] job1=%d job2=%d late_solved_discarded=True inflight_kept=True" % (job1, job2))
            ctrl['release'].set()                          # 放行 task2
            self._wait_threads_quiet(8000)
        finally:
            self._restore_blocking_solver()
            self.w._shutdown_worker()

    def test_h8_c03_late_failed_from_old_task(self):
        """C03：C02 的旧 failed 迟到：新任务运行态不变，不弹旧任务错误。"""
        ctrl = self._install_blocking_solver()
        ctrl['raise_exc'] = RuntimeError("old-task-boom")
        try:
            self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
            self.w.solver_mode.setCurrentIndex(1)
            self._select_strategy("mcts")
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000))
            job1 = self.w._job_id
            worker1 = self.w._solver_worker
            failed_emit = threading.Event()
            worker1.failed.connect(lambda j, m: failed_emit.set(), Qt.DirectConnection)
            ctrl['release'].set()
            self.assertTrue(ctrl['returned'].wait(3.0))
            self.assertTrue(failed_emit.wait(3.0), "worker 未 emit failed")
            ctrl['release'].clear()                        # 让 task2 继续阻塞在计算中
            ctrl['entered'].clear()
            self.w.on_solver_clicked()                     # 停止 task1
            self.w.on_solver_clicked()                     # 启动 task2
            self.assertTrue(self.w._solve_in_flight)
            pump(self.app, 250)                            # 投递迟到的旧 failed
            self.assertTrue(self.w._solve_in_flight, "旧 failed 改动了新任务在途状态")
            print("\n[C03] job1=%d late_failed_discarded=True inflight_kept=True" % job1)
            ctrl['release'].set()
            self._wait_threads_quiet(8000)
        finally:
            self._restore_blocking_solver()
            self.w._shutdown_worker()

    def test_h8_c04_close_window_while_in_compute(self):
        """C04：已进入计算时关闭窗口 → 放行旧任务：无 QThread 销毁告警、引用持续到完成。"""
        from PyQt5.QtCore import qInstallMessageHandler
        msgs = []
        old = qInstallMessageHandler(lambda m, c, s: msgs.append(str(s)))
        ctrl = self._install_blocking_solver()
        try:
            self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
            self.w.solver_mode.setCurrentIndex(1)
            self._select_strategy("mcts")
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000))
            thread = self.w._solver_thread                    # 关闭前捕获引用
            self.w.close()
            pump(self.app, 200)
            ctrl['release'].set()                             # 放行旧任务
            self.assertTrue(wait_until(self.app, lambda: thread is not None and not thread.isRunning(), 8000),
                            "关闭后线程未结束")
            bad = [m for m in msgs if ("Destroyed while thread is still running" in m
                                       or "QThread: Destroyed" in m)]
            self.assertEqual(bad, [], "关闭窗口时出现线程销毁告警：%s" % bad)
            print("\n[C04] thread_finished=True qt_bad_warnings=0")
        finally:
            self._restore_blocking_solver()
            try:
                self.w._shutdown_worker()
            except Exception:                                 # noqa: BLE001
                pass
            qInstallMessageHandler(old)

    def test_h8_c05_ten_inflight_cancels(self):
        """C05：连续 10 次在途取消（每次确认已进入计算）：job_id 单调唯一、线程可追踪、最终归零。"""
        ctrl = self._install_blocking_solver()
        try:
            grid = [[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]]
            ids = []
            for i in range(10):
                ctrl['entered'].clear()
                ctrl['release'].clear()
                self._set_grid(grid)
                self.w.solver_mode.setCurrentIndex(1)
                self._select_strategy("mcts")
                self.w.on_solver_clicked()
                self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000),
                                "第 %d 次未进入计算" % (i + 1))
                ids.append(self.w._job_id)
                self.w.on_solver_clicked()                # 在途取消
                ctrl['release'].set()
                self.assertTrue(wait_until(
                    self.app,
                    lambda: self.w._solver_thread is None
                    and not any(t.isRunning() for t, _w in self.w._retired_threads), 8000),
                    "第 %d 次线程未回收" % (i + 1))
            self.assertEqual(len(ids), 10)
            self.assertEqual(ids, sorted(set(ids)), "job_id 必须单调且唯一")
            live = [t for t, _w in self.w._retired_threads if t.isRunning()]
            self.assertEqual(live, [], "存在未回收线程")
            print("\n[C05] inflight_cancels=%d job_ids=%s live_threads=%d solver_calls=%d"
                  % (len(ids), ids, len(live), ctrl['calls']))
        finally:
            self._restore_blocking_solver()
            self.w._shutdown_worker()

    def test_h8_c06_ui_ops_during_inflight(self):
        """C06：在途求解期间折叠/展开、拖动 splitter、缩放窗口、切模式：不重复提交、展开入口可用。"""
        ctrl = self._install_blocking_solver()
        try:
            self._set_grid([[2, 2, 4, 8], [0, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 2]])
            self.w.solver_mode.setCurrentIndex(1)
            self._select_strategy("mcts")
            self.w.on_solver_clicked()
            self.assertTrue(wait_until(self.app, lambda: ctrl['entered'].is_set(), 4000))
            job = self.w._job_id
            calls0 = ctrl['calls']
            # 折叠/展开 ×3
            for _ in range(3):
                self.w._toggle_solver(); pump(self.app, 60)
                self.w._toggle_solver(); pump(self.app, 60)
            # splitter 拖动 + 窗口缩放 + 模式切换
            self.w.splitter.setSizes([420, 480]); pump(self.app, 40)
            self.w.resize(1000, 780); pump(self.app, 60)
            self.w.resize(760, 620); pump(self.app, 60)
            self.w.solver_mode.setCurrentIndex(0)          # auto
            self.w.solver_mode.setCurrentIndex(1)          # single
            pump(self.app, 120)
            # 不重复提交任务
            self.assertEqual(ctrl['calls'], calls0, "UI 操作触发了新的求解提交")
            self.assertEqual(self.w._job_id, job, "UI 操作改变了 job_id")
            self.assertTrue(self.w._solver_running, "在途任务被 UI 操作打断")
            # 折叠后再展开：入口可用
            self.w._set_solver_collapsed(True); pump(self.app, 120)
            self.assertTrue(self.w._solver_collapsed)
            self.assertIsNotNone(getattr(self.w, "solver_edge_handle", None))
            self.w._set_solver_collapsed(False); pump(self.app, 120)
            self.assertFalse(self.w._solver_collapsed)
            print("\n[C06] no_resubmit=True job_stable=%d edge_handle_ok=True" % job)
            ctrl['release'].set()
            self._wait_threads_quiet(8000)
        finally:
            self._restore_blocking_solver()
            self.w._shutdown_worker()

    # ================= 最终收口：sessions.json 原子保存 + 故障回滚 =================
    def test_sessions_atomic_save_and_rollback(self):
        """原子保存：紧凑单行 JSON；覆盖前转存 .bak；写入故障不破坏原文件；主文件损坏可由 .bak 回滚。"""
        import json as _json
        from unittest import mock
        w = self.w
        sf = self.v5.SESSIONS_FILE
        # 1) 首次保存：紧凑单行、无 .tmp 残留
        w._sessions = [{"id": "s1", "steps": [{"step": 1}]}]
        w._save_sessions()
        raw = open(sf, encoding="utf-8").read()
        self.assertNotIn("\n", raw, "应保持紧凑（单行）JSON")
        self.assertEqual(_json.loads(raw)[0]["id"], "s1")
        self.assertFalse(os.path.exists(sf + ".tmp"))
        # 2) 再次保存：旧版转存为 .bak（回滚点）
        w._sessions = [{"id": "s1"}, {"id": "s2"}]
        w._save_sessions()
        self.assertTrue(os.path.exists(sf + ".bak"), "覆盖前应生成 .bak 回滚点")
        self.assertEqual([s["id"] for s in w._load_sessions()], ["s1", "s2"])
        # 3) 故障A：主文件“写入中断”损坏 → 由 .bak 回滚读取（不返回空、不丢历史）
        with open(sf, "w", encoding="utf-8") as f:
            f.write('{"半截"')
        self.assertEqual([s["id"] for s in w._load_sessions()], ["s1"], "应由 .bak 回滚")
        # 恢复主文件
        w._sessions = [{"id": "s1"}, {"id": "s2"}]
        w._save_sessions()
        before = open(sf, encoding="utf-8").read()
        # 4) 故障B：保存时原子替换抛错 → 原主文件保持不变、无 .tmp 残留
        with mock.patch("os.replace", side_effect=OSError("inject-failure")):
            w._sessions = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
            w._save_sessions()
        self.assertEqual(open(sf, encoding="utf-8").read(), before, "故障时不得破坏原文件")
        self.assertFalse(os.path.exists(sf + ".tmp"), "故障后应清理临时文件")
        self.assertEqual([s["id"] for s in w._load_sessions()], ["s1", "s2"])
        print("\n[H9] sessions atomic save + rollback: PASS (compact=True, bak_rollback=True, fault_safe=True)")



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
