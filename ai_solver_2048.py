# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# 2048游戏AI求解器
# 使用Expectimax算法和启发式评估函数自动玩2048游戏
# """

# import time
# import copy
# import math
# import random
# import os
# import sys

# # 添加当前目录到Python路径，确保可以导入console_2048_with_history
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# class AI2048Solver:
#     def __init__(self, game=None, max_depth=3, max_time=0.05):
#         """
#         初始化AI求解器
#         :param game: 2048游戏实例
#         :param max_depth: 搜索最大深度
#         :param max_time: 每次决策的最大时间（秒）
#         """
#         self.game = game
#         self.max_depth = max_depth
#         self.max_time = max_time
#         self.directions = ['up', 'down', 'left', 'right']
#         self.direction_names = {
#             'up': '向上',
#             'down': '向下',
#             'left': '向左',
#             'right': '向右'
#         }
#         self.move_count = 0
#         self.start_time = 0
#         self.timeout = False
    
#     def set_game(self, game):
#         """设置游戏实例"""
#         self.game = game
    
#     def find_best_move(self):
#         """
#         查找最佳移动
#         :return: 最佳移动方向
#         """
#         self.start_time = time.time()
#         self.timeout = False
        
#         best_score = -float('inf')
#         best_move = None
        
#         # 对每个可能的移动方向进行评估
#         for direction in self.directions:
#             # 复制游戏状态进行模拟
#             game_copy = self._copy_game_state()
            
#             # 尝试移动
#             moved = self._simulate_move(game_copy, direction)
#             if not moved:
#                 continue
            
#             # 使用Expectimax算法评估该移动
#             score = self._expectimax(game_copy, self.max_depth - 1, False)
            
#             # 更新最佳移动
#             if score > best_score:
#                 best_score = score
#                 best_move = direction
        
#         # 如果没有找到有效移动，返回一个随机方向
#         if best_move is None:
#             best_move = random.choice(self.directions)
        
#         self.move_count += 1
#         return best_move
    
#     def _expectimax(self, game_state, depth, is_max_turn):
#         """
#         Expectimax搜索算法
#         :param game_state: 游戏状态
#         :param depth: 当前搜索深度
#         :param is_max_turn: 是否是最大玩家回合
#         :return: 评估分数
#         """
#         # 检查是否超时
#         if time.time() - self.start_time > self.max_time:
#             self.timeout = True
#             return 0
        
#         # 达到最大深度或游戏结束，返回启发式评估
#         if depth == 0 or self._is_game_over(game_state):
#             return self._evaluate_board(game_state)
        
#         if is_max_turn:
#             # 最大玩家回合（AI移动）
#             max_score = -float('inf')
#             for direction in self.directions:
#                 game_copy = copy.deepcopy(game_state)
#                 moved = self._simulate_move(game_copy, direction)
#                 if moved:
#                     score = self._expectimax(game_copy, depth - 1, False)
#                     max_score = max(max_score, score)
#                     if self.timeout:
#                         break
#             return max_score if max_score != -float('inf') else -1000
#         else:
#             # 机会节点（随机生成新方块）
#             empty_cells = self._get_empty_cells(game_state)
#             if not empty_cells:
#                 return self._evaluate_board(game_state)
            
#             total_score = 0
#             count = 0
            
#             # 对每个空位置模拟放置2或4
#             for cell in empty_cells:
#                 # 90%概率放置2，10%概率放置4
#                 # 放置2
#                 game_copy_2 = copy.deepcopy(game_state)
#                 game_copy_2[cell[0]][cell[1]] = 2
#                 score_2 = self._expectimax(game_copy_2, depth - 1, True)
#                 total_score += score_2 * 0.9
                
#                 # 放置4
#                 game_copy_4 = copy.deepcopy(game_state)
#                 game_copy_4[cell[0]][cell[1]] = 4
#                 score_4 = self._expectimax(game_copy_4, depth - 1, True)
#                 total_score += score_4 * 0.1
                
#                 count += 1
                
#                 if self.timeout:
#                     break
            
#             return total_score / count if count > 0 else 0
    
#     def _evaluate_board(self, grid):
#         """
#         启发式评估函数
#         考虑因素：单调性、平滑性、空格数量、高分块位置、边缘行/列
#         :param grid: 游戏网格
#         :return: 评估分数
#         """
#         grid_size = len(grid)
        
#         # 1. 单调性 - 数字从高到低排列
#         monotonicity = self._calculate_monotonicity(grid)
        
#         # 2. 平滑性 - 相邻数字的差异
#         smoothness = self._calculate_smoothness(grid)
        
#         # 3. 空格数量
#         empty_cells = len(self._get_empty_cells(grid))
        
