#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048游戏AI求解器
使用Expectimax算法和启发式评估函数自动玩2048游戏
"""

import time
import copy
import math
import random
import os
import sys

# 添加当前目录与 v2_console_2048_with_history 子目录到 Python 路径，
# 确保可以导入 Console2048WithHistory（其源码位于同级子目录中）
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONSOLE_DIR = os.path.join(_HERE, "v2_console_2048_with_history")
for _p in (_HERE, _CONSOLE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class AI2048Solver:
    def __init__(self, game=None, max_depth=3, max_time=0.05):
        """
        初始化AI求解器
        :param game: 2048游戏实例
        :param max_depth: 搜索最大深度
        :param max_time: 每次决策的最大时间（秒）
        """
        self.game = game
        self.max_depth = max_depth
        self.max_time = max_time
        self.directions = ['up', 'down', 'left', 'right']
        self.direction_names = {
            'up': '向上',
            'down': '向下',
            'left': '向左',
            'right': '向右'
        }
        self.move_count = 0
        self.start_time = 0
        self.timeout = False

    def set_game(self, game):
        """设置游戏实例"""
        self.game = game

    def find_best_move(self):
        """
        查找最佳移动
        :return: 最佳移动方向
        """
        self.start_time = time.time()
        self.timeout = False

        best_score = -float('inf')
        best_move = None

        # 对每个可能的移动方向进行评估
        for direction in self.directions:
            # 复制游戏状态进行模拟
            game_copy = self._copy_game_state()

            # 尝试移动
            moved = self._simulate_move(game_copy, direction)
            if not moved:
                continue

            # 使用Expectimax算法评估该移动
            score = self._expectimax(game_copy, self.max_depth - 1, False)

            # 更新最佳移动
            if score > best_score:
                best_score = score
                best_move = direction

        # 如果没有找到有效移动，返回一个随机方向
        if best_move is None:
            best_move = random.choice(self.directions)

        self.move_count += 1
        return best_move

    def _expectimax(self, game_state, depth, is_max_turn):
        """
        Expectimax搜索算法
        :param game_state: 游戏状态
        :param depth: 当前搜索深度
        :param is_max_turn: 是否是最大玩家回合
        :return: 评估分数
        """
        # 检查是否超时
        if time.time() - self.start_time > self.max_time:
            self.timeout = True
            return self._evaluate_board(game_state)

        # 达到最大深度或游戏结束，返回启发式评估
        if depth == 0 or self._is_game_over(game_state):
            return self._evaluate_board(game_state)

        if is_max_turn:
            # 最大玩家回合（AI移动）
            max_score = -float('inf')
            for direction in self.directions:
                game_copy = copy.deepcopy(game_state)
                moved = self._simulate_move(game_copy, direction)
                if moved:
                    score = self._expectimax(game_copy, depth - 1, False)
                    max_score = max(max_score, score)
                    if self.timeout:
                        break
            return max_score if max_score != -float('inf') else -1000
        else:
            # 机会节点（随机生成新方块）
            empty_cells = self._get_empty_cells(game_state)
            if not empty_cells:
                return self._evaluate_board(game_state)

            total_score = 0
            count = 0

            # 对每个空位置模拟放置2或4
            for cell in empty_cells:
                # 90%概率放置2，10%概率放置4
                # 放置2
                game_copy_2 = copy.deepcopy(game_state)
                game_copy_2[cell[0]][cell[1]] = 2
                score_2 = self._expectimax(game_copy_2, depth - 1, True)
                total_score += score_2 * 0.9

                # 放置4
                game_copy_4 = copy.deepcopy(game_state)
                game_copy_4[cell[0]][cell[1]] = 4
                score_4 = self._expectimax(game_copy_4, depth - 1, True)
                total_score += score_4 * 0.1

                count += 1

                if self.timeout:
                    break

            return total_score / count if count > 0 else 0

    def _evaluate_board(self, grid):
        """
        启发式评估函数
        考虑因素：单调性、平滑性、空格数量、高分块位置、边缘行/列
        :param grid: 游戏网格
        :return: 评估分数
        """
        grid_size = len(grid)

        # 1. 单调性 - 数字从高到低排列
        monotonicity = self._calculate_monotonicity(grid)

        # 2. 平滑性 - 相邻数字的差异
        smoothness = self._calculate_smoothness(grid)

        # 3. 空格数量
        empty_cells = len(self._get_empty_cells(grid))

        # 4. 高分块位置（角落优先）
        max_tile = max(max(row) for row in grid)
        max_tile_bonus = 0
        if max_tile > 0:
            # 检查最高分是否在角落
            corners = [(0, 0), (0, grid_size-1), (grid_size-1, 0), (grid_size-1, grid_size-1)]
            for i, j in corners:
                if grid[i][j] == max_tile:
                    max_tile_bonus = max_tile * 2
                    break

        # 5. 边缘行/列上的大数
        edge_bonus = self._calculate_edge_bonus(grid)

        # 6. 加权总和
        score = (
            empty_cells * 1000 +  # 空格最重要
            monotonicity * 100 +  # 单调性次重要
            smoothness * 10 +     # 平滑性
            max_tile_bonus +      # 高分块在角落的奖励
            edge_bonus +          # 边缘行/列的奖励
            max_tile              # 最高分本身
        )

        return score

    def _calculate_monotonicity(self, grid):
        """计算单调性：数字是否按照从高到低的顺序排列"""
        grid_size = len(grid)

        # 检查从左上到右下的单调递减趋势
        monotonicity = 0

        # 检查行单调性（左到右递减）
        for row in grid:
            for j in range(grid_size - 1):
                if row[j] >= row[j + 1]:
                    monotonicity += row[j] - row[j + 1]
                else:
                    monotonicity -= (row[j + 1] - row[j]) * 2  # 逆序惩罚更重

        # 检查列单调性（上到下递减）
        for j in range(grid_size):
            for i in range(grid_size - 1):
                if grid[i][j] >= grid[i + 1][j]:
                    monotonicity += grid[i][j] - grid[i + 1][j]
                else:
                    monotonicity -= (grid[i + 1][j] - grid[i][j]) * 2  # 逆序惩罚更重

        return monotonicity

    def _calculate_smoothness(self, grid):
        """计算平滑性：相邻数字的差异"""
        grid_size = len(grid)
        smoothness = 0

        # 检查水平相邻
        for row in grid:
            for j in range(grid_size - 1):
                if row[j] != 0 and row[j + 1] != 0:
                    # 使用对数减少大数的影响
                    smoothness -= abs(math.log2(row[j]) - math.log2(row[j + 1]))

        # 检查垂直相邻
        for j in range(grid_size):
            for i in range(grid_size - 1):
                if grid[i][j] != 0 and grid[i + 1][j] != 0:
                    smoothness -= abs(math.log2(grid[i][j]) - math.log2(grid[i + 1][j]))

        return smoothness

    def _calculate_edge_bonus(self, grid):
        """计算边缘行/列上大数的奖励"""
        grid_size = len(grid)
        edge_bonus = 0

        # 检查第一行和最后一行
        for row in [0, grid_size - 1]:
            for j in range(grid_size):
                edge_bonus += grid[row][j] * 0.5

        # 检查第一列和最后一列（排除已经计算的角落）
        for j in [0, grid_size - 1]:
            for row in range(1, grid_size - 1):
                edge_bonus += grid[row][j] * 0.3

        return edge_bonus

    def _copy_game_state(self):
        """复制游戏状态"""
        return copy.deepcopy(self.game.grid)

    # ---- 移动模拟（不产生随机方块，仅用于搜索） ----
    @staticmethod
    def _merge_line(line):
        """合并单行（与游戏主体的合并规则保持一致），返回处理后的新行"""
        size = len(line)
        compressed = [num for num in line if num != 0]

        merged = []
        i = 0
        while i < len(compressed):
            if i + 1 < len(compressed) and compressed[i] == compressed[i + 1]:
                merged.append(compressed[i] * 2)
                i += 2          # 合并后一次跳过两个元素，避免 [x, x, x, x] 下标错位
            else:
                merged.append(compressed[i])
                i += 1

        merged += [0] * (size - len(merged))
        return merged

    def _apply_move(self, grid, direction):
        """在网格副本上执行一次移动，返回新网格（不修改入参）"""
        size = len(grid)
        work = [list(row) for row in grid]

        if direction in ('up', 'down'):
            work = [list(row) for row in zip(*work)]  # 转置

        for i in range(size):
            row = work[i][::-1] if direction in ('right', 'down') else work[i]
            new_row = self._merge_line(row)
            if direction in ('right', 'down'):
                new_row.reverse()
            work[i] = new_row

        if direction in ('up', 'down'):
            work = [list(row) for row in zip(*work)]  # 还原

        return work

    def _simulate_move(self, grid, direction):
        """
        模拟移动：直接把结果写回传入的 grid（原地修改），返回是否发生移动
        :param grid: 游戏网格（会被原地更新）
        :param direction: 移动方向
        :return: 是否成功移动
        """
        new_grid = self._apply_move(grid, direction)
        moved = new_grid != grid
        for i in range(len(grid)):
            grid[i][:] = new_grid[i]
        return moved

    def _get_empty_cells(self, grid):
        """获取所有空单元格位置"""
        empty_cells = []
        for i in range(len(grid)):
            for j in range(len(grid[i])):
                if grid[i][j] == 0:
                    empty_cells.append((i, j))
        return empty_cells

    def _is_game_over(self, grid):
        """检查游戏是否结束"""
        # 如果有空单元格，游戏未结束
        if self._get_empty_cells(grid):
            return False

        grid_size = len(grid)
        # 检查是否有可合并的相邻单元格
        for i in range(grid_size):
            for j in range(grid_size - 1):
                if grid[i][j] == grid[i][j + 1]:
                    return False
                if grid[j][i] == grid[j + 1][i]:
                    return False

        return True


def _play_with_ai(game, ai, delay=0.1, verbose=True):
    """
    使用 AI 驱动一个已初始化的游戏实例，直到游戏结束或用户中断。
    :param game: 游戏实例（需已 start_new_game / load_game_state）
    :param ai: AI2048Solver 实例
    :param delay: 每步延迟（秒），用于可视化
    :return: 游戏最终分数
    """
    win_announced = False
    try:
        while True:
            if verbose:
                game.display_grid()

            # 检查是否达成 2048（达到后仍可继续冲分）
            game.check_win()
            if game.won and not win_announced:
                print("恭喜！已合成 2048，继续挑战更高分数……")
                win_announced = True

            if game.check_game_over():
                if verbose:
                    game.display_grid()
                print(f"\n游戏结束！最终分数: {game.score}")
                print(f"AI执行了 {ai.move_count} 步")
                break

            best_move = ai.find_best_move()
            if verbose:
                print(f"AI选择的移动: {ai.direction_names[best_move]} (步数: {ai.move_count})")

            previous_score = game.score  # 记录移动前的分数
            if game._move(best_move):  # 如果移动成功
                after_move_grid = [row[:] for row in game.grid]  # 移动后、尚未新增方块
                game.add_new_tile()  # 添加新方块
                move_score = game.score - previous_score  # 本次移动获得的分数
                game.record_move(f"向{best_move}移动", move_score, after_move_grid, game.grid)
                game.update_index()  # 同步索引中的分数

            if delay > 0:
                time.sleep(delay)

    except KeyboardInterrupt:
        # 保存游戏状态
        game.save_game_state()
        game.update_index()
        print("\nAI求解已停止，游戏状态已保存")

    return game.score


def run_ai_solver(max_depth=3, max_time=0.05, delay=0.1):
    """运行AI求解器（命令行入口）"""
    from v2_console_2048_with_history import Console2048WithHistory

    print("启动2048游戏AI求解器...")
    print(f"参数：搜索深度={max_depth}，单步思考上限={max_time}秒，演示延迟={delay}秒")
    print("按 Ctrl+C 可随时退出并保存进度")

    game = Console2048WithHistory()

    # 优先询问是否继续上一局未完成的游戏
    last_unfinished = game.get_last_unfinished_game()
    if last_unfinished:
        print(f"检测到未完成的游戏：ID={last_unfinished.get('game_id')}，"
              f"分数={last_unfinished.get('score')}")
        try:
            choice = input("是否继续上一局？(y/n，默认n): ").strip().lower()
        except KeyboardInterrupt:
            print("\n已取消")
            return
        if choice == 'y' and game.load_game_state(last_unfinished.get('game_id')):
            print("已加载上一局，继续对局")
        else:
            game.mark_game_completed(last_unfinished.get('game_id'))
            game.start_new_game()
    else:
        game.start_new_game()

    ai = AI2048Solver(game, max_depth=max_depth, max_time=max_time)
    print("AI求解器已初始化，开始游戏...")
    return _play_with_ai(game, ai, delay=delay)


def solve_2048_automatically(game_instance=None, max_depth=3, max_time=0.05,
                             delay=0.1, verbose=False):
    """
    自动求解2048游戏的函数接口

    :param game_instance: 已有的游戏实例，如果为None则创建新实例
    :param max_depth: AI搜索深度
    :param max_time: 每次决策的最大时间（秒）
    :param delay: 每步移动后的延迟时间（秒），用于可视化
    :param verbose: 是否打印过程信息
    :return: 游戏最终分数
    """
    from v2_console_2048_with_history import Console2048WithHistory

    # 如果没有提供游戏实例，创建一个新的
    if game_instance is None:
        game = Console2048WithHistory()
        game.start_new_game()
    else:
        game = game_instance

    ai = AI2048Solver(game, max_depth=max_depth, max_time=max_time)
    return _play_with_ai(game, ai, delay=delay, verbose=verbose)


if __name__ == "__main__":
    run_ai_solver()
