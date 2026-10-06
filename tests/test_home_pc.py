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


def test_storage_unknown_error_count_is_not_presented_as_zero():
    disks = [f for f in StorageCheck().analyze(load("storage"), {}) if ":disk:" in f.id]
    for f in disks:
        assert "錯誤次數未知" in f.title
        assert "不代表沒有" in f.detail
        assert "最高紀錄" not in f.detail  # 83°C 是硬碟回報的上限值，不是實際到過的溫度
