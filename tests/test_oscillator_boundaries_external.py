"""Native oscillator evidence with explicitly retained initialization/math boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.ta import TaModule

ROOT = Path(__file__).parent / "workloads"


def _capture(name):
    return json.loads((ROOT / f"{name}.tradingview.json").read_text(encoding="utf-8"))


def _script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars(count=32):
    return [dict(time=i * 60, open=1, high=2, low=0, close=1, volume=10) for i in range(count)]


def _assert_result(result, capture_name, count, incremental=False):
    assert result.ok, result.error
    capture = _capture(capture_name)
    lines = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for col, title in enumerate(capture["columns"]):
        if title in ("source", "holes"):
            continue
        if incremental and title.startswith("CMO"):
            continue  # CMO is explicitly batch-only.
        expected = {
            row["index"] * 60: row["values"][col]
            for row in capture["rows"][:count]
            if row["values"][col] is not None
        }
        actual = lines.get(title, {})
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=1e-8, rel=0), title


@pytest.mark.parametrize("name, marker", (
    ("oscillator_flat", "PYNE_OSC_FLAT"),
    ("oscillator_formula", "PYNE_OSC_FORMULA"),
    ("stoch_transitions", "PYNE_STOCH_TRANS"),
    ("stoch_transitions_v5", "PYNE_STOCH_V5"),
))
def test_native_oscillator_evidence_identity(name, marker):
    capture = _capture(name)
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        raw = (ROOT / f"{name}.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(raw.encode()).hexdigest() == capture[key]
    raw = (ROOT / f"{name}.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(marker + r"\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == capture["rows"]
    assert [row["index"] for row in rows] == list(range(32))
    assert all(len(row["values"]) == len(capture["columns"]) for row in rows)


@pytest.mark.parametrize("workload", ("oscillator_flat", "stoch_transitions"))
@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 3, 6, 10, 14, 19, 25, 32))
def test_oscillator_official_prefix(workload, incremental, count):
    name = workload if incremental else workload + "_batch"
    _assert_result(pn.run(_script(name), _bars(count), executor_mode="inline"), workload, count, incremental)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (8, 13, 18, 24))
def test_stochastic_cached_value_and_extrema_restore(mode, cut):
    script = _script("stoch_transitions")
    settings = pn.PyneSettings(executor_mode="inline")
    original = pn.PyneIncrementalSession(script=script, settings=settings)
    original.seed(_bars(cut))
    committed = original.snapshot_result()
    for shift in (10, 20):
        original.on_bar_updated(dict(_bars()[cut], high=100 + shift, close=30 + shift))
        assert original.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            original.snapshot_state(), script=script, settings=settings,
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=script, settings=settings,
        )
    for bar in _bars()[cut:]:
        restored.on_bar_closed(bar)
    _assert_result(restored.snapshot_result(), "stoch_transitions", 32, True)


def test_cmo_matches_native_independent_branch_and_sum_formula():
    capture = _capture("oscillator_formula")
    rows = np.asarray([row["values"] for row in capture["rows"]], dtype=float)
    module = TaModule()
    np.testing.assert_allclose(module.cmo(rows[:, 0], 3), rows[:, 12], rtol=0, atol=1e-8)
    np.testing.assert_allclose(rows[:, 11], rows[:, 12], rtol=0, atol=0)
    # Neither missing deltas nor a zero denominator may become fabricated CMO.
    assert np.all(np.isnan(module.cmo(np.full(20, 5.0), 3)))
    assert np.all(np.isnan(module.cmo(np.full(20, np.nan), 3)))
    assert len(module.cmo(np.asarray([], dtype=float), 3)) == 0


def test_retained_stochastic_initial_lookback_is_explicit():
    from pyne_runtime.incremental.ta import _StepStoch

    source = np.asarray([-4.0, 3.0, -3.0])
    actual = TaModule().stoch(source, source + 1, source - 1, 3)
    np.testing.assert_allclose(actual, [np.nan, np.nan, 200 / 9], rtol=0, atol=1e-10, equal_nan=True)
    step = _StepStoch(3)
    values = [step.update(v, v + 1, v - 1) for v in source]
    assert values[:2] == [None, None]
    assert values[2] == pytest.approx(200 / 9, abs=1e-10)
    assert _capture("stoch_transitions")["rows"][0]["values"][0] is None
    assert _capture("stoch_transitions")["rows"][1]["values"][0] is None


def test_pine_versions_agree_and_flat_tail_holds_last_stochastic():
    assert _capture("stoch_transitions")["rows"] == _capture("stoch_transitions_v5")["rows"]
    assert all(row["values"][4] == 100 for row in _capture("stoch_transitions")["rows"][18:])


def test_correlation_missing_and_flat_match_native_independent_windows():
    # Semantics 30 replaces the old complete-pair restriction. This retained
    # native witness now qualifies independent windows and ready flat zeros;
    # broader shifted/large-offset conditions remain strict counted gaps.
    rows = np.asarray([row["values"] for row in _capture("oscillator_flat")["rows"]], dtype=float)
    assert rows[3, 8] > 1 and rows[10, 8] > 1
    actual = TaModule().correlation(rows[:, 1], rows[:, 0], 3)
    np.testing.assert_allclose(actual, rows[:, 8], rtol=0, atol=1e-8, equal_nan=True)
    assert actual[3] > 1 and actual[10] > 1
    flat = TaModule().correlation(np.full(32, 5.0), rows[:, 0], 3)
    np.testing.assert_allclose(flat, rows[:, 9], rtol=0, atol=1e-8, equal_nan=True)
