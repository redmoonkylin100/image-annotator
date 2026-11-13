# -*- coding: utf-8 -*-
"""图层向下合成器（本轮新增，需求5）。

马赛克处于上层时，其「下方所有内容」都应被马赛克处理 —— 不仅是底图，
还包括导入的截图（ImageItem）以及位于其下的任何标注元素。

本类在【图片坐标系】维护一张离屏位图，按图层绘制顺序：
1. 先铺底图；
2. 每绘制一个元素到屏幕/导出 painter 的同时，把它（export 语义，
   不带选中虚线框等编辑态装饰）画进离屏位图；
3. 遇到马赛克元素时，先从离屏位图取快照作为马赛克源 —— 快照恰好等于
   该马赛克下方所有内容的合成结果；
4. 继续把马赛克本身画进离屏位图，使更上层的马赛克也能包含它。

导入截图（ImageItem）作为普通元素参与同一顺序：位于其下的元素先画、
被其不透明像素遮挡，位于其上的元素后画、正常显示在它上面。

稳定性要点（修复截图闪退）：
- snapshot() 取快照时，QImage 上仍挂着活动 QPainter；此时直接
  QPixmap.fromImage 在 Windows 光栅引擎下可能触发底层崩溃（离屏平台
  不复现）。因此取快照前先 end() 落盘、转换后再 begin() 重开并恢复
  渲染选项，杜绝「边画边转」。
- 离屏位图尺寸设上限：尾尖可任意拖远、元素可能在画布外，不加约束会
  申请超大位图导致分配失败、QPainter 挂到空设备上而崩溃。
"""

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap

# 离屏合成位图单边最大像素（约 2.6 亿像素 ×4 字节 ≈ 1GB 上限内），
# 超出部分钳制，避免异常几何把内存吃爆导致进程崩溃。
_MAX_DIM = 16384


class BelowFlattener:
    """按绘制顺序累积「当前位置以下全部内容」的离屏合成器。"""

    def __init__(self, base_pixmap, width: int, height: int,
                 antialias: bool = True):
        w = max(1, min(_MAX_DIM, int(width)))
        h = max(1, min(_MAX_DIM, int(height)))
        self._w, self._h = w, h
        self._image = QImage(QSize(w, h),
                             QImage.Format.Format_ARGB32_Premultiplied)
        # 分配失败时 isNull 为真：不再挂 QPainter，整体退化为空操作，
        # 由画布回退到「只对底图打码」的旧路径，绝不让进程崩掉。
        self._usable = not self._image.isNull()
        self._ended = False
        self._painter = None
        self._hints = QPainter.RenderHint(0)
        if not self._usable:
            return
        self._image.fill(Qt.GlobalColor.transparent)
        self._painter = QPainter(self._image)
        if antialias:
            self._hints = (
                QPainter.RenderHint.Antialiasing
                | QPainter.RenderHint.SmoothPixmapTransform
                | QPainter.RenderHint.TextAntialiasing)
            self._painter.setRenderHints(self._hints)
        # 底图（原点 0,0，与图片坐标系一致）
        if base_pixmap is not None and not base_pixmap.isNull():
            self._painter.drawPixmap(0, 0, base_pixmap)

    @property
    def usable(self) -> bool:
        """离屏位图是否可用；不可用时画布应回退到「只对底图打码」。"""
        return bool(self._usable)

    # ---- 内部：暂停/恢复离屏 painter，保证转换时无活动 painter ----
    def _suspend(self) -> bool:
        if not self._usable or self._painter is None or self._ended:
            return False
        self._painter.end()
        return True

    def _resume(self) -> None:
        if not self._usable or self._ended:
            return
        # QImage 像素在 end/begin 之间保留，重开后可继续叠加
        self._painter = QPainter(self._image)
        if self._hints:
            self._painter.setRenderHints(self._hints)

    def paint_below(self, item) -> None:
        """把一个元素叠加进离屏位图（export 语义，无选中装饰）。"""
        if self._ended or not self._usable or item is None:
            return
        if self._painter is None:
            self._resume()
        try:
            item.paint(self._painter, export=True)
        except Exception:
            # 单个元素异常不影响整帧合成
            pass

    def snapshot(self) -> QPixmap:
        """返回当前离屏位图的独立副本（调用后仍可继续叠加）。"""
        if self._ended or not self._usable:
            return QPixmap()
        # 关键：转换期间不允许有 painter 正画在 self._image 上
        suspended = self._suspend()
        try:
            return QPixmap.fromImage(QImage(self._image))
        except Exception:
            return QPixmap()
        finally:
            if suspended:
                self._resume()

    def end(self) -> None:
        if self._ended:
            return
        self._ended = True
        if self._usable and self._painter is not None:
            self._painter.end()
        self._painter = None
