# -*- coding: utf-8 -*-
"""回归：截图真实清晰度策略（不预处理 + 原生底图无损裁剪）+ 高 DPI 外框一致性。

要点：
- 遮罩底图保留 grabWindow 的原生物理像素与 DPR，不做缩放预处理；
- 选区内用 clip + QPoint 直绘，与真实屏幕 1:1；
- 最终截图从原生底图按物理像素 QPixmap.copy 裁剪（零重采样），DPR 归 1 输出；
- 画布 drawPixmap 与外框因此尺寸一致（外框不再比图片大）。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.canvas import AnnotationCanvas
from annotator.screenshot import ScreenshotOverlay

app = QApplication([])
RW, RH = 240, 180  # 选区逻辑尺寸


def make_native_bg(dpr, patterned=False):
    """模拟 screen.grabWindow：物理像素 = 逻辑*dpr，自带 DPR。"""
    pw, ph = round(RW * dpr * 2), round(RH * dpr * 2)   # 整屏比选区大
    pm = QPixmap(pw, ph)
    p = QPainter(pm)
    p.fillRect(0, 0, pw, ph, QColor("#E8332E"))
    if patterned:  # 1 物理像素黑白竖条纹，用于清晰度判定
        for x in range(pw):
            p.fillRect(x, 0, 1, ph,
                       QColor(0, 0, 0) if x % 2 == 0 else QColor(255, 255, 255))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def capture_from_bg(bg, local_rect):
    """复刻修复后 ScreenshotOverlay._capture：物理像素无损裁剪。"""
    dpr = bg.devicePixelRatio() or 1.0
    bw, bh = bg.width(), bg.height()
    cx = max(0, min(round(local_rect.x() * dpr), bw - 1))
    cy = max(0, min(round(local_rect.y() * dpr), bh - 1))
    cw = max(1, min(round(local_rect.width() * dpr), bw - cx))
    ch = max(1, min(round(local_rect.height() * dpr), bh - cy))
    shot = bg.copy(QRect(cx, cy, cw, ch))
    shot.setDevicePixelRatio(1.0)
    return shot


def is_red(c):
    return c.red() > 180 and c.green() < 90 and c.blue() < 90


class FakeScreen:
    def __init__(self, bg):
        self._bg = bg
    def geometry(self):
        dpr = self._bg.devicePixelRatio()
        return QRect(0, 0, round(self._bg.width() / dpr),
                     round(self._bg.height() / dpr))
    def grabWindow(self, *a):
        return self._bg


# ---------- 1) 输出分辨率/无损裁剪/外框一致，覆盖多种 DPR ----------
for dpr in (1.0, 1.25, 1.5, 2.0):
    bg = make_native_bg(dpr)
    pw, ph = round(RW * dpr), round(RH * dpr)

    # 用真实 ScreenshotOverlay._capture 走一遍（注入原生 bg）
    ov = ScreenshotOverlay(FakeScreen(bg))
    ov._bg = bg
    got = {}
    ov.captured.connect(lambda m: got.update(m=m))
    ov._capture(QRect(0, 0, RW, RH))
    shot = got["m"]

    assert shot.devicePixelRatio() == 1.0, f"dpr={dpr} 输出 DPR 应归 1"
    assert shot.width() == pw and shot.height() == ph, \
        f"dpr={dpr} 应无损裁剪出原生 {pw}x{ph}，实际 {shot.width()}x{shot.height()}"

    # 无损：裁剪结果必须与底图对应区域逐像素一致（零重采样）
    bi, si = bg.toImage(), shot.toImage()
    mismatch = sum(1 for x in range(pw) for y in range(ph)
                   if si.pixelColor(x, y) != bi.pixelColor(x, y))
    assert mismatch == 0, f"dpr={dpr} 裁剪存在 {mismatch} 个被重采样像素"

    # 画布载入后外框与图片严格重合
    canvas = AnnotationCanvas(); canvas.resize(1000, 900); canvas.show()
    app.processEvents()
    canvas.load_pixmap(shot); app.processEvents()
    img = canvas.grab().toImage()
    tl = canvas.image_to_view(QPointF(0, 0))
    br = canvas.image_to_view(QPointF(pw, ph))
    x0, y0, x1, y1 = int(tl.x()), int(tl.y()), int(br.x()), int(br.y())
    for px, py in [(x0 + 3, (y0 + y1) // 2), (x1 - 3, (y0 + y1) // 2),
                   ((x0 + x1) // 2, y0 + 3), ((x0 + x1) // 2, y1 - 3)]:
        assert is_red(img.pixelColor(px, py)), f"dpr={dpr} 外框内侧({px},{py})非图片"
    canvas.close(); ov.close()
    print(f"dpr={dpr}: 无损裁剪 {pw}x{ph}、DPR=1、与外框重合 OK")

# ---------- 2) 遮罩选区内必须 1:1 锐利（clip+QPoint 直绘原生底图） ----------
# offscreen 窗口 backing 的 DPR 恒为 1，无法承载高 DPR；因此用与底图同 DPR 的
# QImage 作为 backing，严格按 paintEvent 的绘制原语复现，验证选区内是否逐物理像素锐利。
dpr = 1.5
bg = make_native_bg(dpr, patterned=True)
lw, lh = round(bg.width() / dpr), round(bg.height() / dpr)
backing = QImage(bg.width(), bg.height(), QImage.Format.Format_ARGB32)
backing.setDevicePixelRatio(dpr)
p = QPainter(backing)
p.drawPixmap(0, 0, bg)                                   # ① 整屏原生背景（QPoint 直绘）
p.fillRect(QRect(0, 0, lw, lh), QColor(0, 0, 0, 110))   # ② 半透明遮罩
sel = QRect(20, 20, RW, RH)
p.save(); p.setClipRect(sel); p.drawPixmap(0, 0, bg); p.restore()  # ③ 选区恢复（新写法）
p.end()
sel_phys_y = round(30 * dpr)
diffs = [abs(backing.pixelColor(x, sel_phys_y).lightness()
             - backing.pixelColor(x + 1, sel_phys_y).lightness())
         for x in range(round(25 * dpr), round(25 * dpr) + 120)]
contrast = sum(diffs) / len(diffs)
print(f"遮罩选区内邻列对比 = {contrast:.1f}（255=与真实屏幕 1:1）")
assert contrast > 240, "选区内应逐物理像素锐利，未被预处理缩放糊化"

# 对照：旧的矩形重载 drawPixmap(rect,bg,rect) 会轻微柔化
backing2 = QImage(bg.width(), bg.height(), QImage.Format.Format_ARGB32)
backing2.setDevicePixelRatio(dpr)
p = QPainter(backing2)
p.drawPixmap(0, 0, bg)
p.fillRect(QRect(0, 0, lw, lh), QColor(0, 0, 0, 110))
p.drawPixmap(sel, bg, sel)   # 旧写法
p.end()
diffs2 = [abs(backing2.pixelColor(x, sel_phys_y).lightness()
              - backing2.pixelColor(x + 1, sel_phys_y).lightness())
          for x in range(round(25 * dpr), round(25 * dpr) + 120)]
old_contrast = sum(diffs2) / len(diffs2)
print(f"旧矩形重载邻列对比 = {old_contrast:.1f}（应低于新写法）")
assert old_contrast < contrast - 40

# ---------- 3) 对照：旧的“先缩小再放大整屏”确实糊，证明测试有效 ----------
old = bg.scaled(round(bg.width() / dpr), round(bg.height() / dpr),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
old.setDevicePixelRatio(1.0)
probe = QPixmap(bg.width(), bg.height()); probe.fill(QColor(128, 128, 128))
pp = QPainter(probe); pp.drawPixmap(0, 0, old); pp.end()
pi = probe.toImage()
od = [abs(pi.pixelColor(x, 100).lightness() - pi.pixelColor(x + 1, 100).lightness())
      for x in range(40, 160)]
old_contrast = sum(od) / len(od)
print(f"旧预处理路径邻列对比 = {old_contrast:.1f}（应明显糊化）")
assert old_contrast < 80
print("\n全部断言通过：遮罩与截图均为显示器原生真实效果，零预处理、零重采样。")
os._exit(0)
