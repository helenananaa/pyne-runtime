"""Pine-like runtime metadata namespaces."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, tzinfo
from typing import Any, Mapping

import numpy as np

from .series import PyneSeries
from .timezone_ext import parse_timezone


def _timeframe_fields(period: Any) -> tuple[str, int, str, bool, bool, bool, bool]:
    """Parse one timeframe into its canonical public fields."""
    raw = str(period or "1").strip() or "1"
    match = re.fullmatch(r"(\d+)?([A-Za-z]?)", raw)
    if match is None:
        raise ValueError(f"invalid timeframe: {period!r}")

    number_text, suffix = match.groups()
    amount = int(number_text) if number_text else 1
    if amount < 1:
        raise ValueError(f"timeframe multiplier must be >= 1, got {amount}")

    if not suffix or suffix == "m":
        return raw, amount, "", True, False, False, False
    if suffix in {"s", "S"}:
        return raw, amount, "S", True, False, False, False
    if suffix in {"h", "H"}:
        return raw, amount * 60, "", True, False, False, False
    if suffix in {"d", "D"}:
        return raw, amount, "D", False, True, False, False
    if suffix in {"w", "W"}:
        return raw, amount, "W", False, False, True, False
    if suffix == "M":
        return raw, amount, "M", False, False, False, True
    if suffix in {"t", "T"}:
        return raw, amount, "T", True, False, False, False
    raise ValueError(f"invalid timeframe: {period!r}")


def _explicit_timeframe_multiplier(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"timeframe multiplier must be an integer, got {value!r}")
    if isinstance(value, (int, np.integer)):
        explicit = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[+]?[0-9]+", value.strip()):
        explicit = int(value.strip())
    else:
        raise ValueError(f"timeframe multiplier must be an integer, got {value!r}")
    if explicit < 1:
        raise ValueError(f"timeframe multiplier must be >= 1, got {explicit}")
    return explicit


@dataclass(frozen=True)
class SymbolInfo:
    """Symbol metadata exposed as the Pine-like ``syminfo`` namespace."""

    ticker: str = ""
    tickerid: str = ""
    prefix: str = ""
    currency: str = ""
    basecurrency: str = ""
    mintick: float = 1.0
    pointvalue: float = 1.0
    type: str = ""
    timezone: str = ""
    volumetype: str = ""

    @classmethod
    def from_value(cls, value: Any = None) -> "SymbolInfo":
        if isinstance(value, SymbolInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, str):
            return _symbol_from_mapping({"tickerid": value})
        if isinstance(value, Mapping):
            return _symbol_from_mapping(value)
        return cls()


@dataclass(frozen=True)
class TimeframeInfo:
    """Chart timeframe metadata exposed as ``timeframe``."""

    period: str = "1"
    multiplier: int | None = None
    unit: str = ""
    isintraday: bool = True
    isdaily: bool = False
    isweekly: bool = False
    ismonthly: bool = False
    _times: tuple[int, ...] = field(default=(), repr=False, compare=False)
    _timezone: str = field(default="UTC", repr=False, compare=False)

    def __post_init__(self) -> None:
        (
            period,
            expected_multiplier,
            unit,
            isintraday,
            isdaily,
            isweekly,
            ismonthly,
        ) = _timeframe_fields(self.period)
        multiplier = (
            expected_multiplier
            if self.multiplier is None
            else _explicit_timeframe_multiplier(self.multiplier)
        )
        if multiplier != expected_multiplier:
            raise ValueError(
                f"timeframe period {period!r} conflicts with multiplier {multiplier}"
            )
        object.__setattr__(self, "period", period)
        object.__setattr__(self, "multiplier", multiplier)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "isintraday", isintraday)
        object.__setattr__(self, "isdaily", isdaily)
        object.__setattr__(self, "isweekly", isweekly)
        object.__setattr__(self, "ismonthly", ismonthly)

    @property
    def isseconds(self) -> bool:
        return self.unit == "S"

    @property
    def isminutes(self) -> bool:
        return self.unit == ""

    @property
    def isdwm(self) -> bool:
        return self.isdaily or self.isweekly or self.ismonthly

    @property
    def isticks(self) -> bool:
        return self.unit == "T"

    def in_seconds(self, timeframe: str | TimeframeInfo | None = None) -> float:
        """Convert a Pine-style timeframe string to deterministic seconds.

        Month values use TradingView's conventional 30-day conversion for
        timeframe comparison. Tick timeframes do not have a seconds duration.
        """
        info = self if timeframe in {None, ""} else TimeframeInfo.from_value(timeframe)
        seconds = _duration_seconds(info.multiplier, info.unit)
        if seconds is None:
            raise ValueError(f"timeframe {info.period!r} cannot be represented in seconds")
        return float(seconds)

    def from_seconds(self, seconds: int | float) -> str:
        """Return the next valid Pine timeframe at or above ``seconds``."""
        return _timeframe_from_seconds(seconds)

    def change(self, timeframe: str | TimeframeInfo | None = None) -> PyneSeries:
        """Mark the first available bar and each subsequent timeframe boundary.

        Calendar boundaries use ``syminfo.timezone`` when the host supplies it;
        otherwise they use UTC, which matches a typical 24/7 market timeline.
        """
        if not self._times:
            raise RuntimeError("timeframe.change() requires a Pyne runtime context")
        info = self if timeframe in {None, ""} else TimeframeInfo.from_value(timeframe)
        keys = [_timeframe_bucket(value, info, self._timezone) for value in self._times]
        changed = np.ones(len(keys), dtype=bool)
        if len(keys) > 1:
            changed[1:] = np.asarray(keys[1:]) != np.asarray(keys[:-1])
        return PyneSeries(changed, name=f"timeframe.change({info.period})")

    def bind(self, times: list[int], timezone: str = "") -> TimeframeInfo:
        """Bind immutable chart metadata to one execution's bar timeline."""
        return replace(
            self,
            _times=tuple(int(value) for value in times),
            _timezone=str(timezone or "UTC"),
        )

    @classmethod
    def from_value(cls, value: Any = None) -> "TimeframeInfo":
        if isinstance(value, TimeframeInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, Mapping):
            period_text = value.get("period") or value.get("timeframe")
            period_provided = period_text is not None and str(period_text).strip() != ""
            period = str(period_text).strip() if period_provided else "1"
            parsed = _parse_timeframe(period)
            multiplier = value.get("multiplier")
            if multiplier is None:
                return parsed
            explicit = _explicit_timeframe_multiplier(multiplier)
            if period_provided and explicit != parsed.multiplier:
                raise ValueError(
                    f"timeframe period {period!r} conflicts with multiplier {explicit}"
                )
            return cls(
                period=str(explicit) if parsed.unit == "" else parsed.period,
                multiplier=explicit,
                unit=parsed.unit,
                isintraday=parsed.isintraday,
                isdaily=parsed.isdaily,
                isweekly=parsed.isweekly,
                ismonthly=parsed.ismonthly,
            )
        return _parse_timeframe(str(value).strip() or "1")


