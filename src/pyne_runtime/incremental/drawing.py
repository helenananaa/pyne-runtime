"""Incremental drawing object mutation helpers."""

from __future__ import annotations

import copy
import math
from typing import Any

from ..chart import ChartPoint, chart_point_coordinates
from ..collections import PyneArray
from ..plot import ObjectRef
from .limits import IncrementalResourceLimitError, StateCell
from .strategy import _round8


_MISSING = object()


class IncrementalDrawingMixin:
    def line_all(self) -> PyneArray:
        return PyneArray(ObjectRef(id=object_id, kind="line") for object_id in self._object_lines)

    def label_all(self) -> PyneArray:
        return PyneArray(ObjectRef(id=object_id, kind="label") for object_id in self._object_labels)

    def box_all(self) -> PyneArray:
        return PyneArray(ObjectRef(id=object_id, kind="box") for object_id in self._object_boxes)

    def line_new(
        self,
        x1: Any,
        y1: Any,
        x2: Any = _MISSING,
        y2: Any = _MISSING,
        color: str = "#2196f3",
        width: int = 1,
        style: str = "solid",
        extend: str = "none",
        xloc: str = "bar_index",
        pane: str | None = None,
    ) -> ObjectRef:
        if isinstance(x1, ChartPoint) or isinstance(y1, ChartPoint):
            if not isinstance(x1, ChartPoint) or not isinstance(y1, ChartPoint):
                raise TypeError("line.new() point overload requires two chart.point values")
            if x2 is not _MISSING:
                xloc = str(x2)
            if y2 is not _MISSING:
                extend = str(y2)
            resolved_x1, resolved_y1 = _drawing_point_coordinates(x1, xloc)
            resolved_x2, resolved_y2 = _drawing_point_coordinates(y1, xloc)
        else:
            if x2 is _MISSING or y2 is _MISSING:
                raise TypeError("line.new() requires x1, y1, x2, and y2")
            resolved_x1 = _drawing_scalar(x1)
            resolved_y1 = _drawing_scalar(y1)
            resolved_x2 = _drawing_scalar(x2)
            resolved_y2 = _drawing_scalar(y2)
        object_id = self._next_object_id("line")
        entry = {
            "id": object_id,
            "x1": resolved_x1,
            "y1": resolved_y1,
            "x2": resolved_x2,
            "y2": resolved_y2,
            "color": color,
            "width": int(width),
            "style": style,
            "extend": extend,
            "xloc": xloc,
            "pane": pane or "main",
        }
        self._object_lines[object_id] = entry
        self._record_object_event("create", "line", entry)
        return ObjectRef(id=object_id, kind="line")

    def line_set_xy1(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "line", {"x1": _drawing_scalar(x), "y1": _drawing_scalar(y)})

    def line_set_xy2(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "line", {"x2": _drawing_scalar(x), "y2": _drawing_scalar(y)})

    def line_set_first_point(self, ref: ObjectRef, point: ChartPoint) -> None:
        entry = self._object_entry(ref, "line")
        if entry is None:
            return
        x, y = _drawing_point_coordinates(point, str(entry.get("xloc", "bar_index")))
        self._update_object(ref, "line", {"x1": x, "y1": y})

    def line_set_second_point(self, ref: ObjectRef, point: ChartPoint) -> None:
        entry = self._object_entry(ref, "line")
        if entry is None:
            return
        x, y = _drawing_point_coordinates(point, str(entry.get("xloc", "bar_index")))
        self._update_object(ref, "line", {"x2": x, "y2": y})

    def line_set_x1(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "line", {"x1": _drawing_scalar(x)})

    def line_set_y1(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "line", {"y1": _drawing_scalar(y)})

    def line_set_x2(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "line", {"x2": _drawing_scalar(x)})

    def line_set_y2(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "line", {"y2": _drawing_scalar(y)})

    def line_set_color(self, ref: ObjectRef, color: str) -> None:
        self._update_object(ref, "line", {"color": color})

    def line_set_width(self, ref: ObjectRef, width: int) -> None:
        self._update_object(ref, "line", {"width": int(width)})

    def line_set_style(self, ref: ObjectRef, style: str) -> None:
        self._update_object(ref, "line", {"style": style})

    def line_set_extend(self, ref: ObjectRef, extend: str) -> None:
        self._update_object(ref, "line", {"extend": extend})

    def line_delete(self, ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "line":
            for linefill_id, entry in list(self._object_linefills.items()):
                if ref.id in {entry.get("line1_id"), entry.get("line2_id")}:
                    self._delete_object(ObjectRef(id=linefill_id, kind="linefill"), "linefill")
        self._delete_object(ref, "line")

    def linefill_new(
        self,
        line1: ObjectRef,
        line2: ObjectRef,
        color: str = "rgba(33,150,243,0.25)",
        pane: str | None = None,
    ) -> ObjectRef:
        first = self._object_entry(line1, "line")
        second = self._object_entry(line2, "line")
        if first is None or second is None:
            raise TypeError("linefill.new() requires two live line objects")
        object_id = self._next_object_id("linefill")
        entry = {
            "id": object_id,
            "line1_id": line1.id,
            "line2_id": line2.id,
            "color": color,
            "pane": pane
            or (str(first.get("pane")) if first.get("pane") == second.get("pane") else "main"),
        }
        self._object_linefills[object_id] = entry
        self._record_object_event("create", "linefill", entry)
        return ObjectRef(id=object_id, kind="linefill")

    def linefill_set_color(self, ref: ObjectRef, color: str) -> None:
        self._update_object(ref, "linefill", {"color": color})

    def linefill_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "linefill")

    def polyline_new(
        self,
        points: PyneArray | list[ChartPoint] | tuple[ChartPoint, ...],
        curved: bool = False,
        closed: bool = False,
        xloc: str = "bar_index",
        line_color: str = "#2196f3",
        fill_color: str | None = None,
        line_style: str = "solid",
        line_width: int = 1,
        force_overlay: bool = False,
        pane: str | None = None,
    ) -> ObjectRef:
        if isinstance(points, PyneArray):
            raw_points = list(points)
        elif isinstance(points, (list, tuple)):
            raw_points = list(points)
        else:
            raise TypeError("polyline.new() points must be an array of chart.point values")
        if not raw_points:
            raise ValueError("polyline.new() requires at least one chart.point")
        serialized_points: list[dict[str, Any]] = []
        for point in raw_points:
            if not isinstance(point, ChartPoint):
                raise TypeError("polyline.new() points must contain only chart.point values")
            x, y = _drawing_point_coordinates(point, xloc)
            serialized_points.append({"x": x, "y": y})
        object_id = self._next_object_id("polyline")
        entry = {
            "id": object_id,
            "points": serialized_points,
            "curved": bool(curved),
            "closed": bool(closed),
            "xloc": xloc,
            "line_color": line_color,
            "fill_color": fill_color,
            "line_style": line_style,
            "line_width": int(line_width),
            "pane": pane or ("main" if force_overlay else "main"),
        }
        self._object_polylines[object_id] = entry
        self._record_object_event("create", "polyline", entry)
        return ObjectRef(id=object_id, kind="polyline")

    def polyline_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "polyline")

    def label_new(
        self,
        x: Any,
        y: Any = _MISSING,
        text: str = "",
        color: str = "#ffffff",
        textcolor: str = "#000000",
        style: str = "label_down",
        size: str = "normal",
        xloc: str = "bar_index",
        yloc: str = "price",
        pane: str | None = None,
    ) -> ObjectRef:
        if isinstance(x, ChartPoint):
            point_text = text if y is _MISSING else y
            if y is not _MISSING and text in {"bar_index", "bar_time"}:
                xloc = text
            resolved_x, resolved_y = _drawing_point_coordinates(x, xloc)
            resolved_text = str(point_text)
        else:
            if y is _MISSING:
                raise TypeError("label.new() requires x and y coordinates")
            resolved_x = _drawing_scalar(x)
            resolved_y = _drawing_scalar(y)
            resolved_text = str(text)
        object_id = self._next_object_id("label")
        entry = {
            "id": object_id,
            "x": resolved_x,
            "y": resolved_y,
            "text": resolved_text,
            "color": color,
            "textcolor": textcolor,
            "style": style,
            "size": size,
            "xloc": xloc,
            "yloc": yloc,
            "pane": pane or "main",
        }
        self._object_labels[object_id] = entry
        self._record_object_event("create", "label", entry)
        return ObjectRef(id=object_id, kind="label")

    def label_set_xy(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "label", {"x": _drawing_scalar(x), "y": _drawing_scalar(y)})

    def label_set_point(self, ref: ObjectRef, point: ChartPoint) -> None:
        entry = self._object_entry(ref, "label")
        if entry is None:
            return
        x, y = _drawing_point_coordinates(point, str(entry.get("xloc", "bar_index")))
        self._update_object(ref, "label", {"x": x, "y": y})

    def label_set_x(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "label", {"x": _drawing_scalar(x)})

    def label_set_y(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "label", {"y": _drawing_scalar(y)})

    def label_set_text(self, ref: ObjectRef, text: str) -> None:
        self._update_object(ref, "label", {"text": str(text)})

    def label_set_color(self, ref: ObjectRef, color: str) -> None:
        self._update_object(ref, "label", {"color": color})

    def label_set_textcolor(self, ref: ObjectRef, textcolor: str) -> None:
        self._update_object(ref, "label", {"textcolor": textcolor})

    def label_set_style(self, ref: ObjectRef, style: str) -> None:
        self._update_object(ref, "label", {"style": style})

    def label_set_size(self, ref: ObjectRef, size: str) -> None:
        self._update_object(ref, "label", {"size": size})

    def label_set_xloc(self, ref: ObjectRef, xloc: str) -> None:
        self._update_object(ref, "label", {"xloc": xloc})

    def label_set_yloc(self, ref: ObjectRef, yloc: str) -> None:
        self._update_object(ref, "label", {"yloc": yloc})

    def label_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "label")

    def box_new(
        self,
        left: Any,
        top: Any,
        right: Any = _MISSING,
        bottom: Any = _MISSING,
        bgcolor: str = "rgba(0,0,0,0)",
        border_color: str = "#787b86",
        border_width: int = 1,
        border_style: str = "solid",
        xloc: str = "bar_index",
        pane: str | None = None,
    ) -> ObjectRef:
        if isinstance(left, ChartPoint) or isinstance(top, ChartPoint):
            if not isinstance(left, ChartPoint) or not isinstance(top, ChartPoint):
                raise TypeError("box.new() point overload requires two chart.point values")
            if right is not _MISSING or bottom is not _MISSING:
                raise TypeError(
                    "box.new() point overload accepts drawing options as keyword arguments"
                )
            resolved_left, resolved_top = _drawing_point_coordinates(left, xloc)
            resolved_right, resolved_bottom = _drawing_point_coordinates(top, xloc)
        else:
            if right is _MISSING or bottom is _MISSING:
                raise TypeError("box.new() requires left, top, right, and bottom")
            resolved_left = _drawing_scalar(left)
            resolved_top = _drawing_scalar(top)
            resolved_right = _drawing_scalar(right)
            resolved_bottom = _drawing_scalar(bottom)
        object_id = self._next_object_id("box")
        entry = {
            "id": object_id,
            "left": resolved_left,
            "top": resolved_top,
            "right": resolved_right,
            "bottom": resolved_bottom,
            "bgcolor": bgcolor,
            "border_color": border_color,
            "border_width": int(border_width),
            "border_style": border_style,
            "xloc": xloc,
            "pane": pane or "main",
        }
        self._object_boxes[object_id] = entry
        self._record_object_event("create", "box", entry)
        return ObjectRef(id=object_id, kind="box")

    def box_set_left(self, ref: ObjectRef, left: Any) -> None:
        self._update_object(ref, "box", {"left": _drawing_scalar(left)})

    def box_set_top(self, ref: ObjectRef, top: Any) -> None:
        self._update_object(ref, "box", {"top": _drawing_scalar(top)})

    def box_set_right(self, ref: ObjectRef, right: Any) -> None:
        self._update_object(ref, "box", {"right": _drawing_scalar(right)})

    def box_set_bottom(self, ref: ObjectRef, bottom: Any) -> None:
        self._update_object(ref, "box", {"bottom": _drawing_scalar(bottom)})

    def box_set_lefttop(self, ref: ObjectRef, left: Any, top: Any) -> None:
        self._update_object(
            ref,
            "box",
            {"left": _drawing_scalar(left), "top": _drawing_scalar(top)},
        )

    def box_set_rightbottom(self, ref: ObjectRef, right: Any, bottom: Any) -> None:
        self._update_object(
            ref,
            "box",
            {"right": _drawing_scalar(right), "bottom": _drawing_scalar(bottom)},
        )

    def box_set_top_left_point(self, ref: ObjectRef, point: ChartPoint) -> None:
        entry = self._object_entry(ref, "box")
        if entry is None:
            return
        left, top = _drawing_point_coordinates(point, str(entry.get("xloc", "bar_index")))
        self._update_object(ref, "box", {"left": left, "top": top})

    def box_set_bottom_right_point(self, ref: ObjectRef, point: ChartPoint) -> None:
        entry = self._object_entry(ref, "box")
        if entry is None:
            return
        right, bottom = _drawing_point_coordinates(
            point,
            str(entry.get("xloc", "bar_index")),
        )
        self._update_object(ref, "box", {"right": right, "bottom": bottom})

    def box_set_bgcolor(self, ref: ObjectRef, bgcolor: str) -> None:
        self._update_object(ref, "box", {"bgcolor": bgcolor})

    def box_set_border_color(self, ref: ObjectRef, border_color: str) -> None:
        self._update_object(ref, "box", {"border_color": border_color})

    def box_set_border_width(self, ref: ObjectRef, border_width: int) -> None:
        self._update_object(ref, "box", {"border_width": int(border_width)})

    def box_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "box")

    def table_new(
        self,
        position: str = "top_right",
        columns: int = 1,
        rows: int = 1,
        bgcolor: str | None = None,
        frame_color: str = "#787b86",
        frame_width: int = 1,
        border_color: str = "#787b86",
        border_width: int = 1,
        pane: str | None = None,
    ) -> ObjectRef:
        column_count = int(columns)
        row_count = int(rows)
        if column_count <= 0 or row_count <= 0:
            raise ValueError("Incremental table columns and rows must be positive")
        object_id = self._next_object_id("table")
        entry = {
            "id": object_id,
            "position": position,
            "columns": column_count,
            "rows": row_count,
            "bgcolor": bgcolor,
            "frame_color": frame_color,
            "frame_width": int(frame_width),
            "border_color": border_color,
            "border_width": int(border_width),
            "pane": pane or "main",
            "cells": [],
            "merges": [],
        }
        self._object_tables[object_id] = entry
        self._table_cell_indices[object_id] = {}
        self._record_object_event("create", "table", entry)
        return ObjectRef(id=object_id, kind="table")

    def table_cell(
        self,
        ref: ObjectRef,
        column: int,
        row: int,
        text: Any = "",
        text_color: str = "#000000",
        bgcolor: str | None = None,
        width: int | None = None,
        height: int | None = None,
        text_halign: str = "center",
        text_valign: str = "middle",
    ) -> None:
        entry = self._object_entry(ref, "table")
        if entry is None:
            return
        normalized_column = int(column)
        normalized_row = int(row)
        columns = int(entry.get("columns", 0))
        rows = int(entry.get("rows", 0))
        if not 0 <= normalized_column < columns or not 0 <= normalized_row < rows:
            raise IndexError(
                "Incremental table cell "
                f"({normalized_column}, {normalized_row}) is out of bounds for "
                f"{columns} columns x {rows} rows"
            )
        cell = {
            "column": normalized_column,
            "row": normalized_row,
            "text": str(_drawing_scalar(text)),
            "text_color": text_color,
            "bgcolor": bgcolor,
            "width": width,
            "height": height,
            "text_halign": text_halign,
            "text_valign": text_valign,
        }
        cell_indices = self._table_cell_indices.setdefault(ref.id, {})
        cell_key = (normalized_column, normalized_row)
        is_new = cell_key not in cell_indices
        if is_new:
            self._limit_tracker.reserve_table_cell()
        _upsert_table_cell(entry, cell, cell_indices)
        self._record_object_event(
            "update",
            "table",
            entry,
            event_object={"id": entry.get("id"), "cells": [cell]},
        )

    def table_clear(self, ref: ObjectRef) -> None:
        entry = self._object_entry(ref, "table")
        if entry is None:
            return
        released = len(entry.get("cells") or [])
        entry["cells"] = []
        entry["merges"] = []
        self._table_cell_indices.setdefault(ref.id, {}).clear()
        self._limit_tracker.release_table_cells(released)
        self._record_object_event(
            "update",
            "table",
            entry,
            event_object={"id": entry.get("id"), "cells": []},
        )

    def table_merge_cells(
        self,
        ref: ObjectRef,
        start_column: int,
        start_row: int,
        end_column: int,
        end_row: int,
    ) -> None:
        entry = self._object_entry(ref, "table")
        if entry is None:
            return
        left, right = sorted((int(start_column), int(end_column)))
        top, bottom = sorted((int(start_row), int(end_row)))
        _require_table_coordinate(entry, left, top)
        _require_table_coordinate(entry, right, bottom)
        merge = {
            "start_column": left,
            "start_row": top,
            "end_column": right,
            "end_row": bottom,
        }
        for existing in entry.setdefault("merges", []):
            overlaps = not (
                right < existing["start_column"]
                or left > existing["end_column"]
                or bottom < existing["start_row"]
                or top > existing["end_row"]
            )
            if overlaps:
                raise ValueError("table.merge_cells() regions must not overlap")
        entry["merges"].append(merge)
        entry["merges"].sort(key=lambda item: (item["start_row"], item["start_column"]))
        self._record_object_event(
            "update",
            "table",
            entry,
            event_object={"id": entry.get("id"), "merges": copy.deepcopy(entry["merges"])},
        )

    def table_set_position(self, ref: ObjectRef, position: str) -> None:
        self._update_object(ref, "table", {"position": position})

    def table_set_bgcolor(self, ref: ObjectRef, bgcolor: str) -> None:
        self._update_object(ref, "table", {"bgcolor": bgcolor})

    def table_set_frame_color(self, ref: ObjectRef, frame_color: str) -> None:
        self._update_object(ref, "table", {"frame_color": frame_color})

    def table_set_border_color(self, ref: ObjectRef, border_color: str) -> None:
        self._update_object(ref, "table", {"border_color": border_color})

    def table_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "table")

    def _next_object_id(self, kind: str) -> str:
        self._ensure_object_capacity()
        self._object_counter += 1
        return f"{kind}_{self._object_counter}"

    def _ensure_object_capacity(self) -> None:
        total = (
            len(self._object_lines)
            + len(self._object_labels)
            + len(self._object_boxes)
            + len(self._object_tables)
            + len(self._object_linefills)
            + len(self._object_polylines)
        )
        if self._max_drawing_objects is not None and total >= self._max_drawing_objects:
            raise IncrementalResourceLimitError(
                f"Drawing object limit exceeded (max {self._max_drawing_objects})"
            )

    def _object_entry(self, ref: ObjectRef, kind: str) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != kind:
            return None
        buckets = {
            "line": self._object_lines,
            "label": self._object_labels,
            "box": self._object_boxes,
            "table": self._object_tables,
            "linefill": self._object_linefills,
            "polyline": self._object_polylines,
        }
        return buckets[kind].get(ref.id)

    def _update_object(self, ref: ObjectRef, kind: str, updates: dict[str, Any]) -> None:
        entry = self._object_entry(ref, kind)
        if entry is None:
            return
        entry.update(updates)
        event_object = {"id": entry.get("id"), **updates} if kind == "table" else entry
        self._record_object_event("update", kind, entry, event_object=event_object)

    def _delete_object(self, ref: ObjectRef, kind: str) -> None:
        entry = self._object_entry(ref, kind)
        if entry is None:
            return
        event_object = _table_snapshot(entry) if kind == "table" else entry
        self._record_object_event("delete", kind, entry, event_object=event_object)
        {
            "line": self._object_lines,
            "label": self._object_labels,
            "box": self._object_boxes,
            "table": self._object_tables,
            "linefill": self._object_linefills,
            "polyline": self._object_polylines,
        }[kind].pop(ref.id, None)
        if kind == "table":
            self._table_cell_indices.pop(ref.id, None)
            self._limit_tracker.release_table_cells(len(entry.get("cells") or []))

    def _record_object_event(
        self,
        action: str,
        kind: str,
        entry: dict[str, Any],
        *,
        event_object: dict[str, Any] | None = None,
    ) -> None:
        previous_total = self._limit_tracker.object_events
        self._limit_tracker.reserve_object_event()
        try:
            event: dict[str, Any] = {
                "action": action,
                "kind": kind,
                "id": entry.get("id"),
                "object": copy.deepcopy(entry if event_object is None else event_object),
            }
            if self.current_bar is not None:
                event["time"] = self.current_bar.time
                event["bar_index"] = self.bar_index
                event["confirmed"] = self.barstate.isconfirmed
                event["realtime"] = self.barstate.isrealtime
            self._object_events.append(event)
            self._current_object_events.append(event)
        except Exception:
            self._limit_tracker.object_events = previous_total
            raise

    def _objects_snapshot(self) -> dict[str, Any]:
        objects: dict[str, Any] = {}
        if self._object_lines:
            objects["lines"] = list(copy.deepcopy(self._object_lines).values())
        if self._object_labels:
            objects["labels"] = list(copy.deepcopy(self._object_labels).values())
        if self._object_boxes:
            objects["boxes"] = list(copy.deepcopy(self._object_boxes).values())
        if self._object_tables:
            objects["tables"] = [_table_snapshot(entry) for entry in self._object_tables.values()]
        if self._object_linefills:
            objects["linefills"] = list(copy.deepcopy(self._object_linefills).values())
        if self._object_polylines:
            objects["polylines"] = list(copy.deepcopy(self._object_polylines).values())
        return objects


