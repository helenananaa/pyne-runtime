"""Resource independence and restricted-Python authoring regressions."""

from dataclasses import replace

import pytest
import pyne_runtime as pn
from pyne_runtime.security import PyneSecurityError


def bar(i=1):
    return dict(time=i, open=1.0, high=2.0, low=1.0, close=1.5, volume=100.0)


def test_drawing_objects_do_not_consume_series_budget():
    script = "for i in range(21):\n    label.new(i, 1.5, str(i))\nplot(close)"
    settings = pn.PyneSettings(executor_mode="inline", max_output_series=1)
    result = pn.run(script, [bar()], settings=settings)
    assert result.ok, result.error
    assert len(result.output["objects"]["labels"]) == 21
    rejected = pn.run(script, [bar()], settings=replace(settings, max_drawing_objects=20))
    assert not rejected.ok
    assert rejected.code == "PYNE_OUTPUT_LIMIT_EXCEEDED"
    rejected = pn.run("plot(close)\nplot(open)", [bar()], settings=settings)
    assert rejected.code == "PYNE_OUTPUT_LIMIT_EXCEEDED"


@pytest.mark.parametrize("mode", ["safe", "research", "unsafe"])
def test_window_budget_is_configurable_independently_of_imports(mode):
    script = "def on_bar(ctx, bar):\n    ctx.window('long', 10001).append(bar.close)\n    ctx.plot('close', bar.close)"
    settings = pn.PyneSettings(
        executor_mode="inline",
        security_mode=mode,
        max_window_size=10001,
        max_total_window_items=10001,
    )
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    assert session.seed([bar()]).ok
    session = pn.PyneIncrementalSession(
        script=script, settings=replace(settings, max_window_size=10000)
    )
    with pytest.raises(PyneSecurityError, match="max_window_size"):
        session.seed([bar()])


@pytest.mark.parametrize("mode", ["safe", "research"])
def test_basic_iterators_work_and_classes_have_early_diagnostics(mode):
    settings = pn.PyneSettings(executor_mode="inline", security_mode=mode)
    result = pn.run("plot([next(iter([2]))])", [bar()], settings=settings)
    assert result.ok, result.error
    script = "class Helper:\n    pass\nplot(close)"
    diagnostics = pn.validate(script, settings=settings)
    assert diagnostics[0]["code"] == "PYNE_UNSUPPORTED_FEATURE"
    assert "Class definitions" in diagnostics[0]["message"]
    assert pn.run(script, [bar()], settings=settings).code == "PYNE_UNSUPPORTED_FEATURE"


def test_research_standard_libraries_and_explicit_allowlist():
    settings = pn.PyneSettings(executor_mode="inline", security_mode="research")
    script = "import math\nimport statistics\nplot([math.sqrt(statistics.mean([4,4]))])"
    result = pn.run(script, [bar()], settings=settings)
    assert result.ok, result.error
    assert (
        pn.run("import os\nplot(close)", [bar()], settings=settings).code == "PYNE_IMPORT_BLOCKED"
    )
    assert (
        pn.run(script, [bar()], settings=replace(settings, allowed_imports=("numpy",))).code
        == "PYNE_IMPORT_BLOCKED"
    )


@pytest.mark.parametrize("mode", ["local", "replay", "state"])
def test_custom_budgets_survive_portable_restore(mode):
    script = "def on_bar(ctx, bar):\n    ctx.window('long', 10001).append(bar.close)\n    ctx.plot('close', bar.close)"
    settings = pn.PyneSettings(
        executor_mode="inline",
        max_window_size=10001,
        max_total_window_items=10002,
        max_state_keys=101,
        max_object_events=21,
        max_strategy_log_entries=22,
        max_state_payload_items=12345,
        max_preview_payload_items=1234,
        max_table_cells=17,
        request_cache_max_bars=12,
    )
    original = pn.PyneIncrementalSession(script=script, settings=settings)
    original.seed([bar()])
    if mode == "local":
        snapshot = original.snapshot_state()
        restore = pn.PyneIncrementalSession.from_snapshot
    else:
        snapshot = original.snapshot_portable(mode=mode)
        restore = pn.PyneIncrementalSession.from_portable_snapshot
    restored = restore(snapshot, script=script)
    from pyne_runtime.incremental.checkpoint import portable_settings_contract

    assert portable_settings_contract(restored.settings) == portable_settings_contract(settings)
    assert original.on_bar_closed(bar(2)) == restored.on_bar_closed(bar(2))
    expanded = restore(snapshot, script=script, settings=replace(settings, max_window_size=10002))
    assert expanded.settings.max_window_size == 10002
    assert expanded.on_bar_closed(bar(2)).ok
    assert expanded.snapshot_result() == restored.snapshot_result()


@pytest.mark.parametrize(
    "name",
    [
        "cache_max_items",
        "max_window_size",
        "max_total_window_items",
        "max_state_keys",
        "max_object_events",
        "max_strategy_log_entries",
        "max_state_payload_items",
        "max_preview_payload_items",
        "max_table_cells",
        "request_cache_max_bars",
    ],
)
def test_budget_zero_is_not_silently_changed(name, monkeypatch):
    with pytest.raises(ValueError, match=name):
        pn.PyneSettings(**{name: 0})
    monkeypatch.setenv("PYNE_" + name.upper(), "123")
    assert getattr(pn.PyneSettings.from_env(), name) == 123
