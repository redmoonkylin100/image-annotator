# -*- coding: utf-8 -*-
"""历史显示面板：按创建顺序列出全部标注元素。

- 点击条目：在画布中选中对应标注（与画布选中状态双向同步）。
- 双击条目：就地编辑文字。
- 右键条目：删除 / 编辑文字。
- 选中条目后，右侧样式面板可修改该标注的样式。
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QListWidget, QListWidgetItem, QMenu,
                             QVBoxLayout, QWidget)

from .items import (LeaderLineItem, ShapeItem, TextItem, HighlightItem,
                    MosaicItem, EmojiItem, format_number)


class HistoryPanel(QWidget):
    requestSelect = pyqtSignal(int)    # 单击：在画布选中该标注
    requestEditText = pyqtSignal(int)  # 双击/右键：就地编辑文字
    requestDelete = pyqtSignal(int)    # 右键：删除该标注
    requestEditNumber = pyqtSignal(int)     # 右键：编辑引线序号
    requestMove = pyqtSignal(int, int)      # 右键：上移/下移（item_id, delta）

    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # 顶部项目名称标签
        from PyQt6.QtWidgets import QLabel
        self.project_label = QLabel("新图片")
        self.project_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #f0f0f0;")
        lay.addWidget(self.project_label)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.itemClicked.connect(self._on_item_clicked)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self.list)

    def set_project_name(self, name: str) -> None:
        """设置当前项目名称。"""
        self.project_label.setText(name or "新图片")

        self._id_to_row = {}   # item.id -> 行号（增量刷新用）   # item id -> 当前行号

    # ---------------- 数据刷新 ----------------
    def refresh(self, items: list) -> None:
        """全量刷新列表，保持画布中的选中状态。"""
        selected_id = next((it.id for it in items if it.selected), None)
        self.list.blockSignals(True)
        self.list.clear()
        self._id_to_row = {}
        for idx, it in enumerate(items, start=1):
            label = self._describe(it, idx)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, it.id)
            if it.id == selected_id:
                item.setSelected(True)
            self.list.addItem(item)
            self._id_to_row[it.id] = self.list.count() - 1
        self.list.blockSignals(False)

    @staticmethod
    def _describe(it, idx: int) -> str:
        if isinstance(it, LeaderLineItem):
            kind = "引线"
        elif isinstance(it, TextItem):
            kind = "文本"
        elif isinstance(it, ShapeItem):
            kind = "形状"
        elif isinstance(it, HighlightItem):
            kind = "荧光"
        elif isinstance(it, MosaicItem):
            kind = "马赛克"
        elif isinstance(it, EmojiItem):
            kind = "表情"
        else:
            kind = "画笔"
        content = (it.text_content or "").replace("\n", " ")
        if len(content) > 14:
            content = content[:14] + "…"
        if isinstance(it, LeaderLineItem) and it.number:
            return f"{format_number(it.number, it.number_fmt)} [{kind}] {content}"
        if kind in ("形状", "画笔", "荧光", "马赛克"):
            return f"{idx}. [{kind}]"
        return f"{idx}. [{kind}] {content}"

    # ---------------- 交互 ----------------
    def _current_id(self) -> int | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_item_clicked(self, item) -> None:
        self.requestSelect.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_item_double_clicked(self, item) -> None:
        self.requestEditText.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        item_id = item.data(Qt.ItemDataRole.UserRole)
        self.list.setCurrentItem(item)
        menu = QMenu(self)
        act_edit = menu.addAction("编辑文字")
        # 引线标注额外提供序号/顺序操作
        kind = item.text()
        is_leader = "[引线]" in kind
        act_num = None
        act_up = None
        act_down = None
        if is_leader:
            act_num = menu.addAction("编辑序号…")
            act_up = menu.addAction("上移")
            act_down = menu.addAction("下移")
        act_del = menu.addAction("删除")
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen is act_edit:
            self.requestEditText.emit(item_id)
        elif chosen is act_del:
            self.requestDelete.emit(item_id)
        elif chosen is act_num:
            self.requestEditNumber.emit(item_id)
        elif chosen is act_up:
            self.requestMove.emit(item_id, -1)
        elif chosen is act_down:
            self.requestMove.emit(item_id, 1)
