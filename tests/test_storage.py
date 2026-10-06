from pchealth.checks.storage import StorageCheck
from pchealth.model import Severity
from pchealth.runner import load_fixture

GB = 1024**3


def disk(**kw):
    rel = {"Temperature": 40, "TemperatureMax": 60, "Wear": 2, "PowerOnHours": 1000,
           "ReadErrorsUncorrected": 0, "WriteErrorsUncorrected": 0}
    rel.update(kw.pop("rel", {}))
    d = {"DeviceId": "0", "FriendlyName": "CT1000P3PSSD8", "MediaType": "SSD", "BusType": "NVMe",
         "Size": 1000 * GB, "HealthStatus": "Healthy", "OperationalStatus": "OK", "Reliability": rel}
    d.update(kw)
    return d


def vol(letter="C", size=1000, free=500, health="Healthy"):
    return {"DriveLetter": letter, "Label": "", "FileSystem": "NTFS",
            "Size": size * GB, "SizeRemaining": free * GB, "HealthStatus": health}


def analyze(disks=(), volumes=(), admin=True):
    return StorageCheck().analyze({"Admin": admin, "Disks": list(disks), "Volumes": list(volumes)}, {})


def test_healthy_disk_and_volume_are_ok():
    fs = analyze([disk()], [vol()])
    assert [f.severity for f in fs] == [Severity.OK, Severity.OK]
    assert "磨損 2%" in fs[0].title and "40°C" in fs[0].title


def test_uncorrected_errors_are_critical_and_say_backup():
    [f] = analyze([disk(rel={"ReadErrorsUncorrected": 3})])
    assert f.severity == Severity.CRITICAL and "3 次" in f.title
    assert "備份" in f.steps[0]
    assert any("crucial.com" in a.target for a in f.actions)


def test_wear_thresholds():
    assert analyze([disk(rel={"Wear": 79})])[0].severity == Severity.OK
    assert analyze([disk(rel={"Wear": 85})])[0].severity == Severity.WARNING
    assert analyze([disk(rel={"Wear": 100})])[0].severity == Severity.CRITICAL


def test_temperature_limits_depend_on_disk_type():
    assert analyze([disk(rel={"Temperature": 72})])[0].severity == Severity.WARNING  # NVMe
    hdd = disk(MediaType="HDD", BusType="SATA", rel={"Temperature": 62})
    assert analyze([hdd])[0].severity == Severity.CRITICAL


def test_windows_predictive_failure_is_critical():
    [f] = analyze([disk(OperationalStatus="Predictive Failure")])
    assert f.severity == Severity.CRITICAL and "即將故障" in f.title


def test_no_reliability_without_admin_tells_user_to_accept_uac():
    [f] = analyze([disk(Reliability=None)], admin=False)
    assert f.severity == Severity.INFO and "UAC" in f.steps[0]


def test_no_reliability_with_admin_mentions_controller():
    [f] = analyze([disk(Reliability=None)], admin=True)
    assert "RAID" in f.cause


NVME_SMART = {"smart_status": {"passed": True},
              "nvme_smart_health_information_log": {
                  "critical_warning": 0, "temperature": 38, "available_spare": 100,
                  "available_spare_threshold": 5, "percentage_used": 1, "power_on_hours": 1500,
                  "unsafe_shutdowns": 12, "media_errors": 0},
              "temperature": {"current": 38}, "power_on_time": {"hours": 1500}}


def analyze_smart(smart_json, win_rel=None, **disk_kw):
    d = disk(**disk_kw)
    d["Reliability"] = win_rel
    raw = {"Admin": True, "Disks": [d], "Volumes": [],
           "Smart": {"status": "ok", "disks": {"0": smart_json}}}
    return StorageCheck().analyze(raw, {})


def test_smartctl_fills_the_unknown_error_count():
    [f] = analyze_smart(NVME_SMART, {"Temperature": 38, "Wear": 0})
    assert f.severity == Severity.OK
    assert "錯誤次數未知" not in f.title and "通電 1,500 小時" in f.title
    assert "資料來源：smartctl" in f.detail and "讀寫錯誤：0 次" in f.detail


def test_smartctl_media_errors_and_critical_warning():
    log = NVME_SMART["nvme_smart_health_information_log"] | {"media_errors": 7, "critical_warning": 0x04}
    fs = analyze_smart(NVME_SMART | {"nvme_smart_health_information_log": log})
    titles = " ".join(f.title for f in fs)
    assert "7 次" in titles and "嚴重警告" in titles
    assert all(f.severity == Severity.CRITICAL for f in fs)


