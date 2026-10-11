// 2048 V6 C++20 Bitboard 内核（实现）
#include "bitboard.hpp"

#include <algorithm>
#include <cmath>

namespace bb2048 {

inline int cell_exp(uint64_t bb, int r, int c) {
    return int((bb >> (4 * (4 * r + (3 - c)))) & 0xF);
}

inline void set_exp(uint64_t* bb, int r, int c, int e) {
    int p = 4 * (4 * r + (3 - c));
    *bb |= uint64_t(e & 0xF) << p;
}

void slide_row(int code, int* out, int* gained, bool* overflow) {
    int e[4];
    for (int k = 0; k < 4; ++k) e[k] = (code >> (4 * (3 - k))) & 0xF;
    int comp[4];
    int n = 0;
    for (int k = 0; k < 4; ++k)
        if (e[k] != 0) comp[n++] = e[k];
    int res[4] = {0, 0, 0, 0};
    int g = 0;
    bool ov = false;
    int m = 0, i = 0;
    while (i < n) {
        if (i + 1 < n && comp[i] == comp[i + 1]) {
            int ne = comp[i] + 1;
            res[m++] = ne;
            g += (1 << ne);
            if (ne > kMaxExp) ov = true;
            i += 2;
        } else {
            res[m++] = comp[i];
            ++i;
        }
    }
    int rc = 0;
    for (int k = 0; k < 4; ++k) {
        int ee = res[k];
        if (ee > 15) ee = 15;      // 溢出时占位，正确性由 overflow 标记
        rc |= (ee & 0xF) << (4 * (3 - k));
    }
    *out = rc;
    *gained = g;
    *overflow = ov;
}

Tables::Tables() {
    for (int code = 0; code < 65536; ++code) {
        int out, g;
        bool ov;
        slide_row(code, &out, &g, &ov);
        left[code] = out;
        lscore[code] = g;
        lover[code] = ov ? 1 : 0;
        // 右移：反转 nibble -> 左移 -> 再反转
        int rc = 0;
        for (int k = 0; k < 4; ++k) {
            int e = (code >> (4 * k)) & 0xF;
            rc |= e << (4 * (3 - k));
        }
        int rout, rg;
        bool rov;
        slide_row(rc, &rout, &rg, &rov);
        int rback = 0;
        for (int k = 0; k < 4; ++k) {
            int e = (rout >> (4 * k)) & 0xF;
            rback |= e << (4 * (3 - k));
        }
        right[code] = rback;
        rscore[code] = rg;
        rover[code] = rov ? 1 : 0;
    }
}

const Tables& tables() {
    static Tables t;
    return t;
}

uint64_t transpose_bb(uint64_t bb) {
    uint64_t out = 0;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            set_exp(&out, c, r, cell_exp(bb, r, c));
    return out;
}

bool encode_vals(const int* vals, uint64_t* out) {
    uint64_t bb = 0;
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            int v = vals[r * 4 + c];
            if (v < 0) return false;
            if (v >= int(kLimitTile)) return false;
            int e = 0;
            int x = v;
            while (x > 1) { x >>= 1; ++e; }
            set_exp(&bb, r, c, e);
        }
    }
    *out = bb;
    return true;
}

void decode_vals(uint64_t bb, int* vals) {
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) {
            int e = cell_exp(bb, r, c);
            vals[r * 4 + c] = (e == 0) ? 0 : (1 << e);
        }
}

int move_bb(uint64_t bb, int dir, uint64_t* out, bool* overflow) {
    const Tables& T = tables();
    bool trans = (dir == UP || dir == DOWN);
    int mode = (dir == LEFT || dir == UP) ? 0 : 1;   // 0=left, 1=right
    uint64_t cur = trans ? transpose_bb(bb) : bb;
    int score = 0;
    bool ov = false;
    uint64_t res = 0;
    for (int r = 0; r < 4; ++r) {
        int code = row_get(cur, r);
        int nc = (mode == 0) ? T.left[code] : T.right[code];
        score += (mode == 0) ? T.lscore[code] : T.rscore[code];
        if ((mode == 0) ? T.lover[code] : T.rover[code]) ov = true;
        res |= uint64_t(uint32_t(nc) & 0xFFFF) << (16 * r);
    }
    if (trans) res = transpose_bb(res);
    *out = res;
    *overflow = ov;
    return score;
}

bool is_game_over(uint64_t bb) {
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            if (cell_exp(bb, r, c) == 0) return false;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 3; ++c)
            if (cell_exp(bb, r, c) == cell_exp(bb, r, c + 1)) return false;
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 3; ++r)
            if (cell_exp(bb, r, c) == cell_exp(bb, r + 1, c)) return false;
    return true;
}

// ------------------------------------------------ 启发式（在指数上等价计算） ---
// 关键等价性：log2(2^e) == e（精确），故特征都可直接在指数上做，与 V5 数值一致。

static double f_monotonicity(uint64_t bb) {
    double total = 0.0;
    auto l2 = [](int e) { return e <= 0 ? 0.0 : double(e); };
    for (int i = 0; i < 4; ++i) {
        double inc = 0.0, dec = 0.0;
        for (int j = 0; j < 3; ++j) {
            double a = l2(cell_exp(bb, i, j)), b = l2(cell_exp(bb, i, j + 1));
            if (a > b) dec += b - a; else inc += a - b;
        }
        total += std::max(inc, dec);
        inc = 0.0; dec = 0.0;
        for (int j = 0; j < 3; ++j) {
            double a = l2(cell_exp(bb, j, i)), b = l2(cell_exp(bb, j + 1, i));
            if (a > b) dec += b - a; else inc += a - b;
        }
        total += std::max(inc, dec);
    }
    return total;
}

