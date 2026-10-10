#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048：平滑移动 / 合并动画与性能优化

配套博客《第 4 篇：PyQt5 2048 动画与性能优化》。

分层：
    Model       -> 复用第 3 篇的 GameCore（棋盘 / 合并 / 存档 / 撤销重做一行未改），
                   仅由 AnimatedGameCore 子类补充"每块从哪来、到哪去"的过渡信息；
    View        -> BoardView 用 QPainter 自绘：静态背景层（缓存为 QPixmap）
                   + 动画层（QTimer 逐帧插值）；
    Controller  -> MainWindow 处理键盘/按钮，触发动画，并在动画结束后再做胜负提示。
"""

import sys
import os
import math
import random

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                             QMessageBox, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame)
from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap

# =====================================================================
# 复用第 3 篇的 Model（GameCore）：动画版不改动任何棋盘逻辑
# =====================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_V3_DIR = os.path.join(os.path.dirname(_HERE), "pyqt_2048")
if _V3_DIR not in sys.path:
    sys.path.insert(0, _V3_DIR)
from pyqt_2048_with_history import GameCore  # noqa: E402


# =====================================================================
# 视觉规范常量（与第 3 篇保持一致，两个版本看起来是同一个游戏）
# =====================================================================
COLOR_BG = "#faf8ef"
COLOR_TEXT = "#776e65"
COLOR_SUBTITLE = "#8f8175"
COLOR_BOARD = "#bbada0"
COLOR_EMPTY = "#cdc1b4"
COLOR_CARD_LABEL = "#f5efe6"
COLOR_CARD_VALUE = "#ffffff"

TILE_SIZE = 96
TILE_GAP = 10
BOARD_PADDING = 10
TILE_RADIUS = 6
BOARD_RADIUS = 9
BOARD_SIDE = BOARD_PADDING * 2 + TILE_SIZE * 4 + TILE_GAP * 3   # 434

WINDOW_WIDTH, WINDOW_HEIGHT = 500, 672
GAME_MARGIN_X = (WINDOW_WIDTH - BOARD_SIDE) // 2
BUTTON_WIDTH, BUTTON_HEIGHT = 100, 44
CARD_WIDTH, CARD_HEIGHT = 330, 110

# 动画时长（秒）：滑行 / 合并与新生放大
MOVE_DURATION = 0.12
POP_DURATION = 0.14
FRAME_INTERVAL = 16          # 定时器步长（ms），约 60 FPS

TEXT_DARK = "#776e65"
TEXT_LIGHT = "#f9f6f2"
TILE_COLORS = {
    2: (238, 228, 218), 4: (237, 224, 200),
    8: (242, 177, 121), 16: (245, 149, 99),
    32: (246, 124, 95), 64: (246, 94, 59),
    128: (237, 207, 114), 256: (237, 204, 97),
    512: (237, 200, 80), 1024: (237, 197, 63),
    2048: (237, 194, 46),
}
HIGH_COLORS = {4096: (237, 176, 32), 8192: (227, 159, 22), 16384: (214, 143, 15)}

# 按钮样式：主按钮 / 次按钮 / 文字按钮（与第 3 篇一致）
PRIMARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #8f7a66; color: #f9f6f2;
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #9f8b78; }}
QPushButton:pressed  {{ background-color: #7c6a58; }}
QPushButton:focus    {{ border-color: #f9f6f2; }}
QPushButton:disabled {{ background-color: #cdc2b6; color: #f2ece5; }}
"""

SECONDARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #eee4da; color: {COLOR_TEXT};
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #e2d7ca; }}
QPushButton:pressed  {{ background-color: #d5c9ba; }}
QPushButton:focus    {{ border-color: #8f7a66; }}
QPushButton:disabled {{ background-color: #e8e0d7; color: #a99a8d; border-color: #ddd1c4; }}
"""

TEXT_BUTTON_QSS = f"""
QPushButton {{
    background-color: transparent; color: {COLOR_TEXT};
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #efe7db; color: #6a5b4e; }}
QPushButton:pressed  {{ background-color: #e4dacd; color: #5e5245; }}
QPushButton:focus    {{ background-color: #efe7db; border-color: #8f7a66; }}
QPushButton:disabled {{ color: #c3b8ad; }}
"""

START_PAGE = 0
GAME_PAGE = 1


# =====================================================================
# 缓动函数：让插值不机械
# =====================================================================
def ease_out_cubic(t):
    """减速滑行：起步快、收尾稳"""
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.70158):
    """带轻微回弹的放大：用于合并 / 新生方块的出现"""
    t -= 1.0
    return 1 + (s + 1) * t ** 3 + s * t * t


# =====================================================================
# Model 层：在第 3 篇 GameCore 上补充“过渡信息”（从哪来、到哪去）
# =====================================================================
class AnimatedGameCore(GameCore):
    """
    与第 3 篇完全相同的合并规则、存档与撤销/重做；
    额外记录一次移动中每个方块的“起点 -> 终点”，供 View 播放动画。
    """

    def __init__(self, grid_size=4):
        super().__init__(grid_size)
        # 第 4 篇使用自己的存档目录，避免与第 3 篇的对局混在一起
        self.history_dir = os.path.join(_HERE, "game_history")
        os.makedirs(self.history_dir, exist_ok=True)
        self.best_score = 0
        self.load_best_score()

        self.last_transitions = []   # [(src(r,c), dst(r,c), 滑动时显示的数值, 是否合并)]
        self.last_spawn = None       # 本次随机新方块的坐标

    # ---- 记录新生方块位置 ----
    def add_new_tile(self):
        empty = [(i, j) for i in range(self.grid_size)
                 for j in range(self.grid_size) if self.grid[i][j] == 0]
        if not empty:
            self.last_spawn = None
            return False
        i, j = random.choice(empty)
        self.grid[i][j] = 2 if random.random() < 0.9 else 4
        self.last_spawn = (i, j)
        return True

    # ---- 逐行合并，同时输出每一块的去向 ----
    def _merge_line_tracked(self, line):
        """
        返回 (新行, ops)。
        ops: [(源下标, 目标下标, 该块当前显示的数值, 是否合并)]
        合并时两块携带各自的原值一起滑向同一格，落定后再显示合并结果。
        """
        size = len(line)
        items = [(v, p) for p, v in enumerate(line) if v != 0]   # (数值, 源下标)

        result = []            # (最终值, [源下标...], 是否合并, 滑动时显示的数值)
        i = 0
        while i < len(items):
            if i + 1 < len(items) and items[i][0] == items[i + 1][0]:
                v = items[i][0]
                self.score += v * 2
                result.append((v * 2, [items[i][1], items[i + 1][1]], True, v))
                i += 2
            else:
                result.append((items[i][0], [items[i][1]], False, items[i][0]))
                i += 1

        new_line = [r[0] for r in result] + [0] * (size - len(result))
        ops = []
        for dst_p, (_final, srcs, merged, tile_v) in enumerate(result):
            for sp in srcs:
                ops.append((sp, dst_p, tile_v, merged))
        return new_line, ops

    # ---- 覆盖 _slide：复用方向抽象，但额外记录过渡 ----
    def _slide(self, direction):
        size = self.grid_size
        self.last_transitions = []
        moved = False

        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]

        for i in range(size):
            original = self.grid[i]
            row = original[::-1] if direction in ('right', 'down') else original
            new_row, ops = self._merge_line_tracked(row)
            if direction in ('right', 'down'):
                new_row = new_row[::-1]
            if new_row != original:          # 与原行（而非翻转后的行）比较
                moved = True
            self.grid[i] = new_row

            for src_p, dst_p, value, merged in ops:
                # 行内下标 -> 棋盘坐标（注意翻转与转置）
                if direction in ('right', 'down'):
                    src_p, dst_p = size - 1 - src_p, size - 1 - dst_p
                if direction in ('up', 'down'):
                    src, dst = (src_p, i), (dst_p, i)
                else:
                    src, dst = (i, src_p), (i, dst_p)
                self.last_transitions.append((src, dst, value, merged))

        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]
        return moved


# =====================================================================
# View 层：静态背景层（缓存）+ 动画层（逐帧插值）
# =====================================================================
class BoardView(QWidget):
    """自绘棋盘：背景只画一次缓存成 pixmap，方块每帧按进度重画"""

    animationFinished = pyqtSignal()

    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.setFixedSize(BOARD_SIDE, BOARD_SIDE)
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.anim = None
        self._background = self._build_background()

        self.timer = QTimer(self)
        self.timer.setInterval(FRAME_INTERVAL)
        self.timer.timeout.connect(self._tick)

    # ---------------- 几何 ----------------
    def _cell_xy(self, r, c):
        return (BOARD_PADDING + c * (TILE_SIZE + TILE_GAP),
                BOARD_PADDING + r * (TILE_SIZE + TILE_GAP))

    def _cell_rect(self, r, c):
        x, y = self._cell_xy(r, c)
        return QRectF(x, y, TILE_SIZE, TILE_SIZE)

    # ---------------- 静态背景层：只构建一次 ----------------
    def _build_background(self):
        pm = QPixmap(BOARD_SIDE, BOARD_SIDE)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLOR_BOARD))
        p.drawRoundedRect(QRectF(0, 0, BOARD_SIDE, BOARD_SIDE), BOARD_RADIUS, BOARD_RADIUS)
        p.setBrush(QColor(COLOR_EMPTY))
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                p.drawRoundedRect(self._cell_rect(i, j), TILE_RADIUS, TILE_RADIUS)
        p.end()
        return pm

    # ---------------- 对外接口 ----------------
    def is_animating(self):
        return self.anim is not None

    def render(self, grid):
        """静止渲染（新游戏 / 继续 / 撤销重做）"""
        self.timer.stop()
        self.anim = None
        self.grid = [row[:] for row in grid]
        self.update()

    def animate_move(self, final_grid, transitions, spawn):
        """播放一次移动：先滑行，再合并/新生放大"""
        moving = []
        pop_cells = {}
        for src, dst, value, merged in transitions:
            sx, sy = self._cell_xy(*src)
            tx, ty = self._cell_xy(*dst)
            moving.append((value, sx, sy, tx, ty))
            if merged:
                pop_cells[dst] = True

        self.anim = {
            "phase": "move",
            "t": 0.0,
            "moving": moving,
            "pop": pop_cells,
            "spawn": spawn,
            "final": [row[:] for row in final_grid],
        }
        self.timer.start()
        self.update()

    # ---------------- 逐帧推进 ----------------
    def _tick(self):
        if self.anim is None:
            self.timer.stop()
            return
        self.anim["t"] += self.timer.interval() / 1000.0

        if self.anim["phase"] == "move":
            if self.anim["t"] >= MOVE_DURATION:
                self.anim["phase"] = "pop"
                self.anim["t"] = 0.0
        else:
            if self.anim["t"] >= POP_DURATION:
                self.grid = self.anim["final"]
                self.anim = None
                self.timer.stop()
                self.update()
                self.animationFinished.emit()
                return
        self.update()

    # ---------------- 绘制 ----------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, self._background)      # 静态背景层

        if self.anim is None:
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    v = self.grid[r][c]
                    if v:
                        x, y = self._cell_xy(r, c)
                        self._draw_tile(p, v, x, y, 1.0)

        elif self.anim["phase"] == "move":
            prog = ease_out_cubic(min(1.0, self.anim["t"] / MOVE_DURATION))
            for value, sx, sy, tx, ty in self.anim["moving"]:
                x = sx + (tx - sx) * prog
                y = sy + (ty - sy) * prog
                self._draw_tile(p, value, x, y, 1.0)

        else:   # pop：落定后，合并处回弹放大、新生方块放大出现
            prog = min(1.0, self.anim["t"] / POP_DURATION)
            pop_cells = self.anim["pop"]
            spawn = self.anim["spawn"]
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    v = self.anim["final"][r][c]
                    if not v:
                        continue
                    scale = 1.0
                    if (r, c) in pop_cells:
                        scale = 1.0 + 0.16 * math.sin(math.pi * prog)
                    elif spawn is not None and (r, c) == spawn:
                        scale = ease_out_back(prog)
                    x, y = self._cell_xy(r, c)
                    self._draw_tile(p, v, x, y, scale)
        p.end()

    def _draw_tile(self, p, value, x, y, scale):
        """画一个圆角方块 + 居中数字；scale 控制放大（以其中心为准）"""
        size = TILE_SIZE * scale
        cx, cy = x + TILE_SIZE / 2.0, y + TILE_SIZE / 2.0
        rect = QRectF(cx - size / 2.0, cy - size / 2.0, size, size)

        p.setPen(Qt.NoPen)
        p.setBrush(self._tile_color(value))
        p.drawRoundedRect(rect, TILE_RADIUS * scale, TILE_RADIUS * scale)

        p.setPen(QColor(TEXT_DARK if value <= 4 else TEXT_LIGHT))
        font = QFont(self.font())
        if value < 100:
            base = 36
        elif value < 1000:
            base = 30
        elif value < 10000:
            base = 24
        else:
            base = 17
        font.setPixelSize(max(1, int(base * scale)))
        font.setBold(True)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, str(value))

    @staticmethod
    def _tile_color(value):
        if value <= 2048:
            return QColor(*TILE_COLORS.get(value, (60, 58, 50)))
        return QColor(*HIGH_COLORS.get(value, (198, 128, 12)))


class EnterButton(QPushButton):
    """可聚焦按钮；额外支持回车键触发（QPushButton 原生只响应空格）"""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


# =====================================================================
# Controller 层：事件分发 + 驱动动画 + 状态同步
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = AnimatedGameCore(4)
        self.win_announced = False
        self.init_ui()
        self.startup()

    # ---------------- 界面搭建 ----------------
    def init_ui(self):
        self.setWindowTitle("2048")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(f"QMainWindow {{ background-color: {COLOR_BG}; }}")

        self.stack = QStackedWidget()
        self.stack.setFocusPolicy(Qt.NoFocus)
        self.stack.addWidget(self._build_start_page())   # START_PAGE
        self.stack.addWidget(self._build_game_page())    # GAME_PAGE
        self.setCentralWidget(self.stack)

        self.setFocusPolicy(Qt.StrongFocus)
        self.refresh()

    def _build_start_page(self):
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(f"#page {{ background-color: {COLOR_BG}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.addStretch()

        title = QLabel("2048")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 70px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {COLOR_SUBTITLE}; font-size: 13px;")
        layout.addWidget(title)
        layout.addSpacing(5)
        layout.addWidget(subtitle)
        layout.addSpacing(30)

        card = QFrame()
        card.setObjectName("card")
        card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        card.setStyleSheet(
            f"#card {{ background-color: {COLOR_BOARD}; border-radius: 10px; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 14, 20, 14)
        card_layout.setSpacing(6)

        self.last_game_caption = QLabel("上一局")
        self.last_game_caption.setAlignment(Qt.AlignCenter)
        self.last_game_caption.setStyleSheet(f"color: {COLOR_CARD_LABEL}; font-size: 12px;")
        card_layout.addWidget(self.last_game_caption)

        stats = QHBoxLayout()
        stats.addStretch()
        score_box, self.last_score_value = self._make_stat("分数")
        best_box, self.last_best_value = self._make_stat("最高分")
        stats.addLayout(score_box)
        stats.addSpacing(48)
        stats.addLayout(best_box)
        stats.addStretch()
        card_layout.addLayout(stats)

        layout.addWidget(card, 0, Qt.AlignHCenter)
        layout.addSpacing(23)

        self.continue_start_button = self._make_button(
            "继续上一局", self.on_continue_clicked,
            size=(CARD_WIDTH, 48), focusable=True, enter_ok=True)
        self.new_game_start_button = self._make_button(
            "开始新游戏", self.on_new_game_clicked, qss=TEXT_BUTTON_QSS,
            size=(CARD_WIDTH, BUTTON_HEIGHT), focusable=True, enter_ok=True)
        layout.addWidget(self.continue_start_button, 0, Qt.AlignHCenter)
        layout.addSpacing(10)
        layout.addWidget(self.new_game_start_button, 0, Qt.AlignHCenter)
        layout.addStretch()
        return page

    def _make_stat(self, caption):
        box = QVBoxLayout()
        box.setSpacing(2)
        value = QLabel("0")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet(f"color: {COLOR_CARD_VALUE}; font-size: 24px; font-weight: bold;")
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        cap.setStyleSheet(f"color: {COLOR_CARD_LABEL}; font-size: 11px;")
        box.addWidget(value)
        box.addWidget(cap)
        return box, value

    def _build_game_page(self):
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(f"#page {{ background-color: {COLOR_BG}; }}")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(GAME_MARGIN_X, 30, GAME_MARGIN_X, 24)
        main_layout.setSpacing(0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("2048")
        title.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 48px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setStyleSheet(f"color: {COLOR_SUBTITLE}; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.score_label = self._make_score_card()
        self.best_label = self._make_score_card()

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.score_label, 0, Qt.AlignTop)
        header.addWidget(self.best_label, 0, Qt.AlignTop)

        self.board_view = BoardView(self.model.grid_size)
        self.board_view.animationFinished.connect(self._on_animation_finished)

        self.undo_button = self._make_button("撤销", self.on_undo, qss=SECONDARY_BUTTON_QSS)
        self.redo_button = self._make_button("重做", self.on_redo, qss=SECONDARY_BUTTON_QSS)
        self.undo_button.setToolTip("撤销上一步（Ctrl+Z）")
        self.redo_button.setToolTip("重做（Ctrl+Y）")
        self.new_game_button = self._make_button("新游戏", self.on_new_game_clicked)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.undo_button)
        button_layout.addWidget(self.redo_button)
        button_layout.addStretch()
        button_layout.addWidget(self.new_game_button)

        main_layout.addLayout(header)
        main_layout.addSpacing(18)
        main_layout.addWidget(self.board_view)
        main_layout.addSpacing(32)
        main_layout.addLayout(button_layout)
        main_layout.addStretch()
        return page

    def _make_score_card(self):
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(96, 62)
        label.setStyleSheet(
            f"background-color: {COLOR_BOARD}; border-radius: {TILE_RADIUS}px;")
        return label

    def _render_score(self, label, caption, value):
        label.setText(
            f"<div style='font-size:11px; color:{COLOR_CARD_LABEL};'>{caption}</div>"
            f"<div style='font-size:24px; color:{COLOR_CARD_VALUE}; font-weight:bold;'>{value}</div>")

    def _make_button(self, text, slot, qss=PRIMARY_BUTTON_QSS,
                     size=(BUTTON_WIDTH, BUTTON_HEIGHT), focusable=False, enter_ok=False):
        button = EnterButton(text) if enter_ok else QPushButton(text)
        button.setFixedSize(*size)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.StrongFocus if focusable else Qt.NoFocus)
        button.setStyleSheet(qss)
        button.clicked.connect(slot)
        return button

    # ---------------- 刷新视图 ----------------
    def refresh(self):
        if not self.board_view.is_animating():
            self.board_view.render(self.model.grid)
        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        busy = self.board_view.is_animating()
        self.undo_button.setEnabled(self.model.can_undo() and not busy)
        self.redo_button.setEnabled(self.model.can_redo() and not busy)

    # ---------------- 键盘事件 ----------------
    def keyPressEvent(self, event):
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.ControlModifier)

        if ctrl and key == Qt.Key_Z:
            self.on_undo()
            return
        if ctrl and key == Qt.Key_Y:
            self.on_redo()
            return

        direction = {
            Qt.Key_Up: 'up', Qt.Key_W: 'up',
            Qt.Key_Down: 'down', Qt.Key_S: 'down',
            Qt.Key_Left: 'left', Qt.Key_A: 'left',
            Qt.Key_Right: 'right', Qt.Key_D: 'right',
        }.get(key)

        if direction is None:
            super().keyPressEvent(event)
            return
        self.on_move(direction)

    # ---------------- 交互回调 ----------------
    def on_move(self, direction):
        if self.model.game_over or self.board_view.is_animating():
            return                      # 动画进行中忽略输入，避免状态错乱
        if not self.model.apply_move(direction):
            return

        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self.undo_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        self.board_view.animate_move(self.model.grid, self.model.last_transitions,
                                     self.model.last_spawn)

    def _on_animation_finished(self):
        self.refresh()
        if self.model.game_over:
            self.show_game_over()
        elif self.model.won and not self.win_announced:
            self.win_announced = True
            self.show_game_won()

    def on_undo(self):
        if self.board_view.is_animating():
            return
        if self.model.undo():
            self.refresh()

    def on_redo(self):
        if self.board_view.is_animating():
            return
        if self.model.redo():
            self.refresh()

    # ---------------- 启动流程 ----------------
    def startup(self):
        info = self.model.get_recent_game_info()
        self._render_last_game(info)
        if info is None:
            self.start_new_game()
        else:
            self.stack.setCurrentIndex(START_PAGE)
            (self.continue_start_button if self.continue_start_button.isEnabled()
             else self.new_game_start_button).setFocus()

    def _render_last_game(self, info):
        if info is None:
            self.last_game_caption.setText("暂无存档")
            self.last_score_value.setText("—")
            self.last_best_value.setText("—")
            self.continue_start_button.setEnabled(False)
        else:
            self.last_game_caption.setText("上一局")
            self.last_score_value.setText(str(info.get("score", 0)))
            self.last_best_value.setText(str(info.get("best_score", 0)))
            self.continue_start_button.setEnabled(True)

    def on_continue_clicked(self):
        recent = self.model.get_recent_game()
        if recent and self.model.load_game_state(recent):
            self.win_announced = self.model.won
            self.refresh()
            self.stack.setCurrentIndex(GAME_PAGE)
            self.setFocus()

    def on_new_game_clicked(self):
        self.start_new_game()

    def start_new_game(self):
        self.model.start_new_game()
        self.win_announced = False
        self.refresh()
        self.stack.setCurrentIndex(GAME_PAGE)
        self.setFocus()

    # ---------------- 对话框 ----------------
    def show_game_over(self):
        QMessageBox.information(self, "游戏结束",
                                f"游戏结束！\n最终分数：{self.model.score}")
        self.refresh()

    def show_game_won(self):
        reply = QMessageBox.question(
            self, "恭喜胜利！", "你已经达到 2048！是否继续挑战更高分数？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.No:
            self.start_new_game()

    def closeEvent(self, event):
        self.model.save_game_state()
        self.model.update_index()
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 10)
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"])
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
