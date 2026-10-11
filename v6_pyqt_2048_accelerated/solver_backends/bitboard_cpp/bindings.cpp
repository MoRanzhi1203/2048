// 2048 V6 C++20 Bitboard 内核的 pybind11 绑定
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <vector>

#include "bitboard.hpp"

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
}
