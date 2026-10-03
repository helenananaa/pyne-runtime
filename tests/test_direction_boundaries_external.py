"""Independent valid-transition oracle, with missing-only counterexamples."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime import utils

FOLDER = Path(__file__).parent / "workloads"
NAMES = ("direction_missing", "direction_transition_confirmation")


def capture(name):
    return json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))


def bars(count):
    return [dict(time=i * 60, open=1., high=2., low=0., close=1., volume=10.) for i in range(count)]


def assert_official(result, oracle, count):
    assert result.ok, result.error
    lines = {line["name"]: {point["time"]: point["value"] for point in line["data"]} for line in result.lines}
    for column, title in enumerate(oracle["columns"]):
        if not title.startswith(("Rising ", "Falling ")):
            continue
        expected = {row["index"] * 60: row["values"][column] for row in oracle["rows"][:count]}
        assert lines[title] == expected, title


def test_formula_controls_and_rejected_neutral_missing_hypothesis():
    correct = capture("direction_transition_confirmation")
    rejected = capture("direction_missing")
    assert all(row["values"][6::4] == row["values"][8::4] and row["values"][7::4] == row["values"][9::4]
               for row in correct["rows"])
    assert any(row["values"][6::4] != row["values"][8::4] for row in rejected["rows"])
    assert [row["values"][:6] for row in correct["rows"]] == [row["values"][:6] for row in rejected["rows"]]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("count", (1, 2, 3, 5, 8, 13, 19, 24, 32))
def test_direction_native_prefix(name, count):
    source = (FOLDER / f"{name}_batch.py").read_text(encoding="utf-8")
    assert_official(pn.run(source, bars(count), executor_mode="inline"), capture(name), count)


@pytest.mark.parametrize("period", (1, 3, 7, 31))
@pytest.mark.parametrize("upward", (False, True))
def test_direction_long_observation_window(period, upward):
    rng = np.random.default_rng(701)
    source = rng.integers(-3, 4, 2000).astype(float)
    source[rng.random(len(source)) < 0.3] = np.nan
    observations = deque(maxlen=period)
    expected = []
    for index, value in enumerate(source):
        if index and not np.isnan(value) and not np.isnan(source[index - 1]):
            observations.append(value > source[index - 1] if upward else value < source[index - 1])
        expected.append(len(observations) == period and all(observations))
    fn = utils.rising if upward else utils.falling
    np.testing.assert_array_equal(fn(source, period), expected)


SCRIPT = '''
import numpy as np
from pyne_runtime import utils
indicator("Python direction replay", mode="incremental")
def init(ctx):
    ctx.state("values", [])
def on_bar(ctx, bar):
    i = ctx.bar_index
    wave = [2.,1.,2.,3.,4.,3.,4.,5.,6.,3.,2.,1.][i % 12]
    history = ctx.state("values").value
    history.append(None if i in (5,17,18) else wave)
    value = utils.rising(np.asarray(history, dtype=float), 3)[-1]
    ctx.plot("Rising holes 3", float(value))
'''


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (4, 6, 18))
def test_python_direction_replay_and_preview(mode, cut):
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    session.seed(bars(cut))
    committed = session.snapshot_result()
    session.on_bar_updated(bars(cut + 1)[-1])
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=SCRIPT, settings=settings)
    for bar in bars(32)[cut:]:
        restored.on_bar_closed(bar)
    expected = capture("direction_transition_confirmation")
    column = expected["columns"].index("Rising holes 3")
    actual = next(line for line in restored.snapshot_result().lines if line["name"] == "Rising holes 3")
    assert {point["time"]: point["value"] for point in actual["data"]} == {
        row["index"] * 60: row["values"][column] for row in expected["rows"]}
