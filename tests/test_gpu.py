from pchealth.checks.gpu import NvidiaCheck
from pchealth.model import Severity
from pchealth.runner import load_fixture


def gpu(**kw):
    g = {"name": "NVIDIA GeForce RTX 4060 Ti", "driver_version": "591.86", "temperature.gpu": "40",
         "fan.speed": "0", "power.draw": "15.2", "power.limit": "165.00", "utilization.gpu": "2",
         "memory.used": "900", "memory.total": "8188", "pcie.link.gen.current": "1", "pcie.link.gen.max": "4",
         "pcie.link.width.current": "8", "pcie.link.width.max": "8", "clock_reasons": "0x0000000000000001"}
    g.update(kw)
    return g


def analyze(*gpus, available=True):
    return NvidiaCheck().analyze({"available": available, "gpus": list(gpus)}, {})


def test_healthy_idle_gpu_ok_and_gen1_at_idle_is_not_a_problem():
    [f] = analyze(gpu())
    assert f.severity == Severity.OK and "PCIe x8" in f.title
    assert "停轉是正常" in f.detail  # 風扇 0% 不是故障


def test_reduced_pcie_width_warns_with_reseat_steps():
    [f] = analyze(gpu(**{"pcie.link.width.current": "4"}))
    assert f.severity == Severity.WARNING and "x4" in f.title and "x8" in f.title
    assert "插緊" in f.steps[0]


def test_temperature_thresholds():
    assert analyze(gpu(**{"temperature.gpu": "85", "utilization.gpu": "99"}))[0].severity == Severity.WARNING
    assert analyze(gpu(**{"temperature.gpu": "92", "utilization.gpu": "99"}))[0].severity == Severity.CRITICAL
    assert analyze(gpu(**{"temperature.gpu": "75", "utilization.gpu": "99"}))[0].severity == Severity.OK


def test_hot_while_idle_warns():
    [f] = analyze(gpu(**{"temperature.gpu": "70", "utilization.gpu": "3"}))
    assert "閒置" in f.title


def test_throttle_reasons():
    titles = " ".join(f.title for f in analyze(gpu(clock_reasons="0x0000000000000048")))
    assert "過熱" in titles and "供電" in titles


def test_not_supported_values_do_not_crash():
    [f] = analyze(gpu(**{"fan.speed": "[N/A]", "power.draw": "[Not Supported]"}))
    assert f.severity == Severity.OK


def test_no_nvidia_and_driver_failure():
    assert analyze(available=False)[0].severity == Severity.OK
    assert analyze()[0].severity == Severity.WARNING  # nvidia-smi 在但沒回傳資料


def test_demo_fixture():
    titles = " ".join(f.title for f in NvidiaCheck().run(load_fixture("gpu")).findings)
    assert "x4" in titles and "閒置" in titles
