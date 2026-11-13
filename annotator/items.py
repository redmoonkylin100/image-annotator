# -*- coding: utf-8 -*-
"""标注元素对象模型：引线标注、纯文本批注。

所有坐标均为「图片坐标」（与导出图片的像素坐标一致），
画布负责在绘制时进行 视图坐标 <-> 图片坐标 变换。
"""

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QImage, QLinearGradient,
                         QPainter, QPainterPath,
                         QPen, QPolygonF, QPixmap)

from . import callout_geom

FONT_FAMILY = "Microsoft YaHei"
TEXT_PAD_X = 7          # 文字背景框左右内边距
TEXT_PAD_Y = 4          # 文字背景框上下内边距
HANDLE_R = 5            # 选中时 target 点把手半边长
SELECT_COLOR = QColor(0, 120, 215)


def rot_point(p, c, deg: float):
    """点 p 绕中心 c 旋转 deg 度（图片坐标，纯函数）。"""
    import math as _m
    rad = _m.radians(deg)
    dx, dy = p.x() - c.x(), p.y() - c.y()
    return QPointF(c.x() + dx * _m.cos(rad) - dy * _m.sin(rad),
                   c.y() + dx * _m.sin(rad) + dy * _m.cos(rad))

# 形状类型（类似画图工具）
SHAPE_RECT = "rect"
SHAPE_LINE = "line"
SHAPE_ROUND_RECT = "roundrect"
SHAPE_ELLIPSE = "ellipse"
SHAPE_TRIANGLE = "triangle"
SHAPE_RIGHT_TRIANGLE = "righttriangle"
SHAPE_DIAMOND = "diamond"
SHAPE_PENTAGON = "pentagon"
SHAPE_HEXAGON = "hexagon"
SHAPE_STAR = "star"
SHAPE_ARROW = "arrow"
# v2.0 需求5：参考 Office 扩展的更多形状
SHAPE_LEFT_ARROW = "leftarrow"
SHAPE_UP_ARROW = "uparrow"
SHAPE_DOWN_ARROW = "downarrow"
SHAPE_LR_ARROW = "leftrightarrow"     # 左右双向箭头
SHAPE_UD_ARROW = "updownarrow"        # 上下双向箭头
SHAPE_HEART = "heart"
SHAPE_CLOUD = "cloud"
SHAPE_PARALLELOGRAM = "parallelogram"
SHAPE_TRAPEZOID = "trapezoid"
SHAPE_FOUR_STAR = "4star"             # 四角星/闪光
SHAPE_MOON = "moon"
SHAPE_CALLOUT = "callout"             # 圆角对话气泡
SHAPE_PLUS = "plus"                  # 十字/加号
# v2.1：参考 Office 形状库进一步扩充
SHAPE_HEPTAGON = "heptagon"          # 七边形
SHAPE_OCTAGON = "octagon"            # 八边形
SHAPE_DECAGON = "decagon"            # 十边形
SHAPE_DODECAGON = "dodecagon"        # 十二边形
SHAPE_STAR6 = "star6"                # 六角星
SHAPE_STAR8 = "star8"                # 八角星
SHAPE_STAR16 = "star16"              # 十六角星
SHAPE_STAR24 = "star24"              # 二十四角星
SHAPE_BRACE_L = "braceleft"          # 左大括号 {
SHAPE_BRACE_R = "braceright"         # 右大括号 }
SHAPE_BRACKET_L = "bracketleft"      # 左双括号
SHAPE_BRACKET_R = "bracketright"     # 右双括号
SHAPE_MINUS = "minus"                # 减号
SHAPE_TIMES = "times"                # 乘号
SHAPE_DIVIDE = "divide"              # 除号
SHAPE_EQUAL = "equal"                # 等号
SHAPE_NOTEQUAL = "notequal"         # 不等号
SHAPE_DONUT = "donut"                # 圆环
SHAPE_OPEN_ARC = "openarc"           # 空心弧（开口扇形）
SHAPE_CHEVRON = "chevron"            # 燕尾形
SHAPE_BENT_ARROW = "bentarrow"       # 直角（肘形）右箭头
SHAPE_CURVED_ARROW = "curvedarrow"   # 弧形右箭头
SHAPE_RIBBON = "ribbon"              # 波形横幅
SHAPE_BURST = "burst"                # 爆炸形
SHAPE_DOCUMENT = "document"         # 文档（波浪底边）
SHAPE_MULTIDOC = "multidoc"         # 多文档
SHAPE_STORAGE = "storage"           # 顺序存储（圆柱）
SHAPE_SMILEY = "smiley"             # 笑脸
SHAPE_LIGHTNING = "lightning"       # 闪电
SHAPE_SNIP = "snipe"                # 剪去单角矩形
SHAPE_CLOUD_CALLOUT = "cloudcallout"  # 云形标注
SHAPE_OVAL_CALLOUT = "ovalcallout"    # 椭圆标注
# v2.1：参考 Office 形状库进一步扩充（标注/卷轴/流程/旗帜/弧形箭头）
SHAPE_RECT_CALLOUT = "rectcallout"    # 矩形标注（直边矩形+尾巴）
SHAPE_DIAMOND_CALLOUT = "diamondcallout"  # 菱形标注
SHAPE_HOME_CALLOUT = "homecallout"    # 燕尾/五边形标注（Home Plate）
SHAPE_RIBBON_CALLOUT = "ribboncallout"   # 上卷/卷边标注
SHAPE_SCROLL_H = "scrollh"             # 横卷轴
SHAPE_SCROLL_V = "scrollv"             # 竖卷轴
SHAPE_MANUAL_INPUT = "manualinput"     # 手动输入（下边框波浪线）
SHAPE_CARD = "card"                    # 卡片（折角矩形）
SHAPE_SUN = "sun"                      # 太阳
SHAPE_CURVED_UP_ARROW = "curveduparrow"    # 弧形上箭头
SHAPE_CURVED_DOWN_ARROW = "curveddownarrow"  # 弧形下箭头
SHAPE_LEFT_RIBBON = "leftribbon"       # 左波形旗帜
SHAPE_RIGHT_RIBBON = "rightribbon"     # 右波形旗帜

# 支持尾尖拖拉的「标注」类形状：选中后显示黄色菱形控制点，可拖动改变尾巴位置
CALLOUT_SHAPES = frozenset({
    SHAPE_CALLOUT, SHAPE_RECT_CALLOUT, SHAPE_DIAMOND_CALLOUT,
    SHAPE_HOME_CALLOUT, SHAPE_RIBBON_CALLOUT,
    SHAPE_CLOUD_CALLOUT, SHAPE_OVAL_CALLOUT,
})

# 默认（常用）形状：网格第一屏直接展示
SHAPE_OPTIONS_PRIMARY = [
    ("直线", SHAPE_LINE), ("矩形", SHAPE_RECT),
    ("圆角矩形", SHAPE_ROUND_RECT),
    ("椭圆", SHAPE_ELLIPSE), ("三角形", SHAPE_TRIANGLE),
    ("直角三角形", SHAPE_RIGHT_TRIANGLE), ("菱形", SHAPE_DIAMOND),
    ("五边形", SHAPE_PENTAGON), ("六边形", SHAPE_HEXAGON),
    ("五角星", SHAPE_STAR), ("右箭头", SHAPE_ARROW),
    ("左箭头", SHAPE_LEFT_ARROW)]
# 「更多」按钮展开的扩展形状（参考 Office 形状库）
SHAPE_OPTIONS_MORE = [
    ("上箭头", SHAPE_UP_ARROW), ("下箭头", SHAPE_DOWN_ARROW),
    ("左右箭头", SHAPE_LR_ARROW), ("上下箭头", SHAPE_UD_ARROW),
    ("心形", SHAPE_HEART), ("云朵", SHAPE_CLOUD),
    ("平行四边形", SHAPE_PARALLELOGRAM), ("梯形", SHAPE_TRAPEZOID),
    ("四角星", SHAPE_FOUR_STAR), ("月牙", SHAPE_MOON),
    ("对话气泡", SHAPE_CALLOUT), ("十字", SHAPE_PLUS),
    # —— 多边形 ——
    ("七边形", SHAPE_HEPTAGON), ("八边形", SHAPE_OCTAGON),
    ("十边形", SHAPE_DECAGON), ("十二边形", SHAPE_DODECAGON),
    # —— 星 ——
    ("六角星", SHAPE_STAR6), ("八角星", SHAPE_STAR8),
    ("十六角星", SHAPE_STAR16), ("二十四角星", SHAPE_STAR24),
    ("爆炸形", SHAPE_BURST),
    # —— 括号 ——
    ("左大括号", SHAPE_BRACE_L), ("右大括号", SHAPE_BRACE_R),
    ("左双括号", SHAPE_BRACKET_L), ("右双括号", SHAPE_BRACKET_R),
    # —— 公式 ——
    ("减号", SHAPE_MINUS), ("乘号", SHAPE_TIMES),
    ("除号", SHAPE_DIVIDE), ("等号", SHAPE_EQUAL),
    ("不等号", SHAPE_NOTEQUAL),
    # —— 其它基本/流程 ——
    ("圆环", SHAPE_DONUT), ("空心弧", SHAPE_OPEN_ARC),
    ("燕尾形", SHAPE_CHEVRON), ("肘形箭头", SHAPE_BENT_ARROW),
    ("弧形箭头", SHAPE_CURVED_ARROW), ("波形横幅", SHAPE_RIBBON),
    ("文档", SHAPE_DOCUMENT), ("多文档", SHAPE_MULTIDOC),
    ("顺序存储", SHAPE_STORAGE), ("剪角矩形", SHAPE_SNIP),
    ("笑脸", SHAPE_SMILEY), ("闪电", SHAPE_LIGHTNING),
    ("云形标注", SHAPE_CLOUD_CALLOUT), ("椭圆标注", SHAPE_OVAL_CALLOUT),
    # —— v2.1 新增：标注 / 卷轴 / 流程 / 旗帜 / 弧形箭头 ——
    ("矩形标注", SHAPE_RECT_CALLOUT), ("菱形标注", SHAPE_DIAMOND_CALLOUT),
    ("燕尾标注", SHAPE_HOME_CALLOUT), ("上卷标注", SHAPE_RIBBON_CALLOUT),
    ("横卷轴", SHAPE_SCROLL_H), ("竖卷轴", SHAPE_SCROLL_V),
    ("手动输入", SHAPE_MANUAL_INPUT), ("卡片", SHAPE_CARD),
    ("太阳", SHAPE_SUN),
    ("弧形上箭头", SHAPE_CURVED_UP_ARROW),
    ("弧形下箭头", SHAPE_CURVED_DOWN_ARROW),
    ("左波形旗帜", SHAPE_LEFT_RIBBON), ("右波形旗帜", SHAPE_RIGHT_RIBBON),
]
SHAPE_OPTIONS = SHAPE_OPTIONS_PRIMARY + SHAPE_OPTIONS_MORE

# ---- Office 风格 7 大分类（需求4：基本形状/箭头汇总/公式形状/流程图/星与旗帜/标注/括号）----
# 仅按形状存储值归类，显示名统一从 SHAPE_OPTIONS 取，避免标签重复维护。
SHAPE_CATEGORY_ORDER = [
    ("basic", "基本形状", [
        SHAPE_LINE, SHAPE_RECT, SHAPE_ROUND_RECT, SHAPE_ELLIPSE,
        SHAPE_TRIANGLE, SHAPE_RIGHT_TRIANGLE, SHAPE_DIAMOND,
        SHAPE_PARALLELOGRAM, SHAPE_TRAPEZOID,
        SHAPE_PENTAGON, SHAPE_HEXAGON, SHAPE_HEPTAGON, SHAPE_OCTAGON,
        SHAPE_DECAGON, SHAPE_DODECAGON,
        SHAPE_DONUT, SHAPE_OPEN_ARC, SHAPE_MOON, SHAPE_HEART,
        SHAPE_SMILEY, SHAPE_SUN, SHAPE_CLOUD, SHAPE_LIGHTNING,
        SHAPE_SNIP, SHAPE_CARD]),
    ("arrow", "箭头汇总", [
        SHAPE_ARROW, SHAPE_LEFT_ARROW, SHAPE_UP_ARROW, SHAPE_DOWN_ARROW,
        SHAPE_LR_ARROW, SHAPE_UD_ARROW,
        SHAPE_BENT_ARROW, SHAPE_CURVED_ARROW,
        SHAPE_CURVED_UP_ARROW, SHAPE_CURVED_DOWN_ARROW, SHAPE_CHEVRON]),
    ("formula", "公式形状", [
        SHAPE_PLUS, SHAPE_MINUS, SHAPE_TIMES, SHAPE_DIVIDE,
        SHAPE_EQUAL, SHAPE_NOTEQUAL]),
    ("flow", "流程图", [
        SHAPE_DOCUMENT, SHAPE_MULTIDOC, SHAPE_STORAGE, SHAPE_MANUAL_INPUT]),
    ("star", "星与旗帜", [
        SHAPE_STAR, SHAPE_FOUR_STAR, SHAPE_STAR6, SHAPE_STAR8,
        SHAPE_STAR16, SHAPE_STAR24, SHAPE_BURST,
        SHAPE_RIBBON, SHAPE_LEFT_RIBBON, SHAPE_RIGHT_RIBBON,
        SHAPE_SCROLL_H, SHAPE_SCROLL_V]),
    ("callout", "标注", [
        SHAPE_CALLOUT, SHAPE_RECT_CALLOUT, SHAPE_OVAL_CALLOUT,
        SHAPE_DIAMOND_CALLOUT, SHAPE_HOME_CALLOUT, SHAPE_RIBBON_CALLOUT,
        SHAPE_CLOUD_CALLOUT]),
    ("bracket", "括号", [
        SHAPE_BRACE_L, SHAPE_BRACE_R, SHAPE_BRACKET_L, SHAPE_BRACKET_R]),
]


def _shape_label_map():
    return {v: label for label, v in SHAPE_OPTIONS}


def shape_categories():
    """返回 [(类名, [(中文标签, 形状值), ...]), ...]，每个形状恰好出现一次；
    若后续新增形状忘记归类，自动补进「基本形状」，保证不丢失。"""
    label_of = _shape_label_map()
    classified = set()
    result = []
    for key, title, values in SHAPE_CATEGORY_ORDER:
        items = []
        for v in values:
            if v in label_of and v not in classified:
                items.append((label_of[v], v))
                classified.add(v)
        result.append((key, title, items))
    # 兜底：未归类形状统一收进基本形状
    leftover = [(label_of[v], v) for _, v in SHAPE_OPTIONS if v not in classified]
    if leftover:
        k0, t0, items0 = result[0]
        result[0] = (k0, t0, items0 + leftover)
    return result


# 形状值 -> 所属分类 key（面板选中时自动展开对应分类）
_SHAPE_CATEGORY_OF = {}
for _ck, _ct, _citems in shape_categories():
    for _cl, _cv in _citems:
        _SHAPE_CATEGORY_OF[_cv] = _ck


