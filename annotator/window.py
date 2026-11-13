# -*- coding: utf-8 -*-
"""主窗口：顶部工具栏 + 左侧（历史/图层）+ 中央（标尺+画布）+ 右侧样式面板 + 状态栏。"""

from PyQt6.QtCore import QByteArray, QPoint, QPointF, QRectF, QSize, Qt, QTimer
import os
import sys
from PyQt6.QtGui import (QAction, QColor, QFont, QGuiApplication, QIcon,
                         QImage, QImageWriter, QKeySequence, QPalette, QPainter, QPen,
                         QPixmap, QShortcut)
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QDialog, QDockWidget, QFileDialog,
                             QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSplitter, QStyle,
                             QToolBar, QToolButton, QVBoxLayout, QWidget,
                             QSystemTrayIcon)

from . import autosave, settings, screenshot
from .canvas import (MODE_LEADER, MODE_NUMBER, MODE_PEN, MODE_HIGHLIGHT,
                     MODE_MOSAIC, MODE_EMOJI, MODE_SELECT, MODE_SHAPE,
                     MODE_TEXT, AnnotationCanvas)
from .items import LeaderLineItem
from .layer_tree_panel import LayerTreePanel
from .panel import StylePanel
from .rulers import RulerBar

IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*.*)"

# v1.7 需求7：导出支持的多格式（QImageWriter 插件全部内置）
EXPORT_FORMATS = ("PNG", "JPG", "GIF", "BMP", "TIF", "TIFF")
EXPORT_FORMAT_MENU = [
    ("PNG", "导出 PNG…"), ("JPG", "导出 JPG…"), ("GIF", "导出 GIF…"),
    ("BMP", "导出 BMP…"), ("TIF", "导出 TIF…"), ("TIFF", "导出 TIFF…")]


def pil_to_qpixmap(img) -> QPixmap:
    """Pillow Image -> QPixmap。"""
    from PIL import Image
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


TOOL_BTN_SIZE = 38   # 模式工具按钮正方形边长（保证选中后内容完整显示）


def _resource_path(name: str) -> str:
    """返回随程序分发的资源文件（1.ico / 2.ico）的绝对路径。

    打包成 exe 后，PyInstaller 把 datas 里的文件解压到 sys._MEIPASS
    （onefile 运行时临时解压目录），源码运行时则位于项目根目录。
    本函数统一解析，绝不依赖进程当前工作目录。
    """
    import sys
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

