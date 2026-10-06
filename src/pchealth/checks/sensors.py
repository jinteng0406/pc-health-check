"""CPU 與主機板溫度、風扇。

- 免驅動（每台電腦）：最近 N 天 CPU 是否被韌體限速（Kernel-Processor-Power 事件 37，常見於過熱或供電限制）
- 已安裝 PawnIO 時：用 LibreHardwareMonitor 讀 CPU 溫度、主機板溫度、風扇轉速、電壓
  程式不會安裝任何驅動；PawnIO 由使用者自行決定是否安裝（部分反作弊軟體不相容）。
"""
from __future__ import annotations

from ..elevate import is_admin
from ..model import Action, Finding, Severity
from ..powershell import run_ps_json
from .base import Check
from .sensors_ps import base_script, lhm_script

DAYS = 30
PAWNIO_SITE = Action("PawnIO 下載頁（GitHub）", "https://github.com/namazso/PawnIO.Setup/releases/latest")
OPEN_POWER = Action("開啟電源選項", "powercfg.cpl")

CPU_TEMP_WARN, CPU_TEMP_CRIT = 85, 95
IDLE_LOAD, IDLE_TEMP_WARN = 15, 70


def lhm_dir():
    from ..runner import resource_dir  # 避免循環匯入
    return resource_dir() / "bin" / "lhm"


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _seconds(data: dict) -> int:
    """事件 37 的 CapDurationInSeconds（以名稱比對，避免依賴欄位順序）。"""
    return sum(_int(v) for k, v in (data or {}).items() if "second" in k.lower())


