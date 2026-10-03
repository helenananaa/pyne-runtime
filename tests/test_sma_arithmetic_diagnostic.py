"""Preserve native counterexamples and keep formula controls out of agreement."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sma_diagnostic", ROOT / "scripts/sma_arithmetic_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_older_exact_fit_cannot_qualify_independent_counterexamples(report):
    assert report["inputCellsVerified"] == 1152
    assert report["pythonPineControls"] == dict(cells=3456, differences=0)
    assert report["olderFiniteFit"]["cells"] == 768
    assert len(report["olderFiniteFit"]["profiles"]) == 9
    assert report["olderFiniteFit"]["differences"] == 0
    assert {model["name"]: model["differences"] for model in report["independentHoldout"]} == {
        "Candidate2": 458, "Candidate3": 489, "Pair2": 438,
    }
    assert all(model["cells"] == 1152 for model in report["independentHoldout"])
    assert len(report["nativeMeanSumDivision"]["checks"]) == 40
    assert report["nativeMeanSumDivision"]["cells"] == 2560
    assert report["nativeMeanSumDivision"]["differences"] == 0
    assert report["canonicalNativeOutputs"] == 24
    assert report["excludedInputAndFormulaControls"] == 48
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"


@pytest.mark.parametrize("callback,differences", ((False, 994), (True, 966)))
def test_all_native_outputs_enter_runtime_comparison_without_formula_controls(callback, differences):
    reporter = diagnostic._reporter(ROOT)
    result = reporter.workload_report(ROOT, diagnostic.NAME, dict(reporter.WORKLOADS)[diagnostic.NAME], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 24 and len(result["inputOrControlColumns"]) == 48
    assert all(title.startswith(("Native2 ", "Native3 ")) for title in result["columns"])
    assert result["comparisonTolerance"] == 1e-8
    assert sum(column["counts"]["cells"] for column in result["columns"].values()) == 2304
    assert sum(column["counts"]["differences"] for column in result["columns"].values()) == differences
    for title in ("Native2 empty", "Native3 empty"):
        assert result["columns"][title]["counts"]["bothMissingCells"] == 96
        if callback:
            assert result["executedCallbackPlotCalls"][title] == dict(calls=96, missingCalls=96)


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipe_generates_only_supplied_inputs_without_reading_native_results(suffix):
    folder = ROOT / "tests/workloads"
    source = (folder / (diagnostic.NAME + suffix)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    function, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inputs"]
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert names <= {"i", "base", "power", "dict", "float"}
    assert "read_text" not in source and "tradingview" not in source and "Candidate" not in source
    generated = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-inputs", "exec"), generated)
    capture = json.loads((folder / (diagnostic.NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    for index, row in enumerate(capture["rows"]):
        inputs = generated["inputs"](index)
        assert inputs == diagnostic.input_profiles(index)
        assert len(inputs) == 12
        for title, value in inputs.items():
            assert value == row["values"][capture["columns"].index("Input " + title)]


@pytest.mark.parametrize("mutation", ("source", "logs", "row", "order", "duplicate_column"))
def test_diagnostic_rejects_corrupted_native_provenance(tmp_path, mutation):
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/official_alignment_report.py", tmp_path / "scripts/official_alignment_report.py")
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
        shutil.copyfile(ROOT / "tests/workloads" / (diagnostic.NAME + suffix), folder / (diagnostic.NAME + suffix))
    if mutation in ("source", "logs"):
        path = folder / (diagnostic.NAME + (".pine" if mutation == "source" else ".tradingview.txt"))
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        path = folder / (diagnostic.NAME + ".tradingview.json")
        capture = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "row":
            capture["rows"][0]["values"][0] += 1
        elif mutation == "order":
            capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
        else:
            capture["columns"][1] = capture["columns"][0]
        path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)


def test_python_candidate_must_match_separately_executed_pine_control(monkeypatch):
    original = diagnostic.kahan_remove_add

    def altered_model(values, period):
        return [None if value is None else value + 1 for value in original(values, period)]

    monkeypatch.setattr(diagnostic, "kahan_remove_add", altered_model)
    with pytest.raises(ValueError, match="separately executed Pine control"):
        diagnostic.build_diagnostic()


def test_new_native_history_recapture_cannot_inflate_runtime_agreement(report):
    checks = report["nativeSourceHistoryChecks"]
    assert checks["countedAsRuntimeAgreement"] is False
    for name, cells in (("inputAndHistoryIdentity", 800), ("independentPairArithmetic", 320),
                        ("nativeMeanSumDivision", 320), ("independentNativeRecapture", 320),
                        ("nativeDyadicScaling", 160)):
        assert checks[name]["cells"] == cells
        assert checks[name]["differences"] == 0
    assert report["acceptanceProved"] is False


@pytest.mark.parametrize("field", ("Input power", "History1 prefill", "Array2 holes"))
def test_rehashed_native_input_tamper_is_rejected_by_independent_history(tmp_path, field):
    # Internally consistent raw/JSON edits must still fail independent input checks.
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    name = "sma_history_sources"
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
        shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    column = capture["columns"].index(field)
    index = 15
    capture["rows"][index]["values"][column] = 42.
    log_path = folder / (name + ".tradingview.txt")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    pieces = lines[index].split("|")
    pieces[column+2] = "42."
    lines[index] = "|".join(pieces)
    log = "\n".join(lines) + "\n"
    log_path.write_text(log, encoding="utf-8", newline="\n")
    capture["logSha256"] = hashlib.sha256(log.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    reporter = diagnostic._reporter(ROOT)
    reporter.verify_evidence(folder, name, capture)  # Raw identity alone is insufficient.
    _, previous = diagnostic._load(ROOT, reporter, diagnostic.NAME)
    with pytest.raises(ValueError, match="Independent source/history input differs"):
        diagnostic.history_source_checks(tmp_path, reporter, previous)
