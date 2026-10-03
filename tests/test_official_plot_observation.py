"""Execution evidence distinguishes all-missing plots from unimplemented plots."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pyne_runtime as pn
import pytest
from pyne_runtime.incremental.context import IncrementalContext

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("plot_observer_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
BARS = [dict(time=i, open=2, high=3, low=1, close=2, volume=1) for i in range(4)]
SOURCE = '''indicator("Observed missing outputs", mode="incremental")
def on_bar(ctx, bar):
    for title, value in (("Empty dynamic", None), ("NaN dynamic", float("nan")), ("Numbers", 2)):
        ctx.plot(title, value)
    ctx.plot("Alias", None, title="Explicit title")
    ctx.plot("Invalid value", "not a number")
    if False:
        ctx.plot("Unexecuted", None)
'''


def test_observation_preserves_runtime_results_and_only_counts_executed_valid_calls():
    baseline = pn.run(SOURCE, BARS, executor_mode="inline")
    result, calls = reporter.run_with_plot_observations(SOURCE, BARS)
    assert result.ok and baseline.ok
    assert result.to_dict() == baseline.to_dict()
    assert calls == {"Empty dynamic": {"calls": 4, "missingCalls": 4},
                     "NaN dynamic": {"calls": 4, "missingCalls": 4},
                     "Numbers": {"calls": 4, "missingCalls": 0},
                     "Explicit title": {"calls": 4, "missingCalls": 4}}


def test_scoped_observation_restores_plot_method_when_execution_raises(monkeypatch):
    original = IncrementalContext.plot
    def failing_run(*args, **kwargs):
        assert IncrementalContext.plot is not original
        raise RuntimeError("controlled execution exception")
    monkeypatch.setattr(reporter.pn, "run", failing_run)
    with pytest.raises(RuntimeError, match="controlled execution"):
        reporter.run_with_plot_observations(SOURCE, BARS)
    assert IncrementalContext.plot is original


@pytest.mark.parametrize("name,titles", (
    ("rolling_statistics", ("Empty SMA", "Empty Stdev", "Sample variance 1")),
    ("trend_volume", ("Zero weight",)),
))
def test_existing_all_missing_recipes_are_measured_from_executed_calls(name, titles):
    result = reporter.workload_report(ROOT, name, set(), True)
    capture = json.loads((ROOT / "tests/workloads" / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    count = len(capture["rows"])
    for title in titles:
        assert title in result["columns"] and title not in result["unmappedOutputColumns"]
        assert result["executedCallbackPlotCalls"][title] == {"calls": count, "missingCalls": count}
        assert result["columns"][title]["counts"]["bothMissingCells"] == count
        assert result["columns"][title]["counts"]["activeCells"] == 0


def test_absent_recipe_discloses_scope_leads_without_claiming_behavior_failure(tmp_path):
    # Keep an actual absent route after the production recipe is now supplied.
    folder = tmp_path / 'tests/workloads'
    folder.mkdir(parents=True)
    for suffix in ('pine','tradingview.json','tradingview.txt','_batch.py'):
        name = 'direction_missing'+(suffix if suffix.startswith('_') else '.'+suffix)
        shutil.copy2(ROOT / 'tests/workloads' / name, folder / name)
    result = reporter.workload_report(tmp_path, "direction_missing", set(), True)
    assert result["status"] == "unmapped"
    assert result["batchMethodCandidates"] == ["falling", "rising"]
    assert result["undeclaredIncrementalMethodCandidates"] == ["falling", "rising"]
    assert "columns" not in result


def test_remaining_missing_columns_disclose_direct_method_scope_separately(tmp_path):
    # An intentionally partial independent recipe keeps the missing-column
    # detection contract exercised after all production columns are mapped.
    folder = tmp_path / 'tests/workloads'
    folder.mkdir(parents=True)
    for suffix in ('pine','tradingview.json','tradingview.txt','_batch.py'):
        name = 'foundation'+(suffix if suffix.startswith('_') else '.'+suffix)
        shutil.copy2(ROOT / 'tests/workloads' / name, folder / name)
    (folder/'foundation.py').write_text('''indicator("Intentionally partial native recipe", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Change 1", None)
''',encoding='utf-8')
    result = reporter.workload_report(tmp_path, "foundation", set(), True)
    assert result["status"] == "measured"
    assert result["executedCallbackPlotCalls"]["Change 1"]["calls"] > 0
    lead = result["unmappedOutputScopeLeads"]["ROC 1"]
    assert lead["batchMethodCandidates"] == ["roc"]
    assert lead["undeclaredIncrementalMethodCandidates"] == ["roc"]
    assert "ROC 1" in result["unmappedOutputColumns"]
