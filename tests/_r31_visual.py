# -*- coding: utf-8 -*-
"""r31 可视化探针：渲染工具面板三种摆放位置的主窗口截图，供人工核验。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.window import MainWindow


def _drain(app, n=5):
    for _ in range(n):
        app.processEvents()


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    _drain(app)
    cv = win.canvas
    pm = QPixmap(500, 360)
    pm.fill(QColor("#CFE3FF"))
    cv.load_pixmap(pm)
    cv.add_layer(); cv.add_layer()
    _drain(app)

    shots = [
        ("dock_left", "dock-left"),
        ("inner_left", "inner-left"),
        ("inner_right", "inner-right"),
        ("float", "float"),
        ("top", "top"),
    ]
    outdir = os.path.dirname(os.path.abspath(__file__))
    for name, place in shots:
        win._place_tool(place)
        _drain(app, 5)
        pix = win.grab()
        path = os.path.join(outdir, f"_r31_{name}.png")
        pix.save(path)
        print("saved", path, place, win._tool_place,
              "splitter_count=", win.splitter.count(), flush=True)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
