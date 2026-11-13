# -*- coding: utf-8 -*-
"""r30 回归：标注形状尾巴根部贴合（椭圆/云形对齐矩形）+ 引线分区命中/光标。

离屏运行（无需 GUI 交互）：
    venv\\Scripts\\python.exe tests\\regression_r30_callout.py
覆盖：
1. 矩形/椭圆/云形/菱形标注路径均为【单一连续封闭子路径】（仅 1 个 moveTo）；
2. 椭圆根点严格落在椭圆弧上、云形根点严格落在云朵底边直线上；
3. 路径尾部序列为 root2 -> apex -> root1（根部不封口、无 root1-root2 连接线）；
4. 光栅化：根部内外连续填充、根缝处无描边连接线；
5. 引线 hit_test 分区：target / text / hline(横线) / dline(斜线)；
   move_by：hline/text 只动文字、target 只动端点、dline 整体移动；
6. 输出 _r30_callouts.png / _r30_leader_hit.png 供肉眼复核。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from annotator import items as I
from annotator.items import (shape_path, LeaderLineItem, ShapeItem,
                             SHAPE_RECT_CALLOUT, SHAPE_OVAL_CALLOUT,
                             SHAPE_CLOUD_CALLOUT, SHAPE_DIAMOND_CALLOUT)

PASS, FAIL = 0, 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK]", msg)
    else:
        FAIL += 1
        print("  [FAIL]", msg)


def path_points(path: QPainterPath):
    """展开为元素类型 + 点序列（曲线取其控制点/终点，足够做结构检查）。"""
    kinds, pts = [], []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        pts.append(QPointF(e.x, e.y))
        kinds.append(e.type)
    return kinds, pts


def count_move_to(path):
    n = 0
    for i in range(path.elementCount()):
        if path.elementAt(i).type == QPainterPath.ElementType.MoveToElement:
            n += 1
    return n


# ---------------- 1. 路径结构 ----------------
print("== 1. 标注形状路径结构（单一连续封闭、根部不封口） ==")
BODY = QRectF(100, 100, 300, 200)
# 云形尾尖避开底边起点 S0（x=160），以免根点被钳制到与 S0 重合
CASES = [
    ("矩形标注", SHAPE_RECT_CALLOUT, QPointF(180, 360)),
    ("椭圆标注", SHAPE_OVAL_CALLOUT, QPointF(180, 360)),
    ("云形标注", SHAPE_CLOUD_CALLOUT, QPointF(215, 360)),
    ("菱形标注", SHAPE_DIAMOND_CALLOUT, QPointF(180, 360)),
]
paths = {}
for name, shp, apex in CASES:
    p = shape_path(shp, BODY, apex)
    paths[name] = p
    check(count_move_to(p) == 1, f"{name}: 仅 1 个 moveTo（单一连续轮廓），实际 {count_move_to(p)}")
    kinds, pts = path_points(p)
    # 末尾应为 ... -> root2 -> apex -> root1（root1 即路径起点 pts[0]）
    check((pts[-2] - apex).manhattanLength() < 1e-6,
          f"{name}: 倒数第二个点是尾尖 apex")
    check((pts[-1] - pts[0]).manhattanLength() < 1e-6,
          f"{name}: 轮廓最终回到起点根点 root1（root2->apex->root1 闭合）")
    # root1/root2 不应直接相连（两点之间夹着 apex，不存在 root2->root1 的横边）
    root1, root2 = pts[-1], pts[-3]
    direct = False
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if kinds[i + 1] == QPainterPath.ElementType.LineToElement \
                and abs(a.y() - b.y()) < 1e-9 and abs(a.x() - b.x()) > 1e-9:
            # 水平线：若两端正好是两个根点（包围尾尖），即违规连接线
            if (a - root1).manhattanLength() < 1e-6 and (b - root2).manhattanLength() < 1e-6:
                direct = True
            if (a - root2).manhattanLength() < 1e-6 and (b - root1).manhattanLength() < 1e-6:
                direct = True
    check(not direct, f"{name}: root1-root2 之间没有水平连接线")

# 椭圆根点严格在弧上（按与实现相同的解析公式独立复算）
cx, cy = BODY.center().x(), BODY.center().y()
ea, eb = BODY.width() / 2, BODY.height() / 2
_dx, _dy = (180 - cx) / ea, (360 - cy) / eb
theta = math.atan2(_dy, _dx)
root_half = min(14.0, min(ea, eb) * 0.16)
rr = math.hypot(ea * math.sin(theta), eb * math.cos(theta))
dth = min(math.asin(min(0.999, root_half / rr)), math.radians(35.0))
ana_r1 = QPointF(cx + ea * math.cos(theta - dth), cy + eb * math.sin(theta - dth))
ana_r2 = QPointF(cx + ea * math.cos(theta + dth), cy + eb * math.sin(theta + dth))
for nm, rp in (("root1", ana_r1), ("root2", ana_r2)):
    v = ((rp.x() - cx) / ea) ** 2 + ((rp.y() - cy) / eb) ** 2
    check(abs(v - 1.0) < 1e-9, f"椭圆{nm} 严格落在椭圆弧上（方程值={v:.9f}）")
# arcTo 以贝塞尔逼近弧：弧终点（apex 前一元素）应与解析 root2 足够接近
_, opts = path_points(paths["椭圆标注"])
check((opts[-3] - ana_r2).manhattanLength() < 0.6,
      f"椭圆弧终点贴合解析根点 root2（偏差={(opts[-3] - ana_r2).manhattanLength():.4f}）")
check((opts[0] - ana_r1).manhattanLength() < 1e-6,
      "椭圆路径起点即解析根点 root1")

# 云形根点严格在底边直线 cloud_bottom 上
cp = paths["云形标注"]
cloud_bottom = BODY.bottom() - BODY.height() * 0.04
_, cpts = path_points(cp)
croot1, croot2 = cpts[-1], cpts[-3]
check(abs(croot1.y() - cloud_bottom) < 1e-6 and abs(croot2.y() - cloud_bottom) < 1e-6,
      f"云形两个根点落在云朵底边直线 y={cloud_bottom:.2f}")
s0 = QPointF(BODY.left() + BODY.width() * 0.20, cloud_bottom)
# root1 起步后沿底边接到 S0（若 root1 恰与 S0 重合，零长 lineTo 会被 Qt 丢弃）
ok_s0 = (cpts[0] - croot1).manhattanLength() < 1e-6 and (
        (cpts[1] - s0).manhattanLength() < 1e-6 or (cpts[0] - s0).manhattanLength() < 1e-6)
check(ok_s0, "云形轮廓 root1 起步后沿底边接到 S0")

# 尾尖在主体内时：椭圆/云形不画尾巴（完整主体、无向下三角形）
for name, shp in (("椭圆", SHAPE_OVAL_CALLOUT), ("云形", SHAPE_CLOUD_CALLOUT)):
    pin = shape_path(shp, BODY, QPointF(cx, cy))
    _, pipts = path_points(pin)
    check(all(q.y() < BODY.bottom() + 1 for q in pipts),
          f"{name}: 尾尖落在主体内时不生成向下尾巴")

# ---------------- 2. 光栅化：根部连续、无连接线 ----------------
print("== 2. 光栅化检查（根部填充连续、根缝无描边） ==")
FILL = QColor(150, 255, 120)
BORDER = QColor(60, 60, 220)


def render_shape(shp, apex, size=3):
    r = QRectF(120, 120, 360, 240)
    path = shape_path(shp, r, apex)
    img = QImage(int(r.width() + 160) * size, int(r.height() + 200) * size,
                 QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.scale(size, size)
    p.translate(-r.x() + 40, -r.y() + 40)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(BORDER, 2, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(FILL)
    p.drawPath(path)
    p.end()
    return img, r


def is_blue(c):
    return c.blue() > 150 and c.red() < 120 and c.green() < 120


def is_fill(c):
    return abs(c.red() - FILL.red()) < 30 and abs(c.green() - FILL.green()) < 30 \
        and abs(c.blue() - FILL.blue()) < 30


for name, shp in (("椭圆", SHAPE_OVAL_CALLOUT), ("云形", SHAPE_CLOUD_CALLOUT)):
    r = QRectF(120, 120, 360, 240)
    apex = QPointF(200, r.bottom() + 70)
    img, rr = render_shape(shp, apex, size=3)
    # 重新计算根点位置
    pp = shape_path(shp, rr, apex)
    _, qs = path_points(pp)
    r1, r2 = qs[-1], qs[-3]
    root_y = (r1.y() + r2.y()) / 2
    mid_x = (r1.x() + r2.x()) / 2
    S = 3
    ox, oy = 40 - rr.x(), 40 - rr.y()

    def px(x, y):
        return img.pixelColor(int((x + ox) * S), int((y + oy) * S))

    # 根缝内侧（主体内 3px）= 填充色；外侧尾巴三角内 6px = 填充色（连续）
    check(is_fill(px(mid_x, root_y - 3)), f"{name}: 根缝内侧为主体填充色（无空白缺口）")
    check(is_fill(px(mid_x, root_y + 6)), f"{name}: 根缝外侧尾巴三角为填充色（根部无空白）")
    # 根缝处不应有蓝色连接线：在 root1/root2 之间、边界线上下 1px 的细条里统计蓝像素
    blue = 0
    x0, x1 = int((min(r1.x(), r2.x()) + 4 + ox) * S), int((max(r1.x(), r2.x()) - 4 + ox) * S)
    for yy in (root_y - 0.8, root_y, root_y + 0.8):
        iy = int((yy + oy) * S)
        for ix in range(x0, x1):
            if is_blue(img.pixelColor(ix, iy)):
                blue += 1
    total = max(1, (x1 - x0) * 3)
    check(blue / total < 0.04, f"{name}: 根缝处无蓝色连接线（蓝像素占比 {blue/total:.3f}）")

# ---------------- 3. 引线 hit_test 分区 + move_by ----------------
print("== 3. 引线 hit_test 分区 / move_by 语义 ==")


def mid(a, b, t=0.5):
    return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)


for style in ("above_text", "middle_text", "below_text", "no_line"):
    lead = LeaderLineItem((120, 420), (320, 180), "森岛帆高",
                          line_color="#7ED957", line_width=4, arrow_size=12,
                          endpoint_style="circle", label_style=style)
    corner, ls, le, tr = lead._get_leader_geometry(style)
    tol = 6.0
    # 端点
    check(lead.hit_test(QPointF(lead.target_point), tol) == "target",
          f"[{style}] 斜线端点 -> target")
    # 文字块中心
    check(lead.hit_test(tr.center(), tol) == "text",
          f"[{style}] 文字块 -> text")
    # 横线中点（above/below 横线紧贴文字 5px，落在文字扩展容差内时 text 等价）
    hmid = mid(ls, le)
    if (le - ls).manhattanLength() > 0.5:
        got_h = lead.hit_test(hmid, tol)
        want_h = ("hline", "text") if style in ("above_text", "below_text", "no_line") else ("hline",)
        check(got_h in want_h, f"[{style}] 横线 -> hline（实际 {got_h}）")
    # 斜线中点
    dmid = mid(lead.target_point, corner)
    got = lead.hit_test(dmid, tol)
    check(got == "dline", f"[{style}] 斜线 -> dline（实际 {got}）")

    # move_by 语义
    t0, x0 = QPointF(lead.target_point), QPointF(lead.text_point)
    lead.move_by(10, 0, "hline")
    check((lead.target_point - t0).manhattanLength() < 1e-9
          and abs(lead.text_point.x() - (x0.x() + 10)) < 1e-9,
          f"[{style}] hline 只移动文字位置")
    lead.move_by(10, 0, "dline")
    check(abs(lead.target_point.x() - (t0.x() + 10)) < 1e-9
          and abs(lead.text_point.x() - (x0.x() + 20)) < 1e-9,
          f"[{style}] dline 整体平移（端点+文字）")
    lead.move_by(5, 0, "target")
    check(abs(lead.target_point.x() - (t0.x() + 15)) < 1e-9
          and abs(lead.text_point.x() - (x0.x() + 20)) < 1e-9,
          f"[{style}] target 只移动端点")

# 旧 STYLE_ABOVE 仍返回 'line'（兼容）
old = LeaderLineItem((0, 0), (60, 60), "旧样式", label_style="above")
gi, go, _ = old._above_geometry()
check(old.hit_test(mid(old.target_point, gi), 6) == "line",
      "[above 旧样式] 仍返回 line（向后兼容）")

# ---------------- 4. 预览图 ----------------
print("== 4. 输出预览图 ==")
outdir = os.path.dirname(os.path.abspath(__file__))


def draw_three(outname):
    from PyQt6.QtGui import QFont
    # 上排：三个完整标注；下排：各自根部 3x 放大
    W, H = 1500, 1000
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bw, bh = 420, 260
    specs = [
        ("rect callout", SHAPE_RECT_CALLOUT, QPointF(150, 330)),
        ("oval callout", SHAPE_OVAL_CALLOUT, QPointF(650, 360)),
        ("cloud callout", SHAPE_CLOUD_CALLOUT, QPointF(1150, 360)),
    ]
    rects = []
    for i, (nm, shp, ap) in enumerate(specs):
        x = 40 + i * 490
        r = QRectF(x, 70, bw, bh)
        rects.append((nm, shp, r, ap))
        p.setPen(QPen(BORDER, 1.6))
        p.setBrush(FILL)
        p.drawPath(shape_path(shp, r, ap))
        p.setPen(QColor(20, 20, 20))
        p.setFont(QFont("Arial", 14))
        p.drawText(QRectF(x, r.bottom() + 90, bw, 24),
                   Qt.AlignmentFlag.AlignHCenter, nm)
    # 根部放大
    zoom = 3
    for i, (nm, shp, r, ap) in enumerate(rects):
        pp = shape_path(shp, r, ap)
        _, qs = path_points(pp)
        r1, r2 = qs[-1], qs[-3]
        br = QRectF(min(r1.x(), r2.x()) - 30, min(r1.y(), r2.y(), ap.y()) - 16,
                    abs(r2.x() - r1.x()) + 60, abs(ap.y() - min(r1.y(), r2.y())) + 32)
        tx, ty = 40 + i * 490, 560
        p.save()
        p.setClipRect(tx, ty, int(br.width() * zoom), int(br.height() * zoom))
        p.translate(tx, ty)
        p.scale(zoom, zoom)
        p.translate(-br.x(), -br.y())
        p.setPen(QPen(BORDER, 1.4))
        p.setBrush(FILL)
        p.drawPath(shape_path(shp, r, ap))
        p.restore()
        p.setPen(QPen(QColor(200, 0, 0), 1.0, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(tx, ty, int(br.width() * zoom), int(br.height() * zoom))
        p.setPen(QColor(200, 0, 0))
        p.setFont(QFont("Arial", 12))
        p.drawText(tx, ty - 8, f"{nm} tail root x{zoom}")
    p.end()
    img.save(os.path.join(outdir, outname))
    print("  saved", outname)


def draw_leader_zones(outname):
    W, H = 1000, 700
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(QColor(45, 48, 52))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    lead = LeaderLineItem((200, 560), (560, 120), "Label text",
                          line_color="#7ED957", line_width=6, arrow_size=14,
                          font_size=30, text_color="#C8FF7A",
                          endpoint_style="circle", label_style="above_text")
    lead.paint(p, export=True)
    corner, ls, le, tr = lead._get_leader_geometry("above_text")
    # 命中分区示意
    marks = [
        ("target endpoint: drag hand", lead.target_point, QColor(255, 120, 120)),
        ("hline: drag hand", mid(ls, le), QColor(255, 200, 80)),
        ("dline: move-all SizeAll", mid(lead.target_point, corner), QColor(120, 180, 255)),
        ("text: drag hand", tr.center(), QColor(200, 120, 255)),
    ]
    from PyQt6.QtGui import QFont
    p.setFont(QFont("Arial", 12))
    for i, (nm, pt, col) in enumerate(marks):
        p.setPen(QPen(col, 2))
        p.setBrush(col)
        p.drawEllipse(pt, 7, 7)
        p.setPen(QColor(245, 245, 245))
        p.drawText(int(pt.x()) + 12, int(pt.y()) + 4 + (i % 2) * 18, nm)
    p.end()
    img.save(os.path.join(outdir, outname))
    print("  saved", outname)


draw_three("_r30_callouts.png")
draw_leader_zones("_r30_leader_hit.png")

print(f"\n==== RESULT: PASS={PASS} FAIL={FAIL} ====")
sys.exit(1 if FAIL else 0)
