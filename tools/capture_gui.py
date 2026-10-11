#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2048 第四版：完整窗口截图工具（含 Windows 原生标题栏与全部文字）。

为什么需要它：
- 旧流程用 `QWidget.grab()` 只能拿到 Qt 客户区，**必然裁掉原生标题栏/边框**；
- 旧流程常在 `QT_QPA_PLATFORM=offscreen` 下跑，离屏字体引擎不提供真实字形
  （每个字符按 1em 方框度量），文字会缺失或变成方块。

本工具的做法：
1. 只在真实 Windows 图形平台启动程序（拒绝 offscreen）；
2. 让窗口成为前台并恢复到正常状态；
3. 用 DWM 扩展外框（DWMWA_EXTENDED_FRAME_BOUNDS）取得“可见窗口外框”；
4. 从**屏幕 DC** 用 BitBlt 抓取该区域（含标题栏、图标、最小化/最大化/关闭按钮）；
5. 用 GetDIBits 取像素构造 QImage 存为无损 PNG；
6. 结构校验（尺寸/非空白/含外框）+ 文字校验（主标题区域是否有真实字形像素）。

用法：
    python tools/capture_gui.py --scene start [--out FILE] [--settle-ms N]
    python tools/capture_gui.py --scene game
    python tools/capture_gui.py --scene hover
    python tools/capture_gui.py --scene merge

成功：stdout 打印 JSON 结果并返回 0；失败：打印 JSON(ok=false) 并返回非 0。
本工具不修改游戏规则/存档：所有历史写入被重定向到临时目录，且从不 close() 主窗口。
"""

import argparse
import ctypes
import json
import os
import sys
import tempfile
import time

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANIM_DIR = os.path.join(PROJ, "v4_pyqt_2048_animated")
SHOTS_DIR = os.path.join(ANIM_DIR, "screenshots")
for _p in (ANIM_DIR, PROJ):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ui_theme                                                    # noqa: E402

# ---------------------------------------------------------------- Win32 ---
from ctypes import wintypes  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
dwmapi = getattr(ctypes.windll, "dwmapi", None)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
DWMWA_EXTENDED_FRAME_BOUNDS = 9
SW_RESTORE = 9
SW_SHOWNORMAL = 1
PW_RENDERFULLCONTENT = 0x00000002


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("rgbBlue", ctypes.c_byte), ("rgbGreen", ctypes.c_byte),
                ("rgbRed", ctypes.c_byte), ("rgbReserved", ctypes.c_byte)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


# ------------------------------------------------------------ 窗口准备 ---
def force_foreground(hwnd):
    """把窗口置前：后台进程直接 SetForegroundWindow 会被系统拒绝，需依附前台线程输入队列"""
    if user32.GetForegroundWindow() == hwnd:
        return True
    fg = user32.GetForegroundWindow()
    t_fg = user32.GetWindowThreadProcessId(fg, None)
    t_me = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(t_me, t_fg, True)
    user32.BringWindowToTop(hwnd)
    ok = bool(user32.SetForegroundWindow(hwnd))
    user32.AttachThreadInput(t_me, t_fg, False)
    return ok or user32.GetForegroundWindow() == hwnd


def prepare_window(hwnd):
    """恢复到正常显示状态，并放到主屏可见位置后置前。

    固定位置可避免窗口落在副屏/负坐标区域导致截到无关桌面或 DPI 换算不一致。
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOWNORMAL)

    rect = RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    w_px, h_px = rect.right - rect.left, rect.bottom - rect.top
    scr_w, scr_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)   # 主屏
    x = max(20, min((scr_w - w_px) // 2, scr_w - w_px - 20)) if w_px < scr_w else 20
    y = 60 if h_px < scr_h - 120 else max(20, (scr_h - h_px) // 2)
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(0), int(x), int(y),
                        w_px, h_px, 0x0040)               # SWP_SHOWWINDOW
    force_foreground(hwnd)
    return True, "restored"


def is_window_on_top(hwnd):
    """窗口中心点是否确实位于本窗口之上（未被其它窗口遮挡）"""
    rect = RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    return int(user32.WindowFromPoint(wintypes.POINT(cx, cy))) == int(hwnd)


def visible_frame_rect(hwnd):
    """可见窗口外框（物理像素）。优先 DWM 扩展外框，失败则退回 GetWindowRect。"""
    rect = RECT()
    if dwmapi is not None:
        try:
            hr = dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd), wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect), ctypes.sizeof(rect))
            if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
                return (rect.left, rect.top, rect.right, rect.bottom), "dwm"
        except OSError:
            pass
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom), "win32"


# ---------------------------------------------------------------- 捕获 ---
def _grab_with(hdc_src, x, y, w, h):
    """从指定 DC 抓取 (x, y, w, h) 区域，返回 QImage"""
    from PyQt5.QtGui import QImage
    hdc_mem = gdi32.CreateCompatibleDC(hdc_src)
    hbm = gdi32.CreateCompatibleBitmap(hdc_src, w, h)
    gdi32.SelectObject(hdc_mem, hbm)
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_src, x, y, SRCCOPY | CAPTUREBLT)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h                 # 负数 = top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0             # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    img = QImage(buf, w, h, w * 4, QImage.Format_RGB32).copy()
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    return img


