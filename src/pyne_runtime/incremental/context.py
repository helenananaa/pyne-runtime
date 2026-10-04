"""Per-session incremental callback context."""
from __future__ import annotations

import copy
import math
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import asdict
from types import FunctionType, ModuleType
from typing import Any

from ..barstate import PyneIncrementalBarState
from ..metadata import SessionInfo, SymbolInfo, TimeframeInfo
from ..security import PyneSecurityError
from ..trace import PyneTraceRecorder
from .bar import IncrementalBar, _session_info_for_bar, copy_bar_payload
from .drawing import IncrementalDrawingMixin, _filter_object_events
from .limits import (
    IncrementalLimits,
    StateCell,
    _StateHistory,
    _STATE_HISTORY_TOKEN,
    Window,
    _LimitTracker,
    _state_payload_items,
)
from .result import IncrementalPyneResult
from .strategy import IncrementalStrategyNamespace
from .ta import IncrementalTaNamespace


class IncrementalContext(IncrementalDrawingMixin):
    """Per-session context exposed to incremental Pyne callbacks."""

    def __init__(
        self,
        *,
        params: Mapping[str, Any],
        meta: dict[str, Any] | None = None,
        limits: IncrementalLimits | None = None,
        syminfo: SymbolInfo | None = None,
        timeframe: TimeframeInfo | None = None,
        session: SessionInfo | None = None,
        max_drawing_objects: int | None = None,
        trace: PyneTraceRecorder | None = None,
    ) -> None:
        self.params = params
        self.meta = meta or {}
        self._limits = limits or IncrementalLimits(enabled=False)
        self._limit_tracker = _LimitTracker(self._limits)
        self.ta = IncrementalTaNamespace(self._limit_tracker)
        self.syminfo = syminfo or SymbolInfo()
        self.timeframe = timeframe or TimeframeInfo()
        self._default_session = session or SessionInfo()
        self.session = self._default_session
        self.strategy = IncrementalStrategyNamespace(self)
        self._states: dict[str, StateCell] = {}
        self._function_history_cells: set[str] = set()
        self._varip_states: dict[str, StateCell] = {}
        self._windows: dict[str, Window] = {}
        self._series: dict[str, dict[str, Any]] = {}
        self._candles: dict[str, dict[str, Any]] = {}
        self._markers: dict[str, dict[str, Any]] = {}
        self._current_series: dict[str, dict[str, Any]] = {}
        self._current_candles: dict[str, dict[str, Any]] = {}
        self._current_markers: dict[str, dict[str, Any]] = {}
        self._object_lines: dict[str, dict[str, Any]] = {}
        self._object_labels: dict[str, dict[str, Any]] = {}
        self._object_boxes: dict[str, dict[str, Any]] = {}
        self._object_tables: dict[str, dict[str, Any]] = {}
        self._object_linefills: dict[str, dict[str, Any]] = {}
        self._object_polylines: dict[str, dict[str, Any]] = {}
        self._table_cell_indices: dict[str, dict[tuple[int, int], int]] = {}
        self._object_events: list[dict[str, Any]] = []
        self._current_object_events: list[dict[str, Any]] = []
        self._request_bars_storage: list[dict[str, Any]] = []
        self._request_history_exposed = False
        self._preview_request_source: list[dict[str, Any]] | None = None
        self._preview_request_memo: dict[int, Any] | None = None
        self._output_names: dict[tuple[str, str], str] = {}
        self._request_diagnostics: list[dict[str, Any]] = []
        self._request_diagnostics_dropped = 0
        self._request_namespace: Any = None
        self._object_counter = 0
        self._max_drawing_objects = max_drawing_objects
        self.trace = trace or PyneTraceRecorder()
        self.current_bar: IncrementalBar | None = None
        self.bar_index = -1
        self.last_bar_index = -1
        self.barstate = PyneIncrementalBarState()

    @property
    def request(self) -> Any:
        if self._request_namespace is None:
            raise PyneSecurityError(
                "ctx.request.* can only be used inside incremental callbacks"
            )
        return self._request_namespace

    @property
    def _request_bars(self) -> list[dict[str, Any]]:
        self._request_history_exposed = True
        return self._request_bars_for_runtime()

    def _request_bars_for_runtime(self) -> list[dict[str, Any]]:
        # A preview that does not read request history never copies it. Access
        # through this property, including user aliases, materializes an isolated
        # graph using the same memo as its context and callback globals.
        if self._preview_request_source is not None:
            self._request_bars_storage = copy.deepcopy(
                self._preview_request_source, self._preview_request_memo
            )
            self._preview_request_source = None
            self._preview_request_memo = None
        return self._request_bars_storage

    @_request_bars.setter
    def _request_bars(self, values: list[dict[str, Any]]) -> None:
        self._request_history_exposed = True
        self._request_bars_storage = values
        self._preview_request_source = None
        self._preview_request_memo = None

    def _request_source_for_runtime(self) -> list[dict[str, Any]] | None:
        # Once Python has an alias to this graph it may edit any historical
        # row. Keep the ordinary copying/validation path for that context.
        if self._request_history_exposed:
            return None
        return (self._preview_request_source if self._preview_request_source is not None
                else self._request_bars_storage)

    def preview_copy_roots(self) -> tuple[Any, ...]:
        """Values actually copied for preview, excluding runtime-only logs."""
        excluded = {
            "_series", "_candles", "_markers", "_object_events",
            "_current_series", "_current_candles", "_current_markers",
            "_current_object_events", "_request_diagnostics", "current_bar",
            "_request_bars_storage", "_preview_request_source", "_preview_request_memo",
        }
        roots = tuple(value for name, value in vars(self).items() if name not in excluded)
        return (*roots, *self.function_history_roots())

    def function_history_roots(self) -> tuple[Any, ...]:
        return tuple(
            object.__getattribute__(self._states[key], "_StateCell__history")._raw_slice(
                slice(None), _STATE_HISTORY_TOKEN
            )
            for key in self._function_history_cells if key in self._states
        )

    def rebind_function_histories(self, memo: dict[int, Any]) -> None:
        for key in self._function_history_cells:
            cell = self._states.get(key)
            if cell is None:
                continue
            history = object.__getattribute__(cell, "_StateCell__history")
            values = copy.deepcopy(history._raw_slice(slice(None), _STATE_HISTORY_TOKEN), memo)
            object.__setattr__(
                cell, "_StateCell__history", _StateHistory(maxlen=history.maxlen, values=values)
            )

    def clone_for_preview(self, *, memo: dict[int, Any] | None = None) -> "IncrementalContext":
        discarded: dict[str, Any] = {
            "_series": {},
            "_candles": {},
            "_markers": {},
            "_object_events": [],
            "_current_series": {},
            "_current_candles": {},
            "_current_markers": {},
            "_current_object_events": [],
            "_request_diagnostics": [],
            "_request_diagnostics_dropped": (
                self._request_diagnostics_dropped + len(self._request_diagnostics)
            ),
            "current_bar": None,
        }
        memo = {} if memo is None else memo
        clone = memo.setdefault(id(self), object.__new__(type(self)))
        state_mappings: dict[str, dict[str, StateCell]] = {}
        state_pairs: list[tuple[StateCell, StateCell]] = []
        for name in ("_states", "_varip_states"):
            source = getattr(self, name)
            cloned_mapping: dict[str, StateCell] = {}
            memo[id(source)] = cloned_mapping
            state_mappings[name] = cloned_mapping
            for key, cell in source.items():
                cell_clone = memo.get(id(cell))
                if cell_clone is None:
                    cell_clone = object.__new__(type(cell))
                    memo[id(cell)] = cell_clone
                    state_pairs.append((cell, cell_clone))
                cloned_mapping[copy.deepcopy(key, memo)] = cell_clone
        for name, value in vars(self).items():
            if name in {"_request_bars_storage", "_preview_request_source", "_preview_request_memo"}:
                continue
            if name in discarded:
                setattr(clone, name, discarded[name])
            elif name in state_mappings:
                setattr(clone, name, state_mappings[name])
            else:
                setattr(clone, name, copy.deepcopy(value, memo))
        for source, cell_clone in state_pairs:
            object.__setattr__(
                cell_clone,
                "_StateCell__history",
                object.__getattribute__(source, "_StateCell__history"),
            )
            object.__setattr__(cell_clone, "_StateCell__history_writable", False)
            object.__setattr__(
                cell_clone,
                "_StateCell__limit_tracker",
                clone._limit_tracker,
            )
            cell_clone.value = copy.deepcopy(source.value, memo)
        clone.rebind_function_histories(memo)
        # Historical output/event buffers above were discarded. Their counters
        # must describe the actual preview buffers, while registered channels,
        # shared state history and copied strategy logs retain their budgets.
        clone._limit_tracker.output_points = 0
        clone._limit_tracker.object_events = 0
        source_bars = self._request_bars_for_runtime()
        if id(source_bars) in memo:
            clone._request_bars = memo[id(source_bars)]
        else:
            clone._request_bars_storage = []
            clone._preview_request_source = source_bars
            clone._preview_request_memo = memo
        return clone

    def clear_outputs(self) -> None:
        self._series = {}
        self._candles = {}
        self._markers = {}
        self._current_series = {}
        self._current_candles = {}
        self._current_markers = {}
        self._limit_tracker.clear_output()

    def prune_before_time(self, cutoff_time: int) -> None:
        """Drop runtime-managed historical output older than ``cutoff_time``."""

        cutoff = int(cutoff_time)
        for collection in (self._series, self._candles, self._markers):
            for key in list(collection):
                entry = collection[key]
                _prune_time_prefix(entry.get("data") or [], cutoff)
                if not entry["data"]:
                    collection.pop(key, None)
        _prune_time_prefix(self._object_events, cutoff)
        _prune_time_prefix(self._request_bars_for_runtime(), cutoff)
        self.strategy.prune_history(cutoff)
        series_keys = {f"series:{key}" for key in self._series}
        series_keys.update(f"candle:{key}" for key in self._candles)
        series_keys.update(f"marker:{key}" for key in self._markers)
        self._limit_tracker.output_series_keys = series_keys
        self._limit_tracker.output_series = len(series_keys)
        self._limit_tracker.output_points = sum(
            len(entry.get("data") or [])
            for collection in (self._series, self._candles, self._markers)
            for entry in collection.values()
        )
        self._limit_tracker.object_events = len(self._object_events)

    def begin_bar(
        self,
        bar: IncrementalBar,
        *,
        bar_index: int,
        last_bar_index: int,
        barstate: PyneIncrementalBarState,
    ) -> None:
        self._request_diagnostics_dropped += len(self._request_diagnostics)
        self._request_diagnostics = []
        self._current_series = {}
        self._current_candles = {}
        self._current_markers = {}
        self._current_object_events = []
        bar.bar_index = bar_index
        bar.last_bar_index = last_bar_index
        bar.is_first = barstate.isfirst
        bar.is_last = barstate.islast
        bar.is_history = barstate.ishistory
        bar.is_realtime = barstate.isrealtime
        bar.is_new = barstate.isnew
        bar.is_last_confirmed_history = barstate.islastconfirmedhistory
        self.current_bar = bar
        self.bar_index = bar_index
        self.last_bar_index = last_bar_index
        self.barstate = barstate
        if barstate.isconfirmed:
            self._limit_tracker.replace_varip_payload(0)
            self._varip_states = {}
        self.session = _session_info_for_bar(bar, self._default_session)
        self.strategy.begin_bar()
        self.trace._emit_runtime(
            "bar.begin",
            time=bar.time,
            barIndex=bar_index,
            confirmed=barstate.isconfirmed,
            realtime=barstate.isrealtime,
            new=barstate.isnew,
        )

    def request_bars(self) -> list[dict[str, Any]]:
        """Return committed chart bars plus the active preview/confirmed bar."""
        bars = copy.deepcopy(self._request_bars_for_runtime())
        if self.current_bar is not None:
            current = copy.deepcopy(self.current_bar.raw)
            if not bars or int(bars[-1]["time"]) != self.current_bar.time:
                bars.append(current)
            else:
                bars[-1] = current
        return bars

    def commit_request_bar(self) -> None:
        if self.current_bar is None:
            return
        current = copy_bar_payload(self.current_bar.raw)
        bars = self._request_bars_for_runtime()
        if bars and int(bars[-1]["time"]) == self.current_bar.time:
            bars[-1] = current
        else:
            bars.append(current)

    def record_request_diagnostics(self, values: list[dict[str, Any]]) -> None:
        self._request_diagnostics.extend(copy.deepcopy(values))
        for item in values:
            self.trace.emit("request.complete", **item)

    def state(self, name: str, default: Any = None) -> StateCell:
        key = str(name)
        if key not in self._states:
            self._ensure_state_key_available()
            self._states[key] = StateCell(
                copy.deepcopy(default),
                max_history=self._limits.max_state_history,
                limit_tracker=self._limit_tracker,
            )
        return self._states[key]

    def varip(self, name: str, default: Any = None) -> StateCell:
        """Return an intrabar state cell for realtime preview callbacks.

        ``varip`` cells persist across preview updates for the same realtime
        bar, but reset before confirmed callbacks and when a new preview bar
        starts. This mirrors Pine's intrabar-state intent without letting
        preview state mutate the persistent session context.
        """
        key = str(name)
        if key not in self._varip_states:
            self._ensure_state_key_available()
            existing_payload = self._measure_varip_payload()
            previous_payload = self._limit_tracker.varip_payload_items
            self._limit_tracker.replace_varip_payload(
                existing_payload + _state_payload_items(default)
            )
            try:
                self._varip_states[key] = StateCell(
                    copy.deepcopy(default),
                    max_history=self._limits.max_state_history,
                    limit_tracker=self._limit_tracker,
                )
                self.sync_varip_payload()
            except Exception:
                self._varip_states.pop(key, None)
                self._limit_tracker.varip_payload_items = previous_payload
                raise
        return self._varip_states[key]

    def adopt_varip_states(self, states: dict[str, StateCell]) -> None:
        self._varip_states = states
        for cell in states.values():
            object.__setattr__(
                cell,
                "_StateCell__limit_tracker",
                self._limit_tracker,
            )
        self.sync_varip_payload()

    def sync_varip_payload(self) -> None:
        self._limit_tracker.replace_varip_payload(self._measure_varip_payload())

    def _measure_varip_payload(self) -> int:
        return sum(_state_payload_items(cell.value) for cell in self._varip_states.values())

    def commit_state_history(self) -> None:
        for key, cell in self._states.items():
            cell.commit_history()
            if _contains_function(cell.value):
                self._function_history_cells.add(key)

    def _ensure_state_key_available(self) -> None:
        if not self._limits.enabled:
            return
        key_count = len(self._states) + len(self._varip_states)
        if self._limits.max_state_keys is not None and key_count >= self._limits.max_state_keys:
            raise PyneSecurityError(
                f"Incremental state keys exceed max_state_keys limit {self._limits.max_state_keys}"
            )

    def window(self, name: str, size: int) -> Window:
        key = str(name)
        if key not in self._windows:
            self._limit_tracker.reserve_window(size, label=f"window:{key}")
            self._windows[key] = Window(size)
        return self._windows[key]

    def _output_id(self, kind: str, name: str) -> str:
        key = (kind, str(name))
        if key in self._output_names:
            return self._output_names[key]
        stem = _slug(name)
        used = {value for (channel, _), value in self._output_names.items() if channel == kind}
        candidate = stem
        suffix = 2
        while candidate in used:
            candidate = f"{stem}_{suffix}"
            suffix += 1
        self._output_names[key] = candidate
        return candidate

    def plot(
        self,
        name_or_value: Any,
        value: Any = None,
        *,
        title: str | None = None,
        color: str = "#f59e0b",
        pane: str | None = None,
        linewidth: int = 2,
        style: str = "solid",
        type: str = "line",
    ) -> None:
        if self.current_bar is None:
            return

        if isinstance(name_or_value, str):
            name = name_or_value
            point_value = value
        else:
            name = title or "plot"
            point_value = name_or_value

        if point_value is None:
            return
        try:
            number = float(point_value)
        except (TypeError, ValueError):
            return
        if math.isnan(number):
            return

        resolved_pane = pane or self._default_pane()
        local_id = self._output_id("series", name)
        normalized_type = "histogram" if _is_histogram_style(style) else type
        self._limit_tracker.reserve_output_point(series_key=f"series:{local_id}")
        entry = self._series.setdefault(local_id, {
            "id": local_id,
            "title": title or name,
            "color": color,
            "linewidth": linewidth,
            "style": style,
            "type": normalized_type,
            "pane": resolved_pane,
            "data": [],
        })
        point: dict[str, Any] = {
            "time": self.current_bar.time,
            "value": number,
        }
        if normalized_type == "histogram":
            point["color"] = color
        entry["data"].append(point)
        current_entry = self._current_series.setdefault(
            local_id,
            {**entry, "data": []},
        )
        current_entry["data"].append(point)
        self.trace._emit_runtime(
            "output.plot",
            time=self.current_bar.time,
            name=name,
            value=number,
            pane=resolved_pane,
            type=normalized_type,
        )

    def marker(
        self,
        condition: bool,
        *,
        text: str = "",
        shape: str = "circle",
        color: str = "#f59e0b",
        position: str = "above",
        size: str = "normal",
        pane: str | None = None,
    ) -> None:
        if self.current_bar is None or not condition:
            return
        resolved_pane = pane or self._default_pane()
        key = self._output_id("marker", text or shape or "marker")
        self._limit_tracker.reserve_output_point(series_key=f"marker:{key}")
        entry = self._markers.setdefault(key, {
            "id": key,
            "shape": shape,
            "color": color,
            "text": text,
            "position": position,
            "size": size,
            "pane": resolved_pane,
            "data": [],
        })
        point = {
            "time": self.current_bar.time,
            "shape": shape,
            "color": color,
            "text": text,
            "position": position,
            "size": size,
            "pane": resolved_pane,
        }
        entry["data"].append(point)
        current_entry = self._current_markers.setdefault(
            key,
            {**entry, "data": []},
        )
        current_entry["data"].append(point)
        self.trace._emit_runtime(
            "output.marker",
            time=self.current_bar.time,
            text=text,
            shape=shape,
            pane=resolved_pane,
        )

    def plotcandle(
        self,
        open: Any,
        high: Any,
        low: Any,
        close: Any,
        title: str = "",
        color: str | None = None,
        wickcolor: str | None = None,
        bordercolor: str | None = None,
        *,
        show_last: int | None = None,
        force_overlay: bool = False,
        pane: str | None = None,
        display: str | None = None,
        format: str | None = None,
        precision: int | None = None,
        **_: Any,
    ) -> None:
        """Emit one current-bar candle using output-schema v2."""
        if self.current_bar is None:
            return
        values = tuple(_finite_number(value) for value in (open, high, low, close))
        if any(value is None for value in values):
            return
        name = title or "plotcandle"
        local_id = self._output_id("candle", name)
        self._limit_tracker.reserve_output_point(series_key=f"candle:{local_id}")
        entry = self._candles.setdefault(
            local_id,
            {
                "title": name,
                "pane": pane or ("main" if force_overlay else self._default_pane()),
                "data": [],
                **_display_options(display=display, format=format, precision=precision),
            },
        )
        point: dict[str, Any] = {
            "time": self.current_bar.time,
            "open": values[0],
            "high": values[1],
            "low": values[2],
            "close": values[3],
        }
        if color:
            point["color"] = str(color)
        if wickcolor:
            point["wickcolor"] = str(wickcolor)
        if bordercolor:
            point["bordercolor"] = str(bordercolor)
        entry["data"].append(point)
        if show_last is not None:
            keep = max(int(show_last), 0)
            entry["data"] = entry["data"][-keep:] if keep else []
        self._current_candles[local_id] = {**entry, "data": [point]}

    def _default_pane(self) -> str:
        return "main" if self.meta.get("overlay", True) else "separate"


    def to_result(
        self,
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        current_bar_range = self._is_current_bar_range(start_s=start_s, end_s=end_s)
        series = self._current_series if current_bar_range else self._series
        candle_series = self._current_candles if current_bar_range else self._candles
        marker_series = self._current_markers if current_bar_range else self._markers
        lines = []
        for item in series.values():
            data = _filter_points(item.get("data") or [], start_s, end_s)
            if not data:
                continue
            line = {**item, "data": data}
            lines.append({
                "id": line["id"],
                "name": line.get("title", line["id"]),
                "color": line.get("color", "#f59e0b"),
                "type": line.get("type", "line"),
                "pane": line.get("pane", "main"),
                "lineWidth": line.get("linewidth", 2),
                "lineStyle": _style_to_int(line.get("style", "solid")),
                "style": line.get("style", "solid"),
                "data": data,
            })

        markers = []
        for item in marker_series.values():
            data = _filter_points(item.get("data") or [], start_s, end_s)
            if data:
                markers.append({**item, "data": data})

        output: dict[str, Any] = {}
        line_outputs = [line for line in lines if line.get("type") != "histogram"]
        histogram_outputs = [line for line in lines if line.get("type") == "histogram"]
        if line_outputs:
            output["lines"] = [
                {
                    "id": line.get("id"),
                    "title": line.get("name"),
                    "color": line.get("color"),
                    "linewidth": line.get("lineWidth", 2),
                    "style": _line_output_style(line.get("style", "solid")),
                    "pane": line.get("pane", "main"),
                    "data": line.get("data") or [],
                }
                for line in line_outputs
            ]
        if histogram_outputs:
            output["histograms"] = [
                {
                    "title": line.get("name"),
                    "color_up": line.get("color"),
                    "color_down": line.get("color"),
                    "pane": line.get("pane", "main"),
                    "data": line.get("data") or [],
                }
                for line in histogram_outputs
            ]
        candles = []
        for item in candle_series.values():
            data = _filter_points(item.get("data") or [], start_s, end_s)
            if data:
                candles.append({**item, "data": data})
        if candles:
            output["candles"] = candles
        if markers:
            output["markers"] = markers
        if self.strategy.touched:
            output["strategy"] = self.strategy.to_report()
        objects = self._objects_snapshot()
        if objects:
            output["objects"] = objects
        event_source = self._current_object_events if current_bar_range else self._object_events
        object_events = _filter_object_events(event_source, start_s, end_s)
        if object_events:
            output["object_events"] = object_events

        trace_snapshot = self.trace.snapshot()
        return IncrementalPyneResult(
            ok=True,
            lines=lines,
            output=output,
            meta={
                **copy.deepcopy(self.meta),
                "mode": "incremental",
                "bar_index": self.bar_index,
                "last_bar_index": self.last_bar_index,
                "barstate": asdict(self.barstate),
                **(
                    {
                        "requestDiagnostics": copy.deepcopy(self._request_diagnostics),
                        "requestDiagnosticsInfo": {
                            "scope": "current_bar",
                            "barTime": self.current_bar.time if self.current_bar else None,
                            "retained": len(self._request_diagnostics),
                            "dropped": self._request_diagnostics_dropped,
                            "truncated": self._request_diagnostics_dropped > 0,
                        },
                    }
                    if self._request_diagnostics or self._request_diagnostics_dropped
                    else {}
                ),
                **({"trace": trace_snapshot} if trace_snapshot is not None else {}),
            },
        )

    def _is_current_bar_range(
        self,
        *,
        start_s: int | None,
        end_s: int | None,
    ) -> bool:
        return (
            self.current_bar is not None
            and start_s is not None
            and end_s is not None
            and start_s == self.current_bar.time
            and end_s == self.current_bar.time
        )


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value).strip()).strip("_").lower()
    return normalized or "plot"

