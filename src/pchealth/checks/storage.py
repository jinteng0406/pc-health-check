"""硬碟健康與容量：使用 Windows 內建的 Storage 模組（Get-PhysicalDisk / Get-StorageReliabilityCounter）。"""
from __future__ import annotations

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .storage_ps import PS_SCRIPT

OPEN_STORAGE_SETTINGS = Action("開啟儲存體設定", "ms-settings:storagesense")
OPEN_CLEANMGR = Action("磁碟清理", "cleanmgr.exe")
OPEN_DISKMGMT = Action("開啟磁碟管理", "diskmgmt.msc")

BACKUP_NOW = "立刻把重要資料（照片、文件、遊戲存檔）備份到另一顆硬碟或雲端。"

# (注意, 問題) 溫度門檻 °C；這是檢查當下的溫度，高負載時偏高是正常的
TEMP_LIMITS = {"NVMe": (70, 80), "SSD": (65, 75), "HDD": (50, 60)}

VENDOR_TOOLS = [  # (型號開頭／關鍵字, 工具)
    (("CT", "CRUCIAL", "MICRON"), Action("Crucial Storage Executive", "https://www.crucial.com/support/storage-executive")),
    (("SAMSUNG",), Action("Samsung Magician", "https://semiconductor.samsung.com/consumer-storage/support/tools/")),
]


def gb(n: int | float | None) -> float:
    return (n or 0) / 1024**3


def vendor_tool(name: str) -> Action | None:
    upper = (name or "").upper()
    for keys, action in VENDOR_TOOLS:
        if any(upper.startswith(k) if k == "CT" else k in upper for k in keys):
            return action
    return None


def disk_kind(d: dict) -> str:
    if d.get("BusType") == "NVMe":
        return "NVMe"
    return "SSD" if d.get("MediaType") == "SSD" else "HDD"


