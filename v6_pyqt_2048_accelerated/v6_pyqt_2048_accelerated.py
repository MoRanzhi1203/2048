#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2048 第六版（V6）独立启动入口：复用 V5 GUI，隔离全部数据路径，接入 V6 计算后端。

隔离要点（对齐《V6 指令》§1 V1 / §7）：
- 存档目录：通过 `2048_HISTORY_DIR` 把 v3/v4/v5 链路的历史目录全部重定向到
  V6 自己的 `game_history/` 下，**不写入 v1–v5 的 game_history**；V6 使用 `v6` 版本标记。
- 会话与导出：覆盖 V5 的 `_load_sessions/_save_sessions/_export_session/export_comparison`
  指向 V6 的 `solver_results/`（仍沿用 V5 已验证的原子保存 + `.bak` 回退）。
- 求解调度：V6 GUI 使用 `solver_v6`（同一份算法 + 可选计算后端）；V5 源码保持只读、不改动。
- 正式 RL 模型：只读，V6 不训练、不替换 `rl_model.npz`。
"""

from __future__ import annotations

import os
import sys

V6_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(V6_DIR)
V5_DIR = os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')

for _p in (V6_DIR, V5_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# V6 独立数据目录（在实例化窗口前设置隔离环境变量，确保 v3/v4/v5 链路也落在 V6 目录内）
V6_RESULT_DIR = os.path.join(V6_DIR, 'solver_results')
V6_EXPORT_DIR = os.path.join(V6_RESULT_DIR, 'exports')
V6_SESSIONS_FILE = os.path.join(V6_RESULT_DIR, 'sessions.json')
V6_HISTORY_ROOT = os.path.join(V6_DIR, 'game_history')
V6_HISTORY_DIR = os.path.join(V6_HISTORY_ROOT, 'v6')
os.environ.setdefault('2048_HISTORY_DIR', V6_HISTORY_ROOT)

import solver_v6                                                 # noqa: E402
import v5_pyqt_2048_solver as _v5gui                            # noqa: E402  (只读复用 GUI)
import safe_store as _store                                     # noqa: E402
from v6_speed import V6SpeedMixin                               # noqa: E402  (三档速度/分段计时)

# 运行时适配：让 V5 GUI（原样复用）调用 V6 的求解调度（含计算后端）。不修改 V5 源码。
_v5gui.solver = solver_v6

v4 = _v5gui.v4
build_app_icon = v4.build_app_icon

from PyQt5.QtCore import Qt                                       # noqa: E402
from PyQt5.QtGui import QFont                                     # noqa: E402
from PyQt5.QtWidgets import (QApplication, QComboBox, QHBoxLayout,  # noqa: E402
                             QLabel, QSizePolicy)

BACKEND_CHOICES = (
    ('自动（默认）', 'auto'),
    ('参考 Reference', 'reference'),
    ('NumPy', 'numpy'),
    ('Numba', 'numba'),
    ('C++ Bitboard', 'cpp'),
)


class V6MainWindow(V6SpeedMixin, _v5gui.SolverMainWindow):
    """V5 双栏 GUI + V6 数据隔离 + 计算后端选择 + 三档运行速度。"""

    def __init__(self):
        # 数据隔离：全部落在 V6 目录，绝不写 v1–v5
        os.makedirs(V6_RESULT_DIR, exist_ok=True)
        os.makedirs(V6_EXPORT_DIR, exist_ok=True)
        self._v6_backend = (os.environ.get('V6_BACKEND') or 'auto').strip() or 'auto'
        super().__init__()

    # ---------------- 覆盖：界面初始化后切换存档目录与标题 ----------------
    def init_ui(self):
        super().init_ui()                       # 复用 V5 全部界面构建（含双栏/把手）
        self.model.set_history_dir(
            _store.resolve_history_dir(V6_HISTORY_ROOT, 'v6'), 'v6')   # 切到 V6 存档目录
        self._prune_inherited_history_dirs()    # 清理继承链遗留的空版本目录
        self.setWindowTitle(self._title_text())
        self._install_backend_selector()
        self._v6_speed_init()                   # 三档速度 + 分段计时（含持久化）

    def _prune_inherited_history_dirs(self):
        """删除继承链（v3/v4/v5）在 V6 存档根下遗留的**空**目录，使其只保留 v6/。

        成因：V6 GUI 继承 v5/v4/v3，构造期间各版本依次设置自己的存档目录
        （经 `2048_HISTORY_DIR` 全部落在 V6 根下）。仅 v6 会真正写入数据，
        v3/v4/v5 目录保持为空；此处只删除**空**目录，绝不触碰任何非空目录。
        """
        for tag in ('v3', 'v4', 'v5'):
            d = os.path.join(V6_HISTORY_ROOT, tag)
            try:
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
            except OSError:
                pass

    # ---------------- 路径隔离：会话与导出 ----------------
    def _load_sessions(self):
        for path in (V6_SESSIONS_FILE, V6_SESSIONS_FILE + '.bak'):
            if not os.path.exists(path):
                continue
            try:
                import json
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except Exception:                   # noqa: BLE001
                continue
        return []

    def _save_sessions(self):
        """原子保存（tmp → 旧版转存 .bak → 同盘原子替换），指向 V6 路径。"""
        import json
        tmp = V6_SESSIONS_FILE + '.tmp'
        bak = V6_SESSIONS_FILE + '.bak'
        try:
            os.makedirs(V6_RESULT_DIR, exist_ok=True)
            payload = json.dumps(self._sessions, ensure_ascii=False, separators=(',', ':'))
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(V6_SESSIONS_FILE):
                os.replace(V6_SESSIONS_FILE, bak)
            os.replace(tmp, V6_SESSIONS_FILE)
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def _export_session(self, session):
        import csv
        import json
        os.makedirs(V6_EXPORT_DIR, exist_ok=True)
        base = session['id']
        json_path = os.path.join(V6_EXPORT_DIR, base + '.json')
        csv_path = os.path.join(V6_EXPORT_DIR, base + '.csv')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['步数', '方向', '评估分', '搜索深度', '是否超时',
                             '当前分数', '最大瓦片', '用时ms'])
            for st in session.get('steps', []):
                writer.writerow([st['step'], st['name'], st.get('eval'),
                                 st.get('depth_reached'), st.get('timed_out'),
                                 st['score'], st['max_tile'], st['elapsed_ms']])
        return {'json': json_path, 'csv': csv_path}

    def export_comparison(self, rows):
        import csv
        import datetime
        try:
            os.makedirs(V6_EXPORT_DIR, exist_ok=True)
            path = os.path.join(V6_EXPORT_DIR, 'comparison_%s.csv'
                                % datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['开始时间', '策略', '深度', '模式', '步数', '最终分数',
                                 '最大瓦片', '平均ms', '超时次数', '总用时s', '结束原因'])
                for r in rows:
                    writer.writerow([r['started_at'], r['strategy'], r['depth'], r['mode'],
                                     r['steps'], r['final_score'], r['final_max_tile'],
                                     r['avg_ms'], r['timeouts'], r['elapsed_s'], r['reason']])
            return path
        except OSError:
            return None

    # ---------------- 后端注入 ----------------
    def _request_decision(self):
        if isinstance(getattr(self, '_solver_config', None), dict):
            self._solver_config['backend'] = self._v6_backend
        super()._request_decision()

    def _title_text(self):
        status = solver_v6.backend_status()
        info = status.get(self._v6_backend, {}) if self._v6_backend != 'auto' else None
        if self._v6_backend == 'auto':
            used = solver_v6.default_backend_name() if hasattr(solver_v6, 'default_backend_name') else 'reference'
            return '2048 V6 · 后端=自动(%s)' % used
        avail = '可用' if info.get('available') else '回退'
        return '2048 V6 · 后端=%s(%s)' % (self._v6_backend, avail)

    def _install_backend_selector(self):
        """在「高级参数」折叠区内加入“计算后端”下拉（默认不向普通用户暴露）。"""
        body = getattr(self, 'solver_advanced_body', None)
        if body is None or body.layout() is None:
            return
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 2)
        lab = QLabel('计算后端')
        lab.setStyleSheet('color:#8f8175; font-size:11px;')
        lab.setFixedWidth(58)
        combo = QComboBox()
        combo.setStyleSheet(_v5gui.COMBO_QSS if hasattr(_v5gui, 'COMBO_QSS') else '')
        status = solver_v6.backend_status()
        for text, key in BACKEND_CHOICES:
            if key == 'auto':
                suffix = ''
            else:
                suffix = '' if status.get(key, {}).get('available') else '（不可用→回退）'
            combo.addItem(text + suffix, key)
        idx = combo.findData(self._v6_backend)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.currentIndexChanged.connect(self._on_backend_changed)
        self.solver_backend_combo = combo
        row.addWidget(lab)
        row.addWidget(combo, 1)
        body.layout().addLayout(row)

    def _on_backend_changed(self, _index):
        key = self.solver_backend_combo.currentData()
        self._v6_backend = key or 'auto'
        self.setWindowTitle(self._title_text())
        if getattr(self, '_session', None) is not None or True:
            try:
                self._log_step('计算后端切换为：%s' % self._v6_backend)
            except Exception:                   # noqa: BLE001
                pass


# 与其它版本保持一致的主窗口符号（统一截图入口 tools/capture_gui.py 依赖它）
MainWindow = V6MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setWindowIcon(build_app_icon())
    font = QFont('Microsoft YaHei', 10)
    if hasattr(font, 'setFamilies'):
        font.setFamilies(['Microsoft YaHei', 'Microsoft YaHei UI', 'SimHei'])
    app.setFont(font)
    window = V6MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
