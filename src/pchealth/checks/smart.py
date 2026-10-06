"""smartctl（smartmontools）：讀取硬碟完整的 SMART 健康資料。

打包版會附帶 smartctl.exe（GPLv2，見 THIRD_PARTY_NOTICES.md）。需要管理員權限。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
# 不保存可識別硬碟本身的資訊（序號等），匯出資料時也就不會外流
PRIVATE_KEYS = ("serial_number", "wwn", "logical_unit_id", "nvme_eui64")


def find_smartctl() -> Path | None:
    from ..runner import resource_dir  # 避免循環匯入
    candidates = [
        resource_dir() / "bin" / "smartctl.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "smartmontools" / "bin" / "smartctl.exe",
    ]
    if found := shutil.which("smartctl"):
        candidates.append(Path(found))
    return next((p for p in candidates if p.exists()), None)


def device_name(device_id: int) -> str:
    """Windows 的 PhysicalDriveN → smartctl 的 /dev/sdX（0→sda、26→sdaa）。"""
    letters = ""
    n = device_id
    while True:
        letters = chr(ord("a") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            return f"/dev/sd{letters}"


def _run(exe: Path, args: list[str], timeout: int = 30) -> dict | None:
    try:
        proc = subprocess.run([str(exe), *args, "-j"], capture_output=True, timeout=timeout,
                              creationflags=CREATE_NO_WINDOW)
        data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "null")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for key in PRIVATE_KEYS:
        data.pop(key, None)
    return data


def has_health(data: dict | None) -> bool:
    return bool(data) and ("nvme_smart_health_information_log" in data
                           or "ata_smart_attributes" in data or "smart_status" in data)


def collect(disks: list[dict], admin: bool) -> dict:
    """回傳 {"status": ok/not_admin/not_found, "version": ..., "disks": {DeviceId: smartctl JSON}}。"""
    if not admin:
        return {"status": "not_admin", "disks": {}}
    exe = find_smartctl()
    if not exe:
        return {"status": "not_found", "disks": {}}
    version = (_run(exe, ["--version"]) or {}).get("smartctl", {}).get("version")
    results = {}
    for d in disks:
        try:
            dev = device_name(int(d.get("DeviceId")))
        except (TypeError, ValueError):
            continue
        # NVMe 經 Windows 標準驅動時要指定 -d nvme；失敗再讓 smartctl 自動判斷
        attempts = [["-a", "-d", "nvme", dev], ["-a", dev]] if d.get("BusType") == "NVMe" else [["-a", dev]]
        for args in attempts:
            data = _run(exe, args)
            if has_health(data):
                results[str(d["DeviceId"])] = data
                break
    return {"status": "ok", "version": version and ".".join(map(str, version)), "disks": results}
