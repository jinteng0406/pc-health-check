"""NVIDIA 顯示卡即時狀態：使用驅動內建的 nvidia-smi（不需要額外安裝）。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..model import Action, Finding, Severity
from .base import Check

CREATE_NO_WINDOW = 0x08000000
FIELDS = ["name", "driver_version", "temperature.gpu", "fan.speed", "power.draw", "power.limit",
          "utilization.gpu", "memory.used", "memory.total",
          "pcie.link.gen.current", "pcie.link.gen.max", "pcie.link.width.current", "pcie.link.width.max"]
# 舊版驅動叫 clocks_throttle_reasons，新版改名 clocks_event_reasons
REASON_FIELDS = ["clocks_event_reasons.active", "clocks_throttle_reasons.active"]

THERMAL_SLOWDOWN = 0x20 | 0x40 | 0x80  # SW/HW thermal slowdown
POWER_BRAKE = 0x08 | 0x100  # HW slowdown / power brake（常見於供電不足）

TEMP_WARN, TEMP_CRIT = 83, 90
IDLE_TEMP_WARN = 65  # 閒置（使用率 < 10%）時的溫度
NVIDIA_DRIVERS = Action("NVIDIA 驅動下載", "https://www.nvidia.com/Download/index.aspx")


def find_nvidia_smi() -> Path | None:
    for p in (Path(r"C:\Windows\System32\nvidia-smi.exe"),
              Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe")):
        if p.exists():
            return p
    found = shutil.which("nvidia-smi")
    return Path(found) if found else None


def _query(exe: Path, fields: list[str]) -> list[list[str]] | None:
    try:
        proc = subprocess.run([str(exe), f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"],
                              capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.decode("utf-8", errors="replace").strip().splitlines()
    return [[c.strip() for c in line.split(",")] for line in lines if line.strip()]


def _num(s: str | None) -> float | None:
    try:
        return float(s)  # "[N/A]"、"[Not Supported]" → None
    except (TypeError, ValueError):
        return None


class NvidiaCheck(Check):
    id = "gpu"
    title = "顯示卡狀態"

    def collect(self) -> dict:
        exe = find_nvidia_smi()
        if not exe:
            return {"available": False, "gpus": []}
        rows = _query(exe, FIELDS) or []
        gpus = [dict(zip(FIELDS, r)) for r in rows]
        for field in REASON_FIELDS:
            if reasons := _query(exe, [field]):
                for g, r in zip(gpus, reasons):
                    g["clock_reasons"] = r[0]
                break
        return {"available": True, "gpus": gpus}

    def analyze(self, raw: dict, ctx: dict) -> list[Finding]:
        if not raw.get("available"):
            return [Finding("gpu:none", Severity.OK, "沒有偵測到 NVIDIA 顯示卡，略過此項",
                            detail="找不到 nvidia-smi。如果你的電腦有 NVIDIA 顯示卡，代表驅動沒有正確安裝。",
                            actions=[NVIDIA_DRIVERS])]
        if not raw.get("gpus"):
            return [Finding("gpu:smi-failed", Severity.WARNING, "NVIDIA 驅動沒有回應",
                            detail="nvidia-smi 存在但無法讀取顯示卡狀態。",
                            cause="通常代表顯示卡驅動異常，或顯示卡沒有被系統正確辨識。",
                            steps=["重新開機後再檢查一次。", "到 NVIDIA 官網下載最新驅動，選擇「執行全新安裝」。"],
                            actions=[NVIDIA_DRIVERS])]
        out = []
        for g in raw["gpus"]:
            out += self._gpu(g)
        return sorted(out, key=lambda f: -f.severity)

    def _gpu(self, g: dict) -> list[Finding]:
        name = g.get("name") or "NVIDIA 顯示卡"
        key = f"gpu:{name}"
        temp, fan = _num(g.get("temperature.gpu")), _num(g.get("fan.speed"))
        power, limit = _num(g.get("power.draw")), _num(g.get("power.limit"))
        util = _num(g.get("utilization.gpu"))
        mem_used, mem_total = _num(g.get("memory.used")), _num(g.get("memory.total"))
        gen, gen_max = _num(g.get("pcie.link.gen.current")), _num(g.get("pcie.link.gen.max"))
        width, width_max = _num(g.get("pcie.link.width.current")), _num(g.get("pcie.link.width.max"))
        try:
            reasons = int(g.get("clock_reasons") or "0", 16)
        except ValueError:
            reasons = 0

        info = [f"顯示卡：{name}（驅動 {g.get('driver_version')}）"]
        if temp is not None:
            info.append(f"溫度：{temp:.0f}°C")
        if fan is not None:
            info.append(f"風扇：{fan:.0f}%" + ("（低負載時停轉是正常的省電設計）" if fan == 0 else ""))
        if power is not None:
            info.append(f"功耗：{power:.0f} W" + (f" / 上限 {limit:.0f} W" if limit else ""))
        if util is not None:
            info.append(f"使用率：{util:.0f}%")
        if mem_used is not None and mem_total:
            info.append(f"顯示記憶體：{mem_used / 1024:.1f} / {mem_total / 1024:.1f} GB")
        if width is not None:
            info.append(f"PCIe 連線：Gen{gen:.0f} x{width:.0f}（顯示卡最高支援 Gen{gen_max:.0f} x{width_max:.0f}）"
                        if gen and gen_max and width_max else f"PCIe 連線寬度：x{width:.0f}")
        detail = "\n".join(info)
        idle = util is not None and util < 10
        out = []

        def add(suffix, sev, title, cause, steps, actions=()):
            out.append(Finding(f"{key}:{suffix}", sev, f"{name}：{title}", detail=detail,
                               cause=cause, steps=list(steps), actions=list(actions)))

        if width is not None and width_max and width < width_max:
            add("pcie-width", Severity.WARNING, f"PCIe 只以 x{width:.0f} 連線（應為 x{width_max:.0f}）",
                "顯示卡和主機板之間的通道數比應有的少，常見原因是顯示卡沒有完全插緊、插槽或金手指有灰塵，"
                "或插在頻寬較小的插槽。這會降低效能，有時也會造成不穩定。",
                ["關機並拔掉電源，把顯示卡拔下來重新插緊，直到插槽卡榫「喀」一聲扣上。",
                 "確認顯示卡插在最靠近 CPU 的那條長插槽（通常是 PCIEX16_1）。",
                 "用乾淨的橡皮擦或酒精棉輕擦金手指，並清除插槽灰塵。",
                 "如果主機板裝了很多 M.2 SSD，有些主機板會把顯示卡插槽降速，請查閱主機板說明書。"])

        if temp is not None and temp >= TEMP_WARN:
            add("temp", Severity.CRITICAL if temp >= TEMP_CRIT else Severity.WARNING, f"溫度偏高（{temp:.0f}°C）",
                "顯示卡溫度過高時會自動降頻，造成遊戲掉幀；長期高溫也會縮短壽命。",
                ["清理顯示卡散熱鰭片與風扇上的灰塵。", "確認機殼前方進風、後方與上方出風順暢。",
                 "如果顯示卡已使用多年，散熱膏可能乾掉，可以送修更換。"])
        elif temp is not None and idle and temp >= IDLE_TEMP_WARN:
            add("idle-temp", Severity.WARNING, f"閒置時溫度偏高（{temp:.0f}°C，使用率 {util:.0f}%）",
                "顯示卡幾乎沒在工作時溫度仍然偏高，常見原因是散熱器積灰、風扇故障或機殼通風不良。",
                ["確認顯示卡風扇在高負載時有轉動（玩遊戲時看一下）。", "清理灰塵並檢查機殼風扇。"])

        if reasons & THERMAL_SLOWDOWN:
            add("thermal-throttle", Severity.WARNING, "正在因為過熱而降頻",
                "顯示卡為了保護自己正在降低速度，效能會明顯下降。",
                ["清理散熱器灰塵、改善機殼通風。", "降低遊戲畫質或幀數上限，減少發熱。"])
        if reasons & POWER_BRAKE:
            add("power-brake", Severity.WARNING, "硬體強制降速（可能是供電不足）",
                "顯示卡偵測到供電異常而強制降速，常見原因是電源供應器瓦數不足或老化、"
                "顯示卡的 PCIe 電源線沒有插緊。",
                ["確認顯示卡上的電源線（8-pin／12VHPWR）完全插緊，不要使用轉接線串接。",
                 "確認電源供應器瓦數符合顯示卡建議（RTX 4060 Ti 建議 550 W 以上）。"])

        if not out:
            summary = [f"{temp:.0f}°C" if temp is not None else None,
                       f"風扇 {fan:.0f}%" if fan is not None else None,
                       f"{power:.0f} W" if power is not None else None,
                       f"PCIe x{width:.0f}" if width is not None else None]
            out.append(Finding(f"{key}:ok", Severity.OK, f"{name}：正常（{'、'.join(s for s in summary if s)}）",
                               detail=detail))
        return out
