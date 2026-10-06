"""Independent Fraction references cover exact convolution's exponent branches."""
from fractions import Fraction
import math
import sys

import numpy as np
import pytest

from pyne_runtime._weighted_numeric import exact_convolution
from pyne_runtime.ta import TaModule


def _rounded(value):
    try:
        return float(value)
    except OverflowError:
        return math.copysign(math.inf, 1 if value > 0 else -1)


def _reference(source, weights):
    return np.asarray([_rounded(sum(Fraction(float(value)) * Fraction(float(weight))
        for value, weight in zip(source[start:start + len(weights)], weights)))
        for start in range(len(source) - len(weights) + 1)])


_SUBNORMAL = np.nextafter(0.0, 1.0)
_EXTREME = sys.float_info.max
_BOUNDARIES = [math.ldexp(1.0, exponent) for exponent in
               (-1074, -1023, -1022, -971, -970, -513, -512, -65, -64, -1,
                0, 1, 63, 64, 511, 512, 969, 970, 1022, 1023)]
_SOURCES = [
    np.zeros(43),
    np.resize(np.asarray([_EXTREME, -_EXTREME, _SUBNORMAL, -_SUBNORMAL, 1., -1.]), 43),
    np.resize(np.asarray(_BOUNDARIES), 43),
    np.resize(np.asarray([value * (-1 if at % 2 else 1)
                         for at, value in enumerate(_BOUNDARIES)]), 43),
    np.resize(np.asarray([1., 1. + 2**-52, -1., -1. - 2**-52, 0., _SUBNORMAL]), 43),
]
_KERNELS = [
    np.zeros(7),
    np.asarray([.1, .2, .3, .4, .5, .6, .7]),
    np.asarray([-1., .125, -.5, 2., -4., .25, 8.]),
    np.asarray([_SUBNORMAL, -_SUBNORMAL, 1., -1., 2**-512, -(2**-512), .5]),
    np.asarray([_EXTREME, -_EXTREME, _SUBNORMAL, -_SUBNORMAL, 1., -1., 0.]),
]


@pytest.mark.parametrize("source", _SOURCES, ids=["zero", "extremes", "bands", "signed-bands", "ulp"])
@pytest.mark.parametrize("weights", _KERNELS, ids=["zero", "ordinary", "signed", "wide", "extreme"])
def test_exact_convolution_matches_fraction_at_every_valid_prefix(source, weights):
    expected = _reference(source, weights)
    np.testing.assert_array_equal(exact_convolution(source, weights), expected)
    for end in range(len(weights), len(source) + 1):
        np.testing.assert_array_equal(exact_convolution(source[:end], weights),
                                      expected[:end - len(weights) + 1])


@pytest.mark.parametrize("period", [1, 2, 7, 17])
@pytest.mark.parametrize("offset,sigma", [(.85, 6.), (0., 6.), (1., 6.),
                                        (.5, -6.), (.5, 100.), (20., 100.)])
def test_alma_exact_gaussian_values_and_prefixes_across_exponent_ranges(period, offset, sigma):
    source = np.resize(np.asarray([1., _EXTREME, -_EXTREME, _SUBNORMAL,
                                   -_SUBNORMAL, 2**-512, -(2**-512), 7.]), 43)
    with np.errstate(all="ignore"):
        positions = np.arange(period, dtype=float)
        weights = np.exp(-((positions - offset * (period - 1))**2) / (2 * (period / sigma)**2))
        weights /= weights.sum()
        expected = np.full(len(source), np.nan)
        if np.isfinite(weights).all():
            expected[period - 1:] = _reference(source, weights)
        actual = TaModule().alma(source, period, offset, sigma)
        np.testing.assert_array_equal(actual, expected)
        for end in range(1, len(source) + 1):
            np.testing.assert_array_equal(TaModule().alma(source[:end], period, offset, sigma),
                                          actual[:end])


@pytest.mark.parametrize("suffix", [[_EXTREME, -_EXTREME], [_SUBNORMAL, -_SUBNORMAL],
                                    _BOUNDARIES, [-value for value in _BOUNDARIES]])
def test_future_exponent_band_selection_cannot_change_an_ordinary_prefix(suffix):
    source = np.arange(1., 40.)
    weights = np.asarray([.125, .25, .5, -.25, .125, .25, .5])
    before = exact_convolution(source, weights)
    after = exact_convolution(np.r_[source, suffix], weights)
    np.testing.assert_array_equal(after[:len(before)], before)


def test_many_exponent_bands_match_fraction_when_pair_expansion_is_unprofitable():
    powers = [math.ldexp(1., exponent) for exponent in range(-1074, 1024, 53)]
    weights = np.asarray([value * (-1 if index % 2 else 1)
                          for index, value in enumerate(powers)])
    source = np.resize(np.asarray(powers[::-1]), 83)
    expected = _reference(source, weights)
    np.testing.assert_array_equal(exact_convolution(source, weights), expected)
    for end in (len(weights), len(weights) + 1, 63, 82):
        np.testing.assert_array_equal(exact_convolution(source[:end], weights),
                                      expected[:end - len(weights) + 1])
