from pchealth import history, updater


def report(ts, *problems):
    return {"timestamp": ts, "results": [{"findings": [
        {"id": pid, "title": pid, "severity": sev} for pid, sev in problems]}]}


def test_diff_reports_new_and_resolved_problems_only():
    prev = report("2026-10-01T10:00:00", ("a", 2), ("b", 3), ("info", 1))
    cur = report("2026-10-06T10:00:00", ("b", 3), ("c", 2), ("info2", 1))
    d = history.diff(prev, cur)
    assert d.new == ["c"] and d.resolved == ["a"]


def test_no_previous_means_no_diff():
    assert history.diff(None, report("t")) is None


def test_save_and_load_latest(tmp_path):
    history.save(report("2026-10-01T10:00:00", ("a", 2)), tmp_path)
    history.save(report("2026-10-06T10:00:00", ("b", 2)), tmp_path)
    assert history.load_latest(tmp_path)["timestamp"] == "2026-10-06T10:00:00"


def test_load_latest_skips_corrupt_files(tmp_path):
    history.save(report("2026-10-01T10:00:00"), tmp_path)
    (tmp_path / "2026-10-09T00-00-00.json").write_text("{壞掉", encoding="utf-8")
    assert history.load_latest(tmp_path)["timestamp"] == "2026-10-01T10:00:00"


def test_version_compare():
    assert updater.is_newer("v0.2.0", "0.1.0")
    assert updater.is_newer("v0.10.0", "0.9.9")
    assert not updater.is_newer("v0.1.0", "0.1.0")
    assert not updater.is_newer("garbage", "0.1.0")
