"""Session import and codec identity contracts across internal isolation changes."""

from __future__ import annotations

import json

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental import session as session_module
from pyne_runtime.incremental.state_codec import _runtime_type_registry


SCRIPT = '''
indicator("Function state compatibility", mode="incremental")
values = []

def helper(bar, bucket=values):
    bucket.append(bar.close)
    helper.calls += 1
    return sum(bucket) * params["scale"]

helper.calls = 0

def on_bar(ctx, bar):
    ctx.plot("Total", helper(bar))
'''


def _bar(time, close):
    return dict(time=time, open=close, high=close, low=close, close=close, volume=1)


@pytest.mark.parametrize("mode", ("local", "state"))
def test_existing_session_codec_names_and_function_state_continue_after_preview(mode):
    registry = _runtime_type_registry()
    for name in (
        "PyneIncrementalSessionSnapshot",
        "_FunctionStateSnapshot",
        "_ReadOnlyMapping",
        "_PreviewModuleProxy",
    ):
        assert registry[f"pyne_runtime.incremental.session:{name}"] is getattr(
            session_module, name
        )

    original = pn.PyneIncrementalSession(script=SCRIPT, params={"scale": 2})
    original.seed([_bar(1, 1), _bar(2, 2)])
    committed = original.snapshot_portable_state()
    original.on_bar_updated(_bar(3, 30))
    assert original.snapshot_portable_state() == committed

    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            original.snapshot_state(), script=SCRIPT
        )
    else:
        graph = json.loads(committed)["payload"]["stateGraph"]
        names = {node.get("type") for node in graph["nodes"]}
        for name in (
            "PyneIncrementalSessionSnapshot", "_FunctionStateSnapshot", "_ReadOnlyMapping"
        ):
            assert f"pyne_runtime.incremental.session:{name}" in names
        restored = pn.PyneIncrementalSession.from_portable_snapshot(committed, script=SCRIPT)

    assert restored._globals["helper"].__defaults__[0] is restored._globals["values"]
    assert restored._globals["helper"].calls == 2
    assert restored._globals["helper"].__globals__ is restored._globals
    original.on_bar_updated(_bar(3, 3))
    restored.on_bar_updated(_bar(3, 3))
    assert restored.on_bar_closed(_bar(3, 3)) == original.on_bar_closed(_bar(3, 3))
    assert restored._globals["helper"].calls == 3
    assert restored._globals["values"] == [1, 2, 3]
