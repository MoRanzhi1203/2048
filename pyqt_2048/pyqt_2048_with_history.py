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

# =====================================================================
# 视觉规范常量（集中管理：颜色 / 尺寸 / 圆角 / 按钮样式，避免散落硬编码）
# =====================================================================
COLOR_BG = "#faf8ef"           # 页面背景
COLOR_TEXT = "#776e65"         # 主标题 / 深色文本
COLOR_SUBTITLE = "#a39489"     # 副标题
COLOR_BOARD = "#bbada0"        # 棋盘 / 统计卡背景
COLOR_EMPTY = "#cdc1b4"        # 空格
COLOR_CARD_LABEL = "#eee4da"   # 卡片标签
COLOR_CARD_VALUE = "#ffffff"   # 卡片数值

# 棋盘：尺寸由方块推导，保证严格正方形、4×4 每格一致
TILE_SIZE = 96
TILE_GAP = 10
BOARD_PADDING = 10
TILE_RADIUS = 6
BOARD_RADIUS = 9
BOARD_SIDE = BOARD_PADDING * 2 + TILE_SIZE * 4 + TILE_GAP * 3   # 434

# 窗口与布局
WINDOW_WIDTH, WINDOW_HEIGHT = 500, 672
GAME_MARGIN_X = (WINDOW_WIDTH - BOARD_SIDE) // 2   # 33：使按钮与棋盘左右边缘对齐

# 控件尺寸
BUTTON_WIDTH, BUTTON_HEIGHT = 100, 44
CARD_WIDTH, CARD_HEIGHT = 330, 110   # 启动页「上一局」摘要卡

# 按钮样式：主按钮（实心棕）、次按钮（浅色，含禁用态）、文字按钮（无底色）
PRIMARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #8f7a66; color: #f9f6f2;
    border: none; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #9f8b78; }}
