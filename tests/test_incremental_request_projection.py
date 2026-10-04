"""Public request semantics survive indexed current-bar projection."""
import copy
from bisect import bisect_left, bisect_right

import numpy as np
import pytest

import pyne_runtime as pn
from pyne_runtime.context import PyneContext
from pyne_runtime.incremental.context import IncrementalContext
from pyne_runtime.incremental.request import _RangeCachingProvider
from pyne_runtime.request import RequestModule


def bar(time, value=1, **extra):
    return dict(time=time, open=value, high=value + 2, low=value - 2,
                close=value, volume=3, **extra)


class Provider:
    def __init__(self, rows=(), watermark=None):
        self.rows = list(rows)
        self.watermark = watermark
        self.calls = []
        self.metadata_calls = 0

    def get_ohlcv(self, symbol, timeframe, start, end):
        rows = [row for row in self.rows if start <= row["time"] <= end]
        self.calls.append((start, end, len(rows)))
        return copy.deepcopy(rows)

    def get_finalized_through(self, *args):
        return self.watermark

    def get_request_metadata(self, symbol, timeframe):
        self.metadata_calls += 1
        return {"syminfo": {"tickerid": symbol}, "timeframe": timeframe}


def values(session, title):
    return [point["value"] for line in session.snapshot_result().lines
            if line["name"] == title for point in line["data"]]


@pytest.mark.parametrize("watermark", [None, 1000])
@pytest.mark.parametrize("mode", ["field", "callable"])
def test_lower_tf_duplicate_rows_survive_cache_preview_and_restore(watermark, mode):
    rows = [bar(0, 1), bar(0, 2), bar(10, 3), bar(60, 4), bar(60, 5), bar(120, 6)]
    provider = Provider(rows, watermark)
    expression = '"close"' if mode == "field" else "lambda req: req.close"
    script = f'''
indicator("Duplicates", mode="incremental")
def on_bar(ctx, bar):
    group = ctx.request.security_lower_tf("TEST", "10S", {expression})
    ctx.plot("Count", group.size())
    ctx.plot("Sum", group.sum())
'''
    settings = pn.PyneSettings(data_provider=provider, timeframe="1")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed([bar(0), bar(60)])
    assert values(session, "Count") == [3., 2.]
    assert values(session, "Sum") == [6., 9.]
    assert session._globals["request"].cache_stats()["bars"] == (0 if watermark is None else 3)
    for snapshot_mode in ("local", "state", "replay"):
        restored = (pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=script, settings=settings) if snapshot_mode == "local" else
            pn.PyneIncrementalSession.from_portable_snapshot(
                session.snapshot_portable(mode=snapshot_mode), script=script, settings=settings))
        before = restored.snapshot_portable_state()
        preview = restored.on_bar_updated(bar(120))
        assert preview.ok
        assert restored.snapshot_portable_state() == before
        restored.on_bar_closed(bar(120))
        assert values(restored, "Count") == [3., 2., 1.]
        assert values(restored, "Sum") == [6., 9., 6.]


@pytest.mark.parametrize("bad", ["missing", "infinity", "bad_high", "invalid_close"])
@pytest.mark.parametrize("watermark", [None, 100])
def test_caught_malformed_provider_batch_cannot_poison_a_healthy_session(bad, watermark):
    invalid = bar(0, 7)
    if bad == "missing":
        invalid.pop("close")
    elif bad == "infinity":
        invalid["volume"] = float("inf")
    elif bad == "bad_high":
        invalid["high"] = invalid["low"] - 1
    else:
        invalid["time_close"] = float("inf")
    provider = Provider([invalid, bar(10, 8)], watermark)
    script = '''
indicator("Caught request", mode="incremental")
def on_bar(ctx, bar):
    try:
        ctx.plot("Recovered", ctx.request.security("TEST", "10S", "close[2]"))
        ctx.plot("Success", 1)
    except Exception:
        ctx.plot("Success", 0)
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert values(session, "Success") == [0., 0.]
    stats = session._globals["request"].cache_stats()
    assert stats["bars"] == 0 and stats["coveredRanges"] == 0
    provider.rows = [bar(0, 7), bar(10, 8), bar(20, 9)]
    session.on_bar_closed(bar(20))
    assert values(session, "Success") == [0., 0., 1.]
    assert values(session, "Recovered") == [7.]


def test_duplicate_rows_count_against_budget_and_are_recoverable_after_eviction():
    provider = Provider([bar(0, 1), bar(0, 2), bar(0, 3)], 100)
    cache = _RangeCachingProvider(provider, max_cached_bars=2, max_covered_ranges=32)
    cache.begin_evaluation(100)
    for _ in range(2):
        assert [row["close"] for row in cache.get_ohlcv("TEST", "10S", 0, 0)] == [1, 2, 3]
        assert cache.stats()["bars"] == 0
        assert cache.stats()["finalizedThrough"] == []
    assert len(provider.calls) == 2


def test_python_thunks_receive_real_context_reexecute_and_share_mutations_in_callback():
    provider = Provider([bar(0, 2), bar(10, 3), bar(20, 4), bar(30, 5)], 100)
    script = '''
