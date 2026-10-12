#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛窗口（V5 侧）：复用 V5.1 GUI + 纯 Python/Reference 求解，仅叠加竞速协调。

**不修改 V5 源码**：以子类方式复用 `v5_pyqt_2048_solver.SolverMainWindow`。
本进程内 `solver` 仍为 `solver_2048`（纯 Python），故该侧 engine_used = reference。
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
V5_DIR = os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')
for _p in (_HERE, V5_DIR, V6_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v5_pyqt_2048_solver as _v5gui                                   # noqa: E402
from race_common import RaceMixin                                      # noqa: E402

from PyQt5.QtCore import Qt                                            # noqa: E402
from PyQt5.QtGui import QFont                                          # noqa: E402
from PyQt5.QtWidgets import QApplication                               # noqa: E402

v4 = _v5gui.v4


class RaceWindowV5(RaceMixin, _v5gui.SolverMainWindow):
    RACE_SIDE = 'v5'
    RACE_LABEL = 'V5'


def _install_race_excepthook():
    """PyQt5 在槽函数抛出未捕获异常时会调用 qFatal -> abort（Windows 0xc0000409）。

    安装自定义 sys.excepthook 可让 PyQt5 改为调用它（不再 abort），我们同时把
    完整栈写入 <session>/excepthook.log，便于定位而不丢证据、不打断竞赛。
    """
    import os as _os
    import traceback

    def _hook(etype, value, tb):
        text = ''.join(traceback.format_exception(etype, value, tb))
        session = _os.environ.get('V6_RACE_SESSION')
        if session:
            try:
                with open(_os.path.join(session, 'excepthook.log'), 'a', encoding='utf-8') as f:
                    f.write(text + '\n')
            except Exception:                                   # noqa: BLE001
                pass
        try:
            sys.stderr.write(text)
            sys.stderr.flush()
        except Exception:                                       # noqa: BLE001
            pass

    sys.excepthook = _hook


def main():
    import faulthandler
    faulthandler.enable()
    _install_race_excepthook()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setWindowIcon(v4.build_app_icon())
    font = QFont('Microsoft YaHei', 10)
    if hasattr(font, 'setFamilies'):
        font.setFamilies(['Microsoft YaHei', 'Microsoft YaHei UI', 'SimHei'])
    app.setFont(font)
    window = RaceWindowV5()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
