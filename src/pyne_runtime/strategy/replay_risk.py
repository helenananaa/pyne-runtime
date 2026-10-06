"""Session risk resets, liquidation, and end-of-bar equity locks."""

from __future__ import annotations
import numpy as np
from .ledger import _open_profit, _record_fill
from .risk import _intraday_filled_orders_hit, _max_drawdown_hit
from .replay_state import ReplayBindings, ReplayState


def start_bar_risk(bindings: ReplayBindings, state: ReplayState, idx: int) -> None:
    if bindings.session_first[idx]:
        state.risk.intraday_locked = False
        state.risk.intraday_filled_orders = 0
        state.risk.filled_orders_locked = _intraday_filled_orders_hit(
            filled_orders=state.risk.intraday_filled_orders,
            threshold=bindings.configuration.max_intraday_filled_orders,
        )
        state.risk.intraday_peak_equity = (
            float(bindings.output.equity[idx - 1])
            if idx > 0
            else bindings.configuration.initial_capital
        )
    state.risk.risk_locked = (
        state.risk.drawdown_locked or state.risk.intraday_locked or state.risk.filled_orders_locked
    )


def liquidate_bar_risk(
    bindings: ReplayBindings, state: ReplayState, idx: int, timestamp: int, bar_open_size: float
) -> bool:
    reason = _risk_liquidation_reason(bindings, state, idx, bar_open_size)
    if reason is None:
        return False
    state.risk.intraday_locked = True
    state.risk.risk_locked = True
    if state.current_size == 0:
        return False
    _force_close_for_risk(bindings, state, idx, timestamp, reason)
    state.same_direction_entry_count = 0
    return True


def finish_bar_risk(bindings: ReplayBindings, state: ReplayState, idx: int) -> None:
    net_profit = state.gross_profit + state.gross_loss - state.total_commission
    open_profit = _open_profit(state.current_size, state.current_avg, float(bindings.close[idx]))
    equity = bindings.configuration.initial_capital + net_profit + open_profit
    state.risk.peak_equity = max(state.risk.peak_equity, float(equity))
    state.risk.intraday_peak_equity = max(state.risk.intraday_peak_equity, float(equity))
    if bindings.configuration.max_drawdown_value is not None and _max_drawdown_hit(
        equity=float(equity),
        peak_equity=state.risk.peak_equity,
        threshold=bindings.configuration.max_drawdown_value,
        risk_type=bindings.configuration.max_drawdown_type,
    ):
        state.risk.drawdown_locked = True
    if bindings.configuration.max_intraday_loss_value is not None and _max_drawdown_hit(
        equity=float(equity),
        peak_equity=state.risk.intraday_peak_equity,
        threshold=bindings.configuration.max_intraday_loss_value,
        risk_type=bindings.configuration.max_intraday_loss_type,
    ):
        state.risk.intraday_locked = True
    state.risk.risk_locked = (
        state.risk.drawdown_locked or state.risk.intraday_locked or state.risk.filled_orders_locked
    )


def _risk_liquidation_reason(
    bindings: ReplayBindings, state: ReplayState, idx: int, bar_open_size: float
) -> str | None:
    if state.current_size == 0:
        return None
    if bindings.configuration.process_orders_on_close and bar_open_size == 0:
        risk_price = float(bindings.close[idx])
    else:
        risk_price = (
            float(bindings.low[idx]) if state.current_size > 0 else float(bindings.high[idx])
        )
    net_profit = state.gross_profit + state.gross_loss - state.total_commission
    equity = (
        bindings.configuration.initial_capital
        + net_profit
        + _open_profit(state.current_size, state.current_avg, risk_price)
    )
    if bindings.configuration.max_intraday_loss_value is not None and _max_drawdown_hit(
        equity=float(equity),
        peak_equity=state.risk.intraday_peak_equity,
        threshold=bindings.configuration.max_intraday_loss_value,
        risk_type=bindings.configuration.max_intraday_loss_type,
    ):
        return "risk.max_intraday_loss"
    return None


def _force_close_for_risk(
    bindings: ReplayBindings, state: ReplayState, idx: int, timestamp: int, reason: str
) -> None:
    fill_qty = abs(state.current_size)
    fill_side = "sell" if state.current_size > 0 else "buy"
    risk_price = float(bindings.low[idx]) if state.current_size > 0 else float(bindings.high[idx])
    fill_price = bindings.fill_price(risk_price, fill_side)
    order = {
        "time": timestamp,
        "id": reason,
        "type": "close_all",
        "side": "flat",
        "qty": round(fill_qty, 8),
        "price": round(float(fill_price), 8),
        "position_after": 0.0,
        "comment": "",
        "_active": True,
        "_filled_qty": round(fill_qty, 8),
        "_requested_fill_qty": round(fill_qty, 8),
        "_target_qty": round(fill_qty, 8),
        "_risk_liquidation": True,
        "_submit_time": timestamp,
        "_seq": bindings.next_event_seq(),
    }
    bindings.orders.append(order)
    commission = bindings.apply_commission(order, qty=fill_qty, price=fill_price)
    signed_qty = -fill_qty if state.current_size > 0 else fill_qty
    order["_fill_bar_index"] = idx
    state.gross_profit, state.gross_loss, state.total_commission, state.open_trades = _record_fill(
        order=order,
        signed_qty=signed_qty,
        previous_size=state.current_size,
        fill_price=fill_price,
        next_size=0.0,
        commission=commission,
        open_trades=state.open_trades,
        closed_trades=state.closed_trades,
        gross_profit=state.gross_profit,
        gross_loss=state.gross_loss,
        total_commission=state.total_commission,
        open_trade_events=state.open_trade_events,
    )
    state.current_size = 0.0
    state.current_avg = np.nan
