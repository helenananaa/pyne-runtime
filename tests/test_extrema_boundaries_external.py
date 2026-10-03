"""Independent native extrema evidence with explicit startup/sort boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime import utils
from pyne_runtime.incremental.ta import _StepExtremeBars, _StepMonotonic
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).parent / "workloads"


def _capture(name):
    return json.loads((ROOT / f"{name}.tradingview.json").read_text(encoding="utf-8"))


def _script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars(count=32):
    return [dict(time=i * 60, open=1., high=2., low=0., close=1., volume=10.) for i in range(count)]


def _assert_result(result, name, count, incremental):
    assert result.ok, result.error
    capture = _capture(name)
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for column, title in enumerate(capture["columns"]):
        if not title.startswith(("Highest", "Lowest", "Linreg")):
            continue  # Percentiles with missing inputs are explicitly reference-only.
        if incremental and title.startswith("Linreg"):
            continue  # No incremental linreg capability is added here.
        expected = {
            row["index"] * 60: row["values"][column]
            for row in capture["rows"][:count]
            if row["values"][column] is not None
        }
        actual = lines.get(title, {})
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=1e-8, rel=0), title


@pytest.mark.parametrize("name, marker, count", (
    ("extrema_order", "PYNE_EXT_ORDER", 32),
    ("extrema_tie_confirmation", "PYNE_EXT_TIE", 32),
    ("percentile_confirmation", "PYNE_PCT_CONFIRM", 24),
))
def test_official_extrema_evidence_identity(name, marker, count):
    capture = _capture(name)
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        text = (ROOT / f"{name}.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode()).hexdigest() == capture[key]
    raw = (ROOT / f"{name}.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(marker + r"\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == capture["rows"]
    assert [row["index"] for row in rows] == list(range(count))
    assert all(len(row["values"]) == len(capture["columns"]) for row in rows)


@pytest.mark.parametrize("name", ("extrema_order", "extrema_tie_confirmation"))
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 3, 5, 8, 10, 14, 19, 24, 28, 32))
def test_extrema_official_prefix(name, incremental, count):
    script = _script(name if incremental else name + "_batch")
    _assert_result(pn.run(script, _bars(count), executor_mode="inline"), name, count, incremental)


@pytest.mark.parametrize("name", ("extrema_order", "extrema_tie_confirmation"))
@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (3, 7, 9, 13, 24))
def test_extrema_preview_and_restore(name, mode, cut):
    script = _script(name)
    settings = pn.PyneSettings(executor_mode="inline")
    original = pn.PyneIncrementalSession(script=script, settings=settings)
    original.seed(_bars(cut))
    committed = original.snapshot_result()
    for shift in (10, 20):
        original.on_bar_updated(dict(_bars()[cut], high=30 + shift, close=10 + shift))
        assert original.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=script, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=script, settings=settings,
        )
    for bar in _bars()[cut:]:
        restored.on_bar_closed(bar)
    _assert_result(restored.snapshot_result(), name, 32, True)


@pytest.mark.parametrize("highest", (False, True))
@pytest.mark.parametrize("period", (1, 2, 3, 5, 17))
def test_extrema_independent_window_arithmetic(highest, period):
    source = np.asarray([None if i % 11 in (4, 5) else float((i // 3) % 4) for i in range(99)], dtype=float)
    expected_values = np.full(len(source), np.nan)
    expected_offsets = np.full(len(source), np.nan)
    last_missing = -1
    for i, value in enumerate(source):
        if np.isnan(value):
            last_missing = i
            if i >= period - 1:
                expected_offsets[i] = 0
            continue
        if i < period - 1:
            continue
        first = max(0, i - period + 1, last_missing + 1)
        window = source[first:i + 1]
        extreme = max(window) if highest else min(window)
        expected_values[i] = extreme
        expected_offsets[i] = first + list(window).index(extreme) - i
    value_fn = utils.highest if highest else utils.lowest
    offset_fn = utils.highestbars if highest else utils.lowestbars
    np.testing.assert_allclose(value_fn(source, period), expected_values, rtol=0, atol=0, equal_nan=True)
    np.testing.assert_allclose(offset_fn(source, period), expected_offsets, rtol=0, atol=0, equal_nan=True)
    value_step = _StepMonotonic(period, highest=highest)
    offset_step = _StepExtremeBars(period, highest=highest)
    values = np.asarray([value_step.update(v) for v in source], dtype=float)
    offsets = np.asarray([offset_step.update(v) for v in source], dtype=float)
    np.testing.assert_allclose(values, expected_values, rtol=0, atol=0, equal_nan=True)
    np.testing.assert_allclose(offsets, expected_offsets, rtol=0, atol=0, equal_nan=True)


def test_native_percentile_normal_inputs_confirm_existing_hazen_and_rank_formulas():
    capture = _capture("percentile_confirmation")
    rows = np.asarray([row["values"] for row in capture["rows"]], dtype=float)
    module = TaModule()
    for index, pct in enumerate((0, 25, 50, 75, 100)):
        np.testing.assert_allclose(module.percentile_nearest_rank(rows[:, 0], 4, pct), rows[:, 2 + index],
                                   rtol=0, atol=1e-8, equal_nan=True)
        np.testing.assert_allclose(module.percentile_linear_interpolation(rows[:, 0], 4, pct), rows[:, 7 + index],
                                   rtol=0, atol=1e-8, equal_nan=True)
    assert rows[3, 8] == -3.5  # Hazen; type-7 interpolation would be -3.25.


def test_missing_percentile_reference_matches_native_order_state():
    rows = np.asarray([row["values"] for row in _capture("percentile_confirmation")["rows"]], dtype=float)
    module = TaModule()
    for method, col in ((module.percentile_nearest_rank, 12), (module.percentile_linear_interpolation, 15)):
        actual = method(rows[:, 1], 4, 25)
        np.testing.assert_allclose(actual, rows[:, col], rtol=0, atol=1e-8, equal_nan=True)
        assert np.isfinite(rows[7, col]) and np.isfinite(rows[8, col])


def test_retained_extrema_startup_contract_is_explicit():
    source = np.asarray([1., 2., 3.])
    np.testing.assert_allclose(utils.highest(source, 3), [np.nan, np.nan, 3.], equal_nan=True)
    np.testing.assert_allclose(utils.lowest(source, 3), [np.nan, np.nan, 1.], equal_nan=True)
    step = _StepMonotonic(3, highest=True)
    assert [step.update(v) for v in source] == [None, None, 3.]
    assert _capture("extrema_order")["rows"][0]["values"][8] is None
