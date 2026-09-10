"""Separate checkpoint computation identity from caller resource policy."""

from __future__ import annotations

import copy
from dataclasses import fields
from typing import Any, Mapping

from ..collections import (
    ArrayNamespace,
    MapNamespace,
    MatrixNamespace,
    PyneArray,
    PyneMap,
    PyneMatrix,
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
