"""Exact bounded-width binary64 arithmetic for causal weighted calculations.

Each observation enters and leaves a rolling sum once. General fixed-weight
convolution uses integer polynomial multiplication, with byte-aligned slots wide
enough to prevent carries between coefficients. Removing common powers of two
keeps ordinary inputs small. Widely separated exponents can use several narrow
polynomials whose coefficients are recombined exactly before rounding. Only
final results are rounded, so algorithm selection and future samples cannot
change an already calculated window.
"""
from __future__ import annotations

import math

import numpy as np


SCALE = 1 << 1074


def scaled_float(value: float) -> int:
    numerator, denominator = value.as_integer_ratio()
    return numerator << (1074 - (denominator.bit_length() - 1))


def rounded_ratio(numerator: int, denominator: int) -> float:
    try:
        return numerator / denominator
    except OverflowError:
        return math.inf if numerator > 0 else -math.inf


def weighted_windows(source: np.ndarray, period: int):
    """Yield full-window exact raw/1..period sums and finite observation counts."""
    window = [(0, False)] * period
    total = weighted = valid_count = 0
    for index, value in enumerate(source):
        number = float(value)
        valid = math.isfinite(number)
        incoming = scaled_float(number) if valid else 0
        slot = index % period
        outgoing, was_valid = window[slot]
        if index < period:
            weighted += (index + 1) * incoming
        else:
            weighted += period * incoming - total
        total += incoming - outgoing
        valid_count += int(valid) - int(was_valid)
        window[slot] = incoming, valid
        if index >= period - 1:
            yield index, total, weighted, valid_count


def _integer_coefficients(values: np.ndarray) -> tuple[list[int], int]:
    coefficients = [scaled_float(float(value)) for value in values]
    nonzero = [abs(value) for value in coefficients if value]
    shift = min((value & -value).bit_length() - 1 for value in nonzero) if nonzero else 0
    return [value >> shift for value in coefficients], shift


def _packed_polynomial(coefficients: list[int], offset: int, width: int) -> int:
    return int.from_bytes(b"".join((value + offset).to_bytes(width, "little")
        for value in coefficients), "little")


