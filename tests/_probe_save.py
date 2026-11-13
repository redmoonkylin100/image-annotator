# -*- coding: utf-8 -*-
"""复现 save_project JSON 序列化失败（project.json 缺失根因）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QFileDialog

app = QApplication([])
from annotator.window import MainWindow
win = MainWindow(restore=False)
win.resize(1280, 800)
win.show()
app.processEvents()
cv = win.canvas

pm = QPixmap(600, 400)
pm.fill(QColor("#FFFFFF"))
cv.load_pixmap(pm)
app.processEvents()

# 添加各类元素
cv.set_mode("leader")
cv.add_leader_item(QPointF(100, 100), QPointF(250, 60), "引线")
cv.set_mode("text")
cv.add_text_item(QPointF(300, 120), "文本")
cv.set_mode("emoji")
cv.add_emoji_item(QPointF(400, 250), "😀", 48)
cv.set_mode("shape")
cv._line_points = [QPointF(50, 300), QPointF(150, 320)]
cv._line_cursor = QPointF(52, 302)
cv._finish_line_path()   # 闭合折线（v1.6 新形态）
cv.set_mode("pen")
cv._pen_points = [QPointF(10, 10), QPointF(50, 40), QPointF(90, 20)]
cv.add_pen_item(cv._pen_points)
cv.set_mode("highlight")
cv._hl_points = [QPointF(200, 200), QPointF(260, 220)]
cv.add_highlight_item(cv._hl_points)
cv.set_mode("mosaic")
cv.add_mosaic_item(QPointF(300, 280), QPointF(380, 330))
cv.set_mode("select")
app.processEvents()
print("元素数:", len(cv.items), flush=True)

# 直接构建 payload 并尝试 json.dumps（复现保存逻辑）
import io as _io
import json
import zipfile
from PyQt6.QtCore import QBuffer
from annotator import autosave

buf = QBuffer()
buf.open(QBuffer.OpenModeFlag.WriteOnly)
cv.pixmap.toImage().save(buf, "PNG")
st = dict(win.panel.current_style())
for k, v in list(st.items()):
    if isinstance(v, QColor):
        st[k] = win._color_hex(v)
payload = {
    "items": autosave.serialize_items(cv.items),
    "layers": autosave.serialize_layers(cv.layers),
    "current_layer": cv.current_layer,
    "style": st,
    "number_enabled": cv.number_enabled,
    "number_format": cv.number_format,
    "snap_mode": cv.snap_mode,
}
try:
    js = json.dumps(payload, ensure_ascii=False)
    print("JSON dumps OK, len =", len(js), flush=True)
except (TypeError, ValueError) as e:
    print("JSON 失败:", type(e).__name__, e, flush=True)
    # 找出具体问题字段
    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, path + "/" + str(k))
        elif isinstance(o, (list, tuple)):
            for i, v in enumerate(o):
                walk(v, path + f"[{i}]")
        else:
            try:
                json.dumps(o)
            except (TypeError, ValueError) as e2:
                print("  问题值:", path, "=", type(o).__name__, repr(o)[:120], flush=True)
    walk(payload)
    # 再单独测 serialize_items 输出
    print("--- serialize_items 输出中非 JSON 值 ---", flush=True)
    try:
        si = autosave.serialize_items(cv.items)
        walk(si, "items")
    except Exception as e3:
        print("serialize_items 本身抛错:", e3, flush=True)

# 模拟 save_project 落盘到临时文件，检查 zip 内容
try:
    from PyQt6.QtWidgets import QMessageBox
    orig = QMessageBox.warning
    msgs = []
    QMessageBox.warning = lambda *a, **k: msgs.append(a[2] if len(a) > 2 else k)
    save_path = os.path.join(ROOT, "tests", "_probe_save.anno")
    if os.path.exists(save_path):
        os.remove(save_path)
    orig_qfd = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (save_path, "标注项目 (*.anno)"))
    try:
        win.save_project()
    finally:
        QFileDialog.getSaveFileName = orig_qfd
        QMessageBox.warning = orig
    print("保存弹窗:", msgs, flush=True)
    if os.path.exists(save_path):
        with zipfile.ZipFile(save_path) as z:
            print("zip 内容:", z.namelist(), flush=True)
        os.remove(save_path)
    else:
        print("未生成文件", flush=True)
except Exception as e:
    print("save_project 抛错:", type(e).__name__, e, flush=True)
print("DONE", flush=True)
