"""Security helpers for Pyne script execution."""

from __future__ import annotations

import ast
import builtins
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from .errors import classify_security_error, error_hint
from .schema import OUTPUT_KEYS
from .settings import PyneSettings


SECURITY_MODES = {"safe", "research", "unsafe"}


SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "iter": iter,
    "next": next,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
}


@dataclass(frozen=True)
class PyneSecurityPolicy:
    mode: str
    allowed_imports: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float | None = None
    max_bars: int | None = None
    max_output_series: int | None = None
    max_output_points: int | None = None
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

    @classmethod
    def from_settings(
        cls,
        settings: PyneSettings | None = None,
        requested_mode: str | None = None,
    ) -> "PyneSecurityPolicy":
        settings = settings or PyneSettings.from_env()
        mode = normalize_security_mode(requested_mode or settings.security_mode)
        return cls(
            mode=mode,
            allowed_imports=tuple(settings.allowed_imports),
            timeout_seconds=settings.timeout_seconds,
            max_bars=settings.max_bars,
            max_output_series=settings.max_output_series,
            max_output_points=settings.max_output_points,
            max_array_size=settings.max_array_size,
            max_map_size=settings.max_map_size,
            max_matrix_cells=settings.max_matrix_cells,
            max_collection_depth=settings.max_collection_depth,
            max_strategy_pending_operations=settings.max_strategy_pending_operations,
            max_window_size=settings.max_window_size,
            max_total_window_items=settings.max_total_window_items,
            max_state_keys=settings.max_state_keys,
            max_object_events=settings.max_object_events,
            max_strategy_log_entries=settings.max_strategy_log_entries,
            max_state_payload_items=settings.max_state_payload_items,
            max_preview_payload_items=settings.max_preview_payload_items,
            max_table_cells=settings.max_table_cells,
            request_cache_max_bars=settings.request_cache_max_bars,
        )

    @classmethod
    def from_config(cls, requested_mode: str | None = None) -> "PyneSecurityPolicy":
        """Backward-compatible alias for environment-backed settings."""
        return cls.from_settings(PyneSettings.from_env(), requested_mode)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allowedImports": list(self.allowed_imports),
            "timeoutSeconds": self.timeout_seconds,
            "maxBars": self.max_bars,
            "maxOutputSeries": self.max_output_series,
            "maxOutputPoints": self.max_output_points,
            "maxArraySize": self.max_array_size,
            "maxMapSize": self.max_map_size,
            "maxMatrixCells": self.max_matrix_cells,
            "maxCollectionDepth": self.max_collection_depth,
            "maxStrategyPendingOperations": self.max_strategy_pending_operations,
            "maxWindowSize": self.max_window_size,
            "maxTotalWindowItems": self.max_total_window_items,
            "maxStateKeys": self.max_state_keys,
            "maxObjectEvents": self.max_object_events,
            "maxStrategyLogEntries": self.max_strategy_log_entries,
            "maxStatePayloadItems": self.max_state_payload_items,
            "maxPreviewPayloadItems": self.max_preview_payload_items,
            "maxTableCells": self.max_table_cells,
            "requestCacheMaxBars": self.request_cache_max_bars,
        }


