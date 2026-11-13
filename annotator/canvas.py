# -*- coding: utf-8 -*-
"""标注画布：显示图片、管理标注元素、处理鼠标交互、撤销/重做、导出渲染。

坐标体系：
- 图片坐标：原点在图片左上角，单位像素（与导出一致）。
- 视图坐标：控件内坐标。view = image * scale + offset。
"""

import copy
import time

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

from .flatten import BelowFlattener
from .items import (ABOVE_DIR_AUTO, ABOVE_DIR_LEFT, ABOVE_DIR_RIGHT, CALLOUT_SHAPES,
                    Layer, PenItem,
                    ShapeItem, STYLE_ABOVE, TEXT_PAD_X, TEXT_PAD_Y,
                    LeaderLineItem, TextItem, HighlightItem, MosaicItem,
                    EmojiItem, ImageItem, allocate_item_id, draw_arrow_head,
                    make_font, shape_path)

MODE_SELECT = "select"   # 选择/编辑模式

# 右键长按阈值（毫秒）：超过该时长未释放且执行拖动 → 平移画布，不再弹右键菜单
RBTN_LONG_MS = 450

# 右键长按阈值（毫秒）：超过该时长未释放且执行拖动 → 平移画布，不再弹右键菜单
RBTN_LONG_MS = 450
MODE_LEADER = "leader"   # 引线标注模式（默认）：手动输入文字
MODE_NUMBER = "number"   # 引线序号模式：自动编号，无需输入文字
MODE_TEXT = "text"       # 文本批注模式
MODE_SHAPE = "shape"     # 形状绘制模式
MODE_PEN = "pen"         # 画笔模式
MODE_HIGHLIGHT = "highlight"  # 荧光笔模式
MODE_MOSAIC = "mosaic"      # 马赛克模式
MODE_EMOJI = "emoji"        # 表情模式

# v2.x 需求2：标注类指令模式（工具面板中除「选择」「自由截图」外的模式）。
# 「重复上次标注」只恢复这些最近使用的标注指令，不重复删除/复制等其它命令。
ANNOTATION_MODES = (MODE_LEADER, MODE_NUMBER, MODE_TEXT, MODE_SHAPE,
                    MODE_PEN, MODE_HIGHLIGHT, MODE_MOSAIC, MODE_EMOJI)

MAX_UNDO = 100
PREVIEW_COLOR = QColor(0, 120, 215)


class _InlineEditor(QLineEdit):
    """画布内就地文字输入框：回车 / 失焦确认，Esc 取消。"""

    confirmed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._done = False
        self._by_focus_out = False   # 确认方式：True=失焦触发（后续紧跟同一次鼠标点击）
        self.returnPressed.connect(self._emit_confirmed)

    def _emit_confirmed(self):
        if self._done:
            return
        self._done = True
        self._by_focus_out = False
        self.confirmed.emit(self.text())

    def reset_done(self):
        self._done = False
        self._by_focus_out = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if not self._done:
                self._done = True
                self.cancelled.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if not self._done:
            self._done = True
            self._by_focus_out = True
            self.confirmed.emit(self.text())
        super().focusOutEvent(event)


