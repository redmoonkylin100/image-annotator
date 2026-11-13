# 图片快速标注工具（image-annotator）

基于 **PyQt6** 的 Windows 桌面图片快速标注工具。面向「在图片四周加引线标注 / 序号 / 文本 / 形状 / 手绘」的高频场景，内置磁吸对齐、一键自动布局、图层、历史、明暗主题、自动保存、透明背景导出等能力。

- 语言：Python 3.13（最低 3.10+，使用了 `X | None` 类型注解）
- GUI 框架：PyQt6（开发版本 6.10.2，requirements 要求 >=6.6）
- 仅依赖：`PyQt6`、`Pillow`（其余全部标准库）
- 入口：`python main.py`
- 应用名：图片标注大师；组织名：LocalTools

---

## 0. 一分钟运行 / 打包

```bash
py -3.13 -m venv venv                                  # ① 建虚拟环境
venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller -i https://mirrors.aliyun.com/pypi/simple/
                                                       # ② 装依赖（国内镜像，PyQt6+Pillow+PyInstaller）
venv\Scripts\python.exe main.py                       # ③ 源码运行
venv\Scripts\python.exe 一键打包.py --debug            # ④ 打包：dist\图片标注工具.exe（单文件、无控制台）
```

- **一键打包.py**：双击即用 venv 的 PyInstaller 打包（自动用 pythonw 后台静默执行、无 cmd 黑窗，日志写「打包日志.txt」；`--debug` 参数可实时看日志）；产物 `dist\图片标注工具.exe` 为独立单文件（onefile）、`console=False` 不弹黑框。
- **双图标**：exe 文件图标嵌入 `1.ico`（spec `icon='1.ico'`）；`2.ico` 与 `1.ico` 一起经 spec `datas` 嵌入 exe，运行时 `_resource_path()` 从嵌入资源取图，窗口/任务栏/系统托盘统一显示 `2.ico`（缺失时回退 `1.ico`）。打包后 exe **不再依赖外部 ico 文件**。
- **数据目录**：打包后所有持久化数据（`autosave/`、`settings.json`、`items.json`、`image.png` 等）一律写在 **exe 所在目录**（源码运行时为项目根目录），**不写用户目录、不写系统临时目录**（`settings._app_base_dir` / `autosave._app_base_dir` 的 frozen 分支返回 `dirname(sys.executable)`，已实测验证）。

---

## 1. 目录结构（精确）

```
image-annotator/
├── main.py                     # 入口：安装 C 层 stderr 过滤器 → QApplication → MainWindow
├── requirements.txt            # PyQt6>=6.6, Pillow>=10.0
├── 1.ico                       # exe 文件图标（spec icon= 嵌入）
├── 2.ico                       # 窗口/任务栏/托盘图标（spec datas 嵌入）
├── 图片标注工具.spec            # PyInstaller 配置（单文件、无控制台、icon=1.ico、datas=两个 ico）
├── 一键打包.py                 # 使用 venv 的 PyInstaller 一键打包（双击静默、日志打包日志.txt）
├── venv/                       # 虚拟环境（PyQt6/Pillow/PyInstaller，国内镜像安装）
├── README.md
├── annotator/
│   ├── __init__.py
│   ├── window.py              # 主窗口：主工具栏、可停靠工具面板、主题、托盘、左侧面板、项目存取、信号接线
│   ├── canvas.py              # 画布：坐标变换、9 种模式鼠标交互 + 截图动作接线、磁吸、自动布局、撤销重做、就地输入、导出渲染
│   ├── items.py               # 元素：Layer/AnnotationItem/LeaderLineItem/TextItem/ShapeItem/PenItem/HighlightItem/MosaicItem/EmojiItem + 形状路径
│   ├── panel.py               # 右侧样式面板：CollapsibleBox 折叠组 + StylePanel（引线/文字/画布/形状/画笔/荧光笔/马赛克/表情/截图设置/导出 10 组）
│   ├── screenshot.py          # 自由截图：ScreenshotOverlay 全屏框选遮罩（独立模块，见 §18）
│   ├── layers_panel.py        # 图层面板（增删/显隐/拖拽排序/右键重命名/选中本层）
│   ├── history_panel.py       # 历史面板（按创建顺序列元素，单击选中、双击改字、右键菜单）
│   ├── autosave.py            # 自动保存 + 元素/图层序列化/反序列化 + .anno 项目读写基础
│   ├── settings.py            # settings.json 读写（界面/样式参数持久化）
│   └── rulers.py              # 水平/垂直标尺 RulerBar
└── autosave/                  # 运行时自动生成（源码运行在项目根；打包后在 exe 同目录）
    ├── settings.json          # 界面布局 + 上次样式参数
    ├── items.json             # 自动恢复：元素 + 图层
    └── image.png              # 自动恢复：上次图片

打包相关：`dist/图片标注工具.exe`（产物）、`build/`（中间文件）、`打包日志.txt`（一键打包日志，可删除）。
`tests/smoke_test*.py` 是历次迭代的离屏回归脚本，不属于运行时依赖。

> `tests/smoke_test*.py` 是历次迭代的离屏回归脚本，不属于运行时依赖。

---

## 2. 总体架构与数据流

```
MainWindow (window.py)
 ├─ 顶部 QToolBar「主工具栏」（打开/保存/撤销/导出/主题…）
 ├─ QSplitter(水平)
 │   ├─ left_box   ：HistoryPanel(上) + LayerPanel(下)，用垂直 QSplitter 分高度
 │   ├─ center_box ：左上角块 + 水平标尺 + 垂直标尺 + AnnotationCanvas
 │   └─ right_box  ：QScrollArea 包裹 StylePanel（10 个 CollapsibleBox）
 └─ QDockWidget「tool_dock」：模式切换工具面板（可停靠/浮动，见 §7）
