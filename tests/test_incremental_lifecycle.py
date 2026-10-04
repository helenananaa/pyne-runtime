from __future__ import annotations

import copy
import gc
import itertools
import threading
import weakref
from dataclasses import replace

import pyne_runtime as pn
import pytest

from pyne_runtime.cache import PyneCacheSnapshotEntry, PyneExecutionScope
from pyne_runtime.historical import HistoricalSession


SCRIPT = """
indicator("Lifecycle", mode="incremental")
values = []

def helper(value, bucket=values):
    bucket.append(value)
    helper.calls = getattr(helper, "calls", 0) + 1
    return sum(bucket)

def on_bar(ctx, bar):
    total = ctx.state("total", 0)
    total.value += bar.close
    ctx.plot("Total", total.value)
    ctx.plot("Helper", helper(bar.close))
"""

CACHE_SCRIPT = """
indicator("Preparation", mode="incremental")
loaded = pyne.cache("prepared", lambda: [])
loaded.append("prepared")

def on_bar(ctx, bar):
    loaded.append(bar.close)
    ctx.plot("Length", len(loaded))
"""


def _bar(time: int) -> dict[str, int]:
    return dict(time=time, open=time, high=time + 1, low=time - 1, close=time, volume=10)


def _session(script: str = SCRIPT, **kwargs) -> pn.PyneIncrementalSession:
    return pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(timeframe="1S"), **kwargs)


def _bad_snapshot(snapshot, defect: str):
    changes = {
        "times-none": {"retained_closed_times": None},
        "times-string": {"retained_closed_times": "12"},
        "times-duplicate": {"retained_closed_times": (2, 2)},
        "times-incomplete": {"retained_closed_times": (2,)},
        "last-mismatch": {"last_closed_time": 3},
        "count-bool": {"closed_count": True},
        "count-negative": {"closed_count": -1},
        "meta-none": {"meta": None},
        "globals-none": {"global_values": None},
        "globals-key": {"global_values": {1: []}},
        "functions-shape": {"function_states": {"helper": None}},
        "bindings-shape": {"function_bindings": {"helper": None}},
        "detached-shape": {"detached_functions": [None]},
        "namespace-shape": {"namespace_names": ["on_bar"]},
        "namespace-key": {"namespace_names": (None,)},
        "namespace-missing": {"namespace_names": (*snapshot.namespace_names, "missing")},
        "cache-none": {"cache": None},
        "cache-budget": {"cache": replace(snapshot.cache, max_items=0)},
        "cache-entries": {"cache": replace(snapshot.cache, entries=(None,))},
        "cache-ttl": {"cache": replace(snapshot.cache, entries=(PyneCacheSnapshotEntry("x", [], "bad", 0),))},
        "bars-none": {"portable_bars": None},
        "seed-count": {"portable_seed_count": 3},
        "complete-bool": {"portable_complete": 1},
        "incomplete-recording": {"portable_complete": False},
        "trace-shape": {"trace": {}},
        "context-shape": {"context": {}},
    }
    if defect.startswith("function-"):
        state = snapshot.function_states["helper"]
        states = dict(snapshot.function_states)
        states["helper"] = replace(state, **{
            "function-defaults": {"defaults": []},
            "function-kwdefaults": {"kwdefaults": []},
            "function-attributes": {"attributes": []},
        }[defect])
        return replace(snapshot, function_states=states)
    if defect == "graph-copy":
        return replace(snapshot, global_values={**snapshot.global_values, "bad": threading.Lock()})
    if defect == "context-counter":
        context = copy.deepcopy(snapshot.context)
        context._limit_tracker.output_points = -1
        return replace(snapshot, context=context)
    return replace(snapshot, **changes[defect])


@pytest.mark.parametrize("defect", [
    "times-none", "times-string", "times-duplicate", "times-incomplete", "last-mismatch",
    "count-bool", "count-negative", "meta-none", "globals-none", "globals-key",
    "functions-shape", "bindings-shape", "detached-shape", "namespace-shape", "namespace-key",
    "namespace-missing", "cache-none", "cache-budget", "cache-entries", "cache-ttl", "bars-none",
    "seed-count", "complete-bool", "incomplete-recording", "trace-shape", "context-shape",
    "context-counter", "function-defaults", "function-kwdefaults", "function-attributes", "graph-copy",
])
def test_rejected_restore_keeps_committed_bytes_preview_and_continuation(defect: str) -> None:
    source = _session()
    source.seed([_bar(1), _bar(2)])
    snapshot = _bad_snapshot(source.snapshot_state(), defect)
    target, control = _session(), _session()
    for session in (target, control):
        session.seed([_bar(5), _bar(6)])
        session.on_bar_updated(_bar(7))
    before = target.snapshot_portable_state()
    callback, context = target._on_bar, target._ctx

    with pytest.raises((ValueError, TypeError, AttributeError)):
        target.restore_state(snapshot)

    assert target.snapshot_portable_state() == before
    assert target._on_bar is callback and target._ctx is context
    assert target._active_preview_time == 7
    assert target.on_bar_updated(_bar(7)) == control.on_bar_updated(_bar(7))
    assert target.on_bar_closed(_bar(7)) == control.on_bar_closed(_bar(7))
    assert target.snapshot_portable_state() == control.snapshot_portable_state()


