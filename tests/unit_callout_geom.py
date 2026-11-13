# -*- coding: utf-8 -*-
"""callout_geom 纯几何单元测试（不依赖 QApplication，只引入 QPointF/QRectF）。

覆盖：尾尖在主体内外、最近边选择、根点贴边与钳制、0/90/180/270/任意角旋转
等价性、文字区与尾尖重叠（主体内不生成尾巴）、退化尺寸兜底、左右/上下镜像
对称性、默认尾尖与基础距离函数。

离屏运行：venv\\Scripts\\python.exe tests\\unit_callout_geom.py
"""
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, QRectF

from annotator import callout_geom as cg

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def pclose(p, q, tol=1e-6):
    return close(p.x(), q.x(), tol) and close(p.y(), q.y(), tol)


def finite(p):
    return math.isfinite(p.x()) and math.isfinite(p.y())


def rot_about(pt, center, deg):
    """绕 center 旋转 deg 度（Qt 屏幕坐标，y 向下，角度顺时针）。"""
    rad = math.radians(deg)
    dx, dy = pt.x() - center.x(), pt.y() - center.y()
    return QPointF(center.x() + dx * math.cos(rad) - dy * math.sin(rad),
                   center.y() + dx * math.sin(rad) + dy * math.cos(rad))


def pt_param(a, b, p):
    """点 p 在 a→b 线段上的投影参数（不钳制）。"""
    ex, ey = b.x() - a.x(), b.y() - a.y()
    return ((p.x() - a.x()) * ex + (p.y() - a.y()) * ey) / (ex * ex + ey * ey)


def roots_on_edge(r1, r2, verts, ei, tol=1e-9):
    a, b = verts[ei], verts[(ei + 1) % len(verts)]
    return (cg.dist_to_segment(r1, a, b) <= tol and
            cg.dist_to_segment(r2, a, b) <= tol)


# ------------------------------------------------------------------ 基础
def test_矩形顶点顺时针():
    v = cg.rect_vertices(QRectF(5, 10, 100, 80))
    check(pclose(v[0], QPointF(5, 10)), "顶点0 = 左上 (5,10)")
    check(pclose(v[1], QPointF(105, 10)), "顶点1 = 右上 (105,10)")
    check(pclose(v[2], QPointF(105, 90)), "顶点2 = 右下 (105,90)")
    check(pclose(v[3], QPointF(5, 90)), "顶点3 = 左下 (5,90)")


def test_基础距离函数():
    check(close(cg.vlen(3, 4), 5.0), "vlen(3,4) = 5")
    a, b = QPointF(0, 0), QPointF(10, 0)
    check(close(cg.dist_to_segment(QPointF(5, 3), a, b), 3.0),
          "点到线段：垂足落在线段内，距离 3")
    check(close(cg.dist_to_segment(QPointF(-4, 3), a, b), 5.0),
          "点到线段：超出起点时钳制到端点，距离 5")
    check(close(cg.dist_to_segment(QPointF(14, 3), a, b), 5.0),
          "点到线段：超出终点时钳制到端点，距离 5")
    check(close(cg.dist_to_segment(QPointF(2, 2), a, a), math.hypot(2, 2)),
          "退化线段（a==b）退化为点距")


# ------------------------------------------------------- 尾尖在框内 / 框外
def test_尾尖在框内():
    r = QRectF(0, 0, 100, 80)
    verts = cg.rect_vertices(r)
    check(cg.point_in_polygon(verts, QPointF(50, 40)),
          "矩形内部点（文字区中心）判定为内部")
    check(cg.point_in_polygon(verts, QPointF(50, 1)),
          "贴上边界的内部点判定为内部")
    check(cg.point_in_polygon(verts, QPointF(99.5, 79.5)),
          "右下方内部点判定为内部")
    check(not cg.point_in_polygon(verts, QPointF(50, 85)),
          "下边界外 5px 的尾尖判定为外部（需要画尾巴）")
    check(not cg.point_in_polygon(verts, QPointF(-1, 40)),
          "左边界外 1px 的尾尖判定为外部")
    check(cg.point_in_ellipse(r, QPointF(50, 40)),
          "椭圆中心判定为内部")
    check(cg.point_in_ellipse(r, QPointF(100, 40)),
          "椭圆右端点（边界）判定为内部（<=1 含边界）")
    check(not cg.point_in_ellipse(r, QPointF(0, 0)),
          "外接矩形角点判定为椭圆外部")
    check(not cg.point_in_ellipse(r, QPointF(50, 82)),
          "椭圆下侧外 2px 判定为外部")


