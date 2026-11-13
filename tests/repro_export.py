# -*- coding: utf-8 -*-
"""复现导出闪退：全部元素类型 + 旋转后元素，走 render_export 并保存各格式。"""
import os, sys, traceback, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QImageWriter
from PyQt6.QtCore import QPointF, QByteArray

app = QApplication([])
from annotator.window import MainWindow
from annotator.items import (ShapeItem, LeaderLineItem, TextItem, EmojiItem,
                             PenItem, HighlightItem, MosaicItem)

win = MainWindow(restore=False)
win.show(); app.processEvents()
cv = win.canvas
cv.load_pixmap(QPixmap(400, 300)); cv.scale = 1.0; cv.offset = QPointF(0, 0)

items = [
    ShapeItem((20, 20), (120, 90), "rect"),
    ShapeItem((130, 120), (200, 200), "ellipse"),
    ShapeItem((210, 210), (300, 280), "line"),
    LeaderLineItem((30, 30), (150, 80), "标签"),
    TextItem((200, 30), "文字"),
    EmojiItem((250, 150), "😀", 40),
    PenItem([QPointF(10, 10), QPointF(60, 80), QPointF(120, 30)]),
    HighlightItem([QPointF(10, 250), QPointF(200, 260)]),
    MosaicItem((300, 200), (380, 280)),
]
# 一半元素带旋转角度
for i, it in enumerate(items):
    it.rotation = 35.0 if i % 2 else 0.0
cv.items = items

td = tempfile.gettempdir()
try:
    img = cv.render_export()
    print("render_export OK", img.width(), img.height(), "isNull=", img.isNull())
    # PNG
    p = os.path.join(td, "ex.png"); print("PNG", img.save(p, "PNG"), os.path.getsize(p))
    # 其余格式走 QImageWriter（与 window.export_image 完全一致）
    for fmt in ("JPG", "BMP", "TIF", "TIFF"):
        p = os.path.join(td, "ex." + fmt.lower())
        writer = QImageWriter(p, QByteArray(fmt.encode("ascii")))
        if fmt == "JPG":
            writer.setQuality(win.panel.jpg_quality_spin.value())
        ok = writer.write(img)
        print(fmt, ok, writer.errorString() if not ok else os.path.getsize(p))
    # GIF 走 Pillow
    print("GIF", win._save_gif(os.path.join(td, "ex.gif")))
    # 直接调 window.export_image（ask_save=False 提前返回，验证前置不崩）
    win.export_image("PNG", ask_save=False)
    print("export_image(ask_save=False) OK")
except Exception:
    traceback.print_exc()
