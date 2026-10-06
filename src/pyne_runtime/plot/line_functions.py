"""Collector-bound line and linefill drawing operations."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..chart import ChartPoint, chart_point_coordinates
from .collector import OutputCollector
from .linefill_store import linefill_store
from .refs import ObjectRef
from .value_helpers import PlotValueAdapter


_MISSING = object()


def create_line_functions(collector: OutputCollector) -> dict[str, Any]:
    _scalar_from_value = PlotValueAdapter(collector).scalar

    def _point_coordinates(point: ChartPoint, xloc: str) -> tuple[Any, Any]:
        x, y = chart_point_coordinates(point, xloc)
        return _scalar_from_value(x), _scalar_from_value(y)

    def _line_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "line":
            return None
        return collector._object_lines.get(ref.id)

    def _linefill_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "linefill":
            return None
        return collector._object_linefills.get(ref.id)

    def line_new(
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
        if pane is None:
            pane = "main"
        if isinstance(x1, ChartPoint) or isinstance(y1, ChartPoint):
            if not isinstance(x1, ChartPoint) or not isinstance(y1, ChartPoint):
                raise TypeError("line.new() point overload requires two chart.point values")
            if x2 is not _MISSING:
                xloc = str(x2)
            if y2 is not _MISSING:
                extend = str(y2)
            resolved_x1, resolved_y1 = _point_coordinates(x1, xloc)
            resolved_x2, resolved_y2 = _point_coordinates(y1, xloc)
        else:
            if x2 is _MISSING or y2 is _MISSING:
                raise TypeError("line.new() requires x1, y1, x2, and y2")
            resolved_x1 = _scalar_from_value(x1)
            resolved_y1 = _scalar_from_value(y1)
            resolved_x2 = _scalar_from_value(x2)
            resolved_y2 = _scalar_from_value(y2)
        object_id = collector._next_object_id("line")
        collector._object_lines[object_id] = {
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
            "pane": pane,
        }
        return ObjectRef(id=object_id, kind="line")

    def line_set_xy1(ref: ObjectRef, x: Any, y: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x1"] = _scalar_from_value(x)
            entry["y1"] = _scalar_from_value(y)

    def line_set_xy2(ref: ObjectRef, x: Any, y: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x2"] = _scalar_from_value(x)
            entry["y2"] = _scalar_from_value(y)

    def line_set_first_point(ref: ObjectRef, point: ChartPoint) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x1"], entry["y1"] = _point_coordinates(
                point,
                str(entry.get("xloc", "bar_index")),
            )

    def line_set_second_point(ref: ObjectRef, point: ChartPoint) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x2"], entry["y2"] = _point_coordinates(
                point,
                str(entry.get("xloc", "bar_index")),
            )

    def line_set_x1(ref: ObjectRef, x: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x1"] = _scalar_from_value(x)

    def line_set_y1(ref: ObjectRef, y: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["y1"] = _scalar_from_value(y)

    def line_set_x2(ref: ObjectRef, x: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["x2"] = _scalar_from_value(x)

    def line_set_y2(ref: ObjectRef, y: Any) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["y2"] = _scalar_from_value(y)

    def line_set_color(ref: ObjectRef, color: str) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["color"] = color

    def line_set_width(ref: ObjectRef, width: int) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["width"] = int(width)

    def line_set_style(ref: ObjectRef, style: str) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["style"] = style

    def line_set_extend(ref: ObjectRef, extend: str) -> None:
        entry = _line_entry(ref)
        if entry is not None:
            entry["extend"] = extend

    def line_get_x1(ref: ObjectRef) -> Any:
        entry = _line_entry(ref)
        return np.nan if entry is None or entry.get("x1") is None else entry["x1"]

    def line_get_y1(ref: ObjectRef) -> Any:
        entry = _line_entry(ref)
        return np.nan if entry is None or entry.get("y1") is None else entry["y1"]

    def line_get_x2(ref: ObjectRef) -> Any:
        entry = _line_entry(ref)
        return np.nan if entry is None or entry.get("x2") is None else entry["x2"]

    def line_get_y2(ref: ObjectRef) -> Any:
        entry = _line_entry(ref)
        return np.nan if entry is None or entry.get("y2") is None else entry["y2"]

    def line_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "line":
            collector._object_lines.pop(ref.id, None)
            entries = linefill_store(collector)
            for linefill_id in entries.dependent_ids(ref.id):
                entries.pop(linefill_id, None)

    def linefill_new(
        line1: ObjectRef,
        line2: ObjectRef,
        color: str = "rgba(33,150,243,0.25)",
        pane: str | None = None,
    ) -> ObjectRef:
        first = _line_entry(line1)
        second = _line_entry(line2)
        if first is None or second is None:
            raise TypeError("linefill.new() requires two live line objects")
        resolved_pane = pane or (
            str(first.get("pane"))
            if first.get("pane") == second.get("pane")
            else "main"
        )
        object_id = collector._next_object_id("linefill")
        collector._object_linefills[object_id] = {
            "id": object_id,
            "line1_id": line1.id,
            "line2_id": line2.id,
            "color": color,
            "pane": resolved_pane,
        }
        return ObjectRef(id=object_id, kind="linefill")

    def linefill_set_color(ref: ObjectRef, color: str) -> None:
        entry = _linefill_entry(ref)
        if entry is not None:
            entry["color"] = color

    def linefill_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "linefill":
            collector._object_linefills.pop(ref.id, None)

    return {
        "line_new": line_new,
        "line_set_xy1": line_set_xy1,
        "line_set_xy2": line_set_xy2,
        "line_set_first_point": line_set_first_point,
        "line_set_second_point": line_set_second_point,
        "line_set_x1": line_set_x1,
        "line_set_y1": line_set_y1,
        "line_set_x2": line_set_x2,
        "line_set_y2": line_set_y2,
        "line_set_color": line_set_color,
        "line_set_width": line_set_width,
        "line_set_style": line_set_style,
        "line_set_extend": line_set_extend,
        "line_get_x1": line_get_x1,
        "line_get_y1": line_get_y1,
        "line_get_x2": line_get_x2,
        "line_get_y2": line_get_y2,
        "line_delete": line_delete,
        "linefill_new": linefill_new,
        "linefill_set_color": linefill_set_color,
        "linefill_delete": linefill_delete,
    }
