"""Pine-style plot and drawing function factories."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..chart import ChartPoint, chart_point_coordinates
from ..collections import PyneArray
from ..series import PyneSeries
from ..values import is_na_value
from .collector import OutputCollector
from .namespace_builder import assemble_plot_namespace
from .refs import ObjectRef, PlotRef
from .value_helpers import (
    PlotValueAdapter,
    collector_color,
    display_options,
    is_color_series,
    serialize_color,
)


_MISSING = object()


def create_plot_functions(collector: OutputCollector) -> dict[str, Any]:
    """Create all plot/drawing functions bound to a collector.

    Returns a dict of {name: function} to be injected into script globals.
    """

    def indicator(title: str = "", overlay: bool = True, **kwargs: Any) -> None:
        """Declare indicator metadata.

        Pine equivalent: ``indicator("My Indicator", overlay=true)``
        """
        collector.set_indicator_meta(title=title, overlay=overlay, **kwargs)

    values = PlotValueAdapter(collector)
    _values_from_data = values.from_data
    _color_for_index = values.color_for_index
    _is_valid_value = values.is_valid
    _condition_is_true = values.condition_is_true
    _scalar_from_value = values.scalar

    def _line_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "line":
            return None
        return collector._object_lines.get(ref.id)

    def _label_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "label":
            return None
        return collector._object_labels.get(ref.id)

    def _box_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "box":
            return None
        return collector._object_boxes.get(ref.id)

    def _table_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "table":
            return None
        return collector._object_tables.get(ref.id)

    def _linefill_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "linefill":
            return None
        return collector._object_linefills.get(ref.id)

    def _polyline_entry(ref: ObjectRef) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != "polyline":
            return None
        return collector._object_polylines.get(ref.id)

    def _point_coordinates(point: ChartPoint, xloc: str) -> tuple[Any, Any]:
        x, y = chart_point_coordinates(point, xloc)
        return _scalar_from_value(x), _scalar_from_value(y)

    def _object_refs(kind: str, entries: dict[str, dict[str, Any]]) -> PyneArray:
        return PyneArray(ObjectRef(id=object_id, kind=kind) for object_id in entries)

    def plot(
        data: PyneSeries | np.ndarray | list,
        title: str = "",
        color: str | PyneSeries | np.ndarray = "#f59e0b",
        linewidth: int = 2,
        style: str = "solid",
        overlay: bool | None = None,
        pane: str | None = None,
        color_array: PyneSeries | np.ndarray | None = None,
        display: str | None = None,
        format: str | None = None,
        precision: int | None = None,
    ) -> PlotRef:
        """Plot a line series.

        Pine equivalent: ``plot(ta.sma(close, 20), "SMA", color=color.orange)``

        Args:
            data: Array of values to plot.
            title: Display title.
            color: Line color (hex string, or per-bar array).
            linewidth: Line width in pixels.
            style: "solid", "dashed", "dotted".
            overlay: True = on price chart, False = separate pane.
            pane: Explicit pane assignment ("main" or "separate").
            color_array: Per-bar color array (overrides ``color``).
            display: Pine-like display enum string.
            format: Pine-like numeric format enum string.
            precision: Optional display precision.

        Returns:
            PlotRef for use with ``fill()``.
        """
        plot_id = collector._next_id()

        values = _values_from_data(data)

        # Build data points: [{time, value}, ...]
        points = []
        per_bar_color_source = color_array if color_array is not None else color
        has_per_bar_color = color_array is not None or isinstance(
            color, (np.ndarray, PyneSeries, list)
        )
        for i, (t, v) in enumerate(zip(collector.times, values)):
            if _is_valid_value(v):
                point: dict[str, Any] = {"time": t, "value": round(float(v), 8)}
                # Per-bar coloring
                if has_per_bar_color:
                    point_color = _color_for_index(per_bar_color_source, i, t)
                    if point_color:
                        point["color"] = point_color
                points.append(point)

        # Determine pane
        if pane is None:
            if overlay is not None:
                pane = "main" if overlay else "separate"
            elif collector._indicator_meta.get("overlay", True):
                pane = "main"
            else:
                pane = "separate"

        if str(style).lower() in {"histogram", "columns", "column", "bar"}:
            hist_points = []
            for i, (t, v) in enumerate(zip(collector.times, values)):
                if not _is_valid_value(v):
                    continue
                point = {"time": t, "value": round(float(v), 8)}
                point_color = _color_for_index(
                    color_array if color_array is not None else color,
                    i,
                    t,
                )
                if point_color:
                    point["color"] = point_color
                hist_points.append(point)
            collector.histograms.append(
                {
                    "title": title or plot_id,
                    "color_up": (
                        collector_color(color, default="#26a69a")
                        if not is_color_series(color)
                        else "#26a69a"
                    ),
                    "color_down": (
                        collector_color(color, default="#ef5350")
                        if not is_color_series(color)
                        else "#ef5350"
                    ),
                    "pane": pane,
                    "data": hist_points,
                    **display_options(display=display, format=format, precision=precision),
                }
            )
            return PlotRef(id=plot_id, title=title, pane=pane)

        line_entry: dict[str, Any] = {
            "id": plot_id,
            "title": title or plot_id,
            "color": collector_color(color),
            "linewidth": linewidth,
            "style": style,
            "pane": pane,
            "data": points,
            **display_options(display=display, format=format, precision=precision),
        }

        if has_per_bar_color:
            line_entry["per_bar_color"] = True

        collector.lines.append(line_entry)
        return PlotRef(id=plot_id, title=title, pane=pane)

    def plotcandle(
        open: Any,
        high: Any,
        low: Any,
        close: Any,
        title: str = "",
        color: Any = None,
        wickcolor: Any = None,
        bordercolor: Any = None,
        editable: bool = True,
        show_last: int | None = None,
        display: str | None = None,
        format: str | None = None,
        precision: int | None = None,
        force_overlay: bool = False,
        pane: str | None = None,
        **_: Any,
    ) -> None:
        """Emit a versioned OHLC candle collection."""
        _ = editable
        opens = _values_from_data(open)
        highs = _values_from_data(high)
        lows = _values_from_data(low)
        closes = _values_from_data(close)
        if pane is None:
            pane = "main" if force_overlay or collector._indicator_meta.get("overlay", True) else "separate"
        first_visible_index = 0
        if show_last is not None:
            first_visible_index = max(len(collector.times) - max(int(show_last), 0), 0)

        points: list[dict[str, Any]] = []
        for index, (timestamp, open_value, high_value, low_value, close_value) in enumerate(
            zip(collector.times, opens, highs, lows, closes)
        ):
            if index < first_visible_index or not all(
                _is_valid_value(value)
                for value in (open_value, high_value, low_value, close_value)
            ):
                continue
            point = {
                "time": timestamp,
                "open": round(float(open_value), 8),
                "high": round(float(high_value), 8),
                "low": round(float(low_value), 8),
                "close": round(float(close_value), 8),
            }
            body_color = _color_for_index(color, index, timestamp)
            wick_color = _color_for_index(wickcolor, index, timestamp)
            border_color = _color_for_index(bordercolor, index, timestamp)
            if body_color:
                point["color"] = body_color
            if wick_color:
                point["wickcolor"] = wick_color
            if border_color:
                point["bordercolor"] = border_color
            points.append(point)
        collector.candles.append(
            {
                "title": title or collector._next_id(),
                "pane": pane,
                "data": points,
                **display_options(display=display, format=format, precision=precision),
            }
        )

    def bar(
        data: PyneSeries | np.ndarray | list,
        title: str = "",
        color_up: str = "#26a69a",
        color_down: str = "#ef5350",
        pane: str | None = None,
    ) -> None:
        """Plot a histogram / bar chart.

        Pine equivalent: ``plotshape`` or custom histogram plotting.

        Commonly used for MACD histogram, volume bars, etc.

        Args:
            data: Array of values.
            title: Display title.
            color_up: Color for positive values.
            color_down: Color for negative values.
            pane: "main" or "separate".
        """
        values = _values_from_data(data)

        if pane is None:
            pane = "separate"

        points = []
        for t, v in zip(collector.times, values):
            if _is_valid_value(v):
                fv = float(v)
                points.append(
                    {
                        "time": t,
                        "value": round(fv, 8),
                        "color": color_up if fv >= 0 else color_down,
                    }
                )

        collector.histograms.append(
            {
                "title": title,
                "color_up": color_up,
                "color_down": color_down,
                "pane": pane,
                "data": points,
            }
        )

    def hline(
        price: float,
        title: str = "",
        color: str = "#787b86",
        linestyle: str = "dashed",
        linewidth: int = 1,
        pane: str | None = None,
    ) -> None:
        """Plot a horizontal reference line.

        Pine equivalent: ``hline(70, "OB", color=color.red, linestyle=hline.style_dashed)``
        """
        if pane is None:
            pane = "separate" if not collector._indicator_meta.get("overlay", True) else "main"

        collector.hlines.append(
            {
                "price": float(price),
                "title": title,
                "color": color,
                "linestyle": linestyle,
                "linewidth": linewidth,
                "pane": pane,
            }
        )

    def fill(
        plot1: PlotRef,
        plot2: PlotRef,
        color: str = "rgba(59,130,246,0.1)",
        title: str = "",
    ) -> None:
        """Fill the area between two plotted lines.

        Pine equivalent: ``fill(p1, p2, color=color.new(color.blue, 90))``

        Args:
            plot1: First PlotRef (from ``plot()``).
            plot2: Second PlotRef (from ``plot()``).
            color: Fill color (use rgba for transparency).
        """
        collector.fills.append(
            {
                "plot1_id": plot1.id,
                "plot2_id": plot2.id,
                "color": color,
                "title": title,
                "pane": plot1.pane if plot1.pane == plot2.pane else "separate",
            }
        )

    def bgcolor(
        condition: PyneSeries | np.ndarray | bool,
        color: str = "rgba(59,130,246,0.1)",
        pane: str | None = None,
        title: str = "",
    ) -> None:
        """Conditional background coloring.

        Pine equivalent: ``bgcolor(rsi > 70 ? color.new(color.red, 90) : na)``

        Args:
            condition: Boolean array — True where background should be colored.
            color: Background color.
            pane: "main" or "separate".
        """
        if pane is None:
            pane = "main"

        if isinstance(condition, PyneSeries):
            condition = condition.to_numpy()

        if isinstance(condition, np.ndarray):
            regions = []
            for i, (t, c) in enumerate(zip(collector.times, condition)):
                if _condition_is_true(c):
                    regions.append({"time": t})
        elif condition:
            regions = [{"time": t} for t in collector.times]
        else:
            regions = []

        if regions:
            collector.bgcolors.append(
                {
                    "color": color,
                    "pane": pane,
                    "title": title,
                    "regions": regions,
                }
            )

    def marker(
        condition: PyneSeries | np.ndarray | list | bool,
        shape: str = "circle",
        color: str | PyneSeries | np.ndarray | list = "#f59e0b",
        text: str = "",
        char: str | None = None,
        textcolor: str | None = None,
        position: str = "above",
        location: str | None = None,
        size: str = "normal",
        pane: str | None = None,
        title: str = "",
        offset: int = 0,
        show_last: int | None = None,
        display: str | None = None,
        force_overlay: bool = False,
    ) -> None:
        """Plot markers/shapes at specific bars.

        Pine equivalent: ``plotshape(crossover(fast,slow), style=shape.triangleup)``

        Args:
            condition: Boolean array — True where markers should appear.
            shape: "circle", "triangle_up", "triangle_down", "cross",
                   "diamond", "arrow_up", "arrow_down".
            color: Marker color.
            text: Text to display with the marker.
            char: Optional character marker payload for ``plotchar()``.
            textcolor: Optional marker text color.
            position: "above" or "below" the bar.
            size: "tiny", "small", "normal", "large".
            pane: "main" or "separate".
        """
        if location is not None:
            position = location
        if force_overlay:
            pane = "main"
        if pane is None:
            pane = "separate" if not collector._indicator_meta.get("overlay", True) else "main"

        condition_values = _values_from_data(condition)
        offset_value = int(offset)
        first_visible_index = 0
        if show_last is not None:
            first_visible_index = max(len(collector.times) - max(int(show_last), 0), 0)
        entry_color = collector_color(color) if not is_color_series(color) else "#f59e0b"

        marks = []
        for i, (t, c) in enumerate(zip(collector.times, condition_values)):
            if i < first_visible_index:
                continue
            if _condition_is_true(c):
                target_index = i + offset_value
                if target_index < 0 or target_index >= len(collector.times):
                    continue
                target_time = collector.times[target_index]
                point_color = _color_for_index(color, i, t) or entry_color
                mark: dict[str, Any] = {
                    "time": target_time,
                    "shape": shape,
                    "color": point_color,
                    "text": text,
                    "position": position,
                    "size": size,
                    "pane": pane,
                }
                if char is not None:
                    mark["char"] = str(char)
                if textcolor is not None:
                    mark["textcolor"] = textcolor
                if position == "absolute" and not isinstance(c, (bool, np.bool_)):
                    try:
                        mark["value"] = round(float(c), 8)
                    except (TypeError, ValueError):
                        pass
                marks.append(mark)

        if marks:
            marker_entry: dict[str, Any] = {
                "shape": shape,
                "color": entry_color,
                "text": text,
                "position": position,
                "size": size,
                "pane": pane,
                "data": marks,
                **display_options(display=display, format=None, precision=None),
            }
            if title:
                marker_entry["title"] = title
            if char is not None:
                marker_entry["char"] = str(char)
            if textcolor is not None:
                marker_entry["textcolor"] = textcolor
            if offset_value:
                marker_entry["offset"] = offset_value
            if isinstance(color, (PyneSeries, np.ndarray, list)):
                marker_entry["per_bar_color"] = True
            collector.markers.append(marker_entry)

    def plotshape(
        series: PyneSeries | np.ndarray | list | bool,
        title: str = "",
        style: str = "circle",
        location: str = "above",
        color: str | PyneSeries | np.ndarray | list = "#f59e0b",
        offset: int = 0,
        text: str = "",
        textcolor: str | None = None,
        editable: bool = True,
        size: str = "normal",
        show_last: int | None = None,
        display: str | None = None,
        force_overlay: bool = False,
        **_: Any,
    ) -> None:
        """Pine-like ``plotshape()`` wrapper over Pyne marker output."""
        _ = editable
        marker(
            series,
            shape=style,
            color=color,
            text=text,
            textcolor=textcolor,
            location=location,
            size=size,
            title=title,
            offset=offset,
            show_last=show_last,
            display=display,
            force_overlay=force_overlay,
        )

    def plotchar(
        series: PyneSeries | np.ndarray | list | bool,
        title: str = "",
        char: str = "",
        location: str = "above",
        color: str | PyneSeries | np.ndarray | list = "#f59e0b",
        offset: int = 0,
        text: str = "",
        textcolor: str | None = None,
        editable: bool = True,
        size: str = "normal",
        show_last: int | None = None,
        display: str | None = None,
        force_overlay: bool = False,
        **_: Any,
    ) -> None:
        """Pine-like ``plotchar()`` wrapper over Pyne marker output."""
        _ = editable
        glyph = str(char or text or "")
        marker(
            series,
            shape="char",
            color=color,
            text=str(text or glyph),
            char=glyph,
            textcolor=textcolor,
            location=location,
            size=size,
            title=title,
            offset=offset,
            show_last=show_last,
            display=display,
            force_overlay=force_overlay,
        )

    def plotarrow(
        series: PyneSeries | np.ndarray | list | int | float,
        title: str = "",
        colorup: str | PyneSeries | np.ndarray | list = "#26a69a",
        colordown: str | PyneSeries | np.ndarray | list = "#ef5350",
        offset: int = 0,
        minheight: int = 5,
        maxheight: int = 30,
        editable: bool = True,
        show_last: int | None = None,
        display: str | None = None,
        force_overlay: bool = False,
        **_: Any,
    ) -> None:
        """Pine-like ``plotarrow()`` wrapper over Pyne marker output."""
        _ = editable
        pane = (
            "main"
            if force_overlay
            else ("separate" if not collector._indicator_meta.get("overlay", True) else "main")
        )
        values = _values_from_data(series)
        offset_value = int(offset)
        first_visible_index = 0
        if show_last is not None:
            first_visible_index = max(len(collector.times) - max(int(show_last), 0), 0)

        visible_numbers: list[float] = []
        for idx, item in enumerate(values):
            if idx < first_visible_index or is_na_value(item):
                continue
            try:
                number = float(item)
            except (TypeError, ValueError):
                continue
            if number != 0:
                visible_numbers.append(abs(number))

        max_abs = max(visible_numbers) if visible_numbers else 0.0
        min_height = int(minheight)
        max_height = int(maxheight)
        if max_height < min_height:
            min_height, max_height = max_height, min_height

        marks: list[dict[str, Any]] = []
        for idx, (t, item) in enumerate(zip(collector.times, values)):
            if idx < first_visible_index or is_na_value(item):
                continue
            try:
                number = float(item)
            except (TypeError, ValueError):
                continue
            if number == 0:
                continue

            target_index = idx + offset_value
            if target_index < 0 or target_index >= len(collector.times):
                continue

            is_up = number > 0
            color_data = colorup if is_up else colordown
            fallback_color = (
                collector_color(color_data, default="#26a69a" if is_up else "#ef5350")
                if not is_color_series(color_data)
                else "#26a69a"
                if is_up
                else "#ef5350"
            )
            if max_abs > 0 and max_height > min_height:
                height = min_height + int(
                    round((max_height - min_height) * (abs(number) / max_abs))
                )
            else:
                height = min_height

            marks.append(
                {
                    "time": collector.times[target_index],
                    "shape": "arrow_up" if is_up else "arrow_down",
                    "color": _color_for_index(color_data, idx, t) or fallback_color,
                    "text": "",
                    "position": "below" if is_up else "above",
                    "size": "normal",
                    "pane": pane,
                    "direction": "up" if is_up else "down",
                    "value": round(number, 8),
                    "height": height,
                }
            )

        if marks:
            arrow_entry: dict[str, Any] = {
                "shape": "arrow",
                "color_up": (
                    collector_color(colorup, default="#26a69a")
                    if not is_color_series(colorup)
                    else "#26a69a"
                ),
                "color_down": (
                    collector_color(colordown, default="#ef5350")
                    if not is_color_series(colordown)
                    else "#ef5350"
                ),
                "text": "",
                "position": "auto",
                "size": "normal",
                "pane": pane,
                "minheight": min_height,
                "maxheight": max_height,
                "data": marks,
                **display_options(display=display, format=None, precision=None),
            }
            if title:
                arrow_entry["title"] = title
            if offset_value:
                arrow_entry["offset"] = offset_value
            if isinstance(colorup, (PyneSeries, np.ndarray, list)) or isinstance(
                colordown, (PyneSeries, np.ndarray, list)
            ):
                arrow_entry["per_bar_color"] = True
            collector.markers.append(arrow_entry)

    def barcolor(
        color_arr: PyneSeries | np.ndarray | str,
    ) -> None:
        """Color individual candlestick bars.

        Pine equivalent: ``barcolor(close > open ? color.green : color.red)``

        Args:
            color_arr: Array of color strings (one per bar), or a single color.
        """
        if isinstance(color_arr, str):
            colors_list = [color_arr] * len(collector.times)
        elif isinstance(color_arr, PyneSeries):
            colors_list = color_arr.to_numpy().tolist()
        elif isinstance(color_arr, np.ndarray):
            colors_list = color_arr.tolist()
        else:
            colors_list = list(color_arr)

        bar_colors = []
        for t, c in zip(collector.times, colors_list):
            color_text = serialize_color(c)
            if color_text:
                bar_colors.append({"time": t, "color": color_text})

        if bar_colors:
            collector.barcolors.append({"data": bar_colors})

    def emit_signal(
        condition: PyneSeries | np.ndarray | bool,
        name: str = "",
        side: str = "buy",
        message: str = "",
        strength: float | None = None,
        price: PyneSeries | np.ndarray | float | None = None,
        payload: dict[str, Any] | None = None,
        pane: str = "main",
    ) -> None:
        """Emit structured buy/sell/alert signals without placing orders.

        The indicator system only reports these events. Future Strategy or
        Trading modules may consume them, but Pyne indicators do not manage API
        keys or submit orders.
        """
        if isinstance(condition, PyneSeries):
            flags = condition.to_numpy().tolist()
        elif isinstance(condition, np.ndarray):
            flags = condition.tolist()
        elif isinstance(condition, list):
            flags = condition
        else:
            flags = [bool(condition)] * len(collector.times)

        prices = _values_from_data(price) if price is not None else [None] * len(collector.times)
        normalized_side = str(side or "alert").lower()
        data = []
        for t, flag, signal_price in zip(collector.times, flags, prices):
            if not _condition_is_true(flag):
                continue
            point: dict[str, Any] = {
                "time": t,
                "side": normalized_side,
                "name": name or normalized_side,
                "message": message,
            }
            if strength is not None:
                point["strength"] = float(strength)
            if signal_price is not None and _is_valid_value(signal_price):
                point["price"] = round(float(signal_price), 8)
            if payload:
                point["payload"] = payload
            data.append(point)

        if data:
            collector.signals.append(
                {
                    "name": name or normalized_side,
                    "side": normalized_side,
                    "message": message,
                    "pane": pane,
                    "data": data,
                }
            )

    def alertcondition(
        condition: PyneSeries | np.ndarray | bool,
        title: str = "",
        message: str = "",
        side: str = "alert",
    ) -> None:
        """Pine-style alert condition helper."""
        emit_signal(
            condition,
            name=title or side,
            side=side,
            message=message,
            pane="main",
        )

    def label_func(
        text: str,
        position: str = "topright",
        color: str = "#ffffff",
        textcolor: str = "#ffffff",
        pane: str | None = None,
        style: str = "label_down",
    ) -> None:
        """Display a text label on the chart.

        Args:
            text: Text to display.
            position: "topright", "topleft", "bottomright", "bottomleft".
            color: Background color.
            textcolor: Text color.
            pane: "main" or "separate".
            style: Label style.
        """
        if pane is None:
            pane = "main"

        collector.labels.append(
            {
                "text": text,
                "position": position,
                "color": color,
                "textcolor": textcolor,
                "pane": pane,
                "style": style,
            }
        )

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
            for linefill_id, entry in list(collector._object_linefills.items()):
                if ref.id in {entry.get("line1_id"), entry.get("line2_id")}:
                    collector._object_linefills.pop(linefill_id, None)

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

    def polyline_new(
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
            x, y = _point_coordinates(point, xloc)
            serialized_points.append({"x": x, "y": y})
        object_id = collector._next_object_id("polyline")
        collector._object_polylines[object_id] = {
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
        return ObjectRef(id=object_id, kind="polyline")

    def polyline_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "polyline":
            collector._object_polylines.pop(ref.id, None)

    def label_new(
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
        if pane is None:
            pane = "main"
        if isinstance(x, ChartPoint):
            point_text = text if y is _MISSING else y
            if y is not _MISSING and text in {"bar_index", "bar_time"}:
                xloc = text
            resolved_x, resolved_y = _point_coordinates(x, xloc)
            resolved_text = str(point_text)
        else:
            if y is _MISSING:
                raise TypeError("label.new() requires x and y coordinates")
            resolved_x = _scalar_from_value(x)
            resolved_y = _scalar_from_value(y)
            resolved_text = str(text)
        object_id = collector._next_object_id("label")
        collector._object_labels[object_id] = {
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
            "pane": pane,
        }
        return ObjectRef(id=object_id, kind="label")

    def label_set_xy(ref: ObjectRef, x: Any, y: Any) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["x"] = _scalar_from_value(x)
            entry["y"] = _scalar_from_value(y)

    def label_set_point(ref: ObjectRef, point: ChartPoint) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["x"], entry["y"] = _point_coordinates(
                point,
                str(entry.get("xloc", "bar_index")),
            )

    def label_set_x(ref: ObjectRef, x: Any) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["x"] = _scalar_from_value(x)

    def label_set_y(ref: ObjectRef, y: Any) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["y"] = _scalar_from_value(y)

    def label_set_text(ref: ObjectRef, text: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["text"] = str(text)

    def label_set_color(ref: ObjectRef, color: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["color"] = color

    def label_set_textcolor(ref: ObjectRef, textcolor: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["textcolor"] = textcolor

    def label_set_style(ref: ObjectRef, style: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["style"] = style

    def label_set_size(ref: ObjectRef, size: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["size"] = size

    def label_set_xloc(ref: ObjectRef, xloc: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["xloc"] = xloc

    def label_set_yloc(ref: ObjectRef, yloc: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["yloc"] = yloc

    def label_set_tooltip(ref: ObjectRef, tooltip: str) -> None:
        entry = _label_entry(ref)
        if entry is not None:
            entry["tooltip"] = str(tooltip)

    def label_get_x(ref: ObjectRef) -> Any:
        entry = _label_entry(ref)
        return np.nan if entry is None or entry.get("x") is None else entry["x"]

    def label_get_y(ref: ObjectRef) -> Any:
        entry = _label_entry(ref)
        return np.nan if entry is None or entry.get("y") is None else entry["y"]

    def label_get_text(ref: ObjectRef) -> str:
        entry = _label_entry(ref)
        return "" if entry is None else str(entry.get("text") or "")

    def label_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "label":
            collector._object_labels.pop(ref.id, None)

    def box_new(
        left: Any,
        top: Any,
        right: Any = _MISSING,
        bottom: Any = _MISSING,
        bgcolor: str = "rgba(0,0,0,0)",
        border_color: str = "#787b86",
        border_width: int = 1,
        border_style: str = "solid",
        extend: str = "none",
        xloc: str = "bar_index",
        text: str = "",
        text_size: str = "normal",
        text_color: str = "#000000",
        text_halign: str = "center",
        text_valign: str = "middle",
        pane: str | None = None,
    ) -> ObjectRef:
        if pane is None:
            pane = "main"
        if isinstance(left, ChartPoint) or isinstance(top, ChartPoint):
            if not isinstance(left, ChartPoint) or not isinstance(top, ChartPoint):
                raise TypeError("box.new() point overload requires two chart.point values")
            if right is not _MISSING or bottom is not _MISSING:
                raise TypeError(
                    "box.new() point overload accepts drawing options as keyword arguments"
                )
            resolved_left, resolved_top = _point_coordinates(left, xloc)
            resolved_right, resolved_bottom = _point_coordinates(top, xloc)
        else:
            if right is _MISSING or bottom is _MISSING:
                raise TypeError("box.new() requires left, top, right, and bottom")
            resolved_left = _scalar_from_value(left)
            resolved_top = _scalar_from_value(top)
            resolved_right = _scalar_from_value(right)
            resolved_bottom = _scalar_from_value(bottom)
        object_id = collector._next_object_id("box")
        collector._object_boxes[object_id] = {
            "id": object_id,
            "left": resolved_left,
            "top": resolved_top,
            "right": resolved_right,
            "bottom": resolved_bottom,
            "bgcolor": bgcolor,
            "border_color": border_color,
            "border_width": int(border_width),
            "border_style": border_style,
            "extend": extend,
            "xloc": xloc,
            "text": str(text),
            "text_size": text_size,
            "text_color": text_color,
            "text_halign": text_halign,
            "text_valign": text_valign,
            "pane": pane,
        }
        return ObjectRef(id=object_id, kind="box")

    def box_set_left(ref: ObjectRef, left: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["left"] = _scalar_from_value(left)

    def box_set_top(ref: ObjectRef, top: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["top"] = _scalar_from_value(top)

    def box_set_right(ref: ObjectRef, right: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["right"] = _scalar_from_value(right)

    def box_set_bottom(ref: ObjectRef, bottom: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["bottom"] = _scalar_from_value(bottom)

    def box_set_lefttop(ref: ObjectRef, left: Any, top: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["left"] = _scalar_from_value(left)
            entry["top"] = _scalar_from_value(top)

    def box_set_rightbottom(ref: ObjectRef, right: Any, bottom: Any) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["right"] = _scalar_from_value(right)
            entry["bottom"] = _scalar_from_value(bottom)

    def box_set_top_left_point(ref: ObjectRef, point: ChartPoint) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["left"], entry["top"] = _point_coordinates(
                point,
                str(entry.get("xloc", "bar_index")),
            )

    def box_set_bottom_right_point(ref: ObjectRef, point: ChartPoint) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["right"], entry["bottom"] = _point_coordinates(
                point,
                str(entry.get("xloc", "bar_index")),
            )

    def box_set_bgcolor(ref: ObjectRef, bgcolor: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["bgcolor"] = bgcolor

    def box_set_border_color(ref: ObjectRef, border_color: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["border_color"] = border_color

    def box_set_border_width(ref: ObjectRef, border_width: int) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["border_width"] = int(border_width)

    def box_set_border_style(ref: ObjectRef, border_style: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["border_style"] = border_style

    def box_set_extend(ref: ObjectRef, extend: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["extend"] = extend

    def box_set_text(ref: ObjectRef, text: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["text"] = str(text)

    def box_set_text_color(ref: ObjectRef, text_color: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["text_color"] = text_color

    def box_set_text_size(ref: ObjectRef, text_size: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["text_size"] = text_size

    def box_set_text_halign(ref: ObjectRef, text_halign: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["text_halign"] = text_halign

    def box_set_text_valign(ref: ObjectRef, text_valign: str) -> None:
        entry = _box_entry(ref)
        if entry is not None:
            entry["text_valign"] = text_valign

    def box_get_left(ref: ObjectRef) -> Any:
        entry = _box_entry(ref)
        return np.nan if entry is None or entry.get("left") is None else entry["left"]

    def box_get_top(ref: ObjectRef) -> Any:
        entry = _box_entry(ref)
        return np.nan if entry is None or entry.get("top") is None else entry["top"]

    def box_get_right(ref: ObjectRef) -> Any:
        entry = _box_entry(ref)
        return np.nan if entry is None or entry.get("right") is None else entry["right"]

    def box_get_bottom(ref: ObjectRef) -> Any:
        entry = _box_entry(ref)
        return np.nan if entry is None or entry.get("bottom") is None else entry["bottom"]

    def box_copy(ref: ObjectRef) -> ObjectRef | None:
        entry = _box_entry(ref)
        if entry is None:
            return None
        object_id = collector._next_object_id("box")
        collector._object_boxes[object_id] = {**entry, "id": object_id}
        return ObjectRef(id=object_id, kind="box")

    def box_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "box":
            collector._object_boxes.pop(ref.id, None)

    def table_new(
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
        if pane is None:
            pane = "main"
        object_id = collector._next_object_id("table")
        collector._object_tables[object_id] = {
            "id": object_id,
            "position": position,
            "columns": int(columns),
            "rows": int(rows),
            "bgcolor": bgcolor,
            "frame_color": frame_color,
            "frame_width": int(frame_width),
            "border_color": border_color,
            "border_width": int(border_width),
            "pane": pane,
            "cells": [],
            "merges": [],
        }
        return ObjectRef(id=object_id, kind="table")

    def table_cell(
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
        entry = _table_entry(ref)
        if entry is None:
            return
        _require_table_coordinate(entry, int(column), int(row))
        cell = {
            "column": int(column),
            "row": int(row),
            "text": str(_scalar_from_value(text)),
            "text_color": text_color,
            "bgcolor": bgcolor,
            "width": width,
            "height": height,
            "text_halign": text_halign,
            "text_valign": text_valign,
        }
        _upsert_table_cell(entry, cell)

    def table_clear(ref: ObjectRef) -> None:
        entry = _table_entry(ref)
        if entry is not None:
            entry["cells"] = []
            entry["merges"] = []

    def table_merge_cells(
        ref: ObjectRef,
        start_column: int,
        start_row: int,
        end_column: int,
        end_row: int,
    ) -> None:
        entry = _table_entry(ref)
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
        entry["merges"].sort(
            key=lambda item: (item["start_row"], item["start_column"])
        )

    def table_set_position(ref: ObjectRef, position: str) -> None:
        entry = _table_entry(ref)
        if entry is not None:
            entry["position"] = position

    def table_set_bgcolor(ref: ObjectRef, bgcolor: str) -> None:
        entry = _table_entry(ref)
        if entry is not None:
            entry["bgcolor"] = bgcolor

    def table_set_frame_color(ref: ObjectRef, frame_color: str) -> None:
        entry = _table_entry(ref)
        if entry is not None:
            entry["frame_color"] = frame_color

    def table_set_border_color(ref: ObjectRef, border_color: str) -> None:
        entry = _table_entry(ref)
        if entry is not None:
            entry["border_color"] = border_color

    def table_delete(ref: ObjectRef) -> None:
        if isinstance(ref, ObjectRef) and ref.kind == "table":
            collector._object_tables.pop(ref.id, None)

    def _upsert_table_cell(entry: dict[str, Any], cell: dict[str, Any]) -> None:
        cells = entry.setdefault("cells", [])
        for idx, existing in enumerate(cells):
            if existing.get("column") == cell["column"] and existing.get("row") == cell["row"]:
                cells[idx] = cell
                return
        cells.append(cell)
        cells.sort(key=lambda item: (item.get("row", 0), item.get("column", 0)))

    def _require_table_coordinate(entry: dict[str, Any], column: int, row: int) -> None:
        if column < 0 or column >= int(entry["columns"]):
            raise IndexError(f"table column {column} is outside the table")
        if row < 0 or row >= int(entry["rows"]):
            raise IndexError(f"table row {row} is outside the table")

    return assemble_plot_namespace(collector, locals())
