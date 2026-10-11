// 2048 V6 C++20 Bitboard 内核（声明）
// 4bit 指数编码 0=空格，1..15 对应 2..32768；指数 16（值 65536）不可表示 -> 显式拒绝。
#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace bb2048 {

// 位棋盘无法表示 >= 65536 的方块时抛出（Python 侧映射为 BoardOverflowError）
struct BoardOverflowException : std::runtime_error {
    explicit BoardOverflowException(const std::string& msg) : std::runtime_error(msg) {}
};

constexpr int kMaxExp = 15;                       // 可表示的最大指数
constexpr uint32_t kLimitTile = 1u << 16;        // 65536：达到/超过即“超界”

enum Dir { UP = 0, DOWN = 1, LEFT = 2, RIGHT = 3 };

// 65536 行查表：左/右合并结果、得分、溢出标志
struct Tables {
    int32_t left[65536];
    int32_t right[65536];
    int32_t lscore[65536];
    int32_t rscore[65536];
    uint8_t lover[65536];
    uint8_t rover[65536];
    Tables();
};

const Tables& tables();

// 单行（16-bit 编码，col0 位于最高 nibble）向左合并；输出结果行/得分/溢出
void slide_row(int code, int* out, int* gained, bool* overflow);

inline int row_get(uint64_t bb, int r) { return int((bb >> (16 * r)) & 0xFFFF); }

// 单格指数读写（4bit 指数，nibble 位置 p = 4*r + (3-c)）
inline int cell_exp(uint64_t bb, int r, int c) {
    return int((bb >> (4 * (4 * r + (3 - c)))) & 0xF);
}

inline void set_exp(uint64_t* bb, int r, int c, int e) {
    int p = 4 * (4 * r + (3 - c));
    *bb |= uint64_t(e & 0xF) << p;
}

// 4×4 nibble 转置
uint64_t transpose_bb(uint64_t bb);

// 方块值(16, 行主序) -> bitboard；若含 >= 65536 的方块返回 false
bool encode_vals(const int* vals, uint64_t* out);
// bitboard -> 方块值(16, 行主序)
void decode_vals(uint64_t bb, int* vals);

// 一次移动：dir 为 Dir；返回合并得分，写出结果 bb 与溢出标志
int move_bb(uint64_t bb, int dir, uint64_t* out, bool* overflow);

// 是否无可行移动
bool is_game_over(uint64_t bb);

// 启发式评估：权重顺序 [empty, monotonicity, smoothness, merge, corner, snake, danger]
double evaluate_bb(uint64_t bb, const double* w);

// 纯随机 rollout（消费显式事件流）：从 after_move 盘面出发，depth 步
//   events: cell[]/value[]/move[] 三个 [0,1) 浮点序列，长度各为 n_events
double rollout_events(uint64_t bb, int gained, int depth,
                      const double* cell_ev, const double* value_ev, const double* move_ev,
                      int n_events, int* cursor, const double* w);

}  // namespace bb2048
