"""Assembly of Pine-style plot and drawing namespaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..series import PyneSeries
from .collector import OutputCollector
from .objects import _CallableNamespace, _DrawingNamespace, _Namespace


def assemble_plot_namespace(
    collector: OutputCollector,
    functions: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble the public namespace from collector-bound implementations."""
    get = functions.__getitem__
    plot = get("plot")
    hline = get("hline")
    plot.style_line = "line"
    plot.style_histogram = "histogram"
    plot.style_columns = "histogram"
    hline.style_solid = "solid"
    hline.style_dashed = "dashed"
    hline.style_dotted = "dotted"

    def add_line(
        data: PyneSeries | np.ndarray | list,
        title: str = "",
        color: str = "#f59e0b",
        pane: str | None = None,
        line_width: int | None = None,
        line_style: str | int | None = None,
        overlay: bool | None = None,
        type: str = "line",
        color_data: list | PyneSeries | np.ndarray | None = None,
        colorData: list | PyneSeries | np.ndarray | None = None,
        linewidth: int | None = None,
        style: str | int | None = None,
        **_: Any,
    ) -> None:
        """Legacy ``add_line()`` compatibility wrapper."""
        resolved_pane = pane
        if resolved_pane is None:
            resolved_pane = "main" if overlay is None or overlay else "separate"

        resolved_width = linewidth if linewidth is not None else line_width
        if resolved_width is None:
            resolved_width = 2

        resolved_style = style if style is not None else line_style
        if resolved_style is None:
            resolved_style = "solid"

        resolved_color_data = colorData if colorData is not None else color_data
        series_type = (type or "line").lower()
        if series_type in {"histogram", "bar", "columns", "column"}:
            values = get("_values_from_data")(data)
            points = []
            for idx, (timestamp, value) in enumerate(zip(collector.times, values)):
                if not get("_is_valid_value")(value):
                    continue
                point = {"time": timestamp, "value": float(value)}
                point_color = get("_color_for_index")(
                    resolved_color_data,
                    idx,
                    timestamp,
                )
                if point_color:
                    point["color"] = point_color
                points.append(point)

            collector.histograms.append(
                {
                    "title": title,
                    "color_up": color,
                    "color_down": color,
                    "pane": resolved_pane,
                    "data": points,
                }
            )
            return

        plot(
            data,
            title=title,
            color=color,
            linewidth=resolved_width,
            style=resolved_style,
            overlay=overlay,
            pane=resolved_pane,
            color_array=resolved_color_data,
        )

    line_namespace = _DrawingNamespace(
        all_getter=lambda: get("_object_refs")("line", collector._object_lines),
        new=get("line_new"),
        set_xy1=get("line_set_xy1"),
        set_xy2=get("line_set_xy2"),
        set_first_point=get("line_set_first_point"),
        set_second_point=get("line_set_second_point"),
        set_x1=get("line_set_x1"),
        set_y1=get("line_set_y1"),
        set_x2=get("line_set_x2"),
        set_y2=get("line_set_y2"),
        set_color=get("line_set_color"),
        set_width=get("line_set_width"),
        set_style=get("line_set_style"),
        set_extend=get("line_set_extend"),
        get_x1=get("line_get_x1"),
        get_y1=get("line_get_y1"),
        get_x2=get("line_get_x2"),
        get_y2=get("line_get_y2"),
        delete=get("line_delete"),
        style_solid="solid",
        style_dashed="dashed",
        style_dotted="dotted",
        extend_none="none",
        extend_left="left",
        extend_right="right",
        extend_both="both",
    )
    linefill_namespace = _DrawingNamespace(
        all_getter=lambda: get("_object_refs")(
            "linefill", collector._object_linefills
        ),
        new=get("linefill_new"),
        set_color=get("linefill_set_color"),
        delete=get("linefill_delete"),
    )
    polyline_namespace = _DrawingNamespace(
        all_getter=lambda: get("_object_refs")(
            "polyline", collector._object_polylines
        ),
        new=get("polyline_new"),
        delete=get("polyline_delete"),
    )
    label_namespace = _CallableNamespace(
        get("label_func"),
        new=get("label_new"),
        set_xy=get("label_set_xy"),
        set_point=get("label_set_point"),
        set_x=get("label_set_x"),
        set_y=get("label_set_y"),
        set_text=get("label_set_text"),
        set_color=get("label_set_color"),
        set_textcolor=get("label_set_textcolor"),
        set_style=get("label_set_style"),
        set_size=get("label_set_size"),
        set_xloc=get("label_set_xloc"),
        set_yloc=get("label_set_yloc"),
        set_tooltip=get("label_set_tooltip"),
        get_x=get("label_get_x"),
        get_y=get("label_get_y"),
        get_text=get("label_get_text"),
        delete=get("label_delete"),
        style_label_up="label_up",
        style_label_down="label_down",
        style_label_left="label_left",
        style_label_right="label_right",
        style_label_center="label_center",
        style_circle="circle",
        style_none="none",
        style_xcross="xcross",
        style_labelup="label_up",
        style_labeldown="label_down",
        style_label_upper_right="label_upper_right",
        style_label_lower_right="label_lower_right",
    )
    box_namespace = _DrawingNamespace(
        all_getter=lambda: get("_object_refs")("box", collector._object_boxes),
        new=get("box_new"),
        set_left=get("box_set_left"),
        set_top=get("box_set_top"),
        set_right=get("box_set_right"),
        set_bottom=get("box_set_bottom"),
        set_lefttop=get("box_set_lefttop"),
        set_rightbottom=get("box_set_rightbottom"),
        set_top_left_point=get("box_set_top_left_point"),
        set_bottom_right_point=get("box_set_bottom_right_point"),
        set_bgcolor=get("box_set_bgcolor"),
        set_border_color=get("box_set_border_color"),
        set_border_width=get("box_set_border_width"),
        set_border_style=get("box_set_border_style"),
        set_extend=get("box_set_extend"),
        set_text=get("box_set_text"),
        set_text_color=get("box_set_text_color"),
        set_text_size=get("box_set_text_size"),
        set_text_halign=get("box_set_text_halign"),
        set_text_valign=get("box_set_text_valign"),
        get_left=get("box_get_left"),
        get_top=get("box_get_top"),
        get_right=get("box_get_right"),
        get_bottom=get("box_get_bottom"),
        copy=get("box_copy"),
        delete=get("box_delete"),
        border_style_solid="solid",
        border_style_dashed="dashed",
        border_style_dotted="dotted",
    )
    table_namespace = _Namespace(
        new=get("table_new"),
        cell=get("table_cell"),
        clear=get("table_clear"),
        merge_cells=get("table_merge_cells"),
        set_position=get("table_set_position"),
        set_bgcolor=get("table_set_bgcolor"),
        set_frame_color=get("table_set_frame_color"),
        set_border_color=get("table_set_border_color"),
        delete=get("table_delete"),
    )

    return {
        "indicator": get("indicator"),
        "study": get("indicator"),
        "plot": plot,
        "plotcandle": get("plotcandle"),
        "bar": get("bar"),
        "hline": hline,
        "fill": get("fill"),
        "bgcolor": get("bgcolor"),
        "marker": get("marker"),
        "plotshape": get("plotshape"),
        "plotchar": get("plotchar"),
        "plotarrow": get("plotarrow"),
        "barcolor": get("barcolor"),
        "emit_signal": get("emit_signal"),
        "alertcondition": get("alertcondition"),
        "line": line_namespace,
        "linefill": linefill_namespace,
        "polyline": polyline_namespace,
        "label": label_namespace,
        "box": box_namespace,
        "table": table_namespace,
        "add_line": add_line,
        "shape": _enum_namespace(
            xcross="xcross",
            cross="cross",
            circle="circle",
            triangleup="triangle_up",
            triangledown="triangle_down",
            flag="flag",
            arrowup="arrow_up",
            arrowdown="arrow_down",
            labelup="label_up",
            labeldown="label_down",
            square="square",
            diamond="diamond",
        ),
        "location": _enum_namespace(
            abovebar="above",
            belowbar="below",
            top="above",
            bottom="below",
            absolute="absolute",
        ),
        "position": _enum_namespace(
            top_left="top_left",
            top_center="top_center",
            top_right="top_right",
            middle_left="middle_left",
            middle_center="middle_center",
            middle_right="middle_right",
            bottom_left="bottom_left",
            bottom_center="bottom_center",
            bottom_right="bottom_right",
        ),
        "size": _enum_namespace(
            auto="auto",
            tiny="tiny",
            small="small",
            normal="normal",
            large="large",
            huge="huge",
        ),
        "display": _enum_namespace(
            none="none",
            all="all",
            pane="pane",
            data_window="data_window",
            status_line="status_line",
        ),
        "format": _enum_namespace(
            inherit="inherit",
            mintick="mintick",
            price="price",
            volume="volume",
            percent="percent",
        ),
        "scale": _enum_namespace(left="left", right="right", none="none"),
        "xloc": _enum_namespace(bar_index="bar_index", bar_time="bar_time"),
        "yloc": _enum_namespace(
            price="price", abovebar="abovebar", belowbar="belowbar"
        ),
        "extend": _enum_namespace(
            none="none", left="left", right="right", both="both"
        ),
        "text": _enum_namespace(
            align_left="left",
            align_center="center",
            align_right="right",
            align_top="top",
            align_middle="middle",
            align_bottom="bottom",
        ),
    }


def _enum_namespace(**values: Any) -> _Namespace:
    return _Namespace(**values)
