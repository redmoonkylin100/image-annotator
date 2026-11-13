# -*- coding: utf-8 -*-
"""第十四轮冒烟测试：形状/画笔拖拽预览渲染、形状/画笔颜色按钮着色、项目文件保存（style 颜色序列化）。

运行：python tests/smoke_test_r14.py（离屏）
覆盖：
1. _paint_preview 形状分支实际渲染红色边框（此前 NameError 被 paintEvent 吞掉 → 预览从不显示）
2. _paint_preview 画笔分支实际渲染轨迹（此前 QPolygonF NameError）
3. _refresh_color_buttons 覆盖形状/画笔三个颜色按钮（此前漏刷 → 始终白色）
4. save_project 的 style 段 QColor 转 hex（此前 json.dumps 崩 → 保存失败）
5. open_project 恢复 style 后颜色按钮回读正确
"""
import os
import sys
import zipfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPixmap, QPainter
from PyQt6.QtWidgets import QApplication, QFileDialog

app = QApplication([])

from annotator import settings
settings.clear()
from annotator.window import MainWindow
from annotator.canvas import MODE_SHAPE, MODE_PEN

w = MainWindow(restore=False)
w.show()
app.processEvents()

pm = QPixmap(700, 460)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)
app.processEvents()

passed = 0
failed = []


def check(name: str, cond: bool) -> None:
    global passed
    if cond:
        passed += 1
        print(f"OK   | {name}")
    else:
        failed.append(name)
        print(f"FAIL | {name}")


def red_pixels(img, step=4) -> int:
    return sum(1 for x in range(0, img.width(), step) for y in range(0, img.height(), step)
               if QColor(img.pixel(x, y)).red() > 180 and QColor(img.pixel(x, y)).green() < 120)


def dark_pixels(img, step=4) -> int:
    return sum(1 for x in range(0, img.width(), step) for y in range(0, img.height(), step)
               if QColor(img.pixel(x, y)).red() < 80 and QColor(img.pixel(x, y)).green() < 80)


# ---------- 1. 形状拖拽预览 ----------
w.canvas.set_mode(MODE_SHAPE)
w.panel._set_shape("rect")
w.canvas._shape_drag = (QPointF(100, 100), QPointF(300, 250))
out = QPixmap(700, 460)
out.fill(QColor("#FFFFFF"))
p = QPainter(out)
w.canvas._paint_preview(p)
p.end()
check("形状预览渲染红色边框", red_pixels(out.toImage()) > 50)

# ---------- 2. 画笔轨迹预览 ----------
w.canvas.set_mode(MODE_PEN)
w.canvas._pen_points = [QPointF(50, 50), QPointF(150, 100), QPointF(250, 80)]
out = QPixmap(700, 460)
out.fill(QColor("#FFFFFF"))
p = QPainter(out)
w.canvas._paint_preview(p)
p.end()
check("画笔预览渲染轨迹", dark_pixels(out.toImage()) > 10)

# ---------- 3. 颜色按钮着色 ----------
w.panel._refresh_color_buttons()
check("形状边线颜色按钮着色", "rgb(255,0,0)" in w.panel.shape_border_btn.styleSheet())
check("形状填充颜色按钮有样式", "background-color" in w.panel.shape_fill_btn.styleSheet())
check("画笔颜色按钮着色", "rgb(0,0,0)" in w.panel.pen_color_btn.styleSheet())
# 选色路径：直接设置 _color 并刷新
w.panel.shape_border_btn._color = QColor("#00AA00")
w.panel.pen_color_btn._color = QColor("#0000FF")
w.panel._refresh_color_buttons()
check("改色后形状按钮跟随", "rgb(0,170,0)" in w.panel.shape_border_btn.styleSheet())
check("改色后画笔按钮跟随", "rgb(0,0,255)" in w.panel.pen_color_btn.styleSheet())

# ---------- 4. 项目保存（style 颜色序列化） ----------
w.canvas.add_shape_item((10, 10), (200, 150), "rect")
out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "issue14_test.anno"))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_path, ""))
w.save_project()
ok_save = os.path.exists(out_path)
check("项目文件保存成功", ok_save)
if ok_save:
    with zipfile.ZipFile(out_path) as z:
        payload = json.loads(z.read("project.json").decode("utf-8"))
    st = payload.get("style", {})
    check("style 颜色已转 hex 字符串",
          isinstance(st.get("line_color"), str) and st["line_color"].startswith("#"))
    check("项目包含标注元素", len(payload.get("items", [])) >= 1)
    # 5. 打开项目恢复 style
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (out_path, ""))
    w.open_project()
    app.processEvents()
    check("打开项目后按钮颜色回读", w.panel.shape_border_btn._color.red() > 0 or
          w.panel.line_color_btn._color.red() > 0)
    try:
        os.remove(out_path)
    except OSError:
        pass

print(f"\nRESULT: {passed}/{passed + len(failed)} passed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
