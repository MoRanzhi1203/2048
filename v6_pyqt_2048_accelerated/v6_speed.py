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

MODES = ('standard', 'fast', 'background')
MODE_LABELS = (('标准', 'standard'), ('快速', 'fast'), ('后台求解', 'background'))

# 运行方式仅决定「动画 / 步间等待 / UI 调度 / 执行位置」，与算法、求解强度、求解模式完全独立。
# particles_off：在**分配/计时调度之前**抑制合并粒子发射（fast/background）；
# flow：方向提示 B 层（内向流光）是否启用动态时钟（background 为静态，不跑流光计时器）。
MODE_PARAMS = {
    'standard':   {'anim_off': False, 'step_delay_ms': 70, 'metrics_every': 1,
                   'particles_off': False, 'flow': True},
    'fast':       {'anim_off': True,  'step_delay_ms': 0,  'metrics_every': 8,
                   'particles_off': True,  'flow': True},
    'background': {'anim_off': True,  'step_delay_ms': 0,  'metrics_every': 8,
                   'particles_off': True,  'flow': False},
}

PREFS_VERSION = 3                       # ui_prefs 模式版本（运行方式三档 + 固定 1000ms 回传）
_LEGACY_MODE_MAP = {                    # 旧 speed_tier -> 新 run_mode（一次性、幂等）
    'standard': 'standard',
    'extreme': 'fast',                  # 旧“极限性能”（无动画）＝新“快速”
    'fast': 'standard',                 # 旧“快速演示”（带动画）语义不同 -> 安全回退 标准
}


def migrate_prefs(prefs):
    """把历史 `speed_tier` 迁移为带版本的 `run_mode`（只迁移一次，幂等）。

    返回 (prefs, changed, reason)。
    """
    prefs = dict(prefs or {})
    changed = False
    reason = None
    version = int(prefs.get('modes_version') or 0)
    if version < PREFS_VERSION:
        old = prefs.get('speed_tier')
        if old is None:
            new, reason = 'standard', '缺少历史运行方式 -> standard'
        elif old in _LEGACY_MODE_MAP:
            new = _LEGACY_MODE_MAP[old]
            reason = '旧值 %r -> %r（V%d 映射表）' % (old, new, PREFS_VERSION)
        else:
            new, reason = 'standard', '未知历史值 %r -> standard' % (old,)
        prefs['run_mode'] = new
        prefs['run_mode_migrated_from'] = old
        prefs['run_mode_migration_reason'] = reason
        prefs['modes_version'] = PREFS_VERSION
        changed = True
    elif prefs.get('run_mode') not in MODES:
        prefs['run_mode'] = 'standard'
        prefs['run_mode_migration_reason'] = '非法运行方式 -> standard'
        changed = True
    # 结果回传：迁移为**固定内部周期**（单一来源；当前 500ms）。移除 N 步 / N 时间选择器
    # 遗留的旧偏好，防止过期 UI 偏好静默复活旧策略；与运行方式偏好互不影响。v3：500ms。
    if int(prefs.get('report_prefs_version') or 0) < 3:
        prefs.pop('report_mode', None)
        prefs.pop('report_value', None)
        try:
            from v6_background import REPORT_INTERVAL_MS as _ri
        except Exception:                                            # noqa: BLE001
            _ri = 500
        prefs['report_interval_ms'] = int(_ri)
        prefs['report_prefs_version'] = 3
        prefs['report_migration_reason'] = ('报告策略固定为 %dms（移除 N 步/N 时间配置）' % int(_ri))
        changed = True
    return prefs, changed, reason


TIERS = MODES                           # 兼容别名（旧名保留，值域已更新）
TIER_LABELS = MODE_LABELS

# 分段选择：浅米灰底 + 暖棕选中（低饱和，去掉深色块）
_SEG_QSS = (
    'QPushButton { background:#f3ece1; color:#6a5b4e; border:1px solid #e2d7c8;'
    ' border-radius:6px; padding:6px 0px; font-size:12px; }'
    'QPushButton:hover { background:#ece2d4; }'
    'QPushButton:checked { background:#8f7a66; color:#fff8ef; font-weight:bold;'
    ' border:1px solid #8f7a66; }')