def _filter_points(
    points: list[dict[str, Any]],
    start_s: int | None,
    end_s: int | None,
) -> list[dict[str, Any]]:
    if start_s is None and end_s is None:
        return [copy_bar_payload(point) for point in points]
    filtered = []
    for point in points:
        try:
            ts = int(point.get("time"))
        except (TypeError, ValueError):
            continue
        if start_s is not None and ts < start_s:
            continue
        if end_s is not None and ts > end_s:
            continue
        filtered.append(copy_bar_payload(point))
    return filtered


def _prune_time_prefix(points: list[dict[str, Any]], cutoff: int) -> None:
    """Remove an expired prefix of append-ordered runtime history."""
    if not points or _point_time(points[0]) >= cutoff:
        return
    low, high = 0, len(points)
    while low < high:
        middle = (low + high) // 2
        if _point_time(points[middle]) < cutoff:
            low = middle + 1
        else:
            high = middle
    del points[:low]


def _contains_function(value: Any) -> bool:
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, FunctionType):
            return True
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ModuleType, type)):
            continue
        if isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset, deque)):
            pending.extend(current)
        elif isinstance(current, StateCell):
            pending.append(current.value)
        elif hasattr(current, "__dict__"):
            pending.extend(vars(current).values())
    return False


def _point_time(item: Mapping[str, Any]) -> int:
    try:
        return int(item.get("time", -1))
    except (TypeError, ValueError):
        return -1


def _finite_number(value: Any) -> float | None:
    if isinstance(value, StateCell):
        value = value.value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _display_options(
    *,
    display: str | None,
    format: str | None,
    precision: int | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if display is not None:
        options["display"] = display
    if format is not None:
        options["format"] = format
    if precision is not None:
        options["precision"] = int(precision)
    return options

def _style_to_int(style: Any) -> int:
    if isinstance(style, int):
        return style
    normalized = str(style or "solid").lower()
    if normalized in {"dashed", "dash"}:
        return 2
    if normalized in {"dotted", "dot"}:
        return 1
    return 0

def _is_histogram_style(style: Any) -> bool:
    return str(style or "").lower() in {"histogram", "columns", "column", "bar"}

def _line_output_style(style: Any) -> str:
    if isinstance(style, str):
        normalized = style.lower()
        if normalized in {"dashed", "dash"}:
            return "dashed"
        if normalized in {"dotted", "dot"}:
            return "dotted"
        return "solid"
    return {1: "dotted", 2: "dashed"}.get(int(style or 0), "solid")
