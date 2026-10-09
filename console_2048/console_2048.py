#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
控制台版2048游戏
"""

import random
import os
import msvcrt  # Windows下的键盘输入处理

class Console2048:
    def __init__(self, grid_size=4):
        """初始化游戏"""
        self.grid_size = grid_size  # 网格大小
        self.grid = [[0] * grid_size for _ in range(grid_size)]  # 初始化网格为0
        self.score = 0  # 当前分数
        self.best_score = 0  # 最高分
        self.game_over = False  # 是否游戏结束
        self.won = False  # 是否游戏胜利

        # 初始化游戏，添加两个方块
        for _ in range(2):
            self.add_new_tile()  # 添加新方块

    def add_new_tile(self):
        """在随机空位置添加新方块（2或4）"""
        # 找到所有空位置
        empty_cells = [(i, j) for i in range(self.grid_size)
                       for j in range(self.grid_size) if self.grid[i][j] == 0]
        if not empty_cells:  # 如果没有空位置
            return False
        i, j = random.choice(empty_cells)  # 随机选择一个空位置
        self.grid[i][j] = 2 if random.random() < 0.9 else 4  # 90%概率是2，10%概率是4
        return True

    def display_grid(self):
        """在控制台显示游戏网格"""
        os.system('cls' if os.name == 'nt' else 'clear')

        print("=" * 30)
        print(" " * 10 + "2048 游戏" + " " * 10)
        print("=" * 30)
        print(f"分数: {self.score:<8}最高分: {self.best_score}")
        print("-" * 30)

        # 显示网格
        for row in self.grid:  # 遍历每一行
            # 格式化显示每一个方块
            row_str = "|".join(f"{val:^6}" if val else " " * 6 for val in row)
            print(f"|{row_str}|")
            print("-" * 30)

        print("使用方向键或 WASD 移动方块，'Q' 退出游戏")
        if self.won:
            print("恭喜你赢了！继续挑战更高分数！")
        elif self.game_over:
            print("游戏结束！按任意键重新开始")

    # ========= 移动与合并逻辑 =========
    def _merge_line(self, line):
        """合并单行（核心算法），返回新行与是否移动标志"""
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
        """通用移动逻辑（方向: up/down/left/right）"""
        moved = False
        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]  # 转置
        for i in range(self.grid_size):
            row = self.grid[i][::-1] if direction in ('right', 'down') else self.grid[i]
            new_row, has_moved = self._merge_line(row)
            if direction in ('right', 'down'):
                new_row.reverse()
            self.grid[i] = new_row
            moved = moved or has_moved
        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]  # 还原
        return moved

    # ========= 状态检测 =========
    def check_win(self):
        """检查是否有 2048 方块"""
        if any(2048 in row for row in self.grid):
            self.won = True

    def check_game_over(self):
        """检查是否无法移动"""
        if any(0 in row for row in self.grid):
            return False
        for i in range(self.grid_size):
            for j in range(self.grid_size - 1):
                if self.grid[i][j] == self.grid[i][j + 1]:
                    return False
                if self.grid[j][i] == self.grid[j + 1][i]:
                    return False
        self.game_over = True
        return True

    def reset_game(self):
        """重置游戏"""
        self.best_score = max(self.best_score, self.score)
        self.score = 0
        self.game_over = self.won = False
        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        for _ in range(2):
            self.add_new_tile()

    # ========= 输入与控制 =========
    def get_key(self):
        """获取键盘输入"""
        while True:
            key = msvcrt.getch()  # 获取用户输入
            if key in (b'\xe0', b'\x00'):  # 方向键前缀
                key = msvcrt.getch()
                return {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right'}.get(key.decode(), None)  # 映射方向键
            key_map = {'w': 'up', 's': 'down', 'a': 'left', 'd': 'right', 'q': 'quit'}  # 定义按键映射
            ch = key.decode().lower()  # 转换为小写字母
            if ch in key_map:
                return key_map[ch]

    # ========= 主循环 =========
    def run(self):
        """运行游戏主循环"""
        while True:
            # 显示网格
            self.display_grid()  # 显示当前状态
            self.check_win()  # 检查是否赢了

            # 检查是否游戏结束
            if self.check_game_over():  # 如果游戏结束
                self.display_grid()  # 显示最终状态
                input("按回车键重新开始...")
                self.reset_game()  # 重置游戏
                continue

            # 获取用户输入
            key = self.get_key() 
            if key == 'quit':  # 如果用户选择退出
                print("感谢游玩！再见！")
                break

            if key in ('up', 'down', 'left', 'right'):  # 处理用户移动
                if self._move(key):  # 如果移动成功
                    self.add_new_tile()  # 添加新方块


if __name__ == "__main__":
    print("2048 控制台版游戏")
    print("使用方向键或 WASD 键移动方块，按 'Q' 退出游戏")
    input("按回车键开始游戏...")
    Console2048().run()
