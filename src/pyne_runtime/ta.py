"""
Pyne Technical Analysis — Pine-style ``ta.*`` function library.

All functions accept and return numpy arrays. They can be freely
composed and nested::

    ta.ema(ta.rsi(close, 14), 10)   # smooth RSI with EMA
    ta.bb(ta.ema(close, 20), 20, 2) # Bollinger Bands on EMA

The module is injected as ``ta`` in the script namespace. Functions
that need OHLCV data (like ``atr``, ``tr``, ``obv``) receive a
reference to the runtime context so they can implicitly access
global high/low/close/volume when called without explicit arguments.

Usage::

    # In user scripts — ta is already available
    plot(ta.sma(close, 20), title="SMA 20")
    dif, dea, hist = ta.macd(close)
    mid, upper, lower = ta.bb(close, 20, 2)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from . import utils
from .collections import PyneArray
from .series import PyneSeries, to_numpy, wrap_like
from .ta_kernels import (
    _ROLLING_REBASE_CHUNK,
    _FenwickTree as _FenwickTree,
    _broadcast_pivot_types,
    _broadcast_ta_input,
    _fixnan,
    _pivot_level_values,
    _rolling_linear_regression_values,
    _rolling_mean_and_mad,
    _rolling_nansum as _rolling_nansum,
    _rolling_nonmissing_sum,
    _rolling_percentile_values,
    _rolling_weighted_average_values,
    _valid_boolean_correlation,
    _valid_weighted_convolution,
    _window_sums as _window_sums,
)
from .values import is_na_value

if TYPE_CHECKING:
    from .context import PyneContext


def _rolling_variance_values(source: np.ndarray, period: int, ddof: int) -> np.ndarray:
    """Compute full-window variance in O(n) with periodically rebased centered moments."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n or period - ddof <= 0:
        return result

    if period == 1:
        # A finite singleton has exact population variance zero. Rebasing and
        # subtracting moments can introduce future-dependent floating residues.
        result[np.isfinite(values)] = 0.0
        return result

    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        valid = np.isfinite(segment)
        if not np.any(valid):
            continue

        # Rebasing keeps the cumulative moments small even for 1e12-scale inputs.
        anchor = float(np.mean(segment[valid]))
        centered = np.where(valid, segment - anchor, 0.0)
        counts = _window_sums(valid.astype(np.int64), period)
        sums = _window_sums(centered, period)
        squared_sums = _window_sums(centered * centered, period)
        numerator = squared_sums - sums * sums / period
        np.maximum(numerator, 0.0, out=numerator)
        variances = numerator / (period - ddof)
        variances[counts != period] = np.nan
        result[output_start:output_stop] = variances
    return result


def _rolling_nonmissing_variance_values(source: np.ndarray, period: int, ddof: int) -> np.ndarray:
    """Run the stable variance kernel on present observations and restore time positions."""
    values = np.asarray(source, dtype=np.float64)
    present = ~np.isnan(values)
    if np.all(present):
        return _rolling_variance_values(values, period, ddof)
    compact_result = _rolling_variance_values(values[present], period, ddof)
    result = np.full(len(values), np.nan)
    counts = np.cumsum(present)
    seen = counts > 0
    result[seen] = compact_result[counts[seen] - 1]
    return result


def _rolling_full_window_correlation_values(
    source_a: np.ndarray,
    source_b: np.ndarray,
    period: int,
) -> np.ndarray:
    """Compute rolling Pearson correlation using periodically rebased moments."""
    a = np.asarray(source_a, dtype=np.float64)
    b = np.asarray(source_b, dtype=np.float64)
    n = min(len(a), len(b))
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result
    if period == 1:
        result[np.isfinite(a[:n]) & np.isfinite(b[:n])] = 0.0
        return result

    a = a[:n]
    b = b[:n]
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        a_segment = a[segment_start:output_stop]
        b_segment = b[segment_start:output_stop]
        valid = np.isfinite(a_segment) & np.isfinite(b_segment)
        if not np.any(valid):
            continue

        a_anchor = float(np.mean(a_segment[valid]))
        b_anchor = float(np.mean(b_segment[valid]))
        a_centered = np.where(valid, a_segment - a_anchor, 0.0)
        b_centered = np.where(valid, b_segment - b_anchor, 0.0)
        counts = _window_sums(valid.astype(np.int64), period)
        a_sums = _window_sums(a_centered, period)
        b_sums = _window_sums(b_centered, period)
        a_squared_sums = _window_sums(a_centered * a_centered, period)
        b_squared_sums = _window_sums(b_centered * b_centered, period)
        product_sums = _window_sums(a_centered * b_centered, period)

        a_m2 = a_squared_sums - a_sums * a_sums / period
        b_m2 = b_squared_sums - b_sums * b_sums / period
        covariance = product_sums - a_sums * b_sums / period
        np.maximum(a_m2, 0.0, out=a_m2)
        np.maximum(b_m2, 0.0, out=b_m2)
        with np.errstate(divide="ignore", invalid="ignore"):
            correlations = covariance / np.sqrt(a_m2 * b_m2)
        invalid = (counts != period) | (a_m2 <= 0.0) | (b_m2 <= 0.0)
        correlations[invalid] = np.nan
        zero = ((counts == period) & np.isfinite(a_m2) & np.isfinite(b_m2)
                & ((a_m2 == 0.0) | (b_m2 == 0.0)))
        correlations[zero] = 0.0
        np.clip(correlations, -1.0, 1.0, out=correlations)
        result[output_start:output_stop] = correlations
    return result


