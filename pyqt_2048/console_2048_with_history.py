#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
控制台版2048游戏（带历史记录功能）
"""

import random
import os
import msvcrt  # Windows下的键盘输入处理
import csv
import json
import datetime
import shutil

class Console2048WithHistory:
    def __init__(self, grid_size=4):
        """初始化游戏"""
        self.grid_size = grid_size  # 网格大小
        self.grid = [[0] * grid_size for _ in range(grid_size)]  # 初始化网格为0
        self.score = 0  # 当前分数
        self.best_score = 0  # 最高分
        self.game_over = False  # 是否游戏结束
        self.won = False  # 是否游戏胜利
        self.game_id = None  # 游戏ID
        self.history_file = None  # 历史记录文件路径
        self.history_writer = None  # CSV写入器
        self.history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_history")  # 历史记录目录
        self.current_move = 0  # 当前步数
        
        # 确保历史记录目录存在
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
            
        # 读取最高分
        self.load_best_score()

    def load_best_score(self):
        """加载最高分"""
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        if os.path.exists(best_score_file):
            try:
                with open(best_score_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.best_score = data.get('best_score', 0)
            except:
                pass

    def save_best_score(self):
        """保存最高分"""
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        try:
            with open(best_score_file, 'w', encoding='utf-8') as f:
                json.dump({'best_score': self.best_score}, f, ensure_ascii=False)
        except:
            pass

    def start_new_game(self):
        """开始新游戏"""
        # 生成游戏ID（基于时间戳）
        self.game_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # 创建游戏历史记录文件
        game_dir = os.path.join(self.history_dir, self.game_id)
        os.makedirs(game_dir, exist_ok=True)
        
        # 创建历史记录CSV文件
        self.history_file = os.path.join(game_dir, "history.csv")
        with open(self.history_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 写入表头：步数,操作类型,当前分数,网格状态（JSON格式）
            writer.writerow(["步数", "操作类型", "当前分数", "网格状态"])
        
        # 初始化游戏状态
        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        self.score = 0
        self.game_over = False
        self.won = False
        self.current_move = 0
        
        # 添加两个初始方块
        for _ in range(2):
            self.add_new_tile()
        
        # 记录初始状态
        self.record_move("初始状态")
        
        # 更新目录文档
        self.update_index()

    def record_move(self, move_type):
        """记录一步操作"""
        if not self.history_file:
            return
        
        # 增加步数
        self.current_move += 1
        
        # 记录到CSV文件
        with open(self.history_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 将网格转换为JSON字符串保存
            grid_json = json.dumps(self.grid, ensure_ascii=False)
            writer.writerow([self.current_move, move_type, self.score, grid_json])
        
        # 保存游戏状态用于恢复
        self.save_game_state()

    def save_game_state(self):
        """保存游戏完整状态用于恢复"""
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
        """更新目录文档"""
        index_file = os.path.join(self.history_dir, "index.json")
        
        # 读取现有索引
        index_data = []
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            except:
                index_data = []
        
        # 创建或更新当前游戏的索引条目
        game_info = {
            "game_id": self.game_id,
            "start_time": datetime.datetime.now().isoformat(),
            "score": self.score,
            "best_score": self.best_score,
            "is_completed": self.game_over or self.won,
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        # 检查是否已存在，存在则更新，不存在则添加
        existing_index = None
        for i, info in enumerate(index_data):
            if info["game_id"] == self.game_id:
                existing_index = i
                break
        
        if existing_index is not None:
            index_data[existing_index].update(game_info)
        else:
            index_data.append(game_info)
        
        # 保存索引文件
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def get_recent_game(self):
        """获取最近未完成的游戏"""
        index_file = os.path.join(self.history_dir, "index.json")
        
        if not os.path.exists(index_file):
            return None
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            # 找到最近的未完成游戏
            for game_info in sorted(index_data, key=lambda x: x.get("last_updated", ""), reverse=True):
                if not game_info.get("is_completed", False):
                    return game_info["game_id"]
            
            return None
        except:
            return None

    def load_game_state(self, game_id):
        """加载指定游戏ID的状态"""
        game_dir = os.path.join(self.history_dir, game_id)
        state_file = os.path.join(game_dir, "game_state.json")
        
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                game_state = json.load(f)
            
            # 恢复游戏状态
            self.game_id = game_id
            self.grid = game_state["grid"]
            self.score = game_state["score"]
            self.best_score = game_state["best_score"]
            self.game_over = game_state["game_over"]
            self.won = game_state["won"]
            self.current_move = game_state["current_move"]
            self.history_file = os.path.join(game_dir, "history.csv")
            
            # 更新索引
            self.update_index()
            
            return True
        except:
            return False

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
        if self.game_id:
            print(f"游戏ID: {self.game_id}")
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
            # 更新游戏状态
            self.update_index()

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
        # 更新游戏状态
        self.update_index()
        # 更新最高分
        self.best_score = max(self.best_score, self.score)
        self.save_best_score()
        return True

    def reset_game(self):
        """重置游戏"""
        # 更新最高分
        self.best_score = max(self.best_score, self.score)
        self.save_best_score()
        
        # 更新当前游戏状态为已完成
        self.game_over = True
        self.update_index()
        
        # 开始新游戏
        self.start_new_game()

    # ========= 输入与控制 =========
    def get_key(self):
        """获取键盘输入"""
        while True:
            key = msvcrt.getch()
            if key in (b'\xe0', b'\x00'):
                key = msvcrt.getch()
                return {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right'}.get(key.decode(), None)
            key_map = {'w': 'up', 's': 'down', 'a': 'left', 'd': 'right', 'q': 'quit'}
            ch = key.decode().lower()
            if ch in key_map:
                return key_map[ch]

    def check_and_load_recent_game(self):
        """检查并加载最近的未完成游戏"""
        recent_game_id = self.get_recent_game()
        if recent_game_id:
            print("检测到未完成的游戏！")
            print("1. 继续上一局")
            print("2. 新开一局")
            
            while True:
                choice = msvcrt.getch().decode().strip()
                if choice == '1':
                    if self.load_game_state(recent_game_id):
                        print("已成功加载上一局游戏！")
                        return True
                    else:
                        print("加载失败，开始新游戏...")
                        self.start_new_game()
                        return False
                elif choice == '2':
                    self.start_new_game()
                    return False
        else:
            # 没有未完成的游戏，开始新游戏
            self.start_new_game()
            return False

    # ========= 主循环 =========
    def run(self):
        """运行游戏主循环"""
        # 检查是否有未完成的游戏
        self.check_and_load_recent_game()
        
        try:
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
                    # 保存当前状态
                    self.save_game_state()
                    self.update_index()
                    print("感谢游玩！游戏状态已保存，下次可以继续。")
                    break

                if key in ('up', 'down', 'left', 'right'):  # 处理用户移动
                    direction_names = {
                        'up': '向上',
                        'down': '向下',
                        'left': '向左',
                        'right': '向右'
                    }
                    
                    if self._move(key):  # 如果移动成功
                        # 记录移动
                        self.record_move(direction_names[key])
                        # 添加新方块
                        self.add_new_tile()
                        # 记录添加新方块后的状态
                        self.record_move("添加新方块")
        except KeyboardInterrupt:
            # 捕获Ctrl+C，保存游戏状态
            self.save_game_state()
            self.update_index()
            print("\n游戏状态已保存，下次可以继续。")
        finally:
            # 确保最高分已保存
            self.save_best_score()


if __name__ == "__main__":
    print("2048 控制台版游戏（带历史记录功能）")
    print("使用方向键或 WASD 键移动方块，按 'Q' 退出游戏")
    input("按回车键开始游戏...")
    game = Console2048WithHistory()
    game.run()
    