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
SENSITIVE_KEYS = {"SerialNumber", "UniqueId", "ObjectId", "Path", "UUID", "IdentifyingNumber"}


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


def main(src: str, dest: str) -> None:
    report = json.loads(Path(src).read_text(encoding="utf-8"))
    out_dir = Path(dest)
    out_dir.mkdir(parents=True, exist_ok=True)
    for res in report["results"]:
        if res.get("raw") is None:
            continue
        path = out_dir / f"{res['check_id']}.json"
        path.write_text(json.dumps(scrub(res["raw"]), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"寫入 {path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
