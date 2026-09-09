from __future__ import annotations

import pytest

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 120},
        {"time": 3, "open": 3, "high": 4, "low": 2, "close": 3.5, "volume": 140},
    ]


def test_default_runtime_metadata_is_available_to_scripts() -> None:
    result = pn.run(
        """
indicator("Metadata", overlay=False)
plot(syminfo.mintick, "Min Tick")
plot(timeframe.multiplier, "Timeframe Multiplier")
plot(1 if timeframe.isintraday else 0, "Intraday")
plot(session.ismarket, "Market")
plot(session.isfirstbar, "First Session Bar")
plot(session.islastbar, "Last Session Bar")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Min Tick") == [1.0, 1.0, 1.0]
    assert result.values("Timeframe Multiplier") == [1.0, 1.0, 1.0]
    assert result.values("Intraday") == [1.0, 1.0, 1.0]
    assert result.values("Market") == [1.0, 1.0, 1.0]
    assert result.values("First Session Bar") == [1.0, 0.0, 0.0]
    assert result.values("Last Session Bar") == [0.0, 0.0, 1.0]


def test_runtime_metadata_can_be_supplied_through_run() -> None:
    result = pn.run(
        """
indicator("Metadata", overlay=False)
plot(syminfo.mintick, "Min Tick")
plot(1 if syminfo.ticker == "AAPL" else 0, "Ticker Match")
plot(1 if syminfo.timezone == "America/New_York" else 0, "Timezone Match")
plot(1 if syminfo.volumetype == "base" else 0, "Volume Type Match")
plot(timeframe.multiplier, "Timeframe Multiplier")
plot(1 if timeframe.isintraday else 0, "Intraday")
plot(1 if timeframe.isdaily else 0, "Daily")
plot(session.ismarket, "Market")
""",
        _bars(),
        executor_mode="inline",
        syminfo={
            "tickerid": "NASDAQ:AAPL",
            "mintick": 0.01,
            "currency": "USD",
            "timezone": "America/New_York",
            "volume_type": "base",
        },
        timeframe="1h",
        session={"ismarket": False},
    )

    assert result.ok
    assert result.values("Min Tick") == [0.01, 0.01, 0.01]
    assert result.values("Ticker Match") == [1.0, 1.0, 1.0]
    assert result.values("Timezone Match") == [1.0, 1.0, 1.0]
    assert result.values("Volume Type Match") == [1.0, 1.0, 1.0]
    assert result.values("Timeframe Multiplier") == [60.0, 60.0, 60.0]
    assert result.values("Intraday") == [1.0, 1.0, 1.0]
    assert result.values("Daily") == [0.0, 0.0, 0.0]
    assert result.values("Market") == [0.0, 0.0, 0.0]


def test_runtime_rejects_missing_ohlcv_fields() -> None:
    result = pn.PyneRuntime().execute(
        'plot(close, "Close")',
        [{"time": 1, "open": 1, "high": 2, "low": 1, "volume": 100}],
    )

    assert not result.ok
    assert result.code == "PYNE_INVALID_OHLCV"
    assert "missing required fields" in str(result.error)


def test_runtime_classifies_non_increasing_time_as_invalid_ohlcv() -> None:
    result = pn.PyneRuntime().execute(
        'plot(close, "Close")',
        [
            {"time": 2, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
            {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        ],
    )

    assert not result.ok
    assert result.code == "PYNE_INVALID_OHLCV"
    assert "strictly increasing" in str(result.error)


def test_run_classifies_missing_volume_as_invalid_ohlcv() -> None:
    result = pn.run(
        'plot(close, "Close")',
        [{"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5}],
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_INVALID_OHLCV"
    assert "volume" in str(result.error)


@pytest.mark.parametrize(
    "data",
    [
        [{"time": 1, "open": 1, "high": 2, "low": 1, "close": "bad", "volume": 1}],
        [None],
        None,
        [{"time": 1, "open": 1, "high": 2, "low": 1, "close": float("nan"), "volume": 1}],
    ],
)
def test_run_classifies_all_malformed_rows_as_invalid_ohlcv(data: object) -> None:
    result = pn.run('plot(close, "Close")', data, executor_mode="inline")

    assert not result.ok
    assert result.code == "PYNE_INVALID_OHLCV"


def test_time_close_last_bar_uses_timeframe_duration() -> None:
    result = pn.run(
        """
plot(time_close, "Close Time")
""",
        _bars()[:2],
        timeframe="1h",
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Close Time") == [2.0, 3602.0]


def test_time_close_last_bar_supports_minute_suffix_timeframe() -> None:
    result = pn.run(
        """
plot(time_close, "Close Time")
""",
        _bars()[:2],
        timeframe="15m",
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Close Time") == [2.0, 902.0]


def test_derived_series_names_are_stable() -> None:
    result = pn.run(
        """
plot(hl2, hl2.name)
plot(hlc3, hlc3.name)
plot(ohlc4, ohlc4.name)
plot(hlcc4, hlcc4.name)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert [line["name"] for line in result.lines] == ["hl2", "hlc3", "ohlc4", "hlcc4"]


def test_session_namespace_uses_bar_level_host_flags() -> None:
    bars = [
        {**_bars()[0], "session_ismarket": True, "session_isfirstbar": True},
        {**_bars()[1], "session_ismarket": False},
        {**_bars()[2], "session": {"ismarket": True, "islastbar": True}},
    ]

    result = pn.run(
        """
indicator("Session", overlay=False)
plot(session.ismarket, "Market")
plot(session.isfirstbar, "First")
plot(session.islastbar, "Last")
plot(when(session.ismarket, close, 0), "Market Close")
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Market") == [1.0, 0.0, 1.0]
    assert result.values("First") == [1.0, 0.0, 0.0]
    assert result.values("Last") == [0.0, 0.0, 1.0]
    assert result.values("Market Close") == [1.5, 0.0, 3.5]


def test_session_namespace_preserves_explicit_false_first_last_flags() -> None:
    bars = [
        {
            **bar,
            "session_isfirstbar": False,
            "session_islastbar": False,
        }
        for bar in _bars()
    ]

    result = pn.run(
        """
indicator("Session Explicit False", overlay=False)
plot(session.isfirstbar, "First")
plot(session.islastbar, "Last")
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("First") == [0.0, 0.0, 0.0]
    assert result.values("Last") == [0.0, 0.0, 0.0]


def test_timeframe_parses_daily_weekly_and_monthly_periods() -> None:
    assert pn.TimeframeInfo.from_value("1D").isdaily
    assert pn.TimeframeInfo.from_value("2W").isweekly
    assert pn.TimeframeInfo.from_value("3M").ismonthly
    assert pn.TimeframeInfo.from_value("5").multiplier == 5


def test_timeframe_rejects_malformed_and_conflicting_inputs() -> None:
    with pytest.raises(ValueError, match="invalid timeframe"):
        pn.TimeframeInfo.from_value("1h30")
    with pytest.raises(ValueError, match="invalid timeframe"):
        pn.TimeframeInfo.from_value("15min")
    with pytest.raises(ValueError, match="conflicts with multiplier"):
        pn.TimeframeInfo.from_value({"period": "1h", "multiplier": 1})

    hour = pn.TimeframeInfo.from_value("1h")
    direct_hour = pn.TimeframeInfo(period="1h")
    consistent = pn.TimeframeInfo.from_value({"period": "1h", "multiplier": 60})
    assert hour.in_seconds() == 3600
    assert direct_hour.in_seconds() == 3600
    assert consistent.in_seconds() == 3600
    assert hour.multiplier == direct_hour.multiplier == consistent.multiplier == 60

    with pytest.raises(ValueError, match="conflicts with multiplier"):
        pn.TimeframeInfo(period="1h", multiplier=1)
    with pytest.raises(ValueError, match="must be an integer"):
        pn.TimeframeInfo.from_value({"multiplier": 1.5})
    with pytest.raises(ValueError, match="must be an integer"):
        pn.TimeframeInfo.from_value({"multiplier": True})
    with pytest.raises(ValueError, match=">= 1"):
        pn.TimeframeInfo.from_value("0")


def test_time_close_matches_canonical_timeframe_seconds() -> None:
    hour = pn.TimeframeInfo.from_value("1h")
    result = pn.run(
        """
plot(time_close, "Close Time")
plot(timeframe.in_seconds(), "Seconds")
""",
        _bars()[:2],
        timeframe="1h",
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Seconds") == [hour.in_seconds(), hour.in_seconds()]
    assert result.values("Close Time")[-1] == _bars()[1]["time"] + hour.in_seconds()


def test_timeframe_exposes_pine_like_type_flags_and_seconds_conversion() -> None:
    result = pn.run(
        """
plot(timeframe.in_seconds(), "Chart Seconds")
plot(timeframe.in_seconds("2W"), "Two Weeks")
plot(1 if timeframe.isseconds else 0, "Seconds")
plot(1 if timeframe.isminutes else 0, "Minutes")
plot(1 if timeframe.isdwm else 0, "DWM")
""",
        _bars(),
        executor_mode="inline",
        timeframe="15S",
    )

    assert result.ok, result.error
    assert result.values("Chart Seconds") == [15.0, 15.0, 15.0]
    assert result.values("Two Weeks") == [1_209_600.0, 1_209_600.0, 1_209_600.0]
    assert result.values("Seconds") == [1.0, 1.0, 1.0]
    assert result.values("Minutes") == [0.0, 0.0, 0.0]
    assert result.values("DWM") == [0.0, 0.0, 0.0]

    minute = pn.TimeframeInfo.from_value("30")
    assert minute.isminutes
    assert minute.in_seconds() == 1_800
    daily = pn.TimeframeInfo.from_value("1D")
    assert daily.isdwm
    assert daily.in_seconds() == 86_400


def test_timeframe_change_and_from_seconds_follow_valid_period_boundaries() -> None:
    bars = [
        {
            "time": 1704153540,  # 2024-01-01 23:59 UTC
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        },
        {
            "time": 1704153600,  # 2024-01-02 00:00 UTC
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        },
        {
            "time": 1704153660,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        },
    ]
    result = pn.run(
        """
plot(timeframe.change("1D"), "New Day")
plot(timeframe.change("2"), "Two Minutes")
plot(1 if timeframe.from_seconds(604800) == "1W" else 0, "Exact Week")
plot(1 if timeframe.from_seconds(604799) == "7D" else 0, "Next Period")
""",
        bars,
        executor_mode="inline",
        syminfo={"timezone": "UTC"},
        timeframe="1",
    )

    assert result.ok, result.error
    assert result.values("New Day") == [1.0, 1.0, 0.0]
    assert result.values("Two Minutes") == [1.0, 1.0, 0.0]
    assert result.values("Exact Week") == [1.0, 1.0, 1.0]
    assert result.values("Next Period") == [1.0, 1.0, 1.0]


def test_strategy_slippage_uses_syminfo_mintick_when_not_overridden() -> None:
    result = pn.run(
        """
strategy("Metadata Strategy", overlay=True, slippage=2)
strategy.order("Buy", strategy.long, qty=1, when=bar_index == 0, price=close)
""",
        _bars(),
        executor_mode="inline",
        syminfo={"mintick": 0.25},
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Buy",
            "type": "order",
            "side": "long",
            "qty": 1.0,
            "price": 2.0,
            "position_after": 1.0,
            "comment": "",
        },
    ]
