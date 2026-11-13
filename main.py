# -*- coding: utf-8 -*-
"""图片快速标注工具 - 程序入口。

运行：python main.py
"""

import os
import sys
import threading


def _install_native_stderr_filter(blocked_keywords):
    """在操作系统 fd 层面过滤 stderr。

    Qt 底层会绕过 Python 的 sys.stderr，直接向文件描述符 2 写一些无害的
    qWarning（如样式插件 PNG 的「libpng warning: iCCP ...」、样式重绘时的
    「QFont::setPointSize: Point size <= 0 ...」）。仅替换 sys.stderr 拦不住
    C 层输出，因此这里用管道重定向 fd2，后台线程逐行读取，命中任一屏蔽词的
    丢弃，其余原样写回真正的 stderr。
    """
    try:
        read_fd, write_fd = os.pipe()
        saved_fd = os.dup(2)
        os.dup2(write_fd, 2)  # fd2 -> 管道写端
    except (OSError, AttributeError):
        return  # 平台不支持则放弃过滤，不影响程序运行

    def _pump():
        buf = b""
        while True:
            try:
                chunk = os.read(read_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace")
                if not any(k in text for k in blocked_keywords):
                    try:
                        os.write(saved_fd, line + b"\n")
                    except OSError:
                        pass
        # 冲刷残余
        if buf:
            text = buf.decode("utf-8", "replace")
            if not any(k in text for k in blocked_keywords):
                try:
                    os.write(saved_fd, buf)
                except OSError:
                    pass

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    # 让 Python 层的 sys.stderr 也指向真正的终端，而不是管道
    try:
        sys.stderr = os.fdopen(saved_fd, "w", encoding="utf-8", errors="replace")
    except OSError:
        pass


def main() -> int:
    # 在创建 QApplication 前安装 C 层 stderr 过滤。
    # - libpng iCCP：Qt 内置样式 PNG 的不标准 sRGB profile 无害提示；
    # - QFont::setPointSize：Qt 样式引擎 hover 重绘时内部合并字体产生的
    #   无害 qWarning（pointSize=-1 是“改用像素字号”的正常内部值），不影响功能。
    _install_native_stderr_filter(
        ("libpng warning: iCCP", "QFont::setPointSize"))

    # 需求4：设置 Windows 任务栏 AppUserModelID，使任务栏图标分组/悬停提示
    # 显示本程序名称（而非 python.exe）。
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "LocalTools.ImageAnnotator.2")
    except Exception:
        pass

    from PyQt6.QtWidgets import QApplication
    from annotator.window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("图片标注大师")
    app.setOrganizationName("LocalTools")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