@pytest.mark.parametrize("defect", ["graph-copy", "function-defaults", "function-kwdefaults", "function-attributes", "namespace-missing"])
def test_failed_fresh_restore_rolls_back_preparation_and_owned_cache(defect: str) -> None:
    source = _session(CACHE_SCRIPT)
    source.seed([_bar(1), _bar(2)])
    snapshot = source.snapshot_state()
    if defect.startswith("function-"):
        state = snapshot.function_states["on_bar"]
        states = dict(snapshot.function_states)
        states["on_bar"] = replace(state, **{
            "function-defaults": {"defaults": []},
            "function-kwdefaults": {"kwdefaults": []},
            "function-attributes": {"attributes": []},
        }[defect])
        snapshot = replace(snapshot, function_states=states)
    else:
        snapshot = _bad_snapshot(snapshot, defect)
    scope = PyneExecutionScope.fresh()
    original = scope.cache.get_or_load("prepared", lambda: ["existing"])
    target = _session(CACHE_SCRIPT, execution_scope=scope)
    original_fields = dict(vars(target))

    with pytest.raises((ValueError, TypeError, AttributeError)):
        target.restore_state(snapshot)

    assert vars(target) == original_fields
    assert all(vars(target)[name] is value for name, value in original_fields.items())
    assert scope.cache.get_or_load("prepared", lambda: []) is original
    assert original == ["existing"]
    assert target.seed([_bar(5)]).output == _session(CACHE_SCRIPT, execution_scope=_scope_with_existing()).seed([_bar(5)]).output


def _scope_with_existing() -> PyneExecutionScope:
    scope = PyneExecutionScope.fresh()
    scope.cache.get_or_load("prepared", lambda: ["existing"])
    return scope


def test_fresh_restore_keeps_cache_aliases_and_preview_continuation() -> None:
    source = _session(CACHE_SCRIPT)
    source.seed([_bar(1), _bar(2)])
    target = _session(CACHE_SCRIPT)
    scope = target.execution_scope
    target.restore_state(source.snapshot_state())
    assert target.execution_scope is scope
    assert target._cache_namespace._cache is scope.cache
    assert target._globals["loaded"] is scope.cache.get_or_load("prepared", lambda: [])
    assert target.on_bar_updated(_bar(3)) == source.on_bar_updated(_bar(3))
    assert target.on_bar_closed(_bar(3)) == source.on_bar_closed(_bar(3))


def test_failure_during_restore_preparation_preserves_unprepared_target() -> None:
    script = """
indicator("Preparation failure", mode="incremental")
loaded = pyne.cache("prepared", lambda: [])
if loaded:
    loaded.append("temporary")
    raise RuntimeError("preparation failed")
def on_bar(ctx, bar):
    ctx.plot("Close", bar.close)
"""
    source = _session(script)
    source.seed([_bar(1)])
    scope = _scope_with_existing()
    target = _session(script, execution_scope=scope)
    fields = dict(vars(target))
    original = scope.cache.get_or_load("prepared", lambda: [])
    with pytest.raises(RuntimeError, match="preparation failed"):
        target.restore_state(source.snapshot_state())
    assert all(vars(target)[name] is value for name, value in fields.items())
    assert original == ["existing"]
    scope.cache.clear()
    assert target.seed([_bar(2)]).output == _session(script).seed([_bar(2)]).output


