"""Pending and immediate fills, preserving their distinct admission rules."""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..values import is_na_value
from .constants import StrategyOca
from .costs import _strategy_equity
from .ledger import _record_fill, _target_open_qty
from .orders import _pending_trigger, _reject_order
from .risk import (
    _entry_qty_for_max_position_size,
    _entry_rejection_reason,
    _intraday_filled_orders_hit,
)
from .replay_state import Order, ReplayBindings, ReplayState
from .replay_values import (
    _entry_position_after,
    _order_position_after,
    _normalize_direction,
    _position_avg_from_open_trades,
    _requested_close_qty,
)


@dataclass(frozen=True)
class _PendingFill:
    side: str
    qty: float
    fill_price: float
    position_after: float
    avg_after: float


def fill_pending_orders(
    bindings: ReplayBindings,
    state: ReplayState,
    idx: int,
    timestamp: int,
    *,
    carried_only: bool | None,
) -> None:
    if bindings.pending_orders and not state.risk.risk_locked:
        open_price = float(bindings.open[idx])
        high = float(bindings.high[idx])
        low = float(bindings.low[idx])
        for order in bindings.pending_orders.candidates(high=high, low=low):
            _fill_pending_candidate(
                bindings, state, order, idx, timestamp, open_price, high, low, carried_only
            )


def _fill_pending_candidate(
    bindings: ReplayBindings,
    state: ReplayState,
    order: Order,
    idx: int,
    timestamp: int,
    open_price: float,
    high: float,
    low: float,
    carried_only: bool | None,
) -> None:
    if not bindings.pending_orders.contains(order):
        return
    if state.risk.risk_locked and order.get("type") in {"entry", "order"}:
        bindings.pending_orders.reindex(order)
        return
    submitted_before_bar = int(order.get("_submit_time", order.get("time", 0))) < timestamp
    if carried_only is not None and submitted_before_bar != carried_only:
        bindings.pending_orders.reindex(order)
        return
    bindings.consume_operations()
    trigger_reference_price = open_price
    trigger_high, trigger_low = (high, low)
    if (
        bindings.configuration.process_orders_on_close
        and int(order.get("_submit_time", order.get("time", 0))) == timestamp
    ):
        trigger_reference_price = float(bindings.close[idx])
        trigger_high = trigger_low = trigger_reference_price
    trigger = _pending_trigger(
        side=_normalize_direction(str(order.get("side", bindings.long))),
        open_price=trigger_reference_price,
        high=trigger_high,
        low=trigger_low,
        limit=order.get("_limit"),
        stop=order.get("_stop"),
        tick_verify=bindings.limit_fill_verification_amount(),
        same_bar_fill_priority=bindings.configuration.same_bar_fill_priority,
        intrabar_path=bindings.configuration.intrabar_path,
        order_state=order,
        close_price=float(bindings.close[idx]),
    )
    if trigger is None:
        bindings.pending_orders.reindex(order)
        return
    reason, trigger_price = trigger
    order["time"] = timestamp
    if reason is not None:
        order["reason"] = reason
    else:
        order.pop("reason", None)
    order["_base_price"] = float(trigger_price)
    fill = _prepare_pending_position(bindings, state, order, idx, timestamp, trigger_price)
    if fill is not None:
        _complete_pending_fill(bindings, state, order, idx, fill)


