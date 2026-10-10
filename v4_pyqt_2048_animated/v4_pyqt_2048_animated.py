#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 图形界面版 2048：平滑移动 / 合并动画与性能优化

配套博客《第 4 篇：PyQt5 2048 动画与性能优化》。

分层：
    Model       -> 复用第 3 篇的 GameCore（棋盘 / 合并 / 存档 / 撤销重做一行未改），
                   仅由 AnimatedGameCore 子类补充"每块从哪来、到哪去"的过渡信息；
    View        -> BoardView 用 QPainter 自绘：静态背景层（缓存为 QPixmap）
                   + 动画层（QTimer 逐帧插值）；
    Controller  -> MainWindow 处理键盘/按钮，触发动画，并在动画结束后再做胜负提示。
"""

import sys
import os
import math
import random

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton,
                             QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QFrame, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QTimer, QRectF, QRect, QPoint, QPointF, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap, QPen, QIcon, QCursor, QFontMetrics

# =====================================================================
# 复用第 3 篇的 Model（GameCore）：动画版不改动任何棋盘逻辑
# =====================================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_V3_DIR = os.path.join(os.path.dirname(_HERE), "v3_pyqt_2048")
for _p in (_ROOT, _V3_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from v3_pyqt_2048_with_history import GameCore, DIRECTION_NAMES  # noqa: E402
import safe_store as _store                                      # noqa: E402
import ui_theme as _theme                                        # noqa: E402


# =====================================================================
# 视觉规范常量（与第 3 篇保持一致，两个版本看起来是同一个游戏）
# =====================================================================
COLOR_BG = "#faf8ef"
COLOR_TEXT = "#776e65"
COLOR_SUBTITLE = "#8f8175"
COLOR_BOARD = "#bbada0"
COLOR_EMPTY = "#cdc1b4"
COLOR_CARD_LABEL = "#f5efe6"
COLOR_CARD_VALUE = "#ffffff"

TILE_SIZE = 96
TILE_GAP = 10
BOARD_PADDING = 10
TILE_RADIUS = 6
BOARD_RADIUS = 9
BOARD_SIDE = BOARD_PADDING * 2 + TILE_SIZE * 4 + TILE_GAP * 3   # 434

WINDOW_WIDTH, WINDOW_HEIGHT = 500, 672
GAME_MARGIN_X = (WINDOW_WIDTH - BOARD_SIDE) // 2
BUTTON_WIDTH, BUTTON_HEIGHT = 100, 44

# 动画时长（秒）：滑行 / 合并与新生放大
MOVE_DURATION = 0.12
POP_DURATION = 0.14
FRAME_INTERVAL = 16          # 定时器步长（ms），约 60 FPS

TEXT_DARK = "#776e65"
TEXT_LIGHT = "#f9f6f2"
TILE_COLORS = {
    2: (238, 228, 218), 4: (237, 224, 200),
    8: (242, 177, 121), 16: (245, 149, 99),
    32: (246, 124, 95), 64: (246, 94, 59),
    128: (237, 207, 114), 256: (237, 204, 97),
    512: (237, 200, 80), 1024: (237, 197, 63),
    2048: (237, 194, 46),
}
HIGH_COLORS = {4096: (237, 176, 32), 8192: (227, 159, 22), 16384: (214, 143, 15)}

# 按钮样式：主按钮 / 次按钮 / 文字按钮（与第 3 篇一致）
PRIMARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #8f7a66; color: #f9f6f2;
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #9f8b78; }}
QPushButton:pressed  {{ background-color: #7c6a58; }}
QPushButton:focus    {{ border-color: #f9f6f2; }}
QPushButton:disabled {{ background-color: #cdc2b6; color: #f2ece5; }}
"""

SECONDARY_BUTTON_QSS = f"""
QPushButton {{
    background-color: #eee4da; color: {COLOR_TEXT};
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #e2d7ca; }}
QPushButton:pressed  {{ background-color: #d5c9ba; }}
QPushButton:focus    {{ border-color: #8f7a66; }}
QPushButton:disabled {{ background-color: #e8e0d7; color: #a99a8d; border-color: #ddd1c4; }}
"""

TEXT_BUTTON_QSS = f"""
QPushButton {{
    background-color: transparent; color: {COLOR_TEXT};
    border: 2px solid transparent; border-radius: {TILE_RADIUS}px;
    font-size: 14px; font-weight: bold;
}}
QPushButton:hover    {{ background-color: #efe7db; color: #6a5b4e; }}
QPushButton:pressed  {{ background-color: #e4dacd; color: #5e5245; }}
QPushButton:focus    {{ background-color: #efe7db; border-color: #8f7a66; }}
QPushButton:disabled {{ color: #c3b8ad; }}
"""

# ---------------------------------------------------------------------
# 启动页视觉规范（本次仅作用于启动页，游戏页样式保持不变）
# ---------------------------------------------------------------------
SP_BG = "#FAF8EF"                 # 页面背景
SP_TITLE = "#776E65"              # 主标题
SP_TEXT = "#776E65"               # 主要文字
SP_SUBTEXT = "#938579"            # 次要文字
SP_PRIMARY = "#8F7A66"            # 主按钮
SP_PRIMARY_HOVER = "#9F8B78"
SP_PRIMARY_PRESS = "#786554"
SP_SECONDARY_BG = "#F5EFE6"       # 次按钮
SP_SECONDARY_BORDER = "#B7A595"
SP_CARD_BG = "#F2E9DD"            # 信息卡
SP_LINE = "#D8C9B9"               # 装饰线条

SP_CARD_W, SP_CARD_H = 334, 126
SP_BTN_W, SP_BTN_H = 328, 48
SP_BTN_RADIUS = 10
SP_CARD_RADIUS = 13

# 上一局信息卡内部规格（尺寸/配色/圆角/阴影均由上面的常量与 QSS 保持不变）
SP_CARD_PAD_X = 20                 # 卡片左右内边距（20～24）
SP_CARD_VALUE_SIZE = 28            # 分数数字字号（27～28）
SP_CARD_VALUE_MIN_SIZE = 18        # 长数字受控缩放的兜底最小字号
SP_CARD_CAPTION_SIZE = 12          # “分数 / 最高分”标签字号
SP_CARD_TITLE_SIZE = 12            # 卡片标题字号（12～13）
SP_CARD_TITLE_COLOR = "#837468"    # 卡片标题颜色
SP_CARD_LABEL_COLOR = "#8F8175"    # 分数 / 最高分标签颜色
SP_CARD_DIVIDER_W = 1              # 中央分隔线宽度
SP_CARD_DIVIDER_H = 44             # 中央分隔线高度（42～46）
# 单列可用宽度：由卡片宽度、边框、左右内边距与中央分隔线推导（布局改动时同步更新）
SP_CARD_COLUMN_W = (SP_CARD_W - 2 - 2 * SP_CARD_PAD_X - SP_CARD_DIVIDER_W) // 2

# 软件品牌标识：仅用于窗口标题栏 / 任务栏图标（矢量绘制，无外部资源）
# 2×2 小方块，四格数字连读即 “2048”：(字符, 底色, 字色)
BRAND_TILES = (
    ("2", (238, 228, 218), (119, 110, 101)),
    ("0", (242, 177, 121), (255, 255, 255)),
    ("4", (245, 149,  99), (255, 255, 255)),
    ("8", (237, 194,  46), (255, 255, 255)),
)

# 背景装饰方块：(数值, 中心x比例, 中心y比例, 边长, 旋转角, 透明度)
SP_DECOR_TILES = (
    (2,  0.10, 0.10, 74, -12, 34),
    (16, 0.89, 0.15, 84,  10, 30),
    (4,  0.06, 0.50, 62,   8, 28),
    (8,  0.93, 0.46, 72, -10, 30),
    (16, 0.13, 0.89, 80,  12, 26),
    (2,  0.86, 0.87, 66,  -8, 30),
    (8,  0.50, 0.04, 54,   6, 24),
)

SP_PRIMARY_QSS = f"""
QPushButton {{
    background-color: {SP_PRIMARY}; color: #FFFFFF;
    border: 1px solid {SP_PRIMARY}; border-radius: {SP_BTN_RADIUS}px;
    font-size: 14px; font-weight: 600;
}}
QPushButton:hover    {{ background-color: {SP_PRIMARY_HOVER}; border-color: {SP_PRIMARY_HOVER}; }}
QPushButton:pressed  {{ background-color: {SP_PRIMARY_PRESS}; border-color: {SP_PRIMARY_PRESS}; }}
QPushButton:focus    {{ border-color: #E8DFD3; }}
QPushButton:disabled {{ background-color: #D8CBBB; color: #F1EAE0; border-color: #D8CBBB; }}
"""

SP_SECONDARY_QSS = f"""
QPushButton {{
    background-color: {SP_SECONDARY_BG}; color: {SP_TEXT};
    border: 1px solid {SP_SECONDARY_BORDER}; border-radius: {SP_BTN_RADIUS}px;
    font-size: 14px; font-weight: 600;
}}
QPushButton:hover    {{ background-color: #EFE7DC; }}
QPushButton:pressed  {{ background-color: #E4D9C9; border-color: #A89787; }}
QPushButton:focus    {{ border-color: {SP_PRIMARY}; background-color: #EFE7DC; }}
QPushButton:disabled {{ background-color: #F0EBE3; color: #B7A595; border-color: #D8C9B9; }}
"""

START_PAGE = 0
GAME_PAGE = 1


# =====================================================================
# 缓动函数：让插值不机械
# =====================================================================
def ease_out_cubic(t):
    """减速滑行：起步快、收尾稳"""
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.70158):
    """带轻微回弹的放大：用于合并 / 新生方块的出现"""
    t -= 1.0
    return 1 + (s + 1) * t ** 3 + s * t * t


