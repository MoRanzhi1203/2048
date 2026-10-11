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


def probe_backends() -> dict:
    """探测四个后端的可用性，返回 {name: {available, reason, kind}}。"""
    out = {}

    # reference
    try:
        from .reference import ReferenceBackend
        b = ReferenceBackend()
        ok, reason = b.available()
        out['reference'] = {'available': bool(ok), 'reason': reason, 'kind': 'python'}
    except Exception as e:                              # pragma: no cover
        out['reference'] = {'available': False, 'reason': '%r' % (e,), 'kind': 'python'}

    # numpy
    try:
        from .numpy_core import NumpyBackend
        b = NumpyBackend()
        ok, reason = b.available()
        out['numpy'] = {'available': bool(ok), 'reason': reason, 'kind': 'numpy'}
    except Exception as e:
        out['numpy'] = {'available': False, 'reason': '%r' % (e,), 'kind': 'numpy'}

    # numba
    try:
        from .numba_core import NumbaBackend
        b = NumbaBackend()
        ok, reason = b.available()
        out['numba'] = {'available': bool(ok), 'reason': reason, 'kind': 'numba'}
    except Exception as e:
        out['numba'] = {'available': False, 'reason': '%r' % (e,), 'kind': 'numba'}

    # cpp (built extension)
    mod = _load_cpp()
    if mod is None:
        out['cpp'] = {'available': False,
                      'reason': 'BUILD_BLOCKED: %s' % (_cpp_error or 'extension not built'),
                      'kind': 'cpp'}
    else:
        try:
            ok, reason = mod.available()
            out['cpp'] = {'available': bool(ok), 'reason': reason, 'kind': 'cpp'}
        except Exception as e:                          # pragma: no cover
            out['cpp'] = {'available': False, 'reason': 'BUILD_BLOCKED: %r' % (e,),
                          'kind': 'cpp'}

    return out


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
    """按名称创建后端实例；不可用抛 BackendUnavailable。"""
    probe = probe_backends()
    if name not in probe:
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
    probe = probe_backends()
    if requested in (None, 'auto'):
        requested = _read_default_backend()

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
    # 回退顺序：numba -> numpy -> reference（保留 numpy 依赖缺失时仍能回到 reference）
    for cand in ('numba', 'numpy', 'reference'):
        if probe.get(cand, {}).get('available'):
            try:
                return create_backend(cand), cand, reason
            except Exception:                            # pragma: no cover
                continue
    raise BackendUnavailable('所有后端均不可用：%s' % reason)
