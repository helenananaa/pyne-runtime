"""Numerical kernels used by :mod:`pyne_runtime.ta`."""

from __future__ import annotations

import math

import numpy as np

from .series import to_numpy
from ._weighted_numeric import (
    SCALE as _FLOAT_EXACT_SCALE,
    exact_convolution,
    rounded_ratio,
    scaled_float as _scaled_float,
    weighted_windows,
)
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
_FLOAT_MIN_NORMAL = float.fromhex("0x1.0p-1022")


def _exact_variance(total: int, squares: int, period: int, ddof: int = 0) -> float:
    numerator = period * squares - total * total
    denominator = _FLOAT_EXACT_SCALE * _FLOAT_EXACT_SCALE * period * (period - ddof)
    # Divide the exact integers before rounding, so intermediate squares may
    # exceed binary64 while their population variance still fits (e.g. 1e308).
    try:
        return numerator / denominator
    except OverflowError:
        return math.inf


def _round_exact_stdev(numerator: int, divisor: int, candidate: float) -> float:
    """Round an extreme square root using exact neighboring midpoint squares.

    The squared result is numerator / (exact_scale**2 * divisor). Comparing
    integer midpoint squares corrects the normalized division/sqrt rounding,
    including subnormal ties and the finite-to-infinity overflow boundary.
    """
    four_numerator = 4 * numerator
    if math.isinf(candidate):
        lower = math.nextafter(math.inf, 0.0)
        boundary = _scaled_float(lower) + (1 << 2098)  # theoretical next value: 2**1024
        return lower if four_numerator < divisor * boundary * boundary else math.inf
    if candidate == 0.0:
        return math.ulp(0.0) if four_numerator > divisor else 0.0
    current = _scaled_float(candidate)
    odd = (current >> max(current.bit_length() - 53, 0)) & 1
    lower = math.nextafter(candidate, 0.0)
    boundary = current + _scaled_float(lower)
    comparison = four_numerator - divisor * boundary * boundary
    if comparison < 0 or comparison == 0 and odd:
        return lower
    upper = math.nextafter(candidate, math.inf)
    boundary = current + ((1 << 2098) if math.isinf(upper) else _scaled_float(upper))
    comparison = four_numerator - divisor * boundary * boundary
    if comparison > 0 or comparison == 0 and odd:
        return upper
    return candidate


def _exact_stdev(total: int, squares: int, period: int, ddof: int = 0) -> float:
    """Take the square root before rounding an extreme variance to binary64."""
    variance = _exact_variance(total, squares, period, ddof)
    if math.isfinite(variance) and variance >= _FLOAT_MIN_NORMAL:
        # Preserve ordinary sqrt(variance) rounding and established outputs.
        return math.sqrt(variance)
    numerator = period * squares - total * total
    if numerator == 0:
        return 0.0
    denominator = _FLOAT_EXACT_SCALE * _FLOAT_EXACT_SCALE * period * (period - ddof)
    exponent = (numerator.bit_length() - denominator.bit_length()) // 2
    if exponent >= 0:
        normalized = numerator / (denominator << (2 * exponent))
    else:
        normalized = (numerator << (-2 * exponent)) / denominator
    # The normalized ratio lies between 1/2 and 4. Neither its square root
    # nor the exact integer calculation overflows or underflows prematurely.
    try:
        candidate = math.ldexp(math.sqrt(normalized), exponent)
    except OverflowError:
        candidate = math.inf
    return _round_exact_stdev(numerator, period * (period - ddof), candidate)


