"""Captured missing-value semantics, with explicit high-offset numerical differences."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

ROOT = Path(__file__).parent / "workloads"
CAPTURE = json.loads((ROOT / "rolling_statistics.tradingview.json").read_text(encoding="utf-8"))


def _script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def _bars(count=18):
    sequence = (1, 4, 2, 5, 3, 6, 2, 4)
    return [
        {
            "time": i * 60,
            "open": sequence[i % 8],
            "high": sequence[i % 8] + 1,
            "low": sequence[i % 8] - 1,
            "close": sequence[i % 8],
            "volume": 10,
        }
        for i in range(count)
    ]


def _view(result):
    assert result.ok, result.error
    return {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}


def _assert_result(result, count):
    lines = _view(result)
    for col, title in enumerate(CAPTURE["columns"][3:], 3):
        if title in CAPTURE["referenceOnlyColumns"]:
            continue
        expected = {
            r["index"] * 60: round(r["values"][col], 8)
            for r in CAPTURE["rows"][:count]
            if r["values"][col] is not None
        }
        actual = lines.get(title, {})
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=CAPTURE["tolerance"], rel=0), title
    # Independent centered arithmetic for the deliberately non-parity columns.
    window = []
    variance = {}
    for row in CAPTURE["rows"][:count]:
        value = row["values"][1]
        if value is not None:
            window.append(value + 1e9)
            window = window[-3:]
        if len(window) == 3:
            centered = np.asarray(window) - window[0]
            variance[row["index"] * 60] = float(np.var(centered))
    stdev = {time: round(math.sqrt(value), 8) for time, value in variance.items()}
    assert lines.get("High Variance", {}) == pytest.approx(
        {time: round(value, 8) for time, value in variance.items()}, abs=1e-8, rel=0
    )
    assert lines.get("High Stdev", {}) == pytest.approx(stdev, abs=1e-8, rel=0)


def test_rolling_statistics_capture_identity_and_classified_difference():
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        text = (ROOT / f"rolling_statistics.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode()).hexdigest() == CAPTURE[key]
    raw = (ROOT / "rolling_statistics.tradingview.txt").read_text(encoding="utf-8")
    parsed = [
        {"index": int(m[1]), "values": [None if v == "NaN" else float(v) for v in m[2].split("|")]}
        for m in re.finditer(r"PYNE_STATS\|(\d+)\|([^;]+);", raw)
    ]
    assert parsed == CAPTURE["rows"]
    assert [r["index"] for r in parsed] == list(range(18))
    assert CAPTURE["referenceOnlyColumns"] == ["High Stdev", "High Variance"]
    assert parsed[3]["values"][14] == 128
    assert parsed[3]["values"][7] == pytest.approx(26 / 9)
    for row, bar in zip(parsed, _bars()):
        i = row["index"]
        assert row["values"][:3] == [
            bar["close"],
            None if i in (1, 7, 12) else bar["close"],
            None if i < 3 else bar["close"],
        ]


@pytest.mark.parametrize("mode", ("rolling_statistics", "rolling_statistics_batch"))
@pytest.mark.parametrize("count", (1, 3, 6, 8, 13, 18))
def test_statistics_match_captured_semantics_and_stable_reference(mode, count):
    _assert_result(pn.run(_script(mode), _bars(count), executor_mode="inline"), count)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (2, 7, 13))
def test_statistics_restore_at_observation_boundaries(mode, cut):
    source = _script("rolling_statistics")
    settings = pn.PyneSettings(executor_mode="inline", timeframe="1")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    data = _bars()
    session.seed(data[:cut])
    committed = session.snapshot_result()
    for extra in (10, 50):
        session.on_bar_updated(
            dict(data[cut], close=data[cut]["close"] + extra, high=data[cut]["high"] + 50)
        )
        assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=source, settings=settings
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=source, settings=settings
        )
    assert restored.snapshot_result() == committed
    for bar in data[cut:]:
        restored.on_bar_closed(bar)
    _assert_result(restored.snapshot_result(), 18)


@pytest.mark.parametrize("offset", (0.0, 1e9, 1e12))
@pytest.mark.parametrize("period", (3, 63))
def test_streaming_moments_remain_stable_across_long_missing_windows(offset, period):
    from pyne_runtime.incremental.ta import _StepSMA, _StepStdev, _StepVariance, _StepBOLL, _StepBB

    source = offset + (np.arange(9000) % 11) * 0.25
    source[::17] = np.nan
    sma, sd, variance = _StepSMA(period), _StepStdev(period), _StepVariance(period)
    boll, bb = _StepBOLL(period), _StepBB(period)
    means, deviations, variances, bands, bbands = [], [], [], [], []
    expected_means, expected_variances = [], []
    window = []
    for value in source:
        means.append(sma.update(value))
        deviations.append(sd.update(value))
        variances.append(variance.update(value))
        bands.append(boll.update(value))
        bbands.append(bb.update(value))
        if not math.isnan(value):
            window.append(value)
            window = window[-period:]
        if len(window) < period:
            expected_means.append(np.nan)
            expected_variances.append(np.nan)
        else:
            centered = np.asarray(window) - window[0]
            expected_means.append(window[0] + float(np.mean(centered)))
            expected_variances.append(float(np.var(centered)))
    expected_means = np.asarray(expected_means)
    expected_variances = np.asarray(expected_variances)
    expected_sd = np.sqrt(expected_variances)
    # Compare dispersion independently of the price offset; mean/band rounding
    # is bounded by one representable unit at the tested price magnitude.
    price_tolerance = max(math.ulp(offset + 3), 1e-12)
    np.testing.assert_allclose(
        np.asarray(means, dtype=float), expected_means, rtol=0, atol=price_tolerance, equal_nan=True
    )
    np.testing.assert_allclose(
        np.asarray(variances, dtype=float),
        expected_variances,
        rtol=1e-12,
        atol=1e-12,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        np.asarray(deviations, dtype=float), expected_sd, rtol=1e-12, atol=1e-12, equal_nan=True
    )
    upper, lower = expected_means + 2 * expected_sd, expected_means - 2 * expected_sd
    np.testing.assert_allclose(
        np.asarray(bands, dtype=float),
        np.array([upper, expected_means, lower]).T,
        rtol=0,
        atol=price_tolerance,
        equal_nan=True,
    )
    np.testing.assert_allclose(
        np.asarray(bbands, dtype=float),
        np.array([expected_means, upper, lower]).T,
        rtol=0,
        atol=price_tolerance,
        equal_nan=True,
    )


@pytest.mark.parametrize("mode", ("batch", "incremental"))
def test_public_sma_ratios_reproduce_the_previous_vwma_capture(mode):
    capture = json.loads((ROOT / "trend_volume.tradingview.json").read_text(encoding="utf-8"))
    data = [dict(zip(capture["columns"][:6], row["values"][:6])) for row in capture["rows"]]
    if mode == "batch":
        source = (
            _script("trend_volume_batch")
            + """
