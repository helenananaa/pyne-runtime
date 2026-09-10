"""Incremental resource budgets and state containers."""
from __future__ import annotations

import copy
import operator
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import chain
from typing import Any

from ..collections import PyneArray, PyneMap, PyneMatrix
from ..security import PyneResourceLimitError, PyneStateContractError, PyneSecurityPolicy

SAFE_MAX_WINDOW_SIZE = 10_000
SAFE_MAX_TOTAL_WINDOW_ITEMS = 50_000
SAFE_MAX_STATE_KEYS = 100
SAFE_MAX_STATE_HISTORY = 50_000
SAFE_MAX_OUTPUT_SERIES = 20
SAFE_MAX_OUTPUT_POINTS = 1_000_000
SAFE_MAX_OBJECT_EVENTS = 1_000_000
SAFE_MAX_STRATEGY_LOG_ENTRIES = 1_000_000
SAFE_MAX_STATE_PAYLOAD_ITEMS = SAFE_MAX_STATE_KEYS * SAFE_MAX_STATE_HISTORY
SAFE_MAX_TABLE_CELLS = 100_000
SAFE_MAX_PREVIEW_PAYLOAD_ITEMS = 100_000

_SMALL_HISTORY_SLICE = 64
_IMMUTABLE_STATE_TYPES = (type(None), bool, int, float, complex, str, bytes)
_STATE_HISTORY_TOKEN = object()


class IncrementalResourceLimitError(PyneResourceLimitError):
    """Drawing budget error; still catchable as RuntimeError or PyneSecurityError."""


class _StateHistory:
    """Read-only history facade with token-gated runtime mutation."""

    __slots__ = ("__values",)

    def __init__(self, *, maxlen: int | None = None, values: Any = ()) -> None:
        object.__setattr__(self, "_StateHistory__values", deque(values, maxlen=maxlen))

    def __getattribute__(self, name: str) -> Any:
        if name in {"__dict__", "__values", "_StateHistory__values"}:
            raise AttributeError("StateCell history storage is private")
        return object.__getattribute__(self, name)

    def __len__(self) -> int:
        values = object.__getattribute__(self, "_StateHistory__values")
        return len(values)

    def __iter__(self):
        values = object.__getattribute__(self, "_StateHistory__values")
        for value in values:
            yield _copy_state_history_value(value)

    def __getitem__(self, index: int | slice) -> Any:
        values = object.__getattribute__(self, "_StateHistory__values")
        if isinstance(index, slice):
            return [_copy_state_history_value(value) for value in list(values)[index]]
        return _copy_state_history_value(values[index])

    @property
    def maxlen(self) -> int | None:
        values = object.__getattribute__(self, "_StateHistory__values")
        return values.maxlen

    def _raw_get(self, index: int, token: object) -> Any:
        self._require_token(token)
        values = object.__getattribute__(self, "_StateHistory__values")
        return values[index]

    def _raw_slice(self, index: slice, token: object) -> list[Any]:
        self._require_token(token)
        values = object.__getattribute__(self, "_StateHistory__values")
        return list(values)[index]

    def _append(self, value: Any, token: object) -> None:
        self._require_token(token)
        values = object.__getattribute__(self, "_StateHistory__values")
        values.append(value)

    @staticmethod
    def _require_token(token: object) -> None:
        if token is not _STATE_HISTORY_TOKEN:
            raise PyneStateContractError("StateCell history is read-only")


