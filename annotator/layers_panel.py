# -*- coding: utf-8 -*-
"""图层面板（类似 Photoshop）：增删层、显隐、排序、选择当前层。"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QGroupBox, QHBoxLayout,
                             QListWidget, QListWidgetItem, QMenu, QPushButton,
                             QVBoxLayout, QWidget)


class LayerPanel(QWidget):
    requestAdd = pyqtSignal()
    requestDelete = pyqtSignal(int)          # layer_id
    requestVisible = pyqtSignal(int, bool)   # layer_id, visible
    requestMove = pyqtSignal(int, int)       # layer_id, delta
    requestSelect = pyqtSignal(int)          # layer_id
    requestReorder = pyqtSignal(list)        # layer ids（自底向上 = 绘制顺序）
    requestRename = pyqtSignal(int, str)     # layer_id, new_name
    requestSelectLayerItems = pyqtSignal(int)  # 选中该图层所有元素

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._layers = []
        self._item_by_layer: dict = {}   # layer_id -> QListWidgetItem（增量刷新，避免重建列表导致信号派发崩溃）

        g = QGroupBox("图层")
        v = QVBoxLayout(g)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(4)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemChanged.connect(self._on_item_changed)
        # 拖拽调整图层顺序：越靠上越在上一层（列表顶部 = 顶层）
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDropIndicatorShown(True)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        v.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("添加图层")
        self.del_btn = QPushButton("-")
        self.del_btn.setToolTip("删除图层")
        self.up_btn = QPushButton("↑")
        self.down_btn = QPushButton("↓")
        for b in (self.add_btn, self.del_btn, self.up_btn, self.down_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
        self.add_btn.clicked.connect(self.requestAdd.emit)
        self.del_btn.clicked.connect(self._delete_current)
        self.up_btn.clicked.connect(lambda: self._move_current(-1))
        self.down_btn.clicked.connect(lambda: self._move_current(1))
        v.addLayout(row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(g)

    # ---------------- 数据刷新 ----------------
    def refresh(self, layers: list, current_id: int) -> None:
        """增量更新列表：复用已有行、只增删改差异行。

        绝不 clear() 重建——否则正在派发 clicked/itemChanged 信号的
        QListWidgetItem 会被销毁，导致 Qt 事件循环崩溃（0xC0000409）。
        """
        self._syncing = True
        self._layers = list(layers)
        ordered = list(reversed(layers))   # 显示顺序：顶层在上
        valid_ids = {l.id for l in ordered}

        # 1) 移除已不存在的行
        for lid in [x for x in self._item_by_layer if x not in valid_ids]:
            item = self._item_by_layer.pop(lid)
            row = self.list.row(item)
            if row >= 0:
                self.list.takeItem(row)

        # 2) 更新或新增行（含行序变化：拖拽重排后按新顺序移动行）
        for idx, layer in enumerate(ordered):
            item = self._item_by_layer.get(layer.id)
            if item is None:
                item = QListWidgetItem(layer.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, layer.id)
                self.list.insertItem(idx, item)
                self._item_by_layer[layer.id] = item
            elif self.list.row(item) != idx:
                # 行序变化（拖拽重排/程序重排）：移动已有行到目标位置
                self.list.takeItem(self.list.row(item))
                self.list.insertItem(idx, item)
            if item.text() != layer.name:
                item.setText(layer.name)
            want = (Qt.CheckState.Checked if layer.visible
                    else Qt.CheckState.Unchecked)
            if item.checkState() != want:
                item.setCheckState(want)
            if layer.id == current_id and self.list.currentItem() is not item:
                self.list.setCurrentItem(item)
        self._syncing = False

    def _current_layer_id(self) -> int | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    # ---------------- 交互 ----------------
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        try:
            self.requestSelect.emit(item.data(Qt.ItemDataRole.UserRole))
        except RuntimeError:
            pass   # item 已被外部销毁（极少数竞态），忽略本次点击

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        try:
            layer_id = item.data(Qt.ItemDataRole.UserRole)
            visible = item.checkState() == Qt.CheckState.Checked
        except RuntimeError:
            return
        self.requestVisible.emit(layer_id, visible)

    def _delete_current(self) -> None:
        layer_id = self._current_layer_id()
        if layer_id is not None:
            self.requestDelete.emit(layer_id)

    def _on_rows_moved(self, *_args) -> None:
        """列表行被拖拽移动后：把新顺序映射回 layers 顺序（底层在前）。"""
        if self._syncing:
            return
        ids = [self.list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self.list.count())]
        if ids:
            self.requestReorder.emit(list(reversed(ids)))

    def _move_current(self, delta: int) -> None:
        layer_id = self._current_layer_id()
        if layer_id is not None:
            self.requestMove.emit(layer_id, delta)

    def _show_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("设为当前层", lambda: self.requestSelect.emit(layer_id))
        menu.addAction("重命名", lambda: self._rename_layer(layer_id))
        menu.addAction("选中本层全部元素", lambda: self.requestSelectLayerItems.emit(layer_id))
        menu.addAction("删除图层", lambda: self.requestDelete.emit(layer_id))
        menu.addSeparator()
        menu.addAction("上移一层", lambda: self.requestMove.emit(layer_id, -1))
        menu.addAction("下移一层", lambda: self.requestMove.emit(layer_id, 1))
        menu.exec(self.list.mapToGlobal(pos))

    def _rename_layer(self, layer_id: int) -> None:
        """重命名图层（不可重名）。"""
        from PyQt6.QtWidgets import QInputDialog
        # 找当前图层名
        current_name = ""
        for l in self._layers:
            if l.id == layer_id:
                current_name = l.name
                break
        # 现有图层名列表（排除自己）
        existing_names = {l.name for l in self._layers if l.id != layer_id}

        while True:
            new_name, ok = QInputDialog.getText(
                self, "重命名图层", "图层名称：", text=current_name)
            if not ok:
                return
            new_name = new_name.strip()
            if not new_name:
                continue
            if new_name in existing_names:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "重名", "图层名称已存在，请换一个！")
                continue
            # 名称有效，发出信号
            self.requestRename.emit(layer_id, new_name)
            break