static double f_smoothness(uint64_t bb) {
    double total = 0.0;
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            int e = cell_exp(bb, i, j);
            if (e == 0) continue;
            double lv = double(e);
            if (j + 1 < 4 && cell_exp(bb, i, j + 1) != 0)
                total -= std::fabs(lv - double(cell_exp(bb, i, j + 1)));
            if (i + 1 < 4 && cell_exp(bb, i + 1, j) != 0)
                total -= std::fabs(lv - double(cell_exp(bb, i + 1, j)));
        }
    return total;
}

static int f_merge(uint64_t bb) {
    int count = 0;
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            int e = cell_exp(bb, i, j);
            if (e == 0) continue;
            if (j + 1 < 4 && cell_exp(bb, i, j + 1) == e) ++count;
            if (i + 1 < 4 && cell_exp(bb, i + 1, j) == e) ++count;
        }
    return count;
}

static double f_corner(uint64_t bb) {
    int mt = 0;
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) mt = std::max(mt, cell_exp(bb, i, j));
    if (mt == 0) return 0.0;
    const int ci[4] = {0, 0, 3, 3}, cj[4] = {0, 3, 0, 3};
    for (int k = 0; k < 4; ++k)
        if (cell_exp(bb, ci[k], cj[k]) == mt) return double(mt);
    return 0.0;
}

static const int kSnakeI[16] = {0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3};
static const int kSnakeJ[16] = {0, 1, 2, 3, 3, 2, 1, 0, 0, 1, 2, 3, 3, 2, 1, 0};

static double f_snake(uint64_t bb) {
    double num = 0.0, den = 0.0, w = 1.0;
    for (int idx = 0; idx < 16; ++idx) {
        int e = cell_exp(bb, kSnakeI[idx], kSnakeJ[idx]);
        num += w * (e <= 0 ? 0.0 : double(e));
        den += w * 15.0;
        w *= 0.5;
    }
    return den ? 100.0 * num / den : 0.0;
}

static double f_danger(uint64_t bb, int empties) {
    int distinct = 0;
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            int e = cell_exp(bb, i, j);
            if (e <= 0) continue;
            if (j + 1 < 4) { int f = cell_exp(bb, i, j + 1); if (f > 0 && f != e) ++distinct; }
            if (i + 1 < 4) { int f = cell_exp(bb, i + 1, j); if (f > 0 && f != e) ++distinct; }
        }
    return -60.0 * (1.0 - empties / 16.0) - 0.6 * distinct;
}

double evaluate_bb(uint64_t bb, const double* w) {
    int empties = 0;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c)
            if (cell_exp(bb, r, c) == 0) ++empties;
    double score = w[0] * empties + w[1] * f_monotonicity(bb)
                 + w[2] * f_smoothness(bb) + w[3] * f_merge(bb) + w[4] * f_corner(bb);
    if (w[5] != 0.0) score += w[5] * f_snake(bb);
    if (w[6] != 0.0) score += w[6] * f_danger(bb, empties);
    return score;
}

double rollout_events(uint64_t bb, int gained, int depth,
                      const double* cell_ev, const double* value_ev, const double* move_ev,
                      int n_events, int* cursor, const double* w) {
    uint64_t cur = bb;
    double score = gained;
    for (int step = 0; step < depth; ++step) {
        if (is_game_over(cur)) break;
        // spawn：收集空位 nibble 下标
        int empties[16];
        int ne = 0;
        for (int p = 0; p < 16; ++p)
            if (((cur >> (4 * p)) & 0xF) == 0) empties[ne++] = p;
        if (ne == 0) break;
        int c0 = *cursor % n_events;
        double uc = cell_ev[c0];
        double uv = value_ev[c0];
        *cursor = *cursor + 1;
        int idx = int(uc * ne);
        if (idx >= ne) idx = ne - 1;
        if (idx < 0) idx = 0;
        int e_new = (uv >= 0.9) ? 2 : 1;          // 值 4 -> 指数 2；值 2 -> 指数 1
        cur |= uint64_t(e_new & 0xF) << (4 * empties[idx]);
        if (is_game_over(cur)) break;
        int moves[4];
        int nm = 0;
        for (int d = 0; d < 4; ++d) {
            uint64_t o; bool ov;
            move_bb(cur, d, &o, &ov);
            if (o != cur && !ov) moves[nm++] = d;
        }
        if (nm == 0) break;
        int c1 = *cursor % n_events;
        double um = move_ev[c1];
        *cursor = *cursor + 1;
        int mi = int(um * nm);
        if (mi >= nm) mi = nm - 1;
        if (mi < 0) mi = 0;
        uint64_t o; bool ov;
        int g = move_bb(cur, moves[mi], &o, &ov);
        if (ov) break;                            // 溢出：停止（不静默截断）
        cur = o;
        score += g;
    }
    return score + evaluate_bb(cur, w);
}

}  // namespace bb2048
