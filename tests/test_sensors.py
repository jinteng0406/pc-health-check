from pchealth.checks.sensors import SensorsCheck
from pchealth.model import Severity
from pchealth.runner import load_fixture


def cpu(temp=45.0, load=5.0, fans=(900.0,)):
    sensors = [{"HardwareType": "Cpu", "Name": "CPU Package", "Type": "Temperature", "Value": temp},
               {"HardwareType": "Cpu", "Name": "CPU Total", "Type": "Load", "Value": load}]
    sensors += [{"HardwareType": "SuperIO", "Name": f"Fan #{i}", "Type": "Fan", "Value": v} for i, v in enumerate(fans, 1)]
    return {"Sensors": sensors}


def analyze(**raw):
    base = {"Days": 30, "FirmwareLimit": [], "PawnIO": "Running", "Admin": True, "LhmBundled": True, "Lhm": cpu()}
    return {f.id: f for f in SensorsCheck().analyze(base | raw, {})}


def test_without_pawnio_explains_and_warns_about_anticheat():
    fs = analyze(PawnIO=None, Lhm=None)
    assert set(fs) == {"sensors:no-driver", "sensors:no-limit"}
    f = fs["sensors:no-driver"]
    assert f.severity == Severity.INFO  # 不知道溫度，不能顯示成「正常」
    assert "FACEIT" in f.cause and "不會自行安裝" in f.detail
    assert fs["sensors:no-limit"].severity == Severity.OK


def test_healthy_cpu():
    fs = analyze()
    assert fs["sensors:ok"].severity == Severity.OK and "45°C" in fs["sensors:ok"].title


def test_cpu_temperature_thresholds():
    assert analyze(Lhm=cpu(temp=88, load=100))["sensors:cpu-hot"].severity == Severity.WARNING
    assert analyze(Lhm=cpu(temp=97, load=100))["sensors:cpu-hot"].severity == Severity.CRITICAL
    assert "sensors:ok" in analyze(Lhm=cpu(temp=78, load=100))  # 高負載 78°C 正常


def test_idle_hot_cpu():
    f = analyze(Lhm=cpu(temp=72, load=3))["sensors:cpu-idle-hot"]
    assert f.severity == Severity.WARNING and "閒置" in f.title


def test_hot_cpu_with_all_fans_stopped():
    fs = analyze(Lhm=cpu(temp=90, load=100, fans=(0.0, 0.0)))
    assert "sensors:fans-stopped" in fs


def test_firmware_limit_thermal_reason_and_merge_per_processor():
    events = [{"Time": "2026-10-04T21:13:10", "Data": {"Number": str(i), "CapDurationInSeconds": "184", "TpcChanges": "3"}}
              for i in range(16)]
    f = analyze(FirmwareLimit=events)["sensors:firmware-limit"]
    assert "1 次" in f.title and "溫度過高" in f.title  # 16 個邏輯處理器的紀錄合併成 1 次
    assert "184 秒" in f.detail and f.severity == Severity.INFO


def test_firmware_limit_many_is_warning():
    events = [{"Time": f"2026-09-{d:02d}T20:00:00", "Data": {"PpcChanges": "1"}} for d in range(1, 12)]
    f = analyze(FirmwareLimit=events)["sensors:firmware-limit"]
    assert f.severity == Severity.WARNING and "供電" in f.title


def test_pawnio_present_but_problems():
    assert "sensors:need-admin" in analyze(Admin=False)
    assert "sensors:no-lhm" in analyze(LhmBundled=False)
    assert "sensors:lhm-error" in analyze(Lhm=None, LhmError="RuntimeError: x")
    assert "sensors:no-cpu-temp" in analyze(Lhm={"Sensors": [{"HardwareType": "Cpu", "Name": "CPU Total",
                                                                "Type": "Load", "Value": 3}]})


def test_demo_fixture():
    fs = {f.id: f for f in SensorsCheck().run(load_fixture("sensors")).findings}
    assert set(fs) == {"sensors:cpu-idle-hot", "sensors:firmware-limit"}
    assert "3 次" in fs["sensors:firmware-limit"].title
    assert "CPU Fan 612 RPM" in fs["sensors:cpu-idle-hot"].detail
