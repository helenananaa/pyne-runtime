"""Native startup evidence and disclosure must remain exact and auditable."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("legacy_context_diagnostic", ROOT / "scripts/legacy_capture_context_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_every_context_difference_has_native_v5_and_v6_witnesses(report):
    assert report["witnessedDifferences"] == report["disclosedDifferences"] == 32
    assert report["nativeBuiltinWitnesses"] == 22
    assert report["preparedHelperWitnesses"] == report["helperOriginZeroWitnesses"] == 10
    assert report["inputCellsVerifiedPerPineVersion"] == 1200
    assert report["pineVersions"] == [6, 5]
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    for witness in report["witnesses"]:
        assert witness["nativeLeadingIndex"] == witness["originalInputIndex"] + 16
        assert witness["pyne"] is None


@pytest.mark.parametrize("name", diagnostic.NAMES)
@pytest.mark.parametrize("callback", (False, True))
def test_all_native_outputs_and_initial_masks_enter_unchanged_comparison(name, callback):
    reporter = diagnostic._module(ROOT, "official_alignment_report")
    result = reporter.workload_report(ROOT, name, dict(reporter.WORKLOADS)[name], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 16
    assert len(result["inputOrControlColumns"]) == 36
    assert result["comparisonTolerance"] == 1e-8
    assert sum(column["counts"]["cells"] for column in result["columns"].values()) == 640
    assert sum(column["counts"]["differences"] for column in result["columns"].values()) == 0
    if callback:
        assert result["recipeExecutionRoute"]["sourceDeclaration"] == "generic_python_full_history_recompute"
        assert result["recipeExecutionRoute"]["boundedStepHelperQualified"] is False


def test_python_input_generation_reproduces_only_supplied_inputs():
    folder = ROOT / "tests/workloads"
    capture = json.loads((folder / f"{diagnostic.NAMES[0]}.tradingview.json").read_text(encoding="utf-8"))
    source = (folder / f"{diagnostic.NAMES[0]}_batch.py").read_text(encoding="utf-8")
    assert "read_text" not in source and "tradingview" not in source
    metadata = capture["inputContext"]["inputColumns"]
    for title, item in metadata.items():
        short = {"close": "c", "high": "h", "low": "l"}[item["field"]]
        context = "leading" if item["offset"] else "origin"
        source += f"\nplot({item['case']}_{context}_{short}, {title!r})"
    reporter = diagnostic._module(ROOT, "official_alignment_report")
    bars = reporter._bars(diagnostic.NAMES[0], capture)
    result = pn.run(source, bars, executor_mode="inline")
    assert result.ok, result.error
    series = {line["name"]: {p["time"]: p["value"] for p in line["data"]} for line in result.lines}
    for title in metadata:
        index = capture["columns"].index(title)
        expected = {bar["time"]: row["values"][index] for bar, row in zip(bars, capture["rows"])
                    if row["values"][index] is not None}
        assert series.get(title, {}) == expected


@pytest.mark.parametrize("mutation", ("baseline", "expected", "annotation", "missing_annotation", "native_row"))
def test_diagnostic_rejects_changed_provenance_outputs_and_witnesses(tmp_path, mutation):
    shutil.copytree(ROOT / "tests/golden/legacy_capture_context_baseline",
                    tmp_path / "tests/golden/legacy_capture_context_baseline")
    baseline = tmp_path / "tests/golden/legacy_capture_context_baseline"
    for path in baseline.glob("*.json"):
        shutil.copyfile(ROOT / "tests/golden" / path.name, tmp_path / "tests/golden" / path.name)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "ta_capture_diff"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    (tmp_path / "tests/workloads").mkdir()
    for name in diagnostic.NAMES:
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), tmp_path / "tests/workloads" / (name + suffix))
    path = tmp_path / "tests/golden/ta_core_indicators.json"
    if mutation == "baseline":
        path = baseline / path.name
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        if mutation == "native_row":
            path = tmp_path / "tests/workloads" / (diagnostic.NAMES[0] + ".tradingview.json")
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "expected":
            fixture["external_capture"]["series"]["Highest 3"][0]["value"] += 1
        elif mutation == "annotation":
            fixture["external_capture"]["known_differences"][0]["contextWitness"]["nativeLeading"] += 1
        elif mutation == "missing_annotation":
            fixture["external_capture"]["known_differences"].pop()
        else:
            fixture["rows"][0]["values"][0] += 1
        path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
