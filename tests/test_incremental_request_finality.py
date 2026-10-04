"""Only an explicit completeness promise permits live negative caching."""

import copy
from typing import get_type_hints

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.request import _RangeCachingProvider
from pyne_runtime.request import RequestHistoryFinalityProvider


def bar(time, value=1, **extra):
    return dict(time=time, open=value, high=value, low=value, close=value, volume=1, **extra)


class FinalProvider:
    def __init__(self, rows=(), watermark=None):
        self.rows = list(rows)
        self.watermark = watermark
        self.calls = []

    def get_ohlcv(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        return copy.deepcopy([row for row in self.rows if start <= row["time"] <= end])

    def get_finalized_through(self, symbol, timeframe):
        if isinstance(self.watermark, Exception):
            raise self.watermark
        return self.watermark


def cache(provider, *, bars=1000, ranges=32, chart_time=100):
    result = _RangeCachingProvider(provider, max_cached_bars=bars, max_covered_ranges=ranges)
    result.begin_evaluation(chart_time)
    return result


def test_public_protocol_is_optional_and_uses_unix_integer_watermark():
    assert pn.RequestHistoryFinalityProvider is RequestHistoryFinalityProvider
    assert get_type_hints(RequestHistoryFinalityProvider.get_finalized_through) == {
        "symbol": str, "timeframe": str, "return": int | None}
    assert "get_finalized_through" not in pn.DataProvider.__dict__


def test_complete_empty_history_is_cached_but_unfinalized_tail_refreshes():
    provider = FinalProvider(watermark=90)
    wrapped = cache(provider)
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == []
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == []
    assert [call[2:] for call in provider.calls] == [(0, 110), (91, 110)]
    assert wrapped.stats()["coveredRanges"] == 1
    assert wrapped.stats()["finalizedThrough"] == [
        {"symbol": "TEST", "timeframe": "10S", "time": 90}]


def test_sparse_finalized_history_has_only_tail_fetches_and_caller_isolation():
    provider = FinalProvider([bar(0, 1), bar(50, 2), bar(100, 3)], watermark=90)
    wrapped = cache(provider)
    original = wrapped.get_ohlcv("TEST", "10S", 0, 110)
    original[0]["close"] = -1
    provider.rows[-1] = bar(100, 4)
    actual = wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert [row["close"] for row in actual] == [1, 2, 4]
    assert provider.calls[-1][2:] == (91, 110)
    assert wrapped.stats()["bars"] == 2


def test_watermark_advance_covers_only_ranges_fetched_after_the_promise():
    provider = FinalProvider([bar(0), bar(70)], watermark=50)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert wrapped.stats()["bars"] == 1
    provider.rows[-1] = bar(70, 7)
    provider.watermark = 90
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110)[-1]["close"] == 7
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert [call[2:] for call in provider.calls] == [(0, 110), (51, 110), (91, 110)]


@pytest.mark.parametrize("withdrawal", [None, 40, True, False, 12.5, float("nan"),
                                       float("inf"), "90", {}, RuntimeError("offline")])
def test_revoked_regressed_or_invalid_finality_refetches_and_discards_old_evidence(withdrawal):
    provider = FinalProvider([bar(0, 1)], watermark=90)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    provider.watermark = withdrawal
    provider.rows = [bar(0, 2), bar(20, 3)]
    actual = wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert [row["close"] for row in actual] == [2, 3]
    assert provider.calls[-1][2:] == (0, 110)
    assert wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["finalityFallbacks"] == 1
    assert wrapped.stats()["finalizedThrough"] == []


def test_invalid_attribute_and_failing_attribute_accessor_are_safe_fallbacks():
    provider = FinalProvider([bar(0)])
    provider.get_finalized_through = 10
    wrapped = cache(provider)
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == [bar(0)]
    assert wrapped.stats()["finalityFallbacks"] == 1

    class FailingAccessor(FinalProvider):
        @property
        def get_finalized_through(self):
            raise RuntimeError("metadata unavailable")

    wrapped = cache(FailingAccessor([bar(0)]))
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == [bar(0)]
    assert wrapped.stats()["finalityFallbacks"] == 1