def capture_frame(hwnd, frame):
    """抓取完整窗口外框；优先屏幕 DC（所见即所得），失败退回 PrintWindow"""
    left, top, right, bottom = frame
    w, h = right - left, bottom - top
    hdc_screen = user32.GetDC(0)
    try:
        img = _grab_with(hdc_screen, left, top, w, h)
    finally:
        user32.ReleaseDC(0, hdc_screen)
    if not img.isNull() and _image_variance(img) > 1.0:
        return img, "screen-bitblt"

    # 备用：PrintWindow(PW_RENDERFULLCONTENT) 直接抓窗口 DC
    hdc_win = user32.GetWindowDC(wintypes.HWND(hwnd))
    try:
        img2 = _grab_with(hdc_win, 0, 0, w, h)
    finally:
        user32.ReleaseDC(wintypes.HWND(hwnd), hdc_win)
    if not img2.isNull():
        return img2, "printwindow"
    return img, "screen-bitblt"


# ---------------------------------------------------------------- 校验 ---
def _image_variance(img, step=4):
    """抽样统计亮度标准差：用于判断是否空白/纯色"""
    import math as _m
    vals = []
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            c = img.pixelColor(x, y)
            vals.append(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return _m.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))


def widget_rect_in_image(widget, frame, dpr):
    """控件矩形 → 捕获图像的像素矩形（逻辑坐标 × dpr 后减去外框原点）"""
    from PyQt5.QtCore import QPoint, QRect
    tl = widget.mapToGlobal(QPoint(0, 0))
    br = widget.mapToGlobal(QPoint(widget.width(), widget.height()))
    x0 = int(round(tl.x() * dpr)) - frame[0]
    y0 = int(round(tl.y() * dpr)) - frame[1]
    x1 = int(round(br.x() * dpr)) - frame[0]
    y1 = int(round(br.y() * dpr)) - frame[1]
    return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def dark_ratio(img, rect, lum_thresh=205):
    """矩形内“暗像素”（文字/线条）占比，用于验证文字真的被绘制出来"""
    n = tot = 0
    for y in range(max(0, rect.top()), min(rect.bottom(), img.height())):
        for x in range(max(0, rect.left()), min(rect.right(), img.width())):
            c = img.pixelColor(x, y)
            tot += 1
            if 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() < lum_thresh:
                n += 1
    return (n / tot) if tot else 0.0


