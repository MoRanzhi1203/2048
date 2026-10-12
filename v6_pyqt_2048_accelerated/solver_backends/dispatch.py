#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 后端注册、能力探测、选择与回退。

规则（对齐《V6 指令》§2/§9）：
- 没有可用 Numba / C++ 时自动退回 reference，允许正常手动游戏与五策略。
- 后端选择不静默替换算法；回退必须给出清晰原因（backend_fallback_reason）。
- 默认后端依据实测证据决定（见 benchmarks/reports/）；无实测收益时默认 reference。
"""

from __future__ import annotations

import json
import os

from .api import BackendUnavailable, BackendError

BACKEND_NAMES = ('reference', 'numpy', 'numba', 'cpp')

_V6_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_CHOICE_FILE = os.path.join(_V6_DIR, 'benchmarks', 'backend_default.json')

_cpp_module = None
_cpp_error = None


def _load_cpp():
    """尝试导入已构建的 C++ bitboard 扩展；失败则记录原因（BUILD_BLOCKED）。"""
    global _cpp_module, _cpp_error
    if _cpp_module is not None or _cpp_error is not None:
        return _cpp_module
    try:
        from . import bitboard_cpp as _pkg
        mod = _pkg.load_extension()
        if mod is None:
            _cpp_error = 'BUILD_BLOCKED: bitboard_cpp 扩展未构建（缺少 .pyd）'
        _cpp_module = mod
    except Exception as e:  # pragma: no cover - depends on build state
        _cpp_error = '%s: %s' % (type(e).__name__, e)
        _cpp_module = None
    return _cpp_module


_PROBE_CACHE = {}


def reset_probe_cache():
    """清空探测缓存与 C++ 加载缓存（供测试/环境变化后重新探测）。"""
    _PROBE_CACHE.clear()
    global _cpp_module, _cpp_error
    _cpp_module = None
    _cpp_error = None


def _probe_one(name: str) -> dict:
    """探测**单个**后端的可用性（只导入该后端所需依赖，避免无关冷导入）。"""
    if name in _PROBE_CACHE:
        return _PROBE_CACHE[name]
    if name == 'reference':
        try:
            from .reference import ReferenceBackend
            ok, reason = ReferenceBackend().available()
            entry = {'available': bool(ok), 'reason': reason, 'kind': 'python'}
        except Exception as e:                          # pragma: no cover
            entry = {'available': False, 'reason': '%r' % (e,), 'kind': 'python'}
    elif name == 'numpy':
        try:
            from .numpy_core import NumpyBackend
            ok, reason = NumpyBackend().available()
            entry = {'available': bool(ok), 'reason': reason, 'kind': 'numpy'}
        except Exception as e:
            entry = {'available': False, 'reason': '%r' % (e,), 'kind': 'numpy'}
    elif name == 'numba':
        try:
            from .numba_core import NumbaBackend
            ok, reason = NumbaBackend().available()
            entry = {'available': bool(ok), 'reason': reason, 'kind': 'numba'}
        except Exception as e:
            entry = {'available': False, 'reason': '%r' % (e,), 'kind': 'numba'}
    elif name == 'cpp':
        mod = _load_cpp()
        if mod is None:
            entry = {'available': False,
                     'reason': 'BUILD_BLOCKED: %s' % (_cpp_error or 'extension not built'),
                     'kind': 'cpp'}
        else:
            try:
                ok, reason = mod.available()
                entry = {'available': bool(ok), 'reason': reason, 'kind': 'cpp'}
            except Exception as e:                      # pragma: no cover
                entry = {'available': False, 'reason': 'BUILD_BLOCKED: %r' % (e,), 'kind': 'cpp'}
    else:
        entry = {'available': False, 'reason': '未知后端：%s' % name, 'kind': name}
    _PROBE_CACHE[name] = entry
    return entry


def probe_backends(only=None) -> dict:
    """探测后端可用性，返回 {name: {available, reason, kind}}。

    ``only`` 指定时**只探测该后端**（并缓存），从而避免为 cpp/reference 路径冷导入
    numpy/numba 等无关依赖 —— 这是后台 worker 首解卡顿的关键修复之一。
    不传 ``only`` 时返回完整能力矩阵（GUI 展示用；结果同样按后端缓存）。
    """
    if only is not None:
        return {only: _probe_one(only)}
    return {n: _probe_one(n) for n in BACKEND_NAMES}


def _read_default_backend() -> str:
    env = os.environ.get('V6_BACKEND')
    if env and env in BACKEND_NAMES:
        return env
    if os.path.exists(_DEFAULT_CHOICE_FILE):
        try:
            with open(_DEFAULT_CHOICE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            chosen = data.get('default_backend')
            if chosen in BACKEND_NAMES:
                return chosen
        except Exception:                               # pragma: no cover
            pass
    return 'reference'


def create_backend(name: str):
    """按名称创建后端实例；不可用抛 BackendUnavailable（只探测该后端）。"""
    probe = probe_backends(only=name)
    if name not in BACKEND_NAMES:
        raise BackendUnavailable('未知后端：%s' % name)
    if not probe[name]['available']:
        raise BackendUnavailable('%s 不可用：%s' % (name, probe[name]['reason']))
    if name == 'reference':
        from .reference import ReferenceBackend
        return ReferenceBackend()
    if name == 'numpy':
        from .numpy_core import NumpyBackend
        return NumpyBackend()
    if name == 'numba':
        from .numba_core import NumbaBackend
        return NumbaBackend()
    if name == 'cpp':
        from .bitboard_cpp_backend import CppBitboardBackend
        return CppBitboardBackend(_load_cpp())
    raise BackendUnavailable('未知后端：%s' % name)


def get_backend(requested: str = 'auto', allow_fallback: bool = True):
    """解析并返回 ``(backend_instance, backend_used, fallback_reason)``。

    requested: 'auto' | 'reference' | 'numpy' | 'numba' | 'cpp'
    """
    if requested in (None, 'auto'):
        requested = _read_default_backend()
    # 只探测**被请求的后端**：cpp/reference 路径不再冷导入 numpy/numba
    probe = probe_backends(only=requested)
    if requested == 'reference' or probe.get(requested, {}).get('available'):
        try:
            return create_backend(requested), requested, None
        except Exception as e:
            if not allow_fallback:
                raise
            reason = '%s 创建失败：%s' % (requested, e)
    else:
        reason = '%s 不可用：%s' % (requested, probe.get(requested, {}).get('reason', '未注册'))

    if not allow_fallback:
        raise BackendUnavailable(reason)
    # 回退顺序：numba -> numpy -> reference（逐个按需探测，避免无关冷导入）
    for cand in ('numba', 'numpy', 'reference'):
        if cand == requested:
            continue
        if probe_backends(only=cand).get(cand, {}).get('available'):
            try:
                return create_backend(cand), cand, reason
            except Exception:                            # pragma: no cover
                continue
    raise BackendUnavailable('所有后端均不可用：%s' % reason)
