from __future__ import annotations

from collections import deque as StandardDeque
import importlib
import math
from typing import Any

import numpy as np

import pyne_runtime.state as state_module
import pyne_runtime.utils as utils
from pyne_runtime.request.lower_tf import LowerTimeframeSeries
from pyne_runtime.series import PyneSeries
from pyne_runtime.state import PyneVar
from pyne_runtime.ta import TaModule


lower_tf_module = importlib.import_module("pyne_runtime.request.lower_tf")
ta_module = importlib.import_module("pyne_runtime.ta")


def test_stdev_and_variance_match_present_observation_window_reference() -> None:
    source = np.array([1.0, 2.0, np.nan, 4.0, 8.0, np.inf, 32.0, 16.0, 3.0, 2.0])
    period = 3

    expected_biased = np.full(len(source), np.nan)
    expected_unbiased = np.full(len(source), np.nan)
    present = []
    for index, value in enumerate(source):
        if not np.isnan(value):
            present.append(value)
        if len(present) >= period:
            with np.errstate(invalid="ignore"):
                expected_biased[index] = np.var(present[-period:])
                expected_unbiased[index] = np.var(present[-period:], ddof=1)
    expected_stdev = np.sqrt(expected_biased)

    module = TaModule()
    stdev = np.asarray(module.stdev(source, period))
    biased = np.asarray(module.variance(source, period, biased=True))
    unbiased = np.asarray(module.variance(source, period, biased=False))

    _assert_same_missing_and_values(stdev, expected_stdev)
    _assert_same_missing_and_values(biased, expected_biased)
    _assert_same_missing_and_values(unbiased, expected_unbiased)
    assert np.all(np.isnan(module.variance(source, 1, biased=False)))

    from pyne_runtime.incremental.ta import _StepVariance, _StepStdev

    for helper, expected in ((_StepStdev(period), expected_stdev),
                             (_StepVariance(period), expected_biased),
                             (_StepVariance(period, biased=False), expected_unbiased)):
        actual = np.asarray([helper.update(value) for value in source], dtype=float)
        _assert_same_missing_and_values(actual, expected)


def test_correlation_remains_stable_for_large_offsets_and_missing_windows() -> None:
    rng = np.random.default_rng(20260719)
    period = 31
    noise_a = rng.standard_normal(2_000)
    noise_b = 0.45 * noise_a + rng.standard_normal(2_000)
    source_a = 1.0e12 + noise_a
    source_b = -7.0e11 + noise_b
    source_a[300] = np.nan
    source_b[1_100] = np.nan

    expected = _rolling_correlation_reference(source_a, source_b, period)
    actual = np.asarray(TaModule().correlation(source_a, source_b, period))

    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected))
    np.testing.assert_allclose(actual, expected, rtol=5e-7, atol=5e-7, equal_nan=True)
    assert np.nanmax(np.abs(actual)) <= 1.0


def test_rolling_moment_work_is_bounded_by_chunks(monkeypatch) -> None:
    calls = 0
    original = ta_module._window_sums

    def counted(values: np.ndarray, period: int) -> np.ndarray:
        nonlocal calls
        calls += 1
        return original(values, period)

    monkeypatch.setattr(ta_module, "_window_sums", counted)
    rng = np.random.default_rng(7)
    source_a = rng.standard_normal(20_000)
    source_b = rng.standard_normal(20_000)
    source_a[::997] = np.nan

    module = TaModule()
    module.stdev(source_a, 200)
    module.variance(source_a, 200, biased=False)
    module.correlation(source_a, source_b, 200)

    # Three moments per variance call and six per correlation call, once per chunk.
    assert 0 < calls <= 100


