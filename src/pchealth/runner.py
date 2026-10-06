"""執行所有檢查器，產生一份報告。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .checks import ALL_CHECKS
from .elevate import is_admin
from .model import CheckResult


def resource_dir() -> Path:
    """打包後是 PyInstaller 的解壓目錄，開發時是專案根目錄。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def fixtures_dir() -> Path:
    return resource_dir() / "fixtures"


def load_fixture(check_id: str) -> object | None:
    path = fixtures_dir() / f"{check_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run_all(demo: bool = False) -> dict:
    results: list[CheckResult] = []
    ctx: dict = {}
    for check in ALL_CHECKS:
        raw = None
        if demo:
            raw = load_fixture(check.id)
            if raw is None:
                results.append(CheckResult(check.id, check.title, error="假資料模式：找不到樣本資料"))
                continue
        result = check.run(raw, ctx)
        if result.error is None:
            ctx.update(check.context(result.raw))
        results.append(result)
    return {
        "version": __version__,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "demo": demo,
        "admin": is_admin(),
        "results": [r.to_dict() for r in results],
    }
