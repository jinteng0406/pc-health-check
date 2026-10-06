from __future__ import annotations

import argparse
import sys

from . import elevate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="PCHealthCheck")
    parser.add_argument("--demo", action="store_true", help="使用內建的假資料（含故障情境），不讀取真實硬體")
    parser.add_argument("--no-elevate", action="store_true", help="不要求管理員權限")
    parser.add_argument("--elevate", action="store_true", help="開發時也要求管理員權限（打包版預設會要求）")
    args = parser.parse_args(argv)

    wants_elevate = (getattr(sys, "frozen", False) or args.elevate) and not args.no_elevate
    if wants_elevate and not args.demo and not elevate.is_admin():
        relaunch_args = ["--no-elevate"]  # 避免重複要求
        if elevate.relaunch_as_admin(relaunch_args):
            return 0
        # 使用者拒絕 UAC：繼續以一般權限執行

    from .gui import run_app  # 延後載入，讓 --help 不必載入 Qt
    return run_app(demo=args.demo, admin=elevate.is_admin())
