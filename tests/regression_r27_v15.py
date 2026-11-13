# -*- coding: utf-8 -*-
"""r27 回归：v1.5 优化项
1) 关于按钮（版本 1.5 / 作者 redmoonk / 版权 bk100）+ 窗口标题
2) 选择模式右键分类菜单（元素操作/工具/编辑/画布）
3) 复制(克隆)元素：同层、偏移、选中副本；重复上一次命令
4) 元素唯一性：deduplicate_items 清理重复表情；树中绝不重复显示
5) 拖放闪退修复：拖放期间 refresh 挂起、结束后补刷；图层拖拽重排信号延迟
6) 当前层始终醒目：▶ 标记 + 加粗 + 橙色前景
7) 元素节点按类型着色（明暗两套）
8) 图层上移/下移按钮（修复 _current_layer_id 属性/方法冲突）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu

from annotator.window import MainWindow
from annotator.canvas import MODE_SELECT, MODE_TEXT, MODE_EMOJI

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def find_submenu(menu, title):
    for a in menu.actions():
        if a.menu() is not None and a.text() == title:
            return a.menu()
    return None


def find_action(menu, text):
    for a in menu.actions():
        if a.text() == text:
            return a
    return None


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

    # ==================== 1. 关于按钮 ====================
    check(hasattr(win, "about_btn"), "工具栏有关于按钮")
    check(win.about_btn.text() == "关于", "关于按钮文字为「关于」")
    check(win.about_btn.receivers(win.about_btn.clicked) > 0, "关于按钮已接线")
    check("v1.7" in win.windowTitle(), f"窗口标题含版本 v1.7（{win.windowTitle()}）")
    # 关于对话框内容包含版本/作者/版权（不弹窗：直接检查文本方法）
    import annotator.window as _wm
    orig_about = _wm.QMessageBox.about
    captured = []
    _wm.QMessageBox.about = lambda parent, title, text: captured.append((title, text))
    try:
        win._show_about()
    finally:
        _wm.QMessageBox.about = orig_about
    check(len(captured) == 1, "关于对话框已触发")
    if captured:
        title, text = captured[0]
        check("v1.7" in title, "关于标题含版本 1.7")
        check("redmoonk" in text, "关于内容含作者 redmoonk")
        check("bk100" in text, "关于内容含版权 bk100")

    # ==================== 2. 选择模式右键分类菜单 ====================
    cv.set_mode(MODE_SELECT)
    cv.set_mode(MODE_TEXT)
    item = cv.add_text_item(QPointF(50, 50), "右键目标文本")
    cv.push_undo("add")
    cv.set_mode(MODE_SELECT)
    app.processEvents()

    menu_hit = cv._build_context_menu(QPointF(50, 50))
    check(menu_hit is not None, "命中元素时构建出右键菜单")
    check(find_action(menu_hit, "编辑文字…") is not None, "菜单含「编辑文字…」")
    check(find_action(menu_hit, "复制(克隆)") is not None, "菜单含「复制(克隆)」")
    check(find_action(menu_hit, "删除") is not None, "菜单含「删除」")
    check(find_submenu(menu_hit, "移动到图层") is not None, "菜单含「移动到图层」子菜单")
    check(find_submenu(menu_hit, "工具") is not None, "菜单含「工具」子菜单")
    tool_menu = find_submenu(menu_hit, "工具")
    if tool_menu:
        texts = [a.text() for a in tool_menu.actions()]
        check("选择" in texts and "表情" in texts and "自由截图" in texts,
              "工具子菜单含各模式与自由截图")
    check(find_submenu(menu_hit, "编辑") is not None, "菜单含「编辑」子菜单")
    edit_menu = find_submenu(menu_hit, "编辑")
    if edit_menu:
        et = [a.text() for a in edit_menu.actions()]
        check("撤销" in et and "重做" in et and "重复上一次命令" in et
              and "确认当前操作" in et, "编辑子菜单含撤销/重做/重复命令/确认")
    check(find_submenu(menu_hit, "画布") is not None, "菜单含「画布」子菜单")
    canvas_menu = find_submenu(menu_hit, "画布")
    if canvas_menu:
        ct = [a.text() for a in canvas_menu.actions()]
        check("复制标注图" in ct and "清空画布" in ct, "画布子菜单含复制/清空")

    menu_empty = cv._build_context_menu(QPointF(399, 299))
    check(find_action(menu_empty, "删除") is None, "空白处右键不含元素操作")
    check(find_submenu(menu_empty, "工具") is not None, "空白处右键仍有工具子菜单")

    # ==================== 3. 复制（克隆）与重复上一次命令 ====================
    n_before = len(cv.items)
    cv.select_item_by_id(item.id)
    dup = cv.duplicate_selected()
    app.processEvents()
    check(dup is not None, "复制(克隆)成功")
    check(len(cv.items) == n_before + 1, "复制后元素 +1")
    check(dup.layer_id == item.layer_id, "副本在同图层")
    check(dup.selected is True and item.selected is False, "副本被选中、原件取消")
    check(dup.pos.x() != item.pos.x(), "副本已偏移（不与原件完全重叠）")
    # 重复上一次命令 = 再复制一次
    cv.repeat_last_command()
    app.processEvents()
    check(len(cv.items) == n_before + 2, "重复上一次命令（复制）→ 再复制一个")
    # 树中数量与画布一致（无重复显示）
    lt.refresh(cv.layers, cv.items, cv.current_layer)
    app.processEvents()
    total_nodes = sum(lt.tree.topLevelItem(i).childCount()
                      for i in range(lt.tree.topLevelItemCount()))
    check(total_nodes == len(cv.items), f"树中元素节点数与画布一致（{total_nodes}/{len(cv.items)}）")

    # ==================== 4. 元素唯一性（去重） ====================
    cv.set_mode(MODE_EMOJI)
    e1 = cv.add_emoji_item(QPointF(200, 200), "😀", 40)
    e2 = cv.add_emoji_item(QPointF(200, 200), "😀", 40)   # 完全重叠的重复表情
    e3 = cv.add_emoji_item(QPointF(210, 200), "😀", 40)   # 略有偏移：保留
    cv.push_undo("add")
    cv.set_mode(MODE_SELECT)
    n_dup_before = len(cv.items)
    removed = cv.deduplicate_items()
    app.processEvents()
    check(removed == 1, f"去重清理 1 个完全重叠的重复表情（移除 {removed}）")
    check(len(cv.items) == n_dup_before - 1, "去重后元素数量 -1")
    check(e3 in cv.items, "略有偏移的表情保留")

    # 树中绝不重复显示：即使 items 里有同 id 副本，树也只显示一个
    dup_id_item = cv.add_text_item(QPointF(300, 100), "同ID副本")
    cv.items.append(dup_id_item)   # 人为制造重复
    lt.refresh(cv.layers, cv.items, cv.current_layer)
    app.processEvents()
    node_count = 0
    for i in range(lt.tree.topLevelItemCount()):
        layer_node = lt.tree.topLevelItem(i)
        for j in range(layer_node.childCount()):
            if layer_node.child(j).data(0, Qt.ItemDataRole.UserRole) == dup_id_item.id:
                node_count += 1
    check(node_count == 1, "同 id 元素在树中只显示一个节点")

    # ==================== 5. 拖放闪退修复 ====================
    # 拖放期间（_in_drop=True）refresh 必须挂起而不是修改树
    lt.tree._in_drop = True
    lt.refresh(cv.layers, cv.items, cv.current_layer)
    check(lt._pending_refresh is not None, "拖放期间 refresh 被挂起")
    check(lt._syncing is False, "挂起时未进入树刷新（不修改树）")
    lt.tree._in_drop = False
    lt._on_tree_drop_finished()
    app.processEvents()
    check(lt._pending_refresh is None, "拖放结束后补刷完成（挂起清除）")
    # 图层拖拽重排请求仍能正常触发（延迟发射路径存在）
    check(hasattr(lt, "requestReorder"), "图层重排信号存在")
    check(lt.tree.dropFinished is not None, "dropFinished 信号可用")

    # ==================== 6. 当前层始终醒目 ====================
    first_id = cv.layers[0].id
    cv.select_layer(first_id)
    app.processEvents()
    node0 = lt._layer_items.get(first_id)
    check(node0 is not None, "找到当前层节点")
    if node0:
        check(node0.text(0).startswith("▶"), f"当前层带 ▶ 标记（{node0.text(0)!r}）")
        check(node0.font(0).bold(), "当前层加粗")
        fg = node0.foreground(0).color()
        check(fg.red() > 150 and fg.blue() < 200
              and (fg.red() - fg.blue()) > 80,
              f"当前层橙色前景（醒目 R={fg.red()},G={fg.green()},B={fg.blue()}）")
    # 明亮主题同样标记
    lt.set_dark_theme(False)
    app.processEvents()
    node0 = lt._layer_items.get(first_id)
    if node0:
        check(node0.text(0).startswith("▶"), "明亮主题当前层同样带 ▶ 标记")

    # ==================== 7. 元素节点按类型着色 ====================
    lt.set_dark_theme(False)
    app.processEvents()
    text_node = lt._anno_items.get(item.id)
    if text_node:
        c = text_node.foreground(0).color()
        check(c.green() > c.red() and c.green() > c.blue(),
              f"文本节点绿色前景（R={c.red()},G={c.green()},B={c.blue()}）")
    lt.set_dark_theme(True)
    app.processEvents()
    text_node = lt._anno_items.get(item.id)
    if text_node:
        c = text_node.foreground(0).color()
        check(c.green() > c.red() and c.green() > c.blue(),
              "暗黑主题文本节点仍为绿色前景")

    # ==================== 8. 图层上移/下移按钮（修复冲突） ====================
    cv.add_layer()
    app.processEvents()
    layers_before = [l.id for l in cv.layers]
    # 选中最后添加的图层（位于顶部），点下移
    top_id = lt.tree.topLevelItem(0).data(0, Qt.ItemDataRole.UserRole)
    lt.tree.setCurrentItem(lt.tree.topLevelItem(0))
    lt._move_current(1)   # 下移一层
    app.processEvents()
    layers_after = [l.id for l in cv.layers]
    check(layers_after[0] != top_id, "图层下移按钮生效（不崩溃）")
    # 再点一次上移恢复
    lt.tree.setCurrentItem(lt.tree.topLevelItem(0))
    lt._move_current(-1)
    app.processEvents()
    layers_restored = [l.id for l in cv.layers]
    check(layers_restored[0] == top_id, "图层上移按钮生效（恢复原顺序）")

    # ==================== 9. 状态栏消息接线 ====================
    win.canvas.statusMessage.emit("测试提示")
    app.processEvents()
    check(win.status.currentMessage() == "测试提示", "状态栏消息接线正常")

    # ==================== 10. 确认当前操作 ====================
    cv.set_mode(MODE_TEXT)
    cv.start_inline_editor(QPointF(80, 80),
                           lambda content: cv._finish_text(QPointF(80, 80), content))
    app.processEvents()
    check(cv._editor.isVisible(), "就地输入框已显示")
    cv._editor.setText("确认测试")
    cv.confirm_current()
    app.processEvents()
    check(any(it.text_content == "确认测试" for it in cv.items),
          "「确认当前操作」确认了输入框文字")

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit()
        os._exit(1)
    print("==== r27 v1.5 全部断言通过 ====")
    app.quit()
    os._exit(0)


if __name__ == "__main__":
    main()