# 引线标注风格
STYLE_BOX = "box"        # 现有样式：文字框 + 文字
STYLE_ABOVE = "above"    # 隐藏文字框：横线引线，文字在横线上方居中
STYLE_PLAIN = "plain"    # 隐藏文字框，文字在引线末端（现有透明样式）
# 新增引线样式
STYLE_ABOVE_TEXT = "above_text"   # 文字在线上方（横线和文字长度对齐）
STYLE_MIDDLE_TEXT = "middle_text" # 文字在线中间（固定线长）
STYLE_BELOW_TEXT = "below_text"   # 文字在线下方（横线和文字长度对齐）
STYLE_NO_LINE = "no_line"         # 无横线（没有横线）

ABOVE_GAP = 4            # above 风格：文字底部到横线的间距
ABOVE_EXTEND = 10        # above 风格：横线在文字两侧的延伸长度（对称式，兼容旧数据）
ABOVE_EXTEND_SINGLE = 24  # above 风格：单侧横线从文字中心正下方沿方向的延伸长度
ABOVE_DIR_AUTO = "auto"   # 横线方向：按图片左右半区自动判定（创建/应用样式时解析）
ABOVE_DIR_LEFT = "left"
ABOVE_DIR_RIGHT = "right"

# 序号格式：存储值 -> 显示
NUM_FMT_CIRCLE = "circle"   # ①②③…
NUM_FMT_PAREN = "paren"     # （1）（2）（3）
NUM_FMT_PLAIN = "plain"     # 1 2 3
NUM_FMT_OPTIONS = [("①（①②③）", NUM_FMT_CIRCLE),
                   ("（1）（（1）（2））", NUM_FMT_PAREN),
                   ("1（1 2 3）", NUM_FMT_PLAIN)]


def format_number(n: int, fmt: str = NUM_FMT_CIRCLE) -> str:
    """把序号数字格式化为指定格式的显示文本。"""
    if fmt == NUM_FMT_CIRCLE and 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    if fmt == NUM_FMT_PAREN:
        return f"（{n}）"
    return str(n)


def make_font(pixel_size: int) -> QFont:
    """按「图片像素」创建字体，保证画布与导出一致。"""
    try:
        ps = int(pixel_size)
    except (TypeError, ValueError):
        ps = 18
    if ps <= 0:   # 防御 0/-1，避免 QFont 字号非法警告
        ps = 18
    f = QFont(FONT_FAMILY)
    f.setPixelSize(max(6, ps))
    return f


# 文字脚本样式
SCRIPT_NORMAL = "normal"
SCRIPT_SUPER = "super"
SCRIPT_SUB = "sub"
SCRIPT_OPTIONS = [("正常", SCRIPT_NORMAL), ("上标", SCRIPT_SUPER),
                  ("下标", SCRIPT_SUB)]
# 字体粗细（QFont.Weight 数值）
FONT_WEIGHT_OPTIONS = [("细", 25), ("常规", 50), ("中等", 57),
                       ("粗", 75), ("特粗", 87)]


def draw_arrow_head(painter: QPainter, tip: QPointF, direction: QPointF,
                    size: float, color: QColor) -> None:
    """在 tip 处绘制指向 direction 反方向的实心三角箭头。

    尖端（顶点）落在 tip 上，底边朝 direction 方向张开 —— 即箭头「扎进」tip 指向的目标。
    """
    length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
    if length < 1e-6:
        return
    u = QPointF(direction.x() / length, direction.y() / length)
    base = tip + u * size          # 底边中点位于 direction 方向（引线一侧）
    perp = QPointF(-u.y(), u.x()) * (size * 0.55)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([tip, base + perp, base - perp]))
    painter.restore()


