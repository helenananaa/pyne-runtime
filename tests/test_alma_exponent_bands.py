"""Rounding and work-selection checks for exact exponent-band convolution."""
from fractions import Fraction
import math
import sys

import numpy as np
import pytest

from pyne_runtime import _weighted_numeric as numeric


def _reference(source, weights):
    results = []
    for start in range(len(source) - len(weights) + 1):
        value = sum(Fraction(float(a)) * Fraction(float(b))
                    for a, b in zip(source[start:start + len(weights)], weights))
        try:
            results.append(float(value))
        except OverflowError:
            results.append(math.inf if value > 0 else -math.inf)
    return np.asarray(results)


def _assert_bits(actual, expected):
    np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))


_SUBNORMAL = math.ulp(0.0)
_MAXIMUM = sys.float_info.max
_OVERFLOW_HALF = math.ldexp(1.0, 970)


@pytest.mark.parametrize("source,weights", [
    ([1., 2**-53], [1., 1.]),
    ([1. + 2**-52, 2**-53], [1., 1.]),
    ([-1., -(2**-53)], [1., 1.]),
    ([_SUBNORMAL], [.5]),
    ([-_SUBNORMAL], [.5]),
    ([3 * _SUBNORMAL], [.5]),
    ([-3 * _SUBNORMAL], [.5]),
    ([_MAXIMUM, _OVERFLOW_HALF], [1., 1.]),
    ([_MAXIMUM, np.nextafter(_OVERFLOW_HALF, 0.)], [1., 1.]),
    ([-_MAXIMUM, -_OVERFLOW_HALF], [1., 1.]),
    ([-_MAXIMUM, -np.nextafter(_OVERFLOW_HALF, 0.)], [1., 1.]),
    ([_MAXIMUM, _MAXIMUM, _SUBNORMAL], [_MAXIMUM, -_MAXIMUM, _SUBNORMAL]),
    ([_MAXIMUM, _MAXIMUM, -_SUBNORMAL], [_MAXIMUM, -_MAXIMUM, _SUBNORMAL]),
    ([-0., 0., -0.], [-1., 1.]),
    ([1., -1., 0.], [-0., 0.]),
])
def test_exact_convolution_retains_binary64_rounding_and_signed_underflow(source, weights):
    source, weights = np.asarray(source), np.asarray(weights)
    _assert_bits(numeric.exact_convolution(source, weights), _reference(source, weights))


@pytest.mark.parametrize("exponent", [109, 110])
def test_two_coefficients_avoid_band_planning_at_neighboring_widths(exponent, monkeypatch):
    source = np.asarray([1., -(2.**exponent), -0., 3., 2.**exponent])
    weights = np.asarray([1., 1.])
    def unexpected(*args):
        pytest.fail("Fixed two-coefficient expressions must not plan bands or encode polynomials")

    monkeypatch.setattr(numeric, "_exponent_bands", unexpected)
    monkeypatch.setattr(numeric, "_packed_polynomial", unexpected)
    _assert_bits(numeric.exact_convolution(source, weights), _reference(source, weights))


@pytest.mark.parametrize("period", [3, 7, 32])
def test_short_windows_require_work_margin_before_planning_exponent_bands(period, monkeypatch):
    source = np.resize([1., -(2.**110), -0., 3., 2.**110], 71)
    weights = np.ones(period)

    def unexpected(*args):
        pytest.fail("A one-byte slot saving must not trigger short-window band planning")

    monkeypatch.setattr(numeric, "_exponent_bands", unexpected)
    _assert_bits(numeric.exact_convolution(source, weights), _reference(source, weights))


@pytest.mark.parametrize("kernel_bands,expected_products", [(3, 1), (4, 1)])
def test_sparse_bands_do_not_underprice_repeated_coefficient_passes(
        kernel_bands, expected_products, monkeypatch):
    source = np.resize([math.ldexp((-1 if i % 2 else 1) * 1.5, -1000 + 53 * i)
                        for i in range(39)], 129)
    weights = np.resize([math.ldexp((-1 if i % 2 else 1) * 1.5, -1000 + 53 * i)
                         for i in range(kernel_bands)], 32)
    products = []
    original = numeric._packed_polynomial

    def record(coefficients, offset, width):
        products.append(width)
        return original(coefficients, offset, width)

    monkeypatch.setattr(numeric, "_packed_polynomial", record)
    _assert_bits(numeric.exact_convolution(source, weights), _reference(source, weights))
    assert len(products) == 2 * expected_products


@pytest.mark.parametrize("period", [1, 2, 5, 17])
@pytest.mark.parametrize("step", [52, 53, 54])
@pytest.mark.parametrize("wide_weights", [False, True])
def test_band_boundaries_and_window_geometry_have_fraction_exact_prefixes(period, step, wide_weights):
    source = np.resize([math.ldexp((-1 if i % 2 else 1) * (1. + 2**-52), -1000 + step * i)
                        for i in range(38)], 71)
    weights = (np.resize([math.ldexp((-1 if i % 2 else 1) * 1.5, -1000 + step * i)
                          for i in range(38)], period) if wide_weights
               else np.linspace(-.5, 1., period))
    expected = _reference(source, weights)
    _assert_bits(numeric.exact_convolution(source, weights), expected)
    for end in (period, min(period + 1, len(source)), 37, len(source) - 1):
        _assert_bits(numeric.exact_convolution(source[:end], weights), expected[:end-period+1])
