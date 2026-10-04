"""Incremental pivots retain scan semantics with amortized bounded deque work."""

from collections import deque
import importlib
import itertools

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepPivot
from pyne_runtime.utils import pivothigh, pivotlow


@pytest.mark.parametrize("left,right", [(0, 0), (0, 3), (3, 0), (1, 1), (1, 2), (2, 1)])
@pytest.mark.parametrize("highest", [True, False])
def test_incremental_pivot_exhaustive_missing_ties_and_warmup_match_batch(left, right, highest):
    operation = pivothigh if highest else pivotlow
    for values in itertools.product([None, 0.0, 1.0], repeat=6):
        helper = _StepPivot(left, right, highest=highest)
        actual = np.asarray([helper.update(value) for value in values], dtype=float)
        expected = np.asarray(operation(np.asarray(values, dtype=float), left, right))
        np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("values,left,right,expected", [
    ([9, None, 5, 4], 2, 1, 5),
    ([4, 5, None, 9], 1, 2, 5),
    ([5, 5, 4], 1, 1, 5),
    ([4, 5, 5], 1, 1, None),
    ([4, None, 5], 1, 1, None),
])
def test_missing_neighbors_end_comparison_without_crossing_into_another_segment(values, left, right, expected):
    helper = _StepPivot(left, right, highest=True)
    assert [helper.update(value) for value in values][-1] == expected


@pytest.mark.parametrize("size", [2000, 4000, 8000])
@pytest.mark.parametrize("profile", ["flat", "increasing", "gaps"])
def test_incremental_pivot_deque_work_is_linear_without_window_iteration(monkeypatch, size, profile):
    module = importlib.import_module("pyne_runtime.incremental._pivot_window")

    class CountingDeque(deque):
        operations = 0

        def __iter__(self):
            pytest.fail("Pivot update must not iterate or copy a deque window")

        def append(self, value):
            type(self).operations += 1
            super().append(value)

        def pop(self):
            type(self).operations += 1
            return super().pop()

        def popleft(self):
            type(self).operations += 1
            return super().popleft()

    monkeypatch.setattr(module, "deque", CountingDeque)
    period = size // 4
    left, right = period // 2, period - period // 2 - 1
    source = np.ones(size) if profile == "flat" else np.arange(size, dtype=float)
    if profile == "gaps":
        source[::3] = np.nan
    helper = _StepPivot(left, right, highest=True)
    actual = np.asarray([helper.update(value) for value in source], dtype=float)
    np.testing.assert_array_equal(actual, np.asarray(pivothigh(source, left, right)))
    assert 0 < CountingDeque.operations <= 6 * size
    assert len(helper.pending) <= right
    assert len(helper.segments) <= right + 1


SCRIPT = '''indicator("Queued pivots", mode="incremental")
def on_bar(ctx, bar):
    value = None if ctx.bar_index in (2, 7, 8) else bar.close
    ctx.plot("High", ctx.ta.pivothigh("high", 3, 2).update(value))
    ctx.plot("Low", ctx.ta.pivotlow("low", 1, 1).update(value))
'''


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
@pytest.mark.parametrize("cut", [3, 6, 9])
def test_pending_pivot_segments_preview_and_same_version_snapshot_continue(mode, cut):
    bars = [dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)
            for index, value in enumerate([3, 2, 5, 4, 6, 1, 7, 3, 8, 2, 5, 1, 6])]
    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed(bars[:cut])
    committed = session.snapshot_portable_state()
    preview = dict(bars[cut], open=99, high=99, low=99, close=99)
    session.on_bar_updated(preview)
    assert session.snapshot_portable_state() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=SCRIPT)
    for bar in bars[cut:]:
        session.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == session.on_bar_closed(bar)
    assert restored.snapshot_result() == session.snapshot_result()


def test_public_queued_pivot_batch_incremental_parity_with_missing_segments():
    bars = [dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)
            for index, value in enumerate([3, 2, 5, 4, 6, 1, 7, 3, 8, 2, 5, 1, 6])]
    batch = '''indicator("Queued pivots")
value = when((bar_index == 2) | (bar_index == 7) | (bar_index == 8), na, close)
plot(ta.pivothigh(value, 3, 2), "High")
plot(ta.pivotlow(value, 1, 1), "Low")
'''
    report = pn.run_incremental_parity(batch_script=batch, incremental_script=SCRIPT, bars=bars,
                                     normalizer=lambda result: [result.values("High"), result.values("Low")])
    report.assert_ok()
