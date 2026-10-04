from __future__ import annotations

import copy
import threading
from dataclasses import replace

import pyne_runtime as pn
import pytest

from pyne_runtime.cache import PyneCache, PyneCacheSnapshot, PyneCacheSnapshotEntry
from pyne_runtime.historical import HistoricalSession
from pyne_runtime.incremental.checkpoint import PortableStateCheckpoint, encode_portable_state_checkpoint


def bar(time: int):
    return dict(time=time, open=1, high=2, low=0, close=1, volume=1)


SCRIPT = 'def on_bar(ctx, bar):\n    ctx.plot("x",bar.close)'


@pytest.mark.parametrize("malformation", ["different-time", "equity-none", "equity-mapping", "equity-bad-time",
                                          "equity-bad-value", "equity-bad-entry", "realtime-horizon", "missing-init"])
def test_historical_restore_rejects_inconsistent_state_without_changing_continuation(malformation):
    horizon = [bar(1), bar(2), bar(3)]
    donor = HistoricalSession(SCRIPT, horizon)
    donor.advance(1)
    snapshot = donor.snapshot()
    if malformation == "different-time":
        unrelated = pn.PyneIncrementalSession(script=SCRIPT)
        unrelated.seed([bar(10)])
        snapshot["state"] = unrelated.snapshot_state()
    elif malformation == "equity-none":
        snapshot["equity"] = None
    elif malformation == "equity-mapping":
        snapshot["equity"] = {"x": 1}
    elif malformation == "equity-bad-time":
        snapshot["equity"][0]["time"] = 10
    elif malformation == "equity-bad-value":
        snapshot["equity"][0]["value"] = "bad"
    elif malformation == "equity-bad-entry":
        snapshot["equity"][0] = None
    elif malformation == "realtime-horizon":
        unrelated = pn.PyneIncrementalSession(script=SCRIPT)
        unrelated.on_bar_closed(bar(1))
        snapshot["state"] = unrelated.snapshot_state()
    else:
        snapshot.update(cursor=0, equity=[], state=pn.PyneIncrementalSession(script=SCRIPT).snapshot_state())
    target, control = HistoricalSession(SCRIPT, horizon), HistoricalSession(SCRIPT, horizon)
    target.advance(2)
    control.advance(2)
    before = target._session.snapshot_portable_state(), copy.deepcopy(target.equity)
    with pytest.raises((TypeError, ValueError)):
        target.restore(snapshot)
    assert target.cursor == 2
    assert (target._session.snapshot_portable_state(), target.equity) == before
    assert target.advance(3) == control.advance(3)


def test_fixed_horizon_retention_checkpoint_restores_its_exact_prefix():
    settings = pn.PyneSettings(incremental_retention_bars=1, max_output_points=1)
    horizon = [bar(t) for t in range(1, 5)]
    target = HistoricalSession(SCRIPT, horizon, settings=settings)
    target.advance(2)
    snapshot = target.snapshot()
    expected = target.advance(4)
    target.restore(snapshot)
    assert target.advance(4) == expected


def test_same_key_factory_reentrancy_rejects_without_deadlock_or_pending_leak():
    manager = pn.PyneIncrementalSessionManager()
    with pytest.raises(RuntimeError, match="Reentrant acquisition"):
        manager.acquire("same", lambda: manager.acquire("same", object))
    assert manager._pending_creations == {} and manager._creation_owners == {}
    lease = manager.acquire("same", object)
    manager.release("same", shared=lease)
    assert manager.snapshot()["sessions"] == 0


def test_caught_factory_reentrancy_does_not_break_concurrent_waiters():
    manager = pn.PyneIncrementalSessionManager()
    started, finish = threading.Event(), threading.Event()
    result, errors = [], []

    def factory():
        with pytest.raises(RuntimeError, match="Reentrant acquisition"):
            manager.acquire("same", object)
        started.set()
        assert finish.wait(5)
        return object()

    def acquire(factory):
        try:
            result.append(manager.acquire("same", factory))
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=acquire, args=(factory,))
    second = threading.Thread(target=acquire, args=(lambda: pytest.fail("Only first factory executes"),))
    first.start()
    assert started.wait(5)
    second.start()
    finish.set()
    for thread in (first, second):
        thread.join(5)
        assert not thread.is_alive()
    assert not errors and len(result) == 2 and result[0] is result[1]
    assert result[0].ref_count == 2
    manager.release("same", shared=result[0])
    manager.release("same", shared=result[1])
    assert manager.snapshot()["sessions"] == 0


def test_factory_reentrancy_with_a_different_key_remains_valid():
    manager = pn.PyneIncrementalSessionManager()
    inner = []

    def factory():
        inner.append(manager.acquire("inner", object))
        return object()

    outer = manager.acquire("outer", factory)
    assert set(manager.snapshot()["keys"]) == {"inner", "outer"}
    manager.release("inner", shared=inner[0])
    manager.release("outer", shared=outer)
    assert manager.snapshot()["sessions"] == 0


