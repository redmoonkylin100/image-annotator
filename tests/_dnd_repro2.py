# -*- coding: utf-8 -*-
"""原生风格拖放模拟：QDrag.exec 运行中注入 dragEnter/dragMove/drop 事件。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QMimeData, QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QDrag, QDropEvent, QPixmap
from PyQt6.QtWidgets import QApplication


def main() -> int:
    app = QApplication([])
    from annotator.window import MainWindow
    win = MainWindow(restore=False)
    win.resize(1200, 780)
    win.show()
    app.processEvents()
    cv = win.canvas
    lt = win.layer_tree
    tree = lt.tree

    pm = QPixmap(600, 400)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    app.processEvents()
    cv.add_layer("图层2")
    cv.set_mode("emoji")
    e1 = cv.add_emoji_item(QPointF(200, 150), "😀", 48)
    cv.push_undo("add")
    cv.set_mode("select")
    app.processEvents()

    layer1_node = lt._layer_items[cv.layers[0].id]
    item_node = lt._anno_items[e1.id]
    target_rect = tree.visualItemRect(layer1_node)
    target_center = target_rect.center()
    print("拖前 e1.layer_id =", e1.layer_id, flush=True)

    md = tree.model().mimeData([tree.indexFromItem(item_node)])

    def inject():
        # dragEnter + 两次 dragMove + drop
        for _ in range(2):
            evm = QDragMoveEvent(QPointF(target_center), Qt.DropAction.MoveAction,
                                 md, Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(tree, evm)
        evd = QDropEvent(QPointF(target_center), Qt.DropAction.MoveAction,
                         md, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree, evd)

    QTimer.singleShot(100, inject)
    try:
        drag = QDrag(tree)
        drag.setMimeData(md)
        pm2 = QPixmap(16, 16)
        pm2.fill(QColor(0, 0, 0, 0))
        drag.setPixmap(pm2)
        drag.exec(Qt.DropAction.MoveAction)
    except Exception as exc:
        print("drag exc:", exc, flush=True)
    app.processEvents()
    app.processEvents()
    print("拖后 e1.layer_id =", e1.layer_id, flush=True)
    print("DND2-OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