def _prepare_pending_position(
    bindings: ReplayBindings,
    state: ReplayState,
    order: Order,
    idx: int,
    timestamp: int,
    trigger_price: float,
) -> _PendingFill | None:
    """Admit a triggered order without changing its margin retry semantics."""
    if order.get("type") == "entry":
        side = _normalize_direction(str(order.get("side", bindings.long)))
        rejection_reason = _entry_rejection_reason(
            side=side,
            previous_size=state.current_size,
            same_direction_entry_count=len(state.open_trades),
            pyramiding=bindings.configuration.pyramiding,
            allow_entry_in=bindings.configuration.allow_entry_in,
            check_pyramiding=False,
        )
        if rejection_reason is not None:
            _reject_order(order, timestamp=timestamp, reason=rejection_reason)
            bindings.pending_orders.remove(order)
            return
        fill_side = "buy" if side == bindings.long else "sell"
        fill_price = bindings.fill_price(float(trigger_price), fill_side)
        qty = _entry_qty_for_max_position_size(
            side=side,
            previous_size=state.current_size,
            requested_qty=float(order.get("qty", 0.0)),
            max_position_size=bindings.configuration.max_position_size,
        )
        order["_requested_fill_qty"] = float(order.get("_original_qty", order.get("qty", 0.0)))
        if qty <= 0:
            order["_filled_qty"] = 0.0
            _reject_order(order, timestamp=timestamp, reason="max_position_size")
            bindings.pending_orders.remove(order)
            return
        position_after, avg_after = _entry_position_after(
            previous_size=state.current_size,
            previous_avg=state.current_avg,
            side=side,
            qty=qty,
            price=fill_price,
        )
        pre_fill_equity = _strategy_equity(
            initial_capital=bindings.configuration.initial_capital,
            gross_profit=state.gross_profit,
            gross_loss=state.gross_loss,
            total_commission=state.total_commission,
            position_size=state.current_size,
            position_avg=state.current_avg,
            close_price=float(bindings.close[idx]),
        )
        if not bindings.margin_allows_position(
            previous_size=state.current_size,
            next_size=position_after,
            price=fill_price,
            equity=pre_fill_equity,
        ):
            bindings.pending_orders.reindex(order)
            return
        if state.current_size == 0 or (state.current_size > 0) != (position_after > 0):
            state.same_direction_entry_count = 1
        else:
            state.same_direction_entry_count += 1
    else:
        side = _normalize_direction(str(order.get("side", bindings.long)))
        fill_side = "buy" if side == bindings.long else "sell"
        fill_price = bindings.fill_price(float(trigger_price), fill_side)
        qty = float(order.get("qty", 0.0))
        order["_requested_fill_qty"] = float(order.get("_original_qty", qty))
        position_after, avg_after = _order_position_after(
            previous_size=state.current_size,
            previous_avg=state.current_avg,
            side=side,
            qty=qty,
            price=fill_price,
        )
        pre_fill_equity = _strategy_equity(
            initial_capital=bindings.configuration.initial_capital,
            gross_profit=state.gross_profit,
            gross_loss=state.gross_loss,
            total_commission=state.total_commission,
            position_size=state.current_size,
            position_avg=state.current_avg,
            close_price=float(bindings.close[idx]),
        )
        if not bindings.margin_allows_position(
            previous_size=state.current_size,
            next_size=position_after,
            price=fill_price,
            equity=pre_fill_equity,
        ):
            bindings.pending_orders.reindex(order)
            return
        if position_after == 0:
            state.same_direction_entry_count = 0
        elif state.current_size == 0 or (state.current_size > 0) != (position_after > 0):
            state.same_direction_entry_count = 1
    return _PendingFill(side, qty, fill_price, position_after, avg_after)


def _complete_pending_fill(
    bindings: ReplayBindings, state: ReplayState, order: Order, idx: int, fill: _PendingFill
) -> None:
    """Publish a fill, account for it, then apply fill-count risk and OCA."""
    previous_size = state.current_size
    state.current_size = fill.position_after
    state.current_avg = fill.avg_after
    if order.get("type") == "entry":
        order["qty"] = round(fill.qty, 8)
    order["_filled_qty"] = round(float(fill.qty), 8)
    order["price"] = round(float(fill.fill_price), 8)
    order["position_after"] = round(float(fill.position_after), 8)
    if order.get("_oca_name"):
        order["oca_name"] = order.get("_oca_name")
        order["oca_type"] = order.get("_oca_type") or StrategyOca.none
    fill_qty = float(order.get("qty", 0.0))
    signed_qty = fill_qty if fill.side == bindings.long else -fill_qty
    transaction_qty = abs(fill.position_after - previous_size)
    commission_qty = transaction_qty if order.get("type") == "entry" else fill_qty
    if order.get("type") == "entry" and abs(transaction_qty - fill_qty) > 1e-09:
        order["_transaction_qty"] = round(transaction_qty, 8)
    commission = bindings.apply_commission(order, qty=commission_qty, price=fill.fill_price)
    order["_fill_bar_index"] = idx
    state.gross_profit, state.gross_loss, state.total_commission, state.open_trades = _record_fill(
        order=order,
        signed_qty=fill.position_after - previous_size
        if order.get("type") == "entry"
        else signed_qty,
        previous_size=previous_size,
        fill_price=fill.fill_price,
        next_size=fill.position_after,
        commission=commission,
        open_trades=state.open_trades,
        closed_trades=state.closed_trades,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        open_trade_events=state.open_trade_events,
    )
    order["_avg_price_after"] = (
        round(float(fill.avg_after), 8) if not is_na_value(fill.avg_after) else None
    )
    order["_active"] = True
    bindings.pending_orders.remove(order)
    if order.get("type") in {"entry", "order"}:
        state.risk.intraday_filled_orders += 1
        if _intraday_filled_orders_hit(
            filled_orders=state.risk.intraday_filled_orders,
            threshold=bindings.configuration.max_intraday_filled_orders,
        ):
            state.risk.filled_orders_locked = True
            state.risk.risk_locked = True
    bindings.pending_orders.apply_oca_after_fill(order)


