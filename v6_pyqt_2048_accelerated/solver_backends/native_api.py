#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6.2 原生搜索契约：请求 / 结果 / 取消令牌 / 引擎调用适配。

设计（对齐 V6.2 指令 S1）：
- 显式声明所有决策语义参数（budget_type/value、权重、规则、seed/事件流、取消令牌），
  禁止悄悄沿用不同默认值。
- 结果字段区分 ``backend_requested / backend_used / engine_used / fallback_reason``，
  明确「使用 cpp primitive」与「native 整树搜索」。
- 随机数：仅 seed 相同不保证跨语言序列一致；强等价使用预生成事件流 ``spawn_events``。
- 说明：本模块只做契约与转换，真正搜索在 C++ 扩展内（bitboard_cpp.native_*）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

from .api import DIRECTIONS, board_key

WEIGHT_KEYS = ('empty', 'monotonicity', 'smoothness', 'merge', 'corner', 'snake', 'danger')

BUDGET_ROLLOUTS = 'rollouts'
BUDGET_NODES = 'nodes'
BUDGET_DEPTH = 'depth'
BUDGET_TIME = 'time'
BUDGETS = (BUDGET_ROLLOUTS, BUDGET_NODES, BUDGET_DEPTH, BUDGET_TIME)


class NativeEngineNotSupported(Exception):
    """请求的配置在当前原生引擎中不受支持（应显式回退 Python 路径，而非近似替代）。"""


class CancelToken:
    """线程安全的取消令牌。

    GUI/工作线程调用 :meth:`cancel`，原生搜索循环周期性地调用 :meth:`is_cancelled`
    （C++ 侧在释放 GIL 的长循环中按批次重新获取 GIL 后回调）。仅做事件置位，不触碰 Qt。
    """

    __slots__ = ('_ev',)

    def __init__(self):
        self._ev = threading.Event()

    def cancel(self):
        self._ev.set()

    def is_cancelled(self) -> bool:
        return self._ev.is_set()

    def reset(self):
        self._ev.clear()


def weight_vector(weights) -> List[float]:
    """把权重 dict（或 None -> 由调用方给默认）转为定长 7 向量；顺序见 WEIGHT_KEYS。"""
    if weights is None:
        raise ValueError('权重不得为 None（应由调用方显式给出，避免沿用不同默认值）')
    return [float(weights.get(k, 0.0)) for k in WEIGHT_KEYS]


@dataclass
class NativeSearchRequest:
    board: Sequence[Sequence[int]]
    strategy: str
    budget_type: str = BUDGET_DEPTH
    budget_value: float = 1.0
    weights: List[float] = field(default_factory=list)
    seed: int = 2048
    time_limit_ms: float = 300.0
    score_weight: float = 0.0
    # expectimax
    prune: bool = False
    use_tt: bool = False
    move_order: bool = False
    sample_limit: int = 0
    prob_cutoff: float = 0.0
    # mcts
    simulations: int = 200
    rollout_depth: int = 16
    uct_c: float = 1.4
    max_chance_width: int = 8
    progressive_widening: bool = False
    cpw: float = 1.0
    alpha: float = 0.5
    # 取消 / 事件流
    cancel_token: Optional[CancelToken] = None
    event_seed: Optional[int] = None
    events: Any = None            # SpawnEventStream（可选；给定则使用其序列）
    collect_stats: bool = True

    def signature(self) -> tuple:
        return board_key([list(r) for r in self.board])


@dataclass
class NativeSearchResult:
    best_direction: Optional[str] = None
    score: Optional[float] = None
    evaluations: dict = field(default_factory=dict)
    completed_work: Optional[float] = None
    node_count: int = 0
    rollouts: int = 0
    elapsed_ms: float = 0.0
    backend_requested: Optional[str] = None
    backend_used: Optional[str] = None
    engine_used: str = 'native'
    fallback_reason: Optional[str] = None
    cancelled: bool = False
    timed_out: bool = False
    overflow: bool = False
    board_signature: Optional[tuple] = None
    depth_reached: int = 0
    root_visits: int = 0
    root_move_visits: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        return d


