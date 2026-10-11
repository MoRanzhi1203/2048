#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048：算法求解版（第 5 版）

配套博客《第 5 篇：经典算法求解 2048》。

设计要点（V5.1：左侧 GamePanel + 右侧可拖动/可折叠 Solver 工作台）：
    Model       -> 复用第 4 版 AnimatedGameCore（棋盘 / 合并 / 存档 / 撤销重做一行未改），
                   仅把存档目录指向 v5 自己的 game_history；
    View        -> 复用第 4 版 BoardView / ParticleOverlay / 全部视觉常量；
    Layout      -> 把第 4 版游戏页整体作为左栏，右侧放入求解工作台，用水平 QSplitter
                   承载：可拖动调整宽度、可折叠（折叠=整体隐藏右栏，窗口收窄；展开入口
                   为右侧贴边半胶囊把手 SolverEdgeHandle 或左侧「AI 求解」按钮，两者共用同一展开逻辑）；
    Controller  -> SolverMainWindow 继承第 4 版 MainWindow：
                   1) 求解在后台线程（SolverWorker）执行，带超时与异常兜底，绝不阻塞界面；
                   2) 左侧按钮行「AI 求解」仅负责打开/聚焦右侧 AI 求解面板，不启动算法；
                      启动 / 停止求解由右侧面板的「开始求解」（运行中显示「停止」）负责。

求解能力：
    - 策略：启发式 / 贪心模拟 / Expectimax / MCTS / 强化学习（5 类，本体未改）
    - 模式：单步建议（只提示方向） / 自动连走（驱动真实棋盘，复用第 4 版动画）
    - 实时状态：状态 / 步数 / 当前方向与评估分 / 用时 / 最大瓦片 / 分数（2 列指标）
    - 中间结果：逐步日志列表（主 stretch；支持用户上滚查看历史）
    - 结果输出：结构化会话（JSON/CSV 导出）+ 查看 + 多会话对比
