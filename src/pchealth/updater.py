"""檢查 GitHub Releases 是否有新版。只讀取版本號，不會自動下載或覆蓋程式。"""
from __future__ import annotations

import json
import urllib.request

from . import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(tag: str) -> tuple[int, ...]:
    parts = tag.strip().lstrip("vV").split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def is_newer(remote_tag: str, local: str = __version__) -> bool:
    try:
        return parse_version(remote_tag) > parse_version(local)
    except ValueError:
        return False


def check_latest(timeout: float = 5) -> tuple[str, str] | None:
    """有新版時回傳 (版本標籤, 下載頁網址)，否則或連不上時回傳 None。"""
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "pc-health-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return None
    tag = data.get("tag_name", "")
    return (tag, data.get("html_url", "")) if is_newer(tag) else None