def test_vwma_matches_independent_observation_windows_with_nan_and_infinity() -> None:
    source = np.array([1.0, np.nan, 3.0, np.inf, 5.0, 6.0, 7.0, 8.0])
    volume = np.array([1.0, 1.0, 0.0, 1.0, 1.0, np.nan, -1.0, 1.0])
    period = 2
    expected = np.full(len(source), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        for index in range(period - 1, len(source)):
            products = (source * volume)[:index + 1]
            weights = volume[:index + 1]
            products = products[~np.isnan(products)][-period:]
            weights = weights[~np.isnan(weights)][-period:]
            if len(products) == period and len(weights) == period:
                denominator = np.sum(weights)
                if denominator > 0.0:
                    expected[index] = np.sum(products) / denominator

    actual = np.asarray(TaModule().vwma(source, period, volume))

    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected))
    np.testing.assert_allclose(actual, expected, equal_nan=True)

    from pyne_runtime.incremental.ta import _StepVWMA

    step = _StepVWMA(period)
    observed = [step.update(value, weight) for value, weight in zip(source, volume)]
    np.testing.assert_allclose(
        [np.nan if value is None else value for value in observed], expected, equal_nan=True)


def test_rolling_nansum_recovers_after_finite_cumulative_overflow() -> None:
    maximum = np.finfo(np.float64).max
    source = np.array([maximum, maximum, 1.0, 1.0, -maximum, -maximum, 2.0, 2.0])
    period = 2
    with np.errstate(over="ignore", invalid="ignore"):
        expected = np.asarray(
            [np.nansum(source[start : start + period]) for start in range(len(source) - 1)]
        )

    actual = ta_module._rolling_nansum(source, period)

    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected))
    np.testing.assert_allclose(actual, expected)

    # Exact fallback retains small residuals that a whole-series cumulative sum
    # would erase after adding and removing maximum-magnitude finite values.
    cancellation = np.array([1.0, maximum, -maximum, 0.75])
    assert ta_module._rolling_nansum(cancellation, 4)[0] == 1.75


def test_extrema_preserve_warmup_nan_and_most_recent_tie_semantics() -> None:
    source = np.array([np.nan, 3.0, 3.0, 1.0, np.nan, 3.0, 3.0, 2.0])
    period = 3

    highest, highest_bars = _extreme_reference(source, period, highest=True)
    lowest, lowest_bars = _extreme_reference(source, period, highest=False)

    _assert_same_missing_and_values(np.asarray(utils.highest(source, period)), highest)
    _assert_same_missing_and_values(np.asarray(utils.lowest(source, period)), lowest)
    _assert_same_missing_and_values(
        np.asarray(utils.highestbars(source, period)),
        highest_bars,
    )
    _assert_same_missing_and_values(
        np.asarray(utils.lowestbars(source, period)),
        lowest_bars,
    )


def test_extrema_deque_operations_grow_linearly(monkeypatch) -> None:
    class CountingDeque(StandardDeque):
        operations = 0

        def append(self, value: Any) -> None:
            type(self).operations += 1
            super().append(value)

        def pop(self) -> Any:
            type(self).operations += 1
            return super().pop()

        def popleft(self) -> Any:
            type(self).operations += 1
            return super().popleft()

    monkeypatch.setattr(utils, "deque", CountingDeque)
    source = np.sin(np.arange(20_000, dtype=np.float64) / 17.0)

    for operation in (utils.highest, utils.lowest, utils.highestbars, utils.lowestbars):
        CountingDeque.operations = 0
        operation(source, 5_000)
        assert CountingDeque.operations <= 2 * len(source)


def test_rising_and_falling_match_strict_transition_reference() -> None:
    source = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 4.0, 3.0, 2.0, 2.0, 1.0])
    period = 3

    expected_rising = _direction_reference(source, period, rising=True)
    expected_falling = _direction_reference(source, period, rising=False)

    np.testing.assert_array_equal(utils.rising(source, period), expected_rising)
    np.testing.assert_array_equal(utils.falling(source, period), expected_falling)


