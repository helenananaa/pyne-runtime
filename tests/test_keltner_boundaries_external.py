"""Native Keltner widths, source isolation, preview and real snapshot recovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.ta import TaModule

FOLDER = Path(__file__).parent / "workloads"


def oracle():
    return json.loads((FOLDER / "keltner_width_matrix.tradingview.json").read_text())


def source(incremental):
    return (FOLDER / f"keltner_width_matrix{'' if incremental else '_batch'}.py").read_text()


def bars(count=32):
    return [dict(zip(("time", "open", "high", "low", "close", "volume"), row["values"][:6], strict=True))
            for row in oracle()["rows"][:count]]


def assert_native(result, count=32):
    assert result.ok, result.error
    capture = oracle()
    times = [bar["time"] for bar in bars(count)]
    for column, title in enumerate(capture["columns"]):
        if not title.startswith("KC "):
            continue
        expected = {times[i]: row["values"][column] for i, row in enumerate(capture["rows"][:count])
                    if row["values"][column] is not None}
        line = next((line for line in result.lines if line.get("title") == title or line.get("name") == title), {})
        actual = {p["time"]: p["value"] for p in line.get("data", [])}
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=capture["tolerance"], rel=0), title


def test_independent_ema_formula_and_case_metadata_match_native():
    capture = oracle()
    assert len(capture["cases"]) == 15
    pine = (FOLDER / "keltner_width_matrix.pine").read_text()
    for case in capture["cases"]:
        assert f"ta.kc({case['source']},{case['period']},{case['mult']:g},{str(case['useTrueRange']).lower()})" in pine
    for row in capture["rows"]:
        assert row["values"][9::2] == row["values"][10::2]


@pytest.mark.parametrize("incremental", (False, True))
@pytest.mark.parametrize("count", (1, 2, 3, 4, 7, 8, 9, 13, 24, 32))
def test_native_prefixes_in_batch_and_generic_python_callback(incremental, count):
    assert_native(pn.run(source(incremental), bars(count), executor_mode="inline"), count)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (1, 3, 7, 9, 13, 24))
def test_preview_isolation_restore_and_native_continuation(mode, cut):
    script = source(True)
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed(bars(cut))
    committed = session.snapshot_result()
    next_bar = bars(cut + 1)[-1]
    session.on_bar_updated(dict(next_bar, high=next_bar["high"]+10., close=next_bar["high"]+5.))
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),
                                                                   script=script, settings=settings)
    for bar in bars()[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result())


@pytest.mark.parametrize("label,value", (("negative", -1.), ("zero", 0.)))
def test_official_multiplier_rejection_preserves_input_arrays(label, value):
    error = json.loads((FOLDER / f"keltner_invalid_{label}.tradingview-error.json").read_text())
    pine = (FOLDER / f"keltner_invalid_{label}.pine").read_text()
    assert hashlib.sha256(pine.encode()).hexdigest() == error["scriptSha256"]
    assert "It must be > 0." in error["error"]
    high, low, close = (np.asarray(values, dtype=float) for values in ([2, 3, 4], [0, 1, 2], [1, 2, 3]))
    before = [value.copy() for value in (high, low, close)]
    with pytest.raises(ValueError, match="greater than zero"):
        TaModule().keltner(3, value, high, low, close)
    for actual, original in zip((high, low, close), before, strict=True):
        np.testing.assert_array_equal(actual, original)


def test_explicit_atr_retains_old_formula_and_return_shape():
    rows = np.asarray([row["values"] for row in oracle()["rows"]], dtype=float)
    module = TaModule()
    high, low, close = (pn.PyneSeries(rows[:, col]) for col in (2, 3, 4))
    upper, middle, lower = module.keltner(3, 1.5, high, low, close, width_smoothing="atr")
    assert all(isinstance(v, pn.PyneSeries) for v in (upper, middle, lower))
    ema = module.ema(close, 3)
    atr = module.atr(3, high, low, close)
    for actual, expected in ((upper, ema+atr*1.5), (middle, ema), (lower, ema-atr*1.5)):
        np.testing.assert_allclose(actual.values, expected.values, equal_nan=True, rtol=0, atol=0)


@pytest.mark.parametrize("kwargs", ({"width_smoothing": "unknown"}, {"use_true_range": "true"},
                                    {"width_smoothing": "atr", "use_true_range": False},
                                    {"source": np.array([1.])}, {"close": np.array(1.)}))
def test_invalid_options_or_shapes_are_rejected(kwargs):
    params = dict(high=np.array([2., 3.]), low=np.array([0., 1.]), close=np.array([1., 2.]))
    params.update(kwargs)
    with pytest.raises(ValueError):
        TaModule().keltner(3, 1.5, **params)