@pytest.mark.parametrize("initialization", ["empty-seed", "seed", "close", "preview", "result"])
def test_seed_rejects_reinitialization_without_state_or_replay_changes(initialization: str) -> None:
    target, control = _session(), _session()
    for session in (target, control):
        if initialization == "empty-seed":
            session.seed([])
        elif initialization == "seed":
            session.seed([_bar(1)])
        elif initialization == "close":
            session.on_bar_closed(_bar(1))
        elif initialization == "preview":
            session.on_bar_updated(_bar(1))
        else:
            session.snapshot_result()
    before = target.snapshot_portable_state(), target.snapshot_portable()
    with pytest.raises(ValueError, match="already initialized"):
        target.seed([_bar(1)])
    assert (target.snapshot_portable_state(), target.snapshot_portable()) == before
    assert target.on_bar_closed(_bar(2)) == control.on_bar_closed(_bar(2))
    replay = pn.PyneIncrementalSession.from_portable_snapshot(target.snapshot_portable(), script=SCRIPT)
    assert replay.on_bar_closed(_bar(3)) == target.on_bar_closed(_bar(3))


def test_first_seed_after_prepare_or_snapshot_and_historical_empty_seed_remains_valid() -> None:
    target = _session()
    target.snapshot_state()
    assert target.seed([_bar(1)]).output == _session().seed([_bar(1)]).output
    history = HistoricalSession(SCRIPT, [_bar(1), _bar(2)])
    assert history.advance(2).output == _session().seed([_bar(1), _bar(2)]).output


@pytest.mark.parametrize("old_identity,new_identity,old_first", itertools.product((False, True), repeat=3))
def test_release_after_force_close_preserves_active_replacement_and_settles_balanced_returns(
    old_identity: bool, new_identity: bool, old_first: bool,
) -> None:
    manager = pn.PyneIncrementalSessionManager()
    old = manager.acquire("same", _session)
    assert manager.close("same", force=True)
    new = manager.acquire("same", _session)
    releases = [(old, old_identity), (new, new_identity)]
    if not old_first:
        releases.reverse()
    lease, identity = releases[0]
    manager.release("same", **({"shared": lease} if identity else {}))
    if old_first:
        assert manager.acquire("same", _session) is new
        manager.release("same", shared=new)
        assert manager.snapshot()["keys"]["same"]["refCount"] == 1
    lease, identity = releases[1]
    manager.release("same", **({"shared": lease} if identity else {}))
    assert manager.snapshot()["sessions"] == 0
    assert manager._ambiguous_leases == {} and manager._legacy_releases == {}


def test_legacy_returns_after_repeated_replacement_do_not_delete_active_new_session() -> None:
    manager = pn.PyneIncrementalSessionManager(max_sessions=1)
    oldest = manager.acquire("same", _session)
    manager.close("same", force=True)
    middle = manager.acquire("same", _session)
    manager.close("same", force=True)
    current = manager.acquire("same", _session)
    old_ref = weakref.ref(oldest.session)
    del oldest
    gc.collect()
    assert old_ref() is None
    manager.release("same")
    manager.release("same", shared=middle)
    assert manager.snapshot()["keys"]["same"]["refCount"] == 1
    assert manager.acquire("same", _session) is current
    manager.release("same", shared=current)
    manager.release("same", shared=current)
    assert manager.snapshot()["sessions"] == 0
    assert manager._ambiguous_leases == {} and manager._legacy_releases == {}


def test_identified_release_rejects_wrong_key_and_ignores_unrelated_incarnation() -> None:
    manager = pn.PyneIncrementalSessionManager()
    lease = manager.acquire("same", _session)
    other = pn.PyneIncrementalSessionManager().acquire("same", _session)
    with pytest.raises(ValueError, match="key does not match"):
        manager.release("different", shared=lease)
    manager.release("same", shared=other)
    assert manager.snapshot()["keys"]["same"]["refCount"] == 1
    manager.release("same", shared=lease)
    assert manager.snapshot()["sessions"] == 0


@pytest.mark.parametrize("identities", itertools.product((False, True), repeat=3))
def test_multi_acquisition_releases_keep_a_bound_on_true_references(identities: tuple[bool, ...]) -> None:
    for order in itertools.permutations(range(6)):
        manager = pn.PyneIncrementalSessionManager()
        leases = []
        for generation in range(3):
            lease = manager.acquire("same", object)
            assert manager.acquire("same", object) is lease
            leases.append(lease)
            if generation < 2:
                manager.close("same", force=True)
        actual = [2, 2, 2]
        for acquisition in order:
            generation = acquisition // 2
            actual[generation] -= 1
            manager.release("same", **({"shared": leases[generation]} if identities[generation] else {}))
            if actual[2]:
                assert manager._sessions["same"] is leases[2]
                assert leases[2].ref_count >= actual[2]
        assert manager.snapshot()["sessions"] == 0
        assert manager._ambiguous_leases == {} and manager._legacy_releases == {}