def text_contrast_ratio(img, rect):
    """与控件主色（众数亮度）差异明显的像素占比。

    对“浅底深字”和“深底浅字”都适用，因此按钮文字、深色分数卡上的数字同样可判。
    """
    lum = {}
    rows = []
    for y in range(max(0, rect.top()), min(rect.bottom(), img.height())):
        line = []
        for x in range(max(0, rect.left()), min(rect.right(), img.width())):
            c = img.pixelColor(x, y)
            v = int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
            line.append(v)
            lum[v // 8] = lum.get(v // 8, 0) + 1
        rows.append(line)
    if not rows or not lum:
        return 0.0
    mode_v = max(lum, key=lum.get) * 8 + 4
    n = tot = 0
    for line in rows:
        for v in line:
            tot += 1
            if abs(v - mode_v) > 40:
                n += 1
    return (n / tot) if tot else 0.0


def required_text_widgets(w, scene):
    """该场景下截图中必须能看到文字的控件清单：[(名称, 控件)]"""
    start, game = w.stack.widget(0), w.stack.widget(1)
    items = []

    def add(name, wdg):
        if wdg is not None:
            items.append((name, wdg))

    if scene in ("start", "hover", "recover"):
        add("主标题2048", find_label(start, "2048"))
        add("副标题", find_label(start, "合并数字，拼出 2048"))
        add("卡片标题", w.last_game_caption)
        add("标签-分数", find_label(start, "分数"))
        add("标签-最高分", find_label(start, "最高分"))
        add("数值-分数", w.last_score_value)
        add("数值-最高分", w.last_best_value)
        add("按钮-继续上一局", w.continue_start_button)
        add("按钮-开始新游戏", w.new_game_start_button)
    else:
        add("主标题2048", find_label(game, "2048"))
        add("副标题", find_label(game, "合并数字，拼出 2048"))
        add("分数卡", w.score_label)
        add("最高分卡", w.best_label)
        add("按钮-撤销", w.undo_button)
        add("按钮-重做", w.redo_button)
        add("按钮-新游戏", w.new_game_button)
    return items


def titlebar_icon_score(img, tb_h):
    """标题栏左上角区域里“有彩色”的像素数（软件图标是彩色，标题栏底多为灰/白）"""
    from PyQt5.QtCore import QRect
    r = QRect(4, 2, 40, max(8, tb_h - 6))
    n = 0
    for y in range(r.top(), min(r.bottom(), img.height())):
        for x in range(r.left(), min(r.right(), img.width())):
            c = img.pixelColor(x, y)
            mx, mn = max(c.red(), c.green(), c.blue()), min(c.red(), c.green(), c.blue())
            if mx > 40 and (mx - mn) > 30:          # 明显彩色
                n += 1
    return n


def titlebar_controls_stats(img, tb_h):
    """标题栏右上角（最小化/最大化/关闭）区域的 (字形像素数, 占比)。

    三个控制按钮的字形很细，用“像素数”判定比占比更稳定。
    """
    from PyQt5.QtCore import QRect
    r = QRect(max(0, img.width() - 142), 4, 134, max(8, tb_h - 10))
    rows = []
    lum = {}
    for y in range(r.top(), min(r.bottom(), img.height())):
        line = []
        for x in range(r.left(), min(r.right(), img.width())):
            c = img.pixelColor(x, y)
            v = int(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
            line.append(v)
            lum[v // 8] = lum.get(v // 8, 0) + 1
        rows.append(line)
    if not rows or not lum:
        return 0, 0.0
    mode_v = max(lum, key=lum.get) * 8 + 4
    n = tot = 0
    for line in rows:
        for v in line:
            tot += 1
            if abs(v - mode_v) > 40:
                n += 1
    return n, (n / tot if tot else 0.0)


def find_label(page, text):
    """按文本查找 QLabel：优先返回“可见”的匹配项。

    V5.1 右栏隐藏后，其内部指标标签（如 max_tile 恰好等于 "2048"）与主标题文本相同，
    若不加区分会命中不可见标签导致误判；这里优先可见，其次回退首个匹配。
    """
    from PyQt5.QtWidgets import QLabel
    fallback = None
    for lb in page.findChildren(QLabel):
        if lb.text() == text:
            if lb.isVisible():
                return lb
            if fallback is None:
                fallback = lb
    return fallback


def dialog_text_widgets(dlg):
    """弹窗场景必需文字清单：全部标签 + 全部按钮。"""
    from PyQt5.QtWidgets import QLabel, QPushButton
    items = []
    for lb in dlg.findChildren(QLabel):
        if lb.text():
            items.append(("弹窗文字:%s" % lb.text()[:12], lb))
    for btn in dlg.findChildren(QPushButton):
        if btn.text():
            items.append(("弹窗按钮:%s" % btn.text(), btn))
    return items


# ------------------------------------------------------------ 场景准备 ---
def pump(app, ms):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.004)


def wait_until(app, cond, timeout_ms=2000, step_ms=10):
    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(step_ms / 1000.0)
    return False


def scene_start(w, app, settle_ms):
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 260))
    return "start"


def scene_game(w, app, settle_ms):
    """游戏页：使用内存中的展示盘面（含多位数字），不落盘"""
    w.stack.setCurrentIndex(1)
    demo = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
    w.model.grid = [row[:] for row in demo]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w.refresh()
    pump(app, max(settle_ms, 260))
    return "game"


def scene_hover(w, app, settle_ms):
    """启动页 + 真实鼠标悬停“继续上一局”，保留真实悬停背景与持续粒子"""
    from PyQt5.QtCore import QPoint
    w.stack.setCurrentIndex(0)
    pump(app, 220)
    btn = w.continue_start_button
    if not btn.isEnabled():
        btn.setEnabled(True)                    # 仅用于截图呈现，不改动任何数据
    gp = btn.mapToGlobal(QPoint(int(btn.width() * 0.5), int(btn.height() * 0.5)))
    user32.SetCursorPos(int(gp.x()), int(gp.y()))
    ok = wait_until(app, lambda: len(w.particle_layer.engine.particles) > 0, 1500)
    pump(app, max(settle_ms, 260))
    return "hover" if ok else "hover(no-particles)"


def scene_merge(w, app, settle_ms):
    """合并粒子：用独立测试状态驱动棋盘动画，避免污染对局/存档"""
    w.stack.setCurrentIndex(1)
    bv = w.board_view
    w.model.grid = [[128, 128, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    w.model.score = 0
    bv.render(w.model.grid)
    w.refresh()
    pump(app, 120)

    target = [[256, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    transitions = [((0, 0), (0, 0), 128, True), ((0, 1), (0, 0), 128, True)]
    try:                                        # 避免动画结束后的回调改动棋盘
        bv.animationFinished.disconnect(w._on_animation_finished)
    except TypeError:
        pass
    bv.animate_move(target, transitions, None)
    started = wait_until(app, lambda: bool(bv.anim) and bv.anim.get("phase") == "pop", 1500)
    pump(app, max(settle_ms, 60))
    return "merge" if started else "merge(no-pop)"


def v3_scene_start(w, app, settle_ms):
    """第 3 版启动页（控件命名与第 4 版一致，可复用）"""
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 260))
    return "start"


def v3_scene_game(w, app, settle_ms):
    """第 3 版游戏页：内存展示盘面（该版无 MainWindow.refresh()，直接刷新各控件）"""
    w.stack.setCurrentIndex(1)
    demo = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
    w.model.grid = [row[:] for row in demo]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w._render_score(w.score_label, "分数", w.model.score)
    w._render_score(w.best_label, "最高分", w.model.best_score)
    pump(app, max(settle_ms, 260))
    return "game"


SCENES = {"start": scene_start, "game": scene_game,
          "hover": scene_hover, "merge": scene_merge}


# ---------------------------------------------------------- 第 5 版场景 ---
def _v5_demo_board(w):
    """给第 5 版游戏页铺一个内存展示盘面（含多位数字），不落盘"""
    w.stack.setCurrentIndex(1)
    if hasattr(w, "_grow_for_solver"):
        w._grow_for_solver()
    demo = [[2, 4, 8, 16], [128, 512, 1024, 2048], [0, 32, 64, 256], [0, 0, 0, 0]]
    w.model.grid = [row[:] for row in demo]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w.refresh()


def v5_scene_start(w, app, settle_ms):
    # 启动页与第 4 版同尺寸：强制回 500×672（真实“有存档时启动”的状态）
    w.setFixedSize(500, 672)
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 260))
    return "start"