def test_temperature_only_critical_warning_is_warning():
    log = NVME_SMART["nvme_smart_health_information_log"] | {"critical_warning": 0x02}
    [f] = analyze_smart(NVME_SMART | {"nvme_smart_health_information_log": log})
    assert f.severity == Severity.WARNING


def test_low_spare():
    log = NVME_SMART["nvme_smart_health_information_log"] | {"available_spare": 4}
    assert analyze_smart(NVME_SMART | {"nvme_smart_health_information_log": log})[0].severity == Severity.CRITICAL


def test_smart_failed_is_critical():
    [f] = analyze_smart(NVME_SMART | {"smart_status": {"passed": False}})
    assert f.severity == Severity.CRITICAL


def test_ata_reallocated_and_pending():
    ata = {"smart_status": {"passed": True}, "temperature": {"current": 35}, "power_on_time": {"hours": 20000},
           "ata_smart_attributes": {"table": [{"id": 5, "raw": {"value": 8}}, {"id": 197, "raw": {"value": 1}}]}}
    fs = analyze_smart(ata, MediaType="HDD", BusType="SATA")
    sevs = {f.id.rsplit(":", 1)[1]: f.severity for f in fs}
    assert sevs == {"pending": Severity.CRITICAL, "reallocated": Severity.WARNING}


def test_smart_missing_values_fall_back_to_windows():
    [f] = analyze_smart({"smart_status": {"passed": True}}, {"Temperature": 44, "Wear": 9})
    assert "磨損 9%" in f.title and "44°C" in f.title


def test_overheat_history():
    def with_log(**kw):
        return NVME_SMART | {"nvme_smart_health_information_log": NVME_SMART["nvme_smart_health_information_log"] | kw}
    [f] = analyze_smart(with_log(warning_temp_time=12, critical_comp_time=0))
    assert f.severity == Severity.INFO and "12 分鐘" in f.title
    assert analyze_smart(with_log(warning_temp_time=300))[0].severity == Severity.WARNING
    [f] = analyze_smart(with_log(warning_temp_time=300, critical_comp_time=5))
    assert "危險溫度" in f.title and f.severity == Severity.WARNING


def test_drive_own_temperature_limit_lowers_threshold():
    j = NVME_SMART | {"temperature": {"current": 72, "op_limit_max": 75}}
    [f] = analyze_smart(j)
    assert f.severity == Severity.WARNING  # 72 ≥ 75-5
    j = NVME_SMART | {"temperature": {"current": 76, "op_limit_max": 75}}
    assert analyze_smart(j)[0].severity == Severity.CRITICAL


def test_smart_output_is_trimmed_to_whitelist(monkeypatch, tmp_path):
    import json as _json
    import subprocess
    from pchealth.checks import smart
    full = {"model_name": "X", "serial_number": "SECRET", "nvme_namespaces": [{"eui64": {"ext_id": 1}}],
            "smartctl": {"version": [7, 5], "argv": ["smartctl"], "exit_status": 0},
            "smart_status": {"passed": True}}

    class Done:
        stdout = _json.dumps(full).encode()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Done())
    data = smart._run(tmp_path / "smartctl.exe", ["-a", "/dev/sda"])
    assert "serial_number" not in data and "nvme_namespaces" not in data
    assert data["smartctl"] == {"version": [7, 5], "exit_status": 0}


def test_smartctl_disk_names():
    from pchealth.checks.smart import device_name
    assert [device_name(i) for i in (0, 1, 25, 26)] == ["/dev/sda", "/dev/sdb", "/dev/sdz", "/dev/sdaa"]


def test_low_space_thresholds():
    assert analyze(volumes=[vol(free=4)])[0].severity == Severity.CRITICAL
    assert analyze(volumes=[vol(free=80)])[0].severity == Severity.WARNING  # 8%
    assert analyze(volumes=[vol(size=100, free=12)])[0].severity == Severity.WARNING  # < 15 GB
    assert analyze(volumes=[vol(free=300)])[0].severity == Severity.OK


def test_tiny_partitions_ignored_and_dirty_volume_flagged():
    assert analyze(volumes=[{**vol(), "Size": 500 * 1024**2, "SizeRemaining": 0}]) == []
    fs = analyze(volumes=[vol(health="Warning")])
    assert any("修復" in f.title for f in fs)


def test_demo_fixture_covers_scenarios():
    fs = StorageCheck().run(load_fixture("storage")).findings
    titles = " ".join(f.title for f in fs)
    for expected in ("無法修復的讀寫錯誤", "額定寫入壽命", "溫度偏高", "空間不足", "需要修復", "健康",
                     "讀不出來", "壞軌"):
        assert expected in titles
