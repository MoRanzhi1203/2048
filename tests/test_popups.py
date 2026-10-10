#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第四版 / 第五版：主题化弹窗回归测试

覆盖：
    1. 静态检查：v4/v5 源码不再使用原生 QMessageBox；
    2. 游戏结束弹窗（v4）：外观/返回值/关闭语义/不重复弹出；
    3. 游戏胜利弹窗（v4）：继续挑战 / 重新开始 / Enter / Escape 语义；
    4. 弹窗外观：宽度、无文字裁切、暖棕配色、模态；
    5. 关闭后焦点恢复；
    6. v5 导出相关弹窗（无结果 / 导出成功）均为主题化弹窗；
    7. v5 结果对话框为主题化内容弹窗；
    8. 高 DPI（QT_SCALE_FACTOR=1.5）：弹窗文字不被裁切。

用法：python tests/test_popups.py
返回码：0=全部通过；1=存在失败。
"""

import ast
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("2048_HISTORY_DIR", tempfile.mkdtemp(prefix="2048_popup_hist_"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

for _d in ("v3_pyqt_2048", "v4_pyqt_2048_animated", "v5_pyqt_2048_solver"):
    _p = os.path.join(ROOT, _d)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLabel   # noqa: E402
from PyQt5.QtCore import Qt, QTimer                                      # noqa: E402

import ui_theme as theme                                                 # noqa: E402

RESULTS = []


def record(item, ok, detail=""):
    RESULTS.append((item, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", item,
                         (" | " + detail) if detail else ""), flush=True)


def pump(app, ms):
    import time
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.004)


# ---------------------------------------------------------------- 静态检查 ---
def uses_qmessagebox(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "QMessageBox":
                    return True
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "QMessageBox"):
            return True
    return False


def test_static_no_qmessagebox():
    for name, rel in (("v4", "v4_pyqt_2048_animated/v4_pyqt_2048_animated.py"),
                      ("v5", "v5_pyqt_2048_solver/v5_pyqt_2048_solver.py")):
        path = os.path.join(ROOT, rel)
        used = uses_qmessagebox(path)
        record("%s 源码不再使用原生 QMessageBox" % name, not used)


# --------------------------------------------------------------- 弹窗交互 ---
def auto_click(app, index):
    def _do():
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(30, _do)
            return
        dlg._choose(index)
    QTimer.singleShot(40, _do)


def auto_escape(app):
    def _do():
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(30, _do)
            return
        dlg.reject()
    QTimer.singleShot(40, _do)


def auto_enter(app):
    def _do():
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(30, _do)
            return
        for btn in dlg.findChildren(QPushButton):
            if btn.isDefault():
                btn.click()
                return
    QTimer.singleShot(40, _do)


def build_v4(app):
    import v4_pyqt_2048_animated as v4
    w = v4.MainWindow()
    w.show()
    pump(app, 120)
    return w


def build_v5(app):
    import v5_pyqt_2048_solver as v5
    w = v5.SolverMainWindow()
    w.show()
    pump(app, 150)
    return w


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    import v4_pyqt_2048_animated as v4

    test_static_no_qmessagebox()

    # ---- 游戏结束弹窗 ----
    w = build_v4(app)
    gid_before = w.model.game_id
    auto_click(app, 1)                      # 关闭
    w.show_game_over()
    record("v4 游戏结束弹窗：关闭语义（不改变棋局）",
           w.model.game_id == gid_before and w.model.game_over is False,
           "game_id 未变=%s" % (w.model.game_id == gid_before))

    # 不重复弹出：第二次调用应立即返回（内部守卫），不会阻塞
    shown = {"n": 0}
    orig = theme.ThemedDialog.exec_choice

    def counting(self):
        shown["n"] += 1
        return 1
    theme.ThemedDialog.exec_choice = counting
    try:
        w.show_game_over()                  # _game_over_notified 已为 True -> 直接返回
        w.show_game_over()
        record("v4 游戏结束弹窗：同一局不重复弹出", shown["n"] == 0,
               "再次调用弹出次数=%d" % shown["n"])
    finally:
        theme.ThemedDialog.exec_choice = orig

    # 重新开始分支
    gid_before = w.model.game_id
    auto_click(app, 0)                      # 重新开始
    w._game_over_notified = False
    w.show_game_over()
    record("v4 游戏结束弹窗：重新开始分支生效",
           w.model.game_id != gid_before, "game_id 变化=%s" % (w.model.game_id != gid_before))

    # ---- 游戏胜利弹窗 ----
    gid_before = w.model.game_id
    auto_click(app, 1)                      # 继续挑战
    w.show_game_won()
    record("v4 胜利弹窗：继续挑战（不重开）", w.model.game_id == gid_before)

    gid_before = w.model.game_id
    auto_click(app, 0)                      # 重新开始
    w.show_game_won()
    record("v4 胜利弹窗：重新开始分支生效", w.model.game_id != gid_before)

    gid_before = w.model.game_id
    auto_escape(app)                        # Escape -> 与原生 No 语义一致（重新开始）
    w.show_game_won()
    record("v4 胜利弹窗：Escape 语义与原生 No 一致", w.model.game_id != gid_before)

    gid_before = w.model.game_id
    auto_enter(app)                         # Enter -> 默认按钮（继续挑战）
    w.show_game_won()
    record("v4 胜利弹窗：Enter 触发默认按钮（继续挑战）", w.model.game_id == gid_before)

    # ---- 外观 / 配色 / 模态 / 无裁切 ----
    dlg = theme.ThemedDialog(w, "游戏结束", "本局已无可行移动。", badge="info",
                             detail_lines=[("最终分数", 1024), ("历史最高分", 4096)],
                             buttons=[("重新开始", "secondary"), ("关闭", "primary")],
                             default_index=1, escape_index=1)
    dlg.show()
    pump(app, 60)
    labels = dlg.findChildren(QLabel)
    clipped = [lb.text() for lb in labels
               if lb.text() and lb.sizeHint().height() > lb.height() + 1]
    record("弹窗外观：宽度 348 且无文字裁切",
           dlg.width() == 348 and not clipped, "clipped=%s" % clipped)
    record("弹窗外观：暖棕配色（主体色存在）",
           theme.PALETTE["body"].lower() in dlg.styleSheet().lower())
    record("弹窗：模态（exec_ 窗口模态）", dlg.isModal())
    dlg.close()

    # ---- 焦点恢复（在真实 Windows 平台下验证，离屏平台无焦点语义） ----
    focus_code = (
        "import os,sys;sys.path.insert(0,%r);"
        "from PyQt5.QtWidgets import QApplication,QWidget,QPushButton;"
        "from PyQt5.QtCore import QTimer;"
        "app=QApplication(sys.argv[:1]);"
        "import ui_theme as t;"
        "holder=QWidget();btn=QPushButton('focus-me',holder);holder.show();btn.setFocus();"
        "app.processEvents();before=app.focusWidget();"
        "QTimer.singleShot(90, lambda: (app.activeModalWidget() and app.activeModalWidget()._choose(0)));"
        "t.ThemedDialog(holder,'提示','焦点恢复测试',buttons=[('确定','primary')]).exec_choice();"
        "app.processEvents();after=app.focusWidget();inwin=holder.focusWidget();"
        "print('FOCUS before_ok',before is not None,'restored',inwin is btn,'app_is_btn',after is btn)"
    ) % ROOT
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)          # 真实平台
    env.pop("QT_SCALE_FACTOR", None)
    out = subprocess.run([sys.executable, "-c", focus_code], capture_output=True,
                         text=True, env=env, timeout=60)
    line = (out.stdout or "").strip()
    record("弹窗关闭后焦点恢复到原控件", "before_ok True restored True" in line,
           line or (out.stderr or "")[-200:])

    # ---- v5 弹窗 ----
    w.close()
    pump(app, 80)
    w5 = build_v5(app)
    w5._sessions = []
    w5._session = None
    shown["n"] = 0
    theme.ThemedDialog.exec_choice = counting
    try:
        auto_click(app, 0)
        w5.on_solver_export()               # 无结果 -> 主题化提示
        record("v5 导出弹窗：无结果时使用主题化弹窗", shown["n"] == 1,
               "弹出次数=%d" % shown["n"])
    finally:
        theme.ThemedDialog.exec_choice = orig

    # 导出成功路径
    sess = {"id": "unittest_session", "strategy_name": "Expectimax", "depth_label": "标准",
            "mode_name": "自动连走", "started_at": "2026-01-01T00:00:00", "elapsed_ms": 10.0,
            "steps": [], "final_score": 0, "final_max_tile": 0, "game_over": False,
            "stopped_reason": "x", "timeout_count": 0}
    w5._sessions = [sess]
    shown["n"] = 0
    theme.ThemedDialog.exec_choice = counting
    try:
        auto_click(app, 0)
        w5.on_solver_export()
        record("v5 导出弹窗：导出成功使用主题化弹窗", shown["n"] == 1)
    finally:
        theme.ThemedDialog.exec_choice = orig

    # 结果对话框主题化
    import v5_pyqt_2048_solver as v5mod
    results_dlg = v5mod.SolverResultsDialog(w5, [sess], compare=True)
    sheet = results_dlg.styleSheet().lower()
    record("v5 结果对话框：使用统一暖棕主题",
           theme.PALETTE["page"].lower() in sheet and theme.PALETTE["border"].lower() in sheet)
    results_dlg.close()
    w5.close()
    pump(app, 80)

    # ---- 高 DPI ----
    code = (
        "import os,sys;"
        "os.environ.setdefault('QT_QPA_PLATFORM','offscreen');"
        "sys.path.insert(0, %r);"
        "from PyQt5.QtWidgets import QApplication,QLabel;"
        "from PyQt5.QtCore import Qt;"
        "QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True);"
        "app=QApplication(sys.argv[:1]);"
        "import ui_theme as t;"
        "d=t.ThemedDialog(None,'游戏结束','本局已无可行移动。测试文字完整性。',"
        "detail_lines=[('最终分数',1024),('历史最高分',4096)],"
        "buttons=[('重新开始','secondary'),('关闭','primary')],default_index=1,escape_index=1);"
        "d.show();app.processEvents();"
        "clipped=[l.text() for l in d.findChildren(QLabel) if l.text() and l.sizeHint().height()>l.height()+1];"
        "print('DPI',d.devicePixelRatioF(),'size',d.width(),d.height(),'clipped',clipped)"
    ) % ROOT
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "1.5"
    env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    line = (out.stdout or "").strip()
    ok = "clipped []" in line
    record("高 DPI(1.5x) 下弹窗文字不被裁切", ok, line or (out.stderr or "")[-200:])

    total = len(RESULTS)
    passed = sum(1 for _i, ok, _d in RESULTS if ok)
    print("\n==== 弹窗测试汇总：%d/%d 通过 ====" % (passed, total))
    for item, ok, detail in RESULTS:
        if not ok:
            print("  - FAIL %s | %s" % (item, detail))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