def v5_scene_game(w, app, settle_ms):
    w.stack.setCurrentIndex(1)
    _v5_demo_board(w)
    pump(app, max(settle_ms, 260))
    return "game"


def v5_scene_solver(w, app, settle_ms):
    """求解面板“运行中”状态：真实填写面板文案与日志（不启动求解线程）"""
    w.stack.setCurrentIndex(1)
    _v5_demo_board(w)
    w.solver_strategy.setCurrentIndex(1)     # Expectimax
    w.solver_depth.setCurrentIndex(1)        # 标准
    w.solver_mode.setCurrentIndex(0)         # 自动连走
    w.solver_log.clear()
    for line in (
        "开始求解：策略=Expectimax，深度=4，模式=自动连走",
        "第 1 步  向左  评估 1523.4  分数 20180  最大瓦片 2048  (36.2ms)",
        "第 2 步  向下  评估 1488.9  分数 20212  最大瓦片 2048  (41.0ms)",
        "第 3 步  向左  评估 1501.2  分数 20244  最大瓦片 2048  (38.7ms)",
    ):
        w._log_step(line)
    w._set_status("状态：<b>运行中</b>　步数 <b>3</b>　当前：<b>向左</b>（评估 1501.2）",
                  "分数 <b>20244</b>　最大瓦片 <b>2048</b>　用时 <b>0.4s</b>")
    w.solver_start_btn.setText("停止")
    if getattr(w, "solver_ai_button", None) is not None:
        w.solver_ai_button.setText("停止")
    w.solver_progress.setRange(0, 0)         # 忙态
    pump(app, max(settle_ms, 260))
    return "solver"


_SUGGEST_DIR_CN = {"up": "向上", "down": "向下", "left": "向左", "right": "向右"}


def _v5_scene_suggest_dir(w, app, settle_ms, direction):
    """求解面板“单步建议（常驻跟随）”状态：按方向在**棋盘原生边框内**高亮建议。"""
    w.stack.setCurrentIndex(1)
    _v5_demo_board(w)
    w.solver_strategy.setCurrentIndex(1)
    w.solver_depth.setCurrentIndex(1)
    w.solver_mode.setCurrentIndex(1)         # 单步建议（常驻跟随）
    w.solver_log.clear()
    cn = _SUGGEST_DIR_CN.get(direction, direction)
    for line in (
        "开始求解：策略=Expectimax，深度=4，模式=单步建议",
        "建议：%s（评估 1523.4，搜索深度 4，用时 39.5ms）" % cn,
    ):
        w._log_step(line)
    w._set_status("建议方向：<b>%s</b>（评估 1523.4）" % cn,
                  "跟随预测：请按方向键走子，走子后会自动重算下一步。")
    if hasattr(w, "_show_hint"):
        w._show_hint(direction)              # 棋盘边框内嵌式局部高亮建议方向
    w.solver_progress.setRange(0, 100)
    w.solver_progress.setValue(0)
    pump(app, max(settle_ms, 260))
    return "suggest_%s" % direction


def v5_scene_suggest(w, app, settle_ms):
    """默认建议方向（向左）——与历史场景名保持兼容。"""
    return _v5_scene_suggest_dir(w, app, settle_ms, "left")


def v5_scene_suggest_up(w, app, settle_ms):
    return _v5_scene_suggest_dir(w, app, settle_ms, "up")


def v5_scene_suggest_down(w, app, settle_ms):
    return _v5_scene_suggest_dir(w, app, settle_ms, "down")


def v5_scene_suggest_left(w, app, settle_ms):
    return _v5_scene_suggest_dir(w, app, settle_ms, "left")


def v5_scene_suggest_right(w, app, settle_ms):
    return _v5_scene_suggest_dir(w, app, settle_ms, "right")


