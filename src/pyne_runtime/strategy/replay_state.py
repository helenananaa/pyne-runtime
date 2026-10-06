"""Transient replay state and the boundary to the strategy owner.

These objects exist only during one historical replay. They are never retained
by a strategy or serialized into a checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
import numpy as np

from ..security import PyneResourceLimitError
from .configuration import StrategyReplayConfiguration
from .orders import _PendingOrderBook
from .risk import _intraday_filled_orders_hit
from .replay_values import _condition_values

Order = dict[str, Any]
TradeEvent = tuple[str, int, Order | None]
MaterializeOrder = Callable[[int, int, float], Order | None]


@dataclass
class ReplayRiskState:
    drawdown_locked: bool = False
    intraday_locked: bool = False
    filled_orders_locked: bool = False
    risk_locked: bool = False
    peak_equity: float = 0.0
    intraday_peak_equity: float = 0.0
    intraday_filled_orders: int = 0


@dataclass
class ReplayState:
    current_size: float = 0.0
    current_avg: float = np.nan
    same_direction_entry_count: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    total_commission: float = 0.0
    closed_trades: list[Order] = field(default_factory=list)
    open_trades: list[Order] = field(default_factory=list)
    open_trade_events: list[TradeEvent] | None = None
    risk: ReplayRiskState = field(default_factory=ReplayRiskState)

    @classmethod
    def create(cls, settings: StrategyReplayConfiguration) -> ReplayState:
        return cls(
            open_trade_events=[] if settings.process_orders_on_close else None,
            risk=ReplayRiskState(
                peak_equity=settings.initial_capital,
                intraday_peak_equity=settings.initial_capital,
                filled_orders_locked=_intraday_filled_orders_hit(
                    filled_orders=0, threshold=settings.max_intraday_filled_orders
                ),
            ),
        )


class CommissionCalculator(Protocol):
    def __call__(self, order: Order, *, qty: float, price: float) -> float: ...


class MarginAdmission(Protocol):
    def __call__(
        self, *, previous_size: float, next_size: float, price: float, equity: float
    ) -> bool: ...


class ReplayOutputPort(Protocol):
    equity: np.ndarray

    def write(self, idx: int, state: ReplayState) -> None: ...
    def publish(self, state: ReplayState) -> None: ...


@dataclass(frozen=True)
class ReplayBindings:
    configuration: StrategyReplayConfiguration
    times: list[int]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    session_first: list[bool]
    orders: list[Order]
    source_orders: list[Order]
    pending_orders: _PendingOrderBook
    long: str
    fill_price: Callable[[float, str], float]
    apply_commission: CommissionCalculator
    margin_allows_position: MarginAdmission
    limit_fill_verification_amount: Callable[[], float]
    consume_operations: Callable[..., None]
    next_event_seq: Callable[[], int]
    output: ReplayOutputPort


def _consume_pending_order_operations(strategy: Any, count: int = 1) -> None:
    strategy._pending_order_operations += max(int(count), 0)
    if (
        strategy._max_pending_order_operations is not None
        and strategy._pending_order_operations > strategy._max_pending_order_operations
    ):
        raise PyneResourceLimitError(
            "Strategy pending-order operation budget exceeded "
            f"(max {strategy._max_pending_order_operations})"
        )


def initialize_replay(strategy: Any) -> tuple[ReplayBindings, ReplayState]:
    from .replay_events import collect_source_orders
    from .replay_output import capture_replay_output

    settings = StrategyReplayConfiguration.capture(strategy)
    context = strategy._context

    def consume(count: int = 1) -> None:
        _consume_pending_order_operations(strategy, count)

    # Keep the original exception boundary: discard derived source orders,
    # initialize the pending book, reset output history, then read session flags.
    orders = strategy._collector.strategy_orders
    source_orders = collect_source_orders(orders)
    pending_orders = _PendingOrderBook(
        tick_verify=strategy._limit_fill_verification_amount(), consume_operations=consume
    )
    state = ReplayState.create(settings)
    output = capture_replay_output(strategy, settings)
    session_first = _condition_values(context.session.isfirstbar, context.bar_count)
    bindings = ReplayBindings(
        configuration=settings,
        times=context.times,
        open=context.open.values,
        high=context.high.values,
        low=context.low.values,
        close=context.close.values,
        session_first=session_first,
        orders=orders,
        source_orders=source_orders,
        pending_orders=pending_orders,
        long=strategy.long,
        fill_price=strategy._fill_price,
        apply_commission=strategy._apply_commission,
        margin_allows_position=strategy._margin_allows_position,
        limit_fill_verification_amount=strategy._limit_fill_verification_amount,
        consume_operations=consume,
        next_event_seq=strategy._next_event_seq,
        output=output,
    )
    return bindings, state
