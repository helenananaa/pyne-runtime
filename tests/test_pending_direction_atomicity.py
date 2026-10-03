"""Caught direction errors preserve the real ledger and allow continuation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pyne_runtime as pn

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("direction_atomic_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
NAME = "strategy_pending_pyramiding_stop_limit_cancel_direction"
CAPTURE = json.loads((FOLDER / f"{NAME}.tradingview.json").read_text(encoding="utf-8"))
BARS = reporter._bars(NAME, CAPTURE)


def script(callback):
    text = (FOLDER / f"strategy_pending_pyramiding_stop_limit_change_direction{'' if callback else '_batch'}.py").read_text(encoding="utf-8")
    target = next(line for line in text.splitlines() if '.entry("A", ' in line and 'strategy.short' in line)
    if callback:
        replacement = '''    if ctx.bar_index == 2:
        before = pickle.dumps((ctx.strategy._orders, ctx.strategy._pending_orders, ctx.strategy._event_seq))
        budget = repr(ctx._limit_tracker.__dict__)
        try:
            ctx.strategy.entry("A", ctx.strategy.short, qty=2, stop=1000, limit=380)
        except ValueError as error:
            assert "PYNE_STRATEGY_PENDING_DIRECTION_CHANGE" in str(error)
        else:
            raise AssertionError("Pending direction change must fail")
        assert pickle.dumps((ctx.strategy._orders, ctx.strategy._pending_orders, ctx.strategy._event_seq)) == before
        assert repr(ctx._limit_tracker.__dict__) == budget
        ctx.strategy.cancel("A")
        ctx.strategy.entry("A", ctx.strategy.short, qty=2, stop=1000, limit=380)'''
    else:
        replacement = '''before = pickle.dumps((strategy._collector.strategy_orders, strategy._event_seq, strategy._pending_order_operations,
    strategy._collector.strategy_report, strategy._collector.strategy_position))
arrays = {key: value.tobytes() for key, value in strategy.__dict__.items() if isinstance(value, np.ndarray)}
try:
    strategy.entry("A", strategy.short, qty=2, stop=1000, limit=380, when=bar_index == 2)
except ValueError as error:
    assert "PYNE_STRATEGY_PENDING_DIRECTION_CHANGE" in str(error)
else:
    raise AssertionError("Pending direction change must fail")
assert pickle.dumps((strategy._collector.strategy_orders, strategy._event_seq, strategy._pending_order_operations,
    strategy._collector.strategy_report, strategy._collector.strategy_position)) == before
assert {key: value.tobytes() for key, value in strategy.__dict__.items() if isinstance(value, np.ndarray)} == arrays
strategy.cancel("A", when=bar_index == 2)
strategy.entry("A", strategy.short, qty=2, stop=1000, limit=380, when=bar_index == 2)'''
    return 'import pickle\n' + text.replace(target, replacement)


def assert_native(result):
    assert result.ok, result.error
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for column, title in enumerate(CAPTURE["columns"][6:], 6):
        expected = {r["values"][0]: r["values"][column] for r in CAPTURE["rows"] if r["values"][column] is not None}
        assert lines.get(title, {}).keys() == expected.keys(), title
        assert lines.get(title, {}) == pytest.approx(expected, abs=1e-8, rel=0), title


@pytest.mark.parametrize("callback", (False, True))
def test_caught_rejection_preserves_state_and_allows_native_cancel_continuation(callback):
    assert_native(pn.run(script(callback), BARS, executor_mode="inline"))


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (2, 3))
def test_direction_error_recovery_preview_and_restore(mode, cut):
    source = script(True)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(BARS[:cut])
    before = session.snapshot_portable_state()
    session.on_bar_updated(dict(BARS[cut], close=BARS[cut]["open"]))
    assert session.snapshot_portable_state() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=source, settings=settings)
    for bar in BARS[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result())
