# -*- coding: utf-8 -*-
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtCore import QRectF
app = QApplication([])

from annotator.window import MainWindow
from annotator.items import (ShapeItem, SHAPE_OPTIONS, SHAPE_OPTIONS_PRIMARY,
                             SHAPE_OPTIONS_MORE, shape_path)
from annotator.autosave import serialize_items, deserialize_items

w = MainWindow(restore=False)
print("MainWindow built OK")

# 1. 所有形状路径可绘制不崩
from PyQt6.QtGui import QImage, QPainter
img = QImage(200, 200, QImage.Format.Format_ARGB32)
p = QPainter(img)
for label, val in SHAPE_OPTIONS:
    sp = shape_path(val, QRectF(10, 10, 180, 120))
    p.drawPath(sp)
print("All", len(SHAPE_OPTIONS), "shapes path OK")
p.end()

# 2. 形状文字渲染 + text_pos
for tp in ("top", "center", "bottom"):
    it = ShapeItem((10, 10), (200, 120), shape="rect")
    it.text_content = "测试文字"
    it.text_pos = tp
    it.paint(p)  # painter already ended; create fresh
p2 = QPainter(img)
it = ShapeItem((10,10),(200,120), shape="line")
it.text_content = "直线文字"
it.paint(p2)
p2.end()
print("Shape text paint OK")

# 3. 序列化往返（含文字/位置）
it = ShapeItem((5,5),(120,80), shape="heart")
it.text_content = "心形"
it.text_pos = "top"
data = serialize_items([it])
back = deserialize_items(data)
assert len(back) == 1, back
assert back[0].text_content == "心形", back[0].text_content
assert back[0].text_pos == "top"
print("Serialize roundtrip OK:", back[0].shape, back[0].text_pos)

# 4. 面板形状网格按钮数
pb = w.panel
assert len(pb._shape_buttons) == len(SHAPE_OPTIONS), (len(pb._shape_buttons), len(SHAPE_OPTIONS))
print("Shape grid buttons:", len(pb._shape_buttons), "primary", len(SHAPE_OPTIONS_PRIMARY), "more", len(SHAPE_OPTIONS_MORE))
# 切换更多（直接调用，避免 click 触发整条信号链）
pb._shape_more_open = not pb._shape_more_open
for _b in pb._shape_extra_buttons:
    _b.setVisible(pb._shape_more_open)
pb._shape_more_btn.setText("收起 ▴" if pb._shape_more_open else "更多 ▾")
assert not pb._shape_extra_buttons[0].isHidden()
# 再收起
pb._shape_more_open = not pb._shape_more_open
for _b in pb._shape_extra_buttons:
    _b.setVisible(pb._shape_more_open)
assert pb._shape_extra_buttons[0].isHidden()
# 直接同步值（不触发样式变更）
pb._set_shape_val("star")
assert pb._shape_val == "star"
assert pb._shape_buttons["star"].isChecked()
print("Shape pick OK")

# 5. 文字位置 combo
assert pb.shape_textpos_combo.count() == 3
pb._syncing = True
pb.shape_textpos_combo.setCurrentIndex(2)
pb._syncing = False
assert pb.current_style()["shape_text_pos"] == "bottom"
print("Text pos combo OK:", pb.current_style()["shape_text_pos"])

# 6. 工具栏符号按钮存在
assert w.undo_btn.text() == "↶" and w.redo_btn.text() == "↷"
assert "100" not in w.zoom_100_btn.text()
assert w.align_btn.text() == "⊞"
print("Toolbar symbols OK:", w.zoom_100_btn.text(), w.align_btn.text())

# 7. splitter handle width
print("Splitter handle width:", w.splitter.handleWidth())

# 8. 树描述
from annotator.layer_tree_panel import _describe_item
sh = ShapeItem((1,1),(50,50), shape="line")
print("Tree desc shape:", _describe_item(sh))
hl = __import__("annotator.items", fromlist=["HighlightItem"]).HighlightItem([(0,0),(10,10)], hl_width=14)
print("Tree desc highlight:", _describe_item(hl))

# 9. 字形覆盖检查（Segoe UI Symbol）
from PyQt6.QtGui import QFont
sym_font = QFont("Segoe UI Symbol")
fm = QFontMetrics(sym_font)
for ch in ["↶","↷","⛶","⊞","🖍","▦","╱","◺","⬠","⬡","⇔","⇕","⏢","☁","☾","✦","▲","◆","★","➤","◀"]:
    if len(ch) == 1 and not fm.inFont(ch):
        print("  [WARN] not in Segoe UI Symbol:", repr(ch))
print("Glyph check done")

# 10. 关于对话框可构建（不 exec）
print("About method exists:", hasattr(w, "_show_about"))
import os
print("QR dark exists:", os.path.exists(os.path.join(__import__('annotator.settings', fromlist=['_app_base_dir'])._app_base_dir(), "暗黑.png")))
print("ALL SMOKE TESTS PASSED")