indicator("Ordinary Python", mode="incremental")
calls = []
def expression(req):
    from pyne_runtime.context import PyneContext
    assert type(req.context) is PyneContext
    assert not hasattr(req.context, "rows")
    calls.append(req.context.bar_count)
    req.context.close.values[:] += 10
    return req.close
def on_bar(ctx, bar):
    ctx.plot("First", ctx.request.security("TEST", "10S", expression))
    ctx.plot("Second", ctx.request.security("TEST", "10S", expression))
    ctx.plot("Field", ctx.request.security("TEST", "10S", "close"))
    ctx.plot("Calls", len(calls))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert values(session, "First") == [12., 13.]
    assert values(session, "Second") == [22., 23.]
    assert values(session, "Field") == [22., 23.]
    assert values(session, "Calls") == [2., 4.]
    assert provider.metadata_calls == 2
    before = session.snapshot_portable_state()
    session.on_bar_updated(bar(20))
    assert session.snapshot_portable_state() == before
    session.on_bar_closed(bar(20))
    assert values(session, "Field") == [22., 23., 24.]
    assert values(session, "Calls") == [2., 4., 6.]
    assert [row["close"] for row in provider.rows] == [2, 3, 4, 5]


@pytest.mark.parametrize("requested_tf", ["5S", "20S", "1", "1M"])
@pytest.mark.parametrize("gaps,lookahead", [("off", "off"), ("on", "off"),
                                           ("off", "on"), ("on", "on")])
def test_current_fields_match_full_prefix_evaluation_with_duplicate_and_irregular_times(
        requested_tf, gaps, lookahead):
    rows = [bar(t, index + .25, time_close=t + 40) for index, t in enumerate(
        [0, 0, 5, 20, 40, 40, 80, 110, 200])]
    provider = Provider(rows)
    expression = ("open", "hl2", "hlc3[1]", "ohlc4", "hlcc4[2]", "time", "close[999999999999]")
    script = f'''
indicator("Prefix projection", mode="incremental")
def on_bar(ctx, bar):
    result = ctx.request.security("TEST", {requested_tf!r}, {expression!r},
                                  gaps={gaps!r}, lookahead={lookahead!r})
    for i, value in enumerate(result):
        ctx.plot(str(i), value)
'''
    settings = pn.PyneSettings(data_provider=provider, timeframe="10S")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    charts = [bar(t, time_close=t + 13) for t in [0, 10, 30, 60, 120]]
    expected = [[] for _ in expression]
    for index, chart in enumerate(charts):
        session.on_bar_closed(chart)
        oracle = RequestModule(PyneContext.from_ohlcv(charts[:index + 1], timeframe="10S"), provider)
        result = oracle.security("TEST", requested_tf, expression, gaps=gaps, lookahead=lookahead)
        for column, item in zip(expected, result):
            column.append(item.values[-1])
    for index, column in enumerate(expected):
        np.testing.assert_allclose(values(session, str(index)),
                                   [value for value in column if not np.isnan(value)],
                                   rtol=0, atol=0, equal_nan=True)


