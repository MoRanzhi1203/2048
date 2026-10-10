#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2048 主题化弹窗组件（v4 / v5 共用，暖棕配色）

目标：把第四版、第五版中所有原生 QMessageBox 统一为与游戏一致的暖棕风格弹窗，
同时完整保留：
    - 模态（exec_ 窗口模态）
    - 返回值 / 操作语义（确认=是、取消=否）
    - Enter（默认按钮）与 Escape（取消）键盘行为
    - 关闭按钮行为
    - 弹窗关闭后的焦点恢复
    - 父窗口关联

配色（与需求一致）：
    页面背景 #FAF8EF / 弹窗主体 #F3E9DC / 主文字 #776E65 / 次文字 #938579
    主按钮 #8F7A66 / 次按钮 #EDE1D4 / 边框 #D7C3AD
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QWidget, QApplication, QSizePolicy)
from PyQt5.QtCore import Qt


PALETTE = {
    "page": "#FAF8EF",
    "body": "#F3E9DC",
    "text": "#776E65",
    "subtext": "#938579",
    "primary": "#8F7A66",
    "primary_hover": "#9F8B78",
    "primary_press": "#7C6A58",
    "secondary": "#EDE1D4",
    "secondary_hover": "#E4D6C5",
    "secondary_press": "#D9C9B6",
    "button_text": "#F9F6F2",
    "border": "#D7C3AD",
    "line": "#E4D6C5",
}

# 徽标（badge）：分类颜色 + 单字符字形（非 emoji，避免字体缺失）
BADGE_STYLE = {
    "info":     ("#8F7A66", "i"),
    "question": ("#8F7A66", "?"),
    "warning":  ("#C08A3E", "!"),
    "error":    ("#B23B2E", "×"),
    "success":  ("#7FA05A", "✓"),
}

DIALOG_WIDTH = 348          # 内容宽度（需求建议 300～360）


def _primary_qss():
    p = PALETTE
    return (
        "QPushButton { background-color:%s; color:%s; border:1px solid %s;"
        " border-radius:8px; padding:6px 18px; font-size:13px; font-weight:600; }"
        "QPushButton:hover { background-color:%s; }"
        "QPushButton:pressed { background-color:%s; }"
        "QPushButton:focus { border-color:#EFE7DA; }"
        % (p["primary"], p["button_text"], p["primary"], p["primary_hover"], p["primary_press"]))


def _secondary_qss():
    p = PALETTE
    return (
        "QPushButton { background-color:%s; color:%s; border:1px solid %s;"
        " border-radius:8px; padding:6px 18px; font-size:13px; font-weight:600; }"
        "QPushButton:hover { background-color:%s; }"
        "QPushButton:pressed { background-color:%s; }"
        "QPushButton:focus { border-color:%s; }"
        % (p["secondary"], p["text"], p["border"], p["secondary_hover"],
           p["secondary_press"], p["primary"]))


# 供其它自定义对话框复用的按钮样式（v5 的结果对话框等）
def primary_button_qss():
    return _primary_qss()


def secondary_button_qss():
    return _secondary_qss()


def content_dialog_qss():
    """内容型弹窗（含表格/下拉）的整体主题样式。"""
    p = PALETTE
    return (
        "QDialog { background-color:%s; }"
        "QLabel { color:%s; font-size:12px; }"
        "QComboBox { background:#FFFFFF; color:%s; border:1px solid %s;"
        " border-radius:5px; padding:2px 6px; font-size:12px; }"
        "QComboBox::drop-down { border:none; width:16px; }"
        "QTableWidget { background:#FFFFFF; color:%s; gridline-color:%s;"
        " border:1px solid %s; border-radius:6px; font-size:12px; }"
        "QHeaderView::section { background:%s; color:%s; border:none;"
        " padding:4px; font-size:12px; }"
        % (p["page"], p["text"], p["text"], p["border"], p["text"], p["line"],
           p["border"], p["body"], p["text"]))


