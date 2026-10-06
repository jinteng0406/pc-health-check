"""Windows 更新與安全性：多久沒更新、更新失敗、等待重新啟動、防毒軟體狀態。"""
from __future__ import annotations

import re
from datetime import datetime

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .security_ps import PS_SCRIPT

OPEN_WU = Action("開啟 Windows Update", "ms-settings:windowsupdate")
OPEN_WU_HISTORY = Action("更新紀錄", "ms-settings:windowsupdate-history")
OPEN_SECURITY = Action("開啟 Windows 安全性", "windowsdefender:")

DEFENDER_KB = "KB2267602"  # Defender 病毒碼，幾乎每天更新，不代表 Windows 本身有更新
_KB = re.compile(r"KB\d{6,}", re.IGNORECASE)
UPDATE_OLD_DAYS = 40  # 每月第二個星期二發佈，超過 40 天代表至少漏掉一次
SIGNATURE_OLD_DAYS = 7
FAILED, ABORTED, SUCCEEDED, SUCCEEDED_WITH_ERRORS = 4, 5, 2, 3


def _date(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def is_windows_update(title: str) -> bool:
    """有 KB 編號、且不是 Defender 病毒碼的才算 Windows 本身的更新（排除 Store 應用程式更新）。"""
    return bool(_KB.search(title or "")) and DEFENDER_KB not in (title or "").upper()


def av_enabled(state: int) -> bool:
    return ((state >> 8) & 0xFF) in (0x10, 0x11)


class SecurityCheck(Check):
    id = "security"
    title = "Windows 更新與安全性"

    def collect(self) -> dict:
        return run_ps_json(PS_SCRIPT)[0]

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        now = _date(raw.get("Now")) or datetime.now()
        out = self._updates(raw, now) + self._antivirus(raw, now)
        return sorted(out, key=lambda f: -f.severity)

    def _updates(self, raw: dict, now: datetime) -> list[Finding]:
        history = [h for h in raw.get("History") or [] if is_windows_update(h.get("Title"))]
        ok = [h for h in history if h.get("Result") in (SUCCEEDED, SUCCEEDED_WITH_ERRORS)]
        out = []
        last = max((_date(h["Date"]) for h in ok if _date(h.get("Date"))), default=None)

        if last is None and raw.get("History") is not None and not history:
            out.append(Finding("security:no-history", Severity.INFO, "讀不到 Windows 更新紀錄",
                               cause="可能是更新紀錄被清除，或更新服務沒有回應。",
                               steps=["打開 Windows Update 手動檢查一次更新。"], actions=[OPEN_WU]))
        elif last and (now - last).days >= UPDATE_OLD_DAYS:
            out.append(Finding(
                "security:update-old", Severity.WARNING, f"Windows 已經 {(now - last).days} 天沒有安裝系統更新",
                detail=f"最後一次成功安裝系統更新：{last:%Y-%m-%d}",
                cause="微軟每個月都會發佈安全性更新。太久沒更新，電腦會暴露在已知的安全漏洞下。",
                steps=["打開 Windows Update，按「檢查更新」並安裝。",
                       "如果曾經「暫停更新」，記得恢復。"], actions=[OPEN_WU]))

        # 失敗後沒有再成功安裝的更新
        succeeded_titles = {h["Title"] for h in ok}
        failed = {}
        for h in history:
            d = _date(h.get("Date"))
            if h.get("Result") in (FAILED, ABORTED) and d and (now - d).days <= 30 \
                    and h["Title"] not in succeeded_titles:
                failed.setdefault(h["Title"], h)
        if failed:
            lines = [f"・{t}（錯誤碼 {h.get('HResult')}）" for t, h in failed.items()]
            out.append(Finding(
                "security:update-failed", Severity.WARNING, f"有 {len(failed)} 個更新安裝失敗",
                detail="\n".join(lines),
                cause="更新下載或安裝失敗，之後也沒有安裝成功。常見原因是磁碟空間不足、更新暫存檔損毀或網路中斷。",
                steps=["確認 C: 槽有足夠空間（至少 20 GB）。",
                       "到「設定 → 系統 → 疑難排解 → 其他疑難排解員」執行「Windows Update」疑難排解員。",
                       "仍失敗時，以系統管理員身分開啟命令提示字元，依序執行：\n"
                       "DISM /Online /Cleanup-Image /RestoreHealth\nsfc /scannow\n完成後重新開機再更新。",
                       "可以用錯誤碼搜尋微軟的說明。"],
                actions=[OPEN_WU_HISTORY, OPEN_WU]))

        if raw.get("RebootPending"):
            out.append(Finding(
                "security:reboot-pending", Severity.INFO, "有更新正在等待重新啟動",
                cause="更新已經下載安裝，但要重新啟動電腦才會完成。", steps=["找時間從開始選單選「重新啟動」。"],
                actions=[OPEN_WU]))

        if not out and last:
            out.append(Finding("security:updates-ok", Severity.OK, f"Windows 更新正常（最近一次 {last:%Y-%m-%d}）"))
        return out

    def _antivirus(self, raw: dict, now: datetime) -> list[Finding]:
        d = raw.get("Defender")
        others = [a for a in raw.get("Antivirus") or []
                  if "defender" not in (a.get("Name") or "").lower() and av_enabled(a.get("State") or 0)]
        defender_on = bool(d and d.get("AntivirusEnabled") and d.get("RealTimeProtectionEnabled")
                           and "passive" not in (d.get("AMRunningMode") or "").lower())

        if others and not defender_on:
            names = "、".join(a["Name"] for a in others)
            return [Finding("security:av-ok", Severity.OK, f"防毒保護正常（{names}）",
                            detail="Windows Defender 已讓位給其他防毒軟體，這是正常的。")]
        if not defender_on:
            return [Finding(
                "security:av-off", Severity.CRITICAL, "即時防毒保護沒有開啟",
                detail="Windows Defender 的即時保護是關閉的，也沒有偵測到其他防毒軟體。" if d else
                       "讀不到 Windows Defender 的狀態，也沒有偵測到其他防毒軟體。",
                cause="沒有即時防毒保護時，下載或開啟的惡意程式不會被攔截。",
                steps=["打開「Windows 安全性 → 病毒與威脅防護」，開啟「即時保護」。",
                       "如果之前裝過其他防毒軟體又移除了，Defender 有時不會自動恢復，重新開機後再確認一次。"],
                actions=[OPEN_SECURITY])]

        sig = _date(d.get("SignatureLastUpdated"))
        if sig and (now - sig).days >= SIGNATURE_OLD_DAYS:
            return [Finding(
                "security:signature-old", Severity.WARNING, f"病毒碼已經 {(now - sig).days} 天沒有更新",
                detail=f"最後更新：{sig:%Y-%m-%d}",
                cause="病毒碼太舊時，新出現的惡意程式可能偵測不到。通常每天會自動更新好幾次。",
                steps=["打開「Windows 安全性 → 病毒與威脅防護 → 保護更新」，按「檢查更新」。"],
                actions=[OPEN_SECURITY])]
        return [Finding("security:av-ok", Severity.OK, "Windows Defender 即時保護正常",
                        detail=f"病毒碼最後更新：{sig:%Y-%m-%d %H:%M}" if sig else "")]
