"""Future observations must not change existing rolling statistics or trades."""

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepVariance
from pyne_runtime.ta import TaModule


@pytest.mark.parametrize("source", [
    [1, 2, 3, 1e10, 4, 5, 6],
    [1, 2, 3, 1e20, 4, 5, 6],
    [1e12 + 1, 1e12 + 2, 1e12 + 3, 0, 1e12 + 4, 1e12 + 5],
    [5, 5, 5, 1e20, 5, 5, 5],
    [np.nan, 1, 2, np.nan, 3, 1e20, 4, np.nan, 5, 6],
])
@pytest.mark.parametrize("period", [2, 3])
def test_statistics_preserve_prefix_and_recover_after_scale_changes(source, period):
    source = np.asarray(source, dtype=float)
    module = TaModule()
    full = {
        "variance": module.variance(source, period),
        "stdev": module.stdev(source, period),
        "correlation": module.correlation(source, source, period),
    }
    for end in range(period, len(source) + 1):
        prefix = source[:end]
        np.testing.assert_array_equal(module.variance(prefix, period), full["variance"][:end])
        np.testing.assert_array_equal(module.stdev(prefix, period), full["stdev"][:end])
        np.testing.assert_array_equal(
            module.correlation(prefix, prefix, period), full["correlation"][:end])

    expected, window = [], []
    for value in source:
        if not np.isnan(value):
            window.append(value)
            window = window[-period:]
        expected.append(np.var(np.asarray(window) - window[0]) if len(window) == period else np.nan)
    np.testing.assert_allclose(full["variance"], expected, rtol=1e-12, atol=1e-12)
    helper = _StepVariance(period)
    incremental = np.asarray([helper.update(value) for value in source], dtype=float)
    np.testing.assert_allclose(incremental, expected, rtol=1e-12, atol=1e-12)


def test_statistics_are_causal_across_rebase_block_boundaries():
    source = 1e12 + (np.arange(4300) % 17) * .25
    source[300:340] = 0
    source[1000::97] = np.nan
    module = TaModule()
    full = module.variance(source, 31)
    full_correlation = module.correlation(source, source, 31)
    for end in (31, 301, 341, 4095, 4096, 4120, 4299):
        np.testing.assert_array_equal(module.variance(source[:end], 31), full[:end])
        np.testing.assert_array_equal(
            module.correlation(source[:end], source[:end], 31), full_correlation[:end])


def test_correlation_recovers_two_distinct_series_after_opposite_extremes():
    first = np.asarray([1, 2, 3, 1e20, 4, 5, 6], dtype=float)
    second = np.asarray([3, 4, 5, -1e20, 6, 7, 8], dtype=float)
    module = TaModule()
    full = module.correlation(first, second, 2)
    np.testing.assert_allclose(full[1:], [1, 1, -1, -1, 1, 1])
    for end in range(2, len(first) + 1):
        np.testing.assert_array_equal(
            module.correlation(first[:end], second[:end], 2), full[:end])


def test_future_extreme_bar_cannot_erase_a_previous_strategy_entry():
    def bars(values):
        return [dict(time=i * 10, open=v, high=v, low=v, close=v, volume=1)
                for i, v in enumerate(values)]

    script = '''strategy("Causal entry")
strategy.entry_when((bar_index == 1) & (ta.variance(close, 2) > .1),
                    "Long", strategy.long, qty=1, price=close)
plot(strategy.position_size, "Position")
'''
    prefix = pn.run(script, bars([1, 2, 3]), executor_mode="inline")
    extended = pn.run(script, bars([1, 2, 3, 1e10]), executor_mode="inline")
    assert prefix.ok and extended.ok
    assert prefix.values("Position") == [0, 1, 1]
    assert extended.values("Position")[:3] == prefix.values("Position")


@pytest.mark.parametrize("count", [500, 1000, 2000])
def test_extreme_finite_variance_fallback_has_linear_work_and_finite_output(monkeypatch, count):
    import importlib

    module = importlib.import_module("pyne_runtime.ta_kernels")
    work = 0
    original = module._window_sums

    def counted(values, period):
        nonlocal work
        work += len(values)
        return original(values, period)

    monkeypatch.setattr(module, "_window_sums", counted)
    source = np.resize(np.asarray([1e154, -1e154]), count)
    period = count // 4
    with np.errstate(over="ignore", invalid="ignore"):
        values = TaModule().variance(source, period)
    expected = (1 - ((period % 2) / period) ** 2) * 1e308
    assert np.isfinite(values[period - 1:]).all()
    np.testing.assert_allclose(values[period - 1:], expected, rtol=1e-14)
    assert work <= 6 * count


def test_streaming_extreme_finite_variance_survives_intermediate_overflow():
    helper = _StepVariance(4)
    values = [helper.update(value) for value in [1e154, -1e154] * 10]
    assert values[:3] == [None, None, None]
    np.testing.assert_allclose(values[3:], 1e308, rtol=1e-14)


def test_underflowing_streaming_variance_initializes_exact_state_only_once(monkeypatch):
    import importlib

    module = importlib.import_module("pyne_runtime.incremental.ta")
    scans = 0
    original = module._scaled_float

    def counted(value):
        nonlocal scans
        scans += 1
        return original(value)

    monkeypatch.setattr(module, "_scaled_float", counted)
    helper = _StepVariance(100)
    values = [helper.update((1 + i % 2) * 1e-200) for i in range(1000)]
    assert values[:99] == [None] * 99
    assert values[99:] == [0.0] * 901
    assert scans == helper.period
