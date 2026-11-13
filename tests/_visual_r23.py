# -*- coding: utf-8 -*-
"""r23 可视化核验：折线绘制中预览（顶点+磁吸引导）与已提交异形折线。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QPixmap, QColor
from PyQt6.QtWidgets import QApplication
from annotator.window import MainWindow
from annotator.items import SHAPE_LINE

app = QApplication([])
win = MainWindow(restore=False)
win.resize(1000, 760); win.show(); app.processEvents()
cv = win.canvas
pm = QPixmap(640, 480); pm.fill(QColor("#FAFAFA"))
cv.load_pixmap(pm, fit=False); cv.resize(900, 640); cv.scale=1.0; cv.offset=QPointF(20,20)
cv.set_mode("shape"); win.panel._set_shape_val(SHAPE_LINE)

def ev(t, x, y, btn=Qt.MouseButton.NoButton, btns=Qt.MouseButton.NoButton):
    return QMouseEvent(t, QPointF(x+20, y+20), btn, btns, Qt.KeyboardModifier.NoModifier)
def press(x,y): cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress,x,y,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton))
def move(x,y): cv.mouseMoveEvent(ev(QEvent.Type.MouseMove,x,y))

# 已确认 (60,80)->(300,80 水平吸附)，当前段竖直吸附到 (300,300)
press(60,80); move(300,83); press(300,83); move(303,300)
cv.grab().save(os.path.join(ROOT,"tests","_r23_preview.png"))
# 提交一条异形折线并导出
press(303,300); move(480,360); press(480,360)
cv.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
cv.render_export().save(os.path.join(ROOT,"tests","_r23_export.png"))
print("saved")
app.quit(); os._exit(0)
