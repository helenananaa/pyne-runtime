"""Validate and materialize restore inputs before adopting live session state."""

from __future__ import annotations

import copy
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from types import FunctionType
from typing import Any

from ..cache import PyneCache, PyneCacheSnapshot, PyneCacheSnapshotEntry, PyneExecutionScope
from ..trace import PyneTraceRecorder
from .bar import IncrementalBar
from .context import IncrementalContext
from .limits import IncrementalLimits, StateCell, Window, _LimitTracker, _STATE_HISTORY_TOKEN, _state_payload_items
from ._isolation import _allocate_function_clones
from ._ta_capacity import ta_reserved_window_sizes
from .restore_policy import _validate_array_slice_graph


@dataclass(frozen=True)
class RestoreMetadata:
    last_closed_time: int | None
    closed_count: int
    retained_times: deque[int]
    seed_count: int
    complete: bool
    namespace_names: tuple[str, ...]


@contextmanager
def staged_restore_preparation(session: Any):
    """Rollback fresh preparation, including owned cache/trace changes, on failure.

    Namespace closures still capture the destination session. A temporary scope
    keeps top-level cache writes detached until the completed restore adopts its
    incoming cache. External effects of full Python code remain caller-owned.
    """
    original_scope = session.execution_scope
    if session._prepared:
        yield original_scope.cache
        return
    original = dict(vars(session))
    try:
        cache = PyneCache(max_items=session.settings.cache_max_items)
        cache.restore_state(original_scope.cache.snapshot_state())
        session.execution_scope = PyneExecutionScope(cache)
        session.trace = copy.deepcopy(session.trace)
        session._meta = copy.deepcopy(session._meta)
        yield original_scope.cache
    except BaseException:
        vars(session).clear()
        vars(session).update(original)
        raise
    else:
        session.execution_scope = original_scope
        if session._cache_namespace is not None:
            session._cache_namespace._cache = original_scope.cache


def _require(condition: bool, field: str) -> None:
    if not condition:
        raise ValueError(f"Incremental snapshot {field} is invalid")


def validate_restore_shape(snapshot: Any, function_state_type: type) -> RestoreMetadata:
    """Check runtime-owned shapes, including fields previously read after commit."""
    count, last = snapshot.closed_count, snapshot.last_closed_time
    _require(type(count) is int and count >= 0, "closed_count")
    _require(last is None or type(last) is int, "last_closed_time")
    _require((count == 0) == (last is None), "closed_count/last_closed_time")
    times = snapshot.retained_closed_times
    _require(type(times) is tuple and all(type(time) is int for time in times), "retained_closed_times")
    _require(len(times) <= count and all(a < b for a, b in zip(times, times[1:])), "retained_closed_times")
    _require((not count and not times) or bool(times) and times[-1] == last, "retained_closed_times")
    retention = snapshot.retention_bars
    _require(retention is None or type(retention) is int and retention > 0, "retention_bars")
    _require(len(times) == (count if retention is None else min(count, retention)), "retained_closed_times")
    for name in ("params", "meta", "global_values", "function_states", "function_bindings"):
        _require(type(getattr(snapshot, name)) is dict, name)
    for name in ("global_values", "function_states", "function_bindings"):
        _require(all(type(key) is str for key in getattr(snapshot, name)), name)
    _require(all(isinstance(value, function_state_type) for value in snapshot.function_states.values()), "function_states")
    _require(all(isinstance(value, FunctionType) for value in snapshot.function_bindings.values()), "function_bindings")
    _require(type(snapshot.detached_functions) is tuple and all(isinstance(value, FunctionType) for value in snapshot.detached_functions), "detached_functions")
    names = snapshot.namespace_names
    _require(type(names) is tuple and all(type(name) is str for name in names), "namespace_names")
    _require(snapshot.trace is None or isinstance(snapshot.trace, PyneTraceRecorder), "trace")
    context = snapshot.context
    _require(context is None or isinstance(context, IncrementalContext), "context")
    _require(context is not None or count == 0, "context/closed_count")
    if context is not None:
        _require(isinstance(context._limits, IncrementalLimits), "context limits")
        tracker = context._limit_tracker
        _require(isinstance(tracker, _LimitTracker), "context limit tracker")
        for name in ("output_series", "output_points", "object_events", "table_cells",
                     "strategy_log_entries", "state_payload_items", "varip_payload_items",
                     "total_window_items", "largest_window_size"):
            value = getattr(tracker, name)
            _require(type(value) is int and value >= 0, f"context {name}")
        _require(isinstance(context.trace, PyneTraceRecorder), "context trace")
        _require(context.current_bar is None or isinstance(context.current_bar, IncrementalBar), "context current_bar")
        _require(context.current_bar is not None or count == 0, "context current_bar/closed_count")
        _require(type(context.bar_index) is int and context.bar_index == count - 1, "context bar_index")
        if context.current_bar is not None:
            _require(context.current_bar.time == last and context.current_bar.bar_index == count - 1
                     and context.current_bar.is_confirmed is True, "context committed bar")
        validate_context_resources(context)
    bars, seed, complete = snapshot.portable_bars, snapshot.portable_seed_count, snapshot.portable_complete
    _require(type(bars) is tuple and all(type(bar) is dict for bar in bars), "portable_bars")
    _require(type(seed) is int and 0 <= seed <= len(bars), "portable_seed_count")
    _require(type(complete) is bool, "portable_complete")
    _require(not complete or len(bars) == count, "portable_bars/closed_count")
    _require(complete or not bars and seed == 0, "incomplete portable history")
    cache = snapshot.cache
    _require(isinstance(cache, PyneCacheSnapshot), "cache")
    _require(type(cache.max_items) is int and cache.max_items > 0, "cache max_items")
    _require(type(cache.entries) is tuple and all(isinstance(entry, PyneCacheSnapshotEntry) for entry in cache.entries), "cache entries")
    return RestoreMetadata(last, count, deque(times), seed, complete, names)


