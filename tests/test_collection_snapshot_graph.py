"""Collection snapshots retain sharing without recursive graph expansion."""
import copy
import importlib

import pyne_runtime as pn
import pytest

from pyne_runtime.collections import PyneArray, PyneMap, PyneMatrix
from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError


def shared_root(kind, child):
    if kind == "array":
        return PyneArray([child, child])
    if kind == "map":
        return PyneMap({"first": child, "second": child})
    return PyneMatrix.from_rows([[child, child]])


def children(value):
    if isinstance(value, PyneArray):
        return value.get(0), value.get(1)
    if isinstance(value, PyneMap):
        return value.get("first"), value.get("second")
    return value.get(0, 0), value.get(0, 1)


@pytest.mark.parametrize("kind", ["array", "map", "matrix"])
@pytest.mark.parametrize("depth", [12, 24, 48])
def test_snapshot_visits_each_shared_node_once_and_detaches_live_values(kind, depth, monkeypatch):
    leaf = value = PyneArray([1])
    for _ in range(depth):
        value = shared_root(kind, value)
    reads = 0
    for cls, method in ((PyneArray, "to_list"), (PyneMap, "to_dict"), (PyneMatrix, "to_list")):
        original = getattr(cls, method)

        def counted(self, original=original):
            nonlocal reads
            reads += 1
            return original(self)

        monkeypatch.setattr(cls, method, counted)
    snapshot = value.snapshot()
    assert reads == depth + 1
    current = snapshot
    for _ in range(depth):
        first, second = children(current)
        assert first is second
        current = first
    assert current is not leaf
    leaf.set(0, 99)
    assert current.get(0) == 1
    second_snapshot = value.snapshot()
    for _ in range(depth):
        second_snapshot = children(second_snapshot)[0]
    assert second_snapshot.get(0) == 99
    assert second_snapshot is not current


def test_unlimited_deep_snapshot_uses_no_python_recursive_calls():
    value = PyneArray([1])
    for _ in range(1200):
        value = PyneArray([value])
    snapshot = value.snapshot()
    for _ in range(1200):
        assert snapshot is not value
        snapshot, value = snapshot.get(0), value.get(0)
    assert snapshot.get(0) == 1


@pytest.mark.parametrize("kind", ["array", "map", "matrix"])
def test_deepcopy_preallocates_shared_graph_once_and_reuses_external_memo(kind, monkeypatch):
    leaf = value = PyneArray([1])
    for _ in range(48):
        value = shared_root(kind, value)
    module = importlib.import_module("pyne_runtime._collection_copy")
    original = module._attributes
    allocations = 0

    def counted(node):
        nonlocal allocations
        allocations += 1
        return original(node)

    monkeypatch.setattr(module, "_attributes", counted)
    memo = {}
    cloned = copy.deepcopy(value, memo)
    assert allocations == 49
    current = cloned
    for _ in range(48):
        first, second = children(current)
        assert first is second
        current = first
    assert copy.deepcopy(leaf, memo) is current
    current.set(0, 99)
    assert leaf.get(0) == 1


def test_deepcopy_handles_deep_nodes_slice_parent_links_slots_and_callback_memo():
    class SlottedArray(PyneArray):
        __slots__ = ("details",)

    parent = SlottedArray([1, 2])
    parent.details = {"values": [3]}
    view = parent
    for _ in range(1200):
        view = view.slice(0, 2)
    def callback():
        return 1

    def rebound():
        return 2
    parent.callback = callback
    outer = PyneArray([parent, view, view])
    parent.extra = {"owner": parent, "view": view}
    cloned = copy.deepcopy(outer, {id(callback): rebound})
    root, copied_view = cloned.get(0), cloned.get(1)
    assert type(root) is SlottedArray
    assert root.callback is rebound
    assert root.extra["owner"] is root and root.extra["view"] is copied_view
    assert copied_view is cloned.get(2)
    root.details["values"].append(4)
    copied_view.set(0, 99)
    assert root.to_list() == [99, 2] and parent.to_list() == [1, 2]
    assert parent.details == {"values": [3]}


def test_deepcopy_pure_owned_chain_exceeds_python_recursion_depth():
    value = PyneArray([1])
    for _ in range(1200):
        value = PyneArray([value])
    cloned = copy.deepcopy(value)
    for _ in range(1200):
        cloned = cloned.get(0)
    assert cloned.get(0) == 1


def test_deep_owned_state_preview_and_local_snapshot_restore_remain_isolated():
    script = '''indicator("Deep state", mode="incremental")
def init(ctx):
    value = array.from_values(0)
    for _ in range(600):
        value = array.from_values(value)
    ctx.state("deep", value)
def on_bar(ctx, bar):
    value = ctx.state("deep").value
    for _ in range(600):
        value = array.get(value, 0)
    array.set(value, 0, bar.close)
    ctx.plot("Value", array.get(value, 0))
'''
    bar = dict(time=0, open=1, high=1, low=1, close=1, volume=1)
    session = pn.PyneIncrementalSession(script=script)
    session.seed([bar])
    preview = dict(bar, time=10, open=99, high=99, low=99, close=99)
    assert session.on_bar_updated(preview).ok
    assert session.snapshot_result().lines[0]["data"][-1]["value"] == 1
    restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script)
    confirmed = dict(bar, time=10, open=2, high=2, low=2, close=2)
    for target in (session, restored):
        target.on_bar_updated(confirmed)
        target.on_bar_closed(confirmed)
    assert session.snapshot_result() == restored.snapshot_result()