class SensorsCheck(Check):
    id = "sensors"
    title = "CPU 與主機板溫度"

    def collect(self) -> dict:
        raw = run_ps_json(base_script(DAYS))[0]
        raw["Admin"] = is_admin()
        folder = lhm_dir()
        raw["LhmBundled"] = (folder / "LibreHardwareMonitorLib.dll").exists()
        if raw.get("PawnIO") and raw["Admin"] and raw["LhmBundled"]:
            try:
                raw["Lhm"] = run_ps_json(lhm_script(str(folder)), timeout=60)[0]
            except Exception as e:  # 感測器讀取失敗不影響其他檢查
                raw["LhmError"] = f"{type(e).__name__}: {str(e)[:300]}"
        return raw

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        out = self._firmware_limit(raw) + self._sensors(raw)
        return sorted(out, key=lambda f: -f.severity)

    # ---- 免驅動：CPU 被韌體限速 ----
    def _firmware_limit(self, raw: dict) -> list[Finding]:
        days = raw.get("Days") or DAYS
        events = raw.get("FirmwareLimit") or []
        if not events:
            return [Finding("sensors:no-limit", Severity.OK, f"最近 {days} 天 CPU 沒有被韌體限速",
                            detail="沒有「處理器速度受到系統韌體限制」的紀錄（過熱或供電不足時會出現）。")]
        # 每次限速會對每個邏輯處理器各記一筆，以「分鐘」合併成一次
        moments = sorted({e.get("Time", "")[:16] for e in events})
        seconds = max((_seconds(e.get("Data")) for e in events), default=0)
        n = len(moments)
        thermal = any(_int((e.get("Data") or {}).get("TpcChanges")) for e in events)
        platform = any(_int((e.get("Data") or {}).get("PpcChanges")) for e in events)
        reason = ("溫度過高" if thermal and not platform else "供電或平台限制" if platform and not thermal
                  else "溫度與供電限制" if thermal and platform else None)
        sev = Severity.WARNING if n >= 10 or seconds >= 600 else Severity.INFO
        shown = "、".join(m.replace("T", " ") for m in moments[-5:])
        return [Finding(
            "sensors:firmware-limit", sev,
            f"最近 {days} 天 CPU 有 {n} 次被韌體限速" + (f"（{reason}）" if reason else ""),
            detail=f"時間：{shown}" + (f"（另有 {n - 5} 次較早的紀錄）" if n > 5 else "")
                   + (f"\n單次最長持續約 {seconds:,} 秒" if seconds else "")
                   + (f"\n事件記錄的原因：{reason}" if reason else ""),
            cause="主機板韌體為了保護 CPU 而降低了速度，最常見的原因是 CPU 溫度過高，"
                  "其次是主機板供電（VRM）過熱或觸發功耗上限。限速期間電腦會明顯變慢、遊戲掉幀。",
            steps=["清理 CPU 散熱器與機殼風扇的灰塵，確認 CPU 風扇有在轉。",
                   "如果散熱器裝了很多年，散熱膏可能已經乾掉，可以請店家重新塗。",
                   "確認電源計畫不是「省電」模式。",
                   "到主機板官網更新 BIOS，並確認 BIOS 裡沒有開啟過度的 CPU 超頻。"],
            actions=[OPEN_POWER])]

    # ---- 需要 PawnIO：完整感測器 ----
    def _sensors(self, raw: dict) -> list[Finding]:
        if not raw.get("PawnIO"):
            return [Finding(
                "sensors:no-driver", Severity.INFO, "無法讀取 CPU 溫度與風扇（未安裝 PawnIO）",
                detail="Windows 本身沒有提供 CPU 溫度與風扇轉速，需要額外的硬體驅動程式才能讀取。"
                       "本程式不會自行安裝任何驅動。顯示卡與硬碟的溫度不受影響，已在其他項目中檢查。",
                cause="若想看到 CPU 溫度、主機板溫度與風扇轉速，可以自行安裝 PawnIO（有數位簽章的開源硬體驅動），"
                      "安裝後本程式會自動讀取。\n"
                      "⚠ 注意：已有回報 FACEIT 反作弊在裝了 PawnIO 的電腦上會拒絕啟動；其他核心層反作弊"
                      "（例如 Riot Vanguard）的相容性不明。常玩這類遊戲的話，不建議安裝。",
                steps=["不想冒反作弊的風險：維持現狀即可，上方的「CPU 被韌體限速」紀錄仍可間接看出 CPU 是否過熱。",
                       "想安裝：從下方的 GitHub 下載頁下載 PawnIO_setup.exe，或在命令提示字元執行\n"
                       "winget install --id namazso.PawnIO -e",
                       "安裝後若遊戲無法啟動，可在「設定 → 應用程式」中解除安裝 PawnIO。"],
                actions=[PAWNIO_SITE])]
        if not raw.get("Admin"):
            return [Finding("sensors:need-admin", Severity.INFO, "讀取 CPU 溫度需要管理員權限",
                            steps=["關閉程式後重新開啟，在 UAC 視窗按「是」。"])]
        if not raw.get("LhmBundled"):
            return [Finding("sensors:no-lhm", Severity.INFO, "這個版本沒有附帶感測器讀取元件",
                            detail="已偵測到 PawnIO，但程式資料夾中缺少 LibreHardwareMonitor 元件。請重新下載完整的 zip。")]
        if raw.get("LhmError"):
            return [Finding("sensors:lhm-error", Severity.INFO, "讀取 CPU 溫度時發生錯誤",
                            detail=raw["LhmError"],
                            steps=["確認 PawnIO 服務正在執行（重新開機通常可以解決）。",
                                   "可以從 PawnIO 下載頁下載最新版重新安裝。"], actions=[PAWNIO_SITE])]

        sensors = (raw.get("Lhm") or {}).get("Sensors") or []
        cpu_temps = {s["Name"]: s["Value"] for s in sensors
                     if s.get("HardwareType") == "Cpu" and s.get("Type") == "Temperature" and (s.get("Value") or 0) > 0}
        if not cpu_temps:
            return [Finding("sensors:no-cpu-temp", Severity.INFO, "已安裝 PawnIO，但沒有讀到 CPU 溫度",
                            detail=f"PawnIO 服務狀態：{raw.get('PawnIO')}",
                            cause="PawnIO 服務可能沒有在執行，或驅動版本與本程式附帶的感測器元件不相容。",
                            steps=["重新開機後再檢查一次。", "從 PawnIO 下載頁下載最新版重新安裝。"],
                            actions=[PAWNIO_SITE])]

        temp = cpu_temps.get("CPU Package") or cpu_temps.get("Core Max") or max(cpu_temps.values())
        load = next((s["Value"] for s in sensors if s.get("HardwareType") == "Cpu"
                     and s.get("Type") == "Load" and s.get("Name") == "CPU Total"), None)
        fans = [s for s in sensors if s.get("Type") == "Fan"]
        detail = self._detail(sensors, temp, load)
        out = []

        if temp >= CPU_TEMP_WARN:
            out.append(Finding(
                "sensors:cpu-hot", Severity.CRITICAL if temp >= CPU_TEMP_CRIT else Severity.WARNING,
                f"CPU 溫度偏高（{temp:.0f}°C）", detail=detail,
                cause="CPU 太熱時會自動降速，接近 100°C 會強制關機保護。這是檢查當下的溫度；"
                      "如果剛才在跑遊戲或大型程式，偏高是正常的。",
                steps=["閒置幾分鐘後再檢查一次。", "清理 CPU 散熱器與機殼風扇的灰塵，確認 CPU 風扇有在轉。",
                       "散熱器使用多年的話，可以請店家重新塗散熱膏。"]))
        elif load is not None and load < IDLE_LOAD and temp >= IDLE_TEMP_WARN:
            out.append(Finding(
                "sensors:cpu-idle-hot", Severity.WARNING, f"CPU 閒置時溫度偏高（{temp:.0f}°C，負載 {load:.0f}%）",
                detail=detail,
                cause="CPU 幾乎沒在工作時溫度仍然偏高，常見原因是散熱器沒有鎖緊、散熱膏乾掉、"
                      "CPU 風扇故障或機殼通風不良。",
                steps=["確認 CPU 風扇有在轉（看一下機殼內部）。", "清理散熱器灰塵；必要時請店家重新安裝散熱器與散熱膏。"]))

        if temp >= 80 and fans and all((f.get("Value") or 0) == 0 for f in fans):
            out.append(Finding(
                "sensors:fans-stopped", Severity.WARNING, "CPU 很熱，但沒有偵測到任何風扇在轉", detail=detail,
                cause="可能是風扇故障、風扇線沒插好，或主機板讀不到風扇轉速。",
                steps=["打開機殼確認 CPU 風扇與機殼風扇有在轉。", "確認 CPU 風扇插在主機板的 CPU_FAN 插座。"]))

        if not out:
            summary = f"CPU {temp:.0f}°C" + (f"（負載 {load:.0f}%）" if load is not None else "")
            out.append(Finding("sensors:ok", Severity.OK, f"溫度正常：{summary}", detail=detail))
        return out

    @staticmethod
    def _detail(sensors: list[dict], temp: float, load: float | None) -> str:
        lines = [f"CPU 溫度：{temp:.0f}°C" + (f"（負載 {load:.0f}%）" if load is not None else "")]
        cpu_power = next((s["Value"] for s in sensors if s.get("HardwareType") == "Cpu"
                          and s.get("Type") == "Power" and s.get("Name") == "CPU Package"), None)
        if cpu_power:
            lines.append(f"CPU 功耗：{cpu_power:.0f} W")
        board_temps = [s for s in sensors if s.get("HardwareType") != "Cpu" and s.get("Type") == "Temperature"
                       and 0 < (s.get("Value") or 0) < 125]
        if board_temps:
            lines.append("主機板溫度：" + "、".join(f"{s['Name']} {s['Value']:.0f}°C" for s in board_temps))
        fans = [s for s in sensors if s.get("Type") == "Fan"]
        if fans:
            lines.append("風扇：" + "、".join(f"{s['Name']} {s['Value']:.0f} RPM" for s in fans)
                         + "（0 RPM 可能只是該插座沒有接風扇）")
        volts = [s for s in sensors if s.get("HardwareType") != "Cpu" and s.get("Type") == "Voltage"]
        if volts:
            lines.append("電壓（僅供參考，主機板回報值不一定精確）：" + "、".join(f"{s['Name']} {s['Value']:.2f} V" for s in volts))
        return "\n".join(lines)