def test_signed_unix_watermark_is_not_an_invalid_value():
    provider = FinalProvider(watermark=-10)
    wrapped = cache(provider, chart_time=0)
    wrapped.get_ohlcv("TEST", "10S", -30, 10)
    wrapped.get_ohlcv("TEST", "10S", -30, 10)
    assert [call[2:] for call in provider.calls] == [(-30, 10), (-9, 10)]


def test_newly_enabled_finality_refetches_existing_positive_evidence():
    provider = FinalProvider([bar(20, 1)])
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 20, 20)
    provider.rows = [bar(20, 2)]
    provider.watermark = 20
    assert wrapped.get_ohlcv("TEST", "10S", 20, 20) == [bar(20, 2)]
    assert len(provider.calls) == 2
    assert wrapped.stats()["finalityFallbacks"] == 0


def test_unfinalized_ended_rows_remain_revisable_with_an_explicit_partial_promise():
    provider = FinalProvider([bar(20, 1)], watermark=0)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    provider.rows = [bar(20, 2)]
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == [bar(20, 2)]
    assert wrapped.stats()["bars"] == 0


def test_future_watermark_does_not_freeze_active_requested_bar():
    provider = FinalProvider([bar(100, 1)], watermark=10**12)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    provider.rows = [bar(100, 2)]
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == [bar(100, 2)]
    assert provider.calls[-1][2:] == (91, 110)
    assert wrapped.stats()["bars"] == 0


def test_explicit_close_overrides_nominal_duration_in_both_directions():
    provider = FinalProvider([bar(0, 1, time_close=500)], watermark=10**12)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    provider.rows[0] = bar(0, 2, time_close=500)
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == provider.rows
    assert wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["bars"] == 0

    provider = FinalProvider([bar(90, 1, time_close=95)], watermark=90)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", "20S", 90, 90)
    calls = len(provider.calls)
    assert wrapped.get_ohlcv("TEST", "20S", 90, 90) == provider.rows
    assert len(provider.calls) == calls
    assert wrapped.stats()["bars"] == 1


@pytest.mark.parametrize("timeframe", ["D", "2W", "M", "10T", "UNKNOWN"])
def test_calendar_and_unknown_durations_do_not_cache_absence(timeframe):
    provider = FinalProvider([bar(0, 1, time_close=50)], watermark=90)
    wrapped = cache(provider)
    wrapped.get_ohlcv("TEST", timeframe, 0, 110)
    provider.rows.append(bar(20, 2, time_close=30))
    assert wrapped.get_ohlcv("TEST", timeframe, 0, 110) == provider.rows
    assert wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["bars"] == 2


def test_bar_and_coverage_eviction_also_discards_watermark_state():
    provider = FinalProvider([bar(0), bar(20)], watermark=90)
    wrapped = cache(provider, bars=1)
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == provider.rows
    assert wrapped.stats()["bars"] == wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["finalizedThrough"] == []
    wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert provider.calls[-1][2:] == (0, 110)

    provider = FinalProvider(watermark=90)
    wrapped = cache(provider, ranges=1)
    wrapped.get_ohlcv("TEST", "10S", 0, 10)
    wrapped.get_ohlcv("TEST", "10S", 30, 40)
    assert wrapped.stats()["series"] == wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["finalizedThrough"] == []
    wrapped.get_ohlcv("TEST", "10S", 0, 10)
    assert provider.calls[-1][2:] == (0, 10)


def test_active_only_or_unknown_empty_contexts_do_not_accumulate_unbudgeted_watermarks():
    provider = FinalProvider(watermark=10**12)
    wrapped = cache(provider, bars=1, ranges=1)
    for symbol in range(100):
        assert wrapped.get_ohlcv(str(symbol), "UNKNOWN", 0, 110) == []
        assert wrapped.get_ohlcv(str(symbol), "10S", 100, 110) == []
    assert wrapped.stats()["series"] == wrapped.stats()["bars"] == 0
    assert wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["finalizedThrough"] == []


