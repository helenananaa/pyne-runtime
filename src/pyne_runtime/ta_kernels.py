"""Numerical kernels used by :mod:`pyne_runtime.ta`."""

from __future__ import annotations

import numpy as np

from .series import to_numpy
def _fixnan(values: np.ndarray) -> np.ndarray:
    result = np.array(values, dtype=np.float64, copy=True)
    last = np.nan
    for idx, value in enumerate(result):
        if np.isnan(value):
            if not np.isnan(last):
                result[idx] = last
            continue
        last = value
    return result


_ROLLING_REBASE_CHUNK = 4096
_FLOAT_EXACT_SCALE = 1 << 1074


def _rolling_nonmissing_sum(source: np.ndarray, period: int) -> np.ndarray:
    """Sum the last period present samples, retaining the sum across gaps.

    VWMA needs independent observation windows for price*volume and volume.
    Compact once, reuse the robust rolling sum, then map back in linear time.
    """
    values = np.asarray(source, dtype=np.float64)
    result = np.full(len(values), np.nan)
    present = ~np.isnan(values)
    compact = values[present]
    if period <= 0 or len(compact) < period:
        return result
    sums = _rolling_nansum(compact, period)
    counts = np.cumsum(present)
    ready = counts >= period
    result[ready] = sums[counts[ready] - period]
    return result


def _window_sums(values: np.ndarray, period: int) -> np.ndarray:
    cumulative = np.concatenate(
        (np.zeros(1, dtype=values.dtype), np.cumsum(values, dtype=values.dtype))
    )
    return cumulative[period:] - cumulative[:-period]


def _block_window_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Sum windows from block-local prefixes/suffixes, avoiding cumulative poisoning."""
    source = np.asarray(values, dtype=np.float64)
    n = len(source)
    if period == 1:
        return source.copy()

    prefix = np.empty(n, dtype=np.float64)
    suffix = np.empty(n, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        for block_start in range(0, n, period):
            block_stop = min(block_start + period, n)
            block = source[block_start:block_stop]
            prefix[block_start:block_stop] = np.cumsum(block)
            suffix[block_start:block_stop] = np.cumsum(block[::-1])[::-1]

        starts = np.arange(0, n - period + 1, dtype=np.intp)
        ends = starts + period - 1
        sums = suffix[starts] + prefix[ends]
        same_block = starts // period == ends // period
        sums[same_block] = prefix[ends[same_block]]
    return sums


def _exact_window_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Accumulate finite binary64 values exactly, rounding once per output window."""
    source = np.asarray(values, dtype=np.float64)
    result = np.empty(len(source) - period + 1, dtype=np.float64)
    window = [0] * period
    total = 0
    for index, value in enumerate(source):
        numerator, denominator = float(value).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_value = numerator << shift
        slot = index % period
        if index >= period:
            total -= window[slot]
        window[slot] = scaled_value
        total += scaled_value
        if index < period - 1:
            continue
        output_index = index - period + 1
        try:
            result[output_index] = total / _FLOAT_EXACT_SCALE
        except OverflowError:
            result[output_index] = np.inf if total > 0 else -np.inf
    return result


