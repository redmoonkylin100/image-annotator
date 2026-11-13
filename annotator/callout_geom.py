# -*- coding: utf-8 -*-
"""标注类形状（Callout）小尾巴几何 —— Office 风格（本轮新增，纯函数模块）。

设计目标（对应需求 2/3）：
- 主体（矩形/菱形/椭圆/多边形）尺寸恒定，不随尾尖拖动而变形；
- 尾尖 apex 可在未旋转图片坐标系中【任意拖动】，角度与长度自由；
- 系统自动判断尾尖最靠近主体的哪条边（上/下/左/右，多边形为任意边，
  椭圆为弧），尾巴根部自动落到最近边上；
- 根部两个点始终钳制在边（弧）的范围内，不会出现缺口跑到轮廓外；
- 根心偏向主体中心：尖点偏左则根整体偏右、尖点偏右则根整体偏左，
  两条斜边自然不等长，尖角随尖点位置变化（与 Office 一致）。

本模块只做几何计算，不依赖 QPainter，便于单元测试。
"""

import math

from PyQt6.QtCore import QPointF, QRectF

# 根点距边端点的最小留白（边长比例），保证根点不会顶到角上
EDGE_MARGIN = 0.06
# 根心向边中心回收的比例：0=根心正对尖点投影，1=根心恒在边中点
ROOT_BIAS = 0.5
# 根点半宽占边长的比例（两个根点间距 = 2*HALF_RATIO*边长）
HALF_RATIO = 0.08


def vlen(x: float, y: float) -> float:
    return math.hypot(x, y)


def dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    """点 p 到线段 ab 的距离。"""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0.0 and dy == 0.0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = a.x() + t * dx, a.y() + t * dy
    return math.hypot(p.x() - cx, p.y() - cy)


def nearest_edge(verts, apex: QPointF):
    """在闭合多边形 verts 中找距 apex 最近的边。

    返回 (edge_idx, t)：edge_idx 为边起点下标（终点为 (i+1)%n），
    t 为 apex 在该边上的投影参数（已钳制到 [0,1]）。
    """
    n = len(verts)
    best_i, best_d, best_t = 0, None, 0.0
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if dx == 0.0 and dy == 0.0:
            t = 0.0
            d = math.hypot(apex.x() - a.x(), apex.y() - a.y())
        else:
            t = ((apex.x() - a.x()) * dx + (apex.y() - a.y()) * dy) / (dx * dx + dy * dy)
            tc = max(0.0, min(1.0, t))
            cx, cy = a.x() + tc * dx, a.y() + tc * dy
            d = math.hypot(apex.x() - cx, apex.y() - cy)
        if best_d is None or d < best_d:
            best_d, best_i, best_t = d, i, max(0.0, min(1.0, t))
    return best_i, best_t


def edge_roots(verts, edge_idx: int, proj_t: float,
               half_ratio: float = HALF_RATIO,
               margin: float = EDGE_MARGIN,
               bias: float = ROOT_BIAS):
    """在指定边上计算两个根点（沿边方向：root1 偏起点、root2 偏终点）。

    根心 = 边中点 + bias*(投影点-边中点)，即把根心从尖点正投影处向边
    中心回收；根宽固定为 2*half_ratio*边长，并整体钳制在 [margin,1-margin]
    范围内，越界时自动收窄，保证两个根点永远落在边内部。
    """
    n = len(verts)
    a = verts[edge_idx]
    b = verts[(edge_idx + 1) % n]
    ex, ey = b.x() - a.x(), b.y() - a.y()
    elen = math.hypot(ex, ey)
    if elen < 1e-9:
        return QPointF(a), QPointF(a)
    # 根心参数（偏向边中心 0.5）
    center_t = 0.5 + (proj_t - 0.5) * bias
    half_t = half_ratio
    lo, hi = margin, 1.0 - margin
    # 可用宽度不足时收窄根宽，再整体钳制
    max_half = max(0.0, (hi - lo) / 2.0)
    half_t = min(half_t, max_half)
    t1 = center_t - half_t
    t2 = center_t + half_t
    if t1 < lo:
        t2 += lo - t1
        t1 = lo
    if t2 > hi:
        t1 -= t2 - hi
        t2 = hi
    t1 = max(lo, t1)
    t2 = min(hi, t2)
    root1 = QPointF(a.x() + t1 * ex, a.y() + t1 * ey)
    root2 = QPointF(a.x() + t2 * ex, a.y() + t2 * ey)
    return root1, root2


def polygon_tail(verts, apex: QPointF, half_ratio: float = HALF_RATIO):
    """多边形主体：返回 (edge_idx, root1, root2)。"""
    ei, t = nearest_edge(verts, apex)
    r1, r2 = edge_roots(verts, ei, t, half_ratio=half_ratio)
    return ei, r1, r2


def point_in_polygon(verts, pt: QPointF) -> bool:
    """射线法判断点是否在闭合多边形内（含边界）。"""
    n = len(verts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = verts[i].x(), verts[i].y()
        xj, yj = verts[j].x(), verts[j].y()
        if ((yi > pt.y()) != (yj > pt.y())):
            x_cross = xi + (pt.y() - yi) * (xj - xi) / (yj - yi)
            if pt.x() < x_cross:
                inside = not inside
        j = i
    return inside


def rect_vertices(r: QRectF):
    """顺时针矩形顶点：左上、右上、右下、左下。"""
    return [QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
            QPointF(r.right(), r.bottom()), QPointF(r.left(), r.bottom())]


def ellipse_roots(r: QRectF, apex: QPointF, half_ratio: float = 0.12):
    """椭圆主体：尾尖方向与椭圆弧的交点 anchor 为根心中点，
    沿切线向两侧取根点（近似落在弧上，同色填充后视觉无缝）。

    返回 (root1, root2, anchor)。apex 与中心重合时默认朝下。
    """
    cx, cy = r.center().x(), r.center().y()
    a = max(r.width() / 2.0, 1e-6)
    b = max(r.height() / 2.0, 1e-6)
    dx, dy = (apex.x() - cx) / a, (apex.y() - cy) / b
    if dx == 0.0 and dy == 0.0:
        theta = math.pi / 2.0
    else:
        theta = math.atan2(dy, dx)
    anchor = QPointF(cx + a * math.cos(theta), cy + b * math.sin(theta))
    # anchor 处椭圆切向量（参数方程求导）
    tx, ty = -a * math.sin(theta), b * math.cos(theta)
    tl = math.hypot(tx, ty)
    if tl < 1e-9:
        tx, ty, tl = 1.0, 0.0, 1.0
    tx, ty = tx / tl, ty / tl
    off = min(a, b) * half_ratio
    return (QPointF(anchor.x() - tx * off, anchor.y() - ty * off),
            QPointF(anchor.x() + tx * off, anchor.y() + ty * off),
            anchor)


def point_in_ellipse(r: QRectF, pt: QPointF) -> bool:
    a = max(r.width() / 2.0, 1e-6)
    b = max(r.height() / 2.0, 1e-6)
    dx = (pt.x() - r.center().x()) / a
    dy = (pt.y() - r.center().y()) / b
    return dx * dx + dy * dy <= 1.0


def default_apex(r: QRectF) -> QPointF:
    """新建标注形状时的默认尾尖：底边偏左 30%、向下伸出 25% 高度。"""
    return QPointF(r.left() + r.width() * 0.30,
                   r.bottom() + r.height() * 0.25)
