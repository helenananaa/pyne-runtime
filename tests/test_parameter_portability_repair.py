"""Portable parameters must not silently discard a user's scalar type or state."""
from __future__ import annotations

import copy

import numpy as np
import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import (
    PortableCheckpoint,
    decode_portable_checkpoint,
    encode_portable_checkpoint,
)
from pyne_runtime.incremental.state_codec import decode_typed_state_graph, encode_typed_state_graph


class _TaggedInt(int):
    pass


class _TaggedFloat(float):
    pass


class _TaggedStr(str):
    pass


def _copy_numpy_scalar(value, payload, memo):
    clone = type(value)(payload)
    memo[id(value)] = clone
    clone.__dict__.update(copy.deepcopy(value.__dict__, memo))
    return clone


class _TaggedNumpyFloat(np.float64):
    def __deepcopy__(self, memo):
        return _copy_numpy_scalar(self, float(self), memo)


class _TaggedNumpyFloat32(np.float32):
    def __deepcopy__(self, memo):
        return _copy_numpy_scalar(self, float(self), memo)


class _TaggedNumpyInt(np.int64):
    def __deepcopy__(self, memo):
        return _copy_numpy_scalar(self, int(self), memo)


_TAGGED = [(_TaggedInt, 7), (_TaggedFloat, 7.0), (_TaggedStr, "x"),
           (_TaggedNumpyFloat, 7.0), (_TaggedNumpyFloat32, 7.0), (_TaggedNumpyInt, 7)]
_BARS = [dict(time=i, open=1, high=1, low=1, close=1, volume=1) for i in (1, 2, 3)]
_SCRIPT = '''
def on_bar(ctx, bar):
    ticks = ctx.varip("ticks", 0)
    ticks.value += 1
    ctx.plot("Items", len(ctx.params["x"].items))
    ctx.plot("Ticks", ticks.value)
'''


def _tagged(factory, value):
    result = factory(value)
    result.items = [1, 2]
    return result


@pytest.mark.parametrize("factory,value", _TAGGED)
def test_tagged_scalar_local_snapshot_preserves_type_attributes_and_continuation(factory, value):
    supplied = _tagged(factory, value)
    original = pn.PyneIncrementalSession(script=_SCRIPT, params={"x": supplied})
    original.seed(_BARS[:1])
    snapshot = original.snapshot_state()
    original.restore_state(snapshot)
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=_SCRIPT)
    copied = restored.params["x"]
    assert type(copied) is factory
    assert copied.items == [1, 2]
    copied.items.append(3)
    assert supplied.items == [1, 2]
    assert restored.params["x"].items == [1, 2]
    assert restored.on_bar_closed(_BARS[1]) == original.on_bar_closed(_BARS[1])


@pytest.mark.parametrize("factory,value", _TAGGED)
@pytest.mark.parametrize("mode", ["state", "replay"])
def test_tagged_scalar_portable_export_rejects_without_mutating_healthy_session(factory, value, mode):
    original = pn.PyneIncrementalSession(script=_SCRIPT, params={"x": _tagged(factory, value)})
    reference = pn.PyneIncrementalSession(script=_SCRIPT, params={"x": _tagged(factory, value)})
    original.seed(_BARS[:1])
    reference.seed(_BARS[:1])
    assert original.on_bar_updated(_BARS[1]) == reference.on_bar_updated(_BARS[1])
    context, preview, scope, cache = (original._ctx, original._active_ctx,
                                    original.execution_scope, original.execution_scope.cache)
    before = original.snapshot_result()
    bars = copy.deepcopy(original._portable_bars)
    with pytest.raises(pn.PynePortableSnapshotError, match="cannot encode"):
        original.snapshot_portable(mode=mode)
    assert original._ctx is context
    assert original._active_ctx is preview
    assert original.execution_scope is scope
    assert original.execution_scope.cache is cache
    assert original.snapshot_result() == before
    assert original._portable_bars == bars
    assert original.last_closed_time == 1
    assert type(original.params["x"]) is factory
    assert original.params["x"].items == [1, 2]
    assert original.on_bar_updated(_BARS[1]) == reference.on_bar_updated(_BARS[1])
    for bar in _BARS[1:]:
        assert original.on_bar_closed(bar) == reference.on_bar_closed(bar)


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_tagged_string_mapping_key_is_not_silently_normalized(mode):
    key = _tagged(_TaggedStr, "key")
    script = "def on_bar(ctx, bar): ctx.plot('n', ctx.params['mapping']['key'])"
    original = pn.PyneIncrementalSession(script=script, params={"mapping": {key: 7}})
    original.seed(_BARS[:1])
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=script)
    copied_key = next(iter(restored.params["mapping"]))
    assert type(copied_key) is _TaggedStr
    assert copied_key.items == [1, 2]
    with pytest.raises(pn.PynePortableSnapshotError, match="cannot encode|keys must be"):
        original.snapshot_portable(mode=mode)
    assert original.on_bar_closed(_BARS[1]).ok
    assert key.items == [1, 2]


@pytest.mark.parametrize("factory,value", _TAGGED)
def test_scalar_subclass_without_attributes_is_still_an_unknown_portable_type(factory, value):
    with pytest.raises(pn.PynePortableSnapshotError, match="cannot encode"):
        encode_typed_state_graph(factory(value), max_nodes=100, max_depth=16)


@pytest.mark.parametrize("value", [None, True, 7, 7.0, "x"])
@pytest.mark.parametrize("mode", ["state", "replay"])
def test_builtin_scalar_parameters_remain_portable(value, mode):
    script = "def on_bar(ctx, bar): ctx.plot('n', len(str(ctx.params['x'])))"
    original = pn.PyneIncrementalSession(script=script, params={"x": value})
    original.seed(_BARS[:1])
    payload = original.snapshot_portable(mode=mode)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(payload, script=script)
    assert restored.snapshot_result() == original.snapshot_result()
    assert restored.on_bar_closed(_BARS[1]) == original.on_bar_closed(_BARS[1])
    assert type(restored.params["x"]) in (type(None), bool, int, float, str)


@pytest.mark.parametrize("value", [np.bool_(True), np.int64(7), np.float64(7),
                                  np.float32(7), np.str_("x")])
@pytest.mark.parametrize("mode", ["state", "replay"])
def test_standard_numpy_scalars_retain_portable_codec_normalization(value, mode):
    if mode == "state":
        graph = encode_typed_state_graph({"x": value}, max_nodes=100, max_depth=16)
        restored = decode_typed_state_graph(graph, max_nodes=100, max_depth=16)["x"]
    else:
        checkpoint = PortableCheckpoint(
            script_sha256="0" * 64, params={"x": value}, settings={}, retention_bars=None,
            bars=(), seed_count=0, provider_required=False,
        )
        restored = decode_portable_checkpoint(encode_portable_checkpoint(checkpoint)).params["x"]
    assert type(restored) is type(value.item())
    assert restored == value.item()


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_plain_string_mapping_keys_remain_portable(mode):
    script = "def on_bar(ctx, bar): ctx.plot('n', ctx.params['mapping']['key'])"
    original = pn.PyneIncrementalSession(script=script, params={"mapping": {"key": 7}})
    original.seed(_BARS[:1])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(mode=mode), script=script)
    assert restored.on_bar_closed(_BARS[1]) == original.on_bar_closed(_BARS[1])
