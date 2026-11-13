# -*- coding: utf-8 -*-
"""界面 / 样式参数持久化：窗口大小、面板布局、样式参数等，下次启动自动恢复。

数据保存在应用同目录下的 autosave/settings.json（与自动保存图片同一目录）。
"""

import json
import os
import sys


def _app_base_dir() -> str:
    """获取应用基准目录：打包成 exe 时为 exe 所在目录，源码运行时为项目根目录。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后的 exe
        return os.path.dirname(sys.executable)
    else:
        # 源码运行：annotator 包的上一级
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def settings_path() -> str:
    d = os.path.join(_app_base_dir(), "autosave")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def load() -> dict:
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def save(data: dict) -> None:
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except (OSError, TypeError):
        pass


def clear() -> None:
    """删除持久化参数文件（测试隔离用）。"""
    try:
        os.remove(settings_path())
    except OSError:
        pass