QPushButton:pressed  {{ background-color: #7c6a58; }}
QPushButton:disabled {{ background-color: #cdc2b6; color: #f2ece5; }}
"""

SECONDARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #eee4da; color: {COLOR_TEXT};
    border: none; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #e2d7ca; }}
QPushButton:pressed  {{ background-color: #d5c9ba; }}
QPushButton:disabled {{ background-color: #eee8e1; color: #b7aa9e; }}
"""

TEXT_BUTTON_QSS = f"""
QPushButton {{
    background-color: transparent; color: {COLOR_TEXT};
    border: none; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #efe9e1; }}
QPushButton:pressed  {{ background-color: #e6ddd3; }}
QPushButton:disabled {{ color: #c3b8ad; }}
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

    # 经典 2048 配色（空格底色单独用 COLOR_EMPTY）
    COLORS = {
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
        if value == 0:
            bg = QColor(COLOR_EMPTY)
        elif value > 2048:
            level = min(230, 46 + (value // 2048) * 18)
            bg = QColor(237, 194, level)
        else:
            bg = QColor(*self.COLORS.get(value, (60, 58, 50)))

        color = self.TEXT_DARK if value <= 4 else self.TEXT_LIGHT
        # 字号随位数自适应：2–64 常规 36px，逐级递减，保证大数值不溢出
        if value == 0:
            size = 1
        elif value < 100:
            size = 36
        elif value < 1000:
            size = 30
        elif value < 10000:
            size = 24
        else:
            size = 17

        self.setStyleSheet(
            f"QLabel {{ background-color: {bg.name()}; color: {color};"
            f" border-radius: {TILE_RADIUS}px; font-size: {size}px; font-weight: bold; }}")
        self.setText("" if value == 0 else str(value))


class BoardView(QWidget):
    """棋盘视图：把 Model 的二维网格渲染成 4x4 的方块"""
    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background-color: {COLOR_BOARD}; border-radius: {BOARD_RADIUS}px;")
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
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(f"QMainWindow {{ background-color: {COLOR_BG}; }}")

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
        """启动页：标题 + 上一局摘要卡 + 主/次操作（同一中心轴）"""
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(f"#page {{ background-color: {COLOR_BG}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.addStretch()

        title = QLabel("2048")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 70px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {COLOR_SUBTITLE}; font-size: 13px;")
        layout.addWidget(title)
        layout.addSpacing(5)
        layout.addWidget(subtitle)
        layout.addSpacing(30)

        # --- 上一局摘要卡：小标题 + 两列（大数字 / 下方标签）---
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
        self.last_game_caption.setStyleSheet(
            f"color: {COLOR_CARD_LABEL}; font-size: 12px;")
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

        # 继续 = 主操作（实心棕，与卡片同宽）；开始新游戏 = 轻量文字按钮
        self.continue_start_button = self._make_button(
            "继续上一局", self.on_continue_clicked, size=(CARD_WIDTH, 48))
        self.new_game_start_button = self._make_button(
            "开始新游戏", self.on_new_game_clicked,
            qss=TEXT_BUTTON_QSS, size=(CARD_WIDTH, BUTTON_HEIGHT))
        layout.addWidget(self.continue_start_button, 0, Qt.AlignHCenter)
        layout.addSpacing(10)
        layout.addWidget(self.new_game_start_button, 0, Qt.AlignHCenter)
        layout.addStretch()
        return page

    def _make_stat(self, caption):
        """摘要卡里的一列统计：上方大数字，下方小标签；返回 (布局, 数值标签)"""
        box = QVBoxLayout()
        box.setSpacing(2)
        value = QLabel("0")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet(
            f"color: {COLOR_CARD_VALUE}; font-size: 24px; font-weight: bold;")
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        cap.setStyleSheet(f"color: {COLOR_CARD_LABEL}; font-size: 11px;")
        box.addWidget(value)
        box.addWidget(cap)
        return box, value

    def _build_game_page(self):
        """游戏页：标题 + 分数卡 + 棋盘 + 操作按钮"""
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(f"#page {{ background-color: {COLOR_BG}; }}")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(GAME_MARGIN_X, 30, GAME_MARGIN_X, 24)
        main_layout.setSpacing(0)

        # --- 顶部：标题 + 副标题 + 两张统计卡（顶边对齐）---
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("2048")
        title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 48px; font-weight: bold;")
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

        # --- 中部：棋盘（宽度与内容区一致，左右边缘即棋盘边缘）---
        self.board_view = BoardView(self.model.grid_size)

        # --- 底部：撤销/重做居左，新游戏居右，均与棋盘边缘对齐 ---
        self.undo_button = self._make_button(
            "撤销", self.on_undo, qss=SECONDARY_BUTTON_QSS)
        self.redo_button = self._make_button(
            "重做", self.on_redo, qss=SECONDARY_BUTTON_QSS)
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
        main_layout.addSpacing(18)     # 顶部区 → 棋盘
        main_layout.addWidget(self.board_view)
        main_layout.addSpacing(32)     # 棋盘 → 底部操作组
        main_layout.addLayout(button_layout)
        main_layout.addStretch()
        return page

    def _make_score_card(self):
        """分数卡：上方小字标签 + 下方加粗数值"""
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
                     size=(BUTTON_WIDTH, BUTTON_HEIGHT)):
        button = QPushButton(text)
        button.setFixedSize(*size)
        button.setCursor(Qt.PointingHandCursor)
        # 不参与焦点：否则方向键会被 Qt 的焦点导航拦下，无法传到主窗口
        button.setFocusPolicy(Qt.NoFocus)
        button.setStyleSheet(qss)
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
    # 高 DPI 适配：需在创建 QApplication 之前设置，125%/150% 缩放下自适应放大
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    # 字体回退链：优先系统 UI 字体，缺失时逐级回退，避免换行/截断
    font = QFont("Microsoft YaHei", 10)
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"])
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
