# -*- coding: utf-8 -*-
"""r21 回归：直线形状 / 透明背景移组 / 引线空文本 / 启动不弹提示 /
折叠标题配色 / 退出文字按钮 / 运行时 1.ico 图标。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QCheckBox

from annotator.window import MainWindow, _resource_path
from annotator.items import SHAPE_OPTIONS, SHAPE_LINE, ShapeItem, shape_path
from annotator import settings as settings_mod
from annotator.panel import CollapsibleBox

FAILS = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        FAILS.append(msg)


def iter_layout_widgets(layout):
    for i in range(layout.count()):
        it = layout.itemAt(i)
        w = it.widget()
        if w is not None:
            yield w
        sub = it.layout()
        if sub is not None:
            yield from iter_layout_widgets(sub)


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()

    # ===== 1. 直线形状：下拉最前 + 创建/命中/绘制 =====
    check(SHAPE_OPTIONS[0] == ("直线", SHAPE_LINE), "形状下拉第一项为「直线」")
    win.panel._set_shape_val(SHAPE_LINE)
    st = win.panel.current_style()
    check(st.get("shape_type") == "line", "当前样式 shape_type=line")
    win.canvas.load_pixmap(QPixmap(300, 200))
    item = win.canvas.add_shape_item(QPointF(20, 100), QPointF(200, 100), "line")
    check(isinstance(item, ShapeItem) and item.shape == "line", "可创建水平直线元素")
    hit = item.hit_test(QPointF(110, 100), 6)
    check(hit == "body", "直线中点可命中")
    miss = item.hit_test(QPointF(110, 60), 4)
    check(miss is None, "远离直线不误命中")
    pm = QPixmap(300, 200); pm.fill(QColor("#FFFFFF"))
    p = QPainter(pm)
    ok_paint = True
    try:
        item.paint(p)
        p.end()
    except Exception as e:
        ok_paint = False
        print("paint error:", e)
    check(ok_paint, "直线 paint 不报错")
    # 菜单包含直线且在最前
    acts = win.panel.shape_menu.actions()
    check(acts and acts[0].text() == "直线", "形状弹出菜单首项为直线")

    # ===== 2. 导出透明背景 PNG 移到「导出设置」组 =====
    exp_widgets = list(iter_layout_widgets(win.panel._groups["export"].content_layout))
    cv_widgets = list(iter_layout_widgets(win.panel._groups["canvas"].content_layout))
    tbc = win.panel.transparent_bg_check
    check(isinstance(tbc, QCheckBox), "透明背景复选框存在")
    check(tbc in exp_widgets, "透明背景复选框位于导出设置组")
    check(tbc not in cv_widgets, "透明背景复选框已从画布设置组移除")
    # 信号仍生效
    tbc.setChecked(True)
    app.processEvents()
    check(win.canvas.transparent_bg is True, "透明背景勾选仍联动画布")

    # ===== 3. 引线标注允许空文本 =====
    calls = []
    win.canvas.start_inline_editor(
        QPointF(50, 50), lambda s: calls.append(s), allow_empty=True)
    win.canvas._on_editor_confirmed("")
    check(calls == [""], "引线：空文本确认后回调空串（允许空白）")
    calls.clear()
    win.canvas.start_inline_editor(QPointF(50, 50), lambda s: calls.append(s))
    win.canvas._on_editor_confirmed("   ")
    check(calls == [], "文本批注：空文本仍取消（不创建空文本框）")
    # 端到端：两击 + 空确认能生成空内容引线
    win.canvas.set_mode("leader")
    lead = win.canvas.add_leader_item(QPointF(30, 30), QPointF(80, 80), "")
    check(lead.text_content == "", "可创建内容为空的引线元素")

    # ===== 4. 启动恢复不弹「无图片」提示 =====
    settings_mod.save({"mode": "leader"})
    prompted = []
    win._ask_new_or_open_image = lambda: prompted.append(1) or False
    win.canvas.pixmap = None     # 模拟无图
    win._restore_settings()
    app.processEvents()
    check(prompted == [], "启动恢复模式时不弹无图提示")
    check(win.canvas.mode == "leader", "启动仍恢复上次模式")
    # 用户主动点工具时仍会弹
    win._switch_mode("text")
    check(prompted == [1], "用户主动选工具且无图时仍弹提示")
    win.canvas.load_pixmap(QPixmap(300, 200))   # 恢复有图状态

    # ===== 5. 折叠标题配色（v1.5：高对比绿/蓝/红/橙，避免黑白色看不清） =====
    box = CollapsibleBox("测试组")
    box.set_dark(False); box._btn.setChecked(False)
    ss_light_col = box._btn.styleSheet()
    check("#1F6FD0" in ss_light_col.upper(), "明亮-收起：蓝")
    check("#2FA05C" in ss_light_col.upper(), "明亮-悬停：绿")
    check("#E5485C" in ss_light_col.upper(), "明亮-展开：红")
    box.set_dark(True)
    ss_dark = box._btn.styleSheet()
    check("#7CE38B" in ss_dark.upper(), "暗黑-收起：绿")
    check("#5AA8FF" in ss_dark.upper(), "暗黑-悬停：蓝")
    check("#FF6B78" in ss_dark.upper(), "暗黑-展开：红")

    # ===== 6. 退出按钮：红底「退出」文字 =====
    check(win.quit_btn.text() == "退出", "退出按钮文案为「退出」")
    qss = win.quit_btn.styleSheet().upper()
    check("#E0464B" in qss and "#FFFFFF" in qss, "退出按钮红底白字")
    check(win.quit_btn.receivers(win.quit_btn.clicked) > 0, "退出按钮已接线")

    # ===== 7. 运行时图标为 1.ico（PNG 字节哈希比对） =====
    from PyQt6.QtCore import QBuffer, QByteArray
    import hashlib

    def _icon_png_hash(icon):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        icon.pixmap(32, 32).toImage().save(buf, "PNG")
        return hashlib.md5(bytes(ba)).hexdigest()

    ico1 = QIcon(_resource_path("1.ico"))
    ico2 = QIcon(_resource_path("2.ico"))
    check(not win.windowIcon().isNull(), "窗口图标已设置")
    check(_icon_png_hash(win.windowIcon()) == _icon_png_hash(ico1),
          "运行时窗口/任务栏图标 = 1.ico")
    check(_icon_png_hash(ico1) != _icon_png_hash(ico2),
          "1.ico 与 2.ico 确实不同（对照有效）")

    # 存面板人工核对图（明/暗各一张）
    win._apply_light_theme(); app.processEvents()
    win.panel.grab().save(os.path.join(ROOT, "tests", "_r21_panel_light.png"))
    win._apply_dark_theme(); app.processEvents()
    win.panel.grab().save(os.path.join(ROOT, "tests", "_r21_panel_dark.png"))
    win.grab().save(os.path.join(ROOT, "tests", "_r21_window.png"))

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit(); os._exit(1)
    print("==== r21 全部断言通过 ====")
    app.quit(); os._exit(0)


if __name__ == "__main__":
    main()
