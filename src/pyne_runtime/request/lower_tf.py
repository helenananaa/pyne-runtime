"""Lower-timeframe grouping results and helpers."""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..series import PyneSeries
from ..security import PyneResourceLimitError
from ..values import is_na_value

RequestValues = list[Any] | tuple[list[Any], ...]


@dataclass(frozen=True)
class LowerTimeframeSeries:
    """Array-per-chart-bar result returned by ``request.security_lower_tf()``."""

    groups: tuple[tuple[Any, ...], ...]
    name: str | None = None
    _numeric_cache: tuple[np.ndarray, np.ndarray, np.ndarray] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __len__(self) -> int:
        return len(self.groups)

    def __iter__(self):
        return iter(self.groups)

    def __getitem__(self, key: int | slice) -> Any:
        if isinstance(key, slice):
            return self.groups[key]
        if not isinstance(key, (int, np.integer)):
            raise TypeError("LowerTimeframeSeries indices must be a non-negative bars-back integer")
        if key < 0:
            raise IndexError("LowerTimeframeSeries does not support forward history references")
        return self.shift(int(key))

    def to_lists(self) -> list[list[Any]]:
        return [list(group) for group in self.groups]

    def shift(self, periods: int = 1) -> "LowerTimeframeSeries":
        periods = int(periods)
        if periods <= 0:
            return self
        empty: tuple[Any, ...] = ()
        groups = [empty] * len(self.groups)
        if periods < len(self.groups):
            groups[periods:] = self.groups[: len(self.groups) - periods]
        return LowerTimeframeSeries(
            tuple(groups),
            name=f"{self.name}[{periods}]" if self.name else None,
        )

    def size(self) -> PyneSeries:
        return _lower_tf_numeric_series(
            [len(group) for group in self.groups],
            name=f"{self.name}.size" if self.name else None,
        )

    def first(self, default: Any = np.nan) -> PyneSeries:
        return self._edge(0, default=default, label="first")

    def last(self, default: Any = np.nan) -> PyneSeries:
        return self._edge(-1, default=default, label="last")

    def get(self, index: int, default: Any = np.nan) -> PyneSeries:
        """Return the value at ``index`` from each chart bar's lower-TF group."""
        index = int(index)
        if index < 0:
            raise IndexError("LowerTimeframeSeries.get() requires a non-negative index")
        values = [group[index] if index < len(group) else default for group in self.groups]
        return _lower_tf_numeric_series(
            values,
            name=f"{self.name}.get" if self.name else None,
        )

    def sum(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.sum, default=default, label="sum")

    def min(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.min, default=default, label="min")

    def max(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.max, default=default, label="max")

    def avg(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.mean, default=default, label="avg")

    def _edge(self, index: int, *, default: Any, label: str) -> PyneSeries:
        values = [group[index] if group else default for group in self.groups]
        return _lower_tf_numeric_series(
            values,
            name=f"{self.name}.{label}" if self.name else None,
        )

    def _aggregate(
        self,
        op: Callable[[np.ndarray], Any],
        *,
        default: Any,
        label: str,
    ) -> PyneSeries:
        flat, offsets, counts = self._numeric_groups()
        result = np.full(len(self.groups), np.nan, dtype=np.float64)
        nonempty = counts > 0
        if np.any(nonempty):
            starts = offsets[:-1][nonempty]
            if label == "sum" or label == "avg":
                reduced = np.add.reduceat(flat, starts)
                if label == "avg":
                    reduced = reduced / counts[nonempty]
            elif label == "min":
                reduced = np.minimum.reduceat(flat, starts)
            elif label == "max":
                reduced = np.maximum.reduceat(flat, starts)
            else:  # pragma: no cover - private callers use the four labels above
                reduced = np.asarray([op(flat[start:stop]) for start, stop in zip(
                    offsets[:-1][nonempty],
                    offsets[1:][nonempty],
                )])
            result[nonempty] = reduced

        empty = ~nonempty
        if np.any(empty):
            result[empty] = np.nan if is_na_value(default) else float(default)
        return PyneSeries(
            result,
            name=f"{self.name}.{label}" if self.name else None,
        )

    def _numeric_groups(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cached = self._numeric_cache
        if cached is not None:
            return cached

        flat_values: list[float] = []
        counts = np.empty(len(self.groups), dtype=np.intp)
        for index, group in enumerate(self.groups):
            start = len(flat_values)
            for value in group:
                if not is_na_value(value):
                    flat_values.append(float(value))
            counts[index] = len(flat_values) - start

        flat = np.asarray(flat_values, dtype=np.float64)
        offsets = np.empty(len(self.groups) + 1, dtype=np.intp)
        offsets[0] = 0
        np.cumsum(counts, out=offsets[1:])
        flat.setflags(write=False)
        offsets.setflags(write=False)
        counts.setflags(write=False)
        cached = (flat, offsets, counts)
        object.__setattr__(self, "_numeric_cache", cached)
        return cached


def _group_lower_timeframe_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    chart_end: int,
    requested_times: list[int],
    requested_values: RequestValues,
    max_group_size: int | None = None,
) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
    if isinstance(requested_values, tuple):
        return tuple(
            _group_single_lower_timeframe_values(
                symbol=symbol,
                timeframe=timeframe,
                expression_name=f"{expression_name}[{index}]",
                chart_times=chart_times,
                chart_end=chart_end,
                requested_times=requested_times,
                requested_values=values,
                max_group_size=max_group_size,
            )
            for index, values in enumerate(requested_values)
        )
    return _group_single_lower_timeframe_values(
        symbol=symbol,
        timeframe=timeframe,
        expression_name=expression_name,
        chart_times=chart_times,
        chart_end=chart_end,
        requested_times=requested_times,
        requested_values=requested_values,
        max_group_size=max_group_size,
    )

def _group_single_lower_timeframe_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    chart_end: int,
    requested_times: list[int],
    requested_values: list[Any],
    max_group_size: int | None = None,
) -> LowerTimeframeSeries:
    groups: list[tuple[Any, ...]] = []
    for index, chart_time in enumerate(chart_times):
        next_time = chart_times[index + 1] if index + 1 < len(chart_times) else chart_end
        start = bisect_left(requested_times, chart_time)
        end = bisect_left(requested_times, next_time)
        first, last, _ = slice(start, end).indices(len(requested_values))
        count = max(last - first, 0)
        if max_group_size is not None and count > max_group_size:
            raise PyneResourceLimitError(f"array size {count} exceeds limit {max_group_size}")
        groups.append(tuple(
            np.nan if is_na_value(value) else value
            for value in requested_values[start:end]
        ))
    return LowerTimeframeSeries(
        tuple(groups),
        name=f"request.security_lower_tf({symbol},{timeframe},{expression_name})",
    )

def _lower_tf_numeric_series(values: list[Any], *, name: str | None = None) -> PyneSeries:
    return PyneSeries(
        np.asarray(
            [np.nan if is_na_value(value) else float(value) for value in values],
            dtype=np.float64,
        ),
        name=name,
    )
