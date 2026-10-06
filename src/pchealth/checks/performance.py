"""開機啟動項與效能：開機自動執行的程式、記憶體使用率、電源計畫。"""
from __future__ import annotations

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .performance_ps import PS_SCRIPT

OPEN_STARTUP_APPS = Action("開啟啟動應用程式設定", "ms-settings:startupapps")
OPEN_TASKMGR = Action("開啟工作管理員", "taskmgr.exe")
OPEN_POWER = Action("開啟電源選項", "powercfg.cpl")

STARTUP_MANY = 12
MEMORY_HIGH = 90  # %

POWER_SCHEMES = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "平衡",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "高效能",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "省電",
    "e9a42b02-d5df-448d-aa00-03f14749eb61": "極致效能",
}
POWER_SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"


class PerformanceCheck(Check):
    id = "performance"
    title = "開機與效能"

    def collect(self) -> dict:
        return run_ps_json(PS_SCRIPT)[0]

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        out = [self._startup(raw), self._memory(raw)]
        if power := self._power(raw):
            out.append(power)
        return sorted([f for f in out if f], key=lambda f: -f.severity)

    def _startup(self, raw: dict) -> Finding:
        enabled = [s for s in raw.get("Startup") or [] if s.get("Enabled", True)]
        names = sorted({s.get("Name") or "?" for s in enabled}, key=str.lower)
        detail = "開機時會自動執行：\n" + "\n".join(f"・{n}" for n in names) if names else "沒有開機自動執行的程式。"
        if len(names) > STARTUP_MANY:
            return Finding(
                "performance:startup-many", Severity.INFO, f"有 {len(names)} 個程式在開機時自動執行",
                detail=detail,
                cause="開機自動執行的程式越多，開機越慢，也會一直佔用記憶體與 CPU。很多程式（遊戲平台、"
                      "聊天軟體、更新程式）其實不需要開機就啟動。",
                steps=["打開「設定 → 應用程式 → 啟動」，把不需要一開機就執行的程式關掉。",
                       "防毒軟體、音效／觸控板驅動相關的項目建議保留。"],
                actions=[OPEN_STARTUP_APPS, OPEN_TASKMGR])
        return Finding("performance:startup-ok", Severity.OK, f"開機自動執行 {len(names)} 個程式", detail=detail)

    def _memory(self, raw: dict) -> Finding | None:
        total, free = raw.get("TotalMemoryKB") or 0, raw.get("FreeMemoryKB") or 0
        if not total:
            return None
        pct = (total - free) / total * 100
        top = raw.get("TopProcesses") or []
        detail = (f"記憶體使用：{(total - free) / 1024**2:.1f} / {total / 1024**2:.1f} GB（{pct:.0f}%）\n"
                  "目前最佔記憶體的程式：\n" + "\n".join(f"・{p['Name']}：{p['MB']:,} MB" for p in top))
        if pct >= MEMORY_HIGH:
            return Finding(
                "performance:memory-high", Severity.WARNING, f"記憶體使用率偏高（{pct:.0f}%）", detail=detail,
                cause="記憶體快用完時，Windows 會把資料搬到硬碟上，電腦會明顯變慢、遊戲會卡頓。"
                      "這是檢查當下的狀況，跟你目前開了哪些程式有關。",
                steps=["關掉不需要的程式與瀏覽器分頁（瀏覽器分頁很吃記憶體）。",
                       "如果平常就常常超過 90%，代表記憶體容量不夠用，可以考慮加裝。"],
                actions=[OPEN_TASKMGR])
        return Finding("performance:memory-ok", Severity.OK, f"記憶體使用 {pct:.0f}%", detail=detail)

    def _power(self, raw: dict) -> Finding | None:
        scheme = (raw.get("PowerScheme") or "").lower()
        if scheme == POWER_SAVER:
            return Finding(
                "performance:power-saver", Severity.INFO, "電源計畫是「省電」模式",
                detail="目前電源計畫：省電",
                cause="省電模式會限制 CPU 效能，桌上型電腦通常不需要。遊戲或大型程式會變慢。",
                steps=["打開「控制台 → 電源選項」，改成「平衡」（建議）或「高效能」。"],
                actions=[OPEN_POWER])
        if name := POWER_SCHEMES.get(scheme) or raw.get("PowerSchemeName"):
            custom = scheme not in POWER_SCHEMES
            return Finding("performance:power-ok", Severity.OK, f"電源計畫：{name}" + ("（自訂）" if custom else ""),
                           detail="這是主機板工具或你自己建立的電源計畫。" if custom else "")
        return None
