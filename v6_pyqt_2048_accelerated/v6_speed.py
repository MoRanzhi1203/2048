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

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
PREFS_PATH = os.path.join(_HERE, 'config', 'ui_prefs.json')

MODES = ('standard', 'fast', 'background')
MODE_LABELS = (('标准', 'standard'), ('快速', 'fast'), ('后台求解', 'background'))
_MODE_LABEL_CN = {'standard': '标准模式', 'fast': '快速模式', 'background': '后台求解模式'}

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

PREFS_VERSION = 3                       # ui_prefs 模式版本（运行方式三档 + 固定 500ms 回传）
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
    'QPushButton:disabled { background:#e3d8ca; color:#8a7b6c; border-color:#d8cdc0; }')
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
        # 统一执行状态源（P2）：
        #   _v6_speed         = 当前生效/已选择的运行方式（空闲时二者相同）
        #   _v6_selected_mode = 运行中用户点选、但尚未生效的选项卡（非破坏性）
        #   _v6_active_mode   = 真正在执行的模式（空闲为 None）
        self._v6_selected_mode = None
        self._v6_active_mode = None
        self._v6_local_paused = False       # 标准/快速：已在安全步边界暂停
        self._v6_local_pausing = False      # 已请求暂停、等待在途计算返回
        self._v6_paused_result = None       # 暂停时保留的本步结果（恢复时优先使用）
        # 跨运行方式交接（暂停后才允许）：{'from','to','phase'}；非空期间禁用全部操作入口
        self._v6_handoff = None
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
        if getattr(self, '_v6_handoff', None) is not None:
            self._log_step('正在切换运行方式，已忽略本次选项卡点击。')
            self._v6_sync_speed_buttons()
            return
        if self._v6_session_active():
            # 选项卡切换**非破坏性**：只记录“已选择”，绝不暂停/停止/重启活动任务。
            # 真正切换必须等用户显式暂停后，点主按钮完成跨模式安全交接。
            self._v6_selected_mode = key
            self._v6_update_timing_label()
            self._v6_sync_run_controls()
            return
        self._v6_selected_mode = None
        self._v6_apply_tier(key)

    def _v6_apply_tier(self, tier, persist=True):
        if tier not in MODES:
            tier = 'standard'
        self._v6_speed = tier
        self._v6_selected_mode = None
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
        """仅在没有活动会话时落实挂起档位；活动期间绝不隐式切换执行模式。"""
        pending = self._v6_pending_tier
        if pending and not self._v6_session_active():
            self._v6_pending_tier = None
            self._v6_apply_tier(pending)

    # ---------------------------------------------------------- 分段计时
    def _v6_reset_timers(self):
        t = self._v6_t
        t.update({'search_ms': 0.0, 'anim_ms': 0.0, 'wait_ms': 0.0, 'render_ms': 0.0,
                  'steps': 0, 'start': perf_counter(), 'req_t0': None, 'anim_t0': None,
                  'wait_t0': None, 'metrics_steps': 0})

    # ---------------------------------------------------------- 运行控制：唯一状态源
    def _v6_effective_active(self):
        """真正在执行的运行方式（空闲为 None）。

        优先级：显式 `_v6_active_mode` → 本机求解器运行态 → 后台控制器活动状态。
        外部测试/恢复代码只设置其中一种来源时，仍能得到一致结论。
        """
        active = getattr(self, '_v6_active_mode', None)
        if active in MODES:
            return active
        if getattr(self, '_solver_running', False):
            sp = getattr(self, '_v6_speed', 'standard')
            return sp if sp in ('standard', 'fast') else 'standard'
        ctl = getattr(self, '_v6_bg_controller', None)
        if ctl is not None and getattr(ctl, 'state', 'GUI_IDLE') in (
                'HANDOFF_PREPARE', 'BG_RUNNING', 'BG_PAUSING', 'BG_PAUSED', 'BG_STOPPING'):
            return 'background'
        return None

    def _v6_is_paused(self, active=None):
        """该执行模式是否已真正停在安全边界（暂停中不算）。"""
        active = active or self._v6_effective_active()
        if active == 'background':
            ctl = getattr(self, '_v6_bg_controller', None)
            return bool(ctl is not None and getattr(ctl, 'state', '') == 'BG_PAUSED')
        return bool(getattr(self, '_solver_running', False)
                    and getattr(self, '_v6_local_paused', False)
                    and not getattr(self, '_v6_local_pausing', False))

    def _v6_bg(self):
        """活动执行模式为后台（或空闲且选择后台）时返回后台控制器。"""
        active = self._v6_effective_active()
        ctl = getattr(self, '_v6_bg_controller', None)
        if active is not None:
            return ctl if active == 'background' else None
        if getattr(self, '_v6_speed', 'standard') != 'background':
            return None
        return ctl

    def _v6_session_active(self):
        """是否存在**真实执行中**的求解会话（本机线程或后台 Worker；含已暂停）。"""
        if self._v6_effective_active() is not None:
            return True
        ctl = getattr(self, '_v6_bg_controller', None)
        try:
            return bool(ctl is not None and ctl.is_active())
        except Exception:                                            # noqa: BLE001
            return False

    def _v6_active_label(self):
        """当前**执行**模式的限定文案（不是选项卡）。"""
        mode = self._v6_effective_active() or getattr(self, '_v6_speed', 'standard')
        return _MODE_LABEL_CN.get(mode, '标准模式')

    # ------------------------------------------------ 标准/快速：安全步边界暂停
    def _v6_start_local(self):
        """统一入口启动本机求解（标准/快速）。"""
        self._v6_active_mode = self._v6_speed
        self._v6_local_paused = False
        self._v6_local_pausing = False
        self._v6_paused_result = None
        self._start_solver()                       # V6 覆盖：落实挂起档位 + 重置计时
        if not getattr(self, '_solver_running', False):
            self._v6_active_mode = None
        self._v6_sync_run_controls()

    def _v6_request_local_pause(self):
        """请求在**安全步边界**暂停：不打断在途计算，不落子、不生成随机方块。"""
        if not getattr(self, '_solver_running', False) or getattr(self, '_v6_local_paused', False):
            return
        self._v6_local_pausing = True
        if not getattr(self, '_solve_in_flight', False):
            # 当前没有在途计算：立即进入暂停态（下一步不会再被请求）
            self._v6_local_pausing = False
            self._v6_local_paused = True
        self._v6_sync_run_controls()

    def _v6_resume_local(self):
        if not getattr(self, '_solver_running', False):
            return
        self._v6_local_paused = False
        held = getattr(self, '_v6_paused_result', None)
        self._v6_paused_result = None
        if held:
            job_id, result, sig = held
            if (job_id == getattr(self, '_job_id', None)
                    and (sig is None or sig == self._board_signature(self.model.grid))):
                # 暂停期间棋盘未变：直接使用暂停时保留的本步结果，避免重复计算/重复落子
                super()._on_solver_result(job_id, result)
                self._v6_sync_run_controls()
                return
        self._request_decision()
        self._v6_sync_run_controls()

    def _v6_stop_local(self, reason='用户停止', silent=False):
        prev_active = getattr(self, '_v6_active_mode', None)
        self._v6_local_paused = False
        self._v6_local_pausing = False
        self._v6_paused_result = None
        super()._stop_solver(reason, silent=silent)
        # 仅清除“本机执行模式”；交接成功时控制器已把活动模式置为 background，必须保留
        if (prev_active in ('standard', 'fast')
                and getattr(self, '_v6_active_mode', None) == prev_active):
            self._v6_active_mode = None

    # ------------------------------------------------ 跨运行方式：暂停后安全交接
    def _v6_on_run_primary(self):
        """唯一主按钮：开始 / 暂停 / 继续 / 切换至XX并继续（三模式共用）。"""
        if getattr(self, '_v6_handoff', None) is not None:
            self._log_step('正在切换运行方式，已忽略重复点击。')
            return
        active = self._v6_effective_active()
        if active is None:
            ctl = self._v6_bg()
            if ctl is not None:
                ctl.start()
            else:
                self._v6_start_local()
            self._v6_sync_run_controls()
            return
        if not self._v6_is_paused(active):
            if active == 'background':
                self._v6_bg_controller.pause()
            else:
                self._v6_request_local_pause()
            self._v6_sync_run_controls()
            return
        target = getattr(self, '_v6_selected_mode', None)
        if target and target != active:
            self._v6_begin_handoff(active, target)
            return
        self._v6_selected_mode = None
        if active == 'background':
            self._v6_bg_controller.resume()
        else:
            self._v6_resume_local()
        self._v6_sync_run_controls()

    def _v6_begin_handoff(self, src, dst):
        """已暂停 → 执行跨模式安全交接（禁止并发点击/切换/重复创建 Worker）。"""
        label = _MODE_LABEL_CN.get(dst, dst)
        if not self._v6_is_paused(src):
            self._v6_handoff_fail('原会话尚未达到安全暂停状态，未执行切换', src, dst)
            return
        self._v6_handoff = {'from': src, 'to': dst, 'phase': 'switching'}
        self._v6_selected_mode = None
        self._v6_sync_run_controls()
        self._log_step('运行方式切换开始：%s → %s（原会话保持暂停，等待安全交接）'
                       % (_MODE_LABEL_CN.get(src, src), label))
        if src in ('standard', 'fast') and dst in ('standard', 'fast'):
            self._v6_handoff_local_to_local(src, dst)
        elif src in ('standard', 'fast') and dst == 'background':
            self._v6_handoff_local_to_background(src, dst)
        elif src == 'background' and dst in ('standard', 'fast'):
            self._v6_handoff_background_to_local(src, dst)
        else:
            self._v6_handoff_fail('不支持的运行方式切换：%s → %s' % (src, dst), src, dst)

    def _v6_handoff_local_to_local(self, src, dst):
        """标准 ↔ 快速：同一棋盘/会话继续，只更换动画与调度策略。"""
        # 原模式在途/暂存结果失效：新执行会话不得复用旧消息序号
        self._v6_paused_result = None
        self._v6_local_pausing = False
        self._solve_in_flight = False
        self._pending_result = None
        self._job_id += 1
        try:
            self.solver_progress.setRange(0, 100)
            self.solver_progress.setValue(0)
        except Exception:                                            # noqa: BLE001
            pass
        self._clear_hint()                       # 旧方向提示属于旧执行模式，必须清除
        self._v6_apply_tier(dst)                 # 动画/粒子/步间等待/偏好一次性生效
        self._v6_active_mode = dst
        self._v6_local_paused = False
        self._v6_handoff = None
        self._v6_sync_run_controls()
        self._log_step('已切换至%s：同一棋盘继续求解（job=%s，未重新开局/未重复落子）'
                       % (_MODE_LABEL_CN.get(dst, dst), getattr(self, '_job_id', '—')))
        self._request_decision()

    def _v6_handoff_local_to_background(self, src, dst):
        """标准/快速 → 后台：先从最新一致状态建快照，Worker 成功接管后才收尾本机会话。"""
        ctl = getattr(self, '_v6_bg_controller', None)
        if ctl is None:
            self._v6_handoff_fail('后台求解控制器不可用', src, dst)
            return
        meta = {'from': src, 'to': dst, 'reason': 'paused_cross_mode_handoff',
                'model_game_id': getattr(self.model, 'game_id', None),
                'board_sig': self._board_signature(self.model.grid),
                'score': int(self.model.score),
                'best_score': int(getattr(self.model, 'best_score', 0))}
        try:
            snap = ctl._build_snapshot(handoff_meta=meta)
        except Exception as exc:                                     # noqa: BLE001
            self._v6_handoff_fail('生成交接快照失败：%s' % exc, src, dst)
            return
        if not ctl.start(snapshot=snap, handoff_meta=meta):
            # 控制器已在 _fail_start 中回调；若尚未清理（例如拒绝受理），此处兜底
            if getattr(self, '_v6_handoff', None) is not None:
                self._v6_handoff_fail('后台求解无法启动（请确认求解模式为自动连走）', src, dst)
            return

    def _v6_on_bg_started(self, meta):
        """后台 Worker 已确认接管所有权：此时才结束本机会话（单一写者）。"""
        meta = dict(meta or {})
        if meta.get('from') in ('standard', 'fast'):
            self._v6_stop_local('交由后台求解接管', silent=True)
            self._v6_apply_tier('background')
            self._log_step('已切换至后台求解模式：Worker 已接管当前棋盘（正式 game=%s）'
                           % (meta.get('model_game_id') or '—'))
        self._v6_handoff = None
        self._v6_sync_run_controls()

    def _v6_on_bg_start_failed(self, reason, meta):
        """后台启动/交接失败：保留原暂停会话，明确提示，不静默切换模式。"""
        meta = dict(meta or {})
        dst = meta.get('to') or 'background'
        label = _MODE_LABEL_CN.get(dst, dst)
        self._v6_handoff = None
        self._v6_selected_mode = None
        self._v6_sync_speed_buttons()            # 选项卡回到真正执行的模式
        self._v6_sync_run_controls()
        self._log_step('%s切换失败：%s（原会话保持暂停）' % (label, reason))
        try:
            self._set_status('状态：<b>%s切换失败</b>' % label,
                             '原会话保持暂停，可继续或重新尝试切换：%s' % reason, error=True)
        except Exception:                                            # noqa: BLE001
            pass

    def _v6_handoff_background_to_local(self, src, dst):
        """后台 → 标准/快速：先确认终态已提交，再让 Worker 退出并释放所有权，最后由本机继续。"""
        ctl = getattr(self, '_v6_bg_controller', None)
        if ctl is None:
            self._v6_handoff_fail('后台求解控制器不可用', src, dst)
            return
        if getattr(ctl, 'state', '') != 'BG_PAUSED':
            self._v6_handoff_fail('后台会话尚未完成暂停提交，禁止提前切换', src, dst)
            return
        self._ensure_bg_final_adopted(ctl)
        self._v6_handoff['phase'] = 'draining'
        self._v6_sync_run_controls()

        def done(ok, reason):
            if getattr(self, '_v6_handoff', None) is None:
                return                              # 已被停止/关闭等路径收尾
            if not ok:
                self._v6_handoff_fail(reason, src, dst)
                return
            # 旧会话彻底失效：迟到 progress/final 一律丢弃
            try:
                ctl._game_id = None
                ctl._final_seen = True
                ctl._last_progress = None
            except Exception:                                        # noqa: BLE001
                pass
            self._v6_active_mode = None
            self._v6_handoff = None
            self._v6_apply_tier(dst)
            self._v6_sync_run_controls()
            self._log_step('已切换至%s：后台 Worker 已退出并释放所有权，由本机求解器继续（正式 game=%s）'
                           % (_MODE_LABEL_CN.get(dst, dst),
                              getattr(self.model, 'game_id', None) or '—'))
            self._v6_start_local()

        ctl.drain_for_handoff(done, deadline_s=8.0)

    def _ensure_bg_final_adopted(self, ctl):
        """后台暂停终态必须已进入官方模型（棋盘/分数/RNG/历史）；偏离则补一次正式采纳。"""
        res = getattr(ctl, '_last_result', None) or {}
        snap = res.get('snapshot') or {}
        if not snap:
            return
        model = self.model
        try:
            same = ([row[:] for row in model.grid] == [list(r) for r in snap['board']]
                    and int(model.score) == int(snap['score']))
        except Exception:                                            # noqa: BLE001
            same = False
        if same:
            return
        self._log_step('后台终态与官方模型不一致，补一次正式回放采纳（防止交接错位）')
        ctl._adopt(snap, res.get('directions'))

    def _v6_handoff_fail(self, reason, src, dst):
        """交接失败：保留原模式与原暂停状态，仅明确提示失败原因。"""
        label = _MODE_LABEL_CN.get(dst, dst)
        self._v6_handoff = None
        self._v6_selected_mode = None
        self._v6_active_mode = src
        self._v6_sync_speed_buttons()
        self._v6_sync_run_controls()
        self._log_step('%s切换失败：%s（原会话保持暂停）' % (label, reason))
        try:
            self._set_status('状态：<b>%s切换失败</b>' % label,
                             '原会话保持暂停，可继续或重新尝试切换：%s' % reason, error=True)
        except Exception:                                            # noqa: BLE001
            pass

    def _v6_on_run_stop(self):
        """唯一停止按钮（三模式共用）。"""
        if getattr(self, '_v6_handoff', None) is not None:
            self._log_step('正在切换运行方式，停止按钮已禁用。')
            return
        active = self._v6_effective_active()
        if active == 'background':
            self._v6_bg_controller.stop()
        elif active in ('standard', 'fast') or getattr(self, '_solver_running', False):
            self._v6_stop_local('用户停止')
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
        """唯一控制矩阵：三模式共用 开始/暂停/继续/切换并继续 + 停止。

        状态徽标始终标识**真正执行**的模式；选项卡只表达“已选择”。
        """
        primary = getattr(self, 'v6_run_primary', None)
        if primary is None:
            return
        stop = getattr(self, 'v6_run_stop', None)
        handoff = getattr(self, '_v6_handoff', None)
        for btn in (getattr(self, 'v6_speed_buttons', None) or {}).values():
            try:
                btn.setEnabled(handoff is None)
            except Exception:                                        # noqa: BLE001
                pass
        if handoff is not None:
            label = _MODE_LABEL_CN.get(handoff.get('to'), '')
            primary.setText('正在切换至%s…' % label)
            primary.setEnabled(False)
            self._v6_set_badge('stopping', '正在切换至%s' % label)
            if stop is not None:
                stop.setVisible(True)
                stop.setEnabled(False)
            self._v6_update_timing_label()
            return

        active = self._v6_effective_active()
        if active is not None:
            label = _MODE_LABEL_CN.get(active, '标准模式')
            ctl = getattr(self, '_v6_bg_controller', None)
            st = getattr(ctl, 'state', '') if active == 'background' else ''
            paused = self._v6_is_paused(active)
            target = getattr(self, '_v6_selected_mode', None)
            if target == active:
                target = None
            enabled = True
            show_stop = True
            if active == 'background' and st == 'HANDOFF_PREPARE':
                text, enabled, badge = '开始中…', False, ('stopping', '后台求解模式启动中')
            elif active == 'background' and st == 'BG_STOPPING':
                text, enabled, badge = '正在停止', False, ('stopping', '后台求解模式正在停止')
            elif (active != 'background' and getattr(self, '_v6_local_pausing', False)) \
                    or (active == 'background' and st == 'BG_PAUSING'):
                text, enabled, badge = '正在暂停…', False, ('stopping', '%s正在暂停' % label)
            elif paused and target:
                text = '切换至%s并继续' % _MODE_LABEL_CN.get(target, target)
                badge = ('paused', '%s已暂停' % label)
            elif paused:
                text, badge = '继续', ('paused', '%s已暂停' % label)
            else:
                text, badge = '暂停', ('running', '%s运行中' % label)
            primary.setText(text)
            primary.setEnabled(enabled)
            self._v6_set_badge(*badge)
            if stop is not None:
                stop.setVisible(show_stop)
                stop.setEnabled(enabled)
            self._v6_update_timing_label()
            return

        # ---- 空闲：清空活动执行模式；已选择档位直接用于下一次“开始求解” ----
        self._v6_active_mode = None
        ctl = getattr(self, '_v6_bg_controller', None)
        badge = ('idle', '%s未运行' % _MODE_LABEL_CN.get(
            getattr(self, '_v6_speed', 'standard'), '标准模式'))
        if ctl is not None and getattr(ctl, 'state', '') == 'BG_ERROR':
            badge = ('error', '后台求解模式出错')
        else:
            lr = getattr(ctl, '_last_result', None) or {}
            lst = lr.get('status')
            if getattr(self, '_v6_speed', '') == 'background':
                if lst == 'stopped':
                    badge = ('idle', '后台求解模式已停止')
                elif lst in ('completed', 'game_over'):
                    badge = ('idle', '后台求解模式已结束')
        primary.setText('开始求解')
        primary.setEnabled(True)
        self._v6_set_badge(*badge)
        if stop is not None:
            stop.setVisible(False)
            stop.setEnabled(False)
        self._v6_apply_selected_if_idle()
        self._v6_update_timing_label()

    def _v6_apply_selected_if_idle(self):
        """运行中选中的选项卡在会话结束后做一次安全交接（仅空闲时生效）。"""
        sel = getattr(self, '_v6_selected_mode', None)
        if not sel or sel == getattr(self, '_v6_speed', None):
            self._v6_selected_mode = None
            return
        self._v6_selected_mode = None
        QTimer.singleShot(0, lambda k=sel: self._v6_apply_tier(k))

    # ---------------------------------------------------------- 紧凑性能摘要（P3）
    def _v6_update_timing_label(self):
        """≤2 行紧凑摘要：状态 / 有效步数 / 耗时 / 步每秒 / 实际后端。

        详细分段计时保留在 tooltip；**未运行时不把历史计时当作当前耗时**。
        交接中显示目标模式；已暂停且变更选择时提示“切换并继续”入口。
        """
        lbl = getattr(self, 'v6_run_summary', None)
        if lbl is None:
            return
        t = getattr(self, '_v6_t', None) or {}
        active = self._v6_effective_active()
        handoff = getattr(self, '_v6_handoff', None)
        if handoff is not None:
            label = _MODE_LABEL_CN.get(handoff.get('to'), '')
            lbl.setText('正在切换至%s…\n原会话保持暂停，等待安全交接完成' % label)
            lbl.setToolTip('交接期间禁止重复点击/再次切换；旧 Worker 必须释放所有权。')
            return
        sel = getattr(self, '_v6_selected_mode', None)
        if sel == active:
            sel = None
        sel_label = _MODE_LABEL_CN.get(sel or '', '')
        in_bg_view = active == 'background' or (
            active is None and getattr(self, '_v6_speed', 'standard') == 'background')
        ctl = getattr(self, '_v6_bg_controller', None)
        if in_bg_view and ctl is not None:
            st = getattr(ctl, 'state', 'GUI_IDLE')
            p = getattr(ctl, '_last_progress', None) or {}
            if st == 'BG_RUNNING':
                line1 = '后台求解模式运行中　步 %s　%s 步/秒' % (
                    p.get('steps', '—'), p.get('steps_per_s', '—'))
                line2 = '分数 %s　最大 %s　后端 %s' % (
                    p.get('score', '—'), p.get('max_tile', '—'), p.get('backend_used') or '—')
            elif st == 'BG_PAUSED':
                line1 = '后台求解模式已暂停　步 %s' % p.get('steps', '—')
                line2 = '分数 %s　最大 %s　继续后从精确 RNG 恢复' % (
                    p.get('score', '—'), p.get('max_tile', '—'))
            elif st in ('BG_PAUSING', 'BG_STOPPING'):
                line1 = '后台求解模式%s…' % ('正在暂停' if st == 'BG_PAUSING' else '正在停止')
                line2 = '等待 Worker 提交最终状态，界面保持可操作'
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
                    line1, line2 = '后台求解模式未运行', '步骤 —　后端 —'
            if sel_label:
                line2 = '当前执行：后台求解模式｜已选择：%s（未切换）' % sel_label
            lbl.setText(line1 + '\n' + line2)
            lbl.setToolTip('后台指标来自 Worker 最新回传（固定 500ms 一帧）。')
            return
        running = active in ('standard', 'fast')
        paused = running and self._v6_is_paused(active)
        pausing = running and bool(getattr(self, '_v6_local_pausing', False))
        mode = _MODE_LABEL_CN.get(active or getattr(self, '_v6_speed', 'standard'), '标准模式')
        if mode == '后台求解模式':
            mode = '标准模式'
        steps = int(t.get('steps', 0))
        total = ((perf_counter() - t.get('start', perf_counter())) * 1000.0
                 if running else 0.0)
        if running and paused:
            line1 = '%s已暂停　步 %d' % (mode, steps)
            line2 = ('点「继续」从暂停点恢复（棋盘与 RNG 未变）' if not sel_label else
                     '点「切换至%s并继续」完成跨模式安全交接' % sel_label)
        elif running and pausing:
            line1 = '%s正在暂停…' % mode
            line2 = '等待当前计算在安全步边界返回'
        elif running:
            sps = (steps / (total / 1000.0)) if total > 0 else 0.0
            line1 = '%s运行中　步 %d　%.1f 步/秒' % (mode, steps, sps)
            line2 = '耗时 %.0f ms' % total
        elif steps > 0:
            line1 = '上次 %d 步　当前未计时' % steps
            line2 = '%s未运行' % mode
        else:
            line1, line2 = '%s未运行' % mode, '步骤 —　耗时 —'
        if sel_label:
            line2 = '当前执行：%s｜已选择：%s（暂停后可切换）' % (mode, sel_label)
        lbl.setText(line1 + '\n' + line2)
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
                '状态：<b>后台求解模式运行中</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
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
            head = '状态：<b>后台求解模式已暂停</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                steps if steps is not None else '—', score if score is not None else '—')
            tail = '可点「继续」从精确 RNG 状态恢复；最大瓦片 <b>%s</b>' % (
                mt if mt is not None else '—')
            action = '已暂停'
        elif status in ('game_over', 'completed'):
            head = '状态：<b>后台求解模式已结束</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
                steps if steps is not None else '—', score if score is not None else '—')
            tail = '最终棋盘已同步；最大瓦片 <b>%s</b>' % (mt if mt is not None else '—')
            action = '已结束'
        elif status == 'error':
            head, tail, action = '状态：<b>后台求解模式出错</b>', (msg.get('reason') or ''), '出错'
        else:
            head = '状态：<b>后台求解模式已停止</b>　步数 <b>%s</b>　分数 <b>%s</b>' % (
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
        if st in ('GUI_IDLE', 'BG_COMPLETED', 'BG_ERROR'):
            self._v6_active_mode = None
        self._v6_sync_run_controls()
        self._v6_bg_log('[后台] %s · 步 %s · 分数 %s' % (action, steps, score),
                        key=('final', status, steps))

    # ---------------------------------------------------------- 挂钩：搜索
    def _request_decision(self):
        # 标准/快速：已暂停则不再请求下一步（安全步边界，不打断在途计算）
        if getattr(self, '_v6_local_paused', False) and getattr(self, '_solver_running', False):
            return
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
        # 暂停请求已发出：收尾在途标志并**暂存**本步结果，不落子（恢复时优先复用它）
        if (getattr(self, '_v6_local_pausing', False)
                and getattr(self, '_solver_running', False)
                and job_id == getattr(self, '_job_id', None)):
            self._solve_in_flight = False
            self.solver_progress.setRange(0, 100)
            self.solver_progress.setValue(0)
            self._v6_paused_result = (job_id, result, getattr(self, '_board_sig', None))
            self._v6_local_pausing = False
            self._v6_local_paused = True
            self._v6_sync_run_controls()
            return
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
