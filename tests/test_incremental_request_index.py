"""Indexed cache preserves interval coverage, ordering, eviction and isolation."""

import copy
import math
import random

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.request import IncrementalRequestModule, _RangeCachingProvider
from pyne_runtime.incremental.session import _preview_copy_memo


class Provider:
    def __init__(self):
        self.calls = []

    def get_ohlcv(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        return [{"time": t, "close": t + (100 if symbol == "B" else 0), "nested": [t]}
                for t in range(20, -21, -2) if start <= t <= end]


def test_index_matches_authoritative_rows_for_disjoint_overlapping_and_backwards_ranges():
    provider = Provider()
    cache = _RangeCachingProvider(provider, max_cached_bars=1000, max_covered_ranges=100)
    rng = random.Random(731)
    ranges = [(10, 20), (0, 15), (-20, -10), (30, 40), (30, 40), (3, 2)]
    ranges += [(rng.randrange(-30, 30), rng.randrange(-30, 30)) for _ in range(100)]
    for symbol in ("A", "B"):
        for start, end in ranges:
            actual = cache.get_ohlcv(symbol, "10S", start, end)
            expected = sorted(Provider().get_ohlcv(symbol, "10S", start, end), key=lambda r: r["time"])
            assert actual == expected
            if actual:
                actual[0]["nested"].append("caller mutation")
                assert cache.get_ohlcv(symbol, "10S", start, end) == expected


def test_cache_coverage_fetches_only_missing_coordinates_including_empty_ranges():
    provider = Provider()
    cache = _RangeCachingProvider(provider, max_cached_bars=1000, max_covered_ranges=100)
    for start, end in [(10, 20), (14, 16), (0, 15), (30, 40), (30, 40)]:
        cache.get_ohlcv("A", "10S", start, end)
    assert provider.calls == [("A", "10S", 10, 20), ("A", "10S", 0, 9), ("A", "10S", 30, 40)]


def test_index_is_discarded_with_evicted_rows_and_rebuilt_on_refetch():
    provider = Provider()
    cache = _RangeCachingProvider(provider, max_cached_bars=2, max_covered_ranges=2)
    expected = cache.get_ohlcv("A", "10S", 0, 10)
    assert cache.stats()["bars"] == 0
    assert cache.get_ohlcv("A", "10S", 0, 10) == expected
    assert len(provider.calls) == 2
    assert cache.get_ohlcv("A", "10S", 4, 4) == [{"time": 4, "close": 4, "nested": [4]}]


def test_duplicate_provider_timestamps_remain_last_value_wins():
    class Duplicates:
        def get_ohlcv(self, *args):
            return [{"time": 2, "close": 1}, {"time": 0, "close": 0}, {"time": 2, "close": 3}]

    cache = _RangeCachingProvider(Duplicates(), max_cached_bars=20, max_covered_ranges=20)
    expected = [{"time": 0, "close": 0}, {"time": 2, "close": 3}]
    assert cache.get_ohlcv("A", "10S", 0, 2) == expected
    assert cache.get_ohlcv("A", "10S", 0, 2) == expected


def test_opaque_request_graph_is_not_walked_but_user_aliases_still_isolate():
    request = IncrementalRequestModule(lambda: None, settings=pn.PyneSettings(), provider=None)
    # Traversal into this opaque facade has no copy effect: __deepcopy__ returns self.
    request.host_only_module = math
    user = {"nested": []}
    request.user_alias = user
    values = {"request": request, "user": user}
    memo = _preview_copy_memo(values)
    assert id(math) not in memo
    cloned = copy.deepcopy(values, memo)
    assert cloned["request"] is request
    cloned["user"]["nested"].append(1)
    assert user["nested"] == []


def test_user_request_subclasses_do_not_acquire_the_opaque_shortcut():
    from pyne_runtime.incremental.request import IncrementalRequestModule

    class UserFacade(IncrementalRequestModule):
        pass

    request = UserFacade(lambda: None, settings=pn.PyneSettings(), provider=None)
    request.module = math
    assert id(math) in _preview_copy_memo({"request": request})


def test_malformed_fetch_does_not_leave_rows_missing_from_the_index():
    class OnceInvalid:
        invalid = True

        def get_ohlcv(self, *args):
            if self.invalid:
                self.invalid = False
                return [{"time": 0, "close": 10}, {"time": "invalid", "close": 20}]
            return [{"time": 0, "close": 11}]

    cache = _RangeCachingProvider(OnceInvalid(), max_cached_bars=20, max_covered_ranges=20)
    with pytest.raises(ValueError):
        cache.get_ohlcv("A", "10S", 0, 2)
    expected = [{"time": 0, "close": 11}]
    assert cache.get_ohlcv("A", "10S", 0, 2) == expected
    assert cache.get_ohlcv("A", "10S", 0, 2) == expected


def test_small_append_and_lookup_do_not_enumerate_old_cache_rows():
    class LookupOnly(dict):
        def keys(self):
            raise AssertionError("Full historical key enumeration")

        def items(self):
            raise AssertionError("Full historical row enumeration")

        def __iter__(self):
            raise AssertionError("Full historical iteration")

    cache = _RangeCachingProvider(Provider(), max_cached_bars=1000, max_covered_ranges=100)
    cache.get_ohlcv("A", "10S", 0, 10)
    cache._bars[("A", "10S")] = LookupOnly(cache._bars[("A", "10S")])
    assert [r["time"] for r in cache.get_ohlcv("A", "10S", 8, 12)] == [8, 10, 12]
