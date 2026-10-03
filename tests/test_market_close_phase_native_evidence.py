"""Complete native state across prefixes, previews and portable continuation."""
from __future__ import annotations

import json
from pathlib import Path

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("market_update_same_tick", "market_update_same_tick_p2", "stop_limit_to_market_same_tick",
         "stop_limit_to_market_same_tick_p2", "stop_limit_to_market", "market_to_stop_limit_same_tick",
         "market_to_stop_limit_same_tick_p2")


def inputs(case, callback):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    source = (FOLDER / f"{name}{'' if callback else '_batch'}.py").read_text(encoding="utf-8")
    bars = [dict(zip(capture["columns"][:6], row["values"][:6], strict=True)) for row in capture["rows"]]
    return capture, source, bars


def assert_native(result, capture, count):
    assert result.ok, result.error
    lines = {line["name"]: {point["time"]: point["value"] for point in line["data"]} for line in result.lines}
    for column, title in enumerate(capture["columns"][6:], 6):
        expected = {row["values"][0]: row["values"][column] for row in capture["rows"][:count] if row["values"][column] is not None}
        assert set(lines.get(title, {})) == set(expected), title
        assert lines.get(title, {}) == pytest.approx(expected, abs=capture["tolerance"]), title


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("callback", (False, True))
@pytest.mark.parametrize("count", (1, 2, 3, 9, 10, 32))
def test_market_close_phase_native_prefixes(case, callback, count):
    capture, source, bars = inputs(case, callback)
    assert_native(pn.run(source, bars[:count], executor_mode="inline"), capture, count)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("cut", (1, 2, 3, 8, 9))
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
def test_market_close_phase_preview_restore_and_continue(case, cut, mode):
    capture, source, bars = inputs(case, True)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(bars[:cut])
    committed = session.snapshot_portable_state()
    preview = dict(bars[cut], high=2000, low=1, close=1200)
    session.on_bar_updated(preview)
    assert session.snapshot_portable_state() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=source)
    # Snapshots retain confirmed state, not an in-flight preview or its isnew
    # flag. Recreate the same preview on the restored confirmed session.
    restored.on_bar_updated(preview)
    for count, bar in enumerate(bars[cut:], cut + 1):
        assert restored.on_bar_updated(bar) == session.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == session.on_bar_closed(bar)
        assert_native(restored.snapshot_result(), capture, count)
    assert_native(session.snapshot_result(), capture, len(bars))
