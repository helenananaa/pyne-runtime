from __future__ import annotations

from typing import Any

import pytest

import pyne_runtime as pn
from pyne_runtime.barstate import PyneIncrementalBarState
from pyne_runtime.incremental.bar import IncrementalBar
from pyne_runtime.incremental.context import IncrementalContext
from pyne_runtime.incremental.limits import (
    IncrementalLimits,
    StateCell,
    Window,
    _LimitTracker,
    _StateHistory,
)
from pyne_runtime.security import PyneSecurityError


class _NoMaterializationHistory(_StateHistory):
    def _raw_slice(self, index, token):
        raise AssertionError("small bars-back reads must not materialize history")


class _CountingList(list[Any]):
    def __init__(self, values: list[Any]) -> None:
        super().__init__(values)
        self.reads = 0

    def __getitem__(self, index):
        self.reads += 1
        return super().__getitem__(index)


class _DeepcopyBomb:
    def __deepcopy__(self, memo):
        raise AssertionError("discarded output history must not be deep-copied")


class _DeepcopyProbe:
    copies = 0

    def __deepcopy__(self, memo):
        type(self).copies += 1
        clone = type(self)()
        memo[id(self)] = clone
        return clone


class _NoIterationList(list[Any]):
    def __iter__(self):
        raise AssertionError("current-bar result must not scan historical output")


def _begin_bar(ctx: IncrementalContext, timestamp: int) -> None:
    bar = IncrementalBar.from_dict(
        {
            "time": timestamp,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.25,
            "volume": 1.0,
        },
        is_confirmed=True,
    )
    ctx.begin_bar(
        bar,
        bar_index=timestamp - 1,
        last_bar_index=timestamp - 1,
        barstate=PyneIncrementalBarState(isconfirmed=True),
    )


def _bars(count: int) -> list[dict[str, float | int]]:
    return [
        {
            "time": index + 1,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.25,
            "volume": 1.0,
        }
        for index in range(count)
    ]


def _history(cell: StateCell) -> _StateHistory:
    return object.__getattribute__(cell, "_StateCell__history")


def test_state_cell_integer_lookup_does_not_iterate_or_materialize_history() -> None:
    cell = StateCell("current")
    object.__setattr__(
        cell,
        "_StateCell__history",
        _NoMaterializationHistory(values=["oldest", "middle", "latest"]),
    )

    assert cell[0] == "current"
    assert cell[1] == "latest"
    assert cell[2] == "middle"
    assert cell[3] == "oldest"
    assert cell[4] is None
    with pytest.raises(IndexError, match="forward history"):
        _ = cell[-1]

    sliced = StateCell("current")
    object.__setattr__(
        sliced,
        "_StateCell__history",
        _NoMaterializationHistory(values=[1, 2, 3]),
    )
    assert sliced[1:] == [2, 3]
    assert sliced[-1:] == [3]


def test_window_ring_buffer_preserves_order_and_uses_one_read_per_integer_index() -> None:
    lazy = Window(1_000_000)
    assert lazy._values == []

    window = Window(4)
    for value in range(6):
        window.append(value)

    assert window.full
    assert len(window) == 4
    assert list(window) == [2, 3, 4, 5]
    assert window.values() == [2, 3, 4, 5]
    assert window[0] == 2
    assert window[-1] == 5
    assert window[1:3] == [3, 4]
    with pytest.raises(IndexError, match="out of range"):
        _ = window[4]

    storage = _CountingList(window._values)
    window._values = storage
    assert [window[index] for index in range(len(window))] == [2, 3, 4, 5]
    assert storage.reads == len(window)


