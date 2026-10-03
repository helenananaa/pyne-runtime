"""Separate checkpoint computation identity from caller resource policy."""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import fields
from typing import Any, Mapping

from ..collections import (
    ArrayNamespace,
    MapNamespace,
    MatrixNamespace,
    PyneArray,
    PyneMap,
    PyneMatrix,
    _ArraySliceStorage,
    _collection_depth,
)
from ..settings import PyneSettings
from .checkpoint import (
    PynePortableSnapshotError,
    portable_settings_contract,
    settings_from_portable_contract,
)
from .limits import IncrementalLimits, StateCell, _StateHistory, _STATE_HISTORY_TOKEN, _LimitTracker


SEMANTIC_SETTINGS = ("securityMode", "allowedImports", "syminfo", "timeframe", "session")


def validate_restore_settings(contract: Mapping[str, Any], settings: PyneSettings) -> PyneSettings:
    old = settings_from_portable_contract(contract)
    current = portable_settings_contract(settings)
    for key in SEMANTIC_SETTINGS:
        if current[key] != contract[key]:
            raise PynePortableSnapshotError(
                f"Incremental snapshot settings do not match computation contract: {key}"
            )
    return old


def _check(name: str, used: int, maximum: int | None) -> None:
    if maximum is not None and used > maximum:
        raise PynePortableSnapshotError(
            f"Snapshot state exceeds {name}: needs {used}, configured {maximum}"
        )


def _rebind_limit(value: int | None, old: int | None, new: int | None) -> int | None:
    if value == old:
        return new
    # Preserve a deliberately smaller per-object limit while respecting the new budget.
    if value is None:
        return new
    return value if new is None else min(value, new)


def _validate_array_slice_graph(memo: dict[int, Any]) -> None:
    # Validate references before any size/depth accessor can follow a malformed
    # chain. Typed decoding restores attributes without running constructors.
    # StateCell deepcopy deliberately shares confirmed history. Inspect that
    # graph too: a decoded history is not trusted merely because it is frozen.
    pending = list(memo.values())
    seen: set[int] = set()
    storages: list[_ArraySliceStorage] = []
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, StateCell):
            history = object.__getattribute__(value, "_StateCell__history")
            pending.extend(history._raw_slice(slice(None), _STATE_HISTORY_TOKEN))
            pending.append(value.value)
        elif isinstance(value, _ArraySliceStorage):
            storages.append(value)
            pending.extend(vars(value).values())
        elif isinstance(value, (PyneArray, PyneMap, PyneMatrix)):
            if type(getattr(value, "_string_values", None)) is not bool:
                kind = "array" if isinstance(value, PyneArray) else "map" if isinstance(value, PyneMap) else "matrix"
                raise PynePortableSnapshotError(f"Snapshot {kind} string construction intent is invalid")
            if isinstance(value, PyneMatrix):
                width = getattr(value, "_column_count", None)
                rows = getattr(value, "_values", None)
                if (type(width) is not int or width < 0 or not isinstance(rows, list)
                        or any(not isinstance(row, list) or len(row) != width for row in rows)):
                    raise PynePortableSnapshotError("Snapshot matrix shape is invalid")
            pending.extend(vars(value).values())
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, deque, set, frozenset)):
            pending.extend(value)
    validated: set[int] = set()
    for value in storages:
        if not isinstance(value, _ArraySliceStorage):
            continue
        current = value
        path: set[int] = set()
        while isinstance(current, _ArraySliceStorage):
            identity = id(current)
            if identity in path:
                raise PynePortableSnapshotError("Snapshot array slice parent chain is recursive")
            if identity in validated:
                break
            path.add(identity)
            attributes = vars(current)
            if set(attributes) != {"parent", "start", "stop"}:
                raise PynePortableSnapshotError("Snapshot array slice fields are invalid")
            start, stop = current.start, current.stop
            if (type(start) is not int or type(stop) is not int or start < 0 or stop < start
                    or not isinstance(current.parent, PyneArray)):
                raise PynePortableSnapshotError("Snapshot array slice bounds or parent are invalid")
            current = getattr(current.parent, "_values", None)
            if not isinstance(current, (list, _ArraySliceStorage)):
                raise PynePortableSnapshotError("Snapshot array slice parent storage is invalid")
        validated.update(path)


