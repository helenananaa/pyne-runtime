"""Native pivot ties, missing-neighbour stops, warmup and causal confirmation."""
from __future__ import annotations

import json
from pathlib import Path

import pyne_runtime as pn
import pytest

FOLDER = Path(__file__).parent / "workloads"
NAMES = ("conditions_pivot", "pivot_isolated_confirmation", "pivot_formula_confirmation")


def capture(name):
    return json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))


def script(name, incremental=True):
    return (FOLDER / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")


def bars(count):
    return [dict(time=i * 60, open=1., high=2., low=0., close=1., volume=10.) for i in range(count)]


def assert_official(result, name, count):
    assert result.ok, result.error
    oracle = capture(name)
    lines = {line["name"]: {point["time"]: point["value"] for point in line["data"]} for line in result.lines}
    for column, title in enumerate(oracle["columns"]):
        if not title.startswith("Pivot "):
            continue  # rising has a separate unresolved missing-input boundary
        expected = {row["index"] * 60: row["values"][column]
                    for row in oracle["rows"][:count] if row["values"][column] is not None}
        assert lines.get(title, {}) == expected, title


def test_independent_formula_controls_match_native():
    oracle = capture("pivot_formula_confirmation")
    for row in oracle["rows"]:
        assert row["values"][1::2] == row["values"][2::2], row["index"]
    control = capture("pivot_isolated_confirmation")
    native = control["columns"].index("Rising native")
    strict = control["columns"].index("Rising strict formula")
    record = control["columns"].index("Rising record formula")
    assert all(row["values"][native] == row["values"][strict] for row in control["rows"])
    assert any(row["values"][native] != row["values"][record] for row in control["rows"])


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 3, 4, 5, 8, 10, 13, 19, 24, 32))
def test_pivot_native_prefixes(name, incremental, count):
    assert_official(pn.run(script(name, incremental), bars(count), executor_mode="inline"), name, count)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (2, 4, 7, 12, 19))
def test_pivot_preview_and_pending_confirmation_restore(name, mode, cut):
    source = script(name)
    settings = pn.PyneSettings(executor_mode="inline")
    count = len(capture(name)["rows"])
    original = pn.PyneIncrementalSession(script=source, settings=settings)
    original.seed(bars(cut))
    committed = original.snapshot_result()
    for close in (10., 20.):
        original.on_bar_updated(dict(bars(cut + 1)[-1], close=close, high=close + 1))
        assert original.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source, settings=settings)
    for bar in bars(count)[cut:]:
        restored.on_bar_closed(bar)
    assert_official(restored.snapshot_result(), name, count)
