#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 正式 GUI 的可持久化三档「运行速度」（**仅 V6**，V1–V5 只读）。

职责边界（互不越界）：
    求解强度（V5 既有下拉，原「运行方式」）  仅决定**算法参数**（搜索深度/预算/强度）
    求解模式（V5 既有下拉，原「模式」）      仅决定**自动连走 / 单步建议**
    运行速度（本模块）                       仅决定**动画 / 步间等待 / UI 调度**

三档（同一状态源 `self._v6_speed`，同一持久化文件 `config/ui_prefs.json`）：
    standard 标准展示：保留走子动画 + 原有步间停顿（默认）
    fast     快速演示：保留动画，大幅缩短步间停顿、指标每 2 步更新
    extreme  极限性能：**关闭走子动画与人工等待**，指标每 N 步批量更新；
             推进仍由 0ms 定时器逐轮驱动（事件循环友好，非主线程死循环）

分段计时（perf_counter，累计 ms）：搜索 / 动画 / 固定等待 / 渲染 / 总耗时 / 步数。

实现方式：以 Mixin 复用 V5/V6 既有自动连走流程，**不修改 V5/V6 既有源码文件**；
V5 面板中的「运行方式 / 模式」两个标签由本模块在 V6 进程内**运行时改名**
（求解强度 / 求解模式），选项与内部参数映射完全保留。
"""

from __future__ import annotations

import json
import os
import time
from time import perf_counter

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
PREFS_PATH = os.path.join(_HERE, 'config', 'ui_prefs.json')

TIERS = ('standard', 'fast', 'extreme')
TIER_LABELS = (('标准', 'standard'), ('快速', 'fast'), ('极限', 'extreme'))

TIER_PARAMS = {
    'standard': {'anim_off': False, 'step_delay_ms': 70, 'metrics_every': 1},
    'fast':     {'anim_off': False, 'step_delay_ms': 10, 'metrics_every': 2},
    'extreme':  {'anim_off': True,  'step_delay_ms': 0,  'metrics_every': 8},
}

_SEG_QSS = (
    'QPushButton { background:#3a332d; color:#e2d7c7; border:1px solid #5a5048;'
    ' border-radius:4px; padding:5px 0px; font-size:11px; }'
    'QPushButton:hover { background:#463d35; }'
    'QPushButton:checked { background:#c9a227; color:#241d15; font-weight:bold;'
    ' border:1px solid #c9a227; }')

_TIMING_QSS = (
    'background:#2b2622; color:#f3ead9; border:1px solid #5a5048;'
    ' border-radius:6px; padding:5px 8px; font-family:Consolas,Menlo,monospace;'
    ' font-size:11px;')


def load_prefs():
    try:
        with open(PREFS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_prefs(prefs):
    try:
        os.makedirs(os.path.dirname(PREFS_PATH), exist_ok=True)
        tmp = PREFS_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, PREFS_PATH)
        return True
    except OSError:
        return False


class V6SpeedMixin:
    """运行速度（三档）+ 分段计时 + 标签改名混入。宿主须为 V5/V6 SolverMainWindow 子类。"""

    # ---------------------------------------------------------- 初始化
    def _v6_speed_init(self):
        import v5_pyqt_2048_solver as _v5gui
        self._v5gui = _v5gui
        prefs = load_prefs()
        tier = prefs.get('speed_tier')
        self._v6_speed = tier if tier in TIERS else 'standard'
        self._v6_pending_tier = None
        self._v6_t = {'search_ms': 0.0, 'anim_ms': 0.0, 'wait_ms': 0.0, 'render_ms': 0.0,
                      'steps': 0, 'start': perf_counter(), 'req_t0': None, 'anim_t0': None,
                      'wait_t0': None, 'metrics_steps': 0}
        self._v6_render_accum = False
        self._v6_rename_solver_labels()      # 运行方式->求解强度；模式->求解模式（仅 V6 进程）
        self._v6_install_speed_panel()       # 主面板「运行速度」三档切换 + 分段计时读数
        self._v6_apply_tier(self._v6_speed, persist=False)

    # ---------------------------------------------------------- 标签改名（不改 V5 源码）
    def _v6_rename_solver_labels(self):
        try:
            form_group = self.solver_depth.parentWidget()
            lay = form_group.layout()
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget() if item is not None else None
                if isinstance(w, QLabel):
                    if w.text() == '运行方式':
                        w.setText('求解强度')
                    elif w.text() == '模式':
                        w.setText('求解模式')
            if hasattr(self, 'solver_depth'):
                self.solver_depth.setToolTip('求解强度（原“运行方式”）：仅决定算法参数'
                                             '——搜索深度 / 时间预算 / 强度，不影响动画速度')
            if hasattr(self, 'solver_mode'):
                self.solver_mode.setToolTip('求解模式：自动连走（AI 驱动棋盘）或'
                                            '单步建议（常驻跟随，给出下一步最佳方向）')
        except Exception:                                        # noqa: BLE001
            pass

    # ---------------------------------------------------------- UI：主面板「运行速度」
    def _v6_install_speed_panel(self):
        group = QWidget()
        group.setObjectName('v6SpeedPanel')
        apply_style = getattr(self, '_make_solver_group', None)
        if callable(apply_style):
            try:
                group = self._make_solver_group()
                group.setObjectName('v6SpeedPanel')
            except Exception:                                    # noqa: BLE001
                group = QWidget()
        box = QVBoxLayout(group)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(10)
        lab = QLabel('运行速度')
        lab.setStyleSheet('color:#8f8175; font-size:12px;')
        lab.setFixedWidth(58)
        head.addWidget(lab, 0, Qt.AlignVCenter)

        seg = QHBoxLayout()
        seg.setSpacing(4)
        self.v6_speed_buttons = {}
        self.v6_speed_group = QButtonGroup(self)
        self.v6_speed_group.setExclusive(True)
        for text, key in TIER_LABELS:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_SEG_QSS)
            btn.setToolTip({'standard': '标准：保留动画与原有步间停顿',
                            'fast': '快速：保留动画，缩短步间等待',
                            'extreme': '极限：关闭走子动画与人工等待（性能优先）'}[key])
            btn.clicked.connect(lambda _checked, k=key: self._v6_on_speed_clicked(k))
            seg.addWidget(btn)
            self.v6_speed_group.addButton(btn)
            self.v6_speed_buttons[key] = btn
        head.addLayout(seg, 1)
        box.addLayout(head)

        self.v6_timing_label = QLabel()
        self.v6_timing_label.setWordWrap(True)
        self.v6_timing_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.v6_timing_label.setStyleSheet(_TIMING_QSS)
        box.addWidget(self.v6_timing_label)

        if not self._v6_insert_into_main_panel(group):
            # 兜底：贴到求解容器顶部（保证一定可见）
            container = getattr(self, 'solver_container', None)
            lay = container.layout() if container is not None else None
            if lay is not None:
                lay.insertWidget(0, group)
            else:
                group.setParent(self)
                group.setGeometry(6, 6, 470, 96)
                group.show()
        self.v6_speed_panel = group

    def _v6_insert_into_main_panel(self, group):
        """插入到 AI 求解主面板：紧跟参数表单（算法/求解强度/求解模式）之后。"""
        panel = getattr(self, 'solver_panel', None)
        depth = getattr(self, 'solver_depth', None)
        form_group = depth.parentWidget() if depth is not None else None
        lay = panel.layout() if panel is not None else None
        if lay is None or form_group is None:
            return False
        idx = lay.indexOf(form_group)
        lay.insertWidget((idx + 1) if idx >= 0 else 1, group)
        return True

    def _v6_sync_speed_buttons(self):
        btn = getattr(self, 'v6_speed_buttons', {}).get(self._v6_speed)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    # ---------------------------------------------------------- 档位切换
    def _v6_on_speed_clicked(self, key):
        if key not in TIERS:
            return
        if getattr(self, '_solver_running', False):
            # 运行中：不立即生效，标记为“下一步边界生效”，避免打断在途动画/求解
            self._v6_pending_tier = key
            self._v6_update_timing_label()
        else:
            self._v6_apply_tier(key)

    def _v6_apply_tier(self, tier, persist=True):
        if tier not in TIERS:
            tier = 'standard'
        self._v6_speed = tier
        p = TIER_PARAMS[tier]
        self._v5gui.STEP_DELAY_MS = int(p['step_delay_ms'])   # 进程内生效，不改源码文件
        self._v6_anim_off = bool(p['anim_off'])
        self._v6_metrics_every = int(p['metrics_every'])
        if persist:
            prefs = load_prefs()
            prefs['speed_tier'] = tier
            prefs['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_prefs(prefs)
        self._v6_sync_speed_buttons()
        self._v6_update_timing_label()

    def _v6_apply_pending_tier(self):
        pending = self._v6_pending_tier
        if pending:
            self._v6_pending_tier = None
            self._v6_apply_tier(pending)

    # ---------------------------------------------------------- 分段计时
    def _v6_reset_timers(self):
        t = self._v6_t
        t.update({'search_ms': 0.0, 'anim_ms': 0.0, 'wait_ms': 0.0, 'render_ms': 0.0,
                  'steps': 0, 'start': perf_counter(), 'req_t0': None, 'anim_t0': None,
                  'wait_t0': None, 'metrics_steps': 0})

    def _v6_update_timing_label(self):
        t = self._v6_t
        total = (perf_counter() - t['start']) * 1000.0
        steps = t['steps']
        per = (total / steps) if steps else 0.0
        cur = dict(TIER_LABELS).get(self._v6_speed, self._v6_speed)
        pend = dict(TIER_LABELS).get(self._v6_pending_tier or '', '')
        head = '运行速度：%s' % cur
        if pend:
            head += '（下一步切换为 %s）' % pend
        text = ('%s｜动画%s，步间等待 %dms，每 %d 步刷新指标\n'
                '分段累计(ms)  搜索 %.0f | 动画 %.0f | 等待 %.0f | 渲染 %.0f\n'
                '步数 %d   总耗时 %.1f ms   平均 %.1f ms/步'
                % (head, '关' if self._v6_anim_off else '开', self._v5gui.STEP_DELAY_MS,
                   self._v6_metrics_every, t['search_ms'], t['anim_ms'], t['wait_ms'],
                   t['render_ms'], steps, total, per))
        lbl = getattr(self, 'v6_timing_label', None)
        if lbl is not None:
            lbl.setText(text)

    # ---------------------------------------------------------- 挂钩：搜索
    def _request_decision(self):
        t = getattr(self, '_v6_t', None)
        if t is None:
            return super()._request_decision()
        if t['wait_t0'] is not None:
            t['wait_ms'] += (perf_counter() - t['wait_t0']) * 1000.0
            t['wait_t0'] = None
        t['req_t0'] = perf_counter()
        super()._request_decision()
        if not getattr(self, '_solve_in_flight', False):
            t['req_t0'] = None

    def _on_solver_result(self, job_id, result):
        t = getattr(self, '_v6_t', None)
        if t is not None and t['req_t0'] is not None:
            t['search_ms'] += (perf_counter() - t['req_t0']) * 1000.0
            t['req_t0'] = None
        super()._on_solver_result(job_id, result)

    # ---------------------------------------------------------- 挂钩：渲染
    def refresh(self):
        t = getattr(self, '_v6_t', None)
        if t is None or self._v6_render_accum:
            return super().refresh()
        t0 = perf_counter()
        self._v6_render_accum = True
        try:
            return super().refresh()
        finally:
            t['render_ms'] += (perf_counter() - t0) * 1000.0
            self._v6_render_accum = False

    # ---------------------------------------------------------- 挂钩：落子
    def _ai_apply(self, direction):
        if not getattr(self, '_v6_anim_off', False):
            t0 = perf_counter()
            super()._ai_apply(direction)
            if getattr(self, '_v6_t', None) is not None:
                self._v6_t['anim_t0'] = t0
            return
        # 极限性能：关闭动画，立即落子并直接推进
        solver_mod = self._v5gui.solver
        if direction not in solver_mod.legal_moves(self.model.grid):
            self._finish_solver('无可行移动')
            return
        t0 = perf_counter()
        self._ai_applying = True
        try:
            if not self.model.apply_move(direction):
                self._finish_solver('无可行移动')
                return
            self._render_score(self.score_label, '分数', self.model.score)
            self._render_score(self.best_label, '最高分', self.model.best_score)
            self._sync_history_buttons()
        finally:
            self._ai_applying = False
        if getattr(self, '_v6_t', None) is not None:
            self._v6_t['anim_ms'] += (perf_counter() - t0) * 1000.0
        self._on_animation_finished()

    def _on_animation_finished(self):
        t = getattr(self, '_v6_t', None)
        if t is not None:
            if t['anim_t0'] is not None:
                t['anim_ms'] += (perf_counter() - t['anim_t0']) * 1000.0
                t['anim_t0'] = None
            t['wait_t0'] = perf_counter()
        super()._on_animation_finished()

    def _record_step(self):
        super()._record_step()
        t = getattr(self, '_v6_t', None)
        if t is None:
            return
        t['steps'] += 1
        t['metrics_steps'] += 1
        self._v6_apply_pending_tier()          # 步边界安全生效（不新建定时器/线程）
        if t['metrics_steps'] >= self._v6_metrics_every:
            t['metrics_steps'] = 0
            self._v6_update_timing_label()

    def _start_solver(self):
        # 新会话前先落实挂起的档位切换，再重置计时
        if getattr(self, '_v6_t', None) is not None:
            self._v6_apply_pending_tier()
            self._v6_reset_timers()
        return super()._start_solver()