def test_wma_and_linreg_match_window_references_with_missing_values() -> None:
    rng = np.random.default_rng(20260720)
    source = 1.0e12 + rng.normal(size=2_000)
    source[317] = np.nan
    period = 41
    module = TaModule()

    weights = np.arange(1, period + 1, dtype=np.float64)
    expected_wma = _rolling_reference(
        source,
        period,
        lambda window: np.dot(window, weights) / weights.sum(),
    )
    expected_linreg = _rolling_linreg_reference(source, period, offset=3)

    actual_wma = np.asarray(module.wma(source, period))
    actual_linreg = np.asarray(module.linreg(source, period, offset=3))
    np.testing.assert_array_equal(np.isnan(actual_wma), np.isnan(expected_wma))
    np.testing.assert_allclose(actual_wma, expected_wma, rtol=1e-14, atol=5e-4)
    np.testing.assert_array_equal(np.isnan(actual_linreg), np.isnan(expected_linreg))
    np.testing.assert_allclose(actual_linreg, expected_linreg, rtol=1e-12, atol=5e-4)


def test_weighted_and_regression_work_is_bounded_by_rebase_chunks(monkeypatch) -> None:
    calls = 0
    original = ta_module.np.dot

    def counted(left: np.ndarray, right: np.ndarray) -> Any:
        nonlocal calls
        calls += 1
        return original(left, right)

    monkeypatch.setattr(ta_module.np, "dot", counted)
    source = np.sin(np.arange(20_000, dtype=np.float64) / 13.0)
    module = TaModule()

    module.wma(source, 5_000)
    module.linreg(source, 5_000, offset=2)

    assert calls <= 8


def test_wma_and_linreg_seed_does_not_call_np_dot(monkeypatch) -> None:
    """Weighted seed must not dispatch through np.dot (BLAS thread storm)."""
    kernels = importlib.import_module("pyne_runtime.ta_kernels")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("np.dot must not be used on the weighted seed path")

    rng = np.random.default_rng(20260909)
    source = 1.0e12 + rng.normal(size=256)
    source[17] = np.nan
    source[64] = np.inf
    source[65] = -np.inf
    module = TaModule()
    period = 32
    weights = np.arange(1, period + 1, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        expected_wma = _rolling_reference(
            source,
            period,
            lambda window: np.dot(window, weights) / weights.sum(),
        )
        expected_linreg = _rolling_linreg_reference(source, period, offset=7)
    # Compute the independent reference before forbidding only the runtime path.
    monkeypatch.setattr(kernels.np, "dot", forbidden)
    actual_wma = np.asarray(module.wma(source, period))
    actual_linreg = np.asarray(module.linreg(source, period, offset=7))
    np.testing.assert_array_equal(np.isnan(actual_wma), np.isnan(expected_wma))
    np.testing.assert_allclose(actual_wma, expected_wma, rtol=1e-14, atol=5e-4, equal_nan=True)
    np.testing.assert_array_equal(np.isnan(actual_linreg), np.isnan(expected_linreg))
    np.testing.assert_allclose(
        actual_linreg, expected_linreg, rtol=1e-12, atol=5e-4, equal_nan=True
    )


def test_pivots_match_causal_confirmation_reference() -> None:
    source = np.array([1.0, 3.0, 2.0, 3.0, 1.0, np.nan, 5.0, 4.0, 2.0, -1.0, 2.0])
    left = 2
    right = 1

    expected_high = _pivot_reference(source, left, right, highest=True)
    expected_low = _pivot_reference(source, left, right, highest=False)

    _assert_same_missing_and_values(
        np.asarray(utils.pivothigh(source, left, right)),
        expected_high,
    )
    _assert_same_missing_and_values(
        np.asarray(utils.pivotlow(source, left, right)),
        expected_low,
    )


def test_pivot_deque_operations_grow_linearly(monkeypatch) -> None:
    class CountingDeque(StandardDeque):
        operations = 0

        def append(self, value: Any) -> None:
            type(self).operations += 1
            super().append(value)

        def pop(self) -> Any:
            type(self).operations += 1
            return super().pop()

        def popleft(self) -> Any:
            type(self).operations += 1
            return super().popleft()

    monkeypatch.setattr(utils, "deque", CountingDeque)
    source = np.sin(np.arange(20_000, dtype=np.float64) / 17.0)

    for operation in (utils.pivothigh, utils.pivotlow):
        CountingDeque.operations = 0
        operation(source, 2_500, 2_499)
        assert CountingDeque.operations <= 2 * len(source)


def test_ema_large_period_seeds_without_a_complete_contiguous_window() -> None:
    source = np.arange(20_000, dtype=np.float64)
    source[::4_999] = np.nan

    result = ta_module._ema_skip_leading_na(source, 5_000)
    # There is never a run of 5,000 present samples. Pine still seeds from
    # samples 1..5001 excluding 4999, then advances across later gaps.
    assert np.isnan(result[:5001]).all()
    np.testing.assert_allclose(result[5001], ((5001 * 5002 / 2) - 4999) / 5000)
    assert np.isnan(result[9998])
    assert np.isfinite(result[9999:14997]).all()


def test_alma_fft_path_matches_weighted_window_reference(monkeypatch) -> None:
    rng = np.random.default_rng(19)
    source = rng.normal(size=3_000)
    period = 400
    offset = 0.73
    sigma = 5.5
    m = offset * (period - 1)
    s = period / sigma
    positions = np.arange(period, dtype=np.float64)
    weights = np.exp(-((positions - m) ** 2) / (2 * s * s))
    weights /= weights.sum()
    expected = _rolling_reference(
        source,
        period,
        lambda window: np.dot(window, weights),
    )
    fft_calls = 0
    original = ta_module.np.fft.rfft

    def counted(*args: Any, **kwargs: Any) -> np.ndarray:
        nonlocal fft_calls
        fft_calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(ta_module.np.fft, "rfft", counted)

    actual = np.asarray(TaModule().alma(source, period, offset, sigma))

    assert fft_calls >= 2
    np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-11, equal_nan=True)