def _exact_correlation(total_a: int, total_b: int, squares_a: int,
                       squares_b: int, products: int, period: int) -> float:
    a_m2 = period * squares_a - total_a * total_a
    b_m2 = period * squares_b - total_b * total_b
    if a_m2 == 0 or b_m2 == 0:
        return 0.0
    covariance = period * products - total_a * total_b
    if covariance == 0:
        return 0.0
    # Normalize each exact moment independently before taking the square root.
    # Squaring the coefficient first would underflow representable small r.
    a_exp, b_exp, cross_exp = a_m2.bit_length(), b_m2.bit_length(), abs(covariance).bit_length()
    a_scaled, b_scaled = a_m2 / (1 << a_exp), b_m2 / (1 << b_exp)
    cross_scaled = covariance / (1 << cross_exp)
    denominator = math.sqrt(a_scaled * b_scaled)
    if (a_exp + b_exp) % 2:
        denominator *= math.sqrt(2.0)
    coefficient = math.ldexp(cross_scaled / denominator, cross_exp - (a_exp + b_exp) // 2)
    return min(max(coefficient, -1.0), 1.0)


def _exact_rolling_moment_values(source: np.ndarray, period: int, *, ddof: int = 0,
                                 source_b: np.ndarray | None = None,
                                 standard_deviation: bool = False) -> np.ndarray:
    """Bounded-work causal fallback for numerically unstable rolling moments.

    The binary64 exponent range bounds integer sizes independently of history
    and period. Each observation enters and leaves once; no local-window scans
    or repeated block recalculations are needed after fallback begins.
    """
    result = np.full(len(source), np.nan)
    window = [(0, 0, False)] * period
    total_a = total_b = squares_a = squares_b = products = valid_count = 0
    for index, value in enumerate(source):
        number_a = float(value)
        number_b = number_a if source_b is None else float(source_b[index])
        valid = math.isfinite(number_a) and math.isfinite(number_b)
        scaled_a = _scaled_float(number_a) if valid else 0
        scaled_b = _scaled_float(number_b) if valid and source_b is not None else scaled_a
        slot = index % period
        old_a, old_b, old_valid = window[slot]
        window[slot] = scaled_a, scaled_b, valid
        total_a += scaled_a - old_a
        squares_a += scaled_a * scaled_a - old_a * old_a
        valid_count += int(valid) - int(old_valid)
        if source_b is not None:
            total_b += scaled_b - old_b
            squares_b += scaled_b * scaled_b - old_b * old_b
            products += scaled_a * scaled_b - old_a * old_b
        if index < period - 1 or valid_count != period:
            continue
        if source_b is None:
            moment = _exact_stdev if standard_deviation else _exact_variance
            result[index] = moment(total_a, squares_a, period, ddof)
        else:
            result[index] = _exact_correlation(total_a, total_b, squares_a, squares_b, products, period)
    return result


def _rolling_variance_values(source: np.ndarray, period: int, ddof: int, *,
                             standard_deviation: bool = False) -> np.ndarray:
    """Compute rolling variance with causal, adaptively rebased centered blocks."""
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
    output_start = period - 1
    while output_start < n:
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        valid = np.isfinite(segment)
        # Only the first output window may choose this block's origin. Using
        # the entire block makes a future level shift change historical output.
        seed = segment[:period]
        seed_finite = seed[np.isfinite(seed)]
        anchor = float(seed_finite[0]) if len(seed_finite) else 0.0
        with np.errstate(over="ignore", invalid="ignore"):
            # Intermediate overflow is a fallback signal, not an invalid
            # finite input or an overflowing standard-deviation result.
            centered = np.where(valid, segment - anchor, 0.0)
            counts = _window_sums(valid.astype(np.int64), period)
            sums = _window_sums(centered, period)
            squared_sums = _window_sums(centered * centered, period)
            numerator = squared_sums - sums * sums / period
            squared_prefix = np.cumsum(centered * centered)[period - 1:]
        unstable = (counts == period) & (
            (numerator < 0.0)
            | ((squared_sums > 0.0) & (numerator <= 1e-10 * squared_sums))
            | ((squared_prefix > 0.0) & (squared_sums <= 1e-8 * squared_prefix))
            | ~np.isfinite(numerator)
        )
        if standard_deviation:
            small = (counts == period) & (
                (numerator > 0.0) & (numerator < _FLOAT_MIN_NORMAL * (period - ddof))
            )
            if np.any((counts == period) & (squared_sums == 0.0)):
                nonzero = _window_sums((centered != 0.0).astype(np.int64), period)
                small |= (counts == period) & (squared_sums == 0.0) & (nonzero > 0)
            unstable |= small
        suspect = np.flatnonzero(unstable)
        if len(suspect):
            stop = int(suspect[0])
            output_stop = output_start + stop
            numerator, counts = numerator[:stop], counts[:stop]
        np.maximum(numerator, 0.0, out=numerator)
        variances = numerator / (period - ddof)
        variances[counts != period] = np.nan
        if standard_deviation:
            np.sqrt(variances, out=variances)
        result[output_start:output_stop] = variances
        if len(suspect):
            exact = _exact_rolling_moment_values(
                values[output_stop - period + 1:], period, ddof=ddof,
                standard_deviation=standard_deviation)
            result[output_stop:] = exact[period - 1:]
            break
        output_start = output_stop
    return result


def _rolling_nonmissing_variance_values(source: np.ndarray, period: int, ddof: int, *,
                                        standard_deviation: bool = False) -> np.ndarray:
    """Run the stable variance kernel on present observations and restore time positions."""
    values = np.asarray(source, dtype=np.float64)
    present = ~np.isnan(values)
    if np.all(present):
        return _rolling_variance_values(values, period, ddof, standard_deviation=standard_deviation)
    compact_result = _rolling_variance_values(
        values[present], period, ddof, standard_deviation=standard_deviation)
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
    """Compute rolling Pearson correlation using causal centered blocks."""
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
    output_start = period - 1
    while output_start < n:
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        a_segment = a[segment_start:output_stop]
        b_segment = b[segment_start:output_stop]
        valid = np.isfinite(a_segment) & np.isfinite(b_segment)
        seed_valid = valid[:period]
        a_seed, b_seed = a_segment[:period], b_segment[:period]
        a_anchor = float(a_seed[seed_valid][0]) if np.any(seed_valid) else 0.0
        b_anchor = float(b_seed[seed_valid][0]) if np.any(seed_valid) else 0.0
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
        a_prefix = np.cumsum(a_centered * a_centered)[period - 1:]
        b_prefix = np.cumsum(b_centered * b_centered)[period - 1:]
        unstable = (counts == period) & (
            (a_m2 < 0.0) | (b_m2 < 0.0)
            | ((a_squared_sums > 0.0) & (a_m2 <= 1e-10 * a_squared_sums))
            | ((b_squared_sums > 0.0) & (b_m2 <= 1e-10 * b_squared_sums))
            | ((a_prefix > 0.0) & (a_squared_sums <= 1e-8 * a_prefix))
            | ((b_prefix > 0.0) & (b_squared_sums <= 1e-8 * b_prefix))
            | ~np.isfinite(a_m2) | ~np.isfinite(b_m2)
        )
        suspect = np.flatnonzero(unstable)
        if len(suspect):
            stop = int(suspect[0])
            output_stop = output_start + stop
            a_m2, b_m2, covariance, counts = (
                values[:stop] for values in (a_m2, b_m2, covariance, counts)
            )
        np.maximum(a_m2, 0.0, out=a_m2)
        np.maximum(b_m2, 0.0, out=b_m2)
        with np.errstate(divide="ignore", invalid="ignore"):
            correlations = covariance / (np.sqrt(a_m2) * np.sqrt(b_m2))
        invalid = (counts != period) | (a_m2 <= 0.0) | (b_m2 <= 0.0)
        correlations[invalid] = np.nan
        zero = ((counts == period) & np.isfinite(a_m2) & np.isfinite(b_m2)
                & ((a_m2 == 0.0) | (b_m2 == 0.0)))
        correlations[zero] = 0.0
        np.clip(correlations, -1.0, 1.0, out=correlations)
        result[output_start:output_stop] = correlations
        if len(suspect):
            exact = _exact_rolling_moment_values(
                a[output_stop - period + 1:], period,
                source_b=b[output_stop - period + 1:])
            result[output_stop:] = exact[period - 1:]
            break
        output_start = output_stop
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
    # A one-observation window is exactly that observation. Subtracting two
    # cumulative totals can introduce historical/future-dependent roundoff.
    sums = compact.copy() if period == 1 else _rolling_nansum(compact, period)
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
    magnitudes = np.abs(finite_values)
    largest_seen = np.maximum.accumulate(magnitudes)
    smallest_seen = np.minimum.accumulate(np.where(magnitudes > 0.0, magnitudes, np.inf))
    # Admission to a numerical fallback must depend only on history available
    # at this output. A future tiny sample must not rewrite earlier windows.
    dynamic_range_is_unsafe = (
        smallest_seen[period - 1:] <= largest_seen[period - 1:] * np.finfo(np.float64).eps * 4.0
    )
    exact_mask = nonfinite_sums | dynamic_range_is_unsafe
    if np.any(exact_mask):
        # Binary64 has a bounded exponent range, so fixed-scale integer
        # accumulation remains O(n) while recovering after finite overflow.
        exact = _exact_window_sums(finite_values, period)
        sums[exact_mask] = exact[exact_mask]
    block_mask = cancellation_risk & ~exact_mask
    if np.any(block_mask):
        # Prefix subtraction can erase a small window sum after a much larger
        # historical cumulative value. Block-local prefix/suffix sums recover
        # without an O(n*period) fallback.
        blocked = _block_window_sums(finite_values, period)
        sums[block_mask] = blocked[block_mask]
    if not np.any(np.isinf(source)):
        return sums
    positive_infinity = _window_sums((source == np.inf).astype(np.int64), period)
    negative_infinity = _window_sums((source == -np.inf).astype(np.int64), period)

    both = (positive_infinity > 0) & (negative_infinity > 0)
    sums[positive_infinity > 0] = np.inf
    sums[negative_infinity > 0] = -np.inf
    sums[both] = np.nan
    return sums


def _rolling_weighted_average_values(source: np.ndarray, period: int) -> np.ndarray:
    """Round exact causal weighted sums after division, in O(n) work."""
    values = np.asarray(source, dtype=np.float64)
    result = np.empty(len(values) - period + 1, dtype=np.float64)
    denominator = _FLOAT_EXACT_SCALE * (period * (period + 1) // 2)
    for index, _, weighted, _ in weighted_windows(values, period):
        result[index-period+1] = rounded_ratio(weighted, denominator)
    return result


def _rolling_linear_regression_values(
    source: np.ndarray,
    period: int,
    offset: int,
) -> np.ndarray:
    """Compute rolling least-squares values from exact causal moments in O(n)."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result
    if period == 1:
        return values.copy()

    spread = period * period - 1
    denominator = _FLOAT_EXACT_SCALE * period * spread
    target = period - 1 - 2 * offset
    for index, total, weighted, valid in weighted_windows(values, period):
        if valid == period:
            numerator = total * spread + (6 * weighted - 3 * (period + 1) * total) * target
            result[index] = rounded_ratio(numerator, denominator)
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


def _rolling_missing_percentile_values(
    values: np.ndarray, period: int, percentage: float, *, linear: bool,
    start: int = 0,
) -> np.ndarray:
    """Retain native order-update state through missing observations.

    Missing slots are not a total-order sentinel. A replacement moves from the
    expired slot, so equal current windows may reflect different earlier history.
    Native matrix and separately frozen-model holdout evidence cover this path.
    List updates cost O(period) in the worst case; complete arrays use Fenwick.
    """
    result = np.full(len(values), np.nan)
    # Before the first missing bar, native order is value ascending with newer
    # equal observations first. Build that one bounded window directly instead
    # of repeating the missing-order list scans over the whole finite prefix.
    ordered = sorted(((index, float(values[index]))
                      for index in range(max(start-period, 0), start)),
                     key=lambda item: (item[1], -item[0]))
    pct = float(np.clip(percentage, 0.0, 100.0))
    nearest = max(int(np.ceil(pct / 100.0 * period)), 1) - 1
    virtual = float(np.clip(pct / 100.0 * period - 0.5, 0.0, period - 1))
    lower = int(np.floor(virtual))
    upper = min(lower + 1, period - 1)
    for index in range(start, len(values)):
        raw = values[index]
        number = float(raw)
        expired = None
        if index >= period:
            outgoing = float(values[index-period])
            if np.isnan(outgoing):
                expired = next(j for j, (at, _) in enumerate(ordered) if at == index-period)
            else:
                # Equal outgoing values are interchangeable, but the rightmost
                # slot determines the insertion anchor in a partially ordered list.
                expired = next(j for j in range(len(ordered)-1, -1, -1) if ordered[j][1] == outgoing)
        old = np.nan
        if expired is not None:
            _, old = ordered.pop(expired)
        if np.isnan(number):
            position = len(ordered)
        elif expired is None or np.isnan(old):
            position = next((j for j, (_, value) in enumerate(ordered) if number <= value), len(ordered))
        else:
            position = expired
            if number <= old:
                while position and not number > ordered[position-1][1]:
                    position -= 1
            else:
                while position < len(ordered) and not number <= ordered[position][1]:
                    position += 1
        ordered.insert(position, (index, number))
        if index >= period - 1:
            result[index] = (_interpolate_hazen(ordered[lower][1], ordered[upper][1], virtual-lower)
                             if linear else ordered[nearest][1])
    return result


def _rolling_percentile_values(
    source: np.ndarray,
    period: int,
    percentage: float,
    *,
    linear: bool,
) -> np.ndarray:
    """Use native missing-order state, or O(n log n) complete-window statistics."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result

    valid = ~np.isnan(values)
    if not np.any(valid):
        return result
    if not np.all(valid) and not np.isinf(values).any():
        start = int(np.flatnonzero(~valid)[0])
        result = _rolling_missing_percentile_values(
            values, period, percentage, linear=linear, start=start)
        result[:start] = _rolling_percentile_values(values[:start], period, percentage, linear=linear)
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


def _valid_weighted_convolution(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return exact valid correlation using subquadratic integer convolution."""
    source = np.asarray(values, dtype=np.float64)
    kernel = np.asarray(weights, dtype=np.float64)
    return exact_convolution(source, kernel)


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
