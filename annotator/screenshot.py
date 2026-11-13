# -*- coding: utf-8 -*-
"""自由截图：全屏半透明遮罩 + 鼠标框选，松开即截取屏幕区域。

设计为独立模块，尽量不侵入既有标注逻辑：
- ScreenshotOverlay 覆盖指定屏幕，弹出前预先抓取整屏【原生物理像素】作为背景，
  不做任何缩放预处理（绘制时 Qt 依 DPR 1:1 映射，遮罩背景与真实屏幕同样清晰）；
- 鼠标按下拖出选区，选区内清晰、选区外半透明遮罩，实时显示尺寸；
- 松开鼠标时直接从原生底图按物理像素 1:1 裁剪（QPixmap.copy，零重采样，也不会
  拍到仍显示中的遮罩本身），发出 captured(QPixmap)；Esc 取消发出 canceled()。
选区 local_rect 为相对本屏幕的逻辑坐标，需乘底图 DPR 换算为物理像素再裁剪。
"""

from PyQt6.QtCore import Qt, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QCursor, QFont
from PyQt6.QtWidgets import QApplication, QWidget

_MASK_ALPHA = 110          # 选区外遮罩不透明度
_MIN_SIZE = 5              # 小于该尺寸视为误操作，按取消处理
_MAG_ZOOM = 3.0            # 放大镜放大倍数
_MAG_BOX = 132             # 放大镜方块边长（逻辑像素）
_MAG_INFO_W = 216          # 放大镜右侧信息面板宽度


