"""Standalone workloads are unrestricted unless the caller supplies a policy."""

from dataclasses import replace
import json
import os

import pytest
import pyne_runtime as pn
from pyne_runtime.security import PyneSecurityError


def bars(count):
    return [
        dict(time=i + 1, open=1.0, high=2.0, low=1.0, close=1.5, volume=1.0) for i in range(count)
    ]


SCRIPT = """
def on_bar(ctx, bar):
    values = ctx.state("values", array.new_float())
    values.value.push(bar.close)
    ctx.window("sample", 3).append(bar.close)
    ctx.plot("count", values.value.size())
"""


def test_default_pandas_workload_exceeds_old_input_limit():
    pd = pytest.importorskip("pandas")
    data = pn.from_pandas(pd.DataFrame(bars(50001)))
    result = pn.run(
        "import pandas as pd\nplot(pd.Series(close.values).rolling(3, min_periods=1).mean())", data
    )
    assert result.ok, result.error
    assert len(result.lines[0]["data"]) == 50001
    assert result.lines[0]["data"][-1]["value"] == 1.5


def test_default_python_runs_in_callers_process_with_normal_objects():
    result = pn.run(
        "import os\nclass Value:\n    x = params['helper']()\nplot([Value.x])",
        bars(1),
        params={"helper": lambda: os.getpid()},
    )
    assert result.ok, result.error
    assert result.lines[0]["data"][0]["value"] == os.getpid()


def test_default_execution_can_finish_after_old_five_second_deadline():
    result = pn.run("import time\ntime.sleep(5.1)\nplot(close)", bars(1))
    assert result.ok, result.error
    assert pn.PyneSettings().timeout_seconds is None


def test_explicit_process_can_run_without_a_deadline():
    result = pn.run("import os\nplot([os.getpid()])", bars(1), executor_mode="process")
    assert result.ok, result.error
    assert result.lines[0]["data"][0]["value"] != os.getpid()


def test_collections_and_drawing_outputs_are_not_chart_capacity_limited():
    result = pn.run(
        """
a = array.new_float(100001, 0)
m = matrix.new_float(400, 400, 0)
for i in range(501):
    label.new(i, 1.5, str(i))
for i in range(21):
    plot(close, str(i))
""",
        bars(1),
    )
    assert result.ok, result.error
    assert len(result.output["objects"]["labels"]) == 501
    assert len(result.lines) == 21


def test_explicit_import_and_collection_policies_still_work():
    restricted = pn.PyneSettings(security_mode="safe", max_array_size=2)
    assert (
        pn.run("import os\nplot(close)", bars(1), settings=restricted).code == "PYNE_IMPORT_BLOCKED"
    )
    result = pn.run("array.new_float(3, 0)", bars(1), settings=restricted)
    assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    result = pn.run(
        "array.new_float(3, 0)", bars(1), settings=replace(restricted, max_array_size=None)
    )
    assert result.ok, result.error


def test_seed_admission_error_does_not_poison_existing_session():
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=pn.PyneSettings(max_bars=1))
    session.seed(bars(1))
    before = session.snapshot_result()
    with pytest.raises(PyneSecurityError, match="Too many data points"):
        session.seed(bars(2))
    assert session.snapshot_result() == before
    assert session.on_bar_closed(bars(2)[-1]).ok


def test_input_retention_and_replay_history_are_independent():
    settings = pn.PyneSettings(max_bars=1, incremental_retention_bars=3)
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    session.seed(bars(1))
    for bar in bars(5)[1:]:
        session.on_bar_closed(bar)
    assert session.retention_bars == 3
    assert len(session.snapshot_result().lines[0]["data"]) == 3
    payload = session.snapshot_portable()
    assert len(json.loads(payload)["payload"]["bars"]) == 5
    restored = pn.PyneIncrementalSession.from_portable_snapshot(payload, script=SCRIPT)
    assert restored.snapshot_result() == session.snapshot_result()


def test_default_history_is_not_silently_trimmed():
    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed(bars(4))
    assert session.retention_bars is None
    assert len(session.snapshot_result().lines[0]["data"]) == 4
    assert json.loads(session.snapshot_portable())["payload"]["retentionBars"] is None


@pytest.mark.parametrize("mode", ["local", "replay", "state"])
def test_restore_rebinds_collection_budgets_and_allows_operational_changes(mode):
    settings = pn.PyneSettings(max_array_size=2, max_output_points=2, max_window_size=3)
    original = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    original.seed(bars(2))
    before = original.snapshot_portable_state()
    if mode == "local":
        payload = original.snapshot_state()
        restore = pn.PyneIncrementalSession.from_snapshot
    else:
        payload = original.snapshot_portable(mode=mode)
        restore = pn.PyneIncrementalSession.from_portable_snapshot
    settings = replace(
        settings,
        max_array_size=None,
        max_output_points=None,
        timeout_seconds=30,
        cache_max_items=64,
        request_cache_max_bars=12,
    )
    restored = restore(payload, script=SCRIPT, settings=settings)
    assert restored.on_bar_updated(bars(3)[-1]).ok
    assert restored.on_bar_closed(bars(3)[-1]).lines[0]["data"][-1]["value"] == 3
    assert original.snapshot_portable_state() == before
    with pytest.raises((ValueError, PyneSecurityError), match="max_output_points|output points"):
        restore(payload, script=SCRIPT, settings=replace(settings, max_output_points=1))
    assert original.snapshot_portable_state() == before
    with pytest.raises(ValueError, match="computation contract"):
        restore(payload, script=SCRIPT, settings=replace(settings, timeframe="5"))


def test_smaller_budget_that_fits_can_restore_and_then_enforce():
    original = pn.PyneIncrementalSession(script=SCRIPT)
    original.seed(bars(2))
    restored = pn.PyneIncrementalSession.from_snapshot(
        original.snapshot_state(),
        script=SCRIPT,
        settings=pn.PyneSettings(max_array_size=3, max_output_points=3),
    )
    assert restored.on_bar_closed(bars(3)[-1]).ok
    with pytest.raises(PyneSecurityError, match="array size"):
        restored.on_bar_closed(bars(4)[-1])


def test_unlimited_environment_and_constructor_budgets(monkeypatch):
    from pyne_runtime.settings import OPTIONAL_BUDGET_FIELDS

    for name in OPTIONAL_BUDGET_FIELDS:
        assert getattr(pn.PyneSettings(), name) is None
        monkeypatch.setenv("PYNE_" + name.upper(), "none")
    settings = pn.PyneSettings.from_env()
    assert all(getattr(settings, name) is None for name in OPTIONAL_BUDGET_FIELDS)
    assert pn.PyneSettings(timeout_seconds=0).timeout_seconds is None
