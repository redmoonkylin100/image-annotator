# -*- coding: utf-8 -*-
"""画布标尺：横向/纵向刻度条，随画布缩放、平移实时刷新（显示图片坐标）。"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

RULER_SIZE = 24          # 标尺厚度
TICK_MAJOR = 100         # 主刻度间隔（视图像素）
TICK_MINOR = 20          # 次刻度间隔（视图像素）


class RulerBar(QWidget):
    """一条标尺。orientation: 'h'（顶部横向）/ 'v'（左侧纵向）。

    需求8：标尺配色跟随明/暗主题；其底色与主窗口背景略有差异以便区分
    （明亮主窗口 #F5F5F7 → 标尺略深 #E9EBEF；暗黑主窗口 #2D2D2D → 标尺略亮 #3A3A3A）。
    """

    def __init__(self, orientation: str, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self.canvas = None
        self._dark = False
        self._apply_colors()
        self.setFixedHeight(RULER_SIZE) if orientation == "h" else self.setFixedWidth(RULER_SIZE)

    def set_dark(self, dark: bool) -> None:
        """切换标尺明暗配色并立即重绘。"""
        self._dark = bool(dark)
        self._apply_colors()
        self.update()

    def _apply_colors(self) -> None:
        if self._dark:
            self._bg = QColor(58, 58, 58)       # 略亮于主窗口 #2D2D2D
            self._line = QColor(150, 150, 150)
            self._text = QColor(212, 212, 212)
        else:
            self._bg = QColor(233, 235, 239)    # 略区别于主窗口 #F5F5F7
            self._line = QColor(120, 125, 130)
            self._text = QColor(70, 75, 80)

    def attach(self, canvas) -> None:
        self.canvas = canvas
        canvas.viewChanged.connect(self.update)
        canvas.imageLoaded.connect(self.update)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if self.canvas is None or not self.canvas.has_image():
            p.end()
            return
        canvas = self.canvas
        scale = canvas.scale
        offset = canvas.offset
        p.setFont(QFont("Microsoft YaHei", 7))
        p.setPen(QPen(self._line, 1))

        if self.orientation == "h":
            w = self.width()
            # 图片 x 坐标 = (view_x - offset.x) / scale
            for vx in range(0, w + 1, TICK_MINOR):
                img_x = (vx - offset.x()) / scale
                if img_x < -1 or img_x > canvas.pixmap.width() + 1:
                    continue
                major = (vx % TICK_MAJOR) == 0
                h = RULER_SIZE - 8 if major else RULER_SIZE - 4
                p.drawLine(vx, 0, vx, h)
                if major and img_x >= 0:
                    p.setPen(self._text)
                    p.drawText(vx + 3, RULER_SIZE - 6, f"{img_x:.0f}")
                    p.setPen(QPen(self._line, 1))
        else:
            hgt = self.height()
            for vy in range(0, hgt + 1, TICK_MINOR):
                img_y = (vy - offset.y()) / scale
                if img_y < -1 or img_y > canvas.pixmap.height() + 1:
                    continue
                major = (vy % TICK_MAJOR) == 0
                wdt = RULER_SIZE - 8 if major else RULER_SIZE - 4
                p.drawLine(0, vy, wdt, vy)
                if major and img_y >= 0:
                    p.setPen(self._text)
                    p.save()
                    p.translate(RULER_SIZE - 6, vy - 1)
                    p.rotate(-90)
                    p.drawText(0, 0, f"{img_y:.0f}")
                    p.restore()
                    p.setPen(QPen(self._line, 1))
        p.end()
