"""Creation work is bounded independently from mutable-payload enforcement."""
from __future__ import annotations

import pytest

import pyne_runtime as pn
import pyne_runtime.incremental.context as context_module
from pyne_runtime.incremental.context import IncrementalContext
from pyne_runtime.incremental.limits import IncrementalLimits, _state_payload_items
from pyne_runtime.security import PyneResourceLimitError


@pytest.mark.parametrize("count", [32, 128, 512])
def test_unlimited_scalar_varip_initialization_has_linear_payload_work(monkeypatch, count):
    calls = 0
    original = context_module._state_payload_items

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(context_module, "_state_payload_items", counted)
    script = f'''
def init(ctx):
    for i in range({count}):
        ctx.varip(str(i), 0)
def on_bar(ctx, bar):
    pass
'''
    session = pn.PyneIncrementalSession(script=script)
    session.seed([])
    assert len(session._ctx._varip_states) == count
    assert session._limits.max_state_payload_items is None
    assert calls <= 3 * count


def test_new_varip_detects_existing_nested_mutation_before_admission():
    ctx = IncrementalContext(params={}, limits=IncrementalLimits(
        enabled=True, max_state_payload_items=8))
    first = ctx.varip("first", [])
    first.value.extend(range(8))
    before = ctx._limit_tracker.varip_payload_items
    with pytest.raises(PyneResourceLimitError):
        ctx.varip("second", 0)
    assert set(ctx._varip_states) == {"first"}
    assert ctx._limit_tracker.varip_payload_items == before
    first.value[:] = []
    second = ctx.varip("second", 0)
    assert second.value == 0
    assert ctx._limit_tracker.varip_payload_items == 2


def test_new_varip_accounts_for_assignment_mutation_and_actual_copy_payload():
    ctx = IncrementalContext(params={}, limits=IncrementalLimits(
        enabled=True, max_state_payload_items=7))
    first = ctx.varip("first", 0)
    first.value = list(range(6))
    with pytest.raises(PyneResourceLimitError):
        ctx.varip("second", 0)
    assert "second" not in ctx._varip_states


def test_unlimited_varip_mutation_is_recounted_at_existing_sync_boundary():
    ctx = IncrementalContext(params={}, limits=IncrementalLimits(enabled=True))
    first = ctx.varip("first", [])
    ctx.varip("second", 0)
    first.value.extend(range(10))
    ctx.sync_varip_payload()
    assert ctx._limit_tracker.varip_payload_items == (
        _state_payload_items(first.value) + _state_payload_items(0))


class _ExpandingList(list):
    def __deepcopy__(self, memo):
        return list(range(10))


def test_copied_varip_default_must_fit_budget_before_publication():
    ctx = IncrementalContext(params={}, limits=IncrementalLimits(
        enabled=True, max_state_payload_items=5))
    ctx.varip("first", 0)
    with pytest.raises(PyneResourceLimitError):
        ctx.varip("second", _ExpandingList())
    assert set(ctx._varip_states) == {"first"}
    assert ctx._limit_tracker.varip_payload_items == 1


def test_init_nested_mutation_is_recounted_before_context_is_available():
    script = '''
def init(ctx):
    cell = ctx.varip("a", [])
    cell.value.extend(range(10))
def on_bar(ctx, bar):
    pass
'''
    session = pn.PyneIncrementalSession(
        script=script, settings=pn.PyneSettings(max_state_payload_items=5))
    with pytest.raises(PyneResourceLimitError):
        session.seed([])
    assert session._ctx is None