def test_尾尖在框外_最近边():
    verts = cg.rect_vertices(QRectF(0, 0, 100, 80))
    cases = [(QPointF(-200, 200), 2, "左下方远处 → 底边"),
             (QPointF(50, -50), 0, "正上方 → 上边"),
             (QPointF(-50, 40), 3, "正左方 → 左边"),
             (QPointF(150, 40), 1, "正右方 → 右边"),
             (QPointF(50, 200), 2, "正下方 → 底边")]
    for ap, want, label in cases:
        ei, t = cg.nearest_edge(verts, ap)
        check(ei == want, label + f"（实际 {ei}）")
        check(0.0 <= t <= 1.0, label + f" 的投影参数落在 [0,1]（实际 {t:.3f}）")


# ------------------------------------------------------- 根点贴边与钳制
def test_根点贴边与钳制():
    verts = cg.rect_vertices(QRectF(0, 0, 100, 80))
    for ap, want in ((QPointF(50, 200), 2), (QPointF(50, -50), 0),
                     (QPointF(-50, 40), 3), (QPointF(150, 40), 1)):
        ei, t = cg.nearest_edge(verts, ap)
        r1, r2 = cg.edge_roots(verts, ei, t)
        check(ei == want, f"最近边下标 = {want}（实际 {ei}）")
        check(roots_on_edge(r1, r2, verts, ei),
              f"边 {ei} 的两个根点严格落在该边上")
        a, b = verts[ei], verts[(ei + 1) % len(verts)]
        t1, t2 = pt_param(a, b, r1), pt_param(a, b, r2)
        check(t1 >= cg.EDGE_MARGIN - 1e-9 and t2 <= 1.0 - cg.EDGE_MARGIN + 1e-9,
              f"边 {ei} 根点被钳制在 [6%,94%]（{t1:.3f},{t2:.3f}）")
        check(not pclose(r1, r2, 1e-9), f"边 {ei} 两个根点不重合")
    # 尖点偏左时根心向主体中心回收
    ei, t = cg.nearest_edge(verts, QPointF(-200, 200))
    r1, r2 = cg.edge_roots(verts, ei, t)
    check((r1.x() + r2.x()) / 2.0 > 0.0,
          f"尖点在最左时根心偏向主体中心（根心 x={(r1.x() + r2.x()) / 2.0:.1f}）")


# ------------------------------------------------------------ 旋转等价性
def _rotation_case(deg, want_ei, want_roots):
    verts = cg.rect_vertices(QRectF(0, 0, 100, 100))
    ctr = QPointF(50, 50)
    apex = QPointF(50, 150)
    ei0, t0 = cg.nearest_edge(verts, apex)
    br1, br2 = cg.edge_roots(verts, ei0, t0)
    ap = rot_about(apex, ctr, deg)
    ei, t = cg.nearest_edge(verts, ap)
    r1, r2 = cg.edge_roots(verts, ei, t)
    check(ei == want_ei, f"{deg}° 旋转后最近边 = {want_ei}（实际 {ei}）")
    check(close(t, t0, 1e-9), f"{deg}° 旋转不改变边内投影参数（{t:.3f} vs {t0:.3f}）")
    check(pclose(r1, rot_about(br1, ctr, deg), 1e-9) and
          pclose(r2, rot_about(br2, ctr, deg), 1e-9),
          f"{deg}° 旋转后根点与「根点旋转」一致（等变）")
    check(pclose(r1, want_roots[0]) and pclose(r2, want_roots[1]),
          f"{deg}° 根点落在预期坐标 {want_roots[0]},{want_roots[1]}")


def test_旋转0度坐标映射():
    _rotation_case(0, 2, (QPointF(58, 100), QPointF(42, 100)))


def test_旋转90度坐标映射():
    _rotation_case(90, 3, (QPointF(0, 58), QPointF(0, 42)))


def test_旋转180度坐标映射():
    _rotation_case(180, 0, (QPointF(42, 0), QPointF(58, 0)))


def test_旋转270度坐标映射():
    _rotation_case(270, 1, (QPointF(100, 42), QPointF(100, 58)))


