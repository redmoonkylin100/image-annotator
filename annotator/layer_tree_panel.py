# -*- coding: utf-8 -*-
"""图层结构树面板：融合图层管理与历史标注列表，以树状结构展示。

顶层节点为图层，子节点为该图层下的标注元素。
功能涵盖原图层面板与历史面板的全部能力：
  - 图层：增删、重命名、显隐切换、拖拽排序、上下移动、设为当前层、选中本层全部元素
  - 元素：单击选中、双击编辑文字、右键菜单（删除/编辑文字/编辑序号/上下移动/移动到图层）
  - 拖拽：图层可在顶层重排；元素可拖到任意图层下改变归属
  - 显示顺序：树越靠上的图层，其中元素绘制也越靠上（与画布一致）

采用增量刷新策略，绝不 clear() 重建整棵树，
避免信号派发中销毁节点导致 Qt 崩溃（0xC0000409）。
"""

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QInputDialog,
                             QMenu, QMessageBox, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from .items import (LeaderLineItem, ShapeItem, TextItem, HighlightItem,
                    MosaicItem, EmojiItem, ImageItem, format_number, SHAPE_OPTIONS)

# 节点类型标识（存放在 UserRole + 1）
_NODE_TYPE_LAYER = "layer"
_NODE_TYPE_ITEM = "item"

# 类型图标/标签
_ITEM_KIND_LABELS = {
    "leader": "引线",
    "text": "文本",
    "shape": "形状",
    "pen": "画笔",
    "highlight": "荧光",
    "mosaic": "马赛克",
    "emoji": "表情",
    "image": "图片",
}

# v2.0 需求3：各元素类型前的符号（与左侧浮动工具按钮风格一致）
_KIND_GLYPH = {
    "leader": "↗",
    "text": "T",
    "shape": "▭",
    "pen": "✏",
    "highlight": "🖍",
    "mosaic": "▦",
    "emoji": "😀",
    "image": "🖼",
}

# v2.0 需求3：形状子类型 -> 符号（更贴近 Office 形状库）
_SHAPE_GLYPH = {
    "line": "╱", "rect": "▭", "roundrect": "▢", "ellipse": "◯",
    "triangle": "▲", "righttriangle": "◺", "diamond": "◆",
    "pentagon": "⬠", "hexagon": "⬡", "star": "★", "arrow": "➤",
    "leftarrow": "◀", "uparrow": "↑", "downarrow": "↓",
    "leftrightarrow": "⇔", "updownarrow": "⇕",
    "heart": "♥", "cloud": "☁", "parallelogram": "▱",
    "trapezoid": "⏢", "4star": "✦", "moon": "☾",
    "callout": "💬", "plus": "✚",
    "heptagon": "⬯", "octagon": "⬢", "decagon": "⬔", "dodecagon": "⬓",
    "star6": "✡", "star8": "✴", "star16": "✷", "star24": "✵",
    "braceleft": "{", "braceright": "}", "bracketleft": "⟦",
    "bracketright": "⟧", "minus": "−", "times": "✕", "divide": "÷",
    "equal": "=", "notequal": "≠", "donut": "◎", "openarc": "◔",
    "chevron": "❯", "bentarrow": "➥", "curvedarrow": "➲",
    "ribbon": "⊏", "burst": "✸", "document": "📄", "multidoc": "📑",
    "storage": "🛢", "snipe": "▱", "smiley": "☺", "lightning": "⚡",
    "cloudcallout": "💭", "ovalcallout": "💭",
}
# 形状子类型 -> 中文显示名（直接复用 SHAPE_OPTIONS 的标签）
_SHAPE_LABEL = {v: lab for lab, v in SHAPE_OPTIONS}

# 元素节点前景色（暗黑, 明亮）：采用高对比彩色，避免黑白色看不清
_ITEM_KIND_COLORS = {
    "leader":    ("#FF6B6B", "#D92B2B"),   # 红
    "text":      ("#7CE38B", "#1E8E3E"),   # 绿
    "shape":     ("#5AA8FF", "#1F6FD0"),   # 蓝
    "pen":       ("#FFB74D", "#E8590C"),   # 橙
    "highlight": ("#FFD54F", "#B26A00"),   # 黄
    "mosaic":    ("#B39DDB", "#6A4FA3"),   # 紫
    "emoji":     ("#FF8A65", "#D84315"),   # 橙红
}


_BRANCH_ICON_CACHE = {}


def _branch_icon_path(dark: bool, closed: bool) -> str:
    """生成（按主题+方向缓存）图层树展开/折叠三角箭头 PNG，返回 QSS url 路径。

    明亮：深蓝 #1F6FD0；暗黑：亮绿 #7CE38B——明暗背景上都鲜艳可见。
    文件写入应用数据目录 autosave/（源码运行与打包后均可写）。
    """
    key = ("dark" if dark else "light", "c" if closed else "o")
    if key in _BRANCH_ICON_CACHE:
        return _BRANCH_ICON_CACHE[key]
    try:
        from . import settings
        import os as _os
        d = _os.path.join(settings._app_base_dir(), "autosave")
        _os.makedirs(d, exist_ok=True)
        name = ("_branch_dark_c.png" if dark and closed else
                "_branch_dark_o.png" if dark else
                "_branch_light_c.png" if closed else "_branch_light_o.png")
        raw = _os.path.join(d, name)
        path = raw.replace("\\", "/")
        if not _os.path.exists(raw):
            color = "#7CE38B" if dark else "#1F6FD0"
            pm = QPixmap(12, 12)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            if closed:
                # 右箭头（折叠）：实心三角
                p.drawPolygon([QPoint(3, 2), QPoint(10, 6), QPoint(3, 10)])
            else:
                # 下箭头（展开）
                p.drawPolygon([QPoint(2, 3), QPoint(6, 10), QPoint(10, 3)])
            p.end()
            pm.save(raw, "PNG")
        _BRANCH_ICON_CACHE[key] = path
    except Exception:
        _BRANCH_ICON_CACHE[key] = ""
    return _BRANCH_ICON_CACHE[key]


