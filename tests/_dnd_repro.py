# -*- coding: utf-8 -*-
"""复现：拖动元素节点到另一个图层节点（真实 dropEvent 链路）是否会闪退/报错。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QDropEvent, QPixmap
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

    cv.add_layer("图层2")          # current = 图层2
    cv.set_mode("emoji")
    e1 = cv.add_emoji_item(QPointF(200, 150), "😀", 48)
    cv.push_undo("add")
    cv.set_mode("select")
    app.processEvents()

    # 把 e1 从图层2 拖到图层1
    layer1_node = lt._layer_items[cv.layers[0].id]
    item_node = lt._anno_items[e1.id]
    print("拖前 e1.layer_id =", e1.layer_id, "节点父层 =",
          item_node.parent().data(0, Qt.ItemDataRole.UserRole) if item_node.parent() else None,
          flush=True)

    # 模拟拖放：设置 _dragging_node，然后直接向树发 QDropEvent
    tree._dragging_node = item_node
    tree._drag_type = "item"
    rect = tree.visualItemRect(layer1_node)
    pos = QPointF(rect.center())
    md = tree.model().mimeData([tree.indexFromItem(item_node)])
    ev = QDropEvent(pos, Qt.DropAction.MoveAction, md,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(ev)
    print("dropEvent 返回，_in_drop =", tree._in_drop, flush=True)
    app.processEvents()      # 让 singleShot(itemMovedToLayer) 执行
    app.processEvents()
    print("拖后 e1.layer_id =", e1.layer_id, flush=True)
    print("树中节点数：", sum(
        lt.tree.topLevelItem(i).childCount()
        for i in range(lt.tree.topLevelItemCount())), flush=True)
    print("DND-OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
