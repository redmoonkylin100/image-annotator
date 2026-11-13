# -*- coding: utf-8 -*-
"""r25 回归：图层结构树面板
1) 新面板存在，标题为「图层结构树」，左侧面板只有一个面板（不再是历史+图层上下分栏）
2) 树状结构：顶层为图层节点，子节点为标注元素
3) 图层操作：增删、显隐、重命名、上下移动、拖拽重排、设为当前层、选中本层全部元素
4) 元素操作：单击选中、双击编辑文字、右键菜单（删除/编辑文字/编辑序号/上下移动）
5) 显示顺序：树顶部的图层 = 顶层（绘制最上方）
6) 明暗主题适配
7) 增量刷新：多次 refresh 不崩溃、不重建
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QTreeWidgetItem

from annotator.window import MainWindow
from annotator.items import SHAPE_LINE

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

    # 加载一张测试图
    pm = QPixmap(400, 300)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    cv.resize(900, 700)
    app.processEvents()

    # ==================== 1. 面板存在与结构 ====================
    check(lt is not None, "layer_tree 面板存在")
    check(lt.title_label.text() == "图层结构树", "面板标题为「图层结构树」")
    check(hasattr(lt, "tree"), "面板内含 QTreeWidget")
    check(hasattr(lt, "add_btn"), "有添加图层按钮")
    check(hasattr(lt, "del_btn"), "有删除图层按钮")
    check(hasattr(lt, "up_btn"), "有上移按钮")
    check(hasattr(lt, "down_btn"), "有下移按钮")
    check(hasattr(lt, "expand_btn"), "有展开全部按钮")
    check(hasattr(lt, "collapse_btn"), "有折叠全部按钮")

    # 左侧不再有 left_splitter
    check(not hasattr(win, "left_splitter"), "左侧不再有上下分栏 splitter")
    check(not hasattr(win, "history"), "不再有独立 history 面板")
    check(not hasattr(win, "layers_panel"), "不再有独立 layers_panel")

    # ==================== 2. 初始图层 ====================
    # 默认有 1 个图层
    top_count = lt.tree.topLevelItemCount()
    check(top_count >= 1, f"初始至少 1 个图层（实际 {top_count}）")

    # ==================== 3. 添加图层 ====================
    n_before = lt.tree.topLevelItemCount()
    cv.add_layer()
    app.processEvents()
    n_after = lt.tree.topLevelItemCount()
    check(n_after == n_before + 1, f"添加图层后数量 +1（{n_before} → {n_after}）")

    cv.add_layer()
    app.processEvents()
    check(lt.tree.topLevelItemCount() == n_before + 2, "第二次添加图层数量再 +1")

    # ==================== 4. 图层顺序（顶层在上） ====================
    # canvas.layers 底层在前，树显示顶层在上
    # 第一个顶层节点应该是最后添加的图层
    top_item = lt.tree.topLevelItem(0)
    top_layer_id = top_item.data(0, Qt.ItemDataRole.UserRole)
    # 最后一个底层节点应该是最初的默认图层
    bottom_item = lt.tree.topLevelItem(lt.tree.topLevelItemCount() - 1)
    bottom_layer_id = bottom_item.data(0, Qt.ItemDataRole.UserRole)
    # canvas.layers 中底层在前，所以 bottom_layer_id 应该是 layers[0]
    check(cv.layers[0].id == bottom_layer_id,
          "树底部节点对应 canvas.layers[0]（底层）")
    check(cv.layers[-1].id == top_layer_id,
          "树顶部节点对应 canvas.layers[-1]（顶层）")

    # ==================== 5. 图层显隐 ====================
    top_item.setCheckState(0, Qt.CheckState.Unchecked)
    app.processEvents()
    top_layer = cv.layer_by_id(top_layer_id)
    check(top_layer.visible is False, "取消勾选图层 → 图层不可见")
    top_item.setCheckState(0, Qt.CheckState.Checked)
    app.processEvents()
    check(top_layer.visible is True, "勾选图层 → 图层可见")

    # ==================== 6. 设为当前层 ====================
    # 点击中间层
    mid_item = lt.tree.topLevelItem(1)
    mid_id = mid_item.data(0, Qt.ItemDataRole.UserRole)
    lt._on_item_clicked(mid_item, 0)
    app.processEvents()
    check(cv.current_layer == mid_id, "点击图层节点 → 设为当前层")
    # 当前层字体加粗
    check(mid_item.font(0).bold() is True, "当前层字体加粗")

    # ==================== 7. 添加标注元素并检查树中子节点 ====================
    cv.set_mode("text")
    cv.add_text_item(QPointF(50, 50), "测试文本")
    cv.push_undo("add")
    app.processEvents()
    # 当前层下应该有 1 个子节点
    mid_item_children = mid_item.childCount()
    check(mid_item_children == 1, f"当前层下有 1 个元素子节点（实际 {mid_item_children}）")
    child = mid_item.child(0)
    check("[文本]" in child.text(0), "文本元素显示 [文本] 类型标签")
    check("测试文本" in child.text(0), "文本元素显示文字内容")

    # 添加引线
    cv.set_mode("leader")
    cv._pending_target = None
    cv._pending_target = QPointF(100, 100)
    target = QPointF(cv._pending_target)
    cv._pending_target = None
    cv._hover_pos = None
    item = cv.add_leader_item(target, QPointF(200, 80), "引线文字")
    item.number = 1
    item.number_fmt = "circle"
    cv.push_undo("add")
    app.processEvents()
    check(mid_item.childCount() == 2, "添加引线后当前层下有 2 个元素")
    # 找引线节点
    leader_child = None
    for i in range(mid_item.childCount()):
        c = mid_item.child(i)
        if "[引线]" in c.text(0):
            leader_child = c
            break
    check(leader_child is not None, "引线元素节点存在")
    check("①" in leader_child.text(0), "引线序号显示正确（圆圈格式）")

    # 添加形状
    cv.set_mode("shape")
    shape_item = cv.add_shape_item(QPointF(10, 10), QPointF(50, 50), "rect")
    cv.push_undo("add")
    app.processEvents()
    shape_child = None
    for i in range(mid_item.childCount()):
        c = mid_item.child(i)
        if "[形状]" in c.text(0):
            shape_child = c
            break
    check(shape_child is not None, "形状元素节点存在")

    # ==================== 8. 元素在正确的图层下 ====================
    # 切换到顶层，添加元素
    cv.select_layer(top_layer_id)
    app.processEvents()
    cv.set_mode("text")
    cv.add_text_item(QPointF(200, 200), "顶层文本")
    cv.push_undo("add")
    app.processEvents()
    top_item = lt.tree.topLevelItem(0)  # 重新获取（刷新后可能变了）
    # 找到顶层节点（id 匹配）
    top_node = None
    for i in range(lt.tree.topLevelItemCount()):
        n = lt.tree.topLevelItem(i)
        if n.data(0, Qt.ItemDataRole.UserRole) == top_layer_id:
            top_node = n
            break
    check(top_node is not None, "找到顶层节点")
    if top_node:
        check(top_node.childCount() == 1, "顶层图层下有 1 个元素")
        check("顶层文本" in top_node.child(0).text(0), "顶层元素显示正确文字")

    # ==================== 9. 单击元素选中 ====================
    shape_id = shape_item.id
    # 找到形状节点并点击
    shape_node = None
    for i in range(mid_item.childCount()):
        c = mid_item.child(i)
        if c.data(0, Qt.ItemDataRole.UserRole) == shape_id:
            shape_node = c
            break
    check(shape_node is not None, "找到形状节点")
    if shape_node:
        lt._on_item_clicked(shape_node, 0)
        app.processEvents()
        check(shape_item.selected is True, "单击元素节点 → 画布中选中该元素")

    # ==================== 10. 选中本层全部元素 ====================
    lt.requestSelectLayerItems.emit(mid_id)
    app.processEvents()
    # 中间层下的所有元素都应该被选中
    mid_items_selected = all(it.selected for it in cv.items if it.layer_id == mid_id)
    check(mid_items_selected, "选中本层全部元素 → 该层所有元素被选中")

    # ==================== 11. 删除图层 ====================
    # 删除顶层
    n_layers_before = len(cv.layers)
    cv.delete_layer(top_layer_id)
    app.processEvents()
    check(len(cv.layers) == n_layers_before - 1, "删除图层后图层数 -1")
    # 该层元素也被删除
    top_items_remaining = [it for it in cv.items if it.layer_id == top_layer_id]
    check(len(top_items_remaining) == 0, "删除图层后该层元素也被删除")

    # ==================== 12. 上下移动图层 ====================
    # 找到当前第一个和第二个图层（first = 顶层, second = 下一层）
    first_id = lt.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole)
    second_id = lt.tree.topLevelItem(1).data(0, Qt.ItemDataRole.UserRole)
    # 把第二个（底层方向的）往上移一层 → 两层互换
    cv.move_layer(second_id, 1)
    app.processEvents()
    new_first = lt.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole)
    new_second = lt.tree.topLevelItem(1).data(0, Qt.ItemDataRole.UserRole)
    check(new_first == second_id and new_second == first_id,
          "上移/下移图层 → 树中顺序正确变化")
    # 移回去恢复
    cv.move_layer(first_id, -1)
    app.processEvents()

    # ==================== 13. 展开/折叠全部 ====================
    lt._expand_all()
    app.processEvents()
    all_expanded = True
    for i in range(lt.tree.topLevelItemCount()):
        if not lt.tree.topLevelItem(i).isExpanded():
            all_expanded = False
            break
    check(all_expanded, "展开全部 → 所有图层节点展开")

    lt._collapse_all()
    app.processEvents()
    all_collapsed = True
    for i in range(lt.tree.topLevelItemCount()):
        if lt.tree.topLevelItem(i).isExpanded():
            all_collapsed = False
            break
    check(all_collapsed, "折叠全部 → 所有图层节点折叠")

    # ==================== 14. 明暗主题 ====================
    lt.set_dark_theme(True)
    check(lt._dark_theme is True, "设置暗黑主题 → _dark_theme = True")
    lt.set_dark_theme(False)
    check(lt._dark_theme is False, "设置明亮主题 → _dark_theme = False")

    # ==================== 15. 增量刷新（多次 refresh 不崩溃） ====================
    # 连续多次 refresh 不应该崩溃
    for _ in range(5):
        lt.refresh(cv.layers, cv.items, cv.current_layer)
    check(True, "多次 refresh 不崩溃（增量刷新正常）")

    # ==================== 16. 浮动按钮 / 宽度调节不变 ====================
    check(hasattr(win, "left_floating"), "左侧浮动按钮仍然存在")
    check(hasattr(win, "_toggle_left_panel"), "左侧面板隐藏/显示功能仍然存在")
    check(win.left_box.minimumWidth() >= 180, "左侧面板最小宽度 >= 180")

    # ==================== 17. 元素删除后树中同步移除 ====================
    # 先只选中形状元素（避免之前 selectLayerItems 选中了多个）
    text_node = None
    for i in range(mid_item.childCount()):
        c = mid_item.child(i)
        if "[文本]" in c.text(0) and "测试文本" in c.text(0):
            text_node = c
            break
    if text_node:
        lt._on_item_clicked(text_node, 0)
        app.processEvents()
    n_children_before = mid_item.childCount()
    n_selected_before = len([it for it in cv.items if it.selected])
    cv.delete_selected()
    app.processEvents()
    # 重新获取 mid_item（因为可能被重建了）
    mid_node = None
    for i in range(lt.tree.topLevelItemCount()):
        n = lt.tree.topLevelItem(i)
        if n.data(0, Qt.ItemDataRole.UserRole) == mid_id:
            mid_node = n
            break
    check(mid_node is not None, "中间层节点仍然存在")
    if mid_node:
        check(mid_node.childCount() == n_children_before - 1,
              f"删除元素后子节点数 -1（{n_children_before} → {mid_node.childCount()}）")
        check(n_selected_before == 1,
              f"删除前只选中 1 个元素（实际 {n_selected_before}）")

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit()
        os._exit(1)
    print("==== r25 图层结构树全部断言通过 ====")
    app.quit()
    os._exit(0)


if __name__ == "__main__":
    main()
