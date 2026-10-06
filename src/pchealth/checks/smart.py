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
# 只保留判斷需要的欄位：資料量小，也不會留下序號、EUI-64 等可識別硬碟本身的資訊
KEEP_KEYS = ("device", "model_name", "firmware_version", "smart_status", "smartctl",
             "nvme_smart_health_information_log", "nvme_composite_temperature_threshold",
             "ata_smart_attributes", "temperature", "power_on_time", "endurance_used", "spare_available")


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
    data = {k: v for k, v in data.items() if k in KEEP_KEYS}
    if isinstance(data.get("smartctl"), dict):
        data["smartctl"] = {k: data["smartctl"].get(k) for k in ("version", "exit_status")}
    if isinstance(data.get("ata_smart_attributes"), dict):
        data["ata_smart_attributes"] = {"table": [
            {"id": a.get("id"), "name": a.get("name"), "raw": {"value": (a.get("raw") or {}).get("value")}}
            for a in data["ata_smart_attributes"].get("table") or []]}
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
    version = next((d["smartctl"].get("version") for d in results.values()
                    if isinstance(d.get("smartctl"), dict)), None)
    return {"status": "ok", "version": ".".join(map(str, version)) if version else None, "disks": results}
