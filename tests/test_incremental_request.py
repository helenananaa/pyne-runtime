from __future__ import annotations

from typing import Any

import pyne_runtime as pn
import pytest


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
        {"time": 30, "open": 3, "high": 5, "low": 2.5, "close": 4, "volume": 30},
        {"time": 40, "open": 4, "high": 6, "low": 3.5, "close": 5, "volume": 40},
    ]


class _Provider:
    capabilities = {
        "request.security": True,
        "request.security_lower_tf": True,
    }

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        assert symbol == "TEST:BTCUSD"
        self.calls.append((timeframe, start, end))
        if timeframe == "20S":
            rows = [
                {"time": 0, "open": 90, "high": 100, "low": 80, "close": 95, "volume": 1},
                {"time": 20, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 2},
                {"time": 40, "open": 105, "high": 120, "low": 100, "close": 115, "volume": 3},
            ]
        elif timeframe == "5S":
            rows = [
                {
                    "time": timestamp,
                    "open": timestamp,
                    "high": timestamp + 1,
                    "low": timestamp - 1,
                    "close": timestamp + 0.5,
                    "volume": 1,
                }
                for timestamp in range(0, 55, 5)
            ]
        else:
            rows = []
        return [row for row in rows if start <= int(row["time"]) <= end]

    def get_request_metadata(self, symbol: str, timeframe: str) -> dict[str, Any]:
        return {"syminfo": {"tickerid": symbol}, "timeframe": timeframe}


def _value_view(result: pn.PyneResult) -> dict[str, list[float]]:
    return {
        title: result.values(title)
        for title in ("HTF", "LTF Count", "LTF Last")
    }


def test_incremental_request_security_and_lower_tf_match_batch() -> None:
    provider = _Provider()
    report = pn.run_incremental_parity(
        batch_script="""
indicator("Batch Requests", overlay=False)
htf = request.security("TEST:BTCUSD", "20S", "close")
ltf = request.security_lower_tf("TEST:BTCUSD", "5S", "close")
plot(htf, "HTF")
plot(ltf.size(), "LTF Count")
plot(ltf.last(), "LTF Last")
""",
        incremental_script="""
indicator("Incremental Requests", mode="incremental", overlay=False)
def on_bar(ctx, bar):
    htf = ctx.request.security("TEST:BTCUSD", "20S", "close")
    ltf = ctx.request.security_lower_tf("TEST:BTCUSD", "5S", "close")
    ctx.plot("HTF", htf)
    ctx.plot("LTF Count", ltf.size())
    ctx.plot("LTF Last", ltf.last())
""",
        bars=_bars(),
        data_provider=provider,
        syminfo={"tickerid": "TEST:BTCUSD"},
        timeframe="10S",
        normalizer=_value_view,
    )

    report.assert_ok()
    assert report.incremental_result.meta["requestDiagnostics"]
    assert {
        item["api"] for item in report.incremental_result.meta["requestDiagnostics"]
    } == {"request.security", "request.security_lower_tf"}


def test_incremental_request_range_cache_never_refetches_covered_coordinates() -> None:
    provider = _Provider()
    script = """
indicator("Cached Requests", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("HTF", request.security("TEST:BTCUSD", "20S", "close"))
"""
    result = pn.run(
        script,
        _bars(),
        data_provider=provider,
        syminfo={"tickerid": "TEST:BTCUSD"},
        timeframe="10S",
        executor_mode="inline",
    )

    assert result.ok, result.error
    intervals = [(start, end) for timeframe, start, end in provider.calls if timeframe == "20S"]
    for index, (left, right) in enumerate(intervals):
        assert all(right < other_left or left > other_right for other_left, other_right in intervals[:index])


def test_incremental_request_preview_diagnostics_are_isolated_and_cache_is_reused() -> None:
    provider = _Provider()
    session = pn.PyneIncrementalSession(
        script="""
indicator("Preview Request", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("HTF", request.security("TEST:BTCUSD", "20S", "close"))
""",
        settings=pn.PyneSettings(
            executor_mode="inline",
            data_provider=provider,
            syminfo={"tickerid": "TEST:BTCUSD"},
            timeframe="10S",
        ),
    )
    session.seed(_bars()[:2])
    committed_before = session.snapshot_result()

    preview = session.on_bar_updated(_bars()[2])
    calls_after_preview = len(provider.calls)

    assert preview.meta["requestDiagnostics"]
    assert session.snapshot_result() == committed_before
    session.on_bar_closed(_bars()[2])
    assert len(provider.calls) == calls_after_preview


def test_incremental_request_range_cache_is_bounded_by_runtime_limits() -> None:
    provider = _Provider()
    session = pn.PyneIncrementalSession(
        script="""
indicator("Bounded Request", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("HTF", request.security("TEST:BTCUSD", "20S", "close"))
""",
        settings=pn.PyneSettings(
            executor_mode="inline",
            data_provider=provider,
            syminfo={"tickerid": "TEST:BTCUSD"},
            timeframe="10S",
            max_output_points=100,
            request_cache_max_bars=2,
            cache_max_items=1,
        ),
    )
    result = session.seed([_bars()[-1]])

    assert result.ok
    stats = session._globals["request"].cache_stats()
    assert stats["bars"] <= 2
    assert stats["coveredRanges"] <= 1


def test_incremental_request_preserves_typed_missing_provider_error() -> None:
    script = """
indicator("Missing Provider", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Requested", request.security("TEST:BTCUSD", "20S", "close"))
"""
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline", timeframe="10S"),
    )

    with pytest.raises(pn.PyneRequestError) as error:
        session.seed(_bars()[:1])
    assert error.value.category == "missingProvider"


class _InvalidProvider:
    capabilities = {"request.security": True}

    def get_ohlcv(self, symbol: str, timeframe: str, start: int, end: int) -> Any:
        return "not-bars"


def test_incremental_request_preserves_invalid_return_category() -> None:
    result = pn.run(
        """
indicator("Invalid Provider", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Requested", request.security("TEST:BTCUSD", "20S", "close"))
""",
        _bars()[:1],
        data_provider=_InvalidProvider(),
        timeframe="10S",
        executor_mode="inline",
    )

    assert not result.ok
    assert result.error_detail["requestProviderCategory"] == "invalidReturnType"
