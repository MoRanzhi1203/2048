#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 后台求解「所有权 / 心跳 / 恢复」模块 —— **无 Qt**，可独立测试。

解决的问题：进程已退出但所有权记录未清理（stale lock）导致下次启动被拒绝。

身份验证（禁止仅凭 PID 数值判断）：
    pid 存活 + 进程创建时间(GetProcessTimes) 与记录一致 + 可执行镜像名一致
    + 心跳新鲜（heartbeat_at 在 STALE_HEARTBEAT_S 秒内）+ session_id 一致
    → 才认定为“同一 owner 仍活动”。

状态：
    absent   无记录
    alive    身份匹配且心跳新鲜（同一 owner 仍活动）
    stale    进程不存在 / 创建时间不符（PID 复用） / 心跳超时 / 镜像不符
    malformed 记录不可解析

安全释放：`release_stale()` 会**再次校验**当前记录仍为原 stale owner，随后以
“原子替换 + 释放标记”方式收回（避免两个写者同时认为自己是 owner）。
"""

from __future__ import annotations

import ctypes
import datetime
import json
import os
from ctypes import wintypes

import safe_store as _store

OWNER_FILE = 'owner.json'
HEARTBEAT_FILE = 'heartbeat.json'
CONTROL_FILE = 'control.json'
RELEASED_FILE = 'released.json'
STALE_HEARTBEAT_S = 20.0
CHECKPOINT_GLOBS = ('_checkpoint.json', '_resume.json', '_handoff.json')


def now_iso():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def owner_path(staging_dir):
    return os.path.join(staging_dir, OWNER_FILE)


def heartbeat_path(staging_dir):
    return os.path.join(staging_dir, HEARTBEAT_FILE)


def control_path(staging_dir):
    return os.path.join(staging_dir, CONTROL_FILE)


# ------------------------------------------------------------------ 进程身份
def proc_identity(pid):
    """返回 {alive, create_time, image}；create_time 为 Unix 秒（float），用于 PID 复用判定。"""
    out = {'alive': False, 'create_time': None, 'image': None}
    try:
        k32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return out
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:
                return out                                  # 259 = STILL_ACTIVE
            out['alive'] = True
            ctime = wintypes.FILETIME()
            etime = wintypes.FILETIME()
            ktime = wintypes.FILETIME()
            utime = wintypes.FILETIME()
            if k32.GetProcessTimes(h, ctypes.byref(ctime), ctypes.byref(etime),
                                   ctypes.byref(ktime), ctypes.byref(utime)):
                ticks = (ctime.dwHighDateTime << 32) | ctime.dwLowDateTime
                out['create_time'] = round(ticks / 1e7 - 11644473600.0, 3)
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                out['image'] = os.path.basename(buf.value)
        finally:
            k32.CloseHandle(h)
    except Exception:                                       # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------------ 读写
def write_owner(staging_dir, pid, session_id, revision=0, kind='worker'):
    os.makedirs(staging_dir, exist_ok=True)
    ident = proc_identity(pid)
    rec = {'pid': int(pid), 'session_id': str(session_id), 'revision': int(revision),
           'kind': kind, 'create_time': ident.get('create_time'),
           'image': ident.get('image'), 'started_at': now_iso(),
           'heartbeat_at': now_iso()}
    _store.atomic_write_json(owner_path(staging_dir), rec)
    return rec


def read_owner(staging_dir):
    ok, data, _err = _store.read_json(owner_path(staging_dir))
    return data if ok else None


def touch_heartbeat(staging_dir, pid, session_id, revision, step, score, wall_ms):
    os.makedirs(staging_dir, exist_ok=True)
    if os.path.exists(owner_path(staging_dir)):
        rec = read_owner(staging_dir) or {}
        rec['heartbeat_at'] = now_iso()
        rec['revision'] = int(revision)
        _store.atomic_write_json(owner_path(staging_dir), rec)
    _store.atomic_write_json(heartbeat_path(staging_dir),
                             {'pid': int(pid), 'session_id': str(session_id),
                              'revision': int(revision), 'step': int(step),
                              'score': int(score), 'wall_ms': round(float(wall_ms), 1),
                              'at': now_iso()})


def read_heartbeat(staging_dir):
    ok, data, _err = _store.read_json(heartbeat_path(staging_dir))
    return data if ok else None


def write_control(staging_dir, cmd, note=None):
    rec = {'cmd': str(cmd), 'at': now_iso()}
    if note:
        rec['note'] = note
    _store.atomic_write_json(control_path(staging_dir), rec)
    return rec


def read_control(staging_dir):
    ok, data, _err = _store.read_json(control_path(staging_dir))
    return data if ok else None


# ------------------------------------------------------------------ 状态判定
def _age_seconds(iso_text):
    try:
        t = datetime.datetime.strptime(iso_text, '%Y-%m-%d %H:%M:%S')
        return (datetime.datetime.now() - t).total_seconds()
    except (TypeError, ValueError):
        return None


def owner_status(staging_dir, max_age=STALE_HEARTBEAT_S):
    """判定当前所有权记录状态；返回 dict（含 state / 证据字段）。"""
    path = owner_path(staging_dir)
    if not os.path.exists(path):
        return {'state': 'absent', 'path': path}
    rec = read_owner(staging_dir)
    if not isinstance(rec, dict) or 'pid' not in rec or 'session_id' not in rec:
        return {'state': 'malformed', 'path': path, 'record': rec}
    ident = proc_identity(rec['pid'])
    hb = read_heartbeat(staging_dir)
    hb_age = _age_seconds((hb or {}).get('at'))
    if hb_age is None:
        hb_age = _age_seconds(rec.get('heartbeat_at'))
    info = {'path': path, 'record': rec, 'identity': ident, 'heartbeat': hb,
            'heartbeat_age_s': None if hb_age is None else round(hb_age, 1)}
    if not ident['alive']:
        return dict(info, state='stale', reason='进程不存在')
    expect_ct = rec.get('create_time')
    if expect_ct is not None and ident.get('create_time') is not None \
            and abs(float(expect_ct) - float(ident['create_time'])) > 1.0:
        return dict(info, state='stale', reason='进程创建时间不匹配（PID 复用）')
    if rec.get('image') and ident.get('image') and rec['image'] != ident['image']:
        return dict(info, state='stale', reason='镜像名不匹配（%s != %s）'
                    % (rec['image'], ident['image']))
    if hb_age is None or hb_age > max_age:
        return dict(info, state='stale', reason='心跳超时（%.1fs > %.1fs）'
                    % (hb_age if hb_age is not None else -1, max_age))
    return dict(info, state='alive')


def release_stale(staging_dir, expected_session_id=None, reason='stale'):
    """安全释放过期所有权（**再次校验**后原子收回）。返回 dict。"""
    st = owner_status(staging_dir)
    if st['state'] == 'absent':
        return {'released': False, 'state': 'absent'}
    if st['state'] == 'alive':
        return {'released': False, 'state': 'alive',
                'reason': 'owner 仍活动，拒绝释放'}
    rec = st.get('record') or {}
    if expected_session_id and rec.get('session_id') != expected_session_id:
        return {'released': False, 'state': st['state'],
                'reason': 'session_id 与预期不一致，拒绝释放'}
    # 第二次校验（TOCTOU 防护）：记录未变且仍非 alive
    st2 = owner_status(staging_dir)
    if st2['state'] == 'alive':
        return {'released': False, 'state': 'alive', 'reason': '释放前发现 owner 复活'}
    if (st2.get('record') or {}).get('pid') != rec.get('pid'):
        return {'released': False, 'state': st2['state'], 'reason': '记录在释放前被改动'}
    _store.atomic_write_json(os.path.join(staging_dir, RELEASED_FILE),
                             {'released_at': now_iso(), 'reason': reason,
                              'prev': {'pid': rec.get('pid'),
                                       'session_id': rec.get('session_id'),
                                       'revision': rec.get('revision')}})
    try:
        os.remove(owner_path(staging_dir))
    except OSError:
        pass
    try:
        os.remove(heartbeat_path(staging_dir))
    except OSError:
        pass
    return {'released': True, 'state': st['state'], 'prev': rec}


# ------------------------------------------------------------------ 检查点
def latest_checkpoint(staging_dir):
    """返回最新且可解析的检查点 (path, data)；无则 None。"""
    best = None
    if not os.path.isdir(staging_dir):
        return None
    for name in os.listdir(staging_dir):
        if not name.endswith(CHECKPOINT_GLOBS):
            continue
        p = os.path.join(staging_dir, name)
        ok, data, _err = _store.read_json(p)
        if not ok or not isinstance(data, dict):
            continue
        mtime = os.path.getmtime(p)
        if best is None or mtime > best[2]:
            best = (p, data, mtime)
    if best is None:
        return None
    return best[0], best[1]


def released_marker(staging_dir):
    ok, data, _err = _store.read_json(os.path.join(staging_dir, RELEASED_FILE))
    return data if ok else None
