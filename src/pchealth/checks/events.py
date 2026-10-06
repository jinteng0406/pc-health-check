"""當機與錯誤紀錄：藍屏、突然斷電、強制關機、硬體錯誤（WHEA）、顯示卡驅動重置、硬碟錯誤、程式當掉。"""
from __future__ import annotations

from collections import Counter

from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from . import bugchecks
from .base import Check
from .events_ps import script

DAYS = 30
OPEN_EVENTVWR = Action("開啟事件檢視器", "eventvwr.msc")
OPEN_RELIABILITY = Action("開啟可靠性監視器", "perfmon.exe /rel")
MEMORY_DIAG = Action("Windows 記憶體診斷", "mdsched.exe")
APP_CRASH_MIN = 3  # 同一個程式當掉幾次以上才提醒


def _dates(events: list[dict]) -> str:
    times = sorted(e.get("Time", "")[:16].replace("T", " ") for e in events)
    shown = times[-5:]
    return "、".join(shown) + (f"（另有 {len(times) - 5} 次較早的紀錄）" if len(times) > 5 else "")


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def classify_kernel_power(ev: dict) -> str:
    """Kernel-Power 41（沒有正常關機）的可能原因。

    - bsod：藍屏
    - button：長按電源鍵
    - shutdown：關機途中斷電（SleepInProgress = 6 = PowerSystemShutdown）
    - sleep：進入睡眠／休眠途中（2～5），或斷電前曾進出睡眠（常見於睡眠後叫不醒、按了電源鍵）
    - power：其他（停電、拔插頭、電源供應器問題、完全當住）
    """
    data = ev.get("Data") or {}
    if (bugchecks.parse_code(data.get("BugcheckCode")) or 0) != 0:
        return "bsod"
    if str(data.get("LongPowerButtonPressDetected", "")).lower() == "true" or data.get("PowerButtonTimestamp") not in (None, "", "0"):
        return "button"
    state = _int(data.get("SleepInProgress"))
    if state == 6:
        return "shutdown"
    if 2 <= state <= 5 or _int(data.get("SystemSleepTransitionsToOn")) > 0:
        return "sleep"
    return "power"


RECORDED_NOTE = "（時間是下一次開機時記錄的，實際斷電發生在這之前）"