# =====================================================================
# Model 层：在第 3 篇 GameCore 上补充“过渡信息”（从哪来、到哪去）
# =====================================================================
class AnimatedGameCore(GameCore):
    """
    与第 3 篇完全相同的合并规则、存档与撤销/重做；
    额外记录一次移动中每个方块的“起点 -> 终点”，供 View 播放动画。
    """

    def __init__(self, grid_size=4):
        super().__init__(grid_size)
        # 第 4 篇使用自己的存档目录，避免与第 3 篇的对局混在一起；
        # 同时把存档版本标记为 v4 并重新绑定单实例锁（跨版本隔离）。
        self.set_history_dir(
            _store.resolve_history_dir(os.path.join(_HERE, "game_history"), "v4"), "v4")

        self.last_transitions = []   # [(src(r,c), dst(r,c), 滑动时显示的数值, 是否合并)]
        self.last_spawn = None       # 本次随机新方块的坐标

    # ---- 撤销/重做条目序列化：额外保存过渡动画信息，恢复后撤销/重做动画一致 ----
    def _serialize_undo_entry(self, entry):
        spawn = entry.get("spawn")
        return {
            "snapshot": entry["snapshot"],
            "transitions": [[list(src), list(dst), int(value), bool(merged)]
                            for (src, dst, value, merged) in entry.get("transitions", [])],
            "spawn": list(spawn) if spawn else None,
        }

    def _deserialize_undo_entry(self, data):
        spawn = data.get("spawn")
        return {
            "snapshot": data["snapshot"],
            "transitions": [((int(t[0][0]), int(t[0][1])),
                             (int(t[1][0]), int(t[1][1])), int(t[2]), bool(t[3]))
                            for t in data.get("transitions", [])],
            "spawn": (int(spawn[0]), int(spawn[1])) if spawn else None,
        }

    # ---- 记录新生方块位置 ----
    def add_new_tile(self):
        empty = [(i, j) for i in range(self.grid_size)
                 for j in range(self.grid_size) if self.grid[i][j] == 0]
        if not empty:
            self.last_spawn = None
            return False
        i, j = random.choice(empty)
        self.grid[i][j] = 2 if random.random() < 0.9 else 4
        self.last_spawn = (i, j)
        return True

    # ---- 逐行合并，同时输出每一块的去向 ----
    def _merge_line_tracked(self, line):
        """
        返回 (新行, ops)。
        ops: [(源下标, 目标下标, 该块当前显示的数值, 是否合并)]
        合并时两块携带各自的原值一起滑向同一格，落定后再显示合并结果。
        """
        size = len(line)
        items = [(v, p) for p, v in enumerate(line) if v != 0]   # (数值, 源下标)

        result = []            # (最终值, [源下标...], 是否合并, 滑动时显示的数值)
        i = 0
        while i < len(items):
            if i + 1 < len(items) and items[i][0] == items[i + 1][0]:
                v = items[i][0]
                self.score += v * 2
                result.append((v * 2, [items[i][1], items[i + 1][1]], True, v))
                i += 2
            else:
                result.append((items[i][0], [items[i][1]], False, items[i][0]))
                i += 1

        new_line = [r[0] for r in result] + [0] * (size - len(result))
        ops = []
        for dst_p, (_final, srcs, merged, tile_v) in enumerate(result):
            for sp in srcs:
                ops.append((sp, dst_p, tile_v, merged))
        return new_line, ops

    # ---- 覆盖 _slide：复用方向抽象，但额外记录过渡 ----
    def _slide(self, direction):
        size = self.grid_size
        self.last_transitions = []
        moved = False

        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]

        for i in range(size):
            original = self.grid[i]
            row = original[::-1] if direction in ('right', 'down') else original
            new_row, ops = self._merge_line_tracked(row)
            if direction in ('right', 'down'):
                new_row = new_row[::-1]
            if new_row != original:          # 与原行（而非翻转后的行）比较
                moved = True
            self.grid[i] = new_row

            for src_p, dst_p, value, merged in ops:
                # 行内下标 -> 棋盘坐标（注意翻转与转置）
                if direction in ('right', 'down'):
                    src_p, dst_p = size - 1 - src_p, size - 1 - dst_p
                if direction in ('up', 'down'):
                    src, dst = (src_p, i), (dst_p, i)
                else:
                    src, dst = (i, src_p), (i, dst_p)
                self.last_transitions.append((src, dst, value, merged))

        if direction in ('up', 'down'):
            self.grid = [list(row) for row in zip(*self.grid)]
        return moved

    # ---- 覆盖一个完整回合：把本步的过渡信息一并压栈，供撤回/重做播放 ----
    def apply_move(self, direction):
        snapshot = self._snapshot()
        if not self._slide(direction):
            return False                     # 非法移动，不产生快照

        transitions = list(self.last_transitions)

        self.redo_stack.clear()
        self._sync_best_score()
        self.record_move(DIRECTION_NAMES[direction])
        self.add_new_tile()
        spawn = self.last_spawn
        self.record_move("添加新方块")

        # 栈里存“状态 + 本步过渡”：撤回时反向播、重做时正向播
        self.undo_stack.append({"snapshot": snapshot,
                                "transitions": transitions, "spawn": spawn})

        self.check_win()
        self.check_game_over()
        return True

    def undo(self):
        """回退一步；返回本次要播放的过渡信息（没有可撤销时返回 None）"""
        if not self.undo_stack:
            return None
        entry = self.undo_stack.pop()
        self.redo_stack.append({"snapshot": self._snapshot(),
                                "transitions": entry["transitions"],
                                "spawn": entry["spawn"]})
        self._restore(entry["snapshot"])
        self._sync_best_score()
        self.save_game_state()
        self.update_index()
        return {"kind": "undo", "transitions": entry["transitions"],
                "spawn": entry["spawn"]}

    def redo(self):
        """重做被撤回的一步；返回本次要播放的过渡信息（没有可重做时返回 None）"""
        if not self.redo_stack:
            return None
        entry = self.redo_stack.pop()
        self.undo_stack.append({"snapshot": self._snapshot(),
                                "transitions": entry["transitions"],
                                "spawn": entry["spawn"]})
        self._restore(entry["snapshot"])
        self._sync_best_score()
        self.save_game_state()
        self.update_index()
        return {"kind": "redo", "transitions": entry["transitions"],
                "spawn": entry["spawn"]}


# =====================================================================
# 轻量粒子与交互反馈系统（装饰性，与游戏动画完全独立）
# =====================================================================
# 参数集中配置：主碎片 / 辅助高光的数量、速度、寿命(秒)、尺寸、重力、阻尼
PARTICLE_MAX = 240                 # 同屏粒子上限（主碎片 + 高光 合计）
PARTICLE_CULL_MARGIN = 80          # 左右/下方飞出可视区多少像素后剔除
PARTICLE_CULL_MARGIN_TOP = 180     # 上方留更大余量：上抛的粒子可能回落，避免误剔
PARTICLE_DAMPING_REF_DT = FRAME_INTERVAL / 1000.0   # 阻尼基准步长：60 FPS 下与旧的“每帧乘数”完全等价
PARTICLE_PRESETS = {
    "click_tile":  {"main": 16, "accent": 10, "speed": (60, 190),  "life": (0.30, 0.60),
                    "size_main": (5, 9), "size_accent": (2, 4),
                    "gravity": 820.0, "damping": 0.970},
    "click_empty": {"main": 8,  "accent": 16, "speed": (50, 150),  "life": (0.28, 0.55),
                    "size_main": (5, 9), "size_accent": (2, 4),
                    "gravity": 760.0, "damping": 0.970},
    "merge":       {"main": 20, "accent": 10, "speed": (80, 260),  "life": (0.35, 0.75),
                    "size_main": (5, 9), "size_accent": (2, 4),
                    "gravity": 980.0, "damping": 0.960, "up_bias": -60.0},
    "celebrate":   {"main": 36, "accent": 22, "speed": (130, 340), "life": (0.50, 0.90),
                    "size_main": (5, 9), "size_accent": (2, 4),
                    "gravity": 900.0, "damping": 0.965, "up_bias": -120.0},
    "button":      {"main": 4,  "accent": 8,  "speed": (40, 120),  "life": (0.25, 0.45),
                    "size_main": (5, 9), "size_accent": (2, 4),
                    "gravity": 700.0, "damping": 0.970},
    # 启动页悬停（持续发射，此处为“每批”数量）：暖金碎片 + 米白高光，每批 6 颗
    # 指数阻尼 k=2.2s⁻¹、弱重力 → 快速扩散后平缓漂浮，扩散范围明显（约 90～130px）
    "hover_continue":  {"main": 3, "accent": 3, "speed": (180, 300), "life": (0.50, 0.75),
                        "size_main": (5, 7), "size_accent": (3, 4),
                        "gravity": 60.0, "damping_k": 2.2, "up_bias": -24.0},
    # 启动页悬停（持续发射）：浅暖棕碎片 + 米白高光，每批 5 颗；阻尼略强、更柔和（约 70～95px）
    # 浅色碎片加细暖棕描边提升与米色背景的对比
    "hover_new_game":  {"main": 2, "accent": 3, "speed": (165, 255), "life": (0.40, 0.60),
                        "size_main": (3, 5), "size_accent": (2, 4),
                        "gravity": 40.0, "damping_k": 2.4, "up_bias": -18.0,
                        "outline_shards": True},
}

# 启动页两个按钮的持续悬停配置：(主色, 高光, 辅助色) —— 主碎片在主色/辅助色间交替
HOVER_CONTINUE_COLORS = ("#E8C570", "#FFF4D6", "#C49B65")   # 暖金 + 米白 + 浅焦糖
HOVER_NEW_GAME_COLORS = ("#B8A392", "#FFF8EE", "#E8D8C6")   # 浅暖棕 + 米白 + 米色
HOVER_CONTINUE_INTERVAL = 120      # 持续发射间隔（ms），落在 100～140
HOVER_NEW_GAME_INTERVAL = 180      # 持续发射间隔（ms），落在 160～200
# 混合发射位置：一部分粒子在鼠标附近（带抖动），其余在按钮安全区内随机
HOVER_SPAWN_AREA_RATIO = 0.4       # 40% 从按钮内部随机位置生成，60% 在鼠标附近
HOVER_SPAWN_JITTER = 10.0          # 鼠标附近生成时的位置扰动半径（px）
HOVER_AREA_PAD_X = 0.18            # 安全区左右内边距比例（相对按钮宽度）
HOVER_AREA_PAD_Y = 0.30            # 安全区上下内边距比例（相对按钮高度）

