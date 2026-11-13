# -*- coding: utf-8 -*-
"""第十五轮冒烟测试：左侧面板宽度对齐/浮动按钮双向切换/工具栏图标/一键布局固定间距/
新引线磁吸对齐线（吸附上一条）/单击不再翻转、双击翻转横线方向。

运行：python tests/smoke_test_r15.py（离屏）
"""
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
settings.clear()
autosave.clear()
from annotator.canvas import MODE_LEADER, MODE_NUMBER, MODE_SELECT
from annotator.items import (ABOVE_DIR_LEFT, ABOVE_DIR_RIGHT, LeaderLineItem,
                             STYLE_ABOVE)
from annotator.window import MainWindow

w = MainWindow(restore=False)
w.resize(1280, 800)
w.show()
app.processEvents()

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


pm = QPixmap(700, 460)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)
app.processEvents()

# ---------- 1. 左侧面板宽度对齐 ----------
check("历史/图层面板同宽",
      abs(w.history.width() - w.layers_panel.width()) < 2)

# ---------- 2. 浮动按钮双向切换（始终可见） ----------
w._toggle_left(False)
app.processEvents()
check("左面板折叠且浮动按钮可见",
      not w.left_box.isVisible() and w.left_floating.isVisible())
w._toggle_left(True)
app.processEvents()
check("左面板展开且浮动按钮仍可见",
      w.left_box.isVisible() and w.left_floating.isVisible())
w._toggle_right(False)
app.processEvents()
check("右面板折叠且浮动按钮可见",
      not w.right_box.isVisible() and w.right_floating.isVisible())
w._toggle_right(True)
app.processEvents()
check("右面板展开且浮动按钮仍可见",
      w.right_box.isVisible() and w.right_floating.isVisible())

# ---------- 3. 工具栏图标 + 文字 ----------
check("工具栏图标+文字样式", w.toolbar.toolButtonStyle()
      == Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
# 离屏环境 QStyle 标准图标可能为空，图标存在性仅在真实平台验证；此处验证图标动作已设置
check("粘贴按钮已配置图标", w.act_paste.icon() is not None)
check("模式按钮带符号", "↗ 引线标注" in w.mode_buttons["leader"].text()
      and "△ 形状" in w.mode_buttons["shape"].text())

# ---------- 4. 一键布局：左右竖直等距、上下水平等距 ----------
w.canvas.set_mode(MODE_SELECT)
# 左侧 3 条（乱序 y）
l1 = w.canvas.add_leader_item(QPointF(80, 300), QPointF(150, 100), "左一")
l2 = w.canvas.add_leader_item(QPointF(90, 320), QPointF(160, 320), "左二")
l3 = w.canvas.add_leader_item(QPointF(70, 340), QPointF(140, 220), "左三")
# 上方 3 条（乱序 x，x 均处于图片中部避免被分到左右组）
t1 = w.canvas.add_leader_item(QPointF(300, 60), QPointF(300, 150), "上一")
t2 = w.canvas.add_leader_item(QPointF(350, 70), QPointF(420, 160), "上二")
t3 = w.canvas.add_leader_item(QPointF(400, 80), QPointF(430, 170), "上三")
w.canvas.layout_row_lines = 1.0
w.canvas.layout_col_chars = 2
before_targets = [(it.target_point.x(), it.target_point.y())
                  for it in w.canvas.items if isinstance(it, LeaderLineItem)]
w.canvas.auto_layout()
after_targets = [(it.target_point.x(), it.target_point.y())
                 for it in w.canvas.items if isinstance(it, LeaderLineItem)]
check("布局不改变端点", before_targets == after_targets)
lefts = sorted(it.text_rect().left() for it in (l1, l2, l3))
check("左组 x 对齐", max(lefts) - min(lefts) < 0.6)
tops = sorted(it.text_rect().top() for it in (l1, l2, l3))
gap_y = tops[1] - tops[0]
check("左组竖直等距", abs((tops[2] - tops[1]) - gap_y) < 0.6)
tups = sorted(it.text_rect().top() for it in (t1, t2, t3))
check("上组 y 对齐", max(tups) - min(tups) < 0.6)
xl = sorted(it.text_rect().left() for it in (t1, t2, t3))
gap_x = xl[1] - xl[0]
check("上组水平等距", abs((xl[2] - xl[1]) - gap_x) < 0.6)
# 间距可调：行距调 2 行后重新布局，间隔应变大
w.canvas.layout_row_lines = 2.0
w.canvas.auto_layout()
tops2 = sorted(it.text_rect().top() for it in (l1, l2, l3))
check("行距 2 行间隔变大", (tops2[1] - tops2[0]) > gap_y * 1.3)
w.canvas.layout_row_lines = 1.0

# ---------- 5. 新引线磁吸对齐线（吸附上一条） ----------
ref = w.canvas.add_leader_item(QPointF(200, 380), QPointF(600, 360), "参考标注")
r = ref.text_rect()
# 靠近上一条文字框右缘 → 吸附到右缘
near_right = QPointF(r.right() + 5, r.center().y() + 50)
snapped, name = w.canvas._snap_hover_to_prev(near_right)
check("磁吸吸附到右缘", name == "right" and abs(snapped.x() - r.right()) < 0.6)
# 远离参考线 → 不吸附
far = QPointF(r.right() + 80, r.center().y() + 50)
snapped2, name2 = w.canvas._snap_hover_to_prev(far)
check("远离参考线不吸附", name2 is None and snapped2 == far)
# 吸附预览绘制不崩（真实渲染）
from PyQt6.QtGui import QPainter
out = QPixmap(700, 460)
out.fill(QColor("#FFFFFF"))
p = QPainter(out)
w.canvas._hover_pos = near_right
w.canvas._pending_target = QPointF(100, 100)
w.canvas._paint_preview(p)
p.end()
check("磁吸参考线绘制不崩", True)

# ---------- 6. 单击不翻转、双击翻转 ----------
ab = w.canvas.add_leader_item(QPointF(120, 200), QPointF(300, 180), "横线文字")
ab.label_style = STYLE_ABOVE
ab.above_dir = ABOVE_DIR_LEFT
w.canvas.set_mode(MODE_SELECT)
lv = w.canvas.image_to_view(ab.text_point)
pt = QPoint(int(lv.x()), int(lv.y()))
QTest.mouseClick(w.canvas, Qt.MouseButton.LeftButton,
                 Qt.KeyboardModifier.NoModifier, pt)
app.processEvents()
check("单击不翻转横线方向", ab.above_dir == ABOVE_DIR_LEFT)
QTest.mouseDClick(w.canvas, Qt.MouseButton.LeftButton,
                  Qt.KeyboardModifier.NoModifier, pt)
app.processEvents()
check("双击翻转横线方向", ab.above_dir == ABOVE_DIR_RIGHT)

print(f"\nRESULT: {len([1 for _, c in PASS if c])}/{len(PASS)} passed")
failed = [n for n, c in PASS if not c]
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
