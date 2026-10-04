"""Representable standard deviations must survive unrepresentable variances."""

from decimal import Decimal, localcontext
from fractions import Fraction
import importlib
import math
import random

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepBB, _StepStdev, _StepVariance
from pyne_runtime.ta import TaModule


def _reference(values, period, *, biased=True):
    window, outputs = [], []
    for value in values:
        if not math.isnan(value):
            window.append(Fraction.from_float(float(value)))
            window = window[-period:]
        divisor = period if biased else period - 1
        if len(window) < period or divisor <= 0:
            outputs.append(np.nan)
            continue
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / divisor
        numerator_root = math.isqrt(variance.numerator)
        denominator_root = math.isqrt(variance.denominator)
        if (numerator_root ** 2 == variance.numerator
                and denominator_root ** 2 == variance.denominator):
            # An exact subnormal midpoint must round ties to even. Decimal
            # rounding before float conversion could move it above that tie.
            outputs.append(float(Fraction(numerator_root, denominator_root)))
            continue
        with localcontext() as context:
            context.prec = 100
            root = (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
        outputs.append(float(root))
    return np.asarray(outputs)


@pytest.mark.parametrize("scale", [5e-324, 1e-200, 1e-160, 1e200, 1.7e308])
@pytest.mark.parametrize("period", [2, 3])
def test_extreme_stdev_matches_independent_reference_and_preserves_every_prefix(scale, period):
    source = np.asarray([scale, -scale, np.nan, 0, scale, -scale, 0, 0, 0, scale])
    with np.errstate(all="ignore"):
        expected = _reference(source, period)
        actual = TaModule().stdev(source, period)
        helper = _StepStdev(period)
        streaming = np.asarray([helper.update(value) for value in source], dtype=float)
        np.testing.assert_allclose(actual, expected, rtol=3e-15, atol=0, equal_nan=True)
        np.testing.assert_allclose(streaming, expected, rtol=3e-15, atol=0, equal_nan=True)
        for end in range(1, len(source) + 1):
            np.testing.assert_array_equal(TaModule().stdev(source[:end], period), actual[:end])
    assert np.isfinite(actual[period:]).all()
    assert actual[2] == actual[1] if period == 2 else np.isnan(actual[2])
    assert actual[-2] == 0.0


@pytest.mark.parametrize("scale", [1e-200, 1e200, 1.7e308])
@pytest.mark.parametrize("biased", [True, False])
def test_scaled_stdev_keeps_bias_contract_and_variance_representation(scale, biased):
    source = [scale, -scale, scale, -scale]
    helper = _StepStdev(2, biased=biased)
    actual = np.asarray([helper.update(value) for value in source], dtype=float)
    np.testing.assert_allclose(actual, _reference(source, 2, biased=biased), rtol=3e-15, atol=0)
    variance = _StepVariance(2, biased=biased)
    variance.update(scale)
    result = variance.update(-scale)
    assert result == 0.0 if scale < 1 else result == math.inf
    if biased:
        with np.errstate(all="ignore"):
            batch = TaModule().variance(np.asarray(source), 2)
        assert batch[-1] == result


@pytest.mark.parametrize("value", [2e-162, 3e-162, math.sqrt(math.ulp(0.0))])
def test_dividing_a_subnormal_variance_to_zero_still_retains_finite_stdev(value):
    helper = _StepStdev(2)
    assert helper.update(0.0) is None
    assert helper.update(value) == value / 2
    assert TaModule().stdev(np.asarray([0.0, value]), 2)[-1] == value / 2


@pytest.mark.parametrize("units", [1, 3, 5])
def test_subnormal_standard_deviation_midpoints_round_ties_to_even(units):
    source = np.asarray([0.0, units * math.ulp(0.0)])
    expected = float(Fraction.from_float(float(source[-1])) / 2)
    helper = _StepStdev(2)
    helper.update(source[0])
    assert helper.update(source[-1]) == expected
    assert TaModule().stdev(source, 2)[-1] == expected


@pytest.mark.parametrize("biased", [True, False])
def test_subnormal_variance_sqrt_avoids_normalization_double_rounding(biased):
    rng = random.Random(20261004)
    for exponent in (-1074, -1000, -700, -512):
        source = np.asarray([math.ldexp(rng.uniform(-1.0, 1.0), exponent)
                             if index % 11 else np.nan for index in range(72)])
    expected = _reference(source, 7, biased=biased)
    helper = _StepStdev(7, biased=biased)
    streaming = np.asarray([helper.update(value) for value in source], dtype=float)
    np.testing.assert_array_equal(streaming, expected)
    if biased:
        np.testing.assert_array_equal(TaModule().stdev(source, 7), expected)


def test_sample_stdev_distinguishes_largest_finite_result_from_true_overflow():
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    finite = _StepStdev(3, biased=False)
    assert [finite.update(value) for value in [-largest, largest, 0.0]][-1] == largest
    overflowing = _StepStdev(2, biased=False)
    assert [overflowing.update(value) for value in [-largest, largest]][-1] == math.inf


@pytest.mark.parametrize("scale", [1e-200, 1e200])
@pytest.mark.parametrize("count", [500, 1000, 2000])
def test_extreme_batch_stdev_work_is_linear(monkeypatch, scale, count):
    kernels = importlib.import_module("pyne_runtime.ta_kernels")
    original, work = kernels._window_sums, 0

    def counted(values, period):
        nonlocal work
        work += len(values)
        return original(values, period)

    monkeypatch.setattr(kernels, "_window_sums", counted)
    source = np.resize(np.asarray([scale, -scale]), count)
    with np.errstate(all="ignore"):
        result = TaModule().stdev(source, count // 4)
    assert np.isfinite(result[count // 4 - 1:]).all()
    assert 0 < work <= 6 * count


@pytest.mark.parametrize("scale", [1e-200, 1e200])
def test_extreme_streaming_stdev_scans_window_only_once(monkeypatch, scale):
    module = importlib.import_module("pyne_runtime.incremental.ta")
    original, scans = module._scaled_float, 0

    def counted(value):
        nonlocal scans
        scans += 1
        return original(value)

    monkeypatch.setattr(module, "_scaled_float", counted)
    helper = _StepStdev(100)
    actual = [helper.update(scale if index % 2 else -scale) for index in range(1000)]
    assert actual[:99] == [None] * 99
    np.testing.assert_allclose(actual[99:], scale, rtol=3e-15, atol=0)
    assert scans == helper.period


@pytest.mark.parametrize("scale", [1e-200, 1e200])
def test_bollinger_bands_use_the_same_scaled_stdev(scale):
    source = np.asarray([scale, -scale, scale, -scale])
    with np.errstate(all="ignore"):
        mid, upper, lower = TaModule().bb(source, 2, .25)
    helper = _StepBB(2, .25)
    actual = np.asarray([helper.update(value) for value in source], dtype=float)
    np.testing.assert_allclose(actual[:, 0], mid, rtol=3e-15, atol=0)
    np.testing.assert_allclose(actual[:, 1], upper, rtol=3e-15, atol=0)
    np.testing.assert_allclose(actual[:, 2], lower, rtol=3e-15, atol=0)
    assert upper[-1] == pytest.approx(scale * .25, rel=3e-15, abs=0)
    assert lower[-1] == pytest.approx(-scale * .25, rel=3e-15, abs=0)


SCRIPT = '''indicator("Scaled stdev", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Stdev", ctx.ta.stdev("sd", 2).update(bar.close))
    mid, upper, lower = ctx.ta.bb("bb", 2, .25).update(bar.close)
    ctx.plot("Upper", upper)
'''


@pytest.mark.parametrize("scale", [1e-200, 1e200])
@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_public_extreme_stdev_preview_isolation_and_same_version_continuation(scale, mode):
    def bar(index, value):
        return dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)

    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed([bar(0, scale)])
    before = session.snapshot_portable_state()
    session.on_bar_updated(bar(1, -scale))
    assert session.snapshot_portable_state() == before
    session.on_bar_updated(bar(1, 0))
    assert session.snapshot_portable_state() == before
    session.on_bar_closed(bar(1, -scale))
    stdev = next(line for line in session.snapshot_result().lines if line["name"] == "Stdev")
    assert stdev["data"][-1]["value"] == scale
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=SCRIPT)
    for index, value in enumerate([scale, 0, -scale, scale], start=2):
        next_bar = bar(index, value)
        session.on_bar_updated(next_bar)
        restored.on_bar_updated(next_bar)
        assert restored.on_bar_closed(next_bar) == session.on_bar_closed(next_bar)
    assert restored.snapshot_result() == session.snapshot_result()


@pytest.mark.parametrize("scale", [1e-200, 1e200])
def test_public_extreme_stdev_batch_incremental_parity(scale):
    bars = [dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)
            for index, value in enumerate([scale, -scale, scale, -scale])]
    report = pn.run_incremental_parity(
        batch_script='''indicator("Scaled stdev")
plot(ta.stdev(close, 2), "Stdev")
mid, upper, lower = ta.bb(close, 2, .25)
plot(upper, "Upper")
''', incremental_script=SCRIPT, bars=bars,
        normalizer=lambda result: [result.values("Stdev"), result.values("Upper")])
    report.assert_ok()
    assert report.incremental_result.values("Stdev")[-1] == scale
