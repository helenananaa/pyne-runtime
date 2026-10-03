"""Native same-ID amendment/cancel witnesses; measured gaps stay explicit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pyne_runtime as pn

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("stop_limit_update_activated", "stop_limit_cancel_resubmit", "stop_limit_repeat_identical")
spec = importlib.util.spec_from_file_location("pending_lifecycle_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


@pytest.mark.parametrize("case", CASES)
def test_native_same_id_lifecycle_witness(case):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(FOLDER, name, capture)
    assert len(capture["rows"]) == 32 and len(capture["columns"]) == 15
    reference = json.loads((FOLDER / "strategy_pyramiding_1.tradingview.json").read_text(encoding="utf-8"))
    assert [r["values"][:6] for r in capture["rows"]] == [r["values"][:6] for r in reference["rows"]]
    for index, row in enumerate(capture["rows"]):
        expected = [1, 1, 0, 300, 0, 0, 1, 0, 0] if case == "stop_limit_repeat_identical" and index >= 9 else [0, 0, 0, None, 0, 0, 0, 0, 0]
        assert row["values"][6:] == expected


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
def test_native_lifecycle_full_column_measurement(case, incremental):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    result = reporter.workload_report(ROOT, name, set(capture["columns"][:6]), incremental)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == set(capture["columns"][6:])
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 288
    for column in result["columns"].values():
        assert column["counts"]["differences"] == len(column["differences"])
    assert all(c["counts"]["differences"] == 0 for c in result["columns"].values())


def assert_native(result, case, count):
    assert result.ok, result.error
    data = json.loads((FOLDER / f"strategy_pending_pyramiding_{case}.tradingview.json").read_text(encoding="utf-8"))
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for column, title in enumerate(data["columns"][6:], 6):
        expected = {r["values"][0]: r["values"][column] for r in data["rows"][:count] if r["values"][column] is not None}
        assert lines.get(title, {}).keys() == expected.keys(), (case, title)
        assert lines.get(title, {}) == pytest.approx(expected, abs=data["tolerance"], rel=0), (case, title)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 3, 4, 8, 9, 10, 32))
def test_native_pending_amendment_prefixes(case, incremental, count):
    name = f"strategy_pending_pyramiding_{case}"
    data = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    script = (FOLDER / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")
    assert_native(pn.run(script, reporter._bars(name, data)[:count], executor_mode="inline"), case, count)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("cut", (2, 3, 8))
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
def test_native_pending_amendment_preview_and_restore(case, cut, mode):
    name = f"strategy_pending_pyramiding_{case}"
    data = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    script = (FOLDER / f"{name}.py").read_text(encoding="utf-8")
    bars = reporter._bars(name, data)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed(bars[:cut])
    before = session.snapshot_portable_state()
    session.on_bar_updated(dict(bars[cut], high=1500, low=1, close=700))
    assert session.snapshot_portable_state() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=script, settings=settings)
    for bar in bars[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result(), case, len(bars))
