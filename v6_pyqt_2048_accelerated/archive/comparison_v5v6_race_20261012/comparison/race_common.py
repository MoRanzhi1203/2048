#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛混入：把 V5/V6 既有 GUI 的「自动连走」扩展为可协调的竞赛会话。

设计：**不修改 V5/V6 源码**，以 Mixin 形式复用其既有的求解循环
（`_start_solver` / `_request_decision` / `_on_solver_result` / `_record_step` /
`_on_animation_finished`），仅在其前后加：种子与初始棋盘、协调控制文件、
计时（perf_counter）、HUD、步数/时间上限、暂停/停止/重置。

复用而非复制：所有棋盘/动画/求解逻辑仍来自被继承的 V5.1（v5/v4/v3）代码。
"""

from __future__ import annotations

import os
import random
import time
from time import perf_counter

_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in __import__('sys').path:
    __import__('sys').path.insert(0, _THIS)

from race_protocol import (SideLogger, generate_initial_board, load_session,  # noqa: E402
                           now_iso, write_json)

from PyQt5.QtCore import Qt, QTimer                                        # noqa: E402
from PyQt5.QtWidgets import QLabel                                         # noqa: E402


class RaceHud(QLabel):
    """紧凑指标 HUD（插入右侧求解面板顶部，不遮挡棋盘与主要按钮）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setStyleSheet(
            'background:#2b2622; color:#f3ead9; border:1px solid #5a5048;'
            ' border-radius:6px; padding:6px 8px; font-family:Consolas,Menlo,monospace;'
            ' font-size:11px;')