class PyneSecurityError(RuntimeError):
    """Compatibility base for policy, resource and state-contract exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = classify_security_error(message)
        self.hint = error_hint(self.code)


class PyneResourceLimitError(PyneSecurityError):
    """An explicitly configured resource budget was exceeded."""


class PyneStateContractError(PyneSecurityError):
    """An operation cannot preserve incremental state/preview contracts."""


class PyneTimeoutError(RuntimeError):
    """Raised when a script exceeds its configured execution timeout."""


def normalize_security_mode(mode: str | None) -> str:
    normalized = (mode or "unsafe").strip().lower()
    if normalized not in SECURITY_MODES:
        raise PyneSecurityError("securityMode must be 'safe', 'research', or 'unsafe'")
    return normalized


def validate_script_security(script: str, policy: PyneSecurityPolicy) -> None:
    if policy.mode == "unsafe":
        return

    tree = ast.parse(script)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            raise PyneSecurityError(
                "Class definitions are not supported in safe/research mode; "
                "use functions and dictionaries, or unsafe mode for trusted batch code. "
                "Incremental preview and portable state have additional type restrictions."
            )
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            _validate_imports(modules, policy)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise PyneSecurityError("Relative imports are not allowed in Pyne scripts")
            _validate_imports([node.module], policy)


def build_builtins(policy: PyneSecurityPolicy) -> Any:
    if policy.mode == "unsafe":
        return dict(builtins.__dict__)

    safe = dict(SAFE_BUILTINS)
    if policy.mode == "research":
        safe["__import__"] = _build_limited_import(policy)
    return safe


def enforce_output_limits(output: dict[str, Any], policy: PyneSecurityPolicy) -> None:
    series_count = _count_output_collections(output) if policy.max_output_series is not None else 0
    if policy.max_output_series is not None and series_count > policy.max_output_series:
        raise PyneSecurityError(
            f"Too many output series ({series_count}, max {policy.max_output_series})"
        )

    events = output.get("object_events", [])
    if (policy.max_object_events is not None and isinstance(events, list)
            and len(events) > policy.max_object_events):
        raise PyneSecurityError(
            f"Drawing object events exceed max_object_events ({policy.max_object_events})"
        )

    point_count = _count_output_points(output) if policy.max_output_points is not None else 0
    if policy.max_output_points is not None and point_count > policy.max_output_points:
        raise PyneSecurityError(
            f"Too many output points ({point_count}, max {policy.max_output_points})"
        )


def _count_output_collections(output: dict[str, Any]) -> int:
    count = 0
    for key in OUTPUT_KEYS:
        if key in {"objects", "object_events", "strategy"}:
            continue
        value = output.get(key)
        if isinstance(value, list):
            count += len(value)
    return count


def _count_output_points(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        for key, item in value.items():
            if key in {"data", "regions"} and isinstance(item, list):
                count += len(item)
            else:
                count += _count_output_points(item)
        return count
    if isinstance(value, list):
        return sum(_count_output_points(item) for item in value)
    return 0


@contextmanager
def execution_timeout(seconds: float | None) -> Iterator[None]:
    """Best-effort timeout for local script execution.

    ``signal.setitimer`` only works in the main thread on Unix-like systems.
    When unavailable, execution proceeds without a hard interrupt; the policy is
    still exposed so a future process-based runner can enforce it everywhere.
    """
    if seconds is None or seconds <= 0 or threading.current_thread() is not threading.main_thread():
        yield
        return
    if not (
        hasattr(signal, "SIGALRM")
        and hasattr(signal, "ITIMER_REAL")
        and hasattr(signal, "setitimer")
    ):
        yield
        return

    try:
        previous_handler = signal.getsignal(signal.SIGALRM)
    except (AttributeError, ValueError, OSError):
        yield
        return

    def _handler(signum: int, frame: Any) -> None:
        raise PyneTimeoutError(f"Pyne script exceeded {seconds:g}s timeout")

    handler_installed = False
    armed = False
    try:
        signal.signal(signal.SIGALRM, _handler)
        handler_installed = True
        signal.setitimer(signal.ITIMER_REAL, seconds)
        armed = True
    except (AttributeError, ValueError, OSError):
        try:
            yield
            return
        finally:
            if armed:
                signal.setitimer(signal.ITIMER_REAL, 0)
            if handler_installed:
                signal.signal(signal.SIGALRM, previous_handler)
    try:
        yield
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if handler_installed:
            signal.signal(signal.SIGALRM, previous_handler)


def _validate_imports(modules: list[str], policy: PyneSecurityPolicy) -> None:
    if policy.mode == "safe":
        raise PyneSecurityError("Import statements are not allowed in safe mode")

    allowed = set(policy.allowed_imports)
    for module in modules:
        root = module.split(".", 1)[0]
        if root not in allowed:
            raise PyneSecurityError(f"Import '{root}' is not allowed in research mode")


def _build_limited_import(policy: PyneSecurityPolicy):
    allowed = set(policy.allowed_imports)

    def _limited_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        root = name.split(".", 1)[0]
        if root not in allowed:
            raise ImportError(f"Import '{root}' is not allowed in research mode")
        return builtins.__import__(name, globals, locals, fromlist, level)

    return _limited_import