def test_preview_clone_skips_discarded_logs_but_isolates_mutable_runtime_state() -> None:
    ctx = IncrementalContext(params={})
    ctx._series = {"line": {"data": [{"time": 1, "value": 1.0}]}}
    ctx._markers = {"marker": {"data": [_DeepcopyBomb()]}}
    ctx._object_events = [{"object": _DeepcopyBomb()}]
    ctx._current_series = {"line": {"data": [_DeepcopyBomb()]}}
    ctx._current_markers = {"marker": {"data": [_DeepcopyBomb()]}}
    ctx._current_object_events = [{"object": _DeepcopyBomb()}]
    ctx._states["probe"] = StateCell(_DeepcopyProbe())
    ctx._states["private_alias"] = StateCell(ctx._series)
    ctx._object_lines["line-1"] = {"id": "line-1", "points": [[1, 2]]}
    _DeepcopyProbe.copies = 0

    clone = ctx.clone_for_preview()

    assert clone._series == {}
    assert clone._markers == {}
    assert clone._object_events == []
    assert clone._current_series == {}
    assert clone._current_markers == {}
    assert clone._current_object_events == []
    assert _DeepcopyProbe.copies == 1
    clone._states["private_alias"].value["line"]["data"][0]["value"] = 9.0
    assert ctx._series["line"]["data"][0]["value"] == 1.0
    clone._object_lines["line-1"]["points"][0][0] = 99
    assert ctx._object_lines["line-1"]["points"][0][0] == 1


def test_preview_clone_shares_only_read_only_state_history() -> None:
    ctx = IncrementalContext(params={})
    cell = ctx.state("payload", _DeepcopyProbe())
    cell.commit_history()
    cell.value = {"values": [1]}
    _DeepcopyProbe.copies = 0

    clone = ctx.clone_for_preview()
    cloned_cell = clone.state("payload")

    assert _history(cloned_cell) is _history(cell)
    assert _DeepcopyProbe.copies == 0
    assert (
        object.__getattribute__(cloned_cell, "_StateCell__limit_tracker")
        is clone._limit_tracker
    )
    with pytest.raises(AttributeError, match="storage is private"):
        _ = cloned_cell._history
    with pytest.raises(AttributeError, match="storage is private"):
        _ = cloned_cell._StateCell__history
    with pytest.raises(AttributeError, match="storage is read-only"):
        cloned_cell._history = []
    with pytest.raises(AttributeError, match="storage is read-only"):
        cloned_cell._limit_tracker = None
    cloned_cell.value["values"].append(2)
    assert cell.value == {"values": [1]}
    with pytest.raises(PyneSecurityError, match="history is read-only"):
        cloned_cell.commit_history()


def test_state_history_reads_copy_mutable_values_without_changing_budget() -> None:
    limits = IncrementalLimits(enabled=True, max_state_payload_items=100)
    tracker = _LimitTracker(limits)
    cell = StateCell({"values": [1]}, limit_tracker=tracker)
    cell.commit_history()
    retained = tracker.state_payload_items

    previous = cell[1]
    previous["values"].append(2)
    sliced = cell[-1:]
    sliced[0]["values"].append(3)

    assert cell[1] == {"values": [1]}
    assert tracker.state_payload_items == retained


@pytest.mark.parametrize("value", ["abcdef", b"abcdef", bytearray(b"abcdef")])
def test_state_payload_counts_text_and_bytes_before_deepcopy(value: Any) -> None:
    limits = IncrementalLimits(enabled=True, max_state_payload_items=6)
    tracker = _LimitTracker(limits)
    cell = StateCell(value, limit_tracker=tracker)

    with pytest.raises(PyneSecurityError, match="state history payload"):
        cell.commit_history()


def test_state_payload_preflight_rejects_before_copying_value() -> None:
    limits = IncrementalLimits(enabled=True, max_state_payload_items=3)
    tracker = _LimitTracker(limits)
    cell = StateCell([_DeepcopyBomb(), _DeepcopyBomb(), _DeepcopyBomb()], limit_tracker=tracker)

    with pytest.raises(PyneSecurityError, match="state history payload"):
        cell.commit_history()
    assert len(_history(cell)) == 0