```

关键关系：

1. `StylePanel` 是**样式提供者**：`canvas.set_style_provider(panel.current_style)`，画布每次新建元素时调用 `self.style_provider()` 拿到当前样式 dict（`canvas._new_style()`）。
2. 画布通过 **pyqtSignal** 向外通知：`imageLoaded / itemSelectionChanged / itemsChanged / cursorMoved(x,y) / modeChanged / viewChanged / layersChanged`，主窗口在 `_connect_signals()` 里接线，驱动历史/图层/状态栏刷新与自动保存。
3. 所有元素坐标都是**图片坐标**（原点在原图左上角、单位像素，与导出一致）；画布负责 `view = image*scale + offset` 双向变换：`view_to_image()` / `image_to_view()`，缩放 `wheelEvent`、平移（中键/右键）。
4. 任何改动走**撤销栈**：改动前 `push_undo(tag)` 对 `self.items` 做深拷贝快照（`MAX_UNDO=100`），Ctrl+Z/Y 撤销重做。

---

## 3. 元素对象模型（items.py）

所有坐标单位为图片像素。字体统一 `FONT_FAMILY="Microsoft YaHei"`，字号用 **setPixelSize**（不是 pointSize），保证画布与导出一致。

### 3.1 Layer
- 字段：`id`（类级自增 `_id_counter`）、`name`、`visible`。
- `canvas.layers` 列表顺序 = 绘制顺序（底层在前）；图层面板显示时 `reversed()`（顶层在上）。

### 3.2 AnnotationItem（基类）
通用文字块字段：`id, selected, text_content, font_size, text_color(QColor), font_family, font_weight(50), font_italic, script(normal/super/sub), bg_enabled, bg_fill_color, bg_border_color, layer_id`。

- 文字内边距常量：`TEXT_PAD_X=7`、`TEXT_PAD_Y=4`。
- `text_rect_at_origin()`：用 `QFontMetrics.boundingRect` 算文字块矩形（含 padding），左上角恒为 (0,0)。
- `paint_text_only()`：只画文字（左右各留 TEXT_PAD_X，保证左右对称）；上标/下标由 `script_offset()` 偏移、字号 ×0.72。
- `paint_selection()`：选中蓝虚线框；`paint_number()`：序号画在文字块正上方。
- `apply_style(dict)`：把样式 dict 套到通用字段；若是 LeaderLineItem 还会写 `endpoint_style/label_style/above_dir/text_gap/above_gap`。
- **字号兜底**：`make_font / make_item_font / apply_style / __init__` 对非法/0/负字号一律回退 18，避免 `QFont::setPointSize <=0` 警告。

### 3.3 LeaderLineItem（引线标注，核心）
构造：`LeaderLineItem(target_point, text_point, text, line_color, line_width, arrow_size, font_size, text_color, endpoint_style, label_style, text_gap=5.0, above_gap=5.0)`。

- `target_point`：箭头指向的目标点；`text_point`：文字块左上角（旧 STYLE_ABOVE 时为文字中心）。
- `endpoint_style`：`arrow` 三角 / `dot` 圆点 / `circle` 空心圆 / `none` 无（none 时线帽 FlatCap，不画端点和选中把手）。
- `number / number_fmt`：引线序号与格式（circle ① / paren （1）/ plain 1，`format_number()`）。
- `above_dir`：横线方向 `auto/left/right`（默认创建时由画布按半区解析，单击可翻转，见 §6.3）。
- `text_gap`（面板名「空白间隙」）：引线拐点/横线与文字之间的水平留白（px，默认 5，面板 0–20 可调）；middle/no_line 的文字-横线间隙也用它。
- `above_gap`（面板名「上下间隙」，r23 新增）：仅 above_text/below_text 时文字与横线的**垂直**距离（`line_y`），px 默认 5、面板 0–20，与 text_gap 相互独立。
- `hit_test(pos,tol)` 返回命中部位：`'target'`（箭头端点）/`'line'`（斜线或横线）/`'text'`（文字块）/ None。
- `move_by(dx,dy,part)`：part 含 line/target 移动 target_point；含 line/text 移动 text_point（拖横线会同时移动文字和目标点，拖文字只移文字）。

#### 四种现行引线样式（`label_style`，面板下拉仅此 4 项）
几何统一由 `_get_leader_geometry(style)` 返回 `(corner拐点, 横线起点line_start, 横线终点line_end, 文字矩形r)`。先判定 `horizontal_leader = |dx|>=|dy|`（文字相对目标是左右还是上下）、`text_on_right = dx>0`。

| 存储值 | 名称 | 规则 |
|---|---|---|
| `above_text` | 文字在线上方（线长对齐文字） | 横线在文字**下方** `r.bottom()+above_gap`，与文字**等宽**；斜线 target→拐点，横线拐点→另一端 |
| `middle_text` | 文字在线中间（固定线长） | 横线在文字垂直中线 `r.center().y()`，**固定长 15px**，位于文字与目标之间、与文字留 text_gap；文字从横线结束后开始 |
| `below_text` | 文字在线下方（线长对齐文字） | 横线在文字**上方** `r.top()-above_gap`，与文字等宽，其余同 above_text |
| `no_line` | 无横线 | 套用 middle 几何，仅把固定横线长度改为 **1px**（斜线/引导线保留，并非真的没有引导线） |

- **above_text/below_text 的拐点端由 `above_dir` 决定**：`left` 拐点在文字左端、`right` 在右端；`auto` 时水平引线取「靠近目标点」一侧、垂直引线默认左端。水平引线时拐点与文字边缘留 `text_gap`（gx=空白间隙），垂直引线 gx=0；横线与文字的垂直距离用独立的 `above_gap`（上下间隙）。横线不超过拐点，斜线与横线在拐点相交。
- middle/no_line：水平引线时横线在文字靠近目标一侧外（文字在右→横线在左），垂直引线时默认在文字左侧。
- 旧常量 `STYLE_BOX="box"/STYLE_ABOVE="above"/STYLE_PLAIN="plain"` 仍保留用于兼容旧数据，但已从下拉移除；`_above_geometry()` 仅服务旧 above。
- 绘制方法：`_paint_above_text/_paint_middle_text/_paint_below_text/_paint_no_line`，统一顺序：画线（斜线+横线）→ `_paint_endpoint` → `paint_text_only` → `paint_number` → 选中把手。

### 3.4 TextItem / ShapeItem / PenItem
- **TextItem**：纯文本批注，无引线，`pos` 即左上角，可自由拖。
- **ShapeItem**：形状，`p1/p2` 对角点 + `shape` 类型 + 边框/填充色 + 线宽。11 种形状由 `shape_path(shape, rect)` 生成 QPainterPath：矩形/圆角矩形/椭圆/三角形/直角三角形/菱形/五边形/六边形/五角星/右箭头，多边形都 `closeSubpath()` 保证封闭；非法 NaN 几何兜底为矩形。**空心弧（SHAPE_OPEN_ARC，r31 修复）**为 270° 环形扇段（Office Block Arc 风格的粗 C 形弧带，外弧 + 端面 + 反向内弧 + 闭合，内圈为外框 52%）；**空 QPainterPath 直接 `arcTo` 会先从 (0,0) 拉一条直线到弧起点**（旧实现因此被扯到画布左上角、形成细长三角），必须先 `moveTo(外弧起点)`，内外弧端点用与 arcTo 相同的角度公式（`x=cx+rx·cosθ, y=cy−ry·sinθ`）精确对齐。**直线（SHAPE_LINE）不走 shape_path**：严格 `moveTo(p1)→lineTo(p2)`（r23 前用归一化矩形对角线，往右上/左下拖会被换成另一条对角线、起点看似乱跑，已修）；hit_test 逐段点到线段距离。r23 起直线为**点击式连续折线**：多点时存 `points: list[QPointF]`（≥2 逐段 drawPolyline，rect()=全部顶点 boundingRect、move_by 整体平移），两点直线 points=None、仅用 p1/p2；序列化时仅 ≥3 点写 `line_points`，两点保持旧格式。
- **PenItem**：自由手绘，`points: list[QPointF]` + 颜色 + 线宽。

### 3.5 HighlightItem / MosaicItem / EmojiItem（本轮新增）
- **HighlightItem（荧光笔）**：半透明粗自由曲线。`points: list[QPointF]` + `hl_color`(QColor 基色) + `hl_width`(默认22) + `hl_alpha`(0–255，面板按不透明度%换算，默认31%≈79)。圆头圆角 `drawPolyline`（CapRound/JoinRound），单点也画圆点；hit_test 用点到线段距离+半宽；move_by 平移所有点；export_bounds=点 bbox+半宽。
- **MosaicItem（马赛克）**：`p1/p2` 对角点 + `block_size`(默认10) + `show_border`(bool，默认 True，是否绘制马赛克区域边框；选中提示框由基类 paint_selection 负责，与此独立)。**元素自身不持有原图**：`_source` 字段由画布在绘制时**惰性注入**当前 `canvas.pixmap`（`_paint_layers/_paint_layers_export` 里发现 `_source is not self.pixmap` 就 `set_source`），反序列化/撤销恢复后无需在各入口补绑定。`_render_mosaic()`：从原图 copy 交集整数 QRect → 缩小到 w//block → 最近邻(FastTransformation)放大回原尺寸。无原图时画半透明灰占位。**必须实现 `__deepcopy__` 且其中 `_source=None`**（QPixmap 不可 pickle，否则撤销快照崩溃，见 §16）。
- **EmojiItem（表情）**：`pos`（包围盒**中心**）+ `emoji` 字符 + `font_size`(默认40)。字体 `setFamilies(["Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji","Microsoft YaHei","sans-serif"])` 渲染彩色 emoji；text_rect 用 QFontMetrics 计算并以 pos 为中心；单击放置。

---

## 4. 九种工作模式 + 一个即时动作（canvas.py）

模式常量：`MODE_SELECT/LEADER/NUMBER/TEXT/SHAPE/PEN/HIGHLIGHT="highlight"/MOSAIC="mosaic"/EMOJI="emoji"`，默认 `MODE_LEADER`。另有**即时动作**自由截图（不是画布模式，值 `"screenshot"`，见 §18）。

| 模式 | 值 | 交互 |
|---|---|---|
| 选择 | `select` | hit_test 命中→选中；按下记录 `_drag`，移动 `move_by`，松开磁吸吸附 |
| 引线标注 | `leader` | 第 1 击定 target，第 2 击定文字位置并弹就地输入框，回车确认生成 LeaderLineItem |
| 引线序号 | `number` | 两击定 target+位置，不输入文字，自动编号 |
| 文本批注 | `text` | 单击即弹输入框，生成 TextItem |
| 形状 | `shape` | **直线（shape_type=line，r23 起）为点击式连续折线**：第 1 击定起点，线段跟随鼠标（无需按住），逐击追加顶点，Esc/回车/双击结束（丢弃未确认跟随段、保留已确认顶点，生成 1 个多点 ShapeItem，结束后仍在形状工具）；其他形状为按下定起点、拖动预览、松开生成（归一宽高均需 >3/scale） |
| 画笔 | `pen` | 按下记录轨迹点，松开生成 PenItem |
| 荧光笔 | `highlight` | 按下记录 `_hl_points`、移动追加、松开 `add_highlight_item`；光标为箭头 |
| 马赛克 | `mosaic` | 拖矩形交互（状态 `_mosaic_drag`），预览虚线框+半透明蓝，松开 `add_mosaic_item`（创建即 set_source 当前原图） |
| 表情 | `emoji` | **单击即在点击点放置**当前表情（current_style 的 emoji_char/emoji_size），无需拖拽 |

- 进入模式自动展开对应组（`MODE_GROUP`：…/highlight→highlight、mosaic→mosaic、emoji→emoji；**screenshot 不在其中**）。
- set_mode 光标默认 CrossCursor，但 `mode ∈ (SELECT, PEN, HIGHLIGHT)` 用 ArrowCursor；set_mode 清空各模式临时拖拽状态。
- **设置组 ↔ 工具模式双向联动**：进入模式会程序化展开对应组（`MODE_GROUP`，见上）；反向，用户**手动点开**某功能设置组、或**操作该组控件**（改数值/选色/选表情）时，面板发 `groupActivated(key)`，主窗口按 `GROUP_MODE` 反向映射自动切到对应工具（leader/text/shape/pen/highlight/mosaic/emoji；canvas/screenshot/export 不对应画布模式，不切）。程序化 `expand_group` 用 `CollapsibleBox._programmatic` 抑制信号、选中回填/设置恢复用 `StylePanel._syncing` 抑制，二者共同保证不产生回环、不在回填时误切模式。**引线设置组固定映射到「引线标注」MODE_LEADER（不是引线序号）**：展开引线组、或操作引线主样式控件（线宽/箭头/端点/间隙/标注风格/横线上下方/引线颜色）都会切到引线标注；但序号专属控件（启用序号、序号格式）不触发切换，避免在序号模式下被跳走。文字设置组同时服务引线与文本，其控件不强制切模式。
- 序号开关 `number_enabled`、格式 `number_format`；`reorder_by_number()` 支持历史面板调整序号顺序。
- 就地输入框 `_InlineEditor(QLineEdit)`：回车/失焦确认、Esc 取消；失焦确认会置 `_suppress_click` 吞掉紧跟的同一次点击。

---

## 5. 磁吸对齐系统（重点，canvas.py）

设计原则（用户多轮迭代确定，不可改回）：
- **拖动过程完全自由**（不实时吸附、不粘住），**松开鼠标才吸附**，吸附后关闭预览。
- 一次只高亮/吸附**最近的 1 根**参考线。
- 参考线以「**同侧第一个标注**」为基准；同时参考「对侧」已有标注，实现 左↔右、上↔下 相互对齐。

### 5.1 侧别判定 `_get_side(item)`
以文字框中心相对**图片中心**的偏移判定：`|dx|>|dy|` → left/right，否则 top/bottom。

### 5.2 参考线 `_get_ref_lines(item) -> (v_lines, h_lines)`
- `v_lines=[(x, align_type)]`，align_type ∈ left/center/right；`h_lines=[(y,...)]` ∈ top/center/bottom。
- ① 同侧**第一个**标注的左/中/右（或上/中/下）三条边；② 对侧**所有**标注的三条边。基准因此始终是「同侧第一个」，不同标注参考线宽度一致。

### 5.3 新建时吸附 `_snap_hover_to_base(pos)`
第 2 击放置位置在 12px（按 scale 归一）内吸附到任一已有引线的对应边。

### 5.4 松开吸附 `_snap_item_on_release(item)`（拖动调节的核心）
- 吸附容差 `margin = 5/scale`。
- X 轴：仅当文字中心落在「所有竖参考线最左−margin ～ 最右+margin」区间内才吸附；遍历参考线，**按线类型用当前标注对应边**算偏差（left 对 r.left()、right 对 r.right()、center 对 r.center()），取绝对值最小者，把 text_point.x 平移该偏差。Y 轴同理（top/bottom/center）。
- 因此左线对齐文字左边、中线对齐文字中心（自动按各自文字宽度计算）、右线对齐文字右边——文字长度不同也能正确对齐。
- 吸附后调用 `_avoid_overlap()` 防重合。

### 5.5 防重合 `_avoid_overlap(item)`
若文字框与任一其他 LeaderLineItem 相交，则沿 Y 每次下移 `font_size*1.5` 行高，最多 20 次直到不相交（避免新增标注被强制对齐到已有标注同一位置而重叠）。

### 5.6 参考线绘制
`_paint_drag_snap_guides`（拖动预览）、`_paint_new_snap_guides`（新建预览）、`_paint_snap_guides`，被选中的参考线高亮。水平参考线长度至少延伸到文字位置。

---

## 6. 鼠标与键盘交互（canvas.py）

### 6.1 鼠标
| 操作 | 行为 |
|---|---|
| 左键单击（选择模式） | 命中则选中并记录 `_drag`（含 press_time、press_view）；优先命中选中形状的编辑手柄（8 缩放点 + 1 旋转点，v1.7） |
| 左键拖动 | 移动元素（自由，不吸附）；移动 1px 即置 moved=True；拖形状手柄实时缩放/绕中心旋转；点在当前层虚线框内空白 → 整层一起移动（v1.7） |
| 左键松开 | moved→记一次 move/缩放/旋转/整层 撤销；未 moved→进入单击翻转判定（§6.3）；LeaderLine 再执行松开磁吸 |
| 中键按住拖动 | 平移画布 |
| 右键按下 | 记录按下点；**发生位移（>4px）立即进入平移画布（零延迟，v1.7）**；未位移的短按释放才在选择模式弹分类菜单；从指令模式切换来的首次释放不弹菜单 |
| 滚轮 | 以鼠标为锚点缩放 |
| 双击文字 | 进入就地编辑（改文字内容） |

### 6.2 画布快捷键
V 选择 / L 引线 / N 序号 / T 文本 / R 形状 / P 画笔；Delete 删除；Esc 取消待操作（**连续折线绘制中 Esc/回车只结束当前折线、保留已确认部分，不切换工具**）；Ctrl+Z/Y 撤销重做（主工具栏绑定，见 §9）。

### 6.2.1 直线连续折线 + 正交磁吸（r23，canvas.py）
- 状态：`_line_points`（已确认 QPointF 顶点）、`_line_cursor`（跟随鼠标、已吸附的当前端点）、`_line_snap_axis`（'h'/'v'/None）。按下追加顶点（追加的是上一帧 `_line_cursor`，保证所见即所得），鼠标移动（不按键也触发）从最后顶点画跟随段，`_paint_line_path_preview` 画已确认折线 + 白色顶点锚点 + 蓝色虚线磁吸引导。
- 正交磁吸 `_line_ortho_snap(p1,p2)`：容差 `5/scale`（图片坐标，任意缩放下屏幕恒 ±5px）；`|dy|≤容差 且 |dx|≥|dy|` → 水平（p2.y=p1.y，'h'），`|dx|≤容差` → 竖直（p2.x=p1.x，'v'），两轴同时满足按差值较大轴吸。结束走 `_finish_line_path()`（≥2 顶点才建元素）。

### 6.3 单击翻转横线方向（above_text/below_text 专属）
需求：文字在横线上/下时，**单击横线或文字**即调换横线方向（拐点在文字左端↔右端）；但拖动调整位置、长按、双击编辑都不能误触发。

实现（延迟单击，区分点击/拖动/双击）：
1. `mousePressEvent` 命中时在 `_drag` 记录 `press_time`、`press_view`；左键入口若翻转定时器在跑则先停掉（这是双击第二下，要去编辑文字）。
2. `mouseReleaseEvent` 左键且 `not moved` 时调 `_maybe_toggle_line_dir(event, drag)`：必须是 LeaderLineItem、样式 ∈ {above_text,below_text}、part ∈ {text,line}、按住 <0.5s、视图位移 <5px，才 `QTimer.singleShot` 风格地启动单次定时器 `_line_toggle_timer`，间隔 `QApplication.doubleClickInterval()`。
3. 定时器到点执行 `_do_toggle_line_dir()`：`push_undo("above_dir")` → `item.toggle_horizontal_dir()` → 重绘。
4. `LeaderLineItem.toggle_horizontal_dir()`：先把 auto 落到「当前自动方向」，再在 left/right 间取反，保证每点一次必掉头。
> 用「双击判定窗口延迟」是为了让双击编辑文字时，第一下的单击翻转被第二下按下取消，两者不冲突。

---

## 7. 可停靠模式工具面板（window.py，tool_dock）

一个 `QDockWidget`，内含 `tool_widget` + 一个 `QBoxLayout`（`tool_layout`），成员为：`float_btn("⧉")` + 10 个模式按钮 + 末尾 addStretch(1)。

### 7.1 模式按钮（符号 + tooltip，不重复）
👆选择 / ↗️引线标注 / 🔢引线序号 / 🔤文本批注 / ⬜形状 / ✏️画笔 / 🖍️荧光笔(占位) / 🧱马赛克(占位) / 😀表情(占位) / ✂️自由截图(占位)。后四个仅占位、未实现功能。

### 7.2 方向规则（`_do_update_tool_layout_orientation`，必须严格遵守）
- **浮动**：始终**单行横排**，显示完整标题栏（可拖动/关闭/浮动），隐藏 ⧉。
- **停靠上/下**：**单行横排**，用 0 高度空 widget **隐藏标题栏**，最前面显示 ⧉（点击 `setFloating(True)` 变浮动），面板 features 设为 NoDockWidgetFeatures（上下位置不可拖，只能点 ⧉ 浮动）。
- **停靠左/右**：**单列竖排**，恢复默认标题栏（仅保留 DockWidgetMovable，靠标题栏拖动），隐藏 ⧉。
- 方向切换用 `QBoxLayout.setDirection()`（LeftToRight / TopToBottom）原地切换，**禁止删除重建 layout**（曾因此崩溃 `wrapped C/C++ object QHBoxLayout deleted`）；切换时 takeAt 全部 widget 再按「⧉→按钮→stretch」顺序加回。

### 7.3 始终最小尺寸（锁死，不随窗口拉伸）
- 常量 `TOOL_BTN_SIZE = 38`（模块级），每个按钮 `setFixedHeight/Width(TOOL_BTN_SIZE)`，⧉ 同尺寸。
- 横排：`setFixedHeight(38)`，宽锁为 `n*38`；竖排：`setFixedWidth(38)`，高锁为 `n*38`；浮动时额外 resize 到内容大小（横排高 +30 标题栏）。
- layout 的 contentsMargins/spacing 全为 0，按钮紧挨、靠左/靠上对齐，末尾 stretch 留空。
- 选中态**不再加 "●" 前缀**（曾导致 32px 按钮内容被裁切），改用「蓝底 #2f6fed + 2px 浅蓝边框 #bcd6ff」表示；普通态 2px 透明边框、hover 淡蓝底；字号 17px、padding 0，保证符号完整显示。主工具栏 `setIconSize(QSize(22,22))`。

### 7.4 嵌入左右分栏独立竖列（r31 新增，window.py）
除 QDockWidget 原生的浮动/四边停靠外，工具面板还可作为**独立竖列嵌入水平分栏**：
- `inner-left`：插到 `left_box` 与 `center_box` 之间（**左面板右侧**）；`inner-right`：插到 `center_box` 与 `right_box` 之间（**右面板左侧**）。实现：`removeDockWidget` → `tool_dock.setWidget(None)` 释放内容 → `splitter.insertWidget(idx, tool_widget)`，列宽锁 38、高度随分栏拉伸；反向则 `setParent(None)` → `setWidget` 回 Dock。
- **两种入口**：① 工具面板**右键菜单** `_show_tool_place_menu`（浮动/顶/底/最左/最右/两种嵌入，当前位置禁用）；② 把**浮动**工具窗口拖到「左面板右缘 / 右面板左缘」±30px 缝隙，松开自动嵌入——80ms 轮询 `_check_float_tool_dropzone`（要求左键按下→松开且位移 ≥16px，区分点击与拖动，`_tool_drop_zone` 用全局坐标判定缝隙）。嵌入态下 ⧉ 按钮一键弹出浮动。
- 摆放状态统一记在 `self._tool_place`（dock-left/dock-right/top/bottom/float/inner-left/inner-right），原生 dock 迁移经 `dockLocationChanged/topLevelChanged` 自动同步；`_do_update_tool_layout_orientation` 嵌入态走独立尺寸分支（锁 `tool_widget` 而非 `tool_dock`，并放开另一侧历史锁定）。
- **持久化**：嵌入时分栏是 4 列、Dock 已脱离主窗口，直接 saveState 会让下次 3 列结构 restoreState 失效。进入嵌入前留存 `_clean_main_state/_clean_splitter_state`（3 列干净状态，未嵌入时 splitterMoved 持续更新），`_collect_settings` 嵌入时保存干净状态 + `tool_place`；`_restore_settings` 恢复分栏后 singleShot 调 `_restore_tool_place` 重新嵌入。

---

## 8. 右侧样式面板（panel.py）

`StylePanel` 内 10 个 `CollapsibleBox`，**自上而下顺序固定**：引线设置（默认展开）→ 文字设置 → 画布设置 → 形状设置 → 画笔设置 → 荧光笔设置 → 马赛克设置 → 表情设置 → 截图设置 → 导出设置；`self._groups` 顺序与之同步（key: leader/text/canvas/shape/pen/highlight/mosaic/emoji/screenshot/export）。**新增组必须 addWidget 在导出组 g_exp 之前。**

- 右侧面板顶部（滚动区外，固定常显）有一个「▲ 折叠全部 / ▼ 展开全部」按钮（`MainWindow.collapse_all_btn`）：点击一次全部折叠、再点全部展开；内部走 `StylePanel.collapse_all()/expand_all()` 程序化 `set_expanded`，**不触发工具模式切换**。按钮文案由 `_sync_collapse_all_btn()` 按当前状态自动同步（`StylePanel.groupsChanged` 信号：用户手动折叠/展开、切换模式联动展开、恢复设置都会刷新），配色随明/暗主题切换（`_apply_collapse_btn_theme`）。

- 荧光笔设置：6 预设色块（#FFE600/#54FF00/#FF5CA8/#33CCFF/#FF9500/#C77DFF，`_set_hl_preset`）+ 自定义颜色 + 粗细(3–100,默认22) + 不透明度%(5–100,默认31)。
- 马赛克设置：块大小(3–50,默认10) + 「显示马赛克边框」QCheckBox(默认勾选，mosaic_border)。
- 表情设置：24 个 emoji 的 QGridLayout（每行8个、30×30 checkable，闭包 `_pick_emoji` 记录 `self._emoji_char` 互斥高亮）+ 大小(12–160,默认40)。
- 截图设置：QKeySequenceEdit(默认 Ctrl+Q) + 「复制到剪贴板」「载入画布」QCheckBox(默认均开) +「立即截图」按钮(发 screenshotRequested)。

### 8.1 CollapsibleBox 折叠组
QToolButton 标题（箭头 Right/Down）+ 可折叠内容区。**标题三色随主题/状态变化**（`_apply_title_style`）：

| 主题 | 折叠（正常） | 鼠标悬停 | 展开（checked） | 展开+悬停 |
|---|---|---|---|---|
| 暗黑 | 绿 `#7CE38B` | 蓝 `#5AA8FF` | 红 `#FF6B78` | 橙 `#FFA94D` |
| 明亮 | 蓝 `#1F6FD0` | 绿 `#2FA05C` | 红 `#E5485C` | 橙 `#E8590C` |

