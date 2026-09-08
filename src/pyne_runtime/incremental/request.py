"""Incremental facade over the versioned batch request-provider contract."""

from __future__ import annotations

import copy
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from ..collections import PyneArray
from ..context import PyneContext
from ..request import LowerTimeframeSeries, RequestModule
from ..request.provider import DataProvider
from ..series import PyneSeries
from ..settings import PyneSettings


class IncrementalRequestModule:
    """Evaluate request expressions against chart history through a typed Provider.

    Batch ``RequestModule`` remains the single alignment/error implementation.
    This facade materializes the retained chart context, returns only the current
    chart-bar value, and keeps a bounded range cache around the Host provider.
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
                max_cached_bars=settings.max_output_points,
                max_covered_ranges=settings.cache_max_items,
            )
            if provider is not None
            else None
        )
        self._active_key: tuple[int, int, int] | None = None
        self._active_module: RequestModule | None = None
        self._active_diagnostic_count = 0

    def security(self, *args: Any, **kwargs: Any) -> Any:
        module, ctx = self._module()
        with ctx.trace.span("request.security", category="request"):
            value = module.security(*args, **kwargs)
            self._publish_diagnostics(module, ctx)
        return _current_request_value(value)

    def security_lower_tf(self, *args: Any, **kwargs: Any) -> Any:
        module, ctx = self._module()
        with ctx.trace.span("request.security_lower_tf", category="request"):
            value = module.security_lower_tf(*args, **kwargs)
            self._publish_diagnostics(module, ctx)
        return _current_request_value(value)

    def cache_stats(self) -> dict[str, int]:
        if self._provider is None:
            return {"series": 0, "bars": 0, "coveredRanges": 0, "fetches": 0}
        return self._provider.stats()

    def __deepcopy__(self, memo: dict[int, Any]) -> "IncrementalRequestModule":
        # Provider data is immutable Host evidence and can be reused by previews.
        memo[id(self)] = self
        return self

    def _module(self) -> tuple[RequestModule, Any]:
        ctx = self._context_getter()
        bars = ctx.request_bars()
        if not bars:
            raise RuntimeError("Incremental request.* requires an active chart bar")
        key = (id(ctx), int(bars[-1]["time"]), len(bars))
        if self._active_module is None or self._active_key != key:
            batch_ctx = PyneContext.from_ohlcv(
                bars,
                syminfo=self._settings.syminfo,
                timeframe=self._settings.timeframe,
                session=self._settings.session,
            )
            self._active_module = RequestModule(batch_ctx, provider=self._provider)
            self._active_key = key
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
        self._bars: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
        self._times: dict[tuple[str, str], list[int]] = {}
        self._ranges: dict[tuple[str, str], list[tuple[int, int]]] = {}
        self._fetches = 0

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        key = (str(symbol), str(timeframe))
        normalized_start = int(start)
        normalized_end = int(end)
        times = self._times.get(key, [])
        bucket = self._bars.get(key, {})
        selected = times[bisect_left(times, normalized_start):bisect_right(times, normalized_end)]
        result_rows = {timestamp: copy.deepcopy(bucket[timestamp]) for timestamp in selected}
        for missing_start, missing_end in _missing_ranges(
            normalized_start,
            normalized_end,
            self._ranges.get(key, []),
        ):
            rows = self._provider.get_ohlcv(
                key[0],
                key[1],
                missing_start,
                missing_end,
            )
            self._fetches += 1
            if not _cacheable_rows(rows):
                return rows
            prepared: dict[int, dict[str, Any]] = {}
            for row in rows:
                timestamp = int(row["time"])
                if missing_start <= timestamp <= missing_end:
                    prepared[timestamp] = copy.deepcopy(row)
            # Validate/copy the fetched batch before publishing rows or index.
            # A malformed row must not leave an unindexed partial insertion.
            bucket = self._bars.setdefault(key, {})
            new_times = {timestamp for timestamp in prepared if timestamp not in bucket}
            bucket.update(prepared)
            result_rows.update(copy.deepcopy(prepared))
            times = self._times.setdefault(key, [])
            added = sorted(new_times)
            if added and times and added[0] <= times[-1]:
                times[:] = sorted([*times, *added])
            else:
                times.extend(added)
            self._ranges[key] = _merge_ranges(
                [*self._ranges.get(key, []), (missing_start, missing_end)]
            )
        self._enforce_limits(key)
        return [
            result_rows[timestamp]
            for timestamp in sorted(result_rows)
        ]

    def stats(self) -> dict[str, int]:
        return {
            "series": len(self._bars),
            "bars": sum(len(items) for items in self._bars.values()),
            "coveredRanges": sum(len(items) for items in self._ranges.values()),
            "fetches": self._fetches,
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    def _enforce_limits(self, active_key: tuple[str, str]) -> None:
        cached_bars = sum(len(items) for items in self._bars.values())
        covered_ranges = sum(len(items) for items in self._ranges.values())
        if (
            cached_bars <= self._max_cached_bars
            and covered_ranges <= self._max_covered_ranges
        ):
            return
        # Dropping coverage is safe: later calls refetch authoritative evidence.
        # The current request still returns its already materialized rows.
        self._bars.pop(active_key, None)
        self._times.pop(active_key, None)
        self._ranges.pop(active_key, None)


def _current_request_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return tuple(_current_request_value(item) for item in value)
    if isinstance(value, PyneSeries):
        if not len(value.values):
            return float("nan")
        current = value.values[-1]
        return current.item() if isinstance(current, np.generic) else current
    if isinstance(value, LowerTimeframeSeries):
        group = value.groups[-1] if value.groups else ()
        return PyneArray(group)
    return value


def _cacheable_rows(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, Mapping) and "time" in item for item in value
    )


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