class AnnotationCanvas(QWidget):
    imageLoaded = pyqtSignal()
    itemSelectionChanged = pyqtSignal()
    itemsChanged = pyqtSignal()
    cursorMoved = pyqtSignal(float, float)   # 鼠标所在图片坐标
    modeChanged = pyqtSignal(str)            # 当前模式变化（供工具栏同步高亮）
    viewChanged = pyqtSignal()               # 缩放/平移变化（供标尺刷新）
    layersChanged = pyqtSignal()             # 图层增删/显隐/顺序变化（供图层面板刷新）
    commandRequested = pyqtSignal(str)       # 右键菜单等请求主窗口动作（copy_annotated/clear_canvas/screenshot）
    statusMessage = pyqtSignal(str)          # 状态栏提示（右键菜单/重复命令反馈）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)

        self._bg_color = QColor("#F0F2F5")   # 默认浅色画布背景
        self.setStyleSheet(f"background-color: {self._bg_color.name()};")

        self.pixmap: QPixmap | None = None
        self.items: list = []
        self.mode = MODE_LEADER
        self.style_provider = None   # callable() -> dict，创建新元素时取样式

        # 引线序号（CAD 风格）：开关 + 格式；开启后所有引线标注按顺序自动编号
        self.number_enabled = False
        self.number_format = "circle"   # 'circle' ① / 'paren' （1） / 'plain' 1

        self.snap_mode = "none"   # 文字对齐磁吸模式：'none'/'left'/'right'/'hcenter'/'top'/'vcenter'/'center'

        # 图层（类似 Photoshop）：列表顺序 = 绘制顺序（底层在前）
        self.layers: list = [Layer("图层1")]
        self.current_layer = self.layers[0].id
        self._picking_color = False   # 吸管模式：点击图片取色作为画布背景
        self.highlight_layer_id = None  # 仅「选中图层」或「右键选中本层全部元素」时高亮
        self._last_command = None     # 「重复上一次命令」：(name, data)
        self._last_annotation_mode = None  # 「重复上次标注」：最近使用的标注指令模式
        self._rbtn = None             # 右键按下状态（需求3/6）
        self._shape_edit = None      # v1.7 需求2：形状手柄编辑状态（缩放/旋转）
        self._layer_drag = None      # v1.7 需求1：虚线框拖动整层元素状态
        self._op_pre_snap = None     # v1.7：形状编辑/层拖动开始前的快照
        self._last_cmd_data = None
        self._dark_theme = False     # v1.7 需求8：右键菜单等弹层直接套主题 QSS

        self.scale = 1.0
        self.offset = QPointF(0.0, 0.0)

        self._pending_target: QPointF | None = None   # 引线模式：第一次点击的目标点
        self._hover_pos: QPointF | None = None        # 引线模式：文字预览位置
        self._input_preview: tuple | None = None      # (target, text_pos) 输入文字期间的引线预览
        self._drag = None                             # 拖动标注状态
        self._drag_snap_state = {}                    # 拖动磁吸滞回状态
        self.transparent_bg = False                   # 导出时透明背景
        self._shape_drag: tuple | None = None         # 拖拽式形状：(起点, 当前点)
        self._line_points: list | None = None         # 点击式连续折线：已确认顶点
        self._line_cursor: QPointF | None = None      # 折线跟随鼠标的未确认端点（已正交吸附）
        self._line_snap_axis = None                   # 折线当前段吸附轴 "h"/"v"/None
        self._pen_points: list = []                   # 画笔模式：轨迹点
        self._pen_drawing = False                     # 画笔是否正在绘制
        self._hl_points: list = []                    # 荧光笔：轨迹点
        self._hl_drawing = False                      # 荧光笔是否正在绘制
        self._mosaic_drag: tuple | None = None        # 马赛克：(起点,当前点)
        self._panning = False
        self._last_pan = QPointF()
        self._suppress_click = False   # 失焦确认后，抑制同一次鼠标点击被误当作新操作
        self._await_prompt = False     # 完成输入后显示「等待下一次点击」提示
        # 单击翻转横线方向：延迟到双击判定窗口之后执行，避免与双击编辑冲突
        self._line_toggle_item = None
        self._line_toggle_timer = QTimer(self)
        self._line_toggle_timer.setSingleShot(True)
        self._line_toggle_timer.timeout.connect(self._do_toggle_line_dir)

        self.undo_stack: list = []                    # [(items_snapshot, tag, ts)]
        self.redo_stack: list = []

        # ---- 就地文字输入框 ----
        self._editor = _InlineEditor(self)
        self._editor.setStyleSheet(
            "QLineEdit { background-color: white; color: black;"
            " border: 1px solid #0078d7; border-radius: 3px; padding: 2px; }")
        self._editor.hide()
        self._editor.confirmed.connect(self._on_editor_confirmed)
        self._editor.cancelled.connect(self._on_editor_cancelled)
        self._editor_pos: QPointF | None = None        # 输入框锚点（图片坐标）
        self._editor_callback = None                   # 确认后回调(content)
        self._editor_fm: QFontMetrics | None = None
        self._editor_above_center: QPointF | None = None   # above 风格：文字中心（图片坐标）
        self._editor_above_fm: QFontMetrics | None = None

    # ================= 图片加载 =================
    def load_pixmap(self, pixmap: QPixmap, fit: bool = True) -> None:
        # 画布不变量：载入图片的 devicePixelRatio 必须为 1。
        # drawPixmap(0,0) 按 width/DPR 绘制，而外框/坐标按 width/height 计算，
        # 若图片带非 1 DPR（高 DPI 截图等入口可能遗留），图片只占外框左上角、
        # 外框边线比实际图片大一圈。这里只把 DPR 归 1、保留全部原生像素不重采样，
        # 既守住不变量，又避免缩小导致的清晰度损失。
        if not pixmap.isNull() and pixmap.devicePixelRatio() != 1.0:
            pixmap.setDevicePixelRatio(1.0)
        self.pixmap = pixmap
        self.items = []
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._pending_target = None
        self._hover_pos = None
        self._await_prompt = False
        self._line_points = None
        self._line_cursor = None
        self._line_snap_axis = None
        self._shape_edit = None
        self._layer_drag = None
        self._op_pre_snap = None
        self._hide_editor()
        if fit:
            self.fit_to_view()
        else:
            # 截图等入口：按原始分辨率 100% 显示，不自动放大铺满视口
            self.actual_size()
        self.highlight_layer_id = None   # v1.6：仅选中图层/右键选中本层元素时高亮
        self.update()
        self.imageLoaded.emit()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    def has_image(self) -> bool:
        return self.pixmap is not None

    def set_bg_color(self, color) -> None:
        # color=None 表示「无背景」（需求6）：不填画布底色，露出控件主题底色
        if color is None:
            self._bg_color = None
            self.setStyleSheet("")
            self.update()
            return
        self._bg_color = QColor(color)
        self.setStyleSheet(f"background-color: {self._bg_color.name()};")
        self.update()

    def fit_to_view(self) -> None:
        if self.pixmap is None:
            return
        vw, vh = max(1, self.width()), max(1, self.height())
        iw, ih = self.pixmap.width(), self.pixmap.height()
        self.scale = min(vw / iw, vh / ih, 2.0)
        self.offset = QPointF((vw - iw * self.scale) / 2.0, (vh - ih * self.scale) / 2.0)

    def actual_size(self) -> None:
        """按原始分辨率 100% 显示（scale=1），图片在视口中居中。"""
        if self.pixmap is None:
            return
        vw, vh = max(1, self.width()), max(1, self.height())
        iw, ih = self.pixmap.width(), self.pixmap.height()
        self.scale = 1.0
        self.offset = QPointF((vw - iw) / 2.0, (vh - ih) / 2.0)
        self.update()
        self.viewChanged.emit()

    def center_image(self) -> None:
        """在当前缩放比例下将图片居中显示。"""
        if self.pixmap is None:
            return
        vw, vh = max(1, self.width()), max(1, self.height())
        iw, ih = self.pixmap.width(), self.pixmap.height()
        self.offset = QPointF((vw - iw * self.scale) / 2.0,
                              (vh - ih * self.scale) / 2.0)
        self.update()
        self.viewChanged.emit()

    # ================= 坐标变换 =================
    def view_to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self.offset.x()) / self.scale,
                       (p.y() - self.offset.y()) / self.scale)

    def image_to_view(self, p: QPointF) -> QPointF:
        return QPointF(p.x() * self.scale + self.offset.x(),
                       p.y() * self.scale + self.offset.y())

    # -------- 点击式连续折线 --------
    def _line_ortho_snap(self, p1: QPointF, p2: QPointF):
        """当前端点与上一顶点水平/竖直差在 5 屏幕像素内时强制正交对齐。

        返回 (吸附后端点, 轴)，轴 "h"=水平(y 对齐)/"v"=竖直(x 对齐)/None。
        容差换算到图片坐标（5/scale），任意缩放下屏幕上都是 ±5px。
        """
        tol = 5.0 / self.scale
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        if abs(dy) <= tol and abs(dx) >= abs(dy):
            return QPointF(p2.x(), p1.y()), "h"
        if abs(dx) <= tol:
            return QPointF(p1.x(), p2.y()), "v"
        return QPointF(p2), None

    def _finish_line_path(self) -> None:
        """结束连续折线：丢弃未确认的跟随段，已确认顶点生成一个折线元素。

        v1.6 需求5：结束（双击/Esc/回车/中键/右键切换）时若跟随端点吸附到
        初始起点附近，则自动追加起点形成封闭图形。
        """
        pts = self._line_points
        cursor = self._line_cursor   # 先取跟随端点，供闭合判断使用
        self._line_points = None
        self._line_cursor = None
        self._line_snap_axis = None
        if pts and len(pts) >= 2:
            start = pts[0]
            if cursor is not None and (not pts or pts[-1] != start):
                cur = cursor
                _tol = 10.0 / self.scale
                if abs(cur.x() - start.x()) <= _tol and abs(cur.y() - start.y()) <= _tol:
                    pts = list(pts) + [QPointF(start)]
            item = self.add_shape_item(pts[0], pts[-1], "line")
            item.points = [QPointF(p) for p in pts]
            self.push_undo("add")
            item.selected = True
            self.itemSelectionChanged.emit()
        self.update()

    def _paint_line_path_preview(self, painter: QPainter) -> None:
        """连续折线预览：已确认折线 + 跟随段 + 顶点锚点 + 正交磁吸引导。"""
        pts = [QPointF(p) for p in self._line_points]
        if self._line_cursor is not None:
            pts.append(QPointF(self._line_cursor))
        if len(pts) >= 2:
            painter.drawPolyline(QPolygonF(pts))
        hs = 3.0 / self.scale
        for v in self._line_points:
            painter.save()
            painter.setPen(QPen(PREVIEW_COLOR, 1.0 / self.scale))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRect(QRectF(v.x() - hs, v.y() - hs, hs * 2, hs * 2))
            painter.restore()
        if self._line_snap_axis and self._line_cursor is not None and self._line_points:
            a = self._line_points[-1]
            b = self._line_cursor
            ext = 14.0 / self.scale
            painter.save()
            if self._line_snap_axis == "close":
                # v1.6 需求5：终点吸附起点 → 橙色闭合引导 + 高亮起点
                painter.setPen(QPen(QColor("#FF7A00"), 2.0 / self.scale, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(b), QPointF(a))
                hs = 6.0 / self.scale
                painter.setBrush(QColor(255, 122, 0, 90))
                painter.drawEllipse(QPointF(self._line_points[0]), hs, hs)
                painter.restore()
                return
            painter.setPen(QPen(PREVIEW_COLOR, 1.5 / self.scale, Qt.PenStyle.DashLine))
            if self._line_snap_axis == "h":
                y = a.y()
                painter.drawLine(QPointF(min(a.x(), b.x()) - ext, y),
                                 QPointF(max(a.x(), b.x()) + ext, y))
            else:
                x = a.x()
                painter.drawLine(QPointF(x, min(a.y(), b.y()) - ext),
                                 QPointF(x, max(a.y(), b.y()) + ext))
            painter.restore()

    # ================= 标注管理 =================
    def select_item_by_id(self, item_id: int) -> None:
        changed = False
        for it in self.items:
            want = (it.id == item_id)
            if it.selected != want:
                it.selected = want
                changed = True
        if changed:
            self.itemSelectionChanged.emit()
            self.update()

    def delete_item(self, item) -> None:
        if item in self.items:
            self.push_undo("delete")
            self.items.remove(item)
            self.renumber()   # 删除后序号自动补缺
            self._last_command = ("delete", None)   # 供「重复上一次命令」
            self.update()
            self.itemSelectionChanged.emit()
            self.itemsChanged.emit()
    def set_style_provider(self, provider) -> None:
        self.style_provider = provider

    def _new_style(self) -> dict:
        if self.style_provider is not None:
            return dict(self.style_provider())
        return {}

    @staticmethod
    def _to_qpoint(p) -> QPointF:
        if isinstance(p, QPointF):
            return QPointF(p)
        return QPointF(float(p[0]), float(p[1]))

    def apply_style_to_all(self, st: dict) -> None:
        """把一套面板样式应用到全部同类标注元素（引线/文字/形状/画笔）。"""
        if not st or self.pixmap is None:
            return
        changed = False
        for it in self.items:
            if isinstance(it, (LeaderLineItem, TextItem)):
                if isinstance(it, LeaderLineItem):
                    it.line_color = QColor(st.get("line_color", "#FF0000"))
                    it.line_width = int(st.get("line_width", 2))
                    it.arrow_size = float(st.get("arrow_size", 14))
                    if st.get("above_dir") == ABOVE_DIR_AUTO:
                        self._resolve_above_dir(it)
                    else:
                        it.above_dir = st.get("above_dir", ABOVE_DIR_AUTO)
                it.apply_style(st)
                changed = True
            elif isinstance(it, ShapeItem):
                it.shape = st.get("shape_type", "rect")
                it.border_color = QColor(st.get("shape_border_color", "#FF0000"))
                it.fill_color = QColor(st.get("shape_fill_color", "#00000000"))
                it.line_width = int(st.get("shape_line_width", 2))
                changed = True
            elif isinstance(it, PenItem):
                it.pen_color = QColor(st.get("pen_color", "#000000"))
                it.pen_width = int(st.get("pen_width", 3))
                changed = True
            elif isinstance(it, HighlightItem):
                it.hl_color = QColor(st.get("hl_color", "#FFE600"))
                it.hl_width = int(st.get("hl_width", 22))
                it.hl_alpha = int(st.get("hl_alpha", 80))
                changed = True
            elif isinstance(it, MosaicItem):
                it.block_size = max(2, int(st.get("mosaic_block", 10)))
                it.show_border = bool(st.get("mosaic_border", True))
                changed = True
            elif isinstance(it, EmojiItem):
                it.font_size = max(8, int(st.get("emoji_size", 40)))
                changed = True
        if changed:
            self.push_undo("style_all")
            self.update()
            self.itemsChanged.emit()

    def add_leader_item(self, target_pos, text_pos, content: str) -> LeaderLineItem:
        st = self._new_style()
        target = self._to_qpoint(target_pos)
        text = self._to_qpoint(text_pos)
        item = LeaderLineItem(
            (target.x(), target.y()), (text.x(), text.y()), content,
            line_color=st.get("line_color", "#FF0000"),
            line_width=st.get("line_width", 2),
            arrow_size=st.get("arrow_size", 14),
            font_size=st.get("font_size", 18),
            text_color=st.get("text_color", "#000000"))
        item.apply_style(st)
        # above 风格：横线方向按文字所在图片左右半区自动判定
        if st.get("label_style") == STYLE_ABOVE:
            self._resolve_above_dir(item)
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def rename_layer(self, layer_id: int, new_name: str) -> None:
        """重命名图层。"""
        for layer in self.layers:
            if layer.id == layer_id:
                layer.name = new_name
                self.layersChanged.emit()
                return

    def select_layer_items(self, layer_id: int) -> None:
        """选中指定图层的所有元素（醒目显示）。"""
        self.highlight_layer_id = layer_id
        for item in self.items:
            item.selected = (item.layer_id == layer_id)
        self.itemSelectionChanged.emit()
        self.update()

    def apply_layer_order(self, ids: list) -> None:
        """按给定 id 顺序（自底向上）重排图层（图层面板拖拽结果）。"""
        if not ids:
            return
        by_id = {l.id: l for l in self.layers}
        ordered = [by_id[i] for i in ids if i in by_id]
        if len(ordered) != len(self.layers):
            return
        self.layers = ordered
        self.layersChanged.emit()
        self.update()

    def _resolve_above_dir(self, item: LeaderLineItem) -> None:
        """above 风格横线方向：按文字所在图片左右半区自动判定。"""
        mid = self.pixmap.width() / 2.0 if self.pixmap is not None else 0.0
        item.above_dir = (ABOVE_DIR_RIGHT if item.text_point.x() > mid
                          else ABOVE_DIR_LEFT)

    def add_text_item(self, pos, content: str) -> TextItem:
        st = self._new_style()
        p = self._to_qpoint(pos)
        item = TextItem((p.x(), p.y()), content,
                        font_size=st.get("font_size", 18),
                        text_color=st.get("text_color", "#000000"))
        item.apply_style(st)
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def add_shape_item(self, p1, p2, shape: str) -> ShapeItem:
        st = self._new_style()
        a = self._to_qpoint(p1)
        b = self._to_qpoint(p2)
        item = ShapeItem((a.x(), a.y()), (b.x(), b.y()), shape=shape,
                         border_color=st.get("shape_border_color", "#FF0000"),
                         fill_color=st.get("shape_fill_color", "#FFFFFF00"),
                         line_width=st.get("shape_line_width", 2))
        item.layer_id = self.current_layer
        item.text_pos = st.get("shape_text_pos", "center")
        # v2.0：新形状沿用面板当前字体/颜色设置，便于直接输入文字
        item.font_size = int(st.get("font_size", item.font_size))
        item.text_color = QColor(st.get("text_color", "#000000"))
        item.font_family = st.get("font_family", item.font_family)
        item.font_weight = int(st.get("font_weight", item.font_weight))
        item.font_italic = bool(st.get("font_italic", item.font_italic))
        self.items.append(item)
        return item

    def add_emoji_item(self, pos, emoji: str, size: int) -> EmojiItem:
        p = self._to_qpoint(pos)
        item = EmojiItem((p.x(), p.y()), emoji=emoji, font_size=size)
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def add_image_element(self, pixmap, pos=None):
        """v2.x 需求3：把外部图片作为一个新图层元素插入（可缩放/旋转/移动）。

        自动新建一个图层，图片按等比缩放后置于画布中心（或 pos 处），
        并选中该新元素。pixmap 为 QPixmap。
        """
        from .items import ImageItem
        if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
            return None
        layer = self.add_layer("图片")
        if self.pixmap is not None and not self.pixmap.isNull():
            cw, ch = self.pixmap.width(), self.pixmap.height()
        else:
            cw, ch = 1000, 1000
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(1.0, (min(cw, ch) * 0.6) / float(max(pw, ph)))
        dw, dh = pw * scale, ph * scale
        cx = pos.x() if pos is not None else cw / 2.0
        cy = pos.y() if pos is not None else ch / 2.0
        item = ImageItem((cx - dw / 2.0, cy - dh / 2.0),
                         (cx + dw / 2.0, cy + dh / 2.0), pixmap)
        item.layer_id = layer.id
        self.items.append(item)
        self.select_item_by_id(item.id)
        self.itemsChanged.emit()
        self.update()
        return item

    def add_mosaic_item(self, p1, p2, block_size: int = 10,
                        show_border: bool = True) -> MosaicItem:
        a = self._to_qpoint(p1)
        b = self._to_qpoint(p2)
        item = MosaicItem((a.x(), a.y()), (b.x(), b.y()),
                          block_size=block_size, show_border=show_border)
        item.set_source(self.pixmap)   # 注入当前原图
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def add_highlight_item(self, points) -> HighlightItem:
        st = self._new_style()
        item = HighlightItem([(p.x(), p.y()) for p in points],
                             hl_color=st.get("hl_color", "#FFE600"),
                             hl_width=st.get("hl_width", 22),
                             hl_alpha=st.get("hl_alpha", 80))
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def add_pen_item(self, points) -> PenItem:
        st = self._new_style()
        item = PenItem([(p.x(), p.y()) for p in points],
                       pen_color=st.get("pen_color", "#000000"),
                       pen_width=st.get("pen_width", 3))
        item.layer_id = self.current_layer
        self.items.append(item)
        return item

    def selected_items(self) -> list:
        return [it for it in self.items if it.selected]

    def delete_selected(self) -> None:
        sel = self.selected_items()
        if not sel:
            return
        self.push_undo("delete")
        for it in sel:
            self.items.remove(it)
        self.renumber()   # 删除后序号自动补缺
        self._last_command = ("delete", None)   # 供「重复上一次命令」
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    def clear_all(self) -> None:
        if not self.items:
            return
        self.push_undo("clear")
        self._shape_edit = None
        self._layer_drag = None
        self._op_pre_snap = None
        self.items = []
        self.renumber()
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    # ================= 撤销 / 重做 =================
    def _snapshot(self):
        snap = copy.deepcopy(self.items)
        for it in snap:
            it.selected = False   # 选中是 UI 状态，不进入撤销历史
        return snap

    def commit_op(self, tag: str = None) -> None:
        """提交一次操作（拖动/缩放/旋转等）：把操作【开始前】的快照压入撤销栈。

        v1.7：现有 push_undo 在操作结束后调用会快照到“操作后”状态，
        撤销变成无操作。交互型操作（整层拖动、形状缩放/旋转）在按下时
        先 _snapshot() 存开始前状态，结束时用本方法提交，撤销才能正确还原。
        """
        if self._op_pre_snap is not None:
            self.undo_stack.append((self._op_pre_snap, tag, time.time()))
            if len(self.undo_stack) > MAX_UNDO:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self._op_pre_snap = None
            self.itemsChanged.emit()

    def push_undo(self, tag: str = None) -> None:
        snap = self._snapshot()
        now = time.time()
        if (tag is not None and self.undo_stack
                and self.undo_stack[-1][1] == tag
                and now - self.undo_stack[-1][2] < 2.0):
            # 连续同类操作（如拖动滑条调样式）合并为一步
            self.undo_stack[-1] = (snap, tag, now)
        else:
            self.undo_stack.append((snap, tag, now))
            if len(self.undo_stack) > MAX_UNDO:
                self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.itemsChanged.emit()

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self._hide_editor()
        self.redo_stack.append((self._snapshot(), None, time.time()))
        self.items = self.undo_stack.pop()[0]
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self._hide_editor()
        self.undo_stack.append((self._snapshot(), None, time.time()))
        self.items = self.redo_stack.pop()[0]
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    # ================= 模式切换 =================
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        # v2.x 需求2：记录最近使用的标注指令（工具面板中的标注模式）
        if mode in ANNOTATION_MODES:
            self._last_annotation_mode = mode
        self._pending_target = None
        self._hover_pos = None
        self._shape_drag = None
        self._line_points = None
        self._line_cursor = None
        self._line_snap_axis = None
        self._pen_drawing = False
        self._pen_points = []
        self._hl_drawing = False
        self._hl_points = []
        self._mosaic_drag = None
        self._hide_editor()
        self._await_prompt = False
        if mode == MODE_NUMBER and not self.number_enabled:
            # 进入「引线序号」模式即自动开启序号（已有标注立即补号）
            self.number_enabled = True
            self.renumber()
        self.setCursor(Qt.CursorShape.CrossCursor if mode not in (MODE_SELECT, MODE_PEN, MODE_HIGHLIGHT)
                       else Qt.CursorShape.ArrowCursor)
        if mode != MODE_SELECT:
            # v1.6 需求4：进入正常标注模式自动隐藏当前层虚线框
            self.highlight_layer_id = None
        self.update()
        self.modeChanged.emit(mode)

    def _cancel_pending(self) -> None:
        """取消当前绘制/选择流程（Esc 与鼠标中键共用）。"""
        self._pending_target = None
        self._hover_pos = None
        self._shape_drag = None
        self._line_points = None
        self._line_cursor = None
        self._line_snap_axis = None
        self._pen_drawing = False
        self._pen_points = []
        # 取消当前绘制后自动回到「选择」模式
        self.set_mode(MODE_SELECT)
        self.update()

    # ================= 引线序号 =================
    def renumber(self) -> None:
        """按 items 顺序为所有引线标注自动连续编号（1..N）。

        序号功能开启时全部引线标注编号；关闭时全部清空。
        """
        n = 1
        for it in self.items:
            if isinstance(it, LeaderLineItem):
                if self.number_enabled:
                    it.number = n
                    it.number_fmt = self.number_format
                    n += 1
                else:
                    it.number = None

    def set_number_enabled(self, enabled: bool) -> None:
        if self.number_enabled == enabled:
            return
        self.push_undo("number")
        self.number_enabled = enabled
        self.renumber()
        self.update()
        self.itemsChanged.emit()

    def set_number_format(self, fmt: str) -> None:
        if self.number_format == fmt:
            return
        self.number_format = fmt
        if self.number_enabled:
            self.push_undo("number_fmt")
            self.renumber()
            self.update()
            self.itemsChanged.emit()

    def reorder_by_number(self, item_id: int, new_number: int) -> None:
        """按序号调整顺序：把指定标注移到对应序号位置后重新连续编号。"""
        item = next((it for it in self.items
                     if isinstance(it, LeaderLineItem) and it.id == item_id), None)
        if item is None:
            return
        leaders = [it for it in self.items if isinstance(it, LeaderLineItem)]
        if not leaders:
            return
        new_number = max(1, min(new_number, len(leaders)))
        leaders.remove(item)
        leaders.insert(new_number - 1, item)
        new_items = []
        li = iter(leaders)
        for it in self.items:
            if isinstance(it, LeaderLineItem):
                new_items.append(next(li))
            else:
                new_items.append(it)
        self.items = new_items
        self.renumber()
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    def move_item(self, item_id: int, delta: int) -> None:
        """在顺序列表中上移/下移标注（delta = ±1），随后重新编号。"""
        idx = next((i for i, it in enumerate(self.items) if it.id == item_id), None)
        if idx is None:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.items):
            return
        self.items[idx], self.items[new_idx] = self.items[new_idx], self.items[idx]
        self.renumber()
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()

    def move_item_to_layer(self, item_id: int, target_layer_id: int) -> None:
        """将指定元素移动到目标图层。"""
        it = next((x for x in self.items if x.id == item_id), None)
        if it is None:
            return
        if it.layer_id == target_layer_id:
            return
        if self.layer_by_id(target_layer_id) is None:
            return
        it.layer_id = target_layer_id
        self.update()
        self.itemsChanged.emit()

    # ================= 图层 =================
    def layer_by_id(self, layer_id: int) -> Layer | None:
        return next((l for l in self.layers if l.id == layer_id), None)

    def add_layer(self, name: str = "图层") -> Layer:
        n = len(self.layers) + 1
        layer = Layer(f"{name}{n}")
        self.layers.append(layer)
        self.current_layer = layer.id
        self.highlight_layer_id = None   # v1.6：新增图层不高亮，选中后才显示
        self.layersChanged.emit()
        self.update()
        return layer

    def delete_layer(self, layer_id: int) -> None:
        layer = self.layer_by_id(layer_id)
        if layer is None or len(self.layers) <= 1:
            return
        self.push_undo("layer")
        self.items = [it for it in self.items if it.layer_id != layer_id]
        self.layers.remove(layer)
        if self.current_layer == layer_id:
            self.current_layer = self.layers[-1].id
        self.highlight_layer_id = None   # v1.6：删除图层后清除虚线框
        self.layersChanged.emit()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()
        self.update()

    def set_layer_visible(self, layer_id: int, visible: bool) -> None:
        layer = self.layer_by_id(layer_id)
        if layer is None or layer.visible == visible:
            return
        layer.visible = visible
        self.layersChanged.emit()
        self.update()

    def move_layer(self, layer_id: int, delta: int) -> None:
        """调整图层顺序（delta = ±1，正数向上）。"""
        idx = next((i for i, l in enumerate(self.layers) if l.id == layer_id), None)
        if idx is None:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.layers):
            return
        self.layers[idx], self.layers[new_idx] = self.layers[new_idx], self.layers[idx]
        self.layersChanged.emit()
        self.update()

    def select_layer(self, layer_id: int) -> None:
        if self.layer_by_id(layer_id) is not None:
            self.current_layer = layer_id
            self.highlight_layer_id = layer_id
            self.layersChanged.emit()
            self.update()

    def items_on_layer(self, layer_id: int) -> list:
        return [it for it in self.items if it.layer_id == layer_id]

    def copy_layer(self, layer_id: int) -> Layer | None:
        """复制图层（v2.x 需求3，左侧结构树空白右键「复制层」）。

        整层复制（含全部元素），副本插入原图层正上方并设为当前层。
        副本元素深拷贝并重新分配 id（否则画布/树出现同 id 元素，
        破坏唯一显示与去重逻辑），位置与原层完全一致。
        """
        src = self.layer_by_id(layer_id)
        if src is None:
            return None
        self.push_undo("copy layer")
        # 生成不重名的副本名：原层名 + 「 副本」（重名自动加序号）
        base = src.name
        existing = {l.name for l in self.layers}
        name = f"{base} 副本"
        k = 2
        while name in existing:
            name = f"{base} 副本{k}"
            k += 1
        layer = Layer(name)
        idx = self.layers.index(src)
        self.layers.insert(idx + 1, layer)   # 原图层正上方（列表自底向上）
        # 复制该层全部元素（深拷贝 + 重新分配 id；马赛克/图片等 QPixmap
        # 元素靠各自 __deepcopy__ 把 _source 置 None，绘制时惰性注入）
        for it in self.items:
            if getattr(it, "layer_id", None) != layer_id:
                continue
            try:
                new_it = copy.deepcopy(it)
            except Exception:
                continue
            new_it.id = allocate_item_id()
            new_it.layer_id = layer.id
            new_it.selected = False
            self.items.append(new_it)
        self.current_layer = layer.id
        self.highlight_layer_id = layer.id
        self.layersChanged.emit()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()
        self.update()
        return layer

    def begin_pick_color(self) -> None:
        """进入吸管模式：点击图片后取该像素颜色作为画布背景色。"""
        self._picking_color = True
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _pick_color_at(self, img_pos: QPointF) -> bool:
        if self.pixmap is None:
            return False
        x = int(img_pos.x())
        y = int(img_pos.y())
        if not (0 <= x < self.pixmap.width() and 0 <= y < self.pixmap.height()):
            return False
        color = self.pixmap.toImage().pixelColor(x, y)
        self.set_bg_color(color)
        return True

    # ================= 引线磁吸对齐（多参考线：同侧第一个 + 对侧标注） =================
    def _get_side(self, item: LeaderLineItem) -> str:
        """判断标注在图片的哪一侧：'left'/'right'/'top'/'bottom'。
        根据文字框中心和图片中心的相对位置判断。"""
        if self.pixmap is None:
            return "right"
        img_cx = self.pixmap.width() / 2
        img_cy = self.pixmap.height() / 2
        rect = item.text_rect()
        cx = rect.center().x()
        cy = rect.center().y()
        # 判断上下左右，哪个方向偏移最大就是哪一侧
        dx = cx - img_cx
        dy = cy - img_cy
        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        else:
            return "bottom" if dy > 0 else "top"

    def _get_ref_lines(self, item: LeaderLineItem) -> tuple:
        """获取当前标注应该参考的对齐线。
        返回 (v_lines, h_lines)：
        - v_lines: [(x, align_type), ...]  align_type: 'left'/'center'/'right'
        - h_lines: [(y, align_type), ...]  align_type: 'top'/'center'/'bottom'
        逻辑：
        1. 同侧第一个标注的所有边作为参考线（同侧对齐）
        2. 对侧所有标注的所有边也作为参考线（左-右、上-下相互对齐）
        """
        if self.pixmap is None:
            return [], []
        side = self._get_side(item)
        leaders = [it for it in self.items if isinstance(it, LeaderLineItem) and it is not item]
        if not leaders:
            return [], []

        v_lines = []  # (x, align_type)
        h_lines = []  # (y, align_type)

        # 1. 同侧第一个标注的参考线
        same_side_first = None
        for it in leaders:
            if self._get_side(it) == side:
                same_side_first = it
                break
        if same_side_first is not None:
            r = same_side_first.text_rect()
            v_lines.append((r.left(), "left"))
            v_lines.append((r.center().x(), "center"))
            v_lines.append((r.right(), "right"))
            h_lines.append((r.top(), "top"))
            h_lines.append((r.center().y(), "center"))
            h_lines.append((r.bottom(), "bottom"))

        # 2. 对侧所有标注的参考线（左-右、上-下相互对齐）
        opposite_side = {"left": "right", "right": "left",
                         "top": "bottom", "bottom": "top"}.get(side, "right")
        for it in leaders:
            if self._get_side(it) == opposite_side:
                r = it.text_rect()
                v_lines.append((r.left(), "left"))
                v_lines.append((r.center().x(), "center"))
                v_lines.append((r.right(), "right"))
                h_lines.append((r.top(), "top"))
                h_lines.append((r.center().y(), "center"))
                h_lines.append((r.bottom(), "bottom"))

        # 如果当前 item 就是第一个标注（同侧没有其他标注），
        # 那它自己就是基准，参考线为空是正常的
        # 但如果对侧有标注，还是要显示对侧的线

        return v_lines, h_lines

    def _snap_hover_to_base(self, pos):
        """把文字放置位置吸附到参考线。
        返回 (吸附后位置, 吸附线名或 None)。阈值 12px（缩放归一）。"""
        # 用一个临时 item 来判断应该参考哪些线
        # 新建时还没有 item，暂时参考所有已有引线
        leaders = [it for it in self.items if isinstance(it, LeaderLineItem)]
        if not leaders:
            return QPointF(pos), None
        thr = 12.0 / self.scale if self.scale > 0 else 12.0

        # 收集所有参考线
        v_lines = []
        h_lines = []
        for it in leaders:
            r = it.text_rect()
            v_lines.extend([r.left(), r.center().x(), r.right()])
            h_lines.extend([r.top(), r.center().y(), r.bottom()])

        # X 轴吸附
        best_x = None
        best_x_diff = thr
        for ref in v_lines:
            d = abs(pos.x() - ref)
            if d < best_x_diff:
                best_x = ref
                best_x_diff = d
        # Y 轴吸附
        best_y = None
        best_y_diff = thr
        for ref in h_lines:
            d = abs(pos.y() - ref)
            if d < best_y_diff:
                best_y = ref
                best_y_diff = d

        p = QPointF(pos)
        if best_x is not None:
            p.setX(best_x)
        if best_y is not None:
            p.setY(best_y)
        return p, None

    def _paint_snap_guides(self, painter: QPainter, prev, snapped) -> None:
        """绘制上一条引线文字框的 4 边 + 中心对齐虚线；被吸附的线加亮。"""
        if self.pixmap is None:
            return
        thr = 12.0 / self.scale if self.scale > 0 else 12.0
        r = prev.text_rect()
        w, h = self.pixmap.width(), self.pixmap.height()
        lines = [(r.left(), "v"), (r.right(), "v"), (r.center().x(), "v"),
                 (r.top(), "h"), (r.bottom(), "h"), (r.center().y(), "h")]
        painter.save()
        for val, orient in lines:
            cur = snapped.x() if orient == "v" else snapped.y()
            near = abs(cur - val) < thr
            color = QColor(56, 118, 214, 220) if near else QColor(56, 118, 214, 90)
            pen = QPen(color, 1.5 / self.scale, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            if orient == "v":
                painter.drawLine(QPointF(val, 0), QPointF(val, h))
            else:
                painter.drawLine(QPointF(0, val), QPointF(w, val))
        painter.restore()

    def _paint_new_snap_guides(self, painter: QPainter, hover_pos, leaders: list) -> None:
        """新建标注时绘制所有已有引线的对齐参考线。"""
        if self.pixmap is None:
            return
        thr = 12.0 / self.scale if self.scale > 0 else 12.0
        w, h = self.pixmap.width(), self.pixmap.height()

        # 收集所有参考线
        v_lines = []
        h_lines = []
        for it in leaders:
            r = it.text_rect()
            v_lines.extend([r.left(), r.center().x(), r.right()])
            h_lines.extend([r.top(), r.center().y(), r.bottom()])

        painter.save()
        for val in v_lines:
            near = abs(hover_pos.x() - val) < thr
            color = QColor(56, 118, 214, 220) if near else QColor(56, 118, 214, 70)
            pen = QPen(color, 1.5 / self.scale, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(val, 0), QPointF(val, h))
        # 水平参考线延伸到所有标注文字的左右边界
        all_left = 0.0
        all_right = float(w)
        if len(self.items) > 0:
            lefts = []
            rights = []
            for it in self.items:
                r = it.text_rect()
                if not r.isNull():
                    lefts.append(r.left())
                    rights.append(r.right())
            if lefts and rights:
                all_left = min(lefts)
                all_right = max(rights)

        for val in h_lines:
            near = abs(hover_pos.y() - val) < thr
            color = QColor(56, 118, 214, 220) if near else QColor(56, 118, 214, 70)
            pen = QPen(color, 1.5 / self.scale, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(all_left, val), QPointF(all_right, val))
        painter.restore()

    def _paint_drag_snap_guides(self, painter: QPainter, item: LeaderLineItem) -> None:
        """拖动文字时绘制所有对齐参考线。
        所有线淡显，只有最近的那一根高亮。"""
        if self.pixmap is None:
            return
        thr = 20.0 / self.scale if self.scale > 0 else 20.0
        cur_rect = item.text_rect()
        w, h = self.pixmap.width(), self.pixmap.height()
        v_lines, h_lines = self._get_ref_lines(item)
        if not v_lines and not h_lines:
            return

        painter.save()

        # 找最近的竖直参考线（按线类型对应位置计算距离）
        nearest_v_x = None
        nearest_v_dist = thr
        for x, align_type in v_lines:
            if align_type == "left":
                tgt = cur_rect.left()
            elif align_type == "right":
                tgt = cur_rect.right()
            else:
                tgt = cur_rect.center().x()
            d = abs(tgt - x)
            if d < nearest_v_dist:
                nearest_v_dist = d
                nearest_v_x = x

        # 绘制所有竖直参考线
        for x, _ in v_lines:
            near = (x == nearest_v_x)
            color = QColor(56, 118, 214, 220) if near else QColor(56, 118, 214, 60)
            pen = QPen(color, 2.0 / self.scale if near else 1.0 / self.scale,
                       Qt.PenStyle.DashLine if not near else Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, 0), QPointF(x, h))

        # 找最近的水平参考线
        nearest_h_y = None
        nearest_h_dist = thr
        for y, align_type in h_lines:
            if align_type == "top":
                tgt = cur_rect.top()
            elif align_type == "bottom":
                tgt = cur_rect.bottom()
            else:
                tgt = cur_rect.center().y()
            d = abs(tgt - y)
            if d < nearest_h_dist:
                nearest_h_dist = d
                nearest_h_y = y

        # 绘制所有水平参考线（从最左标注到最右标注，贯穿左右）
        # 计算所有标注文字的左右边界
        all_left = 0.0
        all_right = float(w)
        if len(self.items) > 0:
            lefts = []
            rights = []
            for it in self.items:
                r = it.text_rect()
                if not r.isNull():
                    lefts.append(r.left())
                    rights.append(r.right())
            if lefts and rights:
                all_left = min(lefts)
                all_right = max(rights)

        for y, _ in h_lines:
            near = (y == nearest_h_y)
            color = QColor(56, 118, 214, 220) if near else QColor(56, 118, 214, 60)
            pen = QPen(color, 2.0 / self.scale if near else 1.0 / self.scale,
                       Qt.PenStyle.DashLine if not near else Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(all_left, y), QPointF(all_right, y))

        painter.restore()

    # ================= 文字对齐磁吸 =================
    def _snap_item_on_release(self, item: LeaderLineItem) -> None:
        """松开鼠标时执行吸附：
        按线类型对应对齐：左边线对齐左边界，中间线对齐中心，右边线对齐右边界。
        """
        if not isinstance(item, LeaderLineItem):
            return
        margin = 5.0 / self.scale if self.scale > 0 else 5.0
        r = item.text_rect()
        v_lines, h_lines = self._get_ref_lines(item)
        if not v_lines and not h_lines:
            return

        # ============ X 轴 ============
        if v_lines:
            v_x_vals = [x for x, _ in v_lines]
            v_min = min(v_x_vals)
            v_max = max(v_x_vals)
            cx = r.center().x()
            # 判断是否在吸附范围内
            if v_min - margin <= cx <= v_max + margin:
                # 找最近的线，按线类型对应对齐
                best_diff = 999999.0
                for ref, align_type in v_lines:
                    # 根据线类型，用当前标注对应的边来计算距离
                    if align_type == "left":
                        tgt = r.left()
                    elif align_type == "right":
                        tgt = r.right()
                    else:  # center
                        tgt = r.center().x()
                    diff = ref - tgt
                    if abs(diff) < abs(best_diff):
                        best_diff = diff
                if abs(best_diff) < 999999.0:
                    item.text_point.setX(item.text_point.x() + best_diff)

        # ============ Y 轴 ============
        if h_lines:
            h_y_vals = [y for y, _ in h_lines]
            h_min = min(h_y_vals)
            h_max = max(h_y_vals)
            cy = r.center().y()
            if h_min - margin <= cy <= h_max + margin:
                best_diff = 999999.0
                for ref, align_type in h_lines:
                    if align_type == "top":
                        tgt = r.top()
                    elif align_type == "bottom":
                        tgt = r.bottom()
                    else:  # center
                        tgt = r.center().y()
                    diff = ref - tgt
                    if abs(diff) < abs(best_diff):
                        best_diff = diff
                if abs(best_diff) < 999999.0:
                    item.text_point.setY(item.text_point.y() + best_diff)

        # 检查是否和其他标注重合，重合就自动偏移
        self._avoid_overlap(item)

    def _avoid_overlap(self, item: LeaderLineItem) -> None:
        """检查 item 是否和其他标注重合，如果重合就自动偏移。"""
        if not isinstance(item, LeaderLineItem):
            return
        r = item.text_rect()
        fs = float(item.font_size or 18)
        row_gap = fs * 1.5  # 最小行间距

        # 向下偏移直到不重合
        for _ in range(20):  # 最多偏移20次
            overlap = False
            for other in self.items:
                if other is item or not isinstance(other, LeaderLineItem):
                    continue
                other_r = other.text_rect()
                # 检查两个文字框是否重叠
                if (r.left() < other_r.right() and r.right() > other_r.left() and
                        r.top() < other_r.bottom() and r.bottom() > other_r.top()):
                    overlap = True
                    break
            if not overlap:
                break
            # 重合，向下偏移一个行高
            item.text_point.setY(item.text_point.y() + row_gap)
            r = item.text_rect()

    def _snap_axis(self, r, others, thr: float, axis: str) -> float:
        """返回该轴的吸附偏移量（0 = 无吸附）。"""
        mode = self.snap_mode
        pairs: list = []
        if axis == "x":
            for o in others:
                or_ = o.text_rect()
                if mode in ("left", "corner"):
                    pairs.append((or_.left(), r.left()))
                if mode == "right":
                    pairs.append((or_.right(), r.right()))
                if mode in ("hcenter", "center"):
                    pairs.append((or_.center().x(), r.center().x()))
                if mode == "end" and o.label_style == STYLE_ABOVE:
                    _, outer, _ = o._above_geometry()
                    pairs.append((outer.x(), r.left()))
                    pairs.append((outer.x(), r.right()))
        else:
            for o in others:
                or_ = o.text_rect()
                if mode in ("top", "corner"):
                    pairs.append((or_.top(), r.top()))
                if mode in ("vcenter", "center"):
                    pairs.append((or_.center().y(), r.center().y()))
                if mode == "bottom":
                    pairs.append((or_.bottom(), r.bottom()))
        best = 0.0
        for ref, tgt in pairs:
            diff = ref - tgt
            if abs(diff) < thr and (best == 0.0 or abs(diff) < abs(best)):
                best = diff
        return best

    # ================= 一键自动布局 =================
    # 布局间距参数（面板可调）：左右组上下间隔 = 行数倍率 * 行高；上下组左右间隔 = 字符数 * 字宽
    layout_row_lines = 1.0      # 左右组：上下间隔（行数，默认 1 行）
    layout_col_chars = 2        # 上下组：左右间隔（字符数，默认 2 个字符）
    layout_h_align = "left"     # 左右组水平对齐方式："left"/"center"/"right"
    layout_v_align = "center"    # 上下组垂直对齐方式："top"/"center"/"bottom"

    def auto_layout(self) -> None:
        """一键自动对齐（v2.x 重写）。

        规则（按【目标点】而非文字位置分边，修正图2错误）：
        1. 目标点在图片左半区（0~w/2）的标注，文字/横线贴图片左侧边缘向外排；
           右半区（w/2~w）的贴右侧边缘向外排。
        2. 上下（竖向）标注按目标点 x 智能归入左/右半区（0~w/2 左，w/2~w 右），
           再随该侧贴边；纯上下标注贴图片上/下边缘。
        3. 横线方向（above_dir）由目标点 x 半区决定：左→角在左，右→角在右。
        4. 同侧文字竖直方向保持各自位置（最小移动），左右对应标注 Y 相互对齐。
        """
        leaders = [it for it in self.items if isinstance(it, LeaderLineItem)]
        if len(leaders) < 2 or self.pixmap is None:
            return
        self.push_undo("layout")
        w, h = self.pixmap.width(), self.pixmap.height()
        gap = 12.0

        # 1. 按【目标点】分边（不再按文字中心）
        groups: dict = {"left": [], "right": [], "top": [], "bottom": []}
        for it in leaders:
            tx = it.target_point.x()
            ty = it.target_point.y()
            dx = abs(tx - w / 2.0)
            dy = abs(ty - h / 2.0)
            if dx >= dy:
                groups["left" if tx < w / 2.0 else "right"].append(it)
            else:
                groups["top" if ty < h / 2.0 else "bottom"].append(it)

        # 2. 横线拐点方向：左半区标注的拐点靠图片右缘（横线向左延伸），
        #    右半区标注的拐点靠图片左缘（横线向右延伸）。
        #    注意 above_dir 语义与直觉相反：LEFT=拐点在文字左端，RIGHT=拐点在文字右端。
        for it in leaders:
            it.above_dir = (ABOVE_DIR_RIGHT if it.target_point.x() < w / 2.0
                            else ABOVE_DIR_LEFT)

        # 3. 左组：文字贴图片左缘外（右边缘 = -gap）；右组：贴图片右缘外（左边缘 = w+gap）
        for it in groups["left"]:
            r = it.text_rect()
            it.text_point.setX(it.text_point.x() + (-gap - r.right()))
        for it in groups["right"]:
            r = it.text_rect()
            it.text_point.setX(it.text_point.x() + (w + gap - r.left()))

        # 4. 上下组：贴图片上/下边缘
        for it in groups["top"]:
            r = it.text_rect()
            it.text_point.setY(it.text_point.y() + (-gap - r.bottom()))
        for it in groups["bottom"]:
            r = it.text_rect()
            it.text_point.setY(it.text_point.y() + (h + gap - r.top()))

        # 5. 左右都有时，按目标 Y 顺序对应，使左右标注 Y 对齐（取平均）
        if groups["left"] and groups["right"]:
            lg = sorted(groups["left"], key=lambda it: it.target_point.y())
            rg = sorted(groups["right"], key=lambda it: it.target_point.y())
            n = min(len(lg), len(rg))
            for i in range(n):
                ly = lg[i].text_rect().center().y()
                ry = rg[i].text_rect().center().y()
                avg = (ly + ry) / 2.0
                lg[i].text_point.setY(lg[i].text_point.y() + (avg - ly))
                rg[i].text_point.setY(rg[i].text_point.y() + (avg - ry))

        self.update()
        self.itemsChanged.emit()

    # ================= 就地文字输入 =================
    def start_inline_editor(self, image_pos, callback, initial_text: str = "",
                            allow_empty: bool = False) -> None:
        """在 image_pos（图片坐标）处就地显示文字输入框；确认后回调(content)。

        above 风格时 image_pos 为文字中心：输入框以中心对齐，文字变化时实时保持
        输入框与最终标注文字位置一致（左上角 = 中心 - 当前文字矩形的一半）。
        """
        st = self._new_style()
        fs = int(st.get("font_size", 18))
        self._editor.setFont(make_font(fs))
        self._editor_fm = QFontMetrics(make_font(fs))
        self._editor.setFixedHeight(fs + 12)
        if st.get("label_style") == STYLE_ABOVE:
            self._editor_above_center = self._to_qpoint(image_pos)
            self._editor_above_fm = QFontMetrics(make_font(fs))
            self._editor_pos = self._above_editor_pos(initial_text or " ")
        else:
            self._editor_above_center = None
            self._editor_pos = self._to_qpoint(image_pos)
        self._editor_callback = callback
        self._editor_allow_empty = bool(allow_empty)
        self._editor.reset_done()
        self._editor.setText(initial_text)
        self._editor.setPlaceholderText("输入标注文字")
        try:
            self._editor.textChanged.disconnect()
        except TypeError:
            pass
        self._editor.textChanged.connect(self._on_editor_text_changed)
        self._editor.setFixedWidth(160)
        self._on_editor_text_changed(initial_text)
        self._update_editor_position()
        self._editor.show()
        self._update_editor_position()   # show 后再定位一次（确保位置正确）
        self._editor.setFocus()
        self._editor.selectAll()

    def _above_editor_pos(self, text: str) -> QPointF:
        """above 风格：输入框左上角 = 文字中心 - 当前文字矩形的一半（以中心对齐）。"""
        c = self._editor_above_center
        br = self._editor_above_fm.boundingRect(
            0, 0, 1 << 20, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine,
            text or " ")
        w = br.width() + 2 * TEXT_PAD_X
        h = br.height() + 2 * TEXT_PAD_Y
        return c - QPointF(w / 2.0, h / 2.0)

    def _on_editor_text_changed(self, text: str) -> None:
        if self._editor_fm is not None:
            w = max(160, self._editor_fm.horizontalAdvance(text) + 30)
            self._editor.setFixedWidth(min(w, self.width() - 60))
        if self._editor_above_center is not None:
            self._editor_pos = self._above_editor_pos(text)
            self._update_editor_position()

    def _update_editor_position(self) -> None:
        if self._editor_pos is not None:
            view = self.image_to_view(self._editor_pos)
            self._editor.move(int(view.x()), int(view.y()))

    def _on_editor_confirmed(self, text: str) -> None:
        cb = self._editor_callback
        by_focus_out = self._editor._by_focus_out
        self._editor_callback = None
        self._input_preview = None
        self._hide_editor()
        if by_focus_out:
            # 失焦确认：同一次鼠标点击已被用于确认，忽略其作为新操作
            self._suppress_click = True
        if cb is not None and text.strip():
            cb(text.strip())
        elif cb is not None and getattr(self, "_editor_allow_empty", False):
            cb("")   # 引线标注允许空文本：生成空白文字框

    def _on_editor_cancelled(self) -> None:
        self._editor_callback = None
        self._input_preview = None
        self._hide_editor()

    def _hide_editor(self) -> None:
        if self._editor.isVisible():
            self._editor.hide()
        self._editor_pos = None
        self._input_preview = None
        self.setFocus()
        self.update()

    def _finish_leader(self, target, text_pos, content: str) -> None:
        item = self.add_leader_item(target, text_pos, content)
        self._snap_item_on_release(item)   # 创建时按对齐模式吸附到已有标注
        self.renumber()
        self.push_undo("add")
        self._last_command = ("add_leader",
                              {"target": QPointF(target), "text_pos": QPointF(text_pos),
                               "content": content})
        item.selected = True
        self._await_prompt = True
        self.update()
        self.itemSelectionChanged.emit()

    def _finish_number_leader(self, target, text_pos) -> None:
        """自动序号标注：无需输入文字，序号自动按顺序生成。"""
        # 确保序号开关打开（此模式强制显示序号）
        self.number_enabled = True
        item = self.add_leader_item(target, text_pos, "")
        self._snap_item_on_release(item)   # 创建时按对齐模式吸附到已有标注
        self.renumber()
        self.push_undo("add")
        self._last_command = ("add_leader",
                              {"target": QPointF(target), "text_pos": QPointF(text_pos),
                               "content": ""})
        item.selected = True
        self._await_prompt = True
        self.update()
        self.itemSelectionChanged.emit()

    def _finish_text(self, pos, content: str) -> None:
        item = self.add_text_item(pos, content)
        self.push_undo("add")
        self._last_command = ("add_text",
                              {"content": content, "pos": QPointF(pos),
                               "size": int(item.font_size)})
        item.selected = True
        self._await_prompt = True
        self.update()
        self.itemSelectionChanged.emit()

    def _edit_item_text(self, item, content: str) -> None:
        item.text_content = content
        self.push_undo("edit")
        self.update()

    # ================= 选择模式右键快捷菜单 =================
    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键菜单改由 mouseReleaseEvent 手动弹出（需求6：点击释放后才出现）。

        Windows 平台在右键释放后会自动发送 contextMenuEvent，
        这里一律忽略，避免与手动弹出的菜单重复。
        """
        event.ignore()

    def _show_right_menu(self, view_pos) -> None:
        """在指定视图位置（相对画布控件）弹出选择模式右键菜单。"""
        if self.pixmap is None or self.mode != MODE_SELECT:
            return
        if getattr(self, "_menu_open", False):
            return
        img_pos = self.view_to_image(view_pos)
        hit = self._hit_item_at(img_pos)
        if hit is not None:
            # 右键点到元素：先单选该元素，后续菜单操作以它为目标
            changed = False
            for it in self.items:
                if it.selected != (it is hit):
                    it.selected = (it is hit)
                    changed = True
            if changed:
                self.itemSelectionChanged.emit()
                self.update()

        menu = self._build_context_menu(img_pos)
        try:
            self._menu_open = True
            menu.exec(self.mapToGlobal(view_pos.toPoint()))
        finally:
            self._menu_open = False
            menu.deleteLater()

    def _build_context_menu(self, img_pos) -> QMenu:
        """构建选择模式右键快捷菜单（按类分层：重复标注/元素操作/工具/编辑/画布）。"""
        hit = self._hit_item_at(img_pos)
        menu = QMenu(self)
        # v1.7 需求8：带父控件的 QMenu 不继承应用级样式，需直接套主题 QSS
        from .menu_qss import apply_menu_theme
        apply_menu_theme(menu, getattr(self, "_dark_theme", False))
        # v2.x 需求2：菜单顶部「重复上次标注」——快速恢复最近一次标注指令
        act_last = menu.addAction("重复上次标注", self.repeat_last_annotation)
        _last = getattr(self, "_last_annotation_mode", None)
        act_last.setEnabled(_last is not None and _last != MODE_SELECT)
        menu.addSeparator()
        if hit is not None:
            self._add_item_context_actions(menu, hit)
            menu.addSeparator()
        # —— 工具（快捷选择各项指令操作）——
        tool_menu = menu.addMenu("工具")
        self._populate_tool_menu(tool_menu)
        # —— 编辑 ——
        edit_menu = menu.addMenu("编辑")
        edit_menu.addAction("撤销", "Ctrl+Z", self.undo)
        edit_menu.addAction("重做", "Ctrl+Y", self.redo)
        edit_menu.addAction("重复上一次命令", self.repeat_last_command)
        edit_menu.addAction("确认当前操作", self.confirm_current)
        # —— 画布 ——
        canvas_menu = menu.addMenu("画布")
        canvas_menu.addAction("复制标注图",
                              lambda: self.commandRequested.emit("copy_annotated"))
        canvas_menu.addAction("清空画布",
                              lambda: self.commandRequested.emit("clear_canvas"))
        return menu

    def _hit_item_at(self, img_pos) -> object | None:
        """返回图片坐标处命中的最上层元素（选择模式右键定位）。"""
        for item in reversed(self.items):
            try:
                if item.hit_test(img_pos, 8.0 / self.scale):
                    return item
            except Exception:
                continue
        return None

    # ================= v1.7 需求2：形状/标签手柄（缩放/旋转）=================
    @staticmethod
    def _rot_pt(p, c, deg):
        """点 p 绕中心 c 旋转 deg 度（图片坐标）。"""
        import math
        rad = math.radians(deg)
        dx, dy = p.x() - c.x(), p.y() - c.y()
        return QPointF(c.x() + dx * math.cos(rad) - dy * math.sin(rad),
                       c.y() + dx * math.sin(rad) + dy * math.cos(rad))

    @staticmethod
    def _unrot_pt(p, c, deg):
        return AnnotationCanvas._rot_pt(p, c, -deg)

    def _item_has_handles(self, item) -> bool:
        """哪些元素支持 8 缩放点 + 旋转点：形状 + 文本 + 表情。
        引线不再支持缩放/旋转（与画笔一致），仅保留点击文字横线换向、
        拖动文字调整位置、拖动斜线移动等既有交互（需求2）。"""
        return (isinstance(item, (ShapeItem, TextItem, EmojiItem, ImageItem))
                and item.selected)

    def _item_handle_rect(self, item) -> QRectF:
        """元素编辑手柄的未旋转基准框（图片坐标）。"""
        if isinstance(item, ShapeItem):
            return QRectF(item.rect())
        ub = getattr(item, "unrotated_bounds", None)
        if callable(ub):
            try:
                b = ub()
            except Exception:
                b = None
            if b is not None and b.isValid():
                return QRectF(b)
        return QRectF()

    def _shape_handle_pts(self, item):
        """选中元素的 8 个缩放点 + 1 个旋转点 + 标注尾尖点（图片坐标，随 rotation 旋转）。"""
        r = self._item_handle_rect(item)
        c = r.center()
        rot = float(getattr(item, "rotation", 0.0))
        pts = []
        for fx, fy in ((0, 0), (0.5, 0), (1, 0), (1, 0.5),
                       (1, 1), (0.5, 1), (0, 1), (0, 0.5)):
            lp = QPointF(r.left() + fx * r.width(), r.top() + fy * r.height())
            pts.append(self._rot_pt(lp, c, rot))
        gap = 26.0 / self.scale
        rh = self._rot_pt(QPointF(c.x(), r.top() - gap), c, rot)
        # v2.1 需求2：标注类形状额外返回尾巴尖黄色控制点（随旋转）
        tail_pt = None
        if isinstance(item, ShapeItem) and item.shape in CALLOUT_SHAPES:
            tip = item.tail_tip()
            if tip is not None:
                tail_pt = self._rot_pt(tip, c, rot)
        return pts, rh, tail_pt

    def _hit_shape_handle(self, img_pos):
        """命中选中元素的编辑手柄 → (item, 'resize'|'rotate'|'tail', idx)，否则 None。"""
        tol = 10.0 / self.scale
        for item in reversed(self.items):
            if not self._item_has_handles(item):
                continue
            pts, rh, tail_pt = self._shape_handle_pts(item)
            for i, hp in enumerate(pts):
                if (hp - img_pos).manhattanLength() <= tol:
                    return (item, "resize", i)
            if (rh - img_pos).manhattanLength() <= tol:
                return (item, "rotate", -1)
            if tail_pt is not None and (tail_pt - img_pos).manhattanLength() <= tol:
                return (item, "tail", -2)
        return None

    def _apply_shape_resize(self, e, img) -> None:
        """增量式缩放（v1.7 优化）：拖动边/角 1:1 跟随鼠标，对边/对角锚点
        固定不动（不再按比例映射全部顶点，消除“加速变化”与畸形）；
        越界自动钳制（不翻转），拖出=放大、拖回=缩小，全程可控。"""
        import math as _m
        item = e["item"]
        r0 = e["start_rect"]
        c = e["center"]
        rot = e["start_rot"]
        if r0.width() < 1e-9 or r0.height() < 1e-9:
            return
        local = self._unrot_pt(QPointF(img), c, rot)
        idx = e["idx"]
        left, top = r0.left(), r0.top()
        right, bottom = r0.right(), r0.bottom()
        if idx in (0, 6, 7):
            left = local.x()
        if idx in (2, 3, 4):
            right = local.x()
        if idx in (0, 1, 2):
            top = local.y()
        if idx in (4, 5, 6):
            bottom = local.y()
        # 最小尺寸保护（屏幕 4px），且拖动边不得越过对边（防翻转畸形）
        minv = max(4.0 / self.scale, 1.0)
        if right - left < minv:
            if idx in (2, 3, 4):
                right = left + minv
            else:
                left = right - minv
        if bottom - top < minv:
            if idx in (4, 5, 6):
                bottom = top + minv
            else:
                top = bottom - minv
        new_r = QRectF(QPointF(left, top), QPointF(right, bottom))
        sx = new_r.width() / r0.width()
        sy = new_r.height() / r0.height()
        # 固定锚点 = 被拖角点的对角（旧框固定角，缩放时该点绝对不动）
        anchor = {
            0: QPointF(r0.right(), r0.bottom()),
            1: QPointF(r0.left(), r0.bottom()),
            2: QPointF(r0.left(), r0.bottom()),
            3: QPointF(r0.left(), r0.top()),
            4: QPointF(r0.left(), r0.top()),
            5: QPointF(r0.left(), r0.top()),
            6: QPointF(r0.right(), r0.top()),
            7: QPointF(r0.right(), r0.top()),
        }[idx]

        def _map(p):
            lp = self._unrot_pt(QPointF(p), c, rot)
            nx = anchor.x() + (lp.x() - anchor.x()) * sx
            ny = anchor.y() + (lp.y() - anchor.y()) * sy
            return self._rot_pt(QPointF(nx, ny), c, rot)

        sg = e.get("start_geom") or {}
        start_pts = sg.get("points")
        if start_pts is not None and len(start_pts) >= 2:
            # 折线类：始终从按下时的初始顶点整体缩放（不累乘）
            item.points = [_map(p) for p in start_pts]
            item.p1 = QPointF(item.points[0])
            item.p2 = QPointF(item.points[-1])
        elif isinstance(item, (ShapeItem, ImageItem)):
            # 矩形/椭圆/图片元素：直接设对角点（未旋转坐标系，旋转随 rect 中心生效）
            item.p1 = QPointF(left, top)
            item.p2 = QPointF(right, bottom)
            # 标注形状尾尖在未旋转坐标系内按同一锚点/比例映射，始终贴合本体
            if isinstance(item, ShapeItem) and item.shape in CALLOUT_SHAPES:
                a0 = sg.get("tail_apex")
                if a0 is not None:
                    item.set_tail_apex(QPointF(
                        anchor.x() + (a0.x() - anchor.x()) * sx,
                        anchor.y() + (a0.y() - anchor.y()) * sy))
        else:
            # 引线标签/文本/表情：从初始几何无状态缩放 + 字号按比例缩放
            self._resize_label(item, sg, _map,
                               _m.sqrt(max(sx, 1e-6) * max(sy, 1e-6)))
        e["moved"] = True

    def _resize_label(self, item, start_geom, map_fn, fscale: float) -> None:
        """缩放引线/文本/表情元素：始终以按下时的初始几何为基准，
        target/text/pos 随锚点缩放，字号按比例缩放（逐帧不累乘，不脱离鼠标）。"""
        start_geom = start_geom or {}
        for attr in ("target_point", "text_point", "pos"):
            sv = start_geom.get(attr)
            if sv is not None:
                setattr(item, attr, map_fn(sv))
        start_fs = float(start_geom.get("font_size", 18) or 18)
        item.font_size = max(4, min(300, int(round(start_fs * fscale))))

    def _apply_shape_rotate(self, e, img) -> None:
        """绕元素中心旋转（v1.7 优化）：按鼠标角速度逐帧累加角度增量，
        1:1 跟随鼠标环绕方向；单帧限速防小图形/快速拖动猛转，全程可控。"""
        import math
        item = e["item"]
        c = e["center"]
        prev = e.get("last_img")
        if prev is None:
            prev = QPointF(img)
        a1 = math.atan2(prev.y() - c.y(), prev.x() - c.x())
        a2 = math.atan2(img.y() - c.y(), img.x() - c.x())
        d = math.degrees(a2 - a1)
        while d > 180.0:
            d -= 360.0
        while d < -180.0:
            d += 360.0
        # 单帧限速：超出范围的角位移按上限计，避免一次鼠标跳变造成猛转
        d = max(-25.0, min(25.0, d))
        e["accum"] = e.get("accum", 0.0) + d
        item.rotation = (e["start_rot"] + e["accum"]) % 360.0
        e["last_img"] = QPointF(img)
        e["moved"] = True

    def _apply_tail_drag(self, e, img) -> None:
        """v2.1 需求2（本轮重构，Office 风格）：拖动标注形状的黄色尾尖。

        鼠标位置逆旋转回元素未旋转坐标系后【直接作为尾尖绝对位置】，
        不做任何钳制 —— 尾尖可在主体四周任意位置，角度/长度自由，
        主体 p1/p2 尺寸恒定；根部落边与钳制由 callout_geom 在绘制时完成。"""
        item = e["item"]
        c = e["center"]
        rot = e["start_rot"]
        local = self._unrot_pt(QPointF(img), c, rot)
        item.set_tail_apex(local)
        e["moved"] = True

    def _paint_shape_handles(self, painter: QPainter) -> None:
        """选中元素：蓝色虚线框 + 8 蓝色缩放手柄 + 橙色旋转手柄
        （形状/引线标签/文本/表情通用）。"""
        if self.mode != MODE_SELECT:
            return
        hs = 5.0 / self.scale
        for item in self.items:
            if not self._item_has_handles(item):
                continue
            r = self._item_handle_rect(item)
            c = r.center()
            rot = float(getattr(item, "rotation", 0.0))
            pts, rh, tail_pt = self._shape_handle_pts(item)
            painter.save()
            # 虚线框随元素旋转，框与元素完全贴合
            painter.translate(c)
            painter.rotate(rot)
            painter.translate(-c)
            painter.setPen(QPen(QColor("#2F6FED"), 1.2 / self.scale,
                                Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)
            painter.restore()
            # 8 个缩放点
            painter.setPen(QPen(QColor("#FFFFFF"), 1.0 / self.scale))
            painter.setBrush(QColor("#2F6FED"))
            for hp in pts:
                painter.drawRect(QRectF(hp.x() - hs, hp.y() - hs,
                                        hs * 2, hs * 2))
            # 旋转手柄：中心到顶部连线 + 橙色圆
            painter.setPen(QPen(QColor("#E8590C"), 1.4 / self.scale))
            painter.drawLine(c, rh)
            painter.setBrush(QColor("#E8590C"))
            painter.drawEllipse(rh, hs * 1.6, hs * 1.6)
            # v2.1 需求2：标注类形状尾巴尖黄色菱形控制点（Office 风格）
            if tail_pt is not None:
                diamond = QPolygonF([
                    QPointF(tail_pt.x(), tail_pt.y() - hs * 1.4),
                    QPointF(tail_pt.x() + hs * 1.4, tail_pt.y()),
                    QPointF(tail_pt.x(), tail_pt.y() + hs * 1.4),
                    QPointF(tail_pt.x() - hs * 1.4, tail_pt.y())])
                painter.setPen(QPen(QColor("#B8860B"), 1.0 / self.scale))
                painter.setBrush(QColor("#FFE14D"))
                painter.drawPolygon(diamond)
            painter.restore()

    # ================= v1.7 需求1：虚线框整层拖动 =================
    def _highlight_box(self):
        """当前高亮图层全部元素的外接范围（图片坐标，含 3px 内缩边距）。

        v1.7 优化：隐藏图层被点击时同样显示范围虚线（保证各图层都能
        点击显示全部范围）；单个元素包围盒异常不影响整层虚线框。
        """
        lid = self.highlight_layer_id
        if lid is None:
            return None
        layer = self.layer_by_id(lid)
        if layer is None:
            return None
        union = None
        for it in self.items:
            if it.layer_id != lid:
                continue
            try:
                b = it.export_bounds()
            except Exception:
                b = None
            if b is None or not b.isValid():
                continue
            union = b if union is None else union.united(b)
        if union is None or union.isEmpty():
            return None
        return union.adjusted(-3.0, -3.0, 3.0, 3.0)

    def _add_item_context_actions(self, menu, item) -> None:
        """元素操作区：编辑文字 / 复制 / 删除 / 移动到图层。"""
        if hasattr(item, "text_content"):
            menu.addAction("编辑文字…",
                           lambda it=item: self._edit_item_via_menu(it))
        menu.addAction("复制(克隆)", lambda it=item: self.duplicate_item(it))
        menu.addAction("删除", lambda it=item: self.delete_item(it))
        layer_menu = menu.addMenu("移动到图层")
        cur = item.layer_id
        for layer in self.layers:
            if layer.id == cur:
                continue
            layer_menu.addAction(layer.name,
                                 lambda lid=layer.id, iid=item.id:
                                 self.move_item_to_layer(iid, lid))
        if layer_menu.isEmpty():
            layer_menu.setEnabled(False)

    def _edit_item_via_menu(self, item) -> None:
        """右键「编辑文字」：就地打开输入框编辑该元素文字。"""
        if not hasattr(item, "text_content"):
            return
        anchor = getattr(item, "edit_anchor", None)
        if callable(anchor):
            try:
                pos = anchor()
            except Exception:
                pos = QPointF(getattr(item, "pos", (0, 0))[0],
                              getattr(item, "pos", (0, 0))[1])
        else:
            base = getattr(item, "pos", None)
            if base is None:
                return
            pos = QPointF(base.x(), base.y())
        self.start_inline_editor(
            pos,
            lambda content, it=item: self._edit_item_text(it, content),
            initial_text=getattr(item, "text_content", "") or "")

    def _populate_tool_menu(self, tool_menu) -> None:
        """工具子菜单：列出全部标注模式，可勾选当前模式。"""
        for mode, label in (
            (MODE_SELECT, "选择"),
            (MODE_LEADER, "引线标注"),
            (MODE_NUMBER, "引线序号"),
            (MODE_TEXT, "文本标注"),
            (MODE_SHAPE, "形状"),
            (MODE_PEN, "画笔"),
            (MODE_HIGHLIGHT, "荧光笔"),
            (MODE_MOSAIC, "马赛克"),
            (MODE_EMOJI, "表情"),
        ):
            act = tool_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mode == mode)
            act.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
        tool_menu.addSeparator()
        tool_menu.addAction("自由截图",
                            lambda: self.commandRequested.emit("screenshot"))

    # ================= 复制（克隆） =================
    @staticmethod
    def _offset_item_copy(item, dx: float, dy: float) -> None:
        """给克隆副本整体平移一小段距离，避免与原件完全重叠。"""
        if isinstance(item, (TextItem, EmojiItem)):
            item.pos = QPointF(item.pos.x() + dx, item.pos.y() + dy)
        elif isinstance(item, LeaderLineItem):
            item.text_point = QPointF(item.text_point.x() + dx,
                                      item.text_point.y() + dy)
        elif isinstance(item, ShapeItem):
            item.p1 = QPointF(item.p1.x() + dx, item.p1.y() + dy)
            item.p2 = QPointF(item.p2.x() + dx, item.p2.y() + dy)
            # 标注形状尾尖随克隆副本一起平移
            if getattr(item, "tail_apex", None) is not None:
                item.tail_apex = QPointF(item.tail_apex.x() + dx,
                                         item.tail_apex.y() + dy)
        elif isinstance(item, (MosaicItem, ImageItem)):
            item.p1 = QPointF(item.p1.x() + dx, item.p1.y() + dy)
            item.p2 = QPointF(item.p2.x() + dx, item.p2.y() + dy)
        elif isinstance(item, (PenItem, HighlightItem)):
            item.points = [QPointF(p.x() + dx, p.y() + dy)
                           for p in item.points]

    def duplicate_item(self, item) -> object | None:
        """复制（克隆）指定元素到同图层，副本偏移一小段，生成后选中副本。"""
        if item is None or item not in self.items:
            return None
        try:
            new_item = copy.deepcopy(item)
        except Exception:
            return None
        new_item.id = allocate_item_id()   # deepcopy 保留原 id，必须重新分配
        step = max(16.0, float(getattr(item, "font_size", 18)) * 0.7)
        self._offset_item_copy(new_item, step, step)
        new_item.selected = True
        item.selected = False
        self.items.append(new_item)
        self.renumber()
        self.push_undo("duplicate")
        self._last_command = ("duplicate", None)
        self.update()
        self.itemSelectionChanged.emit()
        self.itemsChanged.emit()
        return new_item

    def duplicate_selected(self) -> object | None:
        sel = self.selected_items()
        if not sel:
            return None
        return self.duplicate_item(sel[0])

    # ================= 重复上一次命令 / 确认 =================
    def repeat_last_annotation(self) -> None:
        """重复上次标注（v2.x 需求2）：恢复最近一次在工具面板使用的标注指令。

        与「重复上一次命令」不同：只恢复标注工具本身（引线标注/引线序号/
        文本批注/形状/画笔/荧光笔/马赛克/表情），不重复删除/复制/清空等
        其它命令。选择模式右键菜单顶部调用，无需回到工具面板。
        """
        mode = getattr(self, "_last_annotation_mode", None)
        if mode is None or mode == MODE_SELECT:
            self.statusMessage.emit("暂无可重复的标注指令")
            return
        self.set_mode(mode)
        _names = {MODE_LEADER: "引线标注", MODE_NUMBER: "引线序号",
                  MODE_TEXT: "文本批注", MODE_SHAPE: "形状", MODE_PEN: "画笔",
                  MODE_HIGHLIGHT: "荧光笔", MODE_MOSAIC: "马赛克",
                  MODE_EMOJI: "表情"}
        self.statusMessage.emit(f"已切换到「{_names.get(mode, mode)}」")

    def repeat_last_command(self) -> None:
        """重复上一次命令：复制→再复制选中；删除→再删选中；
        表情/文本/引线→在原位置偏移一小段重复创建（避免完全重叠）。"""
        name, data = self._last_command or (None, None)
        if name == "duplicate":
            if self.duplicate_selected() is None:
                self.statusMessage.emit("没有可复制的选中元素")
        elif name == "delete":
            self.delete_selected()
            if not self.selected_items():
                self.statusMessage.emit("已重复删除")
        elif name == "add_emoji" and data:
            off = max(16.0, float(data.get("size", 40)) * 0.7)
            pos = QPointF(data["pos"]) + QPointF(off, off)
            try:
                item = self.add_emoji_item(pos, data["emoji"],
                                           int(data["size"]))
                self.push_undo("add")
                item.selected = True
                self._last_command = ("add_emoji",
                                      {"emoji": data["emoji"],
                                       "size": data["size"], "pos": pos})
                self.itemSelectionChanged.emit()
                self.update()
            except Exception:
                pass
        elif name == "add_text" and data:
            off = max(16.0, float(data.get("size", 18)) * 1.5)
            pos = QPointF(data["pos"]) + QPointF(0.0, off)
            item = self.add_text_item(pos, data["content"])
            self.push_undo("add")
            self._last_command = ("add_text",
                                  {"content": data["content"], "pos": pos,
                                   "size": data["size"]})
            item.selected = True
            self.itemSelectionChanged.emit()
            self.update()
        elif name == "add_leader" and data:
            off = 24.0
            t = QPointF(data["target"]) + QPointF(off, off)
            tp = QPointF(data["text_pos"]) + QPointF(off, off)
            item = self.add_leader_item(t, tp, data.get("content", ""))
            self._snap_item_on_release(item)
            self.renumber()
            self.push_undo("add")
            self._last_command = ("add_leader",
                                  {"target": t, "text_pos": tp,
                                   "content": data.get("content", "")})
            item.selected = True
            self.itemSelectionChanged.emit()
            self.update()
        else:
            self.statusMessage.emit("暂无可重复的命令")

    def confirm_current(self) -> None:
        """确认当前操作：输入文字中→确认；直线折线绘制中→完成；否则无操作。"""
        if self._editor.isVisible() and self._editor_callback is not None:
            self._editor._emit_confirmed()
        elif self.mode == MODE_SHAPE and self._line_points is not None:
            self._finish_line_path()

    # ================= 元素去重（唯一性） =================
    @staticmethod
    def _dup_key(it):
        """计算元素的几何+内容指纹；返回 None 表示不参与几何去重。"""
        def _r(v, n=1):
            return (round(float(v.x()), n), round(float(v.y()), n))
        try:
            if isinstance(it, EmojiItem):
                return ("emoji", _r(it.pos), it.emoji, int(it.font_size))
            if isinstance(it, TextItem):
                return ("text", _r(it.pos), it.text_content,
                        int(it.font_size), str(it.text_color.name()))
            if isinstance(it, LeaderLineItem):
                return ("leader", _r(it.target), _r(it.text_point),
                        it.text_content, str(it.line_color.name()))
            if isinstance(it, ShapeItem):
                return ("shape", _r(it.p1), _r(it.p2), it.shape,
                        str(it.border_color.name()))
            if isinstance(it, MosaicItem):
                return ("mosaic", _r(it.p1), _r(it.p2), int(it.block_size))
            if isinstance(it, PenItem):
                return ("pen", tuple(_r(p) for p in it.points))
            if isinstance(it, HighlightItem):
                return ("highlight", tuple(_r(p) for p in it.points),
                        int(it.hl_width))
        except Exception:
            return None
        return None

    def deduplicate_items(self) -> int:
        """清理重复元素：同 id 只保留第一个；同类型同几何同内容的
        完全一致副本只保留第一个。返回移除数量（恢复/打开项目时调用）。"""
        removed = 0
        seen_ids = set()
        seen_geom = {}
        out = []
        for it in self.items:
            if it.id in seen_ids:
                removed += 1
                continue
            key = self._dup_key(it)
            if key is not None:
                if key in seen_geom:
                    removed += 1
                    continue
                seen_geom[key] = True
            seen_ids.add(it.id)
            out.append(it)
        if removed:
            self.items = out
            self.renumber()
            self.update()
            self.itemSelectionChanged.emit()
            self.itemsChanged.emit()
        return removed

    # ================= 绘制 =================
    def paintEvent(self, event) -> None:  # noqa: N802
        # 顶层绘制保护：任何元素渲染异常（如非法/NaN 几何）都不能让程序闪退
        painter = QPainter(self)
        try:
            if self._bg_color is not None:
                painter.fillRect(self.rect(), self._bg_color)

            if self.pixmap is None:
                painter.setPen(QColor(170, 170, 170))
                painter.setFont(make_font(20))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                                 "请从剪贴板粘贴图片，或点击【打开本地图片】")
                return

            painter.save()
            painter.translate(self.offset)
            painter.scale(self.scale, self.scale)
            painter.drawPixmap(0, 0, self.pixmap)
            self._paint_layers(painter)
            self._paint_layer_highlight(painter)
            self._paint_shape_handles(painter)
            self._paint_preview(painter)
            painter.restore()

            # 画布边框
            painter.setPen(QPen(QColor(90, 94, 96), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self.image_to_view(QPointF(0, 0)),
                                    self.image_to_view(QPointF(self.pixmap.width(), self.pixmap.height()))))

            # 「等待下一次点击」提示条
            if self._await_prompt:
                self._paint_prompt(painter)
        except Exception:
            pass
        finally:
            painter.end()

    def _ordered_visible_items(self):
        """按图层顺序（底层在前）返回可见图层上的全部元素。

        注意：显隐只挂在 Layer 上，元素本身没有 visible 属性，不能读 item.visible。
        """
        out = []
        for layer in self.layers:
            if not layer.visible:
                continue
            for item in self.items:
                if item.layer_id == layer.id:
                    out.append(item)
        return out

    def _maybe_build_flattener(self, ordered):
        """存在马赛克时构建「下方内容合成器」（需求5）。

        马赛克源不再只是底图，而是底图 + 位于其下的全部元素（含导入截图
        ImageItem）按图层顺序的合成结果。无马赛克时返回 None，零额外开销。
        离屏尺寸覆盖底图与所有元素外接范围（原点 0,0 = 图片坐标原点）。
        """
        if not any(isinstance(i, MosaicItem) for i in ordered):
            return None
        if self.pixmap is not None and not self.pixmap.isNull():
            w, h = self.pixmap.width(), self.pixmap.height()
        else:
            w = h = 1
        for it in ordered:
            try:
                b = it.export_bounds()
            except Exception:
                b = None
            if b is None:
                continue
            w = max(w, int(b.right()) + 1)
            h = max(h, int(b.bottom()) + 1)
        try:
            flat = BelowFlattener(self.pixmap, w, h)
        except Exception:
            return None
        if not flat.usable:
            flat.end()
            return None
        return flat

    def _paint_layers(self, painter: QPainter) -> None:
        """按图层顺序绘制元素（底层在前，隐藏层跳过）。

        逐元素容错：拖动重排/瞬态状态下，单个元素绘制抛异常只跳过它本身，
        不再中断整帧绘制（否则会表现为整层/整批元素「消失一会又出现」）。

        存在马赛克时用 BelowFlattener 边画边累积「下方内容」：每个马赛克
        绘制前取快照作为打码源（含其下导入截图等全部元素）。合成器在本
        方法内即建即销，避免 QPainter 长时间悬挂在离屏图上（最小化/截图
        恢复等场景下更稳）。
        """
        ordered = self._ordered_visible_items()
        flat = self._maybe_build_flattener(ordered)
        try:
            for item in ordered:
                try:
                    if isinstance(item, MosaicItem):
                        if flat is not None:
                            # 源 = 该马赛克下方所有内容（底图+下层元素，含截图）
                            snap = flat.snapshot()
                            item.set_source(
                                self.pixmap if (snap is None or snap.isNull())
                                else snap)
                        elif item._source is not self.pixmap:
                            item.set_source(self.pixmap)
                    item.paint(painter)
                except Exception as e:
                    import sys
                    print(f"[paint] 跳过元素 {getattr(item, 'id', '?')}: {e}",
                          file=sys.stderr)
                finally:
                    # 把本元素叠加进离屏合成，供更上层马赛克使用（export 语义）
                    if flat is not None:
                        flat.paint_below(item)
        finally:
            if flat is not None:
                flat.end()

    def _paint_layer_highlight(self, painter: QPainter) -> None:
        """选中某图层后，用橙虚线框把该图层所有元素的整体范围醒目包围。"""
        box = self._highlight_box()
        if box is None:
            return
        painter.save()
        # 外层柔光 + 内层橙虚线，保证明暗背景上都醒目
        glow = QPen(QColor(255, 122, 0, 70), 5.0, Qt.PenStyle.SolidLine)
        painter.setPen(glow)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        pen = QPen(QColor("#FF7A00"), 1.8, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(box)
        painter.restore()

    def _paint_preview(self, painter: QPainter) -> None:
        """引线/形状/画笔绘制过程的预览。"""
        # 输入文字期间的引线预览
        if self._input_preview is not None:
            self._paint_input_preview(painter)
        # 引线预览（目标点 -> 鼠标位置）
        if self.mode in (MODE_LEADER, MODE_NUMBER) and self._pending_target is not None and self._hover_pos is not None:
            st = self._new_style()
            color = QColor(st.get("line_color", "#FF0000"))
            width = int(st.get("line_width", 2))
            painter.save()
            pen = QPen(color, width, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(self._pending_target, self._hover_pos)
            draw_arrow_head(painter, self._pending_target,
                            self._hover_pos - self._pending_target,
                            float(st.get("arrow_size", 14)), color)
            painter.restore()
            # 磁吸参考线：显示所有已有引线的对齐线，靠近时高亮并吸附
            leaders = [it for it in self.items if isinstance(it, LeaderLineItem)]
            if leaders:
                self._paint_new_snap_guides(painter, self._hover_pos, leaders)
        # 拖动标注文字/横线时：绘制基准标注的对齐参考线（方便手动对齐）
        if self._drag is not None and self._drag.get("part") in ("text", "hline") \
                and isinstance(self._drag.get("item"), LeaderLineItem):
            self._paint_drag_snap_guides(painter, self._drag["item"])

        # 形状预览：直线为点击式连续折线；其他形状为拖拽框
        if self.mode == MODE_SHAPE:
            st = self._new_style()
            _stype = st.get("shape_type", "rect")
            painter.save()
            painter.setPen(QPen(QColor(st.get("shape_border_color", "#FF0000")),
                                int(st.get("shape_line_width", 2)),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            fill = QColor(st.get("shape_fill_color", "#FFFFFF00"))
            painter.setBrush(Qt.BrushStyle.NoBrush
                             if _stype == "line" or fill.alpha() == 0 else fill)
            if _stype == "line" and self._line_points:
                self._paint_line_path_preview(painter)
            elif _stype != "line" and self._shape_drag is not None:
                p1, p2 = self._shape_drag
                painter.drawPath(shape_path(_stype, QRectF(p1, p2).normalized()))
            painter.restore()
        # 画笔预览（已画线段）
        if self.mode == MODE_PEN and self._pen_points:
            st = self._new_style()
            painter.save()
            painter.setPen(QPen(QColor(st.get("pen_color", "#000000")),
                                int(st.get("pen_width", 3)),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QPolygonF(self._pen_points))
            painter.restore()
        # 荧光笔预览
        if self.mode == MODE_HIGHLIGHT and self._hl_points:
            st = self._new_style()
            hc = QColor(st.get("hl_color", "#FFE600"))
            hc.setAlpha(int(st.get("hl_alpha", 80)))
            painter.save()
            painter.setPen(QPen(hc, int(st.get("hl_width", 22)),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QPolygonF(self._hl_points))
            painter.restore()
        # 马赛克预览（虚线框 + 半透明蓝）
        if self.mode == MODE_MOSAIC and self._mosaic_drag is not None:
            p1, p2 = self._mosaic_drag
            painter.save()
            painter.setPen(QPen(PREVIEW_COLOR, 1.5 / self.scale, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 120, 215, 40))
            painter.drawRect(QRectF(p1, p2).normalized())
            painter.restore()

    def _paint_input_preview(self, painter: QPainter) -> None:
        """输入文字期间，用当前样式持续显示引线预览（目标点 -> 文字位置）。"""
        target, text_pos = self._input_preview
        st = self._new_style()
        tmp = LeaderLineItem(
            (target.x(), target.y()), (text_pos.x(), text_pos.y()), " ",
            line_color=st.get("line_color", "#FF0000"),
            line_width=st.get("line_width", 2),
            arrow_size=st.get("arrow_size", 14),
            endpoint_style=st.get("endpoint_style", "arrow"),
            label_style=st.get("label_style", "plain"),
            font_size=st.get("font_size", 18),
            text_color=st.get("text_color", "#000000"))
        tmp.paint(painter, export=True)
        # 文字位置虚线框提示（按当前标注风格计算文字矩形；above 风格不画框）
        if st.get("label_style") != STYLE_ABOVE:
            painter.save()
            text_rect = tmp.text_rect()
            painter.setPen(QPen(PREVIEW_COLOR, 1.5 / self.scale, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(text_rect)
            painter.restore()

    def _paint_prompt(self, painter: QPainter) -> None:
        """顶部居中的半透明提示条：提示用户点击目标点开始下一条标注。"""
        if self.mode in (MODE_LEADER, MODE_NUMBER):
            msg = "点击目标点，开始下一条标注（Esc 取消）"
        else:
            msg = "点击放置位置，开始下一条批注（Esc 取消）"
        painter.save()
        painter.setFont(make_font(14))
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(msg) + 28
        h = fm.height() + 12
        rect = QRectF((self.width() - w) / 2.0, 10.0, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, msg)
        painter.restore()

    # ================= 鼠标交互 =================
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.pixmap is None:
            return
        # 鼠标中键 = 拖动平移（按住中键拖动画布）
        if event.button() == Qt.MouseButton.MiddleButton:
            # 直线连续折线绘制中：中键完成画线（与回车/ESC相同）
            if self.mode == MODE_SHAPE and self._line_points is not None:
                self._finish_line_path()
                return
            self._panning = True
            self._last_pan = QPointF(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._suppress_click:
            # 失焦确认输入后紧跟的同一次鼠标点击：只用于确认，不作为新操作
            self._suppress_click = False
            return
        # 右键按下（需求3/4/6）：
        # - 非选择模式（指令功能）先切换到选择模式，本次不弹菜单；
        # - 按下即记录；之后一旦发生位移（超过阈值）【立即】进入平移画布，
        #   无长按延迟，释放时不弹菜单；短按（未位移）释放才在选择模式弹菜单。
        if event.button() == Qt.MouseButton.RightButton:
            switched = False
            if self.mode != MODE_SELECT:
                if self.mode == MODE_SHAPE and self._line_points is not None:
                    self._finish_line_path()
                self.set_mode(MODE_SELECT)
                switched = True
            self._rbtn = {"pos": QPointF(event.position()),
                          "pan": False,
                          "switched": switched}
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # 新的左键按下：取消尚未触发的单击翻转（这是双击的第二下，要去编辑文字）
        if self._line_toggle_timer.isActive():
            self._line_toggle_timer.stop()
            self._line_toggle_item = None
        self._await_prompt = False   # 用户开始新操作，隐藏提示
        pos = self.view_to_image(QPointF(event.position()))

        # 吸管模式：点击取图片颜色设为画布背景
        if self._picking_color:
            if self._pick_color_at(pos):
                self._picking_color = False
                self.setCursor(Qt.CursorShape.CrossCursor if self.mode != MODE_SELECT
                               else Qt.CursorShape.ArrowCursor)
            return

        if self.mode == MODE_SELECT:
            # v1.7 需求2：优先命中选中形状的编辑手柄（8 缩放点 + 旋转点）
            edit = self._hit_shape_handle(QPointF(pos))
            if edit is not None:
                item, kind, idx = edit
                changed = False
                for it in self.items:
                    if it.selected != (it is item):
                        it.selected = (it is item)
                        changed = True
                if changed:
                    self.itemSelectionChanged.emit()
                import math as _m
                hr = self._item_handle_rect(item)
                c = hr.center()
                # v1.7 再优化：快照标签/文本/表情的初始几何与字号，
                # 缩放时始终从初始状态计算，避免逐帧累乘导致“越拖越快、脱离鼠标”
                start_geom = {}
                for _a in ("target_point", "text_point", "pos"):
                    _v = getattr(item, _a, None)
                    if _v is not None:
                        start_geom[_a] = QPointF(_v)
                if getattr(item, "points", None):
                    start_geom["points"] = [QPointF(_p) for _p in item.points]
                # 标注形状：记录尾尖初始位置（未旋转坐标），缩放时随主体等比映射，
                # 避免主体放大/缩小时尾巴停在原处、根部脱离本体边线。
                if isinstance(item, ShapeItem) and item.shape in CALLOUT_SHAPES:
                    start_geom["tail_apex"] = QPointF(item.tail_apex_point())
                start_geom["font_size"] = float(getattr(item, "font_size", 18) or 18)
                self._shape_edit = {
                    "item": item, "kind": kind, "idx": idx,
                    "start_rect": QRectF(hr),
                    "start_rot": float(getattr(item, "rotation", 0.0)),
                    "center": QPointF(c),
                    "start_geom": start_geom,
                    "start_angle": _m.atan2(QPointF(pos).y() - c.y(),
                                            QPointF(pos).x() - c.x()),
                    "last_img": QPointF(pos),
                    "img": QPointF(pos), "moved": False,
                }
                self._drag = None
                self._op_pre_snap = self._snapshot()
                self.update()
                return
            hit = None
            for item in reversed(self.items):
                part = item.hit_test(pos, 8.0 / self.scale)
                if part:
                    hit = (item, part)
                    break
            if hit is None:
                # 选中元素虚拟范围框内部空白处也可整体拖动
                # （无填充形状内部、标签包围盒内空白、引线/画笔等包围盒内），
                # 优先于整层拖动；不再要求元素带缩放/旋转手柄（需求2）
                _tol = 8.0 / self.scale
                for item in reversed(self.items):
                    if not item.selected:
                        continue
                    hr = self._item_handle_rect(item)
                    if not hr.isValid():
                        continue
                    lp = self._unrot_pt(
                        QPointF(pos), hr.center(),
                        float(getattr(item, "rotation", 0.0)))
                    if hr.adjusted(-_tol, -_tol, _tol, _tol).contains(lp):
                        hit = (item, "body")
                        break
            if hit is None and self.highlight_layer_id is not None:
                # v1.7 需求1：点击虚线框内部空白 → 拖动整层元素一起移动；
                # 点击虚线框外空白 → 隐藏虚线框（v1.6 需求4）
                box = self._highlight_box()
                if box is not None and box.adjusted(
                        -6.0 / self.scale, -6.0 / self.scale,
                        6.0 / self.scale, 6.0 / self.scale).contains(pos):
                    self._layer_drag = {
                        "layer_id": self.highlight_layer_id,
                        "img": QPointF(pos), "moved": False}
                    self._drag = None
                    self._op_pre_snap = self._snapshot()
                    self.update()
                    return
                self.highlight_layer_id = None
            changed = False
            for item in self.items:
                if item.selected != (hit is not None and item is hit[0]):
                    item.selected = (hit is not None and item is hit[0])
                    changed = True
            if hit:
                item, part = hit
                import time as _time
                self._drag = {"item": item, "part": part, "moved": False,
                              "img": QPointF(pos),
                              "press_time": _time.time(),
                              "press_view": QPointF(event.position())}
            if changed:
                self.itemSelectionChanged.emit()
            self.update()

        elif self.mode == MODE_LEADER:
            if self._pending_target is None:
                # 第一次点击：确定引线箭头端点（指向目标）
                self._pending_target = pos
            else:
                # 第二次点击：确定文字位置，输入期间保持引线预览可见
                target = QPointF(self._pending_target)
                text_pos, _ = self._snap_hover_to_base(QPointF(pos))
                self._pending_target = None
                self._hover_pos = None
                self._input_preview = (target, text_pos)
                self.start_inline_editor(
                    text_pos,
                    lambda content, t=target, tp=text_pos: self._finish_leader(t, tp, content),
                    allow_empty=True)
            self.update()

        elif self.mode == MODE_NUMBER:
            # 自动序号标注：两次点击（目标点 + 文字位置），无需输入文字
            if self._pending_target is None:
                self._pending_target = pos
            else:
                target = QPointF(self._pending_target)
                text_pos, _ = self._snap_hover_to_base(QPointF(pos))
                self._pending_target = None
                self._hover_pos = None
                self._finish_number_leader(target, text_pos)
            self.update()

        elif self.mode == MODE_TEXT:
            self.start_inline_editor(
                pos,
                lambda content, p=QPointF(pos): self._finish_text(p, content))

        elif self.mode == MODE_SHAPE:
            _stype = self._new_style().get("shape_type", "rect")
            if _stype == "line":
                # 直线为点击式连续折线：逐点点击确认，线段跟随鼠标，Esc/双击/回车结束
                if self._line_points is None:
                    self._line_points = [QPointF(pos)]
                else:
                    _start = self._line_points[0]
                    _close_tol = 10.0 / self.scale
                    # v1.6 需求5：点击位置靠近初始起点 → 自动磁吸连接形成封闭图形
                    # （用实际点击点判断，_line_cursor 在鼠标未移动时是上一顶点）
                    if (abs(pos.x() - _start.x()) <= _close_tol
                            and abs(pos.y() - _start.y()) <= _close_tol):
                        self._line_points.append(QPointF(_start))
                        self._finish_line_path()
                        return
                    _cur = (QPointF(self._line_cursor)
                            if self._line_cursor is not None else QPointF(pos))
                    # 追加“所见即所得”的已吸附端点（与跟随预览保持一致）
                    self._line_points.append(_cur)
                self._line_cursor = QPointF(pos)
                self._line_snap_axis = None
            else:
                # 其他形状：按下确定起点，拖动预览，松开完成
                # 若中途从直线切到其他形状，先清掉残留折线状态
                self._line_points = None
                self._line_cursor = None
                self._line_snap_axis = None
                self._shape_drag = (QPointF(pos), QPointF(pos))
            self.update()

        elif self.mode == MODE_PEN:
            # 画笔：按下开始记录轨迹点
            self._pen_points = [QPointF(pos)]
            self._pen_drawing = True
            self.update()

        elif self.mode == MODE_HIGHLIGHT:
            # 荧光笔：按下开始记录轨迹点
            self._hl_points = [QPointF(pos)]
            self._hl_drawing = True
            self.update()

        elif self.mode == MODE_MOSAIC:
            # 马赛克：按下确定矩形起点
            self._mosaic_drag = (QPointF(pos), QPointF(pos))
            self.update()

        elif self.mode == MODE_EMOJI:
            # 表情：单击即在点击位置放置当前表情（pos 为图片坐标）
            try:
                st = self._new_style()
                _ch = st.get("emoji_char", "😀")
                _sz = int(st.get("emoji_size", 40))
                item = self.add_emoji_item(QPointF(pos), _ch, _sz)
                self.push_undo("add")
                self._last_command = ("add_emoji",
                                      {"emoji": _ch, "size": _sz,
                                       "pos": QPointF(pos)})
                item.selected = True
                self.itemSelectionChanged.emit()
            except Exception:
                pass
            self.update()

    def _update_hover_cursor(self, img) -> None:
        """选择模式悬停光标（需求1/3）：
        - 缩放手柄 → Windows 默认双向箭头；旋转点 → 手型；
        - 命中【已选中】元素的虚拟范围框内 → 移动十字箭头 SizeAll；
        - 其余（未选中元素 / 框外）→ 正常选择箭头 Arrow，不显示抓取手型。"""
        if self.mode != MODE_SELECT:
            self.unsetCursor()
            return
        # 1) 缩放/旋转/尾尖手柄（仅支持手柄的元素：形状/文本/表情）
        h = self._hit_shape_handle(QPointF(img))
        if h is not None:
            _item, kind, idx = h
            if kind in ("rotate", "tail"):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                return
            _cur = {
                0: Qt.CursorShape.SizeFDiagCursor, 1: Qt.CursorShape.SizeVerCursor,
                2: Qt.CursorShape.SizeBDiagCursor, 3: Qt.CursorShape.SizeHorCursor,
                4: Qt.CursorShape.SizeFDiagCursor, 5: Qt.CursorShape.SizeVerCursor,
                6: Qt.CursorShape.SizeBDiagCursor, 7: Qt.CursorShape.SizeHorCursor,
            }
            self.setCursor(_cur.get(idx, Qt.CursorShape.ArrowCursor))
            return
        # 2) 命中已选中元素的虚拟范围框 → 移动十字箭头（图1）
        tol = 8.0 / self.scale
        for item in reversed(self.items):
            if not getattr(item, "selected", False):
                continue
            # 引线按命中部位区分光标：端点/文字/横线 = 拖动手型（分别拖动
            # 端点与文字位置），斜线 = 整体平移 SizeAll；包围盒空白处也算整体移动
            if isinstance(item, LeaderLineItem):
                part = item.hit_test(QPointF(img), tol)
                if part in ("target", "text", "hline"):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                    return
                if part in ("dline", "line"):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return
                box = self._item_handle_rect(item)
                if box.isValid() and not box.isEmpty() \
                        and box.adjusted(-tol, -tol, tol, tol).contains(QPointF(img)):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            box = self._item_handle_rect(item)
            if box.isValid() and not box.isEmpty():
                rot = float(getattr(item, "rotation", 0.0) or 0.0)
                if abs(rot) > 0.01:
                    lp = self._unrot_pt(QPointF(img), box.center(), rot)
                    inside = box.adjusted(-tol, -tol, tol, tol).contains(lp)
                else:
                    inside = box.adjusted(-tol, -tol, tol, tol).contains(QPointF(img))
                if inside:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return
            # 兜底：直接命中元素本体（如引线斜线附近）→ 移动光标
            if item.hit_test(QPointF(img), tol):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            break
        # 3) 其余：正常选择箭头（图2），不显示抓取符号
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.pixmap is None:
            return
        pos = QPointF(event.position())
        img = self.view_to_image(pos)
        self.cursorMoved.emit(img.x(), img.y())

        rb = getattr(self, "_rbtn", None)
        if rb is not None and (event.buttons() & Qt.MouseButton.RightButton):
            # v1.7 需求4：右键只要发生位移（超过阈值）立即进入平移，零延迟；
            # 是否弹右键菜单取决于释放时是否发生过位移
            if not rb.get("pan"):
                _mv = pos - rb["pos"]
                if abs(_mv.x()) > 4.0 or abs(_mv.y()) > 4.0:
                    rb["pan"] = True
                    self._panning = True
                    self._last_pan = QPointF(pos)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if self._panning:
            delta = pos - self._last_pan
            self.offset += delta
            self._last_pan = pos
            self._update_editor_position()
            self.update()
            self.viewChanged.emit()
            return

        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            d = img - self._drag["img"]
            if d.x() != 0 or d.y() != 0:
                self._drag["moved"] = True
                self._drag["item"].move_by(d.x(), d.y(), self._drag["part"])
                self._drag["img"] = QPointF(img)
                # 拖动过程中不吸附，自由移动；松开鼠标时才自动吸附。
                # 引线端点/文字/横线 = 抓取手型（只动局部）；斜线及其余 = 整体移动
                _part = self._drag.get("part")
                if isinstance(self._drag["item"], LeaderLineItem) \
                        and _part in ("target", "text", "hline"):
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()
            return

        # v1.7 需求1：拖动图层虚线框 → 该层全部元素一起移动
        if self._layer_drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            d = img - self._layer_drag["img"]
            if d.x() != 0 or d.y() != 0:
                self._layer_drag["moved"] = True
                lid = self._layer_drag["layer_id"]
                for it in self.items:
                    if it.layer_id == lid:
                        it.move_by(d.x(), d.y(), "line")
                self._layer_drag["img"] = QPointF(img)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()
            return

        # v1.7 需求2：形状手柄编辑（缩放 / 绕中心旋转）
        # v2.1 需求2：标注类形状尾巴尖拖拉
        if self._shape_edit is not None and event.buttons() & Qt.MouseButton.LeftButton:
            e = self._shape_edit
            if e["kind"] == "resize":
                self._apply_shape_resize(e, QPointF(img))
            elif e["kind"] == "tail":
                self._apply_tail_drag(e, QPointF(img))
            else:
                self._apply_shape_rotate(e, QPointF(img))
            self.update()
            return

        if self.mode in (MODE_LEADER, MODE_NUMBER) and self._pending_target is not None:
            self._hover_pos = img
            self.update()

        if self.mode == MODE_SHAPE:
            _stype = self._new_style().get("shape_type", "rect")
            if _stype == "line" and self._line_points is not None:
                # 连续折线：无需按住鼠标，最后一段跟随鼠标并做正交磁吸
                _last = self._line_points[-1]
                _p2, _axis = self._line_ortho_snap(_last, QPointF(img))
                _start = self._line_points[0]
                _close_tol = 10.0 / self.scale
                # v1.6 需求5：终点靠近初始起点 → 磁吸到起点，提示可闭合
                if (abs(_p2.x() - _start.x()) <= _close_tol
                        and abs(_p2.y() - _start.y()) <= _close_tol):
                    _p2 = QPointF(_start)
                    _axis = "close"
                self._line_cursor = _p2
                self._line_snap_axis = _axis
                self.update()
            elif _stype != "line" and self._shape_drag is not None \
                    and event.buttons() & Qt.MouseButton.LeftButton:
                p1 = self._shape_drag[0]
                self._shape_drag = (p1, QPointF(img))
                self.update()

        if self.mode == MODE_PEN and self._pen_drawing \
                and event.buttons() & Qt.MouseButton.LeftButton:
            self._pen_points.append(QPointF(img))
            self.update()

        if self.mode == MODE_HIGHLIGHT and self._hl_drawing \
                and event.buttons() & Qt.MouseButton.LeftButton:
            self._hl_points.append(QPointF(img))
            self.update()

        if self.mode == MODE_MOSAIC and self._mosaic_drag is not None \
                and event.buttons() & Qt.MouseButton.LeftButton:
            self._mosaic_drag = (self._mosaic_drag[0], QPointF(img))
            self.update()

        # 悬停（未按住任何键、非平移）时按位置实时更新选择光标（需求1）
        if (self.mode == MODE_SELECT
                and not (event.buttons() & Qt.MouseButton.LeftButton)
                and not (event.buttons() & Qt.MouseButton.RightButton)
                and not self._panning and self._drag is None
                and self._layer_drag is None and self._shape_edit is None
                and not self._picking_color):
            self._update_hover_cursor(img)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        # 重置拖动磁吸状态
        self._drag_snap_state = {}
        # 如果结束了拖动标注，松开鼠标时执行吸附（拖文字/横线都只动文字位置）
        if (event.button() == Qt.MouseButton.LeftButton and self._drag is not None
                and self._drag.get("moved")
                and self._drag.get("part") in ("text", "hline")
                and isinstance(self._drag.get("item"), LeaderLineItem)):
            self._snap_item_on_release(self._drag["item"])
            self.update()  # 吸附后立即重绘
            self.viewChanged.emit()  # 通知视图更新
        # v1.7 需求1/2：结束虚线框整层拖动 / 形状手柄编辑并提交撤销
        if event.button() == Qt.MouseButton.LeftButton:
            if self._layer_drag is not None:
                ld = self._layer_drag
                self._layer_drag = None
                if ld["moved"]:
                    self.commit_op("move")
                self._op_pre_snap = None
            if self._shape_edit is not None:
                se = self._shape_edit
                self._shape_edit = None
                if se["moved"]:
                    self.commit_op("resize")
                self._op_pre_snap = None
        # 右键松开（需求3/6）
        if event.button() == Qt.MouseButton.RightButton:
            rb = getattr(self, "_rbtn", None)
            self._rbtn = None
            if self._panning:
                self._panning = False
                self.unsetCursor()
            if rb is None:
                return
            if rb.get("pan"):
                # 已执行过拖动平移：不再弹右键菜单
                return
            # 短按释放：刚由其它模式切换来的不弹菜单（需求3）；
            # 原本就在选择模式的弹分类快捷菜单（需求6：释放时才出现）
            if (not rb.get("switched", False) and self.mode == MODE_SELECT
                    and self.pixmap is not None):
                self._show_right_menu(QPointF(event.position()))
            return
        # 中键松开：结束平移
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            return
        if (event.button() == Qt.MouseButton.LeftButton and self._drag is not None):
            drag = self._drag
            # —— 单击（非拖动）翻转 above_text/below_text 横线方向 ——
            # 延迟判断：必须未发生拖动、按住时间短、松开位置几乎没移动，
            # 这样拖动文字/横线调整位置时绝不会误触发翻转。
            if not drag.get("moved"):
                self._maybe_toggle_line_dir(event, drag)
            if drag["moved"]:
                self.push_undo("move")
            self._drag = None
            if self.mode == MODE_SELECT:
                self._update_hover_cursor(self.view_to_image(
                    QPointF(event.position())))
        # 形状完成：两点差异足够小时视为误触，不创建
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == MODE_SHAPE and self._shape_drag is not None):
            p1, p2 = self._shape_drag
            self._shape_drag = None
            self._line_snap_axis = None
            try:
                st = self._new_style()
                r = QRectF(p1, p2).normalized()
                _shape_type = st.get("shape_type", "rect")
                # 直线允许水平/垂直（单边长度达标即可）；其他形状需宽高都达标
                if _shape_type == "line":
                    _shape_ok = max(r.width(), r.height()) > 3.0 / self.scale
                else:
                    _shape_ok = (r.width() > 3.0 / self.scale
                                 and r.height() > 3.0 / self.scale)
                if _shape_ok:
                    item = self.add_shape_item(p1, p2, _shape_type)
                    self.push_undo("add")
                    item.selected = True
                    self.itemSelectionChanged.emit()
            except Exception:
                pass
            self.update()
        # 画笔完成
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == MODE_PEN and self._pen_drawing):
            self._pen_drawing = False
            pts = self._pen_points
            self._pen_points = []
            if len(pts) >= 2:
                try:
                    item = self.add_pen_item(pts)
                    self.push_undo("add")
                    item.selected = True
                    self.itemSelectionChanged.emit()
                except Exception:
                    pass
            self.update()

        # 荧光笔完成
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == MODE_HIGHLIGHT and self._hl_drawing):
            self._hl_drawing = False
            pts = self._hl_points
            self._hl_points = []
            if len(pts) >= 1:
                try:
                    item = self.add_highlight_item(pts)
                    self.push_undo("add")
                    item.selected = True
                    self.itemSelectionChanged.emit()
                except Exception:
                    pass
            self.update()

        # 马赛克完成
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == MODE_MOSAIC and self._mosaic_drag is not None):
            p1, p2 = self._mosaic_drag
            self._mosaic_drag = None
            try:
                st = self._new_style()
                r = QRectF(p1, p2).normalized()
                if r.width() > 3.0 / self.scale and r.height() > 3.0 / self.scale:
                    item = self.add_mosaic_item(
                        p1, p2, int(st.get("mosaic_block", 10)),
                        show_border=bool(st.get("mosaic_border", True)))
                    self.push_undo("add")
                    item.selected = True
                    self.itemSelectionChanged.emit()
            except Exception:
                pass
            self.update()

    def _maybe_toggle_line_dir(self, event, drag) -> None:
        """判定这是否是一次有效“单击”；若是则延迟到双击窗口结束后翻转。
        只有真正的点击才会进入：未拖动、按住 < 0.5s、位移 < 5px。"""
        import time as _time
        item = drag.get("item")
        part = drag.get("part")
        if not isinstance(item, LeaderLineItem):
            return
        if item.label_style not in ("above_text", "below_text"):
            return
        if part not in ("text", "line", "hline", "dline"):
            return
        held = _time.time() - drag.get("press_time", _time.time())
        if held > 0.5:                      # 长按不翻转
            return
        pv = drag.get("press_view")
        if pv is not None:
            delta = (QPointF(event.position()) - pv).manhattanLength()
            if delta > 5.0:                # 实际发生了拖动，不翻转
                return
        # 延迟执行：间隔为系统双击判定时间，期间再次按下会被取消
        self._line_toggle_item = item
        self._line_toggle_timer.start(QApplication.doubleClickInterval())

    def _do_toggle_line_dir(self) -> None:
        """定时器触发：真正执行一次横线方向翻转。"""
        item = self._line_toggle_item
        self._line_toggle_item = None
        if not isinstance(item, LeaderLineItem):
            return
        self.push_undo("above_dir")
        item.toggle_horizontal_dir()
        self.update()
        self.viewChanged.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击标注：above 风格引线文字切换横线方向；其它文字/引线可就地修改内容。"""
        # 连续折线绘制中：双击结束（第一次点击已确认最后顶点，直接提交）
        if self.mode == MODE_SHAPE and self._line_points is not None:
            self._finish_line_path()
            return
        if self.pixmap is None or self.mode != MODE_SELECT:
            super().mouseDoubleClickEvent(event)
            return
        pos = self.view_to_image(QPointF(event.position()))
        tol = 8.0 / self.scale
        hit_item = None
        for item in reversed(self.items):          # 第一轮：只认文字
            if item.hit_test(pos, tol) == "text":
                hit_item = item
                break
        if hit_item is not None:
            if isinstance(hit_item, LeaderLineItem) \
                    and hit_item.label_style == STYLE_ABOVE:
                # 双击 above 文字：切换横线方向（向左 <-> 向右）
                self.push_undo("above_dir")
                hit_item.above_dir = (ABOVE_DIR_RIGHT
                                      if hit_item.above_dir == ABOVE_DIR_LEFT
                                      else ABOVE_DIR_LEFT)
                self.update()
                return
            self.start_inline_editor(
                hit_item.edit_anchor(),
                lambda content, it=hit_item: self._edit_item_text(it, content),
                initial_text=hit_item.text_content,
                allow_empty=isinstance(hit_item, LeaderLineItem))
            return
        for item in reversed(self.items):          # 第二轮：允许命中引线/端点
            if item.hit_test(pos, tol) in ("line", "target", "hline", "dline"):
                hit_item = item
                break
        if hit_item is not None:
            self.start_inline_editor(
                hit_item.edit_anchor(),
                lambda content, it=hit_item: self._edit_item_text(it, content),
                initial_text=hit_item.text_content,
                allow_empty=isinstance(hit_item, LeaderLineItem))
            return
        # v2.0 需求5：双击形状（含直线）进入文字编辑
        for item in reversed(self.items):
            if isinstance(item, ShapeItem) and item.hit_test(pos, tol) == "body":
                self.start_inline_editor(
                    item.edit_anchor(),
                    lambda content, it=item: self._edit_item_text(it, content),
                    initial_text=getattr(item, "text_content", ""),
                    allow_empty=True)
                break

    # ================= 滚轮缩放 / 键盘 =================
    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.pixmap is None:
            return
        anchor = QPointF(event.position())
        old_img = self.view_to_image(anchor)
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale = max(0.05, min(8.0, self.scale * factor))
        self.offset = anchor - old_img * self.scale
        self._update_editor_position()
        self.update()
        self.viewChanged.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        # 连续折线绘制中：Esc/回车结束（只丢弃未确认跟随段，保留已确认部分），不切换工具
        if self.mode == MODE_SHAPE and self._line_points is not None \
                and key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish_line_path()
            return
        if key == Qt.Key.Key_Escape:
            self._cancel_pending()
        elif key == Qt.Key.Key_Delete:
            self.delete_selected()
        elif key == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif key == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.redo()
        else:
            super().keyPressEvent(event)

    # ================= 导出渲染 =================
    def render_export(self) -> QImage:
        """把原图 + 全部标注合并渲染为静态图像。

        若标注（文字、横线、端点等）超出原图边界，自动扩展画布，
        扩展区域使用画布背景色，保证所有标注完整显示不被截断。
        """
        w = self.pixmap.width()
        h = self.pixmap.height()
        min_x = min_y = 0.0
        max_x = float(w)
        max_y = float(h)
        for item in self.items:
            r = item.export_bounds()
            if r is None:
                continue
            if r.left() < min_x:
                min_x = r.left()
            if r.top() < min_y:
                min_y = r.top()
            if r.right() > max_x:
                max_x = r.right()
            if r.bottom() > max_y:
                max_y = r.bottom()
        if min_x < 0 or min_y < 0 or max_x > w or max_y > h:
            new_w = int(max_x - min_x + 1)
            new_h = int(max_y - min_y + 1)
            if self.transparent_bg:
                # 透明背景：原图保留，超出部分透明
                img = QImage(max(1, new_w), max(1, new_h), QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.transparent)
            else:
                img = QImage(max(1, new_w), max(1, new_h), QImage.Format.Format_RGB32)
                img.fill(self._bg_color if self._bg_color is not None
                         else QColor(Qt.GlobalColor.white))
            painter = QPainter(img)
            # 原图始终绘制（透明背景时，原图部分不透明，超出部分透明）
            painter.drawPixmap(QPointF(-min_x, -min_y), self.pixmap)
            painter.translate(-min_x, -min_y)
            self._paint_layers_export(painter)
            painter.end()
            return img
        if self.transparent_bg:
            # 透明背景：原图保留，整个图背景透明？不对，原图本身不透明
            # 用户要的是：原图保留，标注背景框透明，不是整个图透明
            # 所以透明背景模式下，还是用原图作为背景，只是不绘制画布背景色
            img = QImage(w, h, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
        else:
            img = QImage(w, h, QImage.Format.Format_RGB32)
            img.fill(Qt.GlobalColor.white)
        painter = QPainter(img)
        # 原图始终绘制
        painter.drawPixmap(0, 0, self.pixmap)
        self._paint_layers_export(painter)
        painter.end()
        return img

    def _paint_layers_export(self, painter: QPainter) -> None:
        """导出时按图层顺序绘制元素（隐藏层跳过）。

        马赛克源同样取「下方全部内容」的合成（含导入截图），与屏幕显示一致。
        """
        ordered = []
        for layer in self.layers:
            if not layer.visible:
                continue
            for item in self.items:
                if item.layer_id == layer.id:
                    ordered.append(item)
        flat = self._maybe_build_flattener(ordered)
        try:
            for item in ordered:
                if isinstance(item, MosaicItem):
                    if flat is not None:
                        snap = flat.snapshot()
                        item.set_source(
                            self.pixmap if (snap is None or snap.isNull())
                            else snap)
                    elif item._source is not self.pixmap:
                        item.set_source(self.pixmap)
                item.paint(painter, export=True)
                if flat is not None:
                    flat.paint_below(item)
        finally:
            if flat is not None:
                flat.end()