class ScreenshotOverlay(QWidget):
    """覆盖单块屏幕的截图遮罩。"""

    captured = pyqtSignal(QPixmap)
    canceled = pyqtSignal()

    def __init__(self, screen, parent=None):
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool)
        super().__init__(parent, flags)
        self._screen = screen
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setGeometry(screen.geometry())
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        # 预先抓取整屏（遮罩下仍能看到桌面画面）。
        # 关键：保留 grabWindow 返回的【原生物理像素与其 DPR】，不做任何缩小/放大
        # 预处理——预先缩放到逻辑尺寸会让遮罩背景比真实屏幕粗糙，且最终再抓取时会
        # 拍到这张被处理过的图（二次损失）。绘制时 Qt 依据 DPR 把物理像素 1:1
        # 映射到屏幕，遮罩背景与真实桌面同样清晰；最终截图直接从这份原生底图裁剪。
        self._bg = screen.grabWindow(0)
        self._origin = None
        self._cur = None

    # ---- 交互 ----
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position()
            self._cur = event.position()
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None:
            self._cur = event.position()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = QRect(self._origin.toPoint(), self._cur.toPoint()).normalized()
        self._origin = None
        self._cur = None
        if rect.width() < _MIN_SIZE or rect.height() < _MIN_SIZE:
            self._cancel()
            return
        self._capture(rect)

    # ---- 绘制 ----
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._bg)
        painter.fillRect(self.rect(), QColor(0, 0, 0, _MASK_ALPHA))
        if self._origin is not None and self._cur is not None:
            rect = QRect(self._origin.toPoint(), self._cur.toPoint()).normalized()
            # 选区内恢复清晰画面（覆盖掉遮罩）：用裁剪 + QPoint 直绘原生底图，
            # 而不是 drawPixmap(目标矩形, 底图, 源矩形)——后者在 Qt 里走缩放 blit
            # 路径会轻微柔化，QPoint 直绘是物理像素 1:1 直传，和真实屏幕一样清晰。
            painter.save()
            painter.setClipRect(rect)
            painter.drawPixmap(0, 0, self._bg)
            painter.restore()
            pen = QPen(QColor("#2f80ed"), 1)
            painter.setPen(pen)
            painter.drawRect(rect)
            # 放大镜 + 位置/尺寸信息（选区上方不遮挡处，细节查看）
            self._draw_magnifier(painter, rect)
        painter.end()

    # ---- 放大镜（选区外侧小方块，放大鼠标拖动末端附近画面） ----
    def _draw_magnifier(self, painter: QPainter, sel_rect: QRect) -> None:
        zoom = _MAG_ZOOM
        box = _MAG_BOX                  # 放大镜显示边长（逻辑像素）
        info_w = _MAG_INFO_W
        cx, cy = self._cur.x(), self._cur.y()
        src = box / zoom                # 放大镜对应的源区域边长
        # 源区域（鼠标位置为中心，越界时收缩到屏幕内）
        sx = max(0.0, min(cx - src / 2, max(0.0, self.width() - src)))
        sy = max(0.0, min(cy - src / 2, max(0.0, self.height() - src)))
        # 整块（放大镜 + 间距 + 信息面板）水平方向相对选区居中并夹到屏幕内
        gap = 10
        block_w = box + gap + info_w
        bx = int(sel_rect.center().x() - block_w / 2)
        bx = max(4, min(bx, self.width() - block_w - 4))
        # 垂直方向：优先选区上方（不遮挡选区）；放不下则放下方；再不行贴边
        by = int(sel_rect.top() - box - 8)
        if by < 4:
            below = int(sel_rect.bottom() + 8)
            if below + box <= self.height() - 4:
                by = below
            else:
                by = max(4, min(int(sel_rect.center().y() - box / 2),
                                self.height() - box - 4))
        # 放大镜方块：深色衬底 + 放大画面 + 白边框
        painter.fillRect(QRect(bx, by, box, box), QColor(18, 18, 18, 235))
        painter.drawPixmap(QRectF(bx, by, box, box), self._bg,
                           QRectF(sx, sy, src, src))
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.drawRect(bx, by, box, box)
        # 十字线（鼠标当前位置在放大镜内的映射）+ 中心蓝点
        mx = int(bx + (cx - sx) * zoom)
        my = int(by + (cy - sy) * zoom)
        painter.drawLine(mx, by, mx, by + box)
        painter.drawLine(bx, my, bx + box, my)
        painter.fillRect(QRect(mx - 2, my - 2, 4, 4), QColor("#5AA8FF"))
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.drawRect(mx - 2, my - 2, 4, 4)
        # 信息面板（放大镜右侧）：鼠标末端位置、选区起点、尺寸、放大倍数
        lines = [
            f"鼠标  X:{cx:.0f}  Y:{cy:.0f}",
            f"起点  X:{sel_rect.left()}  Y:{sel_rect.top()}",
            f"尺寸  {sel_rect.width()} × {sel_rect.height()} px",
            f"放大  {zoom:.0f}×",
        ]
        f = QFont("Microsoft YaHei"); f.setPixelSize(13)
        painter.setFont(f)
        fm = painter.fontMetrics()
        line_h = fm.height() + 3
        panel_h = line_h * len(lines) + 10
        ix = bx + box + gap
        iy = by + (box - panel_h) // 2     # 与放大镜方块垂直居中对齐
        painter.fillRect(QRect(ix, iy, info_w, panel_h), QColor(0, 0, 0, 190))
        painter.setPen(QPen(QColor("#9AA0A6"), 1))
        painter.drawRect(ix, iy, info_w, panel_h)
        painter.setPen(QColor("#FFFFFF"))
        for i, ln in enumerate(lines):
            painter.drawText(QRect(ix + 8, iy + 5 + i * line_h,
                                   info_w - 14, line_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             ln)

    # ---- 结果 ----
    def _capture(self, local_rect: QRect) -> None:
        # 直接从遮罩弹出【之前】抓取的原生整屏底图中裁剪选区，而不是此刻再
        # grabWindow——松开时遮罩窗口仍覆盖屏幕，二次截屏会拍到“半透明遮罩 +
        # 被处理过的背景”，既偏色又模糊。底图是原生物理像素，这里只做 1:1
        # 物理像素裁剪（QPixmap.copy，零重采样），得到的就是显示器真实效果。
        # local_rect 是相对本屏幕的逻辑坐标，乘 DPR 换算到底图物理像素坐标。
        bg = self._bg
        dpr = bg.devicePixelRatio() or 1.0
        bw, bh = bg.width(), bg.height()
        cx = max(0, min(round(local_rect.x() * dpr), bw - 1))
        cy = max(0, min(round(local_rect.y() * dpr), bh - 1))
        cw = max(1, min(round(local_rect.width() * dpr), bw - cx))
        ch = max(1, min(round(local_rect.height() * dpr), bh - cy))
        shot = bg.copy(QRect(cx, cy, cw, ch))
        # v1.7 需求3：与所截原图保持一致，不人为放大。
        # grabWindow 底图为物理像素（DPR>1 时比逻辑尺寸大），若直接按物理
        # 像素输出，画布 scale=1 显示会大于用户实际框选区域。这里按逻辑尺寸
        # 缩回 1:1（仅 DPR>1 时重采样；DPR=1 时零重采样，保留原生像素）。
        lw = max(1, round(local_rect.width()))
        lh = max(1, round(local_rect.height()))
        if dpr != 1.0 and (cw != lw or ch != lh):
            shot = shot.scaled(lw, lh, Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        shot.setDevicePixelRatio(1.0)
        self.captured.emit(shot)
        self.close()

    def _cancel(self) -> None:
        self.canceled.emit()
        self.close()


def pick_screen_at_cursor():
    """返回光标当前所在屏幕，找不到时返回主屏幕。"""
    app = QApplication.instance()
    screen = app.screenAt(QCursor.pos())
    return screen or app.primaryScreen()