def _rolling_correlation_values(
    source_a: np.ndarray,
    source_b: np.ndarray,
    period: int,
) -> np.ndarray:
    """Use independent present-observation moments, with stable coherent windows.

    Missing observations advance x, y and x*y windows independently. Their
    means can therefore describe different bars and produce values outside
    [-1, 1]. A full finite calendar window retains the centered Pearson kernel.
    """
    n = min(len(source_a), len(source_b))
    a = np.asarray(source_a, dtype=np.float64)[:n]
    b = np.asarray(source_b, dtype=np.float64)[:n]
    result = _rolling_full_window_correlation_values(a, b, period)
    if period <= 0 or period > n or (not np.any(np.isnan(a)) and not np.any(np.isnan(b))):
        return result

    finite_a, finite_b = a[np.isfinite(a)], b[np.isfinite(b)]
    if not len(finite_a) or not len(finite_b):
        return result
    anchor_a, anchor_b = finite_a[0], finite_b[0]
    pair_present = ~np.isnan(a) & ~np.isnan(b)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        centered_a, centered_b = a - anchor_a, b - anchor_b
        pair_a = np.where(pair_present, centered_a, np.nan)
        pair_b = np.where(pair_present, centered_b, np.nan)
        mean_a = _rolling_nonmissing_sum(centered_a, period) / period
        mean_b = _rolling_nonmissing_sum(centered_b, period) / period
        pair_mean_a = _rolling_nonmissing_sum(pair_a, period) / period
        pair_mean_b = _rolling_nonmissing_sum(pair_b, period) / period
        pair_product = _rolling_nonmissing_sum(pair_a * pair_b, period) / period
        # Expand E[xy] - E[x]E[y] around fixed anchors. The correction terms
        # preserve independent observation windows without subtracting 1e24
        # raw products to recover a small covariance.
        numerator = (pair_product - mean_a * mean_b
                     + anchor_a * (pair_mean_b - mean_b)
                     + anchor_b * (pair_mean_a - mean_a))
        if period == 1:
            # A one-observation variance is exactly zero. Subtracting rebased
            # floating moments can otherwise leave a tiny, history-dependent
            # residual and turn a zero denominator into a huge coefficient.
            variance_a = np.where(np.isfinite(_rolling_nonmissing_sum(a, 1)), 0.0, np.nan)
            variance_b = np.where(np.isfinite(_rolling_nonmissing_sum(b, 1)), 0.0, np.nan)
        else:
            variance_a = _rolling_nonmissing_variance_values(a, period, ddof=0)
            variance_b = _rolling_nonmissing_variance_values(b, period, ddof=0)
        denominator = np.sqrt(variance_a) * np.sqrt(variance_b)
        independent = numerator / denominator
        independent[(denominator == 0.0) & (numerator == 0.0)] = 0.0
        independent[(denominator == 0.0) & (numerator != 0.0)] = np.nan

    coherent = np.zeros(n, dtype=bool)
    coherent[period - 1:] = _window_sums((np.isfinite(a) & np.isfinite(b)).astype(np.int64), period) == period
    result[~coherent] = independent[~coherent]
    return result