class StateCell:
    """Mutable state value exposed to incremental scripts."""

    __slots__ = ("value", "__history", "__history_writable", "__limit_tracker")

    _PROTECTED_ATTRIBUTES = frozenset({
        "__dict__",
        "__history",
        "__history_writable",
        "__limit_tracker",
        "_history",
        "_history_writable",
        "_limit_tracker",
        "_StateCell__history",
        "_StateCell__history_writable",
        "_StateCell__limit_tracker",
    })

    def __init__(
        self,
        value: Any,
        *,
        max_history: int | None = None,
        limit_tracker: _LimitTracker | None = None,
    ) -> None:
        self.value = value
        history_limit = None if max_history is None else max(int(max_history), 1)
        object.__setattr__(
            self,
            "_StateCell__history",
            _StateHistory(maxlen=history_limit),
        )
        object.__setattr__(self, "_StateCell__limit_tracker", limit_tracker)
        object.__setattr__(self, "_StateCell__history_writable", True)

    def __getattribute__(self, name: str) -> Any:
        if name in StateCell._PROTECTED_ATTRIBUTES:
            raise AttributeError("StateCell history and budget storage is private")
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in StateCell._PROTECTED_ATTRIBUTES:
            raise AttributeError("StateCell history and budget storage is read-only")
        object.__setattr__(self, name, value)

    def __deepcopy__(self, memo: dict[int, Any]) -> "StateCell":
        existing = memo.get(id(self))
        if existing is not None:
            return existing
        clone = object.__new__(type(self))
        memo[id(self)] = clone
        history = object.__getattribute__(self, "_StateCell__history")
        copied_history = _StateHistory(
            maxlen=history.maxlen,
            values=history._raw_slice(slice(None), _STATE_HISTORY_TOKEN),
        )
        object.__setattr__(clone, "_StateCell__history", copied_history)
        object.__setattr__(
            clone,
            "_StateCell__history_writable",
            object.__getattribute__(self, "_StateCell__history_writable"),
        )
        object.__setattr__(
            clone,
            "_StateCell__limit_tracker",
            copy.deepcopy(
                object.__getattribute__(self, "_StateCell__limit_tracker"),
                memo,
            ),
        )
        clone.value = copy.deepcopy(self.value, memo)
        return clone

    def __getitem__(self, offset: int | slice) -> Any:
        history = object.__getattribute__(self, "_StateCell__history")
        if isinstance(offset, slice):
            indices = range(*offset.indices(len(history)))
            if len(indices) <= _SMALL_HISTORY_SLICE:
                values = [history._raw_get(index, _STATE_HISTORY_TOKEN) for index in indices]
            else:
                values = history._raw_slice(offset, _STATE_HISTORY_TOKEN)
            return [_copy_state_history_value(value) for value in values]
        if not isinstance(offset, int):
            raise TypeError("StateCell history offset must be a non-negative bars-back integer")
        if offset < 0:
            raise IndexError("StateCell does not support forward history references")
        if offset == 0:
            return self.value
        if offset > len(history):
            return None
        return _copy_state_history_value(history._raw_get(-offset, _STATE_HISTORY_TOKEN))

    def commit_history(self) -> None:
        history = object.__getattribute__(self, "_StateCell__history")
        history_writable = object.__getattribute__(self, "_StateCell__history_writable")
        limit_tracker = object.__getattribute__(self, "_StateCell__limit_tracker")
        if not history_writable:
            raise PyneStateContractError("Incremental preview state history is read-only")

        payload_items = 0
        released_items = 0
        previous_payload_items: int | None = None
        if limit_tracker is not None and limit_tracker.retention_enabled:
            payload_items = _state_payload_items(self.value)
            if history.maxlen is not None and len(history) == history.maxlen:
                released_items = _state_payload_items(
                    history._raw_get(0, _STATE_HISTORY_TOKEN)
                )
            previous_payload_items = limit_tracker.state_payload_items
            limit_tracker.reserve_state_payload(
                payload_items,
                released=released_items,
            )
        try:
            snapshot = _snapshot_state_value(self.value)
        except Exception:
            if previous_payload_items is not None and limit_tracker is not None:
                limit_tracker.state_payload_items = previous_payload_items
            raise
        history._append(snapshot, _STATE_HISTORY_TOKEN)


class Window:
    """Fixed-size rolling window exposed to incremental scripts."""

    def __init__(self, size: int) -> None:
        self.size = max(int(size), 1)
        self._values: list[Any] = []
        self._start = 0
        self._length = 0

    def append(self, value: Any) -> None:
        if self._length < self.size:
            self._values.append(value)
            self._length += 1
            return
        self._values[self._start] = value
        self._start = (self._start + 1) % self.size

    @property
    def full(self) -> bool:
        return self._length >= self.size

    def __len__(self) -> int:
        return self._length

    def __iter__(self):
        for offset in range(self._length):
            yield self._values[(self._start + offset) % self.size]

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return self.values()[index]
        try:
            normalized = operator.index(index)
        except TypeError:
            raise TypeError("Window indices must be integers or slices") from None
        if normalized < 0:
            normalized += self._length
        if normalized < 0 or normalized >= self._length:
            raise IndexError("Window index out of range")
        return self._values[(self._start + normalized) % self.size]

    def values(self) -> list[Any]:
        if self._length == 0:
            return []
        stop = self._start + self._length
        if stop <= self.size:
            return self._values[self._start:stop]
        return self._values[self._start:] + self._values[: stop - self.size]


