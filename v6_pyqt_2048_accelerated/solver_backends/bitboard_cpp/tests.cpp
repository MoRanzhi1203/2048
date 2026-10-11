// 2048 V6 C++20 Bitboard 内核自测（独立于 Python，可单独构建运行）
#include <cstdio>
#include <vector>

#include "bitboard.hpp"

using namespace bb2048;

static int g_fail = 0;

static void expect_eq(const char* what, long got, long want) {
    if (got != want) {
        std::printf("FAIL: %s got=%ld want=%ld\n", what, got, want);
        ++g_fail;
    } else {
        std::printf("ok  : %s = %ld\n", what, got);
    }
}

static int code_of(const int e0, const int e1, const int e2, const int e3) {
    return (e0 << 12) | (e1 << 8) | (e2 << 4) | e3;
}

int main() {
    // --- 行合并（左）：与 2048 规则逐项核对 ---
    struct RowCase { int e0, e1, e2, e3; int out; int score; bool ov; };
    const RowCase cases[] = {
        // [2,2,0,0] -> [4,0,0,0] exp [2,0,0,0]
        {1, 1, 0, 0, code_of(2, 0, 0, 0), 4, false},
        // [2,2,2,2] -> [4,4,0,0]
        {1, 1, 1, 1, code_of(2, 2, 0, 0), 8, false},
        // [2,2,4,0] -> [4,4,0,0]（每个方块单次移动最多合并一次；得分仅 4）
        {1, 1, 2, 0, code_of(2, 2, 0, 0), 4, false},
        // [4,4,4,4] -> [8,8,0,0]
        {2, 2, 2, 2, code_of(3, 3, 0, 0), 16, false},
        // [2,4,4,0] -> [2,8,0,0]  (只合并一次，不可连乘)
        {1, 2, 2, 0, code_of(1, 3, 0, 0), 8, false},
        // [2,0,2,2] -> [4,2,0,0]
        {1, 0, 1, 1, code_of(2, 1, 0, 0), 4, false},
        // [32768,32768,0,0] -> 溢出（得分 65536，结果 nibble 用占位 15）
        {15, 15, 0, 0, 0xF000, 65536, true},
    };
    for (const auto& c : cases) {
        int code = code_of(c.e0, c.e1, c.e2, c.e3);
        int out, g;
        bool ov;
        slide_row(code, &out, &g, &ov);
        char buf[64];
        std::snprintf(buf, sizeof(buf), "slide[%d,%d,%d,%d]", c.e0, c.e1, c.e2, c.e3);
        expect_eq(buf, out, c.out);
        expect_eq("  score", g, c.score);
        expect_eq("  overflow", ov ? 1 : 0, c.ov ? 1 : 0);
    }

    // --- 表大小与溢出覆盖 ---
    const Tables& T = tables();
    expect_eq("table.size.left[0]", T.left[0], 0);
    expect_eq("table.left[0x1100]", T.left[0x1100], code_of(2, 0, 0, 0));

    // --- 4×4 移动（row0=[2,2,0,0]，其余 0） ---
    std::vector<int> vals(16, 0);
    vals[0] = 2; vals[1] = 2;
    uint64_t bb;
    if (!encode_vals(vals.data(), &bb)) { std::printf("FAIL: encode\n"); return 1; }

    uint64_t o; bool ov;
    int sc = move_bb(bb, LEFT, &o, &ov);
    std::vector<int> nv(16);
    decode_vals(o, nv.data());
    expect_eq("move left score", sc, 4);
    expect_eq("move left cell0", nv[0], 4);
    expect_eq("move left cell1", nv[1], 0);

    sc = move_bb(bb, UP, &o, &ov);
    decode_vals(o, nv.data());
    expect_eq("move up unchanged", (o == bb) ? 1 : 0, 1);

    sc = move_bb(bb, DOWN, &o, &ov);
    decode_vals(o, nv.data());
    // 两个 2 在不同列，向下不合并 -> 落到最底行 col0 / col1
    expect_eq("move down cell12", nv[12], 2);
    expect_eq("move down cell13", nv[13], 2);

    // --- 溢出拒绝 ---
    std::vector<int> ovf(16, 0);
    ovf[0] = 65536;
    uint64_t dummy;
    expect_eq("encode(65536) rejected", encode_vals(ovf.data(), &dummy) ? 0 : 1, 1);

    // --- transpose 往返 ---
    expect_eq("transpose involutive", (int)(transpose_bb(transpose_bb(bb)) == bb), 1);

    if (g_fail == 0) std::printf("ALL TESTS PASSED\n");
    else std::printf("%d TEST(S) FAILED\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