`set_dark(bool)` 切换；主窗口主题切换末尾遍历 `_groups` 调 `set_dark`。`expand_group(key)` 程序化展开。

- **暗黑主题复选框白色化（`StylePanel.set_dark_theme`）**：`__init__` 末尾一次性收集全部 QCheckBox 到 `self._checkboxes`；暗黑主题下逐控件设置 QSS——未选态 1px **蓝色边框 #5AA8FF**（hover 橙 `#FFA94D`）+ 深色底（#3d3d3d），选中态**白色填充** + 深色对勾。注意：QSS 一旦自定义 `::indicator`，Qt 不再绘制原生对勾，因此对勾图案由 `_checked_icon_path(color, name)` 用 QPainter 按颜色参数化生成一次深色对勾 PNG（存 autosave/_check_dark.png）并经 `image: url(...)` 注入；明亮主题 `setStyleSheet("")` 清空、恢复原生样式。

### 8.2 current_style() 返回字段（新建元素的样式来源）
`line_color, line_width, arrow_size, endpoint_style, label_style, above_dir, text_gap, above_gap, text_color, font_size, font_family, font_weight, font_italic, script, bg_enabled, bg_fill_color, bg_border_color, shape_type, shape_border_color, shape_fill_color, shape_line_width, pen_color, pen_width`，再加本轮新增：`hl_color(QColor), hl_width, hl_alpha(0–255), mosaic_block, mosaic_border(bool), emoji_char, emoji_size, screenshot_shortcut(str), screenshot_clipboard(bool), screenshot_canvas(bool)`。（r23：引线新增 `above_gap` 上下间隙。）
- 每个新字段都要在 4 处同步：current_style() 产出、_apply_to_selection() 应用到选中、sync_from_selection() 回填、set_style() 从 settings 回填；颜色值在 current_style 里直接放 QColor 对象。
- 注意：`bg_enabled = 背景框勾选 且 label_style==box`（新 4 样式下背景框由「文字设置」独立控制，不再被引线样式强制关闭）。
- 引线设置内含：线型/颜色/线宽/箭头大小/端点样式/引线样式下拉/横线方向/「空白间隙」text_gap_spin（原「文字间隙」，r23 改名，键名仍 text_gap，0–20、后缀 px、默认 5）/「上下间隙」above_gap_spin（r23 新增，文字在横线上/下方时与横线的垂直间隙，0–20、默认 5），两者 valueChanged 均实时生效并回填选中项。
- 「应用到全部同类标注」按钮位于**引线设置**组内。
- 全局状态：序号开关/格式、磁吸模式 snap_combo、画布背景 bg_combo（含透明）、JPG 质量；`_sync_canvas_state()` 同步给画布。
- 顶部 QSpinBox 等都从 panel.py 顶部一次性 import，**禁止函数内重复 import**（曾致 UnboundLocalError）。

