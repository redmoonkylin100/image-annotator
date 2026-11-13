# -*- coding: utf-8 -*-
"""冒烟测试：离屏启动主窗口，程序化完成「加载图片 -> 添加标注 -> 样式修改
-> 撤销/重做 -> 删除 -> 导出」全流程，并输出画布渲染截图供人工核对。

运行：python tests/smoke_test.py
"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # 离屏模式下保证中文字体可用
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from annotator.canvas import MODE_SELECT
from annotator.items import LeaderLineItem, TextItem
from annotator.window import MainWindow


def main() -> int:
    app = QApplication([])
    win = MainWindow(restore=False)   # 测试环境不弹「恢复上次工作」框，避免阻塞
    win.resize(1280, 800)
    win.show()

    # 1. 加载图片（模拟截图的机械零件图样，便于核对引线样式）
    pm = QPixmap(900, 560)
    pm.fill(QColor("#E8F0F8"))
    win.canvas.load_pixmap(pm)
    assert win.canvas.has_image(), "图片加载失败"
    assert win.canvas._bg_color.name() == "#f0f2f5", "画布默认应为浅色背景"

    # 2. 添加标注元素
    lead = win.canvas.add_leader_item(QPointF(150, 420), QPointF(560, 120), "安装孔")
    text = win.canvas.add_text_item(QPointF(600, 400), "普通批注")
    assert len(win.canvas.items) == 2, "元素数量错误"

    # 3. 样式修改（模拟面板应用：红色 3px 引线、大字；默认透明背景）
    st = win.panel.current_style()
    st["line_color"] = QColor("#FF0000")
    st["line_width"] = 3
    st["arrow_size"] = 20.0
    st["font_size"] = 28
    st["text_color"] = QColor("#000000")
    st["bg_enabled"] = False                          # 默认透明背景（无文字框）
    for it in (lead, text):
        it.apply_style(st)
    if isinstance(lead, LeaderLineItem):
        lead.line_color = QColor(st["line_color"])
        lead.line_width = int(st["line_width"])
        lead.arrow_size = float(st["arrow_size"])
    assert lead.bg_enabled is False, "默认应为透明背景"
    assert text.bg_enabled is False, "默认应为透明背景"

    # 4. 撤销/重做：删除一个元素后可撤销恢复
    text.selected = True
    win.canvas.delete_selected()                  # push_undo 快照（2 个）→ items 剩 1
    assert len(win.canvas.items) == 1, "删除失败"
    assert all(it.text_content != "普通批注" for it in win.canvas.items), "删除失败"
    win.canvas.undo()
    assert len(win.canvas.items) == 2, "撤销未恢复"
    assert any(it.text_content == "普通批注" for it in win.canvas.items), "撤销未恢复文字"
    win.canvas.redo()
    assert len(win.canvas.items) == 1, "重做失败"
    win.canvas.undo()                             # 回到 redo 前的完整状态 [lead, text]
    assert len(win.canvas.items) == 2, "二次撤销失败"

    # 5. 删除引线
    lead = next(it for it in win.canvas.items if isinstance(it, LeaderLineItem))
    lead.selected = True
    win.canvas.delete_selected()
    assert all(not isinstance(it, LeaderLineItem) for it in win.canvas.items), "删除引线失败"
    assert any(it.text_content == "普通批注" for it in win.canvas.items), "误删其他元素"

    # 6. 命中测试
    t2 = win.canvas.add_leader_item(QPointF(100, 300), QPointF(400, 200), "再次标注")
    assert t2.hit_test(QPointF(100, 300), 8) == "target", "target 命中失败"
    assert t2.hit_test(QPointF(250, 250), 8) in ("line", None), "折线命中异常"
    assert t2.hit_test(QPointF(400, 200), 8) == "text", "文字框命中失败"
    t2.move_by(10, 10, "line")
    assert t2.target_point == QPointF(110, 310), "整体移动失败"

    # 7. 交互测试：引线模式两次点击 + 就地输入（不弹窗）
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from annotator.canvas import MODE_LEADER, MODE_TEXT

    win.canvas.set_mode(MODE_LEADER)

    def vpoint(x, y):
        return win.canvas.image_to_view(QPointF(x, y)).toPoint()

    def close(p, x, y, tol=1.2):
        return abs(p.x() - x) <= tol and abs(p.y() - y) <= tol

    # 第一次点击：设置箭头端点（目标点）
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(150, 420))
    assert win.canvas._pending_target is not None, "第一次点击未记录端点"
    assert close(win.canvas._pending_target, 150, 420), "第一次点击端点坐标错误"
    # 第二次点击：放置文字位置，就地弹出输入框
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(560, 120))
    assert win.canvas._editor.isVisible(), "第二次点击后应显示就地输入框"
    ed_pos = win.canvas._editor.geometry().topLeft()
    assert ed_pos.x() > 100, f"输入框不应在左上角，实际 {ed_pos}"
    assert abs(ed_pos.x() - vpoint(560, 120).x()) <= 2, "输入框应位于点击处"
    win.canvas._editor.setText("孔位A")
    QTest.keyClick(win.canvas._editor, Qt.Key.Key_Return)
    new_item = win.canvas.items[-1]
    assert isinstance(new_item, LeaderLineItem), "引线未创建"
    assert close(new_item.target_point, 150, 420), "箭头端点应落在第一次点击位置"
    assert close(new_item.text_point, 560, 120), "文字位置应落在第二次点击位置"
    assert new_item.text_content == "孔位A", "就地输入文字错误"
    assert new_item.bg_enabled is False, "新引线默认透明背景"
    assert not win.canvas._editor.isVisible(), "确认后输入框应隐藏"
    assert win.canvas._await_prompt, "完成后应显示「等待下一次点击」提示"
    assert new_item.endpoint_style == "arrow", "端点符号默认应为三角"

    # 文本模式：点击 + 就地输入
    win.canvas.set_mode(MODE_TEXT)
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(600, 400))
    assert win.canvas._editor.isVisible(), "文本模式应显示就地输入框"
    win.canvas._editor.setText("就地批注")
    QTest.keyClick(win.canvas._editor, Qt.Key.Key_Return)
    t_item = win.canvas.items[-1]
    assert isinstance(t_item, TextItem), "文本未创建"
    assert t_item.text_content == "就地批注", "文本内容错误"
    assert close(t_item.pos, 600, 400), "文本位置错误"

    # Esc 取消输入
    win.canvas.set_mode(MODE_TEXT)
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(700, 450))
    n_before = len(win.canvas.items)
    QTest.keyClick(win.canvas._editor, Qt.Key.Key_Escape)
    assert len(win.canvas.items) == n_before, "Esc 不应创建元素"
    assert not win.canvas._editor.isVisible(), "Esc 后输入框应隐藏"

    # 双击文字就地修改
    win.canvas.set_mode(MODE_SELECT)
    lead_dbl = next(it for it in win.canvas.items if isinstance(it, LeaderLineItem))
    dpos = win.canvas.image_to_view(lead_dbl.text_point).toPoint()
    QTest.mouseDClick(win.canvas, Qt.MouseButton.LeftButton, pos=dpos)
    assert win.canvas._editor.isVisible(), "双击后应显示就地输入框"
    win.canvas._editor.setText("孔位B")
    QTest.keyClick(win.canvas._editor, Qt.Key.Key_Return)
    assert lead_dbl.text_content == "孔位B", "双击修改文字失败"

    # 端点符号预设渲染（三角/圆点/圆圈/无均正常绘制，无端点无圆头凸起）
    from annotator.items import STYLE_ABOVE, STYLE_BOX, STYLE_PLAIN
    for style in ("arrow", "dot", "circle", "none"):
        ep = win.canvas.add_leader_item(QPointF(200, 80 + 40), QPointF(700, 80), f"端点{style}")
        ep.endpoint_style = style
    none_item = win.canvas.items[-1]
    assert none_item.endpoint_style == "none", "端点样式赋值失败"
    assert win.canvas._new_style().get("endpoint_style") in ("arrow", "dot", "circle", "none")
    assert win.canvas._new_style().get("label_style") in ("above_text", "middle_text", "below_text", "no_line")
    assert STYLE_BOX == "box" and STYLE_ABOVE == "above" and STYLE_PLAIN == "plain"

    # 标注风格渲染验证：above 文字矩形以 text_point 为中心，单侧横线在文字正下方
    above = win.canvas.add_leader_item(QPointF(300, 300), QPointF(600, 240), "红线上方文字")
    above.label_style = STYLE_ABOVE
    above.above_dir = "left"   # 显式指定方向后断言几何
    above_rect = above.text_rect()
    assert abs(above_rect.center().x() - above.text_point.x()) < 0.6, "above 文字应水平居中于 text_point"
    assert abs(above_rect.center().y() - above.text_point.y()) < 0.6, "above 文字应垂直居中于 text_point"
    inner, outer, _ = above._above_geometry()
    assert inner.y() == outer.y(), "above 横线应水平"
    assert abs((inner.y() - above_rect.bottom()) - 4) < 0.6, "横线应在文字下方 4px"
    # 横线自适应文字宽度：left 方向内端在文字左边缘正下方
    assert abs(inner.x() - above_rect.left()) < 0.6, "left 方向横线内端应在文字左边缘下方"
    assert outer.x() < above_rect.left(), "left 方向横线应向左延伸出文字区域"
    box_item = win.canvas.add_leader_item(QPointF(320, 320), QPointF(620, 260), "框内文字")
    box_item.label_style = STYLE_BOX
    box_item.bg_enabled = True
    assert box_item.text_rect().topLeft() == box_item.text_point, "box 文字左上角应位于 text_point"
    plain_item = win.canvas.add_leader_item(QPointF(340, 340), QPointF(640, 280), "透明文字")
    plain_item.label_style = STYLE_PLAIN
    assert plain_item.text_rect().topLeft() == plain_item.text_point, "plain 文字左上角应位于 text_point"

    # 8. 图层结构树：元素条目数量与点击选中联动（v1.5 起历史面板已并入图层树）
    win.layer_tree.refresh(win.canvas.layers, win.canvas.items, win.canvas.current_layer)
    app.processEvents()
    total_children = sum(win.layer_tree.tree.topLevelItem(i).childCount()
                         for i in range(win.layer_tree.tree.topLevelItemCount()))
    assert total_children == len(win.canvas.items), "图层树元素条目数量错误"
    target_id = win.canvas.items[0].id
    win.layer_tree.requestSelectItem.emit(target_id)
    assert any(it.selected and it.id == target_id for it in win.canvas.items), "图层树点击选中失败"

    # 9. 自动保存：序列化往返 + 去抖定时器触发落盘
    from annotator import autosave
    data = autosave.serialize_items(win.canvas.items)
    restored = autosave.deserialize_items(data)
    assert len(restored) == len(win.canvas.items), "自动保存序列化往返数量错误"
    lead_src = next(it for it in win.canvas.items if isinstance(it, LeaderLineItem))
    lead_dst = next(it for it in restored if isinstance(it, LeaderLineItem))
    assert lead_dst.text_content == lead_src.text_content, "自动保存内容不一致"
    assert lead_dst.target_point == lead_src.target_point, "自动保存坐标不一致"
    assert lead_dst.line_color == lead_src.line_color, "自动保存颜色不一致"

    # 去抖定时器落盘（驱动事件循环等待 600ms 定时器）
    QTest.qWait(900)
    import os as _os
    _d = autosave.autosave_dir()
    assert _os.path.isfile(_os.path.join(_d, "image.png")), "自动保存图片未落盘"
    assert _os.path.isfile(_os.path.join(_d, "items.json")), "自动保存数据未落盘"
    _pm2, _items2, _layers2, _cur2 = autosave.load()
    assert _items2 is not None and len(_items2) == len(win.canvas.items), "自动保存恢复数量错误"
    autosave.clear()   # 清理测试数据，避免污染用户环境

    # 10. 输入期间引线预览（需求：输入文字时标注线一直可见）
    win.canvas.set_mode(MODE_LEADER)
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(150, 320))
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(560, 100))
    assert win.canvas._editor.isVisible(), "输入框应显示"
    assert win.canvas._input_preview is not None, "输入期间应保持引线预览状态"
    n_before_preview = len(win.canvas.items)
    shot_preview = win.canvas.grab()
    shot_preview.save(os.path.join(tempfile.gettempdir(), "annotator_input_preview.png"), "PNG")
    QTest.keyClick(win.canvas._editor, Qt.Key.Key_Escape)
    assert len(win.canvas.items) == n_before_preview, "Esc 不应创建元素"
    assert win.canvas._input_preview is None, "取消后预览应清除"

    # 12. 越界标注导出：文字/引线超出图片边界时画布自动扩展，不截断
    out_item = win.canvas.add_leader_item(QPointF(80, 500), QPointF(-120, -40), "越界文字")
    out_item.label_style = STYLE_BOX
    out_item.bg_enabled = True
    exp_img = win.canvas.render_export()
    b = out_item.export_bounds()
    # 扩展画布应足以容纳原图 + 越界标注（文字矩形约 5 字宽）
    assert exp_img.width() >= win.canvas.pixmap.width() + abs(b.left()), "越界导出宽度未扩展"
    assert exp_img.height() >= win.canvas.pixmap.height() + abs(b.top()), "越界导出高度未扩展"
    assert b.right() <= exp_img.width() and b.bottom() <= exp_img.height(), "越界标注右/下仍被截断"

    # 13. 无端点选中：画布上目标点处不应有蓝色标记（把手）
    none_sel = win.canvas.add_leader_item(QPointF(150, 60), QPointF(300, 60), "无端点选中")
    none_sel.endpoint_style = "none"
    none_sel.selected = True
    win.canvas.update()

    # 15. above 横线方向：按图片左右半区自动判定 + 点击文字翻转
    from annotator.items import ABOVE_DIR_LEFT, ABOVE_DIR_RIGHT
    left_it = win.canvas.add_leader_item(QPointF(400, 470), QPointF(140, 90), "左标注")
    left_it.label_style = STYLE_ABOVE
    left_it.apply_style({"font_size": 18, "text_color": "#000000",
                         "bg_enabled": False, "bg_fill_color": "#FFFFFF",
                         "bg_border_color": "#FF0000", "endpoint_style": "arrow",
                         "label_style": STYLE_ABOVE, "above_dir": "auto"})
    win.canvas._resolve_above_dir(left_it)
    assert left_it.above_dir == ABOVE_DIR_LEFT, "左半区标注横线应向左"
    right_it = win.canvas.add_leader_item(QPointF(200, 470), QPointF(760, 90), "右标注")
    right_it.label_style = STYLE_ABOVE
    right_it.apply_style({"font_size": 18, "text_color": "#000000",
                          "bg_enabled": False, "bg_fill_color": "#FFFFFF",
                          "bg_border_color": "#FF0000", "endpoint_style": "arrow",
                          "label_style": STYLE_ABOVE, "above_dir": "auto"})
    win.canvas._resolve_above_dir(right_it)
    assert right_it.above_dir == ABOVE_DIR_RIGHT, "右半区标注横线应向右"
    # 双击文字 → 翻转（单击改为双击：拖动文字不再误触发方向变化）
    left_it.selected = True
    win.canvas.set_mode(MODE_SELECT)
    lv = win.canvas.image_to_view(left_it.text_point)
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(int(lv.x()), int(lv.y())))
    assert left_it.above_dir == ABOVE_DIR_LEFT, "单击文字不应翻转横线方向"
    QTest.mouseDClick(win.canvas, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(int(lv.x()), int(lv.y())))
    assert left_it.above_dir == ABOVE_DIR_RIGHT, "双击文字应翻转横线方向"
    QTest.mouseDClick(win.canvas, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(int(lv.x()), int(lv.y())))
    assert left_it.above_dir == ABOVE_DIR_LEFT, "再次双击文字应翻回"

    # 16. 引线序号：自动编号 / 删除补缺 / 格式 / 重新排序
    from annotator.items import format_number
    win.canvas.set_number_enabled(True)
    win.canvas.set_number_format("circle")
    n1 = win.canvas.add_leader_item(QPointF(120, 480), QPointF(200, 60), "序号甲")
    n2 = win.canvas.add_leader_item(QPointF(180, 470), QPointF(500, 70), "序号乙")
    n3 = win.canvas.add_leader_item(QPointF(240, 460), QPointF(760, 80), "序号丙")
    win.canvas.renumber()
    nums = [it.number for it in win.canvas.items
            if isinstance(it, LeaderLineItem)]
    assert nums == list(range(1, len(nums) + 1)), "自动编号应连续 1..N"
    assert n2.number == n1.number + 1 and n3.number == n2.number + 1, "新增应连续递增"
    assert format_number(1, "circle") == "①", "① 格式错误"
    assert format_number(2, "paren") == "（2）", "（2）格式错误"
    assert format_number(3, "plain") == "3", "3 格式错误"
    win.canvas.delete_item(n1)
    nums = [it.number for it in win.canvas.items
            if isinstance(it, LeaderLineItem)]
    assert nums == list(range(1, len(nums) + 1)), "删除后序号应自动补缺"
    # 编辑序号调整顺序：把 n3 移到序号 1
    win.canvas.reorder_by_number(n3.id, 1)
    assert n3.number == 1, "编辑序号后应自动重新排序编号"
    nums = [it.number for it in win.canvas.items
            if isinstance(it, LeaderLineItem)]
    assert nums == list(range(1, len(nums) + 1)), "重排后应连续无缺"

    # 17. 文字对齐磁吸：左对齐吸附到其它标注文字左边缘
    win.canvas.snap_mode = "left"
    snap_item = win.canvas.add_leader_item(QPointF(90, 490), QPointF(n3.text_point.x() + 6, 180), "吸附文字")
    win.canvas._snap_item_on_release(snap_item)
    assert abs(snap_item.text_rect().left() - n3.text_rect().left()) < 0.6, "左对齐磁吸失败"
    win.canvas.snap_mode = "none"

    # 18. 一键自动布局：端点不变，文字位置参与对齐分组
    before_targets = [(it.target_point.x(), it.target_point.y())
                      for it in win.canvas.items if isinstance(it, LeaderLineItem)]
    win.canvas.auto_layout()
    after_targets = [(it.target_point.x(), it.target_point.y())
                     for it in win.canvas.items if isinstance(it, LeaderLineItem)]
    assert before_targets == after_targets, "自动布局不应改变端点"

    # 19. Esc 取消当前绘制后自动回到选择模式
    win.canvas.set_mode(MODE_LEADER)
    QTest.mouseClick(win.canvas, Qt.MouseButton.LeftButton, pos=vpoint(150, 320))
    assert win.canvas._pending_target is not None, "应处于引线绘制等待第二次点击状态"
    QTest.keyClick(win.canvas, Qt.Key.Key_Escape)
    assert win.canvas.mode == MODE_SELECT, "Esc 后应自动切回选择模式"

    # 14. 画布渲染截图（人工核对引线/箭头/文字框样式）
    shot = win.canvas.grab()
    shot_path = os.path.join(tempfile.gettempdir(), "annotator_canvas.png")
    assert shot.save(shot_path, "PNG"), "截图失败"

    # 8. 导出 PNG（画布内容 + 标注合并成静态图）
    out_path = os.path.join(tempfile.gettempdir(), "annotator_export.png")
    img = win.canvas.render_export()
    assert img.save(out_path, "PNG"), "导出 PNG 失败"
    assert os.path.getsize(out_path) > 0, "导出文件为空"

    # 9. 导出 JPG
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtGui import QImageWriter
    jpg_path = os.path.join(tempfile.gettempdir(), "annotator_export.jpg")
    writer = QImageWriter(jpg_path, QByteArray(b"JPG"))
    writer.setQuality(90)
    assert writer.write(win.canvas.render_export()), "导出 JPG 失败"

    print(f"SMOKE OK\n  截图: {shot_path}\n  PNG : {out_path}\n  JPG : {jpg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
