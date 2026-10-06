"""Linefill authority keeps its graph identity when its index is reconstructed."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import decode_portable_state_checkpoint
from pyne_runtime.incremental.state_codec import decode_typed_state_graph, encode_typed_state_graph
from pyne_runtime.plot.linefill_store import LineFillStore


SCRIPT = '''
indicator("Aliased fills", mode="incremental")
store = None
refs = []
def on_bar(ctx, bar):
    global store, refs
    if ctx.bar_index == 0:
        refs = [line.new(0, 0, 1, 1), line.new(0, 1, 1, 2)]
        if params["create_first"]:
            linefill.new(refs[0], refs[1])
        store = ctx._object_linefills
    elif ctx.bar_index == 1:
        if params["create_first"]:
            line.delete(refs[0])
        else:
            linefill.new(refs[0], refs[1])
    elif ctx.bar_index == 2:
        if not params["create_first"]:
            line.delete(refs[0])
    ctx.plot("Aliased", len(store))
    ctx.plot("Current", len(ctx._object_linefills))
'''
BARS = [dict(time=i, open=1, high=1, low=1, close=1, volume=1) for i in (1, 2, 3)]


def _values(result):
    return {entry["name"]: [point["value"] for point in entry["data"]]
            for entry in result.lines}


@pytest.mark.parametrize("create_first", [False, True])
@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_empty_and_nonempty_linefill_authority_alias_survives_all_recovery(create_first, mode):
    original = pn.PyneIncrementalSession(script=SCRIPT, params={"create_first": create_first})
    original.seed(BARS[:1])
    restored = (pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
                if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
                    original.snapshot_portable(mode=mode), script=SCRIPT))
    assert restored._globals["store"] is restored._ctx._object_linefills
    assert isinstance(restored._ctx._object_linefills, LineFillStore)
    before = restored.snapshot_portable_state()
    preview = restored.on_bar_updated(BARS[1])
    expected = 0.0 if create_first else 1.0
    assert _values(preview) == {"Aliased": [expected], "Current": [expected]}
    assert original.on_bar_updated(BARS[1]) == preview
    assert restored.snapshot_portable_state() == before
    assert restored._globals["store"] is restored._ctx._object_linefills
    for bar in BARS[1:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
        assert restored._globals["store"] is restored._ctx._object_linefills
    values = _values(restored.snapshot_result())
    assert values["Aliased"] == values["Current"]
    assert values["Current"][-1] == 0


@pytest.mark.parametrize("entry_first", [False, True])
def test_linefill_typed_kind_preserves_cycles_and_entry_alias_without_index_payload(entry_first):
    store = LineFillStore()
    entry = dict(owner=store, id="fill_1", line1_id="line_1", line2_id="line_2", color="blue")
    store["fill_1"] = entry
    value = ({"entry": entry, "store": store, "alias": store} if entry_first
             else {"store": store, "alias": store, "entry": entry})
    graph = encode_typed_state_graph(value, max_nodes=1000, max_depth=32)
    node = next(node for node in graph["nodes"] if node["kind"] == "linefill-store")
    assert set(node) == {"kind", "items"}
    assert "_by_line" not in json.dumps(graph)
    restored = decode_typed_state_graph(graph, max_nodes=1000, max_depth=32)
    assert isinstance(restored["store"], LineFillStore)
    assert restored["store"] is restored["alias"]
    assert restored["store"]["fill_1"] is restored["entry"]
    assert restored["entry"]["owner"] is restored["store"]
    assert restored["store"].dependent_ids("line_1") == ("fill_1",)
    restored["store"].pop("fill_1")
    assert restored["alias"] == {}
    assert restored["store"].dependent_ids("line_2") == ()


def _graph():
    return {"schemaVersion": 1, "root": {"$ref": 0}, "nodes": [
        {"kind": "linefill-store", "items": [["fill_1", {"$ref": 1}]]},
        {"kind": "dict", "items": [["id", "fill_1"], ["line1_id", "line_1"],
                                    ["line2_id", "line_2"], ["color", "blue"]]},
    ]}


@pytest.mark.parametrize("case", ["extra_field", "missing_items", "items_type", "bad_pair",
                                  "duplicate", "key_type", "empty_key", "entry_type",
                                  "missing_id", "different_id", "id_type", "missing_line1",
                                  "missing_line2", "endpoint_type", "empty_endpoint",
                                  "unknown_kind"])
def test_linefill_typed_kind_rejects_malformed_nodes_and_entries(case):
    graph = _graph()
    node, entry = graph["nodes"]
    if case == "extra_field":
        node["_by_line"] = {}
    elif case == "missing_items":
        node.pop("items")
    elif case == "items_type":
        node["items"] = {}
    elif case == "bad_pair":
        node["items"] = [["fill_1"]]
    elif case == "duplicate":
        node["items"].append(list(node["items"][0]))
    elif case == "key_type":
        node["items"][0][0] = 1
    elif case == "empty_key":
        node["items"][0][0] = ""
    elif case == "entry_type":
        node["items"][0][1] = "bad"
    elif case == "different_id":
        entry["items"][0][1] = "different"
    elif case == "id_type":
        graph["nodes"].append({"kind": "list", "items": [1, 2]})
        entry["items"][0][1] = {"$ref": 2}
    elif case.startswith("missing_"):
        name = {"missing_id": "id", "missing_line1": "line1_id", "missing_line2": "line2_id"}[case]
        entry["items"] = [pair for pair in entry["items"] if pair[0] != name]
    elif case == "endpoint_type":
        entry["items"][1][1] = 1
    elif case == "empty_endpoint":
        entry["items"][1][1] = ""
    elif case == "unknown_kind":
        node["kind"] = "linefill-store/unknown"
    with pytest.raises(pn.PynePortableSnapshotError):
        decode_typed_state_graph(graph, max_nodes=1000, max_depth=32)


@pytest.mark.parametrize("corruption", ["extra_field", "missing_endpoint", "different_id"])
def test_malformed_portable_linefill_state_rejects_without_touching_healthy_scope(corruption, monkeypatch):
    monkeypatch.setattr("pyne_runtime.cache.time.time", lambda: 12345.0)
    healthy = pn.PyneIncrementalSession(script=SCRIPT, params={"create_first": True})
    healthy.seed(BARS[:1])
    before = healthy.snapshot_portable_state()
    envelope = json.loads(before)
    graph = envelope["payload"]["stateGraph"]
    node = next(node for node in graph["nodes"] if node["kind"] == "linefill-store")
    if corruption == "extra_field":
        node["_by_line"] = {}
    else:
        entry = graph["nodes"][node["items"][0][1]["$ref"]]
        if corruption == "missing_endpoint":
            entry["items"] = [pair for pair in entry["items"] if pair[0] != "line1_id"]
        else:
            next(pair for pair in entry["items"] if pair[0] == "id")[1] = "different"
    canonical = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode()
    envelope["checksum"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    corrupted = json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode()
    cache = healthy.execution_scope.cache
    sentinel = cache.get_or_load("sentinel", lambda: [1, 2])
    healthy.on_bar_updated(BARS[1])
    with pytest.raises(pn.PynePortableSnapshotError):
        pn.PyneIncrementalSession.from_portable_snapshot(
            corrupted, script=SCRIPT, execution_scope=healthy.execution_scope)
    assert cache.get_or_load("sentinel", lambda: pytest.fail("lost live cache")) is sentinel
    # The sentinel belongs to scope state, so compare after it was published.
    kept = healthy.snapshot_portable_state()
    with pytest.raises(pn.PynePortableSnapshotError):
        decode_portable_state_checkpoint(corrupted)
    assert healthy.snapshot_portable_state() == kept
    assert healthy._globals["store"] is healthy._ctx._object_linefills
    result = healthy.on_bar_closed(BARS[1])
    assert _values(result) == {"Aliased": [0.0], "Current": [0.0]}


def test_reconstructed_linefill_store_deepcopy_keeps_dependency_and_alias():
    decoded = decode_typed_state_graph(_graph(), max_nodes=1000, max_depth=32)
    cloned = copy.deepcopy({"a": decoded, "b": decoded})
    assert cloned["a"] is cloned["b"]
    assert cloned["a"] is not decoded
    assert cloned["a"].dependent_ids("line_1") == ("fill_1",)
