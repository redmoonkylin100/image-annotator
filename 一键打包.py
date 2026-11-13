# -*- coding: utf-8 -*-
"""一键打包脚本（使用项目 venv 中的 PyInstaller）。

用法：
- 双击本脚本：自动改用 pythonw 在后台静默打包，无 cmd 黑窗，
  日志写入项目根目录「打包日志.txt」；
- 命令行实时查看日志：venv\\Scripts\\python.exe 一键打包.py --debug

产物：dist\\图片标注工具.exe
- 独立单文件（onefile）、无控制台窗口（console=False，不弹黑框）；
- exe 文件图标嵌入 1.ico；2.ico 随资源嵌入 exe，运行时作为窗口/任务栏/托盘图标；
- 运行时所有数据（autosave/、settings.json、items.json 等）写在 exe 同目录，
  不写用户目录、不写系统临时目录。
"""

import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
SPEC_FILE = os.path.join(BASE_DIR, "图片标注工具.spec")
DIST_EXE = os.path.join(BASE_DIR, "dist", "图片标注工具.exe")
LOG_FILE = os.path.join(BASE_DIR, "打包日志.txt")
MIRROR = "https://mirrors.aliyun.com/pypi/simple/"


def _say(msg: str) -> None:
    """同时输出到控制台（若存在）与日志文件。"""
    try:
        print(msg)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _run(cmd, debug: bool) -> int:
    """执行子命令：debug 时输出到控制台，否则追加进日志。"""
    if debug:
        return subprocess.run(cmd, cwd=BASE_DIR).returncode
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        return subprocess.run(cmd, cwd=BASE_DIR, stdout=f,
                              stderr=subprocess.STDOUT).returncode


def _do_pack(debug: bool) -> int:
    if not os.path.exists(VENV_PY):
        _say("[错误] 未找到虚拟环境：" + VENV_PY)
        _say("请先执行：")
        _say("    py -3.13 -m venv venv")
        _say("    venv\\Scripts\\python.exe -m pip install -r requirements.txt pyinstaller -i " + MIRROR)
        return 1

    # 确保 PyInstaller 已安装（缺失时自动用国内镜像安装）
    chk = subprocess.run([VENV_PY, "-m", "PyInstaller", "--version"],
                         capture_output=True, text=True)
    if chk.returncode != 0:
        _say("[信息] 虚拟环境中未安装 PyInstaller，正在自动安装（阿里云镜像）…")
        if _run([VENV_PY, "-m", "pip", "install", "pyinstaller",
                 "-i", MIRROR, "--timeout", "60"], debug) != 0:
            _say("[错误] PyInstaller 安装失败，请检查网络后重试。")
            return 1

    _say("[信息] 开始打包（首次约 1~3 分钟，请稍候）…")
    rc = _run([VENV_PY, "-m", "PyInstaller",
               "--noconfirm", "--clean", SPEC_FILE], debug)
    if rc != 0:
        _say("[错误] 打包失败，详见日志：" + LOG_FILE)
        return 1

    if os.path.exists(DIST_EXE):
        _say("[完成] 打包成功：" + DIST_EXE)
        _say("提示：exe 为独立单文件、无控制台窗口；")
        _say("      运行时数据（autosave/ 等）写在 exe 同目录，不在临时目录。")
    else:
        _say("[警告] 打包结束但未找到产物，请检查 dist/ 目录。")
    return 0


def main() -> int:
    debug = "--debug" in sys.argv
    # 清空上一次的日志，开始新的一轮
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("==== 图片标注工具 打包日志 ====\n")
    except OSError:
        pass

    # 双击运行时若带控制台，自动用 pythonw 静默自举，不弹黑窗
    if (not debug and sys.platform == "win32"
            and not sys.executable.lower().endswith("pythonw.exe")):
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            try:
                subprocess.Popen([pythonw, os.path.abspath(__file__), "--debug"],
                                 cwd=BASE_DIR, close_fds=True)
            except OSError:
                pass
            else:
                print("已转入后台静默打包，请稍候查看日志：" + LOG_FILE)
                return 0
    return _do_pack(debug)


if __name__ == "__main__":
    sys.exit(main())
