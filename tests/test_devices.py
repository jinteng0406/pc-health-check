from pchealth.checks.devices import DevicesCheck, vendor_of
from pchealth.model import Severity
from pchealth.runner import load_fixture

ASUS_CTX = {"board": "ASUS TUF GAMING B760M-PLUS WIFI", "board_brand": "ASUS",
            "board_support_url": "https://www.asus.com/support/"}


def analyze(raw, ctx=None):
    return DevicesCheck().analyze(raw, ctx or {})


def dev(code, pnp="PCI\\VEN_1234&DEV_0001", name="測試裝置", present=True):
    return {"Name": name, "PNPClass": None, "Manufacturer": None,
            "ConfigManagerErrorCode": code, "PNPDeviceID": pnp, "Present": present}


def test_all_ok_reports_single_ok_finding():
    findings = analyze([dev(0), dev(0)])
    assert len(findings) == 1
    assert findings[0].severity == Severity.OK
    assert "2 個裝置" in findings[0].title


def test_missing_intel_chipset_driver_suggests_intel_software():
    # 實驗室電腦實際遇到的情況：Intel SMBus 控制器錯誤碼 28
    [f] = analyze([dev(28, "PCI\\VEN_8086&DEV_A323&SUBSYS_86941043&REV_10\\3&11583659&0&FC",
                                      "SM 匯流排控制器")])
    assert f.severity == Severity.WARNING
    assert "沒有安裝驅動程式" in f.title
    assert "Intel Chipset Device Software" in f.steps[0]
    assert any("intel.com" in a.target for a in f.actions)


def test_unplugged_and_not_present_devices_are_ignored():
    findings = analyze([dev(45), dev(43, present=False), dev(0)])
    assert [f.severity for f in findings] == [Severity.OK]


def test_disabled_device_is_info_only_and_sorted_after_problems():
    findings = analyze([dev(22, name="停用的"), dev(43, name="壞掉的")])
    assert [f.severity for f in findings] == [Severity.CRITICAL, Severity.INFO]


def test_unknown_code_still_reported():
    [f] = analyze([dev(99)])
    assert f.severity == Severity.WARNING and "99" in f.title


def test_finding_id_is_stable_for_history_diff():
    a = analyze([dev(28)])[0].id
    b = analyze([dev(28)])[0].id
    assert a == b


def test_vendor_lookup():
    assert vendor_of("PCI\\VEN_10DE&DEV_2504") == "NVIDIA"
    assert vendor_of("USB\\VID_8087&PID_0AAA") == "Intel"
    assert vendor_of("ACPI\\PNP0A08") is None


def test_demo_fixture_covers_fault_scenarios():
    result = DevicesCheck().run(load_fixture("devices"))
    assert result.error is None
    sevs = [f.severity for f in result.findings]
    assert sevs.count(Severity.CRITICAL) == 2  # 音效 code 10、USB code 43
    assert Severity.WARNING in sevs and Severity.INFO in sevs


def test_collect_failure_becomes_error_not_crash():
    class Broken(DevicesCheck):
        def collect(self):
            raise PermissionError("拒絕存取")
    result = Broken().run()
    assert result.error and "拒絕存取" in result.error


def test_known_board_puts_board_support_first_for_onboard_devices():
    [f] = analyze([dev(28, "PCI\\VEN_8086&DEV_7A23&SUBSYS_88821043")], ASUS_CTX)
    assert "TUF GAMING B760M-PLUS WIFI" in f.steps[0]
    assert "Intel Chipset" in f.steps[1]
    assert any("asus.com" in a.target for a in f.actions)


def test_board_hint_not_used_for_nvidia_gpu_or_usb():
    [gpu] = analyze([dev(43, "PCI\\VEN_10DE&DEV_2803")], ASUS_CTX)
    assert "NVIDIA" in gpu.steps[0]
    [usb] = analyze([dev(43, "USB\\VID_0000&PID_0002")], ASUS_CTX)
    assert not any("asus.com" in a.target for a in usb.actions)


def test_real_home_pc_all_ok():
    """使用者家裡那台電腦的真實資料（已去識別化）：232 個裝置都正常，不可誤報。"""
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).parent / "data/home/devices.json").read_text(encoding="utf-8"))
    [f] = analyze(raw)
    assert f.severity == Severity.OK and "232" in f.title