@pytest.mark.parametrize("count", [128, 512])
def test_finalized_field_projection_does_no_full_history_copy_or_context_build(count, monkeypatch):
    rows = [bar(t) for t in range(0, (count + 1) * 10, 10)]
    times = [row["time"] for row in rows]

    class IndexedProvider(Provider):
        def get_ohlcv(self, symbol, timeframe, start, end):
            selected = rows[bisect_left(times, start):bisect_right(times, end)]
            self.calls.append((start, end, len(selected)))
            return copy.deepcopy(selected)

    provider = IndexedProvider(rows)
    script = '''
indicator("Field work", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("First", ctx.request.security("TEST", "10S", "close"))
    ctx.plot("Second", ctx.request.security("TEST", "10S", "close[1]"))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))

    def no_full_history(*args, **kwargs):
        pytest.fail("Literal field request built/copied the complete historical context")

    monkeypatch.setattr(IncrementalContext, "request_bars", no_full_history)
    monkeypatch.setattr(PyneContext, "from_ohlcv", no_full_history)
    for timestamp in range(0, count * 10, 10):
        provider.watermark = timestamp - 10
        session.on_bar_closed(bar(timestamp))
    assert values(session, "First") == [1.] * count
    assert values(session, "Second") == [1.] * (count - 1)
    assert sum(call[2] for call in provider.calls) <= 3 * count
    assert provider.metadata_calls == count


def test_time_close_and_exposed_chart_history_keep_full_context_semantics():
    provider = Provider([bar(0, time_close=19), bar(10), bar(20)], 100)
    script = '''
indicator("Exposed history", mode="incremental")
def on_bar(ctx, bar):
    history = ctx._request_bars
    if history:
        history[-1]["time_close"] = bar.time + 2
    ctx.plot("Close time", ctx.request.security("TEST", "10S", "time_close"))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert values(session, "Close time") == [19., 20.]


def test_callable_fallback_reuses_one_full_requested_context_without_chart_copy(monkeypatch):
    provider = Provider([bar(0), bar(10), bar(20), bar(30)], 100)
    script = '''
indicator("Thunk reuse", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("First", ctx.request.security("TEST", "10S", lambda req: req.close))
    ctx.plot("Second", ctx.request.security("TEST", "10S", lambda req: req.close))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    original = PyneContext.from_ohlcv.__func__
    builds = []

    def counted(cls, rows, **kwargs):
        assert kwargs.get("require_unique_times") is False
        builds.append(len(rows))
        return original(cls, rows, **kwargs)

    def forbidden(*args):
        pytest.fail("Ordinary thunk copied chart history")

    monkeypatch.setattr(PyneContext, "from_ohlcv", classmethod(counted))
    monkeypatch.setattr(IncrementalContext, "request_bars", forbidden)
    session.seed([bar(0), bar(10), bar(20)])
    assert builds == [2, 3, 4]
    assert values(session, "First") == values(session, "Second") == [1., 1., 1.]


def test_exposed_history_same_callback_cache_hit_keeps_original_context():
    provider = Provider([bar(0), bar(10), bar(20)], 100)
    script = '''
indicator("Aliased cache hit", mode="incremental")
def on_bar(ctx, bar):
    history = ctx._request_bars
    ctx.plot("First", ctx.request.security("TEST", "10S", "close"))
    if history:
        history[0].pop("close")
    ctx.plot("Second", ctx.request.security("TEST", "10S", "close"))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert values(session, "First") == values(session, "Second") == [1., 1.]


@pytest.mark.parametrize("mutation", ["rebind", "inplace"])
def test_security_thunk_keeps_pre_call_times_reference_with_original_mutability(mutation):
    provider = Provider([bar(0, 2), bar(10, 3), bar(20, 4)], 100)
    change = ('req.context.times = [t + 1000 for t in req.context.times]' if mutation == "rebind" else
              'req.context.times[:] = [t + 1000 for t in req.context.times]')
    script = f'''
indicator("Time reference", mode="incremental")
def expression(req):
    {change}
    return req.close
def on_bar(ctx, bar):
    ctx.plot("Value", ctx.request.security("TEST", "10S", expression))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert values(session, "Value") == ([2., 3.] if mutation == "rebind" else [])


@pytest.mark.parametrize("first", ["field", "thunk"])
def test_prior_field_read_preserves_derived_cache_before_python_array_mutation(first):
    provider = Provider([bar(0, 2), bar(10, 3), bar(20, 4)], 100)
    preceding = ('ctx.request.security("TEST", "10S", "close")' if first == "field" else
                 'ctx.request.security("TEST", "10S", lambda req: req.close)')
    script = f'''