def v5_scene_auto(w, app, settle_ms):
    """自动连走“运行中”：AI 驱动棋盘走子，并**同样**在棋盘原生边框内高亮本步方向。"""
    w.stack.setCurrentIndex(1)
    _v5_demo_board(w)
    w.solver_strategy.setCurrentIndex(1)     # Expectimax
    w.solver_depth.setCurrentIndex(1)        # 标准
    w.solver_mode.setCurrentIndex(0)         # 自动连走
    w.solver_log.clear()
    for line in (
        "开始求解：策略=Expectimax，深度=4，模式=自动连走",
        "第 1 步  向下  评估 1488.9  分数 20212  最大瓦片 2048  (41.0ms)",
        "第 2 步  向左  评估 1501.2  分数 20244  最大瓦片 2048  (38.7ms)",
    ):
        w._log_step(line)
    w._set_status("状态：<b>运行中</b>　步数 <b>2</b>　当前：<b>向左</b>（评估 1501.2）",
                  "分数 <b>20244</b>　最大瓦片 <b>2048</b>　用时 <b>0.4s</b>")
    w.solver_start_btn.setText("停止")
    if getattr(w, "solver_ai_button", None) is not None:
        w.solver_ai_button.setText("停止")
    w.solver_progress.setRange(0, 0)         # 忙态
    if hasattr(w, "_show_hint"):
        w._show_hint("left")                 # 自动连走同样高亮本步方向
    pump(app, max(settle_ms, 260))
    return "auto"


def v5_scene_collapsed(w, app, settle_ms):
    """右栏折叠态：仅保留窄条与“展开”入口，左栏游戏区照常显示（V5.1）。"""
    w.stack.setCurrentIndex(1)
    _v5_demo_board(w)
    if hasattr(w, "_set_solver_collapsed"):
        w._set_solver_collapsed(True)
    pump(app, max(settle_ms, 260))
    return "collapsed"


V5_SCENES = {"start": v5_scene_start, "game": v5_scene_game,
             "solver": v5_scene_solver, "suggest": v5_scene_suggest,
             "suggest_up": v5_scene_suggest_up, "suggest_down": v5_scene_suggest_down,
             "suggest_left": v5_scene_suggest_left, "suggest_right": v5_scene_suggest_right,
             "collapsed": v5_scene_collapsed}


def v5_required_text_widgets(w, scene):
    """第 5 版必需文字：游戏页原有控件 + 求解面板控件"""
    items = list(required_text_widgets(w, "start" if scene in ("start", "recover") else "game"))
    for name, wdg in (
        ("按钮-AI求解", getattr(w, "solver_ai_button", None)),
        ("求解标题", getattr(w, "solver_title", None)),
        ("高级参数", getattr(w, "solver_advanced_toggle", None)),
        ("按钮-开始求解", getattr(w, "solver_start_btn", None)),
        ("按钮-导出结果", getattr(w, "solver_export_btn", None)),
        ("按钮-查看详情", getattr(w, "solver_view_btn", None)),
        ("按钮-性能对比", getattr(w, "solver_compare_btn", None)),
    ):
        if wdg is not None:
            items.append((name, wdg))
    return items


# ------------------------------------------------ 主题化弹窗 / 恢复场景 ---
def _attach_dialog(w, dlg, app, settle_ms):
    """把弹窗设为截图目标（show() 便于自动化，弹窗本身仍带原生标题栏）。"""
    dlg.show()
    pump(app, max(settle_ms, 220))
    w._capture_target = dlg
    w._capture_texts = dialog_text_widgets(dlg)


def v4_scene_gameover(w, app, settle_ms):
    w.stack.setCurrentIndex(1)
    w.model.grid = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w.refresh()
    dlg = ui_theme.ThemedDialog(
        w, "游戏结束", "本局已无可行移动。", badge="info",
        detail_lines=[("最终分数", w.model.score), ("历史最高分", w.model.best_score)],
        buttons=[("重新开始", "secondary"), ("关闭", "primary")],
        default_index=1, escape_index=1)
    _attach_dialog(w, dlg, app, settle_ms)
    return "gameover"


def v4_scene_won(w, app, settle_ms):
    w.stack.setCurrentIndex(1)
    w.model.grid = [[2048, 1024, 512, 256], [128, 64, 32, 16], [8, 4, 2, 0], [0, 0, 0, 0]]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w.refresh()
    dlg = ui_theme.ThemedDialog(
        w, "恭喜胜利", "你已经达到 2048！是否继续挑战更高分数？", badge="success",
        buttons=[("重新开始", "secondary"), ("继续挑战", "primary")],
        default_index=1, escape_index=0)
    _attach_dialog(w, dlg, app, settle_ms)
    return "won"


def _prepare_recover(w):
    w.model.start_new_game()
    w.model.grid = [[2, 4, 8, 16], [32, 64, 128, 256], [512, 1024, 2048, 4096], [0, 0, 0, 0]]
    w.model.score = 12345
    w.model.best_score = 12345
    w.model.save_game_state()
    w.model.update_index()


