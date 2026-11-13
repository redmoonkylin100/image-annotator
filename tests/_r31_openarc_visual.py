# -*- coding: utf-8 -*-
"""空心弧修复可视化：方形/扁形/高形三种外框，描边+填充两种效果。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from annotator.items import shape_path, SHAPE_OPEN_ARC

img = QImage(760, 300, QImage.Format.Format_ARGB32)
img.fill(QColor("#FFFFFF"))
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)

cases = [(QRectF(20, 30, 240, 240), QColor("#89FF6B"), "square"),
         (QRectF(290, 60, 200, 180), QColor("#89FF6B"), "wide"),
         (QRectF(530, 20, 160, 260), QColor("#89FF6B"), "tall")]
for rect, fill, tag in cases:
    path = shape_path(SHAPE_OPEN_ARC, rect)
    assert path.boundingRect().intersects(rect.adjusted(-1, -1, 1, 1)), tag
    p.setPen(QPen(QColor("#3040D0"), 2))
    p.setBrush(fill)
    p.drawPath(path)
    p.setPen(QPen(QColor("#CCCCCC"), 1, Qt.PenStyle.DashLine))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(rect)
p.end()
out = os.path.join(ROOT, "tests", "_r31_openarc.png")
img.save(out)
print("saved", out)
sys.exit(0)
