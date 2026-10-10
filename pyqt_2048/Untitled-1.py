#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import random
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QGridLayout,
                             QLabel, QPushButton, QMessageBox, QVBoxLayout,
                             QHBoxLayout, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor

class GameCore:
    def __init__(self, grid_size=4):
        self.grid_size = grid_size
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.score = 0
        self.best_score = 0
        self.game_over = False
        self.won = False
        for _ in range(2):
            self.add_new_tile()
    
    def add_new_tile(self):
        empty_cells = [(i, j) for i in range(self.grid_size) for j in range(self.grid_size) if self.grid[i][j] == 0]
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
                self.best_score = max(self.best_score, self.score)
                new_line.pop(i + 1)
            i += 1
        new_line += [0] * (self.grid_size - len(new_line))
        return new_line, new_line != original
    
    def move(self, direction):
        if self.game_over:
            return False
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
        if moved:
            self.add_new_tile()
            self.check_win()
            self.check_game_over()
        return moved
    
    def check_win(self):
        if any(2048 in row for row in self.grid):
            self.won = True
    
    def check_game_over(self):
        if any(0 in row for row in self.grid):
            return False
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1] or self.grid[j][i] == self.grid[j + 1][i]:
                    return False
        self.game_over = True
        return True
    
    def reset(self):
        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        self.score = 0
        self.game_over = False
        self.won = False
        for _ in range(2):
            self.add_new_tile()

class TileLabel(QLabel):
    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        self.value = value
        self.setAlignment(Qt.AlignCenter)
        self.setAutoFillBackground(True)  # 使 QPalette.Window 底色真正填充方块背景
        self.update_tile()
        
    def set_value(self, value):
        self.value = value
        self.update_tile()
        
    def update_tile(self):
        colors = {
            0: (204, 192, 179),
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
        if self.value > 2048:
            color_level = min(255, 46 + (self.value // 2048) * 20)
            bg_color = (237, 194, color_level)
        else:
            bg_color = colors.get(self.value, (0, 0, 0))
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(*bg_color))
        text_color = QColor(119, 110, 101) if self.value <= 4 else QColor(255, 255, 255)
        palette.setColor(QPalette.WindowText, text_color)
        self.setPalette(palette)
        font = self.font()
        if self.value < 100:
            font.setPointSize(24)
        elif self.value < 1000:
            font.setPointSize(20)
        else:
            font.setPointSize(16)
        font.setBold(True)
        self.setFont(font)
        self.setFrameShape(QFrame.Panel)
        self.setFrameShadow(QFrame.Raised)
        self.setLineWidth(2)
        self.setText("" if self.value == 0 else str(self.value))
        self.setMinimumSize(80, 80)

class GameBoard(QWidget):
    score_updated = pyqtSignal(int, int)
    game_over = pyqtSignal()
    game_won = pyqtSignal()
    
    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.game_core = GameCore(grid_size)
        self.tiles = []
        self.init_ui()
        self.update_board()
        
    def init_ui(self):
        self.setStyleSheet("background-color: #bbada0;")
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.tiles = []
        for i in range(self.grid_size):
            row = []
            for j in range(self.grid_size):
                tile = TileLabel()
                self.grid_layout.addWidget(tile, i, j)
                row.append(tile)
            self.tiles.append(row)
        
    def keyPressEvent(self, event):
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
            if self.game_core.move(direction):
                self.update_board()
                if self.game_core.won and not self.game_core.game_over:
                    self.game_won.emit()
                elif self.game_core.game_over:
                    self.game_over.emit()
    
    def update_board(self):
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                self.tiles[i][j].set_value(self.game_core.grid[i][j])
        self.score_updated.emit(self.game_core.score, self.game_core.best_score)
    
    def start_new_game(self):
        self.game_core.reset()
        self.update_board()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("简单2048游戏")
        self.setGeometry(300, 300, 500, 600)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        title_label = QLabel("2048")
        font = title_label.font()
        font.setPointSize(40)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setStyleSheet("color: #776e65;")
        
        score_layout = QHBoxLayout()
        
        self.score_label = QLabel()
        self.score_label.setText("分数\n0")
        self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setMinimumSize(100, 60)
        self.score_label.setStyleSheet('''
            background-color: #bbada0;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        ''')
        
        self.best_label = QLabel()
        self.best_label.setText("最高分\n0")
        self.best_label.setAlignment(Qt.AlignCenter)
        self.best_label.setMinimumSize(100, 60)
        self.best_label.setStyleSheet('''
            background-color: #bbada0;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        ''')
        
        score_layout.addWidget(title_label)
        score_layout.addStretch()
        score_layout.addWidget(self.score_label)
        score_layout.addWidget(self.best_label)
        
        self.game_board = GameBoard()
        self.game_board.score_updated.connect(self.update_scores)
        self.game_board.game_over.connect(self.show_game_over)
        self.game_board.game_won.connect(self.show_game_won)
        
        button_layout = QHBoxLayout()
        new_game_button = QPushButton("新游戏")
        new_game_button.setMinimumSize(100, 40)
        new_game_button.setStyleSheet('''
            background-color: #8f7a66;
            color: #ffffff;
            font-size: 16px;
            font-weight: bold;
            border-radius: 5px;
            padding: 5px;
        ''')
        new_game_button.clicked.connect(self.start_new_game)
        
        button_layout.addStretch()
        button_layout.addWidget(new_game_button)
        button_layout.addStretch()
        
        main_layout.addLayout(score_layout)
        main_layout.addWidget(self.game_board)
        main_layout.addLayout(button_layout)
        
        self.game_board.setFocusPolicy(Qt.StrongFocus)
        self.game_board.setFocus()
    
    def update_scores(self, score, best_score):
        self.score_label.setText(f"分数\n{score}")
        self.best_label.setText(f"最高分\n{best_score}")
    
    def start_new_game(self):
        self.game_board.start_new_game()
        self.game_board.setFocus()
    
    def show_game_over(self):
        QMessageBox.information(self, "游戏结束", 
                               f"游戏结束！\n最终分数：{self.game_board.game_core.score}")
    
    def show_game_won(self):
        reply = QMessageBox.question(self, "恭喜胜利！", 
                                    "你已经达到2048！是否继续挑战更高分数？",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        
        if reply == QMessageBox.No:
            self.start_new_game()
        else:
            self.game_board.setFocus()

def main():
    app = QApplication(sys.argv)
    font = QFont("SimHei")
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()