// 2048 V6.2 原生搜索内核（声明）
//
// 在既有 bitboard 原语之上，把「整棵搜索树」下沉到 C++：
//   - expectimax_exact：Max/Chance 完整递归（精确模式：不采样、不概率截断）
//   - mcts_events    ：P/C 双层节点 MCTS，随机事件全部来自显式事件流（确定性可复现）
//
// 语义等价目标：expectimax 精确模式与 Python reference（prune=False）数值/决策一致；
// MCTS 使用共享事件流，与 Python 事件镜像逐次一致；任一节点出现 >=65536 方块即
// 置 overflow 并在 Python 侧整次决策回退 reference（绝不截断）。
#pragma once

#include <cstdint>
#include <functional>
#include <unordered_map>
#include <vector>

#include "bitboard.hpp"

namespace bb2048 {

// 取消回调：返回 true 表示外部请求取消（线程安全原子语义由调用方保证）。
using CancelFn = std::function<bool()>;

struct SearchStats {
    long long nodes = 0;              // Max 节点数
    long long leaf_evals = 0;         // 叶子评估次数
    long long chance_nodes = 0;       // Chance 节点数
    long long cache_hits = 0;         // TT 命中
    long long cutoffs = 0;            // 预留（精确模式恒为 0）
    long long rollouts = 0;           // rollout 次数
    long long simulations = 0;         // MCTS 完成模拟数
    long long tree_nodes = 0;         // MCTS 树节点总数
    long long chance_children = 0;    // C->P 新建子节点数
    long long reused_children = 0;    // C 节点复用子节点数
    long long rollout_steps = 0;      // rollout 步数
    long long width_limit_rollouts = 0;
    long long no_spawn_leaves = 0;
    int depth_reached = 0;
    bool timed_out = false;
    bool cancelled = false;
    bool overflow = false;
};

struct ExpectimaxParams {
    int max_depth = 1;
    double time_limit_ms = 1000.0;
    double score_weight = 0.0;
    bool use_tt = false;
    bool move_order = false;          // 等价于 Python 的 order=(prune and move_order)
};

struct MctsParams {
    int simulations = 200;
    int rollout_depth = 16;
    double uct_c = 1.4;
    int max_chance_width = 8;
    bool progressive_widening = false;
    double cpw = 1.0;
    double alpha = 0.5;
    double time_limit_ms = 300.0;
};

struct SearchOut {
    int best_dir = -1;                 // 0..3；-1 表示无可行方向/未完成
    double best_value = 0.0;
    double eval[4] = {0.0, 0.0, 0.0, 0.0};
    bool has_eval[4] = {false, false, false, false};
    long long root_visits = 0;
    long long root_move_visits[4] = {0, 0, 0, 0};
};

// ---- Expectimax（精确模式）----
void expectimax_exact(uint64_t bb, const ExpectimaxParams& p, const double* weights,
                      SearchOut* out, SearchStats* st, const CancelFn& cancel,
                      long long cancel_poll);

// ---- MCTS（事件流驱动，确定性）----
void mcts_events(uint64_t bb, const MctsParams& p, const double* weights,
                 const double* cell_ev, const double* value_ev, const double* move_ev,
                 int n_events, SearchOut* out, SearchStats* st, const CancelFn& cancel);

}  // namespace bb2048
