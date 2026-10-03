"""Native cumulative/crossing and OHLCV evidence, with explicit comparison scope."""
from __future__ import annotations

import json
from pathlib import Path

import pyne_runtime as pn
import pytest

FOLDER = Path(__file__).parent / "workloads"
NAMES = ("foundation", "cross_confirmation", "context_foundation")
INPUTS = {"source", "holes", "leading", "empty", "other", "other holes", "zeros",
          "time", "open", "high", "low", "close", "volume", "volume holes"}


def capture(name):
    return json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))


def script(name, incremental=True):
    return (FOLDER / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")


def bars(name, count):
    if name == "context_foundation":
        return [dict(zip(("time", "open", "high", "low", "close", "volume"), row["values"][:6], strict=True))
                for row in capture(name)["rows"][:count]]
    return [dict(time=i * 60, open=1., high=2., low=0., close=1., volume=10.) for i in range(count)]


def assert_official(result, name, count, incremental):
    assert result.ok, result.error
    oracle = capture(name)
    lines = {line["name"]: {point["time"]: point["value"] for point in line["data"]} for line in result.lines}
    times = [bar["time"] for bar in bars(name, count)]
    for column, title in enumerate(oracle["columns"]):
        if title in INPUTS or title.startswith("Formula "):
            continue
        if incremental and name == "foundation" and not title.startswith(("Change", "Cum", "Cross")):
            continue  # No scalar momentum/ROC/nz/shift namespace expansion.
        if incremental and name == "context_foundation" and title not in (
            "ADX 3", "True range", "Volume SMA 3", "Volume SMA holes", "VWAP anchor"):
            continue
        if incremental and title.startswith("Native KC "):
            continue  # No scalar Keltner namespace helper is added.
        first = 2 if title.startswith("Donchian ") else 0
        expected = {times[i]: row["values"][column] for i, row in enumerate(oracle["rows"][:count])
                    if i >= first and row["values"][column] is not None}
        actual = {time: value for time, value in lines.get(title, {}).items() if time in times[first:]}
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=oracle["tolerance"], rel=0), title


def test_cross_independent_formula_controls():
    oracle = capture("cross_confirmation")
    for row in oracle["rows"]:
        assert row["values"][7::2] == row["values"][8::2], row["index"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 3, 8, 13, 24, 32))
def test_foundation_native_prefixes(name, incremental, count):
    assert_official(pn.run(script(name, incremental), bars(name, count), executor_mode="inline"), name, count, incremental)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (1, 7, 9, 13, 24))
def test_foundation_preview_and_restore(name, mode, cut):
    source = script(name)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(bars(name, cut))
    committed = session.snapshot_result()
    preview = bars(name, cut + 1)[-1]
    session.on_bar_updated(dict(preview, close=preview["high"] + 5., high=preview["high"] + 10.,
                                volume=preview["volume"] + 100.))
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=source, settings=settings)
    for bar in bars(name, 32)[cut:]:
        restored.on_bar_closed(bar)
    assert_official(restored.snapshot_result(), name, 32, True)
