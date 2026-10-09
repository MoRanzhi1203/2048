#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048（MVC 架构 + 历史记录 + 撤销/重做）

配套博客《第 3 篇：使用 PyQt 实现 2048 桌面 GUI》。

分层说明：
    Model       -> GameCore   棋盘逻辑、得分、历史持久化、撤销/重做
    View        -> BoardView  只负责把 Model 的网格渲染成方块
    Controller  -> MainWindow 处理键盘/按钮事件，驱动 Model 并刷新 View
"""

import sys
import os
import csv
import json
import random
import datetime
from copy import deepcopy

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QLabel, QPushButton, QMessageBox, QVBoxLayout,
                             QHBoxLayout, QStackedWidget, QFrame)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont


# 方向 -> 中文名，用于写入历史记录
DIRECTION_NAMES = {'up': '向上', 'down': '向下', 'left': '向左', 'right': '向右'}

# 页面索引
START_PAGE = 0
GAME_PAGE = 1

# 界面尺寸常量（棋盘尺寸由方块尺寸推导，保证方块始终是正方形）
TILE_SIZE = 96
TILE_GAP = 10
BOARD_PADDING = 10
BOARD_SIDE = BOARD_PADDING * 2 + TILE_SIZE * 4 + TILE_GAP * 3   # 434

# 按钮样式：主按钮（实心棕）与次按钮（浅灰，含禁用态）
PRIMARY_BUTTON_QSS = """
QPushButton {
    background-color: #8f7a66; color: #f9f6f2;
    border: none; border-radius: 6px;
    font-size: 14px; font-weight: bold;
}
QPushButton:hover   { background-color: #9f8b78; }
QPushButton:pressed { background-color: #7c6a58; }
QPushButton:disabled { background-color: #cbbfb2; color: #efe9e2; }
"""

SECONDARY_BUTTON_QSS = """
QPushButton {
    background-color: #d6cdc4; color: #776e65;
    border: none; border-radius: 6px;
    font-size: 14px; font-weight: bold;
}
QPushButton:hover    { background-color: #c7bcb2; }
QPushButton:pressed  { background-color: #b7aaa0; }
QPushButton:disabled { background-color: #e7e0d9; color: #c3b9af; }
"""


# =====================================================================
# Model 层：游戏核心逻辑（不含任何界面代码，可以单独导入测试）
# =====================================================================
class GameCore:
    """游戏核心：棋盘状态、合并规则、历史持久化、撤销/重做"""

    def __init__(self, grid_size=4):
        self.grid_size = grid_size
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.score = 0
        self.best_score = 0
        self.game_over = False
        self.won = False

        # 历史记录相关
        self.game_id = None
        self.history_file = None
        self.current_move = 0
        self.history_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "game_history")
        os.makedirs(self.history_dir, exist_ok=True)

        # 撤销 / 重做栈，保存的是状态快照
        self.undo_stack = []
        self.redo_stack = []

        self.load_best_score()

    # ---------------- 历史记录持久化 ----------------
    def load_best_score(self):
        """读取历史最高分"""
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        if os.path.exists(best_score_file):
            try:
                with open(best_score_file, 'r', encoding='utf-8') as f:
                    self.best_score = json.load(f).get('best_score', 0)
            except (json.JSONDecodeError, IOError):
                pass

    def save_best_score(self):
        """保存历史最高分"""
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        try:
            with open(best_score_file, 'w', encoding='utf-8') as f:
                json.dump({'best_score': self.best_score}, f, ensure_ascii=False)
        except IOError:
            pass

    def start_new_game(self):
        """开始新游戏：新建历史文件、清空棋盘、生成两个初始方块"""
        self.game_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        game_dir = os.path.join(self.history_dir, self.game_id)
        os.makedirs(game_dir, exist_ok=True)

        self.history_file = os.path.join(game_dir, "history.csv")
        with open(self.history_file, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(["步数", "操作类型", "当前分数", "网格状态"])

        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        self.score = 0
        self.game_over = False
        self.won = False
        self.current_move = 0
        self.undo_stack.clear()
        self.redo_stack.clear()

        for _ in range(2):
            self.add_new_tile()

        self.record_move("初始状态")
        self.update_index()

    def record_move(self, move_type):
        """把一步操作追加到历史 CSV，并同步保存游戏状态"""
        if not self.history_file:
            return
        self.current_move += 1
        with open(self.history_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([self.current_move, move_type, self.score,
                             json.dumps(self.grid, ensure_ascii=False)])
        self.save_game_state()

    def save_game_state(self):
        """保存完整状态，用于下次启动时恢复"""
        if not self.game_id:
            return
        state_file = os.path.join(self.history_dir, self.game_id, "game_state.json")
        game_state = {
            "grid": self.grid,
            "score": self.score,
            "best_score": self.best_score,
            "game_over": self.game_over,
            "won": self.won,
            "current_move": self.current_move,
            "last_updated": datetime.datetime.now().isoformat()
        }
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(game_state, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def update_index(self):
        """更新 index.json，记录每局游戏的概要信息"""
        index_file = os.path.join(self.history_dir, "index.json")
        index_data = []
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                index_data = []

        game_info = {
            "game_id": self.game_id,
            "start_time": datetime.datetime.now().isoformat(),
            "score": self.score,
            "best_score": self.best_score,
            "is_completed": self.game_over or self.won,
            "last_updated": datetime.datetime.now().isoformat()
        }

        for i, info in enumerate(index_data):
            if info["game_id"] == self.game_id:
                index_data[i].update(game_info)
                break
        else:
            index_data.append(game_info)

        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def get_recent_game_info(self):
        """返回最近一局未完成游戏的索引信息（dict），没有则返回 None"""
        index_file = os.path.join(self.history_dir, "index.json")
        if not os.path.exists(index_file):
            return None
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            unfinished = [g for g in index_data if not g.get("is_completed", False)]
            if not unfinished:
                return None
            return sorted(unfinished, key=lambda x: x.get("last_updated", ""),
                          reverse=True)[0]
        except (json.JSONDecodeError, IOError):
            return None

    def get_recent_game(self):
        """返回最近一局未完成游戏的 game_id，没有则返回 None"""
        info = self.get_recent_game_info()
        return info["game_id"] if info else None

    def load_game_state(self, game_id):
        """加载指定游戏的状态"""
        game_dir = os.path.join(self.history_dir, game_id)
        state_file = os.path.join(game_dir, "game_state.json")
        if not os.path.exists(state_file):
            return False
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            self.game_id = game_id
            self.grid = state["grid"]
            self.score = state["score"]
            self.best_score = state["best_score"]
            self.game_over = state["game_over"]
            self.won = state["won"]
            self.current_move = state["current_move"]
            self.history_file = os.path.join(game_dir, "history.csv")
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.update_index()
            return True
        except (json.JSONDecodeError, IOError, KeyError):
            return False

    # ---------------- 棋盘逻辑 ----------------
    def add_new_tile(self):
        """在随机空格生成新方块：90% 为 2，10% 为 4"""
        empty_cells = [(i, j) for i in range(self.grid_size)
                       for j in range(self.grid_size) if self.grid[i][j] == 0]
        if not empty_cells:
            return False
        i, j = random.choice(empty_cells)
        self.grid[i][j] = 2 if random.random() < 0.9 else 4
        return True

    def _merge_line(self, line):
        """
        合并单行（核心算法）：压缩非零 -> 相邻相同合并 -> 右侧补零。
        返回 (新行, 是否发生变化)。
        """
        original = list(line)
        compressed = [v for v in line if v != 0]

        merged = []
        i = 0
        while i < len(compressed):
            if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
                merged.append(compressed[i] * 2)
                self.score += compressed[i] * 2
                i += 2
            else:
                merged.append(compressed[i])
                i += 1

        merged += [0] * (self.grid_size - len(merged))
        return merged, merged != original

    def _slide(self, direction):
        """
        通用移动：上下方向先转置、左右方向按需要翻转行，
        于是四个方向都复用同一套 _merge_line 逻辑。
        """
        moved = False
        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]

        for i in range(self.grid_size):
            row = self.grid[i][::-1] if direction in ('right', 'down') else self.grid[i]
            new_row, has_moved = self._merge_line(row)
            if direction in ('right', 'down'):
                new_row.reverse()
            self.grid[i] = new_row
            moved = moved or has_moved

        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]
        return moved

    def check_win(self):
        """检查是否出现 2048"""
        if any(2048 in row for row in self.grid):
            self.won = True

    def check_game_over(self):
        """没有空格且四周都无法合并时，游戏结束"""
        if any(0 in row for row in self.grid):
            return False
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1]:
                    return False
                if self.grid[j][i] == self.grid[j + 1][i]:
                    return False

        self.game_over = True
        self.best_score = max(self.best_score, self.score)
        self.save_best_score()
        self.update_index()
        return True

    # ---------------- 一个完整回合 ----------------
    def apply_move(self, direction):
        """执行一次移动：记录快照 -> 合并 -> 写历史 -> 生成新方块 -> 判断胜负"""
        snapshot = self._snapshot()
        if not self._slide(direction):
            return False

        self.undo_stack.append(snapshot)
        self.redo_stack.clear()

        self.record_move(DIRECTION_NAMES[direction])
        self.add_new_tile()
        self.record_move("添加新方块")

        self.check_win()
        self.check_game_over()
        return True

    # ---------------- 撤销 / 重做 ----------------
    def _snapshot(self):
        """当前状态快照（深拷贝，避免后续修改污染历史）"""
        return {
            "grid": deepcopy(self.grid),
            "score": self.score,
            "game_over": self.game_over,
            "won": self.won,
        }

    def _restore(self, snapshot):
        self.grid = deepcopy(snapshot["grid"])
        self.score = snapshot["score"]
        self.game_over = snapshot["game_over"]
        self.won = snapshot["won"]

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self):
        """回退到上一步；同时把当前状态压入重做栈"""
        if not self.undo_stack:
            return False
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())
        self.save_game_state()
        self.update_index()
        return True

    def redo(self):
        """重新执行被撤销的一步"""
        if not self.redo_stack:
            return False
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())
        self.save_game_state()
        self.update_index()
        return True


# =====================================================================
# View 层：只负责渲染，不处理任何业务逻辑
# =====================================================================
class TileLabel(QLabel):
    """单个方块（View 的最小元素）"""

    # 经典 2048 配色，0 为空格底色
    COLORS = {
        0: (205, 193, 180),
        2: (238, 228, 218),
        4: (237, 224, 200),
        8: (242, 177, 121),
        16: (245, 149, 99),
        32: (246, 124, 95),
        64: (246, 94, 59),
        128: (237, 207, 114),
        256: (237, 204, 97),
        512: (237, 200, 80),
        1024: (237, 197, 63),
        2048: (237, 194, 46),
    }
    TEXT_DARK = "#776e65"
    TEXT_LIGHT = "#f9f6f2"

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(TILE_SIZE, TILE_SIZE)
        self.set_value(value)

    def set_value(self, value):
        """根据数值刷新圆角背景、字色与字号"""
        if value > 2048:
            level = min(230, 46 + (value // 2048) * 18)
            bg = QColor(237, 194, level)
        else:
            bg = QColor(*self.COLORS.get(value, (60, 58, 50)))

        color = self.TEXT_DARK if value <= 4 else self.TEXT_LIGHT
        if value == 0:
            size = 1
        elif value < 100:
            size = 32
        elif value < 1000:
            size = 26
        elif value < 10000:
            size = 20
        else:
            size = 15

        self.setStyleSheet(
            f"QLabel {{ background-color: {bg.name()}; color: {color};"
            f" border-radius: 6px; font-size: {size}px; font-weight: bold; }}")
        self.setText("" if value == 0 else str(value))


class BoardView(QWidget):
    """棋盘视图：把 Model 的二维网格渲染成 4x4 的方块"""
    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #bbada0; border-radius: 10px;")
        side = BOARD_PADDING * 2 + TILE_SIZE * grid_size + TILE_GAP * (grid_size - 1)
        self.setFixedSize(side, side)

        layout = QGridLayout(self)
        layout.setSpacing(TILE_GAP)
        layout.setContentsMargins(BOARD_PADDING, BOARD_PADDING,
                                  BOARD_PADDING, BOARD_PADDING)

        self.tiles = []
        for i in range(grid_size):
            row = []
            for j in range(grid_size):
                tile = TileLabel()
                layout.addWidget(tile, i, j)
                row.append(tile)
            self.tiles.append(row)

    def render(self, grid):
        """按当前网格刷新所有方块"""
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                self.tiles[i][j].set_value(grid[i][j])


# =====================================================================
# Controller 层：连接 Model 与 View，处理所有交互
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = GameCore(4)
        self.win_announced = False
        self.init_ui()
        self.startup()

    # ---------------- 界面搭建 ----------------
    def init_ui(self):
        self.setWindowTitle("2048")
        self.setFixedSize(500, 660)
        self.setStyleSheet("QMainWindow { background-color: #faf8ef; }")

        # 用 QStackedWidget 承载「启动页」与「游戏页」
        self.stack = QStackedWidget()
        self.stack.setFocusPolicy(Qt.NoFocus)
        self.stack.addWidget(self._build_start_page())   # START_PAGE
        self.stack.addWidget(self._build_game_page())    # GAME_PAGE
        self.setCentralWidget(self.stack)

        # 让主窗口本身持有键盘焦点，方向键才能直达 keyPressEvent
        self.setFocusPolicy(Qt.StrongFocus)
        self.refresh()

    def _build_start_page(self):
        """启动页：标题 + 上一局信息卡 + 继续/新局按钮（替代原来的确认弹窗）"""
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet("#page { background-color: #faf8ef; }")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.addStretch()

        title = QLabel("2048")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #776e65; font-size: 76px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #a39489; font-size: 14px;")
        layout.addWidget(title)
        layout.addSpacing(6)
        layout.addWidget(subtitle)
        layout.addSpacing(34)

        # --- 上一局信息卡：标题 + 分数/最高分 两列 ---
        card = QFrame()
        card.setObjectName("card")
        card.setFixedHeight(106)
        card.setStyleSheet("#card { background-color: #bbada0; border-radius: 10px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 14, 20, 14)
        card_layout.setSpacing(8)

        self.last_game_caption = QLabel("上一局进行中")
        self.last_game_caption.setAlignment(Qt.AlignCenter)
        self.last_game_caption.setStyleSheet("color: #eee4da; font-size: 12px;")
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

        layout.addWidget(card)
        layout.addSpacing(24)

        # 继续 = 主操作（实心棕），开始新游戏 = 次操作（浅灰）
        self.continue_start_button = self._make_button(
            "继续上一局", self.on_continue_clicked, size=(220, 48))
        new_game_start_button = self._make_button(
            "开始新游戏", self.on_new_game_clicked, secondary=True, size=(220, 48))
        layout.addWidget(self.continue_start_button, 0, Qt.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(new_game_start_button, 0, Qt.AlignHCenter)
        layout.addStretch()
        return page

    def _make_stat(self, caption):
        """信息卡里的一列统计：上小字标题，下加粗数值；返回 (布局, 数值标签)"""
        box = QVBoxLayout()
        box.setSpacing(2)
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        cap.setStyleSheet("color: #eee4da; font-size: 11px;")
        value = QLabel("0")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: bold;")
        box.addWidget(cap)
        box.addWidget(value)
        return box, value

    def _build_game_page(self):
        """游戏页：标题 + 分数卡 + 棋盘 + 操作按钮"""
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet("#page { background-color: #faf8ef; }")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(30, 24, 30, 26)
        main_layout.setSpacing(16)

        # --- 顶部：标题 + 副标题 + 两张分数卡 ---
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("2048")
        title.setStyleSheet("color: #776e65; font-size: 46px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setStyleSheet("color: #a39489; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.score_label = self._make_score_card()
        self.best_label = self._make_score_card()

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.score_label)
        header.addWidget(self.best_label)

        # --- 中部：棋盘 ---
        self.board_view = BoardView(self.model.grid_size)

        # --- 底部：操作按钮（撤销/重做为次要按钮，新游戏为主按钮）---
        self.undo_button = self._make_button("撤销", self.on_undo, secondary=True)
        self.redo_button = self._make_button("重做", self.on_redo, secondary=True)
        self.undo_button.setToolTip("撤销上一步（Ctrl+Z）")
        self.redo_button.setToolTip("重做（Ctrl+Y）")
        new_game_button = self._make_button("新游戏", self.on_new_game_clicked)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.undo_button)
        button_layout.addWidget(self.redo_button)
        button_layout.addStretch()
        button_layout.addWidget(new_game_button)

        main_layout.addLayout(header)
        main_layout.addWidget(self.board_view, 0, Qt.AlignHCenter)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        return page

    def _make_score_card(self):
        """分数卡：上方小字标题 + 下方加粗数值"""
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(96, 62)
        label.setStyleSheet("background-color: #bbada0; border-radius: 6px;")
        return label

    def _render_score(self, label, caption, value):
        label.setText(
            f"<div style='font-size:11px; color:#eee4da;'>{caption}</div>"
            f"<div style='font-size:22px; color:#ffffff; font-weight:bold;'>{value}</div>")

    def _make_button(self, text, slot, secondary=False, size=(100, 44)):
        button = QPushButton(text)
        button.setFixedSize(*size)
        button.setCursor(Qt.PointingHandCursor)
        # 不参与焦点：否则方向键会被 Qt 的焦点导航拦下，无法传到主窗口
        button.setFocusPolicy(Qt.NoFocus)
        button.setStyleSheet(SECONDARY_BUTTON_QSS if secondary else PRIMARY_BUTTON_QSS)
        button.clicked.connect(slot)
        return button

    # ---------------- 刷新视图 ----------------
    def refresh(self):
        """把 Model 的最新状态同步到 View 与分数/按钮状态"""
        self.board_view.render(self.model.grid)
        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self.undo_button.setEnabled(self.model.can_undo())
        self.redo_button.setEnabled(self.model.can_redo())

    # ---------------- 键盘事件（Controller 的核心） ----------------
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
        if self.model.game_over:
            return
        if not self.model.apply_move(direction):
            return

        self.refresh()
        if self.model.game_over:
            self.show_game_over()
        elif self.model.won and not self.win_announced:
            self.win_announced = True
            self.show_game_won()

    def on_undo(self):
        if self.model.undo():
            self.refresh()

    def on_redo(self):
        if self.model.redo():
            self.refresh()

    # ---------------- 启动流程与按钮回调 ----------------
    def startup(self):
        """启动时读取存档：有未完成的对局就停在启动页，否则直接开局"""
        info = self.model.get_recent_game_info()
        self._render_last_game(info)
        if info is None:
            self.start_new_game()
        else:
            self.stack.setCurrentIndex(START_PAGE)

    def _render_last_game(self, info):
        if info is None:
            self.last_game_caption.setText("暂无未完成的存档")
            self.last_score_value.setText("—")
            self.last_best_value.setText("—")
            self.continue_start_button.setEnabled(False)
        else:
            self.last_game_caption.setText("上一局进行中")
            self.last_score_value.setText(str(info.get("score", 0)))
            self.last_best_value.setText(str(info.get("best_score", 0)))
            self.continue_start_button.setEnabled(True)

    def on_continue_clicked(self):
        """继续最近一局未完成的游戏，并切换到游戏页"""
        recent = self.model.get_recent_game()
        if recent and self.model.load_game_state(recent):
            self.win_announced = self.model.won
            self.refresh()
            self.stack.setCurrentIndex(GAME_PAGE)
            self.setFocus()

    def on_new_game_clicked(self):
        """开始新游戏，并切换到游戏页"""
        self.start_new_game()

    def start_new_game(self):
        self.model.start_new_game()
        self.win_announced = False
        self.refresh()
        self.stack.setCurrentIndex(GAME_PAGE)
        self.setFocus()

    # ---------------- 对话框 ----------------
    def show_game_over(self):
        QMessageBox.information(
            self, "游戏结束",
            f"游戏结束！\n最终分数：{self.model.score}")
        self.refresh()

    def show_game_won(self):
        reply = QMessageBox.question(
            self, "恭喜胜利！", "你已经达到 2048！是否继续挑战更高分数？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.No:
            self.start_new_game()

    def closeEvent(self, event):
        """关闭窗口时保存当前状态"""
        self.model.save_game_state()
        self.model.update_index()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