def test_bulk_cache_shrink_selects_lru_entries_without_quadratic_rescanning():
    count = 2048
    cache = PyneCache(max_items=count)
    snapshot = PyneCacheSnapshot(count, tuple(PyneCacheSnapshotEntry(str(i), i, None, i // 2) for i in range(count)))
    cache.restore_state(snapshot)

    class CountReads(dict):
        reads = 0

        def __getitem__(self, key):
            self.reads += 1
            return super().__getitem__(key)

    indexed = CountReads(cache._items)
    cache._items = indexed
    cache.configure(max_items=3)
    assert set(cache.stats()["keys"]) == {"0", "1", "3"}
    assert indexed.reads <= 2 * count
    restored = PyneCache()
    restored.restore_state(replace(snapshot, max_items=3))
    assert set(restored.stats()["keys"]) == {"0", "1", "3"}


BUDGET_CASES = {
    "output_points": (SCRIPT, "max_output_points", 1),
    "output_series": ('def on_bar(ctx,bar):\n    ctx.plot("x",1)\n    ctx.plot("y",1)', "max_output_series", 1),
    "object_events": ('def on_bar(ctx,bar):\n    ctx.line_new(0,1,1,2)', "max_object_events", 1),
    "table_cells": ('def init(ctx):\n    ctx.state("t",ctx.table_new(columns=2,rows=1))\ndef on_bar(ctx,bar):\n'
                    '    ctx.table_cell(ctx.state("t").value,0,0,"a")\n    ctx.table_cell(ctx.state("t").value,1,0,"b")', "max_table_cells", 1),
    "state_payload_items": ('def on_bar(ctx,bar):\n    ctx.state("s",[]).value.append("long")', "max_state_payload_items", 1),
    "varip_payload_items": ('def on_bar(ctx,bar):\n    ctx.varip("s","long")', "max_state_payload_items", 1),
    "total_window_items": ('def init(ctx):\n    ctx.window("w",3)\n    ctx.ta.sma("ma",4)\ndef on_bar(ctx,bar):\n    pass', "max_total_window_items", 1),
    "largest_window_size": ('def init(ctx):\n    ctx.ta.sma("ma",4)\ndef on_bar(ctx,bar):\n    pass', "max_window_size", 1),
    "strategy_log_entries": ('def on_bar(ctx,bar):\n    ctx.strategy.entry("L",ctx.strategy.long,qty=1)\n    ctx.strategy.close("L")', "max_strategy_log_entries", 1),
}


@pytest.mark.parametrize("counter", BUDGET_CASES)
@pytest.mark.parametrize("mode", ["local", "typed"])
def test_snapshot_cannot_understate_real_retained_budget(counter, mode):
    script, budget, maximum = BUDGET_CASES[counter]
    source = pn.PyneIncrementalSession(script=script)
    source.seed([bar(1), bar(2)])
    snapshot = source.snapshot_state()
    setattr(snapshot.context._limit_tracker, counter, 0)
    if counter == "output_series":
        snapshot.context._limit_tracker.output_series_keys.clear()
    settings = pn.PyneSettings(**{budget: maximum})
    target = pn.PyneIncrementalSession(script=script, settings=settings)
    before = target.snapshot_portable_state()
    if mode == "local":
        with pytest.raises(ValueError):
            target.restore_state(snapshot)
    else:
        snapshot = replace(snapshot, function_bindings={}, detached_functions=(), portable_bars=(),
                           portable_seed_count=0, portable_complete=False)
        payload = encode_portable_state_checkpoint(PortableStateCheckpoint(
            script_sha256=snapshot.script_sha256, settings=snapshot.settings_contract,
            provider_required=False, snapshot=snapshot))
        with pytest.raises(ValueError):
            pn.PyneIncrementalSession.from_portable_snapshot(payload, script=script, settings=settings)
    assert target.snapshot_portable_state() == before
    assert target._ctx is None and target._poisoned_reason is None


@pytest.mark.parametrize("defect", ["time", "bar-index", "context-index", "confirmed", "ta-tracker", "tracker-limits", "state-tracker"])
def test_inconsistent_committed_shape_rejects_atomically(defect):
    source = pn.PyneIncrementalSession(script='def on_bar(ctx,bar):\n    ctx.state("s",0).value+=1')
    source.seed([bar(1)])
    snapshot = source.snapshot_state()
    context = snapshot.context
    if defect == "time":
        context.current_bar.time = 10
    elif defect == "bar-index":
        context.current_bar.bar_index = 100
    elif defect == "context-index":
        context.bar_index = 100
    elif defect == "confirmed":
        context.current_bar.is_confirmed = False
    elif defect == "ta-tracker":
        context.ta._limits = copy.copy(context._limit_tracker)
    elif defect == "tracker-limits":
        context._limit_tracker.limits = copy.copy(context._limits)
    else:
        object.__setattr__(context._states["s"], "_StateCell__limit_tracker", copy.copy(context._limit_tracker))
    target = pn.PyneIncrementalSession(script=source.script)
    target.seed([bar(5)])
    before = target.snapshot_portable_state()
    with pytest.raises(ValueError):
        target.restore_state(snapshot)
    assert target.snapshot_portable_state() == before
    assert target.on_bar_closed(bar(6)).ok


def test_typed_history_with_interned_dictionary_keys_preserves_unlimited_continuation():
    script = 'def on_bar(ctx,bar):\n    ctx.state("s",[]).value.append({"time":bar.time,"close":bar.close})'
    source = pn.PyneIncrementalSession(script=script)
    source.seed([bar(t) for t in range(1, 6)])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(source.snapshot_portable_state(), script=script)
    assert restored.on_bar_closed(bar(6)) == source.on_bar_closed(bar(6))
    assert restored._ctx._states["s"].value == source._ctx._states["s"].value


def test_preview_bar_payload_cannot_mutate_caller_or_committed_aliases():
    script = '''def on_bar(ctx,bar):
    if bar.is_confirmed:
        ctx.saved = bar.raw["custom"]
    else:
        bar.raw["custom"].append("preview")
    ctx.plot("Length",len(bar.raw["custom"]))
'''
    shared = []
    source = pn.PyneIncrementalSession(script=script)
    source.seed([dict(bar(1), custom=shared)])
    before = source.snapshot_portable_state()
    preview = source.on_bar_updated(dict(bar(2), custom=shared))
    assert preview.lines[0]["data"][0]["value"] == 1
    assert shared == [] and source._ctx.saved == []
    assert source.snapshot_portable_state() == before


def test_input_script_function_rebinds_to_preview_namespace():
    script = '''values = []
def helper():
    values.append(1)
def on_bar(ctx,bar):
    if not bar.is_confirmed:
        bar.raw["handler"]()
    ctx.plot("Length",len(values))
'''
    source = pn.PyneIncrementalSession(script=script)
    source.seed([bar(1)])
    before = source.snapshot_portable_state()
    preview = source.on_bar_updated(dict(bar(2), handler=source._globals["helper"]))
    assert preview.lines[0]["data"][0]["value"] == 1
    assert source._globals["values"] == []
    assert source.snapshot_portable_state() == before


@pytest.mark.parametrize("operation", ["close", "preview"])
def test_uncopyable_bar_payload_rejects_before_poisoning_existing_session(operation):
    target, control = pn.PyneIncrementalSession(script=SCRIPT), pn.PyneIncrementalSession(script=SCRIPT)
    target.seed([bar(1)])
    control.seed([bar(1)])
    before = target.snapshot_portable_state()
    with pytest.raises(TypeError):
        (target.on_bar_closed if operation == "close" else target.on_bar_updated)(dict(bar(2), custom=threading.Lock()))
    assert target.snapshot_portable_state() == before
    assert target._poisoned_reason is None
    assert target.on_bar_closed(bar(2)) == control.on_bar_closed(bar(2))


def test_seed_validates_copyability_of_every_input_before_preparation():
    target = pn.PyneIncrementalSession(script=SCRIPT)
    fields = dict(vars(target))
    with pytest.raises(TypeError):
        target.seed([bar(1), dict(bar(2), custom=threading.Lock())])
    assert all(vars(target)[name] is value for name, value in fields.items())
    assert target.seed([bar(1)]).ok
    assert target.on_bar_closed(bar(2)).ok


@pytest.mark.parametrize("shared_input", [False, True])
def test_replay_records_original_payload_before_callback_mutation(shared_input):
    script = '''def on_bar(ctx,bar):
    bar.raw["custom"].append(1)
    ctx.plot("Length",len(bar.raw["custom"]))
'''
    first = []
    second = first if shared_input else []
    supplied = [dict(bar(1), custom=first), dict(bar(2), custom=second)]
    source = pn.PyneIncrementalSession(script=script)
    source.seed(supplied)
    assert first == second == []
    assert source._portable_bars[0]["custom"] == []
    assert source._portable_bars[1]["custom"] == ([1] if shared_input else [])
    replay = pn.PyneIncrementalSession.from_portable_snapshot(source.snapshot_portable(), script=script)
    assert replay.snapshot_result() == source.snapshot_result()
    assert replay.on_bar_closed(dict(bar(3), custom=[])) == source.on_bar_closed(dict(bar(3), custom=[]))


def test_historical_callbacks_cannot_change_authoritative_horizon_payloads():
    script = '''def on_bar(ctx,bar):
    bar.raw["custom"].append(1)
    ctx.plot("Length",len(bar.raw["custom"]))
'''
    bars = [dict(bar(1), custom=[]), dict(bar(2), custom=[])]
    history = HistoricalSession(script, bars)
    history.advance(1)
    snapshot = history.snapshot()
    assert snapshot["horizon"] == bars
    expected = history.advance(2)
    history.restore(snapshot)
    assert history.advance(2) == expected
    assert history.snapshot()["horizon"] == bars