# 合并粒子：三类区域混合采样（几何按目标方块实际绘制矩形推导，无写死像素）
MERGE_CONTACT_RATIO = 0.40          # 合并接触区域（来源方块所在一侧）
MERGE_INTERIOR_RATIO = 0.40         # 目标方块内部随机
MERGE_EDGE_RATIO = 0.20             # 目标方块四周边缘窄带（避开四角）
MERGE_ZONE_INSET = 0.10             # 采样区域避开最外侧 10% 边距
MERGE_CONTACT_SPREAD = math.radians(80.0)   # 接触区域沿合并方向扩散的半角
MERGE_EDGE_SPREAD = math.radians(45.0)      # 边缘区域向外扩散的半角
# 接触侧 → 合并方向角（屏幕坐标 y 向下）：来源在右 ⇒ 方块向左移动
_SIDE_MERGE_ANGLE = {"right": math.pi, "left": 0.0,
                     "bottom": -math.pi / 2.0, "top": math.pi / 2.0}

# 粒子配色映射：main = 主碎片（沿用数字方块自身背景色），accent = 辅助高光（同色系提亮）
PARTICLE_COLORS = {
    2:    {"main": (238, 228, 218), "accent": (250, 244, 238)},
    4:    {"main": (237, 224, 200), "accent": (249, 240, 224)},
    8:    {"main": (242, 177, 121), "accent": (251, 214, 178)},
    16:   {"main": (245, 149,  99), "accent": (252, 196, 163)},
    32:   {"main": (246, 124,  95), "accent": (252, 180, 162)},
    64:   {"main": (246,  94,  59), "accent": (252, 166, 146)},
    128:  {"main": (237, 207, 114), "accent": (249, 231, 177)},
    256:  {"main": (237, 204,  97), "accent": (249, 229, 167)},
    512:  {"main": (237, 200,  80), "accent": (249, 226, 156)},
    1024: {"main": (237, 197,  63), "accent": (249, 224, 144)},
    2048: {"main": (237, 194,  46), "accent": (250, 222, 132)},
    4096: {"main": (237, 176,  32), "accent": (249, 211, 114)},
    8192: {"main": (227, 159,  22), "accent": (245, 198,  96)},
}
PARTICLE_COLOR_FALLBACK = {"main": (198, 128, 12), "accent": (245, 198, 96)}   # 16384 及以上回退

COLOR_EMPTY_MAIN = (233, 196, 106)         # 点击空格：米金主碎片
COLOR_EMPTY_ACCENT = (250, 236, 200)       # 点击空格：高光
COLOR_CELEBRATE_MAIN = (242, 193, 78)      # 首次达成 2048：金色主碎片
COLOR_CELEBRATE_ACCENT = (255, 240, 200)   # 首次达成 2048：高光
PARTICLE_HIGHLIGHT_OUTLINE = (74, 50, 30)   # 高光的细暖棕描边（浅色方块/浅米底上仍清晰，对比≥3:1）


def particle_colors_for(value):
    """按数字取 (主碎片, 高光) 两组配色；超出映射范围时使用回退配色"""
    entry = PARTICLE_COLORS.get(value, PARTICLE_COLOR_FALLBACK)
    return entry["main"], entry["accent"]


class Particle:
    """一颗粒子（用 __slots__ 降低内存与属性访问开销）"""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "shape",
                 "r", "g", "b", "angle", "spin", "gravity", "damping_k", "outlined")

    def __init__(self, x, y, vx, vy, life, size, shape, rgb, angle, spin,
                 gravity, damping_k, outlined):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.size, self.shape = size, shape
        self.r, self.g, self.b = rgb
        self.angle, self.spin = angle, spin
        self.gravity, self.damping_k = gravity, damping_k   # k 单位 s⁻¹：v(t)=v0·exp(-k·t)
        self.outlined = outlined          # 细暖棕描边（高光小圆点 / 浅色碎片）


class ParticlePreset:
    """把集中配置解析成可直接使用的参数对象"""

    def __init__(self, name):
        cfg = PARTICLE_PRESETS[name]
        self.name = name
        self.main = cfg["main"]            # 主碎片数量
        self.accent = cfg["accent"]        # 辅助高光数量
        self.speed = cfg["speed"]
        self.life = cfg["life"]
        self.size_main = cfg["size_main"]
        self.size_accent = cfg["size_accent"]
        self.gravity = cfg["gravity"]
        if "damping_k" in cfg:
            # 新写法：直接给每秒阻尼系数 k（s⁻¹）
            self.damping_k = float(cfg["damping_k"])
        else:
            # 兼容旧写法“每帧乘数”：换算为等效的每秒阻尼系数（60FPS 下完全等价）
            self.damping_k = -math.log(cfg["damping"]) / PARTICLE_DAMPING_REF_DT
        self.outline_shards = bool(cfg.get("outline_shards", False))
        self.up_bias = cfg.get("up_bias", 0.0)


_PRESET_CACHE = {}


def get_preset(name):
    if name not in _PRESET_CACHE:
        _PRESET_CACHE[name] = ParticlePreset(name)
    return _PRESET_CACHE[name]


def _as_rgb(color):
    if isinstance(color, QColor):
        return (color.red(), color.green(), color.blue())
    return tuple(color)


class ParticleEngine:
    """粒子的生命周期与绘制；不依赖任何游戏状态，可被棋盘与按钮共用"""

    def __init__(self, max_particles=PARTICLE_MAX):
        self.max_particles = max_particles
        self.particles = []
        self._bounds = None            # (w, h)：可视区尺寸，用于屏幕外剔除

    def is_active(self):
        return bool(self.particles)

    def is_saturated(self):
        """是否已达同屏上限：达到后新的悬停批次不再发射，优先保留既有粒子"""
        return len(self.particles) >= self.max_particles

    def clear(self):
        self.particles = []

    def set_bounds(self, width, height):
        """设置可视区尺寸（覆盖层大小），供屏幕外剔除使用"""
        self._bounds = (float(width), float(height))

    def bounding_rect(self, margin=0):
        """所有粒子的包围盒；用于只重绘“脏区”而不是整层"""
        if not self.particles:
            return QRect()
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for p in self.particles:
            r = p.size / 2.0
            if p.x - r < min_x: min_x = p.x - r
            if p.x + r > max_x: max_x = p.x + r
            if p.y - r < min_y: min_y = p.y - r
            if p.y + r > max_y: max_y = p.y + r
        return QRect(int(min_x) - margin, int(min_y) - margin,
                     int(max_x - min_x) + 2 * margin + 1,
                     int(max_y - min_y) + 2 * margin + 1)

    def emit(self, preset_name, x, y, main_rgb, accent_rgb,
             area=None, area_ratio=0.0, jitter=0.0):
        """喷出“主碎片 + 辅助高光”两层粒子；颜色可为 QColor 或 (r, g, b)。

        发射位置采用混合策略：
        - 默认在鼠标点 (x, y) 附近，并附加 jitter 抖动避免同点堆叠；
        - 当给出 area（覆盖层坐标矩形）且 area_ratio>0 时，按该比例把一部分粒子
          改放到 area 内的随机位置，使粒子覆盖整个按钮而非只围着鼠标。
        """
        preset = get_preset(preset_name)
        main_rgb = _as_rgb(main_rgb)
        accent_rgb = _as_rgb(accent_rgb)
        for _ in range(preset.main):
            ox, oy = self._pick_origin(x, y, area, area_ratio, jitter)
            self._spawn(ox, oy, preset, main_rgb, preset.size_main, "shard",
                        preset.outline_shards)
        for _ in range(preset.accent):
            ox, oy = self._pick_origin(x, y, area, area_ratio, jitter)
            self._spawn(ox, oy, preset, accent_rgb, preset.size_accent, "dot", True)
        overflow = len(self.particles) - self.max_particles
        if overflow > 0:                       # 上限保护：丢弃最旧的
            del self.particles[:overflow]

    @staticmethod
    def _pick_origin(x, y, area, area_ratio, jitter):
        """决定一颗粒子的出生点（覆盖层坐标）"""
        if area is not None and area_ratio > 0.0 and random.random() < area_ratio:
            return (random.uniform(area.left(), area.right()),
                    random.uniform(area.top(), area.bottom()))
        if jitter > 0.0:
            return (x + random.uniform(-jitter, jitter),
                    y + random.uniform(-jitter, jitter))
        return (x, y)

    # ---- 区域混合发射（合并粒子：不做中心点爆发） ----
    def emit_zones(self, preset_name, zones, main_rgb, accent_rgb):
        """按区域比例混合发射：每个区域给出候选矩形、占比与方向策略。

        zones: [{"rects": [QRectF, ...], "ratio": float,
                 "angle": float|None, "spread": float, "outward": QPointF|None}]
        主碎片与高光共用同一套区域采样，二者都不会固定生成在中心。
        """
        preset = get_preset(preset_name)
        main_rgb = _as_rgb(main_rgb)
        accent_rgb = _as_rgb(accent_rgb)
        for _ in range(preset.main):
            self._spawn_in_zones(preset, zones, main_rgb, preset.size_main,
                                 "shard", preset.outline_shards)
        for _ in range(preset.accent):
            self._spawn_in_zones(preset, zones, accent_rgb, preset.size_accent,
                                 "dot", True)
        overflow = len(self.particles) - self.max_particles
        if overflow > 0:                       # 上限保护：丢弃最旧的
            del self.particles[:overflow]

    @staticmethod
    def _pick_zone(zones):
        """按 ratio 加权随机选择一个区域"""
        total = sum(z.get("ratio", 0.0) for z in zones)
        if total <= 0.0:
            return zones[0]
        r = random.random() * total
        acc = 0.0
        for z in zones:
            acc += z.get("ratio", 0.0)
            if r <= acc:
                return z
        return zones[-1]

    def _spawn_in_zones(self, preset, zones, rgb, size_range, shape, outlined):
        zone = self._pick_zone(zones)
        rects = zone.get("rects") or []
        rect = random.choice(rects)
        x = random.uniform(rect.left(), rect.right())
        y = random.uniform(rect.top(), rect.bottom())

        spread = float(zone.get("spread", 0.0))
        outward = zone.get("outward")
        if outward is not None:                      # 边缘：由方块中心指向出生点向外
            base = math.atan2(y - outward.y(), x - outward.x())
        elif zone.get("angle") is not None:          # 接触区：沿合并方向（含垂直向）
            base = float(zone["angle"])
        else:                                        # 内部随机：全向
            base = random.uniform(0.0, 2.0 * math.pi)
            spread = 0.0
        angle = base + random.uniform(-spread, spread)

        speed = random.uniform(*preset.speed)
        self.particles.append(Particle(
            x, y,
            math.cos(angle) * speed,
            math.sin(angle) * speed + preset.up_bias,
            random.uniform(*preset.life), random.uniform(*size_range),
            shape, rgb,
            random.uniform(0.0, 2.0 * math.pi), random.uniform(-8.0, 8.0),
            preset.gravity, preset.damping_k, outlined))

    def _spawn(self, x, y, preset, rgb, size_range, shape, outlined):
        angle = random.uniform(0.0, 2.0 * math.pi)
        speed = random.uniform(*preset.speed)
        self.particles.append(Particle(
            x, y,
            math.cos(angle) * speed,
            math.sin(angle) * speed + preset.up_bias,
            random.uniform(*preset.life), random.uniform(*size_range),
            shape, rgb,
            random.uniform(0.0, 2.0 * math.pi), random.uniform(-8.0, 8.0),
            preset.gravity, preset.damping_k, outlined))

    def step(self, dt):
        """原地推进（不新建列表），并剔除已飞出可视区、不会再回来的粒子。

        阻尼为指数形式 v(t) = v0·exp(-k·t)，按“真实经过时间 dt（秒）”计算，
        与帧率无关；旧预设的“每帧乘数”已在 ParticlePreset 中换算为等效 k，
        因此其它预设的运动语义保持不变。
        """
        parts = self.particles
        bounds = self._bounds
        step_dt = dt if dt > 0.0 else 0.0
        write = 0
        for read in range(len(parts)):
            p = parts[read]
            p.life -= dt
            if p.life <= 0.0:
                continue
            decay = math.exp(-p.damping_k * step_dt)   # 指数阻尼
            p.vy += p.gravity * dt
            p.vx *= decay
            p.vy *= decay
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            if bounds is not None:
                w, h = bounds
                if (p.x < -PARTICLE_CULL_MARGIN or p.x > w + PARTICLE_CULL_MARGIN
                        or p.y > h + PARTICLE_CULL_MARGIN
                        or p.y < -PARTICLE_CULL_MARGIN_TOP):
                    continue                       # 已离开可视区且不会再回来
            parts[write] = p
            write += 1
        if write != len(parts):
            del parts[write:]

    def draw(self, painter):
        if not self.particles:
            return
        # 复用同一组 QColor / QPen 实例，避免每帧为每颗粒子新建对象
        color = QColor()
        pen = QPen()
        pen.setWidthF(1.0)
        outline = PARTICLE_HIGHLIGHT_OUTLINE
        for p in self.particles:
            remain = max(0.0, min(1.0, p.life / p.max_life))   # 1 -> 0
            alpha = min(1.0, remain * 1.25)                    # 增强初始不透明度，随后自然淡出
            size = p.size * (0.4 + 0.6 * remain)
            color.setRgb(p.r, p.g, p.b, int(255 * alpha))
            painter.setBrush(color)
            if p.shape == "shard":                             # 主碎片：圆角方片
                if p.outlined:                                 # 浅色碎片：细暖棕描边提对比
                    color.setRgb(outline[0], outline[1], outline[2], int(200 * alpha))
                    pen.setColor(color)
                    painter.setPen(pen)
                else:
                    painter.setPen(Qt.NoPen)
                painter.save()
                painter.translate(p.x, p.y)
                painter.rotate(math.degrees(p.angle))
                painter.drawRoundedRect(QRectF(-size / 2.0, -size / 2.0, size, size), 1.5, 1.5)
                painter.restore()
            else:                                              # 辅助高光：小圆点 + 细暖棕描边
                if p.outlined:
                    color.setRgb(outline[0], outline[1], outline[2], int(245 * alpha))
                    pen.setColor(color)
                    painter.setPen(pen)
                else:
                    painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRectF(p.x - size / 2.0, p.y - size / 2.0, size, size))


