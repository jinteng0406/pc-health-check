"""使用者家裡那台電腦的真實資料（已去識別化）：確保不誤報，且不把「未知」說成「正常」。

ASUS PRIME Z790-P D4 / i5-12600KF / RTX 4060 Ti / 2x Crucial P3 Plus（經 Intel VMD）
"""
import json
from pathlib import Path

from pchealth.checks.storage import StorageCheck
from pchealth.checks.system import SystemCheck
from pchealth.model import Severity

DATA = Path(__file__).parent / "data" / "home"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def test_system_overview_and_only_driver_reminder():
    fs = SystemCheck().analyze(load("system"), {})
    assert fs[0].title.startswith("ASUS PRIME Z790-P D4")
    assert "591.86" in fs[0].detail
    assert [f.id.split(":")[1] for f in fs[1:]] == ["gpu-driver-old"]
    assert all(f.severity <= Severity.INFO for f in fs)


def test_storage_no_false_alarms():
    fs = StorageCheck().analyze(load("storage"), {})
    assert all(f.severity == Severity.OK for f in fs)
    assert len(fs) == 4  # 2 顆硬碟 + C:、D:


def load_smart(name):
    return json.loads((DATA.parent / "home_smart" / f"{name}.json").read_text(encoding="utf-8"))


def test_v03_smartctl_through_intel_vmd():
    """v0.3 在家實測：smartctl 讀得到兩顆硬碟，磨損以 smartctl 為準（Windows 誤報 0%）。"""
    disks = {f.id.split(":")[3]: f for f in StorageCheck().analyze(load_smart("storage"), {}) if ":disk:" in f.id}
    assert all(f.severity == Severity.OK for f in disks.values())
    assert "磨損 7%" in disks["0"].title and "通電 8,499 小時" in disks["0"].title
    assert "磨損 5%" in disks["1"].title
    assert "錯誤次數未知" not in disks["0"].title
    assert "警戒溫度 83°C" in disks["0"].detail and "警戒以上 0 分鐘" in disks["0"].detail


def test_v03_gpu_full_speed_x8():
    from pchealth.checks.gpu import NvidiaCheck
    [f] = NvidiaCheck().analyze(load_smart("gpu"), {})
    assert f.severity == Severity.OK and "PCIe x8" in f.title and "16.0 GB" in f.detail


def load_v04(name):
    return json.loads((DATA.parent / "home_v04" / f"{name}.json").read_text(encoding="utf-8"))


def test_v04_events_match_what_actually_happened():
    """使用者確認：9/9 是關機途中關延長線、9/23 是睡眠叫不醒按電源鍵；電腦其實很穩定。"""
    from pchealth.checks.events import EventsCheck
    ctx = SystemCheck().context(load_v04("system"))
    fs = {f.id: f for f in EventsCheck().analyze(load_v04("events"), ctx)}
    assert set(fs) == {"events:shutdown-cut", "events:sleep-hang", "events:app-crashes"}
    assert all(f.severity == Severity.INFO for f in fs.values())  # 穩定的電腦不該出現「注意」以上
    assert "2026-09-09" in fs["events:shutdown-cut"].detail
    assert "23 次" in fs["events:sleep-hang"].detail
    assert "顯示卡驅動" in fs["events:app-crashes"].steps[0]  # 多款遊戲當掉 + 驅動 8 個月沒更新


def test_v04_security_and_performance_ok():
    from pchealth.checks.performance import PerformanceCheck
    from pchealth.checks.security import SecurityCheck
    sec = {f.id: f for f in SecurityCheck().analyze(load_v04("security"), {})}
    assert set(sec) == {"security:updates-ok", "security:av-ok"}
    assert "2026-09-24" in sec["security:updates-ok"].title  # 不是 Defender 病毒碼或平台更新的日期
    perf = PerformanceCheck().analyze(load_v04("performance"), {})
    assert all(f.severity == Severity.OK for f in perf)


def load_v05(name):
    return json.loads((DATA.parent / "home_v05" / f"{name}.json").read_text(encoding="utf-8"))


def test_v05_sensors_without_pawnio_and_custom_power_plan():
    """v0.5 在家實測：沒裝 PawnIO（使用者常玩 FACEIT）；電源計畫名稱含括號，由登錄檔備援取得。"""
    from pchealth.checks.performance import PerformanceCheck
    from pchealth.checks.sensors import SensorsCheck
    sensors = {f.id: f for f in SensorsCheck().analyze(load_v05("sensors"), {})}
    assert set(sensors) == {"sensors:no-driver", "sensors:no-limit"}
    assert "FACEIT" in sensors["sensors:no-driver"].cause
    perf = {f.id: f for f in PerformanceCheck().analyze(load_v05("performance"), {})}
    assert perf["performance:power-ok"].title == "電源計畫：Ultimate Performance (ExitLag)（自訂）"


def test_storage_unknown_error_count_is_not_presented_as_zero():
    disks = [f for f in StorageCheck().analyze(load("storage"), {}) if ":disk:" in f.id]
    for f in disks:
        assert "錯誤次數未知" in f.title
        assert "不代表沒有" in f.detail
        assert "最高紀錄" not in f.detail  # 83°C 是硬碟回報的上限值，不是實際到過的溫度