@dataclass(frozen=True)
class SessionInfo:
    """Lightweight session metadata exposed as ``session``."""

    ismarket: bool = True
    isfirstbar: bool = False
    islastbar: bool = False

    @classmethod
    def from_value(cls, value: Any = None) -> "SessionInfo":
        if isinstance(value, SessionInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, bool):
            return cls(ismarket=value)
        if isinstance(value, Mapping):
            return cls(
                ismarket=bool(value.get("ismarket", True)),
                isfirstbar=bool(value.get("isfirstbar", False)),
                islastbar=bool(value.get("islastbar", False)),
            )
        return cls()


@dataclass(frozen=True)
class SessionNamespace:
    """Bar-level Pine-like ``session`` namespace exposed to batch scripts."""

    ismarket: PyneSeries
    isfirstbar: PyneSeries
    islastbar: PyneSeries


def normalize_symbol_info(value: Any = None) -> SymbolInfo:
    return SymbolInfo.from_value(value)


def normalize_timeframe_info(value: Any = None) -> TimeframeInfo:
    return TimeframeInfo.from_value(value)


def normalize_session_info(value: Any = None) -> SessionInfo:
    return SessionInfo.from_value(value)


def build_session_namespace(
    ohlcv: list[dict[str, Any]],
    session: Any = None,
) -> SessionNamespace:
    info = normalize_session_info(session)
    bar_count = len(ohlcv)
    market_values = _session_flag_values(
        ohlcv,
        names=("session_ismarket", "ismarket", "is_market"),
        default=info.ismarket,
    )
    first_values = _session_flag_values(
        ohlcv,
        names=("session_isfirstbar", "isfirstbar", "is_firstbar", "session_is_first_bar"),
        default=info.isfirstbar,
    )
    first_explicit = _has_session_flag(
        ohlcv,
        names=("session_isfirstbar", "isfirstbar", "is_firstbar", "session_is_first_bar"),
    )
    last_values = _session_flag_values(
        ohlcv,
        names=("session_islastbar", "islastbar", "is_lastbar", "session_is_last_bar"),
        default=info.islastbar,
    )
    last_explicit = _has_session_flag(
        ohlcv,
        names=("session_islastbar", "islastbar", "is_lastbar", "session_is_last_bar"),
    )

    if not first_explicit and not any(first_values) and bar_count:
        first_values[0] = True
    if not last_explicit and not any(last_values) and bar_count:
        last_values[-1] = True

    return SessionNamespace(
        ismarket=PyneSeries(np.array(market_values, dtype=bool), name="session.ismarket"),
        isfirstbar=PyneSeries(np.array(first_values, dtype=bool), name="session.isfirstbar"),
        islastbar=PyneSeries(np.array(last_values, dtype=bool), name="session.islastbar"),
    )