def _item_kind_color(kind: str, dark: bool):
    pair = _ITEM_KIND_COLORS.get(kind)
    if not pair:
        return None
    return QColor(pair[0] if dark else pair[1])


def _item_kind(it) -> str:
    """根据元素类型返回类型字符串。"""
    if isinstance(it, LeaderLineItem):
        return "leader"
    if isinstance(it, TextItem):
        return "text"
    if isinstance(it, ShapeItem):
        return "shape"
    if isinstance(it, HighlightItem):
        return "highlight"
    if isinstance(it, MosaicItem):
        return "mosaic"
    if isinstance(it, EmojiItem):
        return "emoji"
    if isinstance(it, ImageItem):
        return "image"
    return "pen"


def _describe_item(it, idx: int = 0) -> str:
    """生成元素在树中的显示文本：符号 + 【类型】(参数) + 文字内容。"""
    kind = _item_kind(it)
    kind_label = _ITEM_KIND_LABELS.get(kind, "画笔")
    content = (getattr(it, "text_content", "") or "").replace("\n", " ")
    if len(content) > 18:
        content = content[:18] + "…"
    # 符号：形状用其子类型符号，其它类型用通用符号
    glyph = _KIND_GLYPH.get(kind, "✏")
    param = ""
    if kind == "shape":
        glyph = _SHAPE_GLYPH.get(getattr(it, "shape", "rect"), "▭")
        param = _SHAPE_LABEL.get(getattr(it, "shape", "rect"), "形状")
    elif kind == "highlight":
        param = str(getattr(it, "hl_width", ""))
    elif kind == "pen":
        param = str(getattr(it, "pen_width", ""))
    elif kind == "mosaic":
        param = str(getattr(it, "block_size", ""))
    elif kind == "emoji":
        param = ""
    # 引线序号元素：序号本身就是标识
    if isinstance(it, LeaderLineItem) and it.number:
        prefix = f"{glyph} {format_number(it.number, it.number_fmt)} 【{kind_label}】"
        return f"{prefix} {content}".rstrip()
    head = f"{glyph} 【{kind_label}】"
    if param:
        head += f"({param})"
    if content:
        return f"{head} {content}"
    return head