---

## 9. 主工具栏与快捷键（window.py）

全部用图标（Qt 标准图标），hover 显示中文 tooltip。动作与快捷键（v1.7 按功能重排，从左到右）：

| 位置 | 动作 | 快捷键 | 说明 |
|---|---|---|---|
| 1 | 新建空白 | — | 新建空白画布 |
| 2 | 打开项目 | Ctrl+Shift+O | 读 .anno（图片+标注+图层） |
| 3 | 打开本地图片 | Ctrl+O | |
| 4 | 导入剪贴板 | Ctrl+V | 读剪贴板图片加载（最常用入口） |
| 5 | 保存项目 | Ctrl+Shift+S | 存 .anno（图片+标注+图层） |
| 6 | 导出（下拉） | Ctrl+S | 下拉菜单可选 **PNG / JPG / GIF / BMP / TIF / TIFF**（v1.7 多格式，记忆上次格式；图标为「向下箭头入托盘」，与保存项目软盘区分）；原独立导出按钮已取消 |
| 7 | 复制全部到剪贴板 | Ctrl+C | 渲染「图片+标注」到系统剪贴板 |
| 8 | 撤销 / 重试 | Ctrl+Z / Ctrl+Y | |
| 9 | 删除选中 | Delete | |
| 10 | 删除全部 | — | 清空画布全部标注 |
| 11 | 100% 显示 | — | 点击 `canvas.actual_size()` 回到 scale=1 原始分辨率居中 |
| 12 | 对齐 | — | 一键自动布局（`canvas.auto_layout`） |
| 13 | 主题 ☀️/🌙 | — | 明/暗主题切换（暗黑态显示 ☀️、明亮态显示 🌙） |
| 14 | 关于（右对齐） | — | 绿底白字，位于退出按钮左侧（工具栏倒数第二），点击弹「关于 图片快速标注工具 v1.7」（作者 redmoonk / 版权 © bk100 / 功能说明） |
| 15 | 退出（右对齐） | — | 红底白字，工具栏**最右端**（前置 Expanding 弹簧实现右对齐）；先 `_persist_settings()` 保存参数、`_do_autosave()` 保存当前工作，再隐藏托盘并 `QApplication.quit()` 完全退出（区别于点窗口关闭只是隐藏到托盘） |
| — | 自由截图 ✂️ | Ctrl+Q（可在「截图设置」用 QKeySequenceEdit 自定义，清空禁用） | 隐藏主窗口→全屏框选→按设置复制剪贴板/载入画布，见 §18 |

- 主工具栏被关闭后，可在**右侧面板右键菜单**重新显示（`_show_right_panel_menu` → `_toggle_toolbar`）。
- 明/暗主题：`_apply_dark_theme` 用一套 QSS（深色 #2d2d3d 系，QGroupBox 标题默认浅绿 #90EE90、hover #4da3ff），`_apply_light_theme` 清空 QSS；切换后同步 panel 折叠标题三色。

---

## 10. 左侧面板（历史 + 图层）与左侧浮动按钮

- 左侧 `left_box` 宽度由水平 QSplitter 拖动调节（最小 150），拖动时 `_on_splitter_moved` 记录 `_left_panel_width` 并持久化。
- 仅**左侧**有一个半透明圆形浮动按钮 `left_floating`（挂在 central 上，`_update_left_floating_pos` 定位到左面板右缘中部），点击 `_toggle_left_panel` 在显示/隐藏间切换：隐藏时把 left_box 最大/最小宽都设 0（**真正让出空间给画布**），展开时恢复记录的宽度。状态 `_left_panel_expanded`、宽度 `_left_panel_width` 都存 settings。
- **HistoryPanel**：顶部显示当前项目名（未保存为「新图片」，`set_project_name`）；列表按创建顺序，单击选中、双击编辑文字、右键（编辑文字 / 引线额外有 编辑序号/上移/下移 / 删除）。
- **LayerPanel**：`+/-` 按钮增删层、↑/↓ 移层；勾选框控制显隐；列表支持**拖拽排序**（显示顶层在上，提交时 reversed 回底层在前）；右键菜单：设为当前层 / 重命名（**不可重名**，QInputDialog 循环校验）/ 选中本层全部元素 / 删除 / 上移一层 / 下移一层 / **置为顶层 / 置为底层**（一步到位，等价连续上/下移到底，已在对应边缘时禁用）/ 展开折叠此层。
  - **图层行拖拽 = 确定性重排（r31 重构）**：不再依赖 QTreeWidget 父类 dropEvent（旧实现把图层拖到另一行「行内」时会嵌套成子节点、且 dropEvent 内同步叠放顺序的调用因对象类型不符被 try/except 静默吞掉）。现由 `_LayerTreeWidget._manual_layer_reorder()` 自行 take/insert 顶层节点：拖到目标层**上方/下方指示符**即插到相邻行；落在行内（OnItem）按鼠标位于该行上/下半区分流；拖到某层的元素子行则插到其父层前/后；拖到空白移到最末。效果与多次点「上移/下移图层」完全一致，且**保证图层永不嵌套**；重排后经新增的 `layerOrderEdited` 信号（singleShot 0 延迟）交面板 `_emit_layer_order_from_tree()` 同步画布叠放。
  - 列表刷新必须**增量更新**（复用 QListWidgetItem，禁止 clear 重建，否则信号派发中销毁 item 会触发 0xC0000409 崩溃）。
  - 选中某图层时，画布 `select_layer_items` 醒目选中该层全部元素。
  - **选中图层整体虚线高亮**：点选图层（`select_layer`）或右键「选中本层全部元素」（`select_layer_items`）会置 `canvas.highlight_layer_id`；paintEvent 在元素绘制后调 `_paint_layer_highlight`，对该层所有可见元素的 `export_bounds()` 求并集，画一条橙色（#FF7A00）DashLine 虚线外框（图片坐标系，外扩 2px）。该高亮只在屏幕绘制路径，**不进入 render_export 导出**；初始/加载/打开项目/恢复时 highlight_layer_id=None 不高亮。

**v1.5（r25–r27，图层结构树大幅升级）**：
- **元素↔图层拖放不闪退**：`_LayerTreeWidget` 内 `_in_drop` 标志 + `dropFinished` 信号；dropEvent 内元素改归属改 `QTimer.singleShot(0)` 延迟发射 `itemMovedToLayer`；refresh() 在 `_in_drop` 时挂起到 `_pending_refresh`，`_on_tree_drop_finished` 后 `singleShot(0)` 补刷；`_on_rows_moved`（图层拖拽重排）同样 `singleShot(0)` 延迟发 `requestReorder`。**根因**：dropEvent/rowsMoved 信号派发期间同步刷新树会销毁节点 → Qt 0xC0000409 闪退。
- **图层拖拽重排**：图层行可直接上下拖动（靠上即显示在上层，顶层在列表最上），拖放时允许落在元素子节点区域；`requestReorder` → `apply_layer_order` → 画布按新顺序绘制。
- **始终高亮当前层**：当前层行显示 `▶ 图层名` 前缀 + 加粗 + 蓝底橙字（暗黑 #FFC46B / 明亮 #C2410C）；`load_pixmap / add_layer / delete_layer / select_layer` 均设 `highlight_layer_id = current_layer`；画布当前层高亮框改为橙色双线（外层柔光 5px + 内层 #FF7A00 虚线 1.8px）。
- **元素唯一性**：树内元素节点按 id 去重显示（refresh 与 `_sync_layer_children` 各一层 seen）；`canvas.deduplicate_items()` 按「同 id 只留第一个 + 几何指纹去重」清理，自动保存恢复 / 打开项目后调用；**克隆元素必须 `allocate_item_id()` 重新分配 id**（copy.deepcopy 保留原 id，否则画布 2 个表情、树却出现 3 个）。
- **元素按类型着色**：引线红 / 文本绿 / 形状蓝 / 画笔橙 / 荧光黄 / 马赛克紫 / 表情橙红，明暗主题各一套，`set_dark_theme` 时重着色。

**v1.6（r28，八项体验优化）**：
- **折叠/展开箭头明暗主题鲜艳可见**：三角箭头改为自绘 PNG（`autosave/_branch_*.png`，明亮深蓝 #1F6FD0 / 暗黑亮绿 #7CE38B），QSS `branch:closed/open` 按主题注入；顶部操作按钮按角色配色（+ 绿 / − 红 / ↑↓ 蓝 / 展开折叠 橙，明暗各一套，文字加粗），不再用黑白色导致看不清。
- **拖放防闪退加固**：`startDrag / dragMoveEvent / dropEvent / _do_refresh / _refresh_current_layer_highlight / _sync_layer_children` 全部对节点做 `sip.isdeleted` 存活校验 + try/except 兜底，拖拽期间任何刷新销毁节点都不会再触发 0xC0000409；dropEvent 整体异常安全、finally 复位拖拽状态。
- **右键交互重构**：非选择模式（指令功能）右键 → 仅切换到选择模式**不弹菜单**；再次右键（已处于选择模式）才弹出分类菜单；菜单改为**点击释放后才出现**（`mouseReleaseEvent` 手动 `_show_right_menu`，`contextMenuEvent` 一律 ignore 防重复）；右键**长按超过 450ms 且拖动** → 平移画布，释放不再弹菜单。
- **虚线框显隐（需求4）**：仅「选中图层（高亮）」或右键「选中本层全部元素」时显示该层全部元素范围橙色虚线框；点击画布空白一次或进入任意标注模式自动隐藏；加载图片 / 新增 / 删除图层 / 恢复 / 打开项目均不高亮。
- **直线折线自动闭合**：多段折线终点靠近初始起点（±10px 屏幕容差）时自动磁吸闭合形成封闭图形——移动预览显示橙色闭合引导并高亮起点；点击/双击/回车结束均生效；`ShapeItem._is_closed()`（首尾顶点重合）+ `paint` 加 `closeSubpath` + `hit_test` 含闭合边，封闭带填充时区域内部可命中；序列化向后兼容（闭合=多一个重合尾点）。
- **粘贴/导入前保存确认**：画布已有标注时，Ctrl+V 粘贴、打开图片、打开项目、截图载入前弹「是否先保存当前工作（自动保存）」（保存并继续 / 不保存继续 / 取消）。
- **右键菜单明暗主题 QSS**：主界面与两侧面板右键菜单统一走 `QApplication` 级 QMenu 样式（暗黑深底浅字 + 蓝底选中；明亮清空回原生），文字与背景同步变化，不再出现只有文字变色导致看不清。
- **版本号 v1.6**：窗口标题与关于对话框升级为 v1.6（作者 redmoonk / 版权 © bk100），关于按钮固定在工具栏最末尾（退出之前）。