#         # 4. 高分块位置（角落优先）
#         max_tile = max(max(row) for row in grid)
#         max_tile_bonus = 0
#         if max_tile > 0:
#             # 检查最高分是否在角落
#             corners = [(0, 0), (0, grid_size-1), (grid_size-1, 0), (grid_size-1, grid_size-1)]
#             for i, j in corners:
#                 if grid[i][j] == max_tile:
#                     max_tile_bonus = max_tile * 2
#                     break
        
#         # 5. 边缘行/列上的大数
#         edge_bonus = self._calculate_edge_bonus(grid)
        
#         # 6. 加权总和
#         score = (
#             empty_cells * 1000 +  # 空格最重要
#             monotonicity * 100 +  # 单调性次重要
#             smoothness * 10 +     # 平滑性
#             max_tile_bonus +      # 高分块在角落的奖励
#             edge_bonus +          # 边缘行/列的奖励
#             max_tile              # 最高分本身
#         )
        
#         return score
    
#     def _calculate_monotonicity(self, grid):
#         """计算单调性：数字是否按照从高到低的顺序排列"""
#         grid_size = len(grid)
        
#         # 检查从左上到右下的单调递减趋势
#         monotonicity = 0
        
#         # 检查行单调性（左到右递减）
#         for row in grid:
#             for j in range(grid_size - 1):
#                 if row[j] >= row[j + 1]:
#                     monotonicity += row[j] - row[j + 1]
#                 else:
#                     monotonicity -= (row[j + 1] - row[j]) * 2  # 逆序惩罚更重
        
#         # 检查列单调性（上到下递减）
#         for j in range(grid_size):
#             for i in range(grid_size - 1):
#                 if grid[i][j] >= grid[i + 1][j]:
#                     monotonicity += grid[i][j] - grid[i + 1][j]
#                 else:
#                     monotonicity -= (grid[i + 1][j] - grid[i][j]) * 2  # 逆序惩罚更重
        
#         return monotonicity
    
#     def _calculate_smoothness(self, grid):
#         """计算平滑性：相邻数字的差异"""
#         grid_size = len(grid)
#         smoothness = 0
        
#         # 检查水平相邻
#         for row in grid:
#             for j in range(grid_size - 1):
#                 if row[j] != 0 and row[j + 1] != 0:
#                     # 使用对数减少大数的影响
#                     smoothness -= abs(math.log2(row[j]) - math.log2(row[j + 1]))
        
#         # 检查垂直相邻
#         for j in range(grid_size):
#             for i in range(grid_size - 1):
#                 if grid[i][j] != 0 and grid[i + 1][j] != 0:
#                     smoothness -= abs(math.log2(grid[i][j]) - math.log2(grid[i + 1][j]))
        
#         return smoothness
    
#     def _calculate_edge_bonus(self, grid):
#         """计算边缘行/列上大数的奖励"""
#         grid_size = len(grid)
#         edge_bonus = 0
        
#         # 检查第一行和最后一行
#         for row in [0, grid_size - 1]:
#             for j in range(grid_size):
#                 edge_bonus += grid[row][j] * 0.5
        
#         # 检查第一列和最后一列（排除已经计算的角落）
#         for j in [0, grid_size - 1]:
#             for row in range(1, grid_size - 1):
#                 edge_bonus += grid[row][j] * 0.3
        
#         return edge_bonus
    
#     def _copy_game_state(self):
#         """复制游戏状态"""
#         return copy.deepcopy(self.game.grid)
    
#     def _simulate_move(self, grid, direction):
#         """
#         模拟移动
#         :param grid: 游戏网格
#         :param direction: 移动方向
#         :return: 是否成功移动
#         """
#         grid_size = len(grid)
#         original = copy.deepcopy(grid)
#         moved = False
        
#         # 转置网格以处理上下移动
#         if direction in ('up', 'down'):
#             grid = [list(row) for row in zip(*grid)]
        
#         # 处理每一行
#         for i in range(grid_size):
#             # 如果是向右或向下，反转行
#             if direction in ('right', 'down'):
#                 grid[i] = grid[i][::-1]
            
#             # 合并相同数字
#             new_row = [num for num in grid[i] if num != 0]
#             j = 0
#             while j < len(new_row) - 1:
#                 if new_row[j] == new_row[j + 1]:
#                     new_row[j] *= 2
#                     new_row.pop(j + 1)
#                     new_row.append(0)
#                     j += 1
#                 j += 1
            
#             # 填充零
#             new_row += [0] * (grid_size - len(new_row))
            
#             # 如果是向右或向下，再反转回来
#             if direction in ('right', 'down'):
#                 new_row = new_row[::-1]
            
#             grid[i] = new_row
        
#         # 转回原方向
#         if direction in ('up', 'down'):
#             grid = [list(row) for row in zip(*grid)]
        
