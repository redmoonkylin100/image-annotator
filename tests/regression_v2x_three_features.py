# -*- coding: utf-8 -*-
"""v2.x 三需求回归：
需求1 右侧面板：形状边线/填充颜色均可设为「透明」（即隐藏），引线标注除外
需求2 选择模式右键菜单顶部新增「重复上次标注」：快速恢复最近一次标注指令
      （只重复工具面板中的标注指令，与「重复上一次命令」不同，不含删除/复制等）
需求3 左侧结构树空白处右键：新增层 / 折叠层 / 展开层；
      「复制层」位于图层节点右键菜单，复制被选中的图层（含全部元素）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.window import MainWindow
from annotator import window as winmod
from annotator import canvas as canvasmod
from annotator import panel as panelmod
from annotator import layer_tree_panel as ltp
from annotator.items import MosaicItem, ShapeItem

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


class _FakeSignal:
    def connect(self, *a, **k):
        pass


class _FakeAction:
    def __init__(self, text, slot):
        self.text = text
        self.slot = slot
        self._enabled = True
        self._checked = False
        self.triggered = _FakeSignal()

    def setEnabled(self, v):
        self._enabled = v

    def setCheckable(self, v):
        pass

    def setChecked(self, v):
        self._checked = v


class _FakeMenu:
    """记录右键菜单条目（不真正 exec）。"""
    instances = []

    def __init__(self, *a, **k):
        self.labels = []
        self.actions_map = {}
        _FakeMenu.instances.append(self)

    def addAction(self, text, slot=None, slot2=None):
        # QMenu.addAction 两种重载：(text, slot) 或 (text, shortcut, slot)
        if slot2 is not None:
            slot = slot2
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


def _bottom_layer_ids(cv):
    return [l.id for l in cv.layers]


def main():
    app = QApplication([])
    # 隔离本机 autosave/settings.json：不恢复任何历史状态，保证初始确定
    winmod.settings.load = lambda: {}
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    _drain(app)
    cv = win.canvas
    lt = win.layer_tree
    pn = win.panel

    pm = QPixmap(400, 300)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    _drain(app)

    # ==================== 需求1：形状边线/填充「透明」 ====================
    check(hasattr(pn, "shape_border_trans_check")
          and hasattr(pn, "shape_fill_trans_check"),
          "形状设置组含「透明」复选框（边线/填充）")
    # 默认值：边线红色不透明、填充透明
    bc = pn.shape_border_color()
    fc = pn.shape_fill_color()
    check(bc.alpha() == 255 and bc.red() == 255, "默认边线不透明红色")
    check(fc.alpha() == 0, "默认填充透明（alpha=0）")

    # 勾选「透明」→ 颜色 alpha 置 0；取消 → 恢复
    pn.shape_border_trans_check.setChecked(True)
    check(pn.shape_border_color().alpha() == 0,
          "勾选边线「透明」→ border alpha=0")
    pn.shape_border_trans_check.setChecked(False)
    check(pn.shape_border_color().alpha() == 255,
          "取消边线「透明」→ 恢复不透明")
    pn.shape_fill_trans_check.setChecked(True)
    check(pn.shape_fill_color().alpha() == 0,
          "勾选填充「透明」→ fill alpha=0")

    # 经面板样式创建形状：透明边线/填充生效
    pn.shape_border_trans_check.setChecked(True)
    cv.set_mode(canvasmod.MODE_SHAPE)
    st = pn.current_style()
    item_t = cv.add_shape_item(QPointF(10, 10), QPointF(110, 80),
                               st["shape_type"])
    check(item_t.border_color.alpha() == 0 and item_t.fill_color.alpha() == 0,
          "新建形状（边线透明勾选）border/fill 均为透明")

    # 取消透明并选色 → 新形状使用所选颜色
    pn.shape_border_trans_check.setChecked(False)
    pn.shape_fill_trans_check.setChecked(False)
    pn.shape_border_btn._color = QColor("#00AA00")
    pn.shape_fill_btn._color = QColor("#3366FF")
    pn._refresh_color_buttons()
    st = pn.current_style()
    item_v = cv.add_shape_item(QPointF(20, 20), QPointF(90, 70),
                               st["shape_type"])
    check(item_v.border_color.name() == "#00aa00"
          and item_v.fill_color.name() == "#3366ff",
          "取消透明后新形状使用所选边线/填充颜色")

    # 选中元素回填：透明 → 勾选；非透明 → 不勾选且按钮保留颜色
    pn.sync_from_selection([item_t])
    check(pn.shape_border_trans_check.isChecked()
          and pn.shape_fill_trans_check.isChecked(),
          "选中透明边线/填充形状 → 两个「透明」勾选")
    check(pn.shape_border_btn._color.alpha() != 0
          and pn.shape_fill_btn._color.alpha() != 0,
          "透明态下按钮仍保留上次非透明颜色（可取消恢复）")
    pn.sync_from_selection([item_v])
    check(not pn.shape_border_trans_check.isChecked()
          and not pn.shape_fill_trans_check.isChecked(),
          "选中非透明形状 → 「透明」不勾选")

    # 设置恢复：透明颜色 → 勾选
    pn.set_style({"shape_border_color": QColor(0, 0, 0, 0),
                  "shape_fill_color": QColor(255, 0, 0, 0)})
    check(pn.shape_border_trans_check.isChecked()
          and pn.shape_fill_trans_check.isChecked(),
          "set_style 恢复透明色 → 勾选「透明」")
    pn.set_style({"shape_border_color": QColor("#123456")})
    check(not pn.shape_border_trans_check.isChecked(),
          "set_style 恢复非透明色 → 取消勾选")

    # 用户取色 → 自动取消透明并回填
    _orig_get = panelmod.QColorDialog.getColor
    panelmod.QColorDialog.getColor = lambda *a, **k: QColor("#FFAA00")
    try:
        pn._pick_color("shape_border")
    finally:
        panelmod.QColorDialog.getColor = _orig_get
    check(not pn.shape_border_trans_check.isChecked()
          and pn.shape_border_btn._color.name() == "#ffaa00",
          "取色后取消「透明」并回填新颜色")

    # 含透明边框/填充形状导出渲染不崩溃
    try:
        cv.render_export()
        _ok = True
    except Exception:
        _ok = False
    check(_ok, "含透明边线/填充形状的导出渲染正常")

    # 引线标注样式不受影响（line_color 仍是实体颜色）
    check(pn.line_color().alpha() == 255, "引线颜色不受透明设置影响")

    # ==================== 需求2：重复上次标注 ====================
    # 启动默认进入引线模式，可能已记录；这里模拟「从未使用标注指令」
    cv._last_annotation_mode = None
    check(cv._last_annotation_mode is None, "初始无最近标注指令")
    cv.set_mode(canvasmod.MODE_SELECT)
    check(cv._last_annotation_mode is None, "选择模式不记录标注指令")
    cv.set_mode(canvasmod.MODE_LEADER)
    check(cv._last_annotation_mode == canvasmod.MODE_LEADER,
          "进入引线标注 → 记录")
    cv.set_mode(canvasmod.MODE_MOSAIC)
    check(cv._last_annotation_mode == canvasmod.MODE_MOSAIC,
          "进入马赛克 → 更新记录")
    cv.set_mode(canvasmod.MODE_SELECT)

    orig_menu = canvasmod.QMenu
    canvasmod.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    try:
        menu = cv._build_context_menu(QPointF(200, 150))
    finally:
        canvasmod.QMenu = orig_menu
    check(menu.labels[0] == "重复上次标注",
          f"右键菜单首项为「重复上次标注」（实际 {menu.labels[0]}）")
    check(menu.actions_map["重复上次标注"]._enabled,
          "有最近标注指令时「重复上次标注」可用")

    cv.repeat_last_annotation()
    check(cv.mode == canvasmod.MODE_MOSAIC,
          "重复上次标注 → 切回最近标注指令（马赛克）")

    # 无记录时禁用 + 状态提示
    cv._last_annotation_mode = None
    cv.set_mode(canvasmod.MODE_SELECT)
    canvasmod.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    try:
        menu2 = cv._build_context_menu(QPointF(200, 150))
    finally:
        canvasmod.QMenu = orig_menu
    check(not menu2.actions_map["重复上次标注"]._enabled,
          "无最近标注指令时「重复上次标注」禁用")
    _msgs = []
    cv.statusMessage.connect(lambda m: _msgs.append(m))
    cv.repeat_last_annotation()
    check(any("无可重复" in m for m in _msgs),
          "无记录时提示「暂无可重复的标注指令」")

    # ==================== 需求3：图层树空白右键 + 复制层 ====================
    base_id = cv.layers[0].id
    cv.add_layer()
    l2 = cv.layers[-1].id
    cv.select_layer(l2)
    t1 = cv.add_text_item(QPointF(30, 30), "层2文本")
    cv.add_shape_item(QPointF(60, 60), QPointF(160, 120), "rect")
    m1 = MosaicItem((10, 10), (40, 40), block_size=8)
    m1.layer_id = l2
    cv.items.append(m1)
    cv.itemsChanged.emit()
    _drain(app)

    # 空白处右键菜单（复制层已移至图层节点右键）
    orig_lmenu = ltp.QMenu
    ltp.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    try:
        last_node = lt.tree.topLevelItem(lt.tree.topLevelItemCount() - 1)
        pt = QPoint(5, int(lt.tree.visualItemRect(last_node).bottom()) + 60)
        check(lt.tree.itemAt(pt) is None, "右键点位于空白处（无节点命中）")
        lt._on_context_menu(pt)
    finally:
        ltp.QMenu = orig_lmenu
    bmenu = _FakeMenu.instances[-1]
    for _label in ("新增层", "折叠层", "展开层"):
        check(_label in bmenu.labels,
              f"空白右键菜单含「{_label}」")
    check("复制层" not in bmenu.labels,
          "空白右键菜单不再含「复制层」（已移至图层节点右键）")

    # 图层节点右键菜单：含「复制层」，触发后复制该选中图层
    ltp.QMenu = _FakeMenu
    _FakeMenu.instances.clear()
    node_l2 = lt._layer_items[l2]
    try:
        lt._on_context_menu(lt.tree.visualItemRect(node_l2).center())
    finally:
        ltp.QMenu = orig_lmenu
    lmenu = _FakeMenu.instances[-1]
    check("复制层" in lmenu.labels, "图层节点右键菜单含「复制层」")
    check("删除图层" in lmenu.labels, "图层节点右键菜单仍含「删除图层」")
    _got = []
    lt.requestCopyLayer.connect(lambda lid: _got.append(lid))
    # 临时断开主窗口处理，避免触发真实复制（仅验证信号携带正确的图层 id）
    try:
        lt.requestCopyLayer.disconnect(win._copy_layer)
        lmenu.actions_map["复制层"].slot()
    finally:
        lt.requestCopyLayer.connect(win._copy_layer)
    check(_got and _got[-1] == l2,
          "「复制层」以被右键选中的图层为目标")

    # 复制层功能（canvas.copy_layer）
    src_ids = {it.id for it in cv.items}
    src_layer_ids = _bottom_layer_ids(cv)
    src_idx = cv.layers.index(cv.layer_by_id(l2))
    copied = cv.copy_layer(l2)
    check(copied is not None, "copy_layer 返回新图层")
    check(copied.name == "图层2 副本", f"副本命名「图层2 副本」（实际 {copied.name}）")
    check(_bottom_layer_ids(cv) == src_layer_ids[:src_idx + 1]
          + [copied.id] + src_layer_ids[src_idx + 1:],
          "副本插入原图层正上方（叠放顺序）")
    new_ids = [it.id for it in cv.items if it.id not in src_ids]
    check(len(new_ids) == 3, f"复制出 3 个元素（实际 {len(new_ids)}）")
    check(len({it.id for it in cv.items}) == len([it.id for it in cv.items]),
          "复制后元素 id 全部唯一")
    for it in cv.items:
        if it.id in new_ids:
            check(it.layer_id == copied.id, "副本元素归属新图层")
            check(it.selected is False, "副本元素未选中")
    # 位置保持不变（复制层不偏移）
    _orig_shape = next(it for it in cv.items if isinstance(it, ShapeItem)
                       and it.layer_id == l2 and it.id in src_ids)
    _copy_shape = next(it for it in cv.items if isinstance(it, ShapeItem)
                       and it.id in new_ids)
    check(_copy_shape.p1 == _orig_shape.p1 and _copy_shape.p2 == _orig_shape.p2,
          "副本元素位置与原层一致")
    check(cv.current_layer == copied.id, "复制后副本设为当前层")

    # 树结构同步显示副本
    _drain(app)
    check(copied.id in lt._layer_items, "图层树出现副本节点")
    check(lt._layer_items[copied.id].childCount() == 3,
          "副本节点下挂 3 个元素")

    # 主窗口接线：win._copy_layer 可执行并提示
    _before = len(cv.layers)
    win._copy_layer(l2)
    check(len(cv.layers) == _before + 1, "主窗口「复制层」接线生效")

    # ==================== 汇总 ====================
    print("\n===== 汇总 =====")
    if FAILS:
        print(f"FAILED {len(FAILS)} 项")
        for f in FAILS:
            print(" -", f)
        sys.exit(1)
    print("全部通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
