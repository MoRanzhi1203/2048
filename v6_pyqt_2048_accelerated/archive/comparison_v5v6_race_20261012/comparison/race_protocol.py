#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5.1 ↔ V6.2 双窗口实时 AI 求解竞赛 —— 会话协议与共享工具。

本模块只做「协议 / 文件 / 纯函数」，**不 import Qt、不改动 V5/V6 源码**：
- 会话目录布局、会话配置（session.json）、控制文件（control.json）、
  双边逐步日志（side_<side>.jsonl）、HUD 快照（hud_<side>.json）、汇总（race_summary.*）；
- 初始棋盘的可复现生成（与 v3 `add_new_tile` 同序：行主序空位 + choice + 0.9 阈值）；
- 原子写入（复用根目录 `safe_store`）。

所有文件名均为 ASCII，内容 UTF-8。
"""

from __future__ import annotations

import json
import os
import random
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import safe_store as _store  # noqa: E402

SIDES = ('v5', 'v6')
MODES = ('A', 'B', 'C')
MODE_LABELS = {
    'A': 'A 同步逐步求解',
    'B': 'B 自由竞速',
    'C': 'C 固定工作量搜索对照',
}

# ---------------------------------------------------------------- 路径


def session_paths(session_dir):
    return {
        'dir': session_dir,
        'session': os.path.join(session_dir, 'session.json'),
        'control': os.path.join(session_dir, 'control.json'),
        'summary_json': os.path.join(session_dir, 'race_summary.json'),
        'summary_csv': os.path.join(session_dir, 'race_summary.csv'),
        'launch': os.path.join(session_dir, 'launch.json'),
        'screenshot': os.path.join(session_dir, 'race_desktop.png'),
    }


def side_log_path(session_dir, side):
    return os.path.join(session_dir, 'side_%s.jsonl' % side)


def side_hud_path(session_dir, side):
    return os.path.join(session_dir, 'hud_%s.json' % side)


def side_history_root(session_dir, side):
    """该侧独立存档根（经 `2048_HISTORY_DIR` 重定向，互不干扰、不触碰生产存档）。"""
    return os.path.join(session_dir, 'history', side)


# ------------------------------------------------------------ 读写工具


def read_json(path, default=None):
    ok, data, _err = _store.read_json(path)
    return data if ok else default


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _store.atomic_write_json(path, obj)


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n')
        f.flush()


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def now_iso():
    return time.strftime('%Y-%m-%d %H:%M:%S')


# ------------------------------------------------------------ 会话配置


DEFAULT_SESSION = {
    'mode': 'B',
    'seed': 2048,
    'max_steps': 200,
    'max_seconds': 180.0,
    'auto_exit': False,
    'animate': True,
    'particles': False,          # 竞赛态默认关闭粒子层（两侧一致，降低渲染压力/稳定性）
    'algorithm': {'strategy': 'expectimax', 'depth': 4, 'time_limit': 0.3},
    'v6_override': {},           # 仅 V6 侧注入（如 native_search / backend / prune）
    'step_interval_ms': 900,     # A 模式：协调器推进步进的最小间隔
}


def build_session(session_id, mode='B', seed=2048, max_steps=200, max_seconds=180.0,
                  auto_exit=False, algorithm=None, v6_override=None, animate=True,
                  step_interval_ms=900, particles=False):
    cfg = dict(DEFAULT_SESSION)
    cfg.update({
        'session_id': session_id, 'mode': mode, 'seed': int(seed),
        'max_steps': int(max_steps), 'max_seconds': float(max_seconds),
        'auto_exit': bool(auto_exit), 'animate': bool(animate),
        'particles': bool(particles),
        'algorithm': dict(algorithm or DEFAULT_SESSION['algorithm']),
        'v6_override': dict(v6_override or {}),
        'step_interval_ms': int(step_interval_ms),
        'created_at': now_iso(),
    })
    return cfg


def load_session(session_file):
    return read_json(session_file)


# ------------------------------------------------------------ 初始棋盘


def generate_initial_board(seed, grid_size=4):
    """与 v3 `add_new_tile` 完全同序的可复现初始棋盘（行主序空位）。"""
    rng = random.Random(int(seed))
    grid = [[0] * grid_size for _ in range(grid_size)]
    for _ in range(2):
        empties = [(i, j) for i in range(grid_size) for j in range(grid_size)
                   if grid[i][j] == 0]
        if not empties:
            break
        i, j = rng.choice(empties)
        grid[i][j] = 2 if rng.random() < 0.9 else 4
    return grid


# ------------------------------------------------------------ 控制文件


def read_control(session_dir):
    return read_json(os.path.join(session_dir, 'control.json'), default={})


def write_control(session_dir, cmd=None, step_index=None, note=None):
    path = os.path.join(session_dir, 'control.json')
    cur = read_json(path, default={}) or {}
    if cmd is not None:
        cur['cmd'] = cmd
        cur['seq'] = int(cur.get('seq', 0)) + 1
    if step_index is not None:
        cur['step_index'] = int(step_index)
    if note is not None:
        cur['note'] = note
    cur['updated_at'] = now_iso()
    write_json(path, cur)
    return cur


# ------------------------------------------------------------ 逐步日志


class SideLogger:
    """单侧逐步日志 + HUD 快照写入（原子/追加，UTF-8）。"""

    def __init__(self, session_dir, side):
        self.dir = session_dir
        self.side = side
        self.jsonl = side_log_path(session_dir, side)
        self.hud = side_hud_path(session_dir, side)
        self.control_file = os.path.join(session_dir, 'control.json')

    def event(self, kind, **fields):
        rec = {'side': self.side, 'kind': kind, 't': now_iso(), 'wall': time.time()}
        rec.update(fields)
        append_jsonl(self.jsonl, rec)
        return rec

    def step(self, **fields):
        return self.event('step', **fields)

    def hud_snapshot(self, **fields):
        write_json(self.hud, fields)

    def control(self):
        return read_control(self.dir)

    def control_seq(self):
        return int(self.control().get('seq', 0))

    def control_cmd(self):
        return self.control().get('cmd')

    def control_step_index(self):
        return int(self.control().get('step_index', 0))


# ------------------------------------------------------------ 汇总


def _side_metrics(session_dir, side):
    events = read_jsonl(side_log_path(session_dir, side))
    steps = [e for e in events if e.get('kind') == 'step']
    injected = [e for e in events if e.get('kind') == 'board_injected']
    hud = read_json(side_hud_path(session_dir, side), default={}) or {}
    samples = sorted(float(s['solver_ms']) for s in steps if s.get('solver_ms') is not None)
    n = len(samples)
    p95 = samples[min(n - 1, int(round(0.95 * (n - 1))))] if n else 0.0
    avg = (sum(samples) / n) if n else 0.0
    last = steps[-1] if steps else {}
    return {
        'side': side,
        'steps': len(steps),
        'decisions': len(steps),
        'initial_board': (injected[-1]['board'] if injected else None),
        'final_score': (last.get('score_now') if last else None),
        'final_max_tile': (last.get('max_tile') if last else None),
        'last_direction': (last.get('direction') if last else None),
        'avg_search_ms': round(avg, 4),
        'p95_search_ms': round(p95, 4),
        'search_cum_ms': round(sum(samples), 3),
        'wall_s': hud.get('wall_s'),
        'anim_cum_ms': hud.get('anim_cum_ms'),
        'sched_cum_ms': hud.get('sched_cum_ms'),
        'sims': hud.get('sims'),
        'backend_used': hud.get('backend_used'),
        'engine_used': hud.get('engine_used'),
        'status': hud.get('status'),
        'timed_out_count': hud.get('timed_out_count'),
        'game_over': hud.get('game_over'),
    }


def build_summary(session_dir):
    cfg = read_json(os.path.join(session_dir, 'session.json'), default={}) or {}
    per = {s: _side_metrics(session_dir, s) for s in SIDES}
    v5_steps = [e for e in read_jsonl(side_log_path(session_dir, 'v5')) if e.get('kind') == 'step']
    v6_steps = [e for e in read_jsonl(side_log_path(session_dir, 'v6')) if e.get('kind') == 'step']
    divergence = None
    for a, b in zip(v5_steps, v6_steps):
        if a.get('direction') != b.get('direction'):
            divergence = {'step': a.get('step'), 'v5': a.get('direction'),
                          'v6': b.get('direction')}
            break
    same_initial = (per['v5']['initial_board'] is not None
                    and per['v5']['initial_board'] == per['v6']['initial_board'])
    finished = (per['v5']['status'] in ('idle', None) and per['v6']['status'] in ('idle', None))
    speed_ratio = None
    if per['v5']['avg_search_ms'] and per['v6']['avg_search_ms']:
        speed_ratio = round(per['v5']['avg_search_ms'] / per['v6']['avg_search_ms'], 3)
    return {
        'kind': 'v5_v6_live_race_summary',
        'session_id': cfg.get('session_id'),
        'mode': cfg.get('mode'),
        'mode_label': MODE_LABELS.get(cfg.get('mode')),
        'seed': cfg.get('seed'),
        'algorithm': cfg.get('algorithm'),
        'v6_override': cfg.get('v6_override'),
        'max_steps': cfg.get('max_steps'),
        'max_seconds': cfg.get('max_seconds'),
        'same_initial_board': same_initial,
        'first_divergence': divergence,
        'boards_identical_so_far': divergence is None,
        'note': ('双方初始棋盘一致；若 first_divergence 为 null 表示逐步方向一致、棋盘序列相同；'
                 '一旦分叉，按各自合法空位映射随机事件，不再声称后续棋盘相同。'),
        'sides': per,
        'avg_search_ms_speed_ratio_v5_over_v6': speed_ratio,
        'generated_at': now_iso(),
    }


def write_summary(session_dir):
    summary = build_summary(session_dir)
    paths = session_paths(session_dir)
    write_json(paths['summary_json'], summary)
    import csv
    with open(paths['summary_csv'], 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['side', 'steps', 'final_score', 'final_max_tile', 'avg_search_ms',
                    'p95_search_ms', 'search_cum_ms', 'wall_s', 'backend_used', 'engine_used',
                    'status'])
        for s in SIDES:
            m = summary['sides'][s]
            w.writerow([s, m['steps'], m['final_score'], m['final_max_tile'], m['avg_search_ms'],
                        m['p95_search_ms'], m['search_cum_ms'], m['wall_s'], m['backend_used'],
                        m['engine_used'], m['status']])
    return summary