def fill_market_entry(
    bindings: ReplayBindings, state: ReplayState, order: Order, idx: int, timestamp: int
) -> None:
    side = _normalize_direction(str(order.get("side", bindings.long)))
    rejection_reason = _entry_rejection_reason(
        side=side,
        previous_size=state.current_size,
        same_direction_entry_count=len(state.open_trades),
        pyramiding=bindings.configuration.pyramiding,
        allow_entry_in=bindings.configuration.allow_entry_in,
    )
    if rejection_reason is not None:
        _reject_order(order, timestamp=timestamp, reason=rejection_reason)
        return
    fill_side = "buy" if side == bindings.long else "sell"
    fill_price = bindings.fill_price(
        float(order.get("_base_price", order.get("price", np.nan))), fill_side
    )
    qty = _entry_qty_for_max_position_size(
        side=side,
        previous_size=state.current_size,
        requested_qty=float(order.get("qty", 0.0)),
        max_position_size=bindings.configuration.max_position_size,
    )
    order["_requested_fill_qty"] = float(order.get("_original_qty", order.get("qty", 0.0)))
    if qty <= 0:
        order["_filled_qty"] = 0.0
        _reject_order(order, timestamp=timestamp, reason="max_position_size")
        return
    position_after, avg_after = _entry_position_after(
        previous_size=state.current_size,
        previous_avg=state.current_avg,
        side=side,
        qty=qty,
        price=fill_price,
    )
    pre_fill_equity = _strategy_equity(
        initial_capital=bindings.configuration.initial_capital,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        position_size=state.current_size,
        position_avg=state.current_avg,
        close_price=float(bindings.close[idx]),
    )
    if not bindings.margin_allows_position(
        previous_size=state.current_size,
        next_size=position_after,
        price=fill_price,
        equity=pre_fill_equity,
    ):
        order["_filled_qty"] = 0.0
        _reject_order(order, timestamp=timestamp, reason="margin")
        return
    if state.current_size == 0 or (state.current_size > 0) != (position_after > 0):
        state.same_direction_entry_count = 1
    else:
        state.same_direction_entry_count += 1
    previous_size = state.current_size
    state.current_size = position_after
    state.current_avg = avg_after
    order["qty"] = round(qty, 8)
    order["_filled_qty"] = round(qty, 8)
    order["price"] = round(float(fill_price), 8)
    order["position_after"] = round(float(position_after), 8)
    transaction_qty = abs(position_after - previous_size)
    if abs(transaction_qty - qty) > 1e-09:
        order["_transaction_qty"] = round(transaction_qty, 8)
    commission = bindings.apply_commission(order, qty=transaction_qty, price=fill_price)
    order["_fill_bar_index"] = idx
    state.gross_profit, state.gross_loss, state.total_commission, state.open_trades = _record_fill(
        order=order,
        signed_qty=position_after - previous_size,
        previous_size=previous_size,
        fill_price=fill_price,
        next_size=position_after,
        commission=commission,
        open_trades=state.open_trades,
        closed_trades=state.closed_trades,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        open_trade_events=state.open_trade_events,
    )
    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
    order["_active"] = True
    state.risk.intraday_filled_orders += 1
    if _intraday_filled_orders_hit(
        filled_orders=state.risk.intraday_filled_orders,
        threshold=bindings.configuration.max_intraday_filled_orders,
    ):
        state.risk.filled_orders_locked = True
        state.risk.risk_locked = True