@dataclass
class IncrementalLimits:
    enabled: bool = False
    max_window_size: int | None = None
    max_total_window_items: int | None = None
    max_state_keys: int | None = None
    max_state_history: int | None = None
    max_output_series: int | None = None
    max_output_points: int | None = None
    max_object_events: int | None = None
    max_strategy_log_entries: int | None = None
    max_state_payload_items: int | None = None
    max_table_cells: int | None = None
    max_preview_payload_items: int | None = None
    retention_enabled: bool = False

    @classmethod
    def for_policy(
        cls,
        policy: PyneSecurityPolicy,
        *,
        retention_bars: int | None = None,
    ) -> "IncrementalLimits":
        return cls(
            enabled=True,
            max_window_size=policy.max_window_size,
            max_total_window_items=policy.max_total_window_items,
            max_state_keys=policy.max_state_keys,
            retention_enabled=True,
            max_state_history=retention_bars,
            max_output_series=policy.max_output_series,
            max_output_points=policy.max_output_points,
            max_object_events=policy.max_object_events,
            max_strategy_log_entries=policy.max_strategy_log_entries,
            max_table_cells=policy.max_table_cells,
            max_preview_payload_items=policy.max_preview_payload_items,
            max_state_payload_items=policy.max_state_payload_items,
        )