def _rolling_nansum(values: np.ndarray, period: int) -> np.ndarray:
    """Return full-window ``nansum`` values without letting infinities poison later windows."""
    source = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(source)
    finite_values = np.where(finite, source, 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        cumulative = np.concatenate(([0.0], np.cumsum(finite_values)))
        left = cumulative[period:]
        right = cumulative[:-period]
        sums = left - right
        cancellation_bound = (
            np.maximum(np.abs(left), np.abs(right)) * np.finfo(np.float64).eps * 4.0
        )
    nonfinite_sums = ~np.isfinite(sums)
    cancellation_risk = np.abs(sums) <= cancellation_bound
    magnitudes = np.abs(finite_values[finite_values != 0.0])
    dynamic_range_is_unsafe = bool(
        len(magnitudes)
        and np.min(magnitudes) <= np.max(magnitudes) * np.finfo(np.float64).eps * 4.0
    )
    if np.any(nonfinite_sums) or dynamic_range_is_unsafe:
        # Binary64 has a bounded exponent range, so fixed-scale integer
        # accumulation remains O(n) while recovering after finite overflow.
        sums = _exact_window_sums(finite_values, period)
    elif np.any(cancellation_risk):
        # Prefix subtraction can erase a small window sum after a much larger
        # historical cumulative value. Block-local prefix/suffix sums recover
        # without an O(n*period) fallback.
        sums = _block_window_sums(finite_values, period)
    positive_infinity = _window_sums((source == np.inf).astype(np.int64), period)
    negative_infinity = _window_sums((source == -np.inf).astype(np.int64), period)

    both = (positive_infinity > 0) & (negative_infinity > 0)
    sums[positive_infinity > 0] = np.inf
    sums[negative_infinity > 0] = -np.inf
    sums[both] = np.nan
    return sums


def _exact_rolling_weighted_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Return 1..period weighted sums with exact binary64 accumulation."""
    source = np.asarray(values, dtype=np.float64)
    result = np.empty(len(source) - period + 1, dtype=np.float64)
    scaled_values: list[int] = []
    for value in source:
        numerator, denominator = float(value).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_values.append(numerator << shift)

    simple = sum(scaled_values[:period])
    weighted = sum((index + 1) * value for index, value in enumerate(scaled_values[:period]))
    for output_index in range(len(result)):
        try:
            result[output_index] = weighted / _FLOAT_EXACT_SCALE
        except OverflowError:
            result[output_index] = np.inf if weighted > 0 else -np.inf
        next_index = output_index + period
        if next_index >= len(source):
            continue
        outgoing = scaled_values[output_index]
        incoming = scaled_values[next_index]
        weighted = weighted - simple + period * incoming
        simple = simple - outgoing + incoming
    return result


def _rolling_weighted_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Return 1..period weighted sums in O(n), periodically rebasing drift."""
    source = np.asarray(values, dtype=np.float64)
    n = len(source)
    result = np.empty(n - period + 1, dtype=np.float64)
    weights = np.arange(1, period + 1, dtype=np.float64)
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    with np.errstate(over="ignore", invalid="ignore"):
        for output_start in range(first_output, n, chunk_size):
            output_stop = min(output_start + chunk_size, n)
            segment_start = output_start - period + 1
            segment = source[segment_start:output_stop]
            simple = float(np.sum(segment[:period]))
            weighted = float(np.dot(segment[:period], weights))
            for end_index in range(output_start, output_stop):
                result[end_index - period + 1] = weighted
                relative_end = end_index - output_start + period - 1
                next_index = relative_end + 1
                if next_index >= len(segment):
                    continue
                outgoing = segment[relative_end - period + 1]
                incoming = segment[next_index]
                weighted = weighted - simple + period * incoming
                simple = simple - outgoing + incoming

    # An overflowing recurrence can otherwise remain infinite after the large
    # value leaves its window. Exact integer state preserves O(n) recovery.
    if np.any(~np.isfinite(result)) and np.all(np.isfinite(source)):
        return _exact_rolling_weighted_sums(source, period)
    return result


def _rolling_weighted_average_values(source: np.ndarray, period: int) -> np.ndarray:
    """Compute finite weighted averages with block-local centering."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.empty(n - period + 1, dtype=np.float64)
    denominator = period * (period + 1) / 2.0
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        finite = np.isfinite(segment)
        anchor = float(np.mean(segment[finite])) if np.any(finite) else 0.0
        centered = np.where(finite, segment - anchor, 0.0)
        weighted = _rolling_weighted_sums(centered, period)
        result[output_start - period + 1 : output_stop - period + 1] = (
            anchor + weighted / denominator
        )
    return result


def _rolling_linear_regression_values(
    source: np.ndarray,
    period: int,
    offset: int,
) -> np.ndarray:
    """Compute rolling least-squares values in O(n) with centered chunks."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result
    if period == 1:
        return values.copy()

    x_mean = (period - 1) / 2.0
    denom = period * (period * period - 1) / 12.0
    target_x = float(period - 1 - offset)
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        finite = np.isfinite(segment)
        if not np.any(finite):
            continue
        anchor = float(np.mean(segment[finite]))
        centered = np.where(finite, segment - anchor, 0.0)
        counts = _window_sums(finite.astype(np.int64), period)
        sums = _window_sums(centered, period)
        weighted = _rolling_weighted_sums(centered, period) - sums
        slopes = (weighted - x_mean * sums) / denom
        means = anchor + sums / period
        values_at_target = means + slopes * (target_x - x_mean)
        values_at_target[counts != period] = np.nan
        result[output_start:output_stop] = values_at_target
    return result


class _FenwickTree:
    """Coordinate-compressed rolling counts and sums in O(log n)."""

    def __init__(self, size: int) -> None:
        self.counts = np.zeros(size + 1, dtype=np.int64)
        self.sums = [0] * (size + 1)

    def add(self, index: int, count: int, value: int) -> None:
        position = index + 1
        while position < len(self.counts):
            self.counts[position] += count
            self.sums[position] += value
            position += position & -position

    def prefix(self, stop: int) -> tuple[int, int]:
        count = 0
        total = 0
        position = stop
        while position > 0:
            count += int(self.counts[position])
            total += self.sums[position]
            position -= position & -position
        return count, total

    def kth(self, order: int) -> int:
        """Return the zero-based coordinate containing a one-based order statistic."""
        position = 0
        size = len(self.counts) - 1
        step = 1 << (size.bit_length() - 1)
        remaining = int(order)
        while step:
            candidate = position + step
            if candidate < len(self.counts) and self.counts[candidate] < remaining:
                remaining -= int(self.counts[candidate])
                position = candidate
            step >>= 1
        return position


def _rolling_mean_and_mad(
    source: np.ndarray,
    period: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return full-window means and exact mean absolute deviations in O(n log n)."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    means = np.full(n, np.nan)
    deviations = np.full(n, np.nan)
    if period <= 0 or period > n:
        return means, deviations

    finite = np.isfinite(values)
    if period == 1:
        means[finite] = values[finite]
        deviations[finite] = 0.0
        return means, deviations
    if not np.any(finite):
        return means, deviations
    coordinates = np.unique(values[finite])
    ranks = np.full(n, -1, dtype=np.intp)
    ranks[finite] = np.searchsorted(coordinates, values[finite])
    scaled_values = [0] * n
    for index in np.flatnonzero(finite):
        numerator, denominator = float(values[index]).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_values[int(index)] = numerator << shift
    tree = _FenwickTree(len(coordinates))
    invalid_count = 0
    window_sum = 0

    for index in range(n):
        if finite[index]:
            scaled = scaled_values[index]
            tree.add(int(ranks[index]), 1, scaled)
            window_sum += scaled
        else:
            invalid_count += 1
        if index >= period:
            outgoing = index - period
            if finite[outgoing]:
                scaled = scaled_values[outgoing]
                tree.add(int(ranks[outgoing]), -1, -scaled)
                window_sum -= scaled
            else:
                invalid_count -= 1
        if index < period - 1 or invalid_count:
            continue

        mean = window_sum / (_FLOAT_EXACT_SCALE * period)
        split = int(np.searchsorted(coordinates, mean, side="right"))
        left_count, left_sum = tree.prefix(split)
        right_count = period - left_count
        right_sum = window_sum - left_sum
        minimum = tree.kth(1)
        maximum = tree.kth(period)
        if minimum == maximum:
            means[index] = mean
            deviations[index] = 0.0
            continue
        absolute_numerator = (
            window_sum * left_count
            - period * left_sum
            + period * right_sum
            - window_sum * right_count
        )
        means[index] = mean
        deviations[index] = max(
            absolute_numerator / (_FLOAT_EXACT_SCALE * period * period),
            0.0,
        )
    return means, deviations


def _interpolate_hazen(lower: float, upper: float, fraction: float) -> float:
    with np.errstate(over="ignore", invalid="ignore"):
        difference = upper - lower
        if fraction >= 0.5:
            return float(upper - difference * (1.0 - fraction))
        return float(lower + difference * fraction)


def _rolling_percentile_values(
    source: np.ndarray,
    period: int,
    percentage: float,
    *,
    linear: bool,
) -> np.ndarray:
    """Compute exact rolling order statistics in O(n log n)."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result

    valid = ~np.isnan(values)
    if not np.any(valid):
        return result
    coordinates = np.unique(values[valid])
    ranks = np.full(n, -1, dtype=np.intp)
    ranks[valid] = np.searchsorted(coordinates, values[valid])
    tree = _FenwickTree(len(coordinates))
    invalid_count = 0
    pct = float(np.clip(percentage, 0.0, 100.0))
    nearest_rank = max(int(np.ceil(pct / 100.0 * period)), 1)
    virtual_index = pct / 100.0 * period - 0.5

    for index in range(n):
        if valid[index]:
            tree.add(int(ranks[index]), 1, 0.0)
        else:
            invalid_count += 1
        if index >= period:
            outgoing = index - period
            if valid[outgoing]:
                tree.add(int(ranks[outgoing]), -1, 0.0)
            else:
                invalid_count -= 1
        if index < period - 1 or invalid_count:
            continue

        if not linear:
            result[index] = coordinates[tree.kth(nearest_rank)]
            continue
        if virtual_index < 0.0:
            boundary = float(coordinates[tree.kth(1)])
            result[index] = _interpolate_hazen(boundary, boundary, 0.0)
            continue
        if virtual_index >= period - 1:
            boundary = float(coordinates[tree.kth(period)])
            result[index] = _interpolate_hazen(boundary, boundary, 0.0)
            continue
        lower_order = int(np.floor(virtual_index)) + 1
        fraction = virtual_index - np.floor(virtual_index)
        lower = float(coordinates[tree.kth(lower_order)])
        upper = float(coordinates[tree.kth(lower_order + 1)])
        result[index] = _interpolate_hazen(lower, upper, fraction)
    return result


_DIRECT_CONVOLUTION_WORK_LIMIT = 1_000_000


def _valid_weighted_convolution(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return valid correlation, switching to FFT before direct work can grow quadratic."""
    source = np.asarray(values, dtype=np.float64)
    kernel = np.asarray(weights, dtype=np.float64)
    if len(source) * len(kernel) <= _DIRECT_CONVOLUTION_WORK_LIMIT:
        return np.correlate(source, kernel, mode="valid")

    finite = np.isfinite(source)
    anchor = float(np.mean(source[finite])) if np.any(finite) else 0.0
    centered = np.where(finite, source - anchor, 0.0)
    output_size = len(source) + len(kernel) - 1
    fft_size = 1 << (output_size - 1).bit_length()
    transformed = np.fft.rfft(centered, fft_size) * np.fft.rfft(kernel[::-1], fft_size)
    convolution = np.fft.irfft(transformed, fft_size)[:output_size]
    return convolution[len(kernel) - 1 : len(source)] + anchor * np.sum(kernel)


def _valid_boolean_correlation(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    correlated = _valid_weighted_convolution(
        np.asarray(values, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
    )
    return np.rint(correlated).astype(np.int64)


def _broadcast_ta_input(
    value: object,
    length: int,
    name: str,
    *,
    function: str = "ta.vwap()",
) -> np.ndarray:
    """Broadcast a scalar TA argument or validate a bar-aligned series."""
    raw = to_numpy(value)
    if raw.ndim == 0:
        raw = np.full(length, raw.item())
    elif raw.ndim != 1 or len(raw) != length:
        raise ValueError(f"{function} {name} must be scalar or match the chart length")
    try:
        return np.asarray(raw, dtype=np.float64)
    except (TypeError, ValueError):
        raise TypeError(f"{function} {name} must contain numeric values") from None


def _broadcast_pivot_types(value: object, length: int) -> tuple[str, ...]:
    raw = to_numpy(value)
    if raw.ndim == 0:
        values = [raw.item()] * length
    elif raw.ndim == 1 and len(raw) == length:
        values = raw.tolist()
    else:
        raise ValueError("ta.pivot_point_levels() type must be scalar or match the chart length")
    return tuple(_normalize_pivot_type(item) for item in values)


def _normalize_pivot_type(value: object) -> str:
    if not isinstance(value, str | np.str_):
        raise TypeError("ta.pivot_point_levels() type must contain string values")
    normalized = str(value).strip().lower()
    aliases = {
        "traditional": "traditional",
        "fibonacci": "fibonacci",
        "woodie": "woodie",
        "classic": "classic",
        "dm": "dm",
        "demark": "dm",
        "camarilla": "camarilla",
    }
    try:
        return aliases[normalized]
    except KeyError:
        allowed = "Traditional, Fibonacci, Woodie, Classic, DM, Camarilla"
        raise ValueError(f"ta.pivot_point_levels() type must be one of: {allowed}") from None


def _pivot_level_values(
    pivot_type: str,
    *,
    period_open: float,
    period_high: float,
    period_low: float,
    period_close: float,
    current_open: float,
) -> np.ndarray:
    levels = np.full(11, np.nan, dtype=np.float64)
    required = (period_high, period_low)
    if pivot_type == "woodie":
        required += (current_open,)
    else:
        required += (period_close,)
    if pivot_type == "dm":
        required += (period_open,)
    if not all(np.isfinite(value) for value in required):
        return levels

    high = period_high
    low = period_low
    close = period_close
    price_range = high - low

    if pivot_type == "traditional":
        pivot = (high + low + close) / 3.0
        levels[:] = (
            pivot,
            2.0 * pivot - low,
            2.0 * pivot - high,
            pivot + price_range,
            pivot - price_range,
            2.0 * pivot + high - 2.0 * low,
            2.0 * pivot - 2.0 * high + low,
            3.0 * pivot + high - 3.0 * low,
            3.0 * pivot - 3.0 * high + low,
            4.0 * pivot + high - 4.0 * low,
            4.0 * pivot - 4.0 * high + low,
        )
    elif pivot_type == "fibonacci":
        pivot = (high + low + close) / 3.0
        levels[:7] = (
            pivot,
            pivot + 0.382 * price_range,
            pivot - 0.382 * price_range,
            pivot + 0.618 * price_range,
            pivot - 0.618 * price_range,
            pivot + price_range,
            pivot - price_range,
        )
    elif pivot_type == "woodie":
        pivot = (high + low + 2.0 * current_open) / 4.0
        r3 = high + 2.0 * (pivot - low)
        s3 = low - 2.0 * (high - pivot)
        levels[:9] = (
            pivot,
            2.0 * pivot - low,
            2.0 * pivot - high,
            pivot + price_range,
            pivot - price_range,
            r3,
            s3,
            r3 + price_range,
            s3 - price_range,
        )
    elif pivot_type == "classic":
        pivot = (high + low + close) / 3.0
        levels[:9] = (
            pivot,
            2.0 * pivot - low,
            2.0 * pivot - high,
            pivot + price_range,
            pivot - price_range,
            pivot + 2.0 * price_range,
            pivot - 2.0 * price_range,
            pivot + 3.0 * price_range,
            pivot - 3.0 * price_range,
        )
    elif pivot_type == "dm":
        if period_open == close:
            x_value = high + low + 2.0 * close
        elif close > period_open:
            x_value = 2.0 * high + low + close
        else:
            x_value = 2.0 * low + high + close
        levels[:3] = (
            x_value / 4.0,
            x_value / 2.0 - low,
            x_value / 2.0 - high,
        )
    else:
        pivot = (high + low + close) / 3.0
        r5 = np.nan if low == 0.0 else (high / low) * close
        s5 = np.nan if not np.isfinite(r5) else close - (r5 - close)
        levels[:] = (
            pivot,
            close + 1.1 * price_range / 12.0,
            close - 1.1 * price_range / 12.0,
            close + 1.1 * price_range / 6.0,
            close - 1.1 * price_range / 6.0,
            close + 1.1 * price_range / 4.0,
            close - 1.1 * price_range / 4.0,
            close + 1.1 * price_range / 2.0,
            close - 1.1 * price_range / 2.0,
            r5,
            s5,
        )
    return levels
