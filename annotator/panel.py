# -*- coding: utf-8 -*-
"""右侧样式面板：引线样式、文字样式、文字背景框设置。

行为：
- 未选中元素时：面板值作为「新建标注的默认样式」。
- 选中元素时：面板值修改立即应用到所有选中元素（可撤销合并）。
- 元素选中变化时，面板回填该元素的当前值。
"""

import os

from PyQt6.QtCore import QPoint, QSize, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPalette, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                             QDoubleSpinBox, QFontComboBox, QGroupBox,
                             QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel,
                             QMenu, QPushButton, QSizePolicy, QSpinBox,
                             QToolButton, QVBoxLayout, QWidget)

from .items import (ABOVE_DIR_AUTO, ABOVE_DIR_LEFT, ABOVE_DIR_RIGHT,
                    FONT_FAMILY, FONT_WEIGHT_OPTIONS, SCRIPT_OPTIONS,
                    PenItem, ShapeItem, LeaderLineItem, HighlightItem, MosaicItem,
                    EmojiItem, STYLE_ABOVE,
                    STYLE_BOX, STYLE_PLAIN, NUM_FMT_OPTIONS,
                    SHAPE_OPTIONS, SHAPE_OPTIONS_PRIMARY, SHAPE_OPTIONS_MORE,
                    shape_categories, shape_path, _SHAPE_CATEGORY_OF)

# 端点符号预设：界面文字 -> 存储值
ENDPOINT_OPTIONS = [("三角", "arrow"), ("圆点", "dot"), ("圆圈", "circle"), ("无", "none")]
# 画布背景预设：界面文字 -> 颜色
BG_OPTIONS = [("浅灰", "#F0F2F5"), ("纯白", "#FFFFFF"),
              ("浅蓝", "#E8F0F8"), ("浅绿", "#EFF7EE"),
              ("深灰", "#3C3F41"), ("黑色", "#1E1E1E")]
# 背景下拉首尾项（需求6）：顶部「无」=透明/无背景，底部「自定义」=弹色盘
BG_NONE_LABEL = "无"
BG_CUSTOM_LABEL = "自定义"
# 主题自动跟随对应的预设（需求5）：明亮→浅灰，暗黑→深灰
BG_AUTO_LIGHT = "浅灰"
BG_AUTO_DARK = "深灰"
# 标注风格预设：界面文字 -> 存储值
LABEL_STYLE_OPTIONS = [("文字在线上方", "above_text"),
                       ("文字在线中间", "middle_text"),
                       ("文字在线下方", "below_text"),
                       ("无横线", "no_line")]
# 横线方向预设（仅 above 风格生效）：界面文字 -> 存储值
ABOVE_DIR_OPTIONS = [("自动", ABOVE_DIR_AUTO),
                     ("向左", ABOVE_DIR_LEFT),
                     ("向右", ABOVE_DIR_RIGHT)]
# 文字对齐磁吸模式：界面文字 -> 存储值
SNAP_OPTIONS = [("无", "none"), ("左对齐", "left"), ("右对齐", "right"),
                ("水平居中", "hcenter"), ("顶部对齐", "top"),
                ("垂直居中", "vcenter"), ("线末端对齐", "end"),
                ("拐角对齐", "corner"), ("中心对齐", "center")]


def _color_button(color: QColor) -> QPushButton:
    btn = QPushButton()
    btn.setFixedHeight(28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def _apply_btn_color(btn: QPushButton, color: QColor) -> None:
    r, g, b = color.red(), color.green(), color.blue()
    btn.setStyleSheet(
        f"QPushButton {{ background-color: rgb({r},{g},{b}); "
        f"border: 1px solid #888; border-radius: 4px; }}")
    btn.setText(f"#{r:02X}{g:02X}{b:02X}" if not color.alpha() < 255 else
                f"rgba({r},{g},{b},{color.alpha()})")


def _apply_transparent_btn(btn: QPushButton) -> None:
    """透明色按钮（v2.x 需求1）：浅灰底 + 虚线边框 + 「透明」字样，
    表示该颜色当前被设为透明（隐藏）；保留按钮存储的上次非透明颜色。"""
    btn.setStyleSheet(
        "QPushButton { background-color: #E8E8E8; "
        "border: 1px dashed #AAAAAA; border-radius: 4px; color: #666666; }")
    btn.setText("透明")


def _shape_cat_qss(dark: bool) -> str:
    """形状分类灰色小标题的 QSS（需求4，明暗两套）。"""
    if dark:
        return ("QToolButton#shapeCatHeader {"
                " background:#3D3D3D; color:#C8C8C8; border:none;"
                " border-radius:3px; padding:2px 6px;"
                " font-weight:bold; text-align:left; }"
                "QToolButton#shapeCatHeader:hover { background:#4B4B4B; }")
    return ("QToolButton#shapeCatHeader {"
            " background:#ECECEC; color:#6E6E6E; border:none;"
            " border-radius:3px; padding:2px 6px;"
            " font-weight:bold; text-align:left; }"
            "QToolButton#shapeCatHeader:hover { background:#E2E2E2; }")


class CollapsibleBox(QWidget):
    """可折叠分组框（类 Photoshop 属性面板）：点击标题栏折叠/展开。

    内容统一放入 self.content_layout。

    userToggled(checked) 仅在“用户点击标题”时发出；程序化 set_expanded 不发。
    """

    userToggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None, expanded: bool = False):
        super().__init__(parent)
        self._title = title
        self._btn = QToolButton(text=title)
        self._btn.setCheckable(True)
        self._btn.setChecked(expanded)
        self._btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn.setArrowType(Qt.ArrowType.DownArrow if expanded
                               else Qt.ArrowType.RightArrow)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 用代码设置明确的像素字体；不要在 QSS 里写 font-size/font-weight，
        # 否则 hover 重新 polish 时 Qt 会从残缺字体描述合成 pointSize=-1 并报警告。
        _tf = QFont()
        _tf.setPixelSize(13)
        _tf.setBold(True)
        self._btn.setFont(_tf)
        self._dark = False
        self._programmatic = False
        self._apply_title_style()
        self._btn.toggled.connect(self._on_toggled)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(4, 2, 4, 8)
        self.content_layout.setSpacing(6)
        self._content = QWidget()
        self._content.setLayout(self.content_layout)
        self._content.setVisible(expanded)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._btn)
        outer.addWidget(self._content)

    def _apply_title_style(self) -> None:
        """根据主题和展开状态设置标题颜色（采用高对比绿/蓝/红/橙，避免黑白色看不清）。
        明亮：收起蓝 / 悬停绿 / 展开红 / 展开悬停橙；
        暗黑：收起绿 / 悬停蓝 / 展开红 / 展开悬停橙。"""
        if self._dark:
            self._btn.setStyleSheet(
                "QToolButton { border: none; padding: 4px 2px;"
                " color: #7CE38B; text-align: left; }"
                "QToolButton:hover { color: #5AA8FF; }"
                "QToolButton:checked { color: #FF6B78; }"
                "QToolButton:checked:hover { color: #FFA94D; }")
        else:
            self._btn.setStyleSheet(
                "QToolButton { border: none; padding: 4px 2px;"
                " color: #1F6FD0; text-align: left; }"
                "QToolButton:hover { color: #2FA05C; }"
                "QToolButton:checked { color: #E5485C; }"
                "QToolButton:checked:hover { color: #E8590C; }")

    def set_dark(self, dark: bool) -> None:
        """切换明/暗主题标题颜色。"""
        self._dark = bool(dark)
        self._apply_title_style()

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._btn.setArrowType(Qt.ArrowType.DownArrow if checked
                               else Qt.ArrowType.RightArrow)
        if not self._programmatic:
            self.userToggled.emit(checked)

    def set_expanded(self, expanded: bool) -> None:
        if self._btn.isChecked() != expanded:
            self._programmatic = True
            self._btn.setChecked(expanded)
            self._programmatic = False

    def is_expanded(self) -> bool:
        return self._btn.isChecked()

    def set_title(self, title: str) -> None:
        self._btn.setText(title)


