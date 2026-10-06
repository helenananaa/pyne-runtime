"""Vector admission and position arithmetic shared by replay commands."""

from __future__ import annotations
from typing import Any
import numpy as np
from ..series import PyneSeries
from ..state import PyneVar
from ..values import is_na_value
from .admission import optional_number


def _condition_values(value: Any, length: int) -> list[bool]:
    values = _values(value, length)
    return [False if is_na_value(item) else bool(item) for item in values]


def _price_values(value: Any, fallback: PyneSeries, length: int) -> list[float]:
    values = _values(fallback if value is None else value, length)
    return [
        np.nan if (number := optional_number("price", item)) is None else number for item in values
    ]


def _optional_price_values(value: Any, length: int) -> list[float | None]:
    if value is None:
        return [None] * length
    values = _values(value, length)
    return [optional_number("limit/stop", item) for item in values]


def _optional_numeric_values(value: Any, length: int) -> list[float | None]:
    if value is None:
        return [None] * length
    values = _values(value, length)
    return [optional_number("qty/qty_percent", item) for item in values]


def _requested_close_qty(
    *,
    target_qty: float,
    qty: Any,
    qty_percent: Any,
) -> float:
    target = max(float(target_qty), 0.0)
    if qty is not None and not is_na_value(qty):
        return max(float(qty), 0.0)
    if qty_percent is not None and not is_na_value(qty_percent):
        return target * max(float(qty_percent), 0.0) / 100.0
    return target


def _entry_position_after(
    *,
    previous_size: float,
    previous_avg: float,
    side: str,
    qty: float,
    price: float,
) -> tuple[float, float]:
    signed_qty = qty if side == "long" else -qty
    if previous_size == 0 or (previous_size > 0) != (signed_qty > 0):
        return signed_qty, float(price)

    new_size = previous_size + signed_qty
    if new_size == 0:
        return 0.0, np.nan
    if is_na_value(previous_avg):
        return new_size, float(price)
    weighted = (abs(previous_size) * previous_avg + qty * float(price)) / abs(new_size)
    return new_size, weighted


def _order_position_after(
    *,
    previous_size: float,
    previous_avg: float,
    side: str,
    qty: float,
    price: float,
) -> tuple[float, float]:
    signed_qty = qty if side == "long" else -qty
    new_size = previous_size + signed_qty
    if new_size == 0:
        return 0.0, np.nan
    if previous_size == 0 or (previous_size > 0) != (new_size > 0):
        return new_size, float(price)
    if (previous_size > 0) != (signed_qty > 0):
        return new_size, previous_avg
    if is_na_value(previous_avg):
        return new_size, float(price)
    weighted = (abs(previous_size) * previous_avg + qty * float(price)) / abs(new_size)
    return new_size, weighted


def _position_avg_from_open_trades(
    open_trades: list[dict[str, Any]],
    current_size: float,
) -> float:
    if current_size == 0:
        return np.nan
    side = "long" if current_size > 0 else "short"
    total_qty = 0.0
    weighted = 0.0
    for trade in open_trades:
        if trade.get("side") != side:
            continue
        qty = abs(float(trade.get("qty", 0.0)))
        if qty <= 0:
            continue
        total_qty += qty
        weighted += qty * float(trade.get("entry_price", np.nan))
    if total_qty <= 0:
        return np.nan
    return weighted / total_qty


def _values(value: Any, length: int) -> list[Any]:
    if isinstance(value, PyneVar):
        value = value.get()
    if isinstance(value, PyneSeries):
        return value.to_numpy().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, list):
        if len(value) == length:
            return value
        if len(value) == 1:
            return value * length
        raise ValueError("strategy series inputs must match the OHLCV length")
    return [value] * length


def _normalize_direction(direction: str) -> str:
    normalized = str(direction or "long").lower()
    if normalized in {"short", "-1", "sell"}:
        return "short"
    if normalized in {"long", "1", "buy"}:
        return "long"
    raise ValueError("strategy direction must be strategy.long or strategy.short")