def test_mad_cci_and_percentiles_match_window_references() -> None:
    rng = np.random.default_rng(23)
    source = 1.0e9 + rng.normal(size=500)
    source[117] = np.nan
    period = 37
    module = TaModule()

    expected_dev = _rolling_reference(
        source,
        period,
        lambda window: np.mean(np.abs(window - np.mean(window))),
    )
    actual_dev = np.asarray(module.dev(source, period))
    np.testing.assert_array_equal(np.isnan(actual_dev), np.isnan(expected_dev))
    np.testing.assert_allclose(actual_dev, expected_dev, rtol=2e-7, atol=2e-7)

    expected_cci = np.full(len(source), np.nan)
    for index in range(period - 1, len(source)):
        window = source[index - period + 1 : index + 1]
        if np.any(np.isnan(window)):
            continue
        mean = float(np.mean(window))
        mad = float(np.mean(np.abs(window - mean)))
        expected_cci[index] = (source[index] - mean) / (0.015 * mad) if mad else 0.0
    actual_cci = np.asarray(module.cci(source, period))
    np.testing.assert_array_equal(np.isnan(actual_cci), np.isnan(expected_cci))
    np.testing.assert_allclose(actual_cci, expected_cci, rtol=2e-7, atol=5e-5)

    percentile_source = rng.integers(-5, 8, size=500).astype(np.float64)
    percentile_source[211] = np.nan
    for percentage in (0.0, 17.0, 50.0, 83.0, 100.0):
        expected_nearest = _rolling_reference(
            percentile_source,
            period,
            lambda window, pct=percentage: np.sort(window)[
                max(int(np.ceil(pct / 100.0 * period)), 1) - 1
            ],
        )
        expected_linear = _rolling_reference(
            percentile_source,
            period,
            lambda window, pct=percentage: np.percentile(
                window,
                pct,
                method="hazen",
            ),
        )
        _assert_same_missing_and_values(
            np.asarray(
                module.percentile_nearest_rank(
                    percentile_source,
                    period,
                    percentage,
                )
            ),
            expected_nearest,
        )
        _assert_same_missing_and_values(
            np.asarray(
                module.percentile_linear_interpolation(
                    percentile_source,
                    period,
                    percentage,
                )
            ),
            expected_linear,
        )


