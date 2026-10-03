from __future__ import annotations

from typing import Any

import pyne_runtime as pn
import pytest


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
        {"time": 30, "open": 3, "high": 5, "low": 2.5, "close": 4, "volume": 30},
    ]


def test_plotcandle_emits_candle_collection_with_per_bar_colors() -> None:
    result = pn.run(
        """
indicator("Candles", overlay=True)
body = when(close >= open, color.green, color.red)
plotcandle(open, high, low, close, "Synthetic", color=body, wickcolor=color.blue)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    candle = result.output["candles"][0]
    assert candle["title"] == "Synthetic"
    assert candle["pane"] == "main"
    assert candle["data"][0] == {
        "time": 10,
        "open": 1.0,
        "high": 3.0,
        "low": 0.5,
        "close": 2.0,
        "color": "#26a69a",
        "wickcolor": "#2196f3",
    }


def test_linefill_polyline_and_table_merges_are_serialized() -> None:
    result = pn.run(
        """
first = line.new(0, 1, 2, 3)
second = line.new(0, 2, 2, 4)
cloud = linefill.new(first, second, color=color.new(color.blue, 80))
linefill.set_color(cloud, color.new(color.green, 70))

points = array.new()
array.push(points, chart.point.from_index(0, 1))
array.push(points, chart.point.from_index(1, 3))
array.push(points, chart.point.from_index(2, 2))
polyline.new(points, curved=True, closed=True, fill_color=color.new(color.blue, 85))

summary = table.new(position.top_right, 3, 2)
table.cell(summary, 0, 0, "Merged")
table.merge_cells(summary, 0, 0, 2, 0)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    objects = result.output["objects"]
    assert objects["linefills"] == [
        {
            "id": "linefill_3",
            "line1_id": "line_1",
            "line2_id": "line_2",
            "color": "rgba(38,166,154,0.3)",
            "pane": "main",
        }
    ]
    assert objects["polylines"][0]["points"] == [
        {"x": 0, "y": 1},
        {"x": 1, "y": 3},
        {"x": 2, "y": 2},
    ]
    assert objects["polylines"][0]["curved"] is True
    assert objects["polylines"][0]["closed"] is True
    assert objects["tables"][0]["merges"] == [
        {"start_column": 0, "start_row": 0, "end_column": 2, "end_row": 0}
    ]


def test_table_merge_rejects_overlap_and_out_of_bounds() -> None:
    overlap = pn.run(
        """
t = table.new(position.top_right, 3, 3)
table.merge_cells(t, 0, 0, 1, 1)
table.merge_cells(t, 1, 1, 2, 2)
""",
        _bars(),
        executor_mode="inline",
    )
    bounds = pn.run(
        """
t = table.new(position.top_right, 2, 2)
table.merge_cells(t, 0, 0, 2, 1)
""",
        _bars(),
        executor_mode="inline",
    )

    assert not overlap.ok
    assert "must not overlap" in str(overlap.error)
    assert not bounds.ok
    assert "outside the table" in str(bounds.error)


class _LowerTimeframeProvider:
    capabilities = {"request.security_lower_tf": True}

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        _ = symbol, timeframe, start, end
        return [
            {"time": 10, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 5},
            {"time": 12, "open": 2, "high": 2, "low": 1, "close": 1, "volume": 3},
            {"time": 20, "open": 4, "high": 4, "low": 4, "close": 4, "volume": 7},
            {"time": 30, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 11},
        ]


def test_pinned_tradingview_ta_10_adapter_uses_authoritative_intrabar_data() -> None:
    result = pn.run(
        """
tv_ta = pine_library("TradingView/ta/10")
up, down, delta = tv_ta.requestUpAndDownVolume("1")
plot(up, "Up")
plot(down, "Down")
plot(delta, "Delta")
""",
        _bars(),
        data_provider=_LowerTimeframeProvider(),
        syminfo={"tickerid": "TEST:BTCUSD"},
        timeframe={"period": "10"},
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Up") == [5.0, 7.0, 11.0]
    assert result.values("Down") == [-3.0, 0.0, 0.0]
    assert result.values("Delta") == [2.0, 7.0, 11.0]


def test_pinned_tradingview_ta_10_volume_delta_uses_period_cumulative_values() -> None:
    result = pn.run(
        """
tv_ta = pine_library("TradingView/ta/10")
opening, highest, lowest, current = tv_ta.requestVolumeDelta("1", "1D")
plot(opening, "Opening")
plot(highest, "Highest")
plot(lowest, "Lowest")
plot(current, "Current")
""",
        _bars(),
        data_provider=_LowerTimeframeProvider(),
        syminfo={"tickerid": "TEST:BTCUSD", "timezone": "UTC"},
        timeframe={"period": "10"},
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Opening") == [0.0, 2.0, 9.0]
    assert result.values("Highest") == [5.0, 9.0, 20.0]
    assert result.values("Lowest") == [0.0, 0.0, 0.0]
    assert result.values("Current") == [2.0, 9.0, 20.0]


def test_pinned_tradingview_ta_10_pure_series_members() -> None:
    bars = [
        {"time": 0, "open": 100, "high": 102, "low": 98, "close": 100, "volume": 1},
        {
            "time": 86_400,
            "open": 100,
            "high": 112,
            "low": 99,
            "close": 110,
            "volume": 1,
        },
        {
            "time": 31_536_000,
            "open": 110,
            "high": 125,
            "low": 105,
            "close": 121,
            "volume": 1,
        },
    ]
    result = pn.run(
        """
tv_ta = pine_library("TradingView/ta/10")
plot(tv_ta.changePercent(close, open), "Change")
plot(tv_ta.highestSince(bar_index == 1, close), "Highest Since")
plot(tv_ta.lowestSince(bar_index == 1, close), "Lowest Since")
plot(tv_ta.cagr(0, 100, 31536000, 121), "CAGR")
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Change") == [0.0, 10.0, 10.0]
    assert result.values("Highest Since") == [100.0, 110.0, 121.0]
    assert result.values("Lowest Since") == [100.0, 110.0, 110.0]
    assert result.values("CAGR") == pytest.approx([21.],abs=1e-12,rel=0)


def test_pinned_tradingview_ta_10_dynamic_smoothing_members() -> None:
    bars = [
        {"time": 0, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
        {"time": 1, "open": 11, "high": 13, "low": 11, "close": 12, "volume": 1},
        {"time": 2, "open": 13, "high": 15, "low": 13, "close": 14, "volume": 1},
        {"time": 3, "open": 14, "high": 15, "low": 12, "close": 13, "volume": 1},
        {"time": 4, "open": 15, "high": 17, "low": 15, "close": 16, "volume": 1},
    ]
    result = pn.run(
        """
tv_ta = pine_library("TradingView/ta/10")
plot(tv_ta.ema2(close, 2 + (bar_index >= 2) * 2), "EMA2")
plot(tv_ta.rma2(close, 3 - (bar_index >= 3)), "RMA2")
plot(tv_ta.atr2(3 - (bar_index >= 3)), "ATR2")
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("EMA2") == pytest.approx([10.0, 11.333333, 12.4, 12.64, 13.984])
    assert result.values("RMA2") == pytest.approx(
        [10.0, 10.666667, 11.777778, 12.388889, 14.194444]
    )
    assert result.values("ATR2") == pytest.approx(
        [2.0, 2.333333, 2.555556, 2.777778, 3.388889]
    )


def test_pinned_library_reports_member_level_host_requirements() -> None:
    descriptor = pn.SUPPORTED_PINE_LIBRARIES[0]

    assert descriptor.requirements_for({"ema2", "changePercent"}) == ()
    assert descriptor.requirements_for({"requestVolumeDelta"}) == (
        "request.security_lower_tf",
    )


def test_external_library_registry_fails_closed_for_unknown_library() -> None:
    result = pn.run(
        "pine_library('SomeAuthor/Unknown/1')",
        _bars(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
