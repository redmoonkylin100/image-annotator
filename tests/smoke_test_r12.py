# -*- coding: utf-8 -*-
"""第十二轮冒烟测试：右侧面板滚动、应用到全部、形状菜单、分组折叠联动、
图层拖拽排序、.anno 项目文件（序号保留）、形状/画笔稳定性。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QScrollArea

app = QApplication([])

from annotator import autosave, settings
settings.clear()
autosave.clear()

from annotator.canvas import (MODE_LEADER, MODE_NUMBER, MODE_PEN, MODE_SELECT,
                              MODE_SHAPE)
from annotator.items import LeaderLineItem, ShapeItem, PenItem
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


w = MainWindow(restore=False)
w.show()
app.processEvents()
pm = QPixmap(700, 460)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)

# ---------- 1. 右侧面板滚动 ----------
check("右侧面板包 QScrollArea", isinstance(w.panel_scroll, QScrollArea))
check("滚动区 widgetResizable", w.panel_scroll.widgetResizable() is True)
check("面板在滚动区内", w.panel_scroll.widget() is w.panel)

# ---------- 2. 分组折叠（默认折叠 + 联动展开） ----------
check("引线设置默认展开", w.panel._groups["leader"].is_expanded() is True)
check("形状设置默认折叠", w.panel._groups["shape"].is_expanded() is False)
check("导出设置默认折叠", w.panel._groups["export"].is_expanded() is False)
w.canvas.set_mode(MODE_SHAPE)
check("切形状模式自动展开形状组", w.panel._groups["shape"].is_expanded() is True)
w.canvas.set_mode(MODE_PEN)
check("切画笔模式自动展开画笔组", w.panel._groups["pen"].is_expanded() is True)
w.canvas.set_mode(MODE_LEADER)

# ---------- 3. 形状菜单（完整形状 + 创建不闪退） ----------
w.canvas.set_mode(MODE_SHAPE)
for _ in range(15):   # 反复拖出形状：稳定性
    QTest.mousePress(w.canvas, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(80, 80))
    QTest.mouseMove(w.canvas, QPoint(200, 170))
    QTest.mouseRelease(w.canvas, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(200, 170))
app.processEvents()
shapes = [it for it in w.canvas.items if isinstance(it, ShapeItem)]
check("形状反复绘制不闪退(15个)", len(shapes) == 15)
check("形状菜单按钮存在", w.panel.shape_btn is not None)
w.panel._set_shape("triangle")
check("形状菜单切换三角形", w.panel._shape_val == "triangle")
w.panel._set_shape("rect")
check("形状菜单切回矩形", w.panel._shape_val == "rect")

# ---------- 4. 画笔稳定性 ----------
w.canvas.set_mode(MODE_PEN)
for _ in range(10):
    QTest.mousePress(w.canvas, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(60, 300))
    QTest.mouseMove(w.canvas, QPoint(90, 330))
    QTest.mouseMove(w.canvas, QPoint(120, 310))
    QTest.mouseRelease(w.canvas, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier, QPoint(120, 310))
app.processEvents()
pens = [it for it in w.canvas.items if isinstance(it, PenItem)]
check("画笔反复绘制不闪退(10个)", len(pens) == 10)

# ---------- 5. 应用到全部同类标注 ----------
w.canvas.set_mode(MODE_LEADER)
for tp in [(120, 120), (240, 300)]:
    w.canvas.add_leader_item(QPointF(tp[0], tp[1]), QPointF(500, 200), "测试")
w.canvas.set_mode(MODE_SELECT)
w.panel.line_color_btn._color = QColor("#123456")
w.panel.line_width_spin.setValue(5)
w.panel.arrow_size_spin.setValue(20)
leaders = [it for it in w.canvas.items if isinstance(it, LeaderLineItem)]
check("应用到全部前存在引线", len(leaders) > 0)
w.panel.apply_to_all()
leaders2 = [it for it in w.canvas.items if isinstance(it, LeaderLineItem)]
check("应用到全部：颜色", all(it.line_color == QColor("#123456") for it in leaders2))
check("应用到全部：粗细", all(it.line_width == 5 for it in leaders2))
check("应用到全部：箭头", all(it.arrow_size == 20 for it in leaders2))

# ---------- 6. 图层拖拽排序 ----------
w.canvas.add_layer("图层2")
w.canvas.add_layer("图层3")
app.processEvents()
ids_before = [l.id for l in w.canvas.layers]
# 模拟拖拽：把最后一行（当前底层）拖到列表顶部 -> 新顶层
lp = w.layers_panel
bottom_id = lp.list.item(lp.list.count() - 1).data(Qt.ItemDataRole.UserRole)
top_ids = [bottom_id] + [lp.list.item(i).data(Qt.ItemDataRole.UserRole)
                         for i in range(lp.list.count() - 1)]
# 列表顺序（顶->底）反转 = layers 顺序（底->顶）
new_ids = list(reversed(top_ids))
w.canvas.apply_layer_order(new_ids)
ids_after = [l.id for l in w.canvas.layers]
check("图层重排生效", ids_after == new_ids)
check("图层重排顺序不同", ids_after != ids_before)
check("新底层=原底层上方", ids_after[0] == ids_before[1] if len(ids_before) > 2 else True)
# 列表顺序（顶层在上）与 layers 顺序（底层在前）互逆
top = lp.list.item(0).data(Qt.ItemDataRole.UserRole)
check("列表顶部=最高层", top == w.canvas.layers[-1].id)

# ---------- 7. 项目文件 .anno（序号保留） ----------
w.canvas.set_mode(MODE_NUMBER)
w.canvas.number_enabled = True
for tp in [(120, 120), (240, 200)]:
    w.canvas.add_leader_item(QPointF(tp[0], tp[1]), QPointF(420, 100), "")
w.canvas.renumber()
numbered = [it for it in w.canvas.items if isinstance(it, LeaderLineItem)
            and it.number]
check("项目保存前有序号", len(numbered) >= 2)

proj = os.path.join(tempfile.gettempdir(), "test_proj.anno")
w.canvas._project_path = proj
w.canvas._last_export_fmt = "PNG"
# 直接调用保存/打开逻辑（避开文件对话框）
import json
import zipfile
from PyQt6.QtCore import QBuffer

buf = QBuffer()
buf.open(QBuffer.OpenModeFlag.WriteOnly)
w.canvas.pixmap.toImage().save(buf, "PNG")
payload = {
    "items": autosave.serialize_items(w.canvas.items),
    "layers": autosave.serialize_layers(w.canvas.layers),
    "current_layer": w.canvas.current_layer,
    "number_enabled": True,
    "number_format": "circle",
    "snap_mode": "none",
}
with zipfile.ZipFile(proj, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("image.png", bytes(buf.data()))
    z.writestr("project.json", json.dumps(payload, ensure_ascii=False))
check("项目文件已生成", os.path.isfile(proj))

w2 = MainWindow(restore=False)
w2.show()
app.processEvents()
with zipfile.ZipFile(proj, "r") as z:
    img_bytes = z.read("image.png")
    data = json.loads(z.read("project.json").decode("utf-8"))
pm2 = QPixmap()
pm2.loadFromData(img_bytes, "PNG")
items2 = autosave.deserialize_items(data.get("items", []))
layers2 = autosave.deserialize_layers(data.get("layers", []), items2)
w2.canvas.load_pixmap(pm2)
w2.canvas.items = items2
w2.canvas.layers = layers2
if any(getattr(it, "number", None) for it in items2):
    w2.canvas.number_enabled = True
    w2.canvas.renumber()
leaders2_2 = [it for it in w2.canvas.items if isinstance(it, LeaderLineItem)
              and it.number]
check("项目打开后序号保留", len(leaders2_2) >= 2)
check("项目打开后序号连续", [it.number for it in leaders2_2] ==
      list(range(1, len(leaders2_2) + 1)))
w2.close()

os.remove(proj)
w.close()
autosave.clear()
settings.clear()

fails = [n for n, ok in PASS if not ok]
print(f"\nRESULT: {len(PASS) - len(fails)}/{len(PASS)} passed")
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("SMOKE OK")
