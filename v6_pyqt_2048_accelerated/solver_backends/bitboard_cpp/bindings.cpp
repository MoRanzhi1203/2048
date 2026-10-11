// 2048 V6 C++20 Bitboard 内核的 pybind11 绑定
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <vector>

#include "bitboard.hpp"
#include "search.hpp"

namespace py = pybind11;
using namespace bb2048;

static int dir_index(const std::string& d) {
    if (d == "up") return UP;
    if (d == "down") return DOWN;
    if (d == "left") return LEFT;
    if (d == "right") return RIGHT;
    throw std::invalid_argument("未知方向：" + d);
}

static const char* dir_name(int d) {
    switch (d) {
        case UP: return "up";
        case DOWN: return "down";
        case LEFT: return "left";
        default: return "right";
    }
}

// 把 C++ 搜索结果打包为 Python dict（供 native_api 适配层直接消费）
static py::dict pack_out(const SearchOut& out, const SearchStats& st, const char* engine) {
    py::dict d;
    d["engine"] = std::string(engine);
    d["best_dir"] = out.best_dir;
    d["best_name"] = (out.best_dir >= 0) ? std::string(dir_name(out.best_dir)) : std::string("");
    d["best_value"] = out.best_value;
    py::dict evals;
    for (int i = 0; i < 4; ++i) {
        if (out.has_eval[i]) evals[dir_name(i)] = out.eval[i];
        else evals[dir_name(i)] = py::none();
    }
    d["evals"] = evals;
    py::dict root_visits;
    for (int i = 0; i < 4; ++i) root_visits[dir_name(i)] = out.root_move_visits[i];
    d["root_move_visits"] = root_visits;
    d["root_visits"] = out.root_visits;
    py::dict s;
    s["nodes"] = st.nodes;
    s["leaf_evals"] = st.leaf_evals;
    s["chance_nodes"] = st.chance_nodes;
    s["cache_hits"] = st.cache_hits;
    s["cutoffs"] = st.cutoffs;
    s["rollouts"] = st.rollouts;
    s["simulations"] = st.simulations;
    s["tree_nodes"] = st.tree_nodes;
    s["chance_children"] = st.chance_children;
    s["reused_children"] = st.reused_children;
    s["rollout_steps"] = st.rollout_steps;
    s["width_limit_rollouts"] = st.width_limit_rollouts;
    s["no_spawn_leaves"] = st.no_spawn_leaves;
    s["depth_reached"] = st.depth_reached;
    s["timed_out"] = st.timed_out;
    s["cancelled"] = st.cancelled;
    s["overflow"] = st.overflow;
    d["stats"] = s;
    return d;
}

static CancelFn make_cancel(const py::object& token) {
    if (token.is_none()) return CancelFn();
    return [token]() -> bool {
        py::gil_scoped_acquire g;
        return token.attr("is_cancelled")().cast<bool>();
    };
}

static uint64_t encode_or_throw(const std::vector<int>& vals) {
    if (vals.size() != 16) throw std::invalid_argument("棋盘须为 16 个取值（行主序）");
    uint64_t bb;
    if (!encode_vals(vals.data(), &bb))
        throw BoardOverflowException("bitboard 后端不支持 >= 65536 的方块");
    return bb;
}

static std::vector<int> to_vals(uint64_t bb) {
    std::vector<int> v(16);
    decode_vals(bb, v.data());
    return v;
}