class RaceMixin:
    """竞速混入。要求宿主是 V5/V6 的 SolverMainWindow 子类。"""

    RACE_SIDE = 'v5'
    RACE_LABEL = 'V5'

    # ---------------------------------------------------------- 生命周期
    def init_ui(self):
        super().init_ui()
        self._race_attach()

    def _race_attach(self):
        session_dir = os.environ.get('V6_RACE_SESSION')
        self._race_enabled = bool(session_dir)
        if not session_dir:
            return
        self._race_dir = session_dir
        self._race_cfg = load_session(os.path.join(session_dir, 'session.json')) or {}
        self.logger = SideLogger(session_dir, self.RACE_SIDE)
        self._race_paused = False
        self._race_started = False
        self._race_step_index = 0
        self._race_seq_seen = -1        # 首次轮询即处理启动时已存在的 cmd=start
        self._race_search_t0 = None
        self._race_anim_t0 = None
        self._race_wall_t0 = perf_counter()
        self._race_stats = {
            'search_ms_list': [], 'search_cum_ms': 0.0, 'anim_cum_ms': 0.0,
            'decisions': 0, 'moves': 0, 'sims_cum': 0,
            'backend_used': None, 'engine_used': None,
            'last_search_wall_ms': None, 'last_solver_ms': None,
            'last_nodes': None, 'timed_out_count': 0,
        }
        self._race_build_hud()
        self._race_apply_runtime_tweaks()
        self._race_timer = QTimer(self)
        self._race_timer.timeout.connect(self._race_tick)
        self._race_timer.start(120)
        self._race_hud_timer = QTimer(self)
        self._race_hud_timer.timeout.connect(self._race_refresh_hud)
        self._race_hud_timer.start(250)
        self.setWindowTitle(self._race_title())
        self.logger.event('boot', pid=os.getpid(), side=self.RACE_SIDE,
                          mode=self._race_cfg.get('mode'), seed=self._race_cfg.get('seed'),
                          python=__import__('sys').executable)

    def _race_build_hud(self):
        label = RaceHud(self)
        self._race_hud = label
        container = getattr(self, 'solver_container', None)
        lay = container.layout() if container is not None else None
        if lay is not None:
            lay.insertWidget(0, label)
        else:                                    # 兜底：贴在窗口左上
            label.setParent(self)
            label.setGeometry(6, 6, 470, 150)
            label.show()

    def _race_apply_runtime_tweaks(self):
        """竞赛态运行期微调（**进程内、两侧一致**，不修改 V5/V6 源码）：

        - 放宽自动连走的步间停顿，降低连续动画的压力；
        - 默认关闭窗口级粒子层（仅解绑/隐藏，不改动其源码与参数），减少渲染抖动与内存压力。
        """
        try:
            import v5_pyqt_2048_solver as _g
            _g.STEP_DELAY_MS = int(os.environ.get('V6_RACE_STEP_DELAY_MS', '120'))
        except Exception:                                       # noqa: BLE001
            pass
        if self._race_cfg.get('particles', False):
            return
        try:
            bv = getattr(self, 'board_view', None)
            if bv is not None and hasattr(bv, 'bind_particle_layer'):
                bv.bind_particle_layer(None)                    # emit_* 变为 no-op
        except Exception:                                       # noqa: BLE001
            pass
        try:
            pl = getattr(self, 'particle_layer', None)
            if pl is not None:
                pl.hide()
        except Exception:                                       # noqa: BLE001
            pass

    # ---------------------------------------------------------- 标题 / HUD
    def _race_title(self):
        cfg = self._race_cfg
        return '2048 %s RACE · mode=%s seed=%s pid=%d' % (
            self.RACE_LABEL, cfg.get('mode'), cfg.get('seed'), os.getpid())

    def _race_refresh_hud(self):
        if not getattr(self, '_race_enabled', False):
            return
        st = self._race_stats
        lst = sorted(st['search_ms_list'])
        p95 = lst[min(len(lst) - 1, int(round(0.95 * (len(lst) - 1))))] if lst else 0.0
        avg = (sum(lst) / len(lst)) if lst else 0.0
        wall = perf_counter() - self._race_wall_t0
        sched = max(0.0, wall * 1000.0 - st['search_cum_ms'] - st['anim_cum_ms'])
        cfg = self._race_cfg
        try:
            grid = self.model.grid
            max_tile = max(max(r) for r in grid) if grid else 0
            score = self.model.score
        except Exception:                                       # noqa: BLE001
            max_tile, score = 0, 0
        status = 'paused' if self._race_paused else ('running' if self._race_started else 'idle')
        self._race_hud.setText(
            '[%s] mode=%s seed=%s pid=%d status=%s\n'
            'score=%d max=%d steps=%d/%s decisions=%d\n'
            'search ms: last=%s avg=%.2f p95=%.2f cum=%.1f\n'
            'anim cum=%.1fs sched cum=%.1fs wall=%.1fs\n'
            'sims/nodes=%s backend=%s engine=%s'
            % (self.RACE_LABEL, cfg.get('mode'), cfg.get('seed'), os.getpid(), status,
               score, max_tile, self._race_step_index, cfg.get('max_steps'),
               self._race_stats['decisions'],
               ('%.1f' % st['last_search_wall_ms']) if st['last_search_wall_ms'] else '—',
               avg, p95, st['search_cum_ms'] / 1000.0,
               st['anim_cum_ms'] / 1000.0, sched / 1000.0, wall,
               st['sims_cum'] if st['sims_cum'] else (st['last_nodes'] or '—'),
               st['backend_used'] or '—', st['engine_used'] or '—'))
        self._race_write_hud()

    def _race_write_hud(self):
        st = self._race_stats
        lst = sorted(st['search_ms_list'])
        p95 = lst[min(len(lst) - 1, int(round(0.95 * (len(lst) - 1))))] if lst else 0.0
        avg = (sum(lst) / len(lst)) if lst else 0.0
        wall = perf_counter() - self._race_wall_t0
        try:
            grid = self.model.grid
            max_tile = max(max(r) for r in grid) if grid else 0
            score = self.model.score
            game_over = bool(self.model.game_over)
        except Exception:                                       # noqa: BLE001
            max_tile, score, game_over = 0, 0, False
        self.logger.hud_snapshot(
            side=self.RACE_SIDE, label=self.RACE_LABEL, pid=os.getpid(),
            mode=self._race_cfg.get('mode'), seed=self._race_cfg.get('seed'),
            status=('paused' if self._race_paused else
                    ('running' if self._race_started else 'idle')),
            score=score, max_tile=max_tile, steps=self._race_step_index,
            max_steps=self._race_cfg.get('max_steps'), decisions=st['decisions'],
            moves=st['moves'], last_search_ms=st['last_search_wall_ms'],
            last_solver_ms=st['last_solver_ms'],
            avg_search_ms=round(avg, 3), p95_search_ms=round(p95, 3),
            search_cum_ms=round(st['search_cum_ms'], 3),
            anim_cum_ms=round(st['anim_cum_ms'], 3),
            sched_cum_ms=round(max(0.0, wall * 1000.0 - st['search_cum_ms'] - st['anim_cum_ms']), 3),
            wall_s=round(wall, 3), sims=st['sims_cum'], last_nodes=st['last_nodes'],
            backend_used=st['backend_used'], engine_used=st['engine_used'],
            timed_out_count=st['timed_out_count'], game_over=game_over,
            updated_at=now_iso())

    # ---------------------------------------------------------- 控制
    def _race_tick(self):
        if not getattr(self, '_race_enabled', False):
            return
        ctl = self.logger.control()
        seq = int(ctl.get('seq', 0))
        if seq != self._race_seq_seen:
            self._race_seq_seen = seq
            self._race_handle_cmd(ctl.get('cmd'))

    def _race_handle_cmd(self, cmd):
        if cmd == 'start':
            if not self._race_started:
                self._race_start()
        elif cmd == 'pause':
            self._race_paused = True
            self.logger.event('pause')
        elif cmd == 'resume':
            self._race_paused = False
            self.logger.event('resume')
            if self._race_started and not self._solver_running:
                self._start_solver()
        elif cmd == 'stop':
            self._race_paused = True
            if self._solver_running:
                self._stop_solver('竞赛停止')
            self.logger.event('stop', steps=self._race_step_index)
        elif cmd == 'reset':
            self._race_reset()
        elif cmd == 'quit':
            self.logger.event('quit')
            self.close()

    # ---------------------------------------------------------- 会话
    def _race_solver_overrides(self):
        cfg = dict(self._race_cfg.get('algorithm') or {})
        cfg.pop('strategy', None)
        cfg['seed'] = int(self._race_cfg.get('seed', 2048))
        return cfg

    def _race_apply_widgets(self):
        algo = self._race_cfg.get('algorithm') or {}
        try:
            idx = self.solver_strategy.findData(algo.get('strategy', 'expectimax'))
            if idx >= 0:
                self.solver_strategy.setCurrentIndex(idx)
        except Exception:                                       # noqa: BLE001
            pass
        try:
            if self.solver_mode is not None:
                idx = self.solver_mode.findData('auto')
                if idx >= 0:
                    self.solver_mode.setCurrentIndex(idx)
        except Exception:                                       # noqa: BLE001
            pass

    def _race_inject_board(self):
        board = generate_initial_board(self._race_cfg.get('seed', 2048))
        self.model.grid = [row[:] for row in board]
        self.model.score = 0
        self.model.game_over = False
        self.model.won = False
        try:
            self.model.undo_stack.clear()
            self.model.redo_stack.clear()
        except Exception:                                       # noqa: BLE001
            pass
        self.refresh()
        self.logger.event('board_injected', board=board)
        return board

    def _race_start(self):
        random.seed(int(self._race_cfg.get('seed', 2048)))
        self.start_new_game()
        self._race_inject_board()
        self._race_apply_widgets()
        self._race_started = True
        self._race_paused = False
        self._race_step_index = 0
        st = self._race_stats
        st['search_ms_list'] = []
        st['search_cum_ms'] = 0.0
        st['anim_cum_ms'] = 0.0
        st['decisions'] = 0
        st['moves'] = 0
        st['sims_cum'] = 0
        st['timed_out_count'] = 0
        self._race_wall_t0 = perf_counter()
        self.logger.event('start', mode=self._race_cfg.get('mode'),
                          algorithm=self._race_cfg.get('algorithm'))
        self._start_solver()

    def _race_reset(self):
        if self._solver_running:
            self._stop_solver('重置')
        self._race_start()
        self.logger.event('reset')

    # ---------------------------------------------------------- 求解挂钩
    def _race_barrier_ok(self):
        if self._race_cfg.get('mode') != 'A':
            return True
        return self._race_step_index < self.logger.control_step_index()

    def _request_decision(self):
        if not getattr(self, '_race_enabled', False) or not self._race_started:
            return super()._request_decision()
        if self._race_paused or not self._race_barrier_ok():
            QTimer.singleShot(80, self._request_decision)       # 稍后重试（不被卡死）
            return
        if isinstance(getattr(self, '_solver_config', None), dict):
            self._solver_config.update(self._race_solver_overrides())
        self._race_search_t0 = perf_counter()
        super()._request_decision()
        if not getattr(self, '_solve_in_flight', False):
            self._race_search_t0 = None                          # 未真正发起：不残留计时

    def _on_solver_result(self, job_id, result):
        if getattr(self, '_race_enabled', False) and self._race_search_t0 is not None:
            self._race_stats['last_search_wall_ms'] = \
                (perf_counter() - self._race_search_t0) * 1000.0
            self._race_search_t0 = None
        self._race_anim_t0 = perf_counter()
        super()._on_solver_result(job_id, result)

    def _on_animation_finished(self):
        if getattr(self, '_race_enabled', False) and self._race_anim_t0 is not None:
            self._race_stats['anim_cum_ms'] += (perf_counter() - self._race_anim_t0) * 1000.0
            self._race_anim_t0 = None
        super()._on_animation_finished()

    def _record_step(self):
        res = getattr(self, '_pending_result', None)
        super()._record_step()
        if getattr(self, '_race_enabled', False) and res is not None and self._race_started:
            self._race_on_step(res)

    def _race_on_step(self, res):
        st = self._race_stats
        st['decisions'] += 1
        st['moves'] += 1
        self._race_step_index += 1
        solver_ms = float(res.get('elapsed_ms') or 0.0)
        st['search_ms_list'].append(solver_ms)
        st['search_cum_ms'] += solver_ms
        st['last_solver_ms'] = round(solver_ms, 3)
        if res.get('timed_out'):
            st['timed_out_count'] += 1
        st['last_nodes'] = res.get('nodes')
        st['sims_cum'] += int(res.get('completed_simulations') or res.get('simulations') or 0)
        st['backend_used'] = res.get('backend_used', 'reference')  # V5 结果无此字段 -> reference
        st['engine_used'] = res.get('engine_used', 'reference')
        wall = perf_counter() - self._race_wall_t0
        self.logger.step(
            step=self._race_step_index, direction=res.get('best_direction'),
            score=res.get('score'), solver_ms=round(solver_ms, 3),
            wall_search_ms=(round(st['last_search_wall_ms'], 3)
                            if st['last_search_wall_ms'] else None),
            nodes=res.get('nodes'), depth_reached=res.get('depth_reached'),
            timed_out=bool(res.get('timed_out')),
            backend_used=st['backend_used'], engine_used=st['engine_used'],
            fallback_reason=res.get('backend_fallback_reason'),
            score_now=getattr(self.model, 'score', None),
            max_tile=(max(max(r) for r in self.model.grid) if self.model.grid else 0),
            wall_s=round(wall, 3))
        self._race_refresh_hud()
        # 上限（禁止无限自动运行）
        if self._race_step_index >= int(self._race_cfg.get('max_steps', 200)):
            self._race_stop_limits('达到最大步数 %s' % self._race_cfg.get('max_steps'))
        elif wall >= float(self._race_cfg.get('max_seconds', 180.0)):
            self._race_stop_limits('达到最长运行时间 %ss' % self._race_cfg.get('max_seconds'))

    def _race_stop_limits(self, reason):
        if self._solver_running:
            self._stop_solver(reason)
        self._race_paused = True
        self.logger.event('limit_reached', reason=reason, steps=self._race_step_index)
        if self._race_cfg.get('auto_exit'):
            QTimer.singleShot(600, self._race_finish_and_close)

    def _race_finish_and_close(self):
        self._race_write_hud()
        self.close()

    # ---------------------------------------------------------- 关闭
    def closeEvent(self, event):
        if getattr(self, '_race_enabled', False):
            try:
                self._race_write_hud()
                self.logger.event('close', steps=self._race_step_index,
                                  score=getattr(self.model, 'score', None))
            except Exception:                                   # noqa: BLE001
                pass
        super().closeEvent(event)
