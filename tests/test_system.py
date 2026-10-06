from pchealth.checks.boards import brand_of
from pchealth.checks.system import SystemCheck, nvidia_version
from pchealth.model import Severity
from pchealth.runner import load_fixture

BASE = {
    "BoardManufacturer": "ASUSTeK COMPUTER INC.", "BoardProduct": "TUF GAMING B760M-PLUS WIFI",
    "BiosVersion": "1801", "BiosDate": "2025-06-01", "MemoryBytes": 32 * 1024**3,
    "Cpu": "12th Gen Intel(R) Core(TM) i5-12600KF", "OsCaption": "Windows 11", "OsBuild": "26100",
    "LastBoot": "2026-10-05T08:00:00", "Now": "2026-10-06T22:00:00",
    "Gpus": [{"Name": "NVIDIA GeForce RTX 4060 Ti", "DriverVersion": "32.0.15.8157", "DriverDate": "2026-09-01"}],
}


def analyze(**overrides):
    return SystemCheck().analyze(BASE | overrides, {})


def test_healthy_machine_only_overview():
    [f] = analyze()
    assert f.severity == Severity.OK
    assert "ASUS TUF GAMING B760M-PLUS WIFI" in f.title
    assert "581.57" in f.detail  # NVIDIA 版本號換算


def test_old_gpu_driver_is_info_with_nvidia_link():
    fs = analyze(Gpus=[{"Name": "NVIDIA GeForce RTX 4060 Ti", "DriverVersion": "32.0.15.6094",
                        "DriverDate": "2025-08-20"}])
    [old] = [f for f in fs if "驅動" in f.title]
    assert old.severity == Severity.INFO
    assert any("nvidia.com" in a.target for a in old.actions)


def test_long_uptime_mentions_fast_startup():
    [up] = [f for f in analyze(LastBoot="2026-09-01T08:00:00") if f.id == "system:uptime-long"]
    assert "35 天" in up.title and "快速啟動" in up.cause


def test_old_bios_links_board_support_page():
    [bios] = [f for f in analyze(BiosDate="2021-01-01") if f.id == "system:bios-old"]
    assert any("asus.com" in a.target for a in bios.actions)


def test_basic_display_adapter_ignored():
    [f] = analyze(Gpus=[{"Name": "Microsoft Basic Display Adapter", "DriverVersion": "10.0", "DriverDate": "2006-06-21"}])
    assert "顯示卡" not in f.detail


def test_context_gives_board_to_other_checks():
    ctx = SystemCheck().context(BASE)
    assert ctx["board"] == "ASUS TUF GAMING B760M-PLUS WIFI"
    assert ctx["board_support_url"].startswith("https://www.asus.com")


def test_nvidia_version_and_brand_helpers():
    assert nvidia_version("32.0.15.6094") == "560.94"
    assert nvidia_version("garbage") is None
    assert brand_of("Micro-Star International Co., Ltd.")[0] == "MSI"
    assert brand_of("Some OEM") == ("Some OEM", None)


def test_demo_fixture():
    fs = SystemCheck().run(load_fixture("system")).findings
    ids = {f.id.split(":")[1] for f in fs}
    assert {"overview", "gpu-driver-old", "uptime-long", "bios-old"} <= ids
