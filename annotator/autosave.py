# -*- coding: utf-8 -*-
"""实时自动保存：把「当前图片 + 全部标注」序列化到本地目录。

- 每次画布变化后延迟保存（去抖），防止意外丢失。
- 程序启动时可检测并恢复上次未保存的工作。
- 数据保存在「exe 所在目录（打包后）/ 源码项目根目录」下的 autosave/（见 _app_base_dir），
  不写用户目录、不写系统临时目录。
"""

import json
import os
import base64
import io

from PyQt6.QtCore import QStandardPaths, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QColor, QPixmap, QImage

from .items import (LeaderLineItem, PenItem, ShapeItem, TextItem,
                    HighlightItem, MosaicItem, EmojiItem, ImageItem)


def _app_base_dir() -> str:
    """获取应用基准目录：打包成 exe 时为 exe 所在目录，源码运行时为项目根目录。"""
    import sys
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后的 exe
        return os.path.dirname(sys.executable)
    else:
        # 源码运行：annotator 包的上一级
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def autosave_dir() -> str:
    d = os.path.join(_app_base_dir(), "autosave")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------- 序列化 ----------------
def _color_to_list(c: QColor):
    return [c.red(), c.green(), c.blue(), c.alpha()]


def _color_from_list(v) -> QColor:
    r, g, b, a = v
    return QColor(r, g, b, a)


def serialize_items(items: list) -> list:
    out = []
    for it in items:
        base = {"layer_id": it.layer_id}
        if isinstance(it, LeaderLineItem):
            base.update({
                "type": "leader",
                "target": [it.target_point.x(), it.target_point.y()],
                "text_point": [it.text_point.x(), it.text_point.y()],
                "content": it.text_content,
                "line_color": _color_to_list(it.line_color),
                "line_width": it.line_width,
                "arrow_size": it.arrow_size,
                "endpoint_style": it.endpoint_style,
                "label_style": it.label_style,
                "above_dir": it.above_dir,
                "number": it.number,
                "number_fmt": it.number_fmt,
                "font_size": it.font_size,
                "text_color": _color_to_list(it.text_color),
                "font_family": it.font_family,
                "font_weight": it.font_weight,
                "font_italic": it.font_italic,
                "script": it.script,
                "bg_enabled": it.bg_enabled,
                "bg_fill_color": _color_to_list(it.bg_fill_color),
                "bg_border_color": _color_to_list(it.bg_border_color),
                "rotation": float(getattr(it, "rotation", 0.0)),
            })
        elif isinstance(it, TextItem):
            base.update({
                "type": "text",
                "pos": [it.pos.x(), it.pos.y()],
                "content": it.text_content,
                "font_size": it.font_size,
                "text_color": _color_to_list(it.text_color),
                "font_family": it.font_family,
                "font_weight": it.font_weight,
                "font_italic": it.font_italic,
                "script": it.script,
                "bg_enabled": it.bg_enabled,
                "bg_fill_color": _color_to_list(it.bg_fill_color),
                "bg_border_color": _color_to_list(it.bg_border_color),
                "rotation": float(getattr(it, "rotation", 0.0)),
            })
        elif isinstance(it, ShapeItem):
            base.update({
                "type": "shape",
                "p1": [it.p1.x(), it.p1.y()],
                "p2": [it.p2.x(), it.p2.y()],
                "shape": it.shape,
                "border_color": _color_to_list(it.border_color),
                "fill_color": _color_to_list(it.fill_color),
                "line_width": it.line_width,
                "rotation": float(getattr(it, "rotation", 0.0)),
                # v2.0：形状内嵌文字（含直线）与文字垂直位置
                "content": getattr(it, "text_content", ""),
                "text_pos": getattr(it, "text_pos", "center"),
                "font_size": it.font_size,
                "text_color": _color_to_list(it.text_color),
                "font_family": it.font_family,
                "font_weight": it.font_weight,
                "font_italic": it.font_italic,
                "script": it.script,
                # v2.1：标注类形状尾尖位置（旧版比例字段，保留兼容）
                "tail_x": getattr(it, "tail_x", None),
                "tail_len": getattr(it, "tail_len", None),
            })
            # 新版：尾尖绝对位置（未旋转图片坐标，可在主体四周任意位置）
            _apex = getattr(it, "tail_apex", None)
            if _apex is not None:
                base["tail_apex"] = [_apex.x(), _apex.y()]
            # 多点折线（点击式连续画线）：仅当顶点数>=3 时额外持久化，两点直线保持旧格式
            if getattr(it, "points", None) and len(it.points) >= 3:
                base["line_points"] = [[p.x(), p.y()] for p in it.points]
        elif isinstance(it, PenItem):
            base.update({
                "type": "pen",
                "points": [[p.x(), p.y()] for p in it.points],
                "pen_color": _color_to_list(it.pen_color),
                "pen_width": it.pen_width,
            })
        elif isinstance(it, HighlightItem):
            base.update({
                "type": "highlight",
                "points": [[p.x(), p.y()] for p in it.points],
                "hl_color": _color_to_list(it.hl_color),
                "hl_width": it.hl_width,
                "hl_alpha": it.hl_alpha,
            })
        elif isinstance(it, MosaicItem):
            base.update({
                "type": "mosaic",
                "p1": [it.p1.x(), it.p1.y()],
                "p2": [it.p2.x(), it.p2.y()],
                "block_size": it.block_size,
                "show_border": bool(it.show_border),
            })
        elif isinstance(it, EmojiItem):
            base.update({
                "type": "emoji",
                "pos": [it.pos.x(), it.pos.y()],
                "emoji": it.emoji,
                "font_size": it.font_size,
                "rotation": float(getattr(it, "rotation", 0.0)),
            })
        elif isinstance(it, ImageItem):
            pm = it.pixmap()
            b64 = ""
            if pm is not None and not pm.isNull():
                arr = QByteArray()
                buf = QBuffer(arr)
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                pm.save(buf, "PNG")
                b64 = bytes(base64.b64encode(bytes(arr))).decode("ascii")
            base.update({
                "type": "image",
                "p1": [it.p1.x(), it.p1.y()],
                "p2": [it.p2.x(), it.p2.y()],
                "data": b64,
                "rotation": float(getattr(it, "rotation", 0.0)),
            })
        out.append(base)
    return out