---

## 11. 持久化（autosave/ + settings.py + autosave.py）

基准目录 `_app_base_dir()`：frozen 时为 exe 所在目录，否则为项目根；统一在其下建 `autosave/`。

### 11.1 settings.json（界面 + 样式，`_collect_settings`，力求“所见即所存”）
- `window_geometry`（窗口大小/位置）、`main_state`（**QMainWindow.saveState**：工具面板 tool_dock 的停靠区域/浮动位置几何）、`splitter_state`（左/中/右面板宽度）、`left_splitter_state`（历史/图层上下比例），均为 base64。**主工具栏与 tool_dock 必须显式 `setObjectName`**（PyQt6 构造传标题只设 windowTitle、不设 objectName），否则 saveState 报警告且停靠布局无法持久化。
- `left_panel_expanded / left_panel_width`（左侧面板显隐与宽度）。
- `tool_place`（r31：工具面板摆放位置 dock-left/dock-right/top/bottom/float/inner-left/inner-right）；嵌入分栏期间 `main_state/splitter_state` 保存的是进入嵌入前的 3 列干净状态。
- `theme_dark`（明/暗主题）、`group_expanded`（10 个折叠组各自展开状态，`panel.group_states()/set_group_states()`，程序化恢复不触发模式切换）。
- `style`：current_style **全字段**（含 hl_color/hl_width/hl_alpha、mosaic_block/mosaic_border、emoji_char/emoji_size、screenshot_* 等）+ jpg_quality/bg_index/number_enabled/number_format/snap_mode。**所有 QColor 字段必须在 `_collect_settings` 的颜色转换元组里转 #AARRGGBB**（line/text/bg_fill/bg_border/shape_border/shape_fill/pen_color/**hl_color**，漏一个会让 json.dump 抛 TypeError、被 settings.save 静默吞掉导致整个文件写失败）。
- `mode`（上次模式）、`last_export_fmt`。
- **保存时机（关键）**：点关闭按钮是“隐藏到托盘”而非退出，因此统一入口 `_persist_settings()` 同时在「关闭到托盘 closeEvent」和「托盘菜单真正退出 _quit_app」两处调用；启动 `QTimer.singleShot(0, _restore_settings)` 按 main_state→splitter→style→折叠组→主题→mode 的顺序恢复。

### 11.2 自动恢复（去抖 600ms）
任何变化 `_schedule_autosave` → 600ms 后 `_do_autosave` → `autosave.save()` 写：
- `image.png`：当前图片；`items.json`：`{items:[...], layers:[...], current_layer}`。
启动 `_check_restore()`：若存在自动保存，弹 QMessageBox 询问是否恢复上次工作。

### 11.3 元素序列化格式（serialize_items / deserialize_items）
颜色统一存 `[r,g,b,a]`。
- leader：`type,target[2],text_point[2],content,line_color,line_width,arrow_size,endpoint_style,label_style,above_dir,number,number_fmt,font_size,text_color,font_family,font_weight,font_italic,script,bg_enabled,bg_fill_color,bg_border_color,layer_id`
- text：`type,pos[2],content,font_size,text_color,font_*,script,bg_*,layer_id`
- shape：`type,p1[2],p2[2],shape,border_color,fill_color,line_width,layer_id`；r23 起多点折线额外写 `line_points[[x,y]...]`（仅直线且顶点≥3；两点直线不写、向后兼容，恢复时 p1/p2 为首尾点）
- pen：`type,points[[x,y]...],pen_color,pen_width,layer_id`
- highlight：`type,points[[x,y]...],hl_color[r,g,b,a],hl_width,hl_alpha,layer_id`
- mosaic：`type,p1[2],p2[2],block_size,show_border,layer_id`（不存原图，恢复后绘制时惰性注入；旧档无 show_border 时默认 True）
- emoji：`type,pos[2],emoji,font_size,layer_id`
反序列化全程 try/except 跳过坏条目；字号经正数兜底 lambda；图层按「旧 id→新 id 映射」重新归属。
- `.anno` 项目文件：保存项目时把图片（base64/字节）+ items + layers 打包；读取用对应编码，**不要假设它是 utf-8 纯 JSON**。

---

## 12. 导出渲染（canvas.render_export）

1. 先求所有元素 `export_bounds()` 并集，若标注超出原图则**自动扩展画布**，保证不截断。
2. **透明背景 PNG 逻辑（用户明确要求）**：
   - **原图始终绘制、完整保留**；
   - `transparent_bg=True` 时用 `Format_ARGB32` 并先 fill transparent——只有「**超出原图的扩展区域**」透明，原图区域仍是原图；
   - 各标注的**文字背景框**：未启用则透明，启用则按所选 bg_fill_color 画。
3. 非透明：扩展区填画布背景色 `_bg_color`，未扩展区填白，再画原图。
4. `_paint_layers_export` 按图层顺序绘制、跳过隐藏层。
5. 画布背景色支持在「画布设置」选透明；导出 PNG 才保留 alpha，JPG 不支持透明。

---

## 13. 系统托盘 / 窗口行为

- 启动 `_center_on_screen()` 居中；窗口/任务栏图标用 1.ico。
- `QSystemTrayIcon`：点关闭按钮（closeEvent）或最小化（changeEvent）都**隐藏到任务栏托盘**（不退出），并气泡提示；单击托盘图标 `_on_tray_activated` 在显示/隐藏间切换；真正退出走托盘菜单 `_quit_app()`。**关闭到托盘与真正退出都会先 `_persist_settings()` 保存全部设置**（注意类里只能有一个生效的 closeEvent，历史上曾出现“托盘版 closeEvent 覆盖了保存版”导致设置从不落盘的 bug）。

---

## 14. main.py 的 stderr 过滤（必要的兼容处理）

Qt Windows 样式插件内置 PNG 带不标准 sRGB profile，首次展开折叠组时 C 层会直接向 fd2 打印 `libpng warning: iCCP ...`；鼠标悬停折叠标题时 Qt 样式引擎内部还会打印 `QFont::setPointSize: Point size <= 0 (-1)`（**纯无害**：pointSize=-1 是“使用像素字号 setPixelSize”时的正常内部值，业务侧无法根除），二者**替换 sys.stderr 都拦不住**。`_install_native_stderr_filter(("libpng warning: iCCP", "QFont::setPointSize"))` 在创建 QApplication 前：用 `os.pipe()` + `os.dup2` 重定向 fd2，后台 daemon 线程逐行读取，命中屏蔽词丢弃、其余写回真正 stderr，并把 `sys.stderr` 重开为 saved_fd。平台不支持时静默跳过。

---

## 15. 关键常量速查

| 常量 | 值 | 位置/含义 |
|---|---|---|
| TOOL_BTN_SIZE | 38 | 模式按钮正方形边长、面板最小宽/高 |
| TEXT_PAD_X / Y | 7 / 4 | 文字块左右/上下内边距 |
| middle_text 固定横线 | 15px | 文字在线中间 |
| no_line 固定横线 | 1px | 无横线模式 |
| text_gap 默认 | 5（0–20 可调） | 空白间隙：拐点/横线与文字水平留白 |
| above_gap 默认 | 5（0–20 可调，r23） | 上下间隙：above/below 文字与横线垂直距离 |
| 直线正交磁吸容差 | 5/scale（屏幕恒 ±5px，r23） | _line_ortho_snap |
| 新建吸附阈值 | 12/scale | _snap_hover_to_base |
| 松开吸附容差 | 5/scale | _snap_item_on_release |
| 防重合行高 | font_size*1.5，最多 20 次 | _avoid_overlap |
| 单击翻转判定 | 按住<0.5s、位移<5px、延迟 doubleClickInterval | §6.3 |
| 自动保存去抖 | 600ms | |
| MAX_UNDO | 100 | 撤销栈深度 |
| 默认字号 | 18（非法值兜底） | Microsoft YaHei, setPixelSize |
| 荧光笔默认 | 色#FFE600 / 宽22 / 不透明度31%(alpha≈79) | HighlightItem |
| 马赛克块默认 | 10（3–50） | MosaicItem.block_size |
| 表情默认 | 大小40（12–160），pos 为中心 | EmojiItem |
| 截图前隐藏延迟 | 220ms | start_screenshot→QTimer→遮罩 |
| 截图最小选区 | 5px，小于按取消 | ScreenshotOverlay |

---

## 16. 已知技术债 / 复刻注意事项（避坑）

