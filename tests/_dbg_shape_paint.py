# -*- coding: utf-8 -*-
"""调试 ShapeItem 渲染像素。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from annotator.items import ShapeItem

app = QApplication([])
item = ShapeItem((20, 20), (180, 150), shape="rect",
                 border_color="#FF0000", fill_color="#FFFFFF00",
                 line_width=2)
print("shape:", item.shape, "rect:", item.rect())

qimg = QImage(220, 180, QImage.Format.Format_ARGB32)
qimg.fill(QColor("#FFFFFF"))
qp = QPainter(qimg)
item.paint(qp, export=False)
qp.end()
print("center (100,85):", qimg.pixelColor(100, 85).name(QColor.NameFormat.HexArgb))
print("border (100,20):", qimg.pixelColor(100, 20).name(QColor.NameFormat.HexArgb))

item.border_color = QColor(0, 0, 0, 0)
item.fill_color = QColor("#2F80ED")
qimg2 = QImage(220, 180, QImage.Format.Format_ARGB32)
qimg2.fill(QColor("#FFFFFF"))
qp2 = QPainter(qimg2)
item.paint(qp2, export=False)
qp2.end()
print("--- 透明边框+蓝填充 ---")
print("center (100,85):", qimg2.pixelColor(100, 85).name(QColor.NameFormat.HexArgb))
print("border (100,20):", qimg2.pixelColor(100, 20).name(QColor.NameFormat.HexArgb))
os._exit(0)