class TaModule:
    """Pine-style technical analysis namespace.

    Instantiated with a reference to the current ``PyneContext`` so
    functions like ``atr(14)`` can implicitly use global OHLCV data.
    """

    def __init__(self, ctx: PyneContext | None = None) -> None:
        self._ctx = ctx

    def bind(self, ctx: PyneContext) -> None:
        """Bind to a context (called by runtime before script exec)."""
        self._ctx = ctx

    # ═══════════════════════════════════════════════════════════
    #  Moving Averages
    # ═══════════════════════════════════════════════════════════

    def sma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Simple Moving Average.

        Pine equivalent: ``ta.sma(close, 20)``
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)
        result = _rolling_nonmissing_sum(source, period) / period
        return wrap_like(result, src)

    def ema(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Exponential Moving Average.

        Pine equivalent: ``ta.ema(close, 20)``

        Seeds from the first ``period`` non-missing observations. Missing
        positions emit NaN without advancing the recursive state.
        """
        return wrap_like(_ema_skip_leading_na(to_numpy(src, dtype=np.float64), period), src)

    def wma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Weighted Moving Average.

        Pine equivalent: ``ta.wma(close, 20)``

        Weights: [1, 2, 3, ..., period]. Most recent bar has highest weight.
        Warmup requires ``period`` non-missing observations. Later windows
        carry the last input through gaps, but missing positions emit NaN.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        present = ~np.isnan(source)
        ready = np.cumsum(present) >= period
        if not np.any(ready):
            return wrap_like(result, src)
        if not np.all(present):
            source = _fixnan(source)
        window_values = _rolling_weighted_average_values(source, period)
        positive_infinity = _window_sums((source == np.inf).astype(np.int64), period)
        negative_infinity = _window_sums((source == -np.inf).astype(np.int64), period)
        window_values[positive_infinity > 0] = np.inf
        window_values[negative_infinity > 0] = -np.inf
        window_values[(positive_infinity > 0) & (negative_infinity > 0)] = np.nan
        result[period - 1 :] = window_values
        result[~present | ~ready] = np.nan

        return wrap_like(result, src)

    def hma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Hull Moving Average.

        Pine equivalent: ``ta.hma(close, 20)``.
        """
        if period <= 0:
            return wrap_like(np.full(len(to_numpy(src)), np.nan), src)
        half = max(int(period / 2), 1)
        root = max(int(np.sqrt(period)), 1)
        fast = self.wma(src, half)
        slow = self.wma(src, period)
        return self.wma(2 * fast - slow, root)

    def swma(self, src: PyneSeries | np.ndarray) -> PyneSeries | np.ndarray:
        """Symmetrically weighted moving average.

        Pine equivalent: ``ta.swma(close)``. Uses weights ``[1, 2, 2, 1] / 6``.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        weights = np.array([1.0, 2.0, 2.0, 1.0], dtype=np.float64)
        for idx in range(3, n):
            window = source[idx - 3 : idx + 1]
            if not np.any(np.isnan(window)):
                result[idx] = float(np.dot(window, weights) / 6.0)
        return wrap_like(result, src)

    def alma(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        offset: float = 0.85,
        sigma: float = 6.0,
    ) -> PyneSeries | np.ndarray:
        """Arnaud Legoux Moving Average.

        Pine equivalent: ``ta.alma(close, 20, 0.85, 6)``.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n or sigma == 0:
            return wrap_like(result, src)

        m = offset * (period - 1)
        s = period / sigma
        positions = np.arange(period, dtype=np.float64)
        weights = np.exp(-((positions - m) ** 2) / (2 * s * s))
        weights = weights / np.sum(weights)

        clean = np.where(np.isfinite(source), source, 0.0)
        window_values = _valid_weighted_convolution(clean, weights)
        nan_counts = _window_sums(np.isnan(source).astype(np.int64), period)
        nonzero_weights = weights != 0.0
        zero_weights = ~nonzero_weights
        positive_infinity = _valid_boolean_correlation(
            source == np.inf,
            nonzero_weights,
        )
        negative_infinity = _valid_boolean_correlation(
            source == -np.inf,
            nonzero_weights,
        )
        zero_weight_infinity = _valid_boolean_correlation(
            np.isinf(source),
            zero_weights,
        )
        window_values[positive_infinity > 0] = np.inf
        window_values[negative_infinity > 0] = -np.inf
        window_values[(positive_infinity > 0) & (negative_infinity > 0)] = np.nan
        window_values[zero_weight_infinity > 0] = np.nan
        window_values[nan_counts > 0] = np.nan
        result[period - 1 :] = window_values

        return wrap_like(result, src)

    def vwma(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        volume: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Volume-Weighted Moving Average.

        Pine equivalent: ``ta.vwma(close, 20)``

        If ``volume`` is not provided, uses the global volume from context.
        """
        if volume is None:
            if self._ctx is None:
                raise RuntimeError(
                    "ta.vwma() needs volume data — pass it explicitly or use within a Pyne script"
                )
            volume = self._ctx.volume

        source = to_numpy(src, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        pv = source * volume_arr
        numerator = _rolling_nonmissing_sum(pv, period)
        denominator = _rolling_nonmissing_sum(volume_arr, period)
        with np.errstate(divide="ignore", invalid="ignore"):
            result[:] = np.where(
                denominator > 0.0,
                numerator / denominator,
                np.nan,
            )

        return wrap_like(result, src)

    def vwap(
        self,
        source: PyneSeries | np.ndarray | None = None,
        anchor: PyneSeries | np.ndarray | bool | None = None,
        stdev_mult: PyneSeries | np.ndarray | float | None = None,
    ) -> (
        PyneSeries
        | np.ndarray
        | tuple[
            PyneSeries | np.ndarray,
            PyneSeries | np.ndarray,
            PyneSeries | np.ndarray,
        ]
    ):
        """Session or explicitly anchored Volume-Weighted Average Price.

        Pine equivalents:
        ``ta.vwap(source)``, ``ta.vwap(source, anchor)``, and
        ``ta.vwap(source, anchor, stdev_mult)``.
        """
        if self._ctx is None:
            raise RuntimeError("ta.vwap() requires OHLCV data from a Pyne runtime context")
        if source is None:
            source = self._ctx.hlc3

        source_values = to_numpy(source, dtype=np.float64)
        volume_values = to_numpy(self._ctx.volume, dtype=np.float64)
        if source_values.ndim != 1:
            raise ValueError("ta.vwap() source must be a one-dimensional series")
        if volume_values.ndim != 1 or len(volume_values) != len(source_values):
            raise ValueError("ta.vwap() volume must match the source length")
        length = len(source_values)

        if anchor is None:
            session_anchor = to_numpy(self._ctx.session.isfirstbar, dtype=bool)
            if len(session_anchor) == length and np.any(session_anchor[1:]):
                anchor_values = session_anchor
            else:
                anchor_values = to_numpy(self._ctx.timeframe.change("1D"), dtype=bool)
        else:
            raw_anchor = _broadcast_ta_input(anchor, length, "anchor")
            anchor_values = np.isfinite(raw_anchor) & (raw_anchor != 0.0)

        multipliers = (
            None if stdev_mult is None else _broadcast_ta_input(stdev_mult, length, "stdev_mult")
        )
        result = np.full(length, np.nan, dtype=np.float64)
        upper = np.full(length, np.nan, dtype=np.float64)
        lower = np.full(length, np.nan, dtype=np.float64)
        running = False
        volume_sum = 0.0
        weighted_sum = 0.0
        weighted_square_sum = 0.0

        for index in range(length):
            if bool(anchor_values[index]):
                running = True
                volume_sum = 0.0
                weighted_sum = 0.0
                weighted_square_sum = 0.0
            if not running:
                continue

            price = source_values[index]
            bar_volume = volume_values[index]
            if not np.isfinite(price) or not np.isfinite(bar_volume):
                continue
            volume_sum += bar_volume
            weighted_sum += price * bar_volume
            weighted_square_sum += price * price * bar_volume
            if volume_sum == 0.0:
                continue

            value = weighted_sum / volume_sum
            result[index] = value
            if multipliers is None or is_na_value(multipliers[index]):
                continue
            variance = max(weighted_square_sum / volume_sum - value * value, 0.0)
            deviation = np.sqrt(variance) * multipliers[index]
            upper[index] = value + deviation
            lower[index] = value - deviation

        wrapped = wrap_like(result, source, name="vwap")
        if multipliers is None:
            return wrapped
        return (
            wrapped,
            wrap_like(upper, source, name="vwap.upper"),
            wrap_like(lower, source, name="vwap.lower"),
        )

    def pivot_point_levels(
        self,
        type: str | PyneSeries | np.ndarray,
        anchor: PyneSeries | np.ndarray | bool,
        developing: PyneSeries | np.ndarray | bool = False,
    ) -> PyneArray:
        """Return Pine-ordered pivot levels as eleven chart-aligned series.

        The returned array order is ``P, R1, S1, ... R5, S5``. With
        ``developing=False``, a true anchor calculates a fixed level set from
        the completed period and keeps it until the next anchor. Developing
        levels instead use the current partial period on every bar.
        """
        if self._ctx is None:
            raise RuntimeError(
                "ta.pivot_point_levels() requires OHLC data from a Pyne runtime context"
            )

        opens = to_numpy(self._ctx.open, dtype=np.float64)
        highs = to_numpy(self._ctx.high, dtype=np.float64)
        lows = to_numpy(self._ctx.low, dtype=np.float64)
        closes = to_numpy(self._ctx.close, dtype=np.float64)
        length = len(closes)
        pivot_types = _broadcast_pivot_types(type, length)
        anchor_values = _broadcast_ta_input(
            anchor,
            length,
            "anchor",
            function="ta.pivot_point_levels()",
        )
        developing_values = _broadcast_ta_input(
            developing,
            length,
            "developing",
            function="ta.pivot_point_levels()",
        )
        anchors = np.isfinite(anchor_values) & (anchor_values != 0.0)
        is_developing = np.isfinite(developing_values) & (developing_values != 0.0)
        if any(
            pivot_type == "woodie" and bool(is_developing[index])
            for index, pivot_type in enumerate(pivot_types)
        ):
            raise ValueError(
                "ta.pivot_point_levels() does not allow developing=True with the Woodie type"
            )

        output = np.full((11, length), np.nan, dtype=np.float64)
        fixed_levels = np.full(11, np.nan, dtype=np.float64)
        period_open = np.nan
        period_high = np.nan
        period_low = np.nan
        period_close = np.nan
        period_has_bars = False

        for index in range(length):
            if bool(anchors[index]):
                if period_has_bars:
                    fixed_levels = _pivot_level_values(
                        pivot_types[index],
                        period_open=period_open,
                        period_high=period_high,
                        period_low=period_low,
                        period_close=period_close,
                        current_open=opens[index],
                    )
                else:
                    fixed_levels = np.full(11, np.nan, dtype=np.float64)
                period_open = np.nan
                period_high = np.nan
                period_low = np.nan
                period_close = np.nan
                period_has_bars = False

            if not period_has_bars:
                period_open = opens[index]
                period_has_bars = True
            if np.isfinite(highs[index]):
                period_high = (
                    highs[index] if not np.isfinite(period_high) else max(period_high, highs[index])
                )
            if np.isfinite(lows[index]):
                period_low = (
                    lows[index] if not np.isfinite(period_low) else min(period_low, lows[index])
                )
            if np.isfinite(closes[index]):
                period_close = closes[index]

            levels = fixed_levels
            if bool(is_developing[index]):
                levels = _pivot_level_values(
                    pivot_types[index],
                    period_open=period_open,
                    period_high=period_high,
                    period_low=period_low,
                    period_close=period_close,
                    current_open=period_open,
                )
            output[:, index] = levels

        return PyneArray(
            wrap_like(
                output[level_index],
                self._ctx.close,
                name=f"pivot_point_levels[{level_index}]",
            )
            for level_index in range(11)
        )

    def rma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Running Moving Average (Wilder's smoothing).

        Pine equivalent: ``ta.rma(close, 14)``

        Also known as Wilder's EMA. Used internally by RSI and ATR.
        ``alpha = 1 / period``
        Missing positions emit NaN without advancing the smoothing state.
        """
        return self._rma(src, period, emit_missing=True)

    def _rma(self, src: PyneSeries | np.ndarray, period: int, *, emit_missing: bool) -> PyneSeries | np.ndarray:
        """Apply smoothing with the caller's missing-output policy."""
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        alpha = 1.0 / period

        count = 0
        seed_sum = 0.0
        rma_value = np.nan
        for i in range(n):
            val = source[i]
            if np.isnan(val):
                if not emit_missing:
                    result[i] = rma_value
                continue
            if count < period:
                count += 1
                seed_sum += val
                if count == period:
                    rma_value = seed_sum / period
                    result[i] = rma_value
                continue
            rma_value = alpha * val + (1 - alpha) * rma_value
            result[i] = rma_value

        return wrap_like(result, src)

    # ═══════════════════════════════════════════════════════════
    #  Oscillators
    # ═══════════════════════════════════════════════════════════

    def rsi(self, src: PyneSeries | np.ndarray, period: int = 14) -> PyneSeries | np.ndarray:
        """Relative Strength Index.

        Pine equivalent: ``ta.rsi(close, 14)``
        """
        source = to_numpy(src, dtype=np.float64)
        delta = to_numpy(utils.change(source, 1), dtype=np.float64)
        gain = np.where(np.isnan(delta), np.nan, np.where(delta > 0, delta, 0.0))
        loss = np.where(np.isnan(delta), np.nan, np.where(delta < 0, -delta, 0.0))

        avg_gain = self.rma(gain, period)
        avg_loss = self.rma(loss, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            rs = np.where(avg_loss != 0, avg_gain / avg_loss, np.inf)
            rsi_val = 100.0 - 100.0 / (1.0 + rs)

        # Where avg_loss is 0 (all gains), RSI = 100
        rsi_val = np.where(avg_loss == 0, 100.0, rsi_val)
        # Only-loss histories produce zero; the all-flat double-zero case is
        # 100 in the captured Pine v6 contract (loss-zero branch takes priority).
        rsi_val = np.where((avg_gain == 0) & (avg_loss > 0), 0.0, rsi_val)
        # RMA state survives missing deltas, but RSI must not publish a stale
        # value on a missing source or on the following non-computable delta.
        rsi_val = np.where(np.isnan(delta), np.nan, rsi_val)
        # Preserve NaN in warmup period
        rsi_val[:period] = np.nan

        return wrap_like(rsi_val, src)

    def cmo(self, src: PyneSeries | np.ndarray, period: int = 14) -> PyneSeries | np.ndarray:
        """Chande Momentum Oscillator.

        Pine equivalent: ``ta.cmo(close, 14)``.
        """
        source = to_numpy(src, dtype=np.float64)
        delta = to_numpy(utils.change(source, 1), dtype=np.float64)
        # Native Pine's >= 0 branches send an unknown delta to zero upward
        # flow and missing downward flow. Each sum has its own observations.
        up = np.where(delta >= 0, delta, 0.0)
        down = np.where(delta >= 0, 0.0, -delta)
        up_sum = _rolling_nonmissing_sum(up, period)
        down_sum = _rolling_nonmissing_sum(down, period)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (up_sum + down_sum) != 0,
                100.0 * (up_sum - down_sum) / (up_sum + down_sum),
                np.nan,
            )
        result[:period] = np.nan
        return wrap_like(result, src)

    def wpr(
        self,
        period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Williams Percent Range.

        Pine-style helper for Williams %R over the current OHLC context.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.wpr() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        highest = to_numpy(utils.highest(high_arr, period), dtype=np.float64)
        lowest = to_numpy(utils.lowest(low_arr, period), dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (highest - lowest) != 0,
                -100.0 * (highest - close_arr) / (highest - lowest),
                0.0,
            )
        return wrap_like(result, high, low, close)

    def tsi(
        self,
        src: PyneSeries | np.ndarray,
        short: int = 13,
        long: int = 25,
    ) -> PyneSeries | np.ndarray:
        """True Strength Index.

        Pine equivalent: ``ta.tsi(source, short_length, long_length)``.
        """
        source = to_numpy(src, dtype=np.float64)
        momentum = to_numpy(utils.change(source, 1), dtype=np.float64)
        abs_momentum = np.abs(momentum)
        smooth_mom = _ema_skip_leading_na(_ema_skip_leading_na(momentum, long), short)
        smooth_abs = _ema_skip_leading_na(_ema_skip_leading_na(abs_momentum, long), short)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(smooth_abs != 0, smooth_mom / smooth_abs, np.nan)
        return wrap_like(result, src)

    def stoch(
        self,
        source: PyneSeries | np.ndarray,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        period: int = 14,
        *,
        k_period: int | None = None,
    ) -> PyneSeries | np.ndarray:
        """Stochastic oscillator.

        Pine equivalent: ``ta.stoch(source, high, low, length)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError(
                    "ta.stoch() needs high/low — pass explicitly or use within Pyne script"
                )
            high = self._ctx.high
        if low is None:
            low = self._ctx.low

        length = k_period if k_period is not None else period
        source_arr = to_numpy(source, dtype=np.float64)
        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        # Reset missing high/low windows, retaining the initial lookback
        # readiness shared with the extrema primitives.
        hh = to_numpy(utils._rolling_extreme(
            high_arr, length, highest=True, return_offset=False,
            reset_on_missing=True,
        ), dtype=np.float64)
        ll = to_numpy(utils._rolling_extreme(
            low_arr, length, highest=False, return_offset=False,
            reset_on_missing=True,
        ), dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (hh - ll) != 0,
                100.0 * (source_arr - ll) / (hh - ll),
                np.nan,
            )

        return wrap_like(_fixnan(result), source, high, low)

    def cci(
        self,
        source: PyneSeries | np.ndarray | None = None,
        period: int = 20,
        *,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Commodity Channel Index.

        Pine equivalent: ``ta.cci(source, length)``.
        """
        if source is None:
            if high is None:
                if self._ctx is None:
                    raise RuntimeError("ta.cci() needs a source series")
                high = self._ctx.high
            if low is None:
                low = self._ctx.low
            if close is None:
                close = self._ctx.close
            source = (
                to_numpy(high, dtype=np.float64)
                + to_numpy(low, dtype=np.float64)
                + to_numpy(close, dtype=np.float64)
            ) / 3.0

        source_arr = to_numpy(source, dtype=np.float64)
        source_sma, mad = _rolling_mean_and_mad(source_arr, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(mad != 0, (source_arr - source_sma) / (0.015 * mad), 0.0)
        result[: period - 1] = np.nan
        return wrap_like(result, source)

    # ═══════════════════════════════════════════════════════════
    #  Trend Indicators
    # ═══════════════════════════════════════════════════════════

    def macd(
        self,
        src: PyneSeries | np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """MACD — Moving Average Convergence Divergence.

        Pine equivalent: ``ta.macd(close, 12, 26, 9)``

        Returns:
            Tuple of (MACD line, signal line, histogram) arrays.
            ``histogram = macd_line - signal_line``.
        """
        ema_fast = self.ema(src, fast)
        ema_slow = self.ema(src, slow)
        dif = ema_fast - ema_slow
        dea = wrap_like(_ema_skip_leading_na(to_numpy(dif, dtype=np.float64), signal), src)
        hist = dif - dea
        return dif, dea, hist

    def mom(self, src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
        """Momentum over ``period`` bars.

        Pine equivalent: ``ta.mom(close, 10)``.
        """
        source = to_numpy(src, dtype=np.float64)
        previous = to_numpy(utils.shift(source, period), dtype=np.float64)
        return wrap_like(source - previous, src)

    def linreg(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        offset: int = 0,
    ) -> PyneSeries | np.ndarray:
        """Linear regression curve.

        Pine equivalent: ``ta.linreg(source, length, offset)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_linear_regression_values(source, period, offset)
        return wrap_like(result, src)

    def correlation(
        self,
        source_a: PyneSeries | np.ndarray,
        source_b: PyneSeries | np.ndarray,
        period: int,
    ) -> PyneSeries | np.ndarray:
        """Correlation from independent non-missing observation windows.

        Pine equivalent: ``ta.correlation(source1, source2, length)``.
        Missing x, y and x*y observations advance their moment windows
        independently, so missing-window results can exceed [-1, 1]. Ready
        windows with both numerator and denominator zero return zero;
        a nonzero numerator with zero denominator remains missing. Coherent finite windows retain
        stable centered Pearson arithmetic.
        """
        a = to_numpy(source_a, dtype=np.float64)
        b = to_numpy(source_b, dtype=np.float64)
        result = _rolling_correlation_values(a, b, period)
        return wrap_like(result, source_a, source_b)

    def adx(
        self,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
        period: int = 14,
    ) -> PyneSeries | np.ndarray:
        """Average Directional Index.

        Pine equivalent: ``ta.adx(high, low, close, 14)``

        Returns:
            ADX array.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.adx() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        _, _, adx_val = self._dmi_components(high, low, close, period, period)
        return wrap_like(adx_val, high, low, close)

    def dmi(
        self,
        period: int = 14,
        adx_period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Directional Movement Index.

        Pine equivalent: ``ta.dmi(diLength, adxSmoothing)``.
        Returns ``(+DI, -DI, ADX)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.dmi() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        plus_di, minus_di, adx_val = self._dmi_components(
            high,
            low,
            close,
            period,
            adx_period,
        )

        return (
            wrap_like(plus_di, high, low, close),
            wrap_like(minus_di, high, low, close),
            wrap_like(adx_val, high, low, close),
        )

    def _dmi_components(
        self,
        high: PyneSeries | np.ndarray,
        low: PyneSeries | np.ndarray,
        close: PyneSeries | np.ndarray,
        period: int,
        adx_period: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        up_move = to_numpy(utils.change(high_arr, 1), dtype=np.float64)
        down_move = -to_numpy(utils.change(low_arr, 1), dtype=np.float64)

        plus_dm = np.where(
            np.isnan(up_move),
            np.nan,
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        )
        minus_dm = np.where(
            np.isnan(down_move),
            np.nan,
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        )
        # DMI smooths strict true range. Without a preceding close the first
        # observation is missing; ATR's high-low fallback would seed too early.
        previous_close = to_numpy(utils.shift(close_arr, 1), dtype=np.float64)
        strict_tr = np.maximum(high_arr - low_arr, np.maximum(
            np.abs(high_arr - previous_close), np.abs(low_arr - previous_close)))
        trur = to_numpy(self._rma(strict_tr, period, emit_missing=False), dtype=np.float64)
        plus_smoothed = to_numpy(self._rma(plus_dm, period, emit_missing=False), dtype=np.float64)
        minus_smoothed = to_numpy(self._rma(minus_dm, period, emit_missing=False), dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            plus_di = _fixnan(100.0 * plus_smoothed / trur)
            minus_di = _fixnan(100.0 * minus_smoothed / trur)
            total = plus_di + minus_di
            denominator = np.where(total == 0.0, 1.0, total)
            dx_ratio = np.abs(plus_di - minus_di) / denominator
            adx_val = 100.0 * to_numpy(self._rma(dx_ratio, adx_period, emit_missing=False), dtype=np.float64)
        return plus_di, minus_di, adx_val

    def sar(
        self,
        start: float = 0.02,
        increment: float = 0.02,
        maximum: float = 0.2,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Parabolic SAR.

        Pine equivalent: ``ta.sar(start, increment, max)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.sar() needs high/low data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None and self._ctx is not None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = (
            to_numpy(close, dtype=np.float64) if close is not None else (high_arr + low_arr) / 2.0
        )
        n = len(high_arr)
        result = np.full(n, np.nan)
        if n < 2:
            return wrap_like(result, high, low)

        sar_value = np.nan
        max_min = np.nan
        acceleration = np.nan
        is_below = False

        for idx in range(n):
            is_first_trend_bar = False
            if np.isnan(high_arr[idx]) or np.isnan(low_arr[idx]) or np.isnan(close_arr[idx]):
                sar_value = np.nan
                max_min = np.nan
                acceleration = np.nan
                continue

            if np.isnan(sar_value) and idx > 0 and not np.isnan(close_arr[idx - 1]):
                if close_arr[idx] > close_arr[idx - 1]:
                    is_below = True
                    max_min = high_arr[idx]
                    sar_value = low_arr[idx - 1]
                else:
                    is_below = False
                    max_min = low_arr[idx]
                    sar_value = high_arr[idx - 1]
                is_first_trend_bar = True
                acceleration = float(start)
            elif not np.isnan(sar_value):
                sar_value = sar_value + acceleration * (max_min - sar_value)
                if is_below:
                    if sar_value > low_arr[idx]:
                        is_first_trend_bar = True
                        is_below = False
                        sar_value = max(high_arr[idx], max_min)
                        max_min = low_arr[idx]
                        acceleration = float(start)
                else:
                    if sar_value < high_arr[idx]:
                        is_first_trend_bar = True
                        is_below = True
                        sar_value = min(low_arr[idx], max_min)
                        max_min = high_arr[idx]
                        acceleration = float(start)

                if not is_first_trend_bar:
                    if is_below:
                        if high_arr[idx] > max_min:
                            max_min = high_arr[idx]
                            acceleration = min(acceleration + increment, maximum)
                    elif low_arr[idx] < max_min:
                        max_min = low_arr[idx]
                        acceleration = min(acceleration + increment, maximum)

                if is_below:
                    sar_value = min(sar_value, low_arr[idx - 1])
                    if idx > 1 and not np.isnan(low_arr[idx - 2]):
                        sar_value = min(sar_value, low_arr[idx - 2])
                else:
                    sar_value = max(sar_value, high_arr[idx - 1])
                    if idx > 1 and not np.isnan(high_arr[idx - 2]):
                        sar_value = max(sar_value, high_arr[idx - 2])

            result[idx] = sar_value

        return wrap_like(result, high, low, close)

    def supertrend(
        self,
        factor: float = 3.0,
        atr_period: int = 10,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
        *,
        period: int | None = None,
        mult: float | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Supertrend indicator.

        Pine equivalent: ``ta.supertrend(factor, atrPeriod)``.

        Returns:
            Tuple of (supertrend_line, direction) arrays.
            direction follows Pine's convention: 1 = downtrend, -1 = uptrend.
        """
        if period is not None:
            atr_period = period
        if mult is not None:
            factor = mult

        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.supertrend() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        atr_val = to_numpy(self.atr(atr_period, high_arr, low_arr, close_arr), dtype=np.float64)
        hl2 = (high_arr + low_arr) / 2.0

        n = len(close_arr)
        upper_band = hl2 + factor * atr_val
        lower_band = hl2 - factor * atr_val
        supertrend = np.full(n, np.nan)
        direction = np.full(n, np.nan)

        if n:
            supertrend[0] = 0.0

        for i in range(n):
            prev_lower_band = 0.0 if i == 0 or np.isnan(lower_band[i - 1]) else lower_band[i - 1]
            prev_upper_band = 0.0 if i == 0 or np.isnan(upper_band[i - 1]) else upper_band[i - 1]
            prev_close = np.nan if i == 0 else close_arr[i - 1]

            if not np.isnan(lower_band[i]):
                if not (lower_band[i] > prev_lower_band or prev_close < prev_lower_band):
                    lower_band[i] = prev_lower_band

            if not np.isnan(upper_band[i]):
                if not (upper_band[i] < prev_upper_band or prev_close > prev_upper_band):
                    upper_band[i] = prev_upper_band

            if i == 0 or np.isnan(atr_val[i - 1]):
                direction[i] = 1.0
            else:
                prev_supertrend = supertrend[i - 1]
                if not np.isnan(prev_supertrend) and prev_supertrend == prev_upper_band:
                    direction[i] = -1.0 if close_arr[i] > upper_band[i] else 1.0
                else:
                    direction[i] = 1.0 if close_arr[i] < lower_band[i] else -1.0

            if not np.isnan(upper_band[i]) and not np.isnan(lower_band[i]):
                supertrend[i] = lower_band[i] if direction[i] == -1.0 else upper_band[i]

        return wrap_like(supertrend, high, low, close), wrap_like(direction, high, low, close)

    # ═══════════════════════════════════════════════════════════
    #  Volatility
    # ═══════════════════════════════════════════════════════════

    def tr(
        self,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """True Range.

        Pine equivalent: ``ta.tr``
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.tr() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        prev_close = to_numpy(utils.shift(close_arr, 1), dtype=np.float64)
        tr1 = high_arr - low_arr
        tr2 = np.abs(high_arr - prev_close)
        tr3 = np.abs(low_arr - prev_close)
        result = np.where(np.isnan(prev_close), tr1, np.maximum(tr1, np.maximum(tr2, tr3)))
        return wrap_like(result, high, low, close)

    def atr(
        self,
        period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Average True Range.

        Pine equivalent: ``ta.atr(14)``

        When called without high/low/close, uses the global context data.
        """
        tr_val = self.tr(high, low, close)
        return self._rma(tr_val, period, emit_missing=False)

    def bb(
        self,
        src: PyneSeries | np.ndarray,
        period: int = 20,
        mult: float = 2.0,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Bollinger Bands.

        Pine equivalent: ``ta.bb(close, 20, 2)``

        Returns:
            Tuple of (middle, upper, lower) arrays.
        """
        middle = self.sma(src, period)
        sd = self.stdev(src, period)
        upper = middle + mult * sd
        lower = middle - mult * sd
        return middle, upper, lower

    def stdev(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Rolling Standard Deviation (O(n) optimized).

        Pine equivalent: ``ta.stdev(close, 20)``

        Uses periodically rebased centered moments over the last period
        non-missing observations. Missing inputs preserve the current window.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_nonmissing_variance_values(source, period, ddof=0)
        np.sqrt(result, out=result)
        return wrap_like(result, src)

    def variance(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        biased: bool = True,
    ) -> PyneSeries | np.ndarray:
        """Rolling variance.

        Pine equivalent: ``ta.variance(close, 20, true)``.
        """
        ddof = 0 if biased else 1
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_nonmissing_variance_values(source, period, ddof=ddof)
        return wrap_like(result, src)

    def dev(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Mean absolute deviation from SMA.

        Pine equivalent: ``ta.dev(close, 20)``.
        """
        source = to_numpy(src, dtype=np.float64)
        _, result = _rolling_mean_and_mad(source, period)
        return wrap_like(result, src)

    def percentile_nearest_rank(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        percentage: float,
    ) -> PyneSeries | np.ndarray:
        """Rolling percentile using nearest-rank selection.

        Pine equivalent: ``ta.percentile_nearest_rank(source, length, percentage)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_percentile_values(
            source,
            period,
            percentage,
            linear=False,
        )
        return wrap_like(result, src)

    def percentile_linear_interpolation(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        percentage: float,
    ) -> PyneSeries | np.ndarray:
        """Rolling percentile using linear interpolation.

        Pine equivalent: ``ta.percentile_linear_interpolation(source, length, percentage)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_percentile_values(
            source,
            period,
            percentage,
            linear=True,
        )
        return wrap_like(result, src)

    def keltner(
        self,
        period: int = 20,
        mult: float = 1.5,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
        *,
        source: PyneSeries | np.ndarray | None = None,
        use_true_range: bool = True,
        width_smoothing: str = "ema",
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Keltner Channel with native-style EMA range smoothing.

        ``source`` selects the basis independently of OHLC true range. The
        default width follows native ``ta.kc``; ``width_smoothing="atr"``
        selects the earlier Wilder ATR formula. Both modes require a positive
        multiplier. High-low width is available with EMA smoothing only.

        Returns:
            Tuple of (upper, middle, lower) arrays.
        """
        period = utils.require_positive_period(period)
        mult = float(mult)
        if not mult > 0:
            raise ValueError("ta.keltner() mult must be greater than zero")
        if not isinstance(use_true_range, (bool, np.bool_)):
            raise ValueError("ta.keltner() use_true_range must be a boolean")
        if width_smoothing not in ("ema", "atr"):
            raise ValueError("ta.keltner() width_smoothing must be 'ema' or 'atr'")
        if width_smoothing == "atr" and not use_true_range:
            raise ValueError("ta.keltner() ATR width requires use_true_range=True")
        if close is None:
            if self._ctx is None:
                raise RuntimeError("ta.keltner() needs OHLC data")
            close = self._ctx.close
        if high is None or low is None:
            if self._ctx is None:
                raise RuntimeError("ta.keltner() needs high/low data")
            high = self._ctx.high if high is None else high
            low = self._ctx.low if low is None else low
        basis = close if source is None else source
        high_values, low_values, close_values, basis_values = (
            to_numpy(value, dtype=np.float64) for value in (high, low, close, basis))
        inputs = (high_values, low_values, close_values, basis_values)
        if any(value.ndim != 1 for value in inputs) or any(
            len(value) != len(close_values) for value in inputs
        ):
            raise ValueError("ta.keltner() inputs must be one-dimensional and have matching lengths")
        middle = self.ema(basis, period)
        if width_smoothing == "atr":
            width = self.atr(period, high, low, close)
        else:
            span = high_values - low_values
            if use_true_range:
                previous = np.full(len(close_values), np.nan)
                previous[1:] = close_values[:-1]
                # Native ta.kc uses ta.tr, whose first bar (or missing prior
                # close) is missing; it does not use ta.tr(true)'s fallback.
                span = np.maximum.reduce((span, np.abs(high_values - previous),
                                          np.abs(low_values - previous)))
            width = self.ema(wrap_like(span, high, low, close), period)
        upper = middle + mult * width
        lower = middle - mult * width
        return upper, middle, lower

    def donchian(
        self,
        period: int = 20,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Donchian Channel.

        Returns:
            Tuple of (upper, middle, lower) arrays.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.donchian() needs high/low data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low

        upper = utils.highest(high, period)
        lower = utils.lowest(low, period)
        middle = (upper + lower) / 2.0
        return upper, middle, lower

    # ═══════════════════════════════════════════════════════════
    #  Volume
    # ═══════════════════════════════════════════════════════════

    def obv(
        self,
        close: PyneSeries | np.ndarray | None = None,
        volume: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """On-Balance Volume.

        Pine equivalent: ``ta.obv``
        """
        if close is None:
            if self._ctx is None:
                raise RuntimeError("ta.obv() needs close/volume data")
            close = self._ctx.close
        if volume is None:
            volume = self._ctx.volume

        close_arr = to_numpy(close, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        # Native OBV is cum(sign(change(close)) * volume). Missing products
        # emit no value and leave the internal accumulator available to resume.
        products = np.sign(utils.change(close_arr)) * volume_arr
        result = utils.cum(products)
        return wrap_like(result, close, volume)

    def volume_sma(
        self,
        volume: PyneSeries | np.ndarray | None = None,
        period: int = 20,
    ) -> PyneSeries | np.ndarray:
        """Volume Simple Moving Average."""
        if volume is None:
            if self._ctx is None:
                raise RuntimeError("ta.volume_sma() needs volume data")
            volume = self._ctx.volume
        return self.sma(volume, period)

    def mfi(
        self,
        source: PyneSeries | np.ndarray | int | None = None,
        period: int = 14,
        *,
        volume: PyneSeries | np.ndarray | None = None,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Money Flow Index.

        Pine equivalent: ``ta.mfi(source, length)``.
        """
        if isinstance(source, int):
            period = source
            source = None
        if source is None:
            if high is None:
                if self._ctx is None:
                    raise RuntimeError("ta.mfi() needs a source series and volume data")
                high = self._ctx.high
            if low is None:
                low = self._ctx.low
            if close is None:
                close = self._ctx.close
            source = (
                to_numpy(high, dtype=np.float64)
                + to_numpy(low, dtype=np.float64)
                + to_numpy(close, dtype=np.float64)
            ) / 3.0
        if volume is None:
            if self._ctx is None:
                raise RuntimeError("ta.mfi() needs volume data")
            volume = self._ctx.volume

        source_arr = to_numpy(source, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        raw_mf = source_arr * volume_arr

        pos_mf = np.where(utils.change(source_arr, 1) > 0, raw_mf, 0.0)
        neg_mf = np.where(utils.change(source_arr, 1) < 0, raw_mf, 0.0)
        pos_mf[0] = 0
        neg_mf[0] = 0

        pos_sum = utils.sum_(pos_mf, period)
        neg_sum = utils.sum_(neg_mf, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            mfi_val = np.where(
                (~np.isnan(neg_sum)) & (neg_sum != 0),
                100.0 - 100.0 / (1.0 + pos_sum / neg_sum),
                100.0,
            )
        return wrap_like(mfi_val, source, volume)

    # ═══════════════════════════════════════════════════════════
    #  Proxy methods for utils (so ta.crossover works)
    # ═══════════════════════════════════════════════════════════

    crossover = staticmethod(utils.crossover)
    cross = staticmethod(utils.cross)
    crossunder = staticmethod(utils.crossunder)
    highest = staticmethod(utils.highest)
    lowest = staticmethod(utils.lowest)
    highestbars = staticmethod(utils.highestbars)
    lowestbars = staticmethod(utils.lowestbars)
    change = staticmethod(utils.change)
    roc = staticmethod(utils.roc)
    barssince = staticmethod(utils.barssince)
    valuewhen = staticmethod(utils.valuewhen)
    pivothigh = staticmethod(utils.pivothigh)
    pivotlow = staticmethod(utils.pivotlow)
    cum = staticmethod(utils.cum)
    rising = staticmethod(utils.rising)
    falling = staticmethod(utils.falling)
    shift = staticmethod(utils.shift)
    nz = staticmethod(utils.nz)


def _ema_skip_leading_na(src: np.ndarray, period: int) -> np.ndarray:
    """EMA seeded by non-missing samples, with sparse output and durable state.

    Shared by public EMA, MACD signal and the nested TSI smoothing path.
    The historical name is retained for internal callers.
    """
    source = np.asarray(src, dtype=np.float64)
    n = len(source)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result

    valid_indices = np.flatnonzero(~np.isnan(source))
    if len(valid_indices) < period:
        return result

    seed_index = int(valid_indices[period - 1])
    value = float(np.mean(source[valid_indices[:period]]))
    result[seed_index] = value
    k = 2.0 / (period + 1)
    for idx in range(seed_index + 1, n):
        current = source[idx]
        if np.isnan(current):
            continue
        value = current * k + value * (1 - k)
        result[idx] = value

    return result