1. **items.py 内存在多份重复方法副本**：`LeaderLineItem` 之后的 ShapeItem/TextItem/PenItem 类里被历史误插入多份 `_get_leader_geometry/_paint_above_text/...`（grep 可见 4 处），**真正生效的是 LeaderLineItem 类内第一份**（约 460–790 行）。改引线逻辑务必认准 LeaderLineItem 内副本；建议后续清理冗余副本。
2. 切换工具面板方向只能 `setDirection` 原地切，不能删除重建 QBoxLayout/QHBoxLayout。
3. 图层/历史 QListWidget 刷新只可增量，不可在信号回调中 clear 重建。
4. 所有字号入口都要做正数兜底，避免 `QFont::setPointSize<=0`。
5. 开发解释器须用安装了 PyQt6 的环境（本机 `py -3.13` / Python313）；GUI 回归脚本以独立进程运行、末尾 `os._exit(0)` 干净退出。
6. 面板顶部 import 一次性完成，禁止函数内重复 import 同名控件导致 UnboundLocalError。
7. CollapsibleBox 的 content_layout 必须在 `__init__` 内、toggled.connect 之后创建，不能误缩进到其它方法里。
8. **QPixmap 不可 deepcopy/pickle**：凡元素持有 QPixmap（如 MosaicItem._source），必须实现 `__deepcopy__`，深拷贝时把该字段置 None，否则 `push_undo → _snapshot → copy.deepcopy(items)` 抛 TypeError；该异常若发生在鼠标/信号 C++ 派发路径会表现为**进程静默退出、无 Python traceback**。恢复后靠绘制时惰性注入重新绑定原图。
9. **PyQt6 没有 `drawPixmap(QRectF, QPixmap)` 两参数重载**：两参数只收整数 QRect；QRectF 必须用三参数。且 canvas.paintEvent 顶层有 `try/except Exception: pass`，元素 paint 异常在**屏幕绘制时被静默吞掉**（grab 不报错≠画出来了），必须额外用无保护的 `render_export()` 或在 QImage 上手动绘制才能暴露。
10. **PyQt6 的 QShortcut 在 PyQt6.QtGui**（不是 QtWidgets，PyQt5 才在 QtWidgets）。
11. **QScreen.grabWindow 高 DPI 坑（截图清晰度核心，r22 定稿）**：传入逻辑坐标宽高，返回物理像素（125% 时 120→150，150% 时 200→300），且返回 pixmap 自带 DPR。三条铁律：① **底图绝不预处理**——`ScreenshotOverlay.__init__` 抓到整屏后保留原生物理像素与 DPR，绘制时 Qt 依 DPR 自动 1:1 映射到屏幕；若先 `scaled` 到逻辑尺寸，遮罩一弹出背景就比真实屏幕粗糙。② **最终截图从原生底图 `copy` 裁剪，不要在遮罩显示时二次 `grabWindow`**——否则会拍到半透明遮罩（偏色）和被处理过的背景（模糊）；逻辑选区乘 DPR 得物理 QRect，`bg.copy()` 是零重采样像素拷贝，输出再 `setDevicePixelRatio(1.0)`。③ **选区内恢复清晰必须用 `setClipRect(rect)+drawPixmap(0,0,bg)` 的 QPoint 直绘**；`drawPixmap(目标矩形,bg,源矩形)` 矩形重载即使同尺寸也走缩放 blit、会轻微柔化（实测 1 物理像素条纹邻列对比：QPoint 直绘 255 / 矩形重载 170 / 先缩小再放大 43）。画布侧：`drawPixmap(0,0)` 按 `width/DPR` 绘制、外框按 `width/height`，故 `canvas.load_pixmap` 对任何非 1 DPR 入图只归 1、不缩放，守住「载入图片 DPR 恒为 1」不变量，导出即原生分辨率。多屏坐标用 `self.geometry().topLeft()+local`，不要用未 show 时不可靠的 mapToGlobal。
12. **`_mode_name()` 必须用 dict.get 兜底**：鼠标 move 时 cursorMoved→_mode_name，遇到未知 mode 字符串若用 `{...}[mode]` 会 KeyError，且在信号发射路径中表现为静默退出。新增模式必须同时把中文名补进该 dict。
13. 工具面板里“自由截图”是**即时动作不是模式**：按钮 `setCheckable(False)`、点击直接 `start_screenshot()`，并在 `_apply_mode_button_styles` 中跳过，避免把 canvas.mode 置成未知值。
14. **QToolBar/QDockWidget 构造不会自动设置 objectName**：PyQt6 中 `QToolBar("主工具栏")` / `QDockWidget("工具面板")` 只设 windowTitle，objectName 为空 → `QMainWindow.saveState()` 打印 `'objectName' not set for QToolBar/QDockWidget ...` 警告，且该停靠布局无法随 settings 恢复。必须显式 `setObjectName`（主工具栏 `main_toolbar`、tool_dock `tool_dock`）。
15. **save_project 的 style 颜色转换必须覆盖全部 QColor 字段**：current_style 每新增一个颜色字段（如荧光笔 `hl_color`），若漏同步到 `save_project` 的颜色转换，`json.dumps` 抛 `TypeError: Object of type QColor is not JSON serializable` → 保存失败、`.anno` 只有 image.png 没有 project.json。v1.7 改为 `_deep_color_hex()` **递归**转换任意嵌套的 QColor（dict/list 混合），后续新增颜色字段无需再维护转换元组；保存改为「JSON 先完整序列化 → tempfile 临时文件写 zip → os.replace 原子替换」，任何一步失败都不会留下残缺 .anno；打开侧 `zipfile.is_zipfile` 检查 + 缺 project.json 时降级只加载图片并明确提示（正是用户「图3 无法打开项目」报错的根治）。
16. **直线不能用归一化矩形对角线（r23 修复）**：`shape_path("line", QRectF(p1,p2).normalized())` 恒画「左上→右下」对角线，当用户往右上/左下拖（"/" 方向）时画成另一条对角线、根本不经过按下点，表现为起点乱跑。直线一律按真实顶点 `moveTo(p1)→lineTo(p2)`（多点折线逐段），包围盒/选中框才用 normalized bbox。r23 起直线改为**点击式连续折线**（非拖拽）：按下只追加顶点、跟随段在 mouseMove（hover 也要响应，不能要求 buttons&LeftButton）里更新；Esc/回车/双击结束时只丢弃 `_line_cursor` 未确认段、保留 `_line_points`，且**不调用 `_cancel_pending()`**（那会切回选择工具）。canvas.py/items.py 为 CRLF，Edit 工具对其必报 Native execution failed，改它们用 tests/_patch_*.py 按 `\r\n` 拼接、assert 替换次数、utf-8 bytes 写回。
17. **copy.deepcopy 会保留元素原 id（v1.5 关键坑）**：`duplicate_item` 克隆后不重新分配 id，画布会出现两个同 id 元素——树按 id 去重只显示 1 个、`deduplicate_items()` 会把它当重复误删，正是用户截图「主界面 2 个表情、结果树 3 个」的根因。克隆后必须 `new_item.id = allocate_item_id()`（items.py 末尾模块级函数）。undo 快照不受影响（快照整体恢复、不同时共存）。
18. **拖放/排序信号派发期间禁止同步刷新树（v1.5 闪退根因）**：QTreeWidget 的 dropEvent / rowsMoved 派发中若同步 refresh 销毁节点，Qt 直接 0xC0000409 崩溃（无 Python traceback）。统一 `_in_drop` 挂起 + `QTimer.singleShot(0)` 延迟发射信号/补刷。**不熟 PyQt6 勿改 dropEvent 相关代码**。
19. **PyQt6 QMenu.addAction 重载顺序是 `(text, shortcut, slot)`**：写成 `(text, slot, shortcut)` 会按 ConnectionType 解析抛 TypeError；带快捷键菜单项一律 `menu.addAction("文本", "Ctrl+X", handler)`。

---

## 17. 本轮新增功能实现记录（荧光笔/马赛克/表情/自由截图，均已完成并测试）

新增一个“绘制类模式 + 画布元素 + 右侧设置组 + 持久化”需固定触碰 6 处（照此清单可 100% 复刻）：
1. **items.py 末尾追加元素类**：实现 `text_rect()/paint(painter,export=False)/hit_test(pos,tol)/move_by(dx,dy,part)/export_bounds()`；需要选中框就调基类 `paint_selection(painter,rect)`；字体一律 setPixelSize。
2. **canvas.py**：加 MODE 常量；`__init__` 临时状态；set_mode 清理状态/光标；mousePress/Move/Release 分支；`_paint_preview` 预览；`add_xxx_item` 工厂（内部 `item.layer_id=self.current_layer` 后 append）；`apply_style_to_all` 分支；`_paint_layers/_paint_layers_export`（马赛克在此惰性注入原图）。
3. **panel.py**：在 g_exp 之前 addWidget 新 CollapsibleBox 并注册 `_groups`；current_style 加字段；控件信号连 `_on_style_changed`；颜色走 `_pick_color`；`_apply_to_selection/sync_from_selection/set_style` 三处加该元素分支。
4. **window.py**：import MODE 常量；mode_btn_styles/mode_btn_tooltips；MODE_GROUP 映射；`_mode_name` 补中文名（.get 兜底）。
5. **autosave.py**：serialize/deserialize 成对分支，颜色存 [r,g,b,a]，马赛克不存原图。
6. **history_panel.py**：`_describe` 加中文名；无文字内容元素的 kind 白名单。

新建元素统一：坐标用图片坐标；工厂里设 `layer_id`、append 后由调用方 `push_undo("add")`、`selected=True`、`emit itemSelectionChanged`。最小成立阈值：形状/画笔/马赛克归一宽高 >3/scale；荧光笔轨迹≥1 点即成立。

**r17（右侧面板「折叠/展开全部」+ 启动警告修复 + 保存项目修复，均已测试）**：
- 右侧面板顶部固定「▲ 折叠全部 / ▼ 展开全部」按钮（见 §8），配套 `StylePanel.groupsChanged` 信号与 `any_expanded/collapse_all/expand_all` 方法；
- 修复启动/退出时 `QMainWindow::saveState(): 'objectName' not set ...` 警告：主工具栏、tool_dock 显式 `setObjectName`（见 §16.14）；
- 修复「保存失败: Object of type QColor is not JSON serializable」：`save_project` 颜色转换改为 isinstance 通用转换，补上漏掉的 `hl_color`（见 §16.15）；
- 新增 `tests/smoke_test_r17.py`（20 项断言，覆盖按钮折叠/展开、文案同步、主题配色、模式联动、恢复路径与 objectName）。

**r20（主工具栏退出按钮 + 暗黑复选框白色化 + 截图放大镜重构，均已测试）**：
- 主工具栏末尾新增 ✕ 退出按钮：前置一个水平 Expanding 弹簧 QWidget 实现**右对齐**；点击走 `_quit_app()`（保存参数配置 settings.json + 当前工作 autosave → 隐藏托盘 → QApplication.quit 完全退出），保存动作全程 try/except 保证必退；按钮自带红色符号 QSS，明暗主题一致。
- 右侧面板全部 QCheckBox 在暗黑主题下白色可见（未选白边框、选中白填充+深色对勾，见 §8.1），修复了「QSS 自定义 indicator 后 Qt 不画对勾」的坑（运行时生成对勾 PNG 注入 image）。
- 截图选区内不再放大（1:1 只表示框选范围），放大镜小方块移到选区外侧不遮挡处，右侧面板显示鼠标末端位置/起点/尺寸/倍数；上方空间不足自动翻下方。`tests/smoke_test_r20.py` 19 项断言全过。

**r21（直线形状/导出项移组/引线空文本/启动不弹提示/标题配色/退出文字按钮/1.ico，均已测试）**：
- 形状设置新增「直线」并固定排在形状下拉菜单**最前面**（`SHAPE_LINE`，SHAPE_OPTIONS 首项）：`shape_path` 画归一化矩形左上→右下的开放对角线段，ShapeItem.paint 对直线强制 NoBrush（避免开放路径被隐式闭合填充），hit_test 改为点到线段距离判定；画布松开阈值对直线放宽为「单边长度达标即可」（支持水平/垂直直线），拖拽预览同样强制无填充。
- 「导出透明背景 PNG」复选框从「画布设置」组移到「导出设置」组（JPG 质量行之后），变量名与 toggled 信号连接不变。
- 引线标注允许文本框留空：`start_inline_editor(..., allow_empty=False)` 新增参数，确认时若文本为空且 allow_empty 则回调空串生成空白文字引线；引线第二击与双击编辑引线元素时传 True，文本批注保持默认 False（空文本仍取消）。
- 启动不再弹「当前没有图片」提示：`_restore_settings` 恢复模式改为直接 `canvas.set_mode + _apply_mode_button_styles`（排除 screenshot），不再走会弹提示的 `_switch_mode`；用户主动点选工具且无图时仍弹提示。「恢复上次工作」对话框保留不变。
- 折叠组标题配色（`CollapsibleBox._apply_title_style`）：明亮=收起浅蓝 #7EABD6/悬停蓝 #1F6FD0/展开红 #E5485C；暗黑=收起深蓝 #5B8CC9/悬停白 #FFFFFF/展开红 #FF6B78。
- 退出按钮由 ✕ 符号改为红底白字「退出」文字按钮（#E0464B，hover #F05A60，pressed #C7333A），弹簧右对齐不变。
- 运行时窗口/任务栏/托盘图标统一优先 1.ico（缺失回退 2.ico），exe 文件图标本就由 spec 指定为 1.ico。`tests/smoke_test_r21.py` 28 项断言全过（含 1.ico/2.ico 渲染哈希对照）。