class EventsCheck(Check):
    id = "events"
    title = "當機與錯誤紀錄"

    def collect(self) -> dict:
        return run_ps_json(script(DAYS))[0]

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        days = raw.get("Days") or DAYS
        out: list[Finding] = []
        out += self._crashes(raw, days)
        out += self._hardware(raw, days)
        out += self._apps(raw, days, ctx)
        if not out:
            out.append(Finding("events:ok", Severity.OK, f"最近 {days} 天沒有當機或硬體錯誤紀錄",
                               detail="沒有藍屏、不正常關機、硬體錯誤、顯示卡驅動重置或硬碟錯誤事件。"))
        return sorted(out, key=lambda f: -f.severity)

    # ---- 藍屏、斷電、強制關機 ----
    def _crashes(self, raw: dict, days: int) -> list[Finding]:
        out = []
        kp = raw.get("KernelPower") or []
        groups = {"bsod": [], "button": [], "shutdown": [], "sleep": [], "power": []}
        for ev in kp:
            groups[classify_kernel_power(ev)].append(ev)

        # 藍屏：WER 1001 有完整代碼；若沒有，退而用 Kernel-Power 41 的代碼
        codes = Counter()
        bsod_events = raw.get("BugChecks") or []
        for ev in bsod_events:
            if (c := bugchecks.parse_code((ev.get("Data") or {}).get("param1"))) is not None:
                codes[c] += 1
        if not codes:
            for ev in groups["bsod"]:
                codes[bugchecks.parse_code((ev.get("Data") or {}).get("BugcheckCode"))] += 1
            bsod_events = groups["bsod"]
        if bsod_events:
            n = len(bsod_events)
            lines, steps = [], []
            for code, count in codes.most_common():
                name, cause, step = bugchecks.describe(code)
                lines.append(f"・{name}（0x{code:X}）× {count}：{cause}")
                if step not in steps:
                    steps.append(step)
            dumps = raw.get("Minidumps") or []
            detail = f"時間：{_dates(bsod_events)}\n錯誤代碼：\n" + "\n".join(lines)
            if dumps:
                detail += f"\n當機記錄檔：C:\\Windows\\Minidump 有 {len(dumps)} 個（可提供給技術人員分析）"
            out.append(Finding(
                "events:bsod", Severity.CRITICAL if n >= 3 else Severity.WARNING,
                f"最近 {days} 天發生 {n} 次藍屏", detail=detail,
                cause="藍屏是 Windows 遇到無法繼續執行的嚴重錯誤而強制停止。偶爾一次可能是意外，"
                      "反覆發生就代表驅動程式或硬體有問題。同一個錯誤代碼重複出現時，原因通常相同。",
                steps=steps + ["打開「可靠性監視器」可以看到每次當機前後還發生了什麼事（例如剛更新了某個驅動）。"],
                actions=[OPEN_RELIABILITY, OPEN_EVENTVWR]))

        if sleep := groups["sleep"]:
            n = len(sleep)
            lines = []
            for ev in sleep:
                d = ev.get("Data") or {}
                state, wakes = _int(d.get("SleepInProgress")), _int(d.get("SystemSleepTransitionsToOn"))
                when = ev.get("Time", "")[:16].replace("T", " ")
                lines.append(f"・{when}：" + ("正在進入睡眠或休眠時停止運作" if 2 <= state <= 5
                                              else f"斷電前電腦已從睡眠喚醒過 {wakes} 次"))
            out.append(Finding(
                "events:sleep-hang", Severity.WARNING if n >= 3 else Severity.INFO,
                f"最近 {days} 天有 {n} 次可能是睡眠後叫不醒而重開",
                detail="\n".join(lines) + "\n" + RECORDED_NOTE,
                cause="電腦在睡眠前後沒有正常關機。最常見的情況是：電腦睡著後螢幕叫不醒，只好按電源鍵或重開鍵。"
                      "這通常是驅動程式或 BIOS 對睡眠的支援有問題，不是硬體故障，但每次強制重開都有讓檔案損毀的風險。",
                steps=["更新主機板的晶片組驅動與 BIOS（主機板官網的 BIOS 更新說明常會提到改善睡眠／喚醒）。",
                       "更新顯示卡驅動（睡眠叫不醒、螢幕不亮常跟顯示卡驅動有關）。",
                       "下次叫不醒時，先試著動滑鼠、按鍵盤，或短按一下電源鍵，等 10 秒再判斷是否真的當住。",
                       "如果一直改善不了，可以改用「關機」或「休眠」代替睡眠，或在電源選項中關閉「混合式睡眠」。"],
                actions=[OPEN_RELIABILITY, Action("開啟電源選項", "powercfg.cpl")]))

        if shutdown := groups["shutdown"]:
            n = len(shutdown)
            out.append(Finding(
                "events:shutdown-cut", Severity.WARNING if n >= 5 else Severity.INFO,
                f"最近 {days} 天有 {n} 次在關機還沒完成時就斷電",
                detail=f"時間：{_dates(shutdown)}\n{RECORDED_NOTE}",
                cause="Windows 正在關機的途中電源就被切斷了。常見原因是按了關機後馬上關延長線開關或拔插頭。"
                      "Windows 常常在關機時安裝更新、把資料寫回硬碟，這時候斷電可能讓檔案或系統更新損壞。",
                steps=["按關機後，等電腦的電源燈和風扇完全停止，再關延長線或拔插頭。",
                       "如果畫面顯示「正在進行更新，請勿關閉電腦」，一定要等它跑完。",
                       "如果是因為關機卡很久才忍不住斷電，可以在「可靠性監視器」看看關機時有沒有程式出錯。"],
                actions=[OPEN_RELIABILITY]))

        if power := groups["power"]:
            n = len(power)
            sev = Severity.CRITICAL if n >= 5 else Severity.WARNING if n >= 2 else Severity.INFO
            out.append(Finding(
                "events:power-loss", sev, f"最近 {days} 天有 {n} 次突然斷電或當機重開",
                detail=f"時間：{_dates(power)}\n{RECORDED_NOTE}\n（不是藍屏、不是在關機或睡眠時，也沒有偵測到長按電源鍵）",
                cause="電腦沒有經過正常關機就停止運作。常見原因：停電或跳電、電源線鬆脫、"
                      "電源供應器老化或瓦數不足（特別是玩遊戲時發生）、電腦完全當住後被重新啟動。",
                steps=["回想這些時間點是否有停電、跳電，或有人拔到插頭。",
                       "如果都發生在玩遊戲或高負載時，最可能是電源供應器的問題，建議請店家檢測。",
                       "確認電源線兩端都插緊；如果有用延長線，換一條或直接插牆壁插座試試。",
                       "想避免停電損壞資料，可以考慮加裝不斷電系統（UPS）。"],
                actions=[OPEN_RELIABILITY]))

        if button := groups["button"]:
            n = len(button)
            out.append(Finding(
                "events:forced-off", Severity.WARNING if n >= 3 else Severity.INFO,
                f"最近 {days} 天有 {n} 次長按電源鍵強制關機", detail=f"時間：{_dates(button)}\n{RECORDED_NOTE}",
                cause="強制關機通常是因為電腦卡住沒有反應。偶爾一次沒關係，但次數多代表有東西讓系統當住，"
                      "而且強制關機本身也可能讓正在寫入的檔案損毀。",
                steps=["下次卡住時，先等一兩分鐘，或按 Ctrl+Shift+Esc 開工作管理員結束沒有回應的程式。",
                       "如果常在某個遊戲或程式中卡住，先更新該程式與顯示卡驅動。"],
                actions=[OPEN_RELIABILITY]))
        return out

    # ---- 硬體錯誤事件 ----
    def _hardware(self, raw: dict, days: int) -> list[Finding]:
        out = []
        whea = raw.get("Whea") or []
        fatal = [e for e in whea if e.get("Id") in (1, 18, 20, 46)]
        corrected = [e for e in whea if e.get("Id") in (17, 19, 47)]
        if fatal:
            out.append(Finding(
                "events:whea-fatal", Severity.CRITICAL, f"硬體回報了 {len(fatal)} 次嚴重錯誤（WHEA）",
                detail=f"時間：{_dates(fatal)}",
                cause="CPU、記憶體或 PCIe 裝置回報了無法修正的硬體錯誤，通常會伴隨藍屏或當機。"
                      "常見原因是超頻（含記憶體 XMP）不穩定、電壓不足或硬體故障。",
                steps=["到 BIOS 載入預設值（Load Optimized Defaults），先不開 XMP 測試幾天。",
                       "更新主機板 BIOS（Intel 12～14 代 CPU 的 BIOS 更新常包含穩定性修正）。",
                       "若恢復預設後仍然發生，可能是 CPU、記憶體或主機板故障，建議送修檢測。"],
                actions=[OPEN_EVENTVWR, MEMORY_DIAG]))
        if corrected:
            n = len(corrected)
            out.append(Finding(
                "events:whea-corrected", Severity.WARNING if n >= 10 else Severity.INFO,
                f"硬體回報了 {n} 次已自動修正的錯誤（WHEA）", detail=f"時間：{_dates(corrected)}",
                cause="硬體發生錯誤但已自動修正，暫時不影響使用。偶爾出現不用擔心；"
                      "大量出現代表某個硬體（常見是 PCIe 裝置或記憶體）不太穩定，可能是問題的前兆。",
                steps=["若同時有當機或藍屏，先取消超頻（含 XMP）。",
                       "在事件檢視器的「Windows 紀錄 → 系統」中，找來源為 WHEA-Logger 的事件，可看到是哪個裝置。"],
                actions=[OPEN_EVENTVWR]))

        if tdr := raw.get("DisplayTdr") or []:
            n = len(tdr)
            out.append(Finding(
                "events:tdr", Severity.WARNING if n >= 2 else Severity.INFO,
                f"顯示卡驅動曾停止回應並自動恢復 {n} 次", detail=f"時間：{_dates(tdr)}",
                cause="顯示卡驅動卡住，Windows 把它重新啟動了（畫面會黑一下或遊戲閃退）。"
                      "常見原因是驅動問題、顯示卡超頻、溫度過高或供電不穩。",
                steps=["用「全新安裝」重灌最新的顯示卡驅動。",
                       "如果有用 MSI Afterburner 等工具超頻，先恢復預設。",
                       "確認顯示卡電源線插緊，並注意遊戲時的顯示卡溫度。"],
                actions=[Action("NVIDIA 驅動下載", "https://www.nvidia.com/Download/index.aspx")]))

        disk = raw.get("DiskErrors") or []
        if bad := [e for e in disk if e.get("Id") == 7]:
            out.append(Finding(
                "events:disk-bad-block", Severity.CRITICAL, f"Windows 記錄到 {len(bad)} 次硬碟壞軌",
                detail=f"時間：{_dates(bad)}",
                cause="Windows 在讀寫硬碟時遇到壞掉的區塊，資料可能已經損毀，硬碟可能正在故障。",
                steps=["立刻備份重要資料。", "查看本報告「硬碟健康與容量」中各硬碟的 SMART 狀態，找出是哪一顆。",
                       "盡快更換有問題的硬碟。"], actions=[OPEN_EVENTVWR]))
        io = [e for e in disk if e.get("Id") != 7] + (raw.get("NvmeErrors") or [])
        if io:
            n = len(io)
            out.append(Finding(
                "events:disk-io", Severity.WARNING if n >= 3 else Severity.INFO,
                f"硬碟或硬碟控制器回報了 {n} 次讀寫錯誤", detail=f"時間：{_dates(io)}",
                cause="硬碟讀寫時發生錯誤或逾時後重試。常見原因是 SATA 線接觸不良、USB 外接硬碟被拔除、"
                      "SSD 韌體問題或硬碟開始劣化。",
                steps=["若有外接硬碟，確認不是在拔除時產生的。",
                       "SATA 硬碟可以換一條 SATA 線或換一個插槽。",
                       "更新 SSD 韌體與晶片組驅動，並查看本報告的硬碟 SMART 狀態。"],
                actions=[OPEN_EVENTVWR]))
        if ntfs := raw.get("NtfsErrors") or []:
            out.append(Finding(
                "events:ntfs", Severity.WARNING, f"檔案系統曾回報 {len(ntfs)} 次損毀",
                detail=f"時間：{_dates(ntfs)}",
                cause="硬碟上的檔案系統結構有錯誤，常見於突然斷電或強制關機之後。",
                steps=["開啟檔案總管，對有問題的磁碟按右鍵 → 內容 → 工具 →「檢查」。",
                       "C: 槽的修復可能需要重新開機後才會執行。"],
                actions=[OPEN_EVENTVWR]))
        return out

    # ---- 程式當掉 ----
    def _apps(self, raw: dict, days: int, ctx: dict) -> list[Finding]:
        crashes = raw.get("AppCrashes") or []
        counts = Counter((c.get("App") or "未知程式") for c in crashes)
        repeated = [(app, n) for app, n in counts.most_common() if n >= APP_CRASH_MIN]
        if not repeated:
            return []
        many = len(repeated) >= 3
        lines = [f"・{app}：{n} 次" for app, n in repeated]
        others = len(crashes) - sum(n for _, n in repeated)
        if others:
            lines.append(f"・其他程式合計：{others} 次")
        steps = []
        driver_days = ctx.get("gpu_driver_days")
        if many and driver_days and driver_days >= 180:
            steps.append(f"有好幾個不同的程式都在當，而你的顯示卡驅動已經約 {driver_days // 30} 個月沒更新，"
                         "建議先更新顯示卡驅動，再觀察還會不會當。")
        steps += ["更新反覆當掉的程式到最新版本，或重新安裝。",
                  "遊戲可以用遊戲平台（Steam 等）的「驗證遊戲檔案完整性」功能。"]
        if many:
            steps.append("如果更新後還是很多程式在當，可以到 BIOS 暫時關閉 XMP（記憶體超頻）測試，"
                         "並用「Windows 記憶體診斷」檢查記憶體。")
        return [Finding(
            "events:app-crashes", Severity.INFO,
            f"最近 {days} 天有 {len(repeated)} 個程式反覆當掉" + ("（含多個不同程式）" if many else ""),
            detail=f"當掉 {APP_CRASH_MIN} 次以上的程式：\n" + "\n".join(lines),
            cause="單一程式反覆當掉，通常是那個程式本身的問題。如果很多不同的程式（特別是遊戲）都在當，"
                  "就比較可能是共同的原因，例如顯示卡驅動、記憶體不穩定或系統檔案問題。",
            steps=steps, actions=[OPEN_RELIABILITY, MEMORY_DIAG])]
