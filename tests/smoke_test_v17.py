# -*- coding: utf-8 -*-
"""v1.7 集成验证：形状手柄、层虚线框拖动、截图1:1、项目存取、层内序号。"""
import os, sys, tempfile, json, zipfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtGui import QPixmap, QColor, QImage, QMouseEvent
from PyQt6.QtCore import QPointF, Qt, QPoint, QEvent
from annotator.window import MainWindow
from annotator.items import ShapeItem, LeaderLineItem

FAILS = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)

app = QApplication([])
win = MainWindow(restore=False)
win.show()
app.processEvents()
cv = win.canvas

def mev(typ, pos, btn=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.NoButton,
        mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(typ, QPointF(*pos), QPointF(*pos), btn, buttons, mods)

def V(ix, iy):
    """图片坐标 → 视图坐标（适配任意 offset/scale）。"""
    p = cv.image_to_view(QPointF(ix, iy))
    return (p.x(), p.y())

def gi(iid):
    """按 id 取当前 items 中的元素（撤销/重做会替换对象引用）。"""
    return next(it for it in cv.items if it.id == iid)

# ---------- 0. 底图与元素 ----------
pm = QPixmap(800, 600)
pm.fill(QColor("#FFFFFF"))
cv.load_pixmap(pm, fit=False)
cv.scale = 1.0
cv.offset = QPointF(0.0, 0.0)
sh = ShapeItem((100, 100), (300, 220), "ellipse", border_color="#E5485C")
sh.layer_id = cv.layers[0].id
cv.items = [sh]
cv.select_layer(cv.layers[0].id)
cv.set_mode("select")
app.processEvents()

# ---------- 1. 形状手柄：选中后出现旋转/缩放点 ----------
cv.select_item_by_id(sh.id)
cv.update()
pts, rh = cv._shape_handle_pts(sh)
check(len(pts) == 8, f"形状缩放手柄 8 个点（实际 {len(pts)}）")

# 旋转：点击旋转点拖动 → rotation 变化且撤销栈新增
# v1.7 优化：按鼠标角速度累加（修正旧版角度单位混用），拖直线上方不再误转；
# 绕中心横向拖动（从顶部手柄到右侧）即旋转。
before_rot = sh.rotation
rot_pt = rh
rx, ry = V(rot_pt.x(), rot_pt.y())
cv.mousePressEvent(mev(QEvent.Type.MouseButtonPress, (rx, ry),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
check(cv._shape_edit is not None, "按下旋转点进入形状编辑")
# 从顶部手柄拖到中心正右侧（绕中心旋转 90°，单帧限速 25° 仍应生效）
_cc = cv._shape_edit["center"]
tx, ty = V(_cc.x() + 90, _cc.y())
cv.mouseMoveEvent(mev(QEvent.Type.MouseMove, (tx, ty),
                      Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
cv.mouseReleaseEvent(mev(QEvent.Type.MouseButtonRelease, (tx, ty),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
check(abs(sh.rotation - before_rot) > 0.01, f"旋转生效（{before_rot} -> {sh.rotation:.1f}）")
check(len(cv.undo_stack) >= 1, "旋转产生撤销记录")
cv.undo()
sh = gi(sh.id)
check(abs(sh.rotation - before_rot) < 1e-6, "撤销恢复原旋转")

# 缩放：拖右下角点 → 尺寸变化（撤销会清空选中，重新选中）
cv.select_item_by_id(sh.id)
pts, rh = cv._shape_handle_pts(sh)
br = pts[4]  # 右下角点（宽高同时变化）
w0, h0 = sh.rect().width(), sh.rect().height()
bx, by = V(br.x(), br.y())
cv.mousePressEvent(mev(QEvent.Type.MouseButtonPress, (bx, by),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
check(cv._shape_edit is not None and cv._shape_edit["kind"] == "resize", "按下缩放点进入 resize")
t2x, t2y = V(br.x() + 60, br.y() + 40)
cv.mouseMoveEvent(mev(QEvent.Type.MouseMove, (t2x, t2y),
                      Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
cv.mouseReleaseEvent(mev(QEvent.Type.MouseButtonRelease, (t2x, t2y),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
sh = gi(sh.id)
check(sh.rect().width() > w0 and sh.rect().height() > h0,
      f"缩放生效（{w0}x{h0} -> {sh.rect().width()}x{sh.rect().height()}）")

# ---------- 2. 层虚线框拖动 ----------
sh2 = ShapeItem((400, 300), (500, 400), "rect", border_color="#2F8F4E")
sh2.layer_id = cv.layers[0].id
cv.items.append(sh2)
cv.select_layer(cv.layers[0].id)
app.processEvents()
box = cv._highlight_box()
check(box is not None, "高亮层存在虚线框")
# 选一个在框内、但不落在任何元素上的空白点（图像坐标）
px, py = 370.0, 280.0
hit0 = None
for it in cv.items:
    if it.hit_test(QPointF(px, py), 8.0 / cv.scale):
        hit0 = it
check(hit0 is None, "空白点未命中任何元素")
vx, vy = V(px, py)
c0 = gi(sh.id).rect().center()   # 缩放后中心（v1.7 锚点固定缩放，中心会随拖角变化）
cv.mousePressEvent(mev(QEvent.Type.MouseButtonPress, (vx, vy),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
check(cv._layer_drag is not None, "框内按下进入层拖动")
mx, my = V(px + 40, py + 30)
cv.mouseMoveEvent(mev(QEvent.Type.MouseMove, (mx, my),
                      Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
cv.mouseReleaseEvent(mev(QEvent.Type.MouseButtonRelease, (mx, my),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
sh = gi(sh.id)
c = sh.rect().center()
check(abs(c.x() - c0.x() - 40) < 1e-6 and abs(c.y() - c0.y() - 30) < 1e-6,
      f"整层拖动生效（中心 +40,+30 → {c.x():.0f},{c.y():.0f}）")
check(len(cv.undo_stack) >= 1, "层拖动产生撤销记录")
cv.undo()
sh = gi(sh.id)
c = sh.rect().center()
check(abs(c.x() - c0.x()) < 1e-6 and abs(c.y() - c0.y()) < 1e-6, "撤销层拖动")
cv.redo()
sh = gi(sh.id)
c = sh.rect().center()
check(abs(c.x() - c0.x() - 40) < 1e-6, "重做层拖动")

# ---------- 3. 截图 1:1（DPR 模拟） ----------
from annotator.screenshot import ScreenshotOverlay
from PyQt6.QtCore import QRect

def capture_with(bg_pm, lrect):
    ov = ScreenshotOverlay(win.screen())
    ov._bg = bg_pm
    got = []
    ov.captured.connect(lambda p: got.append(p))
    ov._capture(QRect(*lrect))
    return got[0] if got else None

pm2 = QPixmap(400, 300)
pm2.fill(QColor("#123456"))
pm2.setDevicePixelRatio(2.0)  # 高分屏 DPR=2
shot = capture_with(pm2, (0, 0, 400, 300))
check(shot is not None and shot.width() == 400 and shot.height() == 300,
      f"DPR=2 截图缩回逻辑尺寸（{shot.width() if shot else '?'}x{shot.height() if shot else '?'}，期望 400x300）")

pm3 = QPixmap(320, 240)
pm3.fill(QColor("#654321"))
pm3.setDevicePixelRatio(1.0)
shot3 = capture_with(pm3, (0, 0, 320, 240))
check(shot3 is not None and shot3.width() == 320 and shot3.height() == 240, "DPR=1 截图原尺寸")

# ---------- 3.5 多格式导出（PNG/JPG/GIF/BMP/TIF/TIFF） ----------
def fake_save(*a, **k):
    d = a[2] if len(a) >= 3 else "x.png"
    ext = d.rsplit(".", 1)[-1].lower()
    return (os.path.join(tempfile.gettempdir(), f"fmt_test.{ext}"), "")
QFileDialog.getSaveFileName = staticmethod(fake_save)
for fmt in ("PNG", "JPG", "GIF", "BMP", "TIF", "TIFF"):
    fp = os.path.join(tempfile.gettempdir(), "fmt_test." + fmt.lower())
    if os.path.exists(fp):
        os.remove(fp)
    win.export_image(fmt)
    ok = os.path.exists(fp) and os.path.getsize(fp) > 0
    check(ok, f"导出 {fmt} 成功" + (f"（{os.path.getsize(fp)} 字节）" if ok else ""))

# ---------- 4. 项目存取回环（含旋转/图层/元素） ----------
sh.rotation = 35.0
cv.items = [sh, sh2]
cv.layers.append(cv.add_layer("图层2"))
sh2.layer_id = cv.layers[1].id
p = os.path.join(tempfile.gettempdir(), "v17_roundtrip.anno")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (p, "标注项目 (*.anno)"))
win.save_project()
app.processEvents()
check(os.path.exists(p), "项目文件已保存")
with zipfile.ZipFile(p) as z:
    names = z.namelist()
    check("project.json" in names and "image.png" in names,
          f"zip 内含 project.json + image.png（{names}）")
    data = json.loads(z.read("project.json").decode("utf-8"))
    shapes = [it for it in data.get("items", []) if it.get("type") == "shape"]
    rots = [s.get("rotation") for s in shapes if s.get("rotation") is not None]
    check(any(abs(r - 35.0) < 1e-6 for r in rots), f"rotation 已存档（{rots}）")

cv2_state = (len(cv.items), len(cv.layers))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (p, "标注项目 (*.anno)"))
win._confirm_overwrite = lambda *a, **k: True
win.open_project()
app.processEvents()
check(len(cv.items) == cv2_state[0], f"打开项目元素数一致（{len(cv.items)}/{cv2_state[0]}）")
check(len(cv.layers) == cv2_state[1], f"打开项目图层数一致（{len(cv.layers)}/{cv2_state[1]}）")
sh_loaded = [it for it in cv.items if isinstance(it, ShapeItem) and it.rotation is not None]
check(any(abs(it.rotation - 35.0) < 1e-6 for it in sh_loaded), "打开后 rotation 恢复")

# ---------- 5. 层内元素序号 ----------
win._refresh_layer_tree()
lt = win.layer_tree
def node_texts():
    out = {}
    for lid, node in lt._layer_items.items():
        out[lid] = [node.child(i).text(0) for i in range(node.childCount())]
    return out
txt = node_texts()
for lid, texts in txt.items():
    for i, t in enumerate(texts):
        check(t.startswith(f"{i + 1}. "), f"图层 {lid} 第 {i+1} 项序号前缀（{t[:20]}）")

os.remove(p)
print("==== v1.7 集成验证结束 ====" if not FAILS else f"==== 失败 {len(FAILS)} 项 ====")
sys.exit(1 if FAILS else 0)