def test_任意角旋转坐标映射():
    """任意角：callout_geom 收到的是未旋转坐标系下的尾尖，
    「旋转」只发生在绘制阶段，因此这里校验旋转后的尾尖仍映射到
    真正最近的边，并验证叠加半圈（180°）后的严格等变。"""
    verts = cg.rect_vertices(QRectF(0, 0, 100, 100))
    ctr = QPointF(50, 50)
    apex = QPointF(50, 150)
    deg = 20.0
    ap = rot_about(apex, ctr, deg)
    ei, t = cg.nearest_edge(verts, ap)
    # 暴力求最近边，确认最近边选择正确
    ds = [cg.dist_to_segment(ap, verts[i], verts[(i + 1) % 4]) for i in range(4)]
    check(close(ds[ei], min(ds), 1e-9),
          f"20° 旋转后所选边确为最近边（d={ds[ei]:.3f}, min={min(ds):.3f}）")
    check(0.0 <= t <= 1.0, f"20° 旋转后投影参数落在 [0,1]（{t:.3f}）")
    r1, r2 = cg.edge_roots(verts, ei, t)
    check(roots_on_edge(r1, r2, verts, ei),
          "20° 旋转后两个根点仍严格落在所选边上")
    check(not pclose(r1, r2), "20° 旋转后两个根点不重合")
    # 再旋转 180°：边下标 +2、投影参数不变、根点严格等变
    ap2 = rot_about(ap, ctr, 180)
    ei2, t2 = cg.nearest_edge(verts, ap2)
    check(ei2 == (ei + 2) % 4,
          f"再旋转 180° 后最近边为对边（{ei}→{ei2}）")
    check(close(t2, t, 1e-9), f"再旋转 180° 后投影参数不变（{t2:.3f}）")
    q1, q2 = cg.edge_roots(verts, ei2, t2)
    check(pclose(q1, rot_about(r1, ctr, 180), 1e-9) and
          pclose(q2, rot_about(r2, ctr, 180), 1e-9),
          "任意角 + 180° 组合下根点等变")


# --------------------------------------------------- 文字排版与尾尖重叠
def test_文字区与尾尖重叠():
    """文字块整体位于主体内部；尾尖压到文字区时仍判为「主体内部」，
    调用方（items._rect_callout_path / _ellipse_callout_path / _polygon_callout_path）
    据此不生成尾巴，避免文字被尾巴斜边切开。"""
    body = cg.rect_vertices(QRectF(0, 0, 200, 120))
    text_rect = QRectF(40, 40, 120, 60)
    check(cg.point_in_polygon(body, text_rect.center()),
          "尾尖压住文字中心 → 判为主体内部（不画尾巴）")
    for pt in (QPointF(text_rect.left(), text_rect.top()),
               QPointF(text_rect.right(), text_rect.top()),
               QPointF(text_rect.right(), text_rect.bottom()),
               QPointF(text_rect.left(), text_rect.bottom())):
        check(cg.point_in_polygon(body, pt),
              f"尾尖压住文字角点 ({pt.x():.0f},{pt.y():.0f}) → 判为主体内部")
    check(not cg.point_in_polygon(body, QPointF(100, 121)),
          "尾尖移出主体下边界 → 判为外部（恢复画尾巴）")
    check(cg.point_in_ellipse(QRectF(0, 0, 200, 120), text_rect.center()),
          "椭圆主体：尾尖压住文字中心 → 判为椭圆内部")


# ------------------------------------------------------------ 退化尺寸兜底
def test_退化尺寸_宽为零():
    verts = cg.rect_vertices(QRectF(50, 0, 0, 80))
    check(len(verts) == 4, "宽为 0 的矩形仍返回 4 个顶点")
    ei, t = cg.nearest_edge(verts, QPointF(60, 40))
    check(0 <= ei < 4 and 0.0 <= t <= 1.0,
          f"宽为 0 时最近边合法（ei={ei}, t={t:.3f}）")
    d1, d2 = cg.edge_roots(verts, 0, 0.5)
    check(pclose(d1, verts[0]) and pclose(d2, verts[0]),
          "零长度边（上边退化）根点退化为端点自身")
    r1, r2 = cg.edge_roots(verts, 1, 0.5)
    check(finite(r1) and finite(r2) and not pclose(r1, r2),
          "非零长度的竖向边仍能得到两个不同的有效根点")


def test_退化尺寸_高为零():
    verts = cg.rect_vertices(QRectF(0, 40, 100, 0))
    ei, t = cg.nearest_edge(verts, QPointF(50, 60))
    check(0 <= ei < 4 and 0.0 <= t <= 1.0,
          f"高为 0 时最近边合法（ei={ei}, t={t:.3f}）")
    d1, d2 = cg.edge_roots(verts, 1, 0.5)
    check(pclose(d1, verts[1]) and pclose(d2, verts[1]),
          "零长度边（右边退化）根点退化为端点自身")
    h1, h2 = cg.edge_roots(verts, 0, 0.5)
    check(finite(h1) and finite(h2),
          "非零长度的横向边根点坐标有限")


