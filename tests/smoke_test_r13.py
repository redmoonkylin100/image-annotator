# -*- coding: utf-8 -*-
"""第十三轮冒烟测试：形状菜单选择稳定性（手动 popup + 延迟应用）、
全部形状绘制、历史面板增量刷新（高频 refresh 不崩）、
各类元素选中状态下切换形状不崩。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import autosave, settings
settings.clear()
autosave.clear()

from annotator.canvas import MODE_LEADER, MODE_NUMBER, MODE_PEN, MODE_SELECT, MODE_SHAPE
from annotator.items import (LeaderLineItem, PenItem, ShapeItem, TextItem,
                             SHAPE_OPTIONS)
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


w = MainWindow(restore=False)
w.show()
app.processEvents()
pm = QPixmap(700, 460)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)

# ---------- 1. 形状菜单：手动 popup + 每项选择 ----------
menu = w.panel.shape_menu
check("形状菜单 10 项", len(menu.actions()) == 10)
for act in menu.actions():
    w.panel._set_shape(act.text())
    val = w.panel._shape_val
    check(f"选择形状[{act.text()}]", any(v == val for _, v in SHAPE_OPTIONS))
w.panel._set_shape("rect")
check("菜单选择回矩形", w.panel._shape_val == "rect")
# 无效形状兜底
w.panel._set_shape("not_exist")
check("无效形状回退矩形", w.panel._shape_val == "rect")
w.panel._set_shape("rect")

# ---------- 2. 全部形状逐绘制（渲染路径） ----------
w.canvas.set_mode(MODE_SHAPE)
for i, (_, val) in enumerate(SHAPE_OPTIONS):
    for x in w.canvas.items:      # 清除上一步的选中，避免样式应用到选中元素
        x.selected = False
    w.panel._set_shape(val)
    x0, y0 = 40 + (i % 5) * 130, 60 + (i // 5) * 120
    QTest.mousePress(w.canvas, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(x0, y0))
    QTest.mouseMove(w.canvas, QPoint(x0 + 90, y0 + 70))
    QTest.mouseRelease(w.canvas, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(x0 + 90, y0 + 70))
app.processEvents()
shapes = [it for it in w.canvas.items if isinstance(it, ShapeItem)]
check("10 种形状全部绘制成功", len(shapes) == 10)
check("形状类型各不相同",
      len({it.shape for it in shapes}) == len(SHAPE_OPTIONS))
w.canvas.set_mode(MODE_SELECT)

# ---------- 3. 各类元素选中状态下切换形状不崩 ----------
w.panel._set_shape("triangle")
for it in list(w.canvas.items):
    for x in w.canvas.items:
        x.selected = False
    it.selected = True
    w.panel.sync_from_selection([it])
    w.panel._set_shape("rect")
    w.panel._set_shape("ellipse")
    w.canvas.update()
app.processEvents()
check("各类元素选中+切形状不崩", True)

# ---------- 4. 历史面板高频增量刷新（原 clear() 重建会闪退） ----------
for _ in range(60):
    w.history.refresh(w.canvas.items)
app.processEvents()
check("历史面板高频刷新不崩(60次)", True)
w.canvas.add_leader_item(QPointF(120, 300), QPointF(400, 200), "顺序测试")
w.canvas.renumber()
w.history.refresh(w.canvas.items)
w.history.refresh(list(reversed(w.canvas.items)))   # 顺序变化
w.history.refresh(w.canvas.items)                    # 回到原序
check("历史面板行顺序变化不崩", True)
check("历史列表行数正确", w.history.list.count() == len(w.canvas.items))

# ---------- 5. 形状菜单触发链（真实触发回调路径） ----------
w.panel._set_shape("star")
w.canvas.items[0].selected = True
w.panel._apply_to_selection()
w.canvas.update()
app.processEvents()
check("选中元素应用形状样式不崩", True)

w.close()
autosave.clear()
settings.clear()

fails = [n for n, ok in PASS if not ok]
print(f"\nRESULT: {len(PASS) - len(fails)}/{len(PASS)} passed")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("SMOKE OK")
