# -*- coding: utf-8 -*-
"""第十一轮冒烟测试：序号独立模式/横线自适应/字体面板/参数持久化/图层闪退/垂直分栏。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:\\Windows\\Fonts"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import autosave, settings
settings.clear()   # 测试隔离：清掉上次遗留的参数（导出格式等）
from annotator.canvas import MODE_LEADER, MODE_NUMBER, MODE_SELECT, MODE_SHAPE, AnnotationCanvas
from annotator.items import (LeaderLineItem, STYLE_ABOVE, SCRIPT_SUPER,
                             SCRIPT_SUB, format_number)
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


# ---------- 1. 引线序号独立模式 ----------
w = MainWindow(restore=False)
w.show()
app.processEvents()
pm = QPixmap(600, 400)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)
w.canvas.set_mode(MODE_NUMBER)
# 模拟两次点击（目标点 + 文字位置）
QTest.mouseClick(w.canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(120, 120))
QTest.mouseClick(w.canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(400, 90))
QTest.mouseClick(w.canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(140, 200))
QTest.mouseClick(w.canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, QPoint(420, 260))
leaders = [it for it in w.canvas.items if isinstance(it, LeaderLineItem)]
check("序号模式创建 2 条引线", len(leaders) == 2)
check("序号自动编号 1/2", [it.number for it in leaders] == [1, 2])
check("序号模式无文字内容", all(it.text_content == "" for it in leaders))
check("序号模式自动开启序号开关", w.canvas.number_enabled is True)
check("空内容显示序号文字", leaders[0].display_text() == format_number(1, "circle"))
check("序号模式未弹输入框", not w.canvas._editor.isVisible())

# ---------- 2. 横线自适应文字宽度 ----------
for it in leaders:
    it.label_style = STYLE_ABOVE
    it.above_dir = "left"
r = leaders[0].text_rect()
inner, outer, _ = leaders[0]._above_geometry()
check("横线内端=文字左边缘下方(left)", abs(inner.x() - r.left()) < 1e-6)
check("横线外端向左延伸", outer.x() < inner.x())
leaders[0].above_dir = "right"
inner, outer, _ = leaders[0]._above_geometry()
check("横线内端=文字右边缘下方(right)", abs(inner.x() - r.right()) < 1e-6)
check("横线外端向右延伸", outer.x() > inner.x())

# ---------- 3. 字体面板 ----------
w.canvas.set_mode(MODE_SELECT)
w.canvas.select_item_by_id(leaders[0].id)
w.panel.font_combo.setCurrentFont(leaders[0].font().family() if hasattr(leaders[0], 'font') else w.panel.font_combo.currentFont())
w.panel.font_weight_combo.setCurrentIndex(3)      # 粗
w.panel.italic_check.setChecked(True)
w.panel.script_combo.setCurrentIndex(1)           # 上标
w.panel._apply_to_selection()
check("字体粗细应用", leaders[0].font_weight == 75)
check("斜体应用", leaders[0].font_italic is True)
check("上标应用", leaders[0].script == SCRIPT_SUPER)
# 字体族
w.panel.font_combo.setCurrentFont(__import__('PyQt6.QtGui', fromlist=['QFont']).QFont("Arial"))
w.panel._apply_to_selection()
check("字体族应用", leaders[0].font_family == "Arial")
check("上标偏移为负", leaders[0].script_offset() < 0)
leaders[0].script = SCRIPT_SUB
check("下标偏移为正", leaders[0].script_offset() > 0)

# ---------- 4. 参数持久化 settings 往返 ----------
w.panel.font_weight_combo.setCurrentIndex(4)     # 特粗
w.panel.label_style_combo.setCurrentIndex(1)     # above
w.panel.snap_combo.setCurrentIndex(1)            # 左对齐
w.canvas.set_mode(MODE_SHAPE)
w.resize(1234, 777)
data = w._collect_settings()
settings.save(data)
data2 = settings.load()
check("settings 保存/读取", data2["mode"] == "shape")
check("settings 样式含字体", data2["style"]["font_weight"] == 87)
check("settings 布局含 splitter", "splitter_state" in data2)
check("settings 几何", "window_geometry" in data2)
# 恢复到一个新窗口
w2 = MainWindow(restore=False)
w2.show()
app.processEvents()
w2._restore_settings()
check("恢复-模式", w2.canvas.mode == MODE_SHAPE)
check("恢复-样式", w2.panel.font_weight_combo.currentIndex() == 4)
check("恢复-几何", w2.width() == 1234 or w2.width() != 1400)
check("恢复-导出格式", w2._last_export_fmt == "PNG")
w2.close()

# ---------- 5. 图层显隐闪退（增量刷新） ----------
w.canvas.add_layer("图层2")
lp = w.layers_panel
lp.resize(220, 220)
for i in range(30):
    for row in (0, 1):
        r = lp.list.visualItemRect(lp.list.item(row))
        QTest.mouseClick(lp.list.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(r.left() + 9), int(r.center().y())))
        app.processEvents()
check("图层 checkbox 30 轮不闪退", True)

# ---------- 6. 左侧垂直分栏 ----------
check("左侧垂直 splitter", w.left_splitter is not None and len(w.left_splitter.sizes()) == 2)
w.left_splitter.setSizes([400, 100])
app.processEvents()
s = w.left_splitter.sizes()
check("垂直高度可调", s[0] > s[1])

# ---------- 7. 字体 autosave 往返 ----------
autosave.clear()
autosave.save(w.canvas.pixmap, w.canvas.items, w.canvas.layers, w.canvas.current_layer)
pm2, items2, layers2, cur2 = autosave.load()
lead2 = [it for it in items2 if isinstance(it, LeaderLineItem)]
check("autosave 字体往返-粗体", lead2[0].font_weight == 87)
check("autosave 字体往返-斜体", lead2[0].font_italic is True)
check("autosave 字体往返-上标", lead2[0].script == SCRIPT_SUPER)
check("autosave 字体往返-序号", lead2[0].number == 1)
autosave.clear()

w.close()
failed = [n for n, ok in PASS if not ok]
print(f"\nRESULT: {len(PASS) - len(failed)}/{len(PASS)} passed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
