"""Runtime settings for standalone Pyne execution."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from .metadata import normalize_session_info, normalize_symbol_info, normalize_timeframe_info

if TYPE_CHECKING:
    from .request.provider import DataProvider


SECURITY_MODES = {"safe", "research", "unsafe"}
EXECUTOR_MODES = {"inline", "process"}
DEFAULT_ALLOWED_IMPORTS = (
    "math", "statistics", "decimal", "fractions", "itertools", "functools",
    "collections", "bisect", "heapq", "operator",
    "numpy", "pandas", "scipy", "sklearn", "torch",
)
DEFAULT_TRACE_REDACTED_FIELDS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)


OPTIONAL_BUDGET_FIELDS = (
    "max_bars",
    "max_output_series",
    "max_output_points",
    "max_drawing_objects",
    "max_array_size",
    "max_map_size",
    "max_matrix_cells",
    "max_collection_depth",
    "max_strategy_pending_operations",
    "max_window_size",
    "max_total_window_items",
    "max_state_keys",
    "max_object_events",
    "max_strategy_log_entries",
    "max_state_payload_items",
    "max_preview_payload_items",
    "max_table_cells",
    "incremental_retention_bars",
    "replay_history_bars",
)


@dataclass(frozen=True)
class PyneSettings:
    """Configuration for a Pyne runtime or executor."""

    security_mode: str = "unsafe"
    executor_mode: str = "inline"
    timeout_seconds: float | None = None
    require_hard_timeout: bool = False
    process_grace_seconds: float = 0.5
    max_bars: int | None = None
    max_output_series: int | None = None
    max_output_points: int | None = None
    max_drawing_objects: int | None = None
    max_array_size: int | None = None
    max_map_size: int | None = None
    max_matrix_cells: int | None = None
    max_collection_depth: int | None = None
    max_strategy_pending_operations: int | None = None
    max_window_size: int | None = None
    max_total_window_items: int | None = None
    max_state_keys: int | None = None
    max_object_events: int | None = None
    max_strategy_log_entries: int | None = None
    max_state_payload_items: int | None = None
    max_preview_payload_items: int | None = None
    max_table_cells: int | None = None
    request_cache_max_bars: int = 1_000_000
    incremental_retention_bars: int | None = None
    replay_history_bars: int | None = None
    cache_max_items: int = 32
    trace_enabled: bool = False
    trace_max_events: int = 1_000
    trace_timings_enabled: bool = True
    trace_span_events: bool = False
    trace_slow_span_ms: float = 10.0
    trace_redacted_fields: tuple[str, ...] = DEFAULT_TRACE_REDACTED_FIELDS
    allowed_imports: tuple[str, ...] = DEFAULT_ALLOWED_IMPORTS
    data_provider: DataProvider | None = None
    syminfo: Any = None
    timeframe: Any = "1"
    session: Any = None

    def __post_init__(self) -> None:
        security_mode = normalize_security_mode(self.security_mode)
        executor_mode = normalize_executor_mode(self.executor_mode)
        object.__setattr__(self, "security_mode", security_mode)
        object.__setattr__(self, "executor_mode", executor_mode)
        object.__setattr__(self, "timeout_seconds", _optional_timeout(self.timeout_seconds))
        object.__setattr__(self, "require_hard_timeout", bool(self.require_hard_timeout))
        if self.require_hard_timeout and executor_mode == "inline":
            raise ValueError(
                "require_hard_timeout=True cannot be delivered by executor_mode='inline'; "
                "use executor_mode='process' for hard timeout enforcement"
            )
        object.__setattr__(
            self,
            "process_grace_seconds",
            max(float(self.process_grace_seconds), 0.0),
        )
        for name in OPTIONAL_BUDGET_FIELDS:
            object.__setattr__(self, name, optional_limit(name, getattr(self, name)))
        for name in ("request_cache_max_bars", "cache_max_items"):
            object.__setattr__(self, name, _positive_limit(name, getattr(self, name)))
        object.__setattr__(self, "trace_enabled", bool(self.trace_enabled))
        object.__setattr__(self, "trace_max_events", max(int(self.trace_max_events), 1))
        object.__setattr__(self, "trace_timings_enabled", bool(self.trace_timings_enabled))
        object.__setattr__(self, "trace_span_events", bool(self.trace_span_events))
        object.__setattr__(self, "trace_slow_span_ms", max(float(self.trace_slow_span_ms), 0.0))
        object.__setattr__(
            self,
            "trace_redacted_fields",
            tuple(
                sorted(
                    {
                        str(item).strip().lower()
                        for item in self.trace_redacted_fields
                        if str(item).strip()
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "allowed_imports",
            tuple(str(item).strip() for item in self.allowed_imports if str(item).strip()),
        )
        object.__setattr__(self, "syminfo", normalize_symbol_info(self.syminfo))
        object.__setattr__(self, "timeframe", normalize_timeframe_info(self.timeframe))
        object.__setattr__(self, "session", normalize_session_info(self.session))

    @classmethod
    def from_env(cls) -> "PyneSettings":
        """Build settings from PYNE_* environment variables."""
        allowed_imports = tuple(
            item.strip()
            for item in os.getenv("PYNE_ALLOWED_IMPORTS", ",".join(DEFAULT_ALLOWED_IMPORTS)).split(
                ","
            )
            if item.strip()
        )
        return cls(
            security_mode=os.getenv("PYNE_SECURITY_MODE", "unsafe"),
            executor_mode=os.getenv("PYNE_EXECUTOR_MODE", "inline"),
            timeout_seconds=_optional_timeout(os.getenv("PYNE_EXEC_TIMEOUT_SECONDS")),
            require_hard_timeout=_bool_env("PYNE_REQUIRE_HARD_TIMEOUT", False),
            process_grace_seconds=_float_env("PYNE_PROCESS_GRACE_SECONDS", 0.5),
            **{name: _optional_limit_env("PYNE_" + name.upper())
               for name in OPTIONAL_BUDGET_FIELDS},
            request_cache_max_bars=_int_env("PYNE_REQUEST_CACHE_MAX_BARS", 1_000_000),
            cache_max_items=_int_env("PYNE_CACHE_MAX_ITEMS", 32),
            trace_enabled=_bool_env("PYNE_TRACE_ENABLED", False),
            trace_max_events=_int_env("PYNE_TRACE_MAX_EVENTS", 1_000),
            trace_timings_enabled=_bool_env("PYNE_TRACE_TIMINGS_ENABLED", True),
            trace_span_events=_bool_env("PYNE_TRACE_SPAN_EVENTS", False),
            trace_slow_span_ms=_float_env("PYNE_TRACE_SLOW_SPAN_MS", 10.0),
            trace_redacted_fields=tuple(
                item.strip()
                for item in os.getenv(
                    "PYNE_TRACE_REDACTED_FIELDS",
                    ",".join(DEFAULT_TRACE_REDACTED_FIELDS),
                ).split(",")
                if item.strip()
            ),
            allowed_imports=allowed_imports,
            syminfo={
                "tickerid": os.getenv("PYNE_TICKERID", ""),
                "ticker": os.getenv("PYNE_TICKER", ""),
                "prefix": os.getenv("PYNE_SYMBOL_PREFIX", ""),
                "currency": os.getenv("PYNE_CURRENCY", ""),
                "basecurrency": os.getenv("PYNE_BASE_CURRENCY", ""),
                "mintick": _float_env("PYNE_MINTICK", 1.0),
                "pointvalue": _float_env("PYNE_POINTVALUE", 1.0),
                "type": os.getenv("PYNE_SYMBOL_TYPE", ""),
                "timezone": os.getenv("PYNE_TIMEZONE", ""),
                "volumetype": os.getenv("PYNE_VOLUME_TYPE", ""),
            },
            timeframe=os.getenv("PYNE_TIMEFRAME", "1"),
        )

    def with_security_mode(self, security_mode: str | None) -> "PyneSettings":
        """Return a copy with a requested security mode override."""
        if security_mode is None:
            return self
        return replace(self, security_mode=security_mode)


def normalize_security_mode(mode: str | None) -> str:
    normalized = (mode or "unsafe").strip().lower()
    if normalized not in SECURITY_MODES:
        raise ValueError("security_mode must be 'safe', 'research', or 'unsafe'")
    return normalized


def normalize_executor_mode(mode: str | None) -> str:
    normalized = (mode or "inline").strip().lower()
    if normalized not in EXECUTOR_MODES:
        raise ValueError("executor_mode must be 'inline' or 'process'")
    return normalized


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_limit(name: str, value: Any) -> int:
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{name} must be at least 1; zero does not disable this budget")
    return normalized


def optional_limit(name: str, value: Any) -> int | None:
    """None means unlimited; a supplied budget must be a positive integer."""
    return None if value is None else _positive_limit(name, value)


def _optional_limit_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip().lower() in {"none", "unlimited"}:
        return None
    return optional_limit(name, value)


def _optional_timeout(value: Any) -> float | None:
    import math

    if value is None or str(value).strip().lower() in {"none", "unlimited"}:
        return None
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("timeout_seconds must be finite and non-negative, or None")
    return seconds or None  # Preserve the historical zero-means-no-timeout spelling.
