"""檢查是否有新版：先看本機 OneDrive 資料夾，再看 GitHub Releases。

只讀取版本號，不會自動下載或覆蓋程式。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

from . import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ONEDRIVE_FOLDER = "PCHealthCheck"
_ZIP_RE = re.compile(r"^PCHealthCheck-(v\d+(?:\.\d+)*)\.zip$", re.IGNORECASE)


def onedrive_dir() -> Path | None:
    for var in ("OneDriveConsumer", "OneDrive"):
        if base := os.environ.get(var):
            folder = Path(base) / ONEDRIVE_FOLDER
            if folder.is_dir():
                return folder
    return None


def check_onedrive(folder: Path | None = None) -> tuple[str, Path] | None:
    """OneDrive 資料夾裡有比目前更新的 zip 時，回傳 (版本標籤, 資料夾)。

    檔案就算只在雲端（Files On-Demand 的雲朵圖示）也看得到。
    """
    folder = folder or onedrive_dir()
    if not folder:
        return None
    tags = [m.group(1) for p in folder.glob("PCHealthCheck-*.zip") if (m := _ZIP_RE.match(p.name))]
    newer = [t for t in tags if is_newer(t)]
    return (max(newer, key=parse_version), folder) if newer else None


def parse_version(tag: str) -> tuple[int, ...]:
    parts = tag.strip().lstrip("vV").split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def is_newer(remote_tag: str, local: str = __version__) -> bool:
    try:
        return parse_version(remote_tag) > parse_version(local)
    except ValueError:
        return False


def fetch_latest(timeout: float = 5) -> tuple[str, str] | None:
    """GitHub 上最新版的 (版本標籤, 下載頁網址)；連不上時回傳 None。"""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "pc-health-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return None
    return data.get("tag_name", ""), data.get("html_url", "")


def check(fetch=fetch_latest) -> dict:
    """回傳 {"kind": onedrive／github／latest／unknown, "tag", "target", "onedrive_found"}。"""
    folder = onedrive_dir()
    if local := check_onedrive(folder):
        return {"kind": "onedrive", "tag": local[0], "target": str(local[1]), "onedrive_found": True}
    latest = fetch()
    if latest is None:
        return {"kind": "unknown", "onedrive_found": folder is not None}
    if is_newer(latest[0]):
        return {"kind": "github", "tag": latest[0], "target": latest[1], "onedrive_found": folder is not None}
    return {"kind": "latest", "onedrive_found": folder is not None}