def test_order_statistic_updates_grow_linearly(monkeypatch) -> None:
    calls = 0
    original = ta_module._FenwickTree.add

    def counted(self: Any, index: int, count: int, value: float) -> None:
        nonlocal calls
        calls += 1
        original(self, index, count, value)

    monkeypatch.setattr(ta_module._FenwickTree, "add", counted)
    source = np.sin(np.arange(20_000, dtype=np.float64) / 29.0)
    module = TaModule()

    for operation in (
        lambda: module.dev(source, 5_000),
        lambda: module.cci(source, 5_000),
        lambda: module.percentile_nearest_rank(source, 5_000, 75),
        lambda: module.percentile_linear_interpolation(source, 5_000, 75),
    ):
        calls = 0
        operation()
        assert calls <= 2 * len(source)


def test_percentile_infinity_semantics_match_numpy_hazen() -> None:
    source = np.array([1.0, np.inf, 3.0, -np.inf, 5.0, 6.0, np.nan, 8.0])
    period = 3
    module = TaModule()
    for percentage in (0.0, 25.0, 50.0, 75.0, 100.0):
        expected = _rolling_reference(
            source,
            period,
            lambda window, pct=percentage: np.percentile(
                window,
                pct,
                method="hazen",
            ),
        )
        actual = np.asarray(module.percentile_linear_interpolation(source, period, percentage))
        _assert_same_missing_and_values(actual, expected)


def test_order_statistics_preserve_far_history_and_zero_weight_edges() -> None:
    module = TaModule()
    source = np.array([1_000_000_000.0, 0.0025, 0.0025001])

    np.testing.assert_allclose(module.dev(source, 2)[-1], 5.0e-8, rtol=2e-12)
    np.testing.assert_allclose(
        module.cci(source, 2)[-1],
        66.66666666637755,
        rtol=1e-12,
    )
    assert module.cci(np.array([2.0, 3.0]), 1).tolist() == [0.0, 0.0]

    hazen_edge = np.asarray(
        module.percentile_linear_interpolation(
            np.array([1.0, np.inf]),
            2,
            25,
        )
    )
    assert np.isnan(hazen_edge[-1])

    alma_source = np.array([np.inf] + [1.0] * 99)
    alma_edge = np.asarray(module.alma(alma_source, 100, 0.85, 1000.0))
    assert np.isnan(alma_edge[-1])


def test_set_each_numeric_path_avoids_per_item_missing_checks(monkeypatch) -> None:
    calls = 0
    original = state_module.is_na_value

    def counted(value: Any) -> bool:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(state_module, "is_na_value", counted)
    source = np.arange(20_000, dtype=np.float64)
    source[::7] = np.nan
    result = PyneVar("trend", 3.0).set_each(PyneSeries(source, name="updates"))

    assert isinstance(result, PyneSeries)
    assert result.name == "trend"
    assert calls <= 2
    expected = _carry_forward_reference(source, 3.0)
    np.testing.assert_array_equal(result.values, expected)


def test_set_each_object_values_keep_the_fallback_semantics() -> None:
    source = np.array([None, "up", None, "down", None], dtype=object)

    result = PyneVar("trend", "flat").set_each(source)

    assert list(result) == ["flat", "up", "up", "down", "down"]
    assert result.dtype == object


def test_lower_tf_numeric_cache_reuses_one_flattening_pass(monkeypatch) -> None:
    groups = (
        (1.0, np.nan, 2.0),
        (),
        (None, "4.0", 5.0),
    )
    lower = LowerTimeframeSeries(groups, name="lower")
    calls = 0
    original = lower_tf_module.is_na_value

    def counted(value: Any) -> bool:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(lower_tf_module, "is_na_value", counted)

    np.testing.assert_allclose(lower.sum(default=0).values, [3.0, 0.0, 9.0])
    np.testing.assert_allclose(lower.min(default=-1).values, [1.0, -1.0, 4.0])
    np.testing.assert_allclose(lower.max(default=-1).values, [2.0, -1.0, 5.0])
    np.testing.assert_allclose(lower.avg(default=0).values, [1.5, 0.0, 4.5])

    assert lower.groups == groups
    assert tuple(lower) == groups
    assert calls <= sum(len(group) for group in groups) + 4
    assert lower._numeric_cache is not None
    assert all(not values.flags.writeable for values in lower._numeric_cache)


