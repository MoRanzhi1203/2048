#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行2048游戏AI求解器的示例脚本
"""

import os
import sys
import time

# 让脚本无论从哪个工作目录启动，都能找到同级的 ai_solver_2048 与
# console_2048_with_history 子目录中的模块
_HERE = os.path.dirname(os.path.abspath(__file__))
_CONSOLE_DIR = os.path.join(_HERE, "console_2048_with_history")
for _p in (_CONSOLE_DIR, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from console_2048_with_history import Console2048WithHistory
from ai_solver_2048 import AI2048Solver, _play_with_ai


def run_demo_mode():
    """演示模式：使用AI自动玩2048游戏"""
    print("=" * 60)
    print("2048游戏 AI自动求解器 演示模式")
    print("=" * 60)
    print("本脚本将使用AI算法自动玩2048游戏")
    print("使用的算法：Expectimax + 启发式评估函数")
    print("\n按Ctrl+C随时退出演示")
    print("=" * 60)

    # 获取用户输入的参数
    try:
        print("\n请选择AI搜索深度 (1-8，数字越大越智能但越慢，默认3): ")

        depth_input = input("请输入深度: ").strip()

        try:
            max_depth = int(depth_input)
            if max_depth < 1 or max_depth > 8:
                max_depth = 3
                print("\n输入超出范围，已使用默认深度3")
            else:
                print(f"\n已设置搜索深度为 {max_depth}")
        except ValueError:
            max_depth = 3
            print("\n输入无效，已使用默认深度3")

        # 根据深度设置建议的思考时间
        if max_depth <= 2:
            max_time = 0.02
        elif max_depth <= 4:
            max_time = 0.05
        elif max_depth <= 6:
            max_time = 0.1
        else:
            max_time = 0.2

        print(f"自动设置最大思考时间为 {max_time} 秒")

        print("\n请选择演示速度：")
        print("1. 慢速 (每步1秒)")
        print("2. 中速 (每步0.5秒)")
        print("3. 快速 (每步0.1秒)")
        print("4. 极快 (无延迟)")

        speed = input("请输入选择 (1-4，默认3): ")

        if speed == '1':
            delay = 1.0
            print("\n已选择慢速演示")
        elif speed == '2':
            delay = 0.5
            print("\n已选择中速演示")
        elif speed == '4':
            delay = 0.0
            print("\n已选择极快演示")
        else:
            delay = 0.1
            print("\n已选择快速演示")

        print("\n准备开始演示...")
        input("按回车键开始...")

    except KeyboardInterrupt:
        print("\n操作已取消")
        return
    except Exception:
        # 如果输入出错，使用默认参数
        max_depth = 3
        max_time = 0.05
        delay = 0.1
        print("\n使用默认参数：中等难度，快速演示")
        time.sleep(1)

    # 创建游戏实例
    game = Console2048WithHistory()

    # 检查是否有未完成的游戏
    recent_game = game.get_last_unfinished_game()
    if recent_game:
        try:
            choice = input("检测到未完成的游戏，是否继续？(y/n，默认n): ")
            if choice.strip().lower() == 'y' and game.load_game_state(recent_game.get('game_id')):
                print("已加载未完成的游戏")
            else:
                game.mark_game_completed(recent_game.get('game_id'))
                game.start_new_game()
        except KeyboardInterrupt:
            game.start_new_game()
    else:
        game.start_new_game()

    # 创建AI求解器
    ai = AI2048Solver(game, max_depth=max_depth, max_time=max_time)

    print("\nAI求解器开始运行...")
    print(f"当前设置：深度={max_depth}, 最大思考时间={max_time}秒, 延迟={delay}秒")
    print("按Ctrl+C随时退出")

    start_time = time.time()
    final_score = _play_with_ai(game, ai, delay=delay, verbose=True)

    # 展示最终统计
    elapsed_time = time.time() - start_time
    try:
        game.save_game_state()
        game.update_index(is_completed=True)
        game.save_best_score()
    except Exception:
        pass

    print("\n" + "=" * 60)
    print("演示结束")
    print(f"最终分数: {final_score}")
    print(f"最高分: {game.best_score}")
    print(f"执行步数: {ai.move_count}")
    print(f"总用时: {elapsed_time:.1f}秒")
    if elapsed_time > 0:
        print(f"平均每秒步数: {ai.move_count / elapsed_time:.1f}步/秒")
    print(f"游戏ID: {game.game_id}")
    print(f"历史记录已保存至: game_history/{game.game_id}/")
    print("=" * 60)


def batch_mode():
    """批量测试模式：运行多次AI游戏并收集统计数据"""
    print("=" * 60)
    print("2048游戏 AI自动求解器 批量测试模式")
    print("=" * 60)
    print("此模式将运行多次AI游戏并收集统计数据")

    try:
        num_runs = int(input("请输入要运行的游戏次数 (默认10次): ") or "10")
        if num_runs < 1:
            num_runs = 10
    except Exception:
        num_runs = 10

    print(f"\n将运行 {num_runs} 次AI游戏")
    print("按Ctrl+C随时退出")
    input("按回车键开始...")

    # 统计数据
    scores = []
    steps = []
    times = []
    wins = 0  # 达到2048的次数
    max_scores = []

    try:
        for i in range(1, num_runs + 1):
            print("\n" + "-" * 60)
            print(f"运行游戏 {i}/{num_runs}")
            print("-" * 60)

            # 创建游戏和AI
            game = Console2048WithHistory()
            game.start_new_game()
            ai = AI2048Solver(game, max_depth=3, max_time=0.05)

            run_start_time = time.time()
            _play_with_ai(game, ai, delay=0.0, verbose=False)
            run_time = time.time() - run_start_time

            # 保存统计数据
            scores.append(game.score)
            steps.append(ai.move_count)
            times.append(run_time)
            max_tile = max(max(row) for row in game.grid)
            max_scores.append(max_tile)
            if game.won:
                wins += 1

            # 显示本次结果
            print(f"游戏 {i} 结束")
            print(f"  分数: {game.score}")
            print(f"  最高方块: {max_tile}")
            print(f"  步数: {ai.move_count}")
            print(f"  用时: {run_time:.1f}秒")

            # 保存游戏状态
            game.save_game_state()
            game.update_index(is_completed=True)

    except KeyboardInterrupt:
        print("\n批量测试已中断")

    # 显示统计结果
    if scores:
        print("\n" + "=" * 60)
        print("批量测试统计结果")
        print("=" * 60)
        print(f"总运行次数: {len(scores)}")
        print(f"平均分数: {sum(scores)/len(scores):.1f}")
        print(f"最高分数: {max(scores)}")
        print(f"最低分数: {min(scores)}")
        print(f"平均步数: {sum(steps)/len(steps):.1f}")
        print(f"平均用时: {sum(times)/len(times):.1f}秒")
        if sum(times) > 0:
            print(f"平均每秒步数: {sum(steps)/sum(times):.1f}步/秒")
        print(f"胜利次数 (达到2048): {wins} ({wins/len(scores)*100:.1f}%)")
        print("最高方块统计:")
        # 统计最高方块分布
        tile_counts = {}
        for tile in max_scores:
            if tile in tile_counts:
                tile_counts[tile] += 1
            else:
                tile_counts[tile] = 1
        for tile in sorted(tile_counts.keys(), reverse=True):
            print(f"  {tile}: {tile_counts[tile]}次 ({tile_counts[tile]/len(max_scores)*100:.1f}%)")
        print("=" * 60)


def main():
    """主函数"""
    while True:
        print("\n" + "=" * 60)
        print("2048游戏 AI自动求解器")
        print("=" * 60)
        print("1. 演示模式 - 观看AI自动玩游戏")
        print("2. 批量测试模式 - 运行多次并收集统计数据")
        print("3. 退出")
        print("=" * 60)

        try:
            choice = input("请输入选择 (1-3): ")

            if choice == '1':
                run_demo_mode()
            elif choice == '2':
                batch_mode()
            elif choice == '3':
                print("感谢使用AI求解器，再见！")
                break
            else:
                print("无效的选择，请重新输入")
        except KeyboardInterrupt:
            print("\n操作已取消")
        except Exception as e:
            print(f"发生错误: {e}")
            input("按回车键继续...")


if __name__ == "__main__":
    main()