class ParticleOverlay(QWidget):
    """覆盖整窗、鼠标穿透的透明绘制层：只负责推进并绘制粒子"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)   # 鼠标穿透到下方控件
        self.setFocusPolicy(Qt.NoFocus)
        self.engine = ParticleEngine()
        self._last_rect = QRect()          # 上一帧的脏区，用于清除残影
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_INTERVAL)
        self._timer.timeout.connect(self._tick)

    # ---- 供棋盘 / 按钮上报事件：把控件局部坐标换算到本层坐标 ----
    def emit_from(self, widget, x, y, main_rgb, accent_rgb, preset_name,
                  area_rect=None, area_ratio=0.0, jitter=0.0):
        # 覆盖层与棋盘/按钮是同窗内的“兄弟分支”，mapTo 只接受祖先，
        # 因此统一走“全局坐标”中转（对嵌套层级、高 DPI 都安全）。
        gp = self.mapFromGlobal(widget.mapToGlobal(QPoint(int(round(x)), int(round(y)))))
        # 按钮内部的安全区矩形同样经全局坐标换算到覆盖层坐标，避免坐标错位
        area = None
        if area_rect is not None and area_ratio > 0.0:
            # QRectF.topLeft() 返回 QPointF，需转成 QPoint 才能喂给 mapToGlobal
            tl = self.mapFromGlobal(widget.mapToGlobal(area_rect.topLeft().toPoint()))
            br = self.mapFromGlobal(widget.mapToGlobal(area_rect.bottomRight().toPoint()))
            area = QRectF(tl, br).normalized()
        self.engine.emit(preset_name, gp.x(), gp.y(), main_rgb, accent_rgb,
                         area=area, area_ratio=area_ratio, jitter=jitter)
        if not self._timer.isActive():
            self._timer.start()

    # ---- 供棋盘上报：区域混合发射（把控件局部矩形换算到本层坐标） ----
    def _widget_pt_to_layer(self, widget, pt):
        gp = widget.mapToGlobal(QPoint(int(round(pt.x())), int(round(pt.y()))))
        return QPointF(self.mapFromGlobal(gp))

    def _widget_rect_to_layer(self, widget, rect):
        tl = self._widget_pt_to_layer(widget, rect.topLeft())
        br = self._widget_pt_to_layer(widget, rect.bottomRight())
        return QRectF(tl, br).normalized()

    def emit_zones_from(self, widget, zones, main_rgb, accent_rgb, preset_name):
        """区域混合发射：zones 中的矩形以 widget 局部坐标给出，逐一到本层坐标"""
        conv = []
        for z in zones:
            outward = z.get("outward")
            conv.append({
                "rects": [self._widget_rect_to_layer(widget, r) for r in z.get("rects", [])],
                "ratio": float(z.get("ratio", 0.0)),
                "angle": z.get("angle"),
                "spread": float(z.get("spread", 0.0)),
                "outward": (self._widget_pt_to_layer(widget, outward)
                            if outward is not None else None),
            })
        self.engine.emit_zones(preset_name, conv, main_rgb, accent_rgb)
        if not self._timer.isActive():
            self._timer.start()

    def is_active(self):
        return self.engine.is_active()

    def is_saturated(self):
        return self.engine.is_saturated()

    def clear(self):
        self.engine.clear()
        self._timer.stop()
        self._last_rect = QRect()
        self.update()

    def shutdown(self):
        self._timer.stop()
        self.engine.clear()

    def _tick(self):
        if not self.engine.is_active():
            self._timer.stop()
            if not self._last_rect.isNull():          # 清掉最后一帧的残留
                self.update(self._last_rect)
                self._last_rect = QRect()
            return
        self.engine.set_bounds(self.width(), self.height())
        self.engine.step(self._timer.interval() / 1000.0)
        rect = self.engine.bounding_rect(margin=4)
        if not self._last_rect.isNull():
            rect = rect.united(self._last_rect)       # 连上一帧位置一起重绘，避免残影
        self.update(rect)                             # 只重绘“脏区”，不再整层重绘
        if self.engine.is_active():
            self._last_rect = self.engine.bounding_rect(margin=4)
        else:
            self._last_rect = QRect()
            self._timer.stop()                     # 粒子全部消亡后停表

    def paintEvent(self, event):
        if not self.engine.is_active():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.engine.draw(painter)
        painter.end()


# =====================================================================
# View 层：静态背景层（缓存）+ 动画层（逐帧插值）
# =====================================================================
class BoardView(QWidget):
    """自绘棋盘：背景只画一次缓存成 pixmap，方块每帧按进度重画"""

    animationFinished = pyqtSignal()

    def __init__(self, grid_size=4, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.setFixedSize(BOARD_SIDE, BOARD_SIDE)
        self.grid = [[0] * grid_size for _ in range(grid_size)]
        self.anim = None
        self._background = self._build_background()

        self.timer = QTimer(self)
        self.timer.setInterval(FRAME_INTERVAL)
        self.timer.timeout.connect(self._tick)

        self._particle_layer = None      # 由 MainWindow 注入的窗口级粒子绘制层

    # ---------------- 几何 ----------------
    def _cell_xy(self, r, c):
        return (BOARD_PADDING + c * (TILE_SIZE + TILE_GAP),
                BOARD_PADDING + r * (TILE_SIZE + TILE_GAP))

    def _cell_rect(self, r, c):
        x, y = self._cell_xy(r, c)
        return QRectF(x, y, TILE_SIZE, TILE_SIZE)

    # ---------------- 静态背景层：只构建一次 ----------------
    def _build_background(self):
        pm = QPixmap(BOARD_SIDE, BOARD_SIDE)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLOR_BOARD))
        p.drawRoundedRect(QRectF(0, 0, BOARD_SIDE, BOARD_SIDE), BOARD_RADIUS, BOARD_RADIUS)
        p.setBrush(QColor(COLOR_EMPTY))
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                p.drawRoundedRect(self._cell_rect(i, j), TILE_RADIUS, TILE_RADIUS)
        p.end()
        return pm

    # ---------------- 对外接口 ----------------
    def is_animating(self):
        return self.anim is not None

    def render(self, grid):
        """静止渲染（新游戏 / 继续 / 撤销重做）"""
        self.timer.stop()
        self.anim = None
        self.grid = [row[:] for row in grid]
        self.update()

    def animate_move(self, final_grid, transitions, spawn):
        """播放一次移动：先滑行，再合并/新生放大"""
        moving = []
        pop_cells = {}          # 目标格 -> 来源方块所在侧集合（用于合并粒子的接触区）
        for src, dst, value, merged in transitions:
            sx, sy = self._cell_xy(*src)
            tx, ty = self._cell_xy(*dst)
            moving.append((value, sx, sy, tx, ty))
            if merged:
                sides = pop_cells.setdefault(dst, set())
                dr, dc = dst[0] - src[0], dst[1] - src[1]
                if dr > 0:
                    sides.add("top")       # 来源在上方 ⇒ 向下合并
                elif dr < 0:
                    sides.add("bottom")
                if dc > 0:
                    sides.add("left")
                elif dc < 0:
                    sides.add("right")

        self.anim = {
            "mode": "forward",
            "phase": "move",
            "t": 0.0,
            "moving": moving,
            "pop": pop_cells,
            "spawn": spawn,
            "spawn_value": final_grid[spawn[0]][spawn[1]] if spawn else None,
            "target": [row[:] for row in final_grid],
        }
        self.timer.start()
        self.update()

    def animate_undo(self, target_grid, transitions, spawn):
        """回退动画：方块从落点滑回起点，新生方块同时缩小消失"""
        spawn_value = None
        if spawn is not None:
            spawn_value = self.grid[spawn[0]][spawn[1]]   # 回退前盘面上的新生方块值
        moving = []
        for src, dst, value, merged in transitions:
            sx, sy = self._cell_xy(*src)
            tx, ty = self._cell_xy(*dst)
            moving.append((value, sx, sy, tx, ty))

        self.anim = {
            "mode": "reverse",
            "phase": "move",
            "t": 0.0,
            "moving": moving,
            "pop": {},
            "spawn": spawn,
            "spawn_value": spawn_value,
            "target": [row[:] for row in target_grid],
        }
        self.timer.start()
        self.update()

    # ---------------- 交互反馈：点击粒子 / 合并碎片 ----------------
    def bind_particle_layer(self, layer):
        """注入窗口级粒子绘制层（可为 None）"""
        self._particle_layer = layer

    def _emit_particles(self, x, y, main_rgb, accent_rgb, preset_name):
        if self._particle_layer is not None:
            self._particle_layer.emit_from(self, x, y, main_rgb, accent_rgb, preset_name)

    def _cell_hit(self, x, y):
        """把控件坐标映射到格子；落在间隙或边框时返回 None"""
        step = TILE_SIZE + TILE_GAP
        col = int((x - BOARD_PADDING) // step)
        row = int((y - BOARD_PADDING) // step)
        if not (0 <= row < self.grid_size and 0 <= col < self.grid_size):
            return None
        if (x - BOARD_PADDING) % step >= TILE_SIZE:   # 横向落在格间缝隙
            return None
        if (y - BOARD_PADDING) % step >= TILE_SIZE:   # 纵向落在格间缝隙
            return None
        return (row, col, self.grid[row][col])

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        hit = self._cell_hit(event.x(), event.y())
        if hit is None:                               # 间隙 / 边框：不触发
            event.accept()
            return
        row, col, value = hit
        if value:                                     # 数字方块：主碎片用该方块自身配色
            main, accent = particle_colors_for(value)
            self._emit_particles(event.x(), event.y(), main, accent, "click_tile")
        else:                                         # 空格：米金主碎片 + 高光
            self._emit_particles(event.x(), event.y(),
                                 COLOR_EMPTY_MAIN, COLOR_EMPTY_ACCENT, "click_empty")
        event.accept()

    def _merge_zones(self, row, col, sides):
        """按合并目标格的“实际绘制矩形”推导三类采样区域（均为控件局部坐标）。

        三类区域：
        1. 接触区（40%）：来源方块所在的一侧半幅，方向沿合并方向；
        2. 内部区（40%）：方块内部随机（避开最外侧 10% 边距），方向随机；
        3. 边缘区（20%）：四周内缩窄带（去掉四角），方向由中心向外。
        来源方向未知时（如来源与目标同格）接触区退化为方块内部随机采样。
        """
        tile = self._cell_rect(row, col)
        inset = TILE_SIZE * MERGE_ZONE_INSET
        inner = tile.adjusted(inset, inset, -inset, -inset)
        hw, hh = inner.width() / 2.0, inner.height() / 2.0

        if sides:
            contact_rects = []
            for side in sides:
                if side == "left":
                    contact_rects.append(QRectF(inner.x(), inner.y(), hw, inner.height()))
                elif side == "right":
                    contact_rects.append(QRectF(inner.x() + hw, inner.y(), hw, inner.height()))
                elif side == "top":
                    contact_rects.append(QRectF(inner.x(), inner.y(), inner.width(), hh))
                elif side == "bottom":
                    contact_rects.append(QRectF(inner.x(), inner.y() + hh, inner.width(), hh))
        else:
            contact_rects = [inner]              # 回退：方向未知 ⇒ 方块内部随机

        # 接触区方向：单一来源侧时沿合并方向；两侧或未知时改为随机方向
        if len(sides) == 1:
            dir_angle = _SIDE_MERGE_ANGLE.get(next(iter(sides)))
        else:
            dir_angle = None

        # 边缘区：四周窄带，去掉四角（沿边只取中间 50%）
        band = inset
        edge_rects = [
            QRectF(inner.x() + inner.width() * 0.25, tile.y(),
                   inner.width() * 0.5, band),                                  # 上
            QRectF(inner.x() + inner.width() * 0.25, inner.bottom(),
                   inner.width() * 0.5, band),                                  # 下
            QRectF(tile.x(), inner.y() + inner.height() * 0.25,
                   band, inner.height() * 0.5),                                 # 左
            QRectF(inner.right(), inner.y() + inner.height() * 0.25,
                   band, inner.height() * 0.5),                                 # 右
        ]

        return [
            {"rects": contact_rects, "ratio": MERGE_CONTACT_RATIO,
             "angle": dir_angle, "spread": MERGE_CONTACT_SPREAD},
            {"rects": [inner], "ratio": MERGE_INTERIOR_RATIO,
             "angle": None, "spread": 0.0},
            {"rects": edge_rects, "ratio": MERGE_EDGE_RATIO,
             "angle": None, "spread": MERGE_EDGE_SPREAD,
             "outward": QPointF(tile.center())},
        ]

    def _emit_merge_fragments(self):
        """一步中的多组合并，各自在目标格释放一次碎片（pop 以目标格为键，天然去重）"""
        if self._particle_layer is None or not self.anim or not self.anim["pop"]:
            return
        target = self.anim["target"]
        for (row, col), sides in self.anim["pop"].items():
            value = target[row][col]
            if not value:
                continue
            main, accent = particle_colors_for(value)
            zones = self._merge_zones(row, col, sides)
            self._particle_layer.emit_zones_from(self, zones, main, accent, "merge")

    # ---------------- 逐帧推进 ----------------
    def _tick(self):
        if self.anim is None:
            self.timer.stop()
            return
        self.anim["t"] += self.timer.interval() / 1000.0

        if self.anim["phase"] == "move":
            if self.anim["t"] >= MOVE_DURATION:
                if self.anim["mode"] == "reverse":
                    self._finish_animation()      # 回退只有“滑回”一个阶段
                    return
                self.anim["phase"] = "pop"
                self.anim["t"] = 0.0
                self._emit_merge_fragments()      # 合并落定：与弹性动画同步释放碎片
        else:
            if self.anim["t"] >= POP_DURATION:
                self._finish_animation()
                return
        self.update()

    def _finish_animation(self):
        """动画结束：落定到目标盘面并通知 Controller"""
        self.grid = self.anim["target"]
        self.anim = None
        self.timer.stop()
        self.update()
        self.animationFinished.emit()

    # ---------------- 绘制 ----------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.drawPixmap(0, 0, self._background)      # 静态背景层

        if self.anim is None:
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    v = self.grid[r][c]
                    if v:
                        x, y = self._cell_xy(r, c)
                        self._draw_tile(p, v, x, y, 1.0)

        elif self.anim["phase"] == "move":
            prog = ease_out_cubic(min(1.0, self.anim["t"] / MOVE_DURATION))
            if self.anim["mode"] == "reverse":
                for value, sx, sy, tx, ty in self.anim["moving"]:
                    x = tx + (sx - tx) * prog      # 从落点滑回起点
                    y = ty + (sy - ty) * prog
                    self._draw_tile(p, value, x, y, 1.0)
                spawn = self.anim["spawn"]
                if spawn is not None and self.anim["spawn_value"] is not None:
                    x, y = self._cell_xy(*spawn)
                    self._draw_tile(p, self.anim["spawn_value"], x, y,
                                    max(0.01, 1.0 - prog))   # 新生方块缩小消失
            else:
                for value, sx, sy, tx, ty in self.anim["moving"]:
                    x = sx + (tx - sx) * prog
                    y = sy + (ty - sy) * prog
                    self._draw_tile(p, value, x, y, 1.0)

        else:   # pop：落定后，合并处回弹放大、新生方块放大出现
            prog = min(1.0, self.anim["t"] / POP_DURATION)
            pop_cells = self.anim["pop"]
            spawn = self.anim["spawn"]
            for r in range(self.grid_size):
                for c in range(self.grid_size):
                    v = self.anim["target"][r][c]
                    if not v:
                        continue
                    scale = 1.0
                    if (r, c) in pop_cells:
                        scale = 1.0 + 0.16 * math.sin(math.pi * prog)
                    elif spawn is not None and (r, c) == spawn:
                        scale = ease_out_back(prog)
                    x, y = self._cell_xy(r, c)
                    self._draw_tile(p, v, x, y, scale)
        p.end()

    def _draw_tile(self, p, value, x, y, scale):
        """画一个圆角方块 + 居中数字；scale 控制放大（以其中心为准）"""
        size = TILE_SIZE * scale
        cx, cy = x + TILE_SIZE / 2.0, y + TILE_SIZE / 2.0
        rect = QRectF(cx - size / 2.0, cy - size / 2.0, size, size)

        p.setPen(Qt.NoPen)
        p.setBrush(self._tile_color(value))
        p.drawRoundedRect(rect, TILE_RADIUS * scale, TILE_RADIUS * scale)

        p.setPen(QColor(TEXT_DARK if value <= 4 else TEXT_LIGHT))
        font = QFont(self.font())
        if value < 100:
            base = 36
        elif value < 1000:
            base = 30
        elif value < 10000:
            base = 24
        else:
            base = 17
        font.setPixelSize(max(1, int(base * scale)))
        font.setBold(True)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, str(value))

    @staticmethod
    def _tile_color(value):
        if value <= 2048:
            return QColor(*TILE_COLORS.get(value, (60, 58, 50)))
        return QColor(*HIGH_COLORS.get(value, (198, 128, 12)))


class PressFeedbackButton(QPushButton):
    """按钮交互反馈基类：

    - 按下时上报按压点（供粒子系统在按钮上撒少量粒子；禁用时不触发）
    - 可选开启悬停反馈：进入后立即发射一批，并按固定时间间隔持续发射，
      发射位置跟随鼠标当前位置；离开 / 隐藏 / 禁用 / 销毁时立即停止发射，
      已有粒子仍由粒子层自然淡出（不在这里清空）。
    持续发射用一个挂在按钮上的 QTimer 驱动（QTimer 按真实经过时间触发，
    不是帧计数），并且整只按钮始终只维护这一个定时器，反复进出不会叠加。
    """

    pressedAt = pyqtSignal(int, int)
    hoverPulse = pyqtSignal(int, int)     # 悬停期间按间隔上报一次发射点（按钮局部坐标）

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._hover_enabled = False       # 是否启用悬停持续发射
        self._hover_interval = 120        # 发射间隔（ms）
        self._hover_active = False        # 当前是否处于悬停
        self._hover_timer = None          # 懒创建；父对象为按钮，随按钮一起销毁

    # ---- 配置 ----
    def set_hover_particles(self, enabled=True, interval_ms=120):
        self._hover_enabled = bool(enabled)
        self._hover_interval = max(30, int(interval_ms))
        if self._hover_timer is not None:
            self._hover_timer.setInterval(self._hover_interval)

    # ---- 发射调度（单一循环） ----
    def _hover_emit(self):
        # 任何时刻只要不再满足“启用 + 可用 + 可见 + 仍在悬停”，立即停表
        if not (self._hover_enabled and self._hover_active
                and self.isEnabled() and self.isVisible()):
            self.stop_hover_emission()
            return
        local = self.mapFromGlobal(QCursor.pos())   # 跟随鼠标当前位置
        self.hoverPulse.emit(local.x(), local.y())

    def _start_hover_emission(self):
        if self._hover_timer is None:
            self._hover_timer = QTimer(self)        # 父对象=按钮 → 按钮销毁即回收
            self._hover_timer.timeout.connect(self._hover_emit)
        self._hover_timer.setInterval(self._hover_interval)
        if not self._hover_timer.isActive():
            self._hover_timer.start()
        self._hover_emit()                          # 进入瞬间先来一批

    def stop_hover_emission(self):
        """停止持续发射并清除悬停状态（不清空已存在的粒子）"""
        self._hover_active = False
        if self._hover_timer is not None and self._hover_timer.isActive():
            self._hover_timer.stop()

    # ---- 事件 ----
    def enterEvent(self, event):
        super().enterEvent(event)
        if self._hover_enabled and self.isEnabled() and self.isVisible() and not self._hover_active:
            self._hover_active = True
            self._start_hover_emission()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.stop_hover_emission()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.stop_hover_emission()                 # 页面切换 / 隐藏时立即停表

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange and not self.isEnabled():
            self.stop_hover_emission()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.pressedAt.emit(event.x(), event.y())
        super().mousePressEvent(event)


class EnterButton(PressFeedbackButton):
    """可聚焦按钮；额外支持回车键触发（QPushButton 原生只响应空格）"""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class ArrowButton(EnterButton):
    """启动页按钮：在右侧自绘一枚简洁箭头。

    箭头画在按钮自身 paintEvent 里，不进入任何布局 —— 文本仍由 QSS 居中，
    因此不会造成内部布局偏移，也不影响按压点（粒子）坐标。
    """

    def __init__(self, text, arrow_color="#FFFFFF", arrow_disabled="#F1EAE0", parent=None):
        super().__init__(text, parent)
        self._arrow_color = QColor(arrow_color)
        self._arrow_disabled = QColor(arrow_disabled)

    def paintEvent(self, event):
        super().paintEvent(event)
        color = self._arrow_color if self.isEnabled() else self._arrow_disabled
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(color, 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        ax = self.width() - 22.0
        ay = self.height() / 2.0
        painter.drawLine(QPointF(ax - 7.0, ay), QPointF(ax + 1.0, ay))       # 箭杆
        painter.drawLine(QPointF(ax - 3.0, ay - 4.5), QPointF(ax + 1.5, ay))  # 上翼
        painter.drawLine(QPointF(ax - 3.0, ay + 4.5), QPointF(ax + 1.5, ay))  # 下翼
        painter.end()


# ---------------------------------------------------------------------
# 软件图标：仅用于窗口标题栏 / 任务栏，矢量绘制、不引入外部资源
# ---------------------------------------------------------------------
def paint_brand_mark(painter, cx, cy, side):
    """在中心 (cx, cy)、整体边长 side 处绘制 2×2 小方块，四格连读即 “2048”"""
    gap = max(1.0, side * 0.09)
    tile = (side - gap) / 2.0
    radius = tile * 0.22
    font = QFont()
    font.setBold(True)
    font.setPixelSize(max(6, int(tile * 0.74)))
    painter.setFont(font)
    for idx, (text, bg, fg) in enumerate(BRAND_TILES):
        row, col = divmod(idx, 2)
        rect = QRectF(cx - side / 2.0 + col * (tile + gap),
                      cy - side / 2.0 + row * (tile + gap), tile, tile)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*bg))
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(QColor(*fg))
        painter.drawText(rect, Qt.AlignCenter, text)


def build_app_icon():
    """用矢量绘制生成窗口 / 任务栏图标：多尺寸渲染，高 DPI 下边缘清晰"""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(SP_BG))                    # 暖米色圆角底板
        radius = size * 0.22
        painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
        paint_brand_mark(painter, size / 2.0, size / 2.0, size * 0.74)
        painter.end()
        icon.addPixmap(pm)
    return icon


class StartDecorPage(QWidget):
    """启动页容器：用 QPainter 在页面边缘绘制低对比度 2048 装饰方块。

    - 静态绘制、不启动任何定时器；按窗口尺寸缓存成 QPixmap，仅在尺寸变化时重建
    - 位于所有子控件之下，不接收鼠标事件，页面中央信息区保持干净
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)   # 整页自绘，避免重复重绘父级
        self._cache = None
        self._cache_size = None

    @staticmethod
    def _draw_decor_tile(painter, value, cx, cy, side, angle, alpha):
        r, g, b = TILE_COLORS.get(value, (205, 193, 180))
        radius = side * 0.14
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(angle)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(r, g, b, alpha))
        painter.drawRoundedRect(QRectF(-side / 2.0, -side / 2.0, side, side), radius, radius)
        painter.setPen(QColor(119, 110, 101, min(255, alpha + 20)))   # 淡淡的数字
        font = QFont()
        font.setPixelSize(max(10, int(side * 0.34)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(-side / 2.0, -side / 2.0, side, side), Qt.AlignCenter, str(value))
        painter.restore()

    def _build_cache(self):
        pm = QPixmap(max(1, self.width()), max(1, self.height()))
        pm.fill(QColor(SP_BG))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = pm.width(), pm.height()
        for value, rx, ry, side, angle, alpha in SP_DECOR_TILES:
            self._draw_decor_tile(painter, value, rx * w, ry * h, side, angle, alpha)
        painter.end()
        return pm

    def paintEvent(self, event):
        if self._cache is None or self._cache_size != self.size():
            self._cache = self._build_cache()
            self._cache_size = self.size()
        QPainter(self).drawPixmap(0, 0, self._cache)


# =====================================================================
# Controller 层：事件分发 + 驱动动画 + 状态同步
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = AnimatedGameCore(4)
        self.win_announced = False
        self._game_over_notified = False      # 同一局“游戏结束”提示只弹一次
        self._hover_shard_toggle = 0          # 悬停主碎片在主色/辅助色间交替
        self.init_ui()
        self.startup()

    # ---------------- 界面搭建 ----------------
    def init_ui(self):
        self.setWindowTitle("2048")
        self.setWindowIcon(build_app_icon())          # 标题栏 / 任务栏图标（矢量生成）
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(f"QMainWindow {{ background-color: {COLOR_BG}; }}")

        self.stack = QStackedWidget()
        self.stack.setFocusPolicy(Qt.NoFocus)
        self.stack.addWidget(self._build_start_page())   # START_PAGE
        self.stack.addWidget(self._build_game_page())    # GAME_PAGE
        self.setCentralWidget(self.stack)

        # 窗口级粒子绘制层：覆盖全窗、鼠标穿透，只负责推进与绘制粒子
        self.particle_layer = ParticleOverlay(self)
        self.particle_layer.setGeometry(self.rect())
        self.particle_layer.raise_()
        self.board_view.bind_particle_layer(self.particle_layer)

        self.setFocusPolicy(Qt.StrongFocus)
        self.refresh()

    def _build_start_page(self):
        page = StartDecorPage()                    # 自绘装饰背景的容器
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.addStretch(3)                       # 内容整体略偏上

        title = QLabel("2048")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {SP_TITLE}; font-size: 74px; font-weight: 800;")
        title.setAttribute(Qt.WA_TranslucentBackground, True)
        title_shadow = QGraphicsDropShadowEffect(title)   # 极轻的文字阴影
        title_shadow.setBlurRadius(10)
        title_shadow.setOffset(0, 2)
        title_shadow.setColor(QColor(119, 110, 101, 45))
        title.setGraphicsEffect(title_shadow)

        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {SP_SUBTEXT}; font-size: 13px;")

        layout.addWidget(title)
        layout.addSpacing(7)
        layout.addWidget(subtitle)
        layout.addSpacing(35)

        layout.addWidget(self._build_last_game_card(), 0, Qt.AlignHCenter)
        layout.addSpacing(24)

        self.continue_start_button = self._make_button(
            "继续上一局", self.on_continue_clicked, qss=SP_PRIMARY_QSS,
            size=(SP_BTN_W, SP_BTN_H), focusable=True,
            arrow=("#FFFFFF", "#F1EAE0"),
            hover=("hover_continue", HOVER_CONTINUE_INTERVAL, *HOVER_CONTINUE_COLORS))
        self.new_game_start_button = self._make_button(
            "开始新游戏", self.on_new_game_clicked, qss=SP_SECONDARY_QSS,
            size=(SP_BTN_W, SP_BTN_H), focusable=True, particle_color="#c7b9a8",
            arrow=("#776E65", "#B7A595"),
            hover=("hover_new_game", HOVER_NEW_GAME_INTERVAL, *HOVER_NEW_GAME_COLORS))
        layout.addWidget(self.continue_start_button, 0, Qt.AlignHCenter)
        layout.addSpacing(13)
        layout.addWidget(self.new_game_start_button, 0, Qt.AlignHCenter)
        layout.addStretch(4)
        return page

    def _build_last_game_card(self):
        """浅米色圆角信息卡：顶部标题（带装饰线）+ 分数 / 最高分等宽双列（居中 1px 竖线）"""
        card = QFrame()
        card.setObjectName("infoCard")
        card.setFixedSize(SP_CARD_W, SP_CARD_H)      # 卡片外框尺寸保持不变
        card.setStyleSheet(
            f"#infoCard {{ background-color: {SP_CARD_BG};"
            f" border: 1px solid {SP_LINE}; border-radius: {SP_CARD_RADIUS}px; }}")
        card_shadow = QGraphicsDropShadowEffect(card)     # 轻微柔和阴影
        card_shadow.setBlurRadius(16)
        card_shadow.setOffset(0, 3)
        card_shadow.setColor(QColor(119, 110, 101, 40))
        card.setGraphicsEffect(card_shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SP_CARD_PAD_X, 13, SP_CARD_PAD_X, 14)
        card_layout.setSpacing(0)

        self.last_game_caption = QLabel("上一局记录")
        self.last_game_caption.setAlignment(Qt.AlignCenter)
        self.last_game_caption.setFont(self._card_title_font())
        self.last_game_caption.setStyleSheet(f"color: {SP_CARD_TITLE_COLOR};")

        caption_row = QHBoxLayout()
        caption_row.setSpacing(8)
        caption_row.addStretch()
        caption_row.addWidget(self._make_rule())
        caption_row.addWidget(self.last_game_caption)
        caption_row.addWidget(self._make_rule())
        caption_row.addStretch()
        card_layout.addLayout(caption_row)
        card_layout.addSpacing(11)

        # 左右等宽统计列：两列 stretch 相同 → 宽度一致；中央竖线固定 1px 且严格居中，
        # 不随数字长度变化而偏移（不依赖硬编码坐标）
        score_col, self.last_score_value = self._make_stat("分数")
        best_col, self.last_best_value = self._make_stat("最高分")
        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(0)
        stats.addWidget(score_col, 1)
        stats.addWidget(self._make_divider(), 0, Qt.AlignVCenter)
        stats.addWidget(best_col, 1)
        card_layout.addLayout(stats)
        return card

    # ---- 信息卡字体（统一用 QFont 设置字号/字重，家族沿用应用当前 UI 字体） ----
    @staticmethod
    def _card_value_font(size=SP_CARD_VALUE_SIZE):
        font = QFont()
        font.setPixelSize(int(size))
        font.setWeight(QFont.DemiBold)               # 600 Semibold
        return font

    @staticmethod
    def _card_caption_font():
        font = QFont()
        font.setPixelSize(SP_CARD_CAPTION_SIZE)
        font.setWeight(QFont.Medium)                 # 500
        return font

    @staticmethod
    def _card_title_font():
        font = QFont()
        font.setPixelSize(SP_CARD_TITLE_SIZE)
        font.setWeight(QFont.Medium)                 # 500
        return font

    @staticmethod
    def _make_rule():
        """卡片标题两侧的短装饰线"""
        line = QFrame()
        line.setFixedSize(26, 1)
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"background-color: {SP_LINE}; border: none;")
        return line

    @staticmethod
    def _make_divider():
        """分数与最高分之间的 1px 竖向分隔线"""
        line = QFrame()
        line.setFixedSize(SP_CARD_DIVIDER_W, SP_CARD_DIVIDER_H)
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"background-color: {SP_LINE}; border: none;")
        return line

    def _make_stat(self, caption):
        """一列统计（等宽容器）：数值与标签均水平居中，块整体垂直居中"""
        col = QWidget()
        box = QVBoxLayout(col)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)                            # 数值与标签间距 4px
        box.addStretch()

        value = QLabel("0")
        value.setAlignment(Qt.AlignCenter)
        value.setFont(self._card_value_font())
        value.setStyleSheet(f"color: {SP_TEXT};")

        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        cap.setFont(self._card_caption_font())
        cap.setStyleSheet(f"color: {SP_CARD_LABEL_COLOR};")

        box.addWidget(value)
        box.addWidget(cap)
        box.addStretch()
        return col, value

    def _fit_stat_value(self, label, text):
        """写入数值文本；过长时按 1px 步进缩小字号（下限 SP_CARD_VALUE_MIN_SIZE）。

        用 QFontMetrics 实测文本宽度（不按字符数推断），常规 4～6 位数保持标准 28px。
        """
        label.setText(text)
        col = label.parentWidget()
        avail = (col.width() if col is not None and col.width() > 0 else SP_CARD_COLUMN_W)
        size = SP_CARD_VALUE_SIZE
        font = self._card_value_font(size)
        fm = QFontMetrics(font)
        while size > SP_CARD_VALUE_MIN_SIZE and fm.horizontalAdvance(text) > avail - 6:
            size -= 1
            font = self._card_value_font(size)
            fm = QFontMetrics(font)
        label.setFont(font)

    def _build_game_page(self):
        page = QWidget()
        page.setObjectName("page")
        page.setStyleSheet(f"#page {{ background-color: {COLOR_BG}; }}")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(GAME_MARGIN_X, 30, GAME_MARGIN_X, 24)
        main_layout.setSpacing(0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("2048")
        title.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 48px; font-weight: bold;")
        subtitle = QLabel("合并数字，拼出 2048")
        subtitle.setStyleSheet(f"color: {COLOR_SUBTITLE}; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.score_label = self._make_score_card()
        self.best_label = self._make_score_card()

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(title_box)
        header.addStretch()
        header.addWidget(self.score_label, 0, Qt.AlignTop)
        header.addWidget(self.best_label, 0, Qt.AlignTop)

        self.board_view = BoardView(self.model.grid_size)
        self.board_view.animationFinished.connect(self._on_animation_finished)

        self.undo_button = self._make_button("撤销", self.on_undo, qss=SECONDARY_BUTTON_QSS,
                                             particle_color="#cbbcaa")
        self.redo_button = self._make_button("重做", self.on_redo, qss=SECONDARY_BUTTON_QSS,
                                             particle_color="#cbbcaa")
        self.undo_button.setToolTip("撤销上一步（Ctrl+Z）")
        self.redo_button.setToolTip("重做（Ctrl+Y）")
        self.new_game_button = self._make_button("新游戏", self.on_new_game_clicked)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addWidget(self.undo_button)
        button_layout.addWidget(self.redo_button)
        button_layout.addStretch()
        button_layout.addWidget(self.new_game_button)

        main_layout.addLayout(header)
        main_layout.addSpacing(18)
        main_layout.addWidget(self.board_view)
        main_layout.addSpacing(32)
        main_layout.addLayout(button_layout)
        main_layout.addStretch()
        return page

    def _make_score_card(self):
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(96, 62)
        label.setStyleSheet(
            f"background-color: {COLOR_BOARD}; border-radius: {TILE_RADIUS}px;")
        return label

    def _render_score(self, label, caption, value):
        label.setText(
            f"<div style='font-size:11px; color:{COLOR_CARD_LABEL};'>{caption}</div>"
            f"<div style='font-size:24px; color:{COLOR_CARD_VALUE}; font-weight:bold;'>{value}</div>")

    def _make_button(self, text, slot, qss=PRIMARY_BUTTON_QSS,
                     size=(BUTTON_WIDTH, BUTTON_HEIGHT), focusable=False,
                     particle_color="#8f7a66", arrow=None, hover=None):
        # arrow=(正常色, 禁用色) 时使用带右侧箭头的按钮；箭头不参与布局
        button = ArrowButton(text, arrow[0], arrow[1]) if arrow else EnterButton(text)
        button.setFixedSize(*size)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.StrongFocus if focusable else Qt.NoFocus)
        button.setStyleSheet(qss)
        button.clicked.connect(slot)
        # 启用状态下按下：在按压点撒少量粒子（禁用按钮不触发）
        button.pressedAt.connect(
            lambda x, y, b=button, c=particle_color: self._emit_button_particles(b, x, y, c))
        # hover=(预设名, 间隔ms, 主色, 高光, 辅助色)：悬停期间按间隔持续发射
        if hover:
            preset_name, interval_ms, main_hex, accent_hex, aux_hex = hover
            shard_pool = (main_hex, aux_hex)      # 主碎片在主色 / 辅助色间交替
            button.set_hover_particles(True, interval_ms)
            button.hoverPulse.connect(
                lambda x, y, b=button, p=preset_name, m=shard_pool, a=accent_hex:
                    self._emit_hover_particles(b, x, y, p, m, a))
        return button

    def _emit_button_particles(self, button, x, y, color_hex):
        layer = getattr(self, "particle_layer", None)
        if layer is None or not button.isEnabled():
            return
        main = QColor(color_hex)
        layer.emit_from(button, x, y, main, main.lighter(165), "button")

    def _emit_hover_particles(self, button, x, y, preset_name, shard_pool, accent_hex):
        layer = getattr(self, "particle_layer", None)
        if layer is None or not button.isEnabled() or not button.isVisible():
            return
        if layer.is_saturated():                  # 达到同屏上限：优先削减新的悬停粒子
            return
        # 混合发射：鼠标附近（带抖动）60% + 按钮安全区内随机 40%
        w, h = button.width(), button.height()
        area = QRectF(HOVER_AREA_PAD_X * w, HOVER_AREA_PAD_Y * h,
                      w * (1.0 - 2 * HOVER_AREA_PAD_X),
                      h * (1.0 - 2 * HOVER_AREA_PAD_Y))
        main = QColor(shard_pool[self._hover_shard_toggle % len(shard_pool)])
        self._hover_shard_toggle += 1
        layer.emit_from(button, x, y, main, QColor(accent_hex), preset_name,
                        area_rect=area, area_ratio=HOVER_SPAWN_AREA_RATIO,
                        jitter=HOVER_SPAWN_JITTER)

    # ---------------- 刷新视图 ----------------
    def _sync_history_buttons(self):
        """撤销/重做按钮的视觉状态只跟随历史栈，与动画状态彻底解耦。

        动画期间不再切换 enabled，因此连续滑动时不会出现“禁用态颜色反复闪烁”；
        动画期间的操作保护由 on_move / on_undo / on_redo 的入口检查负责。
        """
        self.undo_button.setEnabled(self.model.can_undo())
        self.redo_button.setEnabled(self.model.can_redo())

    def refresh(self):
        if not self.board_view.is_animating():
            self.board_view.render(self.model.grid)
        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self._sync_history_buttons()
        if not self.model.game_over:          # 撤销/继续后允许再次提示“游戏结束”
            self._game_over_notified = False

    # ---------------- 键盘事件 ----------------
    def keyPressEvent(self, event):
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.ControlModifier)

        if ctrl and key == Qt.Key_Z:
            self.on_undo()
            return
        if ctrl and key == Qt.Key_Y:
            self.on_redo()
            return

        direction = {
            Qt.Key_Up: 'up', Qt.Key_W: 'up',
            Qt.Key_Down: 'down', Qt.Key_S: 'down',
            Qt.Key_Left: 'left', Qt.Key_A: 'left',
            Qt.Key_Right: 'right', Qt.Key_D: 'right',
        }.get(key)

        if direction is None:
            super().keyPressEvent(event)
            return
        self.on_move(direction)

    # ---------------- 交互回调 ----------------
    def on_move(self, direction):
        if self.model.game_over or self.board_view.is_animating():
            return                      # 动画进行中忽略输入（保护历史状态；不影响按钮外观）
        if not self.model.apply_move(direction):
            return

        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self._sync_history_buttons()         # 历史已变化：立即更新按钮外观（无动画耦合）
        self.board_view.animate_move(self.model.grid, self.model.last_transitions,
                                     self.model.last_spawn)

    def _on_animation_finished(self):
        self.refresh()
        if self.model.game_over:
            self.show_game_over()
        elif self.model.won and not self.win_announced:
            self.win_announced = True
            self._celebrate()                 # 首次达成 2048：金色庆祝（整局一次）
            self.show_game_won()

    def _celebrate(self):
        """首次达到 2048：在 2048 方块处释放一次金色庆祝粒子"""
        layer = getattr(self, "particle_layer", None)
        if layer is None:
            return
        row = col = None
        for i in range(self.model.grid_size):
            for j in range(self.model.grid_size):
                if self.model.grid[i][j] == 2048:
                    row, col = i, j
                    break
            if row is not None:
                break
        if row is None:
            x, y = BOARD_SIDE / 2.0, BOARD_SIDE / 2.0
        else:
            bx, by = self.board_view._cell_xy(row, col)
            x, y = bx + TILE_SIZE / 2.0, by + TILE_SIZE / 2.0
        layer.emit_from(self.board_view, x, y,
                        COLOR_CELEBRATE_MAIN, COLOR_CELEBRATE_ACCENT, "celebrate")

    def on_undo(self):
        if self.board_view.is_animating():
            return                      # 动画进行中忽略本次撤销（不改变棋盘与历史栈）
        info = self.model.undo()
        if not info:
            return
        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self._sync_history_buttons()
        self.board_view.animate_undo(self.model.grid, info["transitions"], info["spawn"])

    def on_redo(self):
        if self.board_view.is_animating():
            return                      # 动画进行中忽略本次重做（不改变棋盘与历史栈）
        info = self.model.redo()
        if not info:
            return
        self._render_score(self.score_label, "分数", self.model.score)
        self._render_score(self.best_label, "最高分", self.model.best_score)
        self._sync_history_buttons()
        self.board_view.animate_move(self.model.grid, info["transitions"], info["spawn"])

    # ---------------- 启动流程 ----------------
    def startup(self):
        info = self.model.get_recent_game_info()
        self._render_last_game(info)
        if info is None:
            self.start_new_game()
        else:
            self.stack.setCurrentIndex(START_PAGE)
            (self.continue_start_button if self.continue_start_button.isEnabled()
             else self.new_game_start_button).setFocus()
        if not getattr(self.model, "can_save", True):
            QTimer.singleShot(300, self._warn_readonly)

    def _warn_readonly(self):
        _theme.show_warning(self, "只读模式",
                            "检测到同一版本已有另一个进程在运行。\n"
                            "为避免覆盖存档，本次运行不会写入磁盘。")

    def _render_last_game(self, info):
        if info is None:
            self.last_game_caption.setText("暂无可继续的存档")
            self._fit_stat_value(self.last_score_value, "—")
            self._fit_stat_value(self.last_best_value, str(self.model.best_score))  # 历史最高分仍动态显示
            self.continue_start_button.setEnabled(False)
        else:
            self.last_game_caption.setText("上一局记录")
            self._fit_stat_value(self.last_score_value, str(info.get("score", 0)))
            self._fit_stat_value(self.last_best_value, str(info.get("best_score", 0)))
            self.continue_start_button.setEnabled(True)

    def on_continue_clicked(self):
        recent = self.model.get_recent_game()
        if not recent:
            return
        if self.model.load_game_state(recent):
            self.win_announced = self.model.won
            self._game_over_notified = self.model.game_over
            self.refresh()
            self._reset_start_hover()
            self.stack.setCurrentIndex(GAME_PAGE)
            self.setFocus()
            if self.model.last_load_used_backup:
                _theme.show_info(self, "存档已恢复", "主存档损坏，已自动从备份恢复。",
                                 badge="success")
        else:
            self._reset_start_hover()
            _theme.show_error(self, "无法继续上一局",
                              "存档不可用：%s" % (self.model.last_load_error or "未知原因"))

    def on_new_game_clicked(self):
        # 明确选择“开始新游戏”：先把被放弃的上一局结算为已结束，避免旧档残留为可续玩
        pending = self.model.get_recent_game_info()
        if pending:
            self.model.mark_game_completed(pending.get("game_id"))
        self.start_new_game()

    def start_new_game(self):
        self.model.start_new_game()
        self.win_announced = False
        self._game_over_notified = False
        self.refresh()
        self._reset_start_hover()
        self.stack.setCurrentIndex(GAME_PAGE)
        self.setFocus()

    def _reset_start_hover(self):
        """离开启动页时立即停止两个按钮的持续发射（不清空已有粒子）"""
        for button in (getattr(self, "continue_start_button", None),
                       getattr(self, "new_game_start_button", None)):
            if button is not None:
                button.stop_hover_emission()

    # ---------------- 主题化弹窗（替换原生 QMessageBox） ----------------
    def show_game_over(self):
        if self._game_over_notified:
            return                              # 同一局只提示一次，避免动画回调重复弹出
        self._game_over_notified = True
        choice = _theme.ask_choice(
            self, "游戏结束", "本局已无可行移动。",
            options=[("重新开始", "secondary"), ("关闭", "primary")],
            default_index=1, escape_index=1, badge="info",
            detail_lines=[("最终分数", self.model.score),
                          ("历史最高分", self.model.best_score)])
        if choice == 0:
            self.start_new_game()               # 内部 refresh 会复位提示标志

    def show_game_won(self):
        # 与原生 QMessageBox.question(Yes|No) 语义一致：否/取消=重新开始，是=继续挑战
        choice = _theme.ask_choice(
            self, "恭喜胜利", "你已经达到 2048！是否继续挑战更高分数？",
            options=[("重新开始", "secondary"), ("继续挑战", "primary")],
            default_index=1, escape_index=0, badge="success")
        if choice == 0:
            self.start_new_game()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        layer = getattr(self, "particle_layer", None)
        if layer is not None:                     # 窗口尺寸变化时让粒子层跟随
            layer.setGeometry(self.rect())
            layer.raise_()

    def closeEvent(self, event):
        layer = getattr(self, "particle_layer", None)
        if layer is not None:                     # 窗口销毁前停表并清空粒子
            layer.shutdown()
        self.model.save_game_state()
        self.model.update_index()
        self.model.release_lock()
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setWindowIcon(build_app_icon())   # 应用级图标：标题栏 / 任务栏统一显示 2048 图标
    font = QFont("Microsoft YaHei", 10)
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Microsoft YaHei", "Microsoft YaHei UI", "SimHei"])
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
