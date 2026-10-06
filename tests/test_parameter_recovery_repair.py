"""Parameter ownership and recovery must agree for supported Python values."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

import pyne_runtime as pn
from pyne_runtime.security import PyneSecurityError


def _bar(time: int) -> dict[str, int]:
    return dict(time=time, open=1, high=1, low=1, close=1, volume=1)


class _Box:
    def __init__(self, values=(1, 2)) -> None:
        self.values = list(values)


class _SlotsBox:
    __slots__ = ("values",)

    def __init__(self, values=(1, 2)) -> None:
        self.values = list(values)


class _ShallowSlotsBox(_SlotsBox):
    __slots__ = ()

    def __deepcopy__(self, memo):
        clone = object.__new__(type(self))
        clone.values = self.values
        return clone


class _Array(np.ndarray):
    pass


class _ExplosiveEquality(_Box):
    def __eq__(self, other):
        raise AssertionError("user equality must not run during restore")


class _LyingEquality(_Box):
    def __eq__(self, other):
        return True


class _VectorEquality(_Box):
    def __eq__(self, other):
        return np.array([True, False])


class _ShallowArray(_Array):
    def __deepcopy__(self, memo):
        return np.ndarray.view(self, type(self))


class _OwnedArray(_Array):
    def __deepcopy__(self, memo):
        clone = np.ndarray.copy(self, order="K").view(type(self))
        memo[id(self)] = clone
        clone.__dict__.update(copy.deepcopy(self.__dict__, memo))
        return clone


class _Date(datetime):
    pass


class _TaggedFloat(float):
    def __eq__(self, other):
        raise AssertionError("scalar subclass equality must not run")


class _NumpyFloat(np.float64):
    def __deepcopy__(self, memo):
        clone = type(self)(np.float64.__float__(self))
        memo[id(self)] = clone
        clone.__dict__.update(copy.deepcopy(self.__dict__, memo))
        return clone

    def __eq__(self, other):
        raise AssertionError("NumPy scalar subclass equality must not run")


@pytest.mark.parametrize("base,value", [(int, 7), (float, 7.0), (str, "x"),
                                      (bytes, b"x"), (complex, 7j)])
def test_scalar_subclass_parameter_attributes_are_copied_on_read(base, value):
    tagged = type("Tagged", (base,), {})
    supplied = tagged(value)
    supplied.items = []
    script = '''
def on_bar(ctx, bar):
    item = ctx.params["x"]
    item.items.append(bar.time)
    ctx.plot("n", len(item.items))
'''
    session = pn.PyneIncrementalSession(script=script, params={"x": supplied})
    session.on_bar_closed(_bar(1))
    for _ in range(2):
        preview = session.on_bar_updated(_bar(2))
        assert preview.lines[0]["data"][0]["value"] == 1
    closed = session.on_bar_closed(_bar(2))
    assert closed.lines[0]["data"][0]["value"] == 1
    assert supplied.items == []
    assert session.params["x"].items == []


def test_custom_shallow_copy_cannot_hide_shared_slot_payload():
    with pytest.raises(PyneSecurityError, match="shared mutable state"):
        pn.PyneIncrementalSession(script="def on_bar(ctx, bar): pass",
                                  params={"box": _ShallowSlotsBox()})


def test_custom_array_shallow_copy_cannot_hide_shared_numeric_storage():
    with pytest.raises(PyneSecurityError, match="shared mutable state"):
        pn.PyneIncrementalSession(script="def on_bar(ctx, bar): pass",
                                  params={"a": np.array([1, 2]).view(_ShallowArray)})


@pytest.mark.parametrize("factory", [_Box, _SlotsBox, _ExplosiveEquality, _VectorEquality,
                                     lambda: np.array([1, 2]).view(_Array),
                                     lambda: SimpleNamespace(values=[1, 2]),
                                     lambda: np.array([_ExplosiveEquality()], dtype=object).view(_Array)])
@pytest.mark.parametrize("fresh", [False, True])
def test_custom_parameter_recovers_without_calling_user_equality(factory, fresh):
    script = "def on_bar(ctx, bar): ctx.plot('n', bar.close)"
    original = pn.PyneIncrementalSession(script=script, params={"box": factory()})
    original.on_bar_closed(_bar(1))
    snapshot = original.snapshot_state()
    if fresh:
        restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    else:
        original.restore_state(snapshot)
        restored = original
    assert restored.snapshot_result().lines[0]["data"] == [{"time": 1, "value": 1.0}]
    assert restored.on_bar_closed(_bar(2)).lines[0]["data"][0]["value"] == 1


@pytest.mark.parametrize("factory", [_Box, _SlotsBox, _ExplosiveEquality,
                                     _LyingEquality, _VectorEquality])
def test_different_custom_parameter_state_is_rejected_atomically(factory):
    script = "def on_bar(ctx, bar): ctx.plot('n', bar.close)"
    source = pn.PyneIncrementalSession(script=script, params={"box": factory()})
    source.on_bar_closed(_bar(1))
    destination = pn.PyneIncrementalSession(script=script, params={"box": factory((1, 9))})
    destination.on_bar_closed(_bar(4))
    with pytest.raises(ValueError, match="params do not match"):
        destination.restore_state(source.snapshot_state())
    assert destination.last_closed_time == 4
    assert destination.on_bar_closed(_bar(5)).ok


def test_different_ndarray_parameter_storage_is_rejected():
    script = "def on_bar(ctx, bar): pass"
    source = pn.PyneIncrementalSession(script=script,
                                     params={"a": np.array([1, 2]).view(_Array)})
    target = pn.PyneIncrementalSession(script=script,
                                     params={"a": np.array([1, 3]).view(_Array)})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(source.snapshot_state())


def test_opaque_native_parameter_state_is_not_equated_as_empty_attributes():
    script = "def on_bar(ctx, bar): pass"
    source = pn.PyneIncrementalSession(script=script, params={"date": _Date(2024, 1, 1)})
    target = pn.PyneIncrementalSession(script=script, params={"date": _Date(2025, 1, 1)})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(source.snapshot_state())


@pytest.mark.parametrize("a,b", [(1, 2), (False, 0), (0.0, -0.0),
                                 ("x", "y"), ([1, 2], [2, 1]),
                                 ({"a": 1}, {"b": 1})])
def test_distinct_builtin_parameter_state_is_rejected(a, b):
    script = "def on_bar(ctx, bar): pass"
    source = pn.PyneIncrementalSession(script=script, params={"value": a})
    target = pn.PyneIncrementalSession(script=script, params={"value": b})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(source.snapshot_state())


def test_custom_parameter_cycles_recover_and_alias_changes_are_rejected():
    script = "def on_bar(ctx, bar): pass"
    box = _Box()
    box.self = box
    box.alias = box.values
    session = pn.PyneIncrementalSession(script=script, params={"box": box})
    session.seed([])
    snapshot = session.snapshot_state()
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    copied = restored.params["box"]
    assert copied.self is copied
    assert copied.alias is copied.values
    incoming = dict(snapshot.params)
    incoming["box"] = _Box()
    incoming["box"].self = incoming["box"]
    incoming["box"].alias = list(incoming["box"].values)
    with pytest.raises(ValueError, match="params do not match"):
        session.restore_state(replace(snapshot, params=incoming))


@pytest.mark.parametrize("value", [0.0, -0.0, float("nan"), float("inf")])
def test_scalar_subclass_payload_and_attributes_recover_without_user_equality(value):
    supplied = _TaggedFloat(value)
    supplied.items = [1, 2]
    script = "def on_bar(ctx, bar): pass"
    session = pn.PyneIncrementalSession(script=script, params={"x": supplied})
    session.seed([])
    restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script)
    assert restored.params["x"].items == [1, 2]
    changed = _TaggedFloat(value)
    changed.items = [1, 3]
    target = pn.PyneIncrementalSession(script=script, params={"x": changed})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(session.snapshot_state())


def test_structured_object_array_parameter_preserves_fields_and_owned_objects():
    array = np.empty((2,), dtype=[("value", "i4"), ("object", object)]).view(_Array)
    array["value"] = [1, 2]
    array["object"] = [_ExplosiveEquality(), _ExplosiveEquality((3, 4))]
    script = "def on_bar(ctx, bar): pass"
    session = pn.PyneIncrementalSession(script=script, params={"array": array})
    snapshot = session.snapshot_state()
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    returned = restored.params["array"]
    returned["object"][0].values.append(9)
    assert restored.params["array"]["object"][0].values == [1, 2]
    returned["value"][0] = 9
    target = pn.PyneIncrementalSession(script=script, params={"array": returned})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(snapshot)


def test_numpy_scalar_subclass_owned_attributes_recover_and_differences_reject():
    value = _NumpyFloat(7)
    value.items = [1, 2]
    script = "def on_bar(ctx, bar): pass"
    session = pn.PyneIncrementalSession(script=script, params={"value": value})
    copied = session.params["value"]
    copied.items.append(3)
    assert value.items == [1, 2]
    assert session.params["value"].items == [1, 2]
    snapshot = session.snapshot_state()
    session.restore_state(snapshot)
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    assert restored.params["value"].items == [1, 2]
    for number, items in [(8, [1, 2]), (7, [1, 9])]:
        changed = _NumpyFloat(number)
        changed.items = items
        target = pn.PyneIncrementalSession(script=script, params={"value": changed})
        with pytest.raises(ValueError, match="params do not match"):
            target.restore_state(snapshot)


@pytest.mark.parametrize("array", [np.arange(12).reshape(3, 4)[:, ::2],
                                   np.arange(5)[::-1],
                                   np.asfortranarray(np.arange(12).reshape(3, 4))])
@pytest.mark.parametrize("fresh", [False, True])
def test_noncontiguous_ndarray_parameter_restores_its_canonical_copy(array, fresh):
    script = "def on_bar(ctx, bar): pass"
    supplied = array.view(_Array)
    session = pn.PyneIncrementalSession(script=script, params={"array": supplied})
    snapshot = session.snapshot_state()
    if fresh:
        restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    else:
        session.restore_state(snapshot)
        restored = session
    np.testing.assert_array_equal(restored.params["array"], array)


def test_ndarray_subclass_owned_attributes_are_compared_beside_numeric_storage():
    supplied = np.arange(12).reshape(3, 4)[:, ::2].view(_OwnedArray)
    supplied.items = [1, 2]
    script = "def on_bar(ctx, bar): pass"
    session = pn.PyneIncrementalSession(script=script, params={"array": supplied})
    snapshot = session.snapshot_state()
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=script)
    assert restored.params["array"].items == [1, 2]
    changed = restored.params["array"]
    changed.items.append(3)
    assert supplied.items == [1, 2]
    assert restored.params["array"].items == [1, 2]
    target = pn.PyneIncrementalSession(script=script, params={"array": changed})
    with pytest.raises(ValueError, match="params do not match"):
        target.restore_state(snapshot)


def test_unordered_parameter_members_preserve_alias_relationships():
    script = "def on_bar(ctx, bar): pass"
    box = _Box()
    first, second = _Box(), _Box()
    box.members = {first, second}
    box.selected = second
    session = pn.PyneIncrementalSession(script=script, params={"box": box})
    restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script)
    copied = restored.params["box"]
    assert any(item is copied.selected for item in copied.members)


@pytest.mark.parametrize("first", ["snapshot", "seed", "closed", "preview"])
def test_all_context_initialization_entrypoints_bind_selected_trace(first):
    script = '''
def init(ctx):
    ctx.trace.emit("init")
def on_bar(ctx, bar):
    ctx.trace.emit("decision", time=bar.time)
    trace.emit("global.decision", time=bar.time)
    ctx.plot("n", bar.close)
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(trace_enabled=True, trace_timings_enabled=False))
    if first == "snapshot":
        session.snapshot_result()
    elif first == "seed":
        session.seed([])
    elif first == "preview":
        session.on_bar_updated(_bar(1))
    result = session.on_bar_closed(_bar(1))
    assert session._ctx.trace is session.trace
    events = [entry["event"] for entry in result.meta["trace"]["events"]]
    assert events.count("init") == 1
    assert "decision" in events
    assert "global.decision" in events
