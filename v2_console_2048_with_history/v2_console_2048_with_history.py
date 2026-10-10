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
        self.game_start_time = None  # 游戏开始时间
        self.history_file = None  # 历史记录文件路径
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
            except (json.JSONDecodeError, IOError) as e:
                # 记录错误但继续运行
                pass

    def save_best_score(self):
        """保存最高分"""
        best_score_file = os.path.join(self.history_dir, "best_score.json")
        try:
            with open(best_score_file, 'w', encoding='utf-8') as f:
                json.dump({'best_score': self.best_score}, f, ensure_ascii=False)
        except IOError as e:
            # 记录错误但继续运行
            pass

    def start_new_game(self):
        """开始新游戏"""
        # 生成游戏ID（基于时间戳）
        self.game_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        # 记录游戏开始时间
        self.game_start_time = datetime.datetime.now()
        
        # 创建游戏历史记录文件
        game_dir = os.path.join(self.history_dir, self.game_id)
        os.makedirs(game_dir, exist_ok=True)
        
        # 创建历史记录CSV文件
        self.history_file = os.path.join(game_dir, "history.csv")
        with open(self.history_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 写入表头：步数,操作类型,当前分数,操作得分,移动后的网格状态,随机添加后的网格状态
            writer.writerow(["步数", "操作类型", "操作得分", "总分", "移动后的网格状态", "随机添加后的网格状态"])

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
        self.record_move("初始状态", 0, self.grid, self.grid)
        
        # 更新目录文档
        self.update_index()

    def record_move(self, move_type, move_score, after_move_grid, after_add_tile_grid):
        """记录一步操作"""
        if not self.history_file:
            return
        
        # 增加步数
        self.current_move += 1
        
        # 记录到CSV文件
        with open(self.history_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 将网格转换为JSON字符串保存
            after_move_grid_json = json.dumps(after_move_grid, ensure_ascii=False)
            after_add_tile_grid_json = json.dumps(after_add_tile_grid, ensure_ascii=False)
            writer.writerow([self.current_move, move_type, move_score, self.score, after_move_grid_json, after_add_tile_grid_json])
        
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
        except IOError as e:
            # 记录错误但继续运行
            pass

    def update_index(self, is_completed=None):
        """更新目录文档"""
        if not self.game_id or not self.game_start_time:  # 确保游戏ID和开始时间存在
            return
        
        # 更新最高分
        if self.score > self.best_score:
            self.best_score = self.score
            self.save_best_score()
        
        index_file = os.path.join(self.history_dir, "index.json")
        
        # 读取现有索引
        index_data = []
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                index_data = []
        
        # 确定is_completed状态：如果传入了参数则使用传入的值，否则使用游戏当前状态
        completed_status = is_completed if is_completed is not None else (self.game_over or self.won)
        
        # 创建或更新当前游戏的索引条目
        game_info = {
            "game_id": self.game_id,
            "start_time": self.game_start_time.isoformat(),  # 使用游戏开始时的时间
            "score": self.score,
            "best_score": self.best_score,
            "is_completed": completed_status,
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
        except IOError as e:
            # 记录错误但继续运行
            pass
            
    def mark_game_completed(self, game_id):
        """把指定对局在索引中标记为已完成（用于用户放弃续玩时结算旧档）"""
        if not game_id:
            return
        index_file = os.path.join(self.history_dir, "index.json")
        if not os.path.exists(index_file):
            return
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            for info in index_data:
                if info.get('game_id') == game_id:
                    info['is_completed'] = True
                    info['last_updated'] = datetime.datetime.now().isoformat()
                    break
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, IOError) as e:
            # 记录错误但继续运行
            pass

    def get_last_unfinished_game(self):
        """获取最后一个未完成且非游戏结束状态的游戏信息（活档）"""
        index_file = os.path.join(self.history_dir, "index.json")
        if not os.path.exists(index_file):
            return None
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
                
            # 筛选真正的活档：未完成的游戏
            unfinished_games = [game for game in index_data if not game.get('is_completed', False)]
            if not unfinished_games:
                return None
                
            # 按最后更新时间排序，获取最新的未完成游戏
            unfinished_games.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
            return unfinished_games[0]
        except (json.JSONDecodeError, IOError) as e:
            return None
            
    def load_game_state(self, game_id):
        """加载指定游戏ID的游戏状态"""
        game_dir = os.path.join(self.history_dir, game_id)
        state_file = os.path.join(game_dir, "game_state.json")
        
        if not os.path.exists(state_file):
            return False
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                game_state = json.load(f)
                
            # 恢复游戏状态
            self.game_id = game_id
            self.grid = game_state.get('grid', [[0] * self.grid_size for _ in range(self.grid_size)])
            self.score = game_state.get('score', 0)
            self.best_score = game_state.get('best_score', 0)
            self.game_over = game_state.get('game_over', False)
            self.won = game_state.get('won', False)
            self.current_move = game_state.get('current_move', 0)
            
            # 更新历史文件路径
            self.history_file = os.path.join(game_dir, "history.csv")
            
            # 从索引中获取游戏开始时间
            index_file = os.path.join(self.history_dir, "index.json")
            if os.path.exists(index_file):
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                    for game in index_data:
                        if game.get('game_id') == game_id:
                            start_time_str = game.get('start_time', datetime.datetime.now().isoformat())
                            self.game_start_time = datetime.datetime.fromisoformat(start_time_str)
                            break
            
            if not self.game_start_time:
                self.game_start_time = datetime.datetime.now()
                
            return True
        except (json.JSONDecodeError, IOError, ValueError) as e:
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

        print("使用方向键或 WASD 键移动方块，'Q' 退出游戏")
        if self.won:
            print("恭喜你赢了！继续挑战更高分数！")
        elif self.game_over:
            print("游戏结束！按任意键重新开始")

    def _merge_line(self, line):
        """合并单行（核心算法），返回新行与是否移动标志"""
        original = list(line)
        compressed = [num for num in line if num != 0]

        merged = []
        i = 0
        while i < len(compressed):
            if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
                merged.append(compressed[i] * 2)
                self.score += compressed[i] * 2
                i += 2          # 合并后一次跳过两个元素，避免 [x, x, x, x] 下标错位
            else:
                merged.append(compressed[i])
                i += 1

        merged += [0] * (self.grid_size - len(merged))
        return merged, merged != original

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

    def get_key(self):
        """获取键盘输入"""
        key_map = {'w': 'up', 's': 'down', 'a': 'left', 'd': 'right', 'q': 'quit'}  # 定义按键映射
        arrow_map = {'H': 'up', 'P': 'down', 'K': 'left', 'M': 'right'}  # 方向键后缀映射
        while True:
            key = msvcrt.getch()  # 获取用户输入
            if key in (b'\xe0', b'\x00'):  # 方向键前缀，再读一个字节
                ext = msvcrt.getch().decode('utf-8', errors='ignore')
                if ext in arrow_map:
                    return arrow_map[ext]
                continue
            ch = key.decode('utf-8', errors='ignore').lower()  # 安全解码，忽略无法解析的字节
            if ch in key_map:
                return key_map[ch]

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

    def run(self):
        """运行游戏主循环"""
        # 检查是否有未完成的游戏
        last_unfinished = self.get_last_unfinished_game()
        if last_unfinished:
            print(f"检测到未完成的游戏：")
            print(f"游戏ID: {last_unfinished.get('game_id')}")
            print(f"开始时间: {last_unfinished.get('start_time')}")
            print(f"当前分数: {last_unfinished.get('score')}")
            print(f"最高分: {last_unfinished.get('best_score')}")
            print(f"最后更新: {last_unfinished.get('last_updated')}")
            print()
            
            # 询问用户是否继续
            while True:
                print("是否继续上一把游戏？ (y/n): ")
                choice = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                print(choice)
                if choice == 'y':
                    # 尝试加载游戏状态
                    if self.load_game_state(last_unfinished.get('game_id')):
                        print("游戏加载成功！")
                        input("按回车键继续...")
                        break
                    else:
                        print("游戏加载失败，开始新游戏。")
                        self.start_new_game()
                        break
                elif choice == 'n':
                    # 放弃续玩，把旧对局标记为已结束，避免下次启动再次被当作可续玩的活档
                    self.mark_game_completed(last_unfinished.get('game_id'))
                    self.start_new_game()  # 开始新游戏
                    break
        else:
            self.start_new_game()  # 没有未完成游戏，直接开始新游戏
        
        while True:
            # 显示网格
            self.display_grid()  # 显示当前状态
            self.check_win()  # 检查是否赢了

            # 检查是否游戏结束
            if self.check_game_over():  # 如果游戏结束
                self.display_grid()  # 显示最终状态
                # 更新索引标记为已完成
                self.update_index(is_completed=True)
                input("按回车键重新开始...")
                self.start_new_game()  # 重置游戏
                continue

            # 获取用户输入
            key = self.get_key() 
            if key == 'quit':  # 如果用户选择退出
                print("感谢游玩！再见！")
                # 退出时更新索引，标记为未完成
                self.update_index(is_completed=False)
                break

            if key in ('up', 'down', 'left', 'right'):  # 处理用户移动
                previous_score = self.score  # 记录移动前的分数
                if self._move(key):  # 如果移动成功
                    after_move_grid = [row.copy() for row in self.grid]  # 移动后的网格（尚未添加新方块）
                    self.add_new_tile()  # 添加新方块
                    move_score = self.score - previous_score  # 计算本次移动获得的分数
                    self.record_move(f"向{key}移动", move_score, after_move_grid, self.grid)
                    # 更新索引文件中的分数信息
                    self.update_index()

if __name__ == "__main__": 
    print("2048 控制台版游戏") 
    print("使用方向键或 WASD 键移动方块，按 'Q' 退出游戏") 
    input("按回车键开始游戏...") 
    game = Console2048WithHistory()  # 初始化游戏实例
    game.run()  # 运行游戏
    