def test_invalid_data_does_not_publish_a_completeness_promise():
    provider = FinalProvider([bar(0), bar("invalid")], watermark=90)
    wrapped = cache(provider)
    # A provider that returns a bad coordinate regardless of the range.
    provider.get_ohlcv = lambda *args: provider.rows
    with pytest.raises(pn.PyneRequestError) as error:
        wrapped.get_ohlcv("TEST", "10S", 0, 110)
    assert error.value.category == "invalidBarShape"
    assert wrapped.stats()["bars"] == wrapped.stats()["coveredRanges"] == 0
    assert wrapped.stats()["finalizedThrough"] == []
    provider.rows = [bar(0, 2)]
    assert wrapped.get_ohlcv("TEST", "10S", 0, 110) == provider.rows


SCRIPT = '''indicator("Final requests", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Requested", ctx.request.security("TEST", "10S", "close"))
'''


def session(provider):
    return pn.PyneIncrementalSession(script=SCRIPT, settings=pn.PyneSettings(
        executor_mode="inline", timeframe="10S", data_provider=provider))


def last_value(result):
    return result.lines[0]["data"][-1]["value"]


def test_previews_refresh_active_values_and_finality_failures_do_not_poison_session():
    provider = FinalProvider([bar(0, 100)], watermark=10**12)
    runtime = session(provider)
    runtime.seed([bar(0)])
    committed = runtime.snapshot_result()
    provider.rows.append(bar(10, 111))
    assert last_value(runtime.on_bar_updated(bar(10))) == 111
    provider.rows[-1] = bar(10, 112)
    provider.watermark = True
    assert last_value(runtime.on_bar_updated(bar(10))) == 112
    assert runtime.snapshot_result() == committed
    provider.rows[-1] = bar(10, 113)
    provider.watermark = None
    assert last_value(runtime.on_bar_closed(bar(10))) == 113
    assert runtime._globals["request"].cache_stats()["finalityFallbacks"] == 1


@pytest.mark.parametrize("snapshot_mode", ["local", "portable-state", "portable-replay"])
def test_restored_sessions_recheck_provider_finality_instead_of_persisting_negative_cache(snapshot_mode):
    provider = FinalProvider([bar(0, 100), bar(10, 110)], watermark=0)
    original = session(provider)
    original.seed([bar(0), bar(10)])
    settings = pn.PyneSettings(executor_mode="inline", timeframe="10S", data_provider=provider)
    if snapshot_mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT, settings=settings)
    else:
        payload = original.snapshot_portable(mode="state" if snapshot_mode.endswith("state") else "replay")
        restored = pn.PyneIncrementalSession.from_portable_snapshot(payload, script=SCRIPT, settings=settings)
    provider.rows.append(bar(20, 120))
    provider.watermark = None
    assert last_value(restored.on_bar_closed(bar(20))) == 120
    original.on_bar_closed(bar(20))
    assert restored.snapshot_result() == original.snapshot_result()


def test_restore_clock_rewind_does_not_freeze_a_newly_active_row():
    provider = FinalProvider([bar(0, 100), bar(10, 110)], watermark=10**12)
    runtime = session(provider)
    runtime.seed([bar(0)])
    token = runtime.snapshot_state()
    assert last_value(runtime.on_bar_updated(bar(40))) == 110
    provider.rows[-1] = bar(10, 115)
    runtime.restore_state(token)
    assert last_value(runtime.on_bar_updated(bar(10))) == 115


def test_explicit_finality_bounds_provider_work_to_the_tail_instead_of_full_history():
    finalized = FinalProvider([bar(t) for t in range(0, 1010, 10)])
    unpromised = FinalProvider(finalized.rows)
    bounded, conservative = cache(finalized, chart_time=0), cache(unpromised, chart_time=0)
    for time in range(0, 1000, 10):
        finalized.watermark = time - 10
        bounded.begin_evaluation(time)
        conservative.begin_evaluation(time)
        assert bounded.get_ohlcv("TEST", "10S", 0, time + 10) == conservative.get_ohlcv("TEST", "10S", 0, time + 10)
    bounded_work = sum(end - start + 1 for _, _, start, end in finalized.calls)
    conservative_work = sum(end - start + 1 for _, _, start, end in unpromised.calls)
    assert max(end - start + 1 for _, _, start, end in finalized.calls[2:]) <= 30
    assert conservative_work > 10 * bounded_work
