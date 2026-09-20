"""Incremental bar model and bar metadata helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
from typing import Any

from ..data import PyneData
from ..metadata import SessionInfo, normalize_session_info


def copy_bar_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy canonical scalar bars cheaply, retaining deepcopy for custom data."""
    if type(raw) is dict and all(type(key) is str and type(value) in (int, float, str, bool, type(None))
                                 for key, value in raw.items()):
        return raw.copy()
    return copy.deepcopy(raw)


@dataclass
class IncrementalBar:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_confirmed: bool = True
    bar_index: int = -1
    last_bar_index: int = -1
    is_first: bool = False
    is_last: bool = False
    is_history: bool = False
    is_realtime: bool = False
    is_new: bool = False
    is_last_confirmed_history: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, item: dict[str, Any], *, is_confirmed: bool = True) -> "IncrementalBar":
        normalized = PyneData.from_ohlcv([item]).first
        raw = {**item, **normalized}
        return cls(
            time=int(normalized["time"]),
            open=float(normalized["open"]),
            high=float(normalized["high"]),
            low=float(normalized["low"]),
            close=float(normalized["close"]),
            volume=float(normalized["volume"]),
            is_confirmed=is_confirmed,
            raw=raw,
        )

def _session_info_for_bar(bar: IncrementalBar, default: SessionInfo) -> SessionInfo:
    raw = dict(bar.raw or {})
    nested = raw.get("session")
    if isinstance(nested, dict):
        raw.update(nested)
    return normalize_session_info({
        "ismarket": _first_present(
            raw,
            ("session_ismarket", "ismarket", "is_market"),
            default.ismarket,
        ),
        "isfirstbar": _first_present(
            raw,
            ("session_isfirstbar", "isfirstbar", "is_firstbar", "session_is_first_bar"),
            default.isfirstbar or bar.is_first,
        ),
        "islastbar": _first_present(
            raw,
            ("session_islastbar", "islastbar", "is_lastbar", "session_is_last_bar"),
            default.islastbar or bar.is_last,
        ),
    })

def _first_present(raw: dict[str, Any], names: tuple[str, ...], default: bool) -> bool:
    for name in names:
        if name in raw:
            return bool(raw[name])
    return bool(default)