class ThemedDialog(QDialog):
    """暖棕主题弹窗基类。

    buttons: [(文案, 角色)]，角色为 "primary" / "secondary"
    default_index: 默认（Enter）按钮下标
    escape_index:  Escape / 关闭（X）时返回的下标（默认最后一个按钮）
    """

    def __init__(self, parent=None, title="提示", text="", badge="info",
                 detail_lines=None, buttons=None, default_index=0,
                 escape_index=None, width=DIALOG_WIDTH):
        super().__init__(parent)
        buttons = buttons or [("确定", "primary")]
        self._escape_index = len(buttons) - 1 if escape_index is None else escape_index
        self._index = self._escape_index

        self.setWindowTitle(title)
        self.setModal(True)
        # 去掉标题栏的“?”上下文帮助按钮（保留原生标题栏、图标与关闭按钮）
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if parent is not None and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setFixedWidth(width)

        p = PALETTE
        self.setStyleSheet(
            "QDialog { background-color:%s; }"
            "QLabel#dlgBody { color:%s; font-size:13px; }"
            "QLabel#dlgCaption { color:%s; font-size:12px; }"
            "QLabel#dlgValue { color:%s; font-size:15px; font-weight:600; }"
            "QLabel#dlgHeadline { color:%s; font-size:14px; font-weight:600; }"
            "QFrame#dlgLine { background-color:%s; }"
            % (p["body"], p["text"], p["subtext"], p["text"], p["text"], p["line"]))

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        # 顶部：徽标 + 正文
        top = QHBoxLayout()
        top.setSpacing(12)
        color, glyph = BADGE_STYLE.get(badge, BADGE_STYLE["info"])
        badge_label = QLabel(glyph)
        badge_label.setFixedSize(34, 34)
        badge_label.setAlignment(Qt.AlignCenter)
        badge_label.setStyleSheet(
            "QLabel { background-color:%s; color:#FFFFFF; border-radius:17px;"
            " font-size:18px; font-weight:700; }" % color)
        top.addWidget(badge_label, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(8)
        if text:
            body = QLabel(text)
            body.setObjectName("dlgBody")
            body.setWordWrap(True)
            body.setTextFormat(Qt.PlainText)
            body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            text_box.addWidget(body)
        if detail_lines:
            for caption, value in detail_lines:
                text_box.addLayout(self._detail_row(caption, value))
        top.addLayout(text_box, 1)
        root.addLayout(top)

        # 底部：按钮组（右对齐，尺寸统一）
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()
        for i, (label, role) in enumerate(buttons):
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_primary_qss() if role == "primary" else _secondary_qss())
            btn.setMinimumHeight(32)
            btn.setMinimumWidth(88)
            btn.setAutoDefault(True)
            if i == default_index:
                btn.setDefault(True)
                btn.setFocus()
            btn.clicked.connect(lambda _checked=False, idx=i: self._choose(idx))
            row.addWidget(btn)
        root.addLayout(row)

        self.layout().activate()
        self.adjustSize()
        self.setMinimumHeight(self.sizeHint().height())

    @staticmethod
    def _detail_row(caption, value):
        row = QHBoxLayout()
        row.setSpacing(8)
        cap = QLabel(caption)
        cap.setObjectName("dlgCaption")
        val = QLabel(str(value))
        val.setObjectName("dlgValue")
        row.addWidget(cap)
        row.addStretch()
        row.addWidget(val)
        return row

    def _choose(self, index):
        self._index = index
        self.accept()

    def reject(self):
        # Escape / 关闭按钮：返回 escape_index（与原生弹窗“取消/否”语义一致）
        self._index = self._escape_index
        super().reject()

    def exec_choice(self):
        """显示模态弹窗并返回所选按钮下标（关闭/Escape 返回 escape_index）。"""
        previous = QApplication.focusWidget()
        result = self.exec_()
        if result == QDialog.Rejected:
            self._index = self._escape_index
        if previous is not None:
            try:
                previous.setFocus()
            except RuntimeError:
                pass
        return self._index


# =====================================================================
# 便捷工厂（保持与 QMessageBox 一致的使用语义）
# =====================================================================
def show_info(parent, title, text, detail_lines=None, ok_text="确定", badge="info"):
    """提示弹窗（等价 QMessageBox.information）。"""
    dlg = ThemedDialog(parent, title, text, badge=badge, detail_lines=detail_lines,
                       buttons=[(ok_text, "primary")], default_index=0, escape_index=0)
    return dlg.exec_choice()


def show_warning(parent, title, text, detail_lines=None, ok_text="确定"):
    """警告弹窗（等价 QMessageBox.warning）。"""
    return show_info(parent, title, text, detail_lines, ok_text, badge="warning")


def show_error(parent, title, text, detail_lines=None, ok_text="确定"):
    """错误弹窗（等价 QMessageBox.critical）。"""
    return show_info(parent, title, text, detail_lines, ok_text, badge="error")


def ask_confirm(parent, title, text, confirm_text="确定", cancel_text="取消",
                default_confirm=True, badge="question", detail_lines=None):
    """确认弹窗，返回 True=确认 / False=取消（等价 QMessageBox.question 的 Yes/No）。"""
    buttons = [(cancel_text, "secondary"), (confirm_text, "primary")]
    default_index = 1 if default_confirm else 0
    escape_index = 0                      # 取消 / Escape / 关闭
    dlg = ThemedDialog(parent, title, text, badge=badge, detail_lines=detail_lines,
                       buttons=buttons, default_index=default_index,
                       escape_index=escape_index)
    return dlg.exec_choice() == 1


def ask_choice(parent, title, text, options, default_index=0, escape_index=None,
               badge="question", detail_lines=None):
    """多选弹窗，返回所选下标（options 为 [(文案, 角色)]）。"""
    dlg = ThemedDialog(parent, title, text, badge=badge, detail_lines=detail_lines,
                       buttons=options, default_index=default_index,
                       escape_index=escape_index)
    return dlg.exec_choice()
