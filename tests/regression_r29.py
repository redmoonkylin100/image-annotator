# -*- coding: utf-8 -*-
"""R29 回归：标注尾巴 Office 化 / 形状面板七分类 / 右侧面板宽度 / 马赛克向下合成。

离屏运行：venv\\Scripts\\python.exe tests\\regression_r29.py
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import items as I
from annotator.items import (ShapeItem, MosaicItem, ImageItem,
                             shape_path, shape_categories,
                             SHAPE_OPTIONS, CALLOUT_SHAPES)
from annotator import callout_geom as cg
from annotator.canvas import AnnotationCanvas as Canvas
from annotator.autosave import serialize_items, deserialize_items

FAILS = []


def check(cond, msg):
    print(("  OK  " if cond else " FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


# ---------------------------------------------------------------- 1. 几何
print("[1] callout_geom root clamp / bias / nearest edge")
verts = cg.rect_vertices(QRectF(0, 0, 100, 80))
ei, t = cg.nearest_edge(verts, QPointF(-200, 200))
check(ei == 2, f"far bottom-left apex -> bottom edge (got {ei})")
r1, r2 = cg.edge_roots(verts, ei, t)
edge_y = verts[ei].y()
check(abs(r1.y() - edge_y) < 1e-6 and abs(r2.y() - edge_y) < 1e-6,
      "roots lie on the bottom edge")
check(0 <= r1.x() and r2.x() <= 100 and r1 != r2,
      f"roots clamped inside edge r1={r1.x():.1f} r2={r2.x():.1f}")
# 底边方向为 R->L，投影点被钳到 x=0；根心中点应在其右侧（偏向中心 50）
check((r1.x() + r2.x()) / 2 > 0,
      "apex far left -> root center biased right (toward body center)")
ei2, _ = cg.nearest_edge(verts, QPointF(50, -50))
check(ei2 == 0, f"apex above -> top edge (got {ei2})")
ei3, _ = cg.nearest_edge(verts, QPointF(-50, 40))
check(ei3 == 3, f"apex left -> left edge (got {ei3})")
ei4, _ = cg.nearest_edge(verts, QPointF(150, 40))
check(ei4 == 1, f"apex right -> right edge (got {ei4})")
e1, e2, anchor = cg.ellipse_roots(QRectF(0, 0, 100, 80), QPointF(150, 40))
check(abs(anchor.y() - 40) < 1 and abs(anchor.x() - 100) < 1,
      f"ellipse anchor on right arc (got {anchor.x():.1f},{anchor.y():.1f})")

# ---------------------------------------------------------------- 2. body fixed
print("[2] apex free, body size constant, tails on four sides")
for shape in sorted(CALLOUT_SHAPES):
    it = ShapeItem((20, 20), (120, 100), shape=shape)
    r0 = QRectF(it.rect())
    for ap in (QPointF(60, 220), QPointF(70, -40), QPointF(-60, 60),
               QPointF(200, 70), QPointF(70, 60)):
        it.set_tail_apex(ap)
        rr = it.rect()
        assert rr == r0, (shape, "body changed when dragging apex")
        pp = shape_path(shape, rr, tail=it.tail_apex_point())
        assert not pp.isEmpty()
check(True, "all 7 callouts: 4-side tails never deform body, paths valid")

it = ShapeItem((20, 20), (120, 100), shape="rectcallout")
it.set_tail_apex(QPointF(-100, -100))
check(it.tail_apex == QPointF(-100, -100), "apex freely draggable (no clamp)")
b = it.export_bounds()
check(b.left() <= -100 and b.top() <= -100, "export bounds include far apex")
it.move_by(15, 25, "body")
check(it.tail_apex == QPointF(-85, -75), "apex translates with body move")

it = ShapeItem((0, 0), (100, 100), shape="ovalcallout")
it.rotation = 45
it.set_tail_apex(QPointF(50, 160))
b = it.export_bounds()
# 尾尖绕中心旋转 45° 后向左上方甩出，外接矩形左边界应越过主体左边
check(b.left() < 0, f"rotated export bounds still include apex (left={b.left():.1f})")

leg = ShapeItem((0, 0), (100, 100), shape="diamondcallout")
leg.tail_x, leg.tail_len = 0.5, 0.3
ap = leg.tail_apex_point()
check(abs(ap.x() - 50) < 1e-6 and abs(ap.y() - 130) < 1e-6,
      f"legacy tail_x/tail_len migrates to apex (got {ap.x()},{ap.y()})")

# 根点必须落在【本体边线】上，而不是外接虚线框：菱形斜边校验
dv = [QPointF(50, 0), QPointF(100, 50), QPointF(50, 100), QPointF(0, 50)]
for ap_test in (QPointF(30, 150), QPointF(50, 160), QPointF(75, 150)):
    ei, t = cg.nearest_edge(dv, ap_test)
    q1, q2 = cg.edge_roots(dv, ei, t)
    a, b = dv[ei], dv[(ei + 1) % 4]
    for q in (q1, q2):
        # 点到所在边的距离应≈0（贴合本体边线）
        d = cg.dist_to_segment(q, a, b)
        assert d < 1e-6, (f"root off body edge d={d}", ap_test)
check(True, "diamond callout roots lie exactly on slanted body edges (not bbox)")

# 缩放主体时尾尖按锚点等比跟随，根部不脱离
cv_r = Canvas()
cv_r.load_pixmap(QPixmap(200, 200), fit=False)
shp_r = cv_r.add_shape_item((20, 20), (100, 100), "rectcallout")
shp_r.set_tail_apex(QPointF(40, 140))
ev = {"item": shp_r, "start_rect": QRectF(20, 20, 80, 80),
      "center": QPointF(60, 60), "start_rot": 0.0, "idx": 4,
      "start_geom": {"tail_apex": QPointF(40, 140)}, "moved": False}
# 拖右下角把主体放大到 (20,20)-(180,180)（2x）
cv_r._apply_shape_resize(ev, QPointF(180, 180))
# 锚点=左上角(20,20)，尾尖 (40,140) 应放大到 (60,260)
check(abs(shp_r.tail_apex.x() - 60) < 1e-6 and abs(shp_r.tail_apex.y() - 260) < 1e-6,
      f"apex scales with body resize (got {shp_r.tail_apex.x()},{shp_r.tail_apex.y()})")

img = QImage(220, 220, QImage.Format.Format_ARGB32)
p = QPainter(img)
for _, v in SHAPE_OPTIONS:
    p.drawPath(shape_path(v, QRectF(20, 20, 160, 120)))
p.end()
check(True, f"all {len(SHAPE_OPTIONS)} shape paths render without error")

# ---------------------------------------------------------------- 3. canvas drag
print("[3] canvas yellow-apex drag")
cv = Canvas()
base = QPixmap(200, 200)
base.fill(QColor(255, 255, 255))
cv.load_pixmap(base, fit=False)
shp = cv.add_shape_item((20, 20), (120, 100), "rectcallout")
e = {"item": shp, "start_rect": QRectF(shp.rect()),
     "center": shp.rect().center(), "start_rot": 0.0, "moved": False}
cv._apply_tail_drag(e, QPointF(-50, 260))
check(e["moved"] and shp.tail_apex == QPointF(-50, 260),
      f"drag writes absolute apex (got {shp.tail_apex})")

# ---------------------------------------------------------------- 4. flatten
print("[4] mosaic source = everything below (incl. imported screenshot)")


def solid_pm(rgb, w=120, h=120):
    im = QImage(w, h, QImage.Format.Format_RGB32)
    im.fill(QColor(*rgb))
    return QPixmap.fromImage(im)


cv2 = Canvas()
base_red = QPixmap(200, 200)
base_red.fill(QColor(220, 30, 30))
cv2.load_pixmap(base_red, fit=False)
l_shot = cv2.add_layer("shot").id
l_top = cv2.add_layer("mosaic").id
shot = ImageItem((40, 40), (160, 160), solid_pm((30, 60, 220)))
shot.layer_id = l_shot
cv2.items.append(shot)
mos = MosaicItem((60, 60), (140, 140), block_size=20, show_border=False)
mos.layer_id = l_top
cv2.items.append(mos)
out = cv2.render_export()
col = QColor(out.pixelColor(100, 100))
print(f"   mosaic center R={col.red()} G={col.green()} B={col.blue()}")
check(col.blue() > col.red() + 60,
      "upper mosaic pixelates the imported screenshot below it")

cv3 = Canvas()
cv3.load_pixmap(base_red, fit=False)
l0 = cv3.layers[0].id
l_img = cv3.add_layer("shot").id
l_above = cv3.add_layer("above").id
under = cv3.add_shape_item((50, 50), (150, 150), "rect")
under.fill_color = QColor(0, 200, 0)
under.border_color = QColor(0, 200, 0)
under.layer_id = l0
shot2 = ImageItem((40, 40), (160, 160), solid_pm((30, 60, 220)))
shot2.layer_id = l_img
cv3.items.extend([under, shot2])
above = cv3.add_shape_item((85, 85), (115, 115), "rect")
above.fill_color = QColor(0, 0, 0)
above.border_color = QColor(0, 0, 0)
above.layer_id = l_above
cv3.items.append(above)
out3 = cv3.render_export()
c_under = QColor(out3.pixelColor(55, 55))
c_above = QColor(out3.pixelColor(100, 100))
check(c_under.blue() > c_under.green() + 60,
      "element below screenshot is occluded by it")
check(c_above.red() < 40 and c_above.blue() < 40 and c_above.green() < 40,
      "element above screenshot shows on top of it")

# 屏幕绘制路径不得因元素缺少 visible 属性而抛错（截图闪退回归点）
_screen_ok = True
try:
    for _ in range(8):
        _img = QImage(220, 220, QImage.Format.Format_ARGB32)
        _img.fill(QColor(255, 255, 255))
        _p = QPainter(_img)
        cv3._paint_layers(_p)
        cv3._paint_layer_highlight(_p)
        cv3._paint_shape_handles(_p)
        cv3._paint_preview(_p)
        _p.end()
except Exception as _e:  # noqa: BLE001
    _screen_ok = False
    print("   screen paint raised:", _e)
check(_screen_ok, "screen paint path never raises (screenshot crash regression)")

# BelowFlattener 健壮性：快照可重复累积、活动 painter 下安全转换、超大尺寸不崩
from annotator.flatten import BelowFlattener
_fl = BelowFlattener(base_red, 200, 200)
check(_fl.usable, "flattener usable on normal size")
_s1 = _fl.snapshot(); check(not _s1.isNull(), "first snapshot non-null")
# 快照后仍能继续叠加并再次取快照（suspend/resume 正确）
class _Stub:
    def paint(self, p, export=False):
        from PyQt6.QtGui import QBrush
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(0, 0, 0)))
        p.drawRect(QRectF(0, 0, 20, 20))
_fl.paint_below(_Stub())
_s2 = _fl.snapshot(); check(not _s2.isNull(), "second snapshot after resume non-null")
check(QColor(_s2.toImage().pixelColor(10, 10)).red() == 0,
      "content added between snapshots is accumulated")
_fl.end()
from annotator.flatten import _MAX_DIM
_big = BelowFlattener(None, 10 ** 9, 10 ** 9)
check(_big.usable and _big._w <= _MAX_DIM and _big._h <= _MAX_DIM,
      f"oversize flattener is clamped to cap instead of crashing ({_big._w},{_big._h})")
_big.end()

# ---------------------------------------------------------------- 5. panel
print("[5] shape panel Office 7 categories")
from annotator.panel import StylePanel
panel = StylePanel(cv3)
cats = shape_categories()
check(len(panel._shape_cat_headers) == 7,
      f"category headers = 7 (got {len(panel._shape_cat_headers)})")
titles = [t for _, t, _ in cats]
check(titles == ["基本形状", "箭头汇总", "公式形状", "流程图",
                 "星与旗帜", "标注", "括号"], f"category titles/order {titles}")
all_vals = [v for _, _, cs in cats for _, v in cs]
check(len(all_vals) == len(set(all_vals)) == len(SHAPE_OPTIONS),
      "every shape classified exactly once")
check(len(panel._shape_buttons) == len(SHAPE_OPTIONS), "every shape has a button")
panel._set_shape_val("divide")
check(not panel._shape_cat_widgets["formula"].isHidden(),
      "selecting a shape auto-expands its category")
panel._shape_cat_headers["formula"].setChecked(False)
check(panel._shape_cat_widgets["formula"].isHidden(),
      "category header collapses its grid")

# ---------------------------------------------------------------- 6. widths
print("[6] right panel widths and scrollbar")
from annotator.window import MainWindow
w = MainWindow(restore=False)
check(w.right_box.minimumWidth() == 180,
      f"right panel minimum width = 180 (got {w.right_box.minimumWidth()})")
ss = w.panel_scroll.styleSheet().replace(" ", "")
check("width:34px" in ss, "vertical scrollbar doubled to 34px")

# ---------------------------------------------------------------- 7. serialize
print("[7] tail_apex serialization and legacy compat")
s = ShapeItem((10, 10), (90, 90), shape="rectcallout")
s.set_tail_apex(QPointF(33, 150))
back = deserialize_items(serialize_items([s]))
check(back[0].tail_apex is not None and
      abs(back[0].tail_apex.x() - 33) < 1e-6 and
      abs(back[0].tail_apex.y() - 150) < 1e-6, "tail_apex roundtrip")
old_item = {
    "type": "shape", "shape": "rectcallout", "p1": [0, 0], "p2": [100, 100],
    "border_color": [255, 0, 0, 255], "fill_color": [0, 0, 0, 0],
    "line_width": 2, "tail_x": 0.2, "tail_len": 0.4}
ob = deserialize_items([old_item])
ap2 = ob[0].tail_apex_point()
check(abs(ap2.x() - 20) < 1e-6 and abs(ap2.y() - 140) < 1e-6,
      f"legacy archive migrates (got {ap2.x()},{ap2.y()})")

print()
if FAILS:
    print(f"==== {len(FAILS)} FAILED ====")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("==== R29 ALL REGRESSION PASSED ====")
