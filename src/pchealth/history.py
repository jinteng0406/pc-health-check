"""檢查紀錄：存在本機，用來跟上一次比較。不會上傳到任何地方。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .model import Severity


def history_dir(demo: bool = False) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PCHealthCheck" / "history"
    return base / "demo" if demo else base  # 假資料不和真實紀錄混在一起


def save(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = report["timestamp"].replace(":", "-") + ".json"
    path = directory / name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest(directory: Path) -> dict | None:
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    for path in reversed(files):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _problems(report: dict) -> dict[str, str]:
    """回傳 {finding id: 標題}，只算「注意」以上的問題。"""
    return {f["id"]: f["title"]
            for r in report.get("results", []) for f in r.get("findings", [])
            if f["severity"] >= Severity.WARNING}


@dataclass
class Diff:
    previous_time: str
    new: list[str]  # 新出現的問題標題
    resolved: list[str]  # 已經消失的問題標題


def diff(previous: dict | None, current: dict) -> Diff | None:
    if previous is None:
        return None
    before, after = _problems(previous), _problems(current)
    return Diff(
        previous_time=previous.get("timestamp", "?"),
        new=[after[k] for k in after.keys() - before.keys()],
        resolved=[before[k] for k in before.keys() - after.keys()],
    )