**r22（高 DPI 截图：修复外框比截图大一圈 + 遮罩/截图均为显示器原生真实效果，已离屏/真机回归）**：
- 现象一：125%/150% 等缩放下，截图载入画布后只占外框左上角，右侧/下侧外框多一圈。根因：`grabWindow` 返回物理像素且自带 DPR，画布 `drawPixmap(0,0)` 按 `width/DPR` 绘制、外框按 `width/height`，DPR 不归 1 两者不一致。
- 现象二（用户定位）：**截图遮罩一弹出，桌面背景就比真实屏幕粗糙**，截下来自然不清晰。根因有两层：① `__init__` 把整屏底图先 `scaled` 缩回逻辑尺寸（预处理丢像素），显示时再被放大；② 旧 `_capture` 在遮罩仍显示时二次 `grabWindow`，等于拍到“半透明遮罩 + 被缩放处理过的背景”，二次损失。
- 最终修复（不改变任何交互逻辑，零预处理、零重采样）：
  1. `ScreenshotOverlay.__init__`：整屏底图**保留原生物理像素与 DPR，不再 scaled 预处理**；paintEvent 用 QPoint 直绘，Qt 依 DPR 1:1 上屏，遮罩背景与真实桌面同清晰度。
  2. 选区内恢复清晰：由 `drawPixmap(rect,bg,rect)` 矩形重载改为 `setClipRect(rect)+drawPixmap(0,0,bg)` QPoint 直绘（实测邻列对比 170→255，消除缩放 blit 柔化）。
  3. `_capture`：**不再二次截屏**，改为从弹出前抓取的原生底图按“逻辑选区×DPR”得物理 QRect，`QPixmap.copy` 无损裁剪后 `setDevicePixelRatio(1.0)` 输出；选区区域不变，输出原生最高分辨率（本机 150%：逻辑 500×360→物理 750×540）。
  4. `canvas.load_pixmap` 对任何非 1 DPR 入图只归 1、不缩放（剪贴板/文件/项目入口同样免疫），守住「载入图片 DPR 恒为 1」不变量。
- 说明：屏幕原生物理像素是真实清晰度上限，AI 上采样只会插值发虚，故不做上采样；放大镜改为采样原生底图，顺带更锐利。
- 验证：`tests/_dpr_regression.py` 覆盖 100%/125%/150%/200%，断言无损裁剪（逐像素 0 差异）、输出=物理尺寸、DPR=1、外框四边严合、选区内邻列对比 255；真机 150% 遮罩显示状态下出图，与弹出前原生画面 8424/8424 采样点一致、平均亮度差 0（证明无遮罩污染、无重采样）；r20/r21 既有 smoke 全过。

**r23（截图按原始分辨率载入 + 100% 按钮 + 引线间隙拆分 + 直线点击式连续折线/正交磁吸，已离屏回归）**：
- ① 截图导入不再自动放大：`canvas.load_pixmap(pm, fit=True)` 新增 fit 形参，截图入口 `_on_screenshot_captured` 传 `fit=False` → 新增 `actual_size()`（scale=1、图片居中、emit viewChanged）；粘贴/打开/项目恢复等其余入口仍默认 fit=True 自适应。
- ② 主工具栏分隔线后、**主题按钮左侧**新增「100%」文字按钮（46×28，tooltip「按原始分辨率 100% 显示」），点击 `canvas.actual_size()`。
- ③ 引线间隙拆分：面板「文字间隙」改名「**空白间隙**」（持久化键名仍 `text_gap`，settings/旧档兼容），仍管拐点水平留白 gx 与 middle/no_line 间隙；新增「**上下间隙**」`above_gap`（0–20、默认 5），仅作用于 above_text/below_text 文字与横线的垂直距离 line_y。LeaderLineItem 构造/apply_style 加 above_gap，current_style/set_style/sync_from_selection 全链路同步。
- ④ 直线重构为**点击式连续折线**：第 1 击定起点，线段跟随鼠标（hover 即响应、无需按住），逐击追加顶点可持续画多段异形；`_line_ortho_snap` 在末端与上一顶点水平/竖直差 ≤5 屏幕像素（5/scale 图片坐标）时强制正交并显示蓝色虚线磁吸引导（`_paint_line_path_preview` 另画白色顶点锚点）；Esc/回车/双击调 `_finish_line_path` 结束——只丢弃未确认跟随段、保留已确认顶点生成 1 个 ShapeItem（多点存 `points`，≥3 点序列化 line_points），结束后仍停留在形状工具。顺带修复旧拖拽直线用归一化矩形对角线、反向拖起点乱跑的问题（直线一律真实顶点直连，hit_test 逐段距离）。其他 10 种形状拖拽交互不变。
- 验证：新增 `tests/regression_r23.py` 36 项断言全过（100% 视图/按钮位置与接线/间隙独立几何/真实斜线命中/连续折线全流程/水平竖直磁吸坐标截断/Esc 仅 1 点取消与保留已确认/双击/回车/持久化往返/矩形拖拽不回归）；`_dpr_regression/smoke_r20/r21` 全过；离屏渲染 `_r23_preview.png`（锚点+蓝虚线引导）、`_r23_export.png`（三段异形折线）肉眼核验通过。

---

## 18. 自由截图模块（screenshot.py，独立文件）

**触发**：工具面板 ✂️ 按钮（非 checkable 的即时动作）或快捷键（默认 Ctrl+Q，QShortcut 挂主窗口，QKeySequenceEdit 改键后 `setKey` 重绑，清空则绑定空序列=禁用）或「截图设置」组的“立即截图”按钮，三者都调 `MainWindow.start_screenshot()`。

**流程**：
1. `start_screenshot()`：记录窗口可见性 → `showMinimized()` 隐藏自己（避免截到主窗口）→ `QTimer.singleShot(220ms, _show_screenshot_overlay)`。
2. `_show_screenshot_overlay()`：`pick_screen_at_cursor()` 取光标所在屏幕（兜底主屏）→ 创建 `ScreenshotOverlay(screen)`，连 captured/canceled → `showFullScreen + raise_ + activateWindow`。
3. **ScreenshotOverlay**（FramelessWindowHint|WindowStaysOnTopHint|Tool，WindowFullScreen，setGeometry=屏幕逻辑几何）：`__init__` 先 `screen.grabWindow(0)` 预抓整屏作背景，**保留原生物理像素与其 DPR、不做任何缩放预处理**（缩放会让遮罩背景比真实屏幕粗糙；绘制时 Qt 依 DPR 把物理像素 1:1 映射到屏幕，遮罩背景与真实桌面同样清晰）；鼠标按下记起点、移动更新选区、`paintEvent` 画「整屏背景(QPoint 直绘) + 半透明黑遮罩(alpha=110)，**选区内用 `setClipRect(rect)+drawPixmap(0,0,bg)` 直绘恢复清晰**（必须用裁剪+QPoint 直绘；`drawPixmap(目标矩形,bg,源矩形)` 矩形重载在 Qt 里走缩放 blit 会轻微柔化）+ 蓝框」，并由 `_draw_magnifier` 在**选区外侧**（优先正上方、空间不足翻下方、再不够贴边）画一个 132px、3× 的放大镜方块（十字线+蓝点对准鼠标拖动末端 `_cur`，采样原生底图所以也更锐利）与其右侧信息面板（鼠标 X/Y、起点 X/Y、选区宽×高、放大倍数）；松开（选区≥5px）调 `_capture`，否则/Esc 取消。常量 `_MAG_ZOOM/_MAG_BOX/_MAG_INFO_W`。
4. `_capture(local_rect)`：**不再二次 `grabWindow`**（松开时遮罩仍覆盖屏幕，再截屏会拍到半透明遮罩和被处理过的背景，偏色又模糊）。改为从 `__init__` 抓到的**原生整屏底图 `self._bg` 中按物理像素 1:1 裁剪**：逻辑选区乘底图 DPR 得物理 QRect，`bg.copy(physRect)`（纯像素拷贝、零重采样），再 `setDevicePixelRatio(1.0)` 输出。结果就是遮罩弹出前的显示器真实画面、原生最高分辨率（150% 缩放时逻辑 500×360 → 物理 750×540），且画布 drawPixmap 与外框尺寸一致（不会外框比截图大一圈）；随后 emit `captured(QPixmap)` → close。
5. `_on_screenshot_captured(pm)`：按勾选复制到 `QGuiApplication.clipboard()`、`canvas.load_pixmap(pm, fit=False)` 按**原始分辨率 100%** 载入画布（r23，不自动放大铺满；顶部「100%」按钮可随时回到该状态）；finally `_restore_after_screenshot()`（清 overlay 引用、showNormal/raise/activate 恢复主窗口）。取消走 `_on_screenshot_canceled`，同样恢复窗口。

**设置持久化**：screenshot_shortcut / screenshot_clipboard / screenshot_canvas 走 panel.current_style→settings.json 的 style，set_style 回填。截图是全局屏幕动作而非 items 元素，**不进 autosave 元素序列化、不进撤销栈**。

---

## 19. v1.5 更新记录（7 项需求，r24–r27，全量回归通过）

**① 明暗主题高对比配色**（panel.py）
- 折叠组标题 `_apply_title_style`：明亮=收起蓝 #1F6FD0 / 悬停绿 #2FA05C / 展开红 #E5485C / 展开悬停橙 #E8590C；暗黑=收起绿 #7CE38B / 悬停蓝 #5AA8FF / 展开红 #FF6B78 / 展开悬停橙 #FFA94D——明暗下「文字、标签、选框」均绿/红/蓝/橙四色可辨，不用黑白。
- 暗黑复选框：未选**蓝边框** #5AA8FF（hover 橙 #FFA94D）、选中白底+深色对勾（`_checked_icon_path(color, name)` 参数化生成对勾 PNG 缓存）。

**② 元素拖到任意层不闪退**（layer_tree_panel.py）
- `_in_drop` 挂起 + `dropFinished` 信号 + `QTimer.singleShot(0)` 延迟发射 `itemMovedToLayer`；refresh 在 `_in_drop` 时挂起到 `_pending_refresh`、drop 结束后补刷。修复拖放派发期间销毁树节点导致的 Qt 0xC0000409 崩溃。元素可拖到任意图层，拖后自动移到目标层。

**③ 图层直接拖动重排**
- 图层行上下拖动（`_on_rows_moved` → `singleShot(0)` → `requestReorder` → `apply_layer_order`），列表靠上即显示在上层（绘制顺序随之更新）。

**④ 始终高亮当前层**
- 图层树：当前层 `▶ 前缀` + 加粗 + 蓝底橙字（暗黑 #FFC46B / 明亮 #C2410C）。
- 画布：`highlight_layer_id` 在加载/增删/切换层时恒等于当前层；当前层高亮框改为橙色双线（柔光 5px + #FF7A00 虚线 1.8px），明暗都醒目。

