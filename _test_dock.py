# -*- coding: utf-8 -*-
"""
简单的 QDockWidget 拖动测试
"""
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDockWidget,
                             QPushButton, QWidget, QVBoxLayout)
from PyQt6.QtCore import Qt


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dock 拖动测试")
        self.resize(800, 600)

        # 创建工具 dock
        self.tool_dock = QDockWidget("工具面板", self)
        self.tool_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        # 里面放几个按钮
        tool_widget = QWidget()
        layout = QVBoxLayout(tool_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for i in range(6):
            btn = QPushButton(f"按钮{i+1}")
            btn.setFixedSize(32, 32)
            layout.addWidget(btn)

        # 加弹簧
        layout.addStretch()

        self.tool_dock.setWidget(tool_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tool_dock)

        # 中心 widget
        self.setCentralWidget(QPushButton("中心区域"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TestWindow()
    win.show()
    sys.exit(app.exec())
