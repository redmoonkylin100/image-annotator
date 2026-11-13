# -*- coding: utf-8 -*-
"""精确复现测试中 q2/q3 失败场景。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.window import MainWindow
from annotator import window as winmod

app = QApplication([])
winmod.settings.load = lambda: {}
win = MainWindow(restore=False)
win.show()
cv = win.canvas
panel = win.panel
pm = QPixmap(400, 300)
pm.fill(QColor("#FFFFFF"))
cv.load_pixmap(pm)

panel._finish_pick_color("shape_border", None)
panel._finish_pick_color("shape_fill", None)
shape = cv.add_shape_item((20, 20), (180, 150), "rect")
shape.selected = True
panel._apply_to_selection()
print("after apply:", shape.border_color.getRgb(), shape.fill_color.getRgb())
print("shape val:", shape.shape, "text_pos:", shape.text_pos)


def render(item):
    qimg = QImage(220, 180, QImage.Format.Format_ARGB32)
    qimg.fill(QColor("#FFFFFF"))
    qp = QPainter(qimg)
    item.paint(qp, export=False)
    qp.end()
    return qimg


shape.border_color = QColor(0, 0, 0, 0)
shape.fill_color = QColor("#2F80ED")
q2 = render(shape)
print("q2 center:", q2.pixelColor(100, 85).name(QColor.NameFormat.HexArgb),
      "== QColor(#2F80ED)?", q2.pixelColor(100, 85) == QColor("#2F80ED"))
print("q2 border:", q2.pixelColor(100, 20).name(QColor.NameFormat.HexArgb))

shape.border_color = QColor("#FF0000")
shape.fill_color = QColor(255, 255, 255, 0)
q3 = render(shape)
print("q3 center:", q3.pixelColor(100, 85).name(QColor.NameFormat.HexArgb),
      "== QColor(#FFFFFF)?", q3.pixelColor(100, 85) == QColor("#FFFFFF"))
print("q3 border:", q3.pixelColor(100, 20).name(QColor.NameFormat.HexArgb),
      "== QColor(#FF0000)?", q3.pixelColor(100, 20) == QColor("#FF0000"))
os._exit(0)
