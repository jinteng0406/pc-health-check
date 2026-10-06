from pchealth.checks.devices import DevicesCheck, vendor_of
from pchealth.model import Severity
from pchealth.runner import load_fixture


def dev(code, pnp="PCI\\VEN_1234&DEV_0001", name="測試裝置", present=True):
    return {"Name": name, "PNPClass": None, "Manufacturer": None,
            "ConfigManagerErrorCode": code, "PNPDeviceID": pnp, "Present": present}


def test_all_ok_reports_single_ok_finding():
    findings = DevicesCheck().analyze([dev(0), dev(0)])
    assert len(findings) == 1
    assert findings[0].severity == Severity.OK
    assert "2 個裝置" in findings[0].title


def test_missing_intel_chipset_driver_suggests_intel_software():
    # 實驗室電腦實際遇到的情況：Intel SMBus 控制器錯誤碼 28
    [f] = DevicesCheck().analyze([dev(28, "PCI\\VEN_8086&DEV_A323&SUBSYS_86941043&REV_10\\3&11583659&0&FC",
                                      "SM 匯流排控制器")])
    assert f.severity == Severity.WARNING
    assert "沒有安裝驅動程式" in f.title
    assert "Intel Chipset Device Software" in f.steps[0]
    assert any("intel.com" in a.target for a in f.actions)


def test_unplugged_and_not_present_devices_are_ignored():
    findings = DevicesCheck().analyze([dev(45), dev(43, present=False), dev(0)])
    assert [f.severity for f in findings] == [Severity.OK]


def test_disabled_device_is_info_only_and_sorted_after_problems():
    findings = DevicesCheck().analyze([dev(22, name="停用的"), dev(43, name="壞掉的")])
    assert [f.severity for f in findings] == [Severity.CRITICAL, Severity.INFO]


def test_unknown_code_still_reported():
    [f] = DevicesCheck().analyze([dev(99)])
    assert f.severity == Severity.WARNING and "99" in f.title


def test_finding_id_is_stable_for_history_diff():
    a = DevicesCheck().analyze([dev(28)])[0].id
    b = DevicesCheck().analyze([dev(28)])[0].id
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
