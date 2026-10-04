"""Bounded monotonic candidate queues for delayed pivot confirmation."""
from __future__ import annotations

from collections import deque
from typing import Any


class _PivotWindow:
    """Keep separate candidate queues where missing neighbors end comparisons.

    Ended segments remain available until their centers reach the confirmation
    bar. Every candidate and segment enters and leaves a deque at most once.
    """

    def __init__(self, left: int, right: int, *, highest: bool) -> None:
        self.left = max(int(left), 0)
        self.right = max(int(right), 0)
        self.highest = bool(highest)
        self.window_size = self.left + self.right + 1
        self.index = -1
        self.pending: deque[float | None] = deque()
        # [segment start, last present index or None, candidates]
        self.segments: deque[list[Any]] = deque()
        self.segment_open = False

    @property
    def confirmation_offset(self) -> int:
        return -self.right

    def update(self, current: float | None) -> float | None:
        self.index += 1
        self.pending.append(current)
        if current is None:
            if self.segment_open:
                self.segments[-1][1] = self.index - 1
                self.segment_open = False
        else:
            if not self.segment_open:
                self.segments.append([self.index, None, deque()])
                self.segment_open = True
            candidates = self.segments[-1][2]
            while candidates and ((candidates[-1][1] <= current) if self.highest
                                   else (candidates[-1][1] >= current)):
                candidates.pop()
            candidates.append((self.index, current))
        if len(self.pending) <= self.right:
            return None
        center = self.pending.popleft()
        center_index = self.index - self.right
        while self.segments and self.segments[0][1] is not None and self.segments[0][1] < center_index:
            self.segments.popleft()
        if self.index < self.window_size - 1 or center is None:
            return None
        candidates = self.segments[0][2]
        expiry = center_index - self.left
        while candidates and candidates[0][0] < expiry:
            candidates.popleft()
        return center if candidates and candidates[0][0] == center_index else None
