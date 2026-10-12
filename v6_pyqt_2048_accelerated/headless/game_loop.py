#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 无头游戏循环 —— **纯计算，不导入任何 Qt / GUI / QWidget**。

职责：在“当前真实对局”快照（含精确 RNG 状态）之上，用 V6 既有求解器反复决策并提交合法移动，
按受控频率产出进度，最终返回完整状态与分段耗时。

分段耗时（互不重叠，单位 ms）：
    search_ms      求解器耗时（含 backend_used/engine_used/回退原因）
    apply_logic_ms 移动 + 生成 + 分数更新（**不含**持久化）
    serialize_ms   快照序列化
    write_ms       写入（不含 fsync）
    fsync_ms       落盘（flush/fsync，可合并计入 write_ms 时须显式标注）
    checkpoint_ms  = serialize_ms + write_ms + fsync_ms
    wall_step_ms   单步完整墙钟（含求解/落子/持久化）
    wall_total_ms  整个后台会话墙钟（含启动/收尾）
"""

from __future__ import annotations

import os
import sys
import time
from time import perf_counter

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
V5_DIR = os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')
for _p in (_HERE, V6_DIR, REPO_ROOT, V5_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core                                                          # noqa: E402
import safe_store as _store                                          # noqa: E402

_STATUS_RUNNING = 'running'
_STATUS_PAUSED = 'paused'
_STATUS_STOPPED = 'stopped'
_STATUS_BUDGET = 'budget_reached'       # 显式全局限额（与回传间隔无关）
_STATUS_COMPLETED = 'completed'
_STATUS_GAME_OVER = 'game_over'
_STATUS_ERROR = 'error'


class Checkpoint:
    """当前对局的后台检查点（隔离暂存目录，原子写 + 校验和）。"""

    def __init__(self, staging_path):
        self.path = staging_path
        os.makedirs(os.path.dirname(os.path.abspath(staging_path)), exist_ok=True)

    def save(self, payload):
        payload = dict(payload)
        payload['saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        # safe_store.atomic_write_json 成功返回 None（失败会抛异常）；此处再做存在性校验
        _store.atomic_write_json(self.path, payload)
        if not os.path.exists(self.path):
            raise IOError('检查点写入失败：%s' % self.path)
        return payload

    def load(self):
        ok, data, err = _store.read_json(self.path)
        if not ok:
            raise IOError('检查点不可读：%s' % (err,))
        return data


def run_session(snapshot, limits, checkpoint=None, progress_cb=None, cancel=None, pause=None,
                solver_backend=None, native_search=False):
    """在快照上运行有界的后台求解循环。

    :param snapshot: `core.build_snapshot(...)` 的产物（当前真实对局）
    :param limits: {max_steps, max_seconds, search_time_budget?}
    :param checkpoint: 可选 `Checkpoint`（**每步**持久化，保持与既有每步存档同等安全级别）
    :param progress_cb: 进度回调（受控频率调用；返回 False 可请求停止）
    :param cancel: 可选可调用对象，返回 True 表示请求取消
    :returns: dict(status, snapshot, steps, perf, backend_used, engine_used, reason, last_checkpoint)
    """
    import solver_v6                                                 # 延迟导入（仍无 Qt）

    snap = core.validate_snapshot(snapshot)
    board = [row[:] for row in snap['board']]
    score = int(snap['score'])
    best = int(snap['best_score'])
    revision = int(snap['revision'])
    rng = core.make_rng(snap['rng_state'])
    opts = core.solver_options(snap['algorithm'], snap['strength'], backend=solver_backend,
                               native_search=native_search)

    # ---- 会话上限与「结果回传策略」严格分离（修复：回传间隔曾被误当作终止预算）----
    # max_total_steps：**显式全局限额**（None=不限，由终局/停止/时间预算决定）；兼容旧 max_steps。
    _mts = limits.get('max_total_steps', limits.get('max_steps'))
    max_total_steps = int(_mts) if _mts else None
    _tb = limits.get('time_budget_s', limits.get('max_seconds'))
    time_budget = float(_tb) if _tb else None
    # report_policy: {'mode': 'time'|'steps'|'both', 'ms': 1000, 'steps': 200}
    report_policy = limits.get('report_policy') or {
        'mode': 'both', 'ms': limits.get('progress_interval_s', 0.4) * 1000.0,
        'steps': limits.get('progress_every_steps', 25)}
    _last_report = perf_counter()
    _last_delivered = 0

    def _report_due(now):
        mode = report_policy.get('mode')
        if mode == 'steps':
            n = max(1, int(report_policy.get('steps') or 200))
            return (steps - _last_delivered) >= n
        if mode == 'time':
            ms = max(50.0, float(report_policy.get('ms') or 1000.0))
            return (now - _last_report) * 1000.0 >= ms
        ms = max(50.0, float(report_policy.get('ms') or 400.0))
        n = max(1, int(report_policy.get('steps') or 25))
        return ((now - _last_report) * 1000.0 >= ms) or (steps % n == 0)

    perf = {'search_ms': 0.0, 'apply_logic_ms': 0.0, 'serialize_ms': 0.0, 'write_ms': 0.0,
            'fsync_ms': 0.0, 'checkpoint_ms': 0.0, 'wall_step_ms': 0.0}
    backend_used = None
    engine_used = None
    reason = None
    steps = 0
    last_ckpt = None
    status = _STATUS_RUNNING
    error = None
    t_session = perf_counter()
    t_progress = 0.0

    # 起始点也立即持久化一次（便于异常退出后恢复）
    if checkpoint is not None:
        t0 = perf_counter()
        text = core.snapshot_to_json(core.build_snapshot(
            board, score, best, core.rng_state_to_json(rng.getstate()), snap['game_id'],
            revision, snap['algorithm'], snap['strength'], snap['solver_mode'],
            snap['state_version'], False))
        t1 = perf_counter()
        checkpoint.save({'schema': core.SNAPSHOT_SCHEMA, 'status': 'handoff', 'steps': 0,
                         'snapshot': text, 'game_id': snap['game_id'], 'revision': revision})
        t2 = perf_counter()
        perf['serialize_ms'] += (t1 - t0) * 1000.0
        perf['write_ms'] += (t2 - t1) * 1000.0
        perf['checkpoint_ms'] += (t2 - t0) * 1000.0
        last_ckpt = {'steps': 0, 'revision': revision, 'status': 'handoff'}

    try:
        while True:
            if cancel is not None and cancel():
                status = _STATUS_STOPPED
                break
            if pause is not None and pause():
                status = _STATUS_PAUSED
                break
            if max_total_steps is not None and steps >= max_total_steps:
                status = _STATUS_BUDGET             # 显式全局限额（非回传间隔）
                break
            if time_budget is not None and (perf_counter() - t_session) >= time_budget:
                status = _STATUS_BUDGET             # 显式时间预算
                break
            if core.is_game_over(board):
                status = _STATUS_GAME_OVER
                break
            if core.overflow_risk(board):
                status = _STATUS_ERROR
                error = '棋盘已达安全上限 %d，后台求解停止（需人工处理）' % core.MAX_TILE_LIMIT
                break

            t_step0 = perf_counter()
            decision = solver_v6.solve(board, opts['strategy'], **{k: v for k, v in opts.items()
                                                                   if k != 'strategy'})
            search_ms = float(decision.get('elapsed_ms') or 0.0)
            perf['search_ms'] += search_ms
            backend_used = decision.get('backend_used')
            engine_used = decision.get('engine_used')
            reason = decision.get('backend_fallback_reason')
            if decision.get('error'):
                status = _STATUS_ERROR
                error = '求解失败：%s' % decision['error']
                break
            direction = decision.get('best_direction')
            legal = core.legal_moves(board)
            if not direction or direction not in legal:
                status = _STATUS_STOPPED
                error = '求解返回非法/空方向：%r' % (direction,)
                break

            t_app0 = perf_counter()
            res = core.apply_move(board, direction, rng)
            board = res['board']
            score += int(res['gained'])
            best = max(best, score)
            perf['apply_logic_ms'] += (perf_counter() - t_app0) * 1000.0
            steps += 1
            revision += 1

            if checkpoint is not None:
                t_s0 = perf_counter()
                text = core.snapshot_to_json(core.build_snapshot(
                    board, score, best, core.rng_state_to_json(rng.getstate()),
                    snap['game_id'], revision, snap['algorithm'], snap['strength'],
                    snap['solver_mode'], snap['state_version'], core.is_game_over(board)))
                t_s1 = perf_counter()
                checkpoint.save({'schema': core.SNAPSHOT_SCHEMA, 'status': 'running',
                                 'steps': steps, 'snapshot': text,
                                 'game_id': snap['game_id'], 'revision': revision,
                                 'direction': direction, 'spawn': res['spawn'],
                                 'spawn_pos': res['spawn_pos']})
                t_s2 = perf_counter()
                perf['serialize_ms'] += (t_s1 - t_s0) * 1000.0
                perf['write_ms'] += (t_s2 - t_s1) * 1000.0
                perf['checkpoint_ms'] += (t_s2 - t_s0) * 1000.0
                last_ckpt = {'steps': steps, 'revision': revision, 'status': 'running'}

            perf['wall_step_ms'] += (perf_counter() - t_step0) * 1000.0

            now = perf_counter()
            if progress_cb is not None and _report_due(now):
                _last_report = now
                _last_delivered = steps
                wake = perf_counter()
                keep = progress_cb({
                    'protocol_version': 2, 'type': 'progress',
                    'game_id': snap['game_id'], 'session_id': snap['game_id'],
                    'revision': revision, 'sequence': steps,
                    'step': steps, 'total_committed_moves': steps,
                    'score': score, 'max_tile': core.max_tile(board), 'board': board,
                    'report_reason': ('periodic_steps'
                                      if report_policy.get('mode') == 'steps'
                                      else 'periodic_time'),
                    'backend_used': backend_used, 'engine_used': engine_used,
                    'reason': reason, 'search_ms': round(perf['search_ms'], 3),
                    'wall_ms': round((perf_counter() - t_session) * 1000.0, 3),
                    'steps_per_s': round(steps / max(1e-9, perf_counter() - t_session), 3),
                    'last_checkpoint': last_ckpt, 'status': 'running',
                })
                perf['event_dispatch_ms'] = perf.get('event_dispatch_ms', 0.0) + \
                    (perf_counter() - wake) * 1000.0
                if keep is False:
                    status = _STATUS_STOPPED
                    break

    except Exception as exc:                                          # noqa: BLE001
        status = _STATUS_ERROR
        error = '%s: %s' % (type(exc).__name__, exc)

    if status == _STATUS_RUNNING:
        status = _STATUS_COMPLETED
    perf['wall_total_ms'] = (perf_counter() - t_session) * 1000.0
    final_snapshot = core.build_snapshot(
        board, score, best, core.rng_state_to_json(rng.getstate()), snap['game_id'],
        revision, snap['algorithm'], snap['strength'], snap['solver_mode'],
        snap['state_version'], core.is_game_over(board))
    return {
        'protocol_version': 2,
        'type': 'final',
        'status': status,
        'report_reason': {'game_over': 'terminal', 'stopped': 'stop', 'paused': 'pause',
                          'budget_reached': 'explicit_budget', 'error': 'error',
                          'completed': 'terminal'}.get(status, status),
        'total_committed_moves': steps,
        'reason': error,
        'snapshot': final_snapshot,
        'steps': steps,
        'perf': {k: round(v, 3) for k, v in perf.items()},
        'backend_used': backend_used,
        'engine_used': engine_used,
        'fallback_reason': reason,
        'last_checkpoint': last_ckpt,
        'steps_per_s': round(steps / max(1e-9, perf['wall_total_ms'] / 1000.0), 3),
    }
