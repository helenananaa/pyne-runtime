from __future__ import annotations

from pyne_runtime.incremental import strategy as incremental_strategy
from pyne_runtime.strategy import costs, ledger, orders, risk
from pyne_runtime.strategy.constants import (
    StrategyCommission,
    StrategyDirection,
    StrategyIntrabarPath,
    StrategyOca,
    StrategyRiskMode,
    StrategySameBarPriority,
)


def test_incremental_strategy_reuses_shared_constants() -> None:
    assert incremental_strategy.IncrementalStrategyDirection is StrategyDirection
    assert incremental_strategy.IncrementalStrategyCommission is StrategyCommission
    assert incremental_strategy.IncrementalStrategyRiskMode is StrategyRiskMode
    assert incremental_strategy.IncrementalStrategyNamespace.oca is StrategyOca
    assert incremental_strategy.IncrementalStrategyNamespace.same_bar is StrategySameBarPriority
    assert incremental_strategy.IncrementalStrategyNamespace.intrabar is StrategyIntrabarPath


def test_incremental_strategy_reuses_shared_order_helpers() -> None:
    assert incremental_strategy._pending_trigger is orders._pending_trigger
    assert incremental_strategy._exit_trigger is orders._exit_trigger
    assert incremental_strategy._normalize_intrabar_path is orders._normalize_intrabar_path
    assert (
        incremental_strategy._incremental_strategy_lifecycle_events
        is orders._incremental_strategy_lifecycle_events
    )

    assert orders._normalize_intrabar_path("same-bar-priority") == "same_bar_priority"
    assert orders._pending_trigger(
        side="long",
        open_price=10.0,
        high=11.0,
        low=9.0,
        limit=9.5,
        stop=10.5,
        same_bar_fill_priority=StrategySameBarPriority.limit_first,
        order_state={},
        close_price=10.0,
    ) is None  # The low precedes activation on the selected path.
    assert orders._exit_trigger(
        current_position=1.0,
        open_price=10.0,
        high=11.0,
        low=9.0,
        limit=10.5,
        stop=9.5,
        same_bar_fill_priority=StrategySameBarPriority.stop_first,
    ) == ("stop", 9.5)
    assert orders._exit_trigger(
        current_position=-1.0,
        open_price=73319.5,
        high=73339.3,
        low=72917.0,
        limit=9.0,
        stop=11.0,
        same_bar_fill_priority=StrategySameBarPriority.stop_first,
    ) == ("stop", 73319.5)
    assert orders._exit_trigger(
        current_position=1.0,
        open_price=8.5,
        high=10.0,
        low=8.0,
        limit=None,
        stop=9.0,
        same_bar_fill_priority=StrategySameBarPriority.stop_first,
    ) == ("stop", 8.5)

    assert orders._order_lifecycle_state(
        {
            "type": "entry",
            "_active": False,
            "_pending_submission": True,
        }
    ) == {
        "order_type": "entry",
        "active": False,
        "canceled": False,
        "rejected": False,
        "pending": True,
        "status": "pending",
        "phase": "pending",
    }


def test_incremental_strategy_reuses_shared_cost_and_risk_helpers() -> None:
    assert incremental_strategy._commission_amount is costs._commission_amount
    assert incremental_strategy._entry_rejection_reason is risk._entry_rejection_reason
    assert (
        incremental_strategy._entry_qty_for_max_position_size
        is risk._entry_qty_for_max_position_size
    )

    assert costs._commission_amount(
        commission_type=StrategyCommission.cash_per_contract,
        commission_value=0.5,
        qty=3,
        price=10,
    ) == 1.5
    assert risk._entry_rejection_reason(
        side="short",
        previous_size=1,
        same_direction_entry_count=0,
        pyramiding=0,
        allow_entry_in=StrategyDirection.long,
    ) == "direction_not_allowed"
    assert risk._entry_qty_for_max_position_size(
        side="long",
        previous_size=2,
        requested_qty=5,
        max_position_size=3,
    ) == 1


def test_incremental_strategy_reuses_shared_margin_helpers() -> None:
    assert incremental_strategy._margin_required is costs._margin_required
    assert incremental_strategy._is_exposure_reduction is costs._is_exposure_reduction

    assert costs._margin_required(
        position_size=2,
        price=50,
        margin_percent=25,
        pointvalue=1,
    ) == 25
    assert costs._is_exposure_reduction(5, 3)
    assert not costs._is_exposure_reduction(5, -1)


def test_incremental_strategy_reuses_shared_ledger_helpers() -> None:
    assert incremental_strategy._trade_realized_profit is ledger._trade_realized_profit
    assert incremental_strategy._closed_trade is ledger._closed_trade
    assert incremental_strategy._trade_at is ledger._trade_at
    assert incremental_strategy._trade_profit_percent is ledger._trade_profit_percent
    assert incremental_strategy._event_time is ledger._event_time

    trade = {"side": "long", "qty": 2, "entry_price": 10}
    assert ledger._trade_realized_profit(trade, 1.5, 12) == 3


def test_shared_incremental_lifecycle_kernel_is_order_stable() -> None:
    orders_input = [
        {
            "id": f"O{index}",
            "type": "entry",
            "_seq": index,
            "_submit_time": index // 3,
            "time": index,
            "_active": index % 4 == 0,
            "_pending_submission": index % 4 == 1,
            "_canceled": index % 4 == 2,
            "_rejected_reason": "risk" if index % 4 == 3 else None,
            "qty": 1.0,
            "price": 100.0 + index,
        }
        for index in range(100)
    ]
    shuffled = list(reversed(orders_input))

    expected = orders._incremental_strategy_lifecycle_events(orders_input)
    actual = orders._incremental_strategy_lifecycle_events(shuffled)

    assert actual == expected
    assert len(actual) == 100
