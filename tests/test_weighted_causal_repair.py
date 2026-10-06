"""Independent exact-window and public continuation checks for weighted state."""
from fractions import Fraction
import inspect
import sys

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepVWMA, _StepWMA
from pyne_runtime.ta import TaModule
from pyne_runtime import _weighted_numeric
from pyne_runtime import ta_kernels


def _rounded(value):
    try:
        return float(value)
    except OverflowError:
        return np.inf if value > 0 else -np.inf


def _wma_reference(source, period):
    result = np.full(len(source), np.nan)
    window, observations, last = [], 0, np.nan
    for index, value in enumerate(source):
        missing = np.isnan(value)
        if not missing:
            last, observations = value, observations + 1
        if np.isnan(last):
            continue
        window = (window + [last])[-period:]
        if missing or observations < period:
            continue
        if np.isposinf(window).any() or np.isneginf(window).any():
            result[index] = np.sum(window)
        else:
            result[index] = _rounded(sum(Fraction(float(v)) * (j + 1)
                for j, v in enumerate(window)) / (period * (period + 1) // 2))
    return result


def _linreg_reference(source, period, offset):
    result = np.full(len(source), np.nan)
    x = [Fraction(j) for j in range(period)]
    mean_x = sum(x) / period
    for index in range(period - 1, len(source)):
        window = source[index-period+1:index+1]
        if not np.isfinite(window).all():
            continue
        ys = [Fraction(float(v)) for v in window]
        mean_y = sum(ys) / period
        slope = (sum((a-mean_x)*(b-mean_y) for a, b in zip(x, ys)) /
            sum((a-mean_x)**2 for a in x)) if period > 1 else 0
        result[index] = _rounded(mean_y + slope * (period - 1 - offset - mean_x))
    return result


@pytest.mark.parametrize("period", [1, 2, 3, 7])
@pytest.mark.parametrize("scale", [1e3, 1e12, 1e20, 1e308, 1e-300])
def test_wma_and_linreg_exact_and_causal_at_every_prefix(period, scale):
    source = np.asarray([1., 2., 3., scale, -scale, 4., np.nan, 5., 6., 7.])
    module = TaModule()
    with np.errstate(over="ignore", invalid="ignore"):
        expected_wma = _wma_reference(source, period)
        expected_linreg = _linreg_reference(source, period, 2)
        full_wma = module.wma(source, period)
        full_linreg = module.linreg(source, period, 2)
        np.testing.assert_array_equal(full_wma, expected_wma)
        np.testing.assert_array_equal(full_linreg, expected_linreg)
        for end in range(1, len(source) + 1):
            np.testing.assert_array_equal(module.wma(source[:end], period), full_wma[:end])
            np.testing.assert_array_equal(module.linreg(source[:end], period, 2), full_linreg[:end])


@pytest.mark.parametrize("first,tail", [(1e16, 1.), (1e6, 1e-10), (1e308, 1e-300)])
@pytest.mark.parametrize("period", [1, 2, 5])
def test_streaming_weighted_windows_recover_without_drift(first, tail, period):
    source = np.asarray([first] + [tail] * 15 + [np.nan, tail, np.nan, tail])
    wma, vwma = _StepWMA(period), _StepVWMA(period)
    actual_wma = np.asarray([wma.update(v) for v in source], dtype=float)
    actual_vwma = np.asarray([vwma.update(v, 1) for v in source], dtype=float)
    np.testing.assert_array_equal(actual_wma, _wma_reference(source, period))
    np.testing.assert_array_equal(actual_vwma, TaModule().vwma(source, period, np.ones(len(source))))


@pytest.mark.parametrize("count,period", [(17, 7), (1100, 1000)])
@pytest.mark.parametrize("scale", [1e12, 1e20, 1e308])
def test_alma_exact_window_and_future_prefix_across_convolution_branch(count, period, scale):
    module = TaModule()
    prefix = np.ones(period)
    source = np.r_[prefix, scale, np.ones(count-period-1)]
    positions = np.arange(period, dtype=float)
    weights = np.exp(-((positions-.85*(period-1))**2)/(2*(period/6)**2))
    weights /= weights.sum()
    reference = np.full(len(source), np.nan)
    for at in range(period - 1, len(source)):
        reference[at] = _rounded(sum(Fraction(float(v)) * Fraction(float(w))
            for v, w in zip(source[at-period+1:at+1], weights)))
    actual = module.alma(source, period)
    np.testing.assert_array_equal(actual, reference)
    for end in (period, period + 1, len(source)):
        np.testing.assert_array_equal(module.alma(source[:end], period), actual[:end])


def _bars(values):
    return [dict(time=i*60, open=v, high=v, low=v, close=v, volume=1)
        for i, v in enumerate(values)]


SCRIPT = '''indicator("Weighted continuation", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("WMA", ctx.ta.wma("w", period=2).update(bar.close))
    ctx.plot("VWMA", ctx.ta.vwma("v", period=2).update(bar.close, bar.volume))
    ctx.plot("HMA", ctx.ta.hma("h", period=5).update(bar.close))
'''


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
@pytest.mark.parametrize("cut", [1, 3, 7])
def test_weighted_preview_and_restored_composition_continue_exactly(mode, cut):
    source = [1e16] + [1.] * 10
    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed(_bars(source[:cut]))
    before = session.snapshot_result()
    session.on_bar_updated(_bars(source)[cut])
    session.on_bar_updated(dict(_bars(source)[cut], close=1e20, high=1e20))
    assert session.snapshot_result() == before
    restored = (pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT)
        if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=SCRIPT))
    for bar in _bars(source)[cut:]:
        restored.on_bar_closed(bar)
    result = restored.snapshot_result()
    wma = _wma_reference(np.asarray(source), 2)
    fast, slow = _wma_reference(np.asarray(source), 2), _wma_reference(np.asarray(source), 5)
    hma = _wma_reference(2 * fast - slow, 2)
    for title, expected in (("WMA", wma), ("VWMA", TaModule().vwma(np.asarray(source), 2, np.ones(11))),
                            ("HMA", hma)):
        actual = next(line["data"] for line in result.lines if line["name"] == title)
        assert [p["value"] for p in actual] == [round(float(v), 8) for v in expected if not np.isnan(v)]