**⑤ 元素唯一性（修复「画布 2 个表情、树 3 个」）**
- 根因：`copy.deepcopy` 克隆元素保留原 id → 树按 id 去重误删、显示错乱。
- 修复：克隆后 `new_item.id = allocate_item_id()`；树内节点按 id 去重显示（refresh + `_sync_layer_children` 两层 seen）；`canvas.deduplicate_items()`（同 id 留第一 + 几何指纹）在自动保存恢复/打开项目后调用。

**⑥ 选择模式右键菜单（按类分层）**
- 在**选择**模式下右键元素（或空白处）：命中元素先单选它，菜单四区：
  - **元素操作**：编辑文字 / 复制(克隆) / 删除 / 移动到图层（子菜单列出全部图层）；
  - **工具**：全部 9 种模式可勾选切换 + 自由截图；
  - **编辑**：撤销 Ctrl+Z / 重做 Ctrl+Y / 重复上一次命令 / 确认当前操作；
  - **画布**：复制标注图 / 清空画布。
- 配套：`duplicate_item`（克隆+偏移+选中副本）、`repeat_last_command`（重复 duplicate/delete/add_emoji/add_text/add_leader 四类）、`commandRequested/statusMessage` 信号与主窗口接线（状态栏 3 秒提示）。

**⑦ 关于按钮**
- 主工具栏最末尾（退出按钮之后）新增绿底「关于」按钮（#2F8F4E，52×26），点击弹「关于 图片标注大师 v1.5」：作者 **redmoonk**、版权 **© bk100**、版本 1.5、功能说明列表。窗口标题同步为「图片快速标注工具 v1.5」。

**验证**：`tests/regression_r27_v15.py`（r27 专项）+ r20/r21/r23/r24/r25/r26/smoke_test/_dpr_regression 全量 PASS；离屏渲染截图 `tests/_r27_v15_dark.png` / `tests/_r27_v15_light.png` 人工核验（树仅 2 表情、▶ 当前层、关于按钮、状态栏计数一致）。

---

## 20. v1.7 更新记录（9 项需求，全量回归通过）

**① 明暗主题「文字↔背景」全覆盖复核（需求5/8，window.py）**
- 根因：暗黑主题的 window QSS 会给输入控件（QSpinBox/QComboBox/QLineEdit）刷上调色板文字色；切回明亮清空 QSS 后，控件残留**暗色主题的灰色文字**（实测 text #A8A8A8 on #F0F0F0），正是「文字适应而背景不适应」看不清的来源。
- 修复：`_apply_light_theme()` 不再清空为原生，改为套用**显式明亮 QSS**——QLabel/QCheckBox/QComboBox/QSpinBox/QLineEdit/QListWidget/QMenu/QToolButton/QPushButton/QStatusBar/QToolTip 全部「文字 + 背景成对指定」（深字 #1A1A1A、白底 #FFFFFF、窗口 #F5F5F7、菜单选中蓝 #2f6fed），明暗两套 QSS 互不残留；暗黑主题逻辑不变。
- 离屏像素探针验证：暗黑→明亮切换后 线条粗细/箭头大小/端点符号/字体大小/行距 等输入控件均为「深色文字像素 + 白底」；明亮/暗黑面板整图渲染 OCR 全部标签可读。

**② 选中图层虚线框可整体拖动（需求1，canvas.py）**
- `_highlight_box()` 返回高亮层全部元素 export_bounds 并集（3px 内缩）；选择模式下点在框内空白（未命中元素、未命中形状手柄）→ 进入 `_layer_drag`，按住拖动整层所有元素一起移动，松开提交一次「操作前快照」撤销；框外空白点击仍清除高亮。正常标注模式不显示框。

**③ 形状手柄：独立缩放 / 绕中心旋转 / 移动（需求2，canvas.py + items.py）**
- 选中形状显示随旋转贴合其外接矩形的**蓝色虚线框 + 8 个蓝色缩放点 + 顶部橙色旋转点**（`_paint_shape_handles`）。
- 拖 8 点实时缩放（保持对边/对角不动、顶点按比例映射，最小 4px/scale 防塌陷）；拖旋转点绕形状中心实时旋转，`ShapeItem.rotation`（0–360°）随 `paint`（先平移到中心→rotate→平移回）、`hit_test`（命中点先逆旋转）、`export_bounds`（旋转后外接矩形）全程生效，并纳入 autosave 序列化（.anno/自动保存往返不丢）。
- 缩放/旋转按下时 `_snapshot()` 存「操作前」快照、结束时 `commit_op()` 提交——修复原 push_undo 在操作结束后快照导致撤销无效的问题。

**④ 右键按住立即平移（需求4，canvas.py）**
- `_rbtn` 改为 `{"pos","pan","switched"}`（移除长按计时键）：右键按下即记录；mouseMove 时**位移 >4px 立即 `_panning=True` 平移画布（零延迟，不再等 450ms 长按）**；未位移的短按释放才在选择模式弹分类菜单；从指令模式右键切换来的首次释放不弹菜单。`RBTN_LONG_MS` 常量保留兼容。

**⑤ 截图导入 1:1（需求3，screenshot.py）**
- `_capture` 从原生整屏底图按物理像素裁剪后，若 DPR≠1 且物理尺寸≠逻辑尺寸，`scaled` 缩回**逻辑尺寸**再 `setDevicePixelRatio(1.0)`——高分屏（125%/150%/200%）下截图导入画布后 100% 显示与用户框选的实际区域完全一致，不再人为放大；DPR=1 零重采样。

**⑥ 修复「无法打开项目文件」（需求6，window.py）**
- 用户报错截图（图3）：`There is no item named 'project.json' in the archive`——旧版保存时 `json.dumps(style)` 遇嵌套 QColor 抛 TypeError，zip 只写入 image.png，形成残缺存档。
- 修复：`_deep_color_hex()` 递归转换嵌套 QColor → JSON 先完整序列化 → `tempfile.mkstemp` 写 zip → `os.replace` 原子替换（任何一步失败不留残缺文件）；打开侧 `zipfile.is_zipfile` 校验 + 缺 project.json 时降级只加载图片并弹明确提示。保存→打开回环测试（含旋转形状/多图层）通过。

**⑦ 顶部工具栏重排 + 多格式导出（需求7，window.py）**
- 顺序锁定：新建空白 → 打开项目 → 打开本地图片 → 导入剪贴板 → 保存项目 → 导出(下拉) → 复制全部到剪贴板 → 撤销 → 重试 → 删除选中 → 删除全部 → 100% → 对齐 → 主题 → [Expanding 弹簧] → 关于 → 退出（关于/退出右对齐，退出在最右端）。
- 导出按钮图标改为「向下箭头入托盘」`_export_icon`（与保存项目软盘区分）；下拉 `EXPORT_FORMATS=("PNG","JPG","GIF","BMP","TIF","TIFF")` 六格式，统一 QImageWriter，`_last_export_fmt` 记忆上次格式；取消原独立导出按钮；`center_btn` 移除、新增 `align_btn`（绑定 `canvas.auto_layout`）；`act_save` 保留仅 Ctrl+S 快捷键。

**⑧ 图层树元素层内序号（需求8，layer_tree_panel.py）**
- 元素节点文字 `f"{idx+1}. {描述}"`，**每个图层独立从 1 起排**，互不干扰；顺序变化/文字变化时同步更新。

**⑨ 关于对话框 v1.7**
- 窗口标题「图片快速标注工具 v1.7」；关于：版本 1.7 / 作者 redmoonk / 版权 © bk100 / 功能说明（形状手柄、层虚线框拖动、右键菜单分层、多格式导出等）。

**验证**：`tests/smoke_test_v17.py`（v1.7 集成：形状手柄/旋转/缩放/整层拖动/截图 1:1/项目回环/层内序号）全过；r20/r23/r24/r25/r26/r27/r28/smoke_test 全量 PASS；明暗主题渲染 `tests/_v17_light|dark.png`、`_v17_panel_light|dark.png`、`_v17_tree_light|dark.png` 人工核验可读。

---

## 21. r31 更新记录（图层右键/图层拖拽/工具面板嵌入/空心弧修复）

**① 图层右键「置为顶层 / 置为底层」（layer_tree_panel.py）**
- 图层节点右键菜单在「上移一层/下移一层」后新增两项，一步移动到叠放最顶/最底，等价连续上/下移到底；复用 `requestReorder` 通道（`_bring_layer_to_edge` 按 `self._layers` 底层在前重排，singleShot 0 发出），已在对应边缘时菜单项禁用。

**② 拖拽图层行确定性重排（layer_tree_panel.py）**
- 废弃「图层拖拽走父类 `super().dropEvent`」：父类在 OnItem 指示符下会把图层嵌套成另一图层的子节点，且旧代码 dropEvent 内调用的 `_emit_layer_order_from_tree` 属于面板类、在树控件上必抛 AttributeError（被外层 try/except 吞掉，实际只靠 rowsMoved 兜底）。
- 新 `_manual_layer_reorder`：源/目标节点存活校验 → 解析目标顶层图层（图层行或元素子行的父层）→ 按 Above/Below 指示符（OnItem 按行内上下半区）计算插入行 → `takeTopLevelItem/insertTopLevelItem` 复用同一节点移动，**图层永远留在顶层、绝不嵌套**，元素归属不受影响；新增 `layerOrderEdited` 信号连接面板的 `_emit_layer_order_from_tree`。拖到空白处移到列表最末。

**③ 工具面板嵌入左右分栏独立竖列（window.py，详见 §7.4）**
- 右键工具面板选「嵌入：左面板右侧 / 右面板左侧」，或把浮动工具窗口拖到分栏缝隙自动吸附；嵌入后为 38px 独立竖列，⧉ 一键弹出。摆放位置 `tool_place` 随 settings.json 持久化并在下次启动恢复；嵌入期间保存干净的 3 列 main/splitter 状态，避免恢复失败。

**④ 修复「空心弧」形状（items.py）**
- 现象：空心弧被渲染成从画布左上角拉出的细长三角 + 局部小弧。根因：空 `QPainterPath` 直接 `arcTo` 会从隐式当前点 (0,0) 连直线到弧起点；且旧实现是「扇形饼」而非 Office 空心弧（Block Arc 环形扇段）。
- 修复：先 `moveTo` 外弧起点；外弧 45°→315°（270°，开口朝右）→ 端面线 → 52% 内圈反向弧 → 闭合，形成粗 C 形弧带；方形/扁/高外框均正确，路径严格落在外框内，环带可命中、内孔不命中（无填充时）。

**验证**：新增 `tests/regression_r31_layer_reorder_toolembed.py`（55+ 断言：右键置顶/置底与禁用态、六种拖拽位置与「拖拽=多次上移」等价性、无嵌套、工具面板七种摆放互转与分栏顺序、持久化往返恢复、空心弧几何/命中/绘制）全过；r26/r28/r29/r30 既有回归 PASS；离屏渲染 `tests/_r31_inner_left.png`、`_r31_inner_right.png`、`_r31_openarc.png` 人工核验。r23/smoke_v17/r25 的个别失败为 v2.0 既有漂移（按钮符号化、`【】`标签格式、形状手柄返回值数量变化），与本轮改动无关。
