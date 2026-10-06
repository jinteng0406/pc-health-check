"""這台電腦總覽：硬體規格、顯示卡驅動新舊、連續開機時間、BIOS 年份。"""
from __future__ import annotations

from datetime import datetime

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .boards import brand_of
from .system_ps import PS_SCRIPT

NVIDIA_DRIVERS = Action("NVIDIA 驅動下載", "https://www.nvidia.com/Download/index.aspx")
AMD_DRIVERS = Action("AMD 驅動下載", "https://www.amd.com/en/support/download/drivers.html")
OPEN_WINDOWS_UPDATE = Action("開啟 Windows Update", "ms-settings:windowsupdate")

GPU_DRIVER_OLD_DAYS = 180
UPTIME_LONG_DAYS = 14
BIOS_OLD_YEARS = 3


def nvidia_version(driver_version: str) -> str | None:
    """Windows 驅動版本 32.0.15.6094 → NVIDIA 版本 560.94。"""
    parts = (driver_version or "").split(".")
    if len(parts) != 4:
        return None
    digits = (parts[2] + parts[3])[-5:]
    return f"{digits[:3]}.{digits[3:]}" if len(digits) == 5 and digits.isdigit() else None


def _date(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def _is_real_gpu(name: str) -> bool:
    n = name.upper()
    return ("NVIDIA" in n or "AMD" in n or "RADEON" in n or "INTEL" in n) and "VIRTUAL" not in n


class SystemCheck(Check):
    id = "system"
    title = "這台電腦"

    def collect(self) -> dict:
        return run_ps_json(PS_SCRIPT)[0]

    def context(self, raw: dict) -> dict:
        brand, url = brand_of(raw.get("BoardManufacturer"))
        product = raw.get("BoardProduct") or ""
        now = _date(raw.get("Now")) or datetime.now()
        driver_ages = [(now - d).days for g in raw.get("Gpus") or []
                       if _is_real_gpu(g.get("Name") or "") and (d := _date(g.get("DriverDate")))]
        return {"board": f"{brand} {product}".strip() or None, "board_brand": brand,
                "board_support_url": url, "gpu_driver_days": max(driver_ages, default=None)}

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        now = _date(raw.get("Now")) or datetime.now()
        board = self.context(raw)["board"] or "未知"
        gpus = [g for g in raw.get("Gpus") or [] if _is_real_gpu(g.get("Name") or "")]
        mem_gb = (raw.get("MemoryBytes") or 0) / 1024**3

        lines = [f"主機板：{board}",
                 f"BIOS：{raw.get('BiosVersion') or '?'}（{raw.get('BiosDate') or '日期不明'}）",
                 f"處理器：{raw.get('Cpu') or '?'}",
                 f"記憶體：{mem_gb:.0f} GB"]
        for g in gpus:
            ver = nvidia_version(g.get("DriverVersion") or "") if "NVIDIA" in g["Name"].upper() else None
            lines.append(f"顯示卡：{g['Name']}（驅動 {ver or g.get('DriverVersion')}，{g.get('DriverDate') or '日期不明'}）")
        lines.append(f"作業系統：{raw.get('OsCaption') or '?'}（組建 {raw.get('OsBuild') or '?'}）")

        findings = [Finding("system:overview", Severity.OK, f"{board}・{mem_gb:.0f} GB 記憶體",
                            detail="\n".join(lines))]
        findings += self._gpu_driver_age(gpus, now)
        findings += self._uptime(raw, now)
        findings += self._bios_age(raw, now, ctx | self.context(raw))
        return findings

    def _gpu_driver_age(self, gpus: list[dict], now: datetime) -> list[Finding]:
        out = []
        for g in gpus:
            date = _date(g.get("DriverDate"))
            if not date or (now - date).days < GPU_DRIVER_OLD_DAYS:
                continue
            months = (now - date).days // 30
            name = g["Name"]
            is_nvidia = "NVIDIA" in name.upper()
            out.append(Finding(
                f"system:gpu-driver-old:{name}", Severity.INFO,
                f"{name} 的驅動已約 {months} 個月沒有更新",
                detail=f"目前驅動日期：{g.get('DriverDate')}",
                cause="新版顯示卡驅動通常會修正錯誤、改善新遊戲的效能與相容性。驅動舊不代表有問題，"
                      "但遇到遊戲閃退、畫面異常時，更新驅動往往是第一步。",
                steps=["使用 NVIDIA App 檢查更新，或到 NVIDIA 官網依型號下載最新的 Game Ready 驅動。" if is_nvidia
                       else "到顯示卡製造商官網下載最新驅動。",
                       "安裝時選擇「自訂安裝 → 執行全新安裝」可以清掉舊設定，避免殘留問題。"],
                actions=[NVIDIA_DRIVERS if is_nvidia else AMD_DRIVERS]))
        return out

    def _uptime(self, raw: dict, now: datetime) -> list[Finding]:
        boot = _date(raw.get("LastBoot"))
        if not boot or (now - boot).days < UPTIME_LONG_DAYS:
            return []
        days = (now - boot).days
        return [Finding(
            "system:uptime-long", Severity.INFO, f"電腦已經 {days} 天沒有重新啟動",
            detail=f"上次啟動時間：{boot:%Y-%m-%d %H:%M}",
            cause="長時間沒有重新啟動，Windows 更新可能無法完成，記憶體也可能被慢慢佔滿而變慢。"
                  "注意：Windows 預設的「快速啟動」會讓「關機」不等於重新啟動，所以每天關機也可能出現這個提示。",
            steps=["從開始選單選「重新啟動」（不是關機再開機）。",
                   "如果想讓關機真正清空狀態：控制台 → 電源選項 → 選擇按下電源按鈕時的行為 → 取消勾選「開啟快速啟動」。"],
            actions=[OPEN_WINDOWS_UPDATE])]

    def _bios_age(self, raw: dict, now: datetime, ctx: dict) -> list[Finding]:
        date = _date(raw.get("BiosDate"))
        if not date or (now - date).days < BIOS_OLD_YEARS * 365:
            return []
        actions = [Action(f"{ctx['board_brand']} 支援頁", ctx["board_support_url"])] if ctx.get("board_support_url") else []
        return [Finding(
            "system:bios-old", Severity.INFO, f"BIOS 已經 {(now - date).days // 365} 年沒有更新",
            detail=f"BIOS 版本 {raw.get('BiosVersion')}，發佈日期 {raw.get('BiosDate')}",
            cause="主機板廠商會透過 BIOS 更新修補安全漏洞、改善穩定性與硬體相容性。"
                  "電腦運作正常時不一定要更新，但若遇到相容性問題或廠商發佈安全更新，就值得考慮。",
            steps=[f"到主機板官網搜尋「{ctx.get('board') or '你的主機板型號'}」，查看 BIOS 更新紀錄說明修正了什麼。",
                   "更新 BIOS 有風險：請依官方步驟、使用官方檔案，過程中絕對不可斷電或關機。"],
            actions=actions)]