# =====================================================================
# 引擎调用适配（C++ 扩展 -> NativeSearchResult）
# =====================================================================
def _base_result(req: NativeSearchRequest, raw: dict, backend_requested, backend_used,
                 elapsed_ms: float) -> NativeSearchResult:
    evals = {d: raw['evals'].get(d) for d in DIRECTIONS}
    return NativeSearchResult(
        best_direction=raw['best_name'] if raw['best_name'] else None,
        score=raw.get('best_value'),
        evaluations=evals,
        node_count=int(raw['stats'].get('nodes', 0)),
        rollouts=int(raw['stats'].get('rollouts', 0)),
        elapsed_ms=elapsed_ms,
        backend_requested=backend_requested,
        backend_used=backend_used,
        engine_used=raw.get('engine', 'native'),
        cancelled=bool(raw['stats'].get('cancelled')),
        timed_out=bool(raw['stats'].get('timed_out')),
        overflow=bool(raw['stats'].get('overflow')),
        board_signature=req.signature(),
        depth_reached=int(raw['stats'].get('depth_reached', 0)),
        root_visits=int(raw.get('root_visits', 0)),
        root_move_visits={d: int(raw.get('root_move_visits', {}).get(d, 0)) for d in DIRECTIONS},
        stats=dict(raw['stats']),
    )


def run_expectimax(backend, req: NativeSearchRequest,
                   backend_requested=None, backend_used=None) -> NativeSearchResult:
    """调用 C++ 精确 Expectimax；不支持近似配置（采样/概率截断）时抛 NativeEngineNotSupported。"""
    mod = getattr(backend, 'm', None)
    if mod is None or not hasattr(mod, 'native_expectimax'):
        raise NativeEngineNotSupported('cpp 后端未导出 native_expectimax')
    if req.sample_limit and req.sample_limit > 0:
        raise NativeEngineNotSupported('native Expectimax 不支持空位采样（近似模式），请用 Python 路径')
    if req.prob_cutoff and req.prob_cutoff > 0.0:
        raise NativeEngineNotSupported('native Expectimax 不支持概率截断（近似模式），请用 Python 路径')
    flat = [int(req.board[r][c]) for r in range(4) for c in range(4)]
    t0 = time.time()
    raw = mod.native_expectimax(flat, int(req.budget_value), float(req.time_limit_ms),
                                float(req.score_weight), bool(req.use_tt), bool(req.move_order),
                                list(req.weights), req.cancel_token)
    elapsed = (time.time() - t0) * 1000.0
    res = _base_result(req, raw, backend_requested, backend_used, elapsed)
    res.completed_work = float(res.node_count)
    return res


def run_mcts(backend, req: NativeSearchRequest,
             backend_requested=None, backend_used=None) -> NativeSearchResult:
    """调用 C++ 事件流 MCTS（确定性：同一事件流 -> 同一结果）。"""
    mod = getattr(backend, 'm', None)
    if mod is None or not hasattr(mod, 'native_mcts'):
        raise NativeEngineNotSupported('cpp 后端未导出 native_mcts')
    from .events import mcts_event_stream
    stream = req.events
    if stream is None:
        seed = req.seed if req.event_seed is None else int(req.event_seed)
        stream = mcts_event_stream(int(seed), int(req.simulations), int(req.rollout_depth))
    cell_ev, value_ev, move_ev = stream.as_arrays()
    flat = [int(req.board[r][c]) for r in range(4) for c in range(4)]
    t0 = time.time()
    raw = mod.native_mcts(flat, int(req.simulations), int(req.rollout_depth), float(req.uct_c),
                          int(req.max_chance_width), bool(req.progressive_widening),
                          float(req.cpw), float(req.alpha), float(req.time_limit_ms),
                          list(req.weights), cell_ev, value_ev, move_ev, req.cancel_token)
    elapsed = (time.time() - t0) * 1000.0
    res = _base_result(req, raw, backend_requested, backend_used, elapsed)
    res.completed_work = float(raw['stats'].get('simulations', 0))
    return res


# 供测试/报告：原生引擎能力探测
def native_capabilities(backend) -> dict:
    mod = getattr(backend, 'm', None)
    return {
        'native_expectimax': bool(mod is not None and hasattr(mod, 'native_expectimax')),
        'native_mcts': bool(mod is not None and hasattr(mod, 'native_mcts')),
        'rollout_events': bool(mod is not None and hasattr(mod, 'rollout_events')),
        'rollout_batch': bool(mod is not None and hasattr(mod, 'rollout_batch')),
        'native_cancel_poll': True,
    }
