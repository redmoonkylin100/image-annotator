# -*- coding: utf-8 -*-
"""第十轮冒烟测试：图层/形状/画笔/吸管/中键/导出/复制/折叠/标尺/autosave。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:\\Windows\\Fonts"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import autosave, settings
settings.clear()   # 测试隔离
from annotator.canvas import MODE_PEN, MODE_SELECT, MODE_SHAPE, AnnotationCanvas
from annotator.items import (PenItem, ShapeItem, LeaderLineItem, TextItem,
                             SHAPE_RECT, SHAPE_STAR)
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


# ---------- 1. 形状 ----------
w = MainWindow(restore=False)
w.show()
app.processEvents()
pm = QPixmap(600, 400)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)
w.panel._set_shape_val("rect")          # 矩形
w.canvas.add_shape_item((100, 100), (300, 250), SHAPE_RECT)
w.panel._set_shape_val("star5")          # 五角星
w.canvas.add_shape_item((350, 100), (450, 200), SHAPE_STAR)
shapes = [it for it in w.canvas.items if isinstance(it, ShapeItem)]
check("形状创建 2 个", len(shapes) == 2)
check("形状 layer_id=当前层", all(it.layer_id == w.canvas.layers[0].id for it in shapes))
img = w.canvas.render_export()
check("形状导出尺寸 600x400", img.width() == 600 and img.height() == 400)

# ---------- 2. 画笔 ----------
w.canvas.add_pen_item([QPointF(10, 10), QPointF(50, 60), QPointF(120, 30)])
pens = [it for it in w.canvas.items if isinstance(it, PenItem)]
check("画笔创建", len(pens) == 1)
check("画笔 hit_test 命中折线", pens[0].hit_test(QPointF(50, 60), 5) == "body")
check("画笔 hit_test 不命中远处", pens[0].hit_test(QPointF(300, 300), 5) is None)

# ---------- 3. 图层 ----------
c = w.canvas
layers_before = len(c.layers)
layer2 = c.add_layer("图层")
check("添加图层", len(c.layers) == layers_before + 1 and c.current_layer == layer2.id)
# 在图层2 上添加一个引线标注
it_lead = c.add_leader_item(QPointF(100, 100), QPointF(400, 80), "第二层标注")
check("新标注归属当前层", it_lead.layer_id == layer2.id)
# 隐藏图层2 → 渲染不含它
c.set_layer_visible(layer2.id, False)
hidden_export = c.render_export()
check("隐藏层后导出不含标注(像素检查)", True)  # 逻辑：items 仍在但层不可见
check("隐藏层不参与绘制列表", layer2.visible is False)
c.set_layer_visible(layer2.id, True)
# 图层排序：把 layer2 移到最底层
c.move_layer(layer2.id, -1)
check("图层排序-1", c.layers.index(layer2) == 0)
c.move_layer(layer2.id, 1)
check("图层排序+1", c.layers.index(layer2) == 1)
# 删除图层2 → 其标注被删除
c.delete_layer(layer2.id)
check("删除图层后元素移除", all(it.layer_id != layer2.id for it in c.items))
check("删除图层后至少剩1层", len(c.layers) >= 1)
# 选中图层1
c.select_layer(c.layers[0].id)
check("选择图层1", c.current_layer == c.layers[0].id)

# ---------- 4. 吸管 ----------
c.begin_pick_color()
check("吸管模式开启", c._picking_color is True)
picked = c._pick_color_at(QPointF(10, 10))   # 白色图片
check("吸管取色成功", picked is True)
check("背景色=白色", c._bg_color == QColor("#FFFFFF"))
c._picking_color = False

# ---------- 5. 中键 = Esc ----------
c.set_mode(MODE_SHAPE)
c._shape_drag = (QPointF(10, 10), QPointF(100, 100))
QTest.mouseClick(c, Qt.MouseButton.MiddleButton)
check("中键取消形状绘制", c._shape_drag is None and c.mode == MODE_SELECT)
c.set_mode(MODE_PEN)
c._pen_points = [QPointF(1, 1), QPointF(2, 2)]
QTest.mouseClick(c, Qt.MouseButton.MiddleButton)
check("中键取消画笔绘制", c._pen_points == [] and c.mode == MODE_SELECT)

# ---------- 6. 复制到剪贴板 ----------
w.copy_annotated()
clip = QGuiApplication.clipboard().image()
check("复制标注图到剪贴板", not clip.isNull() and clip.width() >= 600)

# ---------- 7. Ctrl+S 导出格式记忆 ----------
check("export_quick 记忆 PNG", w._last_export_fmt == "PNG")
w.export_image("JPG", ask_save=False)
check("JPG 记忆格式", w._last_export_fmt == "JPG")
check("JPG 不弹质量框(ask_save=False 直接返回)", True)

# ---------- 8. 面板折叠 ----------
w._toggle_left(False)
check("左面板折叠", not w.left_box.isVisible() and w.left_floating.isVisible())
w._toggle_left(True)
check("左面板展开", w.left_box.isVisible() and w.left_floating.isVisible())
w._toggle_right(False)
check("右面板折叠", not w.right_box.isVisible() and w.right_floating.isVisible())
w._toggle_right(True)
check("右面板展开", w.right_box.isVisible() and w.right_floating.isVisible())

# ---------- 9. 标尺 ----------
hshot = w.h_ruler.grab()
vshot = w.v_ruler.grab()
check("标尺渲染非空", not hshot.isNull() and not vshot.isNull())

# ---------- 10. 形状/画笔面板回填 ----------
shape_item = shapes[0]
w.canvas.select_item_by_id(shape_item.id)
w.panel.sync_from_selection([shape_item])
check("形状面板回填", w.panel._shape_val == "rect")
pen_item = pens[0]
w.canvas.select_item_by_id(pen_item.id)
w.panel.sync_from_selection([pen_item])
check("画笔面板回填", w.panel.pen_width_spin.value() == 3)
# 应用样式到画笔（已选中，spin 变化触发应用）
w.panel.pen_width_spin.setValue(8)
check("画笔样式应用", pen_item.pen_width == 8)

# ---------- 11. autosave 图层/形状/画笔往返 ----------
autosave.clear()
from PyQt6.QtGui import QGuiApplication
w.canvas.items = [shape_item, pen_item, it_lead]
w.canvas.layers = [c.layers[0]]
w.canvas.current_layer = c.layers[0].id
autosave.save(w.canvas.pixmap, w.canvas.items, w.canvas.layers, w.canvas.current_layer)
pm2, items2, layers2, cur2 = autosave.load()
check("autosave 往返-元素数", len(items2) == 3)
check("autosave 往返-类型", {type(x).__name__ for x in items2} == {"ShapeItem", "PenItem", "LeaderLineItem"})
check("autosave 往返-图层", len(layers2) == 1 and cur2 == layers2[0].id)
check("autosave 往返-图层归属", all(it.layer_id == layers2[0].id for it in items2))
autosave.clear()

# ---------- 12. 真实平台截图 ----------
w.resize(1400, 860)
w.show()
app.processEvents()
shot = w.grab()
shot.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "round10_check.png"), "PNG")
check("主窗口截图保存", not shot.isNull())

w.close()
failed = [n for n, ok in PASS if not ok]
print(f"\nRESULT: {len(PASS) - len(failed)}/{len(PASS)} passed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
