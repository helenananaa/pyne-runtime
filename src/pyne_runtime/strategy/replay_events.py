"""Source-order reset, chronological scheduling, and command admission."""

from __future__ import annotations
import numpy as np
from .orders import _orders_in_replay_order, _is_pending_submission, _reject_order
from .risk import _entry_rejection_reason
from .replay_fills import fill_market_entry, fill_market_order, fill_close_order
from .replay_state import MaterializeOrder, Order, ReplayBindings, ReplayState
from .replay_values import _normalize_direction


def collect_source_orders(orders: list[Order]) -> list[Order]:
    """Remove derived risk orders before any replay initialization can fail."""
    source_orders = [order for order in orders if not order.get("_risk_liquidation")]
    if len(source_orders) != len(orders):
        orders[:] = source_orders
    return source_orders


def prepare_source_orders(bindings: ReplayBindings) -> dict[int, list[Order]]:
    orders_by_time: dict[int, list[Order]] = {}
    for order in _orders_in_replay_order(bindings.source_orders):
        order["_active"] = False
        order.pop("_stop_limit_activated", None)
        order.pop("_filled_qty", None)
        order.pop("_requested_fill_qty", None)
        order.pop("_target_qty", None)
        order.pop("_transaction_qty", None)
        if order.get("type") in {"entry", "order"}:
            order.pop("_canceled", None)
            order.pop("_canceled_time", None)
            order.pop("_canceled_by", None)
            order.pop("_rejected_reason", None)
            order.pop("_rejected_time", None)
            order["time"] = int(order.get("_submit_time", order.get("time", 0)))
            order["qty"] = float(order.get("_original_qty", order.get("qty", 0.0)))
            order["position_after"] = 0.0
            order["price"] = round(float(order.get("_base_price", order.get("price", np.nan))), 8)
            order.pop("commission", None)
            order.pop("oca_name", None)
            order.pop("oca_type", None)
            if _is_pending_submission(order):
                order.pop("reason", None)
        elif order.get("type") in {"cancel", "cancel_all"}:
            order.pop("canceled", None)
        orders_by_time.setdefault(int(order.get("time", 0)), []).append(order)
    return orders_by_time


def process_scheduled_orders(
    bindings: ReplayBindings,
    state: ReplayState,
    orders_by_time: dict[int, list[Order]],
    idx: int,
    timestamp: int,
    bar_open_size: float,
    materialize_order: MaterializeOrder | None,
) -> bool:
    same_bar_visible_fill = False
    # Copy only this timestamp's source schedule, as before. Materialized
    # commands run last and cannot become visible ahead of earlier commands.
    scheduled = list(orders_by_time.get(timestamp, []))
    sentinel = object()
    if materialize_order is not None:
        scheduled.append(sentinel)
    for item in scheduled:
        if item is sentinel:
            visible_position = (
                bar_open_size
                if bindings.configuration.process_orders_on_close
                else state.current_size
            )
            order = materialize_order(idx, timestamp, visible_position)
            if order is None:
                continue
            bindings.orders.append(order)
        else:
            order = item
        if dispatch_order(bindings, state, order, idx, timestamp):
            same_bar_visible_fill = True
    return same_bar_visible_fill


def dispatch_order(
    bindings: ReplayBindings, state: ReplayState, order: Order, idx: int, timestamp: int
) -> bool:
    if order.get("type") == "entry":
        bindings.pending_orders.validate_entry_direction(order)
        if state.risk.risk_locked:
            _reject_order(order, timestamp=timestamp, reason="risk_locked")
            return False
        if _is_pending_submission(order):
            admission_size, admission_count = bindings.pending_orders.entry_admission_state(
                order, size=state.current_size, count=len(state.open_trades)
            )
            rejection_reason = _entry_rejection_reason(
                side=_normalize_direction(str(order.get("side", bindings.long))),
                previous_size=admission_size,
                same_direction_entry_count=admission_count,
                pyramiding=bindings.configuration.pyramiding,
                allow_entry_in=bindings.configuration.allow_entry_in,
            )
            if rejection_reason is not None:
                if rejection_reason == "pyramiding_exceeded" and (
                    not order.get("_market_submission")
                ):
                    bindings.pending_orders.cancel_market_entry(order)
                _reject_order(order, timestamp=timestamp, reason=rejection_reason)
                return False
            bindings.pending_orders.add(order)
            return False
        fill_market_entry(bindings, state, order, idx, timestamp)
    elif order.get("type") == "order":
        if state.risk.risk_locked:
            _reject_order(order, timestamp=timestamp, reason="risk_locked")
            return False
        if _is_pending_submission(order):
            bindings.pending_orders.add(order)
            return False
        fill_market_order(bindings, state, order, idx, timestamp)
    elif order.get("type") in {"close", "close_all", "exit"} and state.current_size != 0:
        return fill_close_order(bindings, state, order, idx)
    elif order.get("type") == "cancel":
        canceled = bindings.pending_orders.cancel_id(
            str(order.get("id") or ""), timestamp=timestamp, canceled_by=str(order.get("id") or "")
        )
        if canceled:
            order["canceled"] = len(canceled)
            order["_active"] = True
    elif order.get("type") == "cancel_all":
        if bindings.pending_orders:
            canceled = bindings.pending_orders.cancel_all(
                timestamp=timestamp, canceled_by="cancel_all"
            )
            order["canceled"] = len(canceled)
            order["_active"] = True
    return False
