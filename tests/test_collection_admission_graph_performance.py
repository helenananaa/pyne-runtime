"""Explicit collection admission and shared graph validation have bounded work."""

import pyne_runtime as pn
import pytest

import pyne_runtime.collections as collections
from pyne_runtime.collections import PyneArray, PyneMap, PyneMatrix
from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError


@pytest.mark.parametrize("rows,columns", [(1, 100_000), (100_000, 2)])
def test_matrix_explicit_cell_budget_stops_generator_at_first_excess_cell(rows, columns):
    consumed = dict(rows=0, cells=0)

    def row_values():
        for _ in range(columns):
            consumed["cells"] += 1
            if consumed["cells"] > 5:
                pytest.fail("Matrix admission consumed input beyond its rejection boundary")
            yield 1

    def row_source():
        for _ in range(rows):
            consumed["rows"] += 1
            yield row_values()

    with pytest.raises(PyneResourceLimitError, match="matrix cells 5 exceeds limit 4"):
        PyneMatrix.from_rows(row_source(), max_cells=4)
    assert consumed == dict(rows=1 if rows == 1 else 3, cells=5)


def test_matrix_unlimited_admission_and_empty_shapes_preserve_existing_contract():
    values = ((value for value in range(12)) for _ in range(3))
    matrix = PyneMatrix.from_rows(values, max_cells=None)
    assert matrix.rows() == 3 and matrix.columns() == 12
    assert matrix.to_list() == [list(range(12))] * 3
    empty = PyneMatrix.from_rows(([] for _ in range(100)), max_cells=1)
    assert empty.rows() == 100 and empty.columns() == 0
    assert empty.elements_count() == 0
    with pytest.raises(ValueError, match="same length"):
        PyneMatrix.from_rows(iter([[1, 2], [3]]), max_cells=10)


def test_matrix_bounded_generator_preserves_shared_values_and_depth_checks():
    leaf = PyneArray([1])
    matrix = PyneMatrix.from_rows(((leaf for _ in range(2)),), max_cells=2, max_depth=2)
    assert matrix.get(0, 0) is matrix.get(0, 1) is leaf
    leaf.set(0, 2)
    assert matrix.row(0).get(0).get(0) == 2
    with pytest.raises(PyneResourceLimitError, match="nesting depth 2 exceeds limit 1"):
        PyneMatrix.from_rows(((leaf,),), max_cells=1, max_depth=1)


def _diamond(depth):
    leaf = node = PyneArray([1])
    for _ in range(depth):
        node = PyneArray([node, node])
    return node, leaf


@pytest.mark.parametrize("depth", [12, 24, 48])
@pytest.mark.parametrize("kind", ["array", "map", "matrix"])
def test_shared_acyclic_graph_writes_visit_edges_linearly(monkeypatch, depth, kind):
    graph, _ = _diamond(depth)
    edges = 0
    original = collections._collection_children

    def counted(value, **kwargs):
        nonlocal edges
        for child in original(value, **kwargs):
            edges += 1
            yield child

    monkeypatch.setattr(collections, "_collection_children", counted)
    if kind == "array":
        target = PyneArray(max_depth=depth + 2)
        target.push(graph)
        actual = target.get(0)
    elif kind == "map":
        target = PyneMap(max_depth=depth + 2)
        target.put("graph", graph)
        actual = target.get("graph")
    else:
        target = PyneMatrix(1, 1, max_depth=depth + 2)
        target.set(0, 0, graph)
        actual = target.get(0, 0)
    # Reachability, cycle rejection and depth each traverse the graph once.
    assert 0 < edges <= 3 * (2 * depth + 1)
    assert actual is graph
    assert graph.get(0) is graph.get(1)


@pytest.mark.parametrize("reverse", [False, True])
def test_shared_short_and_long_paths_keep_the_longest_nesting_depth(reverse):
    leaf = PyneArray([1])
    longer = PyneMap({"leaf": leaf})
    branches = [leaf, longer]
    graph = PyneArray(list(reversed(branches)) if reverse else branches)
    assert collections._collection_depth(graph) == 3
    target = PyneArray([99], max_depth=3)
    with pytest.raises(PyneResourceLimitError, match="nesting depth 4 exceeds limit 3"):
        target.push(graph)
    assert target.to_list() == [99]


def test_graph_validation_is_fresh_after_mutation_and_preserves_sharing():
    graph, leaf = _diamond(6)
    target = PyneArray(max_depth=8)
    target.push(graph)
    copy = target.copy()
    assert copy.get(0) is target.get(0) is graph
    target.pop()
    leaf.push(PyneArray([2]))
    with pytest.raises(PyneResourceLimitError, match="nesting depth 9 exceeds limit 8"):
        target.push(graph)
    assert target.to_list() == []


def test_a_cycle_inside_a_shared_branch_rejects_without_mutation():
    leaf = PyneArray([1])
    shared = PyneArray([leaf, leaf])
    # A malformed host value may contain a cycle before reaching this API.
    leaf._values.append(shared)
    target = PyneArray([99])
    with pytest.raises(PyneStateContractError, match="recursive collection"):
        target.push(shared)
    assert target.to_list() == [99]


def test_slice_hidden_parent_references_still_reject_a_cycle_without_mutation():
    parent = PyneArray([1, 2, 3])
    view = parent.slice(1, 2)
    with pytest.raises(PyneStateContractError, match="recursive collection"):
        parent.push(view)
    assert parent.to_list() == [1, 2, 3]


DAG_SCRIPT = '''indicator("Shared graph", mode="incremental")
def init(ctx):
    leaf = array.from_values(0)
    branch = leaf
    for _ in range(2):
        branch = array.from_values(branch, branch)
    ctx.state("graph", (branch, leaf))
def on_bar(ctx, bar):
    branch, leaf = ctx.state("graph").value
    array.set(leaf, 0, bar.close)
    for _ in range(2):
        ctx.plot("Shared", array.get(branch, 0) is array.get(branch, 1))
        branch = array.get(branch, 0)
    ctx.plot("Value", array.get(branch, 0))
'''


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_shared_graph_preview_and_snapshot_preserve_aliases(mode):
    bars = [dict(time=index * 10, open=value, high=value, low=value, close=value, volume=1)
            for index, value in enumerate([1, 2, 3, 4])]
    session = pn.PyneIncrementalSession(script=DAG_SCRIPT)
    session.seed(bars[:2])
    committed = session.snapshot_portable_state()
    session.on_bar_updated(dict(bars[2], open=99, high=99, low=99, close=99))
    assert session.snapshot_portable_state() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=DAG_SCRIPT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=DAG_SCRIPT)
    for bar in bars[2:]:
        session.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == session.on_bar_closed(bar)
    assert restored.snapshot_result() == session.snapshot_result()
    value = next(line for line in restored.snapshot_result().lines if line["name"] == "Value")
    assert [point["value"] for point in value["data"]] == [1, 2, 3, 4]