def shape_icon(shape: str, size: int = 30) -> QIcon:
    """为形状类型生成图标（用于形状菜单）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPen
    p.setPen(QPen(QColor("#444444"), 2))
    p.setBrush(QColor("#F5F5F5"))
    p.drawPath(shape_path(shape, QRectF(4, 4, size - 8, size - 8)))
    p.end()
    return QIcon(pm)


_CHECK_ICON_CACHE = {}


def _checked_icon_path(color: str = "#2D2D30", name: str = "_check_dark.png") -> str:
    """生成（按颜色缓存一次）对勾 PNG，返回 QSS 可用的正斜杠绝对路径。

    Qt 的 QSS 一旦自定义了 QCheckBox::indicator 的背景/边框，就不会再
    绘制原生对勾，因此选中态必须通过 image 显式提供对勾图案，否则选中后
    只剩一块纯色、看不出是否勾选。文件放在应用数据目录 autosave/ 下，
    源码运行与 PyInstaller 打包后均可写。
    """
    global _CHECK_ICON_CACHE
    if color in _CHECK_ICON_CACHE:
        return _CHECK_ICON_CACHE[color]
    try:
        from . import settings
        d = os.path.join(settings._app_base_dir(), "autosave")
        os.makedirs(d, exist_ok=True)
        raw = os.path.join(d, name)
        path = raw.replace("\\", "/")
        if not os.path.exists(raw):
            pm = QPixmap(32, 32)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color), 4.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            # 经典对勾：(7,17)->(13,23)->(25,9)
            p.drawLine(7, 17, 13, 23)
            p.drawLine(13, 23, 25, 9)
            p.end()
            pm.save(raw, "PNG")
        _CHECK_ICON_CACHE[color] = path
    except Exception:
        _CHECK_ICON_CACHE[color] = ""
    return _CHECK_ICON_CACHE[color]


class StylePanel(QWidget):
    styleChanged = pyqtSignal()   # 默认样式变化（供画布创建新元素）
    screenshotRequested = pyqtSignal()  # 请求开始自由截图
    groupActivated = pyqtSignal(str)    # 用户主动展开/操作某功能组（key）
    groupsChanged = pyqtSignal()        # 任一功能组展开/折叠状态变化（用户或程序化）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self._syncing = False
        self._shape_val = SHAPE_OPTIONS[0][1]
        # 宽度由 QSplitter 控制，不限制死
        # self.setMinimumWidth(250)
        # self.setMaximumWidth(290)
        self._groups = {}
        self._build_ui()
        # 收集全部复选框，供暗黑主题统一设置白色选框
        self._checkboxes = [v for v in vars(self).values()
                            if isinstance(v, QCheckBox)]

    def attach(self, canvas) -> None:
        self.canvas = canvas

    def set_dark_theme(self, dark: bool) -> None:
        """切换折叠面板标题颜色 + 复选框选框颜色。

        暗黑下选框采用蓝/橙高对比配色（未选=蓝边框、悬停=橙边框），
        选中=白填充+深色对勾，避免黑白色看不清。"""
        for g in getattr(self, "_groups", {}).values():
            g.set_dark(dark)
        if dark:
            # 暗黑主题：未选=蓝色边框+深色底（清晰可见）；
            # 悬停=橙色边框；选中=白填充+深色对勾（QSS 自定义 indicator
            # 后 Qt 不画原生勾，必须用 image 提供对勾图案）。
            icon = _checked_icon_path()
            checked = ("QCheckBox::indicator:checked {"
                       " background-color: #FFFFFF; border: 1px solid #FFFFFF;")
            if icon:
                checked += f" image: url(\"{icon}\");"
            checked += " }"
            ss = ("QCheckBox { color: #F2F2F2; spacing: 6px; }"
                  "QCheckBox::indicator { width: 15px; height: 15px;"
                  " border: 1px solid #5AA8FF; background-color: #3d3d3d;"
                  " border-radius: 3px; }"
                  "QCheckBox::indicator:hover { border-color: #FFA94D; }"
                  "QCheckBox::indicator:checked:hover { border-color: #FFA94D; }"
                  + checked)
        else:
            # 明亮主题：清空控件级 QSS，恢复系统原生样式
            ss = ""
        for cb in getattr(self, "_checkboxes", []):
            cb.setStyleSheet(ss)
        # 形状分类灰色小标题（需求4）
        cat_ss = _shape_cat_qss(dark)
        for _h in getattr(self, "_shape_cat_headers", {}).values():
            _h.setStyleSheet(cat_ss)

    # ---------------- UI 构建 ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # ---- 引线设置 ----
        g_line = CollapsibleBox("引线设置", expanded=True)
        v = g_line.content_layout
        v.addWidget(QLabel("线条颜色"))
        self.line_color_btn = _color_button(QColor("#FF0000"))
        v.addWidget(self.line_color_btn)

        row_w = QHBoxLayout()
        row_w.addWidget(QLabel("线条粗细"))
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 20)
        self.line_width_spin.setValue(2)
        self.line_width_spin.setSuffix(" px")
        row_w.addWidget(self.line_width_spin)
        v.addLayout(row_w)

        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("箭头大小"))
        self.arrow_size_spin = QSpinBox()
        self.arrow_size_spin.setRange(6, 60)
        self.arrow_size_spin.setValue(14)
        row_a.addWidget(self.arrow_size_spin)
        v.addLayout(row_a)

        row_e = QHBoxLayout()
        row_e.addWidget(QLabel("端点符号"))
        self.endpoint_combo = QComboBox()
        for label, _ in ENDPOINT_OPTIONS:
            self.endpoint_combo.addItem(label)
        row_e.addWidget(self.endpoint_combo)
        v.addLayout(row_e)

        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("标注风格"))
        self.label_style_combo = QComboBox()
        for label, _ in LABEL_STYLE_OPTIONS:
            self.label_style_combo.addItem(label)
        row_s.addWidget(self.label_style_combo)
        v.addLayout(row_s)

        # 空白间隙：拐点/横线与文字之间的水平留白（0~20px）
        row_gap = QHBoxLayout()
        row_gap.addWidget(QLabel("空白间隙"))
        self.text_gap_spin = QSpinBox()
        self.text_gap_spin.setRange(0, 20)
        self.text_gap_spin.setValue(5)
        self.text_gap_spin.setSuffix(" px")
        self.text_gap_spin.setToolTip("引线拐点/横线与文字之间的水平留白（0~20px）")
        row_gap.addWidget(self.text_gap_spin)
        v.addLayout(row_gap)

        # 上下间隙：文字在横线上方/下方时，文字与横线的垂直间隙（0~20px）
        row_agap = QHBoxLayout()
        lbl_agap = QLabel("上下间隙")
        lbl_agap.setToolTip("文字在横线上方/下方时，文字与横线之间的垂直间隙（0~20px）")
        row_agap.addWidget(lbl_agap)
        self.above_gap_spin = QSpinBox()
        self.above_gap_spin.setRange(0, 20)
        self.above_gap_spin.setValue(5)
        self.above_gap_spin.setSuffix(" px")
        self.above_gap_spin.setToolTip("文字在横线上方/下方时，文字与横线之间的垂直间隙（0~20px）")
        row_agap.addWidget(self.above_gap_spin)
        v.addLayout(row_agap)

        row_d = QHBoxLayout()
        row_d.addWidget(QLabel("横线方向"))
        self.above_dir_combo = QComboBox()
        for label, _ in ABOVE_DIR_OPTIONS:
            self.above_dir_combo.addItem(label)
        row_d.addWidget(self.above_dir_combo)
        v.addLayout(row_d)

        row_n = QHBoxLayout()
        self.number_check = QCheckBox("引线序号")
        row_n.addWidget(self.number_check)
        self.number_fmt_combo = QComboBox()
        for label, _ in NUM_FMT_OPTIONS:
            self.number_fmt_combo.addItem(label)
        row_n.addWidget(self.number_fmt_combo)
        v.addLayout(row_n)

        # 应用到全部同类标注按钮
        self.apply_all_btn = QPushButton("应用到全部同类标注")
        self.apply_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_all_btn.setToolTip(
            "把当前引线样式应用到画布中全部引线标注元素")
        v.addWidget(self.apply_all_btn)

        root.addWidget(g_line)

        # ---- 文字设置（字体面板：字体/字号/粗细/颜色/斜体/上下标）----
        g_text = CollapsibleBox("文字设置")
        v = g_text.content_layout
        v.addWidget(QLabel("字体"))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(FONT_FAMILY))
        v.addWidget(self.font_combo)
        row_w = QHBoxLayout()
        row_w.addWidget(QLabel("粗细"))
        self.font_weight_combo = QComboBox()
        for label, _ in FONT_WEIGHT_OPTIONS:
            self.font_weight_combo.addItem(label)
        self.font_weight_combo.setCurrentIndex(1)   # 常规
        row_w.addWidget(self.font_weight_combo)
        self.italic_check = QCheckBox("斜体")
        row_w.addWidget(self.italic_check)
        v.addLayout(row_w)
        v.addWidget(QLabel("文字颜色"))
        self.text_color_btn = _color_button(QColor("#000000"))
        v.addWidget(self.text_color_btn)

        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("字体大小"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(18)
        row_f.addWidget(self.font_size_spin)
        v.addLayout(row_f)
        row_s = QHBoxLayout()
        row_s.addWidget(QLabel("脚本"))
        self.script_combo = QComboBox()
        for label, _ in SCRIPT_OPTIONS:
            self.script_combo.addItem(label)
        row_s.addWidget(self.script_combo)
        v.addLayout(row_s)
        # ---- 文字背景框设置（融合在文字设置面板中） ----
        v.addWidget(QLabel("---- 背景框 ----"))
        self.bg_check = QCheckBox("启用背景框")
        self.bg_check.setChecked(False)   # 默认透明背景
        v.addWidget(self.bg_check)
        v.addWidget(QLabel("填充颜色"))
        self.bg_fill_btn = _color_button(QColor(255, 255, 255, 215))
        v.addWidget(self.bg_fill_btn)
        v.addWidget(QLabel("边框颜色"))
        self.bg_border_btn = _color_button(QColor("#FF0000"))
        v.addWidget(self.bg_border_btn)

        root.addWidget(g_text)


        # ---- 画布设置 ----
        g_cv = CollapsibleBox("画布设置")
        v = g_cv.content_layout
        row_b = QHBoxLayout()
        row_b.addWidget(QLabel("背景颜色"))
        self.bg_combo = QComboBox()
        # 需求6：最顶部为「无」（无背景/透明样式），最底部为「自定义」（弹色盘）
        self.bg_combo.addItem(BG_NONE_LABEL)
        for label, _ in BG_OPTIONS:
            self.bg_combo.addItem(label)
        self.bg_combo.addItem(BG_CUSTOM_LABEL)
        row_b.addWidget(self.bg_combo)
        # 自定义背景色 & 是否自动跟随主题（需求5/6）
        self._bg_custom_color = QColor("#808080")
        self._bg_auto_follow = True
        v.addLayout(row_b)
        row_snap = QHBoxLayout()
        row_snap.addWidget(QLabel("文字对齐"))
        self.snap_combo = QComboBox()
        for label, _ in SNAP_OPTIONS:
            self.snap_combo.addItem(label)
        row_snap.addWidget(self.snap_combo)
        v.addLayout(row_snap)
        self.pick_btn = QPushButton("从图片取色（背景色）")
        self.pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        v.addWidget(self.pick_btn)
        row_rowgap = QHBoxLayout()
        row_rowgap.addWidget(QLabel("行距"))
        self.layout_row_spin = QDoubleSpinBox()
        self.layout_row_spin.setRange(0.5, 5.0)
        self.layout_row_spin.setSingleStep(0.5)
        self.layout_row_spin.setValue(1.0)
        self.layout_row_spin.setSuffix(" 行")
        self.layout_row_spin.setToolTip("左右区域标注的竖直行间距（行数倍率）")
        row_rowgap.addWidget(self.layout_row_spin)
        v.addLayout(row_rowgap)
        row_colgap = QHBoxLayout()
        row_colgap.addWidget(QLabel("列距"))
        self.layout_col_spin = QSpinBox()
        self.layout_col_spin.setRange(1, 20)
        self.layout_col_spin.setValue(2)
        self.layout_col_spin.setSuffix(" 字符")
        self.layout_col_spin.setToolTip("上下区域标注的水平列间距（字符数）")
        row_colgap.addWidget(self.layout_col_spin)
        v.addLayout(row_colgap)

        # 对齐方式选择
        row_halign = QHBoxLayout()
        row_halign.addWidget(QLabel("左右组对齐"))
        self.layout_h_align_combo = QComboBox()
        self.layout_h_align_combo.addItems(["左对齐", "居中对齐", "右对齐"])
        self.layout_h_align_combo.setCurrentIndex(0)
        self.layout_h_align_combo.setToolTip("左右两侧标注的水平对齐方式")
        row_halign.addWidget(self.layout_h_align_combo)
        v.addLayout(row_halign)

        row_valign = QHBoxLayout()
        row_valign.addWidget(QLabel("上下组对齐"))
        self.layout_v_align_combo = QComboBox()
        self.layout_v_align_combo.addItems(["顶对齐", "居中对齐", "底对齐"])
        self.layout_v_align_combo.setCurrentIndex(1)
        self.layout_v_align_combo.setToolTip("上下两侧标注的垂直对齐方式")
        row_valign.addWidget(self.layout_v_align_combo)
        v.addLayout(row_valign)

        self.layout_btn = QPushButton("一键自动布局")
        self.layout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        v.addWidget(self.layout_btn)

        root.addWidget(g_cv)

        # ---- 形状设置（需求4：Office 风格 7 大分类）----
        g_shp = CollapsibleBox("形状设置")
        v = g_shp.content_layout
        v.addWidget(QLabel("形状（按 Office 分类，点击灰色小标题展开/收起）"))
        # 基本形状 / 箭头汇总 / 公式形状 / 流程图 / 星与旗帜 / 标注 / 括号
        self._shape_buttons = {}
        self._shape_cat_headers = {}     # 分类小标题按钮（主题着色用）
        self._shape_cat_widgets = {}     # 分类 key -> 网格容器（展开/收起用）
        _SHAPE_COLS = 6

        def _pick_shape(val):
            for _v, _b in self._shape_buttons.items():
                _b.setChecked(_v == val)
            self._set_shape(val)

        def _build_shape_button(label, val):
            b = QToolButton()
            b.setIcon(shape_icon(val, 24))
            b.setIconSize(QSize(24, 24))
            b.setFixedSize(30, 30)
            b.setCheckable(True)
            b.setToolTip(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, vv=val: _pick_shape(vv))
            self._shape_buttons[val] = b
            return b

        self._shape_categories = shape_categories()
        for _ci, (_ckey, _ctitle, _citems) in enumerate(self._shape_categories):
            # 灰色小标题：点击折叠/展开该分类
            cat_btn = QToolButton()
            cat_btn.setObjectName("shapeCatHeader")
            cat_btn.setCheckable(True)
            cat_btn.setAutoRaise(True)
            cat_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            cat_btn.setFixedHeight(24)
            cat_btn.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Fixed)
            cat_btn.setText(f"▸  {_ctitle}（{len(_citems)}）")
            cat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cat_btn.setStyleSheet(_shape_cat_qss(False))   # 默认浅色，主题切换时覆盖
            self._shape_cat_headers[_ckey] = cat_btn

            cat_w = QWidget()
            cat_grid = QGridLayout(cat_w)
            cat_grid.setSpacing(2)
            cat_grid.setContentsMargins(2, 2, 2, 4)
            for _j, (_label, _val) in enumerate(_citems):
                cat_grid.addWidget(_build_shape_button(_label, _val),
                                   _j // _SHAPE_COLS, _j % _SHAPE_COLS)
            self._shape_cat_widgets[_ckey] = cat_w

            def _toggle_cat(checked, key=_ckey, title=_ctitle,
                           n=len(_citems)):
                self._shape_cat_widgets[key].setVisible(checked)
                self._shape_cat_headers[key].setText(
                    f"{'▾' if checked else '▸'}  {title}（{n}）")

            cat_btn.toggled.connect(_toggle_cat)
            # 默认仅展开第一类（基本形状）
            _expanded = (_ci == 0)
            cat_btn.setChecked(_expanded)
            cat_w.setVisible(_expanded)
            v.addWidget(cat_btn)
            v.addWidget(cat_w)
        # 当前默认形状选中态
        self._shape_buttons[self._shape_val].setChecked(True)
        # v2.x 需求1：边线/填充颜色均可设为「透明」（即隐藏），引线标注除外
        row_b = QHBoxLayout()
        row_b.addWidget(QLabel("边线颜色"))
        self.shape_border_btn = _color_button(QColor("#FF0000"))
        row_b.addWidget(self.shape_border_btn, 1)
        self.shape_border_trans_check = QCheckBox("透明")
        self.shape_border_trans_check.setToolTip("勾选后隐藏形状边线（边框颜色设为透明）")
        row_b.addWidget(self.shape_border_trans_check)
        v.addLayout(row_b)

        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("填充颜色"))
        self.shape_fill_btn = _color_button(QColor(255, 255, 255, 0))
        row_f.addWidget(self.shape_fill_btn, 1)
        self.shape_fill_trans_check = QCheckBox("透明")
        self.shape_fill_trans_check.setToolTip("勾选后隐藏形状填充（填充颜色设为透明）")
        row_f.addWidget(self.shape_fill_trans_check)
        v.addLayout(row_f)
        row_w = QHBoxLayout()
        row_w.addWidget(QLabel("线宽"))
        self.shape_width_spin = QSpinBox()
        self.shape_width_spin.setRange(1, 20)
        self.shape_width_spin.setValue(2)
        row_w.addWidget(self.shape_width_spin)
        v.addLayout(row_w)
        # v2.0 需求5：形状内嵌文字的垂直位置（含直线），默认居中
        row_tp = QHBoxLayout()
        row_tp.addWidget(QLabel("文字位置"))
        self.shape_textpos_combo = QComboBox()
        self.shape_textpos_combo.addItems(["居中", "上方", "下方"])
        self._shape_textpos_map = {0: "center", 1: "top", 2: "bottom"}
        row_tp.addWidget(self.shape_textpos_combo)
        v.addLayout(row_tp)
        self.shape_textpos_combo.currentIndexChanged.connect(
            lambda _: (self._request_group_activate("shape"),
                       self._on_style_changed()))
        # v2.x 需求1：边线/填充「透明」开关（勾选 = 颜色 alpha 置 0 隐藏）
        self.shape_border_trans_check.toggled.connect(
            lambda _: (self._request_group_activate("shape"),
                       self._on_style_changed()))
        self.shape_fill_trans_check.toggled.connect(
            lambda _: (self._request_group_activate("shape"),
                       self._on_style_changed()))
        root.addWidget(g_shp)

        # ---- 画笔设置 ----
        g_pen = CollapsibleBox("画笔设置")
        v = g_pen.content_layout
        v.addWidget(QLabel("画笔颜色"))
        self.pen_color_btn = _color_button(QColor("#000000"))
        v.addWidget(self.pen_color_btn)
        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("画笔粗细"))
        self.pen_width_spin = QSpinBox()
        self.pen_width_spin.setRange(1, 30)
        self.pen_width_spin.setValue(3)
        row_p.addWidget(self.pen_width_spin)
        v.addLayout(row_p)
        root.addWidget(g_pen)

        # ---- 荧光笔设置 ----
        g_hl = CollapsibleBox("荧光笔设置")
        v = g_hl.content_layout
        v.addWidget(QLabel("荧光颜色（点选预设或下方自定义）"))
        hl_row = QHBoxLayout()
        self._hl_preset_colors = ("#FFE600", "#54FF00", "#FF5CA8",
                                  "#33CCFF", "#FF9500", "#C77DFF")
        for _hexc in self._hl_preset_colors:
            _sb = QPushButton()
            _sb.setFixedSize(24, 24)
            _sb.setCursor(Qt.CursorShape.PointingHandCursor)
            _sb.setStyleSheet(
                "QPushButton{background:%s;border:1px solid #999;border-radius:4px;}"
                "QPushButton:hover{border:2px solid #2f6fed;}" % _hexc)
            _sb.clicked.connect(lambda _=False, cc=_hexc: self._set_hl_preset(cc))
            hl_row.addWidget(_sb)
        hl_row.addStretch(1)
        v.addLayout(hl_row)
        self.hl_color_btn = _color_button(QColor("#FFE600"))
        v.addWidget(self.hl_color_btn)
        row_hw = QHBoxLayout()
        row_hw.addWidget(QLabel("笔刷粗细"))
        self.hl_width_spin = QSpinBox()
        self.hl_width_spin.setRange(3, 100)
        self.hl_width_spin.setValue(22)
        row_hw.addWidget(self.hl_width_spin)
        v.addLayout(row_hw)
        row_ha = QHBoxLayout()
        row_ha.addWidget(QLabel("不透明度%"))
        self.hl_alpha_spin = QSpinBox()
        self.hl_alpha_spin.setRange(5, 100)
        self.hl_alpha_spin.setValue(31)
        row_ha.addWidget(self.hl_alpha_spin)
        v.addLayout(row_ha)
        root.addWidget(g_hl)

        # ---- 马赛克设置 ----
        g_mos = CollapsibleBox("马赛克设置")
        v = g_mos.content_layout
        row_mb = QHBoxLayout()
        row_mb.addWidget(QLabel("马赛克块大小"))
        self.mosaic_block_spin = QSpinBox()
        self.mosaic_block_spin.setRange(3, 50)
        self.mosaic_block_spin.setValue(10)
        row_mb.addWidget(self.mosaic_block_spin)
        v.addLayout(row_mb)
        self.mosaic_border_check = QCheckBox("显示马赛克边框")
        self.mosaic_border_check.setChecked(True)
        v.addWidget(self.mosaic_border_check)
        root.addWidget(g_mos)

        # ---- 表情设置 ----
        g_em = CollapsibleBox("表情设置")
        v = g_em.content_layout
        self._emoji_char = "😀"
        self._emoji_buttons = {}
        EMOJI_CHOICES = ["😀", "😁", "😂", "😍",
                         "😎", "🤔", "😢", "😭",
                         "😡", "👍", "👎", "👌",
                         "👏", "❤️", "✅", "❌", "⭐", "❓", "❗",
                         "💡", "🔥", "🎉", "⚠️", "🎯"]
        # 需求7：点击「更多」后展开的附加表情
        EMOJI_MORE = ["😇", "🥰", "😅", "😜", "🤣",
                      "😴", "🥳", "😤", "😱", "🤯",
                      "🤗", "🫡", "🤝", "✌️", "🤞",
                      "👋", "👊", "🙏", "💪", "🫶",
                      "💔", "💯", "✨", "⚡", "🌟",
                      "💤", "🆗", "🚫", "📌", "🏥",
                      "💊", "🩺", "🦠", "🧬", "💬"]
        grid_em = QGridLayout()
        grid_em.setSpacing(2)
        grid_em.setContentsMargins(2, 2, 2, 2)
        _EMOJI_COLS = 5

        def _pick_emoji(ch):
            self._emoji_char = ch
            for _c, _b in self._emoji_buttons.items():
                _b.setChecked(_c == ch)
            self._request_group_activate("emoji")
            self._on_style_changed()

        row = 0
        for _i, _ch in enumerate(EMOJI_CHOICES):
            _b = QPushButton(_ch)
            _b.setFixedSize(30, 30)
            _b.setCheckable(True)
            _b.setChecked(_ch == self._emoji_char)
            _b.clicked.connect(lambda _=False, c=_ch: _pick_emoji(c))
            grid_em.addWidget(_b, row, _i % _EMOJI_COLS)
            self._emoji_buttons[_ch] = _b
            if (_i + 1) % _EMOJI_COLS == 0:
                row += 1
        # 需求7：「更多 / 收起」按钮（跨整行），点击展开附加表情
        self._emoji_more_btn = QPushButton("更多 ▾")
        self._emoji_more_btn.setFixedHeight(26)
        grid_em.addWidget(self._emoji_more_btn, row, 0, 1, _EMOJI_COLS)
        row += 1
        self._emoji_extra_widgets = []
        for _j, _ch in enumerate(EMOJI_MORE):
            _b = QPushButton(_ch)
            _b.setFixedSize(30, 30)
            _b.setCheckable(True)
            _b.setChecked(False)
            _b.clicked.connect(lambda _=False, c=_ch: _pick_emoji(c))
            grid_em.addWidget(_b, row, _j % _EMOJI_COLS)
            _b.setVisible(False)
            self._emoji_buttons[_ch] = _b
            self._emoji_extra_widgets.append(_b)
            if (_j + 1) % _EMOJI_COLS == 0:
                row += 1
        self._emoji_more_open = False

        def _toggle_emoji_more():
            self._emoji_more_open = not self._emoji_more_open
            for _b in self._emoji_extra_widgets:
                _b.setVisible(self._emoji_more_open)
            self._emoji_more_btn.setText(
                "收起 ▴" if self._emoji_more_open else "更多 ▾")
        self._emoji_more_btn.clicked.connect(_toggle_emoji_more)
        v.addLayout(grid_em)
        row_es = QHBoxLayout()
        row_es.addWidget(QLabel("表情大小"))
        self.emoji_size_spin = QSpinBox()
        self.emoji_size_spin.setRange(12, 160)
        self.emoji_size_spin.setValue(40)
        row_es.addWidget(self.emoji_size_spin)
        v.addLayout(row_es)
        root.addWidget(g_em)

        # ---- 截图设置 ----
        g_ss = CollapsibleBox("截图设置")
        v = g_ss.content_layout
        row_sk = QHBoxLayout()
        row_sk.addWidget(QLabel("截图快捷键"))
        self.shot_key_edit = QKeySequenceEdit(QKeySequence("Ctrl+Q"))
        self.shot_key_edit.setToolTip("点击后按下想要的组合键；清空则不启用快捷键")
        row_sk.addWidget(self.shot_key_edit)
        v.addLayout(row_sk)
        self.shot_clip_check = QCheckBox("完成后复制到剪贴板")
        self.shot_clip_check.setChecked(True)
        v.addWidget(self.shot_clip_check)
        self.shot_canvas_check = QCheckBox("完成后载入画布继续标注")
        # v1.7 需求5：默认只复制到剪贴板，不载入画布 —— 避免每次截图都弹
        # “覆盖保存”提示打断截图流程；需要载入时再勾选此项。
        self.shot_canvas_check.setChecked(False)
        v.addWidget(self.shot_canvas_check)
        self.shot_now_btn = QPushButton("立即截图")
        self.shot_now_btn.setToolTip("隐藏主窗口并框选屏幕区域（也可按快捷键）")
        v.addWidget(self.shot_now_btn)
        # v2.x：截图边框（无边框选项 / 线宽 / 颜色）
        self.shot_no_border_check = QCheckBox("无边框")
        self.shot_no_border_check.setChecked(True)   # 默认无边框
        self.shot_no_border_check.setToolTip("勾选后截图不添加任何边框")
        v.addWidget(self.shot_no_border_check)
        row_bw = QHBoxLayout()
        row_bw.addWidget(QLabel("边框线宽"))
        self.shot_border_w_spin = QSpinBox()
        self.shot_border_w_spin.setRange(1, 30)
        self.shot_border_w_spin.setValue(2)
        self.shot_border_w_spin.setToolTip("截图后给结果加边框")
        row_bw.addWidget(self.shot_border_w_spin)
        v.addLayout(row_bw)
        v.addWidget(QLabel("边框颜色"))
        self.shot_border_color_btn = _color_button(QColor("#2F80ED"))
        self.shot_border_color_btn._color = QColor("#2F80ED")
        _apply_btn_color(self.shot_border_color_btn, self.shot_border_color_btn._color)
        self.shot_border_color_btn.setToolTip("点击选择边框颜色")
        self.shot_border_color_btn.clicked.connect(self._pick_shot_border_color)
        v.addWidget(self.shot_border_color_btn)

        def _sync_border_enabled(_=False):
            off = self.shot_no_border_check.isChecked()
            self.shot_border_w_spin.setEnabled(not off)
            self.shot_border_color_btn.setEnabled(not off)
        self.shot_no_border_check.toggled.connect(_sync_border_enabled)
        _sync_border_enabled()
        root.addWidget(g_ss)

        # ---- 导出设置 ----
        g_exp = CollapsibleBox("导出设置")
        v = g_exp.content_layout
        row_q = QHBoxLayout()
        row_q.addWidget(QLabel("JPG 质量"))
        self.jpg_quality_spin = QSpinBox()
        self.jpg_quality_spin.setRange(1, 100)
        self.jpg_quality_spin.setValue(90)
        row_q.addWidget(self.jpg_quality_spin)
        v.addLayout(row_q)
        # 透明背景导出选项（从画布设置移到导出设置）
        self.transparent_bg_check = QCheckBox("导出透明背景 PNG")
        self.transparent_bg_check.setToolTip("导出时不包含原图，只保留标注（背景透明）")
        self.transparent_bg_check.toggled.connect(self._on_transparent_bg_changed)
        v.addWidget(self.transparent_bg_check)
        root.addWidget(g_exp)

        root.addStretch(1)

        # ---- 信号 ----
        self.line_color_btn.clicked.connect(lambda: self._pick_color("line_color"))
        self.line_width_spin.valueChanged.connect(lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.arrow_size_spin.valueChanged.connect(lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.endpoint_combo.currentIndexChanged.connect(lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.text_gap_spin.valueChanged.connect(lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.above_gap_spin.valueChanged.connect(lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.text_color_btn.clicked.connect(lambda: self._pick_color("text_color"))
        self.font_size_spin.valueChanged.connect(lambda _: self._on_style_changed())
        self.font_combo.currentFontChanged.connect(lambda _: self._on_style_changed())
        self.font_weight_combo.currentIndexChanged.connect(lambda _: self._on_style_changed())
        self.italic_check.toggled.connect(lambda _: self._on_style_changed())
        self.script_combo.currentIndexChanged.connect(lambda _: self._on_style_changed())
        self.bg_check.toggled.connect(lambda _: self._on_style_changed())
        self.bg_fill_btn.clicked.connect(lambda: self._pick_color("bg_fill"))
        self.bg_border_btn.clicked.connect(lambda: self._pick_color("bg_border"))
        self.bg_combo.currentIndexChanged.connect(lambda _: self._on_bg_changed())
        self.label_style_combo.currentIndexChanged.connect(
            lambda _: (self._request_group_activate("leader"),
                       self._update_bg_group_enabled(), self._on_style_changed()))
        self.above_dir_combo.currentIndexChanged.connect(
            lambda _: (self._request_group_activate("leader"), self._on_style_changed()))
        self.number_check.toggled.connect(self._on_number_toggled)
        self.number_fmt_combo.currentIndexChanged.connect(self._on_number_fmt_changed)
        self.snap_combo.currentIndexChanged.connect(self._on_snap_changed)
        self.layout_btn.clicked.connect(self._on_auto_layout)
        self.pick_btn.clicked.connect(self._on_pick_color)
        
        self.shape_border_btn.clicked.connect(lambda: self._pick_color("shape_border"))
        self.shape_fill_btn.clicked.connect(lambda: self._pick_color("shape_fill"))
        self.shape_width_spin.valueChanged.connect(lambda _: (self._request_group_activate("shape"), self._on_style_changed()))
        self.pen_color_btn.clicked.connect(lambda: self._pick_color("pen"))
        self.pen_width_spin.valueChanged.connect(lambda _: (self._request_group_activate("pen"), self._on_style_changed()))
        self.hl_color_btn.clicked.connect(lambda: self._pick_color("hl"))
        self.hl_width_spin.valueChanged.connect(lambda _: (self._request_group_activate("highlight"), self._on_style_changed()))
        self.hl_alpha_spin.valueChanged.connect(lambda _: (self._request_group_activate("highlight"), self._on_style_changed()))
        self.mosaic_block_spin.valueChanged.connect(lambda _: (self._request_group_activate("mosaic"), self._on_style_changed()))
        self.mosaic_border_check.toggled.connect(lambda _: (self._request_group_activate("mosaic"), self._on_style_changed()))
        self.emoji_size_spin.valueChanged.connect(lambda _: (self._request_group_activate("emoji"), self._on_style_changed()))
        self.apply_all_btn.clicked.connect(self.apply_to_all)

        self._groups = {"leader": g_line, "text": g_text, "canvas": g_cv,
                        "shape": g_shp, "pen": g_pen, "highlight": g_hl,
                        "mosaic": g_mos, "emoji": g_em,
                        "screenshot": g_ss, "export": g_exp}
        for _gk, _gb in self._groups.items():
            _gb.userToggled.connect(
                lambda checked, k=_gk: self._on_group_user_toggled(k, checked))

        self._refresh_color_buttons()
        self._update_bg_group_enabled()

    def _refresh_color_buttons(self) -> None:
        for btn, color, trans in (
            (self.line_color_btn, self.line_color(), False),
            (self.text_color_btn, self.text_color(), False),
            (self.bg_fill_btn, self.bg_fill_color(), False),
            (self.bg_border_btn, self.bg_border_color(), False),
            (self.shape_border_btn, self.shape_border_color(),
             self.shape_border_trans_check.isChecked()),
            (self.shape_fill_btn, self.shape_fill_color(),
             self.shape_fill_trans_check.isChecked()),
            (self.pen_color_btn, self.pen_color(), False),
            (self.hl_color_btn, self.hl_color(), False)):
            if trans:
                # v2.x 需求1：透明态保留按钮上次的非透明颜色，仅显示「透明」
                _apply_transparent_btn(btn)
                continue
            btn._color = QColor(color)
            _apply_btn_color(btn, btn._color)

    # ---------------- 当前值读取 ----------------
    def _color_of(self, btn: QPushButton, default: QColor) -> QColor:
        return getattr(btn, "_color", QColor(default))

    def line_color(self) -> QColor:
        return self._color_of(self.line_color_btn, QColor("#FF0000"))

    def text_color(self) -> QColor:
        return self._color_of(self.text_color_btn, QColor("#000000"))

    def bg_fill_color(self) -> QColor:
        return self._color_of(self.bg_fill_btn, QColor(255, 255, 255, 215))

    def bg_border_color(self) -> QColor:
        return self._color_of(self.bg_border_btn, QColor("#FF0000"))

    def shape_border_color(self) -> QColor:
        # v2.x 需求1：勾选「透明」→ 边线颜色 alpha 置 0（隐藏）
        if getattr(self.shape_border_trans_check, "isChecked",
                   lambda: False)():
            return QColor(255, 0, 0, 0)
        return self._color_of(self.shape_border_btn, QColor("#FF0000"))

    def shape_fill_color(self) -> QColor:
        # v2.x 需求1：勾选「透明」→ 填充颜色 alpha 置 0（隐藏）
        if getattr(self.shape_fill_trans_check, "isChecked",
                   lambda: False)():
            return QColor(255, 255, 255, 0)
        return self._color_of(self.shape_fill_btn, QColor(255, 255, 255, 0))

    def hl_color(self) -> QColor:
        return self._color_of(self.hl_color_btn, QColor("#FFE600"))

    def pen_color(self) -> QColor:
        return self._color_of(self.pen_color_btn, QColor("#000000"))

    def current_style(self) -> dict:
        endpoint = ENDPOINT_OPTIONS[self.endpoint_combo.currentIndex()][1]
        label_style = LABEL_STYLE_OPTIONS[self.label_style_combo.currentIndex()][1]
        above_dir = ABOVE_DIR_OPTIONS[self.above_dir_combo.currentIndex()][1]
        # 隐藏框风格（above/plain）强制无文字框
        bg_enabled = self.bg_check.isChecked() and label_style == STYLE_BOX
        return {
            "line_color": self.line_color(),
            "line_width": self.line_width_spin.value(),
            "arrow_size": float(self.arrow_size_spin.value()),
            "endpoint_style": endpoint,
            "label_style": label_style,
            "above_dir": above_dir,
            "text_gap": float(self.text_gap_spin.value()),
            "above_gap": float(self.above_gap_spin.value()),
            "text_color": self.text_color(),
            "font_size": self.font_size_spin.value(),
            "font_family": self.font_combo.currentFont().family(),
            "font_weight": FONT_WEIGHT_OPTIONS[self.font_weight_combo.currentIndex()][1],
            "font_italic": self.italic_check.isChecked(),
            "script": SCRIPT_OPTIONS[self.script_combo.currentIndex()][1],
            "bg_enabled": bg_enabled,
            "bg_fill_color": self.bg_fill_color(),
            "bg_border_color": self.bg_border_color(),
            # 形状 / 画笔
            "shape_type": self._shape_val,
            "shape_border_color": self.shape_border_color(),
            "shape_fill_color": self.shape_fill_color(),
            "shape_line_width": self.shape_width_spin.value(),
            "shape_text_pos": self._shape_textpos_map.get(
                self.shape_textpos_combo.currentIndex(), "center"),
            "pen_color": self.pen_color(),
            "pen_width": self.pen_width_spin.value(),
            "hl_color": self.hl_color(),
            "hl_width": self.hl_width_spin.value(),
            "hl_alpha": max(1, round(self.hl_alpha_spin.value() * 255 / 100)),
            "mosaic_block": self.mosaic_block_spin.value(),
            "mosaic_border": self.mosaic_border_check.isChecked(),
            "emoji_char": self._emoji_char,
            "emoji_size": self.emoji_size_spin.value(),
            "screenshot_shortcut": self.shot_key_edit.keySequence().toString(),
            "screenshot_clipboard": self.shot_clip_check.isChecked(),
            "screenshot_canvas": self.shot_canvas_check.isChecked(),
            "screenshot_border_w": self.shot_border_w_spin.value(),
            "screenshot_no_border": self.shot_no_border_check.isChecked(),
            "screenshot_border_color": getattr(
                self.shot_border_color_btn, "_color", QColor("#2F80ED")).name(),
        }

    def current_bg_color(self):
        """当前画布背景色；顶部「无」返回 None（透明/无背景）。"""
        idx = self.bg_combo.currentIndex()
        if idx <= 0:
            return None
        if idx == self.bg_combo.count() - 1:
            return QColor(self._bg_custom_color)
        return QColor(BG_OPTIONS[idx - 1][1])

    def current_number_format(self) -> str:
        return NUM_FMT_OPTIONS[self.number_fmt_combo.currentIndex()][1]

    def current_snap_mode(self) -> str:
        return SNAP_OPTIONS[self.snap_combo.currentIndex()][1]

    def _sync_canvas_state(self) -> None:
        """把面板的全局状态同步到画布（背景色/序号开关与格式/对齐模式）。"""
        if self.canvas is None:
            return
        self.canvas.set_bg_color(self.current_bg_color())
        self.canvas.number_enabled = self.number_check.isChecked()
        self.canvas.number_format = self.current_number_format()
        self.canvas.snap_mode = self.current_snap_mode()
        # 序号仅在开启时重排，避免恢复时清空已有序号（序号丢失修复）
        if self.canvas.number_enabled:
            self.canvas.renumber()

    # ---------------- 交互 ----
    def _on_bg_changed(self) -> None:
        if self._syncing:
            return
        idx = self.bg_combo.currentIndex()
        # 底部「自定义」：弹出标准色盘；取消则回退到顶部「无」
        if idx == self.bg_combo.count() - 1:
            color = QColorDialog.getColor(
                QColor(self._bg_custom_color), self, "自定义背景色")
            if not color.isValid():
                self._syncing = True
                self.bg_combo.setCurrentIndex(0)
                self._syncing = False
            else:
                self._bg_custom_color = QColor(color)
        # 用户手动选了背景（无/预设/自定义）后，不再随主题自动切换
        self._bg_auto_follow = False
        if self.canvas is not None:
            self.canvas.set_bg_color(self.current_bg_color())

    def apply_theme_follow_bg(self, dark: bool) -> None:
        """主题切换时按需求5自动套用背景：明亮→浅灰、暗黑→深灰；
        仅在用户尚未手动选择背景（_bg_auto_follow）时生效。"""
        if not self._bg_auto_follow:
            return
        label = BG_AUTO_DARK if dark else BG_AUTO_LIGHT
        off = next((i for i, (l, _) in enumerate(BG_OPTIONS) if l == label), 0)
        self._syncing = True
        self.bg_combo.setCurrentIndex(1 + off)
        self._syncing = False
        if self.canvas is not None:
            self.canvas.set_bg_color(self.current_bg_color())

    def _pick_color(self, key: str) -> None:
        if self._syncing:
            return
        current = {
            "line_color": self.line_color(),
            "text_color": self.text_color(),
            "bg_fill": self.bg_fill_color(),
            "bg_border": self.bg_border_color(),
            "shape_border": self.shape_border_color(),
            "shape_fill": self.shape_fill_color(),
            "pen": self.pen_color(),
            "hl": self.hl_color(),
        }[key]
        color = QColorDialog.getColor(current, self, "选择颜色")
        if not color.isValid():
            return
        self.canvas.push_undo("style") if self.canvas else None
        if key == "line_color":
            self.line_color_btn._color = QColor(color)
        elif key == "text_color":
            self.text_color_btn._color = QColor(color)
        elif key == "bg_fill":
            self.bg_fill_btn._color = QColor(color)
        elif key == "bg_border":
            self.bg_border_btn._color = QColor(color)
        elif key == "shape_border":
            self.shape_border_btn._color = QColor(color)
            # 用户主动取色 = 取消透明（恢复显示该颜色）
            self.shape_border_trans_check.setChecked(False)
        elif key == "shape_fill":
            self.shape_fill_btn._color = QColor(color)
            self.shape_fill_trans_check.setChecked(False)
        elif key == "pen":
            self.pen_color_btn._color = QColor(color)
        elif key == "hl":
            self.hl_color_btn._color = QColor(color)
        self._refresh_color_buttons()
        self._request_group_activate(
            {"line_color": "leader", "shape_border": "shape",
             "shape_fill": "shape", "pen": "pen",
             "hl": "highlight"}.get(key, ""))
        self._apply_to_selection()

    def _pick_shot_border_color(self) -> None:
        """截图边框颜色选择（独立于标注样式，不联动画布）。"""
        cur = getattr(self.shot_border_color_btn, "_color", QColor("#2F80ED"))
        color = QColorDialog.getColor(cur, self, "选择截图边框颜色")
        if not color.isValid():
            return
        self.shot_border_color_btn._color = QColor(color)
        _apply_btn_color(self.shot_border_color_btn, self.shot_border_color_btn._color)

    def _set_hl_preset(self, hexc: str) -> None:
        if self._syncing:
            return
        self.hl_color_btn._color = QColor(hexc)
        self._refresh_color_buttons()
        self._request_group_activate("highlight")
        self._on_style_changed()

    def _on_style_changed(self) -> None:
        if self._syncing or self.canvas is None:
            return
        self.canvas.push_undo("style")
        self._apply_to_selection()

    def _on_number_toggled(self, checked: bool) -> None:
        if self._syncing or self.canvas is None:
            return
        self.canvas.set_number_enabled(bool(checked))

    def _on_number_fmt_changed(self, _idx: int) -> None:
        if self._syncing or self.canvas is None:
            return
        fmt = NUM_FMT_OPTIONS[self.number_fmt_combo.currentIndex()][1]
        self.canvas.set_number_format(fmt)

    def _on_snap_changed(self, _idx: int) -> None:
        if self._syncing or self.canvas is None:
            return
        self.canvas.snap_mode = SNAP_OPTIONS[self.snap_combo.currentIndex()][1]

    def _sync_layout_spins(self) -> None:
        """把行距/列距/对齐方式面板值同步到画布布局参数。"""
        if self.canvas is None:
            return
        self.canvas.layout_row_lines = self.layout_row_spin.value()
        self.canvas.layout_col_chars = self.layout_col_spin.value()
        # 同步水平对齐方式
        h_idx = self.layout_h_align_combo.currentIndex()
        self.canvas.layout_h_align = ["left", "center", "right"][h_idx]
        # 同步垂直对齐方式
        v_idx = self.layout_v_align_combo.currentIndex()
        self.canvas.layout_v_align = ["top", "center", "bottom"][v_idx]

    def _on_transparent_bg_changed(self, checked: bool) -> None:
        if self.canvas is not None:
            self.canvas.transparent_bg = checked

    def _on_auto_layout(self) -> None:
        if self.canvas is not None:
            self._sync_layout_spins()
            self.canvas.auto_layout()

    def _on_pick_color(self) -> None:
        if self.canvas is not None:
            self.canvas.begin_pick_color()

    def _update_bg_group_enabled(self) -> None:
        """标注风格为「现有样式（文字框）」时，背景框相关控件可用；隐藏框风格时禁用。
        「横线方向」仅对「文字在红线上方」风格生效。"""
        label_style = LABEL_STYLE_OPTIONS[self.label_style_combo.currentIndex()][1]
        enabled = label_style == STYLE_BOX
        for w in (self.bg_check, self.bg_fill_btn, self.bg_border_btn):
            w.setEnabled(enabled)
        self.above_dir_combo.setEnabled(label_style == STYLE_ABOVE)

    def _apply_to_selection(self) -> None:
        if self.canvas is None:
            return
        sel = self.canvas.selected_items()
        st = self.current_style()
        pixmap = self.canvas.pixmap
        for item in sel:
            if isinstance(item, LeaderLineItem):
                item.line_color = QColor(st["line_color"])
                item.line_width = int(st["line_width"])
                item.arrow_size = float(st["arrow_size"])
                # 横线方向：选「自动」时按该标注文字所在图片左右半区解析
                if st["above_dir"] == ABOVE_DIR_AUTO:
                    mid = pixmap.width() / 2.0 if pixmap is not None else 0.0
                    item.above_dir = (ABOVE_DIR_RIGHT
                                      if item.text_point.x() > mid
                                      else ABOVE_DIR_LEFT)
                else:
                    item.above_dir = st["above_dir"]
            item.apply_style(st)
        for item in sel:
            if isinstance(item, ShapeItem):
                item.shape = st["shape_type"]
                item.border_color = QColor(st["shape_border_color"])
                item.fill_color = QColor(st["shape_fill_color"])
                item.line_width = int(st["shape_line_width"])
                item.text_pos = st.get("shape_text_pos", "center")
            elif isinstance(item, PenItem):
                item.pen_color = QColor(st["pen_color"])
                item.pen_width = int(st["pen_width"])
            elif isinstance(item, HighlightItem):
                item.hl_color = QColor(st["hl_color"])
                item.hl_width = int(st["hl_width"])
                item.hl_alpha = int(st["hl_alpha"])
            elif isinstance(item, MosaicItem):
                item.block_size = max(2, int(st["mosaic_block"]))
                item.show_border = bool(st.get("mosaic_border", True))
            elif isinstance(item, EmojiItem):
                item.emoji = st["emoji_char"]
                item.text_content = st["emoji_char"]
                item.font_size = max(8, int(st["emoji_size"]))
        self.canvas.update()
        self.styleChanged.emit()

    # ---------------- 回填 ----------------
    def sync_from_selection(self, items: list) -> None:
        self._syncing = True
        if items:
            it = items[0]
            if isinstance(it, LeaderLineItem):
                self.line_color_btn._color = QColor(it.line_color)
                self.line_width_spin.setValue(it.line_width)
                self.arrow_size_spin.setValue(int(it.arrow_size))
                idx = next((i for i, (_, v) in enumerate(ENDPOINT_OPTIONS)
                            if v == it.endpoint_style), 0)
                self.endpoint_combo.setCurrentIndex(idx)
                idx = next((i for i, (_, v) in enumerate(LABEL_STYLE_OPTIONS)
                            if v == it.label_style), 0)
                self.label_style_combo.setCurrentIndex(idx)
                idx = next((i for i, (_, v) in enumerate(ABOVE_DIR_OPTIONS)
                            if v == it.above_dir), 0)
                self.above_dir_combo.setCurrentIndex(idx)
                self.text_gap_spin.setValue(int(getattr(it, "text_gap", 5)))
                self.above_gap_spin.setValue(int(getattr(it, "above_gap", 5)))
            self.text_color_btn._color = QColor(it.text_color)
            self.font_size_spin.setValue(it.font_size)
            self.font_combo.setCurrentFont(QFont(it.font_family))
            idx = next((i for i, (_, w) in enumerate(FONT_WEIGHT_OPTIONS)
                        if w == it.font_weight), 1)
            self.font_weight_combo.setCurrentIndex(idx)
            self.italic_check.setChecked(bool(it.font_italic))
            idx = next((i for i, (_, s) in enumerate(SCRIPT_OPTIONS)
                        if s == it.script), 0)
            self.script_combo.setCurrentIndex(idx)
            self.bg_check.setChecked(it.bg_enabled)
            self.bg_fill_btn._color = QColor(it.bg_fill_color)
            self.bg_border_btn._color = QColor(it.bg_border_color)
            if isinstance(it, ShapeItem):
                idx = next((i for i, (_, v) in enumerate(SHAPE_OPTIONS)
                            if v == it.shape), 0)
                self._set_shape_val(SHAPE_OPTIONS[idx][1])
                # v2.x 需求1：边线/填充为全透明 → 勾选「透明」；
                # 非透明才回填按钮颜色（透明态保留上次颜色供取消后恢复）
                if it.border_color.alpha() == 0:
                    self.shape_border_trans_check.setChecked(True)
                else:
                    self.shape_border_trans_check.setChecked(False)
                    self.shape_border_btn._color = QColor(it.border_color)
                if it.fill_color.alpha() == 0:
                    self.shape_fill_trans_check.setChecked(True)
                else:
                    self.shape_fill_trans_check.setChecked(False)
                    self.shape_fill_btn._color = QColor(it.fill_color)
                self.shape_width_spin.setValue(it.line_width)
                _tp = getattr(it, "text_pos", "center")
                _tpi = next((k for k, v in self._shape_textpos_map.items()
                             if v == _tp), 0)
                self.shape_textpos_combo.setCurrentIndex(_tpi)
            elif isinstance(it, PenItem):
                self.pen_color_btn._color = QColor(it.pen_color)
                self.pen_width_spin.setValue(it.pen_width)
            elif isinstance(it, HighlightItem):
                self.hl_color_btn._color = QColor(it.hl_color)
                self.hl_width_spin.setValue(it.hl_width)
                self.hl_alpha_spin.setValue(round(it.hl_alpha * 100 / 255))
            elif isinstance(it, MosaicItem):
                self.mosaic_block_spin.setValue(it.block_size)
                self.mosaic_border_check.setChecked(getattr(it, "show_border", True))
            elif isinstance(it, EmojiItem):
                self._emoji_char = it.emoji
                for _c, _b in getattr(self, '_emoji_buttons', {}).items():
                    _b.setChecked(_c == it.emoji)
                self.emoji_size_spin.setValue(it.font_size)
            self._refresh_color_buttons()
            self._update_bg_group_enabled()
        self._syncing = False

    # ---------------- 参数恢复（settings.json）----------------
    def set_style(self, st: dict) -> None:
        """按持久化样式字典恢复全部面板控件（不触发撤销/应用）。"""
        if not st:
            return
        self._syncing = True
        try:
            if "line_color" in st:
                self.line_color_btn._color = QColor(st["line_color"])
            if "line_width" in st:
                self.line_width_spin.setValue(int(st["line_width"]))
            if "arrow_size" in st:
                self.arrow_size_spin.setValue(int(st["arrow_size"]))
            if "endpoint_style" in st:
                idx = next((i for i, (_, v) in enumerate(ENDPOINT_OPTIONS)
                            if v == st["endpoint_style"]), 0)
                self.endpoint_combo.setCurrentIndex(idx)
            if "label_style" in st:
                idx = next((i for i, (_, v) in enumerate(LABEL_STYLE_OPTIONS)
                            if v == st["label_style"]), 0)
                self.label_style_combo.setCurrentIndex(idx)
            if "above_dir" in st:
                idx = next((i for i, (_, v) in enumerate(ABOVE_DIR_OPTIONS)
                            if v == st["above_dir"]), 0)
                self.above_dir_combo.setCurrentIndex(idx)
            if "text_gap" in st:
                self.text_gap_spin.setValue(int(float(st["text_gap"])))
            if "above_gap" in st:
                self.above_gap_spin.setValue(int(float(st["above_gap"])))
            if "text_color" in st:
                self.text_color_btn._color = QColor(st["text_color"])
            if "font_size" in st:
                self.font_size_spin.setValue(int(st["font_size"]))
            if "font_family" in st:
                self.font_combo.setCurrentFont(QFont(st["font_family"]))
            if "font_weight" in st:
                idx = next((i for i, (_, w) in enumerate(FONT_WEIGHT_OPTIONS)
                            if w == int(st["font_weight"])), 1)
                self.font_weight_combo.setCurrentIndex(idx)
            if "font_italic" in st:
                self.italic_check.setChecked(bool(st["font_italic"]))
            if "script" in st:
                idx = next((i for i, (_, s) in enumerate(SCRIPT_OPTIONS)
                            if s == st["script"]), 0)
                self.script_combo.setCurrentIndex(idx)
            if "bg_enabled" in st:
                self.bg_check.setChecked(bool(st["bg_enabled"]))
            if "bg_fill_color" in st:
                self.bg_fill_btn._color = QColor(st["bg_fill_color"])
            if "bg_border_color" in st:
                self.bg_border_btn._color = QColor(st["bg_border_color"])
            if "shape_type" in st:
                idx = next((i for i, (_, v) in enumerate(SHAPE_OPTIONS)
                            if v == st["shape_type"]), 0)
                self._set_shape_val(SHAPE_OPTIONS[idx][1])
            if "shape_border_color" in st:
                _bc = QColor(st["shape_border_color"])
                # v2.x 需求1：恢复时同步「透明」勾选态
                self.shape_border_trans_check.setChecked(_bc.alpha() == 0)
                if _bc.alpha() != 0:
                    self.shape_border_btn._color = _bc
            if "shape_fill_color" in st:
                _fc = QColor(st["shape_fill_color"])
                self.shape_fill_trans_check.setChecked(_fc.alpha() == 0)
                if _fc.alpha() != 0:
                    self.shape_fill_btn._color = _fc
            if "shape_line_width" in st:
                self.shape_width_spin.setValue(int(st["shape_line_width"]))
            if "shape_text_pos" in st:
                _tpi = next((k for k, v in self._shape_textpos_map.items()
                             if v == st["shape_text_pos"]), 0)
                self.shape_textpos_combo.setCurrentIndex(_tpi)
            if "pen_color" in st:
                self.pen_color_btn._color = QColor(st["pen_color"])
            if "pen_width" in st:
                self.pen_width_spin.setValue(int(st["pen_width"]))
            if "hl_color" in st:
                self.hl_color_btn._color = QColor(st["hl_color"])
            if "hl_width" in st:
                self.hl_width_spin.setValue(int(st["hl_width"]))
            if "hl_alpha" in st:
                self.hl_alpha_spin.setValue(round(int(st["hl_alpha"]) * 100 / 255))
            if "mosaic_block" in st:
                self.mosaic_block_spin.setValue(int(st["mosaic_block"]))
            if "mosaic_border" in st:
                self.mosaic_border_check.setChecked(bool(st["mosaic_border"]))
            if "emoji_size" in st:
                self.emoji_size_spin.setValue(int(st["emoji_size"]))
            if "emoji_char" in st:
                self._emoji_char = st["emoji_char"]
                for _c, _b in getattr(self, '_emoji_buttons', {}).items():
                    _b.setChecked(_c == self._emoji_char)
                # 需求7：恢复到附加表情时自动展开「更多」，否则选中项不可见
                _cur_btn = self._emoji_buttons.get(self._emoji_char)
                if _cur_btn is not None and not _cur_btn.isVisible():
                    self._emoji_more_open = True
                    for _b in self._emoji_extra_widgets:
                        _b.setVisible(True)
                    self._emoji_more_btn.setText("收起 ▴")
            if "screenshot_shortcut" in st:
                self.shot_key_edit.setKeySequence(QKeySequence(st["screenshot_shortcut"] or ""))
            if "screenshot_clipboard" in st:
                self.shot_clip_check.setChecked(bool(st["screenshot_clipboard"]))
            if "screenshot_canvas" in st:
                self.shot_canvas_check.setChecked(bool(st["screenshot_canvas"]))
            if "screenshot_border_w" in st:
                self.shot_border_w_spin.setValue(int(st["screenshot_border_w"]))
            if "screenshot_no_border" in st:
                self.shot_no_border_check.setChecked(bool(st["screenshot_no_border"]))
            if "screenshot_border_color" in st:
                try:
                    c = QColor(st["screenshot_border_color"])
                    self.shot_border_color_btn._color = c
                    _apply_btn_color(self.shot_border_color_btn, c)
                except Exception:
                    pass
            if "jpg_quality" in st:
                self.jpg_quality_spin.setValue(int(st["jpg_quality"]))
            if "bg_auto_follow" in st:
                self._bg_auto_follow = bool(st["bg_auto_follow"])
            if "bg_custom_color" in st:
                self._bg_custom_color = QColor(st["bg_custom_color"])
            if "bg_index" in st:
                idx = int(st["bg_index"])
                if 0 <= idx < self.bg_combo.count():
                    self.bg_combo.setCurrentIndex(idx)
            if "number_enabled" in st:
                self.number_check.setChecked(bool(st["number_enabled"]))
            if "number_format" in st:
                idx = next((i for i, (_, v) in enumerate(NUM_FMT_OPTIONS)
                            if v == st["number_format"]), 0)
                self.number_fmt_combo.setCurrentIndex(idx)
            if "snap_mode" in st:
                idx = next((i for i, (_, v) in enumerate(SNAP_OPTIONS)
                            if v == st["snap_mode"]), 0)
                self.snap_combo.setCurrentIndex(idx)
        finally:
            self._syncing = False
            self._refresh_color_buttons()
            self._update_bg_group_enabled()

    # ---------------- 形状菜单 / 分组折叠 / 应用到全部 ----------------
    def _set_shape(self, val: str) -> None:
        """用户从形状菜单选择：切换当前形状并触发样式变更。"""
        if val not in {v for _, v in SHAPE_OPTIONS}:
            val = SHAPE_OPTIONS[0][1]
        self._set_shape_val(val)
        self._request_group_activate("shape")
        self._on_style_changed()

    def _set_shape_val(self, val: str) -> None:
        """内部同步形状值（不触发样式变更）：勾选对应按钮并展开其所属分类。"""
        if val not in {v for _, v in SHAPE_OPTIONS}:
            val = SHAPE_OPTIONS[0][1]
        self._shape_val = val
        for v, b in getattr(self, "_shape_buttons", {}).items():
            b.setChecked(v == val)
        # 自动展开该形状所属分类（不折叠其它分类，避免用户已展开的被收起）
        cat = _SHAPE_CATEGORY_OF.get(val)
        if cat is not None and hasattr(self, "_shape_cat_headers"):
            _h = self._shape_cat_headers.get(cat)
            _w = self._shape_cat_widgets.get(cat)
            if _h is not None and not _h.isChecked():
                _h.setChecked(True)   # toggled 信号会负责显示网格
            elif _w is not None:
                _w.setVisible(True)

    def _on_group_user_toggled(self, key: str, checked: bool) -> None:
        # 用户手动展开某组 -> 请求主窗口切换到对应工具模式（折叠不切）
        if checked:
            self.groupActivated.emit(key)
        self.groupsChanged.emit()

    def _request_group_activate(self, key: str) -> None:
        # 用户主动操作某工具组控件 -> 请求切换到对应模式；
        # _syncing（选中回填/设置恢复）期间不触发，避免误切模式。
        if not key or self._syncing:
            return
        self.groupActivated.emit(key)

    def group_states(self) -> dict:
        """返回各折叠组当前展开/折叠状态（用于持久化）。"""
        return {k: g.is_expanded() for k, g in self._groups.items()}

    def set_group_states(self, states: dict) -> None:
        """恢复各折叠组展开状态（程序化，不触发工具模式切换）。"""
        if not isinstance(states, dict):
            return
        for k, v in states.items():
            g = self._groups.get(k)
            if g is not None:
                g.set_expanded(bool(v))

    def expand_group(self, key: str) -> None:
        """展开指定设置组（Photoshop 风格：选中相关类型时才打开）。"""
        g = self._groups.get(key)
        if g is not None:
            g.set_expanded(True)
        self.groupsChanged.emit()

    def any_expanded(self) -> bool:
        """是否存在至少一个展开的功能组。"""
        return any(g.is_expanded() for g in self._groups.values())

    def collapse_all(self) -> None:
        """程序化折叠全部功能组（不触发工具模式切换）。"""
        for g in self._groups.values():
            g.set_expanded(False)

    def expand_all(self) -> None:
        """程序化展开全部功能组（不触发工具模式切换）。"""
        for g in self._groups.values():
            g.set_expanded(True)

    def apply_to_all(self) -> None:
        """把当前面板样式应用到全部同类标注元素。"""
        if self.canvas is None:
            return
        self.canvas.apply_style_to_all(self.current_style())