class _LayerTreeWidget(QTreeWidget):
    """自定义 QTreeWidget，处理拖拽逻辑：
    - 图层节点只允许在顶层重排（不允许嵌套到其它图层下）
    - 元素节点允许拖到任意图层节点下（改变元素所属图层）
    - 元素节点不允许嵌套到另一个元素节点下
    """

    itemMovedToLayer = pyqtSignal(int, int)  # item_id, target_layer_id
    dropFinished = pyqtSignal()          # 拖放事件完全结束后发出
    layerOrderEdited = pyqtSignal()      # 图层行被手动重排（请面板同步叠放顺序）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self._dragging_node = None
        self._drag_type = None
        self._in_drop = False   # 拖放事件进行中：禁止任何树刷新，避免闪退

    def _node_type(self, item: QTreeWidgetItem) -> str:
        return item.data(0, Qt.ItemDataRole.UserRole + 1)

    def startDrag(self, supportedActions):
        """记录被拖拽的节点类型（拖拽前校验节点存活）。"""
        items = self.selectedItems()
        if items and not sip.isdeleted(items[0]):
            self._dragging_node = items[0]
            self._drag_type = self._node_type(items[0])
        super().startDrag(supportedActions)

    def dragMoveEvent(self, event):
        """根据拖拽目标决定是否允许放置（节点存活校验，防拖拽期间刷新闪退）。"""
        try:
            src_deleted = (self._dragging_node is None
                           or sip.isdeleted(self._dragging_node))
            target = self.itemAt(event.position().toPoint())
            tgt_deleted = (target is None or sip.isdeleted(target))
        except Exception:
            event.ignore()
            return
        if src_deleted:
            event.ignore()
            return
        if target is None:
            # 拖到空白处：图层可放（排序到末尾），元素不允许
            if self._drag_type == _NODE_TYPE_LAYER:
                event.acceptProposedAction()
            else:
                event.ignore()
            return

        target_type = self._node_type(target)

        if self._drag_type == _NODE_TYPE_LAYER:
            # 拖拽图层：顶层重排；也可落在元素子节点区域（按行插入顶层）
            if target_type == _NODE_TYPE_LAYER and target.parent() is None:
                event.acceptProposedAction()
            elif target_type == _NODE_TYPE_ITEM:
                parent = target.parent()
                if (parent is not None and not sip.isdeleted(parent)
                        and self._node_type(parent) == _NODE_TYPE_LAYER):
                    event.acceptProposedAction()
                else:
                    event.ignore()
            else:
                event.ignore()
        elif self._drag_type == _NODE_TYPE_ITEM:
            # 拖拽元素：只允许放到图层节点上（或图层的子元素区域，最终归到该图层）
            if target_type == _NODE_TYPE_LAYER:
                event.acceptProposedAction()
            elif target_type == _NODE_TYPE_ITEM:
                # 放到元素上 → 归到该元素所在图层
                parent = target.parent()
                if (parent is not None and not sip.isdeleted(parent)
                        and self._node_type(parent) == _NODE_TYPE_LAYER):
                    event.acceptProposedAction()
                else:
                    event.ignore()
            else:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event):
        """处理放下事件：图层重排 / 元素改归属。

        防御（v1.6）：原生拖放期间，源节点可能在拖拽过程中被其它刷新销毁，
        此时再访问该节点会触发 Qt 0xC0000409 闪退。因此：
        - 所有节点访问前先做 sip.isdeleted 存活校验；
        - 整体 try/except 兜底，任何异常都按「忽略本次放下」处理。
        """
        self._in_drop = True
        try:
            target = self.itemAt(event.position().toPoint())
            try:
                src_deleted = (self._dragging_node is None
                               or sip.isdeleted(self._dragging_node))
                tgt_deleted = (target is None or sip.isdeleted(target))
            except Exception:
                event.ignore()
                return

            if src_deleted:
                super().dropEvent(event)
                return

            drag_type = self._drag_type

            if drag_type == _NODE_TYPE_LAYER:
                # 图层重排：完全自行处理，确定性地插到目标图层的上/下一行，
                # 不调用父类 dropEvent，彻底杜绝「图层被嵌套成另一图层子节点」。
                # 效果等价于多次点击「上移/下移图层」，但一步到位。
                if self._manual_layer_reorder(event, target):
                    event.accept()
                    # 重排完成后请求面板把新树顺序同步到画布叠放，
                    # 不依赖 rowsMoved 的时序（避免「树变了但画布没动」）
                    self.layerOrderEdited.emit()
                else:
                    event.ignore()

            elif drag_type == _NODE_TYPE_ITEM:
                # 元素改归属：找到目标图层
                target_layer_id = None
                if target is not None and not tgt_deleted:
                    if self._node_type(target) == _NODE_TYPE_LAYER:
                        target_layer_id = target.data(0, Qt.ItemDataRole.UserRole)
                    elif self._node_type(target) == _NODE_TYPE_ITEM:
                        parent = target.parent()
                        if (parent is not None and not sip.isdeleted(parent)
                                and self._node_type(parent) == _NODE_TYPE_LAYER):
                            target_layer_id = parent.data(0, Qt.ItemDataRole.UserRole)

                if target_layer_id is not None and not src_deleted:
                    item_id = self._dragging_node.data(0, Qt.ItemDataRole.UserRole)
                    # 延迟到拖放事件结束后再发射：若同步刷新树，会在 dropEvent
                    # 派发期间销毁节点，触发 Qt 0xC0000409 闪退
                    QTimer.singleShot(
                        0,
                        lambda iid=item_id, lid=target_layer_id:
                        self.itemMovedToLayer.emit(iid, lid))
                    # 不调用父类 dropEvent，避免树结构变化（靠 refresh 同步）
                    event.accept()
                else:
                    event.ignore()
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass
        finally:
            self._dragging_node = None
            self._drag_type = None
            self._in_drop = False
            try:
                self.dropFinished.emit()
            except Exception:
                pass

    def _manual_layer_reorder(self, event, target) -> bool:
        """把被拖拽的顶层图层确定性地移动到目标位置（只在顶层行之间移动，绝不嵌套）。

        - 目标为图层行：按放置指示符决定插到该图层「上一行/下一行」；
          指示符为落在行内（OnItem）时，按鼠标位于该行的上/下半区分流；
        - 目标为某图层的元素子行：上方=插到其父图层之前，其余=插到其父图层之后；
        - 目标为空白处：移动到列表最末（树最下方 = 绘制最底层）。

        移动结果与多次点击「上移/下移图层」完全一致，只是一步到位。
        全程复用同一个 QTreeWidgetItem（take/insert，不销毁、不新建）。
        """
        try:
            src = self._dragging_node
            if src is None or sip.isdeleted(src):
                return False
            if src.parent() is not None:
                return False  # 只允许顶层图层参与重排
            src_row = self.indexOfTopLevelItem(src)
            if src_row < 0:
                return False
            total = self.topLevelItemCount()

            # 解析目标顶层图层节点
            tgt_layer = None
            if target is not None and not sip.isdeleted(target):
                if (target.parent() is None
                        and self._node_type(target) == _NODE_TYPE_LAYER):
                    tgt_layer = target
                elif self._node_type(target) == _NODE_TYPE_ITEM:
                    par = target.parent()
                    if (par is not None and not sip.isdeleted(par)
                            and self._node_type(par) == _NODE_TYPE_LAYER):
                        tgt_layer = par

            DIP = QAbstractItemView.DropIndicatorPosition
            if tgt_layer is None:
                insert_row = total  # 取出源节点后再 clamp，即落到列表最末
            else:
                tgt_row = self.indexOfTopLevelItem(tgt_layer)
                if tgt_row < 0:
                    return False
                indicator = self.dropIndicatorPosition()
                if target.parent() is not None:
                    # 落在元素子行：指示「上方」→ 父层之前，其余 → 父层之后
                    above = (indicator == DIP.AboveItem)
                elif indicator == DIP.AboveItem:
                    above = True
                elif indicator == DIP.BelowItem:
                    above = False
                else:
                    # OnItem / OnViewport：按鼠标在目标图层行的上下半区分流
                    rect = self.visualItemRect(tgt_layer)
                    my = event.position().toPoint().y()
                    above = my < rect.center().y()
                insert_row = tgt_row if above else tgt_row + 1

            # 取出源节点（同一节点复用，不触发销毁）
            self.takeTopLevelItem(src_row)
            if insert_row > src_row:
                insert_row -= 1
            insert_row = max(0, min(insert_row, self.topLevelItemCount()))
            self.insertTopLevelItem(insert_row, src)
            try:
                self.setCurrentItem(src)
            except Exception:
                pass
            return True
        except Exception:
            return False


