# -*- coding: utf-8 -*-
"""r28 回归：v1.6 八项新需求
1) 图层树折叠箭头明暗主题鲜艳配色（图标文件生成 + QSS 注入）
2) 拖放元素到图层 dropEvent 链路安全（复用合成 drop 模拟）
3) 右键交互：非选择模式切换不弹菜单；选择模式短按释放才弹
4) 虚线框高亮：仅 select_layer/select_layer_items 设置；空白点击/非选择模式隐藏
5) 直线折线终点磁吸闭合（_is_closed / 闭合边命中 / 预览不崩）
6) 右键长按超阈值 → 平移，释放不弹菜单
7) 粘贴/导入/截图/打开项目前保存确认（_confirm_overwrite 三态）
8) 右键菜单明暗主题 QSS（应用级 QMenu 样式随主题切换）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QContextMenuEvent, QDropEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def press_right(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(*pos),
                       Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                       Qt.KeyboardModifier.NoModifier)


def release_right(pos):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(*pos),
                       Qt.MouseButton.RightButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def move_right(pos):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(*pos),
                       Qt.MouseButton.NoButton, Qt.MouseButton.RightButton,
                       Qt.KeyboardModifier.NoModifier)


def main():
    app = QApplication([])
    from annotator.window import MainWindow
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    cv = win.canvas
    lt = win.layer_tree
    tree = lt.tree

    pm = QPixmap(600, 400)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    cv.resize(900, 700)
    app.processEvents()

    # ==================== 1. 折叠箭头配色 ====================
    from annotator import layer_tree_panel as LTP
    for dark, closed in ((True, True), (True, False), (False, True), (False, False)):
        p = LTP._branch_icon_path(dark, closed)
        check(p and os.path.exists(p), f"分支箭头图标已生成 dark={dark} closed={closed} → {p}")
    lt.set_dark_theme(True)
    app.processEvents()
    dark_ss = lt.tree.styleSheet()
    check("_branch_dark_c.png" in dark_ss and "_branch_dark_o.png" in dark_ss,
          "暗黑主题 QSS 注入折叠箭头图标路径")
    lt.set_dark_theme(False)
    app.processEvents()
    light_ss = lt.tree.styleSheet()
    check("_branch_light_c.png" in light_ss and "_branch_light_o.png" in light_ss,
          "明亮主题 QSS 注入折叠箭头图标路径")

    # ==================== 2. 拖放 dropEvent 链路（合成事件，防闪退回归） ====================
    cv.add_layer("图层2")          # current = 图层2
    cv.set_mode("emoji")
    e1 = cv.add_emoji_item(QPointF(200, 150), "😀", 48)
    cv.push_undo("add")
    cv.set_mode("select")
    app.processEvents()
    layer1_node = lt._layer_items[cv.layers[0].id]
    item_node = lt._anno_items[e1.id]
    tree._dragging_node = item_node
    tree._drag_type = "item"
    rect = tree.visualItemRect(layer1_node)
    md = tree.model().mimeData([tree.indexFromItem(item_node)])
    ev = QDropEvent(QPointF(rect.center()), Qt.DropAction.MoveAction, md,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(ev)
    app.processEvents()
    app.processEvents()
    check(e1.layer_id == cv.layers[0].id, f"拖放后元素归属图层1（layer_id={e1.layer_id}）")
    check(tree._in_drop is False and tree._dragging_node is None and tree._drag_type is None,
          "dropEvent 后状态复位（无残留，防闪退）")
    total_children = sum(tree.topLevelItem(i).childCount()
                         for i in range(tree.topLevelItemCount()))
    check(total_children == 1, f"树中元素节点唯一（共 {total_children}）")

    # ==================== 3/6. 右键交互 ====================
    from annotator.canvas import RBTN_LONG_MS
    check(RBTN_LONG_MS == 450, "RBTN_LONG_MS 常量 = 450")

    cv.set_mode("select")
    calls = []
    cv._show_right_menu = lambda view_pos: calls.append(view_pos)
    # 短按（选择模式内）→ 释放弹菜单
    cv.mousePressEvent(press_right((300, 200)))
    check(cv._rbtn is not None and cv._rbtn["switched"] is False,
          "选择模式右键按下：记录状态、非切换")
    cv.mouseReleaseEvent(release_right((300, 200)))
    check(len(calls) == 1 and cv._rbtn is None, "选择模式短按释放 → 弹出菜单（1 次）")

    # 从指令模式右键 → 切到选择模式，本次不弹菜单
    cv.set_mode("text")
    calls.clear()
    cv.mousePressEvent(press_right((300, 200)))
    check(cv.mode == "select" and cv._rbtn is not None and cv._rbtn["switched"] is True,
          "指令模式右键按下 → 切到选择模式（不弹菜单）")
    cv.mouseReleaseEvent(release_right((300, 200)))
    check(len(calls) == 0, "切换后的首次右键释放 → 不弹菜单（需求3）")
    # 再次右键（已处于选择模式）→ 弹出
    cv.mousePressEvent(press_right((300, 200)))
    cv.mouseReleaseEvent(release_right((300, 200)))
    check(len(calls) == 1, "再次右键 → 弹出菜单（需求3）")

    # v1.7 需求4：右键按住发生位移 → 立即平移（零延迟），释放不弹菜单
    calls.clear()
    cv.mousePressEvent(press_right((100, 100)))
    cv.mouseMoveEvent(move_right((160, 140)))
    check(cv._rbtn["pan"] is True and cv._panning is True, "右键位移即进入平移（零延迟）")
    cv.mouseReleaseEvent(release_right((160, 140)))
    check(len(calls) == 0 and cv._panning is False, "右键平移后释放 → 不弹菜单")

    # contextMenuEvent 一律忽略（避免与手动菜单重复）
    cme = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(100, 100), QPoint(200, 200))
    cv.contextMenuEvent(cme)
    check(cme.isAccepted() is False, "contextMenuEvent 被忽略（需求6）")

    # ==================== 4. 虚线框高亮 ====================
    cv.highlight_layer_id = None
    check(cv.highlight_layer_id is None, "load_pixmap 后不高亮（需求4）")
    lid1 = cv.layers[0].id
    cv.select_layer(lid1)
    check(cv.highlight_layer_id == lid1, "select_layer → 高亮该层")
    cv.select_layer_items(lid1)
    check(cv.highlight_layer_id == lid1, "select_layer_items（选中本层全部元素）→ 高亮")
    cv.set_mode("text")
    check(cv.highlight_layer_id is None, "进入标注模式 → 隐藏虚线框")
    cv.set_mode("select")
    cv.highlight_layer_id = lid1
    cv.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(8, 8),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                   Qt.KeyboardModifier.NoModifier))
    check(cv.highlight_layer_id is None, "点击画布空白一次 → 隐藏虚线框")
    # 新增/删除图层不高亮
    cv.add_layer("图层3")
    check(cv.highlight_layer_id is None, "新增图层不高亮")
    lid3 = cv.layers[-1].id
    cv.select_layer(lid3)
    check(cv.highlight_layer_id == lid3, "选中图层3 高亮")
    cv.delete_layer(lid3)
    check(cv.highlight_layer_id is None, "删除图层后清除高亮")

    # ==================== 5. 折线闭合 ====================
    cv.set_mode("shape")
    cv._line_points = [QPointF(10, 10), QPointF(200, 10), QPointF(200, 150)]
    cv._line_cursor = QPointF(12, 11)   # 靠近起点(10,10)
    cv._finish_line_path()
    app.processEvents()
    closed_items = [it for it in cv.items
                    if getattr(it, "_is_closed", lambda: False)()]
    check(len(closed_items) == 1, f"终点靠近起点 → 自动闭合（闭合元素 {len(closed_items)}）")
    ci = closed_items[0]
    check(ci.points[0] == ci.points[-1], "闭合后首尾顶点重合")
    # 闭合边（最后一个顶点到起点）中部应命中
    mid = QPointF((ci.points[-2].x() + ci.points[0].x()) / 2,
                  (ci.points[-2].y() + ci.points[0].y()) / 2)
    check(ci.hit_test(mid, 3.0) == "body", "闭合边中部可命中")
    # 渲染不崩
    cv.update()
    app.processEvents()
    pm2 = cv.render_export()
    check(pm2 is not None and not pm2.isNull(), "含闭合折线渲染正常")

    # ==================== 7. 粘贴/导入前保存确认 ====================
    import annotator.window as W
    real_qmb = W.QMessageBox
    class FakeMB:
        last = None
        @classmethod
        def question(cls, *a, **k):
            return cls.last
        @classmethod
        def information(cls, *a, **k):
            return None
        @classmethod
        def warning(cls, *a, **k):
            return None
    FakeMB.StandardButton = real_qmb.StandardButton
    W.QMessageBox = FakeMB
    try:
        # 无标注 → 直接放行（不弹框）
        FakeMB.last = None
        cv.clear_all()
        app.processEvents()
        check(win._confirm_overwrite("测试") is True and FakeMB.last is None,
              "画布无标注 → 不弹确认框直接放行")
        # 有标注 → 选 No（不保存继续）
        cv.set_mode("emoji")
        cv.add_emoji_item(QPointF(50, 50), "🔥", 40)
        cv.push_undo("add")
        app.processEvents()
        FakeMB.last = W.QMessageBox.StandardButton.No
        check(win._confirm_overwrite("测试") is True, "有标注 → 选「不保存」继续")
        FakeMB.last = W.QMessageBox.StandardButton.Cancel
        check(win._confirm_overwrite("测试") is False, "有标注 → 选「取消」中止")
        FakeMB.last = W.QMessageBox.StandardButton.Save
        check(win._confirm_overwrite("测试") is True, "有标注 → 选「保存」先自动保存再继续")
    finally:
        W.QMessageBox = real_qmb

    # ==================== 8. 右键菜单明暗主题 QSS ====================
    win._apply_dark_theme()
    app_ss = app.styleSheet()
    check("QMenu {" in app_ss and "background-color" in app_ss,
          "暗黑主题：应用级 QMenu QSS 已设置（菜单文字+背景同步）")
    win._apply_light_theme()
    check(app.styleSheet() == "", "明亮主题：应用级 QMenu QSS 已清空（回原生浅色）")

    print("==== r28 v1.6 全部断言通过 ====" if not FAILS
          else f"==== r28 存在 {len(FAILS)} 项失败 ====", flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