PYBIND11_MODULE(bitboard_cpp, m) {
    m.doc() = "2048 V6 C++20/pybind11 bitboard 内核";

    py::register_exception<BoardOverflowException>(m, "BoardOverflowError");

    m.attr("MAX_EXP") = kMaxExp;
    m.attr("LIMIT_TILE") = kLimitTile;

    m.def("available", []() {
        return py::make_tuple(true, std::string("bitboard_cpp C++20/pybind11"));
    });

    m.def("move", [](const std::vector<int>& vals, const std::string& dir) {
        uint64_t bb = encode_or_throw(vals);
        uint64_t out;
        bool ov;
        int score = move_bb(bb, dir_index(dir), &out, &ov);
        if (ov) throw BoardOverflowException("移动产生 >= 65536 的方块");
        std::vector<int> nv = to_vals(out);
        bool changed = (nv != vals);
        return py::make_tuple(nv, score, changed);
    });

    m.def("legal_moves", [](const std::vector<int>& vals) {
        uint64_t bb = encode_or_throw(vals);
        std::vector<std::string> out;
        for (int d = 0; d < 4; ++d) {
            uint64_t o;
            bool ov;
            move_bb(bb, d, &o, &ov);
            if (ov) throw BoardOverflowException("移动产生 >= 65536 的方块");
            if (o != bb) out.push_back(dir_name(d));
        }
        return out;
    });

    m.def("evaluate", [](const std::vector<int>& vals, const std::vector<double>& w) {
        uint64_t bb = encode_or_throw(vals);
        if (w.size() != 7) throw std::invalid_argument("权重须为长度 7");
        return evaluate_bb(bb, w.data());
    });

    // 65536 行查表（供等价性穷举与消融）
    m.def("row_left", []() {
        const Tables& T = tables();
        return py::make_tuple(
            py::array_t<int32_t>(65536, T.left),
            py::array_t<int32_t>(65536, T.lscore),
            py::array_t<uint8_t>(65536, T.lover));
    });
    m.def("row_right", []() {
        const Tables& T = tables();
        return py::make_tuple(
            py::array_t<int32_t>(65536, T.right),
            py::array_t<int32_t>(65536, T.rscore),
            py::array_t<uint8_t>(65536, T.rover));
    });

    // 批量跨边界接口：一次传入多盘，避免每节点一次 pybind 往返
    m.def("batch_move", [](const std::vector<std::vector<int>>& boards, const std::string& dir) {
        std::vector<std::vector<int>> outs;
        std::vector<int> scores;
        std::vector<bool> changed;
        int di = dir_index(dir);
        outs.reserve(boards.size());
        for (const auto& b : boards) {
            uint64_t bb = encode_or_throw(b);
            uint64_t o;
            bool ov;
            int score = move_bb(bb, di, &o, &ov);
            if (ov) throw BoardOverflowException("移动产生 >= 65536 的方块");
            std::vector<int> nv = to_vals(o);
            changed.push_back(nv != b);
            outs.push_back(std::move(nv));
            scores.push_back(score);
        }
        return py::make_tuple(outs, scores, changed);
    });

    m.def("rollout_events", [](const std::vector<int>& vals, int gained, int depth,
                               py::array_t<double, py::array::c_style | py::array::forcecast> cell_ev,
                               py::array_t<double, py::array::c_style | py::array::forcecast> value_ev,
                               py::array_t<double, py::array::c_style | py::array::forcecast> move_ev,
                               const std::vector<double>& w) {
        uint64_t bb = encode_or_throw(vals);
        if (w.size() != 7) throw std::invalid_argument("权重须为长度 7");
        int n = int(cell_ev.size());
        int cursor = 0;
        return rollout_events(bb, gained, depth, cell_ev.data(), value_ev.data(),
                              move_ev.data(), n, &cursor, w.data());
    });

    // 一次 API 调用完成“一组 rollout”（n_rollouts 次），共享同一事件流游标，
    // 每次 rollout 消费不同事件；用于把完整 N 步模拟全部下沉到原生，降低跨边界次数。
    m.def("rollout_batch", [](const std::vector<int>& vals, int gained, int depth, int n_rollouts,
                              py::array_t<double, py::array::c_style | py::array::forcecast> cell_ev,
                              py::array_t<double, py::array::c_style | py::array::forcecast> value_ev,
                              py::array_t<double, py::array::c_style | py::array::forcecast> move_ev,
                              const std::vector<double>& w) {
        uint64_t bb = encode_or_throw(vals);
        if (w.size() != 7) throw std::invalid_argument("权重须为长度 7");
        int n = int(cell_ev.size());
        int cursor = 0;
        std::vector<double> out;
        out.reserve(n_rollouts > 0 ? n_rollouts : 0);
        for (int i = 0; i < n_rollouts; ++i)
            out.push_back(rollout_events(bb, gained, depth, cell_ev.data(), value_ev.data(),
                                         move_ev.data(), n, &cursor, w.data()));
        return out;
    });

    // ---- V6.2 原生整树搜索 ----
    m.def("native_expectimax",
          [](const std::vector<int>& vals, int max_depth, double time_limit_ms,
             double score_weight, bool use_tt, bool move_order,
             const std::vector<double>& w, py::object cancel_token, long long cancel_poll) {
              uint64_t bb = encode_or_throw(vals);
              if (w.size() != 7) throw std::invalid_argument("权重须为长度 7");
              ExpectimaxParams p;
              p.max_depth = max_depth;
              p.time_limit_ms = time_limit_ms;
              p.score_weight = score_weight;
              p.use_tt = use_tt;
              p.move_order = move_order;
              SearchOut out;
              SearchStats st;
              CancelFn cb = make_cancel(cancel_token);
              {
                  py::gil_scoped_release rel;
                  expectimax_exact(bb, p, w.data(), &out, &st, cb, cancel_poll);
              }
              return pack_out(out, st, "native_expectimax");
          },
          py::arg("vals"), py::arg("max_depth"), py::arg("time_limit_ms"),
          py::arg("score_weight"), py::arg("use_tt"), py::arg("move_order"),
          py::arg("weights"), py::arg("cancel_token") = py::none(),
          py::arg("cancel_poll") = 4096);

    m.def("native_mcts",
          [](const std::vector<int>& vals, int simulations, int rollout_depth, double uct_c,
             int max_chance_width, bool progressive_widening, double cpw, double alpha,
             double time_limit_ms, const std::vector<double>& w,
             py::array_t<double, py::array::c_style | py::array::forcecast> cell_ev,
             py::array_t<double, py::array::c_style | py::array::forcecast> value_ev,
             py::array_t<double, py::array::c_style | py::array::forcecast> move_ev,
             py::object cancel_token) {
              uint64_t bb = encode_or_throw(vals);
              if (w.size() != 7) throw std::invalid_argument("权重须为长度 7");
              int n = int(cell_ev.size());
              if (n <= 0) throw std::invalid_argument("事件流不能为空");
              if (int(value_ev.size()) < n) n = int(value_ev.size());
              if (int(move_ev.size()) < n) n = int(move_ev.size());
              MctsParams p;
              p.simulations = simulations;
              p.rollout_depth = rollout_depth;
              p.uct_c = uct_c;
              p.max_chance_width = max_chance_width;
              p.progressive_widening = progressive_widening;
              p.cpw = cpw;
              p.alpha = alpha;
              p.time_limit_ms = time_limit_ms;
              SearchOut out;
              SearchStats st;
              CancelFn cb = make_cancel(cancel_token);
              {
                  py::gil_scoped_release rel;
                  mcts_events(bb, p, w.data(), cell_ev.data(), value_ev.data(), move_ev.data(), n,
                              &out, &st, cb);
              }
              return pack_out(out, st, "native_mcts");
          },
          py::arg("vals"), py::arg("simulations"), py::arg("rollout_depth"), py::arg("uct_c"),
          py::arg("max_chance_width"), py::arg("progressive_widening"), py::arg("cpw"),
          py::arg("alpha"), py::arg("time_limit_ms"), py::arg("weights"), py::arg("cell_ev"),
          py::arg("value_ev"), py::arg("move_ev"), py::arg("cancel_token") = py::none());
}
