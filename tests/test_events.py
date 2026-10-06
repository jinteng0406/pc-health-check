from pchealth.checks import bugchecks
from pchealth.checks.events import EventsCheck, classify_kernel_power
from pchealth.model import Severity
from pchealth.runner import load_fixture


def kp(code="0", button="0", long_press="false", t="2026-10-01T10:00:00", sleep="0", wakes="0"):
    return {"Time": t, "Id": 41, "Data": {"BugcheckCode": code, "PowerButtonTimestamp": button,
                                          "LongPowerButtonPressDetected": long_press,
                                          "SleepInProgress": sleep, "SystemSleepTransitionsToOn": wakes}}


def analyze(**raw):
    return EventsCheck().analyze({"Days": 30, **raw}, {})


def ids(findings):
    return {f.id: f for f in findings}


def test_quiet_machine_is_ok():
    [f] = analyze()
    assert f.severity == Severity.OK and "30 天" in f.title


def test_kernel_power_classification():
    assert classify_kernel_power(kp(code="278")) == "bsod"
    assert classify_kernel_power(kp(button="133712345678")) == "button"
    assert classify_kernel_power(kp(long_press="true")) == "button"
    assert classify_kernel_power(kp(sleep="6")) == "shutdown"
    assert classify_kernel_power(kp(sleep="4")) == "sleep"
    assert classify_kernel_power(kp(wakes="23")) == "sleep"
    assert classify_kernel_power(kp()) == "power"


def test_shutdown_cut_and_sleep_hang_are_info_with_specific_advice():
    fs = ids(analyze(KernelPower=[kp(sleep="6"), kp(wakes="23")]))
    assert set(fs) == {"events:shutdown-cut", "events:sleep-hang"}
    assert all(f.severity == Severity.INFO for f in fs.values())
    assert "延長線" in fs["events:shutdown-cut"].steps[0]
    assert "23 次" in fs["events:sleep-hang"].detail and "BIOS" in fs["events:sleep-hang"].steps[0]
    assert "下一次開機時記錄" in fs["events:shutdown-cut"].detail


def test_single_power_loss_is_info_two_is_warning():
    assert analyze(KernelPower=[kp()])[0].severity == Severity.INFO
    assert analyze(KernelPower=[kp(), kp()])[0].severity == Severity.WARNING


def test_bsod_uses_wer_code_and_does_not_double_count_kernel_power():
    raw = {"KernelPower": [kp(code="278")],
           "BugChecks": [{"Time": "2026-10-01T10:00:30", "Data": {"param1": "0x00000116 (0x1, 0x2, 0x3, 0x4)"}}]}
    fs = ids(analyze(**raw))
    assert set(fs) == {"events:bsod"}
    assert "1 次藍屏" in fs["events:bsod"].title and "VIDEO_TDR_FAILURE" in fs["events:bsod"].detail


def test_bsod_falls_back_to_kernel_power_code():
    [f] = analyze(KernelPower=[kp(code="292")])  # 0x124
    assert "WHEA_UNCORRECTABLE_ERROR" in f.detail


def test_three_bsods_is_critical():
    assert analyze(KernelPower=[kp(code="26")] * 3)[0].severity == Severity.CRITICAL


def test_whea_fatal_vs_corrected():
    assert analyze(Whea=[{"Id": 18, "Time": "t"}])[0].severity == Severity.CRITICAL
    assert analyze(Whea=[{"Id": 19, "Time": "t"}])[0].severity == Severity.INFO
    assert analyze(Whea=[{"Id": 19, "Time": "t"}] * 10)[0].severity == Severity.WARNING


def test_disk_bad_block_is_critical():
    fs = ids(analyze(DiskErrors=[{"Id": 7, "Time": "t"}, {"Id": 153, "Time": "t"}]))
    assert fs["events:disk-bad-block"].severity == Severity.CRITICAL
    assert "events:disk-io" in fs


def test_app_crashes_only_when_repeated():
    crashes = [{"App": "game.exe", "Time": "t"}] * 3 + [{"App": "chrome.exe", "Time": "t"}] * 2
    [f] = analyze(AppCrashes=crashes)
    assert f.severity == Severity.INFO and "1 個程式" in f.title
    assert "game.exe：3 次" in f.detail and "其他程式合計：2 次" in f.detail
    assert analyze(AppCrashes=crashes[3:])[0].id == "events:ok"


def test_many_crashing_apps_with_old_gpu_driver_suggests_driver_first():
    crashes = [{"App": f"g{i}.exe", "Time": "t"} for i in range(4) for _ in range(3)]
    [f] = EventsCheck().analyze({"Days": 30, "AppCrashes": crashes}, {"gpu_driver_days": 250})
    assert "多個不同程式" in f.title and "顯示卡驅動" in f.steps[0] and "8 個月" in f.steps[0]
    [f] = EventsCheck().analyze({"Days": 30, "AppCrashes": crashes}, {"gpu_driver_days": 20})
    assert "顯示卡驅動" not in f.steps[0]


def test_parse_bugcheck_codes():
    assert bugchecks.parse_code("278") == 0x116
    assert bugchecks.parse_code("0x00000124 (0x0, ...)") == 0x124
    assert bugchecks.parse_code(None) is None


def test_demo_fixture():
    fs = ids(EventsCheck().run(load_fixture("events")).findings)
    assert {"events:bsod", "events:power-loss", "events:forced-off", "events:whea-corrected",
            "events:tdr", "events:disk-io", "events:app-crashes"} <= set(fs)
    assert "2 次藍屏" in fs["events:bsod"].title
