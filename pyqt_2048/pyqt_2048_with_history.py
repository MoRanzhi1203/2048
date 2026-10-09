#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048 游戏（带历史记录功能）
"""

import sys
import random
import os
import csv
import json
import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QLabel, QPushButton, QMessageBox, QVBoxLayout,
                             QHBoxLayout, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QRect, QEasingCurve
from PyQt5.QtGui import QFont, QPalette, QColor, QPainter, QBrush, QPen


class GameCore:
    """游戏核心逻辑（从原始代码中提取）"""
    def __init__(self, grid_size=4):
        self.grid_size = grid_size
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.score = 0
        self.best_score = 0
        self.game_over = False
        self.won = False
        self.game_id = None
        self.history_file = None
        self.current_move = 0
        self.history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_history")
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
        self.load_best_score()

    # 从原始代码复制的历史记录相关功能
    def load_best_score(self):
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        if os.path.exists(best_score_file):
            try:
                with open(best_score_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.best_score = data.get('best_score', 0)
            except:
                pass

    def save_best_score(self):
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        try:
            with open(best_score_file, 'w', encoding='utf-8') as f:
                json.dump({'best_score': self.best_score}, f, ensure_ascii=False)
        except:
            pass

    def start_new_game(self):
        self.game_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        game_dir = os.path.join(self.history_dir, self.game_id)
        os.makedirs(game_dir, exist_ok=True)
        self.history_file = os.path.join(game_dir, "history.csv")
        with open(self.history_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["步数", "操作类型", "当前分数", "网格状态"])
        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        self.score = 0
        self.game_over = False
        self.won = False
        self.current_move = 0
        for _ in range(2):
            self.add_new_tile()
        self.record_move("初始状态")
        self.update_index()

    def record_move(self, move_type):
        if not self.history_file:
            return
        self.current_move += 1
        with open(self.history_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            grid_json = json.dumps(self.grid, ensure_ascii=False)
            writer.writerow([self.current_move, move_type, self.score, grid_json])
        self.save_game_state()

    def save_game_state(self):
        if not self.game_id:
            return
        game_dir = os.path.join(self.history_dir, self.game_id)
        state_file = os.path.join(game_dir, "game_state.json")
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
        except:
            pass

    def update_index(self):
        index_file = os.path.join(self.history_dir, "index.json")
        index_data = []
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            except:
                index_data = []
        game_info = {
            "game_id": self.game_id,
            "start_time": datetime.datetime.now().isoformat(),
            "score": self.score,
            "best_score": self.best_score,
            "is_completed": self.game_over or self.won,
            "last_updated": datetime.datetime.now().isoformat()
        }
        existing_index = None
        for i, info in enumerate(index_data):
            if info["game_id"] == self.game_id:
                existing_index = i
                break
        if existing_index is not None:
            index_data[existing_index].update(game_info)
        else:
            index_data.append(game_info)
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def get_recent_game(self):
        index_file = os.path.join(self.history_dir, "index.json")
        if not os.path.exists(index_file):
            return None
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            for game_info in sorted(index_data, key=lambda x: x.get("last_updated", ""), reverse=True):
                if not game_info.get("is_completed", False):
                    return game_info["game_id"]
            return None
        except:
            return None

    def load_game_state(self, game_id):
        game_dir = os.path.join(self.history_dir, game_id)
        state_file = os.path.join(game_dir, "game_state.json")
        if not os.path.exists(state_file):
            return False
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                game_state = json.load(f)
            self.game_id = game_id
            self.grid = game_state["grid"]
            self.score = game_state["score"]
            self.best_score = game_state["best_score"]
            self.game_over = game_state["game_over"]
            self.won = game_state["won"]
            self.current_move = game_state["current_move"]
            self.history_file = os.path.join(game_dir, "history.csv")
            self.update_index()
            return True
        except:
            return False

    # 从原始代码复制的游戏核心逻辑
    def add_new_tile(self):
        empty_cells = [(i, j) for i in range(self.grid_size)
                       for j in range(self.grid_size) if self.grid[i][j] == 0]
        if not empty_cells:
            return False
        i, j = random.choice(empty_cells)
        self.grid[i][j] = 2 if random.random() < 0.9 else 4
        return True

    def _merge_line(self, line):
        original = list(line)
        new_line = [num for num in line if num != 0]
        i = 0
        while i < len(new_line) - 1:
            if new_line[i] == new_line[i + 1]:
                new_line[i] *= 2
                self.score += new_line[i]
                new_line.pop(i + 1)
                new_line.append(0)
                i += 1
            i += 1
        new_line += [0] * (self.grid_size - len(new_line))
        return new_line, new_line != original

    def _move(self, direction):
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
        if any(2048 in row for row in self.grid):
            self.won = True
            self.update_index()

    def check_game_over(self):
        if any(0 in row for row in self.grid):
            return False
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1]:
                    return False
                if self.grid[j][i] == self.grid[j + 1][i]:
                    return False
        self.game_over = True
        self.update_index()
        self.best_score = max(self.best_score, self.score)
        self.save_best_score()
        return True


class TileLabel(QLabel):
    """游戏方块标签"""
    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self.value = value
        self.setAlignment(Qt.AlignCenter)
        self.update_tile()
        
    def set_value(self, value):
        self.value = value
        self.update_tile()
        
    def update_tile(self):
        # 设置方块颜色和文本
        colors = {
            0: (204, 192, 179),  # 空格子
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
        
        # 大于2048的方块颜色逐渐加深
        if self.value > 2048:
            color_level = min(255, 46 + (self.value // 2048) * 20)
            bg_color = (237, 194, color_level)
        else:
            bg_color = colors.get(self.value, (0, 0, 0))
        
        # 设置背景颜色
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(*bg_color))
        
        # 设置文本颜色
        if self.value <= 4:
            text_color = QColor(119, 110, 101)
        else:
            text_color = QColor(255, 255, 255)
        palette.setColor(QPalette.WindowText, text_color)
        
        self.setPalette(palette)
        
        # 设置字体大小
        font = self.font()
        if self.value < 100:
            font.setPointSize(24)
        elif self.value < 1000:
            font.setPointSize(20)
        else:
            font.setPointSize(16)
        font.setBold(True)
        self.setFont(font)
        
        # 设置边框
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(2)
        
        # 设置文本
        if self.value == 0:
            self.setText("")
        else:
            self.setText(str(self.value))
        
        # 设置固定大小
        self.setMinimumSize(80, 80)
        
    def animate(self):
        """方块出现时的动画效果"""
        animation = QPropertyAnimation(self, b"geometry")
        animation.setDuration(200)
        animation.setStartValue(QRect(self.x(), self.y(), 0, 0))
        animation.setEndValue(QRect(self.x(), self.y(), self.width(), self.height()))
        animation.setEasingCurve(QEasingCurve.OutBounce)
        animation.start()


class GameBoard(QWidget):
    """游戏主面板"""
    score_updated = pyqtSignal(int)
    game_over = pyqtSignal()
    game_won = pyqtSignal()
    
    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.game_core = GameCore(grid_size)
        self.tiles = []
        self.init_ui()
        
    def init_ui(self):
        # 设置主布局
        self.setStyleSheet("background-color: #bbada0;")
        
        # 创建网格布局
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        
        # 初始化方块
        self.tiles = []
        for i in range(self.grid_size):
            row = []
            for j in range(self.grid_size):
                tile = TileLabel()
                self.grid_layout.addWidget(tile, i, j)
                row.append(tile)
            self.tiles.append(row)
        
    def keyPressEvent(self, event):
        """处理键盘事件"""
        if self.game_core.game_over:
            return
        
        direction = None
        if event.key() == Qt.Key_Up or event.key() == Qt.Key_W:
            direction = 'up'
        elif event.key() == Qt.Key_Down or event.key() == Qt.Key_S:
            direction = 'down'
        elif event.key() == Qt.Key_Left or event.key() == Qt.Key_A:
            direction = 'left'
        elif event.key() == Qt.Key_Right or event.key() == Qt.Key_D:
            direction = 'right'
        
        if direction:
            direction_names = {
                'up': '向上',
                'down': '向下',
                'left': '向左',
                'right': '向右'
            }
            
            if self.game_core._move(direction):
                # 记录移动
                self.game_core.record_move(direction_names[direction])
                # 添加新方块
                self.game_core.add_new_tile()
                # 记录添加新方块后的状态
                self.game_core.record_move("添加新方块")
                # 更新界面
                self.update_board()
                # 检查游戏状态
                self.game_core.check_win()
                if self.game_core.won and not self.game_core.game_over:
                    self.game_won.emit()
                
                if self.game_core.check_game_over():
                    self.game_over.emit()
        
    def update_board(self):
        """更新游戏面板显示"""
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                self.tiles[i][j].set_value(self.game_core.grid[i][j])
        
        # 发送分数更新信号
        self.score_updated.emit(self.game_core.score)
        
        # 更新最高分
        if self.game_core.score > self.game_core.best_score:
            self.game_core.best_score = self.game_core.score
            self.game_core.save_best_score()
    
    def start_new_game(self):
        """开始新游戏"""
        self.game_core.start_new_game()
        self.update_board()
    
    def load_recent_game(self):
        """加载最近的游戏"""
        recent_game_id = self.game_core.get_recent_game()
        if recent_game_id and self.game_core.load_game_state(recent_game_id):
            self.update_board()
            return True
        return False
    
    def save_game(self):
        """保存当前游戏"""
        self.game_core.save_game_state()
        self.game_core.update_index()


class MainWindow(QMainWindow):
    """主窗口类"""
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        # 设置窗口标题和大小
        self.setWindowTitle("2048 游戏")
        self.setGeometry(300, 300, 500, 600)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 创建标题标签
        title_label = QLabel("2048")
        font = title_label.font()
        font.setPointSize(40)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setStyleSheet("color: #776e65;")
        
        # 创建分数显示区域
        score_layout = QHBoxLayout()
        
        # 当前分数
        self.score_label = QLabel()
        self.score_label.setText("分数\n0")
        self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setMinimumSize(100, 60)
        self.score_label.setStyleSheet("""
            background-color: #bbada0;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        """)
        
        # 最高分
        self.best_label = QLabel()
        self.best_label.setText("最高分\n0")
        self.best_label.setAlignment(Qt.AlignCenter)
        self.best_label.setMinimumSize(100, 60)
        self.best_label.setStyleSheet("""
            background-color: #bbada0;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        """)
        
        score_layout.addWidget(title_label)
        score_layout.addStretch()
        score_layout.addWidget(self.score_label)
        score_layout.addWidget(self.best_label)
        
        # 创建游戏面板
        self.game_board = GameBoard()
        self.game_board.score_updated.connect(self.update_score)
        self.game_board.game_over.connect(self.show_game_over)
        self.game_board.game_won.connect(self.show_game_won)
        
        # 创建按钮区域
        button_layout = QHBoxLayout()
        
        # 新游戏按钮
        new_game_button = QPushButton("新游戏")
        new_game_button.setMinimumSize(100, 40)
        new_game_button.setStyleSheet("""
            background-color: #8f7a66;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        """)
        new_game_button.clicked.connect(self.start_new_game)
        
        # 继续游戏按钮
        continue_button = QPushButton("继续游戏")
        continue_button.setMinimumSize(100, 40)
        continue_button.setStyleSheet("""
            background-color: #8f7a66;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        """)
        continue_button.clicked.connect(self.continue_game)
        
        button_layout.addStretch()
        button_layout.addWidget(new_game_button)
        button_layout.addWidget(continue_button)
        button_layout.addStretch()
        
        # 添加到主布局
        main_layout.addLayout(score_layout)
        main_layout.addWidget(self.game_board)
        main_layout.addLayout(button_layout)
        
        # 初始更新最高分
        self.update_best_score()
        
        # 检查是否有未完成的游戏
        self.check_recent_game()
    
    def update_score(self, score):
        """更新分数显示"""
        self.score_label.setText(f"分数\n{score}")
        
    def update_best_score(self):
        """更新最高分显示"""
        best_score = self.game_board.game_core.best_score
        self.best_label.setText(f"最高分\n{best_score}")
    
    def start_new_game(self):
        """开始新游戏"""
        self.game_board.start_new_game()
        self.update_best_score()
    
    def continue_game(self):
        """继续游戏"""
        if self.game_board.load_recent_game():
            self.update_best_score()
            QMessageBox.information(self, "成功", "已成功加载上一局游戏！")
        else:
            QMessageBox.information(self, "提示", "没有找到可继续的游戏！")
    
    def check_recent_game(self):
        """检查是否有未完成的游戏"""
        recent_game_id = self.game_board.game_core.get_recent_game()
        if recent_game_id:
            reply = QMessageBox.question(self, "继续游戏", 
                                        "检测到未完成的游戏，是否继续？",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            
            if reply == QMessageBox.Yes:
                self.continue_game()
            else:
                self.game_board.start_new_game()
        else:
            self.game_board.start_new_game()
    
    def show_game_over(self):
        """显示游戏结束对话框"""
        QMessageBox.information(self, "游戏结束", 
                               f"游戏结束！\n最终分数：{self.game_board.game_core.score}")
        self.update_best_score()
    
    def show_game_won(self):
        """显示游戏胜利对话框"""
        reply = QMessageBox.question(self, "恭喜胜利！", 
                                    "你已经达到2048！是否继续挑战更高分数？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        
        if reply == QMessageBox.No:
            self.start_new_game()
    
    def closeEvent(self, event):
        """关闭窗口时保存游戏状态"""
        self.game_board.save_game()
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()