def test_退化尺寸_极小矩形():
    verts = cg.rect_vertices(QRectF(0, 0, 1e-12, 1e-12))
    d1, d2 = cg.edge_roots(verts, 0, 0.5)
    check(pclose(d1, verts[0]) and pclose(d2, verts[0]),
          "边长 1e-12（<1e-9）时根点退化为端点，不产生除零")
    tiny = cg.rect_vertices(QRectF(0, 0, 0.5, 0.5))
    r1, r2 = cg.edge_roots(tiny, 0, 0.5)
    a, b = tiny[0], tiny[1]
    t1, t2 = pt_param(a, b, r1), pt_param(a, b, r2)
    check(0.0 <= t1 < t2 <= 1.0 and finite(r1) and finite(r2),
          f"0.5px 极小矩形根点仍在边内（t={t1:.2f},{t2:.2f}）")


def test_退化尺寸_椭圆():
    for r in (QRectF(0, 0, 0, 0), QRectF(0, 0, 100, 0), QRectF(0, 0, 0, 80)):
        r1, r2, anchor = cg.ellipse_roots(r, QPointF(10, 10))
        check(finite(r1) and finite(r2) and finite(anchor),
              f"退化椭圆 {r.width():g}x{r.height():g} 的根点/锚点均为有限值")
        check(cg.point_in_ellipse(r, r.center()),
              f"退化椭圆 {r.width():g}x{r.height():g} 中心仍判为内部")


# -------------------------------------------------------------- 镜像对称
def test_左右镜像():
    verts = cg.rect_vertices(QRectF(0, 0, 100, 80))
    ei_l, t_l = cg.nearest_edge(verts, QPointF(20, 120))
    ei_r, t_r = cg.nearest_edge(verts, QPointF(80, 120))
    rl1, rl2 = cg.edge_roots(verts, ei_l, t_l)
    rr1, rr2 = cg.edge_roots(verts, ei_r, t_r)
    check(ei_l == ei_r == 2, f"左右镜像尾尖都落在底边（{ei_l},{ei_r}）")
    check(close(rl1.x(), 100.0 - rr2.x()) and close(rl2.x(), 100.0 - rr1.x()),
          f"左右镜像：根点严格互为镜像（{rl1.x():.1f},{rl2.x():.1f} ↔ "
          f"{rr1.x():.1f},{rr2.x():.1f}）")
    check(close(rl1.y(), 80.0) and close(rr1.y(), 80.0),
          "左右镜像后根点仍在底边 y=80")
    # 椭圆主体：方向与根点同样镜像
    el1, el2, al = cg.ellipse_roots(QRectF(0, 0, 100, 80), QPointF(150, 40))
    er1, er2, ar = cg.ellipse_roots(QRectF(0, 0, 100, 80), QPointF(-50, 40))
    check(close(al.x(), 100.0 - ar.x()) and close(al.y(), ar.y()),
          "椭圆锚点左右镜像")
    check(close(el1.x(), 100.0 - er1.x()) and close(el1.y(), er2.y()) and
          close(el2.y(), er1.y()),
          "椭圆根点左右镜像且顺序反转")


def test_上下镜像():
    verts = cg.rect_vertices(QRectF(0, 0, 100, 80))
    ei_t, t_t = cg.nearest_edge(verts, QPointF(30, -20))
    ei_b, t_b = cg.nearest_edge(verts, QPointF(30, 100))
    rt1, rt2 = cg.edge_roots(verts, ei_t, t_t)
    rb1, rb2 = cg.edge_roots(verts, ei_b, t_b)
    check(ei_t == 0 and ei_b == 2, f"上下镜像尾尖分别落在上/下边（{ei_t},{ei_b}）")
    check(close(rt1.x(), rb2.x()) and close(rt2.x(), rb1.x()),
          f"上下镜像：根点 x 互为镜像且顺序反转（上 {rt1.x():.1f},{rt2.x():.1f}"
          f" / 下 {rb1.x():.1f},{rb2.x():.1f}）")
    check(close(rt1.y(), 0.0) and close(rb1.y(), 80.0),
          "上下镜像后根点分别贴上/下边")


