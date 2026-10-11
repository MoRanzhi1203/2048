#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公共随机事件流（对齐《V6 指令》§4.5 / §6.2B）。

用途：让纯 Python / NumPy / Numba / C++ 各后端在 **相同的显式事件流** 下续玩，
从而比较“同算法 + 同工作量”的行为（同 seed 不保证跨语言 RNG 序列一致，故不依赖各语言 RNG）。

事件流约定（与 V5 `sample_spawn` 的分布口径一致）：
    - 选空位：u_cell ∈ [0,1)，取 idx = min(E-1, int(u_cell * E))（E 为当前空位数量）
    - 选数值：u_value ∈ [0,1)，u_value < 0.9 -> 2，否则 -> 4
"""

from __future__ import annotations

import random


class SpawnEventStream:
    """确定性、可复现、可跨后端消费的 spawn 事件流。

    每个“生成事件”消耗两个 [0,1) 浮点数（选格、选值）。事件数量有上限，
    超出后循环复用同一序列（rollout 深度有限，实际不会耗尽）。
    """

    def __init__(self, seed: int, events: int = 200000):
        rng = random.Random(int(seed))
        self.seed = int(seed)
        self.cell = [rng.random() for _ in range(events)]
        self.value = [rng.random() for _ in range(events)]
        self.move = [rng.random() for _ in range(events)]
        self.n = events
        self._i = 0

    def reset(self):
        self._i = 0

    def next_pair(self):
        i = self._i
        self._i = (i + 1) % self.n
        return self.cell[i], self.value[i]

    def as_arrays(self):
        """返回 (cell[], value[], move[]) 供 Numba / C++ 批量消费。"""
        import numpy as np
        return (np.asarray(self.cell, dtype=np.float64),
                np.asarray(self.value, dtype=np.float64),
                np.asarray(self.move, dtype=np.float64))


def pick_cell_index(u_cell: float, n_empty: int) -> int:
    """把 u_cell ∈ [0,1) 映射到当前空位列表的下标（与 C++/Numba 同一规则）。"""
    if n_empty <= 0:
        return -1
    idx = int(u_cell * n_empty)
    if idx >= n_empty:
        idx = n_empty - 1
    if idx < 0:
        idx = 0
    return idx


def pick_tile_value(u_value: float) -> int:
    return 4 if u_value >= 0.9 else 2