def distance_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    """点 p 到线段 ab 的最短距离。"""
    ax, ay = a.x(), a.y()
    bx, by = b.x(), b.y()
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((p.x() - ax) ** 2 + (p.y() - ay) ** 2) ** 0.5
    t = ((p.x() - ax) * dx + (p.y() - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((p.x() - cx) ** 2 + (p.y() - cy) ** 2) ** 0.5


class Layer:
    """图层：元素归属 + 显隐 + 顺序（列表顺序即绘制顺序，底层在前）。"""

    _id_counter = 0

    def __init__(self, name: str = "图层1", visible: bool = True):
        Layer._id_counter += 1
        self.id = Layer._id_counter
        self.name = name
        self.visible = visible


def _resolve_apex(shape: str, r: QRectF, tail):
    """统一尾尖参数：返回未旋转图片坐标中的尾尖 QPointF。

    - tail 为 QPointF：直接使用（尾尖可在主体四周任意位置）；
    - tail 为旧版 (tx, tl) 比例元组：兼容换算为绝对点；
    - None：使用默认尾尖（底边偏左、向下伸出）。
    非标注类形状返回 None。
    """
    if shape not in CALLOUT_SHAPES:
        return None
    if isinstance(tail, QPointF):
        return QPointF(tail)
    if isinstance(tail, (tuple, list)):
        try:
            tx = max(0.05, min(0.95, float(tail[0])))
            tl = max(0.0, min(0.85, float(tail[1])))
            return QPointF(r.left() + tx * r.width(),
                           r.bottom() + tl * r.height())
        except (TypeError, ValueError, IndexError):
            pass
    return callout_geom.default_apex(r)


def _rect_callout_path(r: QRectF, apex: QPointF, rad: float) -> QPainterPath:
    """直边/圆角矩形标注：主体矩形尺寸不变，尾巴从距 apex 最近的边伸出。
    路径：root1 → 角 ei → 逆时针绕其余三角 → 角(ei+1) → root2 → 尖点 → root1。
    root1-root2 之间的边不画（根部不封口），填充连续。"""
    cg = callout_geom
    verts = cg.rect_vertices(r)
    has_tail = not r.adjusted(1, 1, -1, -1).contains(apex)
    p = QPainterPath()
    rad = max(0.0, float(rad))
    if not has_tail:
        if rad > 0:
            p.addRoundedRect(r, rad, rad)
        else:
            p.addRect(r)
        return p
    ei, t = cg.nearest_edge(verts, apex)
    root1, root2 = cg.edge_roots(verts, ei, t)
    # 边 i 由角 i 指向角 (i+1)%4：0=上(L->R) 1=右(T->B) 2=底(R->L) 3=左(B->T)
    L, T, R, B = r.left(), r.top(), r.right(), r.bottom()
    corners = [QPointF(L, T), QPointF(R, T), QPointF(R, B), QPointF(L, B)]

    def _corner_to(cpath, from_pt, corner_pt, next_pt):
        """圆角过渡：从 from_pt 到 corner_pt 做 quadTo，再到 next_pt。"""
        if rad <= 0.5:
            cpath.lineTo(corner_pt)
            cpath.lineTo(next_pt)
            return
        # 角点往两边内收 rad
        v1 = corner_pt - from_pt
        l1 = (v1.x()**2 + v1.y()**2) ** 0.5
        v2 = next_pt - corner_pt
        l2 = (v2.x()**2 + v2.y()**2) ** 0.5
        if l1 < 1e-6 or l2 < 1e-6:
            cpath.lineTo(corner_pt)
            cpath.lineTo(next_pt)
            return
        a = QPointF(corner_pt.x() - v1.x()/l1*rad, corner_pt.y() - v1.y()/l1*rad)
        b = QPointF(corner_pt.x() + v2.x()/l2*rad, corner_pt.y() + v2.y()/l2*rad)
        cpath.lineTo(a)
        cpath.quadTo(corner_pt, b)

    # 从 root1 走到角 ei（root1 侧）
    p.moveTo(root1)
    # 逆时针绕圈：角 ei -> 角(ei-1) -> 角(ei-2) -> 角(ei+1)
    order = [ei, (ei - 1) % 4, (ei - 2) % 4, (ei - 3) % 4]
    prev = root1
    for i, cidx in enumerate(order):
        cpt = corners[cidx]
        # 下一个角（order 中的下一个）
        nidx = order[i + 1] if i + 1 < len(order) else None
        if nidx is not None:
            _corner_to(p, prev, cpt, corners[nidx])
            prev = corners[nidx]
        else:
            # 最后一个角(ei+1)，之后沿边走到 root2
            _corner_to(p, prev, cpt, root2)
            prev = root2
    # 尾巴：root2 → 尖点 → root1，闭合
    p.lineTo(apex)
    p.lineTo(root1)
    p.closeSubpath()
    return p


def _polygon_callout_path(body_verts, apex: QPointF,
                          half_ratio: float = 0.08) -> QPainterPath:
    """多边形标注（菱形/燕尾等）：主体多边形 + 尾巴三角形，单一连续封闭路径。
    填充连续（尾巴与主体同色）；描边时 root1-root2 之间不画（根部不封口）。"""
    p = QPainterPath()
    if callout_geom.point_in_polygon(body_verts, apex):
        p.addPolygon(QPolygonF(body_verts))
        p.closeSubpath()
        return p
    ei, r1, r2 = callout_geom.polygon_tail(body_verts, apex, half_ratio)
    n = len(body_verts)
    # 边 ei 方向：角 ei -> 角(ei+1)。r1 偏角 ei 侧，r2 偏角(ei+1)侧。
    # 从 r1 走到角 ei，逆时针绕其余角（ei-1, ei-2, ..., ei+1），再到 r2。
    p.moveTo(r1)
    p.lineTo(body_verts[ei])
    for k in range(1, n):
        cidx = (ei - k) % n
        p.lineTo(body_verts[cidx])
    p.lineTo(r2)
    # 尾巴：r2 → 尖点 → r1，闭合
    p.lineTo(apex)
    p.lineTo(r1)
    p.closeSubpath()
    return p


def _cloud_callout_path(r: QRectF, apex: QPointF,
                        root_scale: float = 1.0) -> QPainterPath:
    """云形标注：云朵主体 + 尾巴，单一连续封闭路径（与矩形标注同构）。

    云朵底边是一条水平线（y=cloud_bottom，从 S0 到 E）；尾巴两个根点
    严格落在这条底边上。轮廓从 root1 沿底边走到 S0，绕云朵一周到 E，再
    沿底边走到 root2，最后 root2→尖点→root1。因此：
    - 根点与云朵底边直线完全重合相连，不存在悬空缝隙；
    - root1-root2 之间不画连接线（该段底边被尾巴两条斜边替代）；
    - 填充连续（尾巴与主体同色）。
    """
    w, h = r.width(), r.height()
    cx = r.center().x()
    cloud_bottom = r.bottom() - h * 0.04
    s0 = QPointF(r.left() + w * 0.20, cloud_bottom)
    e_pt = QPointF(r.right() - w * 0.02, cloud_bottom)

    def _trace_cloud_body(cpath: QPainterPath) -> None:
        # 与云朵主体一致的 4 段贝塞尔：S0 → E（逆时针绕云朵一周）
        cpath.cubicTo(r.left(), cloud_bottom + h * 0.02,
                      r.left() + w * 0.05, r.top() + h * 0.45,
                      r.left() + w * 0.22, r.top() + h * 0.42)
        cpath.cubicTo(r.left() + w * 0.28, r.top() + h * 0.12,
                      cx, r.top() + h * 0.10,
                      cx + w * 0.12, r.top() + h * 0.30)
        cpath.cubicTo(r.right() - w * 0.08, r.top() + h * 0.18,
                      r.right(), r.top() + h * 0.42,
                      r.right() - w * 0.02, cloud_bottom)

    p = QPainterPath()
    if callout_geom.point_in_ellipse(r, apex):
        # 尾尖落在主体内：只画云朵，不画尾巴
        p.moveTo(s0)
        _trace_cloud_body(p)
        p.lineTo(s0)
        p.closeSubpath()
        return p
    # 根点半宽，并保证两个根点始终落在底边 [S0, E] 范围之内
    root_half = min(14.0, r.width() * 0.08) * max(0.1, float(root_scale))
    span_half = (e_pt.x() - s0.x()) / 2.0 - 1.0
    root_half = max(0.0, min(root_half, span_half))
    tip_x = max(s0.x() + root_half, min(e_pt.x() - root_half, apex.x()))
    root1 = QPointF(tip_x - root_half, cloud_bottom)
    root2 = QPointF(tip_x + root_half, cloud_bottom)
    # root1 → S0 → 绕云朵一周 → E → root2 → 尖点 → root1（根部不封口）
    p.moveTo(root1)
    p.lineTo(s0)
    _trace_cloud_body(p)
    p.lineTo(root2)
    p.lineTo(apex)
    p.lineTo(root1)
    p.closeSubpath()
    return p


def _ellipse_callout_path(r: QRectF, apex: QPointF,
                          cloud_path: QPainterPath = None,
                          root_scale: float = 1.0) -> QPainterPath:
    """椭圆标注：主体椭圆 + 尾巴，单一连续封闭路径（与矩形标注同构）。

    两个根点严格落在椭圆弧线上（按参数角 θ±δ 精确计算）：轮廓从 root1
    沿椭圆弧绕远路到 root2，再 root2→尖点→root1。根点与弧线无缝相连，
    root1-root2 之间不画连接线，填充连续（尾巴与主体同色、根部无空白）。
    cloud_path 参数仅为兼容旧调用保留，云形统一走 _cloud_callout_path。
    """
    import math
    if cloud_path is not None:
        return _cloud_callout_path(r, apex, root_scale)
    p = QPainterPath()
    if callout_geom.point_in_ellipse(r, apex):
        p.addEllipse(r)
        return p
    cx, cy = r.center().x(), r.center().y()
    a = max(r.width() / 2.0, 1e-6)
    b = max(r.height() / 2.0, 1e-6)
    # 尾尖方向（椭圆参数角，y 向下坐标系；与 callout_geom.ellipse_roots 一致）
    dx, dy = (apex.x() - cx) / a, (apex.y() - cy) / b
    theta = math.atan2(dy, dx) if (dx != 0.0 or dy != 0.0) else math.pi / 2.0
    # 期望根点弦半宽（px），按弦长公式 2·sinδ·√(a²sin²θ+b²cos²θ) 反解参数半角
    root_half = min(14.0, min(a, b) * 0.16)
    rr = math.hypot(a * math.sin(theta), b * math.cos(theta))
    if rr > 1e-9:
        d_theta = math.asin(max(0.0, min(0.999, root_half / rr)))
    else:
        d_theta = 0.0
    d_theta = min(d_theta, math.radians(35.0))
    t1, t2 = theta - d_theta, theta + d_theta
    # 根点严格落在椭圆弧线上
    root1 = QPointF(cx + a * math.cos(t1), cy + b * math.sin(t1))
    root2 = QPointF(cx + a * math.cos(t2), cy + b * math.sin(t2))
    # Qt 弧角度 0° 在 3 点方向、屏幕上逆时针为正（y 轴向下），与 y 向下
    # 参数角 θ 互为相反数；从 root1 沿【远侧弧】扫到 root2，跳过两个根点
    # 之间朝向尾尖的一小段弧（根部不封口）。
    start_deg = -math.degrees(t1)
    sweep_deg = 360.0 - 2.0 * math.degrees(d_theta)
    p.moveTo(root1)
    p.arcTo(r, start_deg, sweep_deg)
    # 尾巴：root2 → 尖点 → root1（根部不封口、无连接线）
    p.lineTo(apex)
    p.lineTo(root1)
    p.closeSubpath()
    return p


def shape_path(shape: str, r: QRectF, tail=None) -> QPainterPath:
    """把形状类型 + 矩形范围转换为可绘制的 QPainterPath。

    对非法/NaN 几何与未知形状做兜底（回退为矩形），保证任何情况下
    渲染都不会因无效路径崩溃。

    tail（仅标注类形状）：尾尖在未旋转图片坐标中的绝对位置 QPointF，
    可在主体四周任意位置；兼容旧版 (tail_x_ratio, tail_len_ratio) 元组；
    None 时使用默认尾尖。主体矩形 r 的尺寸不随尾尖变化。
    """
    # 清理 NaN/无穷值，防止 Qt 渲染非法路径
    def _finite(v):
        try:
            import math
            if math.isnan(v) or math.isinf(v):
                return 0.0
        except (TypeError, ValueError):
            return 0.0
        return v
    r = QRectF(_finite(r.x()), _finite(r.y()),
               max(_finite(r.width()), 0.0), max(_finite(r.height()), 0.0))
    if r.width() < 1e-9 or r.height() < 1e-9:
        r = QRectF(r.x(), r.y(), 1.0, 1.0)
    # 标注类形状尾尖（绝对坐标，主体尺寸保持不变）
    apex = _resolve_apex(shape, r, tail)
    p = QPainterPath()
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if shape == SHAPE_LINE:
        # 直线：归一化矩形左上 -> 右下的对角线段（开放路径，不闭合）
        p.moveTo(r.topLeft())
        p.lineTo(r.bottomRight())
    elif shape == SHAPE_RECT:
        p.addRect(r)
    elif shape == SHAPE_ROUND_RECT:
        p.addRoundedRect(r, min(12.0, w * 0.2), min(12.0, h * 0.2))
    elif shape == SHAPE_ELLIPSE:
        p.addEllipse(r)
    elif shape == SHAPE_TRIANGLE:
        p.addPolygon(QPolygonF([QPointF(cx, r.top()), QPointF(r.right(), r.bottom()),
                                QPointF(r.left(), r.bottom())]))
        p.closeSubpath()
    elif shape == SHAPE_RIGHT_TRIANGLE:
        p.addPolygon(QPolygonF([QPointF(r.left(), r.bottom()),
                                QPointF(r.right(), r.bottom()),
                                QPointF(r.left(), r.top())]))
        p.closeSubpath()
    elif shape == SHAPE_DIAMOND:
        p.addPolygon(QPolygonF([QPointF(cx, r.top()), QPointF(r.right(), cy),
                                QPointF(cx, r.bottom()), QPointF(r.left(), cy)]))
        p.closeSubpath()
    elif shape in (SHAPE_PENTAGON, SHAPE_HEXAGON):
        n = 5 if shape == SHAPE_PENTAGON else 6
        pts = []
        for i in range(n):
            ang = -90.0 + i * 360.0 / n
            import math
            rad = math.radians(ang)
            pts.append(QPointF(cx + w / 2.0 * math.cos(rad),
                               cy + h / 2.0 * math.sin(rad)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif shape == SHAPE_STAR:
        import math
        pts = []
        for i in range(10):
            ang = -90.0 + i * 36.0
            rad = math.radians(ang)
            rr = w / 2.0 if i % 2 == 0 else w * 0.42 / 2.0
            pts.append(QPointF(cx + rr * math.cos(rad), cy + rr * math.sin(rad)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif shape == SHAPE_ARROW:
        # 右箭头：头部占宽 40%
        hw = w * 0.40
        body = QPolygonF([QPointF(r.left(), r.top() + h * 0.30),
                          QPointF(r.right() - hw, r.top() + h * 0.30),
                          QPointF(r.right() - hw, r.top()),
                          QPointF(r.right(), cy),
                          QPointF(r.right() - hw, r.bottom()),
                          QPointF(r.right() - hw, r.bottom() - h * 0.30),
                          QPointF(r.left(), r.bottom() - h * 0.30)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_LEFT_ARROW:
        # 左箭头（右箭头水平翻转）
        hw = w * 0.40
        body = QPolygonF([QPointF(r.right(), r.top() + h * 0.30),
                          QPointF(r.left() + hw, r.top() + h * 0.30),
                          QPointF(r.left() + hw, r.top()),
                          QPointF(r.left(), cy),
                          QPointF(r.left() + hw, r.bottom()),
                          QPointF(r.left() + hw, r.bottom() - h * 0.30),
                          QPointF(r.right(), r.bottom() - h * 0.30)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_UP_ARROW:
        # 上箭头
        hw = h * 0.40
        body = QPolygonF([QPointF(r.left() + w * 0.30, r.bottom()),
                          QPointF(r.left() + w * 0.30, r.top() + hw),
                          QPointF(r.left(), r.top() + hw),
                          QPointF(cx, r.top()),
                          QPointF(r.right(), r.top() + hw),
                          QPointF(r.right() - w * 0.30, r.top() + hw),
                          QPointF(r.right() - w * 0.30, r.bottom())])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_DOWN_ARROW:
        hw = h * 0.40
        body = QPolygonF([QPointF(r.left() + w * 0.30, r.top()),
                          QPointF(r.left() + w * 0.30, r.bottom() - hw),
                          QPointF(r.left(), r.bottom() - hw),
                          QPointF(cx, r.bottom()),
                          QPointF(r.right(), r.bottom() - hw),
                          QPointF(r.right() - w * 0.30, r.bottom() - hw),
                          QPointF(r.right() - w * 0.30, r.top())])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_LR_ARROW:
        # 左右双向箭头
        hh = h * 0.40
        body = QPolygonF([QPointF(cx, r.top()), QPointF(r.right(), cy),
                          QPointF(cx, r.bottom()), QPointF(cx, cy + hh / 2.0),
                          QPointF(r.left(), cy + hh / 2.0), QPointF(r.left(), cy - hh / 2.0),
                          QPointF(cx, cy - hh / 2.0)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_UD_ARROW:
        hw = w * 0.40
        body = QPolygonF([QPointF(r.left(), cy), QPointF(cx, r.top()),
                          QPointF(r.right(), cy), QPointF(cx + hw / 2.0, cy),
                          QPointF(cx + hw / 2.0, r.bottom()), QPointF(cx - hw / 2.0, r.bottom()),
                          QPointF(cx - hw / 2.0, cy)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_PARALLELOGRAM:
        sx = w * 0.22
        body = QPolygonF([QPointF(r.left() + sx, r.top()),
                          QPointF(r.right(), r.top()),
                          QPointF(r.right() - sx, r.bottom()),
                          QPointF(r.left(), r.bottom())])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_TRAPEZOID:
        sx = w * 0.25
        body = QPolygonF([QPointF(r.left() + sx, r.top()),
                          QPointF(r.right() - sx, r.top()),
                          QPointF(r.right(), r.bottom()),
                          QPointF(r.left(), r.bottom())])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_PLUS:
        arm = min(w, h) * 0.25
        body = QPolygonF([QPointF(cx - arm, r.top()), QPointF(cx + arm, r.top()),
                          QPointF(cx + arm, cy - arm), QPointF(r.right(), cy - arm),
                          QPointF(r.right(), cy + arm), QPointF(cx + arm, cy + arm),
                          QPointF(cx + arm, r.bottom()), QPointF(cx - arm, r.bottom()),
                          QPointF(cx - arm, cy + arm), QPointF(r.left(), cy + arm),
                          QPointF(r.left(), cy - arm), QPointF(cx - arm, cy - arm)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_FOUR_STAR:
        # 四角闪光星：上下左右四个长顶点 + 四个内凹顶点
        inner = 0.18
        body = QPolygonF([
            QPointF(cx, r.top()),
            QPointF(cx + inner * w, cy - inner * h),
            QPointF(r.right(), cy),
            QPointF(cx + inner * w, cy + inner * h),
            QPointF(cx, r.bottom()),
            QPointF(cx - inner * w, cy + inner * h),
            QPointF(r.left(), cy),
            QPointF(cx - inner * w, cy - inner * h)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_HEART:
        # 心形：用贝塞尔曲线近似
        import math
        top_dip = cy - h * 0.15
        p.moveTo(cx, r.bottom())
        p.cubicTo(r.left(), cy - h * 0.10, r.left(), r.top() + h * 0.18,
                  cx, top_dip)
        p.cubicTo(r.right(), r.top() + h * 0.18, r.right(),
                  cy - h * 0.10, cx, r.bottom())
        p.closeSubpath()
    elif shape == SHAPE_CLOUD:
        # 云朵：多个圆弧叠加近似
        p.moveTo(r.left() + w * 0.20, r.bottom() - h * 0.15)
        p.cubicTo(r.left(), r.bottom(), r.left() + w * 0.05, r.top() + h * 0.45,
                  r.left() + w * 0.22, r.top() + h * 0.42)
        p.cubicTo(r.left() + w * 0.28, r.top() + h * 0.12, r.left() + w * 0.55,
                  r.top() + h * 0.10, r.left() + w * 0.62, r.top() + h * 0.30)
        p.cubicTo(r.right() - w * 0.08, r.top() + h * 0.18, r.right(),
                  r.top() + h * 0.42, r.right() - w * 0.02, r.bottom() - h * 0.18)
        p.cubicTo(r.right(), r.bottom(), r.left() + w * 0.80, r.bottom(),
                  r.left() + w * 0.20, r.bottom() - h * 0.15)
        p.closeSubpath()
    elif shape == SHAPE_MOON:
        # 月牙：两个椭圆差集近似（外弧+内弧）
        import math
        p.moveTo(cx, r.top())
        p.arcTo(r, 90, 180)
        # 内凹弧
        inner = QRectF(cx - w * 0.28, r.top() + h * 0.05,
                       w * 0.62, h * 0.90)
        p.arcTo(inner, 90, -180)
        p.closeSubpath()
    elif shape in (SHAPE_CALLOUT, SHAPE_RECT_CALLOUT, SHAPE_RIBBON_CALLOUT):
        # 圆角矩形/矩形/卷边标注：主体尺寸恒定，尾巴从距尖点最近的边伸出，
        # 根部在该边开口、由两条斜边替代，整条路径连续封闭（Office 风格）。
        if shape == SHAPE_CALLOUT:
            rad = min(10.0, w * 0.15, h * 0.2)
        else:
            rad = 0.0
        p = _rect_callout_path(r, apex, rad)
        # 卷边标注：顶部加一条波浪线（装饰，不影响主体路径）
        if shape == SHAPE_RIBBON_CALLOUT:
            p.moveTo(r.left() + w * 0.05, r.top())
            p.lineTo(r.right() - w * 0.05, r.top())
    elif shape == SHAPE_DIAMOND_CALLOUT:
        # 菱形标注：菱形主体（尺寸恒定）+ 尾巴自动贴合最近的菱形边
        diamond_verts = [QPointF(cx, r.top()), QPointF(r.right(), cy),
                         QPointF(cx, r.bottom()), QPointF(r.left(), cy)]
        p = _polygon_callout_path(diamond_verts, apex)
    elif shape == SHAPE_HOME_CALLOUT:
        # 燕尾/五边形标注（Home Plate）：主体轮廓不变 + 尾巴贴合最近边
        home_verts = [QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
                      QPointF(r.right(), cy), QPointF(r.left(), cy)]
        p = _polygon_callout_path(home_verts, apex, half_ratio=0.10)
    elif shape == SHAPE_SCROLL_H:
        # 横卷轴：中间矩形 + 左右两个圆柱卷边
        cy = (r.top() + r.bottom()) / 2.0
        coil_w = w * 0.12
        # 中间纸面
        p.addRect(QRectF(r.left() + coil_w, r.top(), w - 2 * coil_w, h))
        # 左卷边（椭圆）
        p.addEllipse(QRectF(r.left(), r.top() - h * 0.05, coil_w * 1.6, h * 1.10))
        # 右卷边
        p.addEllipse(QRectF(r.right() - coil_w * 0.6, r.top() - h * 0.05,
                            coil_w * 1.6, h * 1.10))
    elif shape == SHAPE_SCROLL_V:
        # 竖卷轴：中间矩形 + 上下两个圆柱卷边
        coil_h = h * 0.12
        p.addRect(QRectF(r.left(), r.top() + coil_h, w, h - 2 * coil_h))
        p.addEllipse(QRectF(r.left() - w * 0.05, r.top(), w * 1.10, coil_h * 1.6))
        p.addEllipse(QRectF(r.left() - w * 0.05, r.bottom() - coil_h * 0.6,
                            w * 1.10, coil_h * 1.6))
    elif shape == SHAPE_MANUAL_INPUT:
        # 手动输入：矩形，下边框为波浪线
        p.moveTo(r.left(), r.top())
        p.lineTo(r.right(), r.top())
        p.lineTo(r.right(), r.bottom() - h * 0.10)
        # 下边框波浪（两个波峰）
        seg = w / 4.0
        p.quadTo(r.left() + seg * 1.5, r.bottom() - h * 0.28,
                 r.left() + seg * 2.0, r.bottom() - h * 0.10)
        p.quadTo(r.left() + seg * 2.5, r.bottom() + h * 0.08,
                 r.left() + seg * 3.0, r.bottom() - h * 0.10)
        p.quadTo(r.left() + seg * 3.5, r.bottom() - h * 0.28,
                 r.left() + seg * 4.0, r.bottom() - h * 0.10)
        p.lineTo(r.left(), r.bottom() - h * 0.10)
        p.closeSubpath()
    elif shape == SHAPE_CARD:
        # 卡片：右上角折角矩形
        fold = min(w, h) * 0.28
        p.moveTo(r.left(), r.top())
        p.lineTo(r.right() - fold, r.top())
        p.lineTo(r.right(), r.top() + fold)
        p.lineTo(r.right(), r.bottom())
        p.lineTo(r.left(), r.bottom())
        p.closeSubpath()
    elif shape == SHAPE_SUN:
        # 太阳：中心圆 + 12 道光芒
        import math
        p.addEllipse(QRectF(cx - w * 0.22, cy - h * 0.22, w * 0.44, h * 0.44))
        for i in range(12):
            ang = i * 30.0
            rad = math.radians(ang)
            r1 = min(w, h) * 0.30
            r2 = min(w, h) * 0.46
            x1 = cx + r1 * math.cos(rad); y1 = cy + r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad); y2 = cy + r2 * math.sin(rad)
            p.moveTo(x1, y1)
            p.lineTo(x2, y2)
    elif shape == SHAPE_CURVED_UP_ARROW:
        # 弧形上箭头：粗弧向上弯，顶部箭头
        p.moveTo(r.left() + w * 0.25, r.bottom())
        p.cubicTo(r.left() - w * 0.10, cy, cx, r.bottom(), cx, r.top())
        p.lineTo(cx - w * 0.18, r.top() + h * 0.28)
        p.cubicTo(cx - w * 0.10, cy + h * 0.05, r.left() + w * 0.20,
                  r.bottom() - h * 0.25, r.left() + w * 0.40, r.bottom() - h * 0.25)
        p.closeSubpath()
    elif shape == SHAPE_CURVED_DOWN_ARROW:
        # 弧形下箭头
        p.moveTo(r.left() + w * 0.25, r.top())
        p.cubicTo(r.left() - w * 0.10, cy, cx, r.top(), cx, r.bottom())
        p.lineTo(cx - w * 0.18, r.bottom() - h * 0.28)
        p.cubicTo(cx - w * 0.10, cy - h * 0.05, r.left() + w * 0.20,
                  r.top() + h * 0.25, r.left() + w * 0.40, r.top() + h * 0.25)
        p.closeSubpath()
    elif shape in (SHAPE_LEFT_RIBBON, SHAPE_RIGHT_RIBBON):
        # 左/右波形旗帜：矩形 + 外侧波浪边
        s = -1.0 if shape == SHAPE_LEFT_RIBBON else 1.0
        p.moveTo(r.left(), r.top())
        p.lineTo(r.right(), r.top())
        # 右侧直边
        p.lineTo(r.right(), r.bottom())
        # 底部波浪向左
        p.lineTo(r.left() + w * 0.10, r.bottom())
        seg = w * 0.20
        p.quadTo(r.left() + w * 0.05 + s * seg, r.bottom() - h * 0.18,
                 r.left() + w * 0.10, r.bottom() - h * 0.36)
        p.quadTo(r.left() + w * 0.05 + s * seg, r.bottom() - h * 0.54,
                 r.left() + w * 0.10, r.bottom() - h * 0.72)
        p.quadTo(r.left() + w * 0.05 + s * seg, r.bottom() - h * 0.90,
                 r.left(), r.top())
        p.closeSubpath()
    elif shape in (SHAPE_HEPTAGON, SHAPE_OCTAGON, SHAPE_DECAGON, SHAPE_DODECAGON):
        import math
        n = {SHAPE_HEPTAGON: 7, SHAPE_OCTAGON: 8,
             SHAPE_DECAGON: 10, SHAPE_DODECAGON: 12}[shape]
        pts = []
        for i in range(n):
            ang = -90.0 + i * 360.0 / n
            rad = math.radians(ang)
            pts.append(QPointF(cx + w / 2.0 * math.cos(rad),
                               cy + h / 2.0 * math.sin(rad)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif shape in (SHAPE_STAR6, SHAPE_STAR8, SHAPE_STAR16, SHAPE_STAR24):
        import math
        n_outer = {SHAPE_STAR6: 6, SHAPE_STAR8: 8,
                   SHAPE_STAR16: 16, SHAPE_STAR24: 24}[shape]
        pts = []
        for i in range(n_outer * 2):
            ang = -90.0 + i * 180.0 / n_outer
            rad = math.radians(ang)
            rr = w / 2.0 if i % 2 == 0 else w * 0.45 / 2.0
            pts.append(QPointF(cx + rr * math.cos(rad),
                               cy + h / 2.0 * (rr / (w / 2.0)) * math.sin(rad)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif shape in (SHAPE_BRACE_L, SHAPE_BRACE_R):
        # 大括号 { / }：三段贝塞尔近似
        s = 1.0 if shape == SHAPE_BRACE_L else -1.0
        x_edge = r.left() if s == 1.0 else r.right()
        x_mid = r.right() if s == 1.0 else r.left()
        p.moveTo(x_edge, r.top() + h * 0.20)
        p.cubicTo(x_mid, r.top() + h * 0.20, x_mid, r.top() + h * 0.38,
                  x_mid, cy)
        p.cubicTo(x_mid, r.bottom() - h * 0.38, x_mid,
                  r.bottom() - h * 0.20, x_edge, r.bottom() - h * 0.20)
    elif shape in (SHAPE_BRACKET_L, SHAPE_BRACKET_R):
        # 双括号 [ / ]
        s = 1.0 if shape == SHAPE_BRACKET_L else -1.0
        x0 = r.left() if s == 1.0 else r.right()
        x1 = r.right() if s == 1.0 else r.left()
        p.moveTo(x1, r.top())
        p.lineTo(x0, r.top())
        p.lineTo(x0, r.bottom())
        p.lineTo(x1, r.bottom())
    elif shape == SHAPE_MINUS:
        bh = h * 0.18
        p.addRect(QRectF(r.left() + w * 0.10, cy - bh, w * 0.80, bh * 2))
    elif shape == SHAPE_EQUAL:
        bh = h * 0.14
        p.addRect(QRectF(r.left() + w * 0.10, cy - h * 0.22 - bh, w * 0.80, bh * 2))
        p.addRect(QRectF(r.left() + w * 0.10, cy + h * 0.22 - bh, w * 0.80, bh * 2))
    elif shape == SHAPE_NOTEQUAL:
        bh = h * 0.13
        p.addRect(QRectF(r.left() + w * 0.10, cy - h * 0.22 - bh, w * 0.80, bh * 2))
        p.addRect(QRectF(r.left() + w * 0.10, cy + h * 0.18 - bh, w * 0.80, bh * 2))
        p.moveTo(r.left() + w * 0.15, r.bottom() - h * 0.10)
        p.lineTo(r.right() - w * 0.15, r.top() + h * 0.10)
    elif shape == SHAPE_TIMES:
        arm = min(w, h) * 0.16
        p.addPolygon(QPolygonF([
            QPointF(cx - arm, cy - arm), QPointF(cx + arm, cy - arm),
            QPointF(r.right(), cy - min(w, h) * 0.30), QPointF(r.right() - min(w, h) * 0.30, cy),
            QPointF(r.right(), cy + min(w, h) * 0.30), QPointF(cx + arm, cy + arm),
            QPointF(cx - arm, cy + arm), QPointF(r.left(), cy + min(w, h) * 0.30),
            QPointF(r.left() + min(w, h) * 0.30, cy), QPointF(r.left(), cy - min(w, h) * 0.30)]))
        p.closeSubpath()
    elif shape == SHAPE_DIVIDE:
        bh = h * 0.13
        p.addRect(QRectF(r.left() + w * 0.15, cy - bh, w * 0.70, bh * 2))
        p.addEllipse(QRectF(cx - w * 0.09, r.top() + h * 0.12 - h * 0.09,
                            w * 0.18, h * 0.18))
        p.addEllipse(QRectF(cx - w * 0.09, r.bottom() - h * 0.12 - h * 0.09,
                            w * 0.18, h * 0.18))
    elif shape == SHAPE_DONUT:
        outer = QPainterPath()
        outer.addEllipse(r)
        inner = QPainterPath()
        ir = QRectF(cx - w * 0.30, cy - h * 0.30, w * 0.60, h * 0.60)
        inner.addEllipse(ir)
        p = outer.subtracted(inner)
    elif shape == SHAPE_OPEN_ARC:
        # 空心弧（对应 Office「空心弧 / Block Arc」）：270° 环形扇段（粗弧带），
        # 开口朝右，外弧与内弧之间围成单一封闭区域（可填充、可命中）。
        # 关键：空 QPainterPath 直接 arcTo 会先从 (0,0) 拉一条直线到弧起点，
        # 导致形状被扯到画布左上角，因此必须先 moveTo 到外弧起点。
        import math
        start_deg, sweep_deg = 45.0, 270.0

        def _arc_pt(rect: QRectF, ang_deg: float) -> QPointF:
            # 与 QPainterPath.arcTo 同一套角度约定：0° 在 3 点方向、逆时针为正
            t = math.radians(ang_deg)
            return QPointF(rect.center().x() + rect.width() / 2.0 * math.cos(t),
                           rect.center().y() - rect.height() / 2.0 * math.sin(t))

        out_start = _arc_pt(r, start_deg)
        # 内圈为外框的 52%，形成粗细协调的固定弧带
        iw, ih = w * 0.52, h * 0.52
        ir = QRectF(cx - iw / 2.0, cy - ih / 2.0, iw, ih)
        in_end = _arc_pt(ir, start_deg + sweep_deg)
        p.moveTo(out_start)
        p.arcTo(r, start_deg, sweep_deg)                 # 外弧：起点扫到终点
        p.lineTo(in_end)                                # 端面：外终点→内终点
        p.arcTo(ir, start_deg + sweep_deg, -sweep_deg)  # 内弧反向扫回
        p.closeSubpath()                                # 端面：内起点→外起点
    elif shape == SHAPE_CHEVRON:
        body = QPolygonF([QPointF(r.left(), r.top()),
                          QPointF(r.right() - w * 0.28, r.top()),
                          QPointF(r.right(), cy),
                          QPointF(r.right() - w * 0.28, r.bottom()),
                          QPointF(r.left(), r.bottom()),
                          QPointF(r.left() + w * 0.22, cy)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_BENT_ARROW:
        # 直角肘形右箭头：竖直段+水平箭头
        hw = w * 0.38
        body = QPolygonF([
            QPointF(r.left(), cy - h * 0.22),
            QPointF(r.right() - hw, cy - h * 0.22),
            QPointF(r.right() - hw, r.top() + h * 0.20),
            QPointF(r.right() - hw, r.top()),
            QPointF(r.right(), cy),
            QPointF(r.right() - hw, r.bottom()),
            QPointF(r.right() - hw, cy + h * 0.22),
            QPointF(r.left(), cy + h * 0.22)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_CURVED_ARROW:
        # 弧形右箭头（粗弧）
        import math
        p.moveTo(r.left() + w * 0.25, r.bottom())
        p.cubicTo(r.left() - w * 0.15, cy, r.left() + w * 0.2,
                  r.top(), cx, r.top())
        p.lineTo(cx, r.top() + h * 0.30)
        p.cubicTo(cx - w * 0.10, cy, r.left() + w * 0.18,
                  r.bottom() - h * 0.25, r.left() + w * 0.35, r.bottom() - h * 0.25)
        p.closeSubpath()
    elif shape == SHAPE_RIBBON:
        # 波形横幅：矩形 + 下沿波浪
        p.addRect(QRectF(r.left(), r.top(), w, h * 0.62))
        p.moveTo(r.left(), r.top() + h * 0.62)
        p.lineTo(r.right(), r.top() + h * 0.62)
        p.lineTo(r.right(), r.bottom())
        p.quadTo(cx + w * 0.25, r.bottom() - h * 0.18, cx, r.bottom())
        p.quadTo(r.left() + w * 0.25, r.bottom() - h * 0.18, r.left(), r.bottom())
        p.closeSubpath()
    elif shape == SHAPE_BURST:
        # 爆炸形：12 尖角锯齿
        import math
        pts = []
        for i in range(24):
            ang = -90.0 + i * 15.0
            rad = math.radians(ang)
            rr = w / 2.0 if i % 2 == 0 else w * 0.62 / 2.0
            pts.append(QPointF(cx + rr * math.cos(rad),
                               cy + (h / 2.0 if i % 2 == 0 else h * 0.62 / 2.0)
                               * math.sin(rad)))
        p.addPolygon(QPolygonF(pts))
        p.closeSubpath()
    elif shape == SHAPE_DOCUMENT:
        # 文档：矩形 + 底部波浪
        p.moveTo(r.left(), r.top())
        p.lineTo(r.right(), r.top())
        p.lineTo(r.right(), r.bottom() - h * 0.12)
        p.quadTo(cx + w * 0.25, r.bottom() - h * 0.30, cx, r.bottom() - h * 0.12)
        p.quadTo(r.left() + w * 0.25, r.bottom() - h * 0.0, r.left(), r.bottom() - h * 0.12)
        p.closeSubpath()
    elif shape == SHAPE_MULTIDOC:
        p.addRect(QRectF(r.left() + w * 0.12, r.top() + h * 0.05,
                         w * 0.80, h * 0.80))
        p.addRect(QRectF(r.left(), r.top() + h * 0.15, w * 0.80, h * 0.80))
    elif shape == SHAPE_STORAGE:
        # 圆柱：顺序存储
        p.moveTo(r.left(), r.top() + h * 0.15)
        p.quadTo(cx, r.top() - h * 0.10, r.right(), r.top() + h * 0.15)
        p.lineTo(r.right(), r.bottom() - h * 0.15)
        p.quadTo(cx, r.bottom() + h * 0.10, r.left(), r.bottom() - h * 0.15)
        p.closeSubpath()
    elif shape == SHAPE_SNIP:
        # 剪去单角（右下角切角）
        body = QPolygonF([QPointF(r.left(), r.top()),
                          QPointF(r.right(), r.top()),
                          QPointF(r.right(), r.bottom() - h * 0.30),
                          QPointF(r.right() - w * 0.30, r.bottom()),
                          QPointF(r.left(), r.bottom())])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_SMILEY:
        p.addEllipse(r)
        p.addEllipse(QRectF(r.left() + w * 0.28, r.top() + h * 0.30,
                            w * 0.12, h * 0.12))
        p.addEllipse(QRectF(r.right() - w * 0.40, r.top() + h * 0.30,
                            w * 0.12, h * 0.12))
        p.moveTo(r.left() + w * 0.28, r.bottom() - h * 0.30)
        p.quadTo(cx, r.bottom() - h * 0.05, r.right() - w * 0.28, r.bottom() - h * 0.30)
    elif shape == SHAPE_LIGHTNING:
        body = QPolygonF([QPointF(cx + w * 0.05, r.top()),
                           QPointF(cx - w * 0.30, cy + h * 0.10),
                           QPointF(cx - w * 0.05, cy + h * 0.10),
                           QPointF(cx - w * 0.15, r.bottom()),
                           QPointF(cx + w * 0.30, cy - h * 0.05),
                           QPointF(cx + w * 0.05, cy - h * 0.05)])
        p.addPolygon(body)
        p.closeSubpath()
    elif shape == SHAPE_CLOUD_CALLOUT:
        # 云形标注：云朵主体（尺寸恒定，铺满 r）+ 尾巴根点落在底边直线上，
        # 单一连续封闭路径（根部不封口、无连接线，与矩形标注一致）
        p = _cloud_callout_path(r, apex, root_scale=0.82)
    elif shape == SHAPE_OVAL_CALLOUT:
        # 椭圆标注：椭圆主体（尺寸恒定）+ 尾巴贴合到朝向尖点的弧
        p = _ellipse_callout_path(r, apex)
    else:
        # 未知形状：回退为矩形（保证永不返回空路径导致渲染异常）
        p.addRect(r)
    return p


class AnnotationItem:
    """标注元素基类：文字块（含可选背景框）+ 选中状态。"""

    _id_counter = 0

    def __init__(self, text_content: str, font_size: int, text_color):
        AnnotationItem._id_counter += 1
        self.id = AnnotationItem._id_counter
        self.selected = False
        self.text_content = text_content
        try:
            _fs = int(font_size)
        except (TypeError, ValueError):
            _fs = 18
        self.font_size = _fs if _fs > 0 else 18
        self.text_color = QColor(text_color)
        self.font_family = FONT_FAMILY            # 字体族
        self.font_weight = 50                     # QFont.Weight（50 = Normal）
        self.font_italic = False                  # 斜体
        self.script = SCRIPT_NORMAL               # 正常/上标/下标
        self.bg_enabled = False                            # 默认透明背景（无文字框）
        self.bg_fill_color = QColor(255, 255, 255, 215)    # 半透明白填充（启用背景框时使用）
        self.bg_border_color = QColor(255, 0, 0)           # 红色边框（启用背景框时使用）
        self.layer_id = 0                                  # 所属图层 id（0 = 默认层）
        self.rotation = 0.0   # v1.7：绕自身包围盒中心旋转角度（度）

    # ---- 字体 ----
    def make_item_font(self, size: int | None = None) -> QFont:
        """按元素自身字体设置创建 QFont（图片像素）。上标/下标自动缩小字号。"""
        size = self.font_size if size is None else size
        try:
            size = float(size)
        except (TypeError, ValueError):
            size = 18.0
        if size <= 0:
            size = 18.0
        if self.script != SCRIPT_NORMAL:
            size = size * 0.72
        family = self.font_family if getattr(self, "font_family", "") else FONT_FAMILY
        f = QFont(family)
        f.setPixelSize(max(6, int(size)))
        try:
            f.setWeight(int(self.font_weight))
        except (TypeError, ValueError):
            f.setWeight(50)
        f.setItalic(bool(self.font_italic))
        return f

    def script_offset(self) -> float:
        """上标/下标的纵向偏移（图片像素；0 = 正常基线）。"""
        if self.script == SCRIPT_SUPER:
            return -self.font_size * 0.30
        if self.script == SCRIPT_SUB:
            return self.font_size * 0.22
        return 0.0

    def display_text(self) -> str:
        """实际显示的文字：无文字内容但有序号时，直接显示序号。"""
        if self.text_content:
            return self.text_content
        number = getattr(self, "number", None)
        if number:
            return format_number(number, getattr(self, "number_fmt", NUM_FMT_CIRCLE))
        return ""

    # ---- 文字块绘制 ----
    def text_rect_at_origin(self) -> QRectF:
        """文字块矩形（含内边距），左上角恒为 (0,0)。用 QFontMetrics 计算，无需 QPainter。"""
        font = self.make_item_font()
        fm = QFontMetrics(font)
        br = fm.boundingRect(0, 0, 1 << 20, 0,
                             Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine,
                             self.display_text() or " ")
        h = max(float(br.height()), self.font_size * 1.25)
        return QRectF(0.0, 0.0, float(br.width()) + 2 * TEXT_PAD_X,
                      h + 2 * TEXT_PAD_Y)

    def paint_text_only(self, painter: QPainter, top_left: QPointF) -> None:
        """只绘制文字（无背景框）。文字在矩形内左右各留 TEXT_PAD_X，保证对称。"""
        painter.save()
        painter.setFont(self.make_item_font())
        rect = self.text_rect_at_origin().translated(top_left)
        # 向右偏移 TEXT_PAD_X，宽度减去左右 padding，使文字在矩形内左右对称
        text_draw_rect = rect.adjusted(TEXT_PAD_X, 0, -TEXT_PAD_X, 0)
        dy = self.script_offset()
        if dy:
            painter.translate(0.0, dy)
        painter.setPen(QPen(self.text_color, 1))
        painter.drawText(text_draw_rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                         | Qt.TextFlag.TextSingleLine,
                         self.display_text().replace("&", "&&"))
        painter.restore()

    def paint_text_block(self, painter: QPainter, top_left: QPointF) -> None:
        """在 top_left（框左上角）处绘制文字背景框 + 文字（文字在框体内垂直居中）。"""
        painter.save()
        painter.setFont(self.make_item_font())
        rect = self.text_rect_at_origin().translated(top_left)
        if self.bg_enabled:
            painter.setPen(QPen(self.bg_border_color, 2))
            painter.setBrush(QColor(self.bg_fill_color))
            painter.drawRect(rect)
        dy = self.script_offset()
        if dy:
            painter.translate(0.0, dy)
        painter.setPen(QPen(self.text_color, 1))
        painter.drawText(rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                         | Qt.TextFlag.TextSingleLine,
                         self.display_text().replace("&", "&&"))
        painter.restore()

    def paint_selection(self, painter: QPainter, rect: QRectF) -> None:
        """选中高亮：蓝色虚线框。"""
        painter.save()
        painter.setPen(QPen(SELECT_COLOR, 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        painter.restore()

    def paint_number(self, painter: QPainter, rect: QRectF) -> None:
        """把序号（①②等）绘制在文字矩形正上方。

        仅当文字内容非空时绘制（无文字内容时序号本身就是显示文字，
        由 display_text() 直接渲染，避免重复）。
        """
        if not getattr(self, "number", None) or not self.text_content:
            return
        painter.save()
        painter.setFont(self.make_item_font(max(9, self.font_size - 4)))
        txt = format_number(self.number, getattr(self, "number_fmt", NUM_FMT_CIRCLE))
        fm = QFontMetrics(self.make_item_font(max(9, self.font_size - 4)))
        br = fm.boundingRect(txt)
        w = float(br.width())
        h = float(br.height())
        painter.setPen(QPen(self.text_color, 1))
        painter.drawText(QRectF(rect.center().x() - w / 2.0,
                                rect.top() - h - 2.0, w, h),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine,
                         txt)
        painter.restore()

    def apply_style(self, st: dict) -> None:
        """把样式字典套用到文字块通用字段。"""
        try:
            fs = int(st.get("font_size", 18))
        except (TypeError, ValueError):
            fs = 18
        self.font_size = fs if fs > 0 else 18
        self.text_color = QColor(st["text_color"])
        self.font_family = st.get("font_family", self.font_family)
        self.font_weight = int(st.get("font_weight", self.font_weight))
        self.font_italic = bool(st.get("font_italic", self.font_italic))
        self.script = st.get("script", self.script)
        self.bg_enabled = bool(st["bg_enabled"])
        self.bg_fill_color = QColor(st["bg_fill_color"])
        self.bg_border_color = QColor(st["bg_border_color"])
        if isinstance(self, LeaderLineItem):
            self.endpoint_style = st.get("endpoint_style", "arrow")
            self.label_style = st.get("label_style", STYLE_PLAIN)
            self.above_dir = st.get("above_dir", self.above_dir)
            self.text_gap = float(st.get("text_gap", getattr(self, "text_gap", 5.0)))
            self.above_gap = float(st.get("above_gap", getattr(self, "above_gap", 5.0)))

    def unrotated_bounds(self) -> QRectF | None:
        """未旋转时的绘制包围盒（图片坐标）；None 表示无需特殊处理。

        子类实现包围盒主体逻辑；export_bounds() 在其上叠加旋转。
        """
        return None

    def export_bounds(self) -> QRectF | None:
        """导出时的绘制包围盒（图片坐标），自动叠加 rotation 旋转。"""
        return self._rotated_bounds(self.unrotated_bounds())

    def _rotated_bounds(self, b) -> QRectF | None:
        """把未旋转包围盒按 rotation 旋转后取外接矩形。"""
        rot = float(getattr(self, "rotation", 0.0) or 0.0)
        if not rot or b is None or not b.isValid():
            return b
        c = b.center()
        xs, ys = [], []
        for q in (b.topLeft(), b.topRight(), b.bottomRight(), b.bottomLeft()):
            p = rot_point(q, c, rot)
            xs.append(p.x())
            ys.append(p.y())
        return QRectF(min(xs), min(ys), max(xs) - min(xs),
                      max(ys) - min(ys))

    def _with_rotation(self, painter: QPainter, fn, export: bool) -> None:
        """以旋转后的画家状态执行绘制函数 fn(painter, export)。"""
        rot = float(getattr(self, "rotation", 0.0) or 0.0)
        b = self.unrotated_bounds()
        if not rot or b is None or not b.isValid():
            fn(painter, export)
            return
        c = b.center()
        painter.save()
        painter.translate(c)
        painter.rotate(rot)
        painter.translate(-c)
        try:
            fn(painter, export)
        finally:
            painter.restore()

    def _unrotated_hit(self, pos: QPointF) -> QPointF:
        """命中测试前把点击点逆旋转回未旋转坐标系。"""
        rot = float(getattr(self, "rotation", 0.0) or 0.0)
        if not rot:
            return pos
        b = self.unrotated_bounds()
        if b is None or not b.isValid():
            return pos
        return rot_point(QPointF(pos), b.center(), -rot)


class LeaderLineItem(AnnotationItem):
    """折线引线标注：端点指向 target_point，文字位于 text_point。

    折线形态：target_point -> corner(拐点) -> anchor(文字矩形边缘中点)。
    标注风格：
      box   —— 文字框 + 文字（现有样式）
      above —— 隐藏文字框，文字位于红线（引线锚点）正上方
      plain —— 隐藏文字框，文字在引线末端（现有透明样式）
    """

    def __init__(self, target_point, text_point, text_content: str,
                 line_color="#FF0000", line_width=2, arrow_size=14,
                 font_size=18, text_color="#000000", endpoint_style="arrow",
                 label_style=STYLE_PLAIN, text_gap=5.0, above_gap=5.0):
        super().__init__(text_content, font_size, text_color)
        self.target_point = QPointF(*target_point)
        self.text_point = QPointF(*text_point)
        self.line_color = QColor(line_color)
        self.line_width = max(1, int(line_width))
        self.arrow_size = float(arrow_size)
        self.endpoint_style = endpoint_style   # 'arrow' 三角 / 'dot' 圆点 / 'circle' 圆圈 / 'none' 无
        self.label_style = label_style         # 'box' / 'above' / 'plain'
        self.above_dir = ABOVE_DIR_LEFT        # above 横线方向：'left' / 'right'（创建时由画布按图片宽度解析）
        self.number: int | None = None         # 引线序号（None = 不显示）；由画布自动编号维护
        self.number_fmt = NUM_FMT_CIRCLE       # 序号格式
        self.text_gap = float(text_gap)        # 空白间隙：拐点/横线与文字的水平间隙（px）
        self.above_gap = float(above_gap)      # 文字在横线上/下方时，文字与横线的垂直间隙（px）

    def text_rect(self) -> QRectF:
        """文字实际显示矩形（图片坐标）。

        box/plain：左上角在 text_point；
        above：text_point 为文字中心（文字水平居中于横线，横线在其下方）。
        """
        r = self.text_rect_at_origin()
        if self.label_style == STYLE_ABOVE:
            return r.translated(QPointF(self.text_point.x() - r.width() / 2.0,
                                        self.text_point.y() - r.height() / 2.0))
        return r.translated(self.text_point)

    def edit_anchor(self) -> QPointF:
        """就地编辑器锚点（图片坐标）。above 风格时 text_point 是文字中心，
        由 start_inline_editor 统一换算为输入框左上角；其余风格 text_point 即左上角。"""
        return self.text_point

    def toggle_horizontal_dir(self) -> None:
        """单击翻转 above_text/below_text 横线方向（拐点在文字左端<->右端）。
        若当前为 AUTO，先落到当前自动方向，再取反，保证每次单击都掉头。"""
        r = self.text_rect()
        dx = r.center().x() - self.target_point.x()
        dy = r.center().y() - self.target_point.y()
        horizontal_leader = abs(dx) >= abs(dy)
        text_on_right = dx > 0
        d = getattr(self, "above_dir", ABOVE_DIR_AUTO)
        if d == ABOVE_DIR_LEFT:
            cur_left = True
        elif d == ABOVE_DIR_RIGHT:
            cur_left = False
        else:
            cur_left = text_on_right if horizontal_leader else True
        self.above_dir = ABOVE_DIR_RIGHT if cur_left else ABOVE_DIR_LEFT

    def _above_geometry(self):
        """above 风格折线结构（单侧横线）：target -> 横线内端 -> 横线外端。

        横线位于文字正下方（间距 ABOVE_GAP），内端在文字「方向侧边缘」正下方，
        外端沿 above_dir 方向再延伸 ABOVE_EXTEND_SINGLE——横线整体覆盖文字
        全部宽度（文字居中显示在横线上方）。
        返回 (inner, outer, text_rect)。
        """
        r = self.text_rect()
        line_y = r.bottom() + ABOVE_GAP
        sign = -1.0 if self.above_dir == ABOVE_DIR_LEFT else 1.0
        if sign < 0:
            inner = QPointF(r.left(), line_y)          # 左边缘正下方
        else:
            inner = QPointF(r.right(), line_y)         # 右边缘正下方
        outer = QPointF(inner.x() + sign * ABOVE_EXTEND_SINGLE, line_y)
        return inner, outer, r

    def _paint_endpoint(self, painter: QPainter, toward: QPointF) -> None:
        """在 target_point 处绘制端点符号（toward 为引线方向参考点）。"""
        if self.endpoint_style == "arrow":
            draw_arrow_head(painter, self.target_point, toward - self.target_point,
                            self.arrow_size, self.line_color)
        elif self.endpoint_style == "dot":
            r = max(2.0, self.arrow_size * 0.32)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.line_color))
            painter.drawEllipse(self.target_point, r, r)
            painter.restore()
        elif self.endpoint_style == "circle":
            r = max(3.0, self.arrow_size * 0.40)
            painter.save()
            painter.setPen(QPen(self.line_color, max(1.5, self.line_width)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.target_point, r, r)
            painter.restore()

    def geometry(self):
        """计算 (anchor, corner)。折线绘制顺序：target -> corner -> anchor。"""
        text_rect = self.text_rect()
        center = text_rect.center()
        dx = self.target_point.x() - center.x()
        dy = self.target_point.y() - center.y()
        # 沿占主导的方向，从文字矩形对应边的中点引出
        if abs(dx) >= abs(dy):
            anchor = QPointF(text_rect.right() if dx > 0 else text_rect.left(), center.y())
        else:
            anchor = QPointF(center.x(), text_rect.bottom() if dy > 0 else text_rect.top())
        dist = ((self.target_point.x() - anchor.x()) ** 2
                + (self.target_point.y() - anchor.y()) ** 2) ** 0.5
        if abs(dx) >= abs(dy):
            step = min(abs(dx) * 0.5, 80.0, dist)
            corner = QPointF(anchor.x() + (1 if dx > 0 else -1) * step, anchor.y())
        else:
            step = min(abs(dy) * 0.5, 80.0, dist)
            corner = QPointF(anchor.x(), anchor.y() + (1 if dy > 0 else -1) * step)
        return anchor, corner

    def paint(self, painter: QPainter, export: bool = False) -> None:
        # v1.7 需求1：标签与形状一致，支持绕自身包围盒中心旋转
        self._with_rotation(painter, self._paint_impl, export)

    def _paint_impl(self, painter: QPainter, export: bool) -> None:
        # 新样式
        if self.label_style == "above_text":
            self._paint_above_text(painter, export)
            return
        if self.label_style == "middle_text":
            self._paint_middle_text(painter, export)
            return
        if self.label_style == "below_text":
            self._paint_below_text(painter, export)
            return
        if self.label_style == "no_line":
            self._paint_no_line(painter, export)
            return
        # 旧样式
        if self.label_style == STYLE_ABOVE:
            self._paint_above(painter, export)
            return
        anchor, corner = self.geometry()
        # 「无端点」时用平头线帽，避免线段端点在目标处留下半圆凸起
        cap = (Qt.PenCapStyle.FlatCap if self.endpoint_style == "none"
               else Qt.PenCapStyle.RoundCap)
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([self.target_point, corner, anchor]))
        painter.restore()
        self._paint_endpoint(painter, corner)
        # 文字（按标注风格渲染）
        rect = self.text_rect()
        if self.label_style == STYLE_BOX:
            self.paint_text_block(painter, rect.topLeft())
        else:
            self.paint_text_only(painter, rect.topLeft())
        self.paint_number(painter, rect)
        # 选中高亮
        if self.selected and not export:
            self.paint_selection(painter, rect)
            # 「无端点」时目标点处不画任何标记（含选中把手）
            if self.endpoint_style != "none":
                painter.save()
                painter.setPen(QPen(SELECT_COLOR, 1))
                painter.setBrush(SELECT_COLOR)
                painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                        self.target_point.y() - HANDLE_R,
                                        HANDLE_R * 2, HANDLE_R * 2))
                painter.restore()

    def _paint_above(self, painter: QPainter, export: bool) -> None:
        """above 风格：target -> 横线内端 -> 横线外端；文字在横线上方居中（单侧横线）。"""
        inner, outer, r = self._above_geometry()
        cap = (Qt.PenCapStyle.FlatCap if self.endpoint_style == "none"
               else Qt.PenCapStyle.RoundCap)
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([self.target_point, inner, outer]))
        painter.restore()
        self._paint_endpoint(painter, inner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        # 选中态：above 风格文字不画任何框；「无端点」时目标点也不画标记
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _get_leader_geometry(self, style: str):
        """计算引线几何：返回 (corner拐点, 横线起点, 横线终点, 文字矩形)。
        使用 self.text_gap 控制文字和线之间的间隙，左右上下一致。
        """
        r = self.text_rect()
        gap = float(getattr(self, "text_gap", 5.0))  # 文字和线的间隙
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()

        # 判断方向：文字在目标点的哪个方向
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)  # 水平方向引线（左右）
        text_on_right = dx > 0  # 文字在目标点右边
        text_on_bottom = dy > 0  # 文字在目标点下方

        if style in ("above_text", "below_text"):
            # 文字在线上方/下方：横线与文字等宽。
            # 垂直方向“文字<->横线”的间隙用独立的 above_gap（上下间隙，0~20），
            # 水平拐点间隙 gx 仍用 gap（空白间隙）。
            vgap = float(getattr(self, "above_gap", gap))
            # 拐点端由 above_dir 决定：LEFT 拐点在左端、RIGHT 在右端，
            # AUTO 时水平引线取靠近目标点一侧、垂直引线默认左端。
            line_y = r.bottom() + vgap if style == "above_text" else r.top() - vgap
            _d = getattr(self, "above_dir", ABOVE_DIR_AUTO)
            if _d == ABOVE_DIR_LEFT:
                corner_left = True
            elif _d == ABOVE_DIR_RIGHT:
                corner_left = False
            else:
                corner_left = text_on_right if horizontal_leader else True
            gx = gap if horizontal_leader else 0.0
            if corner_left:
                corner = QPointF(r.left() - gx, line_y)
                line_end = QPointF(r.right(), line_y)
            else:
                corner = QPointF(r.right() + gx, line_y)
                line_end = QPointF(r.left(), line_y)
            return corner, corner, line_end, r

        elif style == "middle_text":
            # 文字在线中间：横线固定15px，文字和横线之间保持 gap 间隙
            fixed_len = 15.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    # 文字在右边：横线在文字左边，间隙 gap
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    # 文字在左边：横线在文字右边，间隙 gap
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        elif style == "no_line":
            # 无横线模式：套用中间模式，固定1px横线
            fixed_len = 1.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        return None, None, None, r

    def _paint_above_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线上方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("above_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点（不超过拐点）
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_middle_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线中间：横线固定5px，文字从横线结束后开始。"""
        corner, line_start, line_end, r = self._get_leader_geometry("middle_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 固定5px横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_below_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线下方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("below_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_no_line(self, painter: QPainter, export: bool = False) -> None:
        """无横线模式：套用中间模式逻辑，横线固定1px。"""
        # 临时把样式改成 middle_text 来计算几何，然后横线长度用1px
        r = self.text_rect()
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)

        fixed_len = 1.0  # 无横线模式固定1px
        if horizontal_leader:
            line_y = r.center().y()
            if dx > 0:
                # 文字在右边：横线从文字左边缘向左延伸
                line_start = QPointF(r.left() - fixed_len, line_y)
                line_end = QPointF(r.left(), line_y)
            else:
                # 文字在左边：横线从文字右边缘向右延伸
                line_start = QPointF(r.right() + fixed_len, line_y)
                line_end = QPointF(r.right(), line_y)
        else:
            line_y = r.center().y()
            line_start = QPointF(r.left() - fixed_len, line_y)
            line_end = QPointF(r.left(), line_y)

        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 1px小横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def hit_test(self, pos: QPointF, tol: float):
        """返回命中部位：
        - 'target'：斜线端点（箭头/圆点，拖动只移动端点）；
        - 'dline' ：斜线本身（整体平移，端点与文字一起动）；
        - 'hline' ：横线（拖动只移动文字位置）；
        - 'text'  ：文字块（拖动只移动文字位置）；
        - None    ：未命中。
        旧 STYLE_ABOVE 兼容返回 'line'（斜线+横线，整体平移）。"""
        pos = self._unrotated_hit(pos)
        if self.label_style == STYLE_ABOVE:
            inner, outer, r = self._above_geometry()
            if (pos - self.target_point).manhattanLength() <= tol + self.arrow_size:
                return "target"
            if (distance_to_segment(pos, self.target_point, inner) <= tol + 2
                    or distance_to_segment(pos, inner, outer) <= tol):
                return "line"
            if r.adjusted(-tol, -tol, tol, tol).contains(pos):
                return "text"
            return None
        corner, line_start, line_end, r = self._get_leader_geometry(self.label_style)
        if corner is None:
            # 旧样式（box/plain）兜底：geometry() 给出折线两段
            anchor, corner = self.geometry()
            line_start, line_end = corner, anchor
            r = self.text_rect()
        # 1) 斜线端点（优先，容差含箭头大小）
        if (pos - self.target_point).manhattanLength() <= tol + self.arrow_size:
            return "target"
        # 2) 文字块（文字与横线重叠时优先按文字处理，二者拖动行为一致）
        if r.adjusted(-tol, -tol, tol, tol).contains(pos):
            return "text"
        d_diag = distance_to_segment(pos, self.target_point, corner)
        d_horiz = distance_to_segment(pos, line_start, line_end)
        # 3) 横线（起点→终点）：离横线更近时优先（只移动文字位置）
        if d_horiz <= tol and d_horiz <= d_diag + 1.5:
            return "hline"
        # 4) 斜线（target→拐点）：整体平移
        if d_diag <= tol + 2:
            return "dline"
        # 5) 斜线容差外但仍在横线容差内
        if d_horiz <= tol:
            return "hline"
        return None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        # body/dline/line = 点在斜线或虚拟范围框空白处，整体平移（端点+文字）；
        # target = 只动斜线端点；text/hline = 只动文字（及横线）位置。
        if part in ("line", "target", "body", "dline"):
            self.target_point += QPointF(dx, dy)
        if part in ("line", "text", "body", "dline", "hline"):
            self.text_point += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        pad = max(self.line_width / 2.0 + 1.0, self.arrow_size / 2.0 + 1.0)
        rects = [self.text_rect().adjusted(-2, -2, 2, 2)]
        # 序号显示在文字正上方
        if getattr(self, "number", None):
            num_rect = QRectF(self.text_rect().center().x() - 20,
                              self.text_rect().top() - 26, 40, 26)
            rects.append(num_rect)
        rects.append(QRectF(self.target_point.x() - pad, self.target_point.y() - pad,
                            pad * 2, pad * 2))
        if self.label_style == STYLE_ABOVE:
            inner, outer, _ = self._above_geometry()
            rects.append(QRectF(min(inner.x(), outer.x()),
                                inner.y() - self.line_width / 2.0,
                                abs(outer.x() - inner.x()), self.line_width))
        else:
            anchor, corner = self.geometry()
            xs = [self.target_point.x(), corner.x(), anchor.x()]
            ys = [self.target_point.y(), corner.y(), anchor.y()]
            rects.append(QRectF(min(xs) - pad, min(ys) - pad,
                                max(xs) - min(xs) + 2 * pad,
                                max(ys) - min(ys) + 2 * pad))
        union = rects[0]
        for r in rects[1:]:
            union = union.united(r)
        return union


class TextItem(AnnotationItem):
    """纯文本批注：无引线，可自由拖动。"""

    def __init__(self, pos, text_content: str, font_size=18, text_color="#000000"):
        super().__init__(text_content, font_size, text_color)
        self.pos = QPointF(*pos)

    def edit_anchor(self) -> QPointF:
        return self.pos

    def text_rect(self) -> QRectF:
        return self.text_rect_at_origin().translated(self.pos)

    def unrotated_bounds(self) -> QRectF:
        return self.text_rect_at_origin().translated(self.pos).adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, export: bool = False) -> None:
        # v1.7 需求1：文本与形状一致，支持绕文字框中心旋转
        self._with_rotation(painter, self._paint_impl, export)

    def _paint_impl(self, painter: QPainter, export: bool) -> None:
        self.paint_text_block(painter, self.pos)
        if self.selected and not export:
            text_rect = self.text_rect_at_origin().translated(self.pos)
            self.paint_selection(painter, text_rect)

    def _get_leader_geometry(self, style: str):
        """计算引线几何：返回 (corner拐点, 横线起点, 横线终点, 文字矩形)。
        使用 self.text_gap 控制文字和线之间的间隙，左右上下一致。
        """
        r = self.text_rect()
        gap = float(getattr(self, "text_gap", 5.0))  # 文字和线的间隙
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()

        # 判断方向：文字在目标点的哪个方向
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)  # 水平方向引线（左右）
        text_on_right = dx > 0  # 文字在目标点右边
        text_on_bottom = dy > 0  # 文字在目标点下方

        if style in ("above_text", "below_text"):
            # 文字在线上方/下方：横线与文字等宽。
            # 垂直方向“文字<->横线”的间隙用独立的 above_gap（上下间隙，0~20），
            # 水平拐点间隙 gx 仍用 gap（空白间隙）。
            vgap = float(getattr(self, "above_gap", gap))
            # 拐点端由 above_dir 决定：LEFT 拐点在左端、RIGHT 在右端，
            # AUTO 时水平引线取靠近目标点一侧、垂直引线默认左端。
            line_y = r.bottom() + vgap if style == "above_text" else r.top() - vgap
            _d = getattr(self, "above_dir", ABOVE_DIR_AUTO)
            if _d == ABOVE_DIR_LEFT:
                corner_left = True
            elif _d == ABOVE_DIR_RIGHT:
                corner_left = False
            else:
                corner_left = text_on_right if horizontal_leader else True
            gx = gap if horizontal_leader else 0.0
            if corner_left:
                corner = QPointF(r.left() - gx, line_y)
                line_end = QPointF(r.right(), line_y)
            else:
                corner = QPointF(r.right() + gx, line_y)
                line_end = QPointF(r.left(), line_y)
            return corner, corner, line_end, r

        elif style == "middle_text":
            # 文字在线中间：横线固定15px，文字和横线之间保持 gap 间隙
            fixed_len = 15.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    # 文字在右边：横线在文字左边，间隙 gap
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    # 文字在左边：横线在文字右边，间隙 gap
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        elif style == "no_line":
            # 无横线模式：套用中间模式，固定1px横线
            fixed_len = 1.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        return None, None, None, r

    def _paint_above_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线上方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("above_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点（不超过拐点）
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_middle_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线中间：横线固定5px，文字从横线结束后开始。"""
        corner, line_start, line_end, r = self._get_leader_geometry("middle_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 固定5px横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_below_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线下方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("below_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_no_line(self, painter: QPainter, export: bool = False) -> None:
        """无横线模式：套用中间模式逻辑，横线固定1px。"""
        # 临时把样式改成 middle_text 来计算几何，然后横线长度用1px
        r = self.text_rect()
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)

        fixed_len = 1.0  # 无横线模式固定1px
        if horizontal_leader:
            line_y = r.center().y()
            if dx > 0:
                # 文字在右边：横线从文字左边缘向左延伸
                line_start = QPointF(r.left() - fixed_len, line_y)
                line_end = QPointF(r.left(), line_y)
            else:
                # 文字在左边：横线从文字右边缘向右延伸
                line_start = QPointF(r.right() + fixed_len, line_y)
                line_end = QPointF(r.right(), line_y)
        else:
            line_y = r.center().y()
            line_start = QPointF(r.left() - fixed_len, line_y)
            line_end = QPointF(r.left(), line_y)

        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 1px小横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def hit_test(self, pos: QPointF, tol: float):
        pos = self._unrotated_hit(pos)
        if self.text_rect_at_origin().translated(self.pos).adjusted(-tol, -tol, tol, tol).contains(pos):
            return "text"
        return None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        self.pos += QPointF(dx, dy)


class ShapeItem(AnnotationItem):
    """形状元素（画图工具风格）：矩形/椭圆/三角形等，可设边线与填充颜色。"""

    def __init__(self, p1, p2, shape: str = SHAPE_RECT,
                 border_color="#FF0000", fill_color="#FFFFFF00",
                 line_width=2, text_color="#000000", font_size=18):
        super().__init__("", font_size, text_color)
        self.p1 = QPointF(*p1)
        self.p2 = QPointF(*p2)
        self.shape = shape
        self.border_color = QColor(border_color)
        self.fill_color = QColor(fill_color)   # 默认透明
        self.line_width = max(1, int(line_width))
        # 多点折线顶点（仅 SHAPE_LINE）：None 表示普通两点直线；
        # 非空时按顶点顺序逐段连接，p1/p2 同步为首尾点用于包围盒/兼容旧存档。
        self.points = None
        self.rotation = 0.0   # v1.7 需求2：绕 rect 中心旋转角度（度）
        # v2.0 需求5：形状内嵌文字（含直线），默认居中；可上/下/中
        self.text_pos = "center"
        # v2.1 需求2（本轮重构）：标注类形状尾尖位置（仅 CALLOUT_SHAPES 生效）。
        # tail_apex：尾尖在【未旋转图片坐标】中的绝对位置，可在主体四周任意
        # 位置拖动，主体 p1/p2 尺寸恒定不变；None 时用默认尾尖。
        # tail_x/tail_len 仅用于兼容旧存档（比例值），首次访问时迁移为绝对点。
        self.tail_apex = None
        self.tail_x = None
        self.tail_len = None

    def tail_params(self):
        """兼容旧接口：把当前尾尖换算回 (tail_x, tail_len) 比例（非标注类返回 None）。"""
        if self.shape not in CALLOUT_SHAPES:
            return None
        ap = self.tail_apex_point()
        r = self.rect()
        if r.width() < 1e-9 or r.height() < 1e-9:
            return (0.30, 0.25)
        tx = (ap.x() - r.left()) / r.width()
        tl = (ap.y() - r.bottom()) / r.height()
        return (max(0.05, min(0.95, tx)),
                max(-0.30, min(0.85, tl)))

    def tail_apex_point(self):
        """尾尖绝对位置（未旋转图片坐标）。

        优先使用 tail_apex；否则从旧版 tail_x/tail_len 比例迁移并缓存；
        再否则使用默认尾尖。非标注类形状返回 None。
        """
        if self.shape not in CALLOUT_SHAPES:
            return None
        if self.tail_apex is not None:
            return QPointF(self.tail_apex)
        r = self.rect()
        if self.tail_x is not None or self.tail_len is not None:
            tx = self.tail_x if self.tail_x is not None else 0.30
            tl = self.tail_len if self.tail_len is not None else 0.25
            tx = max(0.05, min(0.95, float(tx)))
            tl = max(0.0, min(0.85, float(tl)))   # 旧负值无意义，归零
            self.tail_apex = QPointF(r.left() + tx * r.width(),
                                     r.bottom() + tl * r.height())
        else:
            self.tail_apex = callout_geom.default_apex(r)
        return QPointF(self.tail_apex)

    def set_tail_apex(self, pt) -> None:
        """拖动黄色控制点：尾尖可在主体四周任意位置（不钳制、主体不变形）。"""
        if self.shape in CALLOUT_SHAPES:
            self.tail_apex = QPointF(pt)
            # 已迁移为绝对点，旧比例不再使用
            self.tail_x = None
            self.tail_len = None

    def tail_tip(self):
        """尾巴尖在未旋转图片坐标中的位置（供 canvas 绘制黄色控制点）。"""
        return self.tail_apex_point()

    def _is_closed(self) -> bool:
        """折线是否闭合：首尾顶点重合（v1.6 需求5 自动磁吸闭合产物）。"""
        if not self.points or len(self.points) < 3:
            return False
        p0 = self.points[0]
        pn = self.points[-1]
        return abs(p0.x() - pn.x()) < 0.5 and abs(p0.y() - pn.y()) < 0.5

    def rect(self) -> QRectF:
        if self.shape == SHAPE_LINE and self.points and len(self.points) >= 2:
            return QPolygonF(self.points).boundingRect().normalized()
        return QRectF(self.p1, self.p2).normalized()

    def unrotated_bounds(self) -> QRectF:
        """未旋转包围盒（手柄/旋转中心使用）。"""
        return QRectF(self.rect())
    def text_rect(self) -> QRectF:
        return self.rect()

    def paint(self, painter: QPainter, export: bool = False) -> None:
        painter.save()
        # v1.7 需求2：绕 rect 中心旋转后绘制（直线折线同样适用）
        _rot = float(getattr(self, "rotation", 0.0))
        if _rot:
            _c = self.rect().center()
            painter.translate(_c)
            painter.rotate(_rot)
            painter.translate(-_c)
        if self.shape == SHAPE_LINE:
            # 直线严格连接真实顶点：多点折线逐段连接；两点直线直连 p1->p2。
            # 不能用归一化矩形对角线（否则反向拖时会被换成另一条对角线）。
            path = QPainterPath()
            if self.points and len(self.points) >= 2:
                path.moveTo(self.points[0])
                for _v in self.points[1:]:
                    path.lineTo(_v)
                if self._is_closed():
                    path.closeSubpath()   # v1.6 需求5：首尾重合 → 封闭图形
            else:
                path.moveTo(self.p1)
                path.lineTo(self.p2)
        else:
            path = shape_path(self.shape, self.rect(),
                              tail=self.tail_apex_point() if self.shape in CALLOUT_SHAPES else None)
        # v2.x 需求1：边线设为透明（alpha=0）时不再绘制边框（隐藏）
        pen = QPen(self.border_color, self.line_width,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        if self.border_color.alpha() == 0:
            pen.setStyle(Qt.PenStyle.NoPen)
        painter.setPen(pen)
        if self.shape == SHAPE_LINE and not self._is_closed():
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.fill_color.alpha() == 0:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setBrush(self.fill_color)
        painter.drawPath(path)
        self._paint_shape_text(painter)
        painter.restore()
        # 选中框不再由元素画：canvas 负责绘制随形状旋转的蓝色虚线框 +
        # 8 缩放点 + 旋转手柄（v1.7 需求2），避免双重虚线框

    def _paint_shape_text(self, painter: QPainter) -> None:
        """v2.0：形状内嵌文字（含直线）。默认水平居中；垂直位置按 text_pos。"""
        content = (getattr(self, "text_content", "") or "").strip()
        if not content:
            return
        r = self.rect()
        if not r.isValid() or r.width() < 4 or r.height() < 4:
            return
        painter.save()
        painter.setFont(self.make_item_font())
        pad = 4.0
        tr = r.adjusted(pad, pad, -pad, -pad)
        pos = getattr(self, "text_pos", "center")
        if pos == "top":
            valign = Qt.AlignmentFlag.AlignTop
        elif pos == "bottom":
            valign = Qt.AlignmentFlag.AlignBottom
        else:
            valign = Qt.AlignmentFlag.AlignVCenter
        flags = (Qt.AlignmentFlag.AlignHCenter | valign
                 | Qt.TextFlag.TextWordWrap)
        painter.setPen(QPen(self.text_color, 1))
        painter.drawText(tr, flags, content.replace("&", "&&"))
        painter.restore()

    def edit_anchor(self) -> QPointF:
        """就地文字编辑器锚点：形状包围盒中心（图片坐标）。"""
        return self.rect().center()

    def _get_leader_geometry(self, style: str):
        """计算引线几何：返回 (corner拐点, 横线起点, 横线终点, 文字矩形)。
        使用 self.text_gap 控制文字和线之间的间隙，左右上下一致。
        """
        r = self.text_rect()
        gap = float(getattr(self, "text_gap", 5.0))  # 文字和线的间隙
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()

        # 判断方向：文字在目标点的哪个方向
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)  # 水平方向引线（左右）
        text_on_right = dx > 0  # 文字在目标点右边
        text_on_bottom = dy > 0  # 文字在目标点下方

        if style in ("above_text", "below_text"):
            # 文字在线上方/下方：横线与文字等宽。
            # 垂直方向“文字<->横线”的间隙用独立的 above_gap（上下间隙，0~20），
            # 水平拐点间隙 gx 仍用 gap（空白间隙）。
            vgap = float(getattr(self, "above_gap", gap))
            # 拐点端由 above_dir 决定：LEFT 拐点在左端、RIGHT 在右端，
            # AUTO 时水平引线取靠近目标点一侧、垂直引线默认左端。
            line_y = r.bottom() + vgap if style == "above_text" else r.top() - vgap
            _d = getattr(self, "above_dir", ABOVE_DIR_AUTO)
            if _d == ABOVE_DIR_LEFT:
                corner_left = True
            elif _d == ABOVE_DIR_RIGHT:
                corner_left = False
            else:
                corner_left = text_on_right if horizontal_leader else True
            gx = gap if horizontal_leader else 0.0
            if corner_left:
                corner = QPointF(r.left() - gx, line_y)
                line_end = QPointF(r.right(), line_y)
            else:
                corner = QPointF(r.right() + gx, line_y)
                line_end = QPointF(r.left(), line_y)
            return corner, corner, line_end, r

        elif style == "middle_text":
            # 文字在线中间：横线固定15px，文字和横线之间保持 gap 间隙
            fixed_len = 15.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    # 文字在右边：横线在文字左边，间隙 gap
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    # 文字在左边：横线在文字右边，间隙 gap
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        elif style == "no_line":
            # 无横线模式：套用中间模式，固定1px横线
            fixed_len = 1.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        return None, None, None, r

    def _paint_above_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线上方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("above_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点（不超过拐点）
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_middle_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线中间：横线固定5px，文字从横线结束后开始。"""
        corner, line_start, line_end, r = self._get_leader_geometry("middle_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 固定5px横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_below_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线下方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("below_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_no_line(self, painter: QPainter, export: bool = False) -> None:
        """无横线模式：套用中间模式逻辑，横线固定1px。"""
        # 临时把样式改成 middle_text 来计算几何，然后横线长度用1px
        r = self.text_rect()
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)

        fixed_len = 1.0  # 无横线模式固定1px
        if horizontal_leader:
            line_y = r.center().y()
            if dx > 0:
                # 文字在右边：横线从文字左边缘向左延伸
                line_start = QPointF(r.left() - fixed_len, line_y)
                line_end = QPointF(r.left(), line_y)
            else:
                # 文字在左边：横线从文字右边缘向右延伸
                line_start = QPointF(r.right() + fixed_len, line_y)
                line_end = QPointF(r.right(), line_y)
        else:
            line_y = r.center().y()
            line_start = QPointF(r.left() - fixed_len, line_y)
            line_end = QPointF(r.left(), line_y)

        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 1px小横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def hit_test(self, pos: QPointF, tol: float):
        r = self.rect().adjusted(-tol, -tol, tol, tol)
        if not r.contains(pos):
            return None
        # v1.7 需求2：命中点先逆旋转到未旋转坐标系再测距，保证旋转后点击准确
        _rot = float(getattr(self, "rotation", 0.0))
        if _rot:
            _c = r.center()
            import math as _m
            _rad = _m.radians(-_rot)
            _dx, _dy = pos.x() - _c.x(), pos.y() - _c.y()
            pos = QPointF(_c.x() + _dx * _m.cos(_rad) - _dy * _m.sin(_rad),
                          _c.y() + _dx * _m.sin(_rad) + _dy * _m.cos(_rad))
        if self.shape == SHAPE_LINE:
            # 点到折线距离：逐段取最小值（严格按真实顶点；闭合时含首尾连线）
            import math
            _verts = (self.points if (self.points and len(self.points) >= 2)
                      else [self.p1, self.p2])
            if self._is_closed():
                _verts = list(_verts) + [_verts[0]]
            best = None
            for _i in range(len(_verts) - 1):
                x1, y1 = _verts[_i].x(), _verts[_i].y()
                x2, y2 = _verts[_i + 1].x(), _verts[_i + 1].y()
                dx, dy = x2 - x1, y2 - y1
                if dx * dx + dy * dy < 1e-9:
                    dseg = math.hypot(pos.x() - x1, pos.y() - y1)
                else:
                    t = ((pos.x() - x1) * dx + (pos.y() - y1) * dy) / (dx * dx + dy * dy)
                    t = max(0.0, min(1.0, t))
                    qx, qy = x1 + t * dx, y1 + t * dy
                    dseg = math.hypot(pos.x() - qx, pos.y() - qy)
                best = dseg if best is None else min(best, dseg)
            if best is not None and best <= tol + self.line_width / 2.0:
                return "body"
            # 封闭且带填充：区域内部也视为命中
            if self._is_closed() and self.fill_color.alpha() > 0:
                return "body"
            return None
        if self.fill_color.alpha() > 0:
            return "body"
        # 无填充时仅在边界附近命中
        path = shape_path(self.shape, self.rect(),
                          tail=self.tail_apex_point() if self.shape in CALLOUT_SHAPES else None)
        if path.intersects(QRectF(pos.x() - tol, pos.y() - tol, tol * 2, tol * 2)):
            return "body"
        return None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        self.p1 += QPointF(dx, dy)
        self.p2 += QPointF(dx, dy)
        if self.points:
            self.points = [p + QPointF(dx, dy) for p in self.points]
        # 尾尖随主体一起平移（未旋转坐标）
        if self.shape in CALLOUT_SHAPES and self.tail_apex is not None:
            self.tail_apex = self.tail_apex + QPointF(dx, dy)

    def export_bounds(self) -> QRectF:
        r = self.rect()
        _rot = float(getattr(self, "rotation", 0.0))
        # 标注类形状：尾尖可能伸出主体外，导出/高亮范围需把尾尖并进来
        apex = (self.tail_apex_point()
                if self.shape in CALLOUT_SHAPES else None)
        if _rot:
            # v1.7：返回旋转后的外接矩形（供高亮虚线框/导出范围使用）
            import math as _m
            c = r.center()
            _rad = _m.radians(_rot)
            _co, _si = _m.cos(_rad), _m.sin(_rad)
            _corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
            if apex is not None:
                _corners.append(apex)
            _p = []
            for _q in _corners:
                _dx, _dy = _q.x() - c.x(), _q.y() - c.y()
                _p.append(QPointF(c.x() + _dx * _co - _dy * _si,
                                  c.y() + _dx * _si + _dy * _co))
            r = QRectF(_p[0], _p[1])
            for _q in _p:
                r = r.united(QRectF(_q.x() - 0.01, _q.y() - 0.01, 0.02, 0.02))
        elif apex is not None:
            # QRectF.united 会忽略零面积矩形，尾尖用 1px 小矩形并入
            r = r.united(QRectF(apex.x() - 1, apex.y() - 1, 2, 2))
        return r.adjusted(-2, -2, 2, 2)


class PenItem(AnnotationItem):
    """画笔元素：自由手绘折线（点序列）。"""

    def __init__(self, points, pen_color="#000000", pen_width=3,
                 text_color="#000000", font_size=18):
        super().__init__("", font_size, text_color)
        self.points = [p if isinstance(p, QPointF) else QPointF(p[0], p[1])
                       for p in points]
        self.pen_color = QColor(pen_color)
        self.pen_width = max(1, int(pen_width))

    def text_rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def paint(self, painter: QPainter, export: bool = False) -> None:
        if len(self.points) < 2:
            return
        painter.save()
        painter.setPen(QPen(self.pen_color, self.pen_width,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(self.points))
        painter.restore()
        if self.selected and not export:
            self.paint_selection(painter, self.text_rect())

    def _get_leader_geometry(self, style: str):
        """计算引线几何：返回 (corner拐点, 横线起点, 横线终点, 文字矩形)。
        使用 self.text_gap 控制文字和线之间的间隙，左右上下一致。
        """
        r = self.text_rect()
        gap = float(getattr(self, "text_gap", 5.0))  # 文字和线的间隙
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()

        # 判断方向：文字在目标点的哪个方向
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)  # 水平方向引线（左右）
        text_on_right = dx > 0  # 文字在目标点右边
        text_on_bottom = dy > 0  # 文字在目标点下方

        if style in ("above_text", "below_text"):
            # 文字在线上方/下方：横线与文字等宽。
            # 垂直方向“文字<->横线”的间隙用独立的 above_gap（上下间隙，0~20），
            # 水平拐点间隙 gx 仍用 gap（空白间隙）。
            vgap = float(getattr(self, "above_gap", gap))
            # 拐点端由 above_dir 决定：LEFT 拐点在左端、RIGHT 在右端，
            # AUTO 时水平引线取靠近目标点一侧、垂直引线默认左端。
            line_y = r.bottom() + vgap if style == "above_text" else r.top() - vgap
            _d = getattr(self, "above_dir", ABOVE_DIR_AUTO)
            if _d == ABOVE_DIR_LEFT:
                corner_left = True
            elif _d == ABOVE_DIR_RIGHT:
                corner_left = False
            else:
                corner_left = text_on_right if horizontal_leader else True
            gx = gap if horizontal_leader else 0.0
            if corner_left:
                corner = QPointF(r.left() - gx, line_y)
                line_end = QPointF(r.right(), line_y)
            else:
                corner = QPointF(r.right() + gx, line_y)
                line_end = QPointF(r.left(), line_y)
            return corner, corner, line_end, r

        elif style == "middle_text":
            # 文字在线中间：横线固定15px，文字和横线之间保持 gap 间隙
            fixed_len = 15.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    # 文字在右边：横线在文字左边，间隙 gap
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    # 文字在左边：横线在文字右边，间隙 gap
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        elif style == "no_line":
            # 无横线模式：套用中间模式，固定1px横线
            fixed_len = 1.0
            line_y = r.center().y()
            if horizontal_leader:
                if text_on_right:
                    line_end = QPointF(r.left() - gap, line_y)
                    line_start = QPointF(line_end.x() - fixed_len, line_y)
                else:
                    line_end = QPointF(r.right() + gap, line_y)
                    line_start = QPointF(line_end.x() + fixed_len, line_y)
                corner = line_end
            else:
                line_end = QPointF(r.left() - gap, line_y)
                line_start = QPointF(line_end.x() - fixed_len, line_y)
                corner = line_end
            return corner, line_start, line_end, r

        return None, None, None, r

    def _paint_above_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线上方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("above_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点（不超过拐点）
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_middle_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线中间：横线固定5px，文字从横线结束后开始。"""
        corner, line_start, line_end, r = self._get_leader_geometry("middle_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 固定5px横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_below_text(self, painter: QPainter, export: bool = False) -> None:
        """文字在线下方：横线和文字等宽，拐点是文字对齐起点。"""
        corner, line_start, line_end, r = self._get_leader_geometry("below_text")
        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 拐点
        painter.drawLine(self.target_point, corner)
        # 横线：拐点 -> 横线终点
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, corner)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def _paint_no_line(self, painter: QPainter, export: bool = False) -> None:
        """无横线模式：套用中间模式逻辑，横线固定1px。"""
        # 临时把样式改成 middle_text 来计算几何，然后横线长度用1px
        r = self.text_rect()
        cx = self.target_point.x()
        cy = self.target_point.y()
        tx = r.center().x()
        ty = r.center().y()
        dx = tx - cx
        dy = ty - cy
        horizontal_leader = abs(dx) >= abs(dy)

        fixed_len = 1.0  # 无横线模式固定1px
        if horizontal_leader:
            line_y = r.center().y()
            if dx > 0:
                # 文字在右边：横线从文字左边缘向左延伸
                line_start = QPointF(r.left() - fixed_len, line_y)
                line_end = QPointF(r.left(), line_y)
            else:
                # 文字在左边：横线从文字右边缘向右延伸
                line_start = QPointF(r.right() + fixed_len, line_y)
                line_end = QPointF(r.right(), line_y)
        else:
            line_y = r.center().y()
            line_start = QPointF(r.left() - fixed_len, line_y)
            line_end = QPointF(r.left(), line_y)

        cap = Qt.PenCapStyle.FlatCap if self.endpoint_style == "none" else Qt.PenCapStyle.RoundCap
        painter.save()
        painter.setPen(QPen(self.line_color, self.line_width, Qt.PenStyle.SolidLine,
                            cap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # 斜线：目标点 -> 横线起点
        painter.drawLine(self.target_point, line_start)
        # 1px小横线
        painter.drawLine(line_start, line_end)
        painter.restore()

        self._paint_endpoint(painter, line_start)
        self.paint_text_only(painter, r.topLeft())
        self.paint_number(painter, r)
        if self.selected and not export and self.endpoint_style != "none":
            painter.save()
            painter.setPen(QPen(SELECT_COLOR, 1))
            painter.setBrush(SELECT_COLOR)
            painter.drawRect(QRectF(self.target_point.x() - HANDLE_R,
                                    self.target_point.y() - HANDLE_R,
                                    HANDLE_R * 2, HANDLE_R * 2))
            painter.restore()

    def hit_test(self, pos: QPointF, tol: float):
        for a, b in zip(self.points, self.points[1:]):
            if distance_to_segment(pos, a, b) <= tol + self.pen_width / 2.0:
                return "body"
        if self.points and (pos - self.points[0]).manhattanLength() <= tol + 2:
            return "body"
        return None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        for p in self.points:
            p += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        r = self.text_rect()
        if r.isNull():
            return None
        pad = self.pen_width / 2.0 + 2
        return r.adjusted(-pad, -pad, pad, pad)


class HighlightItem(AnnotationItem):
    """荧光笔元素：半透明粗自由曲线，对底图起高亮作用。

    points 为图片坐标点序列；hl_color 为不透明基色，hl_alpha 为不透明度
    （0-255），绘制时把基色与 alpha 合成，圆头圆角保证涂抹连续。
    """

    def __init__(self, points, hl_color="#FFE600", hl_width=22, hl_alpha=80,
                 text_color="#000000", font_size=18):
        super().__init__("", font_size, text_color)
        self.points = [p if isinstance(p, QPointF) else QPointF(p[0], p[1])
                       for p in points]
        self.hl_color = QColor(hl_color)
        self.hl_width = max(2, int(hl_width))
        self.hl_alpha = max(1, min(255, int(hl_alpha)))

    def _paint_color(self) -> QColor:
        col = QColor(self.hl_color)
        col.setAlpha(self.hl_alpha)
        return col

    def text_rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def paint(self, painter: QPainter, export: bool = False) -> None:
        if len(self.points) < 2:
            # 单点也画一个圆点，避免单击无反馈
            if self.points:
                painter.save()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._paint_color())
                r = self.hl_width / 2.0
                painter.drawEllipse(self.points[0], r, r)
                painter.restore()
            return
        painter.save()
        pen = QPen(self._paint_color(), self.hl_width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(self.points))
        painter.restore()
        if self.selected and not export:
            self.paint_selection(painter, self.text_rect())

    def hit_test(self, pos: QPointF, tol: float):
        half = self.hl_width / 2.0
        for a, b in zip(self.points, self.points[1:]):
            if distance_to_segment(pos, a, b) <= tol + half:
                return "body"
        if self.points and (pos - self.points[0]).manhattanLength() <= tol + half:
            return "body"
        return None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        for p in self.points:
            p += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        r = self.text_rect()
        if r.isNull():
            return None
        pad = self.hl_width / 2.0 + 2
        return r.adjusted(-pad, -pad, pad, pad)


class MosaicItem(AnnotationItem):
    """马赛克元素：对原图指定矩形区域做像素化（打码）。

    p1/p2 为图片坐标对角点，block_size 为马赛克块边长（像素）。
    原图 _source 由画布在加载/反序列化后注入（set_source），不参与序列化；
    绘制时实时从原图采样 -> 缩小 -> 最近邻放大，得到马赛克效果。
    """

    def __init__(self, p1, p2, block_size=10, show_border=True,
                 text_color="#000000", font_size=18):
        super().__init__("", font_size, text_color)
        self.p1 = QPointF(*p1)
        self.p2 = QPointF(*p2)
        self.block_size = max(2, int(block_size))
        self.show_border = bool(show_border)   # 是否绘制马赛克区域边框
        self._source = None  # QPixmap，运行时注入

    def set_source(self, pixmap) -> None:
        self._source = pixmap

    def __deepcopy__(self, memo):
        # QPixmap 不可 deepcopy/pickle；撤销快照里不携带原图，
        # 恢复后由画布在绘制时惰性重新注入当前原图。
        import copy as _copy
        new = MosaicItem.__new__(MosaicItem)
        memo[id(self)] = new
        for k, v in self.__dict__.items():
            new.__dict__[k] = None if k == "_source" else _copy.deepcopy(v, memo)
        return new

    def rect(self) -> QRectF:
        return QRectF(self.p1, self.p2).normalized()

    def text_rect(self) -> QRectF:
        return self.rect()

    def _render_mosaic(self):
        """返回 (目标矩形 QRectF, 马赛克 QPixmap)；无可用原图时返回 None。"""
        if self._source is None or getattr(self._source, "isNull", lambda: True)():
            return None
        full = self._source.rect()
        src = QRectF(self.rect()).toRect().intersected(full)
        if src.isEmpty():
            return None
        piece = self._source.copy(src)
        bw = max(2, self.block_size)
        sw = max(1, src.width() // bw)
        sh = max(1, src.height() // bw)
        small = piece.scaled(sw, sh,
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        big = small.scaled(src.width(), src.height(),
                           Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.FastTransformation)
        return src, big

    def _feather(self, pm: QPixmap) -> QPixmap:
        """v2.x：把马赛克四周边缘羽化，使其与原图柔和过渡、不突兀。

        在与 pm 同尺寸的透明层上先按 pm 绘制不透明底，再用「边缘透明、中心不透明」
        的渐变蒙版（DestinationIn）裁出羽化边缘；羽化宽度约为一个马赛克块。
        """
        w, h = pm.width(), pm.height()
        if w < 8 or h < 8:
            return pm
        f = max(2.0, min(self.block_size, w / 4.0, h / 4.0))
        out = QPixmap(w, h)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.drawPixmap(0, 0, pm)
        # 渐变蒙版：水平方向左右边缘渐变，垂直方向上下边缘渐变，两次相乘
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        # 水平羽化
        gh = QLinearGradient(0, 0, w, 0)
        gh.setColorAt(0.0, QColor(0, 0, 0, 0))
        gh.setColorAt(min(1.0, f / w), QColor(0, 0, 0, 255))
        gh.setColorAt(max(0.0, 1.0 - f / w), QColor(0, 0, 0, 255))
        gh.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, w, h), gh)
        # 垂直羽化
        gv = QLinearGradient(0, 0, 0, h)
        gv.setColorAt(0.0, QColor(0, 0, 0, 0))
        gv.setColorAt(min(1.0, f / h), QColor(0, 0, 0, 255))
        gv.setColorAt(max(0.0, 1.0 - f / h), QColor(0, 0, 0, 255))
        gv.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, w, h), gv)
        p.end()
        return out

    def paint(self, painter: QPainter, export: bool = False) -> None:
        r = self.rect()
        painter.save()
        res = self._render_mosaic()
        if res is None:
            # 原图尚未注入：半透明占位，保证元素可见、可选中
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(150, 150, 150, 90))
            painter.drawRect(r)
        else:
            target_rect, big = res
            # v2.x：边缘羽化，柔和过渡（导出时也生效）
            painter.drawPixmap(target_rect, self._feather(big))
        if self.show_border:
            painter.setPen(QPen(QColor(0, 120, 215) if self.selected else QColor(0, 0, 0, 60),
                                1, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)
        painter.restore()
        if self.selected and not export:
            self.paint_selection(painter, r)

    def hit_test(self, pos: QPointF, tol: float):
        rr = self.rect().adjusted(-tol, -tol, tol, tol)
        return "body" if rr.contains(pos) else None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        self.p1 += QPointF(dx, dy)
        self.p2 += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        return self.rect().adjusted(-2, -2, 2, 2)


class EmojiItem(AnnotationItem):
    """表情元素：在图片上放置一个彩色 emoji，pos 为其包围盒中心。"""

    EMOJI_FAMILIES = ["Segoe UI Emoji", "Apple Color Emoji",
                      "Noto Color Emoji", "Microsoft YaHei", "sans-serif"]

    def __init__(self, pos, emoji: str = "😀", font_size=40,
                 text_color="#000000"):
        super().__init__(emoji, font_size, text_color)
        self.pos = QPointF(*pos)
        self.emoji = emoji or "😀"

    def _emoji_font(self) -> QFont:
        f = QFont()
        try:
            f.setFamilies(self.EMOJI_FAMILIES)
        except Exception:
            f.setFamily("Segoe UI Emoji")
        f.setPixelSize(max(8, int(self.font_size)))
        return f

    def _emoji_size(self):
        fm = QFontMetrics(self._emoji_font())
        w = max(1.0, float(fm.horizontalAdvance(self.emoji)))
        h = max(1.0, float(fm.height()))
        return w, h

    def text_rect(self) -> QRectF:
        w, h = self._emoji_size()
        return QRectF(self.pos.x() - w / 2.0, self.pos.y() - h / 2.0, w, h)

    def paint(self, painter: QPainter, export: bool = False) -> None:
        # v1.7 需求1：表情与形状一致，支持绕表情中心旋转
        self._with_rotation(painter, self._paint_impl, export)

    def _paint_impl(self, painter: QPainter, export: bool) -> None:
        r = self.text_rect()
        painter.save()
        painter.setFont(self._emoji_font())
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self.emoji)
        painter.restore()
        if self.selected and not export:
            self.paint_selection(painter, r)

    def hit_test(self, pos: QPointF, tol: float):
        pos = self._unrotated_hit(pos)
        rr = self.text_rect().adjusted(-tol, -tol, tol, tol)
        return "body" if rr.contains(pos) else None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        self.pos += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        return self.text_rect().adjusted(-2, -2, 2, 2)


class ImageItem(AnnotationItem):
    """v2.x 图片元素：把外部图片/剪贴板图作为一个独立图层元素。

    p1/p2 为图片坐标对角点（与形状/马赛克一致），_pm 为像素内容。
    行为与表情元素一致：支持 8 点缩放、旋转、拖动，且可跨多图层。
    QPixmap 不参与 deepcopy（隐式共享），序列化走 base64 PNG。
    """

    def __init__(self, p1, p2, pixmap, text_color="#000000", font_size=18):
        super().__init__("", font_size, text_color)
        self.p1 = QPointF(*p1)
        self.p2 = QPointF(*p2)
        self._pm = pixmap

    def pixmap(self):
        return self._pm

    def set_pixmap(self, pm) -> None:
        self._pm = pm

    def __deepcopy__(self, memo):
        import copy as _copy
        new = ImageItem.__new__(ImageItem)
        memo[id(self)] = new
        for k, v in self.__dict__.items():
            # QPixmap 隐式共享，撤销快照直接复用引用即可
            new.__dict__[k] = v if k == "_pm" else _copy.deepcopy(v, memo)
        return new

    def rect(self) -> QRectF:
        return QRectF(self.p1, self.p2).normalized()

    def text_rect(self) -> QRectF:
        return self.rect()

    def paint(self, painter: QPainter, export: bool = False) -> None:
        self._with_rotation(painter, self._paint_impl, export)

    def _paint_impl(self, painter: QPainter, export: bool) -> None:
        r = self.rect()
        painter.save()
        if self._pm is not None and not getattr(self._pm, "isNull", lambda: True)():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(r, self._pm.toImage())
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(150, 150, 150, 90))
            painter.drawRect(r)
        painter.restore()
        if self.selected and not export:
            self.paint_selection(painter, r)

    def hit_test(self, pos: QPointF, tol: float):
        pos = self._unrotated_hit(pos)
        rr = self.rect().adjusted(-tol, -tol, tol, tol)
        return "body" if rr.contains(pos) else None

    def move_by(self, dx: float, dy: float, part: str) -> None:
        self.p1 += QPointF(dx, dy)
        self.p2 += QPointF(dx, dy)

    def unrotated_bounds(self) -> QRectF:
        return self.rect().adjusted(-2, -2, 2, 2)


def allocate_item_id() -> int:
    """为克隆元素分配新的唯一 id。

    copy.deepcopy 会原样复制 id，直接使用会导致画布/树中出现同 id 元素，
    破坏唯一显示与去重逻辑，因此克隆后必须重新分配。
    """
    AnnotationItem._id_counter += 1
    return AnnotationItem._id_counter
