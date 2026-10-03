"""Native live-slot admission, partial closure and independent ledger arithmetic."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("0", "1", "2", "3", "orders_confirmation")
spec = importlib.util.spec_from_file_location("pyramiding_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def capture(case):
    return json.loads((FOLDER / f"strategy_pyramiding_{case}.tradingview.json").read_text())


def bars(case, count=32):
    return [dict(zip(("time", "open", "high", "low", "close", "volume"), row["values"][:6], strict=True))
            for row in capture(case)["rows"][:count]]


def source(case, incremental):
    return (FOLDER / f"strategy_pyramiding_{case}{'' if incremental else '_batch'}.py").read_text()


def assert_native(result, case, count=32):
    assert result.ok, result.error
    data = capture(case)
    for column, title in enumerate(data["columns"][6:], 6):
        expected = {bar["time"]: row["values"][column]
                    for bar, row in zip(bars(case, count), data["rows"][:count], strict=True)
                    if row["values"][column] is not None}
        line = next((line for line in result.lines if line.get("title") == title or line.get("name") == title), {})
        observed = {point["time"]: point["value"] for point in line.get("data", [])}
        assert observed.keys() == expected.keys(), (case, title)
        assert observed == pytest.approx(expected, abs=data["tolerance"], rel=0), (case, title)


@pytest.mark.parametrize("case", CASES)
def test_native_identity_and_complete_output_measurement(case):
    data = capture(case)
    reporter.verify_evidence(FOLDER, f"strategy_pyramiding_{case}", data)
    assert len(data["rows"]) == 32
    for incremental in (False, True):
        report = reporter.workload_report(ROOT, f"strategy_pyramiding_{case}", set(data["columns"][:6]), incremental)
        assert report["unmappedOutputColumns"] == []
        assert len(report["columns"]) == len(data["columns"])-6
        assert sum(column["counts"]["differences"] for column in report["columns"].values()) == 0


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 3, 5, 7, 9, 14, 16, 19, 20, 21, 32))
def test_official_prefixes_and_live_trade_slots(case, incremental, count):
    assert_native(pn.run(source(case, incremental), bars(case, count), executor_mode="inline"), case, count)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (5, 19))
def test_preview_and_restored_live_slot_continuation(case, mode, cut):
    script = source(case, True)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed(bars(case, cut))
    committed = session.snapshot_result()
    next_bar = bars(case, cut+1)[-1]
    session.on_bar_updated(dict(next_bar, close=next_bar["close"]+100, high=next_bar["high"]+100))
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),
                                                                   script=script, settings=settings)
    for bar in bars(case)[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result(), case)


@pytest.mark.parametrize("case", ("2", "3", "orders_confirmation"))
@pytest.mark.parametrize("incremental", (False, True))
def test_partial_lot_average_and_equity_from_independent_live_ledger(case, incremental):
    count = 20 if case != "orders_confirmation" else 8
    result = pn.run(source(case, incremental), bars(case, count), executor_mode="inline")
    assert result.ok, result.error
    report = result.output["strategy"]
    lots = report["opentrades"]
    quantity = sum(trade["qty"] for trade in lots)
    last_close = bars(case, count)[-1]["close"]
    average = sum(trade["qty"]*trade["entry_price"] for trade in lots)/quantity
    profit = sum(trade["qty"]*(last_close-trade["entry_price"])*(-1 if trade["side"] == "short" else 1)
                 for trade in lots)
    assert report["summary"]["openprofit"] == pytest.approx(profit, abs=1e-7, rel=0)
    assert report["summary"]["equity"] == pytest.approx(1e9+report["summary"]["netprofit"]+profit, abs=1e-6, rel=0)
    # The next native bar reports this bar's settled fills before new commands.
    next_native = capture(case)["rows"][count]["values"]
    assert average == pytest.approx(next_native[9], abs=1e-8, rel=0)
    assert quantity == next_native[6]
