"""
Pyne Utils — Pine-style utility functions.

Provides commonly used Pine Script helper functions as Python equivalents:
  * ``na`` / ``nz()``         — NaN handling
  * ``shift()``               — Pine's ``close[1]`` equivalent
  * ``crossover()``           — bullish cross detection
  * ``crossunder()``          — bearish cross detection
  * ``highest()`` / ``lowest()`` — rolling extremes
  * ``change()`` / ``roc()``  — price changes
  * ``barssince()``           — bars since condition
  * ``valuewhen()``           — value when condition was true
  * ``pivothigh()`` / ``pivotlow()`` — pivot detection

All functions operate on numpy arrays and return numpy arrays.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from .series import PyneSeries, to_numpy, wrap_like, _truthy
from .ta_kernels import _rolling_nonmissing_sum
from .values import is_na, is_na_value, na as _na, to_missing_scalar


# ═══════════════════════════════════════════════════════════════
#  NaN Handling
# ═══════════════════════════════════════════════════════════════

# Pine's ``na`` value — alias for NaN
na = _na


def nz(
    src: PyneSeries | np.ndarray | float, replacement: float = 0.0
) -> PyneSeries | np.ndarray | float:
    """Replace NaN values with a replacement value.

    Pine equivalent: ``nz(x, 0)``

    Args:
        src: Input array or scalar.
        replacement: Value to use where src is NaN.

    Returns:
        Array/scalar with NaN replaced.
    """
    replacement = to_missing_scalar(replacement)
    if isinstance(src, PyneSeries):
        values = src.to_numpy()
        mask = to_numpy(is_na(src), dtype=bool)
        return src.with_values(np.where(mask, replacement, values))
    if isinstance(src, np.ndarray):
        mask = is_na(src)
        return np.where(mask, replacement, src)
    if is_na_value(src):
        return replacement
    return src


def fixnan(src: PyneSeries | np.ndarray | list | tuple | float) -> PyneSeries | np.ndarray | float:
    """Carry the latest non-missing value forward through later missing values."""
    if isinstance(src, PyneSeries):
        values = _fixnan_array(to_numpy(src, dtype=np.float64))
        return src.with_values(values)
    if isinstance(src, np.ndarray):
        return _fixnan_array(np.asarray(src, dtype=np.float64))
    if isinstance(src, list | tuple):
        return _fixnan_array(np.asarray(src, dtype=np.float64))
    if is_na_value(src):
        return np.nan
    return src


def na_check(src: PyneSeries | np.ndarray) -> PyneSeries | np.ndarray:
    """Check which elements are NaN.

    Pine equivalent: ``na(x)``

    Args:
        src: Input array.

    Returns:
        Boolean array — True where value is NaN.
    """
    result = is_na(src)
    return result if isinstance(result, PyneSeries) else wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Bar Offset / Shift
# ═══════════════════════════════════════════════════════════════


def _fixnan_array(values: np.ndarray) -> np.ndarray:
    result = np.array(values, dtype=np.float64, copy=True)
    last = np.nan
    for idx, value in enumerate(result):
        if np.isnan(value):
            if not np.isnan(last):
                result[idx] = last
            continue
        last = value
    return result


def shift(src: PyneSeries | np.ndarray, periods: int = 1) -> PyneSeries | np.ndarray:
    """Shift an array by N periods (like Pine's ``close[1]``).

    Pine equivalent: ``close[n]`` → ``shift(close, n)``

    Args:
        src: Input array.
        periods: Number of bars to look back. Positive = shift right (older values).

    Returns:
        Shifted array with NaN for positions without data.

    Example::

        prev_close = shift(close, 1)  # previous bar's close
        two_bars_ago = shift(close, 2)
    """
    periods = int(periods)
    if periods < 0:
        raise IndexError("shift() does not support forward history references")
    source = to_numpy(src, dtype=np.float64)
    result = np.full_like(source, np.nan, dtype=np.float64)
    if periods < len(source):
        result[periods:] = source[: len(source) - periods]
    return wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Cross Detection
# ═══════════════════════════════════════════════════════════════


def crossover(
    a: PyneSeries | np.ndarray, b: PyneSeries | np.ndarray | float
) -> PyneSeries | np.ndarray:
    """Detect where ``a`` crosses above ``b`` (bullish cross / golden cross).

    Pine equivalent: ``ta.crossover(a, b)``

    Compare against the previous pair with both values present. The previous
    pair permits equality; the current pair must be strictly above.

    Args:
        a: First series.
        b: Second series (or scalar threshold).

    Returns:
        Boolean array — True at crossover points.
    """
    return _cross(a, b, direction="over")


def crossunder(
    a: PyneSeries | np.ndarray, b: PyneSeries | np.ndarray | float
) -> PyneSeries | np.ndarray:
    """Detect where ``a`` crosses below ``b`` (bearish cross / death cross).

    Pine equivalent: ``ta.crossunder(a, b)``

    Compare against the previous pair with both values present. The previous
    pair permits equality; the current pair must be strictly below.

    Args:
        a: First series.
        b: Second series (or scalar threshold).

    Returns:
        Boolean array — True at crossunder points.
    """
    return _cross(a, b, direction="under")


def _cross(a, b, *, direction):
    a_arr = to_numpy(a, dtype=np.float64)
    b_arr = (
        np.full_like(a_arr, b, dtype=np.float64)
        if isinstance(b, (int, float))
        else to_numpy(b, dtype=np.float64)
    )
    result = np.zeros(len(a_arr), dtype=bool)
    valid = np.flatnonzero(~(np.isnan(a_arr) | np.isnan(b_arr)))
    if len(valid) < 2:
        return wrap_like(result, a, b)
    previous, current = valid[:-1], valid[1:]
    if direction == "over":
        crossed = (a_arr[previous] <= b_arr[previous]) & (a_arr[current] > b_arr[current])
    elif direction == "under":
        crossed = (a_arr[previous] >= b_arr[previous]) & (a_arr[current] < b_arr[current])
    else:
        crossed = ((a_arr[previous] < b_arr[previous]) & (a_arr[current] > b_arr[current])) | (
            (a_arr[previous] > b_arr[previous]) & (a_arr[current] < b_arr[current]))
    result[current] = crossed
    return wrap_like(result, a, b)


def cross(
    a: PyneSeries | np.ndarray, b: PyneSeries | np.ndarray | float
) -> PyneSeries | np.ndarray:
    """Detect any cross between ``a`` and ``b``.

    Pine equivalent: ``ta.cross(a, b)``.
    """
    return _cross(a, b, direction="either")


# ═══════════════════════════════════════════════════════════════
#  Rolling Extremes
# ═══════════════════════════════════════════════════════════════


def highest(src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
    """Rolling highest value over the last ``period`` bars.

    Pine equivalent: ``ta.highest(high, 20)``

    Args:
        src: Input array.
        period: Lookback window size.

    Returns:
        Rolling maximums after the initial ``period`` bar span. Missing input
        resets the window; later values use only bars after that gap without
        restarting the initial readiness clock.
    """
    return _rolling_extreme(src, period, highest=True, return_offset=False, reset_on_missing=True)


def lowest(src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
    """Rolling lowest value over the last ``period`` bars.

    Pine equivalent: ``ta.lowest(low, 20)``

    Args:
        src: Input array.
        period: Lookback window size.

    Returns:
        Rolling minimums after the initial ``period`` bar span. Missing input
        resets the window; later values use only bars after that gap without
        restarting the initial readiness clock.
    """
    return _rolling_extreme(src, period, highest=False, return_offset=False, reset_on_missing=True)


def highestbars(src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
    """Bars back to the highest value in the last ``period`` bars.

    Pine equivalent: ``ta.highestbars(source, length)``.
    Returns ``0`` when the current bar is the selected highest, or a negative
    offset when the highest value is in the past. If the highest value appears
    more than once in the window, the earliest occurrence wins. Missing input
    resets the window and yields zero after the initial lookback span.
    """
    return _extreme_bars(src, period, highest=True)


def lowestbars(src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
    """Bars back to the lowest value in the last ``period`` bars.

    Pine equivalent: ``ta.lowestbars(source, length)``.
    Returns ``0`` when the current bar is the selected lowest, or a negative
    offset when the lowest value is in the past. If the lowest value appears
    more than once in the window, the earliest occurrence wins. Missing input
    resets the window and yields zero after the initial lookback span.
    """
    return _extreme_bars(src, period, highest=False)


def _extreme_bars(
    src: PyneSeries | np.ndarray, period: int, *, highest: bool
) -> PyneSeries | np.ndarray:
    return _rolling_extreme(src, period, highest=highest, return_offset=True, reset_on_missing=True)


def _rolling_extreme(
    src: PyneSeries | np.ndarray,
    period: int,
    *,
    highest: bool,
    return_offset: bool,
    reset_on_missing: bool = False,
) -> PyneSeries | np.ndarray:
    """Return rolling extrema or their earliest bars-back offsets in O(n)."""
    source = to_numpy(src, dtype=np.float64)
    n = len(source)
    result = np.full(n, np.nan)
    if period <= 0:
        return wrap_like(result, src)

    candidates: deque[int] = deque()
    for idx, value in enumerate(source):
        window_start = idx - period + 1
        while candidates and candidates[0] < window_start:
            candidates.popleft()

        if np.isnan(value) and reset_on_missing:
            candidates.clear()
            if return_offset and idx >= period - 1:
                result[idx] = 0.0
        if not np.isnan(value):
            if highest:
                while candidates and source[candidates[-1]] < value:
                    candidates.pop()
            else:
                while candidates and source[candidates[-1]] > value:
                    candidates.pop()
            candidates.append(idx)

        if candidates and idx >= period - 1:
            extreme_idx = candidates[0]
            result[idx] = float(extreme_idx - idx) if return_offset else source[extreme_idx]
    return wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Price Change Functions
# ═══════════════════════════════════════════════════════════════


def require_positive_period(period: int, *, name: str = "period") -> int:
    """Require a positive integer lookback period at the API boundary."""
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)):
        raise ValueError(f"{name} must be a positive integer")
    value = int(period)
    if value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value}")
    return value


def change(src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
    """Difference between current and previous value.

    Pine equivalent: ``ta.change(close)`` or ``ta.change(close, 5)``

    Args:
        src: Input array.
        period: Lookback period (default 1).

    Returns:
        Array of differences. NaN for the first ``period`` bars.
    """
    period = require_positive_period(period)
    source = to_numpy(src, dtype=np.float64)
    result = np.full_like(source, np.nan, dtype=np.float64)
    if period < len(source):
        result[period:] = source[period:] - source[: len(source) - period]
    return wrap_like(result, src)


def roc(src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
    """Rate of Change — percentage change over ``period`` bars.

    Pine equivalent: ``ta.roc(close, 10)``

    ``roc = (src - src[period]) / src[period] * 100``

    Args:
        src: Input array.
        period: Lookback period.

    Returns:
        Array of percentage changes. NaN where undefined.
    """
    period = require_positive_period(period)
    source = to_numpy(src, dtype=np.float64)
    result = np.full_like(source, np.nan, dtype=np.float64)
    if period < len(source):
        prev = source[: len(source) - period]
        curr = source[period:]
        with np.errstate(divide="ignore", invalid="ignore"):
            result[period:] = np.where(prev != 0, (curr - prev) / prev * 100, np.nan)
    return wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Condition-Based Lookback
# ═══════════════════════════════════════════════════════════════


def barssince(condition: PyneSeries | np.ndarray) -> PyneSeries | np.ndarray:
    """Number of bars since condition was last True.

    Pine equivalent: ``ta.barssince(crossover(fast, slow))``

    Args:
        condition: Boolean array.

    Returns:
        Integer array — bars since last True. NaN if never True before.
    """
    flags = np.asarray(_truthy(to_numpy(condition)), dtype=bool)
    n = len(flags)
    result = np.full(n, np.nan)
    last_true = -1
    for i in range(n):
        if flags[i]:
            last_true = i
        if last_true >= 0:
            result[i] = float(i - last_true)
    return wrap_like(result, condition)


def valuewhen(
    condition: PyneSeries | np.ndarray,
    src: PyneSeries | np.ndarray,
    occurrence: int = 0,
) -> PyneSeries | np.ndarray:
    """Value of ``src`` when ``condition`` was True.

    Pine equivalent: ``ta.valuewhen(crossover(fast, slow), close, 0)``

    Args:
        condition: Boolean array.
        src: Value array to sample from.
        occurrence: Which occurrence to return (0 = most recent, 1 = second most recent, etc.)

    Returns:
        Array where each element is the value of src at the nth most recent True.
    """
    flags = np.asarray(_truthy(to_numpy(condition)), dtype=bool)
    source = to_numpy(src, dtype=np.float64)
    n = len(flags)
    result = np.full(n, np.nan)
    true_indices: list[int] = []

    for i in range(n):
        if flags[i]:
            true_indices.append(i)
        if len(true_indices) > occurrence:
            idx = true_indices[-(occurrence + 1)]
            result[i] = source[idx]
    return wrap_like(result, src, condition)


# ═══════════════════════════════════════════════════════════════
#  Pivot Detection
# ═══════════════════════════════════════════════════════════════


def pivothigh(src: PyneSeries | np.ndarray, left: int, right: int) -> PyneSeries | np.ndarray:
    """Detect pivot highs.

    Pine equivalent: ``ta.pivothigh(high, 5, 5)``

    A pivot high at bar ``i`` means ``src[i]`` is the highest value
    in the window ``[i-left, i+right]``.

    Args:
        src: Input array (typically ``high``).
        left: Number of bars to the left.
        right: Number of bars to the right.

    Returns:
        Array with pivot high values on their confirmation bars, NaN elsewhere.
        The returned price belongs to the pivot ``right`` bars earlier, matching
        Pine's causal ``ta.pivothigh()`` contract.
    """
    return _pivot(src, left, right, highest=True)


def pivotlow(src: PyneSeries | np.ndarray, left: int, right: int) -> PyneSeries | np.ndarray:
    """Detect pivot lows.

    Pine equivalent: ``ta.pivotlow(low, 5, 5)``

    A pivot low at bar ``i`` means ``src[i]`` is the lowest value
    in the window ``[i-left, i+right]``.

    Args:
        src: Input array (typically ``low``).
        left: Number of bars to the left.
        right: Number of bars to the right.

    Returns:
        Array with pivot low values on their confirmation bars, NaN elsewhere.
    """
    return _pivot(src, left, right, highest=False)


def _pivot(
    src: PyneSeries | np.ndarray,
    left: int,
    right: int,
    *,
    highest: bool,
) -> PyneSeries | np.ndarray:
    """Confirm rightmost extrema within contiguous present segments in O(n)."""
    source = to_numpy(src, dtype=np.float64)
    n = len(source)
    result = np.full(n, np.nan)
    left = int(left)
    right = int(right)
    if left < 0 or right < 0:
        return wrap_like(result, src)
    if right >= n:
        return wrap_like(result, src)

    # A missing neighbour ends comparison on that side of the center. Process
    # each present segment separately, while keeping the global warmup span.
    start = 0
    while start < n:
        if np.isnan(source[start]):
            start += 1
            continue
        end = start + 1
        while end < n and not np.isnan(source[end]):
            end += 1
        candidates: deque[int] = deque()
        added = start
        for center in range(start, end):
            stop = min(end, center + right + 1)
            while added < stop:
                value = source[added]
                if highest:
                    while candidates and source[candidates[-1]] <= value:
                        candidates.pop()
                else:
                    while candidates and source[candidates[-1]] >= value:
                        candidates.pop()
                candidates.append(added)
                added += 1
            while candidates and candidates[0] < center - left:
                candidates.popleft()
            if center >= left and center + right < n and candidates[0] == center:
                result[center + right] = source[center]
        start = end
    return wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Summation
# ═══════════════════════════════════════════════════════════════


def cum(src: PyneSeries | np.ndarray) -> PyneSeries | np.ndarray:
    """Cumulative sum.

    Pine equivalent: ``ta.cum(close)``

    Args:
        src: Input array.

    Returns:
        Cumulative sum array (NaN-aware).
    """
    source = to_numpy(src, dtype=np.float64)
    result = np.nancumsum(source)
    result[np.isnan(source)] = np.nan
    return wrap_like(result, src)


def sum_(src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
    """Sum the last ``period`` non-missing observations, carrying across gaps.

    Pine equivalent: ``math.sum(src, period)``

    Args:
        src: Input array.
        period: Window size.

    Returns:
        Rolling sum array. NaN until ``period`` observations are available.
    """
    source = to_numpy(src, dtype=np.float64)
    if period > 0:
        return wrap_like(_rolling_nonmissing_sum(source, period), src)
    # Preserve the prior Python contract for non-positive periods; this branch
    # is outside the captured native positive-length qualification.
    n = len(source)
    result = np.full(n, np.nan)
    rolling = 0.0
    nan_count = 0

    for i in range(n):
        val = source[i]
        if np.isnan(val):
            nan_count += 1
        else:
            rolling += val

        if i >= period:
            old = source[i - period]
            if np.isnan(old):
                nan_count -= 1
            else:
                rolling -= old

        if i >= period - 1 and nan_count == 0:
            result[i] = rolling

    return wrap_like(result, src)


# ═══════════════════════════════════════════════════════════════
#  Comparison Helpers
# ═══════════════════════════════════════════════════════════════


def rising(src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
    """True when the latest ``period`` valid adjacent comparisons all rise.

    Pine equivalent: ``ta.rising(close, 5)``
    """
    return _direction(src, period, upward=True)


def falling(src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
    """True when the latest ``period`` valid adjacent comparisons all fall.

    Pine equivalent: ``ta.falling(close, 5)``
    """
    return _direction(src, period, upward=False)


def _direction(src: PyneSeries | np.ndarray, period: int, *, upward: bool) -> PyneSeries | np.ndarray:
    """Missing pairs do not enter or advance the observation window, in O(n)."""
    source = to_numpy(src, dtype=np.float64)
    result = np.zeros(len(source), dtype=bool)
    if period <= 0:
        result[:] = True
        return wrap_like(result, src)
    if period >= len(source):
        return wrap_like(result, src)

    valid = ~np.isnan(source[1:]) & ~np.isnan(source[:-1])
    observed = (source[1:] > source[:-1] if upward else source[1:] < source[:-1])[valid]
    if len(observed) < period:
        return wrap_like(result, src)
    failures = np.concatenate(([0], np.cumsum(~observed, dtype=np.int64)))
    states = np.zeros(len(observed), dtype=bool)
    states[period - 1:] = failures[period:] - failures[:-period] == 0
    counts = np.cumsum(valid, dtype=np.int64)
    result[1:] = (counts >= period) & states[np.maximum(counts - 1, 0)]
    return wrap_like(result, src)