def deserialize_items(data: list) -> list:
    items = []
    for d in data:
        try:
            t = d.get("type", "")
            if t == "leader":
                it = LeaderLineItem(
                    (d["target"][0], d["target"][1]),
                    (d["text_point"][0], d["text_point"][1]),
                    d.get("content", ""),
                    line_color=_color_from_list(d["line_color"]),
                    line_width=d.get("line_width", 2),
                    arrow_size=d.get("arrow_size", 14),
                    endpoint_style=d.get("endpoint_style", "arrow"),
                    label_style=d.get("label_style", "plain"),
                    font_size=(lambda v: v if isinstance(v, (int, float)) and v > 0 else 18)(d.get("font_size", 18)),
                    text_color=_color_from_list(d["text_color"]))
                it.above_dir = d.get("above_dir", "left")
                it.number = d.get("number")
                it.number_fmt = d.get("number_fmt", "circle")
                it.bg_enabled = bool(d.get("bg_enabled", False))
                it.bg_fill_color = _color_from_list(d["bg_fill_color"])
                it.bg_border_color = _color_from_list(d["bg_border_color"])
            elif t == "text":
                it = TextItem(
                    (d["pos"][0], d["pos"][1]),
                    d.get("content", ""),
                    font_size=(lambda v: v if isinstance(v, (int, float)) and v > 0 else 18)(d.get("font_size", 18)),
                    text_color=_color_from_list(d["text_color"]))
                it.bg_enabled = bool(d.get("bg_enabled", False))
                it.bg_fill_color = _color_from_list(d["bg_fill_color"])
                it.bg_border_color = _color_from_list(d["bg_border_color"])
            elif t == "shape":
                it = ShapeItem(
                    (d["p1"][0], d["p1"][1]), (d["p2"][0], d["p2"][1]),
                    shape=d.get("shape", "rect"),
                    border_color=_color_from_list(d["border_color"]),
                    fill_color=_color_from_list(d["fill_color"]),
                    line_width=d.get("line_width", 2))
                it.rotation = float(d.get("rotation", 0.0))
                it.text_content = d.get("content", "") or ""
                it.text_pos = d.get("text_pos", "center")
                # v2.1：标注尾尖旧版比例字段（用于旧存档迁移）
                tx = d.get("tail_x", None)
                tl = d.get("tail_len", None)
                it.tail_x = float(tx) if isinstance(tx, (int, float)) else None
                it.tail_len = float(tl) if isinstance(tl, (int, float)) else None
                # 新版尾尖绝对位置优先（存在时旧比例字段不再使用）
                _ap = d.get("tail_apex", None)
                if (isinstance(_ap, (list, tuple)) and len(_ap) == 2):
                    from PyQt6.QtCore import QPointF as _QPF2
                    it.tail_apex = _QPF2(float(_ap[0]), float(_ap[1]))
                _lp = d.get("line_points")
                if _lp and len(_lp) >= 3:
                    from PyQt6.QtCore import QPointF as _QPF
                    it.points = [_QPF(float(p[0]), float(p[1])) for p in _lp]
            elif t == "pen":
                it = PenItem([[p[0], p[1]] for p in d.get("points", [])],
                             pen_color=_color_from_list(d["pen_color"]),
                             pen_width=d.get("pen_width", 3))
            elif t == "highlight":
                it = HighlightItem([[p[0], p[1]] for p in d.get("points", [])],
                                   hl_color=_color_from_list(d.get("hl_color", [255, 230, 0, 255])),
                                   hl_width=d.get("hl_width", 22),
                                   hl_alpha=d.get("hl_alpha", 80))
            elif t == "mosaic":
                it = MosaicItem((d["p1"][0], d["p1"][1]), (d["p2"][0], d["p2"][1]),
                                block_size=d.get("block_size", 10),
                                show_border=d.get("show_border", True))
            elif t == "emoji":
                it = EmojiItem((d["pos"][0], d["pos"][1]),
                               emoji=d.get("emoji", "😀"),
                               font_size=d.get("font_size", 40))
            elif t == "image":
                pm = QPixmap()
                b64 = d.get("data", "") or ""
                if b64:
                    try:
                        raw = base64.b64decode(b64)
                        pm.loadFromData(QByteArray(raw), "PNG")
                    except Exception:
                        pm = QPixmap()
                it = ImageItem((d["p1"][0], d["p1"][1]),
                               (d["p2"][0], d["p2"][1]), pm)
            else:
                continue
            it.layer_id = int(d.get("layer_id", 0))
            # v1.7 需求1：引线标签/文本/表情与形状一致支持旋转，统一存档
            it.rotation = float(d.get("rotation", 0.0))
            if "font_family" in d:
                it.font_family = d["font_family"]
            if "font_weight" in d:
                it.font_weight = int(d["font_weight"])
            if "font_italic" in d:
                it.font_italic = bool(d["font_italic"])
            if "script" in d:
                it.script = d["script"]
            it.selected = False
            items.append(it)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return items