plot(ta.sma(holes * volume, 3) / ta.sma(volume, 3), "Native ratio")
plot(ta.sma(holes * missing_weights, 3) / ta.sma(missing_weights, 3), "Custom ratio")
"""
        )
    else:
        source = """
indicator("SMA ratios", mode="incremental")
def init(ctx):
    for name in ("p", "v", "p2", "v2"):
        ctx.ta.sma(name, 3)
def on_bar(ctx, bar):
    i = ctx.bar_index
    holes = None if i in (1, 7, 12) else 10.0 * (i % 4 + 1)
    weight = None if i in (2, 9) else i % 3 + 1.0
    p = ctx.ta.sma("p").update(None if holes is None else holes * bar.volume)
    v = ctx.ta.sma("v").update(bar.volume)
    p2 = ctx.ta.sma("p2").update(None if holes is None or weight is None else holes * weight)
    v2 = ctx.ta.sma("v2").update(weight)
    ctx.plot("Native ratio", None if p is None or v in (None, 0) else p / v)
    ctx.plot("Custom ratio", None if p2 is None or v2 in (None, 0) else p2 / v2)
"""
    actual = _view(pn.run(source, data, executor_mode="inline"))
    for name, column in (("Native ratio", 13), ("Custom ratio", 17)):
        expected = {
            r["values"][0]: round(r["values"][column], 8)
            for r in capture["rows"]
            if r["values"][column] is not None
        }
        assert actual[name].keys() == expected.keys()
        assert actual[name] == pytest.approx(expected, abs=1e-8, rel=0)
