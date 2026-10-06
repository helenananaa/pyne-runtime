"""Publication of historical strategy arrays and trade-event visibility."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
import numpy as np
from .configuration import StrategyReplayConfiguration
from .ledger import _open_profit
from .replay_state import ReplayState, TradeEvent


@dataclass(frozen=True)
class ReplayOutput:
    position_size: np.ndarray
    position_avg_price: np.ndarray
    grossprofit: np.ndarray
    grossloss: np.ndarray
    netprofit: np.ndarray
    openprofit: np.ndarray
    equity: np.ndarray
    closedtrades_count: np.ndarray
    opentrades_count: np.ndarray
    close: np.ndarray
    initial_capital: float
    process_orders_on_close: bool
    open_trade_events_by_bar: list[list[TradeEvent]]
    publish_report: Callable[[ReplayState], None]

    def write(self, idx: int, state: ReplayState) -> None:
        net_profit = state.gross_profit + state.gross_loss - state.total_commission
        open_profit = _open_profit(state.current_size, state.current_avg, float(self.close[idx]))
        self.position_size[idx] = state.current_size
        self.position_avg_price[idx] = state.current_avg
        self.grossprofit[idx] = state.gross_profit
        self.grossloss[idx] = state.gross_loss
        self.netprofit[idx] = net_profit
        self.openprofit[idx] = open_profit
        self.equity[idx] = self.initial_capital + net_profit + open_profit
        self.closedtrades_count[idx] = len(state.closed_trades)
        self.opentrades_count[idx] = len(state.open_trades)
        if self.process_orders_on_close and state.open_trade_events:
            self.open_trade_events_by_bar[idx].extend(state.open_trade_events)
            state.open_trade_events.clear()

    def publish(self, state: ReplayState) -> None:
        self.publish_report(state)


def capture_replay_output(strategy: Any, settings: StrategyReplayConfiguration) -> ReplayOutput:
    strategy._closed_trades_by_bar = []
    strategy._open_trades_by_bar = []
    strategy._open_trade_events_by_bar = (
        [[] for _ in range(strategy._context.bar_count)] if settings.process_orders_on_close else []
    )

    def publish(state: ReplayState) -> None:
        strategy._risk_locked = state.risk.risk_locked
        strategy._sync_strategy_report(
            closed_trades=state.closed_trades,
            open_trades=state.open_trades,
            gross_profit=state.gross_profit,
            gross_loss=state.gross_loss,
            total_commission=state.total_commission,
        )

    return ReplayOutput(
        position_size=strategy._position_size,
        position_avg_price=strategy._position_avg_price,
        grossprofit=strategy._grossprofit,
        grossloss=strategy._grossloss,
        netprofit=strategy._netprofit,
        openprofit=strategy._openprofit,
        equity=strategy._equity,
        closedtrades_count=strategy._closedtrades_count,
        opentrades_count=strategy._opentrades_count,
        close=strategy._context.close.values,
        initial_capital=settings.initial_capital,
        process_orders_on_close=settings.process_orders_on_close,
        open_trade_events_by_bar=strategy._open_trade_events_by_bar,
        publish_report=publish,
    )