def test_current_bar_result_uses_delta_instead_of_scanning_historical_logs() -> None:
    ctx = IncrementalContext(params={})
    _begin_bar(ctx, 1)
    ctx.plot("close", 1.0)
    ctx.marker(True, text="first")

    _begin_bar(ctx, 2)
    ctx.plot("close", 2.0)
    ctx.marker(True, text="second")
    ctx._record_object_event("update", "line", {"id": "line-1"})
    ctx._series["close"]["data"] = _NoIterationList(ctx._series["close"]["data"])
    ctx._markers["first"]["data"] = _NoIterationList(ctx._markers["first"]["data"])
    ctx._object_events = _NoIterationList(ctx._object_events)

    result = ctx.to_result(start_s=2, end_s=2)

    assert result.lines[0]["data"] == [{"time": 2, "value": 2.0}]
    assert result.output["markers"][0]["data"][0]["time"] == 2
    assert result.output["object_events"][0]["time"] == 2


def test_direct_incremental_session_enforces_output_point_budget() -> None:
    session = pn.PyneIncrementalSession(
        script='''
indicator("Bounded Output", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("close", bar.close)
''',
        settings=pn.PyneSettings(executor_mode="inline", max_output_points=2),
    )

    with pytest.raises(PyneSecurityError, match="Too many output points"):
        session.seed(_bars(3))
    with pytest.raises(PyneSecurityError, match="session is poisoned.*Too many output points"):
        session.snapshot_result()


def test_preview_reuses_registered_series_budget_after_history_is_elided() -> None:
    session = pn.PyneIncrementalSession(
        script='''
indicator("Bounded Series", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("close", bar.close)
''',
        settings=pn.PyneSettings(
            executor_mode="inline",
            max_output_series=1,
            max_output_points=10,
        ),
    )
    session.seed(_bars(1))

    preview = session.on_bar_updated(_bars(2)[-1])

    assert preview.lines[0]["data"] == [{"time": 2, "value": 1.25}]


def test_incremental_retention_budgets_fail_closed_without_silent_trimming() -> None:
    limits = IncrementalLimits(
        enabled=True,
        max_object_events=1,
        max_strategy_log_entries=1,
        max_state_payload_items=5,
    )
    ctx = IncrementalContext(params={}, limits=limits)
    _begin_bar(ctx, 1)
    ctx._record_object_event("create", "line", {"id": "line-1"})
    with pytest.raises(PyneSecurityError, match="object events"):
        ctx._record_object_event("update", "line", {"id": "line-1"})
    assert len(ctx._object_events) == 1

    ctx.strategy._append_order({"id": "first"})
    with pytest.raises(PyneSecurityError, match="strategy log"):
        ctx.strategy._append_order({"id": "second"})
    assert ctx.strategy._orders == [{"id": "first"}]

    tracker = _LimitTracker(limits)
    cell = StateCell([], max_history=3, limit_tracker=tracker)
    cell.value = [1, 2]
    cell.commit_history()
    with pytest.raises(PyneSecurityError, match="state history payload"):
        cell.commit_history()
    assert len(_history(cell)) == 1
    assert tracker.state_payload_items == 3

    nested_tracker = _LimitTracker(limits)
    nested = StateCell([[1, 2], [3]], max_history=3, limit_tracker=nested_tracker)
    with pytest.raises(PyneSecurityError, match="state history payload"):
        nested.commit_history()
    assert len(_history(nested)) == 0


def test_state_payload_budget_releases_evicted_history_before_reserving_next() -> None:
    limits = IncrementalLimits(enabled=True, max_state_payload_items=3)
    tracker = _LimitTracker(limits)
    cell = StateCell([], max_history=1, limit_tracker=tracker)

    cell.value = [1, 2]
    cell.commit_history()
    cell.value = [3, 4]
    cell.commit_history()

    assert list(_history(cell)) == [[3, 4]]
    assert tracker.state_payload_items == 3


