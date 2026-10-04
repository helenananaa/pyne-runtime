"""Internal immutable timeline views for incremental current-bar requests."""
from __future__ import annotations

import copy
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from sys import float_info

import numpy as np

from ..context import PyneContext
from ..metadata import SessionInfo, SymbolInfo, TimeframeInfo
from ..metadata import normalize_session_info, normalize_symbol_info, normalize_timeframe_info


def can_defer_metadata(metadata):
    """Defer only standard values whose conversion/binding has no Python hooks."""
    def ordinary(value, ancestors):
        if type(value) in (type(None), bool, int, float, str):
            return True
        if type(value) in (SymbolInfo, TimeframeInfo, SessionInfo):
            return all(ordinary(item, ancestors) for key, item in vars(value).items()
                       if key not in {"_times", "_timezone"})
        if type(value) is dict and id(value) not in ancestors:
            path = ancestors | {id(value)}
            return all(type(key) is str and ordinary(item, path) for key, item in value.items())
        return False

    return all(ordinary(metadata[key], set()) for key in ("syminfo", "timeframe", "session"))


class SequenceWindow(Sequence):
    def __init__(self, source: Sequence, left: int = 0, right: int | None = None):
        self.source, self.left = source, left
        self.right = len(source) if right is None else right

    def __len__(self):
        return max(self.right - self.left, 0)

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step == 1:
                return SequenceWindow(self.source, self.left + start, self.left + stop)
            return [self[i] for i in range(start, stop, step)]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self.source[self.left + index]


class RowIndex:
    """Appendable rows; replacement on insert preserves prior request views."""

    def __init__(self, rows=()):
        self.rows = []
        self.times = []
        self.minimum_steps = []
        self.unsafe_derived_counts = []
        self.append(rows)

    def append(self, rows):
        for row in rows:
            timestamp = int(row["time"])
            minimum = self.minimum_steps[-1] if self.minimum_steps else None
            if self.times and timestamp > self.times[-1]:
                step = timestamp - self.times[-1]
                minimum = step if minimum is None else min(minimum, step)
            self.rows.append(row)
            self.times.append(timestamp)
            self.minimum_steps.append(minimum)
            unsafe = any(abs(float(row.get(field, float("nan")))) > float_info.max / 4
                         for field in ("open", "high", "low", "close"))
            self.unsafe_derived_counts.append(
                (self.unsafe_derived_counts[-1] if self.unsafe_derived_counts else 0) + unsafe)

    def window(self, start: int, end: int):
        left = bisect_left(self.times, start)
        return IndexedRows(self, left, max(left, bisect_right(self.times, end)))


class _RowTimes(Sequence):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return SequenceWindow(self)[index]
        return int(self.rows[index]["time"])


class IndexedRows(Sequence):
    """Validated row snapshot with a zero-copy stable prefix and a small tail."""

    def __init__(self, index: RowIndex, left=0, right=None, tail=()):
        self.index, self.left = index, left
        self.right = len(index.rows) if right is None else right
        self.tail = tuple(tail)
        self.times = _RowTimes(self)
        self.fast_step_known = left == 0 or self.right - left <= 1
        self.minimum_positive_step = None
        unsafe_count = ((index.unsafe_derived_counts[self.right - 1] if self.right else 0)
                        - (index.unsafe_derived_counts[left - 1] if left else 0))
        self.unsafe_derived = bool(unsafe_count) or any(
            abs(float(row.get(field, float("nan")))) > float_info.max / 4
            for row in self.tail for field in ("open", "high", "low", "close"))
        if self.fast_step_known:
            if left == 0 and self.right:
                self.minimum_positive_step = index.minimum_steps[self.right - 1]
            previous = index.times[self.right - 1] if self.right > left else None
            for row in self.tail:
                timestamp = int(row["time"])
                if previous is not None and timestamp > previous:
                    step = timestamp - previous
                    self.minimum_positive_step = (step if self.minimum_positive_step is None
                                                  else min(self.minimum_positive_step, step))
                previous = timestamp

    def __len__(self):
        return self.right - self.left + len(self.tail)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return SequenceWindow(self)[index]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        prefix = self.right - self.left
        return self.index.rows[self.left + index] if index < prefix else self.tail[index - prefix]

    def combine(self, groups):
        tail = [row for _, group in sorted(groups.items()) for row in group]
        if not tail or self.right == self.left or int(tail[0]["time"]) >= self.index.times[self.right - 1]:
            return IndexedRows(self.index, self.left, self.right, tail)
        # Late arrivals or nonuniform active bars may interleave stable rows.
        # Materialize this unusual merge; never reinterpret their ordering.
        return IndexedRows(RowIndex(sorted([*self, *tail], key=lambda row: int(row["time"]))))

    def copied(self):
        return [copy.deepcopy(row) for row in self]


class LazyRequestedContext:
    """Validate metadata now; build all Python-visible series only on demand."""

    def __init__(self, rows: IndexedRows, metadata):
        self.rows = rows
        # Match the metadata validation that normal PyneContext construction
        # performs, without binding an unused full timeline or series graph.
        self.metadata = {
            "syminfo": normalize_symbol_info(metadata["syminfo"]),
            "timeframe": normalize_timeframe_info(metadata["timeframe"]),
            "session": normalize_session_info(metadata["session"]),
        }
        self.full_context = None
        self.field_values_read = False
        self.field_error_policy = None

    @property
    def times(self):
        return self.full_context.times if self.full_context is not None else self.rows.times

    @property
    def bar_count(self):
        return len(self.rows)

    def materialize(self):
        if self.full_context is None:
            self.full_context = PyneContext.from_ohlcv(
                self.rows, syminfo=self.metadata["syminfo"],
                timeframe=self.metadata["timeframe"], session=self.metadata["session"],
                allow_empty=True, allow_missing_values=True, require_unique_times=False)
            if self.field_values_read:
                # The ordinary field helper eagerly creates all four derived
                # series. Preserve those cached values before Python receives
                # the context and can mutate its base arrays.
                with np.errstate(**self.field_error_policy):
                    for field in ("hl2", "hlc3", "ohlc4", "hlcc4"):
                        getattr(self.full_context, field)
        return self.full_context

    def __getattr__(self, name):
        return getattr(self.materialize(), name)