indicator("Derived cache", mode="incremental")
def expression(req):
    req.context.close.values[:] += 10
    return req.hlc3
def on_bar(ctx, bar):
    {preceding}
    ctx.plot("Value", ctx.request.security("TEST", "10S", expression))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    np.testing.assert_allclose(values(session, "Value"),
                               [2., 3.] if first == "field" else [2 + 10/3, 3 + 10/3], rtol=0, atol=1e-15)


@pytest.mark.parametrize("withdrawal", [None, True, -1])
def test_retracted_finality_refetches_new_duplicate_rows_at_an_existing_coordinate(withdrawal):
    provider = Provider([bar(0, 1)], 100)
    cache = _RangeCachingProvider(provider, max_cached_bars=100, max_covered_ranges=32)
    cache.begin_evaluation(100)
    assert [row["close"] for row in cache.get_ohlcv("TEST", "10S", 0, 0)] == [1]
    assert cache.stats()["bars"] == 1
    provider.watermark = withdrawal
    provider.rows.append(bar(0, 2))
    cache.begin_evaluation(110)
    assert [row["close"] for row in cache.get_ohlcv("TEST", "10S", 0, 0)] == [1, 2]
    assert cache.stats()["finalityFallbacks"] == 1
    assert cache.stats()["bars"] == 0


def test_unpromised_duplicate_arrival_and_revision_refresh_in_live_and_restored_session():
    provider = Provider([bar(0, 1)])
    script = '''
indicator("Later duplicate", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Count", ctx.request.security("TEST", "10S", lambda req: req.context.bar_count))
    ctx.plot("Sum", ctx.request.security("TEST", "10S", lambda req: sum(req.close.values)))
'''
    settings = pn.PyneSettings(data_provider=provider, timeframe="10S")
    live = pn.PyneIncrementalSession(script=script, settings=settings)
    live.seed([bar(0)])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        live.snapshot_portable_state(), script=script, settings=settings)
    provider.rows.append(bar(0, 2))
    for session in (live, restored):
        session.on_bar_closed(bar(10))
        assert values(session, "Count") == [1., 2.]
        assert values(session, "Sum") == [1., 3.]
        assert session._globals["request"].cache_stats()["bars"] == 0
    provider.rows[0] = bar(0, 4)
    live.on_bar_closed(bar(20))
    assert values(live, "Sum") == [1., 3., 6.]


@pytest.mark.parametrize("policy", ["raise", "call", "log"])
def test_literal_field_preserves_numpy_eager_derived_error_policy(policy):
    value = np.finfo(float).max / 2
    row = dict(time=0, open=value, high=value, low=value, close=value, volume=1)
    provider = Provider([row], 100)
    script = '''
indicator("NumPy error policy", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Value", ctx.request.security("TEST", "10S", "close"))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    events = []

    class Log:
        def write(self, message):
            events.append(message)

    old_callback = np.geterrcall()
    try:
        np.seterrcall(Log() if policy == "log" else lambda *args: events.append(args))
        with np.errstate(over=policy):
            if policy == "raise":
                with pytest.raises(FloatingPointError):
                    session.seed([bar(0)])
            else:
                session.seed([bar(0)])
                assert events
                assert values(session, "Value") == [value]
    finally:
        np.seterrcall(old_callback)


def test_mutated_multi_field_error_retains_sequential_derived_cache_side_effects():
    class MutatingProvider(Provider):
        def get_ohlcv(self, *args):
            self.runtime._globals["expression"][1] = "unsupported"
            return super().get_ohlcv(*args)

    provider = MutatingProvider([bar(0, 2)], 100)
    script = '''
indicator("Sequential field failure", mode="incremental")
expression = ["close", "hl2"]
def changed(req):
    req.context.close.values[:] += 10
    return req.hlc3
def on_bar(ctx, bar):
    try:
        ctx.request.security("TEST", "10S", expression)
    except Exception:
        ctx.plot("Caught", 1)
    ctx.plot("Derived", ctx.request.security("TEST", "10S", changed))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    provider.runtime = session
    session.seed([bar(0)])
    assert values(session, "Caught") == [1.]
    assert values(session, "Derived") == [2.]
