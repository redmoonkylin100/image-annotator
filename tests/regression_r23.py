# -*- coding: utf-8 -*-
"""r23 回归：
1) 截图导入按原始分辨率 100% 显示 + 顶部「100%」按钮；
2) 引线「空白间隙」改名 + 新增「上下间隙 above_gap」(0~20)；
3) 直线改为点击式连续折线（逐点点击、跟随、正交磁吸 ±5px、Esc/双击/回车结束、保留已确认部分）；
4) 直线严格走真实顶点（修复反向拖拽起点漂移）；多点折线持久化往返；其他形状拖拽不回归。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel

from annotator.window import MainWindow
from annotator.items import SHAPE_LINE, ShapeItem, LeaderLineItem
from annotator import autosave

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def iter_layout_widgets(layout):
    for i in range(layout.count()):
        it = layout.itemAt(i)
        w = it.widget()
        if w is not None:
            yield w
        sub = it.layout()
        if sub is not None:
            yield from iter_layout_widgets(sub)


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    cv = win.canvas

    def fresh_image(w=400, h=300, fit=False):
        pm = QPixmap(w, h)
        pm.fill(QColor("#FFFFFF"))
        cv.load_pixmap(pm, fit=fit)
        loaded_scale = cv.scale
        cv.resize(900, 700)
        cv.scale = 1.0
        cv.offset = QPointF(0.0, 0.0)   # 让视图坐标==图片坐标，便于事件注入
        return loaded_scale

    # ---------- 1. 100% 视图 ----------
    fresh_image(400, 300, fit=False)
    check(abs(cv.scale - 1.0) < 1e-9, "截图入口 fit=False：初始 scale=1（不放大）")
    cv.fit_to_view()
    check(cv.scale > 1.0, "小图 fit_to_view 会放大铺满（对照）")
    cv.actual_size()
    check(abs(cv.scale - 1.0) < 1e-9, "actual_size() 恢复 100%")
    s_fit = fresh_image(400, 300, fit=True)
    check(s_fit > 1.0, "其他入口 fit=True 仍自适应（不回归）")

    # ---------- 2. 顶部「100%」按钮（主题按钮左侧） ----------
    b = getattr(win, "zoom_100_btn", None)
    check(b is not None and b.text() == "100%", "顶部存在「100%」按钮")
    check(b.receivers(b.clicked) > 0, "100% 按钮已接线")
    cv.fit_to_view()
    b.click()
    app.processEvents()
    check(abs(cv.scale - 1.0) < 1e-9, "点击 100% 按钮恢复原始分辨率")
    # 通过子控件顺序验证 100% 在主题按钮左侧
    order = []
    def _walk(w):
        for c in w.children():
            if c.__class__.__name__ == "QPushButton":
                order.append(c.text())
            _walk(c)
    _walk(win.toolbar)
    def _pos(s):
        return order.index(s) if s in order else -1
    check(_pos("100%") < _pos("🌙") or _pos("100%") < _pos("☀️"),
          "100% 按钮位于主题按钮左侧")

    # ---------- 3. 引线间隙：改名 + 上下间隙 ----------
    panel = win.panel
    labels = [w.text() for w in panel.findChildren(QLabel)]
    check("空白间隙" in labels, "原「文字间隙」已改名为「空白间隙」")
    check("文字间隙" not in labels, "旧标签「文字间隙」已移除")
    check("上下间隙" in labels, "新增「上下间隙」标签")
    ag = panel.above_gap_spin
    check(ag.minimum() == 0 and ag.maximum() == 20 and ag.value() == 5,
          "上下间隙范围 0~20、默认 5")
    st = panel.current_style()
    check("text_gap" in st and "above_gap" in st, "current_style 同时含 text_gap / above_gap")
    # 几何：above_gap 独立控制文字与横线的垂直距离
    lead = LeaderLineItem((300, 300), (60, 60), "测试")
    lead.label_style = "plain"
    lead.apply_style({"font_size": 18, "text_color": "#000000", "font_family": "Microsoft YaHei",
                      "font_weight": 400, "font_italic": False, "script": "normal",
                      "bg_enabled": False, "bg_fill_color": "#FFFFFF00", "bg_border_color": "#00000000",
                      "endpoint_style": "arrow", "label_style": "plain", "above_dir": "left",
                      "text_gap": 5.0, "above_gap": 5.0})
    c5 = lead._get_leader_geometry("above_text")[0].y()
    lead.apply_style({"font_size": 18, "text_color": "#000000", "font_family": "Microsoft YaHei",
                      "font_weight": 400, "font_italic": False, "script": "normal",
                      "bg_enabled": False, "bg_fill_color": "#FFFFFF00", "bg_border_color": "#00000000",
                      "endpoint_style": "arrow", "label_style": "plain", "above_dir": "left",
                      "text_gap": 5.0, "above_gap": 12.0})
    c12 = lead._get_leader_geometry("above_text")[0].y()
    check(abs((c12 - c5) - 7.0) < 1e-6, "above_gap 5→12：横线垂直下移 7px（与空白间隙独立）")

    # ---------- 4. 直线严格走真实顶点（修复起点漂移） ----------
    # “/” 方向：p1 左下 (20,200) → p2 右上 (200,20)；旧实现归一化后画成 “\”
    ln = ShapeItem((20, 200), (200, 20), shape=SHAPE_LINE)
    check(ln.hit_test(QPointF(60, 160), 4) == "body", "真实斜线 “/” 上的点 (60,160) 可命中")
    check(ln.hit_test(QPointF(60, 60), 3) is None, "错误对角线 “\\” 上的点 (60,60) 不命中")

    # ---------- 事件工厂 ----------
    def press(x, y):
        e = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, y),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
        cv.mousePressEvent(e)

    def move(x, y, held=False):
        btns = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        e = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                        Qt.MouseButton.NoButton, btns,
                        Qt.KeyboardModifier.NoModifier)
        cv.mouseMoveEvent(e)

    def release(x, y):
        e = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(x, y),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
        cv.mouseReleaseEvent(e)

    def key(k):
        e = QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier)
        cv.keyPressEvent(e)

    def dblclick(x, y):
        e = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(x, y),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
        cv.mouseDoubleClickEvent(e)

    cv.set_mode("shape")
    panel._set_shape_val(SHAPE_LINE)

    # ---------- 5. 点击式连续折线 + 正交磁吸 + Esc 结束 ----------
    fresh_image()
    cv.set_mode("shape")
    n_before = len(cv.items)
    press(50, 100)
    check(cv._line_points is not None and len(cv._line_points) == 1, "首次点击确定起点")
    move(150, 103)   # dy=3 ≤5 → 水平吸附
    check(cv._line_snap_axis == "h" and abs(cv._line_cursor.y() - 100) < 1e-9,
          "接近水平（±5px）吸附为水平线")
    press(150, 103)  # 确认第二点（所见即所得，y 已被吸附为 100）
    check(len(cv._line_points) == 2, "第二次点击确认第二个顶点")
    move(153, 50)    # dx=3 ≤5 → 竖直吸附
    check(cv._line_snap_axis == "v" and abs(cv._line_cursor.x() - 150) < 1e-9,
          "接近竖直（±5px）吸附为竖直线")
    press(153, 50)
    check(len(cv._line_points) == 3, "第三次点击确认第三个顶点（可连续画异形）")
    move(260, 200)   # 斜向，不吸附
    check(cv._line_snap_axis is None, "明显斜向时不吸附")
    key(Qt.Key.Key_Escape)
    check(cv._line_points is None, "Esc 退出连续画线状态")
    check(len(cv.items) == n_before + 1, "Esc 后生成 1 个折线元素")
    poly = cv.items[-1]
    check(isinstance(poly, ShapeItem) and poly.points is not None and len(poly.points) == 3,
          "折线元素含 3 个已确认顶点（未确认的跟随段被丢弃）")
    pts = [(round(p.x()), round(p.y())) for p in poly.points]
    check(pts == [(50, 100), (150, 100), (150, 50)],
          f"顶点坐标正确且已正交截断：{pts}")
    check(cv.mode == "shape", "Esc 结束后仍停留在形状工具（不切换工具）")

    # Esc 后可立即开始下一条新折线
    press(10, 10)
    check(len(cv._line_points) == 1, "结束后再次点击可开始新折线")
    key(Qt.Key.Key_Escape)   # 只有 1 个点 → 取消，不生成元素
    check(len(cv.items) == n_before + 1, "仅起点时 Esc 取消，不产生元素")

    # ---------- 6. 双击结束 ----------
    fresh_image()
    cv.set_mode("shape")
    press(20, 20); move(120, 120); press(120, 120)
    dblclick(120, 120)
    check(cv._line_points is None and len(cv.items) == 1, "双击结束连续折线")
    check(len(cv.items[-1].points) == 2, "双击提交 2 个顶点")

    # ---------- 7. 回车结束 ----------
    fresh_image()
    cv.set_mode("shape")
    press(0, 0); press(80, 80)
    key(Qt.Key.Key_Return)
    check(len(cv.items) == 1 and len(cv.items[-1].points) == 2, "回车同样可结束折线")

    # ---------- 8. 多点折线持久化往返 ----------
    from PyQt6.QtCore import QPointF as _QPF
    poly3 = ShapeItem((0, 0), (120, 60), shape=SHAPE_LINE)
    poly3.points = [_QPF(0, 0), _QPF(120, 0), _QPF(120, 60)]
    data = autosave.serialize_items([poly3])
    check("line_points" in data[0] and len(data[0]["line_points"]) == 3,
          "3 点折线写出 line_points")
    restored = autosave.deserialize_items(data)
    check(len(restored) == 1 and len(restored[0].points) == 3, "折线序列化/反序列化保留顶点")
    # 普通两点直线不写 line_points（向后兼容旧存档）
    two = ShapeItem((0, 0), (50, 50), shape=SHAPE_LINE)
    d2 = autosave.serialize_items([two])
    check("line_points" not in d2[0], "两点直线保持旧格式（不写 line_points）")

    # ---------- 9. 其他形状拖拽流程不回归 ----------
    fresh_image()
    cv.set_mode("shape")
    panel._set_shape_val("rect")
    press(30, 30); move(200, 150, held=True); release(200, 150)
    check(len(cv.items) == 1 and cv.items[-1].shape == "rect" and cv.items[-1].points is None,
          "矩形仍为按下-拖动-松开创建（不回归）")

    # 切回直线，切模式会清空未完成折线状态
    panel._set_shape_val(SHAPE_LINE)
    cv.set_mode("select")
    check(cv._line_points is None and cv._shape_drag is None, "切换模式清空绘制临时状态")

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit(); os._exit(1)
    print("==== r23 全部断言通过 ====")
    app.quit(); os._exit(0)


if __name__ == "__main__":
    main()