def _filter_object_events(
    events: list[dict[str, Any]],
    start_s: int | None,
    end_s: int | None,
) -> list[dict[str, Any]]:
    if start_s is None and end_s is None:
        return copy.deepcopy(events)
    filtered = []
    for event in events:
        try:
            ts = int(event.get("time"))
        except (TypeError, ValueError):
            continue
        if start_s is not None and ts < start_s:
            continue
        if end_s is not None and ts > end_s:
            continue
        filtered.append(copy.deepcopy(event))
    return filtered


def _drawing_scalar(value: Any) -> Any:
    if isinstance(value, StateCell):
        value = value.value
    if value is None:
        return None
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else _round8(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return None if math.isnan(number) else _round8(number)


def _drawing_point_coordinates(point: ChartPoint, xloc: str) -> tuple[Any, Any]:
    x, y = chart_point_coordinates(point, xloc)
    return _drawing_scalar(x), _drawing_scalar(y)


def _upsert_table_cell(
    entry: dict[str, Any],
    cell: dict[str, Any],
    cell_indices: dict[tuple[int, int], int],
) -> None:
    cells = entry.setdefault("cells", [])
    key = (cell["column"], cell["row"])
    existing_index = cell_indices.get(key)
    if existing_index is not None:
        cells[existing_index] = cell
        return
    cell_indices[key] = len(cells)
    cells.append(cell)


def _require_table_coordinate(entry: dict[str, Any], column: int, row: int) -> None:
    if column < 0 or column >= int(entry["columns"]):
        raise IndexError(f"table column {column} is outside the table")
    if row < 0 or row >= int(entry["rows"]):
        raise IndexError(f"table row {row} is outside the table")


def _table_snapshot(entry: dict[str, Any]) -> dict[str, Any]:
    snapshot = copy.deepcopy(entry)
    snapshot["cells"] = sorted(
        snapshot.get("cells") or [],
        key=lambda item: (item.get("row", 0), item.get("column", 0)),
    )
    return snapshot
