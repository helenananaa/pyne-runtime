"""Native pending-order evidence and complete measurement, including known gaps."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pyne_runtime as pn

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("stop_same_tick", "limit_same_tick", "stop_limit_same_tick", "stop_existing_full",
         "stop_staggered", "market_same_tick_control", "stop_seed_same_tick",
         "stop_favorable_same_tick", "stop_seed_favorable_same_tick")
spec = importlib.util.spec_from_file_location("pending_native_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def capture(case):
    return json.loads((FOLDER / f"strategy_pending_pyramiding_{case}.tradingview.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES)
def test_native_timeline_identity_and_input_provenance(case):
    name = f"strategy_pending_pyramiding_{case}"
    data = capture(case)
    reporter.verify_evidence(FOLDER, name, data)
    assert len(data["rows"]) == 32
    assert len(data["columns"]) == 15
    reference = json.loads((FOLDER / "strategy_pyramiding_1.tradingview.json").read_text(encoding="utf-8"))
    assert [row["values"][:6] for row in data["rows"]] == [row["values"][:6] for row in reference["rows"]]
    assert reporter._bars(name, data) == [dict(zip(data["columns"][:6], row["values"][:6], strict=True))
                                          for row in data["rows"]]


@pytest.mark.parametrize("case,first,quantity,average,holdings", (
    ("stop_same_tick", 1, 6, 377, [0, 1, 2, 3]),
    ("limit_same_tick", 6, 6, 369, [0, 1, 2, 3]),
    ("stop_limit_same_tick", 1, 6, 377, [0, 1, 2, 3]),
    ("stop_existing_full", 1, 1, 370, [1, 0, 0, 0]),
    ("stop_staggered", 6, 6, 398, [0, 1, 2, 3]),
    ("market_same_tick_control", 1, 1, 370, [0, 1, 0, 0]),
    ("stop_seed_same_tick", 1, 1, 370, [1, 0, 0, 0]),
    ("stop_favorable_same_tick", 1, 6, 370, [0, 1, 2, 3]),
    ("stop_seed_favorable_same_tick", 1, 1, 370, [1, 0, 0, 0]),
))
def test_independent_native_boundary_witnesses(case, first, quantity, average, holdings):
    rows = capture(case)["rows"]
    assert all(row["values"][6:9] == [0, 0, 0] for row in rows[:first])
    for row in rows[first:]:
        assert row["values"][6] == quantity
        assert row["values"][7] == sum(value > 0 for value in holdings)
        assert row["values"][8:11] == [0, average, 0]
        assert row["values"][11:] == holdings


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
def test_every_state_and_holding_column_is_measured_without_hiding_differences(case, incremental):
    data = capture(case)
    result = reporter.workload_report(ROOT, f"strategy_pending_pyramiding_{case}", set(data["columns"][:6]), incremental)
    assert result["status"] == "measured"
    assert result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == set(data["columns"][6:])
    assert sum(col["counts"]["cells"] for col in result["columns"].values()) == 288
    for col in result["columns"].values():
        assert col["counts"]["cells"] == 32
        assert col["counts"]["differences"] == len(col["differences"])
    if case in ("stop_existing_full", "market_same_tick_control"):
        assert sum(col["counts"]["differences"] for col in result["columns"].values()) == 0


ALIGNED = CASES


def assert_native(result, case, count):
    assert result.ok, result.error
    data = capture(case)
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for column, title in enumerate(data["columns"][6:], 6):
        expected = {row["values"][0]: row["values"][column] for row in data["rows"][:count]
                    if row["values"][column] is not None}
        assert lines.get(title, {}).keys() == expected.keys(), (case, title)
        assert lines.get(title, {}) == pytest.approx(expected, abs=data["tolerance"], rel=0), (case, title)


@pytest.mark.parametrize("case", ALIGNED)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 6, 7, 32))
def test_native_admission_prefixes(case, incremental, count):
    name = f"strategy_pending_pyramiding_{case}"
    source = (FOLDER / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")
    assert_native(pn.run(source, reporter._bars(name, capture(case))[:count], executor_mode="inline"), case, count)


@pytest.mark.parametrize("case", ALIGNED)
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (1, 5))
def test_native_pending_preview_and_snapshot_continuation(case, mode, cut):
    name = f"strategy_pending_pyramiding_{case}"
    source = (FOLDER / f"{name}.py").read_text(encoding="utf-8")
    bars = reporter._bars(name, capture(case))
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(bars[:cut])
    committed = session.snapshot_result()
    session.on_bar_updated(dict(bars[cut], high=bars[cut]["high"]+100, close=bars[cut]["close"]+100))
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),
                                                                  script=source, settings=settings)
    for bar in bars[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result(), case, 32)
