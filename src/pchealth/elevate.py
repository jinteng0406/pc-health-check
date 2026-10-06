"""要求管理員權限。使用者拒絕時，程式仍以一般權限執行。"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(extra_args: list[str]) -> bool:
    """以 UAC 重新啟動自己；成功送出回傳 True（呼叫端應結束目前的程序）。"""
    if getattr(sys, "frozen", False):
        params = extra_args
    else:
        params = [os.path.abspath(sys.argv[0]), *extra_args]
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, subprocess.list2cmdline(params), None, 1)
    return ret > 32  # 使用者按「否」時回傳值 <= 32