def validate_context_resources(context: IncrementalContext, *, reconcile_payload: bool = False) -> None:
    """Check counters against retained roots instead of trusting decoded totals.

    Counters can conservatively exceed actual usage after a caught reservation
    error. They must never understate owned objects or use a different tracker.
    """
    tracker = context._limit_tracker
    # A decoded collection graph must be structurally valid before payload
    # accessors can traverse slice parents, including frozen state history.
    _validate_array_slice_graph({0: context._states, 1: context._varip_states})
    _require(tracker.limits is context._limits, "context tracker limits")
    _require(context.ta._limits is tracker, "context TA tracker")
    series_keys, points = set(), 0
    for family, attribute in (("series", "_series"), ("candle", "_candles"), ("marker", "_markers")):
        collection = getattr(context, attribute)
        _require(type(collection) is dict, f"context {attribute}")
        for key, entry in collection.items():
            _require(type(key) is str and type(entry) is dict and type(entry.get("data")) is list,
                     f"context {attribute} entries")
            series_keys.add(f"{family}:{key}")
            points += len(entry["data"])
    _require(type(tracker.output_series_keys) is set and series_keys <= tracker.output_series_keys,
             "context output series keys")
    used = {"output_series": len(series_keys), "output_points": points,
            "object_events": len(context._object_events),
            "strategy_log_entries": len(context.strategy._orders) + len(context.strategy._closed_trades)}
    _require(context.strategy._context is context, "context strategy binding")
    _require(type(context._object_tables) is dict, "context tables")
    cells = 0
    for table in context._object_tables.values():
        _require(type(table) is dict and type(table.get("cells")) is list, "context table cells")
        cells += len(table["cells"])
    used["table_cells"] = cells
    for attribute, counter in (("_states", "state_payload_items"), ("_varip_states", "varip_payload_items")):
        states = getattr(context, attribute)
        _require(type(states) is dict, f"context {attribute}")
        payload = 0
        for cell in states.values():
            _require(isinstance(cell, StateCell), f"context {attribute} cell")
            _require(object.__getattribute__(cell, "_StateCell__limit_tracker") is tracker,
                     f"context {attribute} tracker")
            if attribute == "_states":
                history = object.__getattribute__(cell, "_StateCell__history")
                payload += sum(_state_payload_items(value) for value in history._raw_slice(slice(None), _STATE_HISTORY_TOKEN))
            else:
                payload += _state_payload_items(cell.value)
        used[counter] = payload
    _require(type(context._windows) is dict and all(isinstance(window, Window) for window in context._windows.values()),
             "context windows")
    sizes = [window.size for window in context._windows.values()]
    sizes.extend(ta_reserved_window_sizes(context.ta))
    _require(all(type(size) is int and size > 0 for size in sizes), "context window sizes")
    used["total_window_items"] = sum(sizes)
    used["largest_window_size"] = max(sizes, default=0)
    for name, minimum in used.items():
        if name in {"state_payload_items", "varip_payload_items"}:
            # Typed decoding inlines immutable strings. Their aliases can have
            # a larger physical payload than the original interned graph.
            # Reconcile detached roots before selected-budget validation; never
            # reject unlimited valid computation merely for those identities.
            if reconcile_payload:
                setattr(tracker, name, max(getattr(tracker, name), minimum))
            continue
        _require(getattr(tracker, name) >= minimum, f"context {name} undercounts retained state")


def prepare_function_bindings(
    snapshot: Any, *, prepared_values: dict[str, Any], namespace: dict[str, Any],
    memo: dict[int, Any],
) -> tuple[dict[str, FunctionType], list[tuple[FunctionType, FunctionType]]]:
    """Allocate every function before copying roots so aliases share its clone."""
    functions: dict[str, FunctionType] = {}
    clones: list[tuple[FunctionType, FunctionType]] = []
    for name in snapshot.function_states:
        binding = snapshot.function_bindings.get(name)
        function = memo.get(id(binding)) if binding is not None else None
        if function is None:
            original = binding if binding is not None else prepared_values.get(name, namespace.get(name))
            _require(isinstance(original, FunctionType), f"function is missing: {name}")
            allocated = _allocate_function_clones(
                (original,), memo=memo, script_globals=namespace, target_globals=namespace,
            )
            clones.extend(allocated)
            function = allocated[0][1]
        functions[name] = function
    return functions, clones


def apply_function_states(functions: dict[str, FunctionType], states: dict[str, Any], memo: dict[int, Any]) -> None:
    """Apply copied state to detached functions; setters can reject malformed data."""
    for name, function in functions.items():
        state = states[name]
        defaults = copy.deepcopy(state.defaults, memo)
        kwdefaults = copy.deepcopy(state.kwdefaults, memo)
        attributes = copy.deepcopy(state.attributes, memo)
        _require(defaults is None or isinstance(defaults, tuple), f"function defaults: {name}")
        _require(kwdefaults is None or isinstance(kwdefaults, dict), f"function kwdefaults: {name}")
        _require(isinstance(attributes, dict), f"function attributes: {name}")
        function.__defaults__ = defaults
        function.__kwdefaults__ = kwdefaults
        function.__dict__.clear()
        function.__dict__.update(attributes)
