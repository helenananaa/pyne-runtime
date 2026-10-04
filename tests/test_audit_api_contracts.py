"""Admission, recovery and result-export contracts found by the runtime audit."""
from __future__ import annotations

import tracemalloc
from dataclasses import replace

import pytest

import pyne_runtime as pn
from pyne_runtime.collections import ArrayNamespace, PyneArray
from pyne_runtime.historical import HistoricalSession
from pyne_runtime.plot import OutputCollector, create_plot_functions
from pyne_runtime.security import PyneResourceLimitError


def _bars(count: int = 4):
    return [dict(time=i, open=1, high=1, low=1, close=1, volume=0)
            for i in range(count)]


SOURCE = 'def on_bar(ctx, bar):\n    ctx.plot("x", bar.close)\n'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_process_grace_rejected_with_required_hard_timeout(value):
    with pytest.raises(ValueError, match="process_grace_seconds must be finite"):
        pn.PyneSettings(executor_mode="process", require_hard_timeout=True,
                        timeout_seconds=0.01, process_grace_seconds=value)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_process_grace_from_env_rejected(monkeypatch, value):
    monkeypatch.setenv("PYNE_PROCESS_GRACE_SECONDS", value)
    with pytest.raises(ValueError, match="process_grace_seconds must be finite"):
        pn.PyneSettings.from_env()


def test_historical_admission_rejects_before_callbacks(monkeypatch):
    def unexpected_prepare(*args, **kwargs):
        pytest.fail("Rejected historical input must not prepare script callbacks")

    monkeypatch.setattr(pn.PyneIncrementalSession, "prepare", unexpected_prepare)
    with pytest.raises(PyneResourceLimitError, match="Too many data points"):
        HistoricalSession(SOURCE, _bars(), settings=pn.PyneSettings(max_bars=1))


@pytest.mark.parametrize("max_bars", [4, None])
def test_historical_admission_at_limit_and_unlimited(max_bars):
    history = HistoricalSession(SOURCE, _bars(), settings=pn.PyneSettings(max_bars=max_bars))
    assert history.advance(4).ok
    assert history.cursor == len(history.equity) == 4


def test_historical_restore_copy_failure_is_atomic():
    class UncopyableEquity(float):
        def __deepcopy__(self, memo):
            raise TypeError("equity copy failed")

    history = HistoricalSession(SOURCE, _bars())
    history.advance(1)
    snapshot = history.snapshot()
    before = history.advance(3)
    before_equity = list(history.equity)
    snapshot["equity"][0]["value"] = UncopyableEquity(1)

    with pytest.raises(TypeError, match="equity copy failed"):
        history.restore(snapshot)

    assert history.cursor == 3
    assert history.equity == before_equity
    assert history.advance(3) == before
    assert history.advance(4).ok
    assert len(history.equity) == 4


def test_historical_restore_state_failure_is_atomic():
    history = HistoricalSession(SOURCE, _bars())
    history.advance(1)
    snapshot = history.snapshot()
    before = history.advance(3)
    before_equity = list(history.equity)
    snapshot["state"] = replace(snapshot["state"], script_sha256="invalid")

    with pytest.raises(ValueError, match="script"):
        history.restore(snapshot)

    assert history.cursor == 3
    assert history.equity == before_equity
    assert history.advance(3) == before


def test_historical_failed_callback_cannot_run_again():
    source = '''def on_bar(ctx, bar):
    counter = ctx.state("counter", 0)
    counter.value += 1
    raise ValueError("callback failed")
'''
    history = HistoricalSession(source, _bars())
    calls = []
    callback = history._session._on_bar

    def tracked_callback(ctx, bar):
        calls.append(bar.time)
        callback(ctx, bar)

    history._session._on_bar = tracked_callback
    with pytest.raises(ValueError, match="callback failed"):
        history.advance(1)
    with pytest.raises(pn.PyneSecurityError, match="poisoned"):
        history.advance(1)
    assert calls == [0]


def test_known_array_size_rejected_before_allocation():
    namespace = ArrayNamespace(max_size=2)
    tracemalloc.start()
    try:
        with pytest.raises(PyneResourceLimitError, match="array size 100000 exceeds limit 2"):
            namespace.new(100_000)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 128_000


def test_sized_array_input_rejected_before_iterator_consumption():
    class TooLarge:
        def __len__(self):
            return 100_000

        def __iter__(self):
            pytest.fail("Over-limit sized input must not be iterated")

    with pytest.raises(PyneResourceLimitError, match="array size"):
        PyneArray(TooLarge(), max_size=2)


def test_unsized_array_input_stops_after_first_over_limit_item():
    consumed = []

    def values():
        for item in range(100_000):
            consumed.append(item)
            yield item

    with pytest.raises(PyneResourceLimitError, match="array size 3 exceeds limit 2"):
        ArrayNamespace(max_size=2).from_list(values())
    assert consumed == [0, 1, 2]


def test_array_iterator_at_limit_and_unlimited():
    assert PyneArray(iter([1, 2]), max_size=2).to_list() == [1, 2]
    assert ArrayNamespace().from_list(iter(range(100))).size() == 100


def test_frame_column_names_preserve_all_values_and_time():
    pytest.importorskip("pandas")
    names = ["A", "A", "A_2", "time", "time"]
    result = pn.PyneResult(lines=[
        {"name": name, "data": [{"time": 42, "value": value}]}
        for value, name in enumerate(names, 1)
    ])
    frame = result.to_frame()
    assert frame.columns.is_unique
    assert frame["time"].tolist() == [42]
    assert frame.drop(columns="time").iloc[0].tolist() == [1, 2, 3, 4, 5]


def test_batch_table_budget_rejects_before_mutation_and_releases_capacity():
    collector = OutputCollector(times=[0], max_table_cells=1)
    table = create_plot_functions(collector)["table"]
    first = table.new(columns=2, rows=1)
    second = table.new(columns=1, rows=1)
    table.cell(first, 0, 0, "initial")
    table.cell(first, 0, 0, "updated")
    before = collector.to_dict()

    with pytest.raises(PyneResourceLimitError, match="max_table_cells"):
        table.cell(second, 0, 0, "over limit")
    assert collector.to_dict() == before

    table.clear(first)
    table.cell(second, 0, 0, "after clear")
    table.delete(second)
    table.cell(first, 1, 0, "after delete")
    assert collector.to_dict()["objects"]["tables"][0]["cells"][0]["text"] == "after delete"


def test_batch_table_budget_is_shared_across_tables_and_default_unlimited():
    script = '''left = table.new(columns=2, rows=1)
right = table.new(columns=1, rows=1)
table.cell(left, 0, 0, "a")
table.cell(left, 1, 0, "b")
table.cell(right, 0, 0, "c")
'''
    limited = pn.run(script, _bars(1), settings=pn.PyneSettings(max_table_cells=1))
    assert not limited.ok
    assert limited.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    unlimited = pn.run(script, _bars(1))
    assert unlimited.ok, unlimited.error
    assert sum(len(table["cells"]) for table in unlimited.output["objects"]["tables"]) == 3
