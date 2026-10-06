"""把「匯出原始資料」的 JSON 去識別化，轉成可以放進公開 repo 的測試樣本。

用法：python tools/sanitize_export.py <匯出檔.json> <輸出資料夾>
每個檢查器輸出一個 <check_id>.json（只含 raw，已遮掉序號、MAC、GUID）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAC_OR_SERIAL = re.compile(r"(?<![0-9A-F])[0-9A-F]{12,}(?![0-9A-F])", re.IGNORECASE)
GUID = re.compile(r"\{[0-9A-F-]{36}\}", re.IGNORECASE)
SENSITIVE_KEYS = {"SerialNumber", "UniqueId", "ObjectId", "Path", "UUID", "IdentifyingNumber",
                  "serial_number", "wwn", "eui64", "nvme_eui64", "logical_unit_id"}


def sanitize_pnp_id(pnp_id: str, index: int) -> str:
    """保留匯流排與廠商/型號（VEN/DEV/VID/PID），把實例編號（可能是序號）換掉。"""
    if not pnp_id:
        return pnp_id
    parts = pnp_id.split("\\")
    if len(parts) >= 3:
        parts[-1] = f"INST{index:03d}"
    middle = "\\".join(parts)
    return GUID.sub("{GUID}", MAC_OR_SERIAL.sub("X" * 12, middle))


def scrub(obj, counter=[0]):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in SENSITIVE_KEYS:
                out[k] = "REDACTED" if v else v
            elif k == "PNPDeviceID" and isinstance(v, str):
                counter[0] += 1
                out[k] = sanitize_pnp_id(v, counter[0])
            else:
                out[k] = scrub(v, counter)
        return out
    if isinstance(obj, list):
        return [scrub(v, counter) for v in obj]
    return obj


def trim_smart(raw: dict) -> None:
    """舊版匯出的 smartctl 資料可能很完整，套用程式目前的欄位白名單。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from pchealth.checks.smart import KEEP_KEYS
    for key, data in ((raw.get("Smart") or {}).get("disks") or {}).items():
        raw["Smart"]["disks"][key] = {k: v for k, v in data.items() if k in KEEP_KEYS}


WINDOWS_NAMES = {"securityhealth", "explorer", "memory compression", "onedrive", "onedrivesetup",
                 "rtkaudservice", "rtkaudservice64", "rtkaudservice.exe", "svchost", "dwm"}


class Pseudonyms:
    """把使用者安裝的程式名稱換成 app01、app02…（同名得到同代號），Windows 內建名稱保留。"""

    def __init__(self):
        self.names: dict[str, str] = {}

    def __call__(self, name: str | None) -> str | None:
        if not name or name.lower() in WINDOWS_NAMES:
            return name
        stem, dot, ext = name.rpartition(".")
        base, suffix = (stem, f".{ext}") if dot and ext.lower() == "exe" else (name, "")
        if base.lower() not in self.names:
            self.names[base.lower()] = f"app{len(self.names) + 1:02d}"
        return self.names[base.lower()] + suffix


def pseudonymize(check_id: str, raw: dict) -> None:
    alias = Pseudonyms()
    if check_id == "events":
        for c in raw.get("AppCrashes") or []:
            c["App"] = alias(c.get("App"))
    elif check_id == "performance":
        for key in ("Startup", "TopProcesses"):
            for item in raw.get(key) or []:
                item["Name"] = alias(item.get("Name"))


def main(src: str, dest: str) -> None:
    report = json.loads(Path(src).read_text(encoding="utf-8"))
    out_dir = Path(dest)
    out_dir.mkdir(parents=True, exist_ok=True)
    for res in report["results"]:
        if res.get("raw") is None:
            continue
        if res["check_id"] == "storage":
            trim_smart(res["raw"])
        if isinstance(res["raw"], dict):
            pseudonymize(res["check_id"], res["raw"])
        path = out_dir / f"{res['check_id']}.json"
        path.write_text(json.dumps(scrub(res["raw"]), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"寫入 {path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
