"""Request projection respects Python metadata, floating policy and quotas."""
import copy

import numpy as np
import pytest

import pyne_runtime as pn
from pyne_runtime.metadata import TimeframeInfo
from pyne_runtime.request import RequestModule
from pyne_runtime.security import PyneResourceLimitError
from pyne_runtime.context import PyneContext


def bar(time, value=1, **extra):
    return dict(time=time, open=value, high=value, low=value, close=value, volume=1, **extra)


class Provider:
    def __init__(self, rows):
        self.rows = rows

    def get_ohlcv(self, symbol, timeframe, start, end):
        return copy.deepcopy([row for row in self.rows if start <= row["time"] <= end])


def points(session, title):
    return [point["value"] for line in session.snapshot_result().lines
            if line["name"] == title for point in line["data"]]


def test_deferred_derived_fields_keep_the_error_policy_at_the_first_field_read():
    row = bar(0, 0)
    row["high"] = float.fromhex("0x0.0000000000001p-1022")
    provider = Provider([row])
    full = RequestModule(PyneContext.from_ohlcv([bar(0)], timeframe="10S"), provider)
    full.security("TEST", "10S", "close")
    with np.errstate(under="raise"):
        expected = full.security("TEST", "10S", lambda req: req.hlc3).values[-1]
    script = '''
import numpy as np
indicator("Prior floating policy", mode="incremental")
def on_bar(ctx, bar):
    ctx.request.security("TEST", "10S", "close")
    with np.errstate(under="raise"):
        ctx.plot("Value", ctx.request.security("TEST", "10S", lambda req: req.hlc3))
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0)])
    assert points(session, "Value") == [expected] == [0.]


@pytest.mark.parametrize("expression", ['"close"', '("close", "high")', 'lambda req: req.close'])
def test_lower_tf_array_budget_rejects_oversize_results_and_recovers(expression):
    provider = Provider([bar(0), bar(0), bar(5)])
    script = f'''
indicator("Lower array budget", mode="incremental")
def on_bar(ctx, bar):
    try:
        value = ctx.request.security_lower_tf("TEST", "5S", {expression})
        values = value if isinstance(value, tuple) else (value,)
        ctx.plot("Count", values[0].size())
        ctx.plot("Accepted", 1)
    except Exception:
        ctx.plot("Accepted", 0)
'''
    session = pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(
        data_provider=provider, timeframe="10S", max_array_size=1))
    session.seed([bar(0)])
    assert points(session, "Accepted") == [0.]
    provider.rows = [bar(10)]
    session.on_bar_closed(bar(10))
    assert points(session, "Accepted") == [0., 1.]
    assert points(session, "Count") == [1.]


@pytest.mark.parametrize("mode", ["live", "local", "state", "replay"])
def test_lower_tf_result_keeps_selected_budget_on_mutation_preview_and_restore(mode):
    provider = Provider([bar(0), bar(10), bar(20)])
    script = '''
indicator("Bound lower result", mode="incremental")
def on_bar(ctx, bar):
    value = ctx.request.security_lower_tf("TEST", "5S", "close")
    ctx.state("saved", None).value = value
    try:
        value.push(99)
        ctx.plot("Rejected", 0)
    except Exception:
        ctx.plot("Rejected", 1)
    ctx.plot("Count", value.size())
'''
    settings = pn.PyneSettings(data_provider=provider, timeframe="10S", max_array_size=1)
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed([bar(0)])
    if mode == "local":
        session = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script, settings=settings)
    elif mode != "live":
        session = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=script, settings=settings)
    before = session.snapshot_portable_state()
    assert session.on_bar_updated(bar(10)).ok
    assert session.snapshot_portable_state() == before
    session.on_bar_closed(bar(10))
    assert points(session, "Rejected") == [1., 1.]
    assert points(session, "Count") == [1., 1.]


def test_lower_tf_default_unlimited_and_selected_depth_remain_independent():
    provider = Provider([bar(0), bar(0), bar(5)])
    script = '''
indicator("Unbounded lower", mode="incremental")
def on_bar(ctx, bar):
    value = ctx.request.security_lower_tf("TEST", "5S", "close")
    value.push(99)
    ctx.plot("Count", value.size())
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0)])
    assert points(session, "Count") == [4.]
    nested = '''
indicator("Nested lower", mode="incremental")
def on_bar(ctx, bar):
    ctx.request.security_lower_tf("TEST", "5S", lambda req: [array.from_values(value) for value in req.close.values])
'''
    limited = pn.PyneIncrementalSession(script=nested, settings=pn.PyneSettings(
        data_provider=provider, timeframe="10S", max_collection_depth=1))
    with pytest.raises(PyneResourceLimitError):
        limited.seed([bar(0)])


def test_lower_tf_limit_is_checked_before_materializing_group_values(monkeypatch):
    from pyne_runtime.request._current import _FieldValues

    provider = Provider([bar(0), bar(0), bar(5)])
    script = '''
indicator("Admission before group", mode="incremental")
def on_bar(ctx, bar):
    ctx.request.security_lower_tf("TEST", "5S", "close")
'''
    session = pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(
        data_provider=provider, timeframe="10S", max_array_size=1))

    def forbidden(*args):
        pytest.fail("Rejected request materialized group values")

    monkeypatch.setattr(_FieldValues, "__getitem__", forbidden)
    with pytest.raises(PyneResourceLimitError, match="array size 3 exceeds limit 1"):
        session.seed([bar(0)])


def test_custom_requested_metadata_methods_execute_with_bound_history_on_every_callback():
    calls = []

    class CustomTimeframe(TimeframeInfo):
        def in_seconds(self, timeframe=None):
            calls.append(tuple(self._times))
            return 10

    class MetadataProvider(Provider):
        def get_request_metadata(self, symbol, timeframe):
            return {"timeframe": CustomTimeframe("10S")}

    provider = MetadataProvider([bar(0), bar(10), bar(20)])
    script = '''
indicator("Metadata methods", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Value", ctx.request.security("TEST", "10S", "close"))
    ctx.request.security("TEST", "10S", "close")
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(data_provider=provider, timeframe="10S"))
    session.seed([bar(0), bar(10)])
    assert calls == [(0, 10), (0, 10, 20)]
    assert points(session, "Value") == [1., 1.]


def test_custom_chart_metadata_keeps_timeline_binding_for_provider_close_boundary():
    class BoundDuration(TimeframeInfo):
        def in_seconds(self, timeframe=None):
            return 10 * len(self._times)

    class RecordingProvider(Provider):
        def get_ohlcv(self, symbol, timeframe, start, end):
            self.end = end
            return super().get_ohlcv(symbol, timeframe, start, end)

    provider = RecordingProvider([bar(0), bar(10)])
    script = '''
indicator("Chart metadata binding", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Value", ctx.request.security("TEST", "10S", "close"))
'''
    session = pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(
        data_provider=provider, timeframe=BoundDuration("10S")))
    session.seed([bar(0)])
    assert provider.end == 10