#         # 检查是否移动成功
#         for i in range(grid_size):
#             for j in range(grid_size):
#                 if grid[i][j] != original[i][j]:
#                     moved = True
#                     break
#             if moved:
#                 break
        
#         return moved
    
#     def _get_empty_cells(self, grid):
#         """获取所有空单元格位置"""
#         empty_cells = []
#         for i in range(len(grid)):
#             for j in range(len(grid[i])):
#                 if grid[i][j] == 0:
#                     empty_cells.append((i, j))
#         return empty_cells
    
#     def _is_game_over(self, grid):
#         """检查游戏是否结束"""
#         # 如果有空单元格，游戏未结束
#         if self._get_empty_cells(grid):
#             return False
        
#         grid_size = len(grid)
#         # 检查是否有可合并的相邻单元格
#         for i in range(grid_size):
#             for j in range(grid_size - 1):
#                 if grid[i][j] == grid[i][j + 1]:
#                     return False
#                 if grid[j][i] == grid[j + 1][i]:
#                     return False
        
#         return True

# def run_ai_solver():
#     """
#     运行AI求解器，调用console_2048_with_history.py
#     """
#     print("启动2048游戏AI求解器...")
#     print("注意：这个脚本需要先运行游戏主程序才能控制游戏")
#     print("请按Ctrl+C退出")
    
#     try:
#         # 尝试导入游戏类
#         from console_2048_with_history import Console2048WithHistory
        
#         # 创建游戏实例
#         game = Console2048WithHistory()
#         # 创建AI求解器实例，设置搜索深度和思考时间
#         ai = AI2048Solver(game, max_depth=3, max_time=0.05)
        
#         print("AI求解器已初始化，开始游戏...")
#         print("按Ctrl+C随时退出")
        
#         # 开始新游戏
#         game.start_new_game()
        
#         # 主游戏循环
#         try:
#             while True:
#                 # 显示游戏状态
#                 game.display_grid()
                
#                 # 检查游戏状态
#                 game.check_win()
#                 if game.check_game_over():
#                     print(f"\n游戏结束！最终分数: {game.score}")
#                     print(f"AI执行了 {ai.move_count} 步")
#                     break
                
#                 # AI寻找最佳移动
#                 best_move = ai.find_best_move()
#                 print(f"AI选择的移动: {ai.direction_names[best_move]} (步数: {ai.move_count})")
                
#                 # 执行移动
#                 if game._move(best_move):
#                     # 记录移动
#                     game.record_move(ai.direction_names[best_move])
#                     # 添加新方块
#                     game.add_new_tile()
#                     # 记录添加新方块后的状态
#                     game.record_move("添加新方块")
                
#                 # 短暂延迟，让用户可以看到游戏进展
#                 time.sleep(0.1)
                
#         except KeyboardInterrupt:
#             # 保存游戏状态
#             game.save_game_state()
#             game.update_index()
#             print("\nAI求解已停止，游戏状态已保存")
        
#     except ImportError:
#         print("错误：无法导入console_2048_with_history模块")
#         print("请确保console_2048_with_history.py文件在同一目录下")
#     except Exception as e:
#         print(f"发生错误: {e}")

# if __name__ == "__main__":
#     run_ai_solver()

# # 为了方便直接调用，提供一个函数接口
# def solve_2048_automatically(game_instance=None, max_depth=3, max_time=0.05, delay=0.1):
#     """
#     自动求解2048游戏的函数接口
    
#     :param game_instance: 已有的游戏实例，如果为None则创建新实例
#     :param max_depth: AI搜索深度
#     :param max_time: 每次决策的最大时间（秒）
#     :param delay: 每步移动后的延迟时间（秒），用于可视化
#     :return: 游戏最终分数
#     """
#     from console_2048_with_history import Console2048WithHistory
    
#     # 如果没有提供游戏实例，创建一个新的
#     if game_instance is None:
#         game = Console2048WithHistory()
#         game.start_new_game()
#     else:
#         game = game_instance
    
#     # 创建AI求解器
#     ai = AI2048Solver(game, max_depth=max_depth, max_time=max_time)
    
#     try:
#         while True:
#             # 显示游戏状态
#             game.display_grid()
            
#             # 检查游戏状态
#             game.check_win()
#             if game.check_game_over():
#                 break
            
#             # AI寻找最佳移动
#             best_move = ai.find_best_move()
            
#             # 执行移动
#             if game._move(best_move):
#                 game.record_move(ai.direction_names[best_move])
#                 game.add_new_tile()
#                 game.record_move("添加新方块")
            
#             # 延迟
#             time.sleep(delay)
            
#     except KeyboardInterrupt:
#         game.save_game_state()
#         game.update_index()
    
#     return game.score
    