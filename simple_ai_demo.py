#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版2048游戏AI演示
这个脚本展示了AI求解器的基本功能，无需用户交互
"""

import os
import sys
import time

# 让脚本无论从哪个工作目录启动，都能找到相关模块
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONSOLE_DIR = os.path.join(_HERE, "v2_console_2048_with_history")
for _p in (_CONSOLE_DIR, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from v2_console_2048_with_history import Console2048WithHistory
from ai_solver_2048 import AI2048Solver


def run_simple_demo(steps=10, delay=0.5):
    """运行简化版AI演示，执行固定步数并展示结果"""
    print("=" * 60)
    print("2048游戏 AI求解器 简化演示")
    print("=" * 60)
    print(f"本演示将运行AI求解器执行{steps}步操作，并展示结果")

    # 创建游戏实例
    game = Console2048WithHistory()
    game.start_new_game()

    # 创建AI求解器，设置较浅的深度以便快速执行
    ai = AI2048Solver(game, max_depth=2, max_time=0.02)

    print(f"游戏ID: {game.game_id}")
    print("\n初始游戏状态:")

    # 显示初始状态
    game.display_grid()
    print("\n开始AI演示...")

    try:
        # 执行固定步数操作
        for i in range(1, steps + 1):
            print(f"\n第 {i}/{steps} 步:")

            # 先判断是否已无法继续
            game.check_win()
            if game.check_game_over():
                print("棋盘已无法移动，提前结束演示")
                break

            # AI寻找最佳移动
            best_move = ai.find_best_move()
            print(f"AI选择的移动: {ai.direction_names[best_move]}")

            # 执行移动并按游戏主流程记录历史
            previous_score = game.score
            if game._move(best_move):
                after_move_grid = [row[:] for row in game.grid]
                game.add_new_tile()
                move_score = game.score - previous_score
                game.record_move(f"向{best_move}移动", move_score, after_move_grid, game.grid)
                game.update_index()

            # 显示当前状态
            game.display_grid()

            # 短暂延迟
            if delay > 0:
                time.sleep(delay)

        print("\n演示完成！")
        print(f"{steps}步后的分数: {game.score}")
        print(f"历史记录已保存至: game_history/{game.game_id}/")

        # 保存游戏状态
        game.save_game_state()
        game.update_index()

    except KeyboardInterrupt:
        print("\n演示已中断")
    finally:
        # 确保保存状态
        game.save_game_state()
        game.update_index()


def print_ai_algorithm_info():
    """打印AI算法的详细信息"""
    print("\n" + "=" * 60)
    print("2048游戏 AI求解器 算法说明")
    print("=" * 60)
    print("1. 算法类型: Expectimax搜索")
    print("   - 不同于Minimax，Expectimax在机会节点取期望值而非最小值")
    print("   - 更适合2048这类有随机元素的游戏")

    print("\n2. 启发式评估函数因素:")
    print("   - 空格数量: 优先保持较多的空格")
    print("   - 单调性: 确保数字从高到低排列")
    print("   - 平滑性: 相邻数字的差异应尽可能小")
    print("   - 高分块位置: 高分块应尽可能放在角落")
    print("   - 边缘行/列: 较大的数字应放在边缘")

    print("\n3. 优化策略:")
    print("   - 迭代深度限制: 避免搜索空间过大")
    print("   - 时间限制: 确保每步决策在合理时间内完成")
    print("   - 剪枝优化: 跳过无效移动")

    print("\n4. 最佳实践:")
    print("   - 中等深度(3)通常能在性能和效果间取得平衡")
    print("   - 思考时间不宜过长，建议0.05-0.1秒/步")
    print("   - 高分策略：保持角落有最大的方块，边缘有次大的方块")
    print("=" * 60)


def main():
    """主函数"""
    # 运行简化演示
    run_simple_demo()

    # 打印算法信息
    print_ai_algorithm_info()

    print("\n要运行完整的AI演示，请使用以下命令:")
    print("python run_ai_2048.py")
    print("\n要直接使用AI求解器API，请参考以下示例:")
    print("""
from ai_solver_2048 import solve_2048_automatically
from v2_console_2048_with_history import Console2048WithHistory

# 创建游戏实例
game = Console2048WithHistory()
game.start_new_game()

# 使用AI自动求解，返回最终分数
final_score = solve_2048_automatically(
    game_instance=game,
    max_depth=3,
    max_time=0.05,
    delay=0.1
)
print(f"最终分数: {final_score}")
    """)


if __name__ == "__main__":
    main()