def _symbol_from_mapping(value: Mapping[str, Any]) -> SymbolInfo:
    tickerid = str(value.get("tickerid") or value.get("symbol") or "").strip()
    ticker = str(value.get("ticker") or "").strip()
    prefix = str(value.get("prefix") or "").strip()

    if tickerid and ":" in tickerid:
        inferred_prefix, inferred_ticker = tickerid.split(":", 1)
        prefix = prefix or inferred_prefix
        ticker = ticker or inferred_ticker
    elif tickerid:
        ticker = ticker or tickerid
    elif ticker:
        tickerid = ticker

    return SymbolInfo(
        ticker=ticker,
        tickerid=tickerid,
        prefix=prefix,
        currency=str(value.get("currency") or "").strip(),
        basecurrency=str(value.get("basecurrency") or value.get("base_currency") or "").strip(),
        mintick=_positive_float(value.get("mintick", value.get("min_tick", 1.0)), 1.0),
        pointvalue=_positive_float(value.get("pointvalue", value.get("point_value", 1.0)), 1.0),
        type=str(value.get("type") or "").strip(),
        timezone=str(value.get("timezone") or "").strip(),
        volumetype=str(value.get("volumetype") or value.get("volume_type") or "").strip(),
    )


def _positive_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return number


def _session_flag_values(
    ohlcv: list[dict[str, Any]],
    *,
    names: tuple[str, ...],
    default: bool,
) -> list[bool]:
    values: list[bool] = []
    for item in ohlcv:
        flag_value = _lookup_session_flag(item, names)
        values.append(default if flag_value is None else bool(flag_value))
    return values


def _lookup_session_flag(item: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    nested = item.get("session")
    if isinstance(nested, Mapping):
        for name in names:
            if name in nested:
                return nested[name]
    for name in names:
        if name in item:
            return item[name]
    return None


def _has_session_flag(ohlcv: list[dict[str, Any]], *, names: tuple[str, ...]) -> bool:
    return any(_lookup_session_flag(item, names) is not None for item in ohlcv)


def _parse_timeframe(period: str) -> TimeframeInfo:
    raw, multiplier, unit, isintraday, isdaily, isweekly, ismonthly = _timeframe_fields(
        period
    )
    return TimeframeInfo(
        period=raw,
        multiplier=multiplier,
        unit=unit,
        isintraday=isintraday,
        isdaily=isdaily,
        isweekly=isweekly,
        ismonthly=ismonthly,
    )


def _duration_seconds(multiplier: int, unit: str) -> int | None:
    amount = max(int(multiplier), 1)
    if unit in {"", "m"}:
        return amount * 60
    if unit == "S":
        return amount
    if unit == "D":
        return amount * 24 * 60 * 60
    if unit == "W":
        return amount * 7 * 24 * 60 * 60
    if unit == "M":
        return amount * 30 * 24 * 60 * 60
    return None


def _timeframe_seconds(period: str) -> int | None:
    try:
        info = _parse_timeframe(str(period or "1").strip() or "1")
    except ValueError:
        return None
    return _duration_seconds(info.multiplier, info.unit)


def _timeframe_from_seconds(seconds: int | float) -> str:
    try:
        requested = max(int(float(seconds)), 1)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"invalid timeframe seconds: {seconds!r}") from None

    candidates: list[tuple[int, int, str]] = []
    for amount in (1, 5, 10, 15, 30, 45):
        candidates.append((amount, 0, f"{amount}S"))
    for amount in range(1, 1441):
        candidates.append((amount * 60, 1, str(amount)))
    for amount in range(1, 366):
        candidates.append((amount * 86_400, 2, f"{amount}D"))
    for amount in range(1, 53):
        candidates.append((amount * 604_800, 3, f"{amount}W"))
    # TradingView's from_seconds conversion treats a month as 30.5 days.
    for amount in range(1, 13):
        candidates.append((amount * 2_635_200, 4, f"{amount}M"))

    durations = sorted({duration for duration, _, _ in candidates})
    for duration in durations:
        if duration < requested:
            continue
        matches = [item for item in candidates if item[0] == duration]
        if requested == duration:
            return max(matches, key=lambda item: item[1])[2]
        return min(matches, key=lambda item: item[1])[2]
    return "12M"


def _timeframe_bucket(timestamp: int, timeframe: TimeframeInfo, timezone_name: str) -> int:
    if timeframe.isticks:
        raise ValueError("tick timeframes do not have calendar boundaries")
    local = datetime.fromtimestamp(_timestamp_seconds(timestamp), tz=_timezone(timezone_name))
    amount = max(int(timeframe.multiplier), 1)
    if timeframe.unit == "M":
        return (local.year * 12 + local.month - 1) // amount
    if timeframe.unit == "W":
        return (local.date().toordinal() - 1) // (7 * amount)
    if timeframe.unit == "D":
        return (local.date().toordinal() - 1) // amount

    seconds = (
        (local.date().toordinal() - 1) * 86_400
        + local.hour * 3_600
        + local.minute * 60
        + local.second
    )
    duration = amount if timeframe.unit == "S" else amount * 60
    return seconds // duration


def _timestamp_seconds(value: int | float) -> float:
    timestamp = float(value)
    return timestamp / 1000.0 if abs(timestamp) > 100_000_000_000 else timestamp


def _timezone(name: str) -> tzinfo:
    return parse_timezone(name)