class MainWindow(QMainWindow):
    def __init__(self, parent=None, restore: bool = True):
        super().__init__(parent)
        # 设置窗口/任务栏图标：统一使用 1.ico（嵌入 exe 资源），缺失时回退 2.ico
        icon_path = _resource_path("1.ico")
        if not os.path.exists(icon_path):
            icon_path = _resource_path("2.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle("图片快速标注工具 v2.0")
        self.resize(1400, 820)
        # 需求9：记住最近一次打开/保存的目录（持久化到 settings.json）
        self._last_open_dir = ""
        self._last_save_dir = ""

        # ---- 中央区：左面板(历史+图层) + 标尺画布 + 右侧样式面板 ----
        self.canvas = AnnotationCanvas()
        self.panel = StylePanel()
        self.panel.attach(self.canvas)
        self.canvas.set_style_provider(self.panel.current_style)
        self.layer_tree = LayerTreePanel()

        # 左侧面板容器：图层结构树
        self.left_box = QWidget()
        self.left_box.setMinimumWidth(180)
        lv = QVBoxLayout(self.left_box)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self.layer_tree)

        # 中间：标尺 + 画布
        self.center_box = QWidget()
        grid = QGridLayout(self.center_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        corner = QLabel("")
        corner.setFixedSize(24, 24)
        corner.setStyleSheet("background:#F8F9FA; border:1px solid #D0D3D6;")
        self.h_ruler = RulerBar("h")
        self.v_ruler = RulerBar("v")
        self.h_ruler.attach(self.canvas)
        self.v_ruler.attach(self.canvas)
        grid.addWidget(corner, 0, 0)
        grid.addWidget(self.h_ruler, 0, 1)
        grid.addWidget(self.v_ruler, 1, 0)
        grid.addWidget(self.canvas, 1, 1)

        # 右侧面板容器（可折叠 + 可滚动：主界面高度任意调整，面板内容不溢出）
        self.right_box = QWidget()
        # 需求1：右侧面板最小宽度修正为 180（原 360 过宽、无法拖窄），
        # splitter 默认宽度见下方 setSizes（260）。
        self.right_box.setMinimumWidth(180)
        # 右键菜单：显示/隐藏主工具栏
        self.right_box.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.right_box.customContextMenuRequested.connect(self._show_right_panel_menu)
        rv = QVBoxLayout(self.right_box)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(2)
        # 顶部固定按钮：折叠/展开右侧全部功能组（放在滚动区外，始终可见）
        self.collapse_all_btn = QPushButton("▲ 折叠全部")
        self.collapse_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_all_btn.setToolTip("折叠右侧全部功能面板")
        self.collapse_all_btn.setFixedHeight(30)
        self.collapse_all_btn.setObjectName("collapseAllBtn")
        self.collapse_all_btn.clicked.connect(self._toggle_right_panel_all)
        self._apply_collapse_btn_theme()
        rv.addWidget(self.collapse_all_btn)
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel_scroll.setWidget(self.panel)
        # 需求1：右侧面板纵向滑块条宽度加倍（系统默认约 17px → 34px），更易拖动
        self.panel_scrollbar_w = 34
        rv.addWidget(self.panel_scroll, 1)
        # 启动先给一套浅色样式，主题切换时由 _apply_panel_scrollbar_theme 覆盖
        self._apply_panel_scrollbar_theme(False)

        # 面板常显，不使用浮动按钮折叠功能（用户反馈浮动按钮交互有问题）

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_box)
        self.splitter.addWidget(self.center_box)
        self.splitter.addWidget(self.right_box)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        # 需求1：splitter 右侧面板默认宽度 260（原 520 过宽）
        self.splitter.setSizes([240, 900, 260])
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(2, True)
        # v2.0 需求4：加宽分隔条，便于拖拽调整面板宽度（避免与参数滑动混淆）
        self.splitter.setHandleWidth(6)
        # 光标只设在分隔条 handle 上；若设在整个 splitter 上，会传播到右侧面板
        # 全部子控件，导致面板内也显示左右调整箭头。
        for i in range(1, self.splitter.count()):
            self.splitter.handle(i).setCursor(Qt.CursorShape.SplitHCursor)

        # 左侧面板状态
        self._left_panel_expanded = True
        self._left_panel_width = 240  # 用户设置的展开宽度，保存到配置

        # 左侧浮动按钮（只加左侧，右侧不加）
        self.left_floating = QToolButton()
        self.left_floating.setCursor(Qt.CursorShape.PointingHandCursor)
        self.left_floating.setToolTip("显示 / 隐藏左侧面板")
        _FLOAT_SS = ("QToolButton { background: rgba(110,120,132,0.55); color: #fff;"
                     " border: none; border-radius: 8px; }"
                     " QToolButton:hover { background: rgba(56,118,214,0.85); }")
        self.left_floating.setStyleSheet(_FLOAT_SS)
        _lf = QFont(); _lf.setPixelSize(11); self.left_floating.setFont(_lf)

        self.central = QWidget()
        lay = QHBoxLayout(self.central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.splitter, 1)
        self.setCentralWidget(self.central)
        # 浮动按钮挂在 central 上
        self.left_floating.setParent(self.central)
        self.left_floating.clicked.connect(self._toggle_left_panel)
        self.splitter.splitterMoved.connect(lambda *_: self._update_left_floating_pos())
        QTimer.singleShot(0, self._update_left_floating_pos)
        QTimer.singleShot(0, self._sync_left_floating_icon)

        self._last_export_fmt = "PNG"   # Ctrl+S 直接导出使用的格式（记忆上次选择）

        # ---- 自动保存（去抖 600ms）----
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(600)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._autosave_lbl = QLabel(" 自动保存：-")

        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        self._update_action_states()
        self._refresh_layer_tree()
        # 恢复上次界面/样式参数（show 后应用，保证几何/分栏生效）
        QTimer.singleShot(0, self._restore_settings)
        if restore:
            self._check_restore()

    # ================= 界面参数持久化（settings.json） =================
    @staticmethod
    def _color_hex(c) -> str:
        """QColor -> #AARRGGBB（Qt 8 位 hex 为 ARGB 顺序；写成 RGBA 恢复时会错乱）。"""
        if isinstance(c, QColor):
            return f"#{c.alpha():02X}{c.red():02X}{c.green():02X}{c.blue():02X}"
        return c

    def _deep_color_hex(self, obj):
        """递归把 dict/list/tuple 中所有 QColor 转 #AARRGGBB（v1.7 加固）。

        此前只转换顶层 QColor，若样式/数据里嵌套了 QColor，json.dumps 抛
        TypeError，image.png 已写入而 project.json 缺失 → 文件无法再打开。
        """
        if isinstance(obj, QColor):
            return self._color_hex(obj)
        if isinstance(obj, dict):
            return {k: self._deep_color_hex(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._deep_color_hex(v) for v in obj]
        return obj

    def _collect_settings(self) -> dict:
        st = dict(self.panel.current_style())
        for k in ("line_color", "text_color", "bg_fill_color", "bg_border_color",
                  "shape_border_color", "shape_fill_color", "pen_color", "hl_color"):
            if k in st:
                st[k] = self._color_hex(st[k])
        st["jpg_quality"] = self.panel.jpg_quality_spin.value()
        st["bg_index"] = self.panel.bg_combo.currentIndex()
        st["bg_auto_follow"] = bool(getattr(self.panel, "_bg_auto_follow", True))
        st["bg_custom_color"] = QColor(getattr(self.panel, "_bg_custom_color",
                                              "#808080")).name()
        st["last_open_dir"] = self._last_open_dir   # 需求9
        st["last_save_dir"] = self._last_save_dir
        st["number_enabled"] = self.panel.number_check.isChecked()
        st["number_format"] = self.panel.current_number_format()
        st["snap_mode"] = self.panel.current_snap_mode()
        # 工具面板嵌入分栏时，主窗口/分栏是 4 列临时结构；持久化统一保存
        # 未嵌入时的「干净」状态（3 列），恢复时再按 tool_place 重新嵌入，
        # 避免 restoreState/restoreState 因控件数量不匹配而失效。
        embedded_tool = getattr(self, "_tool_place", "") in (
            "inner-left", "inner-right")
        if embedded_tool and self._clean_main_state:
            main_state = self._clean_main_state
            splitter_state = self._clean_splitter_state
        else:
            main_state = bytes(self.saveState().toBase64()).decode()
            splitter_state = bytes(self.splitter.saveState().toBase64()).decode()
        return {
            "window_geometry": bytes(self.saveGeometry().toBase64()).decode(),
            "main_state": main_state,
            "splitter_state": splitter_state,
            "tool_place": getattr(self, "_tool_place", "dock-left"),
            "left_panel_expanded": self._left_panel_expanded,
            "left_panel_width": self._left_panel_width,
            "theme_dark": bool(self._dark_theme),
            "group_expanded": self.panel.group_states(),
            "style": st,
            "mode": self.canvas.mode,
            "last_export_fmt": self._last_export_fmt,
        }

    def _restore_settings(self) -> None:
        data = settings.load()
        if not data:
            # 首次启动：按默认（明亮）主题自动套用画布背景（需求5）
            self.panel.apply_theme_follow_bg(self._dark_theme)
            return
        geo = data.get("window_geometry")
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
        ms = data.get("main_state")
        if ms:
            self.restoreState(QByteArray.fromBase64(ms.encode("ascii")))
        ss = data.get("splitter_state")
        if ss:
            self.splitter.restoreState(QByteArray.fromBase64(ss.encode("ascii")))
        # v2.1：恢复工具面板摆放位置（嵌入分栏必须在分栏状态恢复后进行）
        tool_place = data.get("tool_place", "dock-left")
        QTimer.singleShot(0, lambda p=tool_place: self._restore_tool_place(p))
        # 恢复左侧面板展开/收起状态和宽度
        self._left_panel_expanded = bool(data.get("left_panel_expanded", True))
        self._left_panel_width = int(data.get("left_panel_width", 240))
        if not self._left_panel_expanded:
            self.left_box.setMaximumWidth(0)
            self.left_box.setMinimumWidth(0)
        QTimer.singleShot(0, self._update_left_floating_pos)
        QTimer.singleShot(0, self._sync_left_floating_icon)
        st = data.get("style") or {}
        self.panel.set_style(st)
        self.panel._sync_canvas_state()
        self.panel.set_group_states(data.get("group_expanded") or {})
        self._sync_collapse_all_btn()
        if bool(data.get("theme_dark", False)):
            self._dark_theme = True
            self.theme_btn.setText("☀️")
            self._apply_dark_theme()
        mode = data.get("mode", MODE_LEADER)
        if mode in self.mode_btn_styles and mode != "screenshot":
            # 启动恢复只还原模式与按钮高亮，不触发“无图片”提示；
            # 该提示仅在用户主动点选工具且确实无图时才弹出。
            self.canvas.set_mode(mode)
            self._apply_mode_button_styles(mode)
        self._last_export_fmt = data.get("last_export_fmt", "PNG")
        # 需求9：恢复最近打开/保存目录
        self._last_open_dir = data.get("last_open_dir", "") or ""
        self._last_save_dir = data.get("last_save_dir", "") or ""
        # 需求5：启动时按当前主题自动套用画布背景（明亮→浅灰 / 暗黑→深灰），
        # 仅在用户从未手动改过背景时生效（_bg_auto_follow）
        self.panel.apply_theme_follow_bg(self._dark_theme)
        self._update_action_states()

    def _persist_settings(self) -> None:
        """统一持久化全部界面/样式设置（关窗到托盘、退出时调用）。"""
        try:
            settings.save(self._collect_settings())
        except Exception:
            pass

    # ================= 工具栏 =================
    MODE_BTN_SS_CHECKED = (
        "QPushButton { background-color: #2f6fed; color: white;"
        " border: 2px solid #bcd6ff; border-radius: 5px;"
        " padding: 0px; margin: 0px; }"
        "QPushButton:hover { background-color: #3d7bf0; }")
    MODE_BTN_SS_NORMAL = (
        "QPushButton { border: 2px solid transparent; padding: 0px;"
        " margin: 0px; border-radius: 5px; background: transparent; }"
        "QPushButton:hover { background-color: rgba(47,111,237,0.18); }")

    def _export_icon(self) -> QIcon:
        """导出图标：向下箭头落入托盘（与「保存项目」的软盘图标区分，需求7）。"""
        pm = QPixmap(24, 24)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#3A7BD5"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(2.0, 14.0, 20.0, 6.0), 2.0, 2.0)   # 托盘
        p.drawLine(QPointF(12.0, 2.0), QPointF(12.0, 14.0))          # 杆
        p.drawLine(QPointF(6.5, 9.0), QPointF(12.0, 15.0))           # 左箭头
        p.drawLine(QPointF(17.5, 9.0), QPointF(12.0, 15.0))          # 右箭头
        p.end()
        return QIcon(pm)

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setObjectName("main_toolbar")   # saveState/restoreState 依赖 objectName
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))   # 主工具栏图标统一尺寸，完整显示
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(tb)
        # addToolBar 后主窗口可能重置按钮样式，这里再次显式设置
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        st = self.style()

        self.act_new = QAction("新建空白图片", self)
        self.act_new.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.act_new.setToolTip("新建指定尺寸与背景色的空白图片（Ctrl+N）")
        self.act_new.setShortcut(QKeySequence("Ctrl+N"))
        tb.addAction(self.act_new)

        # v1.7 需求7 顺序：打开项目 -> 打开图片 -> 导入剪贴板 -> 保存项目
        self.act_open_proj = QAction("打开项目", self)
        self.act_open_proj.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.act_open_proj.setToolTip("打开项目文件继续编辑（Ctrl+Shift+O）")
        self.act_open_proj.setShortcut(QKeySequence("Ctrl+Shift+O"))
        tb.addAction(self.act_open_proj)

        self.act_open = QAction("打开本地图片", self)
        self.act_open.setToolTip("打开本地图片（Ctrl+O）")
        self.act_open.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        tb.addAction(self.act_open)

        self.act_paste = QAction("导入剪贴板", self)
        self.act_paste.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.act_paste.setToolTip("读取系统剪贴板图片并加载到画布（最常用入口，Ctrl+V）")
        self.act_paste.setShortcut(QKeySequence("Ctrl+V"))
        tb.addAction(self.act_paste)

        self.act_save_proj = QAction("保存项目", self)
        self.act_save_proj.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.act_save_proj.setToolTip("保存可继续编辑的项目文件（图片+标注+图层，Ctrl+Shift+S）")
        self.act_save_proj.setShortcut(QKeySequence("Ctrl+Shift+S"))
        tb.addAction(self.act_save_proj)

        tb.addSeparator()

        # 模式切换按钮：放到浮动工具面板中（可拖动、可停靠任意位置）
        self.mode_btn_styles = {
            MODE_SELECT: "👆", MODE_LEADER: "↗️", MODE_NUMBER: "🔢",
            MODE_TEXT: "🔤", MODE_SHAPE: "🔺", MODE_PEN: "✏️",
            MODE_HIGHLIGHT: "🖍️", MODE_MOSAIC: "🧱", MODE_EMOJI: "😀", "screenshot": "✂️"}
        self.mode_btn_tooltips = {
            MODE_SELECT: "选择模式：点击选中/拖动移动标注 (V)；右键弹出快捷菜单",
            MODE_LEADER: "引线标注：点击目标点+文字位置，输入文字 (L)",
            MODE_NUMBER: "引线序号：自动生成序号标注 (N)",
            MODE_TEXT: "文本批注：直接点击位置输入文字 (T)",
            MODE_SHAPE: "形状工具：矩形/椭圆/三角形等 (R)",
            MODE_PEN: "画笔工具：自由手绘线条 (P)",
            MODE_HIGHLIGHT: "荧光笔：半透明高亮涂抹",
            MODE_MOSAIC: "马赛克：对图片区域像素化打码",
            MODE_EMOJI: "表情：在图片上点击放置表情",
            "screenshot": "自由截图：框选屏幕区域（Ctrl+Q，可在截图设置自定义）"}
        self.mode_buttons: dict = {}
        # 创建浮动工具面板
        self.tool_dock = QDockWidget("工具面板", self)
        self.tool_dock.setObjectName("tool_dock")   # saveState/restoreState 依赖 objectName
        self.tool_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.tool_widget = QWidget()
        self.tool_layout = QVBoxLayout(self.tool_widget)  # 初始竖向（停靠左侧）
        self.tool_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_layout.setSpacing(0)
        # 创建浮动按钮
        self.float_btn = QPushButton("⧉")
        self.float_btn.setFixedHeight(TOOL_BTN_SIZE)
        self.float_btn.setFixedWidth(TOOL_BTN_SIZE)
        self.float_btn.setToolTip("浮动面板（右键选择停靠/嵌入位置）")
        _ff = QFont(); _ff.setPixelSize(17); self.float_btn.setFont(_ff)
        self.float_btn.clicked.connect(self._on_float_btn_clicked)
        # 工具面板右键菜单：浮动 / 四边停靠 / 嵌入左右分栏独立列
        self.tool_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.tool_widget.customContextMenuRequested.connect(
            self._show_tool_place_menu)
        # 先加到布局里
        self.tool_layout.addWidget(self.float_btn)

        # 创建按钮
        self.mode_buttons_list = []
        for mode, symbol in self.mode_btn_styles.items():
            btn = QPushButton(symbol)
            is_shot = (mode == "screenshot")
            btn.setCheckable(not is_shot)   # 截图是即时动作，不是画布模式
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            _bf = QFont(); _bf.setPixelSize(17); btn.setFont(_bf)
            btn.setFixedHeight(TOOL_BTN_SIZE)
            btn.setFixedWidth(TOOL_BTN_SIZE)
            btn.setToolTip(self.mode_btn_tooltips.get(mode, ""))
            if is_shot:
                btn.clicked.connect(lambda _=False: self.start_screenshot())
            else:
                btn.clicked.connect(lambda _=False, m=mode: self._switch_mode(m))
            self.tool_layout.addWidget(btn)
            self.mode_buttons[mode] = btn
            self.mode_buttons_list.append(btn)
        # 加弹簧，让按钮紧凑向上对齐，剩下的空间留空
        self.tool_layout.addStretch(1)
        self.tool_dock.setWidget(self.tool_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tool_dock)
        # 监听 dock 位置变化，自动调整布局方向
        self.tool_dock.dockLocationChanged.connect(self._on_tool_dock_location_changed)
        self.tool_dock.topLevelChanged.connect(self._on_tool_dock_floating_changed)
        # 初始：停靠在左侧，竖向排列（初始就是 QVBoxLayout）
        self._apply_mode_button_styles(MODE_LEADER)
        # 初始设置：停靠时只保留可拖动，隐藏关闭和浮动按钮
        from PyQt6.QtWidgets import QDockWidget as _QD
        self.tool_dock.setFeatures(_QD.DockWidgetFeature.DockWidgetMovable)
        # 初始锁死宽度（竖排）
        self.tool_dock.setFixedWidth(TOOL_BTN_SIZE)
        # v2.1 工具面板摆放状态：
        #   dock-left/dock-right/top/bottom = QDockWidget 停靠；
        #   float = 浮动窗口；
        #   inner-left/inner-right = 嵌入水平分栏，作为独立竖列
        #   （分别位于左面板右侧、右面板左侧）。
        self._tool_place = "dock-left"
        self._tool_drag_active = False      # 浮动面板是否正被鼠标拖动
        self._tool_drag_start_pos = None    # 拖动起点（用于区分点击与拖动）
        # 未嵌入分栏时的干净布局状态（嵌入后 splitter/main 多出一列，
        # 持久化时统一保存干净状态，避免下次恢复时数量不匹配）
        self._clean_main_state = ""
        self._clean_splitter_state = ""
        # 浮动拖动时轮询鼠标：松开瞬间若位于左右分栏缝隙则自动嵌入
        self._tool_float_timer = QTimer(self)
        self._tool_float_timer.setInterval(80)
        self._tool_float_timer.timeout.connect(self._check_float_tool_dropzone)
        # 记录初始的干净布局状态（此时工具面板仍在 Dock 中、分栏为 3 列）
        self._clean_main_state = bytes(self.saveState().toBase64()).decode()
        self._clean_splitter_state = bytes(
            self.splitter.saveState().toBase64()).decode()
        # 窗口显示后再更新一次布局方向和尺寸
        QTimer.singleShot(100, self._update_tool_layout_orientation)

        tb.addSeparator()

        # v1.7 需求7：导出图片（下拉选格式，图标与保存项目软盘区分）
        self.export_btn = QToolButton()
        self.export_btn.setIcon(self._export_icon())
        self.export_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.export_btn.setToolTip("导出图片（PNG/JPG/GIF/BMP/TIF/TIFF；Ctrl+S 按上次格式直接导出）")
        self.export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.export_btn)
        for fmt, label in EXPORT_FORMAT_MENU:
            menu.addAction(label, lambda _=False, f=fmt: self.export_image(f, ask_save=True))
        self.export_btn.setMenu(menu)
        tb.addWidget(self.export_btn)

        # 复制全部到剪贴板
        self.act_copy = QAction("复制全部到剪贴板", self)
        self.act_copy.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.act_copy.setShortcut(QKeySequence("Ctrl+C"))
        self.act_copy.setToolTip("把「图片+全部标注」渲染图复制到剪贴板，可直接粘贴使用")
        tb.addAction(self.act_copy)

        # 撤销 / 重做 / 删除选中 / 删除全部
        # v2.0：撤销/重做改用 Windows 风格弯箭头符号（↶/↷），保持 QAction 承担快捷键与启用态
        self.act_undo = QAction("撤销", self)
        self.act_undo.setToolTip("撤销（Ctrl+Z）")
        self.act_undo.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.act_redo = QAction("重做", self)
        self.act_redo.setToolTip("重做（Ctrl+Y）")
        self.act_redo.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.act_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self.act_delete = QAction("删除选中", self)
        self.act_delete.setToolTip("删除选中（Delete）")
        self.act_delete.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.act_delete.setShortcut("Delete")
        self.act_clear = QAction("删除全部", self)
        self.act_clear.setToolTip("删除全部标注（清空画布）")
        self.act_clear.setIcon(st.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        # 工具栏上的符号化按钮（与 100%/对齐一致，随主题配色）
        self.undo_btn = QPushButton("↶")
        self.undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_btn.setFixedHeight(28)
        self.undo_btn.setFixedWidth(32)
        _uf = QFont("Segoe UI Symbol"); _uf.setPixelSize(15); self.undo_btn.setFont(_uf)
        self.undo_btn.setToolTip("撤销（Ctrl+Z）")
        self.undo_btn.clicked.connect(self.act_undo.trigger)
        self.redo_btn = QPushButton("↷")
        self.redo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.redo_btn.setFixedHeight(28)
        self.redo_btn.setFixedWidth(32)
        self.redo_btn.setFont(_uf)
        self.redo_btn.setToolTip("重做（Ctrl+Y）")
        self.redo_btn.clicked.connect(self.act_redo.trigger)
        tb.addWidget(self.undo_btn)
        tb.addWidget(self.redo_btn)
        tb.addAction(self.act_delete)
        tb.addAction(self.act_clear)

        # Ctrl+S 直接导出：隐藏动作只保留快捷键（v1.7 取消独立导出按钮）
        self.act_save = QAction("导出图片 (Ctrl+S)", self)
        self.act_save.setToolTip("导出图片（Ctrl+S）")
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))

        tb.addSeparator()

        # 100% 按钮：按原始分辨率显示（scale=1），符号化显示
        self.zoom_100_btn = QPushButton("⛶")
        self.zoom_100_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_100_btn.setFixedHeight(28)
        self.zoom_100_btn.setFixedWidth(32)
        _zf = QFont("Segoe UI Symbol"); _zf.setPixelSize(14); self.zoom_100_btn.setFont(_zf)
        self.zoom_100_btn.setToolTip("百分百显示：按原始分辨率 1:1 展示")
        self.zoom_100_btn.clicked.connect(lambda: self.canvas.actual_size())
        tb.addWidget(self.zoom_100_btn)

        # 对齐：一键自动布局（最小移动原则，保持图片外部对齐），符号化显示
        self.align_btn = QPushButton("⊞")
        self.align_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.align_btn.setFixedHeight(28)
        self.align_btn.setFixedWidth(32)
        self.align_btn.setFont(_zf)
        self.align_btn.setToolTip("一键对齐/自动布局：引线标注自动左/中/右、上/下对齐")
        self.align_btn.clicked.connect(lambda: self.canvas.auto_layout())
        tb.addWidget(self.align_btn)

        # 主题切换按钮：明/暗主题
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCheckable(True)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setFixedHeight(28)
        self.theme_btn.setFixedWidth(32)
        self.theme_btn.setToolTip("切换明/暗主题")
        self.theme_btn.clicked.connect(self._toggle_theme)
        tb.addWidget(self.theme_btn)

        # v1.7 需求7：关于、退出右对齐（弹性弹簧推到行末，关于在最右）
        self._tb_spacer = QWidget()
        self._tb_spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Preferred)
        tb.addWidget(self._tb_spacer)

        self.about_btn = QPushButton("关于")
        self.about_btn.setToolTip("版本信息、作者与版权、功能说明")
        self.about_btn.setFixedSize(52, 26)
        _af = QFont(); _af.setPixelSize(12)
        self.about_btn.setFont(_af)
        self.about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.about_btn.setStyleSheet(
            "QPushButton { background-color: #2F8F4E; color: #FFFFFF;"
            " border: 1px solid #257A41; border-radius: 4px; padding: 0px; }"
            "QPushButton:hover { background-color: #3BA75F; border-color: #2F8F4E; }"
            "QPushButton:pressed { background-color: #257A41; }")
        self.about_btn.clicked.connect(self._show_about)
        tb.addWidget(self.about_btn)

        self.quit_btn = QPushButton("退出")
        self.quit_btn.setToolTip("保存参数配置并完全退出程序")
        self.quit_btn.setFixedSize(52, 26)
        _qf = QFont(); _qf.setBold(True); _qf.setPixelSize(13)
        self.quit_btn.setFont(_qf)
        self.quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 红底白字按钮（自带完整 QSS，不依赖全局明/暗主题）
        self.quit_btn.setStyleSheet(
            "QPushButton { background-color: #E0464B; color: #FFFFFF;"
            " border: 1px solid #C7333A; border-radius: 4px; padding: 0px; }"
            "QPushButton:hover { background-color: #F05A60; border-color: #E0464B; }"
            "QPushButton:pressed { background-color: #C7333A; }")
        self.quit_btn.clicked.connect(self._quit_app)
        tb.addWidget(self.quit_btn)

        self.toolbar = tb
        self._dark_theme = False



    MODE_GROUP = {MODE_LEADER: "leader", MODE_NUMBER: "leader",
                  MODE_TEXT: "text", MODE_SHAPE: "shape", MODE_PEN: "pen",
                  MODE_HIGHLIGHT: "highlight", MODE_MOSAIC: "mosaic",
                  MODE_EMOJI: "emoji"}
    GROUP_MODE = {"leader": MODE_LEADER, "text": MODE_TEXT,
                  "shape": MODE_SHAPE, "pen": MODE_PEN,
                  "highlight": MODE_HIGHLIGHT, "mosaic": MODE_MOSAIC,
                  "emoji": MODE_EMOJI}

    # QDockWidget 停靠区 -> 内部摆放状态名
    _TOOL_AREA_PLACE = {
        Qt.DockWidgetArea.TopDockWidgetArea: "top",
        Qt.DockWidgetArea.BottomDockWidgetArea: "bottom",
        Qt.DockWidgetArea.LeftDockWidgetArea: "dock-left",
        Qt.DockWidgetArea.RightDockWidgetArea: "dock-right",
    }
    _TOOL_PLACE_AREA = {
        "top": Qt.DockWidgetArea.TopDockWidgetArea,
        "bottom": Qt.DockWidgetArea.BottomDockWidgetArea,
        "dock-left": Qt.DockWidgetArea.LeftDockWidgetArea,
        "dock-right": Qt.DockWidgetArea.RightDockWidgetArea,
    }
    _QW_MAX = 16777215  # QWIDGETSIZE_MAX：放开 min/max 锁定时用

    def _on_tool_dock_location_changed(self, area):
        """工具面板停靠位置变化时，同步摆放状态并调整布局方向。"""
        if (area in self._TOOL_AREA_PLACE
                and self._tool_place not in ("inner-left", "inner-right")):
            # 用户直接把 Dock 拖到了另一个停靠区
            self._tool_place = self._TOOL_AREA_PLACE[area]
        self._update_tool_layout_orientation()

    def _update_tool_layout_orientation(self):
        """根据停靠位置/浮动/嵌入状态，调整工具面板按钮排列方向。
        停靠左右两侧 / 嵌入分栏：竖向排列（一列）
        停靠上下两侧 / 浮动：横向排列（一行）
        """
        try:
            self._do_update_tool_layout_orientation()
        except Exception as e:
            print(f"Layout orientation update error: {e}")

    def _do_update_tool_layout_orientation(self):
        embedded = self._tool_place in ("inner-left", "inner-right")
        # 判断方向：
        # 嵌入分栏 → 单列竖排；浮动 → 单行横排；
        # 上下停靠 → 单行横排；左右停靠 → 单列竖排
        if embedded:
            horizontal = False
        elif self.tool_dock.isFloating():
            horizontal = True  # 浮动时始终横排
        else:
            area = self.dockWidgetArea(self.tool_dock)
            horizontal = area in (Qt.DockWidgetArea.TopDockWidgetArea,
                                  Qt.DockWidgetArea.BottomDockWidgetArea)

        # 获取旧布局
        old_layout = self.tool_widget.layout()
        if old_layout is None:
            return

        # 先执行标题栏和浮动按钮的逻辑，不管方向变没变
        from PyQt6.QtWidgets import QDockWidget as _QD
        if embedded:
            # 嵌入分栏：Dock 隐藏在布局外；显示 ⧉ 用于一键弹出浮动
            self.float_btn.show()
            self.float_btn.setToolTip("弹出为浮动窗口（右键选择停靠/嵌入位置）")
        elif self.tool_dock.isFloating():
            # 浮动：显示标题栏，隐藏浮动按钮
            self.tool_dock.setTitleBarWidget(None)
            self.tool_dock.setFeatures(_QD.DockWidgetFeature.DockWidgetClosable |
                                      _QD.DockWidgetFeature.DockWidgetMovable |
                                      _QD.DockWidgetFeature.DockWidgetFloatable)
            self.float_btn.hide()
        else:
            area = self.dockWidgetArea(self.tool_dock)
            if area in (Qt.DockWidgetArea.TopDockWidgetArea,
                        Qt.DockWidgetArea.BottomDockWidgetArea):
                # 上下停靠：隐藏标题栏，显示浮动按钮
                empty_widget = QWidget()
                empty_widget.setFixedHeight(0)
                self.tool_dock.setTitleBarWidget(empty_widget)
                self.tool_dock.setFeatures(_QD.DockWidgetFeature.NoDockWidgetFeatures)
                self.float_btn.show()
            else:
                # 左右停靠：显示标题栏，隐藏浮动按钮
                self.tool_dock.setTitleBarWidget(None)
                self.tool_dock.setFeatures(_QD.DockWidgetFeature.DockWidgetMovable)
                self.float_btn.hide()

        # 方向变化时用 setDirection() 原地切换（禁止删除重建 layout，曾因此崩溃）
        current_dir = old_layout.direction()
        current_is_h = current_dir in (QBoxLayout.Direction.LeftToRight,
                                       QBoxLayout.Direction.RightToLeft)
        if isinstance(old_layout, QBoxLayout) and current_is_h != horizontal:
            if horizontal:
                old_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            else:
                old_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            # 清除旧的 item
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    old_layout.removeWidget(item.widget())
            # 先加浮动按钮
            old_layout.addWidget(self.float_btn)
            # 再加所有按钮
            for btn in self.mode_buttons_list:
                old_layout.addWidget(btn)
            # 加弹簧，把按钮推到一边，剩下的空间留空
            old_layout.addStretch(1)

        # 尺寸锁定（每次都按当前状态重算——竖排↔竖排之间切换，
        # 例如左侧停靠→嵌入分栏，方向不变但尺寸约束不同）
        n = len(self.mode_buttons_list)
        btn_size = TOOL_BTN_SIZE  # 每个按钮正方形边长

        # 先放开 tool_widget 自身的历史锁定（嵌入时锁它，停靠时锁 Dock）
        self.tool_widget.setMinimumWidth(0)
        self.tool_widget.setMaximumWidth(self._QW_MAX)
        self.tool_widget.setMinimumHeight(0)
        self.tool_widget.setMaximumHeight(self._QW_MAX)

        if embedded:
            # 嵌入分栏独立竖列：宽度锁 38，高度随分栏自由拉伸
            self.tool_widget.setFixedWidth(btn_size)
            # Dock 不在布局中，放开其历史锁定，避免回切时残留
            self.tool_dock.setMinimumWidth(0)
            self.tool_dock.setMaximumWidth(self._QW_MAX)
            self.tool_dock.setMinimumHeight(0)
            self.tool_dock.setMaximumHeight(self._QW_MAX)
            self.tool_widget.show()
            return

        if horizontal:
            # 横排：Dock 高度锁死为最小，宽度自适应内容
            self.tool_dock.setFixedHeight(btn_size)
            self.tool_dock.setMinimumWidth(n * btn_size)
            self.tool_dock.setMaximumWidth(n * btn_size)
            self.tool_dock.setMaximumHeight(btn_size)
        else:
            # 竖排：Dock 宽度锁死为最小，高度自适应内容
            self.tool_dock.setFixedWidth(btn_size)
            self.tool_dock.setMinimumHeight(n * btn_size)
            self.tool_dock.setMaximumHeight(n * btn_size)
            self.tool_dock.setMaximumWidth(btn_size)

        # 浮动时额外调整窗口大小
        if self.tool_dock.isFloating():
            if horizontal:
                self.tool_dock.resize(n * btn_size, btn_size + 30)
            else:
                self.tool_dock.resize(btn_size, n * btn_size + 30)

    # ---------------- 工具面板：停靠 / 浮动 / 嵌入分栏独立列 ----------------
    def _on_float_btn_clicked(self):
        """⧉ 按钮：嵌入分栏时一键弹出为浮动窗口；其余状态直接浮动。"""
        if self._tool_place in ("inner-left", "inner-right"):
            self._place_tool("float")
        else:
            self.tool_dock.setFloating(True)

    def _show_tool_place_menu(self, pos):
        """工具面板右键菜单：选择浮动/四边停靠/嵌入左右分栏独立列。"""
        menu = QMenu(self)
        from .menu_qss import apply_menu_theme
        apply_menu_theme(menu, getattr(self, "_dark_theme", False))
        entries = (
            ("浮动窗口", "float"),
            ("停靠到顶部", "top"),
            ("停靠到底部", "bottom"),
            ("停靠到最左侧", "dock-left"),
            ("停靠到最右侧", "dock-right"),
            ("嵌入：左面板右侧（独立竖列）", "inner-left"),
            ("嵌入：右面板左侧（独立竖列）", "inner-right"),
        )
        for label, place in entries:
            act = menu.addAction(
                label, lambda _=False, p=place: self._place_tool(p))
            act.setEnabled(place != self._tool_place)
        menu.exec(self.tool_widget.mapToGlobal(pos))

    def _place_tool(self, place: str) -> None:
        """统一摆放工具面板。

        place:
          float                 浮动窗口
          top/bottom            停靠主窗口顶/底（单行横排）
          dock-left/dock-right  停靠主窗口最左/最右（单列竖排）
          inner-left            嵌入水平分栏：左面板与画布之间（独立竖列）
          inner-right           嵌入水平分栏：画布与右面板之间（独立竖列）
        """
        valid = ("float", "top", "bottom", "dock-left", "dock-right",
                 "inner-left", "inner-right")
        if place not in valid or place == self._tool_place:
            return
        embedded_now = self._tool_place in ("inner-left", "inner-right")
        embedded_next = place in ("inner-left", "inner-right")

        if embedded_next:
            # —— 进入分栏：先把内容从 Dock 取出 ——
            if not embedded_now:
                # 进入前留存「干净」的 3 列分栏 / 主窗口 Dock 状态，
                # 供设置持久化与恢复使用
                try:
                    self._clean_main_state = bytes(
                        self.saveState().toBase64()).decode()
                    self._clean_splitter_state = bytes(
                        self.splitter.saveState().toBase64()).decode()
                except Exception:
                    pass
                self.removeDockWidget(self.tool_dock)
                self.tool_dock.setWidget(None)
            else:
                # 从一侧嵌入列换到另一侧：先从分栏取出
                self.tool_widget.setParent(None)
            if place == "inner-left":
                idx = self.splitter.indexOf(self.center_box)
            else:
                idx = self.splitter.indexOf(self.right_box)
            if idx < 0:
                idx = 1 if place == "inner-left" else self.splitter.count()
            self.splitter.insertWidget(idx, self.tool_widget)
            self.splitter.setCollapsible(idx, False)
            try:
                self.splitter.handle(idx).setCursor(
                    Qt.CursorShape.SplitHCursor)
            except Exception:
                pass
            self.tool_widget.show()
            self._tool_place = place
        elif embedded_now:
            # —— 从分栏回到 Dock 体系 ——
            self.tool_widget.setParent(None)
            self.tool_dock.setWidget(self.tool_widget)
            if place == "float":
                self.addDockWidget(
                    Qt.DockWidgetArea.LeftDockWidgetArea, self.tool_dock)
                self.tool_dock.setFloating(True)
                self._tool_place = "float"
            else:
                self.addDockWidget(self._TOOL_PLACE_AREA[place], self.tool_dock)
                if self.tool_dock.isFloating():
                    self.tool_dock.setFloating(False)
                self._tool_place = place
        else:
            # —— Dock 体系内部迁移（停靠区互转 / 浮动） ——
            if place == "float":
                self.tool_dock.setFloating(True)
                self._tool_place = "float"
            else:
                self.addDockWidget(self._TOOL_PLACE_AREA[place], self.tool_dock)
                if self.tool_dock.isFloating():
                    self.tool_dock.setFloating(False)
                self._tool_place = place

        self._update_tool_layout_orientation()

    def _tool_drop_zone(self):
        """浮动工具面板当前位置是否落在左右分栏嵌入缝隙。

        以「左面板右缘」「右面板左缘」为吸附锚点，返回
        'inner-left' / 'inner-right' / None。
        """
        try:
            center = self.tool_dock.frameGeometry().center()
            left_edge = self.left_box.mapToGlobal(
                QPoint(self.left_box.width(), 0)).x()
            right_edge = self.right_box.mapToGlobal(QPoint(0, 0)).x()
            c_top = self.central.mapToGlobal(QPoint(0, 0)).y()
            c_bottom = c_top + self.central.height()
            # 纵向需落在中央区范围内（容差 40px）
            if not (c_top - 40 <= center.y() <= c_bottom + 40):
                return None
            gap = 30  # 屏幕像素吸附半径
            if abs(center.x() - left_edge) <= gap:
                return "inner-left"
            if abs(center.x() - right_edge) <= gap:
                return "inner-right"
        except Exception:
            return None
        return None

    def _check_float_tool_dropzone(self):
        """轮询浮动面板拖动：松开且确实发生过拖动时，若位于缝隙则嵌入。"""
        if not self.tool_dock.isFloating():
            return
        pressed = bool(QApplication.mouseButtons()
                       & Qt.MouseButton.LeftButton)
        if pressed:
            if not self._tool_drag_active:
                self._tool_drag_active = True
                self._tool_drag_start_pos = self.tool_dock.frameGeometry().topLeft()
            return
        if not self._tool_drag_active:
            return
        self._tool_drag_active = False
        start = self._tool_drag_start_pos
        self._tool_drag_start_pos = None
        cur = self.tool_dock.frameGeometry().topLeft()
        # 区分「点击」与「拖动」：位移过小不触发嵌入，避免点 ⧉ 误吸附
        if start is not None and abs(cur.x() - start.x()) + abs(cur.y() - start.y()) < 16:
            return
        zone = self._tool_drop_zone()
        if zone:
            self._place_tool(zone)

    def _restore_tool_place(self, place: str) -> None:
        """启动恢复工具面板的摆放位置。"""
        valid = ("float", "top", "bottom", "dock-left", "dock-right",
                 "inner-left", "inner-right")
        if place in valid and place != self._tool_place:
            self._place_tool(place)

    def _on_tool_dock_floating_changed(self, floating):
        """工具面板浮动状态变化：调整方向，并启停嵌入区拖动轮询。"""
        if floating:
            self._tool_place = "float"
            self._tool_drag_active = False
            self._tool_drag_start_pos = None
            self._tool_float_timer.start()
        else:
            self._tool_float_timer.stop()
            self._tool_drag_active = False
            # 用户直接把浮动 Dock 拖入停靠区时，同步内部摆放状态
            if self._tool_place not in ("inner-left", "inner-right"):
                area = self.dockWidgetArea(self.tool_dock)
                if area in self._TOOL_AREA_PLACE:
                    self._tool_place = self._TOOL_AREA_PLACE[area]
        self._update_tool_layout_orientation()




    def _switch_mode(self, mode: str) -> None:
        # 无图片时使用标注工具：提示新建或打开图片（select/截图除外）
        if (mode not in ("select", "screenshot")
                and not self.canvas.has_image()
                and not self._ask_new_or_open_image()):
            return
        self.canvas.set_mode(mode)
        self._apply_mode_button_styles(mode)

    def _on_canvas_mode_changed(self, mode: str) -> None:
        """Photoshop 风格：进入某模式自动展开相关设置组（所有 set_mode 路径）。"""
        g = self.MODE_GROUP.get(mode)
        if g:
            self.panel.expand_group(g)

    def _on_group_activated(self, key: str) -> None:
        """反向联动：用户主动展开/操作某功能设置组时，自动切到对应工具模式。"""
        mode = self.GROUP_MODE.get(key)
        if mode and getattr(self.canvas, "mode", None) != mode:
            self._switch_mode(mode)

    def _apply_mode_button_styles(self, checked_mode: str) -> None:
        """当前选中的模式按钮高亮（蓝底+浅蓝边框），其余普通态。"""
        for mode, btn in self.mode_buttons.items():
            label = self.mode_btn_styles[mode]
            if mode == "screenshot":
                btn.setStyleSheet(self.MODE_BTN_SS_NORMAL)
                continue
            btn.setChecked(mode == checked_mode)
            btn.setText(label)   # 不加前缀，靠蓝底+浅色边框表示选中
            if mode == checked_mode:
                btn.setStyleSheet(self.MODE_BTN_SS_CHECKED)
            else:
                btn.setStyleSheet(self.MODE_BTN_SS_NORMAL)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_left_floating_pos()

    def _build_statusbar(self) -> None:
        self.status = self.statusBar()
        self.status.addPermanentWidget(self._autosave_lbl)
        self.status.showMessage("就绪")

        # 系统托盘图标
        self._tray_icon = QSystemTrayIcon(self)
        tray_icon_path = _resource_path("1.ico")
        if not os.path.exists(tray_icon_path):
            tray_icon_path = _resource_path("2.ico")
        if os.path.exists(tray_icon_path):
            self._tray_icon.setIcon(QIcon(tray_icon_path))
        else:
            self._tray_icon.setIcon(self.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon))
        self._tray_icon.setToolTip("图片快速标注工具")
        tray_menu = QMenu()
        show_act = tray_menu.addAction("显示主界面")
        show_act.triggered.connect(self._show_from_tray)
        quit_act = tray_menu.addAction("退出")
        quit_act.triggered.connect(self._quit_app)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _quit_app(self):
        """真正退出程序：保存参数配置 + 保存当前工作到 autosave，再完全退出。"""
        try:
            self._persist_settings()
        except Exception:
            pass
        try:
            self._do_autosave()
        except Exception:
            pass
        try:
            self._tray_icon.hide()
        except Exception:
            pass
        QApplication.quit()

    def _center_on_screen(self):
        """窗口居中显示。"""
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _show_from_tray(self):
        """从托盘显示主界面。"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        """点击托盘图标切换显示/隐藏。"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_from_tray()

    def closeEvent(self, event):
        """关闭窗口时隐藏到托盘，不退出程序；同时持久化全部设置。"""
        self._persist_settings()
        event.ignore()
        self.hide()
        self._tray_icon.showMessage("提示", "程序已最小化到托盘，点击图标恢复",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)

    def changeEvent(self, event):
        """最小化时隐藏到托盘。"""
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized():
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def _connect_signals(self) -> None:
        self.act_new.triggered.connect(self.new_blank_image)
        self.act_paste.triggered.connect(self.paste_clipboard)
        self.act_open.triggered.connect(self.open_image)
        self.act_save_proj.triggered.connect(self.save_project)
        self.act_open_proj.triggered.connect(self.open_project)
        self.act_undo.triggered.connect(self.canvas.undo)
        self.act_redo.triggered.connect(self.canvas.redo)
        self.act_delete.triggered.connect(self.canvas.delete_selected)
        self.act_clear.triggered.connect(self.clear_canvas)
        self.act_copy.triggered.connect(self.copy_annotated)
        self.act_save.triggered.connect(self.export_quick)

        self.canvas.imageLoaded.connect(self._on_image_loaded)
        self.canvas.itemsChanged.connect(self._on_items_changed)
        self.canvas.itemSelectionChanged.connect(self._on_selection_changed)
        self.canvas.cursorMoved.connect(self._on_cursor_moved)
        self.canvas.modeChanged.connect(self._apply_mode_button_styles)
        self.canvas.layersChanged.connect(self._refresh_layer_tree)
        self.canvas.commandRequested.connect(self._on_canvas_command)
        self.canvas.statusMessage.connect(self._show_status_message)

        # 图层结构树面板 <-> 画布
        self.layer_tree.requestAdd.connect(self.canvas.add_layer)
        self.layer_tree.requestDelete.connect(self.canvas.delete_layer)
        self.layer_tree.requestVisible.connect(self.canvas.set_layer_visible)
        self.layer_tree.requestMove.connect(self.canvas.move_layer)
        self.layer_tree.requestSelect.connect(self.canvas.select_layer)
        self.layer_tree.requestReorder.connect(self.canvas.apply_layer_order)
        self.layer_tree.requestRename.connect(self.canvas.rename_layer)
        self.layer_tree.requestSelectLayerItems.connect(self.canvas.select_layer_items)
        self.layer_tree.requestCopyLayer.connect(self._copy_layer)
        self.layer_tree.requestSelectItem.connect(self._history_select)
        self.layer_tree.requestEditText.connect(self._history_edit_text)
        self.layer_tree.requestDeleteItem.connect(self._history_delete)
        self.layer_tree.requestEditNumber.connect(self._history_edit_number)
        self.layer_tree.requestMoveItem.connect(self._history_move)
        self.layer_tree.requestMoveItemToLayer.connect(self._move_item_to_layer)
        self.canvas.modeChanged.connect(self._on_canvas_mode_changed)

        # 设置组主动展开/操作 -> 自动切换对应工具模式
        self.panel.groupActivated.connect(self._on_group_activated)
        # 功能组展开/折叠状态变化 -> 同步「折叠/展开全部」按钮
        self.panel.groupsChanged.connect(self._sync_collapse_all_btn)
        # 自由截图
        self.panel.screenshotRequested.connect(self.start_screenshot)
        self.panel.shot_now_btn.clicked.connect(self.start_screenshot)
        self.panel.shot_key_edit.keySequenceChanged.connect(
            lambda _seq=None: self._bind_screenshot_shortcut())
        self._shot_shortcut = None
        self._shot_overlay = None
        QTimer.singleShot(0, self._bind_screenshot_shortcut)

    # ================= 自由截图 =================
    def _bind_screenshot_shortcut(self) -> None:
        # 按面板设置（重新）绑定应用内截图快捷键；清空则禁用
        seq_str = self.panel.shot_key_edit.keySequence().toString()
        seq = QKeySequence(seq_str) if seq_str else QKeySequence()
        if self._shot_shortcut is None:
            self._shot_shortcut = QShortcut(
                seq if seq_str else QKeySequence("Ctrl+Q"), self)
            self._shot_shortcut.activated.connect(self.start_screenshot)
        else:
            self._shot_shortcut.setKey(seq)

    def start_screenshot(self) -> None:
        # 隐藏主窗口后弹出全屏框选遮罩
        if self._shot_overlay is not None:
            return
        # v1.7 需求5：截图前先把正在编辑的就地输入框收尾（失焦即提交），
        # 避免半编辑状态被最小化窗口带偏，也避免后续流程出现覆盖提示。
        try:
            if (hasattr(self.canvas, "_editor")
                    and self.canvas._editor.isVisible()):
                self.canvas._editor._emit_confirmed()
        except Exception:
            pass
        self._shot_was_visible = self.isVisible()
        self.showMinimized()
        QTimer.singleShot(220, self._show_screenshot_overlay)

    def _show_screenshot_overlay(self) -> None:
        # 截图遮罩弹出属于关键交互：任何异常都不能让进程闪退，
        # 出错时恢复主窗口并给出提示（不改动 screenshot.py 本身）。
        try:
            scr = screenshot.pick_screen_at_cursor()
            ov = screenshot.ScreenshotOverlay(scr)
            self._shot_overlay = ov
            ov.captured.connect(self._on_screenshot_captured)
            ov.canceled.connect(self._on_screenshot_canceled)
            ov.showFullScreen()
            ov.raise_()
            ov.activateWindow()
        except Exception:
            import traceback
            traceback.print_exc()
            self._shot_overlay = None
            self._restore_after_screenshot()

    def _restore_after_screenshot(self) -> None:
        self._shot_overlay = None
        if getattr(self, "_shot_was_visible", True):
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _apply_screenshot_border(self, pm: QPixmap) -> QPixmap:
        """按面板设置给截图加边框；勾选「无边框」时不加。"""
        try:
            if self.panel.shot_no_border_check.isChecked():
                return pm
        except Exception:
            pass
        try:
            bw = self.panel.shot_border_w_spin.value()
        except Exception:
            bw = 0
        if not bw or bw <= 0 or pm.isNull():
            return pm
        color = QColor("#2F80ED")
        try:
            color = getattr(self.panel.shot_border_color_btn, "_color", color)
        except Exception:
            pass
        out = QPixmap(pm)
        p = QPainter(out)
        pen = QPen(color, bw)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        half = bw / 2.0
        p.drawRect(QRectF(half, half, out.width() - bw, out.height() - bw))
        p.end()
        return out

    def _on_screenshot_captured(self, pm: QPixmap) -> None:
        # 先恢复主窗口，再延迟插入图片（等窗口真正显示后再操作画布）
        self._shot_overlay = None
        self._screenshot_in_progress = False
        try:
            pm = self._apply_screenshot_border(pm)
            if self.panel.shot_clip_check.isChecked():
                QGuiApplication.clipboard().setPixmap(pm)
            import_into = self.panel.shot_canvas_check.isChecked()
            if import_into:
                self._pending_screenshot_pm = pm
            else:
                self._pending_screenshot_pm = None
        except Exception:
            self._pending_screenshot_pm = None
        if getattr(self, "_shot_was_visible", True):
            self.showNormal()
            self.raise_()
            self.activateWindow()
        # 延迟 80ms 插入，确保窗口已激活、画布可接收事件
        QTimer.singleShot(80, self._do_pending_screenshot)

    def _do_pending_screenshot(self) -> None:
        pm = getattr(self, "_pending_screenshot_pm", None)
        self._pending_screenshot_pm = None
        if pm is None:
            return
        try:
            # 1) 没有主图 / 没有任何已编辑元素 → 截图直接作为主图载入
            # 2) 已有图片且有编辑内容 → 截图作为新图层图片元素插入
            has_image = self.canvas.pixmap is not None
            has_items = len(self.canvas.items) > 0
            if not has_image and not has_items:
                self.canvas.load_pixmap(pm, fit=False)
                self.status.showMessage(
                    "截图已载入主界面", 2500)
            else:
                item = self.canvas.add_image_element(pm)
                if item is not None:
                    self.status.showMessage(
                        "截图已作为新图层插入（可缩放/旋转/移动）", 2500)
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self.status.showMessage("截图载入出现异常，已保留到剪贴板", 3000)
            except Exception:
                pass

    def _on_screenshot_canceled(self) -> None:
        self._restore_after_screenshot()

    # ================= 历史面板联动 =================
    def _history_select(self, item_id: int) -> None:
        self.canvas.select_item_by_id(item_id)

    def _history_edit_number(self, item_id: int) -> None:
        leaders = [it for it in self.canvas.items
                   if isinstance(it, LeaderLineItem)]
        item = next((it for it in leaders if it.id == item_id), None)
        if item is None:
            return
        cur = item.number or 1
        n, ok = QInputDialog.getInt(self, "编辑序号", "输入新序号（1 起，自动连续补全）：",
                                    cur, 1, max(1, len(leaders)))
        if ok:
            self.canvas.push_undo("reorder")
            self.canvas.reorder_by_number(item_id, n)
            self._refresh_layer_tree()

    def _history_move(self, item_id: int, delta: int) -> None:
        self.canvas.push_undo("reorder")
        self.canvas.move_item(item_id, delta)
        self._refresh_layer_tree()

    def _move_item_to_layer(self, item_id: int, target_layer_id: int) -> None:
        """将元素移动到目标图层。"""
        self.canvas.push_undo("move to layer")
        self.canvas.move_item_to_layer(item_id, target_layer_id)
        self._refresh_layer_tree()

    def _copy_layer(self, layer_id: int) -> None:
        """复制图层（v2.x 需求3：左侧结构树空白右键「复制层」）。"""
        layer = self.canvas.copy_layer(layer_id)
        if layer is not None:
            self.status.showMessage(
                f"已复制图层「{layer.name}」（"
                f"{len(self.canvas.items_on_layer(layer.id))} 个元素）", 3000)

    def _history_edit_text(self, item_id: int) -> None:
        for it in self.canvas.items:
            if it.id == item_id:
                self.canvas.start_inline_editor(
                    it.edit_anchor(),
                    lambda content, tgt=it: self.canvas._edit_item_text(tgt, content),
                    initial_text=it.text_content)
                return

    def _history_delete(self, item_id: int) -> None:
        for it in self.canvas.items:
            if it.id == item_id:
                self.canvas.delete_item(it)
                return

    # ================= 图片输入 =================
    def new_blank_image(self) -> None:
        """新建指定尺寸与背景颜色的空白图片，用于直接标注。"""
        from PyQt6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox,
                                     QLabel as _QL, QSpinBox, QHBoxLayout as _HB,
                                     QPushButton as _PB, QVBoxLayout as _VB)
        dlg = QDialog(self)
        dlg.setWindowTitle("新建空白图片")
        lay = _VB(dlg)
        lay.addWidget(_QL("创建一张空白画布用于标注（可继续添加引线/文字/形状等）。"))
        # ---- 尺寸 ----
        row = _HB()
        row.addWidget(_QL("宽度："))
        w_spin = QSpinBox(); w_spin.setRange(64, 8192); w_spin.setValue(1920)
        row.addWidget(w_spin)
        row.addWidget(_QL("高度："))
        h_spin = QSpinBox(); h_spin.setRange(64, 8192); h_spin.setValue(1080)
        row.addWidget(h_spin)
        row.addStretch(1)
        lay.addLayout(row)
        pre_row = _HB()
        pre_row.addWidget(_QL("预设："))
        for txt, w, h in (("1920×1080", 1920, 1080), ("1280×720", 1280, 720),
                          ("800×600", 800, 600), ("512×512", 512, 512)):
            b = _PB(txt)
            b.clicked.connect(lambda _=False, w=w, h=h:
                              (w_spin.setValue(w), h_spin.setValue(h)))
            pre_row.addWidget(b)
        pre_row.addStretch(1)
        lay.addLayout(pre_row)
        # ---- 背景颜色 ----
        colors = [("白色", QColor("#FFFFFF")), ("浅灰", QColor("#F0F2F5")),
                  ("深灰", QColor("#3C3F41")), ("黑色", QColor("#1E1E1E")),
                  ("透明", QColor(0, 0, 0, 0))]
        state = {"cur": colors[0][1]}

        def pick(c):
            state["cur"] = c
            for btn, cc in color_btns:
                btn.setChecked(cc == c)

        color_btns = []
        color_row = _HB()
        color_row.addWidget(_QL("背景色："))
        for txt, c in colors:
            b = _PB(txt)
            b.setCheckable(True)
            b.setFixedWidth(64)
            bg = c.name() if c.alpha() else "#FFFFFF"
            fg = "#1E1E1E" if c.lightness() > 128 or not c.alpha() else "#FFFFFF"
            b.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {fg};"
                f" border: 1px solid #999; border-radius: 4px; }}"
                f"QPushButton:checked {{ border: 2px solid #2F6FED; }}")
            b.clicked.connect(lambda _=False, c=c: pick(c))
            color_btns.append((b, c))
            color_row.addWidget(b)
        cust = _PB("自定义…")
        cust.clicked.connect(lambda: self._pick_blank_color(dlg, state, pick))
        color_row.addWidget(cust)
        color_row.addStretch(1)
        lay.addLayout(color_row)
        pick(colors[0][1])
        # ---- 按钮 ----
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        w, h = w_spin.value(), h_spin.value()
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(state["cur"])
        self.canvas.load_pixmap(QPixmap.fromImage(img))
        self.status.showMessage(f"已新建空白图片：{w}×{h}", 3000)

    def _pick_blank_color(self, parent, state, pick) -> None:
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(state["cur"], parent, "选择背景颜色")
        if c.isValid():
            pick(c)

    def _ask_new_or_open_image(self) -> bool:
        """无图片时使用工具，提示新建或打开图片。返回 True 表示已成功加载图片。"""
        box = QMessageBox(self)
        box.setWindowTitle("提示")
        box.setText("当前没有图片，无法使用标注工具。\n请先新建空白图片，或打开一张图片。")
        b_new = box.addButton("新建空白图片", QMessageBox.ButtonRole.AcceptRole)
        b_open = box.addButton("打开图片", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_new)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_new:
            self.new_blank_image()
            return self.canvas.has_image()
        if clicked is b_open:
            self.open_image()
            return self.canvas.has_image()
        return False

    def _confirm_overwrite(self, action_name: str = "导入新图片") -> bool:
        """v1.6 需求7：画布已有标注时，询问是否先保存当前工作再继续。

        返回 True 表示可继续（已按用户选择保存或明确不保存），
        返回 False 表示用户取消，调用方应中止操作。
        """
        if not self.canvas.has_image() or not self.canvas.items:
            return True
        ret = QMessageBox.question(
            self, "保存当前工作",
            f"当前画布已有 {len(self.canvas.items)} 个标注。\n"
            f"{action_name}将覆盖当前内容，是否先保存当前工作（自动保存）？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if ret == QMessageBox.StandardButton.Save:
            self._do_autosave()
            self.status.showMessage("已保存当前工作（自动保存）", 2500)
            return True
        return ret == QMessageBox.StandardButton.No

    def _ask_import_mode(self, action_name: str = "导入图片"):
        """v2.x 需求3：画布已有内容时，询问图片导入方式。

        返回：
          "overwrite" —— 覆盖主图（已通过 _confirm_overwrite 确认）
          "element"   —— 作为新图层元素插入（不覆盖当前图片）
          "cancel"     —— 用户取消
        画布为空时直接返回 "overwrite"（沿用原行为，不弹窗）。
        """
        if not self.canvas.has_image() or not self.canvas.items:
            return "overwrite"
        box = QMessageBox(self)
        box.setWindowTitle("导入图片")
        box.setText(f"{action_name}：希望如何导入这张图片？")
        b_ow = box.addButton("覆盖当前图片", QMessageBox.ButtonRole.AcceptRole)
        b_el = box.addButton("导入为元素（新图层）", QMessageBox.ButtonRole.ActionRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_ow)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_el:
            return "element"
        if clicked is b_ow:
            return "overwrite" if self._confirm_overwrite(action_name) else "cancel"
        return "cancel"

    def paste_clipboard(self) -> None:
        try:
            from PIL import Image, ImageGrab
            clip = ImageGrab.grabclipboard()
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "读取剪贴板失败", f"无法读取剪贴板：{exc}")
            return
        if isinstance(clip, Image.Image):
            pm = pil_to_qpixmap(clip)
            mode = self._ask_import_mode("粘贴图片")
            if mode == "cancel":
                return
            if mode == "element":
                self.canvas.add_image_element(pm)
                self.status.showMessage("图片已作为新图层元素插入（可缩放/旋转/移动）", 2500)
            else:
                self.canvas.load_pixmap(pm)
        else:
            QMessageBox.information(self, "提示", "剪贴板没有图片。\n请先复制一张图片（如截图），再点击本按钮。")

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开本地图片", self._last_open_dir, IMAGE_FILTER)
        if not path:
            return
        self._last_open_dir = os.path.dirname(path)   # 需求9：记录打开目录
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "无法打开", f"无法加载图片：\n{path}")
            return
        mode = self._ask_import_mode("打开新图片")
        if mode == "cancel":
            return
        if mode == "element":
            self.canvas.add_image_element(pm)
            self.status.showMessage("图片已作为新图层元素插入（可缩放/旋转/移动）", 2500)
        else:
            self.canvas.load_pixmap(pm)

    def clear_canvas(self) -> None:
        if not self.canvas.has_image():
            return
        if self.canvas.items:
            ret = QMessageBox.question(self, "清空画布",
                                       "确定要删除全部标注吗？（可使用撤销恢复）")
            if ret != QMessageBox.StandardButton.Yes:
                return
        self.canvas.clear_all()

    # ================= 导出 / 复制 =================
    def export_quick(self) -> None:
        """Ctrl+S / 工具栏：按上次选择的格式直接导出（不再弹质量面板）。"""
        self.export_image(self._last_export_fmt, ask_save=True)

    def export_image(self, fmt: str, ask_save: bool = True) -> None:
        if not self.canvas.has_image():
            QMessageBox.information(self, "提示", "请先加载一张图片再导出。")
            return
        fmt = fmt.upper()
        if fmt not in EXPORT_FORMATS:
            fmt = "PNG"
        self._last_export_fmt = fmt
        if not ask_save:
            # 供自动化测试：直接返回渲染图（不弹保存框）
            return
        ext = fmt.lower()
        if fmt == "JPG":
            fname = "JPG 图片 (*.jpg *.jpeg)"
        elif fmt == "TIF":
            fname = "TIFF 图片 (*.tif *.tiff)"
        else:
            fname = f"{fmt} 图片 (*.{ext})"
        _start = (os.path.join(self._last_save_dir, f"标注导出.{ext}")
                  if self._last_save_dir else f"标注导出.{ext}")
        path, _ = QFileDialog.getSaveFileName(self, f"导出 {fmt}", _start, fname)
        if not path:
            return
        self._last_save_dir = os.path.dirname(path)   # 需求9：记录保存目录
        ok = False
        if fmt == "PNG":
            ok = self.canvas.render_export().save(path, "PNG")
        elif fmt == "GIF":
            # Qt 内置 GIF 插件只读（supportedImageFormats 无 gif），
            # 改用项目已依赖的 Pillow 写 GIF
            ok = self._save_gif(path)
        else:
            # JPG/BMP/TIF/TIFF：统一走 QImageWriter（格式插件 Qt 内置）
            writer = QImageWriter(path, QByteArray(fmt.encode("ascii")))
            if fmt == "JPG":
                writer.setQuality(self.panel.jpg_quality_spin.value())
            ok = writer.write(self.canvas.render_export())
        if not ok:
            QMessageBox.warning(self, "导出失败", f"无法写入文件：\n{path}")
            return
        self.status.showMessage(f"已导出：{path}")

    def _save_gif(self, path: str) -> bool:
        """用 Pillow 写 GIF（Qt 内置 GIF 插件只读，见 export_image）。"""
        try:
            from PIL import Image as PILImage
            qimg = self.canvas.render_export().convertToFormat(
                QImage.Format.Format_RGB888)
            w, h = qimg.width(), qimg.height()
            bpl = qimg.bytesPerLine()
            ptr = qimg.constBits()
            ptr.setsize(qimg.sizeInBytes())
            raw = bytes(ptr)
            rows = b"".join(raw[y * bpl: y * bpl + w * 3] for y in range(h))
            PILImage.frombytes("RGB", (w, h), rows).save(path, "GIF")
            return True
        except Exception:
            return False

    def copy_annotated(self) -> None:
        """把「图片 + 全部标注」渲染图复制到系统剪贴板，可直接粘贴到 PPT 等。"""
        if not self.canvas.has_image():
            QMessageBox.information(self, "提示", "请先加载一张图片再复制。")
            return
        img = self.canvas.render_export()
        QGuiApplication.clipboard().setImage(img)
        self.status.showMessage("已复制标注图到剪贴板（可直接粘贴）")

    # ================= 右侧面板：折叠/展开全部功能组 =================
    def _toggle_right_panel_all(self) -> None:
        """点击「折叠/展开全部」：有展开的组则全部折叠，否则全部展开。"""
        if self.panel.any_expanded():
            self.panel.collapse_all()
        else:
            self.panel.expand_all()
        self._sync_collapse_all_btn()

    def _sync_collapse_all_btn(self) -> None:
        """根据右侧功能组状态同步按钮文案/提示。"""
        if not hasattr(self, "collapse_all_btn"):
            return
        if self.panel.any_expanded():
            self.collapse_all_btn.setText("▲ 折叠全部")
            self.collapse_all_btn.setToolTip("折叠右侧全部功能面板")
        else:
            self.collapse_all_btn.setText("▼ 展开全部")
            self.collapse_all_btn.setToolTip("展开右侧全部功能面板")

    def _apply_collapse_btn_theme(self) -> None:
        """「折叠/展开全部」按钮配色随明/暗主题切换。"""
        if not hasattr(self, "collapse_all_btn"):
            return
        if getattr(self, "_dark_theme", False):
            self.collapse_all_btn.setStyleSheet(
                "QPushButton { background-color: #3d3d3d; color: #E0E0E0;"
                " border: 1px solid #555555; border-radius: 4px; padding: 3px 8px; }"
                "QPushButton:hover { background-color: #4a4a4a; }"
                "QPushButton:pressed { background-color: #565656; }")
        else:
            self.collapse_all_btn.setStyleSheet(
                "QPushButton { background-color: #F2F3F5; color: #333333;"
                " border: 1px solid #D0D3D6; border-radius: 4px; padding: 3px 8px; }"
                "QPushButton:hover { background-color: #E4E6EB; }"
                "QPushButton:pressed { background-color: #D8DAE0; }")

    def _apply_panel_scrollbar_theme(self, dark: bool) -> None:
        """右侧面板纵向滚动条样式（需求1：宽度加倍为 34px，随明暗主题配色）。"""
        if not hasattr(self, "panel_scroll"):
            return
        w = int(getattr(self, "panel_scrollbar_w", 34))
        if dark:
            ss = (
                f"QScrollBar:vertical {{ width:{w}px; background:#2B2B2B;"
                " margin:0; border:none; }"
                "QScrollBar::handle:vertical { background:#6A6A6A; min-height:48px;"
                " border-radius:6px; margin:3px; }"
                "QScrollBar::handle:vertical:hover { background:#8A8A8A; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
                " height:0; border:none; }"
                "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
                " background:transparent; }"
                "QScrollBar:horizontal { height:0; }")
        else:
            ss = (
                f"QScrollBar:vertical {{ width:{w}px; background:#F0F1F3;"
                " margin:0; border:none; }"
                "QScrollBar::handle:vertical { background:#B9BDC2; min-height:48px;"
                " border-radius:6px; margin:3px; }"
                "QScrollBar::handle:vertical:hover { background:#8E949B; }"
                "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
                " height:0; border:none; }"
                "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
                " background:transparent; }"
                "QScrollBar:horizontal { height:0; }")
        self.panel_scroll.setStyleSheet(ss)

    def _toggle_left_panel(self) -> None:
        """切换左侧面板显示/隐藏。"""
        self._left_panel_expanded = not self._left_panel_expanded
        if self._left_panel_expanded:
            # 展开：恢复宽度，恢复可拖动的最小宽度
            self.left_box.setMaximumWidth(16777215)
            self.left_box.setMinimumWidth(150)  # 最小宽度，允许拖动调节
            sizes = self.splitter.sizes()
            sizes[0] = self._left_panel_width
            sizes[1] = max(self.splitter.width() - self._left_panel_width - sizes[2], 100)
            self.splitter.setSizes(sizes)
        else:
            # 收起：记录当前宽度，收缩到 0
            if self.left_box.width() > 24:
                self._left_panel_width = self.left_box.width()
            self.left_box.setMaximumWidth(0)
            self.left_box.setMinimumWidth(0)
            sizes = self.splitter.sizes()
            sizes[0] = 0
            sizes[1] = max(self.splitter.width() - sizes[2], 100)
            self.splitter.setSizes(sizes)
        self._sync_left_floating_icon()
        QTimer.singleShot(0, self._update_left_floating_pos)

    def _show_right_panel_menu(self, pos):
        """右侧面板右键菜单：显示/隐藏主工具栏。"""
        menu = QMenu(self)
        from .menu_qss import apply_menu_theme
        apply_menu_theme(menu, getattr(self, "_dark_theme", False))
        toolbar_visible = self.toolbar.isVisible() if hasattr(self, 'toolbar') else True
        act = menu.addAction("显示主工具栏" if not toolbar_visible else "隐藏主工具栏")
        act.triggered.connect(self._toggle_toolbar)
        menu.exec(self.right_box.mapToGlobal(pos))

    def _toggle_toolbar(self):
        """切换主工具栏显示/隐藏。"""
        if hasattr(self, 'toolbar'):
            self.toolbar.setVisible(not self.toolbar.isVisible())

    def _toggle_theme(self):
        """切换明/暗主题。"""
        self._dark_theme = not self._dark_theme
        if self._dark_theme:
            self.theme_btn.setText("☀️")
            self._apply_dark_theme()
        else:
            self.theme_btn.setText("🌙")
            self._apply_light_theme()

    def _apply_dark_theme(self):
        """应用深色主题。"""
        qss = """
QMainWindow, QWidget { background-color: #2d2d2d; color: #e0e0e0; }
QToolBar { background-color: #3d3d3d; border-bottom: 1px solid #555555; spacing: 3px; padding: 3px; }
QPushButton { background-color: #4a4a4a; color: #e0e0e0; border: 1px solid #555555; border-radius: 4px; padding: 4px 8px; }
QPushButton:hover { background-color: #5a5a5a; }
QPushButton:checked { background-color: #2f6fed; color: white; }
QGroupBox { border: 1px solid #555555; border-radius: 4px; margin-top: 12px; padding-top: 12px; color: #e0e0e0; font-weight: bold; background-color: #3a3a3a; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #90EE90; background-color: transparent; }
QGroupBox::title:hover { color: #4da3ff; }
QGroupBox:hover { border-color: #666666; }
QListWidget, QComboBox, QLineEdit, QKeySequenceEdit { background-color: #3d3d3d; color: #e0e0e0; border: 1px solid #555555; border-radius: 3px; padding: 2px; }
QSpinBox, QDoubleSpinBox { background-color: #3d3d3d; color: #e0e0e0; border: 1px solid #555555; border-radius: 3px; padding: 2px 18px 2px 4px; }
QSpinBox:hover, QDoubleSpinBox:hover { border-color: #2F6FED; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 16px; border: none; border-left: 1px solid #555555; border-top-right-radius: 3px; background: #4a4a4a; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 16px; border: none; border-left: 1px solid #555555; border-bottom-right-radius: 3px; background: #4a4a4a; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #2F6FED; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #1F56C8; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: none; width: 0px; height: 0px; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 5px solid #E0E0E0; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: none; width: 0px; height: 0px; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #E0E0E0; }
QSpinBox::up-button:hover::up-arrow, QDoubleSpinBox::up-button:hover::up-arrow,
QSpinBox::down-button:hover::down-arrow, QDoubleSpinBox::down-button:hover::down-arrow,
QSpinBox::up-button:pressed::up-arrow, QDoubleSpinBox::up-button:pressed::up-arrow,
QSpinBox::down-button:pressed::down-arrow, QDoubleSpinBox::down-button:pressed::down-arrow {
    border-top-color: #FFFFFF; border-bottom-color: #FFFFFF; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #E0E0E0; }
QMenu { background-color: #3d3d3d; color: #e0e0e0; border: 1px solid #555555; }
QMenu::item:selected { background-color: #2f6fed; }
QSplitter::handle { background-color: #555555; }
QLabel { color: #e0e0e0; }
QCheckBox { color: #e0e0e0; }
"""
        self.setStyleSheet(qss)
        # v1.6 需求8：应用级 QMenu 样式 —— 画布右键菜单与两侧面板右键菜单
        # 都继承自 QApplication 样式，明暗主题下文字与背景同步变化
        _app = QApplication.instance()
        if _app is not None:
            _app.setStyleSheet(
                "QMenu { background-color: #2f2f3a; color: #F2F2F2;"
                " border: 1px solid #555555; padding: 3px; }"
                "QMenu::item { padding: 5px 24px; border-radius: 3px; }"
                "QMenu::item:selected { background-color: #2f6fed; color: white; }"
                "QMenu::item:disabled { color: #8a8a8a; }"
                "QMenu::separator { height: 1px; background: #555555;"
                " margin: 4px 8px; }"
                "QMenu::indicator { width: 14px; height: 14px; }")
        if hasattr(self, "panel"):
            self.panel.set_dark_theme(True)
        if hasattr(self, "layer_tree"):
            self.layer_tree.set_dark_theme(True)
        if hasattr(self, "canvas"):
            self.canvas._dark_theme = True
        if hasattr(self, "panel"):
            self.panel.apply_theme_follow_bg(True)   # 需求5：暗黑→深灰（未手动改背景时）
        if hasattr(self, "h_ruler"):
            self.h_ruler.set_dark(True)               # 需求8：标尺随主题
            self.v_ruler.set_dark(True)
        self._apply_collapse_btn_theme()
        self._apply_panel_scrollbar_theme(True)

    def _apply_light_theme(self):
        """应用浅色主题（默认）。

        v1.7 需求5：不再清空为原生样式，而是套用一套显式 QSS —— 文字颜色与
        背景颜色成对指定（黑字白底/深字浅底）。此前清空样式后，输入控件
        （QSpinBox/QComboBox/QLineEdit 等）会残留暗黑主题的调色板文字色，
        出现“文字适应而背景不适应”的灰字看不清问题。
        """
        qss = """
QMainWindow, QWidget { background-color: #F5F5F7; color: #1A1A1A; }
QToolBar { background-color: #FFFFFF; border-bottom: 1px solid #D0D3D6; spacing: 3px; padding: 3px; }
QPushButton { background-color: #FFFFFF; color: #1A1A1A; border: 1px solid #C8CBD0; border-radius: 4px; padding: 4px 8px; }
QPushButton:hover { background-color: #F0F2F5; }
QPushButton:pressed { background-color: #E2E5E9; }
QPushButton:checked { background-color: #2f6fed; color: white; }
QPushButton:disabled { color: #A0A4AB; background-color: #F0F1F3; }
QToolButton { background: transparent; color: #1A1A1A; border: none; }
QToolButton:hover { background: rgba(47,111,237,0.12); }
QToolButton:checked { background: #2f6fed; color: white; border-radius: 4px; }
QCheckBox { color: #1A1A1A; spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #5F6B7A; border-radius: 3px; background-color: #FFFFFF; }
QCheckBox::indicator:hover { border-color: #2F6FED; }
QCheckBox::indicator:checked { background-color: #2F6FED; border-color: #2F6FED; }
QRadioButton { color: #1A1A1A; }
QLabel { color: #1A1A1A; }
QComboBox, QLineEdit, QListWidget, QKeySequenceEdit {
    background-color: #FFFFFF; color: #1A1A1A; border: 1px solid #C8CBD0;
    border-radius: 3px; padding: 2px; selection-background-color: #2F6FED;
    selection-color: #FFFFFF; }
QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF; color: #1A1A1A; border: 1px solid #C8CBD0;
    border-radius: 3px; padding: 2px 18px 2px 4px; selection-background-color: #2F6FED;
    selection-color: #FFFFFF; }
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: #2F6FED; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow { image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid #1A1A1A; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 16px; border: none;
    border-left: 1px solid #C8CBD0; border-top-right-radius: 3px; background: #E8EAED; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 16px; border: none;
    border-left: 1px solid #C8CBD0; border-bottom-right-radius: 3px; background: #E8EAED; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #2F6FED; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #1F56C8; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: none; width: 0px; height: 0px;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid #1A1A1A; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: none; width: 0px; height: 0px;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #1A1A1A; }
QSpinBox::up-button:hover::up-arrow, QDoubleSpinBox::up-button:hover::up-arrow,
QSpinBox::down-button:hover::down-arrow, QDoubleSpinBox::down-button:hover::down-arrow,
QSpinBox::up-button:pressed::up-arrow, QDoubleSpinBox::up-button:pressed::up-arrow,
QSpinBox::down-button:pressed::down-arrow, QDoubleSpinBox::down-button:pressed::down-arrow {
    border-top-color: #FFFFFF; border-bottom-color: #FFFFFF; }
QMenu { background-color: #FFFFFF; color: #1A1A1A; border: 1px solid #C8CBD0; padding: 3px; }
QMenu::item { padding: 5px 24px; border-radius: 3px; }
QMenu::item:selected { background-color: #2f6fed; color: white; }
QMenu::item:disabled { color: #A0A4AB; }
QMenu::separator { height: 1px; background: #E0E2E6; margin: 4px 8px; }
QSplitter::handle { background-color: #D0D3D6; }
QStatusBar { background-color: #EDEEF0; color: #1A1A1A; }
QToolTip { background-color: #FFFFFF; color: #1A1A1A; border: 1px solid #C8CBD0; }
"""
        self.setStyleSheet(qss)
        # v1.6 需求8：清除应用级 QMenu 样式（明亮下菜单由窗口 QSS/原生提供）
        _app = QApplication.instance()
        if _app is not None:
            _app.setStyleSheet("")
        if hasattr(self, "panel"):
            self.panel.set_dark_theme(False)
        if hasattr(self, "layer_tree"):
            self.layer_tree.set_dark_theme(False)
        if hasattr(self, "canvas"):
            self.canvas._dark_theme = False
        if hasattr(self, "panel"):
            self.panel.apply_theme_follow_bg(False)  # 需求5：明亮→浅灰（未手动改背景时）
        if hasattr(self, "h_ruler"):
            self.h_ruler.set_dark(False)              # 需求8：标尺随主题
            self.v_ruler.set_dark(False)
        self._apply_collapse_btn_theme()
        self._apply_panel_scrollbar_theme(False)

    def _on_splitter_moved(self, pos, index):
        """Splitter 拖动时保存左侧面板宽度。"""
        # index=1 表示第一个 splitter handle（左侧和中间之间）
        if index == 1 and self._left_panel_expanded:
            new_width = self.left_box.width()
            if new_width > 100:  # 有效宽度
                self._left_panel_width = new_width
        # 工具面板未嵌入分栏时，持续更新「干净」的 3 列分栏状态，
        # 供嵌入期间持久化使用（嵌入后是 4 列，不能直接存）
        if getattr(self, "_tool_place", "") not in ("inner-left", "inner-right"):
            try:
                self._clean_splitter_state = bytes(
                    self.splitter.saveState().toBase64()).decode()
            except Exception:
                pass

    def _sync_left_floating_icon(self) -> None:
        """浮动按钮箭头：展开时显示 ◀（点击收起），收起时显示 ▶（点击展开）。"""
        self.left_floating.setText("◀" if self._left_panel_expanded else "▶")

    def _update_left_floating_pos(self) -> None:
        """浮动按钮定位：贴在左面板右缘 / 屏幕左缘，垂直居中。"""
        if not hasattr(self, "central") or self.central is None:
            return
        cw, ch = self.central.width(), self.central.height()
        y = ch // 2 - 14
        btn_w, btn_h = 16, 28
        lw = self.left_box.width()
        if self._left_panel_expanded and lw > 24:
            x = lw - btn_w // 2
        else:
            x = 0
        self.left_floating.setGeometry(x, y, btn_w, btn_h)
        self.left_floating.raise_()

    def _refresh_layer_tree(self) -> None:
        self.layer_tree.refresh(self.canvas.layers, self.canvas.items, self.canvas.current_layer)

    # ================= 状态 =================
    def _update_action_states(self) -> None:
        self.act_undo.setEnabled(self.canvas.can_undo())
        self.act_redo.setEnabled(self.canvas.can_redo())
        if hasattr(self, "undo_btn"):
            self.undo_btn.setEnabled(self.canvas.can_undo())
            self.redo_btn.setEnabled(self.canvas.can_redo())
        n = len(self.canvas.items)
        has_img = self.canvas.has_image()
        self.act_delete.setEnabled(has_img and bool(self.canvas.selected_items()))
        self.act_clear.setEnabled(has_img and n > 0)
        self.export_btn.setEnabled(has_img)
        self.act_save.setEnabled(has_img)
        self.act_copy.setEnabled(has_img)
        if has_img:
            self.status.showMessage(
                f"标注元素：{n} 个 ｜ 撤销 {len(self.canvas.undo_stack)} 步 ｜ "
                f"重做 {len(self.canvas.redo_stack)} 步 ｜ 缩放：{self.canvas.scale * 100:.0f}%")

    def _on_cursor_moved(self, x: float, y: float) -> None:
        if self.canvas.has_image():
            self.status.showMessage(
                f"坐标 ({x:.0f}, {y:.0f}) ｜ 缩放 {self.canvas.scale * 100:.0f}% ｜ "
                f"撤销 {len(self.canvas.undo_stack)} ｜ 重做 {len(self.canvas.redo_stack)} ｜ "
                f"标注元素 {len(self.canvas.items)} 个 ｜ 模式：{self._mode_name()}")
        else:
            self.status.showMessage("就绪")

    def _mode_name(self) -> str:
        _names = {"select": "选择", "leader": "引线标注", "number": "引线序号",
                  "text": "文本批注", "shape": "形状", "pen": "画笔",
                  "highlight": "荧光笔", "mosaic": "马赛克", "emoji": "表情",
                  "screenshot": "自由截图"}
        return _names.get(self.canvas.mode, self.canvas.mode)

    # ================= 图层结构树刷新 + 自动保存 =================
    def _on_selection_changed(self) -> None:
        self.panel.sync_from_selection(self.canvas.selected_items())
        self._refresh_layer_tree()
        self._update_action_states()

    def _show_status_message(self, msg: str) -> None:
        """状态栏短暂显示提示消息（右键菜单/重复命令等反馈）。"""
        if self.status is not None:
            self.status.showMessage(msg, 3000)

    def _show_about(self) -> None:
        """关于对话框：版本 2.0 / 作者 redmoonk / 版权 bk100 / 功能说明 + 二维码。

        v2.0 需求6：内嵌「中天健」二维码（明亮.png / 暗黑.png 随主题切换）。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("关于 图片标注大师 v2.0")
        dlg.setMinimumSize(560, 440)
        lay = QHBoxLayout(dlg)
        # 左：二维码（按当前主题选图）
        qr_label = QLabel()
        qr_label.setFixedSize(168, 168)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet(
            "QLabel { background:#FFFFFF; border:1px solid #BBBBBB; border-radius:4px; }")
        dark = bool(getattr(self, "_dark_theme", False))
        qr_name = "暗黑.png" if dark else "明亮.png"
        # 用字节流加载，避免中文路径在个别运行环境下 QPixmap(path) 偶发失败。
        # 搜索顺序：① PyInstaller 解压目录 sys._MEIPASS（打包内嵌资源）；
        # ② exe 所在目录（允许用户外置替换二维码图）；③ 源码运行目录。
        pm = QPixmap()
        _search_dirs = []
        _meipass = getattr(sys, "_MEIPASS", None)
        if _meipass:
            _search_dirs.append(_meipass)
        _search_dirs.append(settings._app_base_dir())
        for _name in (qr_name, "明亮.png", "暗黑.png"):
            for _d in _search_dirs:
                try:
                    with open(os.path.join(_d, _name), "rb") as _f:
                        if pm.loadFromData(_f.read()):
                            break
                except Exception:
                    continue
            if not pm.isNull():
                break
        if not pm.isNull():
            qr_label.setPixmap(pm.scaled(
                160, 160, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            qr_label.setText("二维码")
        lay.addWidget(qr_label, 0, Qt.AlignmentFlag.AlignTop)
        # 右：文字说明
        info = QLabel()
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setText(
            "<h3 style='margin:0 0 6px 0;'>图片快速标注工具 v2.0</h3>"
            "<p style='margin:2px 0;'><b>版本：</b>2.0</p>"
            "<p style='margin:2px 0;'><b>作者：</b>redmoonk</p>"
            "<p style='margin:2px 0;'><b>版权：</b>© bk100</p>"
            "<hr>"
            "<p style='margin:2px 0;'><b>主要功能：</b></p>"
            "<ul style='margin:2px 0; padding-left:18px;'>"
            "<li>标注：引线/序号/文本/形状/画笔/荧光/马赛克/表情</li>"
            "<li>形状库：参考 Office 的更多形状（箭头/心形/云朵/对话气泡等），"
            "全部形状（含直线）支持嵌入文字，可设上/中/下位置</li>"
            "<li>明暗主题自动跟随、标尺随主题、记忆打开/保存目录</li>"
            "<li>自由截图、自动保存、.anno 项目文件、多格式导出</li>"
            "</ul>"
            "<p style='margin:4px 0 0 0; color:#888;'>扫描左侧二维码关注/联系</p>")
        lay.addWidget(info, 1)
        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok = QPushButton("确定")
        ok.setFixedWidth(80)
        ok.clicked.connect(dlg.accept)
        btn_row.addWidget(ok)
        outer = QVBoxLayout()
        outer.addLayout(lay)
        outer.addLayout(btn_row)
        outer.setSpacing(10)
        dlg.setLayout(outer)
        dlg.adjustSize()
        dlg.exec()

    def _on_canvas_command(self, cmd: str) -> None:
        """处理画布右键菜单发来的主窗口级动作。"""
        if cmd == "copy_annotated":
            self.copy_annotated()
        elif cmd == "clear_canvas":
            self.clear_canvas()
        elif cmd == "screenshot":
            self.start_screenshot()

    def _on_items_changed(self) -> None:
        self._refresh_layer_tree()
        self._update_action_states()
        self._schedule_autosave()

    def _on_image_loaded(self) -> None:
        self.status.showMessage("图片已加载")
        self._update_action_states()
        self._schedule_autosave()
        QTimer.singleShot(0, self.canvas.center_image)

    def _schedule_autosave(self) -> None:
        if self.canvas.has_image():
            self._autosave_timer.start()
            self._autosave_lbl.setText(" 自动保存：待保存…")

    def _do_autosave(self) -> None:
        if not self.canvas.has_image():
            return
        if autosave.save(self.canvas.pixmap, self.canvas.items,
                         self.canvas.layers, self.canvas.current_layer):
            self._autosave_lbl.setText(f" 自动保存：{__import__('time').strftime('%H:%M:%S')}")
        else:
            self._autosave_lbl.setText(" 自动保存：失败")

    def _check_restore(self) -> None:
        """启动时检测自动保存数据，询问是否恢复上次未完成的工作。"""
        pm, items, layers, current_layer = autosave.load()
        if pm is None:
            return
        ret = QMessageBox.question(
            self, "恢复上次工作",
            "检测到上次未保存的标注工作，是否恢复？\n"
            "（选择「否」将丢弃自动保存的数据）")
        if ret == QMessageBox.StandardButton.Yes:
            self.canvas.load_pixmap(pm)
            self.canvas.items = items
            if layers:
                self.canvas.layers = layers
                self.canvas.current_layer = current_layer if current_layer is not None \
                    else layers[-1].id
            # 序号不丢失：恢复出的引线带序号时自动开启序号开关并重新编号
            if any(getattr(it, "number", None) for it in items):
                self.canvas.number_enabled = True
                self.panel.number_check.setChecked(True)
                self.canvas.renumber()
            self.canvas.undo_stack.clear()
            self.canvas.redo_stack.clear()
            # 唯一性：清理恢复数据中的重复元素（同位置同内容的副本只留一个）
            dup = self.canvas.deduplicate_items()
            self.canvas.highlight_layer_id = None   # v1.6：恢复工作不显示虚线框
            self.canvas.update()
            self.canvas.itemSelectionChanged.emit()
            self.canvas.itemsChanged.emit()
            self.canvas.layersChanged.emit()
            self.status.showMessage(
                f"已恢复自动保存：{len(self.canvas.items)} 个标注"
                + (f"（清理 {dup} 个重复元素）" if dup else ""))
        else:
            autosave.clear()

    # ================= 项目文件（.anno：图片 + 标注 + 图层，可继续编辑） =================
    def save_project(self) -> None:
        """把当前画布（图片 + 全部标注 + 图层 + 样式）保存为可编辑项目文件。"""
        if self.canvas.pixmap is None:
            QMessageBox.information(self, "提示", "画布为空，请先加载图片")
            return
        _start = (os.path.join(self._last_save_dir, "标注项目.anno")
                  if self._last_save_dir else "标注项目.anno")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目文件", _start, "标注项目 (*.anno)")
        if not path:
            return
        self._last_save_dir = os.path.dirname(path)   # 需求9：记录保存目录
        import io
        import json
        import zipfile
        from PyQt6.QtCore import QBuffer
        from PyQt6.QtGui import QImageWriter
        try:
            buf = QBuffer()
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            self.canvas.pixmap.toImage().save(buf, "PNG")
            st = self._deep_color_hex(dict(self.panel.current_style()))
            payload = {
                "items": autosave.serialize_items(self.canvas.items),
                "layers": autosave.serialize_layers(self.canvas.layers),
                "current_layer": self.canvas.current_layer,
                "style": st,
                "number_enabled": self.canvas.number_enabled,
                "number_format": self.canvas.number_format,
                "snap_mode": self.canvas.snap_mode,
            }
            # v1.7：先把 JSON 完整序列化，再整体写入临时文件后原子替换，
            # 任何一步失败都不会留下「只有 image.png、没有 project.json」的残缺文件
            data = json.dumps(payload, ensure_ascii=False)
            import tempfile
            _dir = os.path.dirname(os.path.abspath(path)) or "."
            fd, tmp = tempfile.mkstemp(suffix=".anno.tmp", dir=_dir)
            try:
                with os.fdopen(fd, "wb") as f:
                    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
                        z.writestr("image.png", bytes(buf.data()))
                        z.writestr("project.json", data)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"无法保存项目：{e}")
            return
        self.status.showMessage(f"项目已保存：{path}")

    def open_project(self) -> None:
        """打开项目文件，恢复图片 + 标注 + 图层继续编辑。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目文件", self._last_open_dir, "标注项目 (*.anno);;所有文件 (*.*)")
        if not path:
            return
        self._last_open_dir = os.path.dirname(path)   # 需求9：记录打开目录
        if not self._confirm_overwrite("打开项目"):
            return
        import json
        import zipfile
        try:
            if not zipfile.is_zipfile(path):
                QMessageBox.warning(self, "打开失败", "所选文件不是有效的项目文件（.anno）。")
                return
            with zipfile.ZipFile(path, "r") as z:
                names = z.namelist()
                if "project.json" not in names:
                    # v1.7：旧版/残缺项目 → 仅加载图片，明确提示不报神秘错误
                    img_bytes = z.read("image.png")
                    pm = QPixmap()
                    if not pm.loadFromData(img_bytes, "PNG"):
                        QMessageBox.warning(
                            self, "打开失败",
                            "项目文件不完整（缺少 project.json 且图片损坏），无法打开。")
                        return
                    self.canvas.load_pixmap(pm)
                    self.canvas.items = []
                    if self.canvas.layers:
                        self.canvas.layers = self.canvas.layers[:1]
                        self.canvas.current_layer = self.canvas.layers[0].id
                    self.canvas.undo_stack.clear()
                    self.canvas.redo_stack.clear()
                    self.canvas.update()
                    self.canvas.itemSelectionChanged.emit()
                    self.canvas.itemsChanged.emit()
                    self.canvas.layersChanged.emit()
                    QMessageBox.information(
                        self, "提示",
                        "该项目文件缺少标注数据（project.json），已仅加载其中的图片。")
                    return
                img_bytes = z.read("image.png")
                payload = json.loads(z.read("project.json").decode("utf-8"))
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开项目文件：{e}")
            return
        pm = QPixmap()
        if not pm.loadFromData(img_bytes, "PNG"):
            QMessageBox.warning(self, "打开失败", "项目文件中的图片损坏")
            return
        try:
            items = autosave.deserialize_items(payload.get("items", []))
            layers = autosave.deserialize_layers(payload.get("layers", []), items)
        except (TypeError, ValueError):
            items, layers = [], []
        current_layer = payload.get("current_layer")
        if layers and current_layer is not None:
            for l in layers:
                if l.id == current_layer:
                    break
            else:
                current_layer = layers[-1].id
        self.canvas.load_pixmap(pm)
        self.canvas.items = items
        if layers:
            self.canvas.layers = layers
            self.canvas.current_layer = current_layer if current_layer is not None \
                else layers[-1].id
        # 序号/全局状态恢复（不丢失序号）
        if payload.get("number_enabled") or any(getattr(it, "number", None)
                                                for it in items):
            self.canvas.number_enabled = True
            self.panel.number_check.setChecked(True)
            self.canvas.number_format = payload.get("number_format", "circle")
            self.canvas.renumber()
        if payload.get("snap_mode"):
            self.canvas.snap_mode = payload["snap_mode"]
        st = payload.get("style")
        if st:
            self.panel.set_style(st)
        self.canvas.undo_stack.clear()
        self.canvas.redo_stack.clear()
        # 唯一性：清理项目文件中的重复元素（同位置同内容的副本只留一个）
        dup = self.canvas.deduplicate_items()
        self.canvas.highlight_layer_id = None   # v1.6：打开项目不显示虚线框
        self.canvas.update()
        self.canvas.itemSelectionChanged.emit()
        self.canvas.itemsChanged.emit()
        self.canvas.layersChanged.emit()
        self.status.showMessage(
            f"已打开项目：{path}"
            + (f"（清理 {dup} 个重复元素）" if dup else ""))
