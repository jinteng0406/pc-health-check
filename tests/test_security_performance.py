from pchealth.checks.performance import PerformanceCheck
from pchealth.checks.security import SecurityCheck, is_windows_update
from pchealth.model import Severity
from pchealth.runner import load_fixture

NOW = "2026-10-06T22:00:00"
DEFENDER_OK = {"AntivirusEnabled": True, "RealTimeProtectionEnabled": True,
               "SignatureLastUpdated": "2026-10-06T09:00:00", "AMRunningMode": "Normal"}
CU = "2026-09 x64 型 Windows 11 累積更新 (KB5099999)"


def sec(**raw):
    base = {"Now": NOW, "History": [{"Date": "2026-09-20T03:00:00", "Title": CU, "Result": 2}],
            "RebootPending": False, "Defender": DEFENDER_OK, "Antivirus": []}
    return {f.id: f for f in SecurityCheck().analyze(base | raw, {})}


def test_healthy_security():
    fs = sec()
    assert set(fs) == {"security:updates-ok", "security:av-ok"}


def test_defender_and_store_updates_do_not_count_as_windows_updates():
    assert not is_windows_update("安全情報更新 Microsoft Defender Antivirus - KB2267602 (版本 1.459)")
    assert not is_windows_update("9NRZT3Q9R3DL-Microsoft.WindowsAppRuntime.2")
    assert is_windows_update(CU)
    fs = sec(History=[{"Date": "2026-10-06T09:00:00", "Title": "Defender - KB2267602", "Result": 2},
                      {"Date": "2026-08-01T03:00:00", "Title": CU, "Result": 2}])
    assert "security:update-old" in fs and "66 天" in fs["security:update-old"].title


def test_failed_update_without_later_success():
    fs = sec(History=[{"Date": "2026-10-01T03:00:00", "Title": "新更新 (KB5100000)", "Result": 4, "HResult": "0x800F0922"},
                      {"Date": "2026-09-20T03:00:00", "Title": CU, "Result": 2}])
    assert "0x800F0922" in fs["security:update-failed"].detail


def test_failed_then_succeeded_is_fine():
    fs = sec(History=[{"Date": "2026-10-02T03:00:00", "Title": CU, "Result": 2},
                      {"Date": "2026-10-01T03:00:00", "Title": CU, "Result": 4}])
    assert "security:update-failed" not in fs


def test_realtime_off_is_critical_unless_other_av():
    off = DEFENDER_OK | {"RealTimeProtectionEnabled": False}
    assert sec(Defender=off)["security:av-off"].severity == Severity.CRITICAL
    fs = sec(Defender=off | {"AMRunningMode": "Passive Mode"}, Antivirus=[{"Name": "Kaspersky", "State": 266240}])
    assert "Kaspersky" in fs["security:av-ok"].title


def test_old_signatures():
    fs = sec(Defender=DEFENDER_OK | {"SignatureLastUpdated": "2026-09-20T09:00:00"})
    assert fs["security:signature-old"].severity == Severity.WARNING


def test_security_demo_fixture():
    fs = {f.id for f in SecurityCheck().run(load_fixture("security")).findings}
    assert {"security:update-old", "security:update-failed", "security:reboot-pending", "security:av-ok"} <= fs


def perf(**raw):
    base = {"Startup": [{"Name": f"app{i}", "Enabled": True} for i in range(5)],
            "TotalMemoryKB": 32 * 1024**2, "FreeMemoryKB": 20 * 1024**2,
            "TopProcesses": [{"Name": "chrome", "MB": 2000}],
            "PowerScheme": "381b4222-f694-41f0-9685-ff5bb260df2e"}
    return {f.id: f for f in PerformanceCheck().analyze(base | raw, {})}


def test_healthy_performance():
    assert set(perf()) == {"performance:startup-ok", "performance:memory-ok", "performance:power-ok"}


def test_disabled_startup_items_not_counted():
    items = [{"Name": f"a{i}", "Enabled": True} for i in range(13)] + [{"Name": "off", "Enabled": False}]
    f = perf(Startup=items)["performance:startup-many"]
    assert "13 個" in f.title and "off" not in f.detail


def test_memory_and_power_saver():
    fs = perf(FreeMemoryKB=2 * 1024**2, PowerScheme="a1841308-3541-4fab-bc81-f71556f20b4a")
    assert fs["performance:memory-high"].severity == Severity.WARNING
    assert "performance:power-saver" in fs


def test_performance_demo_fixture():
    fs = {f.id for f in PerformanceCheck().run(load_fixture("performance")).findings}
    assert fs == {"performance:startup-many", "performance:memory-high", "performance:power-saver"}
