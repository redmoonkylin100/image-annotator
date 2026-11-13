# -*- coding: utf-8 -*-
"""r26 回归：图层结构树增强
1) 元素可拖拽/右键移动到不同图层
2) 当前层高亮（粗体 + 背景色）
3) 暗黑主题配色优化
4) 图层/元素同级关系（图层不能嵌套，元素不能嵌套元素）
5) move_item_to_layer 画布方法正确
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.window import MainWindow

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    cv = win.canvas
    lt = win.layer_tree

    pm = QPixmap(400, 300)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    cv.resize(900, 700)
    app.processEvents()

    # ==================== 1. move_item_to_layer 画布方法 ====================
    # 创建两个图层
    layer0_id = cv.layers[0].id
    cv.add_layer("图层2")
    app.processEvents()
    layer1_id = cv.layers[-1].id

    # 在 layer0 添加一个文本元素
    cv.select_layer(layer0_id)
    app.processEvents()
    cv.set_mode("text")
    text_item = cv.add_text_item(QPointF(50, 50), "测试文本")
    cv.push_undo("add")
    app.processEvents()

    check(text_item.layer_id == layer0_id, "初始元素在 layer0")

    # 移动到 layer1
    cv.move_item_to_layer(text_item.id, layer1_id)
    app.processEvents()
    check(text_item.layer_id == layer1_id, "move_item_to_layer 后元素在 layer1")

    # 检查树中位置
    layer1_node = lt._layer_items.get(layer1_id)
    check(layer1_node is not None, "找到 layer1 节点")
    if layer1_node:
        found = False
        for i in range(layer1_node.childCount()):
            c = layer1_node.child(i)
            if c.data(0, Qt.ItemDataRole.UserRole) == text_item.id:
                found = True
                break
        check(found, "元素在树中显示在目标图层下")

    # layer0 下应该没有了
    layer0_node = lt._layer_items.get(layer0_id)
    if layer0_node:
        has_text = False
        for i in range(layer0_node.childCount()):
            c = layer0_node.child(i)
            if c.data(0, Qt.ItemDataRole.UserRole) == text_item.id:
                has_text = True
                break
        check(not has_text, "原图层下不再有该元素")

    # 移动到不存在的图层应该无操作
    orig_layer = text_item.layer_id
    cv.move_item_to_layer(text_item.id, 99999)
    app.processEvents()
    check(text_item.layer_id == orig_layer, "移动到不存在的图层无操作")

    # 移动到当前图层应该无操作
    cv.move_item_to_layer(text_item.id, text_item.layer_id)
    app.processEvents()
    check(True, "移动到当前图层无操作（不报错）")

    # ==================== 2. 当前层高亮（背景色 + 粗体） ====================
    cv.select_layer(layer0_id)
    app.processEvents()
    node0 = lt._layer_items.get(layer0_id)
    node1 = lt._layer_items.get(layer1_id)
    check(node0.font(0).bold() is True, "当前层字体加粗")
    check(node1.font(0).bold() is False, "非当前层不加粗")

    # 明亮主题下当前层背景色（显式切明亮并刷新，避免上次运行残留暗黑设置）
    lt.set_dark_theme(False)
    lt.refresh(cv.layers, cv.items, cv.current_layer)
    app.processEvents()
    node0 = lt._layer_items.get(layer0_id)
    bg0 = node0.background(0).color()
    check(bg0.red() > 200 and bg0.green() > 220 and bg0.blue() > 240,
          f"明亮主题当前层背景为淡蓝色（R={bg0.red()},G={bg0.green()},B={bg0.blue()}）")

    # 暗黑主题下当前层背景色
    lt.set_dark_theme(True)
    app.processEvents()
    bg0_dark = node0.background(0).color()
    check(bg0_dark.red() < 100 and bg0_dark.green() < 100 and bg0_dark.blue() > 60,
          f"暗黑主题当前层背景为深蓝色（R={bg0_dark.red()},G={bg0_dark.green()},B={bg0_dark.blue()}）")
    lt.set_dark_theme(False)
    app.processEvents()

    # ==================== 3. 右键「移动到图层」子菜单 ====================
    # 触发右键菜单获取菜单项（间接测试：验证信号存在且能连接）
    check(hasattr(lt, "requestMoveItemToLayer"),
          "面板有 requestMoveItemToLayer 信号")
    check(lt.requestMoveItemToLayer is not None,
          "requestMoveItemToLayer 信号可用")

    # 通过 window 调用移动
    win._move_item_to_layer(text_item.id, layer0_id)
    app.processEvents()
    check(text_item.layer_id == layer0_id,
          "通过 window._move_item_to_layer 移动元素成功")

    # ==================== 4. 暗黑主题样式 ====================
    lt.set_dark_theme(True)
    ss = lt.tree.styleSheet()
    check("#252535" in ss, "暗黑主题背景色 #252535")
    check("#3a7bd5" in ss, "暗黑主题选中色 #3a7bd5")
    check("font-size: 12px" in ss, "暗黑主题字体大小 12px")
    lt.set_dark_theme(False)
    ss_light = lt.tree.styleSheet()
    check("#FFFFFF" in ss_light, "明亮主题背景白色")
    check("#2f6fed" in ss_light, "明亮主题选中色 #2f6fed")

    # ==================== 5. 同级关系验证 ====================
    # 所有顶层节点都是图层类型
    all_layers = True
    for i in range(lt.tree.topLevelItemCount()):
        n = lt.tree.topLevelItem(i)
        if n.data(0, Qt.ItemDataRole.UserRole + 1) != "layer":
            all_layers = False
            break
    check(all_layers, "顶层节点全部为图层类型（无元素嵌套到顶层）")

    # 所有元素节点的父节点都是图层类型
    all_items_have_layer_parent = True
    for iid, node in lt._anno_items.items():
        parent = node.parent()
        if parent is None:
            all_items_have_layer_parent = False
            break
        if parent.data(0, Qt.ItemDataRole.UserRole + 1) != "layer":
            all_items_have_layer_parent = False
            break
    check(all_items_have_layer_parent, "所有元素节点的父节点都是图层类型")

    # 元素节点没有子节点（同级关系）
    no_nested_items = True
    for iid, node in lt._anno_items.items():
        if node.childCount() > 0:
            no_nested_items = False
            break
    check(no_nested_items, "元素节点没有子节点（元素同级）")

    # ==================== 6. 选中元素时自动展开父图层 ====================
    # 先折叠所有图层
    lt._collapse_all()
    app.processEvents()
    # 选中文本元素
    for it in cv.items:
        it.selected = False
    text_item.selected = True
    cv.itemSelectionChanged.emit()
    app.processEvents()
    # 检查该元素所在图层是否展开
    parent_expanded = False
    node = lt._anno_items.get(text_item.id)
    if node is not None:
        parent = node.parent()
        if parent is not None and parent.isExpanded():
            parent_expanded = True
    check(parent_expanded, "选中元素时自动展开其父图层")

    # ==================== 7. 无元素选中时选中当前图层节点 ====================
    for it in cv.items:
        it.selected = False
    cv.itemSelectionChanged.emit()
    app.processEvents()
    current_item = lt.tree.currentItem()
    check(current_item is not None, "无元素选中时树有当前项")
    if current_item:
        check(current_item.data(0, Qt.ItemDataRole.UserRole + 1) == "layer",
              "无元素选中时当前项为图层节点")
        check(current_item.data(0, Qt.ItemDataRole.UserRole) == cv.current_layer,
              "无元素选中时当前项为当前图层")

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit()
        os._exit(1)
    print("==== r26 图层结构树增强全部断言通过 ====")
    app.quit()
    os._exit(0)


if __name__ == "__main__":
    main()
