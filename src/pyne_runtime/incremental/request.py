"""Incremental facade over the versioned batch request-provider contract."""

from __future__ import annotations

import copy
import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from ..collections import PyneArray
from ..context import PyneContext
from ..data import PyneData
from ..request import LowerTimeframeSeries, RequestModule
from ..request._indexed import IndexedRows, RowIndex, SequenceWindow
from ..request.errors import PyneRequestError, RequestProviderErrorCategory
from ..request.provider import DataProvider, _request_finalized_through
from ..request.module import _timeframe_seconds_from_text
from ..series import PyneSeries
from ..settings import PyneSettings
from ._request_chart import ChartHistoryIndex


class IncrementalRequestModule:
    """Evaluate request expressions against chart history through a typed Provider.

    Batch ``RequestModule`` remains the single alignment/error implementation.
    Field requests use derived timeline views. Python expression thunks retain
    full requested contexts. A bounded cache stores validated provider rows.
    """

    def __init__(
        self,
        context_getter: Callable[[], Any],
        *,
        settings: PyneSettings,
        provider: DataProvider | None,
    ) -> None:
        self._context_getter = context_getter
        self._settings = settings
        self._provider = (
            _RangeCachingProvider(
                provider,
                max_cached_bars=settings.request_cache_max_bars,
                max_covered_ranges=settings.cache_max_items,
            )
            if provider is not None
            else None
        )
        self._active_key: tuple[int, int, int] | None = None
        self._active_module: RequestModule | None = None
        self._active_bar: Any = None
        self._active_diagnostic_count = 0
        self._chart_index = ChartHistoryIndex()

    def security(self, *args: Any, **kwargs: Any) -> Any:
        module, ctx = self._module()
        with ctx.trace.span("request.security", category="request"):
            value = module.security(*args, **kwargs)
            self._publish_diagnostics(module, ctx)
        return _current_request_value(value, max_array_size=self._settings.max_array_size,
                                      max_depth=self._settings.max_collection_depth)

    def security_lower_tf(self, *args: Any, **kwargs: Any) -> Any:
        module, ctx = self._module()
        with ctx.trace.span("request.security_lower_tf", category="request"):
            value = module.security_lower_tf(*args, **kwargs)
            self._publish_diagnostics(module, ctx)
        return _current_request_value(value, max_array_size=self._settings.max_array_size,
                                      max_depth=self._settings.max_collection_depth)

    def cache_stats(self) -> dict[str, Any]:
        if self._provider is None:
            return {"series": 0, "bars": 0, "coveredRanges": 0, "fetches": 0,
                    "finalityFallbacks": 0, "finalizedThrough": []}
        return self._provider.stats()

    def __deepcopy__(self, memo: dict[int, Any]) -> "IncrementalRequestModule":
        # Finalized historical evidence can be reused by previews. The active
        # requested bar is fetched again for each callback, including its close.
        memo[id(self)] = self
        return self

    def _module(self) -> tuple[RequestModule, Any]:
        ctx = self._context_getter()
        if ctx.current_bar is None:
            raise RuntimeError("Incremental request.* requires an active chart bar")
        canonical = ctx._request_source_for_runtime() is not None
        if (canonical and self._active_module is not None
                and self._active_key is not None and self._active_key[0] == id(ctx)
                and self._active_bar is ctx.current_bar):
            return self._active_module, ctx
        batch_ctx = self._chart_index.view(ctx, self._settings)
        if batch_ctx is None:
            bars = ctx.request_bars()
            key = (id(ctx), int(bars[-1]["time"]), len(bars))
        else:
            key = (id(ctx), int(batch_ctx.times[-1]), len(batch_ctx.times))
        if (self._active_module is None or self._active_key != key
                or self._active_bar is not ctx.current_bar):
            if batch_ctx is None:
                batch_ctx = PyneContext.from_ohlcv(
                    bars, syminfo=self._settings.syminfo,
                    timeframe=self._settings.timeframe, session=self._settings.session)
            if self._provider is not None:
                self._provider.begin_evaluation(key[1])
            self._active_module = RequestModule(
                batch_ctx, provider=self._provider, current_only=True,
                max_array_size=self._settings.max_array_size)
            self._active_key = key
            self._active_bar = ctx.current_bar
            self._active_diagnostic_count = 0
        return self._active_module, ctx

    def _publish_diagnostics(self, module: RequestModule, ctx: Any) -> None:
        diagnostics = module.diagnostics
        new_items = diagnostics[self._active_diagnostic_count :]
        if new_items:
            ctx.record_request_diagnostics(new_items)
        self._active_diagnostic_count = len(diagnostics)


