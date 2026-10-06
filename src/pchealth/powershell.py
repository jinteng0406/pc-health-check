"""透過 PowerShell 取得系統資料（不需要額外的 Python 套件）。"""
from __future__ import annotations

import json
import subprocess

CREATE_NO_WINDOW = 0x08000000
_PRELUDE = (
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
    "$ProgressPreference = 'SilentlyContinue'; "
)


def run_ps_json(script: str, timeout: int = 60) -> list[dict]:
    """執行 PowerShell 腳本（輸出須為 ConvertTo-Json），一律回傳 list。"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", _PRELUDE + script],
        capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"PowerShell 結束代碼 {proc.returncode}")
    out = proc.stdout.decode("utf-8", errors="replace").lstrip("﻿").strip()
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]