class _LimitTracker:
    def __init__(self, limits: IncrementalLimits) -> None:
        self.limits = limits
        self.total_window_items = 0
        self.largest_window_size = 0
        self.output_series = 0
        self.output_series_keys: set[str] = set()
        self.output_points = 0
        self.object_events = 0
        self.strategy_log_entries = 0
        self.state_payload_items = 0
        self.varip_payload_items = 0
        self.table_cells = 0

    @property
    def retention_enabled(self) -> bool:
        return self.limits.enabled or self.limits.retention_enabled

    def reserve_window(self, size: int, *, label: str) -> None:
        if not self.limits.enabled:
            return
        normalized = max(int(size), 1)
        if self.limits.max_window_size is not None and normalized > self.limits.max_window_size:
            raise PyneResourceLimitError(
                f"Incremental window '{label}' size {normalized} exceeds max_window_size limit "
                f"{self.limits.max_window_size}"
            )
        next_total = self.total_window_items + normalized
        if self.limits.max_total_window_items is not None and next_total > self.limits.max_total_window_items:
            raise PyneResourceLimitError(
                f"Incremental windows need {next_total} items, exceeding max_total_window_items total "
                f"limit {self.limits.max_total_window_items}"
            )
        self.total_window_items = next_total
        self.largest_window_size = max(self.largest_window_size, normalized)

    def reserve_output_point(self, *, series_key: str) -> None:
        if not self.retention_enabled:
            return
        normalized_key = str(series_key)
        new_series = normalized_key not in self.output_series_keys
        next_series = self.output_series + (1 if new_series else 0)
        next_points = self.output_points + 1
        if self.limits.max_output_series is not None and next_series > self.limits.max_output_series:
            raise PyneResourceLimitError(
                f"Too many output series ({next_series}, max {self.limits.max_output_series})"
            )
        if self.limits.max_output_points is not None and next_points > self.limits.max_output_points:
            raise PyneResourceLimitError(
                f"Too many output points ({next_points}, max {self.limits.max_output_points})"
            )
        self.output_series = next_series
        self.output_points = next_points
        self.output_series_keys.add(normalized_key)

    def clear_output(self) -> None:
        self.output_series = 0
        self.output_points = 0
        self.output_series_keys = set()

    def reserve_object_event(self) -> None:
        if not self.retention_enabled:
            return
        next_total = self.object_events + 1
        if self.limits.max_object_events is not None and next_total > self.limits.max_object_events:
            raise PyneResourceLimitError(
                "Incremental object events exceed retention limit "
                f"{self.limits.max_object_events}"
            )
        self.object_events = next_total

    def reserve_strategy_log(self) -> None:
        if not self.retention_enabled:
            return
        next_total = self.strategy_log_entries + 1
        if self.limits.max_strategy_log_entries is not None and next_total > self.limits.max_strategy_log_entries:
            raise PyneResourceLimitError(
                "Incremental strategy log exceeds retention limit "
                f"{self.limits.max_strategy_log_entries}"
            )
        self.strategy_log_entries = next_total

    def reserve_state_payload(self, added: int, *, released: int = 0) -> None:
        if not self.retention_enabled:
            return
        next_total = max(self.state_payload_items - max(int(released), 0), 0) + max(
            int(added),
            0,
        )
        if self.limits.max_state_payload_items is not None and next_total + self.varip_payload_items > self.limits.max_state_payload_items:
            raise PyneResourceLimitError(
                "Incremental state history payload exceeds retention limit "
                f"{self.limits.max_state_payload_items}"
            )
        self.state_payload_items = next_total

    def replace_varip_payload(self, total: int) -> None:
        if not self.retention_enabled:
            return
        normalized = max(int(total), 0)
        if self.limits.max_state_payload_items is not None and self.state_payload_items + normalized > self.limits.max_state_payload_items:
            raise PyneResourceLimitError(
                "Incremental varip payload exceeds retention limit "
                f"{self.limits.max_state_payload_items}"
            )
        self.varip_payload_items = normalized

    def reserve_table_cell(self) -> None:
        if not self.retention_enabled:
            return
        next_total = self.table_cells + 1
        if self.limits.max_table_cells is not None and next_total > self.limits.max_table_cells:
            raise PyneResourceLimitError(
                "Incremental table cells exceed retention limit "
                f"{self.limits.max_table_cells}"
            )
        self.table_cells = next_total

    def validate_preview_payload(self, items: int) -> None:
        if not self.retention_enabled:
            return
        normalized = max(int(items), 0)
        if self.limits.max_preview_payload_items is not None and normalized > self.limits.max_preview_payload_items:
            raise PyneResourceLimitError(
                "Incremental preview globals exceed payload limit "
                f"{self.limits.max_preview_payload_items}"
            )

    def release_table_cells(self, count: int) -> None:
        if not self.retention_enabled:
            return
        self.table_cells = max(self.table_cells - max(int(count), 0), 0)


def _snapshot_state_value(value: Any) -> Any:
    if isinstance(value, (PyneArray, PyneMap, PyneMatrix)):
        return value.snapshot()
    return copy.deepcopy(value)


def _copy_state_history_value(value: Any) -> Any:
    if type(value) in _IMMUTABLE_STATE_TYPES:
        return value
    return _snapshot_state_value(value)


def _state_payload_items(value: Any) -> int:
    """Estimate retained built-in slots plus text and byte payload units."""
    total = 1
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str | bytes | bytearray | memoryview):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            size = current.nbytes if isinstance(current, memoryview) else len(current)
            total += max(int(size), 1)
            continue
        if isinstance(current, PyneArray):
            children = current._values
            slot_count = len(children)
        elif isinstance(current, PyneMap):
            mapping = current._values
            children = chain(mapping.keys(), mapping.values())
            slot_count = len(mapping) * 2
        elif isinstance(current, PyneMatrix):
            children = current._values
            slot_count = len(children)
        elif isinstance(current, Mapping):
            children = chain(current.keys(), current.values())
            slot_count = len(current) * 2
        elif isinstance(current, (list, tuple, set, frozenset, deque)):
            children = current
            slot_count = len(current)
        else:
            continue

        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        total += slot_count
        pending.extend(child for child in children if _is_state_payload_value(child))
    return total


def _is_state_payload_value(value: Any) -> bool:
    return isinstance(
        value,
        (
            PyneArray,
            PyneMap,
            PyneMatrix,
            Mapping,
            list,
            tuple,
            set,
            frozenset,
            deque,
            str,
            bytes,
            bytearray,
            memoryview,
        ),
    )
