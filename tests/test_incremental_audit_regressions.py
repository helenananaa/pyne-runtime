"""Public isolation, continuation and bounded-history regressions from audit."""

from __future__ import annotations

import copy

import pyne_runtime as pn
import pytest

import pyne_runtime.incremental.context as context_module


def _bar(time: int, close: float = 1, **extra):
    return dict(time=time, open=close, high=close, low=close, close=close, volume=0, **extra)


SIMPLE = '''
indicator("Audit", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Close", bar.close)
'''


def _restore(session, script, mode):
    if mode == "local":
        return pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script)
    return pn.PyneIncrementalSession.from_portable_snapshot(
        session.snapshot_portable(mode=mode), script=script
    )


@pytest.mark.parametrize("method", ("seed", "closed", "snapshot"))
def test_result_point_and_metadata_mutation_cannot_change_committed_output(method):
    script = '''
indicator("Detached", mode="incremental")
def init(ctx):
    ctx.meta["custom"] = {"values": [1]}
def on_bar(ctx, bar):
    ctx.plot("Close", bar.close)
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Bars")
    ctx.marker(True, text="event")
'''
    session = pn.PyneIncrementalSession(script=script)
    result = session.seed([_bar(1)])
    if method == "closed":
        result = session.on_bar_closed(_bar(2))
    elif method == "snapshot":
        result = session.snapshot_result()
    before = copy.deepcopy(session.snapshot_result())
    result.lines[0]["data"][0]["value"] = 999
    result.output["lines"][0]["data"][0]["time"] = -1
    result.output["candles"][0]["data"][0]["close"] = 888
    result.output["markers"][0]["data"][0]["text"] = "changed"
    result.meta["custom"]["values"].append(2)
    assert session.snapshot_result() == before


CALLBACKS = '''
indicator("Callback graph", mode="incremental")
values = []
def helper(ctx, bar, bucket=values):
    bucket.append(bar.close)
    ctx.plot("Count", len(bucket))
def init(ctx):
    ctx.saved_helper = helper
    ctx.nested = {"callbacks": [helper]}
    ctx.state("callback", helper)
    ctx.cached_helper = cache("callback", lambda: helper)
def on_bar(ctx, bar):
    assert ctx.saved_helper is helper
    assert ctx.nested["callbacks"][0] is helper
    assert ctx.state("callback").value is helper
    assert ctx.cached_helper is cache("callback", lambda: helper)
    helper(ctx, bar)
def on_preview(ctx, bar):
    on_bar(ctx, bar)
    previous = ctx.state("callback")[1]
    if previous is not None:
        previous(ctx, bar)
'''


def test_preview_rebinds_context_state_history_cache_and_nested_function_aliases():
    session = pn.PyneIncrementalSession(script=CALLBACKS)
    control = pn.PyneIncrementalSession(script=CALLBACKS)
    session.seed([_bar(1)])
    control.seed([_bar(1)])
    session.on_bar_updated(_bar(2))
    session.on_bar_updated(_bar(2, 2))
    assert session._globals["values"] == [1]
    actual = session.on_bar_closed(_bar(2))
    expected = control.on_bar_closed(_bar(2))
    assert actual.lines == expected.lines
    assert session._globals["values"] == control._globals["values"] == [1, 1]


def test_local_callback_snapshot_is_detached_and_rebinds_the_restored_namespace():
    original = pn.PyneIncrementalSession(script=CALLBACKS)
    original.seed([_bar(1)])
    snapshot = original.snapshot_state()
    # Advancing the origin must not change either function defaults or globals
    # captured by the reusable checkpoint.
    original.on_bar_closed(_bar(2, 2))
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=CALLBACKS)
    assert restored._ctx.saved_helper is restored._globals["helper"]
    assert restored._ctx.saved_helper is not original._globals["helper"]
    assert restored._globals["values"] == [1]
    restored.on_bar_updated(_bar(2))
    actual = restored.on_bar_closed(_bar(2))
    assert actual.lines[0]["data"] == [{"time": 2, "value": 2.0}]
    assert original._globals["values"] == [1, 2]
    assert restored._globals["values"] == [1, 1]
    second = pn.PyneIncrementalSession.from_snapshot(snapshot, script=CALLBACKS)
    assert second._globals["values"] == [1]
    with pytest.raises(pn.PynePortableSnapshotError, match="cannot encode.*function"):
        restored.snapshot_portable_state()