class _RangeCachingProvider:
    """Cache exact authoritative Provider rows over covered coordinate ranges."""

    def __init__(
        self,
        provider: DataProvider,
        *,
        max_cached_bars: int,
        max_covered_ranges: int,
    ) -> None:
        self._provider = provider
        self._max_cached_bars = max(int(max_cached_bars), 1)
        self._max_covered_ranges = max(int(max_covered_ranges), 1)
        self._bars: dict[tuple[str, str], dict[int, list[dict[str, Any]]]] = {}
        self._indices: dict[tuple[str, str], RowIndex] = {}
        self._times: dict[tuple[str, str], list[int]] = {}
        self._ranges: dict[tuple[str, str], list[tuple[int, int]]] = {}
        self._finalized_through: dict[tuple[str, str], int] = {}
        self._finality_fallbacks = 0
        self._fetches = 0
        self._chart_time: int | None = None

    def begin_evaluation(self, chart_time: int) -> None:
        """Select the callback's mutable tail without invalidating promised history."""
        if self._chart_time is not None and chart_time < self._chart_time:
            # Previews and process-local restore can move the callback clock
            # backwards. Do not reuse a formerly ended row as an active row.
            self._bars.clear()
            self._indices.clear()
            self._times.clear()
            self._finalized_through.clear()
            self._ranges.clear()
        elif self._chart_time is None:
            self._ranges.clear()
        self._chart_time = int(chart_time)

    def get_ohlcv(self, symbol: str, timeframe: str, start: int, end: int) -> list[dict[str, Any]]:
        return self.get_ohlcv_view(symbol, timeframe, start, end).copied()

    def get_ohlcv_view(self, symbol: str, timeframe: str, start: int, end: int) -> IndexedRows:
        """Internal validated snapshot; ordinary provider callers receive copies."""
        key = (str(symbol), str(timeframe))
        normalized_start, normalized_end = int(start), int(end)
        step = _fixed_timeframe_seconds(key[1])
        watermark = self._read_finality(key) if self._chart_time is not None else None
        history_end = (normalized_end if self._chart_time is None else
                       self._chart_time - step if step is not None else normalized_start - 1)
        times = self._times.get(key, [])
        bucket = self._bars.get(key, {})
        selected = SequenceWindow(times, bisect_left(times, normalized_start),
                                  bisect_right(times, normalized_end))
        index = self._indices.get(key, RowIndex())
        result = index.window(normalized_start, normalized_end)
        fresh = {}
        if self._chart_time is None:
            missing_ranges = _missing_ranges(normalized_start, normalized_end,
                                            self._ranges.get(key, []))
        else:
            covered = [(left, min(right, history_end))
                       for left, right in self._ranges.get(key, []) if left <= history_end]
            missing_ranges = _missing_live_span(normalized_start, normalized_end, selected, covered)
        for missing_start, missing_end in missing_ranges:
            rows = self._provider.get_ohlcv(key[0], key[1], missing_start, missing_end)
            self._fetches += 1
            # Validate the entire response before admitting any coordinate or
            # absence evidence. A caught provider error cannot poison history.
            validated = _validated_rows(rows)
            prepared = {}
            for row in validated:
                timestamp = int(row["time"])
                if missing_start <= timestamp <= missing_end:
                    prepared.setdefault(timestamp, []).append(row)
            if self._chart_time is not None:
                for timestamp, group in prepared.items():
                    if not all(_row_has_ended(row, timestamp, self._chart_time, step) for row in group):
                        history_end = min(history_end, timestamp - 1)
                prepared = {timestamp: group for timestamp, group in prepared.items()
                            if timestamp not in bucket}
            fresh.update(prepared)
            durable = {timestamp: group for timestamp, group in prepared.items()
                       if self._chart_time is None or (
                           watermark is not None and timestamp <= watermark
                           and all(_row_has_ended(row, timestamp, self._chart_time, step)
                                   for row in group))}
            if durable:
                bucket = self._bars.setdefault(key, {})
                bucket.update(durable)
                added = sorted(durable)
                times = self._times.setdefault(key, [])
                inserted = bool(added and times and added[0] <= times[-1])
                if inserted:
                    times[:] = sorted(bucket)
                    self._indices[key] = RowIndex(
                        row for timestamp in times for row in bucket[timestamp])
                else:
                    times.extend(added)
                    retained_index = self._indices.setdefault(key, RowIndex())
                    retained_index.append(row for timestamp in added for row in durable[timestamp])
            coverage_end = (missing_end if self._chart_time is None else
                            min(missing_end, history_end, watermark)
                            if watermark is not None else missing_start - 1)
            if coverage_end >= missing_start:
                self._bars.setdefault(key, {})
                self._ranges[key] = _merge_ranges(
                    [*self._ranges.get(key, []), (missing_start, coverage_end)])
        if watermark is not None and key in self._bars:
            self._finalized_through[key] = watermark
        self._enforce_limits(key)
        return result.combine(fresh)

    def stats(self) -> dict[str, Any]:
        return {
            "series": len(self._bars),
            "bars": sum(len(index.rows) for index in self._indices.values()),
            "coveredRanges": sum(len(items) for items in self._ranges.values()),
            "fetches": self._fetches,
            "finalityFallbacks": self._finality_fallbacks,
            "finalizedThrough": [
                {"symbol": symbol, "timeframe": timeframe, "time": watermark}
                for (symbol, timeframe), watermark in sorted(self._finalized_through.items())
            ],
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def _read_finality(self, key: tuple[str, str]) -> int | None:
        watermark, invalid = _request_finalized_through(self._provider, *key)
        previous = self._finalized_through.get(key)
        withdrawn = previous is not None and (watermark is None or watermark < previous)
        if invalid or withdrawn:
            self._drop_context(key)
            self._finality_fallbacks += 1
            return None
        if watermark is not None and previous is None:
            # Earlier observations made without this promise do not prove that
            # the newly finalized response was already complete or unchanged.
            self._drop_context(key)
        return watermark

    def _drop_context(self, key: tuple[str, str]) -> None:
        self._bars.pop(key, None)
        self._indices.pop(key, None)
        self._times.pop(key, None)
        self._ranges.pop(key, None)
        self._finalized_through.pop(key, None)

    def _enforce_limits(self, active_key: tuple[str, str]) -> None:
        cached_bars = sum(len(index.rows) for index in self._indices.values())
        covered_ranges = sum(len(items) for items in self._ranges.values())
        if (
            cached_bars <= self._max_cached_bars
            and covered_ranges <= self._max_covered_ranges
        ):
            return
        # Dropping coverage is safe: later calls refetch authoritative evidence.
        # The current request still returns its already materialized rows.
        self._drop_context(active_key)


def _current_request_value(value: Any, *, max_array_size: int | None = None,
                           max_depth: int | None = None) -> Any:
    if isinstance(value, tuple):
        return tuple(_current_request_value(item, max_array_size=max_array_size, max_depth=max_depth)
                     for item in value)
    if isinstance(value, PyneSeries):
        if not len(value.values):
            return float("nan")
        current = value.values[-1]
        return current.item() if isinstance(current, np.generic) else current
    if isinstance(value, LowerTimeframeSeries):
        group = value.groups[-1] if value.groups else ()
        return PyneArray(group, max_size=max_array_size, max_depth=max_depth)
    return value


def _validated_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PyneRequestError(
            "request data provider must return a list of OHLCV bars",
            code="PYNE_RUNTIME_ERROR", category=RequestProviderErrorCategory.INVALID_RETURN_TYPE)
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise PyneRequestError(
                f"request data provider returned non-mapping bar at row {index}",
                code="PYNE_RUNTIME_ERROR", category=RequestProviderErrorCategory.INVALID_BAR_SHAPE)
        if "time" not in row:
            raise PyneRequestError(
                f"request data provider returned OHLCV bar without time at row {index}",
                code="PYNE_RUNTIME_ERROR", category=RequestProviderErrorCategory.INVALID_BAR_SHAPE)
    try:
        ordered = sorted(value, key=lambda row: int(row["time"]))
        normalized = PyneData.from_ohlcv(
            ordered, allow_empty=True, allow_missing_values=True, require_unique_times=False)
        # Retain extension payloads and their isolation, while all computation
        # fields use precisely the normal OHLCV coercion/validation contract.
        return [dict(copy.deepcopy(raw), **bar) for raw, bar in zip(ordered, normalized)]
    except (TypeError, ValueError, OverflowError) as exc:
        raise PyneRequestError(
            f"request data provider returned invalid OHLCV: {exc}",
            code="PYNE_RUNTIME_ERROR", category=RequestProviderErrorCategory.INVALID_BAR_SHAPE) from exc


def _missing_observed_span(start: int, end: int, times: Sequence[int]) -> list[tuple[int, int]]:
    """Find one refresh span, excluding only observed contiguous edge points."""
    left, right = start, end
    for timestamp in times:
        if timestamp != left:
            break
        left += 1
    for timestamp in reversed(times):
        if timestamp != right:
            break
        right -= 1
    return [(left, right)] if left <= right else []


def _missing_live_span(
    start: int, end: int, times: Sequence[int], covered: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Coalesce refreshable holes while excluding promised complete history."""
    first, last = None, None
    for left, right in _missing_ranges(start, end, covered):
        observed = times[bisect_left(times, left):bisect_right(times, right)]
        missing = _missing_observed_span(left, right, observed)
        if missing:
            first = missing[0][0] if first is None else first
            last = missing[-1][1]
    return [] if first is None else [(first, last)]


def _fixed_timeframe_seconds(timeframe: str) -> int | None:
    # Calendar periods and ticks do not have a fixed authoritative duration.
    if timeframe.strip().endswith(("D", "d", "W", "w", "M", "T", "t")):
        return None
    return _timeframe_seconds_from_text(timeframe)


def _row_has_ended(
    row: Mapping[str, Any], timestamp: int, chart_time: int, step: int | None,
) -> bool:
    if "time_close" in row:
        close = row["time_close"]
        return (not isinstance(close, bool)
                and isinstance(close, (int, float, np.integer, np.floating))
                and math.isfinite(close) and timestamp < close <= chart_time)
    return step is not None and timestamp + step <= chart_time


def _missing_ranges(
    start: int,
    end: int,
    covered: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if end < start:
        return []
    missing: list[tuple[int, int]] = []
    cursor = start
    for left, right in _merge_ranges(covered):
        if right < cursor:
            continue
        if left > end:
            break
        if left > cursor:
            missing.append((cursor, min(left - 1, end)))
        cursor = max(cursor, right + 1)
        if cursor > end:
            break
    if cursor <= end:
        missing.append((cursor, end))
    return missing


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted((int(left), int(right)) for left, right in ranges):
        if end < start:
            continue
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged
