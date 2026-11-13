# -*- coding: utf-8 -*-
"""r20 回归：退出按钮（主工具栏末尾右对齐）+ 暗黑主题白色复选框 + 截图放大镜。

离屏运行：venv\\Scripts\\python.exe tests\\smoke_test_r20.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPixmap, QPainter
from PyQt6.QtWidgets import QApplication, QSizePolicy

from annotator.window import MainWindow
from annotator.screenshot import (ScreenshotOverlay, _MAG_BOX, _MAG_INFO_W,
                                  _MASK_ALPHA)

FAILS = []
_PROG = open(os.path.join(ROOT, "tests", "_r20_progress.txt"), "w",
             encoding="utf-8")


def logp(msg):
    _PROG.write(msg + "\n"); _PROG.flush()


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg, flush=True)
    logp(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def ordered_toolbar_widgets(win):
    """按视觉顺序返回主工具栏中 addWidget 加入的控件。"""
    out = []
    for a in win.toolbar.actions():
        w = win.toolbar.widgetForAction(a)
        if w is not None:
            out.append(w)
    return out


def make_pattern(w, h):
    """生成可逐像素区分的测试底图（彩色网格 + 白噪声点）。"""
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.fillRect(0, 0, w, h, QColor("#224466"))
    for x in range(0, w, 40):
        p.fillRect(x, 0, 2, h, QColor("#88aa33"))
    for y in range(0, h, 40):
        p.fillRect(0, y, w, 2, QColor("#aa6633"))
    for i in range(0, w * h, 997):
        x, y = i % w, i // w
        p.setPen(QColor((i * 7) % 256, (i * 13) % 256, (i * 29) % 256))
        p.drawPoint(x, y)
    p.end()
    return pm


def main():
    app = QApplication([])
    win = MainWindow(restore=False)
    win.resize(1280, 800)
    win.show()
    app.processEvents()

    # ============ 需求 1：主工具栏末尾右对齐的退出按钮 ============
    check(hasattr(win, "quit_btn"), "主工具栏存在 quit_btn 退出按钮")
    check(win.quit_btn.text() == "退出", "退出按钮显示「退出」文字（r21 起改为红底文字按钮）")
    widgets = ordered_toolbar_widgets(win)
    i_quit = widgets.index(win.quit_btn)
    # v1.7 需求7：关于、退出均右对齐（退出在最右端，关于在其左侧）
    check(hasattr(win, "about_btn"), "主工具栏存在 about_btn 关于按钮（v1.5）")
    check(win.about_btn.text() == "关于", "关于按钮显示「关于」文字")
    check(widgets.index(win.about_btn) == len(widgets) - 2,
          "关于按钮位于工具栏倒数第二（退出之前）")
    check(i_quit == len(widgets) - 1, "退出按钮位于工具栏最后端")
    spacer = widgets[i_quit - 2]
    sp = spacer.sizePolicy().horizontalPolicy()
    check(sp == QSizePolicy.Policy.Expanding,
          "退出按钮前为水平 Expanding 弹簧（实现右对齐）")
    check(win.quit_btn.receivers(win.quit_btn.clicked) > 0,
          "退出按钮 clicked 已连接处理槽")
    check(win.about_btn.receivers(win.about_btn.clicked) > 0,
          "关于按钮 clicked 已连接处理槽")
    # 点击路径依赖的保存方法可用，且确实落盘
    win._persist_settings()
    from annotator import settings as st_mod
    check(os.path.exists(st_mod.settings_path()), "退出前保存：settings.json 已落盘")

    # ============ 需求 2：暗黑主题复选框白色可见 ============
    logp("SECTION 2 start")
    win._apply_dark_theme()
    app.processEvents()
    cbs = win.panel._checkboxes
    check(len(cbs) >= 6, f"右侧面板收集到全部复选框（{len(cbs)} 个）")
    target = win.panel.bg_check          # 「启用背景框」
    check("::indicator" in target.styleSheet(), "暗黑下复选框有自定义 indicator 样式")
    check("#FFFFFF" in target.styleSheet().upper(),
          "暗黑下选框边框/填充为白色")

    # 折叠组未展开时子控件 grab 为空，统一展开全部组后整体 grab 面板，
    # 再用 mapTo 定位每个复选框 indicator 的像素区域。
    win.panel.expand_all()
    app.processEvents()

    def panel_grab():
        app.processEvents()
        return win.panel.grab().toImage()

    def indicator_stats(cb, panel_img):
        tl = cb.mapTo(win.panel, QPoint(0, 0))
        x0, y0 = tl.x(), tl.y()
        h = max(cb.height(), 18)
        white_n = dark_n = 0
        for y in range(y0, min(panel_img.height(), y0 + h)):
            for x in range(x0, min(panel_img.width(), x0 + 18)):
                c = panel_img.pixelColor(x, y)
                if c.red() > 235 and c.green() > 235 and c.blue() > 235:
                    white_n += 1
                if c.red() < 90 and c.green() < 90 and c.blue() < 90:
                    dark_n += 1
        return white_n, dark_n

    target.setChecked(False)
    img_un = panel_grab()
    w_un, _ = indicator_stats(target, img_un)
    check(w_un < 110, f"未选态只有白色边框、无白色填充（白像素 {w_un}）")
    target.setChecked(True)
    img_on = panel_grab()
    w_on, d_on = indicator_stats(target, img_on)
    check(w_on >= 150, f"选中态存在大面积白色填充（白像素 {w_on}）")
    check(20 <= d_on < 200,
          f"选中态白填充内有深色对勾笔画（深色 {d_on}）")
    # 明亮主题恢复原生（清空控件 QSS）
    win._apply_light_theme()
    app.processEvents()
    check(win.panel.bg_check.styleSheet() == "", "明亮主题下复选框控件 QSS 已清空")
    win._apply_dark_theme()
    # 存一张人工核对图（暗黑主题整面板）
    img_on.save(os.path.join(ROOT, "tests", "_r20_checkbox.png"))

    # ============ 需求 3：截图选框不放大 + 外侧放大镜 + 信息 ============
    logp("SECTION 3 start")
    # offscreen 平台下 QScreen.grabWindow 可能阻塞，用 FakeScreen 代替，
    # 仅提供 overlay 用到的 geometry()/grabWindow()。
    class FakeScreen:
        def geometry(self):
            from PyQt6.QtCore import QRect
            return QRect(0, 0, 1280, 800)

        def grabWindow(self, *a):
            return QPixmap(1280, 800)

    ov = ScreenshotOverlay(FakeScreen())
    logp("overlay created")
    ov.resize(1280, 800)
    ov._bg = make_pattern(1280, 800)     # 注入可比对底图
    ov.show()
    app.processEvents()
    logp("overlay shown")

    # 场景 A：选区在屏幕中部，放大镜应位于选区上方
    o = QPointF(400, 300)
    c = QPointF(700, 520)
    ov._origin, ov._cur = o, c
    ov.repaint()
    app.processEvents()
    shot = ov.grab().toImage()
    shot.save(os.path.join(ROOT, "tests", "_r20_overlay_mid.png"))

    sel_x1, sel_y1, sel_x2, sel_y2 = 400, 300, 700, 520
    # 3a 选区内 1:1（与底图逐像素一致，未被遮罩压暗、未放大）
    bg_img = ov._bg.toImage()   # 缓存，避免循环里反复转换
    same = 0
    total = 0
    for x in range(sel_x1 + 3, sel_x2 - 3, 11):
        for y in range(sel_y1 + 3, sel_y2 - 3, 11):
            total += 1
            a = shot.pixelColor(x, y)
            b = bg_img.pixelColor(x, y)
            if abs(a.red() - b.red()) < 6 and abs(a.green() - b.green()) < 6 \
                    and abs(a.blue() - b.blue()) < 6:
                same += 1
    check(same == total, f"选区内与底图 1:1 一致（{same}/{total} 采样点）")
    # 3b 选区外被遮罩压暗（不等于底图）
    out_c = shot.pixelColor(20, 20)
    bg_c = bg_img.pixelColor(20, 20)
    check(out_c.red() < bg_c.red(), "选区外存在半透明遮罩")
    # 3c 放大镜方块位于选区上方且不遮挡选区：by = top - box - 8
    exp_by = sel_y1 - _MAG_BOX - 8
    block_w = _MAG_BOX + 10 + _MAG_INFO_W
    exp_bx = max(4, min(int(((sel_x1 + sel_x2) / 2) - block_w / 2),
                        1280 - block_w - 4))
    # 放大镜白边框像素
    border_white = 0
    for x in range(exp_bx, exp_bx + _MAG_BOX):
        for y in (exp_by, exp_by + _MAG_BOX - 1):
            cc = shot.pixelColor(x, y)
            if cc.red() > 230 and cc.green() > 230 and cc.blue() > 230:
                border_white += 1
    check(border_white > 100, f"选区上方存在放大镜白边框（{border_white}）")
    check(exp_by + _MAG_BOX <= sel_y1, "放大镜整体在选区上方，不遮挡选区")
    # 信息面板在放大镜右侧，含白色文字像素
    ix = exp_bx + _MAG_BOX + 10
    text_white = 0
    for x in range(ix + 2, ix + _MAG_INFO_W - 2, 2):
        for y in range(exp_by + 20, exp_by + _MAG_BOX - 20, 2):
            cc = shot.pixelColor(x, y)
            if cc.red() > 220 and cc.green() > 220 and cc.blue() > 220:
                text_white += 1
    check(text_white > 30, f"放大镜右侧信息面板有文字（{text_white}）")

    # 场景 B：选区贴近屏幕顶部，放大镜应自动翻到选区下方
    ov._origin, ov._cur = QPointF(20, 10), QPointF(300, 200)
    ov.repaint(); app.processEvents()
    shot2 = ov.grab().toImage()
    shot2.save(os.path.join(ROOT, "tests", "_r20_overlay_top.png"))
    below_by = 200 + 8
    bw2 = 0
    for x in range(0, 400):
        for y in (below_by, below_by + _MAG_BOX - 1):
            cc = shot2.pixelColor(x, y)
            if cc.red() > 230 and cc.green() > 230 and cc.blue() > 230:
                bw2 += 1
    check(bw2 > 100, "顶部空间不足时放大镜自动翻到选区下方")

    ov.close()

    print()
    if FAILS:
        print(f"==== 有 {len(FAILS)} 项失败 ====")
        for m in FAILS:
            print(" -", m)
        app.quit()
        os._exit(1)
    print("==== r20 全部断言通过 ====")
    app.quit()
    os._exit(0)


if __name__ == "__main__":
    main()
