#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 bitboard_cpp 包：承载已构建的 C++ 扩展 ``bitboard_cpp.<abi>.pyd``。

未构建时本包仍可 import（返回 None），由 dispatch 记录 BUILD_BLOCKED 并回退 reference。
"""

import glob
import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_extension():
    """返回编译好的扩展模块；未构建返回 None。"""
    if importlib.util.find_spec(__name__ + '.bitboard_cpp') is not None:
        return importlib.import_module(__name__ + '.bitboard_cpp')
    cands = sorted(glob.glob(os.path.join(_HERE, 'bitboard_cpp*.pyd'))
                   + glob.glob(os.path.join(_HERE, 'bitboard_cpp*.so')))
    if not cands:
        return None
    spec = importlib.util.spec_from_file_location(__name__ + '.bitboard_cpp', cands[-1])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def built_path():
    cands = sorted(glob.glob(os.path.join(_HERE, 'bitboard_cpp*.pyd'))
                   + glob.glob(os.path.join(_HERE, 'bitboard_cpp*.so')))
    return cands[-1] if cands else None
