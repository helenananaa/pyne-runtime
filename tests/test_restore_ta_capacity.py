"""Real TA capacities stay consistent across admission and state restoration."""
import pytest
from collections import deque
import pyne_runtime as pn

from pyne_runtime.incremental._ta_capacity import ta_reserved_window_sizes
from pyne_runtime.incremental.limits import IncrementalLimits, _LimitTracker
from pyne_runtime.incremental.ta import IncrementalTaNamespace
from pyne_runtime.security import PyneResourceLimitError


@pytest.mark.parametrize("method,arguments,expected", [
    ("sma", (4,), 4), ("wma", (4,), 4), ("vwma", (4,), 4),
    ("variance", (4,), 4), ("stdev", (4,), 4), ("change", (4,), 5),
    ("highestbars", (4,), 4), ("lowestbars", (4,), 4),
    ("pivothigh", (1, 2), 4), ("pivotlow", (1, 2), 4), ("swma", (), 4),
    ("alma", (4,), 4), ("dev", (4,), 4), ("boll", (4,), 4), ("bb", (4,), 4),
    ("highest", (4,), 4), ("lowest", (4,), 4), ("stoch", (4,), 8),
    ("cci", (4,), 4), ("hma", (4,), 8), ("valuewhen", (3,), 4),
    ("sar", (0.02,), 4), ("mfi", (4,), 8),
    ("ema", (4,), 0), ("rma", (4,), 0), ("rsi", (4,), 0), ("atr", (4,), 0),
    ("tr", (), 0), ("cum", (), 0), ("macd", (4,), 0), ("barssince", (), 0),
    ("crossover", (), 0), ("crossunder", (), 0), ("cross", (), 0), ("vwap", (), 0),
    ("dmi", (4,), 0), ("adx", (4,), 0), ("supertrend", (3,), 0),
    ("pivot_point_levels", ("Traditional",), 0),
])
def test_actual_registered_helpers_match_their_resource_contract(method, arguments, expected):
    tracker = _LimitTracker(IncrementalLimits(enabled=True))
    namespace = IncrementalTaNamespace(tracker)
    getattr(namespace, method)("test", *arguments)
    sizes = ta_reserved_window_sizes(namespace)
    assert sum(sizes) == expected
    assert tracker.total_window_items == expected
    assert tracker.largest_window_size == expected


@pytest.mark.parametrize("method", ["stoch", "mfi"])
def test_double_window_admission_uses_normalized_capacity_before_allocation(method):
    tracker = _LimitTracker(IncrementalLimits(enabled=True, max_window_size=1))
    namespace = IncrementalTaNamespace(tracker)
    with pytest.raises(PyneResourceLimitError, match="window"):
        getattr(namespace, method)("test", 0.4)
    assert not namespace._helpers
    assert tracker.total_window_items == 0


@pytest.mark.parametrize("kind", ["period", "stochastic", "hma", "pivot", "occurrence", "unknown"])
def test_forged_helper_capacity_is_rejected(kind):
    namespace = IncrementalTaNamespace()
    if kind == "period":
        namespace.sma("test", 2).period = 0
    elif kind == "stochastic":
        namespace.stoch("test", 2).lowest.period = 3
    elif kind == "hma":
        namespace.hma("test", 4).fast.period = 3
    elif kind == "pivot":
        namespace.pivothigh("test", 1, 2).window_size = 2
    elif kind == "occurrence":
        namespace.valuewhen("test", 2).occurrence = -1
    else:
        namespace._helpers["test"] = object()
    with pytest.raises(ValueError, match="Incremental snapshot TA"):
        ta_reserved_window_sizes(namespace)


@pytest.mark.parametrize("method,buffer", [("sma", "window"), ("wma", "window"),
                                         ("vwma", "products"), ("mfi", "positive"),
                                         ("change", "window"), ("alma", "window"),
                                         ("valuewhen", "values")])
def test_helper_backing_storage_cannot_exceed_reserved_capacity(method, buffer):
    namespace = IncrementalTaNamespace()
    helper = getattr(namespace, method)("test", 2)
    original = getattr(helper, buffer)
    setattr(helper, buffer, deque([1.] * 100, maxlen=original.maxlen if original.maxlen is None else 100))
    with pytest.raises(ValueError, match="TA window storage"):
        ta_reserved_window_sizes(namespace)


def test_composite_helper_cannot_hide_a_different_window_family():
    namespace = IncrementalTaNamespace()
    namespace.hma("test", 4).fast = IncrementalTaNamespace().hma("nested", 2)
    with pytest.raises(ValueError, match="HMA helper type"):
        ta_reserved_window_sizes(namespace)


@pytest.mark.parametrize("method,child", [("macd", "fast"), ("macd", "slow"), ("macd", "signal"),
                                        ("dmi", "atr"), ("dmi", "plus"), ("dmi", "minus"),
                                        ("dmi", "adx"), ("adx", "atr"), ("supertrend", "atr")])
def test_scalar_composite_cannot_hide_a_buffered_helper(method, child):
    namespace = IncrementalTaNamespace()
    helper = getattr(namespace, method)("test", 4)
    setattr(helper, child, IncrementalTaNamespace().sma("hidden", 100))
    with pytest.raises(ValueError, match="scalar helper type"):
        ta_reserved_window_sizes(namespace)


def test_oversized_real_ta_state_rejects_before_replacing_healthy_session():
    script = '''indicator("TA storage", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Average", ctx.ta.sma("test", 2).update(bar.close))
'''
    bars = [dict(time=i, open=i, high=i, low=i, close=i, volume=1) for i in (1, 2, 3)]
    settings = pn.PyneSettings(max_window_size=2, max_total_window_items=2)
    source = pn.PyneIncrementalSession(script=script, settings=settings)
    source.seed(bars[:2])
    bad = source.snapshot_state()
    bad.context.ta._helpers["sma:test"].window = deque([1.] * 100)
    target = pn.PyneIncrementalSession(script=script, settings=settings)
    target.seed(bars[:2])
    before = target.snapshot_portable_state()
    with pytest.raises(ValueError, match="TA window storage"):
        target.restore_state(bad)
    assert target.snapshot_portable_state() == before
    assert target.on_bar_closed(bars[2]) == source.on_bar_closed(bars[2])
