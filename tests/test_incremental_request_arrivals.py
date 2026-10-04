"""Finalized historical caching must not conceal new arrivals or live changes."""

import pyne_runtime as pn
import pytest


def bar(time, value):
    return dict(time=time, open=value, high=value, low=value, close=value, volume=1)


class ArrivingProvider:
    capabilities = {"request.security": True, "request.security_lower_tf": True}

    def __init__(self):
        self.available = 0
        self.active_value = None
        self.calls = []

    def get_ohlcv(self, symbol, timeframe, start, end):
        self.calls.append((start, end))
        step = {"10S": 10, "20S": 20, "5S": 5}[timeframe]
        return [bar(t, self.active_value if t == self.available and self.active_value is not None else 100 + t)
                for t in range(0, self.available + 1, step) if start <= t <= end]

    def get_request_metadata(self, symbol, timeframe):
        return {"timeframe": timeframe}


SCRIPT = '''indicator("Arrivals", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Requested", ctx.request.security("TEST", "10S", "close"))
'''


def session(provider, script=SCRIPT):
    return pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(
        executor_mode="inline", timeframe="10S", data_provider=provider))


def last_value(result):
    return result.lines[0]["data"][-1]["value"]


def test_normal_appended_provider_bars_are_visible_without_history_revisions():
    provider = ArrivingProvider()
    runtime = session(provider)
    assert last_value(runtime.seed([bar(0, 1)])) == 100
    for time in (10, 20, 30):
        provider.available = time
        assert last_value(runtime.on_bar_closed(bar(time, 1))) == 100 + time
    assert provider.calls == [(0, 10), (0, 20), (0, 30), (0, 40)]


def test_preview_change_and_final_requested_value_refresh_without_committed_mutation():
    provider = ArrivingProvider()
    runtime = session(provider)
    runtime.seed([bar(0, 1)])
    committed = runtime.snapshot_result()
    provider.available, provider.active_value = 10, 111
    assert last_value(runtime.on_bar_updated(bar(10, 1))) == 111
    provider.active_value = 112
    assert last_value(runtime.on_bar_updated(bar(10, 2))) == 112
    assert runtime.snapshot_result() == committed
    provider.active_value = 113
    assert last_value(runtime.on_bar_closed(bar(10, 3))) == 113
    assert runtime.snapshot_result().lines[0]["data"] == [
        {"time": 0, "value": 100}, {"time": 10, "value": 113}]


def test_requested_higher_timeframe_bar_refreshes_until_its_close():
    provider = ArrivingProvider()
    script = SCRIPT.replace('"10S", "close"', '"20S", "close"')
    runtime = session(provider, script)
    runtime.seed([bar(0, 1)])
    provider.active_value = 125
    assert last_value(runtime.on_bar_closed(bar(10, 1))) == 125


def test_arrival_cache_rebuilds_from_same_version_portable_state():
    provider = ArrivingProvider()
    original = session(provider)
    original.seed([bar(0, 1)])
    provider.available = 10
    original.on_bar_closed(bar(10, 1))
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(), script=SCRIPT, settings=pn.PyneSettings(
            executor_mode="inline", timeframe="10S", data_provider=provider))
    for time in (20, 30):
        provider.available = time
        actual = restored.on_bar_closed(bar(time, 1))
        expected = original.on_bar_closed(bar(time, 1))
        assert last_value(actual) == pytest.approx(100 + time)
        assert actual == expected


def test_lower_timeframe_arrivals_refresh_inside_the_same_preview_bar():
    provider = ArrivingProvider()
    script = '''indicator("Lower arrivals", mode="incremental")
def on_bar(ctx, bar):
    lower = ctx.request.security_lower_tf("TEST", "5S", "close")
    ctx.plot("Last lower", lower.last())
'''
    runtime = session(provider, script)
    assert last_value(runtime.on_bar_updated(bar(0, 1))) == 100
    provider.available = 5
    assert last_value(runtime.on_bar_updated(bar(0, 2))) == 105
    provider.available = 10
    assert last_value(runtime.on_bar_closed(bar(0, 3))) == 105


def test_explicit_requested_close_keeps_nonuniform_bar_refreshable():
    class LongRequestedBar(ArrivingProvider):
        def get_ohlcv(self, symbol, timeframe, start, end):
            self.calls.append((start, end))
            return [dict(bar(0, self.active_value), time_close=100)] if start <= 0 <= end else []

    provider = LongRequestedBar()
    provider.active_value = 100
    runtime = session(provider)
    runtime.seed([bar(0, 1)])
    assert last_value(runtime.on_bar_closed(bar(30, 1))) == 100
    provider.active_value = 110
    assert last_value(runtime.on_bar_closed(bar(40, 1))) == 110


def test_absent_historical_coordinate_is_not_a_finality_watermark():
    from pyne_runtime.incremental.request import _RangeCachingProvider

    class DelayedProvider:
        def __init__(self):
            self.rows = [bar(60, 160)]
            self.calls = []

        def get_ohlcv(self, symbol, timeframe, start, end):
            self.calls.append((start, end))
            return [row for row in self.rows if start <= row["time"] <= end]

    provider = DelayedProvider()
    cache = _RangeCachingProvider(provider, max_cached_bars=100, max_covered_ranges=100)
    cache.begin_evaluation(120)
    assert cache.get_ohlcv("TEST", "1", 0, 179) == [bar(60, 160)]
    assert cache.stats()["coveredRanges"] == 0
    assert cache.stats()["bars"] == 0
    provider.rows.insert(0, bar(0, 100))
    cache.begin_evaluation(130)
    assert cache.get_ohlcv("TEST", "1", 0, 179) == [bar(0, 100), bar(60, 160)]
    assert len(provider.calls) == 2


def test_sparse_positive_coverage_coalesces_gaps_in_one_provider_call():
    from pyne_runtime.incremental.request import _RangeCachingProvider

    provider = ArrivingProvider()
    provider.available = 200
    cache = _RangeCachingProvider(provider, max_cached_bars=100, max_covered_ranges=100)
    cache.begin_evaluation(200)
    expected = cache.get_ohlcv("TEST", "10S", 0, 210)
    count = len(provider.calls)
    actual = cache.get_ohlcv("TEST", "10S", 0, 210)
    assert actual == expected
    assert len(provider.calls) == count + 1


def test_finalized_history_uses_bar_budget_instead_of_one_range_per_timestamp():
    from pyne_runtime.incremental.request import _RangeCachingProvider

    provider = ArrivingProvider()
    provider.available = 1000
    provider.get_finalized_through = lambda *args: 990
    cache = _RangeCachingProvider(provider, max_cached_bars=1000, max_covered_ranges=32)
    cache.begin_evaluation(1000)
    cache.get_ohlcv("TEST", "10S", 0, 1010)
    assert cache.stats()["bars"] == 100
    assert cache.stats()["series"] == 1
    assert cache.stats()["coveredRanges"] == 1
    calls = len(provider.calls)
    assert cache.get_ohlcv("TEST", "10S", 500, 500) == [bar(500, 600)]
    assert len(provider.calls) == calls