@pytest.mark.parametrize("kind", ["array", "map", "matrix"])
def test_snapshot_rejects_host_corrupted_cycles(kind):
    value = shared_root(kind, 1)
    if kind == "array":
        value._values[0] = value
    elif kind == "map":
        value._values["first"] = value
    else:
        value._values[0][0] = value
    with pytest.raises(PyneStateContractError, match="recursive collection snapshots"):
        value.snapshot()


def test_snapshot_keeps_selected_depth_and_stable_value_checks_after_child_mutation():
    leaf = PyneArray([1])
    value = PyneArray([leaf], max_depth=2)
    leaf.push(PyneArray([2]))
    with pytest.raises(PyneResourceLimitError, match="nesting depth 3 exceeds limit 2"):
        value.snapshot()
    leaf.pop()
    leaf._values.append(lambda: 1)
    with pytest.raises(ValueError, match="callable and module"):
        value.snapshot()


@pytest.mark.parametrize("rows,columns", [(0, 4), (4, 0)])
def test_snapshot_preserves_empty_matrix_shape(rows, columns):
    value = PyneMatrix(rows, columns, max_cells=1)
    snapshot = value.snapshot()
    assert (snapshot.rows(), snapshot.columns()) == (rows, columns)


def test_slice_snapshot_detaches_its_structure_and_retains_shared_children():
    leaf = PyneArray([1])
    parent = PyneArray([leaf, leaf, 99])
    snapshot = parent.slice(0, 2).snapshot()
    assert snapshot.get(0) is snapshot.get(1)
    assert snapshot.get(0) is not leaf
    parent.set(0, 10)
    leaf.set(0, 5)
    assert snapshot.size() == 2 and snapshot.get(0).get(0) == 1


def test_deep_slice_access_and_mutation_preserve_owner_budgets_and_windows():
    parent = PyneArray([1, 2], max_size=4)
    views = [parent]
    for _ in range(1200):
        views.append(views[-1].slice(0, 2))
    view = views[-1]
    assert view.to_list() == [1, 2]
    view.set(0, 5)
    view.push(3)
    assert parent.to_list() == view.to_list() == [5, 2, 3]
    parent.push(4)
    assert view.to_list() == [5, 2, 3]
    stops = [item._values.stop for item in views[1:]]
    with pytest.raises(PyneResourceLimitError, match="array size 5 exceeds limit 4"):
        view.push(9)
    assert parent.to_list() == [5, 2, 3, 4]
    assert [item._values.stop for item in views[1:]] == stops
    with pytest.raises(PyneStateContractError, match="recursive collection"):
        view.set(0, parent)
    assert parent.pop() == 4
    assert view.remove(1) == 2
    view.unshift(9)
    view.reverse()
    assert parent.to_list() == view.to_list() == [3, 5, 9]
    view.clear()
    assert parent.to_list() == []
    assert all(item.size() == 0 for item in views)


def test_nested_slice_offsets_resize_every_affected_window_and_keep_sort_atomic():
    parent = PyneArray(list(range(20)))
    first = parent.slice(2, 18)
    second = first.slice(3, 12)
    third = second.slice(1, 6)
    third.set(0, 99)
    assert parent.get(6) == 99
    third.insert(1, "bad ordering")
    before = parent.to_list(), [value.to_list() for value in (first, second, third)]
    with pytest.raises(TypeError):
        third.sort()
    assert (parent.to_list(), [value.to_list() for value in (first, second, third)]) == before
    assert third.remove(1) == "bad ordering"
    third.clear()
    assert parent.to_list() == [*range(6), *range(11, 20)]
    assert (first.size(), second.size(), third.size()) == (11, 4, 0)


SCRIPT = '''indicator("Shared snapshots", mode="incremental")
def init(ctx):
    leaf = array.from_values(0)
    ctx.state("graph", array.from_values(leaf, leaf))
def on_bar(ctx, bar):
    graph = ctx.state("graph").value
    snapshot = array.snapshot(graph)
    ctx.plot("SnapshotShared", array.get(snapshot, 0) is array.get(snapshot, 1))
    if ctx.bar_index > 0:
        previous = ctx.state("graph")[1]
        ctx.plot("HistoryShared", array.get(previous, 0) is array.get(previous, 1))
    array.set(array.get(graph, 0), 0, bar.close)
'''


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_shared_snapshot_history_preview_and_same_version_continuation(mode):
    bars = [dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)
            for index, value in enumerate([1, 2, 3, 4])]
    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed(bars[:2])
    before = session.snapshot_portable_state()
    session.on_bar_updated(dict(bars[2], open=99, high=99, low=99, close=99))
    assert session.snapshot_portable_state() == before
    restored = (pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT)
                if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
                    session.snapshot_portable(mode=mode), script=SCRIPT))
    for bar in bars[2:]:
        session.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == session.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result == session.snapshot_result()
    for line in result.lines:
        assert all(point["value"] == 1 for point in line["data"])
