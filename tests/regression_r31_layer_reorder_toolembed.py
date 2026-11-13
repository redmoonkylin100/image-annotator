# -*- coding: utf-8 -*-
"""r31 回归：
需求1 图层右键「置为顶层 / 置为底层」
需求2 拖拽图层行确定性重排（自由移动相对位置，等价多次上移/下移，绝不嵌套）
需求3 工具面板嵌入左面板右侧 / 右面板左侧独立竖列（菜单切换 + 持久化往返）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QAbstractItemView, QApplication

from annotator.window import MainWindow
from annotator import layer_tree_panel as ltp
from annotator import window as winmod

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


class _FakeDrop:
    """模拟 QDropEvent：只提供 _manual_layer_reorder 用到的 position()。"""
    def __init__(self, x, y):
        self._p = QPointF(x, y)

    def position(self):
        return self._p


class _FakeAction:
    def __init__(self, text, slot):
        self.text = text
        self.slot = slot
        self._enabled = True

    def setEnabled(self, v):
        self._enabled = v


class _FakeMenu:
    """记录右键菜单条目（不真正 exec）。"""
    instances = []

    def __init__(self, *a, **k):
        self.labels = []
        self.actions_map = {}
        _FakeMenu.instances.append(self)

    def addAction(self, text, slot=None):
        self.labels.append(text)
        act = _FakeAction(text, slot)
        self.actions_map[text] = act
        return act

    def addSeparator(self):
        pass

    def addMenu(self, text):
        sub = _FakeMenu()
        sub.labels.append(text)
        return sub

    def setStyleSheet(self, *a, **k):
        pass

    def exec(self, *a, **k):
        pass


def _drain(app, times=3):
    for _ in range(times):
        app.processEvents()


def _layer_ids_bottom_top(canvas):
    return [l.id for l in canvas.layers]


def _tree_top_to_bottom(tree):
    return [tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(tree.topLevelItemCount())]


def main():
    app = QApplication([])
    # 隔离本机 autosave/settings.json：启动不恢复任何历史停靠/分栏状态，
    # 保证初始状态确定（默认停靠最左）
    winmod.settings.load = lambda: {}
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    _drain(app)
    cv = win.canvas
    lt = win.layer_tree

    pm = QPixmap(400, 300)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    _drain(app)

    # 构造 4 个图层：底层在前 [a,b,c,d]，树显示 [d,c,b,a]
    base = list(cv.layers)
    a = base[0].id
    cv.add_layer(); b = cv.layers[-1].id
    cv.add_layer(); c = cv.layers[-1].id
    cv.add_layer(); d = cv.layers[-1].id
    _drain(app)
    check(_layer_ids_bottom_top(cv) == [a, b, c, d],
          f"初始叠放顺序 底→顶 [a,b,c,d]（实际 {_layer_ids_bottom_top(cv)}）")
    check(_tree_top_to_bottom(lt.tree) == [d, c, b, a],
          "树显示顺序 顶→底 [d,c,b,a]")

    # ==================== 需求1：置为顶层 / 置为底层 ====================
    lt._bring_layer_to_edge(a, True)   # 最底层 a 一步到最顶
    _drain(app)
    check(_layer_ids_bottom_top(cv) == [b, c, d, a],
          f"置为顶层：a 到最顶（实际 {_layer_ids_bottom_top(cv)}）")
    check(_tree_top_to_bottom(lt.tree) == [a, d, c, b],
          "置为顶层后树顶行是 a")

    lt._bring_layer_to_edge(a, False)  # a 再一步回最底
    _drain(app)
    check(_layer_ids_bottom_top(cv) == [a, b, c, d],
          f"置为底层：a 回最底（实际 {_layer_ids_bottom_top(cv)}）")

    lt._bring_layer_to_edge(b, True)   # b 到最顶
    _drain(app)
    check(_layer_ids_bottom_top(cv) == [a, c, d, b],
          f"中间层 b 置为顶层（实际 {_layer_ids_bottom_top(cv)}）")
    lt._bring_layer_to_edge(d, False)  # d 到最底
    _drain(app)
    check(_layer_ids_bottom_top(cv) == [d, a, c, b],
          f"中间层 d 置为底层（实际 {_layer_ids_bottom_top(cv)}）")

    # 右键菜单包含两个新动作，且处于边缘时禁用对应项
    orig_menu = ltp.QMenu
    ltp.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    try:
        node_d = lt._layer_items[d]
        lt._on_context_menu(lt.tree.visualItemRect(node_d).center())
    finally:
        ltp.QMenu = orig_menu
    menu = _FakeMenu.instances[-1]
    check("置为顶层" in menu.labels and "置为底层" in menu.labels,
          "图层右键菜单含「置为顶层」「置为底层」")
    # d 已在最底：置为底层应禁用
    check(menu.actions_map["置为底层"]._enabled is False,
          "已在最底层时「置为底层」禁用")
    check(menu.actions_map["置为顶层"]._enabled is True,
          "非顶层时「置为顶层」可用")

    # 恢复标准顺序，便于后续拖拽测试
    cv.apply_layer_order([a, b, c, d])
    _drain(app)

    # ==================== 需求2：拖拽图层行确定性重排 ====================
    tree = lt.tree
    DIP = QAbstractItemView.DropIndicatorPosition

    def drag_layer(src_id, tgt_id, indicator, y_off=0):
        src = lt._layer_items[src_id]
        tgt = lt._layer_items[tgt_id]
        tree._dragging_node = src
        tree._drag_type = ltp._NODE_TYPE_LAYER
        tree.dropIndicatorPosition = lambda: indicator
        r = tree.visualItemRect(tgt)
        ev = _FakeDrop(r.center().x(), r.center().y() + y_off)
        ok = tree._manual_layer_reorder(ev, tgt)
        lt._emit_layer_order_from_tree()
        _drain(app)
        return ok

    # 把最底层 a 拖到 c 的「上方」：树 [d,a,c,b]，叠放 底→顶 [b,c,a,d]
    ok = drag_layer(a, c, DIP.AboveItem)
    check(ok, "拖拽 a 到 c 上方：接受放置")
    check(_tree_top_to_bottom(tree) == [d, a, c, b],
          f"树顺序变为 [d,a,c,b]（实际 {_tree_top_to_bottom(tree)}）")
    check(_layer_ids_bottom_top(cv) == [b, c, a, d],
          f"画布叠放同步为 [b,c,a,d]（实际 {_layer_ids_bottom_top(cv)}）")
    # 关键：没有任何图层被嵌套成子节点
    check(all(tree.topLevelItem(i).parent() is None
              for i in range(tree.topLevelItemCount())),
          "拖拽后所有图层仍是顶层节点（无嵌套）")

    # OnItem + 鼠标落在目标行上半区 = 插到上方；下半区 = 插到下方
    cv.apply_layer_order([a, b, c, d]); _drain(app)
    node_b = lt._layer_items[b]
    rb = tree.visualItemRect(node_b)
    tree._dragging_node = lt._layer_items[d]
    tree._drag_type = ltp._NODE_TYPE_LAYER
    tree.dropIndicatorPosition = lambda: DIP.OnItem
    ev = _FakeDrop(rb.center().x(), rb.top() + 2)   # 上半区
    check(tree._manual_layer_reorder(ev, node_b), "OnItem 上半区放置成功")
    lt._emit_layer_order_from_tree(); _drain(app)
    # 树原 [d,c,b,a]：d 插到 b 之前 → [c,d,b,a]；叠放 → [a,b,d,c]
    check(_tree_top_to_bottom(tree) == [c, d, b, a],
          f"OnItem 上半区=插到上方，树 [c,d,b,a]（实际 {_tree_top_to_bottom(tree)}）")

    cv.apply_layer_order([a, b, c, d]); _drain(app)
    tree._dragging_node = lt._layer_items[d]
    tree._drag_type = ltp._NODE_TYPE_LAYER
    tree.dropIndicatorPosition = lambda: DIP.OnItem
    ev = _FakeDrop(rb.center().x(), rb.bottom() - 2)  # 下半区
    check(tree._manual_layer_reorder(ev, node_b), "OnItem 下半区放置成功")
    lt._emit_layer_order_from_tree(); _drain(app)
    # 树 [d,c,b,a]：d 插到 b 之后 → [c,b,d,a]；叠放 → [a,d,b,c]
    check(_tree_top_to_bottom(tree) == [c, b, d, a],
          f"OnItem 下半区=插到下方，树 [c,b,d,a]（实际 {_tree_top_to_bottom(tree)}）")

    # 拖到元素子行：落到其父图层的相邻位置，且图层不嵌套
    cv.apply_layer_order([a, b, c, d]); _drain(app)
    txt = cv.add_text_item((50, 50), "x")
    txt.layer_id = b
    cv.itemsChanged.emit(); _drain(app)
    child = lt._anno_items[txt.id]
    check(child.parent() is lt._layer_items[b], "元素子节点挂在 b 层下")
    # 把最顶层 d 拖到 b 层元素子行的「下方」→ d 落到 b 之后
    tree._dragging_node = lt._layer_items[d]
    tree._drag_type = ltp._NODE_TYPE_LAYER
    tree.dropIndicatorPosition = lambda: DIP.BelowItem
    ev = _FakeDrop(0, 0)
    check(tree._manual_layer_reorder(ev, child), "拖到元素子行也可放置")
    lt._emit_layer_order_from_tree(); _drain(app)
    # 树 [d,c,b(+child),a]：d 插到 b 之后 → [c,b,d,a]；叠放 → [a,d,b,c]
    check(_tree_top_to_bottom(tree) == [c, b, d, a],
          f"拖到元素子行=插到其父层之后（实际 {_tree_top_to_bottom(tree)}）")
    check(_layer_ids_bottom_top(cv) == [a, d, b, c],
          f"叠放顺序同步为 [a,d,b,c]（实际 {_layer_ids_bottom_top(cv)}）")
    check(all(tree.topLevelItem(i).parent() is None
              for i in range(tree.topLevelItemCount())),
          "经元素子行放置后图层仍无嵌套")
    check(lt._anno_items[txt.id].parent() is lt._layer_items[b],
          "元素归属未被图层拖拽破坏")

    # 拖到空白 = 移到列表最末（树最下方=最底层）
    cv.apply_layer_order([a, b, c, d]); _drain(app)
    tree._dragging_node = lt._layer_items[d]
    tree._drag_type = ltp._NODE_TYPE_LAYER
    tree.dropIndicatorPosition = lambda: DIP.OnViewport
    ev = _FakeDrop(0, 0)
    check(tree._manual_layer_reorder(ev, None), "拖到空白处可放置")
    lt._emit_layer_order_from_tree(); _drain(app)
    # 树 [d,c,b,a]：d 移到末行 → [c,b,a,d]；叠放 → [d,a,b,c]
    check(_tree_top_to_bottom(tree) == [c, b, a, d],
          f"拖到空白处=移到最底（实际 {_tree_top_to_bottom(tree)}）")

    # 连续多次上移的等价性：拖拽一步到位 == 逐次 move_layer
    cv.apply_layer_order([a, b, c, d]); _drain(app)
    # 逐次上移（delta=1 表示向上）三次
    cv.move_layer(a, 1); cv.move_layer(a, 1); cv.move_layer(a, 1)
    stepwise = _layer_ids_bottom_top(cv)
    cv.apply_layer_order([a, b, c, d]); _drain(app)
    # 拖拽：树中原 a 在最底行，拖到 d 的上方
    drag_layer(a, d, DIP.AboveItem)
    drag_once = _layer_ids_bottom_top(cv)
    check(stepwise == drag_once == [b, c, d, a],
          f"拖拽一步到位与三次上移等价（逐步 {stepwise} / 拖拽 {drag_once}）")

    # ==================== 附加：空心弧（openarc）形状修复 ====================
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from annotator.items import shape_path, ShapeItem, SHAPE_OPEN_ARC
    rr = QRectF(30, 40, 200, 200)
    ap = shape_path(SHAPE_OPEN_ARC, rr)
    bb = ap.boundingRect()
    check(rr.adjusted(-1, -1, 1, 1).contains(bb),
          f"空心弧路径完全落在外框内（bbox={round(bb.x(),1)},{round(bb.y(),1)},"
          f"{round(bb.width(),1)}x{round(bb.height(),1)}）")
    e0 = ap.elementAt(0)
    check(not (abs(e0.x) < 1e-6 and abs(e0.y) < 1e-6),
          "空心弧起点不再是 (0,0)（修复空路径 arcTo 拉线到左上角）")
    # 空心弧是封闭环形扇段：环带处可命中，内孔空白处不命中（无填充时）
    arc_item = ShapeItem((rr.left(), rr.top()), (rr.right(), rr.bottom()),
                         shape=SHAPE_OPEN_ARC, border_color="#3040D0",
                         fill_color="#00000000", line_width=2)
    check(arc_item.hit_test(QPointF(rr.left() + 4, rr.center().y()), 4) == "body",
          "空心弧环带（左端）可命中")
    check(arc_item.hit_test(rr.center(), 4) is None,
          "空心弧内孔中心不命中")
    # 直接绘制不异常（canvas.paintEvent 会吞异常，这里无保护暴露问题）
    qimg = QImage(260, 260, QImage.Format.Format_ARGB32)
    qimg.fill(QColor("#FFFFFF"))
    qp = QPainter(qimg)
    arc_item.paint(qp)
    qp.end()
    check(True, "空心弧直接绘制无异常")

    # ==================== 需求3：工具面板嵌入分栏独立列 ====================
    def splitter_order():
        return [win.splitter.widget(i) for i in range(win.splitter.count())]

    check(win._tool_place == "dock-left", "初始工具面板停靠最左")
    check(win.tool_widget.parent() is win.tool_dock, "初始工具内容在 Dock 内")

    win._place_tool("inner-left"); _drain(app)
    order = splitter_order()
    check(win._tool_place == "inner-left", "切换为 inner-left")
    check(order == [win.left_box, win.tool_widget, win.center_box, win.right_box],
          "inner-left：工具列位于左面板与画布之间")
    check(win.tool_widget.maximumWidth() == 38,
          "嵌入列宽度锁定 38")
    check(all(b.parent() is win.tool_widget for b in win.mode_buttons_list),
          "嵌入后所有模式按钮仍在工具列内")

    win._place_tool("inner-right"); _drain(app)
    order = splitter_order()
    check(order == [win.left_box, win.center_box, win.tool_widget, win.right_box],
          "inner-right：工具列位于画布与右面板之间")

    # 右键摆放菜单条目齐全
    orig_qmenu = winmod.QMenu
    winmod.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    try:
        win._show_tool_place_menu(QPointF(0, 0).toPoint())
    finally:
        winmod.QMenu = orig_qmenu
    tmenu = _FakeMenu.instances[-1]
    for label in ("嵌入：左面板右侧（独立竖列）", "嵌入：右面板左侧（独立竖列）",
                  "浮动窗口", "停靠到最右侧"):
        check(label in tmenu.labels, f"摆放菜单含「{label}」")
    check(tmenu.actions_map["嵌入：右面板左侧（独立竖列）"]._enabled is False,
          "当前位置对应的菜单项禁用")

    win._place_tool("float"); _drain(app)
    check(win.tool_dock.isFloating(), "inner-right → 浮动窗口")
    check(win.tool_dock.widget() is win.tool_widget, "浮动时工具内容回到 Dock 内")
    check(win.splitter.count() == 3, "浮动后分栏恢复 3 列")

    win._place_tool("dock-right"); _drain(app)
    check(not win.tool_dock.isFloating(), "浮动 → 停靠最右（不再浮动）")
    check(win.dockWidgetArea(win.tool_dock) == Qt.DockWidgetArea.RightDockWidgetArea,
          "Dock 位于右侧停靠区")
    check(win._tool_place == "dock-right", "状态同步为 dock-right")

    win._place_tool("inner-left"); _drain(app)
    win._place_tool("dock-left"); _drain(app)
    check(win.splitter.count() == 3, "inner-left → dock-left 后分栏恢复 3 列")
    check(splitter_order() == [win.left_box, win.center_box, win.right_box],
          "分栏顺序恢复为 左/中/右")
    check(win.dockWidgetArea(win.tool_dock) == Qt.DockWidgetArea.LeftDockWidgetArea,
          "Dock 回到左侧停靠区")
    check(win.tool_dock.widget() is win.tool_widget, "工具内容重新回到 Dock")

    # 顶部横排往返（验证方向切换不损坏）
    win._place_tool("top"); _drain(app)
    check(win.dockWidgetArea(win.tool_dock) == Qt.DockWidgetArea.TopDockWidgetArea,
          "可停靠顶部（横排）")
    win._place_tool("inner-right"); _drain(app)
    check(splitter_order()[2] is win.tool_widget, "顶部横排 → inner-right 竖列正常")

    # ==================== 需求3：持久化往返 ====================
    data = win._collect_settings()
    check(data.get("tool_place") == "inner-right", "设置中记录 tool_place")
    live_state = bytes(win.splitter.saveState().toBase64()).decode()
    check(data["splitter_state"] != live_state,
          "嵌入期间保存的是干净 3 列分栏状态，而非当前 4 列")
    check(len(data["main_state"]) > 10 and len(data["splitter_state"]) > 10,
          "干净布局状态非空")

    # 用该设置启动第二个窗口，验证自动恢复嵌入
    winmod.settings.load = lambda: data
    win2 = MainWindow(restore=False)
    win2.show(); _drain(app, 8)
    order2 = [win2.splitter.widget(i) for i in range(win2.splitter.count())]
    check(win2._tool_place == "inner-right",
          f"新窗口恢复 tool_place（实际 {win2._tool_place}）")
    check(order2 == [win2.left_box, win2.center_box, win2.tool_widget, win2.right_box],
          "新窗口启动即恢复为 inner-right 独立竖列")
    check(all(b.parent() is win2.tool_widget for b in win2.mode_buttons_list),
          "恢复后模式按钮齐全")

    print()
    if FAILS:
        print(f"==== {len(FAILS)} 项失败 ====")
        for f in FAILS:
            print(" -", f)
        sys.exit(1)
    print("==== r31 全部断言通过 ====")
    sys.exit(0)


if __name__ == "__main__":
    main()
