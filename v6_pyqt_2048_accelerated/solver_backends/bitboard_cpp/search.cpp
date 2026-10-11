// 2048 V6.2 原生搜索内核（实现）
//
// 设计要点（对齐 V6.2 指令 S1/S3/S4）：
//  - 决策语义与 Python reference 严格对齐：Max 节点沿用合法动作/终局/启发式/深度含义/
//    并列方向「先出现者优先」；Chance 节点按真实空格数、2/4 概率(0.9/0.1)加权。
//  - 随机事件一律来自显式事件流（cell/value/move 三个 [0,1) 序列 + 游标），
//    避免依赖各语言 RNG 序列，从而可跨语言逐位比对。
//  - 任一节点出现 >=65536 方块：置 overflow 并立即停止（调用方整次决策回退 reference）。
//  - 长循环每 cancel_poll 节点轮询一次取消回调（GIL 由绑定层释放后回调内再获取）。
#include "search.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace bb2048 {

namespace {

inline double now_ms() {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

// 行主序收集空位 nibble 位置（与 Python empty_cells / C++ rollout_events 顺序一致）
inline int list_empties(uint64_t bb, int* pos) {
    int n = 0;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            if (cell_exp(bb, r, c) == 0) pos[n++] = 4 * r + (3 - c);
    return n;
}

// 在 nibble 位置写入方块值（2 或 4 -> 指数 1 或 2）
inline uint64_t set_tile(uint64_t bb, int nibble_pos, int value) {
    int e = (value == 4) ? 2 : 1;
    return bb | (uint64_t(e & 0xF) << (4 * nibble_pos));
}

// 是否溢出（位棋盘无法表示 >=65536）：出现指数 16 的占位即视为溢出。
// move_bb 在溢出时把该 nibble 写成占位 15 并置 overflow 标志，故以标志为准。

// 合法方向（DIRECTIONS 顺序 up,down,left,right），返回数量
inline int legal_dirs(uint64_t bb, int* dirs, bool* overflow) {
    int n = 0;
    for (int d = 0; d < 4; ++d) {
        uint64_t o; bool ov;
        move_bb(bb, d, &o, &ov);
        if (ov) { *overflow = true; return n; }
        if (o != bb) dirs[n++] = d;
    }
    return n;
}

// 按启发式估值降序、稳定排序方向（等价 Python _ordered_moves(order=True)）
inline int ordered_dirs(uint64_t bb, const double* w, int* out) {
    int dirs[4]; int n = 0;
    double vals[4];
    for (int d = 0; d < 4; ++d) {
        uint64_t o; bool ov;
        move_bb(bb, d, &o, &ov);
        if (o == bb) continue;
        dirs[n] = d;
        vals[n] = evaluate_bb(o, w);
        ++n;
    }
    // 插入排序（稳定、降序），n<=4
    for (int i = 1; i < n; ++i) {
        int dd = dirs[i]; double vv = vals[i];
        int j = i - 1;
        while (j >= 0 && vals[j] < vv) {          // 严格小于才前移 -> 相等保持原序
            dirs[j + 1] = dirs[j]; vals[j + 1] = vals[j];
            --j;
        }
        dirs[j + 1] = dd; vals[j + 1] = vv;
    }
    for (int i = 0; i < n; ++i) out[i] = dirs[i];
    return n;
}

// 显式事件流游标
struct Events {
    const double* cell;
    const double* value;
    const double* move;
    int n;
    long long cur = 0;
    void spawn_pair(double* uc, double* uv) {
        long long i = cur % n;
        *uc = cell[i];
        *uv = value[i];
        ++cur;
    }
    double next_move() {
        long long i = cur % n;
        ++cur;
        return move[i];
    }
};

inline int pick_index(double u, int count) {
    if (count <= 0) return -1;
    int idx = int(u * count);
    if (idx >= count) idx = count - 1;
    if (idx < 0) idx = 0;
    return idx;
}

}  // namespace

// ============================================================ Expectimax ===
namespace {

struct TTKey {
    uint64_t bb;
    int depth;
    int kind;          // 0=Max, 1=Chance
    bool operator==(const TTKey& o) const {
        return bb == o.bb && depth == o.depth && kind == o.kind;
    }
};
struct TTHash {
    size_t operator()(const TTKey& k) const {
        size_t h = std::hash<uint64_t>()(k.bb);
        return h ^ (size_t)(k.depth * 1315423911u) ^ (size_t)(k.kind * 2654435761u);
    }
};

struct ExCtx {
    const double* w;
    double score_weight;
    const ExpectimaxParams* p;
    SearchStats* st;
    double t_limit;
    double t0;
    const CancelFn* cancel;
    long long cancel_poll;
    long long since_cancel_check;
    long long poll_steps;
    bool stop;                 // 超时/取消/溢出后置位
    std::unordered_map<TTKey, double, TTHash>* tt;
};

inline bool ex_poll(ExCtx& c) {
    if (c.stop) return true;
    c.poll_steps += 1;
    if ((c.poll_steps & 1023) == 0 && (now_ms() - c.t0) > c.t_limit) {
        c.st->timed_out = true;
        c.stop = true;
        return true;
    }
    if (c.cancel) {
        c.since_cancel_check += 1;
        if (c.since_cancel_check >= c.cancel_poll) {
            c.since_cancel_check = 0;
            if ((*c.cancel)()) {
                c.st->cancelled = true;
                c.stop = true;
                return true;
            }
        }
    }
    return false;
}

double ex_max(uint64_t bb, int depth, ExCtx& c);
double ex_chance(uint64_t bb, int depth, ExCtx& c);

double ex_leaf(uint64_t bb, ExCtx& c) {
    c.st->leaf_evals += 1;
    return evaluate_bb(bb, c.w);
}

double ex_max(uint64_t bb, int depth, ExCtx& c) {
    if (depth <= 0) return ex_leaf(bb, c);
    if (ex_poll(c)) return ex_leaf(bb, c);
    if (c.tt) {
        TTKey k{bb, depth, 0};
        auto it = c.tt->find(k);
        if (it != c.tt->end()) { c.st->cache_hits += 1; return it->second; }
    }
    c.st->nodes += 1;
    double best = -std::numeric_limits<double>::infinity();
    bool any = false;
    int dirs[4]; double ev[4];
    if (c.p->move_order) {
        // 与 Python _ordered_moves 一致：按子节点启发式降序（稳定）
        int n = 0;
        for (int d = 0; d < 4; ++d) {
            uint64_t o; bool ov;
            move_bb(bb, d, &o, &ov);
            if (ov) { c.st->overflow = true; c.stop = true; return 0.0; }
            if (o == bb) continue;
            dirs[n] = d; ev[n] = evaluate_bb(o, c.w); ++n;
        }
        for (int i = 1; i < n; ++i) {
            int dd = dirs[i]; double vv = ev[i]; int j = i - 1;
            while (j >= 0 && ev[j] < vv) { dirs[j + 1] = dirs[j]; ev[j + 1] = ev[j]; --j; }
            dirs[j + 1] = dd; ev[j + 1] = vv;
        }
        for (int i = 0; i < n; ++i) {
            any = true;
            uint64_t o; bool ov; int gain = move_bb(bb, dirs[i], &o, &ov);
            if (ov) { c.st->overflow = true; c.stop = true; return 0.0; }
            double v = c.score_weight * gain + ex_chance(o, depth - 1, c);
            if (c.stop) return 0.0;
            if (v > best) best = v;
        }
    } else {
        for (int d = 0; d < 4; ++d) {
            uint64_t o; bool ov; int gain = move_bb(bb, d, &o, &ov);
            if (ov) { c.st->overflow = true; c.stop = true; return 0.0; }
            if (o == bb) continue;
            any = true;
            double v = c.score_weight * gain + ex_chance(o, depth - 1, c);
            if (c.stop) return 0.0;
            if (v > best) best = v;
        }
    }
    if (!any) best = ex_leaf(bb, c);
    if (c.tt && !c.stop) (*c.tt)[TTKey{bb, depth, 0}] = best;
    return best;
}

double ex_chance(uint64_t bb, int depth, ExCtx& c) {
    if (depth <= 0) return ex_leaf(bb, c);
    if (ex_poll(c)) return ex_leaf(bb, c);
    int pos[16];
    int n = list_empties(bb, pos);
    if (n == 0) return ex_leaf(bb, c);
    c.st->chance_nodes += 1;
    if (c.tt) {
        TTKey k{bb, depth, 1};
        auto it = c.tt->find(k);
        if (it != c.tt->end()) { c.st->cache_hits += 1; return it->second; }
    }
    double total = 0.0;
    for (int k = 0; k < n; ++k) {
        uint64_t c2 = set_tile(bb, pos[k], 2);
        total += 0.9 * ex_max(c2, depth - 1, c);
        if (c.stop) return 0.0;
        uint64_t c4 = set_tile(bb, pos[k], 4);
        total += 0.1 * ex_max(c4, depth - 1, c);
        if (c.stop) return 0.0;
    }
    double result = total / n;
    if (c.tt && !c.stop) (*c.tt)[TTKey{bb, depth, 1}] = result;
    return result;
}

}  // namespace

void expectimax_exact(uint64_t bb, const ExpectimaxParams& p, const double* weights,
                      SearchOut* out, SearchStats* st, const CancelFn& cancel,
                      long long cancel_poll) {
    for (int i = 0; i < 4; ++i) { out->has_eval[i] = false; out->eval[i] = 0.0; }
    out->best_dir = -1;
    out->best_value = 0.0;

    std::unordered_map<TTKey, double, TTHash> tt;
    ExCtx c;
    c.w = weights;
    c.score_weight = p.score_weight;
    c.p = &p;
    c.st = st;
    c.t_limit = p.time_limit_ms;
    c.t0 = now_ms();
    c.cancel = cancel ? &cancel : nullptr;
    c.cancel_poll = cancel_poll > 0 ? cancel_poll : 4096;
    c.since_cancel_check = 0;
    c.poll_steps = 0;
    c.stop = false;
    c.tt = p.use_tt ? &tt : nullptr;

    for (int d = 1; d <= p.max_depth; ++d) {
        if (c.stop) break;
        bool completed = true;
        int best_dir = -1;
        double best_val = -std::numeric_limits<double>::infinity();
        double evals[4]; bool has[4] = {false, false, false, false};

        int dirs[4]; double order_val[4]; int n = 0;
        if (p.move_order) {
            for (int dd = 0; dd < 4; ++dd) {
                uint64_t o; bool ov;
                move_bb(bb, dd, &o, &ov);
                if (ov) { st->overflow = true; c.stop = true; break; }
                if (o == bb) continue;
                dirs[n] = dd; order_val[n] = evaluate_bb(o, weights); ++n;
            }
            for (int i = 1; i < n; ++i) {
                int dd = dirs[i]; double vv = order_val[i]; int j = i - 1;
                while (j >= 0 && order_val[j] < vv) {
                    dirs[j + 1] = dirs[j]; order_val[j + 1] = order_val[j]; --j;
                }
                dirs[j + 1] = dd; order_val[j + 1] = vv;
            }
        } else {
            for (int dd = 0; dd < 4; ++dd) {
                uint64_t o; bool ov;
                move_bb(bb, dd, &o, &ov);
                if (ov) { st->overflow = true; c.stop = true; break; }
                if (o == bb) continue;
                dirs[n++] = dd;
            }
        }
        if (c.stop) break;

        for (int i = 0; i < n; ++i) {
            uint64_t o; bool ov; int gain = move_bb(bb, dirs[i], &o, &ov);
            if (ov) { st->overflow = true; c.stop = true; break; }
            double v = p.score_weight * gain + ex_chance(o, d - 1, c);
            if (c.stop) { completed = false; break; }
            evals[dirs[i]] = v; has[dirs[i]] = true;
            if (v > best_val) { best_val = v; best_dir = dirs[i]; }
        }

        if (completed && best_dir >= 0) {
            out->best_dir = best_dir;
            out->best_value = best_val;
            for (int i = 0; i < 4; ++i) { out->eval[i] = evals[i]; out->has_eval[i] = has[i]; }
            st->depth_reached = d;
        } else {
            if (out->best_dir < 0 && best_dir >= 0) {
                out->best_dir = best_dir;
                out->best_value = best_val;
                for (int i = 0; i < 4; ++i) { out->eval[i] = evals[i]; out->has_eval[i] = has[i]; }
                if (!st->timed_out && !st->cancelled) st->timed_out = true;
            }
            break;
        }
        if ((now_ms() - c.t0) > c.t_limit) { st->timed_out = true; break; }
    }
    out->root_visits = 0;
}

// ================================================================ MCTS ===
namespace {

struct Node {
    uint64_t bb = 0;
    int kind = 0;                 // 0=P(玩家), 1=C(机会)
    int parent = -1;
    int move = -1;                // 从父 P 节点沿用的方向
    double edge_gain = 0.0;
    std::vector<int> children;
    std::unordered_map<uint64_t, int> child_index;   // 仅 C 节点
    int untried[4] = {0, 0, 0, 0};
    int n_untried = 0;
    int untried_pos = 0;
    long long visits = 0;
    double total_return = 0.0;
};

struct MctsCtx {
    const double* w;
    const MctsParams* p;
    SearchStats* st;
    double t_limit;
    double t0;
    const CancelFn* cancel;
    bool stop = false;
    std::vector<Node> pool;
    Events ev;
};

inline bool mcts_poll(MctsCtx& c, long long work) {
    if (c.stop) return true;
    if ((work & 255) == 0) {
        if ((now_ms() - c.t0) > c.t_limit) { c.st->timed_out = true; c.stop = true; return true; }
        if (c.cancel && (*c.cancel)()) { c.st->cancelled = true; c.stop = true; return true; }
    }
    return false;
}

inline int new_node(MctsCtx& c, uint64_t bb, int kind, int parent, int move, double edge_gain) {
    Node n;
    n.bb = bb; n.kind = kind; n.parent = parent; n.move = move; n.edge_gain = edge_gain;
    c.pool.push_back(std::move(n));
    return int(c.pool.size()) - 1;
}

inline double ucb(MctsCtx& c, int parent, int child) {
    const Node& ch = c.pool[child];
    if (ch.visits == 0) return std::numeric_limits<double>::infinity();
    const Node& pa = c.pool[parent];
    return ch.total_return / double(ch.visits)
         + c.p->uct_c * std::sqrt(std::log(double(std::max<long long>(1, pa.visits)))
                                  / double(ch.visits));
}

inline int chance_width(MctsCtx& c, int node) {
    if (!c.p->progressive_widening) return c.p->max_chance_width;
    long long n = std::max<long long>(1, c.pool[node].visits);
    int k = int(std::ceil(c.p->cpw * std::pow(double(n), c.p->alpha)));
    if (k < 1) k = 1;
    if (k > c.p->max_chance_width) k = c.p->max_chance_width;
    return k;
}

// 单步 rollout（消费事件流；kind==1 时先做一次 spawn）
inline double mcts_rollout(MctsCtx& c, uint64_t bb, int kind, double acc, long long* work) {
    uint64_t g = bb;
    if (kind == 1) {
        double uc, uv;
        c.ev.spawn_pair(&uc, &uv);
        int pos[16];
        int n = list_empties(g, pos);
        if (n > 0) {
            int idx = pick_index(uc, n);
            g = set_tile(g, pos[idx], (uv >= 0.9) ? 4 : 2);
        }
    }
    for (int step = 0; step < c.p->rollout_depth; ++step) {
        if (is_game_over(g)) break;
        int dirs[4]; bool ovf = false;
        int nm = legal_dirs(g, dirs, &ovf);
        if (ovf) { c.st->overflow = true; c.stop = true; return 0.0; }
        if (nm == 0) break;
        double um = c.ev.next_move();
        int mi = pick_index(um, nm);
        uint64_t o; bool ov; int gain = move_bb(g, dirs[mi], &o, &ov);
        if (ov) { c.st->overflow = true; c.stop = true; return 0.0; }
        g = o;
        acc += gain;
        // spawn
        double uc, uv;
        c.ev.spawn_pair(&uc, &uv);
        int pos[16];
        int n = list_empties(g, pos);
        if (n > 0) {
            int idx = pick_index(uc, n);
            g = set_tile(g, pos[idx], (uv >= 0.9) ? 4 : 2);
        }
        c.st->rollout_steps += 1;
        *work += 1;
        if (mcts_poll(c, *work)) return 0.0;
    }
    return acc + evaluate_bb(g, c.w);
}

// descend：返回叶子 bb/kind，填充 path 与累计 gain
inline void mcts_descend(MctsCtx& c, int root, uint64_t* leaf_bb, int* leaf_kind,
                         std::vector<int>* path, double* acc, long long* work) {
    int node = root;
    *acc = 0.0;
    path->clear();
    while (true) {
        path->push_back(node);
        if (c.pool[node].kind == 0) {          // P 节点
            Node& nd = c.pool[node];
            if (nd.untried_pos < nd.n_untried) {
                int d = nd.untried[nd.untried_pos++];
                uint64_t o; bool ov; int gain = move_bb(nd.bb, d, &o, &ov);
                if (ov) { c.st->overflow = true; c.stop = true; *leaf_bb = nd.bb; *leaf_kind = 1; return; }
                int child = new_node(c, o, 1, node, d, double(gain));
                c.pool[node].children.push_back(child);
                c.st->tree_nodes += 1;
                c.st->chance_nodes += 1;
                path->push_back(child);
                *leaf_bb = o; *leaf_kind = 1;
                *acc += gain;
                return;
            }
            if (nd.children.empty()) { *leaf_bb = nd.bb; *leaf_kind = 0; return; }
            int best = -1; double best_u = -std::numeric_limits<double>::infinity();
            for (int ch : nd.children) {
                double u = ucb(c, node, ch);
                if (u > best_u) { best_u = u; best = ch; }
            }
            *acc += c.pool[best].edge_gain;
            node = best;
        } else {                                // C 节点
            Node& nd = c.pool[node];
            int pos[16];
            int n = list_empties(nd.bb, pos);
            if (n == 0) { c.st->no_spawn_leaves += 1; *leaf_bb = nd.bb; *leaf_kind = 1; return; }
            double uc, uv;
            c.ev.spawn_pair(&uc, &uv);
            int idx = pick_index(uc, n);
            uint64_t cg = set_tile(nd.bb, pos[idx], (uv >= 0.9) ? 4 : 2);
            auto it = nd.child_index.find(cg);
            int child;
            if (it == nd.child_index.end()) {
                if (int(nd.children.size()) >= chance_width(c, node)) {
                    c.st->width_limit_rollouts += 1;
                    *leaf_bb = cg; *leaf_kind = 0; return;
                }
                int dirs[4];
                int nu = ordered_dirs(cg, c.w, dirs);
                child = new_node(c, cg, 0, node, -1, 0.0);
                Node& cn = c.pool[child];
                cn.n_untried = nu;
                for (int i = 0; i < nu; ++i) cn.untried[i] = dirs[i];
                cn.untried_pos = 0;
                c.pool[node].children.push_back(child);
                c.pool[node].child_index[cg] = child;
                c.st->tree_nodes += 1;
                c.st->chance_children += 1;
            } else {
                child = it->second;
                c.st->reused_children += 1;
            }
            node = child;
        }
    }
}

}  // namespace

void mcts_events(uint64_t bb, const MctsParams& p, const double* weights,
                 const double* cell_ev, const double* value_ev, const double* move_ev,
                 int n_events, SearchOut* out, SearchStats* st, const CancelFn& cancel) {
    for (int i = 0; i < 4; ++i) { out->has_eval[i] = false; out->eval[i] = 0.0; out->root_move_visits[i] = 0; }
    out->best_dir = -1;
    out->best_value = 0.0;
    out->root_visits = 0;

    MctsCtx c;
    c.w = weights;
    c.p = &p;
    c.st = st;
    c.t_limit = p.time_limit_ms;
    c.t0 = now_ms();
    c.cancel = cancel ? &cancel : nullptr;
    c.stop = false;
    c.ev.cell = cell_ev; c.ev.value = value_ev; c.ev.move = move_ev; c.ev.n = n_events; c.ev.cur = 0;

    int dirs[4];
    int nu = ordered_dirs(bb, weights, dirs);
    int root = new_node(c, bb, 0, -1, -1, 0.0);
    {
        Node& rn = c.pool[root];
        rn.n_untried = nu;
        for (int i = 0; i < nu; ++i) rn.untried[i] = dirs[i];
        rn.untried_pos = 0;
    }
    c.st->tree_nodes += 1;

    long long total = std::max(1, p.simulations);
    long long completed = 0;
    long long work = 0;
    std::vector<int> path;
    while (completed < total) {
        if ((now_ms() - c.t0) > c.t_limit) { c.st->timed_out = true; break; }
        if (mcts_poll(c, work)) break;
        uint64_t leaf_bb; int leaf_kind; double acc;
        mcts_descend(c, root, &leaf_bb, &leaf_kind, &path, &acc, &work);
        if (c.stop) break;
        double value = mcts_rollout(c, leaf_bb, leaf_kind, acc, &work);
        if (c.stop) break;
        for (int n : path) {
            c.pool[n].visits += 1;
            c.pool[n].total_return += value;
        }
        st->rollouts += 1;
        completed += 1;
    }
    st->simulations = completed;
    out->root_visits = c.pool[root].visits;

    out->best_value = -std::numeric_limits<double>::infinity();
    for (int ch : c.pool[root].children) {
        const Node& cn = c.pool[ch];
        if (cn.visits == 0) continue;
        double mean = cn.total_return / double(cn.visits);
        if (cn.move >= 0 && cn.move < 4) {
            out->eval[cn.move] = mean;
            out->has_eval[cn.move] = true;
            out->root_move_visits[cn.move] = cn.visits;
            if (mean > out->best_value) { out->best_value = mean; out->best_dir = cn.move; }
        }
    }
    if (out->best_dir < 0) out->best_value = 0.0;
}

}  // namespace bb2048
