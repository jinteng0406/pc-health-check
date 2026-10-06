"""硬碟健康與容量。

資料來源有兩個，整理成同一份 Health 後再套規則：
- Windows 內建（Get-PhysicalDisk / Get-StorageReliabilityCounter）：一定有，但常缺錯誤次數
- smartctl：較完整（媒體錯誤、嚴重警告、備用區、重新配置磁區…），有就優先使用
"""
from __future__ import annotations

from dataclasses import dataclass

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from . import smart
from .base import Check
from .storage_ps import PS_SCRIPT

OPEN_STORAGE_SETTINGS = Action("開啟儲存體設定", "ms-settings:storagesense")
OPEN_CLEANMGR = Action("磁碟清理", "cleanmgr.exe")
OPEN_DISKMGMT = Action("開啟磁碟管理", "diskmgmt.msc")

BACKUP_NOW = "立刻把重要資料（照片、文件、遊戲存檔）備份到另一顆硬碟或雲端。"

# (注意, 問題) 溫度門檻 °C；這是檢查當下的溫度，高負載時偏高是正常的
TEMP_LIMITS = {"NVMe": (70, 80), "SSD": (65, 75), "HDD": (50, 60)}

# NVMe Critical Warning 位元
CRITICAL_WARNING_BITS = {
    0x01: "備用區（用來替換壞掉區塊的保留空間）低於安全門檻",
    0x02: "溫度超過硬碟的安全範圍",
    0x04: "硬碟可靠度下降（發生了嚴重的內部錯誤）",
    0x08: "硬碟已進入唯讀模式，無法再寫入資料",
    0x10: "斷電保護電路故障",
}

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


@dataclass
class Health:
    """一顆硬碟的健康數據；None 代表「讀不到」，不是 0。"""
    source: str | None = None  # "smartctl" / "Windows" / None
    temperature: int | None = None
    wear: int | None = None
    power_on_hours: int | None = None
    media_errors: int | None = None  # 無法修復的讀寫錯誤
    reallocated: int | None = None  # ATA：已重新配置的磁區
    pending: int | None = None  # ATA：等待重新配置（目前讀不出來）的磁區
    critical_warning: int | None = None  # NVMe
    spare: int | None = None  # NVMe 備用區剩餘 %
    spare_threshold: int | None = None
    smart_passed: bool | None = None
    unsafe_shutdowns: int | None = None


def from_windows(r: dict | None) -> Health:
    if not r:
        return Health()
    errs = [r.get("ReadErrorsUncorrected"), r.get("WriteErrorsUncorrected")]
    return Health(source="Windows", temperature=r.get("Temperature") or None, wear=r.get("Wear"),
                  power_on_hours=r.get("PowerOnHours"),
                  media_errors=None if all(e is None for e in errs) else sum(e or 0 for e in errs))


def from_smartctl(j: dict | None) -> Health:
    if not j:
        return Health()
    h = Health(source="smartctl",
               temperature=(j.get("temperature") or {}).get("current"),
               power_on_hours=(j.get("power_on_time") or {}).get("hours"),
               smart_passed=(j.get("smart_status") or {}).get("passed"))
    if log := j.get("nvme_smart_health_information_log"):
        h.temperature = h.temperature or log.get("temperature")
        h.wear = log.get("percentage_used")
        h.power_on_hours = h.power_on_hours if h.power_on_hours is not None else log.get("power_on_hours")
        h.media_errors = log.get("media_errors")
        h.critical_warning = log.get("critical_warning")
        h.spare = log.get("available_spare")
        h.spare_threshold = log.get("available_spare_threshold")
        h.unsafe_shutdowns = log.get("unsafe_shutdowns")
    if table := (j.get("ata_smart_attributes") or {}).get("table"):
        raw = {a.get("id"): (a.get("raw") or {}).get("value") for a in table}
        h.reallocated = raw.get(5)
        h.pending = raw.get(197)
        uncorrect = [v for v in (raw.get(187), raw.get(198)) if v is not None]
        h.media_errors = max(uncorrect) if uncorrect else None
        if (pct := (j.get("endurance_used") or {}).get("current_percent")) is not None:
            h.wear = pct
    return h


def merge(primary: Health, fallback: Health) -> Health:
    """smartctl 優先，缺的欄位用 Windows 的補。"""
    if primary.source is None:
        return fallback
    merged = Health(**vars(primary))
    for k, v in vars(fallback).items():
        if getattr(merged, k) is None:
            setattr(merged, k, v)
    return merged


