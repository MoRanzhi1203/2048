#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qt 致命退出取证（V6 专用，尽量零依赖、可长期常开）。

背景（已证实）：
    Windows 事件日志 / WER 对全部 16 次崩溃给出**完全一致**的签名：
        Faulting module = Qt5Core.dll 5.15.2, offset 0x204e8, code 0xc0000409,
        **异常数据 = 7 = __fastfail(FAST_FAIL_FATAL_APP_EXIT)**
    即进程是**主动 abort()**（Qt 的 fatal 路径：qt_message_fatal / qFatal），
    不是内存越界或 GS cookie 破坏；而 stderr 为空，说明 Qt 的致命文本未被捕获
    （Qt 在 Windows 上默认走 OutputDebugString，且未安装消息处理器时无人接收）。

本模块做三件事，使“下一次崩溃”能直接给出致命文本与线程栈：
    1) `qInstallMessageHandler`：把 Qt 的全部消息（尤其 QtFatalMsg）写入 qt_messages.log；
    2) `faulthandler`：致命信号/异常时 dump 所有线程 Python 栈；
    3) 兜底钩子：`sys.excepthook` / `threading.excepthook` / `sys.unraisablehook`
       （PyQt5 在槽函数抛出未捕获异常时会走 qFatal；自定义 excepthook 可截获并记录）。

用法（V6 入口已自动调用）：`install()`；环境变量 `V6_QT_CAPTURE_DIR` 可改日志目录，
`V6_QT_CAPTURE=0` 可整体关闭。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback

_STATE = {'installed': False, 'dir': None, 'msg_fh': None, 'msg_count': 0}
MAX_LOG_BYTES = 4 * 1024 * 1024


def _open_log(path):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    hi = path + '.1'
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_BYTES:
            if os.path.exists(hi):
                os.remove(hi)
            os.replace(path, hi)
    except OSError:
        pass
    fh = open(path, 'a', encoding='utf-8', errors='replace')
    fh.write('\n===== session start %s pid=%s =====\n'
             % (time.strftime('%Y-%m-%d %H:%M:%S'), os.getpid()))
    fh.flush()
    return fh


def _write(text):
    fh = _STATE['msg_fh']
    if fh is None:
        return
    try:
        fh.write('[%s] %s\n' % (time.strftime('%H:%M:%S'), text.rstrip('\n')))
        fh.flush()
    except Exception:                                            # noqa: BLE001
        pass


def install(out_dir=None, enable=True):
    """安装 Qt 消息捕获 + 崩溃取证。返回日志目录（未安装返回 None）。"""
    if _STATE['installed']:
        return _STATE['dir']
    if not enable or os.environ.get('V6_QT_CAPTURE', '1') == '0':
        return None
    try:
        from PyQt5 import QtCore
    except Exception:                                            # noqa: BLE001
        return None

    out_dir = out_dir or os.environ.get('V6_QT_CAPTURE_DIR') or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'diagnostics', 'qt_crash')
    _STATE['dir'] = out_dir
    _STATE['msg_fh'] = _open_log(os.path.join(out_dir, 'qt_messages.log'))

    # 1) Qt 消息处理器：致命消息在 abort 之前一定会经过这里
    _LEVEL = {QtCore.QtDebugMsg: 'DEBUG', QtCore.QtInfoMsg: 'INFO',
              QtCore.QtWarningMsg: 'WARNING', QtCore.QtCriticalMsg: 'CRITICAL',
              QtCore.QtFatalMsg: 'FATAL'}

    def handler(mode, ctx, message):
        _STATE['msg_count'] += 1
        level = _LEVEL.get(mode, str(int(mode)))
        tag = '<<<QTFATAL>>>' if mode == QtCore.QtFatalMsg else ''
        _write('%s %s %s' % (level, tag, message))
        if mode == QtCore.QtFatalMsg:
            # 致命：把 Python 侧全线程栈一并落盘，随后 Qt 才会 abort
            try:
                fh = _STATE['msg_fh']
                fh.write('--- python thread stacks at QTFATAL ---\n')
                faulthandler_dump(fh)
                fh.write('--- end stacks ---\n')
                fh.flush()
            except Exception:                                    # noqa: BLE001
                pass

    QtCore.qInstallMessageHandler(handler)

    # 2) faulthandler：原生致命信号（含 Windows SEH）时 dump Python 栈
    try:
        import faulthandler
        fh = _open_log(os.path.join(out_dir, 'faulthandler.log'))
        faulthandler.enable(file=fh, all_threads=True)
    except Exception:                                            # noqa: BLE001
        pass

    # 3) 兜底钩子
    def excepthook(etype, value, tb):
        text = ''.join(traceback.format_exception(etype, value, tb))
        _write('PY_EXCEPTION\n' + text)
        sys.__stderr__.write(text)
        sys.__stderr__.flush()
    sys.excepthook = excepthook

    def thread_hook(args):
        text = ''.join(traceback.format_exception(args.exc_type, args.exc_value,
                                                  args.exc_traceback))
        _write('THREAD_EXCEPTION in %s\n%s' % (args.thread.name if args.thread else '?', text))
    threading.excepthook = thread_hook

    def unraisable_hook(args):
        _write('UNRAISABLE: %r\n%s' % (args.exc_value,
                                       ''.join(traceback.format_exception(
                                           args.exc_type, args.exc_value, args.exc_traceback))))
    sys.unraisablehook = unraisable_hook

    _STATE['installed'] = True
    _write('capture installed: argv=%s cwd=%s' % (sys.argv, os.getcwd()))
    return out_dir


def faulthandler_dump(fh):
    import faulthandler
    faulthandler.dump_traceback(file=fh, all_threads=True)


def status():
    return {'installed': _STATE['installed'], 'dir': _STATE['dir'],
            'messages': _STATE['msg_count']}


if __name__ == '__main__':
    d = install()
    print('installed ->', d)