def _rolling_reference(
    source: np.ndarray,
    period: int,
    operation: Any,
) -> np.ndarray:
    result = np.full(len(source), np.nan)
    for index in range(period - 1, len(source)):
        window = source[index - period + 1 : index + 1]
        if not np.any(np.isnan(window)):
            with np.errstate(invalid="ignore", over="ignore"):
                result[index] = operation(window)
    return result


def _rolling_correlation_reference(
    source_a: np.ndarray,
    source_b: np.ndarray,
    period: int,
) -> np.ndarray:
    result = np.full(min(len(source_a), len(source_b)), np.nan)
    for index in range(period - 1, len(result)):
        a_window = source_a[index - period + 1 : index + 1]
        b_window = source_b[index - period + 1 : index + 1]
        if np.any(np.isnan(a_window)) or np.any(np.isnan(b_window)):
            continue
        if np.std(a_window) == 0.0 or np.std(b_window) == 0.0:
            continue
        result[index] = np.corrcoef(a_window, b_window)[0, 1]
    return result


def _rolling_linreg_reference(
    source: np.ndarray,
    period: int,
    *,
    offset: int,
) -> np.ndarray:
    result = np.full(len(source), np.nan)
    x = np.arange(period, dtype=np.float64)
    x_mean = float(np.mean(x))
    denominator = float(np.sum((x - x_mean) ** 2))
    target = float(period - 1 - offset)
    for index in range(period - 1, len(source)):
        window = source[index - period + 1 : index + 1]
        if np.any(np.isnan(window)):
            continue
        mean = float(np.mean(window))
        slope = float(np.sum((x - x_mean) * (window - mean)) / denominator)
        result[index] = mean + slope * (target - x_mean)
    return result


def _pivot_reference(
    source: np.ndarray,
    left: int,
    right: int,
    *,
    highest: bool,
) -> np.ndarray:
    result = np.full(len(source), np.nan)
    for index in range(0, len(source) - right):
        window = source[max(index - left, 0) : index + right + 1]
        if np.isnan(source[index]):
            continue
        target = np.nanmax(window) if highest else np.nanmin(window)
        if source[index] == target and np.sum(window == target) == 1:
            result[index + right] = source[index]
    return result


def _extreme_reference(
    source: np.ndarray,
    period: int,
    *,
    highest: bool,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.full(len(source), np.nan)
    offsets = np.full(len(source), np.nan)
    for index in range(len(source)):
        start = max(0, index - period + 1)
        window = source[start : index + 1]
        if np.all(np.isnan(window)):
            continue
        target = np.nanmax(window) if highest else np.nanmin(window)
        matches = np.flatnonzero(window == target)
        match = int(matches[-1])
        values[index] = target
        offsets[index] = float(match - (len(window) - 1))
    return values, offsets


def _direction_reference(source: np.ndarray, period: int, *, rising: bool) -> np.ndarray:
    result = np.zeros(len(source), dtype=bool)
    for index in range(period, len(source)):
        window = source[index - period : index + 1]
        if np.any(np.isnan(window)):
            continue
        differences = np.diff(window)
        result[index] = bool(np.all(differences > 0 if rising else differences < 0))
    return result


def _carry_forward_reference(source: np.ndarray, initial: float) -> np.ndarray:
    result = np.empty(len(source), dtype=np.float64)
    current = initial
    for index, value in enumerate(source):
        if not math.isnan(value):
            current = value
        result[index] = current
    return result


def _assert_same_missing_and_values(actual: np.ndarray, expected: np.ndarray) -> None:
    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected))
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12, equal_nan=True)