def rebind_restored_budgets(
    memo: dict[int, Any],
    old: PyneSettings,
    new: PyneSettings,
    limits: IncrementalLimits,
    context: Any,
) -> None:
    """Validate and update copied runtime-owned objects before atomic adoption.

    deepcopy's memo covers globals, callback defaults, state and cache aliases.
    StateCell history is normally shared as immutable snapshots; copy it first
    before changing collection capacity metadata. Never mutate the source graph.
    """
    collections_changed = any(
        getattr(old, name) != getattr(new, name)
        for name in (
            "max_array_size",
            "max_map_size",
            "max_matrix_cells",
            "max_collection_depth",
        )
    )
    if collections_changed:
        for value in list(memo.values()):
            if isinstance(value, StateCell):
                history = object.__getattribute__(value, "_StateCell__history")
                copied = copy.deepcopy(history._raw_slice(slice(None), _STATE_HISTORY_TOKEN), memo)
                object.__setattr__(
                    value,
                    "_StateCell__history",
                    _StateHistory(maxlen=history.maxlen, values=copied),
                )
    _validate_array_slice_graph(memo)
    seen: set[int] = set()
    for value in list(memo.values()):
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, IncrementalLimits):
            for item in fields(limits):
                setattr(value, item.name, getattr(limits, item.name))
        elif isinstance(value, _LimitTracker):
            for name, used in (
                ("max_window_size", value.largest_window_size),
                ("max_total_window_items", value.total_window_items),
                ("max_output_series", value.output_series),
                ("max_output_points", value.output_points),
                ("max_object_events", value.object_events),
                ("max_strategy_log_entries", value.strategy_log_entries),
                ("max_table_cells", value.table_cells),
                ("max_state_payload_items", value.state_payload_items + value.varip_payload_items),
            ):
                _check(name, used, getattr(new, name))
        elif isinstance(
            value, (PyneArray, ArrayNamespace, PyneMap, MapNamespace, PyneMatrix, MatrixNamespace)
        ):
            attrs = {"_max_depth": "max_collection_depth"}
            if isinstance(value, (PyneArray, ArrayNamespace)):
                attrs["_max_size"] = "max_array_size"
            elif isinstance(value, (PyneMap, MapNamespace)):
                attrs.update(_max_size="max_map_size", _array_max_size="max_array_size")
            else:
                attrs.update(_max_cells="max_matrix_cells", _array_max_size="max_array_size")
            for attr, setting in attrs.items():
                setattr(
                    value,
                    attr,
                    _rebind_limit(
                        getattr(value, attr), getattr(old, setting), getattr(new, setting)
                    ),
                )
            if isinstance(value, (PyneArray, PyneMap, PyneMatrix)):
                if isinstance(value, PyneMatrix):
                    _check("max_matrix_cells", sum(map(len, value._values)), value._max_cells)
                else:
                    _check("collection size", len(value._values), value._max_size)
                if value._max_depth is not None:
                    _check("max_collection_depth", _collection_depth(value), value._max_depth)
    if context is not None:
        _check(
            "max_state_keys", len(context._states) + len(context._varip_states), new.max_state_keys
        )
        objects = sum(
            len(getattr(context, name))
            for name in (
                "_object_lines",
                "_object_labels",
                "_object_boxes",
                "_object_tables",
                "_object_linefills",
                "_object_polylines",
            )
        )
        _check("max_drawing_objects", objects, new.max_drawing_objects)
        context._max_drawing_objects = new.max_drawing_objects