class StorageCheck(Check):
    id = "storage"
    title = "硬碟健康與容量"

    def collect(self) -> dict:
        raw = run_ps_json(PS_SCRIPT)[0]
        raw["Smart"] = smart.collect(raw.get("Disks") or [], bool(raw.get("Admin")))
        return raw

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        admin = bool(raw.get("Admin"))
        smart_info = raw.get("Smart") or {}
        findings = []
        for d in raw.get("Disks") or []:
            sj = (smart_info.get("disks") or {}).get(str(d.get("DeviceId")))
            health = merge(from_smartctl(sj), from_windows(d.get("Reliability")))
            findings += self._disk(d, health, admin, smart_info.get("status"))
        for v in raw.get("Volumes") or []:
            findings += self._volume(v)
        return sorted(findings, key=lambda f: -f.severity)

    # ---- 實體硬碟 ----
    def _disk(self, d: dict, h: Health, admin: bool, smart_status: str | None) -> list[Finding]:
        name = d.get("FriendlyName") or f"硬碟 {d.get('DeviceId')}"
        key = f"storage:disk:{name}:{d.get('DeviceId')}"
        kind = disk_kind(d)
        tool = vendor_tool(name)
        tool_actions = [tool] if tool else []
        detail = self._detail(d, h, kind, name)
        out: list[Finding] = []

        def add(suffix, sev, title, cause, steps, actions=()):
            out.append(Finding(f"{key}:{suffix}", sev, f"{name}：{title}", detail=detail,
                               cause=cause, steps=list(steps), actions=list(actions)))

        health, op = d.get("HealthStatus"), d.get("OperationalStatus") or ""
        if health == "Unhealthy" or "Predictive Failure" in op or "Failed" in op or h.smart_passed is False:
            add("health", Severity.CRITICAL, "硬碟自我檢測回報即將故障",
                "硬碟的 SMART 自我檢測判定狀態不合格，隨時可能無法讀取，資料有遺失風險。",
                [BACKUP_NOW, "備份完成後盡快更換這顆硬碟。", "若仍在保固期內，聯絡製造商申請保固更換。"],
                [OPEN_DISKMGMT, *tool_actions])
        elif health == "Warning" or (op and op != "OK"):
            add("health", Severity.WARNING, "Windows 回報健康警告",
                f"Windows 回報的狀態是「{health}／{op}」，代表硬碟出現需要留意的狀況。",
                [BACKUP_NOW, "使用製造商的工具檢查詳細健康資訊並更新韌體。"], [OPEN_DISKMGMT, *tool_actions])

        if h.source is None:
            if not admin:
                cause, steps = "讀取硬碟磨損、溫度、錯誤次數需要系統管理員權限。", ["關閉程式後重新開啟，在 UAC 視窗按「是」。"]
            else:
                cause = ("這顆硬碟沒有提供健康細節。常見原因是接在 USB 外接盒或 RAID 控制器上，或硬碟本身不支援。"
                         "上方的 Windows 健康狀態仍然有效。")
                steps = ["可以改用製造商的工具查看完整健康資訊。"]
            add("no-detail", Severity.INFO, "無法讀取健康細節", cause, steps, tool_actions)
            return out

        if h.critical_warning:
            bits = [text for bit, text in CRITICAL_WARNING_BITS.items() if h.critical_warning & bit]
            only_temp = h.critical_warning == 0x02
            add("critical-warning", Severity.WARNING if only_temp else Severity.CRITICAL,
                "硬碟發出嚴重警告", "硬碟自己回報了以下狀況：" + "；".join(bits) + "。",
                (["確認機殼通風與 M.2 散熱片，閒置後再檢查一次。"] if only_temp
                 else [BACKUP_NOW, "盡快更換這顆硬碟。"]), tool_actions)

        if h.spare is not None and h.spare_threshold is not None and h.spare < max(h.spare_threshold, 20):
            sev = Severity.CRITICAL if h.spare <= h.spare_threshold else Severity.WARNING
            add("spare", sev, f"備用區只剩 {h.spare}%",
                "SSD 會用備用區替換損壞的區塊。備用區快用完時，代表已經有大量區塊損壞，硬碟接近壽命終點。",
                [BACKUP_NOW, "規劃更換這顆 SSD。"], tool_actions)

        if h.media_errors:
            add("errors", Severity.CRITICAL, f"發生 {h.media_errors} 次無法修復的讀寫錯誤",
                "硬碟曾經有資料讀不出來或寫不進去，而且無法自動修正。這通常是硬碟開始損壞的徵兆，次數增加就代表情況惡化。",
                [BACKUP_NOW, "下次檢查時留意這個數字是否繼續增加；若增加，請盡快更換硬碟。",
                 "使用製造商工具更新韌體並執行完整檢測。"], [*tool_actions, OPEN_DISKMGMT])

        if h.pending:
            add("pending", Severity.CRITICAL, f"有 {h.pending} 個磁區目前讀不出來",
                "這些磁區的資料已經讀不到，硬碟正在等待把它們換掉。存在這些磁區上的檔案可能已經損毀。",
                [BACKUP_NOW, "盡快更換這顆硬碟。"], tool_actions)

        if h.reallocated:
            sev = Severity.CRITICAL if h.reallocated >= 100 else Severity.WARNING
            add("reallocated", sev, f"已有 {h.reallocated} 個壞軌被替換",
                "硬碟發現壞掉的磁區並用備用磁區替換了。少量是可以接受的，但數字持續增加代表硬碟正在劣化。",
                ["確認重要資料都有備份。", "下次檢查時比較這個數字；若持續增加，請規劃更換。"], tool_actions)

        if h.wear is not None and h.wear >= 80:
            sev = Severity.CRITICAL if h.wear >= 100 else Severity.WARNING
            add("wear", sev, f"已用掉 {h.wear}% 的額定寫入壽命",
                "SSD 的快閃記憶體能寫入的總量有上限。超過 100% 不代表馬上會壞，但已超出製造商保證的範圍，故障機率會明顯上升。",
                [BACKUP_NOW if sev == Severity.CRITICAL else "確認重要資料都有備份。", "開始規劃更換這顆 SSD。",
                 "避免把大量頻繁寫入的工作（例如錄影暫存、下載暫存）放在這顆上。"], tool_actions)

        temp = h.temperature or 0
        warn, crit = TEMP_LIMITS[kind]
        if temp >= warn:
            sev = Severity.CRITICAL if temp >= crit else Severity.WARNING
            add("temp", sev, f"溫度偏高（{temp}°C）",
                f"{kind} 硬碟長時間超過 {warn}°C 會降速保護，也會縮短壽命。"
                "這是檢查當下的溫度；如果剛才在大量讀寫（例如安裝遊戲），偏高是正常的。",
                ["在電腦閒置幾分鐘後再檢查一次，確認溫度是否回落。",
                 "確認機殼風扇運作正常、進出風口沒有被灰塵堵住。",
                 "M.2 SSD 可以加裝散熱片（很多主機板有附 M.2 散熱片，確認有沒有裝上、保護膜有沒有撕掉）。"
                 if kind == "NVMe" else "確認硬碟附近有氣流經過。"])

        if not out:
            summary = [f"磨損 {h.wear}%" if h.wear is not None else None,
                       f"{temp}°C" if temp else None,
                       f"通電 {h.power_on_hours:,} 小時" if h.power_on_hours is not None else None,
                       None if h.media_errors is not None else "錯誤次數未知"]
            cause = ""
            if h.media_errors is None:
                cause = ("目前只讀得到這顆硬碟的部分健康資訊，讀寫錯誤次數未知。"
                         + {"not_found": "找不到 smartctl 工具。",
                            "not_admin": "完整檢查需要管理員權限。"}.get(smart_status or "", ""))
            out.append(Finding(f"{key}:ok", Severity.OK, f"{name}：健康（{'、'.join(s for s in summary if s)}）",
                               detail=detail, cause=cause))
        return out

    @staticmethod
    def _detail(d: dict, h: Health, kind: str, name: str) -> str:
        info = [f"型號：{name}", f"類型：{kind}（{d.get('BusType')}）", f"容量：{gb(d.get('Size')):.0f} GB",
                f"Windows 健康狀態：{d.get('HealthStatus')}／{d.get('OperationalStatus')}"]
        if h.source is None:
            return "\n".join(info)
        info.append(f"資料來源：{h.source}")
        if h.smart_passed is not None:
            info.append(f"SMART 自我檢測：{'通過' if h.smart_passed else '未通過'}")
        if h.wear is not None:
            info.append(f"磨損程度：{h.wear}%（已用掉的額定寫入壽命）")
        if h.spare is not None:
            info.append(f"備用區剩餘：{h.spare}%（低於 {h.spare_threshold}% 為危險）")
        if h.temperature:
            info.append(f"目前溫度：{h.temperature}°C")
        if h.power_on_hours is not None:
            info.append(f"通電時數：{h.power_on_hours:,} 小時")
        info.append(f"無法修復的讀寫錯誤：{h.media_errors} 次" if h.media_errors is not None
                    else "無法修復的讀寫錯誤：讀不到（未知，不代表沒有）")
        if h.reallocated is not None:
            info.append(f"已替換的壞軌：{h.reallocated}")
        if h.pending is not None:
            info.append(f"等待替換的磁區：{h.pending}")
        if h.unsafe_shutdowns is not None:
            info.append(f"不正常斷電次數：{h.unsafe_shutdowns:,}")
        return "\n".join(info)

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
