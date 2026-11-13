# -*- coding: utf-8 -*-
"""r24 回归：
1) 直线画线时中键/右键短按完成画线（与 ESC/回车相同）；
2) 选择模式下操作形状菜单（选图案）自动切换到形状工具；
3) 顶部工具栏 100% 与主题按钮间存在对齐按钮（v1.7 居中按钮移除）；
4) 启动/新打开图片时图片居中显示；
5) 表情面板每行 5 个表情，右侧面板最小宽度 180px 防遮挡。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import time as _time
from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel

from annotator.window import MainWindow
from annotator.items import SHAPE_LINE, ShapeItem
from annotator import canvas as canvas_mod

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    cv = win.canvas
    panel = win.panel

    def fresh_image(w=400, h=300):
        pm = QPixmap(w, h)
        pm.fill(QColor("#FFFFFF"))
        cv.load_pixmap(pm, fit=False)
        cv.resize(900, 700)
        cv.scale = 1.0
        cv.offset = QPointF(0.0, 0.0)
        return pm

    # ---- 事件工厂 ----
    def press(x, y, btn=Qt.MouseButton.LeftButton):
        e = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                        btn, btn, Qt.KeyboardModifier.NoModifier)
        cv.mousePressEvent(e)

    def move(x, y, held=False, btn=Qt.MouseButton.LeftButton):
        btns = btn if held else Qt.MouseButton.NoButton
        e = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                        Qt.MouseButton.NoButton, btns,
                        Qt.KeyboardModifier.NoModifier)
        cv.mouseMoveEvent(e)

    def release(x, y, btn=Qt.MouseButton.LeftButton):
        e = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                        btn, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
        cv.mouseReleaseEvent(e)

    def key(k):
        e = QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier)
        cv.keyPressEvent(e)

    # ==================== 1. 中键完成画线 ====================
    fresh_image()
    cv.set_mode("shape")
    panel._set_shape_val(SHAPE_LINE)
    n0 = len(cv.items)
    press(50, 50)           # 起点
    move(150, 50)           # 跟随
    press(150, 50)          # 第二点
    move(200, 100)          # 跟随
    # 中键点击 = 完成画线
    press(200, 100, btn=Qt.MouseButton.MiddleButton)
    check(cv._line_points is None, "中键完成画线：折线状态已清空")
    check(len(cv.items) == n0 + 1, "中键完成画线：生成 1 个折线元素")
    check(len(cv.items[-1].points) == 2, "中键完成画线：折线含 2 个顶点")

    # 中键不在画线状态时仍为平移
    fresh_image()
    cv.set_mode("shape")
    panel._set_shape_val(SHAPE_LINE)
    press(50, 50)
    # 不开始画线时中键不完成
    cv._line_points = None
    press(100, 100, btn=Qt.MouseButton.MiddleButton)
    check(cv._panning is True, "非画线状态中键仍启动平移")

    # ==================== 2. 右键短按完成画线 ====================
    fresh_image()
    cv.set_mode("shape")
    panel._set_shape_val(SHAPE_LINE)
    n0 = len(cv.items)
    press(30, 30)
    move(100, 80)
    press(100, 80)
    move(200, 150)
    # 右键短按（模拟快速点击）
    press(200, 150, btn=Qt.MouseButton.RightButton)
    # 立即释放（短按 <0.3s，未移动）
    release(200, 150, btn=Qt.MouseButton.RightButton)
    check(cv._line_points is None, "右键短按完成画线：折线状态已清空")
    check(len(cv.items) == n0 + 1, "右键短按完成画线：生成 1 个折线元素")

    # 右键短按不在画线状态时仍为取消（Esc）
    fresh_image()
    cv.set_mode("leader")
    cv._pending_target = QPointF(50, 50)
    press(200, 200, btn=Qt.MouseButton.RightButton)
    release(200, 200, btn=Qt.MouseButton.RightButton)
    check(cv._pending_target is None, "非画线状态右键短按仍取消待操作")
    check(cv.mode == "select", "非画线状态右键短按切回选择模式")

    # ==================== 3. 选择模式下选形状图案自动切换工具 ====================
    fresh_image()
    cv.set_mode("select")
    check(cv.mode == "select", "初始为选择模式")
    # 模拟从形状菜单选择矩形（调用 _set_shape，不是 _set_shape_val）
    panel._set_shape("rect")
    app.processEvents()
    check(cv.mode == "shape", "选择模式下选择形状图案 -> 自动切换到形状工具")

    # 选择直线也切换
    cv.set_mode("select")
    panel._set_shape(SHAPE_LINE)
    app.processEvents()
    check(cv.mode == "shape", "选择模式下选择直线 -> 自动切换到形状工具")

    # _syncing 期间不触发切换（设置恢复不误切模式）
    panel._syncing = True
    cv.set_mode("select")
    panel._set_shape("rect")
    panel._syncing = False
    check(cv.mode == "select", "设置恢复（_syncing）期间选择形状不切换模式")

    # ==================== 4. 对齐按钮 + center_image ====================
    # v1.7 需求7：工具栏重排后居中按钮移除，改为「对齐」按钮（100% 与主题之间）
    cb = getattr(win, "align_btn", None)
    check(cb is not None, "顶部工具栏存在对齐按钮")
    check(cb.toolTip() == "一键对齐/自动布局：引线标注自动左/中/右、上/下对齐",
          "对齐按钮 tooltip 正确")
    check(cb.receivers(cb.clicked) > 0, "对齐按钮已接线")
    check(getattr(win, "center_btn", None) is None, "v1.7 已移除独立居中按钮")

    # 按钮位置：在 100% 和主题按钮之间
    order = []
    def _walk(w):
        for c in w.children():
            if c.__class__.__name__ == "QPushButton":
                order.append(c.text())
            _walk(c)
    _walk(win.toolbar)
    def _pos(s):
        return order.index(s) if s in order else -1
    check(_pos("对齐") > _pos("100%"), "对齐按钮在 100% 按钮右侧")
    check(_pos("对齐") < _pos("🌙") or _pos("对齐") < _pos("☀️"),
          "对齐按钮在主题按钮左侧")

    # center_image 方法存在且功能正确
    check(hasattr(cv, "center_image"), "canvas 有 center_image 方法")
    fresh_image(200, 150)
    cv.scale = 2.0
    cv.offset = QPointF(100.0, 200.0)  # 偏移到非居中位置
    cv.center_image()
    expected_x = (cv.width() - 200 * 2.0) / 2.0
    expected_y = (cv.height() - 150 * 2.0) / 2.0
    check(abs(cv.offset.x() - expected_x) < 1e-6 and abs(cv.offset.y() - expected_y) < 1e-6,
          f"center_image 在 scale=2 下正确居中：offset=({cv.offset.x():.1f},{cv.offset.y():.1f})")

    # 点击居中按钮
    cv.offset = QPointF(500.0, 500.0)
    cb.click()
    app.processEvents()
    check(abs(cv.offset.x() - expected_x) < 1e-6, "点击居中按钮后图片居中")

    # ==================== 5. 启动/新打开图片居中 ====================
    fresh_image(300, 200)
    app.processEvents()
    # imageLoaded 信号已触发，QTimer.singleShot(0, center_image) 排队
    # 手动处理待发事件
    QTimer.singleShot(0, lambda: None)  # 确保事件循环跑一轮
    app.processEvents()
    expected_cx = (cv.width() - 300 * cv.scale) / 2.0
    expected_cy = (cv.height() - 200 * cv.scale) / 2.0
    check(abs(cv.offset.x() - expected_cx) < 1e-6 and abs(cv.offset.y() - expected_cy) < 1e-6,
          f"新打开图片后自动居中：offset=({cv.offset.x():.1f},{cv.offset.y():.1f})")

    # ==================== 6. 表情面板每行 5 个 ====================
    # 找到 emoji grid
    emoji_grid = None
    for w in panel.findChildren(type(panel)):
        pass
    # 直接检查 _emoji_buttons 的布局
    emoji_buttons = getattr(panel, "_emoji_buttons", {})
    check(len(emoji_buttons) == 24, f"表情按钮共 24 个（实际 {len(emoji_buttons)}）")
    # 检查布局列数：通过 grid_em 的 columnCount
    grids = []
    from PyQt6.QtWidgets import QGridLayout
    def _find_grids(parent):
        lay = parent.layout()
        if lay is not None:
            for i in range(lay.count()):
                sub = lay.itemAt(i)
                if sub.layout() is not None and isinstance(sub.layout(), QGridLayout):
                    grids.append(sub.layout())
                w = sub.widget()
                if w is not None:
                    _find_grids(w)
        for i in range(lay.count() if lay else 0):
            pass
    _find_grids(panel)
    emoji_grid = None
    for g in grids:
        # 找包含 emoji 按钮的 grid
        for i in range(g.count()):
            w = g.itemAt(i).widget()
            if w is not None and w.text() in emoji_buttons:
                emoji_grid = g
                break
        if emoji_grid:
            break
    check(emoji_grid is not None, "找到表情 grid 布局")
    if emoji_grid:
        # 统计有多少列有按钮
        max_col = -1
        for i in range(emoji_grid.count()):
            r, c = emoji_grid.getItemPosition(i)[:2]
            if c > max_col:
                max_col = c
        check(max_col == 4, f"表情每行 5 个（列索引 0~4，最大列索引={max_col}）")

    # 右侧面板最小宽度
    check(win.right_box.minimumWidth() >= 180,
          f"右侧面板最小宽度 >= 180（实际 {win.right_box.minimumWidth()}）")

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit(); os._exit(1)
    print("==== r24 全部断言通过 ====")
    app.quit(); os._exit(0)


if __name__ == "__main__":
    main()
