#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048：算法求解版（第 5 版）

配套博客《第 6 篇：经典算法求解 2048》。

设计要点（严格沿用第 4 版界面，只做“增量”扩展）：
    Model       -> 复用第 4 版 AnimatedGameCore（棋盘 / 合并 / 存档 / 撤销重做一行未改），
                   仅把存档目录指向 v5 自己的 game_history；
    View        -> 复用第 4 版 BoardView / ParticleOverlay / 全部视觉常量；
    Controller  -> SolverMainWindow 继承第 4 版 MainWindow：
                   1) 在游戏页底部“向下扩展”一块求解面板（原有控件坐标完全不变）；
                   2) 在原按钮行新增一个「AI 求解」入口按钮；
                   3) 求解在后台线程（SolverWorker）执行，带超时与异常兜底，
                      绝不阻塞或破坏原有界面。

求解能力：
    - 策略：启发式（单步贪心） / Expectimax（迭代加深 + 时间预算）
    - 模式：单步建议（只提示方向） / 自动连走（驱动真实棋盘，复用第 4 版动画）
    - 实时状态：状态 / 步数 / 当前方向与评估分 / 用时 / 最大瓦片 / 分数
    - 中间结果：逐步日志列表
    - 结果输出：结构化会话（JSON/CSV 导出）+ 查看 + 多会话对比
"""

import csv
import datetime
import json
import os
import sys
import time

# ---- 复用第 4 版的界面与模型（v5 不改动它们） ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_V4_DIR = os.path.join(os.path.dirname(_HERE), "v4_pyqt_2048_animated")
for _p in (_ROOT, _V4_DIR, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v4_pyqt_2048_animated as v4                                    # noqa: E402
import solver_2048 as solver                                          # noqa: E402
import ui_theme as _theme                                             # noqa: E402
import safe_store as _store                                           # noqa: E402

from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QPushButton,   # noqa: E402
                             QVBoxLayout, QHBoxLayout, QComboBox, QListWidget,
                             QListWidgetItem, QProgressBar,
                             QDialog, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QScrollArea, QFrame)
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal, pyqtSlot   # noqa: E402
from PyQt5.QtGui import QColor, QFont                                 # noqa: E402


# =====================================================================
# 常量：窗口与求解面板
# =====================================================================
WINDOW_WIDTH = v4.WINDOW_WIDTH                 # 500（与第 4 版一致）
WINDOW_HEIGHT = v4.WINDOW_HEIGHT               # 672（第 4 版游戏页高度）

PANEL_H = 214                                  # 底部求解面板的“期望”高度（空间足够时）
PANEL_MIN = 60                                 # 面板最小高度（再小时改为面板内滚动）
TITLEBAR_RESERVE = 56                          # 估算标题栏 + 边距（逻辑像素）
V5_WINDOW_HEIGHT = WINDOW_HEIGHT + PANEL_H     # 886：整窗在原版基础上向下加高（上限）

PANEL_BG = "#F2E9DD"
PANEL_LINE = "#D8C9B9"
PANEL_RADIUS = 12
LOG_BG = "#FAF5EE"
LOG_LINE = "#E4D9C9"

RESULT_DIR = os.path.join(_HERE, "solver_results")
EXPORT_DIR = os.path.join(RESULT_DIR, "exports")
SESSIONS_FILE = os.path.join(RESULT_DIR, "sessions.json")

STEP_DELAY_MS = 70                             # 自动连走时每步之间的停顿（ms）

COMBO_QSS = f"""
QComboBox {{
    background-color: #FFFFFF; color: {v4.COLOR_TEXT};
    border: 1px solid {PANEL_LINE}; border-radius: 5px;
    padding: 2px 6px; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; width: 16px; }}