class LayerTreePanel(QWidget):
    """图层结构树：图层为顶层节点，标注元素为子节点。"""

    # —— 图层操作信号 ——
    requestAdd = pyqtSignal()
    requestDelete = pyqtSignal(int)          # layer_id
    requestVisible = pyqtSignal(int, bool)   # layer_id, visible
    requestMove = pyqtSignal(int, int)       # layer_id, delta
    requestSelect = pyqtSignal(int)          # layer_id（设为当前层）
    requestReorder = pyqtSignal(list)        # layer ids（自底向上 = 绘制顺序）
    requestRename = pyqtSignal(int, str)     # layer_id, new_name
    requestSelectLayerItems = pyqtSignal(int)  # 选中该图层所有元素
    requestCopyLayer = pyqtSignal(int)        # v2.x 需求3：复制该图层（含全部元素）

    # —— 元素操作信号 ——
    requestSelectItem = pyqtSignal(int)     # 单击：在画布选中该标注
    requestEditText = pyqtSignal(int)       # 双击/右键：就地编辑文字
    requestDeleteItem = pyqtSignal(int)     # 右键：删除该标注
    requestEditNumber = pyqtSignal(int)     # 右键：编辑引线序号
    requestMoveItem = pyqtSignal(int, int)  # 右键：上移/下移（item_id, delta）
    requestMoveItemToLayer = pyqtSignal(int, int)  # 拖拽/右键：移动元素到指定图层（item_id, layer_id）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._layers = []
        self._items = []       # 全部标注元素（来自画布）
        self._layer_items = {}  # layer_id -> QTreeWidgetItem（图层节点）
        self._anno_items = {}   # item.id -> QTreeWidgetItem（元素节点）
        self._dark_theme = False
        self._current_layer_id = None
        self._pending_refresh = None   # 拖放期间挂起的刷新参数
        self._item_objects = {}        # item.id -> item（供主题重着色）

        # 顶部标题栏
        title_row = QHBoxLayout()
        title_row.setContentsMargins(6, 4, 6, 2)
        from PyQt6.QtWidgets import QLabel
        self.title_label = QLabel("图层结构树")
        f = QFont()
        f.setBold(True)
        f.setPixelSize(13)
        self.title_label.setFont(f)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(6, 2, 6, 4)
        btn_row.setSpacing(3)
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("添加图层")
        self.add_btn.setFixedSize(24, 22)
        self.del_btn = QPushButton("−")
        self.del_btn.setToolTip("删除图层")
        self.del_btn.setFixedSize(24, 22)
        self.up_btn = QPushButton("↑")
        self.up_btn.setToolTip("上移图层")
        self.up_btn.setFixedSize(24, 22)
        self.down_btn = QPushButton("↓")
        self.down_btn.setToolTip("下移图层")
        self.down_btn.setFixedSize(24, 22)
        self.expand_btn = QPushButton("⊟")
        self.expand_btn.setToolTip("展开全部")
        self.expand_btn.setFixedSize(24, 22)
        self.collapse_btn = QPushButton("⊞")
        self.collapse_btn.setToolTip("折叠全部")
        self.collapse_btn.setFixedSize(24, 22)
        for b in (self.add_btn, self.del_btn, self.up_btn, self.down_btn,
                  self.expand_btn, self.collapse_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_row.addWidget(b)
        btn_row.addStretch(1)

        self.add_btn.clicked.connect(self.requestAdd.emit)
        self.del_btn.clicked.connect(self._delete_current)
        self.up_btn.clicked.connect(lambda: self._move_current(1))
        self.down_btn.clicked.connect(lambda: self._move_current(-1))
        self.expand_btn.clicked.connect(self._expand_all)
        self.collapse_btn.clicked.connect(self._collapse_all)

        # 树形控件（使用自定义类）
        self.tree = _LayerTreeWidget()
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.model().rowsMoved.connect(self._on_rows_moved)
        self.tree.itemMovedToLayer.connect(self._on_item_moved_to_layer)
        self.tree.dropFinished.connect(self._on_tree_drop_finished)
        # 图层行手动重排（确定性拖拽）→ 同步画布叠放顺序
        self.tree.layerOrderEdited.connect(self._emit_layer_order_from_tree)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(title_row)
        outer.addLayout(btn_row)
        outer.addWidget(self.tree, 1)

    # ============================================================
    #  主题适配
    # ============================================================
    def set_dark_theme(self, dark: bool) -> None:
        """设置明暗主题（与主窗口主题同步）。"""
        self._dark_theme = dark
        if dark:
            self.tree.setStyleSheet("""
                QTreeWidget {
                    background-color: #252535;
                    color: #E8E8E8;
                    border: none;
                    outline: 0;
                    font-size: 12px;
                }
                QTreeWidget::item {
                    padding: 4px 6px;
                    border-bottom: 1px solid #2f2f42;
                    min-height: 22px;
                }
                QTreeWidget::item:selected {
                    background-color: #3a7bd5;
                    color: white;
                }
                QTreeWidget::item:hover {
                    background-color: rgba(58, 123, 213, 0.22);
                }
                QTreeWidget::item:has-children {
                    font-weight: normal;
                }
                QTreeWidget::branch {
                    background: transparent;
                    width: 16px;
                }
                QTreeWidget::branch:has-children:!has-siblings:closed,
                QTreeWidget::branch:closed:has-children:has-siblings {
                    border-image: none;
                    image: url("{_dark_c}");
                }
                QTreeWidget::branch:has-children:!has-siblings:open,
                QTreeWidget::branch:open:has-children:has-siblings {
                    border-image: none;
                    image: url("{_dark_o}");
                }
            """.replace("{_dark_c}", _branch_icon_path(True, True))
                .replace("{_dark_o}", _branch_icon_path(True, False)))
            self.title_label.setStyleSheet("color: #E8E8E8;")
            btn_ss = {
                "add": "#7CE38B", "del": "#FF7B7B", "up": "#7BB8FF",
                "down": "#7BB8FF", "expand": "#FFB74D", "collapse": "#FFB74D",
            }
        else:
            self.tree.setStyleSheet("""
                QTreeWidget {
                    background-color: #FFFFFF;
                    color: #1A1A1A;
                    border: none;
                    outline: 0;
                    font-size: 12px;
                }
                QTreeWidget::item {
                    padding: 4px 6px;
                    border-bottom: 1px solid #f0f0f0;
                    min-height: 22px;
                }
                QTreeWidget::item:selected {
                    background-color: #2f6fed;
                    color: white;
                }
                QTreeWidget::item:hover {
                    background-color: rgba(47, 111, 237, 0.10);
                }
                QTreeWidget::branch {
                    background: transparent;
                    width: 16px;
                }
                QTreeWidget::branch:has-children:!has-siblings:closed,
                QTreeWidget::branch:closed:has-children:has-siblings {
                    border-image: none;
                    image: url("{_light_c}");
                }
                QTreeWidget::branch:has-children:!has-siblings:open,
                QTreeWidget::branch:open:has-children:has-siblings {
                    border-image: none;
                    image: url("{_light_o}");
                }
            """.replace("{_light_c}", _branch_icon_path(False, True))
                .replace("{_light_o}", _branch_icon_path(False, False)))
            self.title_label.setStyleSheet("color: #1A1A1A;")
            btn_ss = {
                "add": "#1E8E3E", "del": "#D92B2B", "up": "#1F6FD0",
                "down": "#1F6FD0", "expand": "#E8590C", "collapse": "#E8590C",
            }
        _btn_bg = "#3a3a4a" if dark else "#f5f5f5"
        _btn_bd = "#555555" if dark else "#cccccc"
        _btn_hbg = "#4a4a5a" if dark else "#e8e8e8"
        _btn_pbg = "#2a2a3a" if dark else "#d8d8d8"
        for _name, _b in (("add", self.add_btn), ("del", self.del_btn),
                          ("up", self.up_btn), ("down", self.down_btn),
                          ("expand", self.expand_btn),
                          ("collapse", self.collapse_btn)):
            _c = btn_ss[_name]
            _b.setStyleSheet(
                f"QPushButton {{ background: {_btn_bg}; color: {_c};"
                f" border: 1px solid {_btn_bd}; border-radius: 3px;"
                f" font-size: 13px; font-weight: bold; }}"
                f" QPushButton:hover {{ background: {_btn_hbg}; }}"
                f" QPushButton:pressed {{ background: {_btn_pbg}; }}")

        # 元素节点按类型重着色（明暗两套配色）
        for iid, node in self._anno_items.items():
            it = self._item_objects.get(iid)
            if it is None:
                continue
            c = _item_kind_color(_item_kind(it), dark)
            if c is not None:
                node.setForeground(0, c)

        # 重新应用当前层高亮
        self._refresh_current_layer_highlight()

    # ============================================================
    #  数据刷新（增量）
    # ============================================================
    def refresh(self, layers: list, items: list, current_layer_id: int) -> None:
        """增量刷新树：图层 + 元素。

        绝不 clear() 重建——否则正在派发 clicked/itemChanged 信号的
        节点会被销毁，导致 Qt 事件循环崩溃。
        拖放事件进行中（_in_drop）则挂起刷新，等 dropFinished 后补刷，
        避免在 dropEvent 派发期间增删节点触发闪退。
        """
        if getattr(self.tree, "_in_drop", False):
            self._pending_refresh = (list(layers), list(items),
                                     current_layer_id)
            return
        self._do_refresh(layers, items, current_layer_id)

    def _on_tree_drop_finished(self) -> None:
        """拖放结束后补刷被挂起的刷新（延后到事件循环再执行）。"""
        if self._pending_refresh is not None:
            args = self._pending_refresh
            self._pending_refresh = None
            QTimer.singleShot(0, lambda: self._do_refresh(*args))

    def _do_refresh(self, layers: list, items: list,
                    current_layer_id: int) -> None:
        """入口：保证 _syncing 无论中途是否异常都复位，避免拖拽同步被永久卡死。"""
        self._syncing = True
        try:
            self._do_refresh_impl(layers, items, current_layer_id)
        finally:
            self._syncing = False

    def _do_refresh_impl(self, layers: list, items: list,
                    current_layer_id: int) -> None:
        self._syncing = True
        self._layers = list(layers)
        self._items = list(items)
        self._item_objects = {it.id: it for it in items}
        self._current_layer_id = current_layer_id

        # 显示顺序：顶层在上 = reversed(layers)
        ordered_layers = list(reversed(layers))
        valid_layer_ids = {l.id for l in ordered_layers}
        valid_item_ids = {it.id for it in items}

        # ---- 1) 移除已不存在的元素节点 ----
        for iid in [x for x in self._anno_items if x not in valid_item_ids]:
            node = self._anno_items.pop(iid)
            if sip.isdeleted(node):
                continue
            parent = node.parent()
            if parent is not None and not sip.isdeleted(parent):
                parent.removeChild(node)
            else:
                idx = self.tree.indexOfTopLevelItem(node)
                if idx >= 0:
                    self.tree.takeTopLevelItem(idx)

        # ---- 2) 移除已不存在的图层节点 ----
        for lid in [x for x in self._layer_items if x not in valid_layer_ids]:
            node = self._layer_items.pop(lid)
            if sip.isdeleted(node):
                continue
            idx = self.tree.indexOfTopLevelItem(node)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)

        # ---- 3) 更新/新增图层节点，并调整顺序 ----
        for idx, layer in enumerate(ordered_layers):
            node = self._layer_items.get(layer.id)
            if node is not None and sip.isdeleted(node):
                node = None
            if node is None:
                node = QTreeWidgetItem([layer.name])
                node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                node.setData(0, Qt.ItemDataRole.UserRole, layer.id)
                node.setData(0, Qt.ItemDataRole.UserRole + 1, _NODE_TYPE_LAYER)
                self.tree.insertTopLevelItem(idx, node)
                self._layer_items[layer.id] = node
            elif self.tree.indexOfTopLevelItem(node) != idx:
                # 行序变化：移动到目标位置
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(node))
                self.tree.insertTopLevelItem(idx, node)

            # 统一图层节点标志：可勾选 + 可选择/可拖放，每次刷新都重新断言，
            # 避免增量 take/insert 后某些节点丢失「显隐复选框」导致显示不一致
            node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable
                          | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            # 更新文字（当前层加 ▶ 标记，始终醒目）
            display = self._layer_display_text(layer)
            if node.text(0) != display:
                node.setText(0, display)
            # 更新复选框状态（强制同步，不依赖上次值）
            want = (Qt.CheckState.Checked if layer.visible
                    else Qt.CheckState.Unchecked)
            node.setCheckState(0, want)

        # ---- 3.5) 兜底：任何游离到顶层的元素节点都不应存在 ----
        for i in reversed(range(self.tree.topLevelItemCount())):
            node = self.tree.topLevelItem(i)
            if sip.isdeleted(node):
                continue
            if self._node_type(node) == _NODE_TYPE_ITEM:
                self.tree.takeTopLevelItem(i)

        # ---- 4) 更新/新增元素节点，放到对应图层下 ----
        # 唯一性保护：同一元素（同 id）绝不重复显示
        items_by_layer = {}
        seen_ids = set()
        for it in items:
            if it.id in seen_ids:
                continue
            seen_ids.add(it.id)
            lid = getattr(it, "layer_id", None)
            if lid is None:
                continue
            items_by_layer.setdefault(lid, []).append(it)

        for lid, layer_node in self._layer_items.items():
            layer_items = items_by_layer.get(lid, [])
            self._sync_layer_children(layer_node, layer_items)

        # ---- 5) 当前层高亮 ----
        self._refresh_current_layer_highlight()

        # ---- 6) 保持选中元素的高亮 ----
        selected_item_id = next((it.id for it in items if it.selected), None)
        if selected_item_id is not None:
            node = self._anno_items.get(selected_item_id)
            if node is not None and self.tree.currentItem() != node:
                self.tree.setCurrentItem(node)
                # 展开其父图层节点
                parent = node.parent()
                if parent is not None and not parent.isExpanded():
                    parent.setExpanded(True)
        elif current_layer_id is not None:
            # 没有元素被选中时，选中当前图层节点
            layer_node = self._layer_items.get(current_layer_id)
            if layer_node is not None and self.tree.currentItem() != layer_node:
                self.tree.setCurrentItem(layer_node)

        self._syncing = False

    def _refresh_current_layer_highlight(self) -> None:
        """刷新当前层的高亮显示（粗体 + 蓝底 + 橙色文字，始终醒目）。"""
        if self._current_layer_id is None:
            return
        for lid, node in list(self._layer_items.items()):
            if sip.isdeleted(node):
                continue
            f = node.font(0)
            if lid == self._current_layer_id:
                f.setBold(True)
                node.setFont(0, f)
                # 当前层背景色高亮
                if self._dark_theme:
                    node.setBackground(0, QBrush(QColor(42, 55, 80)))
                    node.setForeground(0, QColor("#FFC46B"))
                else:
                    node.setBackground(0, QBrush(QColor(220, 235, 255)))
                    node.setForeground(0, QColor("#C2410C"))
            else:
                if f.bold():
                    f.setBold(False)
                    node.setFont(0, f)
                node.setBackground(0, QBrush(QColor(0, 0, 0, 0)))
                node.setForeground(0, QBrush())   # 恢复默认文字色

    def _sync_layer_children(self, layer_node: QTreeWidgetItem, layer_items: list) -> None:
        """增量同步某个图层下的元素子节点（层内按 id 去重，保证唯一显示）。"""
        valid_ids = {it.id for it in layer_items}

        # 移除已不存在的子节点
        to_remove = []
        for i in range(layer_node.childCount()):
            child = layer_node.child(i)
            cid = child.data(0, Qt.ItemDataRole.UserRole)
            if cid not in valid_ids:
                to_remove.append(child)
        for child in to_remove:
            try:
                layer_node.removeChild(child)
            except RuntimeError:
                pass
            cid = child.data(0, Qt.ItemDataRole.UserRole)
            if cid in self._anno_items:
                del self._anno_items[cid]

        # 更新/新增子节点（层内同 id 重复项跳过，确保唯一显示）
        _seen = set()
        for idx, it in enumerate(layer_items):
            if it.id in _seen:
                continue
            _seen.add(it.id)
            # v1.7 需求8：每个图层内的元素从 1 独立排序，互不干扰
            display = f"{idx + 1}. {_describe_item(it)}"
            node = self._anno_items.get(it.id)
            if node is not None and sip.isdeleted(node):
                self._anno_items.pop(it.id, None)
                node = None
            if node is None:
                node = QTreeWidgetItem([display])
                node.setData(0, Qt.ItemDataRole.UserRole, it.id)
                node.setData(0, Qt.ItemDataRole.UserRole + 1, _NODE_TYPE_ITEM)
                # 元素节点按类型着色（红/绿/蓝/橙/黄/紫，明暗主题各有高对比色）
                c = _item_kind_color(_item_kind(it), self._dark_theme)
                if c is not None:
                    node.setForeground(0, c)
                layer_node.insertChild(idx, node)
                self._anno_items[it.id] = node
            elif layer_node.indexOfChild(node) != idx:
                # 顺序变化
                layer_node.removeChild(node)
                layer_node.insertChild(idx, node)
                if node.text(0) != display:
                    node.setText(0, display)
            else:
                # 更新文字（可能文字内容/序号变了）
                if node.text(0) != display:
                    node.setText(0, display)

    # ============================================================
    #  辅助方法
    # ============================================================
    def _node_type(self, item: QTreeWidgetItem) -> str:
        """返回节点类型：'layer' 或 'item'。"""
        return item.data(0, Qt.ItemDataRole.UserRole + 1)

    def _layer_display_text(self, layer) -> str:
        """图层节点显示文本：当前层加 ▶ 前缀（无论是否选中都醒目）。"""
        if self._current_layer_id is not None and layer.id == self._current_layer_id:
            return "▶ " + layer.name
        return layer.name

    def _selected_layer_id(self) -> int | None:
        """获取当前选中的图层 ID（选中元素时返回其所在图层）。"""
        it = self.tree.currentItem()
        if it is None:
            return self._current_layer_id
        ntype = self._node_type(it)
        if ntype == _NODE_TYPE_LAYER:
            return it.data(0, Qt.ItemDataRole.UserRole)
        elif ntype == _NODE_TYPE_ITEM:
            parent = it.parent()
            if parent is not None:
                return parent.data(0, Qt.ItemDataRole.UserRole)
        return self._current_layer_id

    def _current_item_id(self) -> int | None:
        """获取当前选中的元素 ID。"""
        it = self.tree.currentItem()
        if it is None:
            return None
        if self._node_type(it) == _NODE_TYPE_ITEM:
            return it.data(0, Qt.ItemDataRole.UserRole)
        return None

    def _layer_name(self, layer_id: int) -> str:
        for l in self._layers:
            if l.id == layer_id:
                return l.name
        return f"图层{layer_id}"

    # ============================================================
    #  交互：点击 / 双击 / 复选框
    # ============================================================
    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing:
            return
        ntype = self._node_type(item)
        if ntype == _NODE_TYPE_LAYER:
            # 点击图层节点 = 设为当前层
            try:
                self.requestSelect.emit(item.data(0, Qt.ItemDataRole.UserRole))
            except RuntimeError:
                pass
        elif ntype == _NODE_TYPE_ITEM:
            # 点击元素节点 = 在画布中选中
            try:
                self.requestSelectItem.emit(item.data(0, Qt.ItemDataRole.UserRole))
            except RuntimeError:
                pass

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing:
            return
        ntype = self._node_type(item)
        if ntype == _NODE_TYPE_ITEM:
            # 双击元素 = 编辑文字
            try:
                self.requestEditText.emit(item.data(0, Qt.ItemDataRole.UserRole))
            except RuntimeError:
                pass
        # 双击图层节点由 Qt 默认处理展开/折叠

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing:
            return
        ntype = self._node_type(item)
        if ntype == _NODE_TYPE_LAYER:
            try:
                layer_id = item.data(0, Qt.ItemDataRole.UserRole)
                visible = item.checkState(0) == Qt.CheckState.Checked
                self.requestVisible.emit(layer_id, visible)
            except RuntimeError:
                pass

    # ============================================================
    #  拖拽：元素移动到目标图层
    # ============================================================
    def _on_item_moved_to_layer(self, item_id: int, target_layer_id: int) -> None:
        """元素被拖拽到目标图层：发出信号。"""
        if self._syncing:
            return
        self.requestMoveItemToLayer.emit(item_id, target_layer_id)

    # ============================================================
    #  右键菜单
    # ============================================================
    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        # v1.7 需求8：带父控件的 QMenu 不继承应用级样式，需直接套主题 QSS
        from .menu_qss import apply_menu_theme
        apply_menu_theme(menu, self._dark_theme)

        if item is None:
            # v2.x 需求3：空白位置右键 → 新增层 / 折叠层 / 展开层
            # （复制层已移至图层选中后的右键菜单，复制选中层）
            menu.addAction("新增层", self.requestAdd.emit)
            menu.addAction("折叠层", self._collapse_all)
            menu.addAction("展开层", self._expand_all)
            menu.exec(self.tree.mapToGlobal(pos))
            return

        ntype = self._node_type(item)
        if ntype == _NODE_TYPE_LAYER:
            layer_id = item.data(0, Qt.ItemDataRole.UserRole)
            self.tree.setCurrentItem(item)
            menu.addAction("设为当前层",
                           lambda: self.requestSelect.emit(layer_id))
            menu.addAction("重命名…",
                           lambda: self._rename_layer(layer_id))
            menu.addAction("选中本层全部元素",
                           lambda: self.requestSelectLayerItems.emit(layer_id))
            menu.addSeparator()
            menu.addAction("上移一层",
                           lambda: self.requestMove.emit(layer_id, 1))
            menu.addAction("下移一层",
                           lambda: self.requestMove.emit(layer_id, -1))
            # 一步到位：置为顶层 / 置为底层（等价连续上移/下移到底；
            # 已在对应边缘时禁用，避免无意义操作）
            order_ids = [l.id for l in self._layers]  # 底层在前、顶层在末
            act_top = menu.addAction(
                "置为顶层",
                lambda: self._bring_layer_to_edge(layer_id, True))
            act_bottom = menu.addAction(
                "置为底层",
                lambda: self._bring_layer_to_edge(layer_id, False))
            if order_ids:
                act_top.setEnabled(layer_id != order_ids[-1])
                act_bottom.setEnabled(layer_id != order_ids[0])
            # 展开/折叠该图层
            if item.isExpanded():
                menu.addAction("折叠此图层",
                               lambda: item.setExpanded(False))
            else:
                menu.addAction("展开此图层",
                               lambda: item.setExpanded(True))
            menu.addSeparator()
            # v2.x 需求3：复制选中图层（含全部元素，副本插入原图层上方）
            menu.addAction("复制层",
                           lambda: self.requestCopyLayer.emit(layer_id))
            menu.addAction("删除图层",
                           lambda: self.requestDelete.emit(layer_id))

        elif ntype == _NODE_TYPE_ITEM:
            item_id = item.data(0, Qt.ItemDataRole.UserRole)
            self.tree.setCurrentItem(item)
            is_leader = "[引线]" in item.text(0)

            menu.addAction("编辑文字",
                           lambda: self.requestEditText.emit(item_id))
            if is_leader:
                menu.addAction("编辑序号…",
                               lambda: self.requestEditNumber.emit(item_id))
            menu.addSeparator()

            # 「移动到图层」子菜单
            move_menu = menu.addMenu("移动到图层")
            for layer in self._layers:
                # 跳过当前所在图层
                parent = item.parent()
                current_lid = parent.data(0, Qt.ItemDataRole.UserRole) if parent else None
                if layer.id == current_lid:
                    continue
                move_menu.addAction(
                    layer.name,
                    lambda _=False, lid=layer.id, iid=item_id:
                    self.requestMoveItemToLayer.emit(iid, lid)
                )

            menu.addSeparator()
            if is_leader:
                menu.addAction("上移",
                               lambda: self.requestMoveItem.emit(item_id, -1))
                menu.addAction("下移",
                               lambda: self.requestMoveItem.emit(item_id, 1))
                menu.addSeparator()
            menu.addAction("删除",
                           lambda: self.requestDeleteItem.emit(item_id))

        menu.exec(self.tree.mapToGlobal(pos))

    # ============================================================
    #  图层操作
    # ============================================================
    def _delete_current(self) -> None:
        lid = self._selected_layer_id()
        if lid is not None:
            self.requestDelete.emit(lid)

    def _move_current(self, delta: int) -> None:
        lid = self._selected_layer_id()
        if lid is not None:
            self.requestMove.emit(lid, delta)

    def _bring_layer_to_edge(self, layer_id: int, top: bool) -> None:
        """把图层一步移动到最顶层（绘制最上）或最底层（绘制最下）。

        self._layers 与画布叠放顺序一致（底层在前、顶层在末），
        重排后复用 requestReorder 通道提交，效果等价于连续上移/下移到底。
        """
        ids = [l.id for l in self._layers]
        if layer_id not in ids or len(ids) <= 1:
            return
        ids.remove(layer_id)
        if top:
            ids.append(layer_id)       # 列表末尾 = 绘制最顶层
        else:
            ids.insert(0, layer_id)    # 列表开头 = 绘制最底层
        QTimer.singleShot(0, lambda o=ids: self.requestReorder.emit(o))

    def _rename_layer(self, layer_id: int) -> None:
        """重命名图层（不可重名）。"""
        current_name = ""
        for l in self._layers:
            if l.id == layer_id:
                current_name = l.name
                break
        existing_names = {l.name for l in self._layers if l.id != layer_id}

        while True:
            new_name, ok = QInputDialog.getText(
                self, "重命名图层", "图层名称：", text=current_name)
            if not ok:
                return
            new_name = new_name.strip()
            if not new_name:
                continue
            if new_name in existing_names:
                QMessageBox.warning(self, "重名", "图层名称已存在，请换一个！")
                continue
            self.requestRename.emit(layer_id, new_name)
            break

    def _expand_all(self) -> None:
        """展开所有图层节点。"""
        for lid, node in self._layer_items.items():
            node.setExpanded(True)

    def _collapse_all(self) -> None:
        """折叠所有图层节点。"""
        for lid, node in self._layer_items.items():
            node.setExpanded(False)

    # ============================================================
    #  拖拽重排
    # ============================================================
    def _emit_layer_order_from_tree(self) -> None:
        """读取当前树顶层图层顺序，映射为自底向上并发射 requestReorder。

        不读 _syncing 守卫——由调用方决定时机。drop 后直接调用，保证即便
        rowsMoved 时序异常，画布叠放顺序也一定同步。
        """
        ids = []
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            if sip.isdeleted(node):
                continue
            if self._node_type(node) == _NODE_TYPE_LAYER:
                ids.append(node.data(0, Qt.ItemDataRole.UserRole))
        if ids:
            order = list(reversed(ids))
            QTimer.singleShot(0, lambda o=order: self.requestReorder.emit(o))

    def _on_rows_moved(self, *_args) -> None:
        """图层被拖拽移动后：把新顺序映射回 layers 顺序（底层在前）。"""
        if self._syncing:
            return
        self._emit_layer_order_from_tree()
