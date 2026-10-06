"""Normalize a complete strategy settings update before applying any field."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, cast

from .admission import nonnegative_integer, nonnegative_number
from .costs import _normalize_commission_type
from .orders import _normalize_intrabar_path, _normalize_same_bar_fill_priority


class StrategySettingsUpdate(TypedDict, total=False):
    _pyramiding: int
    _slippage_ticks: int
    _mintick: float
    _commission_type: str
    _commission_value: float
    _initial_capital: float
    _currency: str
    _backtest_fill_limits_assumption: int
    _process_orders_on_close: bool
    _same_bar_fill_priority: str
    _intrabar_path: str
    _margin_long: float
    _margin_short: float
    _allow_entry_in: str
    _max_drawdown_value: float
    _max_drawdown_type: str
    _max_intraday_loss_value: float
    _max_intraday_loss_type: str
    _max_position_size: float
    _max_intraday_filled_orders: int


class StrategySettingsTarget(Protocol):
    def _update_strategy_settings(self, updates: StrategySettingsUpdate) -> None: ...


class StrategyReplaySettingsSource(Protocol):
    _initial_capital: float
    _pyramiding: int
    _process_orders_on_close: bool
    _allow_entry_in: str
    _max_drawdown_value: float | None
    _max_drawdown_type: str
    _max_intraday_loss_value: float | None
    _max_intraday_loss_type: str
    _max_intraday_filled_orders: int | None
    _max_position_size: float | None
    _same_bar_fill_priority: str
    _intrabar_path: str


@dataclass(frozen=True)
class StrategyReplayConfiguration:
    """One consistent settings view for a complete historical replay."""

    initial_capital: float
    pyramiding: int
    process_orders_on_close: bool
    allow_entry_in: str
    max_drawdown_value: float | None
    max_drawdown_type: str
    max_intraday_loss_value: float | None
    max_intraday_loss_type: str
    max_intraday_filled_orders: int | None
    max_position_size: float | None
    same_bar_fill_priority: str
    intrabar_path: str

    @classmethod
    def capture(cls, source: StrategyReplaySettingsSource) -> StrategyReplayConfiguration:
        return cls(
            initial_capital=source._initial_capital, pyramiding=source._pyramiding,
            process_orders_on_close=source._process_orders_on_close,
            allow_entry_in=source._allow_entry_in,
            max_drawdown_value=source._max_drawdown_value,
            max_drawdown_type=source._max_drawdown_type,
            max_intraday_loss_value=source._max_intraday_loss_value,
            max_intraday_loss_type=source._max_intraday_loss_type,
            max_intraday_filled_orders=source._max_intraday_filled_orders,
            max_position_size=source._max_position_size,
            same_bar_fill_priority=source._same_bar_fill_priority,
            intrabar_path=source._intrabar_path,
        )


def normalize_strategy_configuration(options: Mapping[str, Any]) -> StrategySettingsUpdate:
    """Return detached, validated updates; None leaves an existing setting alone."""
    updates: dict[str, Any] = {}
    for name, attribute in (
        ("pyramiding", "_pyramiding"),
        ("slippage", "_slippage_ticks"),
        ("backtest_fill_limits_assumption", "_backtest_fill_limits_assumption"),
    ):
        if options.get(name) is not None:
            updates[attribute] = nonnegative_integer(name, options[name])
    for name in ("commission_value", "initial_capital", "margin_long", "margin_short"):
        if options.get(name) is not None:
            updates["_" + name] = nonnegative_number(name, options[name])
    tick = options.get("mintick")
    if tick is None:
        tick = options.get("min_tick")
    if tick is not None:
        updates["_mintick"] = nonnegative_number("mintick", tick)
    if options.get("commission_type") is not None:
        updates["_commission_type"] = _normalize_commission_type(options["commission_type"])
    if options.get("currency") is not None:
        updates["_currency"] = str(options["currency"])
    if options.get("process_orders_on_close") is not None:
        updates["_process_orders_on_close"] = bool(options["process_orders_on_close"])
    if options.get("same_bar_fill_priority") is not None:
        updates["_same_bar_fill_priority"] = _normalize_same_bar_fill_priority(
            options["same_bar_fill_priority"]
        )
    if options.get("intrabar_path") is not None:
        updates["_intrabar_path"] = _normalize_intrabar_path(options["intrabar_path"])
    return cast(StrategySettingsUpdate, updates)
