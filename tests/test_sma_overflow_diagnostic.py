"""Keep finite-input native overflow gaps and independently witnessed masks visible."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sma_overflow_diagnostic", ROOT / "scripts/sma_overflow_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_finite_exact_means_do_not_override_native_missing_states(report):
    assert report["inputCellsVerified"] == 192
    assert report["nativeStateGuardCellsVerified"] == 1440
    assert report["pythonPineSafeControls"] == dict(cells=192, differences=0)
    assert report["finiteExactMeanNativeMissing"] == 135
    assert report["fullySmallTailNativeMissing"] == 33
    assert report["canonicalNativeOutputs"] == 12 and report["excludedControls"] == 20
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    for case in report["missingProfiles"]:
        assert case["nativeMissingAfterFullWindow"] == (0 if case["profile"] == "mixed" else 25 - case["period"])


@pytest.mark.parametrize("callback", (False, True))
def test_every_original_native_output_and_missing_mask_enters_comparison(callback):
    _, reporter = diagnostic._modules(ROOT)
    result = reporter.workload_report(ROOT, "sma_finite_overflow", dict(reporter.WORKLOADS)["sma_finite_overflow"], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 12 and len(result["inputOrControlColumns"]) == 20
    assert result["comparisonTolerance"] == 1e-8
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 288
    assert sum(c["counts"]["differences"] for c in result["columns"].values()) == 135
    assert sum(c["counts"]["missingDifferences"] for c in result["columns"].values()) == 135
    assert sum(c["counts"]["bothMissingCells"] for c in result["columns"].values()) == 12
    for profile in diagnostic.PROFILES:
        assert result["columns"]["Native1 " + profile]["counts"]["differences"] == 0


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_independent_recipe_inputs_never_read_native_results(suffix):
    folder = ROOT / "tests/workloads"
    source = (folder / ("sma_finite_overflow" + suffix)).read_text(encoding="utf-8")
    assert "tradingview" not in source and "read_text" not in source and "Safe" not in source
    function, = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "inputs"]
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert names <= {"large", "i", "float", "dict"}
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-finite-inputs", "exec"), namespace)
    capture = json.loads((folder / "sma_finite_overflow.tradingview.json").read_text(encoding="utf-8"))
    for index, row in enumerate(capture["rows"]):
        supplied = namespace["inputs"](index)
        assert supplied == diagnostic.input_profiles(index)
        for profile, value in supplied.items():
            assert row["values"][capture["columns"].index("Input " + profile)] == value


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "rehash_mask", "rehash_input",
                                      "rehash_helper", "rehash_native1", "qualification", "order"))
def test_corrupted_and_consistently_rehashed_evidence_fails_independent_checks(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "sma_arithmetic_diagnostic"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for name in ("sma_finite_overflow", "sma_overflow_state_guard"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    name = "sma_overflow_state_guard" if mutation in ("logs", "json", "rehash_mask", "qualification") else "sma_finite_overflow"
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    if mutation in ("source", "logs"):
        path = folder / (name + (".pine" if mutation == "source" else ".tradingview.txt"))
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        if mutation == "json":
            capture["rows"][1]["values"][0] = 42.
        elif mutation == "qualification":
            capture["diagnosticOnly"] = False
        elif mutation == "order":
            capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
        else:
            field, value = {"rehash_mask": ("IsNa Native2 recovery", 0.),
                            "rehash_input": ("Input recovery", 42.),
                            "rehash_helper": ("Safe2 recovery", 42.),
                            "rehash_native1": ("Native1 recovery", 42.)}[mutation]
            column = capture["columns"].index(field)
            capture["rows"][8]["values"][column] = value
            log_path = folder / (name + ".tradingview.txt")
            lines = log_path.read_text(encoding="utf-8").splitlines()
            pieces = lines[8].split("|")
            pieces[column+2] = str(value)
            lines[8] = "|".join(pieces)
            log = "\n".join(lines) + "\n"
            log_path.write_text(log, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(log.encode()).hexdigest()
        path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
