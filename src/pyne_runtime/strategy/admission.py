"""Numeric admission shared by batch and incremental strategy commands."""
from __future__ import annotations

import math
from typing import Any

from ..values import is_na_value


def finite_number(name: str, value: Any) -> float:
    """Convert a required number before changing strategy state."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"strategy {name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"strategy {name} must be a finite number")
    return number


def optional_number(name: str, value: Any) -> float | None:
    """None and actual Pyne missing values mean an omitted optional argument."""
    return None if is_na_value(value) else finite_number(name, value)


def nonnegative_number(name: str, value: Any) -> float:
    return max(finite_number(name, value), 0.0)


def nonnegative_integer(name: str, value: Any) -> int:
    finite_number(name, value)
    return max(int(value), 0)
