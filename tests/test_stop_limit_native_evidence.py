"""Independent native activation timelines; measure gaps without asserting parity."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pyne_runtime as pn

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("stop_limit_wait_369", "stop_limit_wait_300", "stop_limit_never_activated",
         "stop_limit_gap_then_limit", "stop_limit_short_prior_high", "stop_limit_short_activated_close",
         "stop_limit_long_prior_low", "stop_limit_short_later_high")
spec = importlib.util.spec_from_file_location("stop_limit_native_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def capture(case):
    return json.loads((FOLDER / f"strategy_pending_pyramiding_{case}.tradingview.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case,first,quantity,price", (
    ("stop_limit_wait_369", 6, 6, 369),
    ("stop_limit_wait_300", 9, 6, 300),
    ("stop_limit_never_activated", 32, 0, None),
    ("stop_limit_gap_then_limit", 6, 6, 380),
    ("stop_limit_short_prior_high", 32, 0, None),
    ("stop_limit_short_activated_close", 1, -6, 377),
    ("stop_limit_long_prior_low", 23, 6, 250),
    ("stop_limit_short_later_high", 22, -6, 300),
))
def test_native_activation_and_price_path_witnesses(case, first, quantity, price):
    data = capture(case)
    reporter.verify_evidence(FOLDER, f"strategy_pending_pyramiding_{case}", data)
    assert len(data["rows"]) == 32 and len(data["columns"]) == 15
    for row in data["rows"][:first]:
        assert row["values"][6:] == [0, 0, 0, None, 0, 0, 0, 0, 0]
    sign = -1 if quantity < 0 else 1
    for row in data["rows"][first:]:
        assert row["values"][6:] == [quantity, 3, 0, price, 0, 0, sign, 2*sign, 3*sign]
    reference = json.loads((FOLDER / "strategy_pyramiding_1.tradingview.json").read_text(encoding="utf-8"))
    assert [r["values"][:6] for r in data["rows"]] == [r["values"][:6] for r in reference["rows"]]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
def test_all_native_state_columns_are_measured(case, incremental):
    data = capture(case)
    result = reporter.workload_report(ROOT, f"strategy_pending_pyramiding_{case}", set(data["columns"][:6]), incremental)
    assert result["unmappedOutputColumns"] == [] and result["status"] == "measured"
    assert set(result["columns"]) == set(data["columns"][6:])
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 288
    for column in result["columns"].values():
        assert column["counts"]["differences"] == len(column["differences"])
        assert column["counts"]["differences"] == 0


def assert_native(result, case, count):
    assert result.ok, result.error
    data = capture(case)
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for column, title in enumerate(data["columns"][6:], 6):
        expected = {r["values"][0]: r["values"][column] for r in data["rows"][:count]
                    if r["values"][column] is not None}
        assert lines.get(title, {}).keys() == expected.keys(), (case, title)
        assert lines.get(title, {}) == pytest.approx(expected, abs=data["tolerance"], rel=0), (case, title)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 6, 7, 9, 10, 22, 23, 24, 32))
def test_native_stop_limit_prefixes(case, incremental, count):
    name = f"strategy_pending_pyramiding_{case}"
    source = (FOLDER / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")
    bars = reporter._bars(name, capture(case))[:count]
    assert_native(pn.run(source, bars, executor_mode="inline"), case, count)


@pytest.mark.parametrize("case,cut", (("stop_limit_wait_369", 2), ("stop_limit_wait_300", 8),
                                     ("stop_limit_never_activated", 6), ("stop_limit_gap_then_limit", 6),
                                     ("stop_limit_short_prior_high", 7), ("stop_limit_short_activated_close", 1),
                                     ("stop_limit_long_prior_low", 23), ("stop_limit_short_later_high", 22)))
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
def test_native_activation_preview_and_snapshot_continuation(case, cut, mode):
    name = f"strategy_pending_pyramiding_{case}"
    source = (FOLDER / f"{name}.py").read_text(encoding="utf-8")
    bars = reporter._bars(name, capture(case))
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(bars[:cut])
    before = session.snapshot_result()
    session.on_bar_updated(dict(bars[cut], high=1500, low=1, close=700))
    assert session.snapshot_result() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),
                                                                  script=source, settings=settings)
    for bar in bars[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result(), case, 32)