def v3_scene_recover(w, app, settle_ms):
    _prepare_recover(w)
    w._render_last_game(w.model.get_recent_game_info())
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 320))
    return "recover"


def v4_scene_recover(w, app, settle_ms):
    _prepare_recover(w)
    w._render_last_game(w.model.get_recent_game_info())
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 320))
    return "recover"


def v5_scene_recover(w, app, settle_ms):
    _prepare_recover(w)
    w._render_last_game(w.model.get_recent_game_info())
    w.setFixedSize(500, 672)                 # 启动页与第 4 版同尺寸
    w.stack.setCurrentIndex(0)
    pump(app, max(settle_ms, 320))
    return "recover"


def v5_scene_gameover(w, app, settle_ms):
    w.stack.setCurrentIndex(1)
    w._grow_for_solver()
    w.model.grid = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
    w.model.score = 20148
    w.model.best_score = 20148
    w.board_view.render(w.model.grid)
    w.refresh()
    dlg = ui_theme.ThemedDialog(
        w, "游戏结束", "本局已无可行移动。", badge="info",
        detail_lines=[("最终分数", w.model.score), ("历史最高分", w.model.best_score)],
        buttons=[("重新开始", "secondary"), ("关闭", "primary")],
        default_index=1, escape_index=1)
    _attach_dialog(w, dlg, app, settle_ms)
    return "gameover"


def v5_scene_export(w, app, settle_ms):
    w.stack.setCurrentIndex(1)
    w._grow_for_solver()
    dlg = ui_theme.ThemedDialog(
        w, "导出结果", "已导出以下文件：", badge="success",
        detail_lines=[("JSON", "solver_results/exports/session.json"),
                      ("CSV", "solver_results/exports/session.csv")],
        buttons=[("确定", "primary")])
    _attach_dialog(w, dlg, app, settle_ms)
    return "export"


def v5_scene_results(w, app, settle_ms):
    import importlib
    v5mod = importlib.import_module("v5_pyqt_2048_solver")
    w.stack.setCurrentIndex(1)
    w._grow_for_solver()
    sessions = [
        {"id": "20260101_101010_000001", "strategy": "expectimax",
         "strategy_name": "Expectimax", "depth_label": "标准", "time_limit": 0.3,
         "mode": "auto", "mode_name": "自动连走", "started_at": "2026-01-01T10:10:10",
         "elapsed_ms": 4200.0, "steps": [], "final_score": 5120, "final_max_tile": 512,
         "game_over": True, "stopped_reason": "游戏结束", "timeout_count": 0},
        {"id": "20260101_101500_000002", "strategy": "heuristic",
         "strategy_name": "启发式", "depth_label": "快速", "time_limit": 0.1,
         "mode": "auto", "mode_name": "自动连走", "started_at": "2026-01-01T10:15:00",
         "elapsed_ms": 2100.0, "steps": [], "final_score": 3120, "final_max_tile": 256,
         "game_over": True, "stopped_reason": "游戏结束", "timeout_count": 0},
    ]
    for s in sessions:
        s["steps"] = [{"step": i + 1, "direction": "left", "name": "向左",
                       "eval": 1200.5 - i * 3, "elapsed_ms": 35.0 + i,
                       "depth_reached": 4, "timed_out": False,
                       "score": 1000 + i * 120, "max_tile": 128}
                      for i in range(6)]
    dlg = v5mod.SolverResultsDialog(w, sessions, compare=True)
    dlg.resize(480, 420)
    _attach_dialog(w, dlg, app, settle_ms)
    return "results"


V4_SCENES = dict(SCENES)
V4_SCENES.update({"gameover": v4_scene_gameover, "won": v4_scene_won,
                  "recover": v4_scene_recover})

V3_SCENES = {"start": v3_scene_start, "game": v3_scene_game, "recover": v3_scene_recover}

V5_SCENES_ALL = dict(V5_SCENES)
V5_SCENES_ALL.update({"gameover": v5_scene_gameover, "export": v5_scene_export,
                      "results": v5_scene_results, "recover": v5_scene_recover})
V5_SCENES_ALL.update({"auto": v5_scene_auto})


# 统一入口覆盖的版本：新增 GUI 版本时在此登记（模块目录 / 模块名 / 可用场景 / 出图目录）
VERSIONS = {
    "v6": {
        "label": "第 6 版 · 高性能计算后端",
        "dir": "v6_pyqt_2048_accelerated",
        "module": "v6_pyqt_2048_accelerated",
        "entry": "v6_pyqt_2048_accelerated.py",
        "scenes": V5_SCENES_ALL,
        "texts": v5_required_text_widgets,
        "shots": os.path.join(PROJ, "v6_pyqt_2048_accelerated", "screenshots"),
    },
    "v5": {
        "label": "第 5 版 · 算法求解版",
        "dir": "v5_pyqt_2048_solver",
        "module": "v5_pyqt_2048_solver",
        "entry": "v5_pyqt_2048_solver.py",
        "scenes": V5_SCENES_ALL,
        "texts": v5_required_text_widgets,
        "shots": os.path.join(PROJ, "v5_pyqt_2048_solver", "screenshots"),
    },
    "v4": {
        "label": "第 4 版 · 动画版",
        "dir": "v4_pyqt_2048_animated",
        "module": "v4_pyqt_2048_animated",
        "entry": "v4_pyqt_2048_animated.py",
        "scenes": V4_SCENES,
        "shots": os.path.join(PROJ, "v4_pyqt_2048_animated", "screenshots"),
    },
    "v3": {
        "label": "第 3 版 · MVC 与撤销重做",
        "dir": "v3_pyqt_2048",
        "module": "v3_pyqt_2048_with_history",
        "entry": "v3_pyqt_2048_with_history.py",
        "scenes": V3_SCENES,
        "shots": os.path.join(PROJ, "v3_pyqt_2048", "screenshots"),
    },
}
# 统一命名：每个版本的正式整窗截图一律为 screenshots/full_<scene>.png
SHOT_NAME = "full_%s.png"


