"""裝置管理員檢查：涵蓋主機板晶片組、顯示卡、USB/接口、音效、網卡等所有裝置。"""
from __future__ import annotations

import re

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .boards import board_support
from .error_codes import IGNORED_CODES, UPDATE_DRIVER, rule_for

OPEN_DEVMGMT = Action("開啟裝置管理員", "devmgmt.msc")

# PCI 的 VEN_xxxx / USB 的 VID_xxxx → 製造商
VENDORS = {
    "8086": "Intel", "8087": "Intel", "10DE": "NVIDIA", "1002": "AMD", "1022": "AMD",
    "10EC": "Realtek", "0BDA": "Realtek", "14E4": "Broadcom", "168C": "Qualcomm Atheros",
    "17CB": "Qualcomm", "1B21": "ASMedia", "1B4B": "Marvell", "144D": "Samsung",
    "046D": "Logitech", "1532": "Razer", "1038": "SteelSeries",
}
_VENDOR_RE = re.compile(r"(?:VEN|VID)_([0-9A-F]{4})", re.IGNORECASE)

VENDOR_HINTS = {
    "Intel": ("Intel 晶片組／主機板內建裝置的驅動通常來自「Intel Chipset Device Software」"
              "或主機板官網的晶片組（Chipset）驅動，也可以用 Intel 驅動與支援助理自動偵測。",
              Action("Intel 驅動與支援助理", "https://www.intel.com/content/www/us/en/support/detect.html")),
    "NVIDIA": ("NVIDIA 顯示卡驅動請到 NVIDIA 官網依型號下載，或使用 NVIDIA App 更新。",
               Action("NVIDIA 驅動下載", "https://www.nvidia.com/Download/index.aspx")),
    "AMD": ("AMD 晶片組或顯示卡驅動請到 AMD 官網下載（可用 AMD Auto-Detect 工具）。",
            Action("AMD 驅動下載", "https://www.amd.com/en/support/download/drivers.html")),
    "Realtek": ("Realtek 多半是主機板內建的音效或網路晶片，建議從主機板官網的支援頁下載對應驅動。", None),
}

PS_SCRIPT = (
    "Get-CimInstance Win32_PnPEntity | "
    "Select-Object Name, PNPClass, Manufacturer, ConfigManagerErrorCode, PNPDeviceID, Present | "
    "ConvertTo-Json -Depth 2 -Compress"
)


def vendor_of(pnp_id: str) -> str | None:
    m = _VENDOR_RE.search(pnp_id or "")
    return VENDORS.get(m.group(1).upper()) if m else None


class DevicesCheck(Check):
    id = "devices"
    title = "裝置與驅動程式"

    def collect(self) -> list[dict]:
        return run_ps_json(PS_SCRIPT)

    def analyze(self, raw: list[dict], ctx: dict) -> list[Finding]:
        devices = [d for d in raw if d.get("Present", True) is not False]
        findings = [self._finding(d, code, ctx) for d in devices
                    if (code := d.get("ConfigManagerErrorCode") or 0) and code not in IGNORED_CODES]
        if not findings:
            findings.append(Finding(
                "devices:all-ok", Severity.OK, f"全部 {len(devices)} 個裝置運作正常",
                detail="裝置管理員中沒有任何裝置回報錯誤。"))
        return sorted(findings, key=lambda f: -f.severity)

    def _finding(self, d: dict, code: int, ctx: dict) -> Finding:
        rule = rule_for(code)
        pnp_id = d.get("PNPDeviceID") or ""
        name = d.get("Name") or "未知裝置"
        vendor = vendor_of(pnp_id)
        steps = list(rule.steps)
        actions = [OPEN_DEVMGMT]
        if rule.severity >= Severity.WARNING:
            # 主機板內建裝置（非獨立顯示卡）優先建議到主機板官網找驅動
            board = board_support(ctx) if pnp_id.upper().startswith(("PCI", "ACPI", "HDAUDIO")) \
                and vendor not in ("NVIDIA",) else None
            if board:
                steps = [s for s in steps if s != UPDATE_DRIVER]  # 已有更具體的主機板建議
                steps.insert(0, board[0])
                if board[1]:
                    actions.append(board[1])
            if vendor in VENDOR_HINTS and not (board and vendor == "Realtek"):
                hint, action = VENDOR_HINTS[vendor]
                steps.insert(1 if board else 0, hint)
                if action:
                    actions.append(action)

        info = [f"裝置名稱：{name}"]
        if d.get("PNPClass"):
            info.append(f"類別：{d['PNPClass']}")
        if vendor or d.get("Manufacturer"):
            info.append(f"製造商：{vendor or d['Manufacturer']}")
        info += [f"錯誤碼：{code}", f"硬體識別碼：{pnp_id}"]

        return Finding(
            id=f"devices:{pnp_id}:{code}", severity=rule.severity,
            title=f"{name}：{rule.title}", detail="\n".join(info),
            cause=rule.cause, steps=steps, actions=actions)