# 紧凑性能摘要（浅米灰卡片）
_SUMMARY_QSS = (
    'background:#f7f1e7; color:#5e5245; border:1px solid #e6dccd;'
    ' border-radius:8px; padding:7px 10px; font-size:11px;')
# 统一主操作按钮（低饱和暖棕）
_PRIMARY_QSS = (
    'QPushButton { background:#8f7a66; color:#fff8ef; border:1px solid #8f7a66;'
    ' border-radius:6px; padding:6px 14px; font-size:12px; font-weight:bold; }'
    'QPushButton:hover { background:#9a8571; }'
    'QPushButton:pressed { background:#7f6b58; }'
    'QPushButton:disabled { background:#d8cdc0; color:#f6efe6; border-color:#d8cdc0; }')
# 统一停止按钮（米白描边，避免黑块）
_STOP_QSS = (
    'QPushButton { background:#f3ece1; color:#6a5b4e; border:1px solid #cbbcaa;'
    ' border-radius:6px; padding:6px 14px; font-size:12px; }'
    'QPushButton:hover { background:#e9dfd1; }'
    'QPushButton:pressed { background:#ded2c2; }'
    'QPushButton:disabled { color:#b3a695; border-color:#e6dccd; }')


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
        prefs, changed, reason = migrate_prefs(prefs)
        self._v6_migration = {'changed': bool(changed), 'reason': reason,
                              'run_mode': prefs.get('run_mode')}
        if changed:
            prefs['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_prefs(prefs)
        mode = prefs.get('run_mode')
        self._v6_speed = mode if mode in MODES else 'standard'
        self._v6_pending_tier = None
        self._v6_t = {'search_ms': 0.0, 'anim_ms': 0.0, 'wait_ms': 0.0, 'render_ms': 0.0,
                      'steps': 0, 'start': perf_counter(), 'req_t0': None, 'anim_t0': None,
                      'wait_t0': None, 'metrics_steps': 0}
        self._v6_render_accum = False
        self._v6_rename_solver_labels()      # 运行方式->求解强度；模式->求解模式（仅 V6 进程）
        self._v6_install_speed_panel()       # 主面板「运行方式」三档切换 + 分段计时读数
        self._v6_bg_controller = None
        try:
            from v6_background import BackgroundController
            ctl = BackgroundController(self, _v5gui)
            # 后台生命周期控制已并入统一「AI 运行控制」模块，不再插入独立按钮面板
            self._v6_bg_controller = ctl
            ctl.recover_on_start()          # 启动期安全恢复：重连活动任务 / 释放过期所有权
        except Exception:                                        # noqa: BLE001
            self._v6_bg_controller = None
        self._v6_apply_tier(self._v6_speed, persist=False)

    def closeEvent(self, event):
        ctl = getattr(self, '_v6_bg_controller', None)
        if ctl is not None and ctl.is_active():
            ok = ctl.shutdown(timeout=6.0)
            if not ok:
                # 有界等待超时：保留检查点并如实提示（不盲目终止存储事务）
                try:
                    self._v5gui  # noqa: B018  (保持引用，避免误删导入)
                    print('[v6] 后台求解未在期限内停止，已保留检查点', flush=True)
                except Exception:                                # noqa: BLE001
                    pass
        super().closeEvent(event)

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

    # ---------------------------------------------------------- UI：统一「AI 运行控制」
    def _v6_install_speed_panel(self):
        """统一的 AI 运行控制模块：三档 + 紧凑性能摘要 + 唯一一套求解操作按钮。

        合并原「运行方式」三档、纯黑分段计时大块、独立浅色「开始求解」大按钮与
        后台四按钮；不再额外插入后台专用按钮行。
        """
        group = QWidget()
        group.setObjectName('v6RunControl')
        apply_style = getattr(self, '_make_solver_group', None)
        if callable(apply_style):
            try:
                group = self._make_solver_group()
                group.setObjectName('v6RunControl')
            except Exception:                                    # noqa: BLE001
                group = QWidget()
        box = QVBoxLayout(group)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel('AI 运行控制')
        title.setStyleSheet('color:#5e4b35; font-size:12px; font-weight:bold;')
        head.addWidget(title, 0, Qt.AlignVCenter)
        head.addStretch(1)
        self.v6_run_badge = QLabel('未运行')
        self.v6_run_badge.setAlignment(Qt.AlignCenter)
        head.addWidget(self.v6_run_badge, 0, Qt.AlignVCenter)
        box.addLayout(head)
        self._v6_set_badge('idle', '未运行')

        # 运行方式：标准 / 快速 / 后台求解（唯一可见三档）
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.v6_speed_buttons = {}
        self.v6_speed_group = QButtonGroup(self)
        self.v6_speed_group.setExclusive(True)
        for text, key in TIER_LABELS:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet(_SEG_QSS)
            btn.setToolTip({'standard': '标准：保留走子动画与原有步间停顿（本机 GUI 实时渲染）',
                            'fast': '快速：关闭走子动画与人工等待，本机 GUI 立即落子',
                            'background': '后台求解：独立计算进程接管当前这局（无 Qt 渲染），GUI 仅低频显示进度'}[key])
            btn.clicked.connect(lambda _checked, k=key: self._v6_on_speed_clicked(k))
            seg.addWidget(btn, 1)
            self.v6_speed_group.addButton(btn)
            self.v6_speed_buttons[key] = btn
        box.addLayout(seg)

        # 紧凑性能摘要（浅米灰，≤2 行；详细分段在 tooltip）
        self.v6_run_summary = QLabel()
        self.v6_run_summary.setWordWrap(True)
        self.v6_run_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.v6_run_summary.setStyleSheet(_SUMMARY_QSS)
        box.addWidget(self.v6_run_summary)
        self.v6_timing_label = self.v6_run_summary      # 兼容旧属性名

        # 唯一一套求解操作：主按钮（开始/暂停/继续）+ 停止
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.v6_run_primary = QPushButton('开始求解')
        self.v6_run_primary.setStyleSheet(_PRIMARY_QSS)
        self.v6_run_primary.setCursor(Qt.PointingHandCursor)
        self.v6_run_primary.setFixedHeight(32)
        self.v6_run_primary.clicked.connect(self._v6_on_run_primary)
        self.v6_run_stop = QPushButton('停止')
        self.v6_run_stop.setStyleSheet(_STOP_QSS)
        self.v6_run_stop.setCursor(Qt.PointingHandCursor)
        self.v6_run_stop.setFixedHeight(32)
        self.v6_run_stop.clicked.connect(self._v6_on_run_stop)
        actions.addWidget(self.v6_run_primary, 1)
        actions.addWidget(self.v6_run_stop, 0)
        box.addLayout(actions)

        if not self._v6_insert_into_main_panel(group):
            # 兜底：贴到求解容器顶部（保证一定可见）
            container = getattr(self, 'solver_container', None)
            lay = container.layout() if container is not None else None
            if lay is not None:
                lay.insertWidget(0, group)
            else:
                group.setParent(self)
                group.setGeometry(6, 6, 470, 150)
                group.show()
        self.v6_speed_panel = group

        # 隐藏 V5 旧「开始求解」大按钮与忙态进度条（逻辑保留，入口已并入统一模块）
        for w in (getattr(self, 'solver_start_btn', None),
                  getattr(self, 'solver_progress', None)):
            if w is not None:
                try:
                    w.hide()
                except Exception:                                # noqa: BLE001
                    pass
        self._v6_sync_run_controls()

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
        if tier not in MODES:
            tier = 'standard'
        self._v6_speed = tier
        p = MODE_PARAMS[tier]
        self._v5gui.STEP_DELAY_MS = int(p['step_delay_ms'])   # 进程内生效，不改源码文件
        self._v6_anim_off = bool(p['anim_off'])
        self._v6_metrics_every = int(p['metrics_every'])
        self._v6_particles_off = bool(p.get('particles_off', False))
        self._v6_flow = bool(p.get('flow', True))
        if tier == 'background':
            # 切到后台：仅重置“上一求解会话”的计数/指标，不动真实游戏分数/最高分
            self._v6_bg_log_key = None
            self._v6_last_bg = None
            for k in ('steps', 'action', 'eval', 'score', 'max_tile', 'elapsed'):
                self._set_metric(k, '—')
            try:
                self._set_status('状态：<b>后台求解未启动</b>',
                                 '选择「开始求解」后由后台 Worker 接管当前这局。')
            except Exception:                                    # noqa: BLE001
                pass
        if persist:
            prefs = load_prefs()
            prefs['run_mode'] = tier
            prefs['modes_version'] = PREFS_VERSION
            prefs['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            save_prefs(prefs)
        self._v6_sync_speed_buttons()
        self._v6_update_timing_label()
        self._v6_apply_effects()
        ctl = getattr(self, '_v6_bg_controller', None)
        if ctl is not None:
            ctl.on_mode_changed(tier)
        self._v6_sync_run_controls()

    def _v6_apply_effects(self):
        """按运行方式应用**粒子 / 方向光**策略（仅 V6 运行时控制，不改 V4/V5 源码）。

        - standard：合并粒子开 + 方向光 A/B 动态；
        - fast：合并粒子**在分配前**抑制（零发射）+ 方向光 A/B 动态保留；
        - background：合并粒子抑制 + 方向光 B 关闭（静态 A，不跑流光计时器）。
        """
        bv = getattr(self, 'board_view', None)
        layer = getattr(bv, '_particle_layer', None)
        off = bool(getattr(self, '_v6_particles_off', False))
        if layer is not None:
            for name in ('emit_from', 'emit_zones_from'):
                cur = getattr(layer, name, None)
                if cur is None:
                    continue
                if off:
                    if getattr(cur, '_v6_noop', False):
                        continue
                    setattr(layer, '_v6_orig_' + name, cur)

                    def _noop(*_a, **_k):
                        return None
                    _noop._v6_noop = True
                    setattr(layer, name, _noop)
                else:
                    orig = getattr(layer, '_v6_orig_' + name, None)
                    if orig is not None:
                        setattr(layer, name, orig)
            if off:                                   # 清理已存在的粒子对象，避免残留
                eng = getattr(layer, 'engine', None)
                if eng is not None and hasattr(eng, 'clear'):
                    try:
                        eng.clear()
                    except Exception:                                # noqa: BLE001
                        pass
        ov = getattr(self, '_hint_overlay', None)
        if ov is not None:
            try:
                ov.set_flow_enabled(bool(getattr(self, '_v6_flow', True)))
            except Exception:                                        # noqa: BLE001
                pass
            if not getattr(self, '_v6_flow', True):
                # 后台：不做持续流光，也不展示可能过期的“下一步建议”（避免误导）
                try:
                    ov.set_direction(None)
                    self._hint_direction = None
                except Exception:                                    # noqa: BLE001
                    pass

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

    # ---------------------------------------------------------- 运行控制：唯一状态源
    def _v6_bg(self):
        """仅当运行方式为后台时返回后台控制器（否则 None）。"""
        if getattr(self, '_v6_speed', 'standard') != 'background':
            return None
        return getattr(self, '_v6_bg_controller', None)

    def _v6_on_run_primary(self):
        """统一主按钮：标准/快速复用 V5 开始-停止；后台按状态 start/pause/resume。"""
        ctl = self._v6_bg()
        if ctl is not None:
            st = getattr(ctl, 'state', 'GUI_IDLE')
            try:
                if st in ('GUI_IDLE', 'BG_COMPLETED', 'BG_ERROR'):
                    ctl.start()
                elif st in ('BG_RUNNING', 'HANDOFF_PREPARE'):
                    ctl.pause()
                elif st == 'BG_PAUSED':
                    ctl.resume()
            finally:
                self._v6_sync_run_controls()
            return
        self.on_solver_clicked()          # 复用既有算法求解入口（开始/停止）
        self._v6_sync_run_controls()

    def _v6_on_run_stop(self):
        """统一停止按钮（仅后台需要；标准/快速由主按钮切换为“停止”）。"""
        ctl = self._v6_bg()
        if ctl is not None:
            ctl.stop()
            self._v6_sync_run_controls()

    def _update_solver_buttons(self):
        """V5 更新旧按钮文案后，同步统一控制按钮（避免两套状态不一致）。"""
        super()._update_solver_buttons()
        self._v6_sync_run_controls()

    _BADGE_STYLES = {
        'idle': ('#efe7db', '#8f8175', '#e2d7c8'),
        'running': ('#8f7a66', '#fff8ef', '#8f7a66'),
        'paused': ('#e7d5ba', '#6b5334', '#dcc8a9'),
        'stopping': ('#efe7db', '#8f8175', '#e2d7c8'),
        'error': ('#e8ccc7', '#8a3a30', '#d9b3ad'),
    }

    def _v6_set_badge(self, kind, text):
        """运行状态徽标（低饱和胶囊）。"""
        lbl = getattr(self, 'v6_run_badge', None)
        if lbl is None:
            return
        bg, fg, bd = self._BADGE_STYLES.get(kind, self._BADGE_STYLES['idle'])
        lbl.setText(text)
        lbl.setStyleSheet(
            'background:%s; color:%s; border:1px solid %s; border-radius:9px;'
            ' padding:2px 9px; font-size:10px; font-weight:bold;' % (bg, fg, bd))

    def _v6_sync_run_controls(self):
        """按“运行方式 + 运行状态”刷新唯一一套控制按钮（信号只连接一次）。"""
        primary = getattr(self, 'v6_run_primary', None)
        if primary is None:
            return
        stop = getattr(self, 'v6_run_stop', None)
        ctl = self._v6_bg()
        if ctl is not None:
            st = getattr(ctl, 'state', 'GUI_IDLE')
            text, enabled = '开始求解', True
            badge = ('idle', '未运行')
            if st == 'HANDOFF_PREPARE':
                text, enabled, badge = '开始中…', False, ('stopping', '开始中')
            elif st == 'BG_RUNNING':
                text, badge = '暂停', ('running', '运行中')
            elif st == 'BG_PAUSING':
                text, enabled, badge = '暂停中…', False, ('stopping', '暂停中')
            elif st == 'BG_PAUSED':
                text, badge = '继续', ('paused', '已暂停')
            elif st == 'BG_STOPPING':
                text, enabled, badge = '正在停止', False, ('stopping', '正在停止')
            elif st == 'BG_ERROR':
                badge = ('error', '出错')
            else:
                lr = getattr(ctl, '_last_result', None) or {}
                lst = lr.get('status')
                if lst == 'stopped':
                    badge = ('idle', '已停止')
                elif lst in ('completed', 'game_over'):
                    badge = ('idle', '已结束')
            primary.setText(text)
            primary.setEnabled(enabled)
            self._v6_set_badge(*badge)
            if stop is not None:
                stop.setVisible(True)
                stop.setEnabled(st in ('BG_RUNNING', 'BG_PAUSED'))
        else:
            running = bool(getattr(self, '_solver_running', False))
            primary.setText('停止' if running else '开始求解')
            primary.setEnabled(True)
            self._v6_set_badge('running' if running else 'idle',
                               '运行中' if running else '未运行')
            if stop is not None:
                stop.setVisible(False)
        self._v6_update_timing_label()

    # ---------------------------------------------------------- 紧凑性能摘要（P3）
    def _v6_update_timing_label(self):
        """≤2 行紧凑摘要：状态 / 有效步数 / 耗时 / 步每秒 / 实际后端。

        详细分段计时保留在 tooltip；**未运行时不把历史计时当作当前耗时**。
        """
        lbl = getattr(self, 'v6_run_summary', None)
        if lbl is None:
            return
        t = getattr(self, '_v6_t', None) or {}
        mode_name = dict((k, text) for text, k in TIER_LABELS).get(
            getattr(self, '_v6_speed', 'standard'), '')
        ctl = self._v6_bg()
        if ctl is not None:
            st = getattr(ctl, 'state', 'GUI_IDLE')
            p = getattr(ctl, '_last_progress', None) or {}
            if st == 'BG_RUNNING':
                line1 = '步 %s　%s 步/秒' % (p.get('steps', '—'), p.get('steps_per_s', '—'))
                line2 = '分数 %s　最大 %s　后端 %s' % (
                    p.get('score', '—'), p.get('max_tile', '—'), p.get('backend_used') or '—')
            elif st == 'BG_PAUSED':
                line1 = '步 %s　分数 %s' % (p.get('steps', '—'), p.get('score', '—'))
                line2 = '最大 %s　继续后从精确 RNG 恢复' % p.get('max_tile', '—')
            elif st in ('BG_PAUSING', 'BG_STOPPING'):
                line1, line2 = '等待 Worker 提交最终状态…', '界面保持可操作，请稍候'
            else:
                # 未运行：若已有上一段后台结果，则显示“上次”并与下方 solver_status 一致
                lr = getattr(ctl, '_last_result', None) or {}
                snap = lr.get('snapshot') or {}
                if lr and snap:
                    grid = snap.get('board') or []
                    mt2 = max((max(r) for r in grid), default=None) if grid else None
                    lsteps = lr.get('total_committed_moves')
                    line1 = '上次 %s 步　分数 %s' % (
                        lsteps if lsteps is not None else '—',
                        snap.get('score') if snap.get('score') is not None else '—')
                    line2 = '%s　最大 %s' % (
                        '已结束' if lr.get('status') in ('completed', 'game_over') else '已停止',
                        mt2 if mt2 is not None else '—')
                else:
                    line1, line2 = '步骤 —　— 步/秒', '分数 —　最大 —　后端 —'
            lbl.setText(line1 + '\n' + line2)
            lbl.setToolTip('后台指标来自 Worker 最新回传（固定 500ms 一帧）。')
            return
        running = bool(getattr(self, '_solver_running', False))
        steps = int(t.get('steps', 0))
        total = ((perf_counter() - t.get('start', perf_counter())) * 1000.0
                 if running else 0.0)
        if not running and steps == 0:
            lbl.setText('步骤 —　— 步/秒\n耗时 —　%s求解' % mode_name)
            lbl.setToolTip('未运行。')
            return
        if not running:
            lbl.setText('上次 %d 步　当前未计时\n%s求解' % (steps, mode_name))
        else:
            sps = (steps / (total / 1000.0)) if total > 0 else 0.0
            lbl.setText('步 %d　%.1f 步/秒\n耗时 %.0f ms　%s求解'
                        % (steps, sps, total, mode_name))
        lbl.setToolTip('分段累计(ms)  搜索 %.0f | 动画 %.0f | 等待 %.0f | 渲染 %.0f\n'
                       '步数 %d  总耗时 %.1f ms  平均 %.1f ms/步'
                       % (t.get('search_ms', 0), t.get('anim_ms', 0), t.get('wait_ms', 0),
                          t.get('render_ms', 0), steps, total,
                          (total / steps) if steps else 0.0))

    # ---------------------------------------------------------- 后台：统一状态源（P3）
    def _v6_bg_log(self, text, key=None):
        """后台日志：按 (阶段, revision/status) 去重，避免每帧刷屏。"""
        if key is not None:
            if key == getattr(self, '_v6_bg_log_key', None):
                return
            self._v6_bg_log_key = key
        try:
            self._log_step(text)
        except Exception:                                            # noqa: BLE001
            pass

    def _v6_apply_bg_progress(self, p):
        """PROGRESS → 顶部摘要 + 下方 solver_status/metrics/log 使用**同一数据源**。"""
        p = dict(p or {})
        self._v6_last_bg = p
        self._v6_sync_run_controls()                     # 顶部紧凑摘要（含状态/步数/后端）
        steps = p.get('steps'); score = p.get('score'); mt = p.get('max_tile')
        sps = p.get('steps_per_s'); backend = p.get('backend_used')
        engine = p.get('engine_used'); rev = p.get('revision')
        lag = p.get('render_age_ms')
        try:
            self._set_status(
                '状态：<b>后台求解中</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                    steps if steps is not None else '—',
                    score if score is not None else '—'),
                '最大瓦片 <b>%s</b>　%s 步/秒　引擎 <b>%s</b> / %s　rev %s　同步延迟 %sms' % (
                    mt if mt is not None else '—',
                    ('%.1f' % sps) if isinstance(sps, (int, float)) else '—',
                    backend or '—', engine or '—',
                    rev if rev is not None else '—',
                    ('%.0f' % lag) if isinstance(lag, (int, float)) else '—'))
        except Exception:                                            # noqa: BLE001
            pass
        # 下方既有 metrics：未知值显示 —，不造假零值
        self._set_metric('steps', steps if steps is not None else '—')
        self._set_metric('action', '后台连走')
        self._set_metric('eval', '—')
        self._set_metric('score', score if score is not None else '—')
        self._set_metric('max_tile', mt if mt is not None else '—')
        el = p.get('elapsed_s')
        self._set_metric('elapsed', ('%.1fs' % el) if isinstance(el, (int, float)) else '—')
        self._v6_bg_log(
            '[后台] rev %s · 步 %s · 分数 %s · 最大 %s · %s 步/秒'
            % (rev, steps, score, mt,
               ('%.1f' % sps) if isinstance(sps, (int, float)) else '—'),
            key=('progress', rev))

    def _v6_apply_bg_final(self, msg):
        """PAUSED / STOPPED / COMPLETED / GAME_OVER / ERROR → 顶部与下方状态一次收敛。"""
        msg = dict(msg or {})
        ctl = getattr(self, '_v6_bg_controller', None)
        st = getattr(ctl, 'state', 'GUI_IDLE')
        snap = msg.get('snapshot') or {}
        score = snap.get('score')
        steps = msg.get('total_committed_moves')
        grid = snap.get('board') or []
        mt = max((max(r) for r in grid), default=None) if grid else None
        status = msg.get('status')
        if st == 'BG_PAUSED':
            head = '状态：<b>已暂停</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                steps if steps is not None else '—', score if score is not None else '—')
            tail = '可点「继续」从精确 RNG 状态恢复；最大瓦片 <b>%s</b>' % (
                mt if mt is not None else '—')
            action = '已暂停'
        elif status in ('game_over', 'completed'):
            head = '状态：<b>后台求解结束</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                steps if steps is not None else '—', score if score is not None else '—')
            tail = '最终棋盘已同步；最大瓦片 <b>%s</b>' % (mt if mt is not None else '—')
            action = '已结束'
        elif status == 'error':
            head, tail, action = '状态：<b>后台求解出错</b>', (msg.get('reason') or ''), '出错'
        else:
            head = '状态：<b>后台求解已停止</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                steps if steps is not None else '—', score if score is not None else '—')
            tail = '最终棋盘已同步；最大瓦片 <b>%s</b>' % (mt if mt is not None else '—')
            action = '已停止'
        try:
            self._set_status(head, tail)
        except Exception:                                            # noqa: BLE001
            pass
        self._set_metric('steps', steps if steps is not None else '—')
        self._set_metric('action', action)
        self._set_metric('eval', '—')
        self._set_metric('score', score if score is not None else '—')
        self._set_metric('max_tile', mt if mt is not None else '—')
        self._set_metric('elapsed', '—')
        self._v6_sync_run_controls()
        self._v6_bg_log('[后台] %s · 步 %s · 分数 %s' % (action, steps, score),
                        key=('final', status, steps))

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