def _coefficient_width(value_span: int, kernel_span: int, period: int) -> int:
    # Every product coefficient has at most period nonnegative terms.
    bound = period * value_span * kernel_span
    return max((max(bound, value_span, kernel_span).bit_length() + 7) // 8, 1)


def _convolution_coefficients(values: list[int], kernel: list[int]):
    """Yield unrounded correlation coefficients from one integer product."""
    period = len(kernel)
    value_offset = max(-min(values, default=0), 0)
    kernel_offset = max(-min(kernel, default=0), 0)
    max_value = max(values, default=0) + value_offset
    max_kernel = max(kernel, default=0) + kernel_offset
    width = _coefficient_width(max_value, max_kernel, period)
    packed = (_packed_polynomial(values, value_offset, width)
              * _packed_polynomial(kernel, kernel_offset, width))
    coefficients = memoryview(packed.to_bytes((len(values) + period - 1) * width, "little"))
    kernel_sum = sum(kernel)
    total = sum(values[:period])
    correction = value_offset * kernel_sum + period * value_offset * kernel_offset
    for at in range(len(values) - period + 1):
        start = (at + period - 1) * width
        coefficient = int.from_bytes(coefficients[start:start+width], "little")
        yield coefficient - correction - kernel_offset * total
        if at + period < len(values):
            total += values[at+period] - values[at]


def _exponent_bands(values: list[int]) -> list[tuple[int, list[tuple[int, int]], int]]:
    """Split binary64 significands by powers of two without rounding.

    A binary64 significand has at most 53 bits. Rounding its trailing exponent
    down to a multiple of 53 leaves each nonzero band coefficient below 106
    bits, independent of the distance between the original exponents. Entries
    stay sparse until the multiplication budget has selected this algorithm.
    """
    grouped: dict[int, tuple[list[tuple[int, int]], int, int]] = {}
    for index, number in enumerate(values):
        if number:
            absolute = abs(number)
            shift = (((absolute & -absolute).bit_length() - 1) // 53) * 53
            part = number >> shift
            entries, low, high = grouped.get(shift, ([], 0, 0))
            entries.append((index, part))
            grouped[shift] = entries, min(low, part), max(high, part)
    return [(shift, entries, high - low) for shift, (entries, low, high) in grouped.items()]


def _band_convolution(values: list[int], kernel: list[int], value_span: int,
                      kernel_span: int, value_bits: int, kernel_bits: int):
    """Return exact band coefficients only when their padded work is smaller."""
    # Ordinary coefficients already fit in twice the binary64 significand
    # width, so avoid constructing sparse bands for this common case.
    # A one-coefficient kernel is already a scalar integer multiplication;
    # splitting it adds passes without reducing a polynomial product's degree.
    if len(kernel) == 1 or (value_bits <= 106 and kernel_bits <= 106):
        return None
    period = len(kernel)
    dense_width = _coefficient_width(value_span, kernel_span, period)
    minimum_width = (53 + 7) // 8
    # Controlled short-window probes show that a marginal byte saving cannot
    # amortize repeated Python passes. Require twice the compression through
    # 32 coefficients. A wide operand needs at least two bands, so this lower
    # bound also skips sparse-band planning when it cannot meet that margin.
    margin = 2 if period <= 32 else 1
    if dense_width <= margin * 2 * minimum_width:
        return None
    dense_values = [(0, None, value_span)]
    dense_kernel = [(0, None, kernel_span)]
    value_bands = _exponent_bands(values) if value_bits > 106 else dense_values
    kernel_bands = _exponent_bands(kernel) if kernel_bits > 106 else dense_kernel
    # Each pair packs the same sample/window counts. Comparing the sum of its
    # guarded byte widths with the dense width bounds total padded bytes and
    # prevents a large Cartesian product of exponent bands.
    choices = [(value_bands, kernel_bands), (value_bands, dense_kernel),
               (dense_values, kernel_bands)]

    def padded_width(choice):
        # Even a one-bit literal incurs one Python encoding/decoding pass per
        # observation. Charge each pair at least a binary64 significand (seven
        # bytes), so many tiny sparse bands cannot underprice those passes.
        return sum(max(_coefficient_width(a[2], b[2], period), minimum_width)
                   for a in choice[0] for b in choice[1])

    value_bands, kernel_bands = min(choices, key=padded_width)
    if margin * padded_width((value_bands, kernel_bands)) >= dense_width:
        return None
    result = [0] * (len(values) - period + 1)
    for value_shift, value_entries, _ in value_bands:
        small_values = values
        if value_entries is not None:
            small_values = [0] * len(values)
            for index, part in value_entries:
                small_values[index] = part
        for kernel_shift, kernel_entries, _ in kernel_bands:
            small_kernel = kernel
            if kernel_entries is not None:
                small_kernel = [0] * period
                for index, part in kernel_entries:
                    small_kernel[index] = part
            shift = value_shift + kernel_shift
            for index, coefficient in enumerate(_convolution_coefficients(small_values, small_kernel)):
                result[index] += coefficient << shift
    return result


def exact_convolution(source: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return valid correlation without a window scan or floating FFT leakage.

    Python's large-integer multiplication uses subquadratic multiplication.
    Signed inputs and weights use independent nonnegative offsets whose cross
    terms are removed exactly after multiplication. Separated binary64 exponent
    bands use narrow products when their total padded byte count is smaller;
    otherwise one dense product avoids an excessive number of band pairs.
    Both paths recombine exact integers and round only the final window result.
    """
    values, value_shift = _integer_coefficients(source)
    kernel, kernel_shift = _integer_coefficients(weights[::-1])
    period = len(kernel)
    result = np.empty(len(values) - period + 1)
    if not any(values) or not any(kernel):
        result.fill(0.0)
        return result
    if period == 2:
        # A fixed two-coefficient expression needs only two integer products
        # and one addition per output. It avoids polynomial/band setup while
        # remaining linear for all source lengths and binary64 exponent ranges.
        left_weight, right_weight = kernel[1], kernel[0]
        coefficients = (values[at] * left_weight + values[at+1] * right_weight
                        for at in range(len(values) - 1))
    else:
        value_low, value_high = min(values), max(values)
        kernel_low, kernel_high = min(kernel), max(kernel)
        value_span = value_high - min(value_low, 0)
        kernel_span = kernel_high - min(kernel_low, 0)
        coefficients = _band_convolution(values, kernel, value_span, kernel_span,
                                        max(abs(value_low), abs(value_high)).bit_length(),
                                        max(abs(kernel_low), abs(kernel_high)).bit_length())
        if coefficients is None:
            coefficients = _convolution_coefficients(values, kernel)
    exponent = 2148 - value_shift - kernel_shift
    divisor = 1 << max(exponent, 0)
    for at, numerator in enumerate(coefficients):
        if exponent < 0:
            numerator <<= -exponent
        result[at] = rounded_ratio(numerator, divisor)
    return result
