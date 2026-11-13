# -*- coding: utf-8 -*-
"""第十六轮冒烟测试：颜色持久化 #AARRGGBB 往返正确性（修复 RGBA 顺序 bug）。

背景：_color_hex 此前输出 #RRGGBBAA，而 Qt 8 位 hex 按 #AARRGGBB 解析，
导致 settings/.anno 恢复后颜色错乱（红线变蓝、黑字变透明不可见）。
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:\\Windows\\Fonts"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import autosave, settings
settings.clear()
autosave.clear()
from annotator.items import LeaderLineItem, STYLE_ABOVE
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


# ---------- 1. _color_hex 往返（ARGB） ----------
for name, src in (("红", QColor(255, 0, 0, 255)), ("黑", QColor(0, 0, 0, 255)),
                  ("蓝", QColor(0, 0, 255, 255)), ("半透明绿", QColor(0, 128, 0, 128))):
    h = MainWindow._color_hex(src)
    back = QColor(h)
    check(f"{name} 往返 {src.name()}(a{src.alpha()}) -> {h} -> {back.name()}(a{back.alpha()})",
          back.red() == src.red() and back.green() == src.green()
          and back.blue() == src.blue() and back.alpha() == src.alpha())

# ---------- 2. settings 保存/恢复样式颜色 ----------
w = MainWindow(restore=False)
w.show()
app.processEvents()
pm = QPixmap(600, 400)
pm.fill(QColor("#FFFFFF"))
w.canvas.load_pixmap(pm)
app.processEvents()

# 设置红色线条 + 黑色文字 + 蓝色填充，保存设置
w.panel.line_color_btn._color = QColor("#FF0000")
w.panel.text_color_btn._color = QColor("#000000")
w.panel.bg_border_btn._color = QColor("#00FF00")
data = w._collect_settings()
st = data["style"]
check("settings 颜色为 ARGB hex", st["line_color"].startswith("#FF") and
      st["text_color"] == "#FF000000")
# 直接按恢复路径解析
from PyQt6.QtGui import QColor as QC
check("恢复后红线条", QC(st["line_color"]).name() == "#ff0000")
check("恢复后黑文字", QC(st["text_color"]).name() == "#000000")
check("恢复后绿边框", QC(st["bg_border_color"]).name() == "#00ff00")

# ---------- 3. 引线创建使用面板样式，颜色正确 ----------
it = w.canvas.add_leader_item(QPointF(100, 100), QPointF(300, 80), "颜色测试")
it.apply_style(st)
check("引线线条红色", it.line_color.name() == "#ff0000")
check("引线文字黑色", it.text_color.name() == "#000000")
check("引线边框绿色", it.bg_border_color.name() == "#00ff00")
check("文字不透明", it.text_color.alpha() == 255)

# ---------- 4. 渲染后文字存在（像素级：导出图含黑色文字像素） ----------
it.label_style = STYLE_ABOVE
print("DBG rect:", it.text_rect(), "color:", it.text_color.name(), it.text_color.alpha())
out = w.canvas.render_export()
print("DBG export:", out.width(), out.height())
out.save(os.path.join(os.path.dirname(__file__), "_r16_out.png"), "PNG")
img = out
dark = 0
for y in range(0, img.height(), 2):
    for x in range(0, img.width(), 2):
        c = img.pixelColor(x, y)
        if c.red() < 120 and c.green() < 120 and c.blue() < 120:
            dark += 1
check("导出图含深色文字像素", dark > 20)

print(f"\nRESULT: {len([1 for _, c in PASS if c])}/{len(PASS)} passed")
failed = [n for n, c in PASS if not c]
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