# -------------------------------------------------------- 多边形与默认尾尖
def test_多边形尾尖落边():
    diamond = [QPointF(50, 0), QPointF(100, 50),
               QPointF(50, 100), QPointF(0, 50)]
    apex = QPointF(5, 5)
    check(not cg.point_in_polygon(diamond, apex), "菱形外部尾尖判为外部")
    ei, r1, r2 = cg.polygon_tail(diamond, apex, half_ratio=0.08)
    check(ei == 3, f"菱形尾尖最近边 = 3（左上斜边，实际 {ei}）")
    check(roots_on_edge(r1, r2, diamond, ei),
          "菱形两个根点严格落在斜边上（不是外接矩形）")
    check(not pclose(r1, r2), "菱形两个根点不重合")
    check(cg.point_in_polygon(diamond, QPointF(50, 50)),
          "菱形中心判为内部（尾尖在内时不画尾巴）")


def test_默认尾尖位置():
    ap = cg.default_apex(QRectF(10, 20, 200, 100))
    check(close(ap.x(), 70.0), f"默认尾尖 x = 左边 + 30% 宽（实际 {ap.x():.1f}）")
    check(close(ap.y(), 145.0), f"默认尾尖 y = 底边 + 25% 高（实际 {ap.y():.1f}）")


def test_椭圆根点方向():
    r = QRectF(0, 0, 100, 80)
    r1, r2, anchor = cg.ellipse_roots(r, QPointF(150, 40))
    check(pclose(anchor, QPointF(100, 40)),
          f"尾尖在正右 → 锚点落在右弧 (100,40)（实际 {anchor.x():.1f},{anchor.y():.1f}）")
    check(close(r1.y(), 40.0 - 4.8) and close(r2.y(), 40.0 + 4.8),
          "右弧切线竖直 → 两个根点沿切线上下对称")
    check(close(abs(r1.y() - anchor.y()), abs(r2.y() - anchor.y())),
          "两个根点相对锚点等距")
    r1c, r2c, anchor_c = cg.ellipse_roots(r, r.center())
    check(pclose(anchor_c, QPointF(50, 80)),
          f"尾尖与中心重合 → 默认朝下锚点 (50,80)（实际 {anchor_c.x():.1f},{anchor_c.y():.1f}）")
    check(close(r1c.y(), 80.0) and close(r2c.y(), 80.0),
          "默认朝下时两个根点都落在底弧切线 y=80 上")
    # 外接矩形内、椭圆外的尾尖：仍需尾巴，锚点必须落在椭圆弧上
    corner_apex = QPointF(0, 0)
    check((not cg.point_in_ellipse(r, corner_apex)) and r.contains(corner_apex),
          "外接矩形角点在矩形内但在椭圆外（需要画尾巴）")
    a1, a2, anc = cg.ellipse_roots(r, corner_apex)
    dx = (anc.x() - 50.0) / 50.0
    dy = (anc.y() - 40.0) / 40.0
    check(close(dx * dx + dy * dy, 1.0, 1e-9),
          f"左上角尾尖的锚点严格落在椭圆弧上（{anc.x():.2f},{anc.y():.2f}）")


TESTS = [
    test_矩形顶点顺时针,
    test_基础距离函数,
    test_尾尖在框内,
    test_尾尖在框外_最近边,
    test_根点贴边与钳制,
    test_旋转0度坐标映射,
    test_旋转90度坐标映射,
    test_旋转180度坐标映射,
    test_旋转270度坐标映射,
    test_任意角旋转坐标映射,
    test_文字区与尾尖重叠,
    test_退化尺寸_宽为零,
    test_退化尺寸_高为零,
    test_退化尺寸_极小矩形,
    test_退化尺寸_椭圆,
    test_左右镜像,
    test_上下镜像,
    test_多边形尾尖落边,
    test_默认尾尖位置,
    test_椭圆根点方向,
]


def main():
    print("==== callout_geom 纯几何单元测试 ====")
    print(f"模块：{os.path.relpath(cg.__file__, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))}")
    for i, fn in enumerate(TESTS, 1):
        print(f"\n[{i:02d}] {fn.__name__[5:]}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILS.append(f"{fn.__name__} 抛出异常: {exc}")
            print(f"FAIL {fn.__name__} 抛出异常: {exc}", flush=True)
    print()
    if FAILS:
        print(f"==== {len(FAILS)} 项失败 / 共 {CHECKS[0]} 项断言 ====")
        for msg in FAILS:
            print(" -", msg)
        return 1
    print(f"==== 全部 PASS（{len(TESTS)} 个测试函数 / {CHECKS[0]} 项断言） ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