# ---------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description="2048 统一完整窗口截图工具（跨版本）")
    ap.add_argument("--version", default="v5", choices=sorted(VERSIONS),
                    help="目标版本：v5=算法求解版，v4=动画版，v3=MVC/撤销重做版")
    ap.add_argument("--scene", required=True,
                    help="场景，可用值随版本而定：v5=start|game|solver|suggest|collapsed|auto|gameover|export|results|recover；"
                         "v4=start|game|hover|merge|gameover|won|recover；v3=start|game|recover")
    ap.add_argument("--out", default=None,
                    help="输出 PNG 路径（默认 <版本>/screenshots/full_<scene>.png）")
    ap.add_argument("--settle-ms", type=int, default=300, help="绘制完成后的稳定等待")
    ap.add_argument("--also-legacy", action="store_true",
                    help="额外用 QWidget.grab() 存一张“仅客户区”对照图（说明旧流程的问题）")
    ap.add_argument("--visual-confirm", action="store_true",
                    help="由人工核对过图像后授予 VISUAL_PASS（否则该项记为 UNVERIFIED）")
    args = ap.parse_args()

    ver = VERSIONS[args.version]
    available = sorted(ver["scenes"])
    result = {"ok": False, "version": args.version, "scene": args.scene}
    if args.scene not in ver["scenes"]:
        result["error"] = ("版本 %s 不支持场景 %s，可用：%s"
                           % (args.version, args.scene, available))
        print(json.dumps(result, ensure_ascii=False))
        return 2

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])

    if app.platformName() != "windows":
        result["error"] = ("必须在真实 Windows 图形平台运行，当前 platform=%s"
                           % app.platformName())
        print(json.dumps(result, ensure_ascii=False))
        return 3

    sys.path.insert(0, os.path.join(PROJ, ver["dir"]))
    import importlib
    mod = importlib.import_module(ver["module"])

    icon_builder = getattr(mod, "build_app_icon", None)
    if callable(icon_builder):
        app.setWindowIcon(icon_builder())
    font = QFont("Microsoft YaHei", 10)
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"])
    app.setFont(font)

    w = mod.MainWindow()
    # 先读取真实最近对局（只读），随后把所有历史写入重定向到临时目录，避免污染用户存档
    get_info = getattr(w.model, "get_recent_game_info", None)
    recent = get_info() if callable(get_info) else None
    w.model.history_dir = os.path.join(tempfile.gettempdir(), "2048_capture_history")
    os.makedirs(w.model.history_dir, exist_ok=True)

    w.resize(500, 672)
    w.show()
    w.raise_()
    pump(app, 420)

    hwnd = int(w.winId())
    original_cursor = (user32.GetSystemMetrics(0) // 2, user32.GetSystemMetrics(1) // 2)
    try:
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        original_cursor = (pt.x, pt.y)
    except Exception:
        pass
    prepare_window(hwnd)
    pump(app, 220)

    try:
        scene_note = ver["scenes"][args.scene](w, app, args.settle_ms)
        pump(app, 120)
        # 弹窗场景：场景函数会把要截图的弹窗挂到 w._capture_target
        target = getattr(w, "_capture_target", None) or w
        if target is not w:
            hwnd = int(target.winId())
            prepare_window(hwnd)
            pump(app, 220)
        if not is_window_on_top(hwnd):           # 被遮挡则再置前一次
            force_foreground(hwnd)
            pump(app, 160)
        frame, frame_src = visible_frame_rect(hwnd)
        img, grab_src = capture_frame(hwnd, frame)

        if img.isNull():
            result["error"] = "捕获失败：QImage 为空"
            print(json.dumps(result, ensure_ascii=False))
            return 4

        dpr = target.devicePixelRatioF()
        client_h = int(round(target.height() * dpr))
        frame_h = frame[3] - frame[1]
        variance = _image_variance(img)

        dialog_texts = getattr(w, "_capture_texts", None)
        is_dialog = dialog_texts is not None

        # 主标题文字校验（真实字形而非空白）
        title_ratio = 0.0
        if is_dialog and dialog_texts:
            anchor = dialog_texts[0][1]
            if anchor.isVisible():
                r = widget_rect_in_image(anchor, frame, dpr)
                title_ratio = dark_ratio(img, r)
        else:
            page_index = 0 if args.scene in ("start", "hover", "recover") else 1
            page = w.stack.widget(page_index)
            title = find_label(page, "2048")
            if title is not None:
                r = widget_rect_in_image(title, frame, dpr)
                title_ratio = dark_ratio(img, r)

        # 全部必需文字元素的对比度校验（不同版本/弹窗可自带文字清单）
        texts = {}
        if is_dialog:
            items = dialog_texts
            min_texts = 3
        else:
            text_fn = ver.get("texts") or required_text_widgets
            items = text_fn(w, args.scene)
            min_texts = 7
        for name, wdg in items:
            if not wdg.isVisible():
                continue
            r = widget_rect_in_image(wdg, frame, dpr)
            texts[name] = round(text_contrast_ratio(img, r), 4)
        texts_ok = (len(texts) >= min_texts) and all(v > 0.01 for v in texts.values())

        particles = 0
        if getattr(w, "particle_layer", None) is not None:
            particles = len(w.particle_layer.engine.particles)
        tb_h = max(8, frame_h - client_h)
        icon_score = titlebar_icon_score(img, tb_h)
        controls_px, controls_ratio = titlebar_controls_stats(img, tb_h)

        checks = {
            "platform": app.platformName(),
            "version_label": ver["label"],
            "grab": grab_src,
            "frame_from": frame_src,
            "frame_xywh": list(frame),
            "size": [img.width(), img.height()],
            "dpr": round(dpr, 3),
            "client_height_px": client_h,
            "frame_height_px": frame_h,
            "titlebar_height_px": tb_h,
            "has_titlebar": frame_h > client_h + 6,      # 外框必须比客户区高（含标题栏）
            "titlebar_icon_pixels": icon_score,
            "titlebar_icon_visible": icon_score > 20,
            "titlebar_controls_pixels": controls_px,
            "titlebar_controls_ratio": round(controls_ratio, 4),
            "titlebar_controls_visible": controls_px > 15,
            "window_on_top": is_window_on_top(hwnd),
            "variance": round(variance, 2),
            "not_blank": variance > 3.0,
            "title_dark_ratio": round(title_ratio, 4),
            "text_rendered": title_ratio > 0.03,
            "texts": texts,
            "texts_ok": texts_ok,
            "particles_at_capture": particles,
            "recent_game": recent,
        }
        result.update(checks)

        out = args.out or os.path.join(ver["shots"], SHOT_NAME % args.scene)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        saved = img.save(out, "PNG")
        if not saved:
            result["error"] = "PNG 保存失败：%s" % out
            print(json.dumps(result, ensure_ascii=False))
            return 5
        result["path"] = out
        result["scene_note"] = scene_note
        if args.also_legacy:                        # 对照：旧流程只有客户区，必然没有标题栏
            legacy = out[:-4] + "_clientarea.png"
            w.grab().save(legacy, "PNG")
            result["legacy_clientarea"] = {
                "path": legacy,
                "size": [w.width(), w.height()],
                "has_titlebar": False,
                "note": "QWidget.grab() 仅客户区，无原生标题栏（仅可用于组件级调试）",
            }

        # ---- 项目级截图验收门禁（见 docs/GUI_SCREENSHOT_STANDARD.md）----
        structure_pass = bool(checks["has_titlebar"] and checks["not_blank"]
                              and checks["window_on_top"]
                              and checks["titlebar_icon_visible"]
                              and checks["titlebar_controls_visible"])
        text_pass = bool(checks["text_rendered"] and checks["texts_ok"])
        visual_pass = True if args.visual_confirm else "UNVERIFIED"
        gates = {
            "CAPTURE_PASS": bool(saved),
            "STRUCTURE_PASS": structure_pass,
            "TEXT_PASS": text_pass,
            "VISUAL_PASS": visual_pass,
            "GUI_SCREENSHOT_PASS": bool(saved and structure_pass and text_pass
                                        and visual_pass is True),
        }
        result["gates"] = gates
        if not args.visual_confirm:
            result["visual_hint"] = ("VISUAL_PASS 需人工核对图像后加 --visual-confirm 授予；"
                                     "未验证不得标记 PASS")
        result["ok"] = bool(saved and structure_pass and text_pass)
        print(json.dumps(result, ensure_ascii=False))
        rc = 0 if result["ok"] else 6
    except Exception as exc:                        # noqa: BLE001
        import traceback
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        result["traceback"] = traceback.format_exc()
        print(json.dumps(result, ensure_ascii=False))
        rc = 7
    finally:
        try:                                        # 还原真实光标位置
            user32.SetCursorPos(int(original_cursor[0]), int(original_cursor[1]))
        except Exception:
            pass
        w.hide()                                    # 不调用 close()：避免写入存档
        app.quit()
    return rc


if __name__ == "__main__":
    sys.exit(main())