def test_incremental_table_cells_are_bounded_and_emit_constant_size_deltas() -> None:
    limits = IncrementalLimits(enabled=True, max_table_cells=2)
    ctx = IncrementalContext(params={}, limits=limits)
    _begin_bar(ctx, 1)
    table = ctx.table_new(columns=2, rows=2)

    ctx.table_cell(table, 1, 1, "last")
    ctx.table_cell(table, 0, 0, "first")
    snapshot = ctx._objects_snapshot()["tables"][0]
    assert [
        (cell["column"], cell["row"]) for cell in snapshot["cells"]
    ] == [(0, 0), (1, 1)]

    entry = ctx._object_tables[table.id]
    entry["cells"] = _NoIterationList(entry["cells"])
    ctx.table_cell(table, 1, 1, "updated")
    assert ctx._current_object_events[-1]["object"] == {
        "id": table.id,
        "cells": [
            {
                "column": 1,
                "row": 1,
                "text": "updated",
                "text_color": "#000000",
                "bgcolor": None,
                "width": None,
                "height": None,
                "text_halign": "center",
                "text_valign": "middle",
            }
        ],
    }
    assert ctx._limit_tracker.table_cells == 2

    with pytest.raises(PyneSecurityError, match="table cells"):
        ctx.table_cell(table, 1, 0, "over limit")

    ctx.table_clear(table)
    assert ctx._limit_tracker.table_cells == 0
    ctx.table_cell(table, 1, 0, "reused after clear")
    assert ctx._limit_tracker.table_cells == 1
    ctx.table_delete(table)
    assert ctx._limit_tracker.table_cells == 0


@pytest.mark.parametrize("column,row", [(-1, 0), (2, 0), (0, -1), (0, 2)])
def test_incremental_table_cell_rejects_declared_bounds(column: int, row: int) -> None:
    ctx = IncrementalContext(params={})
    _begin_bar(ctx, 1)
    table = ctx.table_new(columns=2, rows=2)

    with pytest.raises(IndexError, match="out of bounds"):
        ctx.table_cell(table, column, row, "invalid")
    assert ctx._object_tables[table.id]["cells"] == []


def test_preview_varip_payload_is_bounded_and_poisons_real_session() -> None:
    session = pn.PyneIncrementalSession(
        script='''
indicator("Bounded Varip", mode="incremental")
def on_bar(ctx, bar):
    ticks = ctx.varip("ticks", [])
    ticks.value.extend([1, 2, 3])
''',
        settings=pn.PyneSettings(executor_mode="inline"),
    )
    session._limits.max_state_payload_items = 3

    with pytest.raises(PyneSecurityError, match="varip payload"):
        session.on_bar_updated(_bars(1)[0])
    assert session._ctx is None
    assert session._preview_varip_states == {}
    with pytest.raises(PyneSecurityError, match="session is poisoned.*varip payload"):
        session.snapshot_result()
    with pytest.raises(PyneSecurityError, match="session is poisoned.*varip payload"):
        session.on_bar_updated(_bars(1)[0])


def test_preview_global_payload_fails_before_unbounded_deepcopy() -> None:
    session = pn.PyneIncrementalSession(
        script='''
payload = list(range(64))
indicator("Bounded Preview Globals", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("close", bar.close)
''',
        settings=pn.PyneSettings(
            executor_mode="inline",
            max_preview_payload_items=32,
        ),
    )

    with pytest.raises(PyneSecurityError, match="preview globals exceed payload limit 32"):
        session.on_bar_updated(_bars(1)[0])
    with pytest.raises(PyneSecurityError, match="session is poisoned.*preview globals"):
        session.snapshot_result()
    with pytest.raises(PyneSecurityError, match="session is poisoned.*preview globals"):
        session.on_bar_updated(_bars(1)[0])