@pytest.mark.parametrize("values,weights", [
    ([0., 0., 0., 0.], [.1, .2]), ([-1., -1., -1.], [.1, .2]),
    ([1e308, 1e308, 1e308], [.5, .5]),
    ([1e308, -1e308, 1e-300, -1e-300], [-.125, .875]),
    ([1., 2., 3., 4.], [-1., -2.]),
])
def test_integer_convolution_signed_offsets_and_exponent_extremes(values, weights):
    expected = [_rounded(sum(Fraction(v) * Fraction(w)
        for v, w in zip(values[at:at+len(weights)], weights)))
        for at in range(len(values)-len(weights)+1)]
    actual = _weighted_numeric.exact_convolution(np.asarray(values), np.asarray(weights))
    np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("count", [1000, 2000, 4000])
def test_weighted_and_regression_convert_each_observation_once(monkeypatch, count):
    calls = 0
    original = _weighted_numeric.scaled_float

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(_weighted_numeric, "scaled_float", counted)
    source = np.resize(np.asarray([1e308, 1e-300, -1e308, 1.]), count)
    TaModule().wma(source, count // 4)
    TaModule().linreg(source, count // 4)
    assert calls == 2 * count


@pytest.mark.parametrize("count", [1000, 2000, 4000])
@pytest.mark.parametrize("linear", [False, True])
def test_trailing_missing_percentile_scans_only_its_affected_window(count, linear):
    source = np.arange(count, dtype=float)
    source[-1] = np.nan
    period = count // 4
    lines, start = inspect.getsourcelines(ta_kernels._rolling_missing_percentile_values)
    outgoing_line = start + next(i for i, line in enumerate(lines)
        if "expired = next(j for j in range" in line)
    filename = inspect.getsourcefile(ta_kernels._rolling_missing_percentile_values)
    visits = 0

    def trace(frame, event, arg):
        nonlocal visits
        if frame.f_code.co_filename != filename:
            return None
        if event == "line" and frame.f_code.co_name == "<genexpr>" and frame.f_lineno == outgoing_line:
            visits += 1
        return trace

    sys.settrace(trace)
    try:
        module = TaModule()
        fn = module.percentile_linear_interpolation if linear else module.percentile_nearest_rank
        actual = fn(source, period, 50)
    finally:
        sys.settrace(None)
    assert visits == period  # Previously (count-period)*period, including unaffected history.
    for end in (period, period + 1, count - 1, count):
        np.testing.assert_array_equal(fn(source[:end], period, 50), actual[:end])


def test_weighted_kernels_preserve_prefix_across_former_rebase_boundaries():
    source = 1e12 + np.arange(4300) % 19
    source[40] = 1e20
    source[170::179] = np.nan
    module = TaModule()
    wma, linreg = module.wma(source, 17), module.linreg(source, 17, 3)
    for end in (17, 40, 41, 4095, 4096, 4097, 4299):
        np.testing.assert_array_equal(module.wma(source[:end], 17), wma[:end])
        np.testing.assert_array_equal(module.linreg(source[:end], 17, 3), linreg[:end])


def test_nonfinite_weighted_windows_recover_with_independent_missing_queues():
    source = np.asarray([1., np.inf, 2., np.nan, 3., -np.inf, 4., 5., 6., 7.])
    weights = np.asarray([1., 1., 0., np.inf, 2., 1., np.nan, 3., 1., 1.])
    with np.errstate(over="ignore", invalid="ignore"):
        wma, vwma = _StepWMA(2), _StepVWMA(2)
        actual_wma = np.asarray([wma.update(v) for v in source], dtype=float)
        actual_vwma = np.asarray([vwma.update(v, w) for v, w in zip(source, weights)], dtype=float)
        np.testing.assert_array_equal(actual_wma, TaModule().wma(source, 2))
        np.testing.assert_allclose(actual_vwma, TaModule().vwma(source, 2, weights), equal_nan=True)