class StorageCheck(Check):
    id = "storage"
    title = "硬碟健康與容量"

    def collect(self) -> dict:
        return run_ps_json(PS_SCRIPT)[0]

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        admin = bool(raw.get("Admin"))
        findings = []
        for d in raw.get("Disks") or []:
            findings += self._disk(d, admin)
        for v in raw.get("Volumes") or []:
            findings += self._volume(v)
        return sorted(findings, key=lambda f: -f.severity)

    # ---- 實體硬碟 ----
    def _disk(self, d: dict, admin: bool) -> list[Finding]:
        name = d.get("FriendlyName") or f"硬碟 {d.get('DeviceId')}"
        key = f"storage:disk:{name}:{d.get('DeviceId')}"
        kind = disk_kind(d)
        tool = vendor_tool(name)
        tool_actions = [tool] if tool else []
        r = d.get("Reliability")
        info = [f"型號：{name}", f"類型：{kind}（{d.get('BusType')}）", f"容量：{gb(d.get('Size')):.0f} GB",
                f"Windows 健康狀態：{d.get('HealthStatus')}／{d.get('OperationalStatus')}"]
        if r:
            if r.get("Wear") is not None:
                info.append(f"磨損程度：{r['Wear']}%（已用掉的額定寫入壽命）")
            if r.get("Temperature"):
                info.append(f"目前溫度：{r['Temperature']}°C" + (f"（最高紀錄 {r['TemperatureMax']}°C）" if r.get("TemperatureMax") else ""))
            if r.get("PowerOnHours") is not None:
                info.append(f"通電時數：{r['PowerOnHours']:,} 小時")
        detail = "\n".join(info)
        out: list[Finding] = []

        health, op = d.get("HealthStatus"), d.get("OperationalStatus") or ""
        if health == "Unhealthy" or "Predictive Failure" in op or "Failed" in op:
            out.append(Finding(
                f"{key}:health", Severity.CRITICAL, f"{name}：Windows 判定這顆硬碟即將故障",
                detail=detail, cause="硬碟自我檢測回報了嚴重錯誤，隨時可能無法讀取，資料有遺失風險。",
                steps=[BACKUP_NOW, "備份完成後盡快更換這顆硬碟。", "若仍在保固期內，聯絡製造商申請保固更換。"],
                actions=[OPEN_DISKMGMT, *tool_actions]))
        elif health == "Warning" or (op and op != "OK"):
            out.append(Finding(
                f"{key}:health", Severity.WARNING, f"{name}：Windows 回報健康警告",
                detail=detail, cause=f"Windows 回報的狀態是「{health}／{op}」，代表硬碟出現需要留意的狀況。",
                steps=[BACKUP_NOW, "使用製造商的工具檢查詳細健康資訊並更新韌體。"],
                actions=[OPEN_DISKMGMT, *tool_actions]))

        if not r:
            if admin:
                cause = ("這顆硬碟沒有透過 Windows 提供健康細節。常見原因是接在 USB 外接盒、RAID／Intel VMD 控制器上，"
                         "或硬碟本身不支援。上方的 Windows 健康狀態仍然有效。")
                steps = ["可以改用製造商的工具查看完整健康資訊。"]
            else:
                cause = "讀取硬碟磨損、溫度、錯誤次數需要系統管理員權限。"
                steps = ["關閉程式後重新開啟，在 UAC 視窗按「是」。"]
            out.append(Finding(f"{key}:no-detail", Severity.INFO, f"{name}：無法讀取健康細節",
                               detail=detail, cause=cause, steps=steps, actions=tool_actions))
            return out

        errors = (r.get("ReadErrorsUncorrected") or 0) + (r.get("WriteErrorsUncorrected") or 0)
        if errors > 0:
            out.append(Finding(
                f"{key}:errors", Severity.CRITICAL, f"{name}：發生 {errors} 次無法修復的讀寫錯誤",
                detail=detail, cause="硬碟曾經有資料讀不出來或寫不進去，而且無法自動修正。"
                                     "這通常是硬碟開始損壞的徵兆，次數增加就代表情況惡化。",
                steps=[BACKUP_NOW, "下次檢查時留意這個數字是否繼續增加；若增加，請盡快更換硬碟。",
                       "使用製造商工具更新韌體並執行完整檢測。"],
                actions=[*tool_actions, OPEN_DISKMGMT]))

        wear = r.get("Wear")
        if wear is not None and wear >= 80:
            sev = Severity.CRITICAL if wear >= 100 else Severity.WARNING
            out.append(Finding(
                f"{key}:wear", sev, f"{name}：已用掉 {wear}% 的額定寫入壽命",
                detail=detail, cause="SSD 的快閃記憶體能寫入的總量有上限。超過 100% 不代表馬上會壞，"
                                     "但已超出製造商保證的範圍，故障機率會明顯上升。",
                steps=[BACKUP_NOW if sev == Severity.CRITICAL else "確認重要資料都有備份。",
                       "開始規劃更換這顆 SSD。",
                       "避免把大量頻繁寫入的工作（例如錄影暫存、下載暫存）放在這顆上。"],
                actions=tool_actions))

        temp = r.get("Temperature") or 0
        warn, crit = TEMP_LIMITS[kind]
        if temp >= warn:
            sev = Severity.CRITICAL if temp >= crit else Severity.WARNING
            out.append(Finding(
                f"{key}:temp", sev, f"{name}：溫度偏高（{temp}°C）",
                detail=detail, cause=f"{kind} 硬碟長時間超過 {warn}°C 會降速保護，也會縮短壽命。"
                                     "這是檢查當下的溫度；如果剛才在大量讀寫（例如安裝遊戲），偏高是正常的。",
                steps=["在電腦閒置幾分鐘後再檢查一次，確認溫度是否回落。",
                       "確認機殼風扇運作正常、進出風口沒有被灰塵堵住。",
                       "M.2 SSD 可以加裝散熱片（很多主機板有附 M.2 散熱片，確認有沒有裝上、保護膜有沒有撕掉）。"
                       if kind == "NVMe" else "確認硬碟附近有氣流經過。"]))

        if not out:
            summary = [f"磨損 {wear}%" if wear is not None else None,
                       f"{temp}°C" if temp else None,
                       f"通電 {r['PowerOnHours']:,} 小時" if r.get("PowerOnHours") is not None else None]
            out.append(Finding(f"{key}:ok", Severity.OK,
                               f"{name}：健康（{'、'.join(s for s in summary if s)}）", detail=detail))
        return out

    # ---- 磁碟區（C:、D: …）----
    def _volume(self, v: dict) -> list[Finding]:
        size, free = v.get("Size") or 0, v.get("SizeRemaining") or 0
        if size < 1024**3:  # 忽略小於 1 GB 的分割區
            return []
        letter = v.get("DriveLetter")
        pct = free / size * 100
        label = f"{letter}: 槽" + (f"（{v['Label']}）" if v.get("Label") else "")
        detail = f"總容量 {gb(size):.0f} GB，剩餘 {gb(free):.1f} GB（{pct:.0f}%）"
        key = f"storage:volume:{letter}"
        out = []

        if pct < 5 or gb(free) < 5:
            sev = Severity.CRITICAL
        elif pct < 10 or gb(free) < 15:
            sev = Severity.WARNING
        else:
            sev = None
        if sev:
            is_c = letter == "C"
            out.append(Finding(
                f"{key}:space", sev, f"{label} 空間不足：只剩 {gb(free):.1f} GB",
                detail=detail,
                cause=("系統磁碟空間不足會讓 Windows 更新失敗、程式變慢甚至無法開啟，虛擬記憶體也需要空間。"
                       if is_c else "空間不足會讓遊戲更新、下載失敗，SSD 太滿時效能和壽命也會下降。"),
                steps=["用「儲存體設定」查看哪些類別佔最多空間，清除暫存檔與資源回收筒。",
                       "解除安裝不再玩的遊戲或不用的程式。",
                       "執行「磁碟清理」→「清理系統檔」，可以刪除舊的 Windows 更新檔。" if is_c
                       else "把大型檔案（影片、遊戲安裝檔）移到其他硬碟。"],
                actions=[OPEN_STORAGE_SETTINGS, OPEN_CLEANMGR]))

        if v.get("HealthStatus") not in (None, "", "Healthy"):
            out.append(Finding(
                f"{key}:health", Severity.WARNING, f"{label} 的檔案系統需要修復",
                detail=f"{detail}\n健康狀態：{v.get('HealthStatus')}",
                cause="Windows 偵測到這個磁碟區的檔案系統有錯誤，常見於突然斷電或強制關機之後。",
                steps=[f"開啟檔案總管，對 {letter}: 按右鍵 → 內容 → 工具 →「檢查」，讓 Windows 掃描並修復。",
                       "如果是 C: 槽，可能需要重新開機後才會執行修復。"]))

        if not out:
            out.append(Finding(f"{key}:ok", Severity.OK, f"{label}：剩餘 {gb(free):.0f} GB（{pct:.0f}%）",
                               detail=detail))
        return out