"""

import csv
import datetime
import json
import os
import sys
import threading
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
                             QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox,
                             QListWidget, QListWidgetItem, QProgressBar, QSplitter,
                             QToolButton, QSizePolicy,
                             QDialog, QTableWidget, QTableWidgetItem,
                             QAbstractItemView, QHeaderView, QFrame)
from PyQt5.QtCore import (Qt, QTimer, QThread, QObject, pyqtSignal, pyqtSlot,   # noqa: E402
                          QRect)
from PyQt5.QtGui import (QColor, QFont, QPainter, QPen, QPainterPath)   # noqa: E402


# =====================================================================
# 常量：窗口与求解工作台（V5.1 左右双栏）
# =====================================================================
WINDOW_WIDTH = v4.WINDOW_WIDTH                 # 500（左侧游戏区宽度，与第 4 版逐像素一致）
WINDOW_HEIGHT = v4.WINDOW_HEIGHT               # 672（第 4 版游戏页高度 = 左侧最小高度）

# 右侧 Solver 工作台（可拖动 / 可折叠）
SOLVER_W_DEFAULT = 400                         # 右栏默认宽度
SOLVER_W_MIN = 300                             # 右栏展开态最小宽度
SPLITTER_HANDLE = 6                            # 水平分隔条宽度
CONTAINER_MARGIN = 6                           # 右栏容器边距（展开态）

V5_DEFAULT_H = 720                             # 游戏页默认高度（约 960×720 目标）
V5_MIN_H = WINDOW_HEIGHT                       # 游戏页最小高度（不低于第 4 版高度）
TITLEBAR_RESERVE = 56                          # 估算标题栏 + 边距（逻辑像素）

V5_DEFAULT_WIDTH = WINDOW_WIDTH + SOLVER_W_DEFAULT + SPLITTER_HANDLE   # 906：默认双栏整窗宽
V5_MIN_WIDTH = WINDOW_WIDTH + SOLVER_W_MIN + SPLITTER_HANDLE           # 806：展开态最小整窗宽
COLLAPSED_WIDTH = WINDOW_WIDTH                 # 500：折叠后整体隐藏右栏，窗口收窄到纯游戏宽度

# 折叠态右侧贴边半胶囊把手（EdgeHandle；父级为主窗口，不随 Solver 容器隐藏，作为 overlay 不参与布局）
EDGE_HANDLE_W = 22                             # 把手宽度（20–24 px）
EDGE_HANDLE_H = 40                             # 把手高度（38–44 px）
EDGE_HANDLE_RADIUS = 9                         # 左侧圆角（右侧直边，贴窗口右缘无缝隙）
EDGE_HANDLE_TOP = 150                          # 距内容区顶部锚点（避开分数卡/标题，落在右侧空白边距内）
EDGE_HANDLE_BG = "#F3EDE5"                     # 常态背景
EDGE_HANDLE_BORDER = "#CDBEAF"                 # 左/上/下边框（右侧不描边）
EDGE_HANDLE_BG_HOVER = "#E9DFD3"               # hover 背景
EDGE_HANDLE_BG_PRESSED = "#DCD0C2"             # pressed 背景
EDGE_HANDLE_ARROW = "#8A7662"                  # 箭头色（与标题栏收起箭头一致）
EDGE_HANDLE_ARROW_WIDTH = 1.6                  # 箭头线宽（与标题栏收起箭头一致）

PANEL_BG = "#F2E9DD"
PANEL_LINE = "#D8C9B9"
PANEL_RADIUS = 12
GROUP_BG = "#F7F0E7"
LOG_BG = "#FAF5EE"
LOG_LINE = "#E4D9C9"

# 折叠/展开 Chevron 箭头按钮（QSS 负责背景/边框，QPainter 负责细线箭头；
# 不再使用 Windows 系统绿色圆形方向图标）
COLLAPSE_BTN_SIZE = 26                          # 按钮尺寸 26×26 px
COLLAPSE_BTN_RADIUS = 6                         # 圆角 6 px
COLLAPSE_BTN_BG = "#F3EDE5"                     # 常态背景
COLLAPSE_BTN_BORDER = "#CDBEAF"                 # 常态边框
COLLAPSE_BTN_BG_HOVER = "#EAE1D6"               # hover 背景
COLLAPSE_BTN_BG_PRESSED = "#DED3C4"             # pressed 背景
COLLAPSE_BTN_BG_DISABLED = "#F6F1EA"            # disabled 背景
COLLAPSE_BTN_BORDER_DISABLED = "#E3DACF"        # disabled 边框
COLLAPSE_ARROW = "#8A7662"                      # 箭头常态色
COLLAPSE_ARROW_HOVER = "#6E5C4A"                # 箭头 hover 色
COLLAPSE_ARROW_PRESSED = "#584736"              # 箭头 pressed 色
COLLAPSE_ARROW_DISABLED = "#C3B4A4"             # 箭头 disabled 色
COLLAPSE_ARROW_WIDTH = 1.6                      # 箭头线宽（px）

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

# 参数表单：标签 + 控件（V5.1 由横排小框改为结构化表单）
FORM_LABEL_QSS = f"color:{v4.COLOR_TEXT}; font-size:12px;"

# 右栏内的分组卡片（浅米色圆角，复用 v5 既有卡片配色）
GROUP_QSS = (
    f"QFrame#solverGroup {{ background-color: {GROUP_BG};"
    f" border: 1px solid {PANEL_LINE}; border-radius: 7px; }}")

# 折叠 / 高级参数 小工具按钮
TOOL_BUTTON_QSS = f"""
QToolButton {{
    background-color: #EEE4DA; color: {v4.COLOR_TEXT};
    border: 1px solid {PANEL_LINE}; border-radius: 6px;
    font-size: 12px; padding: 2px 8px;
}}
QToolButton:hover {{ background-color: #E2D7CA; }}
QToolButton:checked {{ background-color: #E2D7CA; }}
"""

# 标题栏收起/展开 Chevron 图标按钮（无文字；语义由箭头方向 + 工具提示表达）
COLLAPSE_ICON_QSS = f"""
QToolButton#solverCollapseBtn {{
    background-color: {COLLAPSE_BTN_BG}; border: 1px solid {COLLAPSE_BTN_BORDER};
    border-radius: {COLLAPSE_BTN_RADIUS}px; padding: 0;
}}
QToolButton#solverCollapseBtn:hover {{ background-color: {COLLAPSE_BTN_BG_HOVER}; }}
QToolButton#solverCollapseBtn:pressed {{ background-color: {COLLAPSE_BTN_BG_PRESSED}; }}
QToolButton#solverCollapseBtn:disabled {{
    background-color: {COLLAPSE_BTN_BG_DISABLED}; border-color: {COLLAPSE_BTN_BORDER_DISABLED};
}}
"""

# 状态指标：标签（次要色）+ 数值（正文色）
METRIC_KEY_QSS = "color:#8f8175; font-size:11px;"
METRIC_VAL_QSS = f"color:{v4.COLOR_TEXT}; font-size:12px; font-weight:bold;"


# =====================================================================
# 自定义 Chevron 箭头按钮
# QSS 负责背景/边框（含 hover/pressed/disabled），QPainter 负责绘制细线箭头；
# 用于替代 Windows 系统绿色圆形方向图标。
# =====================================================================
class ChevronToolButton(QToolButton):
    """细线 Chevron 箭头按钮。

    direction="right"：展开态，表示把求解栏向右收起；
    direction="left"： 折叠态，表示把求解栏向左展开。
    箭头颜色按 hover / pressed / disabled 三态切换，配合 QSS 背景反馈。
    """

    def __init__(self, direction="right", parent=None):
        super().__init__(parent)
        self._direction = "right"
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(COLLAPSE_BTN_SIZE, COLLAPSE_BTN_SIZE)
        self.setDirection(direction)

    def setDirection(self, direction):
        self._direction = "left" if str(direction).lower() == "left" else "right"
        self.update()

    def direction(self):
        return self._direction

    def _arrow_color(self):
        if not self.isEnabled():
            return QColor(COLLAPSE_ARROW_DISABLED)
        if self.isDown():
            return QColor(COLLAPSE_ARROW_PRESSED)
        if self.underMouse():
            return QColor(COLLAPSE_ARROW_HOVER)
        return QColor(COLLAPSE_ARROW)

    def paintEvent(self, event):
        super().paintEvent(event)                    # 由 QSS 绘制背景与边框
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._arrow_color(), COLLAPSE_ARROW_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        hw, hh = 2.6, 4.8                            # Chevron 水平半宽 / 垂直半高
        if self._direction == "right":
            pts = ((cx - hw, cy - hh), (cx + hw, cy), (cx - hw, cy + hh))
        else:
            pts = ((cx + hw, cy - hh), (cx - hw, cy), (cx + hw, cy + hh))
        path = QPainterPath()
        path.moveTo(*pts[0])
        path.lineTo(*pts[1])
        path.lineTo(*pts[2])
        painter.drawPath(path)
        painter.end()


# =====================================================================
# 折叠态右侧贴边半胶囊把手（EdgeHandle）
# 自绘：单侧圆角（左侧两角圆角、右侧直边）+ 细线左向 Chevron；
# 作为 overlay 挂主窗口，不参与布局；QSS 无法可靠表达“单侧圆角”，故用 paintEvent。
# =====================================================================
class SolverEdgeHandle(QWidget):
    """折叠态右侧贴边半胶囊展开把手。

    点击或键盘（回车/空格）发射 clicked；hover / pressed / disabled / 焦点均有视觉反馈。
    箭头与标题栏收起按钮同色（#8A7662）、同粗细（1.6 px）、同为圆角笔帽细线。
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("solverEdgeHandle")
        self.setFixedSize(EDGE_HANDLE_W, EDGE_HANDLE_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("展开 AI 求解面板")
        self.setAccessibleName("展开 AI 求解面板")
        self._hover = False
        self._pressed = False

    # ---- 交互状态 ----
    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ---- 绘制 ----
    def _palette(self):
        if not self.isEnabled():
            return (QColor(COLLAPSE_BTN_BG_DISABLED), QColor(COLLAPSE_BTN_BORDER_DISABLED),
                    QColor(COLLAPSE_ARROW_DISABLED))
        if self._pressed:
            return (QColor(EDGE_HANDLE_BG_PRESSED), QColor(EDGE_HANDLE_BORDER),
                    QColor(EDGE_HANDLE_ARROW))
        if self._hover:
            return (QColor(EDGE_HANDLE_BG_HOVER), QColor(EDGE_HANDLE_BORDER),
                    QColor(EDGE_HANDLE_ARROW))
        return (QColor(EDGE_HANDLE_BG), QColor(EDGE_HANDLE_BORDER), QColor(EDGE_HANDLE_ARROW))

    def _geometry_pts(self):
        w = float(self.width())
        h = float(self.height())
        x0, y0 = 0.5, 0.5
        x1, y1 = w - 0.5, h - 0.5
        r = min(float(EDGE_HANDLE_RADIUS), (y1 - y0) / 2.0, (x1 - x0))
        return x0, y0, x1, y1, r

    def _body_path(self):
        """半胶囊轮廓：左上/左下圆角，右侧直边。"""
        x0, y0, x1, y1, r = self._geometry_pts()
        path = QPainterPath()
        path.moveTo(x1, y0)                                   # 右上
        path.lineTo(x0 + r, y0)                               # 上边（到圆角起点）
        path.arcTo(x0, y0, 2 * r, 2 * r, 90, 90)               # 左上圆角
        path.lineTo(x0, y1 - r)                               # 左边
        path.arcTo(x0, y1 - 2 * r, 2 * r, 2 * r, 180, 90)      # 左下圆角
        path.lineTo(x1, y1)                                   # 下边（到右直边）
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bg, border, arrow = self._palette()
        # 背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawPath(self._body_path())
        # 边框：仅左 / 上 / 下（右侧直边不描边，紧贴窗口右缘）
        x0, y0, x1, y1, r = self._geometry_pts()
        border_path = QPainterPath()
        border_path.moveTo(x1, y0)
        border_path.lineTo(x0 + r, y0)
        border_path.arcTo(x0, y0, 2 * r, 2 * r, 90, 90)
        border_path.lineTo(x0, y1 - r)
        border_path.arcTo(x0, y1 - 2 * r, 2 * r, 2 * r, 180, 90)
        border_path.lineTo(x1, y1)
        bpen = QPen(border, 1.0)
        bpen.setCapStyle(Qt.FlatCap)
        bpen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(bpen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(border_path)
        # 细线左向 Chevron（与标题栏箭头同色同粗细）
        apen = QPen(arrow, EDGE_HANDLE_ARROW_WIDTH)
        apen.setCapStyle(Qt.RoundCap)
        apen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(apen)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        hw, hh = 2.6, 4.8
        chevron = QPainterPath()
        chevron.moveTo(cx + hw, cy - hh)
        chevron.lineTo(cx - hw, cy)
        chevron.lineTo(cx + hw, cy + hh)
        painter.drawPath(chevron)
        # 键盘焦点反馈（不占用鼠标态视觉）
        if self.hasFocus():
            fpen = QPen(QColor(EDGE_HANDLE_ARROW), 1.0)
            fpen.setStyle(Qt.DashLine)
            painter.setPen(fpen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 4, 4)
        painter.end()


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
    """后台求解工作对象（H3：携带 job_id + 协作式取消）。

    - 求解前/后都检查取消令牌；已取消则**不返回任何结果**（协作式取消，绝不使用
      QThread.terminate()）；
    - 结果/失败信号都携带 job_id，供界面做“任务身份 + 棋盘快照”校验，丢弃过期结果。
    """
    solved = pyqtSignal(int, dict)
    failed = pyqtSignal(int, str)

    @pyqtSlot(int, list, dict, object)
    def solve(self, job_id, grid, config, cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            return
        try:
            result = solver.solve(grid, **config)
            if cancel_event is not None and cancel_event.is_set():
                return                                        # 求解期间被取消：丢弃结果
            self.solved.emit(job_id, result)
        except Exception as exc:                              # noqa: BLE001
            if cancel_event is None or not cancel_event.is_set():
                self.failed.emit(job_id, "%s: %s" % (type(exc).__name__, exc))


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
    # (job_id, grid 快照, config, 取消令牌)
    solveRequested = pyqtSignal(int, list, dict, object)

    def __init__(self):
        super().__init__()

    # ---------------- 覆盖：构建游戏页（追加 AI 入口按钮） ----------------
    def _build_game_page(self):
        page = super()._build_game_page()
        row = self._find_row_layout(page.layout(), self.new_game_button)
        if row is not None:
            self.solver_ai_button = self._make_button(
                "AI 求解", self._open_solver_panel,
                qss=v4.SECONDARY_BUTTON_QSS, size=(78, 44),
                particle_color="#cbbcaa")
            self.solver_ai_button.setToolTip(
                "打开右侧「AI 求解」面板；算法运行请在面板内点击「开始求解」")
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

    # ---------------- 覆盖：界面初始化（复用 v4 后扩展为左右双栏） ----------------
    def init_ui(self):
        super().init_ui()

        # v5 使用自己的存档目录与版本标记（跨版本隔离），并重绑单实例锁
        self.model.set_history_dir(
            _store.resolve_history_dir(os.path.join(_HERE, "game_history"), "v5"), "v5")

        self._init_solver()
        self._restructure_two_columns()
        # 启动页尺寸与第 4 版完全一致；进入游戏页时再切换为双栏可调整尺寸
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.refresh()

    # =================================================================
    # V5.1：左 GamePanel + 右 Solver Workbench（水平 QSplitter）
    # =================================================================
    def _restructure_two_columns(self):
        """把 v4 的游戏页整体作为左栏，右侧放入求解工作台，用水平 QSplitter 承载。

        - 左栏仍是 v4 原页面对象（不重建棋盘/控件，避免状态不同步）；
        - 旧“底部求解区”不再存在（UI-01）：求解面板只出现在右栏。
        """
        game_page = self.stack.widget(v4.GAME_PAGE)
        self.game_page = game_page
        self.stack.removeWidget(game_page)              # 从堆叠页取出（对象保留，未销毁）

        container = QWidget()
        container.setObjectName("v5Root")
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("mainSplitter")
        self.splitter.setHandleWidth(SPLITTER_HANDLE)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter)

        # 左栏内容固定为第 4 版宽度并左对齐：窗口变宽时留白落在 holder 内，
        # 而不是把棋盘/按钮拉伸到窗口两端（修复 G04/G10 的按钮散开）。
        game_page.setFixedWidth(WINDOW_WIDTH)
        game_page.show()                                # removeWidget() 会隐式 hide()，重新标记为可见
        holder = QWidget()
        holder.setObjectName("gameHolder")
        hbox = QHBoxLayout(holder)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addWidget(game_page)                       # 宽度固定 500、高度填满
        hbox.addStretch(1)                              # 多余宽度在此吸收（自然留白）
        self.game_holder = holder
        self.splitter.addWidget(holder)

        self._solver_collapsed = False
        self._solver_saved_sizes = None
        self._expanded_geometry = None                  # 折叠前备份的整窗几何
        self._solver_transition = False                 # 折叠/展开防重入
        self._build_solver_panel()                      # 构建右栏（展开体 + 折叠窄条）
        self.splitter.addWidget(self.solver_container)

        self.splitter.setStretchFactor(0, 0)            # 展开：新增空间主要给右栏
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([WINDOW_WIDTH, SOLVER_W_DEFAULT])

        self.stack.insertWidget(v4.GAME_PAGE, container)  # 保持在 GAME_PAGE(=1) 索引
        self._root_container = container
        self._build_solver_edge_handle()                # 右侧贴边把手（父级=主窗口 overlay）

    # ---------------- 右侧贴边半胶囊把手（折叠态专用入口） ----------------
    def _build_solver_edge_handle(self):
        """在主窗口右侧边缘创建独立贴边把手（overlay）。

        父级为主窗口 self（与粒子层同层），**不随 solver_container 隐藏**，也不加入任何布局，
        因此不参与主布局宽度分配；由稳定定位逻辑贴宿主内容右缘、对齐内容区顶部锚点。
        """
        handle = SolverEdgeHandle(self)
        handle.clicked.connect(self._open_solver_panel)  # 与左侧 AI 按钮共用同一展开逻辑
        handle.hide()                                     # 仅折叠态显示
        self.solver_edge_handle = handle
        self._position_solver_edge_handle()

    def _position_solver_edge_handle(self):
        """把手贴宿主内容右缘、对齐内容区顶部锚点；随 resize/DPI 变化重新定位。"""
        handle = getattr(self, "solver_edge_handle", None)
        if handle is None:
            return
        x = max(0, self.width() - EDGE_HANDLE_W)         # 紧贴右缘，不留悬空缝隙
        handle.move(x, EDGE_HANDLE_TOP)

    def _show_solver_edge_handle(self):
        handle = getattr(self, "solver_edge_handle", None)
        if handle is None:
            return
        self._position_solver_edge_handle()
        handle.show()
        handle.raise_()

    def _grow_for_solver(self):
        """进入游戏页：切换为左右双栏的可调整窗口尺寸（高度自适应屏幕）。"""
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

        # 任务身份（H3）：每次「开始求解」自增；用于丢弃过期 worker 结果
        self._job_id = 0
        self._board_sig = None            # 发起求解时的棋盘快照签名
        self._solver_cancel = None        # 当前任务的协作式取消令牌（threading.Event）

        # 窗口位置跟踪：仅在用户未手动拖动时自动居中 / 校正越界
        self._shown_once = False
        self._user_moved = False
        self._programmatic_move = False

        # 工作线程按需创建：只有真正求解时才启动，空闲/截图/退出时不存在运行中的线程
        self._solver_thread = None
        self._solver_worker = None
        self._retired_threads = []        # 未能在预算内退出、待 finished 后回收的线程

    @staticmethod
    def _board_signature(grid):
        """棋盘快照签名（用于校验结果对应的棋盘状态）。"""
        return tuple(tuple(int(v) for v in row) for row in grid)

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

    def _shutdown_worker(self, wait_ms=3000):
        """协作式停止并回收求解线程（幂等）。

        H3 修复：先置取消令牌 → 断开请求 → quit()+wait()。
        若线程未在预算内退出，**不丢弃引用**，转入退休列表，待 finished 信号到达后回收，
        避免“worker 仍在运行却把引用置空”导致线程失控或对象被提前销毁。
        绝不使用 QThread.terminate()。
        """
        thread = self._solver_thread
        worker = self._solver_worker
        if thread is None:
            return True
        if self._solver_cancel is not None:
            self._solver_cancel.set()                        # 协作式取消：worker 主动放弃结果
        try:
            self.solveRequested.disconnect(worker.solve)
        except (TypeError, RuntimeError):
            pass
        exited = True
        try:
            thread.quit()
            exited = bool(thread.wait(wait_ms))
        except RuntimeError:
            exited = True
        if not exited:
            self._retire_thread(thread, worker)              # 保留引用 + 完成通知后回收
        self._solver_thread = None
        self._solver_worker = None
        self._solver_cancel = None
        return exited

    def _retire_thread(self, thread, worker):
        """把未及时退出的线程暂存，等其 finished 后回收（不丢弃引用）。"""
        self._retired_threads.append((thread, worker))
        thread.finished.connect(lambda: self._collect_retired(thread))

    def _collect_retired(self, thread):
        self._retired_threads = [(t, w) for (t, w) in self._retired_threads if t is not thread]

    # ---------------- 右侧 Solver 工作台（V5.1） ----------------
    def _build_solver_panel(self):
        """构建右侧求解工作台：头部 / 参数 / 运行 / 状态 / 高级 / 日志 / 结果。

        - 结构对应 V5.1 规范 2.3；日志分配主 stretch，窗口变高时由日志吸收空间；
        - 右栏整体不套嵌套滚动区（规范 5.5），避免拖动/缩放时重建控件。
        """
        # 外层容器：折叠时整体隐藏该容器（见 _do_collapse），不保留任何窄条
        container = QWidget()
        self.solver_container = container
        cbox = QVBoxLayout(container)
        cbox.setContentsMargins(CONTAINER_MARGIN, CONTAINER_MARGIN,
                                CONTAINER_MARGIN, CONTAINER_MARGIN)
        cbox.setSpacing(0)

        panel = QWidget()
        panel.setObjectName("solverPanel")
        panel.setStyleSheet(
            f"#solverPanel {{ background-color: {PANEL_BG};"
            f" border: 1px solid {PANEL_LINE}; border-radius: {PANEL_RADIUS}px; }}")
        cbox.addWidget(panel)
        self.solver_panel = panel

        box = QVBoxLayout(panel)
        box.setContentsMargins(12, 10, 12, 12)
        box.setSpacing(8)

        # A. 头部：[收起/展开 Chevron 按钮] + 标题 —— 两者左对齐、间距固定，不分散到两端
        head = QHBoxLayout()
        head.setSpacing(8)
        self.solver_collapse_btn = ChevronToolButton("right")
        self.solver_collapse_btn.setObjectName("solverCollapseBtn")
        self.solver_collapse_btn.setStyleSheet(COLLAPSE_ICON_QSS)
        self.solver_collapse_btn.clicked.connect(self._toggle_solver)
        title = QLabel("AI 求解")
        title.setStyleSheet(f"color:{v4.COLOR_TEXT}; font-size:14px; font-weight:bold;")
        self.solver_title = title
        head.addWidget(self.solver_collapse_btn, 0, Qt.AlignVCenter)
        head.addWidget(title, 0, Qt.AlignVCenter)
        head.addStretch()                                          # 末尾留白
        box.addLayout(head)

        # B. 参数区：标签 + 控件的结构化表单（复用原有下拉框对象与回调）
        form_group = self._make_solver_group()
        form = QGridLayout(form_group)
        form.setContentsMargins(10, 8, 10, 8)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self.solver_strategy = self._make_combo(
            [(solver.STRATEGIES[k], k) for k in solver.STRATEGY_ORDER])
        self.solver_depth = self._make_combo(
            [(solver.PRESET_LABELS[k], k) for k in solver.PRESET_ORDER])
        self.solver_depth.setCurrentIndex(1)
        self.solver_mode = self._make_combo([("自动连走", "auto"), ("单步建议", "single")])
        self.solver_strategy.setCurrentIndex(solver.STRATEGY_ORDER.index("expectimax"))  # 默认 Expectimax
        self.solver_strategy.currentIndexChanged.connect(self._on_strategy_changed)

        for row, (text, wdg) in enumerate((("算法", self.solver_strategy),
                                           ("运行方式", self.solver_depth),
                                           ("模式", self.solver_mode))):
            lab = QLabel(text)
            lab.setStyleSheet(FORM_LABEL_QSS)
            lab.setFixedWidth(58)
            form.addWidget(lab, row, 0, Qt.AlignVCenter)
            form.addWidget(wdg, row, 1)
        form.setColumnStretch(1, 1)
        box.addWidget(form_group)

        # C. 运行区：求解控制（主动作按钮 + 忙态进度），与结果操作分区（UI-05）
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.solver_start_btn = QPushButton("开始求解")
        self.solver_start_btn.setStyleSheet(PANEL_PRIMARY_QSS)
        self.solver_start_btn.setFixedHeight(32)
        self.solver_start_btn.setCursor(Qt.PointingHandCursor)
        self.solver_start_btn.clicked.connect(self.on_solver_clicked)
        self.solver_progress = QProgressBar()
        self.solver_progress.setFixedHeight(8)
        self.solver_progress.setTextVisible(False)
        self.solver_progress.setStyleSheet(PROGRESS_QSS)
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
        ctrl.addWidget(self.solver_start_btn, 1)
        ctrl.addWidget(self.solver_progress, 1)
        box.addLayout(ctrl)

        # D. 状态区：标题行 + 2 列明细指标（值与真实业务对象一致）
        status_group = self._make_solver_group()
        sbox = QVBoxLayout(status_group)
        sbox.setContentsMargins(10, 8, 10, 8)
        sbox.setSpacing(6)
        self.solver_status = QLabel()
        self.solver_status.setWordWrap(True)
        self.solver_status.setStyleSheet(f"color:{v4.COLOR_TEXT}; font-size:12px;")
        sbox.addWidget(self.solver_status)
        self.solver_metrics = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        metric_defs = (("steps", "步数"), ("action", "当前动作"), ("eval", "评估值"),
                       ("score", "当前分数"), ("max_tile", "最大瓦片"), ("elapsed", "累计耗时"))
        for idx, (key, text) in enumerate(metric_defs):
            r, c = divmod(idx, 2)
            k = QLabel(text)
            k.setStyleSheet(METRIC_KEY_QSS)
            v = QLabel("—")
            v.setStyleSheet(METRIC_VAL_QSS)
            self.solver_metrics[key] = v
            grid.addWidget(k, r, c * 2)
            grid.addWidget(v, r, c * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        sbox.addLayout(grid)
        box.addWidget(status_group)

        # G. 高级参数：可折叠容器；仅展示当前真实生效的配置，不放置伪控件
        self.solver_advanced_toggle = QToolButton()
        self.solver_advanced_toggle.setStyleSheet(TOOL_BUTTON_QSS)
        self.solver_advanced_toggle.setText("高级参数 ▸")
        self.solver_advanced_toggle.setCheckable(True)
        self.solver_advanced_toggle.setCursor(Qt.PointingHandCursor)
        self.solver_advanced_toggle.toggled.connect(self._on_advanced_toggled)
        box.addWidget(self.solver_advanced_toggle, 0, Qt.AlignLeft)

        self.solver_advanced_body = QWidget()
        abox = QVBoxLayout(self.solver_advanced_body)
        abox.setContentsMargins(2, 0, 2, 0)
        abox.setSpacing(2)
        self.solver_advanced_text = QLabel()
        self.solver_advanced_text.setWordWrap(True)
        self.solver_advanced_text.setStyleSheet("color:#8f8175; font-size:11px;")
        abox.addWidget(self.solver_advanced_text)
        self.solver_advanced_body.setVisible(False)
        box.addWidget(self.solver_advanced_body)

        # E. 日志区：主 stretch（窗口变高时由日志吸收）
        self.solver_log = QListWidget()
        self.solver_log.setStyleSheet(LOG_QSS)
        self.solver_log.setFocusPolicy(Qt.NoFocus)
        box.addWidget(self.solver_log, 1)

        # F. 结果区：导出结果 / 查看详情 / 性能对比（复用真实动作与业务参数）
        result = QHBoxLayout()
        result.setSpacing(8)
        self.solver_export_btn = QPushButton("导出结果")
        self.solver_view_btn = QPushButton("查看详情")
        self.solver_compare_btn = QPushButton("性能对比")
        for btn, slot in ((self.solver_export_btn, self.on_solver_export),
                          (self.solver_view_btn, self.on_solver_view),
                          (self.solver_compare_btn, self.on_solver_compare)):
            btn.setStyleSheet(PANEL_BUTTON_QSS)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            result.addWidget(btn)
        box.addLayout(result)

        # 折叠态不保留右侧窄条：整体隐藏 solver_container 即可（见 _do_collapse）；
        # 重新展开的入口为右上角悬浮 Chevron 按钮与左侧「AI 求解」按钮（见 _open_solver_panel）。

        self._on_strategy_changed()          # 同步“强度”可用状态 + 高级配置文本
        self._update_collapse_button()
        self._render_idle_status()

    @staticmethod
    def _make_solver_group():
        """右栏内的浅米色圆角分组卡片。"""
        frame = QFrame()
        frame.setObjectName("solverGroup")
        frame.setStyleSheet(GROUP_QSS)
        return frame

    def _on_advanced_toggled(self, checked):
        self.solver_advanced_body.setVisible(bool(checked))
        self.solver_advanced_toggle.setText("高级参数 ▾" if checked else "高级参数 ▸")

    def _update_collapse_button(self):
        """同步面板标题栏 Chevron 按钮：该按钮仅存在于展开态，动作为“向右收起 AI 求解面板”。"""
        btn = getattr(self, "solver_collapse_btn", None)
        if btn is None:
            return
        btn.setDirection("right")
        btn.setToolTip("收起 AI 求解面板")
        if hasattr(btn, "setAccessibleName"):
            btn.setAccessibleName("收起 AI 求解面板")

    # ---------------- 自适应尺寸：窗口始终完整落在屏幕内 ----------------
    def _available_height(self):
        """当前屏幕可用高度（Qt 逻辑像素）；取不到时退回期望整窗高度。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return V5_DEFAULT_H + TITLEBAR_RESERVE
        return screen.availableGeometry().height()

    def _min_width(self):
        """整窗最小宽度：左栏保持第 4 版宽度 + 右栏（展开/折叠）最小宽度 + 分隔条。"""
        if self._solver_collapsed:
            return COLLAPSED_WIDTH                        # 折叠：整体隐藏右栏，仅左栏宽度
        return V5_MIN_WIDTH

    def _apply_splitter_sizes(self):
        """按折叠状态与当前窗口宽度重排左右比例。

        只调整分隔器 sizes，不改变窗口尺寸，避免 splitterMoved / resize 互相触发。
        """
        if not hasattr(self, "splitter"):
            return
        total = self.width()                              # 折叠后窗口会变窄，不能用固定下限
        if self._solver_collapsed:
            # 右栏容器已隐藏：全部宽度归左栏，不留任何残留
            self.splitter.setSizes([max(WINDOW_WIDTH, total), 0])
            return
        saved = self._solver_saved_sizes
        right = max(SOLVER_W_MIN, saved[1] if saved else SOLVER_W_DEFAULT)
        right = min(right, max(0, total - WINDOW_WIDTH - SPLITTER_HANDLE))
        left = max(WINDOW_WIDTH, total - right - SPLITTER_HANDLE)
        self.splitter.setSizes([left, right])

    def _apply_solver_size(self):
        """进入游戏页：切换为可调整尺寸的左右双栏，高度自适应屏幕。

        位置：未被用户手动拖动过时自动居中；否则只做越界校正，不打扰用户摆放。
        """
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)          # 解除启动页的固定尺寸
        avail = self._available_height()
        height = int(max(V5_MIN_H, min(V5_DEFAULT_H, avail - TITLEBAR_RESERVE)))
        self.setMinimumSize(self._min_width(), V5_MIN_H)  # 缩放不裁断关键按钮/棋盘
        self.resize(V5_DEFAULT_WIDTH, height)
        self._apply_splitter_sizes()
        if not self._user_moved:
            self._center_on_screen()
        self._keep_on_screen()

    # ---------------- 折叠 / 展开（UI-07、交互细则 3） ----------------
    def _toggle_solver(self):
        self._set_solver_collapsed(not self._solver_collapsed)

    def _is_normal_window(self):
        """普通（非最大化/非全屏）窗口才允许程序化调整几何。"""
        return not (self.isMaximized() or self.isFullScreen())

    def _clamp_to_screen(self, geom):
        """把几何夹到当前显示器可用区域，避免展开时窗口跑出屏幕。"""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return geom
        av = screen.availableGeometry()
        w = min(geom.width(), av.width())
        h = min(geom.height(), av.height())
        x = min(max(geom.x(), av.left()), av.right() - w + 1)
        y = min(max(geom.y(), av.top()), av.bottom() - h + 1)
        return QRect(x, y, w, h)

    def _set_splitter_handles_enabled(self, enabled):
        """启用/禁用分隔条拖动（折叠态禁用，避免把窄条拖成大块空白）。"""
        for i in range(self.splitter.count()):
            handle = self.splitter.handle(i)
            if handle is not None:
                handle.setEnabled(enabled)

    def _set_solver_collapsed(self, collapsed):
        """折叠/展开右栏：不停止 worker、不清空日志与算法状态（防重入）。"""
        collapsed = bool(collapsed)
        if self._solver_transition or collapsed == self._solver_collapsed:
            return
        self._solver_transition = True
        try:
            if collapsed:
                self._do_collapse()
            else:
                self._do_expand()
        finally:
            self._solver_transition = False

    def _do_collapse(self):
        # 1) 仅在“有效展开且为普通窗口”时备份几何与右栏宽度，避免用折叠态覆盖备份
        if self._is_normal_window():
            self._expanded_geometry = self.geometry()
        sizes = self.splitter.sizes()
        if sizes and sizes[1] >= SOLVER_W_MIN:
            self._solver_saved_sizes = sizes
        # 2) 完整隐藏右侧 Solver 容器：求解控件/背景/边框/窄条与分隔条一并消失
        self._solver_collapsed = True
        self.solver_container.hide()
        self._set_splitter_handles_enabled(False)
        # 3) 多余宽度全部归左栏 holder（留白在 holder 内，按钮不散开）
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.setMinimumSize(self._min_width(), V5_MIN_H)
        # 4) 普通窗口同步收窄到纯游戏尺寸（无右侧空白或窄条）
        if self._is_normal_window() and self.width() > COLLAPSED_WIDTH:
            self.resize(COLLAPSED_WIDTH, self.height())
        self._apply_splitter_sizes()
        self._update_collapse_button()
        self._update_solver_buttons()                       # AI 按钮作为“重新打开面板”入口
        self._show_solver_edge_handle()                     # 显示右侧贴边把手
        QTimer.singleShot(0, self._apply_splitter_sizes)   # 排队等待布局落定（非轮询）

    def _do_expand(self):
        # 1) 先隐藏贴边把手，再恢复完整右栏与几何（注意 Qt 布局事件顺序）
        self._solver_collapsed = False
        handle = getattr(self, "solver_edge_handle", None)
        if handle is not None:
            handle.hide()                                   # 展开态隐藏把手
        self.solver_container.show()
        self._set_splitter_handles_enabled(True)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.setMinimumSize(V5_MIN_WIDTH, V5_MIN_H)
        # 2) 恢复折叠前的整窗几何（夹到屏幕内）
        if self._expanded_geometry is not None and self._is_normal_window():
            self.setGeometry(self._clamp_to_screen(self._expanded_geometry))
        # 3) 恢复右栏宽度与业务状态（控件实例未销毁，配置/参数/日志自动保留）
        self._apply_splitter_sizes()
        self._update_collapse_button()
        self._update_solver_buttons()
        self._render_metrics()
        QTimer.singleShot(0, self._apply_splitter_sizes)

    # ---------------- 窗口事件：贴边把手随尺寸变化重新贴边 ----------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_solver_edge_handle()

    # ---------------- 状态指标（UI-04 / T-11） ----------------
    def _set_metric(self, key, value):
        lbl = self.solver_metrics.get(key)
        if lbl is not None:
            lbl.setText("—" if value is None else str(value))

    def _render_metrics(self):
        """状态指标与真实业务对象（session / model）一致，不造假。"""
        if not getattr(self, "solver_metrics", None):
            return
        steps = self._session.get("steps", []) if self._session is not None else []
        last = steps[-1] if steps else None
        self._set_metric("steps", len(steps))
        self._set_metric("action", last.get("name", "—") if last else "—")
        if last is not None:
            ev = last.get("eval")
            self._set_metric("eval", "—" if ev is None else "%.1f" % ev)
        else:
            self._set_metric("eval", "—")
        self._set_metric("score", self.model.score)
        self._set_metric("max_tile",
                         max(max(r) for r in self.model.grid) if self.model.grid else 0)
        if self._session is not None:
            self._set_metric("elapsed",
                             "%.1fs" % (self._session.get("elapsed_ms", 0.0) / 1000.0))
        else:
            self._set_metric("elapsed", "—")

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

    def _make_combo(self, items, width=None):
        combo = QComboBox()
        if width:
            combo.setFixedSize(width, 26)
        else:                                # 表单内下拉框：水平填满、高度固定
            combo.setFixedHeight(26)
            combo.setMinimumWidth(90)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setStyleSheet(COMBO_QSS)
        combo.setCursor(Qt.PointingHandCursor)
        for text, data in items:
            combo.addItem(text, data)
        return combo

    def _on_strategy_changed(self):
        # 仅部分策略有“强度”参数（贪心模拟 / Expectimax / MCTS），其余置灰
        self.solver_depth.setEnabled(solver.has_presets(self.solver_strategy.currentData()))
        self._refresh_advanced_text()

    def _refresh_advanced_text(self):
        """高级参数区只展示“当前真实生效的配置”，不显示伪控件/伪指标。"""
        lbl = getattr(self, "solver_advanced_text", None)
        if lbl is None:
            return
        strategy = self.solver_strategy.currentData()
        preset = self.solver_depth.currentData()
        try:
            cfg = solver.build_config(strategy, preset)
            desc = solver.describe_config(cfg)
        except Exception:                                     # noqa: BLE001
            desc = "—"
        lbl.setText(
            "当前生效配置：%s\n"
            "（此区为可折叠预留位；仅在使用到真实可调参数时才会展示对应控件）" % desc)

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
        self._render_metrics()

    def _render_running_status(self, computing=False):
        if self._session is None:
            self._render_metrics()
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
        self._render_metrics()

    def _log_step(self, text):
        # 仅在原本处于底部时自动跟随；用户上滚查看历史时不强制抢回底部
        sb = self.solver_log.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 2
        item = QListWidgetItem(text)
        item.setForeground(QColor(v4.COLOR_TEXT))
        self.solver_log.addItem(item)
        if at_bottom:
            self.solver_log.scrollToBottom()

    # ---------------- 入口：AI 求解按钮 / 悬浮展开按钮 / 面板开始按钮 ----------------
    def _open_solver_panel(self):
        """统一的“展开（打开）AI 求解面板”逻辑：右侧悬浮按钮与左侧 AI 按钮共用，不启动算法。

        面板已展开时为无操作（幂等）；不重建控件、不重复连接信号。
        """
        self._set_solver_collapsed(False)

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
        self._job_id += 1                     # 新任务身份：旧任务的在途结果将被丢弃
        self._solver_cancel = threading.Event()
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
        if self._solver_cancel is None or self._solver_cancel.is_set():
            self._solver_cancel = threading.Event()
        self._board_sig = self._board_signature(grid)       # 记录本任务对应的棋盘快照
        self._solve_in_flight = True
        self.solver_progress.setRange(0, 0)          # 忙态（不确定进度）动画
        self._render_running_status(computing=True)
        self.solveRequested.emit(self._job_id, grid, dict(self._solver_config),
                                 self._solver_cancel)

    # ---------------- 接收求解结果 ----------------
    def _on_solver_result(self, job_id, result):
        # H3：**先**校验任务在运行、结果属于当前任务、棋盘快照未变，再进行任何状态改写。
        # 过期结果不得在被判定之前清零新任务的 _solve_in_flight / 进度条（否则幽灵状态）。
        if not self._solver_running:
            return
        if job_id != self._job_id:
            self._log_step("已忽略过期求解结果（job_id=%s ≠ %s）。" % (job_id, self._job_id))
            return
        if self._board_sig is not None and \
                self._board_signature(self.model.grid) != self._board_sig:
            self._log_step("已忽略过期求解结果（棋盘在求解期间已变化）。")
            return

        # 校验通过：本结果确属当前任务，收尾在途标志与进度条
        self._solve_in_flight = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)

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

    def _on_solver_failed(self, job_id, message):
        # H3：先校验身份，过期/已停止的结果不得改写当前状态
        if not self._solver_running or job_id != self._job_id:
            return
        self._solve_in_flight = False
        self.solver_progress.setRange(0, 100)
        self.solver_progress.setValue(0)
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
        self._render_metrics()
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
        self._render_metrics()
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
        """仅「开始求解」随运行状态切换文案；左侧「AI 求解」恒为打开面板入口，不参与启停。"""
        running = self._solver_running
        self.solver_start_btn.setText("停止" if running else "开始求解")
        ai = getattr(self, "solver_ai_button", None)
        if ai is not None:
            ai.setText("AI 求解")

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
