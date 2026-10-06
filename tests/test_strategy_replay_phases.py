"""Observable chronology and exception boundaries of historical replay phases."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from pyne_runtime.context import PyneContext
from pyne_runtime.plot import OutputCollector
from pyne_runtime.security import PyneResourceLimitError
from pyne_runtime.strategy import StrategyModule
from pyne_runtime.strategy.replay import replay_strategy_orders


BARS = [
    dict(time=1, open=10, high=10.5, low=9, close=10, volume=1),
    dict(time=2, open=10, high=12, low=9, close=11, volume=1),
    dict(time=3, open=11, high=12, low=10, close=11, volume=1),
]


def _strategy(close_fill=False):
    context = PyneContext.from_ohlcv(BARS)
    collector = OutputCollector(context.times)
    strategy = StrategyModule(context, collector)
    strategy.configure(initial_capital=1000, process_orders_on_close=close_fill)
    return strategy, collector


@pytest.mark.parametrize(
    "close_fill, visible, arrays",
    [(False, [0, 1, 3], [0, 3, 3]), (True, [0, 2, 3], [0, 2, 3])],
)
def test_materializer_sees_carried_fills_and_scheduled_commands_in_original_order(
    close_fill, visible, arrays,
):
    strategy, _ = _strategy(close_fill)
    strategy.entry("pending", qty=2, stop=11, when=[True, False, False])
    strategy.order("same_bar", qty=1, when=[False, True, False])
    observed = []

    def materialize(idx, timestamp, position):
        observed.append(position)
        return None

    replay_strategy_orders(strategy, materialize_order=materialize)
    assert observed == visible
    assert strategy._position_size.tolist() == arrays
    assert strategy._pending_order_operations == 3


def test_pending_book_initialization_failure_keeps_history_and_discards_derived_orders(monkeypatch):
    strategy, collector = _strategy()
    strategy.order("source", qty=1, when=[True, False, False])
    source = copy.deepcopy(collector.strategy_orders)
    collector.strategy_orders.append({"_risk_liquidation": True})
    marker = [[{"id": "old-history"}]]
    strategy._closed_trades_by_bar = marker
    strategy._open_trades_by_bar = marker
    failure = RuntimeError("cannot initialize pending book")

    def fail():
        raise failure

    monkeypatch.setattr(strategy, "_limit_fill_verification_amount", fail)
    with pytest.raises(RuntimeError) as caught:
        replay_strategy_orders(strategy)
    assert caught.value is failure
    assert collector.strategy_orders == source
    assert strategy._closed_trades_by_bar is marker
    assert strategy._open_trades_by_bar is marker


def test_session_flag_failure_resets_history_before_resetting_source_order_metadata(monkeypatch):
    strategy, collector = _strategy(close_fill=True)
    strategy.order("source", qty=1, when=[True, False, False])
    source = copy.deepcopy(collector.strategy_orders)
    collector.strategy_orders.append({"_risk_liquidation": True})
    strategy._closed_trades_by_bar = [[{"id": "old-history"}]]
    strategy._open_trades_by_bar = [[{"id": "old-history"}]]
    failure = RuntimeError("bad session flag")

    class InvalidFlag:
        def __bool__(self):
            raise failure

    monkeypatch.setattr(strategy._context, "session", SimpleNamespace(isfirstbar=[InvalidFlag()] * 3))
    with pytest.raises(RuntimeError) as caught:
        replay_strategy_orders(strategy)
    assert caught.value is failure
    assert collector.strategy_orders == source
    assert strategy._closed_trades_by_bar == []
    assert strategy._open_trades_by_bar == []
    assert strategy._open_trade_events_by_bar == [[], [], []]


@pytest.mark.parametrize("close_fill", [False, True])
def test_budget_failure_keeps_cumulative_count_and_does_not_publish_a_new_report(close_fill):
    strategy, collector = _strategy(close_fill)
    strategy.entry("pending", qty=2, stop=11, when=[True, False, False])
    report = copy.deepcopy(collector.strategy_report)
    consumed = strategy._pending_order_operations
    strategy._max_pending_order_operations = consumed
    with pytest.raises(PyneResourceLimitError, match=f"max {consumed}"):
        replay_strategy_orders(strategy)
    assert strategy._pending_order_operations == consumed + 1
    assert collector.strategy_report == report
    assert not collector.strategy_orders[0]["_active"]
    # Completed prior bars remain published; later arrays retain their old values.
    assert strategy._position_size.tolist() == [0, 2, 2]
