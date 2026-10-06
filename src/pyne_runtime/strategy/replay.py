"""Historical strategy replay coordinated by explicit execution phases."""

from __future__ import annotations
from typing import Any
from .replay_events import prepare_source_orders, process_scheduled_orders
from .replay_fills import fill_pending_orders
from .replay_risk import start_bar_risk, liquidate_bar_risk, finish_bar_risk
from .replay_state import MaterializeOrder, initialize_replay
from .replay_values import (
    _condition_values as _condition_values,
    _normalize_direction as _normalize_direction,
    _optional_numeric_values as _optional_numeric_values,
    _optional_price_values as _optional_price_values,
    _price_values as _price_values,
    _requested_close_qty as _requested_close_qty,
)


def replay_strategy_orders(
    strategy: Any, *, materialize_order: MaterializeOrder | None = None
) -> None:
    """Replay source commands with carried, calculation, fill, and risk phases.

    Materialization runs after existing same-time commands. Close-fill mode
    publishes the carried position before this bar's newly submitted fills.
    """
    bindings, state = initialize_replay(strategy)
    orders_by_time = prepare_source_orders(bindings)
    for idx, timestamp in enumerate(bindings.times):
        start_bar_risk(bindings, state, idx)
        if bindings.configuration.process_orders_on_close:
            fill_pending_orders(bindings, state, idx, timestamp, carried_only=True)
        bar_open_size = state.current_size
        if bindings.configuration.process_orders_on_close:
            bindings.output.write(idx, state)
        visible_fill = process_scheduled_orders(
            bindings, state, orders_by_time, idx, timestamp, bar_open_size, materialize_order
        )
        fill_pending_orders(
            bindings,
            state,
            idx,
            timestamp,
            carried_only=False if bindings.configuration.process_orders_on_close else None,
        )
        if liquidate_bar_risk(bindings, state, idx, timestamp, bar_open_size):
            visible_fill = True
        if not bindings.configuration.process_orders_on_close or visible_fill:
            bindings.output.write(idx, state)
        finish_bar_risk(bindings, state, idx)
    bindings.output.publish(state)
