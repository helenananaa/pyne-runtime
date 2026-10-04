"""Derived current chart views; ordinary exposed history keeps the full path."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..request._indexed import can_defer_metadata
from ..series import PyneSeries


class ChartTimes(Sequence):
    def __init__(self, times, minima, current):
        self.times = times
        self.current = current
        self.prefix = len(times) - bool(times and times[-1] == current)
        self.minimum_positive_step = minima[self.prefix - 1] if self.prefix else None
        self.last_positive_step = (times[self.prefix - 1] - times[self.prefix - 2]
                                   if self.prefix > 1 else None)
        if self.prefix and current > times[self.prefix - 1]:
            step = current - times[self.prefix - 1]
            self.last_positive_step = step
            self.minimum_positive_step = (step if self.minimum_positive_step is None
                                          else min(self.minimum_positive_step, step))

    def __len__(self):
        return self.prefix + 1

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self.current if index == self.prefix else self.times[index]


class ChartHistoryIndex:
    def __init__(self):
        self.source = None
        self.times = []
        self.minima = []

    def view(self, ctx, settings):
        if not can_defer_metadata({"syminfo": settings.syminfo, "timeframe": settings.timeframe,
                                   "session": settings.session}):
            return None
        source = ctx._request_source_for_runtime()
        if source is None or ctx.current_bar is None:
            return None
        if (source is not self.source or len(source) < len(self.times)
                or source and self.times and int(source[0]["time"]) != self.times[0]):
            self.source, self.times, self.minima = source, [], []
        for index in range(len(self.times), len(source)):
            timestamp = int(source[index]["time"])
            minimum = self.minima[-1] if self.minima else None
            if self.times and timestamp > self.times[-1]:
                step = timestamp - self.times[-1]
                minimum = step if minimum is None else min(minimum, step)
            self.times.append(timestamp)
            self.minima.append(minimum)
        return ChartContextView(ChartTimes(self.times, self.minima, ctx.current_bar.time),
                                ctx.current_bar.raw, settings.timeframe)


class ChartContextView:
    def __init__(self, times, current, timeframe):
        self.times = times
        self.bar_count = len(times)
        self.timeframe = timeframe
        explicit = current.get("time_close") is not None
        try:
            close = current["time_close"] if explicit else times[-1] + timeframe.in_seconds()
        except (TypeError, ValueError):
            close = np.nan
        self.time_close = PyneSeries(np.asarray([close], dtype=np.float64))
        self._time_close_explicit = (explicit,)
