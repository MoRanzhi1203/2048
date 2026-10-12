#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竞赛窗口（V6 侧）：复用 V6 GUI（V5 界面 + V6 计算后端/原生整树），仅叠加竞速协调。

**不修改 V6/V5 源码**：以子类方式复用 `v6_pyqt_2048_accelerated.V6MainWindow`。
该侧使用 `solver_v6`，结果携带真实 backend_used / engine_used（native / python_kernel / reference）。
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
V6_DIR = os.path.dirname(_HERE)
REPO_ROOT = os.path.dirname(V6_DIR)
for _p in (_HERE, V6_DIR, REPO_ROOT, os.path.join(REPO_ROOT, 'v5_pyqt_2048_solver')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import v6_pyqt_2048_accelerated as _v6                                  # noqa: E402
from race_common import RaceMixin                                       # noqa: E402

from PyQt5.QtCore import Qt                                             # noqa: E402
from PyQt5.QtGui import QFont                                           # noqa: E402
from PyQt5.QtWidgets import QApplication                                # noqa: E402


class RaceWindowV6(RaceMixin, _v6.V6MainWindow):
    RACE_SIDE = 'v6'
    RACE_LABEL = 'V6'

    def _race_solver_overrides(self):
        d = super()._race_solver_overrides()
        d.update(self._race_cfg.get('v6_override') or {})   # 如 native_search / backend / prune
        return d


def _install_race_excepthook():
    """见 race_window_v5：自定义 sys.excepthook 避免 PyQt5 槽异常触发 qFatal/abort。"""
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
    app.setWindowIcon(_v6.build_app_icon())
    font = QFont('Microsoft YaHei', 10)
    if hasattr(font, 'setFamilies'):
        font.setFamilies(['Microsoft YaHei', 'Microsoft YaHei UI', 'SimHei'])
    app.setFont(font)
    window = RaceWindowV6()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
