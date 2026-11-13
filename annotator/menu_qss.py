# -*- coding: utf-8 -*-
"""菜单（QMenu）明暗主题 QSS。

Qt 特性：带父控件的 QMenu 弹出层【不继承】应用级样式表，也不继承窗口
样式表，会落回原生浅色调色板（暗黑主题下右键菜单变白底，v1.7 需求8）。
因此所有右键菜单在弹出前必须调用 apply_menu_theme 直接套主题 QSS。
"""

MENU_QSS_DARK = (
    "QMenu { background-color: #2f2f3a; color: #F2F2F2;"
    " border: 1px solid #555555; padding: 3px; }"
    "QMenu::item { padding: 5px 24px; border-radius: 3px; }"
    "QMenu::item:selected { background-color: #2f6fed; color: white; }"
    "QMenu::item:disabled { color: #8a8a8a; }"
    "QMenu::separator { height: 1px; background: #555555;"
    " margin: 4px 8px; }"
    "QMenu::indicator { width: 14px; height: 14px; }"
)

MENU_QSS_LIGHT = (
    "QMenu { background-color: #FFFFFF; color: #1A1A1A;"
    " border: 1px solid #C8CBD0; padding: 3px; }"
    "QMenu::item { padding: 5px 24px; border-radius: 3px; }"
    "QMenu::item:selected { background-color: #2f6fed; color: white; }"
    "QMenu::item:disabled { color: #A0A4AB; }"
    "QMenu::separator { height: 1px; background: #E0E2E6;"
    " margin: 4px 8px; }"
    "QMenu::indicator { width: 14px; height: 14px; }"
)


def apply_menu_theme(menu, dark: bool) -> None:
    """给菜单对象直接套用主题 QSS（保证弹窗不落回原生浅色）。"""
    menu.setStyleSheet(MENU_QSS_DARK if dark else MENU_QSS_LIGHT)