# ---------------- 图层序列化 ----------------
def serialize_layers(layers: list) -> list:
    return [{"id": l.id, "name": l.name, "visible": l.visible}
            for l in layers]


def deserialize_layers(data: list, items: list) -> list:
    """重建图层列表；保存时的 layer_id 已写入 items，
    反序列化后按「顺序 + 旧 id 映射」把 items 归属到新图层 id。"""
    from .items import Layer
    layers = []
    mapping = {}
    for d in data:
        try:
            old_id = int(d.get("id", 0))
            layer = Layer(d.get("name", "图层"))
            layer.visible = bool(d.get("visible", True))
            mapping[old_id] = layer.id
            layers.append(layer)
        except (KeyError, TypeError, ValueError):
            continue
    if not layers:
        layer = Layer("图层1")
        layers = [layer]
        mapping[0] = layer.id
    default_id = layers[-1].id
    for it in items:
        it.layer_id = mapping.get(it.layer_id, default_id)
    return layers


# ---------------- 保存 / 恢复 ----------------
def save(pixmap: QPixmap, items: list, layers: list = None,
         current_layer: int = None) -> bool:
    """把画布状态保存到自动保存目录。"""
    d = autosave_dir()
    img_path = os.path.join(d, "image.png")
    data_path = os.path.join(d, "items.json")
    try:
        if not pixmap.save(img_path, "PNG"):
            return False
        payload = {
            "items": serialize_items(items),
            "layers": serialize_layers(layers) if layers else None,
            "current_layer": current_layer,
        }
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except (OSError, TypeError):
        return False


def load():
    """返回 (QPixmap, items, layers, current_layer)；无数据时 (None, None, None, None)。"""
    d = autosave_dir()
    img_path = os.path.join(d, "image.png")
    data_path = os.path.join(d, "items.json")
    if not (os.path.isfile(img_path) and os.path.isfile(data_path)):
        return None, None, None, None
    pm = QPixmap(img_path)
    if pm.isNull():
        return None, None, None, None
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            # 兼容旧版：直接是 items 数组
            items = deserialize_items(payload)
            layers = None
            current_layer = None
        else:
            items = deserialize_items(payload.get("items", []))
            layers = deserialize_layers(payload.get("layers", []), items)
            current_layer = payload.get("current_layer")
            if layers and current_layer is not None:
                for l in layers:
                    if l.id == current_layer:
                        break
                else:
                    current_layer = layers[-1].id
    except (OSError, ValueError, json.JSONDecodeError):
        return None, None, None, None
    return pm, items, layers, current_layer


def clear() -> None:
    d = autosave_dir()
    for name in ("image.png", "items.json"):
        try:
            os.remove(os.path.join(d, name))
        except OSError:
            pass