def fill_market_order(
    bindings: ReplayBindings, state: ReplayState, order: Order, idx: int, timestamp: int
) -> None:
    side = _normalize_direction(str(order.get("side", bindings.long)))
    fill_side = "buy" if side == bindings.long else "sell"
    fill_price = bindings.fill_price(
        float(order.get("_base_price", order.get("price", np.nan))), fill_side
    )
    qty = float(order.get("qty", 0.0))
    order["_requested_fill_qty"] = float(order.get("_original_qty", qty))
    position_after, avg_after = _order_position_after(
        previous_size=state.current_size,
        previous_avg=state.current_avg,
        side=side,
        qty=qty,
        price=fill_price,
    )
    pre_fill_equity = _strategy_equity(
        initial_capital=bindings.configuration.initial_capital,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        position_size=state.current_size,
        position_avg=state.current_avg,
        close_price=float(bindings.close[idx]),
    )
    if not bindings.margin_allows_position(
        previous_size=state.current_size,
        next_size=position_after,
        price=fill_price,
        equity=pre_fill_equity,
    ):
        order["_filled_qty"] = 0.0
        _reject_order(order, timestamp=timestamp, reason="margin")
        return
    if position_after == 0:
        state.same_direction_entry_count = 0
    elif state.current_size == 0 or (state.current_size > 0) != (position_after > 0):
        state.same_direction_entry_count = 1
    previous_size = state.current_size
    state.current_size = position_after
    state.current_avg = avg_after
    order["price"] = round(float(fill_price), 8)
    order["_filled_qty"] = round(qty, 8)
    order["position_after"] = round(float(position_after), 8)
    commission = bindings.apply_commission(order, qty=qty, price=fill_price)
    signed_qty = qty if side == bindings.long else -qty
    order["_fill_bar_index"] = idx
    state.gross_profit, state.gross_loss, state.total_commission, state.open_trades = _record_fill(
        order=order,
        signed_qty=signed_qty,
        previous_size=previous_size,
        fill_price=fill_price,
        next_size=position_after,
        commission=commission,
        open_trades=state.open_trades,
        closed_trades=state.closed_trades,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        open_trade_events=state.open_trade_events,
    )
    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
    order["_active"] = True
    state.risk.intraday_filled_orders += 1
    if _intraday_filled_orders_hit(
        filled_orders=state.risk.intraday_filled_orders,
        threshold=bindings.configuration.max_intraday_filled_orders,
    ):
        state.risk.filled_orders_locked = True
        state.risk.risk_locked = True


def fill_close_order(bindings: ReplayBindings, state: ReplayState, order: Order, idx: int) -> bool:
    same_bar_visible_fill = False
    previous_size = state.current_size
    if order.get("type") == "exit":
        target_qty = _target_open_qty(order, state.open_trades, state.current_size)
        requested_qty = _requested_close_qty(
            target_qty=target_qty,
            qty=order.get("_requested_qty"),
            qty_percent=order.get("_qty_percent"),
        )
        fill_qty = min(requested_qty, target_qty)
    elif order.get("type") == "close":
        target_qty = _target_open_qty(order, state.open_trades, state.current_size)
        requested_qty = _requested_close_qty(
            target_qty=target_qty,
            qty=order.get("_requested_qty"),
            qty_percent=order.get("_qty_percent"),
        )
        fill_qty = min(target_qty, abs(state.current_size), requested_qty)
    else:
        target_qty = abs(state.current_size)
        requested_qty = target_qty
        fill_qty = abs(state.current_size)
    order["_target_qty"] = round(float(target_qty), 8)
    order["_requested_fill_qty"] = round(float(requested_qty), 8)
    if fill_qty <= 0:
        return False
    remaining = abs(state.current_size) - fill_qty
    next_size = 0.0
    if remaining > 0:
        next_size = remaining if state.current_size > 0 else -remaining
    fill_side = "sell" if state.current_size > 0 else "buy"
    fill_price = bindings.fill_price(
        float(order.get("_base_price", order.get("price", np.nan))), fill_side
    )
    order["qty"] = round(fill_qty, 8)
    order["_filled_qty"] = round(fill_qty, 8)
    order["price"] = round(float(fill_price), 8)
    order["position_after"] = round(next_size, 8)
    commission = bindings.apply_commission(order, qty=fill_qty, price=fill_price)
    signed_qty = -fill_qty if previous_size > 0 else fill_qty
    order["_fill_bar_index"] = idx
    state.gross_profit, state.gross_loss, state.total_commission, state.open_trades = _record_fill(
        order=order,
        signed_qty=signed_qty,
        previous_size=previous_size,
        fill_price=fill_price,
        next_size=next_size,
        commission=commission,
        open_trades=state.open_trades,
        closed_trades=state.closed_trades,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        open_trade_events=state.open_trade_events,
    )
    order["_active"] = True
    if next_size != 0:
        state.current_avg = _position_avg_from_open_trades(state.open_trades, next_size)
    if (
        order.get("type") == "exit"
        and bindings.configuration.process_orders_on_close
        and (not order.get("_process_on_close_new_exit"))
    ):
        same_bar_visible_fill = True
    if bindings.configuration.process_orders_on_close and order.get("_risk_liquidation"):
        same_bar_visible_fill = True
    state.current_size = next_size
    if state.current_size == 0:
        state.current_avg = np.nan
        state.same_direction_entry_count = 0
    return same_bar_visible_fill