def test_context_global_alias_is_rebound_to_one_preview_context():
    script = '''
indicator("Context alias", mode="incremental")
saved = None
def init(ctx):
    global saved
    saved = ctx
    ctx.values = []
def on_bar(ctx, bar):
    assert saved is ctx
    ctx.values.append(bar.close)
    ctx.plot("Size", len(ctx.values))
'''
    session = pn.PyneIncrementalSession(script=script)
    session.seed([_bar(1)])
    session.on_bar_updated(_bar(2))
    assert session._ctx.values == [1]
    assert session.on_bar_closed(_bar(2)).lines[0]["data"][0]["value"] == 2
    restored = _restore(session, script, "local")
    assert restored._globals["saved"] is restored._ctx
    assert restored.on_bar_closed(_bar(3)).lines[0]["data"][0]["value"] == 3


class _UnusedHistory(list):
    def __deepcopy__(self, memo):
        raise AssertionError("unused request history was copied")


@pytest.mark.parametrize("count", (1, 10000))
def test_no_request_preview_never_copies_committed_request_history(count):
    session = pn.PyneIncrementalSession(script=SIMPLE)
    session.seed([_bar(index + 1) for index in range(count)])
    session._ctx._request_bars = _UnusedHistory(session._ctx._request_bars)
    assert session.on_bar_updated(_bar(count + 1)).ok


def test_user_request_history_aliases_materialize_one_isolated_graph():
    script = '''
indicator("Request alias", mode="incremental")
def on_bar(ctx, bar):
    ctx.alias = ctx._request_bars
    ctx.plot("Close", bar.close)
def on_preview(ctx, bar):
    assert ctx.alias is ctx._request_bars
    ctx.alias[0]["payload"]["values"].append(99)
    ctx._request_bars[0]["close"] = 999
    exported = ctx.request_bars()
    exported[0]["payload"]["values"].append(100)
    assert ctx.alias[0]["payload"]["values"] == [1, 99]
    ctx.plot("Close", bar.close)
'''
    session = pn.PyneIncrementalSession(script=script)
    session.seed([_bar(1, payload={"values": [1]})])
    before = session.snapshot_portable_state()
    session.on_bar_updated(_bar(2))
    assert session.snapshot_portable_state() == before
    assert session._ctx._request_bars[0]["close"] == 1
    assert session._ctx.alias[0]["payload"]["values"] == [1]


@pytest.mark.parametrize("channel", ("points", "events"))
def test_full_history_budget_allows_isolated_preview_and_enforces_actual_overlay(channel):
    action = (
        'ctx.plot("Close", bar.close)' if channel == "points"
        else 'line.new(ctx.bar_index, 0, ctx.bar_index, bar.close)'
    )
    script = f'''
indicator("Preview budget", mode="incremental")
def on_bar(ctx, bar):
    ctx.state("history", [1])
    for _ in range(int(bar.close)):
        {action}
'''
    budget = {"max_output_points": 2} if channel == "points" else {"max_object_events": 2}
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(incremental_retention_bars=2, max_output_series=1, **budget),
    )
    session.seed([_bar(1), _bar(2)])
    committed = session._ctx
    before = session.snapshot_portable_state()
    points = committed._limit_tracker.output_points
    events = committed._limit_tracker.object_events
    clone = committed.clone_for_preview()
    assert clone._limit_tracker.output_points == clone._limit_tracker.object_events == 0
    assert clone._limit_tracker.output_series_keys == committed._limit_tracker.output_series_keys
    assert clone._limit_tracker.state_payload_items == committed._limit_tracker.state_payload_items
    assert clone._limit_tracker.strategy_log_entries == committed._limit_tracker.strategy_log_entries
    preview = session.on_bar_updated(_bar(3, 2))
    overlay = (
        preview.lines[0]["data"] if channel == "points"
        else preview.output["object_events"]
    )
    assert len(overlay) == 2
    assert committed._limit_tracker.output_points == points
    assert committed._limit_tracker.object_events == events
    assert session.snapshot_portable_state() == before
    assert session.on_bar_closed(_bar(3)).ok
    healthy_history = copy.deepcopy(committed.to_result())
    error = "Too many output points" if channel == "points" else "object events"
    with pytest.raises(pn.PyneSecurityError, match=error):
        session.on_bar_updated(_bar(4, 3))
    # Over-limit callback output is rejected, and its temporary graph never
    # replaces or mutates the committed context even though the session poisons.
    assert committed.to_result() == healthy_history