QComboBox:disabled {{ background-color: #F0EBE3; color: #B7A595; }}
QComboBox QAbstractItemView {{
    background: #FFFFFF; color: {v4.COLOR_TEXT};
    selection-background-color: #E4D9C9; font-size: 12px; outline: none;
}}
"""

PANEL_BUTTON_QSS = f"""
QPushButton {{
    background-color: #EEE4DA; color: {v4.COLOR_TEXT};
    border: 1px solid {PANEL_LINE}; border-radius: 6px;
    font-size: 12px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #E2D7CA; }}
QPushButton:pressed  {{ background-color: #D5C9BA; }}
QPushButton:focus    {{ border-color: #8F7A66; }}
QPushButton:disabled {{ background-color: #F0EBE3; color: #B7A595; border-color: #E0D6C8; }}
"""

PANEL_PRIMARY_QSS = f"""
QPushButton {{
    background-color: {v4.COLOR_BOARD}; color: #FFFFFF;
    border: 1px solid {v4.COLOR_BOARD}; border-radius: 6px;
    font-size: 12px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #A8998B; }}
QPushButton:pressed  {{ background-color: #9A8B7D; }}
QPushButton:focus    {{ border-color: #8F7A66; }}
QPushButton:disabled {{ background-color: #D8CBBB; color: #F1EAE0; border-color: #D8CBBB; }}
"""

PROGRESS_QSS = f"""
QProgressBar {{
    background-color: #E4D9C9; border: none; border-radius: 4px;
}}
QProgressBar::chunk {{ background-color: {v4.COLOR_BOARD}; border-radius: 4px; }}
"""

LOG_QSS = f"""
QListWidget {{
    background-color: {LOG_BG}; border: 1px solid {LOG_LINE}; border-radius: 6px;
    color: {v4.COLOR_TEXT}; font-size: 11px; outline: none;
}}
QListWidget::item {{ padding: 1px 4px; }}
QListWidget::item:selected {{ background-color: #E4D9C9; color: {v4.COLOR_TEXT}; }}
"""

# 求解面板内层滚动区：透明背景 + 细滚动条（卡片外框由外层 solverPanel 绘制）
SCROLL_QSS = """
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 1px 2px 0; }
QScrollBar::handle:vertical { background: #CBBBA9; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #BCA893; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


# =====================================================================
# 求解会话（结构化结果）
# =====================================================================
def new_session(strategy, depth_label, time_limit, mode):
    return {
        "id": datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        "strategy": strategy,
        "strategy_name": solver.STRATEGIES.get(strategy, strategy),
        "depth_label": depth_label,
        "time_limit": time_limit,
        "mode": mode,
        "mode_name": {"auto": "自动连走", "single": "单步建议"}.get(mode, mode),
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "elapsed_ms": 0.0,
        "steps": [],
        "final_score": None,
        "final_max_tile": None,
        "game_over": False,
        "stopped_reason": "",
        "timeout_count": 0,
    }


def session_rows(session):
    """会话摘要行（用于查看/对比表格）"""
    steps = session.get("steps", [])
    avg = 0.0
    if steps:
        avg = sum(s.get("elapsed_ms", 0.0) for s in steps) / len(steps)
    return {
        "id": session.get("id", ""),
        "strategy": session.get("strategy_name", ""),
        "depth": session.get("depth_label", ""),
        "mode": session.get("mode_name", ""),
        "steps": len(steps),
        "final_score": session.get("final_score"),
        "final_max_tile": session.get("final_max_tile"),
        "avg_ms": round(avg, 1),
        "timeouts": session.get("timeout_count", 0),
        "elapsed_s": round(session.get("elapsed_ms", 0.0) / 1000.0, 2),
        "started_at": session.get("started_at", ""),
        "reason": session.get("stopped_reason", ""),
    }


# =====================================================================
# 后台求解线程：把“可能耗时”的搜索移出 UI 线程，界面始终可响应
# =====================================================================
class SolverWorker(QObject):
    solved = pyqtSignal(dict)
    failed = pyqtSignal(str)

    @pyqtSlot(list, dict)
    def solve(self, grid, config):
        try:
            result = solver.solve(grid, **config)
            self.solved.emit(result)
        except Exception as exc:                                      # noqa: BLE001
            self.failed.emit("%s: %s" % (type(exc).__name__, exc))


# =====================================================================
# 结果对话框：查看单个会话 / 对比全部会话
# =====================================================================
class SolverResultsDialog(QDialog):
    def __init__(self, parent, sessions, compare=False):
        super().__init__(parent)
        self.sessions = sessions
        self.compare = compare
        self.setWindowTitle("求解结果对比" if compare else "查看求解结果")
        self.setStyleSheet(_theme.content_dialog_qss())      # 统一暖棕主题
        self.resize(480, 420 if compare else 470)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        caption = QLabel("各会话对比" if compare else "求解会话详情")
        caption.setStyleSheet(
            "color:%s; font-size:14px; font-weight:bold;" % _theme.PALETTE["text"])
        root.addWidget(caption)

        if compare:
            self._build_compare(root)
        else:
            self._build_view(root)

    # ---------- 查看：单会话 ----------
    def _build_view(self, root):
        if not self.sessions:
            root.addWidget(QLabel("暂无求解结果。"))
            root.addStretch()
            root.addWidget(self._close_button())
            return

        picker = QHBoxLayout()
        picker.addWidget(QLabel("选择会话："))
        self.combo = QComboBox()
        self.combo.setStyleSheet(COMBO_QSS)
        for s in reversed(self.sessions):
            r = session_rows(s)
            self.combo.addItem("%s · %s · %d 步 · 分数 %s"
                               % (r["started_at"], r["strategy"], r["steps"], r["final_score"]),
                               s)
        picker.addWidget(self.combo, 1)
        root.addLayout(picker)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color:{v4.COLOR_TEXT}; font-size:12px;")
        root.addWidget(self.summary)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["步", "方向", "评估分", "分数", "最大瓦片", "用时ms"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        self.combo.currentIndexChanged.connect(self._refresh)
        self._refresh()
        root.addWidget(self._close_button())

    def _refresh(self):
        s = self.combo.currentData()
        if s is None:
            return
        r = session_rows(s)
        self.summary.setText(
            "策略 %s · 深度 %s · 模式 %s · 用时 %ss · 超时 %d 次<br>"
            "最终分数 <b>%s</b> · 最大瓦片 <b>%s</b> · 结束原因：%s"
            % (r["strategy"], r["depth"], r["mode"], r["elapsed_s"], r["timeouts"],
               r["final_score"], r["final_max_tile"], r["reason"] or "—"))
        steps = s.get("steps", [])
        self.table.setRowCount(len(steps))
        for i, st in enumerate(steps):
            ev = st.get("eval")
            values = [st.get("step"), st.get("name"),
                      ("—" if ev is None else "%.1f" % ev),
                      st.get("score"), st.get("max_tile"),
                      "%.1f" % st.get("elapsed_ms", 0.0)]
            for j, val in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(str(val)))

    # ---------- 对比：多会话 ----------
    def _build_compare(self, root):
        if not self.sessions:
            root.addWidget(QLabel("暂无可对比的求解结果。"))
            root.addStretch()
            root.addWidget(self._close_button())
            return

        rows = [session_rows(s) for s in self.sessions]
        headers = ["开始时间", "策略", "深度", "模式", "步数", "最终分数",
                   "最大瓦片", "平均ms", "超时"]
        self.table = QTableWidget(len(rows), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for i, r in enumerate(rows):
            values = [r["started_at"][-8:], r["strategy"], r["depth"], r["mode"],
                      r["steps"], r["final_score"], r["final_max_tile"],
                      r["avg_ms"], r["timeouts"]]
            for j, val in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(str(val)))
        root.addWidget(self.table, 1)

        note = QLabel("提示：步数 / 最终分数越高越好，平均 ms 越低越好。")
        note.setStyleSheet(f"color:#8f8175; font-size:11px;")
        root.addWidget(note)

        bar = QHBoxLayout()
        export_btn = QPushButton("导出对比 CSV")
        export_btn.setStyleSheet(_theme.secondary_button_qss())
        export_btn.setFixedHeight(30)
        export_btn.setCursor(Qt.PointingHandCursor)

        def _export():
            path = self.parent().export_comparison(rows) if hasattr(self.parent(), "export_comparison") else None
            if path:
                _theme.show_info(self, "导出对比", "已导出：\n%s" % path, badge="success")
            else:
                _theme.show_warning(self, "导出对比", "导出失败，请检查磁盘权限或路径。")

        export_btn.clicked.connect(_export)
        bar.addWidget(export_btn)
        bar.addStretch()
        bar.addWidget(self._close_button())
        root.addLayout(bar)

    def _close_button(self):
        btn = QPushButton("关闭")
        btn.setStyleSheet(_theme.primary_button_qss())
        btn.setFixedSize(84, 30)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(btn)
        holder = QWidget()
        holder.setLayout(wrapper)
        return holder


# =====================================================================
# 主窗口：在第 4 版基础上“向下扩展”求解面板
# =====================================================================
class SolverMainWindow(v4.MainWindow):

    # 主线程 -> 工作线程 的求解请求（跨线程自动排队）
    solveRequested = pyqtSignal(list, dict)

    def __init__(self):
        super().__init__()

    # ---------------- 覆盖：构建游戏页（追加 AI 入口按钮） ----------------
    def _build_game_page(self):
        page = super()._build_game_page()
        row = self._find_row_layout(page.layout(), self.new_game_button)
        if row is not None:
            self.solver_ai_button = self._make_button(
                "AI 求解", self.on_solver_clicked,
                qss=v4.SECONDARY_BUTTON_QSS, size=(78, 44),
                particle_color="#cbbcaa")
            self.solver_ai_button.setToolTip("用算法（启发式 / Expectimax）求解当前局面")
            row.insertWidget(row.indexOf(self.new_game_button), self.solver_ai_button)
        return page

    @staticmethod
    def _find_row_layout(layout, widget):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            sub = item.layout() if item is not None else None
            if sub is not None and sub.indexOf(widget) != -1:
                return sub
        return None

    # ---------------- 覆盖：界面初始化（复用 v4 后扩展） ----------------
    def init_ui(self):
        super().init_ui()

        # v5 使用自己的存档目录与版本标记（跨版本隔离），并重绑单实例锁
        self.model.set_history_dir(
            _store.resolve_history_dir(os.path.join(_HERE, "game_history"), "v5"), "v5")

        self._init_solver()
        self._build_solver_panel()
        # 启动页尺寸与第 4 版完全一致；进入游戏页时再向下扩展出求解面板
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.refresh()

    def _grow_for_solver(self):
        """进入游戏页时把窗口扩展到“第 4 版布局 + 底部求解面板”（高度自适应屏幕）。"""
        self._apply_solver_size()

    # ---------------- 覆盖：切到游戏页时同步扩展窗口 ----------------
    def start_new_game(self):
        self._grow_for_solver()          # 先扩好尺寸，再切页，避免出现被压扁的一帧
        super().start_new_game()

    def on_continue_clicked(self):
        self._grow_for_solver()
        super().on_continue_clicked()

    # ---------------- 求解状态初始化 ----------------
    def _init_solver(self):
        self._solver_running = False
        self._solve_in_flight = False
        self._ai_applying = False
        self._solver_mode = "auto"
        self._solver_config = {"strategy": "expectimax", "depth": 4, "time_limit": 0.3}
        self._session = None
        self._pending_result = None
        self._sessions = self._load_sessions()

        # 窗口位置跟踪：仅在用户未手动拖动时自动居中 / 校正越界
        self._shown_once = False
        self._user_moved = False
        self._programmatic_move = False

        # 工作线程按需创建：只有真正求解时才启动，空闲/截图/退出时不存在运行中的线程
        self._solver_thread = None
        self._solver_worker = None

    def _ensure_worker(self):
        """惰性创建并启动后台求解线程（已运行则直接复用）。"""
        if self._solver_thread is not None and self._solver_thread.isRunning():
            return
        self._solver_thread = QThread(self)
        self._solver_worker = SolverWorker()
        self._solver_worker.moveToThread(self._solver_thread)
        self._solver_worker.solved.connect(self._on_solver_result)
        self._solver_worker.failed.connect(self._on_solver_failed)
        self.solveRequested.connect(self._solver_worker.solve)
        self._solver_thread.start()

    def _shutdown_worker(self):
        """停止并回收求解线程（幂等，可重复调用）。"""
        thread = self._solver_thread
        if thread is None:
            return
        try:
            self.solveRequested.disconnect(self._solver_worker.solve)
        except (TypeError, RuntimeError):
            pass
        try:
            thread.quit()
            thread.wait(1500)
        except RuntimeError:
            pass
        self._solver_thread = None
        self._solver_worker = None

    # ---------------- 求解面板 ----------------
    def _build_solver_panel(self):
        # 外层：卡片外框（与启动页信息卡同款的圆角米色卡片）
        panel = QWidget()
        panel.setObjectName("solverPanel")
        panel.setStyleSheet(
            f"#solverPanel {{ background-color: {PANEL_BG};"
            f" border: 1px solid {PANEL_LINE}; border-radius: {PANEL_RADIUS}px; }}")
        panel.setFixedHeight(PANEL_H)
        panel_box = QVBoxLayout(panel)
        panel_box.setContentsMargins(2, 2, 2, 2)
        panel_box.setSpacing(0)

        # 内层：可滚动内容 —— 当屏幕高度不足以完整显示面板时，面板内部滚动，
        # 保证策略/按钮/状态/日志始终都能访问到。
        content = QWidget()
        content.setAutoFillBackground(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(SCROLL_QSS)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(content)
        panel_box.addWidget(scroll)
        self.solver_panel = panel
        self.solver_scroll = scroll

        outer = QVBoxLayout(content)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(7)

        # 第一行：标题 + 策略 / 深度 / 模式
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        title = QLabel("算法求解")
        title.setStyleSheet(f"color:{v4.COLOR_TEXT}; font-size:13px; font-weight:bold;")
        self.solver_title = title
        row1.addWidget(title)
        row1.addStretch()
        self.solver_strategy = self._make_combo(
            [(solver.STRATEGIES[k], k) for k in solver.STRATEGY_ORDER], 106)
        self.solver_depth = self._make_combo(
            [(solver.PRESET_LABELS[k], k) for k in solver.PRESET_ORDER], 66)
        self.solver_depth.setCurrentIndex(1)
        self.solver_mode = self._make_combo([("自动连走", "auto"), ("单步建议", "single")], 84)
        self.solver_strategy.setCurrentIndex(solver.STRATEGY_ORDER.index("expectimax"))  # 默认 Expectimax
        self.solver_strategy.currentIndexChanged.connect(self._on_strategy_changed)
        self._on_strategy_changed()                       # 同步“强度”可用状态
        row1.addWidget(self.solver_strategy)
        row1.addWidget(self.solver_depth)
        row1.addWidget(self.solver_mode)
        outer.addLayout(row1)

        # 第二行：操作按钮
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.solver_start_btn = QPushButton("开始求解")
        self.solver_start_btn.setStyleSheet(PANEL_PRIMARY_QSS)
        self.solver_start_btn.setFixedSize(96, 30)
        self.solver_start_btn.setCursor(Qt.PointingHandCursor)
        self.solver_start_btn.clicked.connect(self.on_solver_clicked)

        self.solver_export_btn = QPushButton("导出结果")
        self.solver_view_btn = QPushButton("查看结果")
        self.solver_compare_btn = QPushButton("对比")
        for btn, slot, width in ((self.solver_export_btn, self.on_solver_export, 78),
                                 (self.solver_view_btn, self.on_solver_view, 78),
                                 (self.solver_compare_btn, self.on_solver_compare, 60)):
            btn.setStyleSheet(PANEL_BUTTON_QSS)
            btn.setFixedSize(width, 30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
        row2.addWidget(self.solver_start_btn)
        row2.addWidget(self.solver_export_btn)
        row2.addWidget(self.solver_view_btn)
        row2.addWidget(self.solver_compare_btn)
        row2.addStretch()
        outer.addLayout(row2)

        # 第三行：进度 + 状态
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.solver_progress = QProgressBar()
        self.solver_progress.setFixedSize(110, 8)
        self.solver_progress.setTextVisible(False)
        self.solver_progress.setStyleSheet(PROGRESS_QSS)
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        self.solver_status = QLabel()
        self.solver_status.setWordWrap(True)
        self.solver_status.setMinimumHeight(38)
        row3.addWidget(self.solver_progress, 0, Qt.AlignVCenter)
        row3.addWidget(self.solver_status, 1)
        outer.addLayout(row3)

        # 第四行：步骤日志
        self.solver_log = QListWidget()
        self.solver_log.setFixedHeight(62)
        self.solver_log.setStyleSheet(LOG_QSS)
        self.solver_log.setFocusPolicy(Qt.NoFocus)
        outer.addWidget(self.solver_log)
        outer.addStretch()                    # 多余空间落到底部，避免内容被拉伸

        # 插入到游戏页布局：放在“尾部 stretch”之前（即按钮行下方），
        # 上方原有控件坐标保持不变。注意 addSpacing 也会产生 spacer，
        # 因此取“最后一个 spacer”（尾部 addStretch）作为插入点。
        page = self.stack.widget(v4.GAME_PAGE)
        lay = page.layout()
        insert_at = lay.count()
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is not None and item.spacerItem() is not None:
                insert_at = i
        lay.insertWidget(insert_at, panel)
        lay.insertSpacing(insert_at, 12)      # 面板与按钮行之间留出呼吸空间

        self._render_idle_status()

    # ---------------- 自适应尺寸：窗口始终完整落在屏幕内 ----------------
    def _available_height(self):
        """当前屏幕可用高度（Qt 逻辑像素）；取不到时退回期望整窗高度。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return V5_WINDOW_HEIGHT
        return screen.availableGeometry().height()

    def _target_game_height(self):
        avail = self._available_height()
        return int(max(WINDOW_HEIGHT, min(V5_WINDOW_HEIGHT, avail - TITLEBAR_RESERVE)))

    def _apply_solver_size(self):
        """进入游戏页：按屏幕可用高度自适应窗口高度，并让面板内部滚动兜底。

        高度下限取“游戏页布局最小高度”，保证窗口再矮也不会把原有控件压变形。
        位置：未被用户手动拖动过时自动居中；否则只做越界校正，不打扰用户摆放。
        """
        target = self._target_game_height()
        panel_h = max(PANEL_MIN, target - WINDOW_HEIGHT)
        self.solver_panel.setFixedHeight(panel_h)
        page = self.stack.widget(v4.GAME_PAGE)
        if page is not None:
            target = max(target, page.minimumSizeHint().height())
        self.setFixedSize(WINDOW_WIDTH, int(target))
        if not self._user_moved:
            self._center_on_screen()
        self._keep_on_screen()

    def _safe_move(self, x, y):
        """程序化移动窗口（不记为“用户拖动”）。"""
        self._programmatic_move = True
        try:
            self.move(int(x), int(y))
        finally:
            self._programmatic_move = False

    def _center_on_screen(self):
        """把窗口居中到当前屏幕的可用区域。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        av = screen.availableGeometry()
        fg = self.frameGeometry()
        x = av.left() + (av.width() - fg.width()) // 2
        y = av.top() + (av.height() - fg.height()) // 2
        self._safe_move(x, y)

    def _keep_on_screen(self):
        """若窗口（含标题栏）超出屏幕可用区域，则整体移回可见范围内。

        背景：本机 125% 缩放下，系统会按“放大后的尺寸”去摆放窗口，导致标题栏被
        推到屏幕上方而抓不到。这里以 frameGeometry 与 availableGeometry 求位移，
        只在真正越界时才移动，不影响用户手动摆放的位置。
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        av = screen.availableGeometry()
        fg = self.frameGeometry()
        dx = dy = 0
        if fg.left() < av.left():
            dx = av.left() - fg.left()
        elif fg.right() > av.right():
            dx = av.right() - fg.right()
        if fg.top() < av.top():
            dy = av.top() - fg.top()
        elif fg.bottom() > av.bottom():
            dy = av.bottom() - fg.bottom()
        if dx or dy:
            self._safe_move(self.x() + dx, self.y() + dy)

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self._programmatic_move:      # 用户手动拖动
            self._user_moved = True

    def showEvent(self, event):
        super().showEvent(event)
        if not self._shown_once:             # 启动首次显示：居中（0ms + 稍后各一次，避开系统延迟摆放）
            self._shown_once = True
            QTimer.singleShot(0, self._center_initial)
            QTimer.singleShot(180, self._center_initial)
        else:
            self._keep_on_screen()

    def _center_initial(self):
        """启动首次显示后的居中：强制居中，覆盖系统延迟摆放产生的偏移。"""
        self._user_moved = False             # 启动摆放期间的移动不视为“用户拖动”
        self._center_on_screen()
        self._keep_on_screen()

    def _make_combo(self, items, width):
        combo = QComboBox()
        combo.setFixedSize(width, 26)
        combo.setStyleSheet(COMBO_QSS)
        combo.setCursor(Qt.PointingHandCursor)
        for text, data in items:
            combo.addItem(text, data)
        return combo

    def _on_strategy_changed(self):
        # 仅部分策略有“强度”参数（贪心模拟 / Expectimax / MCTS），其余置灰
        self.solver_depth.setEnabled(solver.has_presets(self.solver_strategy.currentData()))

    # ---------------- 状态文案 ----------------
    def _set_status(self, line1, line2="", error=False):
        c1 = "#B23B2E" if error else v4.COLOR_TEXT
        c2 = "#A1665E" if error else "#8f8175"
        html = "<span style='font-size:12px;color:%s;'>%s</span>" % (c1, line1)
        if line2:
            html += "<br><span style='font-size:11px;color:%s;'>%s</span>" % (c2, line2)
        self.solver_status.setText(html)

    def _render_idle_status(self):
        self._set_status("就绪：选择策略后点击「开始求解」",
                         "自动连走会驱动棋盘走子；单步建议只提示方向。")

    def _render_running_status(self, computing=False):
        if self._session is None:
            return
        steps = len(self._session["steps"])
        last = self._session["steps"][-1] if steps else None
        if computing:
            head = "状态：<b>求解中…</b>"
        else:
            head = "状态：<b>运行中</b>"
        if last is not None:
            cur = "当前：<b>%s</b>（评估 %.1f）" % (last["name"], last.get("eval") or 0.0)
            extra = "分数 <b>%d</b>　最大瓦片 <b>%d</b>　用时 <b>%.1fs</b>" % (
                last["score"], last["max_tile"], self._session["elapsed_ms"] / 1000.0)
        else:
            cur = "等待第一步…"
            extra = "分数 <b>%d</b>" % self.model.score
        self._set_status("%s　步数 <b>%d</b>　%s" % (head, steps, cur), extra)

    def _log_step(self, text):
        item = QListWidgetItem(text)
        item.setForeground(QColor(v4.COLOR_TEXT))
        self.solver_log.addItem(item)
        self.solver_log.scrollToBottom()

    # ---------------- 入口：AI 求解按钮 / 面板开始按钮 ----------------
    def on_solver_clicked(self):
        if self._solver_running:
            self._stop_solver("用户停止")
            return
        self._start_solver()

    def _start_solver(self):
        if self._solve_in_flight:
            return
        if self.model.game_over:
            self._set_status("游戏已结束，请先「新游戏」再求解。", error=True)
            return
        if not solver.legal_moves(self.model.grid):
            self._set_status("当前无可移动方向。", error=True)
            return

        strategy = self.solver_strategy.currentData()
        preset = self.solver_depth.currentData()
        self._solver_config = solver.build_config(strategy, preset)
        self._solver_mode = self.solver_mode.currentData()

        self._session = new_session(strategy, solver.PRESET_LABELS.get(preset, preset),
                                    self._solver_config.get("time_limit", 0.0),
                                    self._solver_mode)
        self._session["_start_ts"] = time.time()
        self.solver_log.clear()
        self._solver_running = True
        self._pending_result = None
        self._update_solver_buttons()
        self._log_step("开始求解：策略=%s，%s，模式=%s"
                       % (solver.STRATEGIES[strategy],
                          solver.describe_config(self._solver_config),
                          "自动连走" if self._solver_mode == "auto" else "单步建议"))
        self._render_running_status()
        self._request_decision()

    def _request_decision(self):
        if not self._solver_running or self._solve_in_flight:
            return
        if self.model.game_over:
            self._finish_solver("游戏结束")
            return
        if self.board_view.is_animating():
            return
        grid = [row[:] for row in self.model.grid]
        self._ensure_worker()
        self._solve_in_flight = True
        self.solver_progress.setRange(0, 0)          # 忙态（不确定进度）动画
        self._render_running_status(computing=True)
        self.solveRequested.emit(grid, dict(self._solver_config))

    # ---------------- 接收求解结果 ----------------
    def _on_solver_result(self, result):
        self._solve_in_flight = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        if not self._solver_running:
            return

        if result.get("error"):
            self._log_step("求解异常：%s" % result["error"])
            self._set_status("求解出现异常：%s" % result["error"],
                             "已保持当前棋盘不变，原有功能不受影响。", error=True)
            self._stop_solver("求解异常")
            return

        direction = result.get("best_direction")
        if not direction:
            self._finish_solver("无可行移动")
            return

        self._pending_result = result
        if result.get("timed_out"):
            self._session["timeout_count"] += 1

        if self._solver_mode == "single":
            ev = result["evaluations"].get(direction)
            self._log_step("建议：%s（评估 %s，搜索深度 %d，用时 %.1fms）"
                           % (result["best_name"],
                              "—" if ev is None else "%.1f" % ev,
                              result.get("depth_reached", 0), result.get("elapsed_ms", 0.0)))
            self._set_status("建议方向：<b>%s</b>（评估 %s）"
                             % (result["best_name"], "—" if ev is None else "%.1f" % ev),
                             "单步建议模式：未自动走子，可自行按方向键。")
            self._stop_solver("已给出建议")
            return

        # 自动连走：走这一步（复用 v4 的移动 + 动画路径）
        self._ai_apply(direction)

    def _on_solver_failed(self, message):
        self._solve_in_flight = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        if not self._solver_running:
            return
        self._log_step("求解线程异常：%s" % message)
        self._set_status("求解线程异常：%s" % message,
                         "已停止求解，界面与原有功能保持正常。", error=True)
        self._stop_solver("线程异常")

    def _ai_apply(self, direction):
        # 安全检查：方向必须对当前棋盘合法，否则不进入动画（避免卡在“等待动画结束”）
        if direction not in solver.legal_moves(self.model.grid):
            self._finish_solver("无可行移动")
            return
        self._ai_applying = True
        try:
            self.on_move(direction)
        finally:
            self._ai_applying = False

    # ---------------- 覆盖：动画结束后推进求解 ----------------
    def _on_animation_finished(self):
        self.refresh()
        if self._solver_running and self._solver_mode == "auto":
            self._record_step()
            if self.model.game_over:
                self._finish_solver("游戏结束")
            elif self.model.won and not self.win_announced:
                self.win_announced = True
                self._celebrate()
                self._set_status("已合成 <b>2048</b>，继续向更高分挑战…")
                QTimer.singleShot(STEP_DELAY_MS, self._request_decision)
            else:
                QTimer.singleShot(STEP_DELAY_MS, self._request_decision)
            return
        # 非求解状态：完全沿用第 4 版行为（胜负弹窗等）
        super()._on_animation_finished()

    def _record_step(self):
        res = self._pending_result
        if res is None or self._session is None:
            return
        direction = res["best_direction"]
        step = {
            "step": len(self._session["steps"]) + 1,
            "direction": direction,
            "name": res["best_name"],
            "eval": res["evaluations"].get(direction),
            "elapsed_ms": res.get("elapsed_ms", 0.0),
            "depth_reached": res.get("depth_reached", 0),
            "timed_out": bool(res.get("timed_out")),
            "score": self.model.score,
            "max_tile": max(max(row) for row in self.model.grid),
        }
        self._session["steps"].append(step)
        self._session["elapsed_ms"] = (time.time() - self._session["_start_ts"]) * 1000.0
        self._log_step("第 %d 步  %s  评估 %s  分数 %d  最大瓦片 %d  (%.1fms%s)"
                       % (step["step"], step["name"],
                          "—" if step["eval"] is None else "%.1f" % step["eval"],
                          step["score"], step["max_tile"], step["elapsed_ms"],
                          " 超时" if step["timed_out"] else ""))
        self._pending_result = None           # 已消费，避免被后续动画结束事件重复记录
        self._render_running_status()

    # ---------------- 停止 / 结束 ----------------
    def _stop_solver(self, reason, silent=False):
        was_running = self._solver_running
        self._solver_running = False
        self._solve_in_flight = False
        self._ai_applying = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        if not silent and was_running:
            self._log_step("已停止求解（%s）。" % reason)
        self._finalize_session(reason)
        self._update_solver_buttons()
        if not silent:
            self._set_status("已停止求解（%s）。" % reason,
                             "棋盘保持当前状态，可继续手动操作或再次求解。")

    def _finish_solver(self, reason):
        self._solver_running = False
        self._solve_in_flight = False
        self._ai_applying = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        summary = self._finalize_session(reason)
        self._update_solver_buttons()
        if summary:
            self._log_step("求解结束（%s）：共 %d 步，最终分数 %d，最大瓦片 %s"
                           % (reason, summary["steps"], summary["final_score"],
                              summary["final_max_tile"]))
            self._set_status(
                "求解结束（%s）" % reason,
                "共 <b>%d</b> 步　最终分数 <b>%d</b>　最大瓦片 <b>%s</b>　可导出 / 查看 / 对比。"
                % (summary["steps"], summary["final_score"], summary["final_max_tile"]))
        if reason == "游戏结束":
            self.show_game_over()                     # 复用 v4 的结束提示（仅一次）

    def _finalize_session(self, reason):
        """结算当前会话并持久化；返回摘要 dict（无会话时返回 None）。"""
        if self._session is None:
            return None
        self._session["final_score"] = self.model.score
        self._session["final_max_tile"] = max(max(row) for row in self.model.grid) \
            if self.model.grid else 0
        self._session["game_over"] = bool(self.model.game_over)
        self._session["stopped_reason"] = reason
        if "_start_ts" in self._session:
            self._session["elapsed_ms"] = (time.time() - self._session["_start_ts"]) * 1000.0
            del self._session["_start_ts"]
        summary = {
            "steps": len(self._session["steps"]),
            "final_score": self._session["final_score"],
            "final_max_tile": self._session["final_max_tile"],
        }
        self._sessions.append(self._session)
        self._save_sessions()
        self._session = None
        self._shutdown_worker()          # 空闲时回收线程，避免残留运行中的 QThread
        return summary

    def _update_solver_buttons(self):
        running = self._solver_running
        self.solver_start_btn.setText("停止" if running else "开始求解")
        if hasattr(self, "solver_ai_button"):
            self.solver_ai_button.setText("停止" if running else "AI 求解")

    # ---------------- 覆盖：求解期间屏蔽手动操作 ----------------
    def on_move(self, direction):
        if self._solver_running and not self._ai_applying:
            return
        super().on_move(direction)

    def on_undo(self):
        if self._solver_running:
            return
        super().on_undo()

    def on_redo(self):
        if self._solver_running:
            return
        super().on_redo()

    # ---------------- 结果：导出 / 查看 / 对比 ----------------
    def _load_sessions(self):
        if not os.path.exists(SESSIONS_FILE):
            return []
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError):
            return []

    def _save_sessions(self):
        try:
            os.makedirs(RESULT_DIR, exist_ok=True)
            with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def _current_session_for_export(self):
        if self._session is not None:
            return self._session
        return self._sessions[-1] if self._sessions else None

    def on_solver_export(self):
        session = self._current_session_for_export()
        if session is None:
            _theme.show_info(self, "导出结果", "当前没有可导出的求解结果。")
            return
        try:
            paths = self._export_session(session)
        except IOError as exc:
            _theme.show_warning(self, "导出结果", "导出失败：%s" % exc)
            return
        _theme.show_info(self, "导出结果",
                         "已导出以下文件：",
                         detail_lines=[("JSON", paths["json"]), ("CSV", paths["csv"])],
                         badge="success")

    def _export_session(self, session):
        os.makedirs(EXPORT_DIR, exist_ok=True)
        base = session["id"]
        json_path = os.path.join(EXPORT_DIR, base + ".json")
        csv_path = os.path.join(EXPORT_DIR, base + ".csv")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["步数", "方向", "评估分", "搜索深度", "是否超时",
                             "当前分数", "最大瓦片", "用时ms"])
            for st in session.get("steps", []):
                writer.writerow([st["step"], st["name"], st.get("eval"),
                                 st.get("depth_reached"), st.get("timed_out"),
                                 st["score"], st["max_tile"], st["elapsed_ms"]])
        return {"json": json_path, "csv": csv_path}

    def export_comparison(self, rows):
        try:
            os.makedirs(EXPORT_DIR, exist_ok=True)
            path = os.path.join(EXPORT_DIR, "comparison_%s.csv"
                                % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = ["开始时间", "策略", "深度", "模式", "步数", "最终分数",
                           "最大瓦片", "平均ms", "超时次数", "总用时s", "结束原因"]
                writer.writerow(headers)
                for r in rows:
                    writer.writerow([r["started_at"], r["strategy"], r["depth"], r["mode"],
                                     r["steps"], r["final_score"], r["final_max_tile"],
                                     r["avg_ms"], r["timeouts"], r["elapsed_s"], r["reason"]])
            return path
        except IOError:
            return None

    def on_solver_view(self):
        SolverResultsDialog(self, self._sessions, compare=False).exec_()

    def on_solver_compare(self):
        SolverResultsDialog(self, self._sessions, compare=True).exec_()

    # ---------------- 生命周期 ----------------
    def closeEvent(self, event):
        try:
            if self._solver_running or self._session is not None:
                self._stop_solver("窗口关闭", silent=True)
        except Exception:                                            # noqa: BLE001
            pass
        super().closeEvent(event)
        self._shutdown_worker()


# 与其它版本保持一致的主窗口符号（统一截图入口 tools/capture_gui.py 依赖它）
MainWindow = SolverMainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setWindowIcon(v4.build_app_icon())
    font = QFont("Microsoft YaHei", 10)
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"])
    app.setFont(font)
    window = SolverMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
