# -*- coding: utf-8 -*-
"""r32 回归：
需求1 右侧面板：形状的边框/填充颜色可设为「透明（隐藏）」（引线标注除外）
需求2 主界面右键顶部「重复上次标注」：快速恢复最近一次使用的标注工具模式
需求3 图层结构树空白处右键：新增层 / 折叠层 / 展开层
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.window import MainWindow
from annotator import layer_tree_panel as ltp
from annotator import window as winmod
from annotator import autosave
from annotator.canvas import (MODE_SELECT, MODE_LEADER, MODE_SHAPE)

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


class _FakeAction:
    def __init__(self, text, slot):
        self.text = text
        self.slot = slot
        self._enabled = True

    def setEnabled(self, v):
        self._enabled = v

    def setToolTip(self, t):
        pass


class _FakeMenu:
    """记录菜单条目（不真正 exec）。"""
    instances = []

    def __init__(self, *a, **k):
        self.labels = []
        self.actions_map = {}
        self._actions = []
        _FakeMenu.instances.append(self)

    def addAction(self, text, slot=None):
        self.labels.append(text)
        act = _FakeAction(text, slot)
        self.actions_map[text] = act
        self._actions.append(act)
        return act

    def addSeparator(self):
        pass

    def addMenu(self, text):
        sub = _FakeMenu()
        sub.labels.append(text)
        self._actions.append(sub)
        return sub

    def setStyleSheet(self, *a, **k):
        pass

    def exec(self, *a, **k):
        pass


def _drain(app, times=3):
    for _ in range(times):
        app.processEvents()


def _render_item(item, w=220, h=180):
    qimg = QImage(w, h, QImage.Format.Format_ARGB32)
    qimg.fill(QColor("#FFFFFF"))
    qp = QPainter(qimg)
    item.paint(qp, export=False)
    qp.end()
    return qimg


_ORIG_QMenu = ltp.QMenu


def _open_blank_menu(lt):
    """在树空白处触发右键，返回记录的菜单（事后恢复真实 QMenu）。"""
    _FakeMenu.instances.clear()
    ltp.QMenu = _FakeMenu
    try:
        lt._on_context_menu(QPoint(5, 5000))   # 视口外空白位置
    finally:
        ltp.QMenu = _ORIG_QMenu
    return _FakeMenu.instances[-1]


def main():
    app = QApplication([])
    # 隔离本机 autosave/settings.json：初始状态确定
    winmod.settings.load = lambda: {}
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    _drain(app)
    cv = win.canvas
    lt = win.layer_tree
    panel = win.panel

    pm = QPixmap(400, 300)
    pm.fill(QColor("#FFFFFF"))
    cv.load_pixmap(pm)
    _drain(app)

    # ==================== 需求1：透明边框/填充 ====================
    # 面板默认形状为「直线」，先切到矩形，确保测试形状为矩形
    panel._set_shape_val("rect")

    panel._finish_pick_color("shape_border", None)
    check(panel.shape_border_color().alpha() == 0,
          "形状边线颜色可设为透明（alpha=0）")
    check(panel.shape_border_btn.text() == "透明", "边线按钮显示「透明」")
    panel._finish_pick_color("shape_fill", None)
    check(panel.shape_fill_color().alpha() == 0,
          "形状填充颜色可设为透明（alpha=0）")
    check(panel.shape_fill_btn.text() == "透明", "填充按钮显示「透明」")

    # 选中形状 → 应用样式 → 边框/填充均为透明
    shape = cv.add_shape_item((20, 20), (180, 150), "rect")
    shape.selected = True
    cv.update()
    panel._apply_to_selection()
    check(shape.shape == "rect", "形状保持为矩形")
    check(shape.border_color.alpha() == 0 and shape.fill_color.alpha() == 0,
          "应用到选中形状：边框与填充均为透明")

    # 全透明：画面无任何绘制
    q1 = _render_item(shape)
    check(q1.pixelColor(100, 85) == QColor("#FFFFFF")
          and q1.pixelColor(100, 20) == QColor("#FFFFFF"),
          "边框+填充全透明：渲染无任何绘制")

    # 透明边框 + 蓝色填充：只有填充可见
    shape.border_color = QColor(0, 0, 0, 0)
    shape.fill_color = QColor("#2F80ED")
    q2 = _render_item(shape)
    check(q2.pixelColor(100, 85) == QColor("#2F80ED"),
          "透明边框+填充色：内部填充可见")
    _p2 = q2.pixelColor(100, 20)
    check(_p2.blue() > _p2.red(), "透明边框：边界处无红色边框（无残留）")

    # 红色边框 + 透明填充：边框可见、内部透明
    shape.border_color = QColor("#FF0000")
    shape.fill_color = QColor(255, 255, 255, 0)
    q3 = _render_item(shape)
    check(q3.pixelColor(100, 85) == QColor("#FFFFFF"),
          "边框+透明填充：内部不填充")
    _p3 = q3.pixelColor(100, 20)
    check(_p3.red() > _p3.blue(), "可见边框正常绘制")

    # 全透明形状仍可点选（内部命中保留）
    shape.border_color = QColor(0, 0, 0, 0)
    shape.fill_color = QColor(0, 0, 0, 0)
    check(shape.hit_test(QPointF(100, 85), 5.0) == "body",
          "全透明形状内部仍可命中（可选中/拖动）")

    # 序列化往返保留透明色
    data = autosave.serialize_items([shape])
    restored = autosave.deserialize_items(data)
    check(restored and restored[0].border_color.alpha() == 0
          and restored[0].fill_color.alpha() == 0,
          "序列化往返保留透明色（alpha=0）")

    # 画布拖拽预览：可见边框正常；透明边框不绘制
    cv.set_mode(MODE_SHAPE)
    panel._set_shape_val("rect")
    panel.shape_border_btn._color = QColor("#FF0000")
    panel.shape_fill_btn._color = QColor("#2F80ED")
    panel._refresh_color_buttons()
    cv._shape_drag = (QPointF(20, 20), QPointF(180, 150))
    cv.update()
    _drain(app)
    v_tl = cv.image_to_view(QPointF(20, 20))
    edge_x = int(v_tl.x()) + 80
    edge_y = int(v_tl.y())
    g1 = cv.grab().toImage()
    _pb = g1.pixelColor(edge_x, edge_y)
    check(_pb.red() > _pb.blue(), "拖拽预览：可见边框正常绘制")

    panel.shape_border_btn._color = QColor(0, 0, 0, 0)
    panel._refresh_color_buttons()
    cv.update()
    _drain(app)
    g2 = cv.grab().toImage()
    _pb2 = g2.pixelColor(edge_x, edge_y)
    check(_pb2.blue() > _pb2.red(), "拖拽预览：透明边框不绘制（填充可见）")
    v_mid = cv.image_to_view(QPointF(100, 85))
    check(g2.pixelColor(int(v_mid.x()), int(v_mid.y())) == QColor("#2F80ED"),
          "拖拽预览：填充色正常预览")
    cv._shape_drag = None
    cv.set_mode(MODE_SELECT)

    # ==================== 需求2：重复上次标注 ====================
    # 需求1 的预览测试切过形状模式，这里重置为「无记录」初始态再验证
    cv._last_annotation_mode = None
    check(cv._last_annotation_mode is None, "初始无上次标注记录")
    menu0 = cv._build_context_menu(QPointF(5, 5))
    acts0 = menu0.actions()
    check(acts0[0].text() == "重复上次标注", "右键菜单顶部第一项为「重复上次标注」")
    check(not acts0[0].isEnabled(), "无记录时「重复上次标注」禁用")
    menu0.deleteLater()

    cv.set_mode(MODE_SHAPE)
    check(cv._last_annotation_mode == MODE_SHAPE, "使用形状工具后记录为 shape")
    cv.set_mode(MODE_SELECT)
    check(cv._last_annotation_mode == MODE_SHAPE, "切回选择模式不覆盖记录")

    msgs = []
    cv.statusMessage.connect(msgs.append)
    cv.repeat_last_annotation()
    check(cv.mode == MODE_SHAPE, "「重复上次标注」恢复为形状工具")
    check(msgs and "上次标注" in msgs[-1], "重复后状态栏提示")
    check(panel.group_states().get("shape") is True,
          "恢复后自动展开形状设置组")

    # 执行其它命令（如复制）不影响「重复上次标注」的记录
    cv.set_mode(MODE_SELECT)
    cv.duplicate_item(shape)
    cv.set_mode(MODE_LEADER)
    cv.set_mode(MODE_SELECT)
    cv.repeat_last_annotation()
    check(cv.mode == MODE_LEADER,
          "复制/其它命令不干扰「重复上次标注」（仍回到上次标注工具）")

    menu1 = cv._build_context_menu(QPointF(5, 5))
    acts1 = menu1.actions()
    check(acts1[0].text() == "重复上次标注" and acts1[0].isEnabled(),
          "有记录后「重复上次标注」可用")
    menu1.deleteLater()

    # ==================== 需求3：图层树空白处右键 ====================
    # 给每个图层放一个元素，确保展开/折叠状态有意义
    cv.add_layer()
    for l in cv.layers:
        cv.current_layer = l.id
        cv.add_shape_item((10, 10), (60, 50), "rect")
    _drain(app)

    m = _open_blank_menu(lt)
    check(m.labels[:3] == ["新增层", "折叠层", "展开层"],
          f"空白右键菜单含 新增层/折叠层/展开层（实际 {m.labels}）")

    n0 = len(cv.layers)
    m.actions_map["新增层"].slot()
    _drain(app)
    check(len(cv.layers) == n0 + 1, "空白右键「新增层」生效")

    # 全部展开 → 折叠层
    lt._expand_all()
    _drain(app)
    check(all(n.isExpanded() for n in lt._layer_items.values()),
          "准备：所有图层已展开")
    m2 = _open_blank_menu(lt)
    m2.actions_map["折叠层"].slot()
    _drain(app)
    check(all(not n.isExpanded() for n in lt._layer_items.values()),
          "空白右键「折叠层」：所有图层折叠")

    # 折叠层 → 展开层
    m3 = _open_blank_menu(lt)
    m3.actions_map["展开层"].slot()
    _drain(app)
    check(all(n.isExpanded() for n in lt._layer_items.values()),
          "空白右键「展开层」：所有图层展开")

    # ==================== 收尾 ====================
    print(f"\n结果：{len(FAILS)} 项失败")
    if FAILS:
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    os._exit(0)


if __name__ == "__main__":
    main()
