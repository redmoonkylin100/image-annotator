# -*- coding: utf-8 -*-
"""第十七轮冒烟测试：右侧面板「折叠/展开全部」按钮 + saveState objectName 修复。

1. QDockWidget/QToolBar 显式设置 objectName，消除 QMainWindow::saveState() 启动警告；
2. 右侧面板顶部固定「▲ 折叠全部 / ▼ 展开全部」按钮：点击折叠/展开全部功能组，
   文案随状态同步、配色随明暗主题切换、程序化展开（模式联动）也能同步按钮。
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:\\Windows\\Fonts"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication

app = QApplication([])

from annotator import autosave, settings
settings.clear()
autosave.clear()
from annotator.window import MainWindow

PASS = []


def check(name, cond):
    PASS.append((name, bool(cond)))
    print(("OK  " if cond else "FAIL") + " | " + name)


w = MainWindow(restore=False)
w.show()
app.processEvents()

# ---------- 1. objectName 已设置，saveState 不再报警 ----------
check("主工具栏 objectName = main_toolbar",
      w.toolbar.objectName() == "main_toolbar")
check("工具面板 objectName = tool_dock",
      w.tool_dock.objectName() == "tool_dock")
check("saveState 正常返回", len(w.saveState()) > 0)

# ---------- 2. 折叠/展开全部按钮初始状态 ----------
check("折叠按钮已创建", hasattr(w, "collapse_all_btn"))
check("初始存在展开组（引线设置默认展开）", w.panel.any_expanded())
check("初始按钮文案含「折叠全部」", "折叠全部" in w.collapse_all_btn.text())

# ---------- 3. 点击一次：全部折叠 ----------
w._toggle_right_panel_all()
app.processEvents()
check("点击后全部折叠", not w.panel.any_expanded())
check("折叠后按钮文案含「展开全部」", "展开全部" in w.collapse_all_btn.text())

# ---------- 4. 再点一次：全部展开 ----------
w._toggle_right_panel_all()
app.processEvents()
check("再点后全部展开",
      all(g.is_expanded() for g in w.panel._groups.values()))
check("展开后按钮文案含「折叠全部」", "折叠全部" in w.collapse_all_btn.text())

# ---------- 5. 用户手动折叠单个组 -> 按钮状态同步 ----------
w.panel._groups["text"]._btn.setChecked(False)  # 模拟用户点击标题折叠
app.processEvents()
check("部分折叠后按钮仍为「折叠全部」（还有展开组）",
      "折叠全部" in w.collapse_all_btn.text())
for g in w.panel._groups.values():
    g._btn.setChecked(False)  # 逐组手动折叠全部
app.processEvents()
check("全部手动折叠后按钮为「展开全部」",
      "展开全部" in w.collapse_all_btn.text())

# ---------- 6. 主题切换 -> 按钮配色跟随 ----------
w._dark_theme = True
w._apply_dark_theme()
app.processEvents()
check("暗色主题按钮样式含暗色背景 #3d3d3d",
      "#3d3d3d" in w.collapse_all_btn.styleSheet())
w._dark_theme = False
w._apply_light_theme()
app.processEvents()
check("亮色主题按钮样式含亮色背景 #F2F3F5",
      "#F2F3F5" in w.collapse_all_btn.styleSheet())

# ---------- 7. 全折叠后切换模式 -> 程序化展开对应组并同步按钮 ----------
w.panel.collapse_all()
w._sync_collapse_all_btn()
check("全折叠（程序化）后按钮为「展开全部」",
      "展开全部" in w.collapse_all_btn.text())
w._switch_mode("shape")
app.processEvents()
check("切 shape 模式后 shape 组被展开",
      w.panel._groups["shape"].is_expanded())
check("模式联动展开后按钮同步为「折叠全部」",
      "折叠全部" in w.collapse_all_btn.text())

# ---------- 8. 恢复路径：set_group_states 后按钮同步 ----------
w.panel.set_group_states({k: False for k in w.panel._groups})
w._sync_collapse_all_btn()
check("恢复全折叠后按钮为「展开全部」",
      "展开全部" in w.collapse_all_btn.text())
w.panel.set_group_states({"leader": True})
w._sync_collapse_all_btn()
check("恢复部分展开后按钮为「折叠全部」",
      "折叠全部" in w.collapse_all_btn.text())

# ---------- 9. 折叠/展开全部不触发工具模式切换 ----------
w.panel.expand_all()
mode_before = w.canvas.mode
w.panel.collapse_all()
app.processEvents()
check("折叠全部不改变当前模式", w.canvas.mode == mode_before)

print(f"\nRESULT: {len([1 for _, c in PASS if c])}/{len(PASS)} passed")
failed = [n for n, c in PASS if not c]
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("SMOKE OK")