@pytest.mark.parametrize("mode", ("local", "state", "replay"))
def test_retention_quota_rolls_without_poison_and_continues_after_restore(mode, monkeypatch):
    retention = 1000
    session = pn.PyneIncrementalSession(
        script=SIMPLE,
        settings=pn.PyneSettings(incremental_retention_bars=retention, max_output_points=retention),
    )
    session.seed([_bar(index + 1) for index in range(retention)])
    calls = 0
    original_point_time = context_module._point_time

    def measured(point):
        nonlocal calls
        calls += 1
        return original_point_time(point)

    monkeypatch.setattr(context_module, "_point_time", measured)
    for timestamp in range(retention + 1, retention + 11):
        session.on_bar_closed(_bar(timestamp))
    # Expiring ten bars should locate old prefixes, never visit the ten thousand
    # remaining points or request rows repeatedly.
    assert calls < 400
    result = session.snapshot_result()
    assert result.meta["retainedBars"] == retention
    assert len(result.lines[0]["data"]) == retention
    assert result.lines[0]["data"][0]["time"] == 11
    with pytest.raises(ValueError, match="strictly increasing"):
        session.on_bar_closed(_bar(retention + 10))
    assert session.snapshot_result() == result
    restored = _restore(session, SIMPLE, mode)
    assert restored.on_bar_closed(_bar(retention + 11)).lines == session.on_bar_closed(
        _bar(retention + 11)
    ).lines
    assert len(restored._ctx._request_bars) == retention


@pytest.mark.parametrize("count", (2, 3, 100))
def test_seed_obeys_replay_recording_budget_without_rejecting_computation(count):
    session = pn.PyneIncrementalSession(
        script=SIMPLE, settings=pn.PyneSettings(replay_history_bars=2)
    )
    result = session.seed([_bar(index + 1) for index in range(count)])
    assert result.meta["totalCommittedBars"] == count
    assert len(result.lines[0]["data"]) == count
    if count > 2:
        assert session._portable_bars == []
        with pytest.raises(pn.PynePortableSnapshotError, match="history exceeded replay_history_bars"):
            session.snapshot_portable()
        restored = _restore(session, SIMPLE, "state")
    else:
        restored = _restore(session, SIMPLE, "replay")
    assert restored.snapshot_result() == session.snapshot_result()
    assert restored.on_bar_closed(_bar(count + 1)).ok


@pytest.mark.parametrize("mode", ("local", "state", "replay"))
def test_exact_output_names_keep_separate_stable_ids_after_restore(mode):
    script = '''
indicator("Names", mode="incremental")
names = ("均线", "均量", "MA", "ma", "A-B", "A B", "a_b")
def on_bar(ctx, bar):
    for value, name in enumerate(names):
        ctx.plot(name, value)
    ctx.plotcandle(1, 1, 1, 1, "价格")
    ctx.plotcandle(2, 2, 2, 2, "成交")
    ctx.marker(True, text="买入")
    ctx.marker(True, text="卖出")
'''
    session = pn.PyneIncrementalSession(script=script)
    result = session.seed([_bar(1), _bar(2)])
    assert len(result.lines) == len({line["id"] for line in result.lines}) == 7
    assert [line["data"][0]["value"] for line in result.lines] == list(range(7))
    assert len(result.output["candles"]) == len(result.output["markers"]) == 2
    restored = _restore(session, script, mode)
    actual = restored.on_bar_closed(_bar(3))
    assert actual.lines == session.on_bar_closed(_bar(3)).lines
    assert [line["id"] for line in actual.lines] == [line["id"] for line in result.lines]
