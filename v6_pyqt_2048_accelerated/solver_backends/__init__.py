#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V6 计算后端包：统一协议 + 四类实现（reference / numpy / numba / cpp）。"""

from .api import (BackendBase, BackendError, BackendUnavailable, BoardOverflowError,
                  InvalidBoardError, DIRECTIONS, MAX_EXP, MAX_BITBOARD_TILE, LIMIT_TILE,
                  validate_board, board_key)
from .dispatch import (BACKEND_NAMES, probe_backends, get_backend, create_backend,
                       _read_default_backend as read_default_backend)

__all__ = [
    'BackendBase', 'BackendError', 'BackendUnavailable', 'BoardOverflowError',
    'InvalidBoardError', 'DIRECTIONS', 'MAX_EXP', 'MAX_BITBOARD_TILE', 'LIMIT_TILE',
    'validate_board', 'board_key',
    'BACKEND_NAMES', 'probe_backends', 'get_backend', 'create_backend',
    'read_default_backend', 'default_backend_name',
]


def default_backend_name():
    return read_default_backend()
