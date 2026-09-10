from __future__ import annotations

import importlib

import pyne_runtime as pn
import pytest


strategy_module = importlib.import_module("pyne_runtime.strategy.module")
strategy_replay = importlib.import_module("pyne_runtime.strategy.replay")
strategy_ledger = importlib.import_module("pyne_runtime.strategy.ledger")


def _bars(count: int) -> list[dict[str, float]]:
    return [
        {
            "time": index + 1,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("bar_count", [32, 64, 128])
def test_default_dense_strategy_keeps_replay_and_snapshots_linear(
    monkeypatch: pytest.MonkeyPatch,
    bar_count: int,
) -> None:
    counters = {
        "replays": 0,
        "snapshot_writes": 0,
        "captured_trade_items": 0,
    }
    original_replay = strategy_module.replay_strategy_orders
    original_write_snapshot = strategy_replay._write_strategy_snapshot

    def counted_replay(strategy, **kwargs):
        counters["replays"] += 1
        return original_replay(strategy, **kwargs)

    def counted_write_snapshot(strategy, **kwargs):
        result = original_write_snapshot(strategy, **kwargs)
        counters["snapshot_writes"] += 1
        counters["captured_trade_items"] += sum(
            len(trades) for trades in strategy._closed_trades_by_bar
        )
        counters["captured_trade_items"] += sum(
            len(trades) for trades in strategy._open_trades_by_bar
        )
        assert strategy._closed_trades_by_bar == []
        assert strategy._open_trades_by_bar == []
        return result

    monkeypatch.setattr(strategy_module, "replay_strategy_orders", counted_replay)
    monkeypatch.setattr(strategy_replay, "_write_strategy_snapshot", counted_write_snapshot)

    result = pn.run(
        """
strategy("Dense")
strategy.order_when(True, "Long", strategy.long, qty=1, price=close)
""",
        _bars(bar_count),
        executor_mode="inline",
    )

    assert result.ok
    assert counters == {
        "replays": 1,
        "snapshot_writes": bar_count,
        "captured_trade_items": 0,
    }
    assert len(result.output["strategy"]["orders"]) == bar_count
    assert len(result.output["strategy"]["opentrades"]) == bar_count


@pytest.mark.parametrize("bar_count", [32, 64, 128])
def test_alternating_close_materializes_in_one_replay(
    monkeypatch: pytest.MonkeyPatch,
    bar_count: int,
) -> None:
    counters = {"replays": 0, "snapshot_writes": 0}
    original_replay = strategy_module.replay_strategy_orders
    original_write_snapshot = strategy_replay._write_strategy_snapshot

    def counted_replay(strategy, **kwargs):
        counters["replays"] += 1
        return original_replay(strategy, **kwargs)

    def counted_write_snapshot(strategy, **kwargs):
        counters["snapshot_writes"] += 1
        return original_write_snapshot(strategy, **kwargs)

    monkeypatch.setattr(strategy_module, "replay_strategy_orders", counted_replay)
    monkeypatch.setattr(strategy_replay, "_write_strategy_snapshot", counted_write_snapshot)

    result = pn.run(
        """
strategy("Alternating Close")
strategy.order_when(bar_index % 2 == 0, "Long", strategy.long, qty=1, price=close)
strategy.close_when(bar_index % 2 == 1, "", price=close)
plot(strategy.position_size, "Position")
""",
        _bars(bar_count),
        executor_mode="inline",
    )

    assert result.ok
    assert counters == {"replays": 2, "snapshot_writes": 2 * bar_count}
    assert result.values("Position") == [1.0, 0.0] * (bar_count // 2)
    assert len(result.output["strategy"]["orders"]) == bar_count
    assert len(result.output["strategy"]["closedtrades"]) == bar_count // 2


def test_alternating_exit_materializes_against_live_position_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_calls = 0
    original_replay = strategy_module.replay_strategy_orders

    def counted_replay(strategy, **kwargs):
        nonlocal replay_calls
        replay_calls += 1
        return original_replay(strategy, **kwargs)

    monkeypatch.setattr(strategy_module, "replay_strategy_orders", counted_replay)
    bar_count = 64
    result = pn.run(
        """
strategy("Alternating Exit")
strategy.entry_when(bar_index % 2 == 0, "Long", strategy.long, qty=1, price=close)
strategy.exit("Exit", from_entry="Long", limit=100, when=bar_index % 2 == 1)
plot(strategy.position_size, "Position")
""",
        _bars(bar_count),
        executor_mode="inline",
    )

    assert result.ok
    assert replay_calls == 2
    assert result.values("Position") == [1.0, 0.0] * (bar_count // 2)
    assert len(result.output["strategy"]["closedtrades"]) == bar_count // 2


def test_process_orders_on_close_uses_compact_trade_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_strategy = None
    original_write_snapshot = strategy_replay._write_strategy_snapshot

    def observed_write_snapshot(strategy, **kwargs):
        nonlocal observed_strategy
        observed_strategy = strategy
        result = original_write_snapshot(strategy, **kwargs)
        assert strategy._closed_trades_by_bar == []
        assert strategy._open_trades_by_bar == []
        return result

    monkeypatch.setattr(strategy_replay, "_write_strategy_snapshot", observed_write_snapshot)
    bars = _bars(4)
    result = pn.run(
        """
strategy("Snapshots", process_orders_on_close=True)
strategy.entry("Long", strategy.long, when=bar_index == 0, price=close)
strategy.close("Long", when=bar_index == 2, price=close)
plot(strategy.closedtrades.profit(0), "Closed Profit")
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok
    assert observed_strategy is not None
    assert len(observed_strategy._open_trade_events_by_bar) == len(bars)
    assert sum(map(len, observed_strategy._open_trade_events_by_bar)) == 2
    assert result.values("Closed Profit") == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize("bar_count", [32, 64, 128])
def test_process_orders_on_close_dense_ledger_storage_is_linear(
    monkeypatch: pytest.MonkeyPatch,
    bar_count: int,
) -> None:
    observed_strategy = None
    replay_calls = 0
    original_replay = strategy_module.replay_strategy_orders

    def observed_replay(strategy, **kwargs):
        nonlocal observed_strategy, replay_calls
        observed_strategy = strategy
        replay_calls += 1
        return original_replay(strategy, **kwargs)

    monkeypatch.setattr(strategy_module, "replay_strategy_orders", observed_replay)
    result = pn.run(
        """
strategy("Dense On Close", process_orders_on_close=True)
strategy.order_when(True, "Long", strategy.long, qty=1, price=close)
""",
        _bars(bar_count),
        executor_mode="inline",
    )

    assert result.ok
    assert replay_calls == 1
    assert observed_strategy is not None
    assert observed_strategy._closed_trades_by_bar == []
    assert observed_strategy._open_trades_by_bar == []
    assert len(observed_strategy._open_trade_events_by_bar) == bar_count
    assert sum(map(len, observed_strategy._open_trade_events_by_bar)) == bar_count - 1
    assert len(result.output["strategy"]["opentrades"]) == bar_count


def test_process_orders_on_close_open_trade_projection_tracks_lot_updates() -> None:
    result = pn.run(
        """
strategy("Open Projection", process_orders_on_close=True, pyramiding=2)
strategy.entry("A", strategy.long, qty=2, when=bar_index == 0, price=close)
strategy.entry("B", strategy.long, qty=1, when=bar_index == 1, price=close)
strategy.close("A", qty=1, when=bar_index == 2, price=close)
plot(strategy.opentrades.size(0), "First Size")
plot(strategy.opentrades.size(-1), "Last Size")
plot(strategy.opentrades.entry_bar_index(0), "First Entry Bar")
""",
        _bars(4),
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("First Size") == [0.0, 2.0, 2.0, 1.0]
    assert result.values("Last Size") == [0.0, 2.0, 1.0, 1.0]
    assert result.values("First Entry Bar") == [0.0, 0.0, 0.0, 0.0]


def test_risk_liquidations_are_rederived_without_persistent_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_risk_counts: list[int] = []
    original_ordering = strategy_replay._orders_in_replay_order

    def observed_ordering(orders):
        source_risk_counts.append(sum(bool(order.get("_risk_liquidation")) for order in orders))
        return original_ordering(orders)

    monkeypatch.setattr(strategy_replay, "_orders_in_replay_order", observed_ordering)
    result = pn.run(
        """
strategy("Risk Source", initial_capital=1000)
strategy.risk.max_intraday_loss(5, strategy.percent_of_equity)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=10, price=close)
strategy.entry_when(bar_index == 2, "Blocked", strategy.long, qty=1, price=close)
strategy.close_all(when=bar_index == 2, price=close)
strategy.entry_when(bar_index == 3, "Reset", strategy.long, qty=1, price=close)
""",
        [
            {
                "time": 1,
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1,
                "session_isfirstbar": True,
            },
            {"time": 2, "open": 100, "high": 100, "low": 89, "close": 90, "volume": 1},
            {"time": 3, "open": 90, "high": 91, "low": 89, "close": 90, "volume": 1},
            {
                "time": 4,
                "open": 90,
                "high": 91,
                "low": 89,
                "close": 90,
                "volume": 1,
                "session_isfirstbar": True,
            },
            {"time": 5, "open": 90, "high": 92, "low": 89, "close": 90, "volume": 1},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert source_risk_counts == [0, 0, 0, 0]
    assert [
        order["id"]
        for order in result.output["strategy"]["orders"]
        if order["id"] == "risk.max_intraday_loss"
    ] == ["risk.max_intraday_loss"]


def test_replay_discards_stale_risk_liquidation_after_earlier_order_reduces_loss() -> None:
    result = pn.run(
        """
strategy("Stale Risk", initial_capital=1000)
strategy.risk.max_intraday_loss(5, strategy.percent_of_equity)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=10, price=close)
strategy.order_when(bar_index == 0, "Reduce", strategy.short, qty=6, price=close)
plot(strategy.position_size, "Position")
""",
        [
            {
                "time": 1,
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "volume": 1,
                "session_isfirstbar": True,
            },
            {"time": 2, "open": 100, "high": 100, "low": 90, "close": 100, "volume": 1},
            {"time": 3, "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Position") == [4.0, 4.0, 4.0]
    assert all(
        order["id"] != "risk.max_intraday_loss" for order in result.output["strategy"]["orders"]
    )


def test_repeated_session_risk_orders_do_not_grow_replay_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sizes: list[tuple[int, int]] = []
    original_ordering = strategy_replay._orders_in_replay_order

    def observed_ordering(orders):
        source_sizes.append(
            (
                len(orders),
                sum(bool(order.get("_risk_liquidation")) for order in orders),
            )
        )
        return original_ordering(orders)

    monkeypatch.setattr(strategy_replay, "_orders_in_replay_order", observed_ordering)
    bar_count = 16
    bars = [
        {
            **bar,
            "low": 98.0,
            "session_isfirstbar": True,
        }
        for bar in _bars(bar_count)
    ]
    result = pn.run(
        """
strategy("Repeated Risk", initial_capital=100000)
strategy.risk.max_intraday_loss(1, strategy.cash)
strategy.entry_when(session.isfirstbar, "Long", strategy.long, qty=1, price=close)
strategy.cancel("missing", when=False)
strategy.close_all(when=False)
""",
        bars,
        executor_mode="inline",
    )

    assert result.ok
    assert source_sizes == [(bar_count, 0)] * 3
    assert (
        sum(
            order["id"] == "risk.max_intraday_loss" for order in result.output["strategy"]["orders"]
        )
        == bar_count
    )


@pytest.mark.parametrize("bar_count", [32, 64, 128])
def test_never_triggered_pending_orders_use_price_index_without_full_scans(
    monkeypatch: pytest.MonkeyPatch,
    bar_count: int,
) -> None:
    trigger_calls = 0
    original_trigger = strategy_replay._pending_trigger

    def observed_trigger(**kwargs):
        nonlocal trigger_calls
        trigger_calls += 1
        return original_trigger(**kwargs)

    monkeypatch.setattr(strategy_replay, "_pending_trigger", observed_trigger)
    result = pn.run(
        """
strategy("Indexed Pending")
strategy.entry_when(True, "Long", strategy.long, qty=1, stop=200)
""",
        _bars(bar_count),
        executor_mode="inline",
    )

    assert result.ok
    assert trigger_calls == 0


def test_pending_order_operation_budget_is_exact_and_cumulative_across_replays() -> None:
    bars = _bars(5)
    settings = pn.PyneSettings(max_strategy_pending_operations=15)
    one_replay = pn.run(
        """
strategy("Budget", initial_capital=0, margin_long=100)
strategy.entry_when(True, "Long", strategy.long, qty=1, limit=200)
""",
        bars,
        settings=settings,
        executor_mode="inline",
    )
    repeated_replay = pn.run(
        """
strategy("Budget", initial_capital=0, margin_long=100)
strategy.entry_when(True, "Long", strategy.long, qty=1, limit=200)
strategy.cancel("missing", when=False)
""",
        bars,
        settings=settings,
        executor_mode="inline",
    )

    assert one_replay.ok
    assert not repeated_replay.ok
    assert repeated_replay.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    assert "pending-order operation budget exceeded (max 15)" in str(repeated_replay.error)


def test_process_orders_on_close_rank_index_preserves_positive_and_negative_accessors() -> None:
    result = pn.run(
        """
strategy("Ranks", process_orders_on_close=True, pyramiding=3)
strategy.entry("A", strategy.long, qty=1, when=bar_index == 0, price=close)
strategy.entry("B", strategy.long, qty=2, when=bar_index == 1, price=close)
strategy.entry("C", strategy.long, qty=3, when=bar_index == 2, price=close)
plot(strategy.opentrades.size(1), "Middle")
plot(strategy.opentrades.size(-2), "Negative")
plot(strategy.opentrades.entry_bar_index(1), "Middle Bar")
""",
        _bars(4),
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Middle") == [0.0, 0.0, 2.0, 2.0]
    assert result.values("Negative") == [1.0, 2.0]
    assert result.values("Middle Bar") == [0.0, 0.0, 1.0, 1.0]


@pytest.mark.parametrize("lot_count", [32, 64, 128])
def test_active_trade_middle_rank_lookup_is_logarithmic(lot_count: int) -> None:
    index = strategy_ledger._ActiveTradeIndex(list(range(lot_count)))
    for lot_id in range(lot_count):
        index.upsert(lot_id, {"_lot_id": lot_id, "qty": float(lot_id + 1)})

    class CountingTree(list):
        reads = 0

        def __getitem__(self, item):
            self.reads += 1
            return super().__getitem__(item)

    tree = CountingTree(index._tree)
    index._tree = tree
    for _ in range(lot_count):
        assert index.trade_at(lot_count // 2)["_lot_id"] == lot_count // 2

    assert tree.reads <= 2 * lot_count * (lot_count.bit_length() + 1)
