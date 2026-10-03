"""Keep ordered-overflow witnesses and native sum counterexamples reproducible."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sma_update_order_diagnostic", ROOT / "scripts/sma_update_order_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_add_before_remove_is_falsified_without_qualifying_a_replacement(report):
    assert report["inputCellsVerified"] == 192
    assert report["nativeStateGuardCellsVerified"] == 1536
    witnesses = report["addBeforeRemoveFalsification"]
    assert witnesses["cells"] == 4 and witnesses["countedAsRuntimeAgreement"] is False
    assert {item["addThenRemove"]["nonfiniteNumber"] for item in witnesses["witnesses"]} == {
        "positiveInfinity", "negativeInfinity"}
    assert all(item["native"] == item["removeThenAdd"] for item in witnesses["witnesses"])
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    assert len(report["candidateComparisons"]) == 24
    assert sum(len(case["fullySmallWindowMissingIndices"]) for case in report["recoveryMissing"]) == 86
    json.dumps(report, allow_nan=False)


def test_native_sma_sum_bridge_is_not_universal_at_overflow_boundary(report):
    bridge = report["nativeMeanSumBridge"]
    assert bridge["universalIdentityQualified"] is False
    assert bridge["counts"] == dict(cells=384, activeCells=70, matchedActiveCells=8,
                                    bothMissingCells=314, valueDifferences=0, missingDifferences=62, differences=62)
    differing = [case for case in bridge["checks"] if case["comparison"]["counts"]["differences"]]
    assert {(case["profile"], case["period"]) for case in differing} == {("half", 2), ("negativeHalf", 2)}
    assert all(case["comparison"]["counts"]["differences"] == 31 for case in differing)


@pytest.mark.parametrize("callback", (False, True))
def test_all_native_sma_and_sum_outputs_enter_runtime_comparison(callback):
    _, reporter = diagnostic._modules(ROOT)
    result = reporter.workload_report(ROOT, "sma_overflow_update_order", dict(reporter.WORKLOADS)["sma_overflow_update_order"], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 24 and len(result["inputOrControlColumns"]) == 18
    assert result["comparisonTolerance"] == 1e-8
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 768
    assert sum(c["counts"]["differences"] for c in result["columns"].values()) == 654
    assert sum(c["counts"]["missingDifferences"] for c in result["columns"].values()) == 654
    assert sum(c["counts"]["bothMissingCells"] for c in result["columns"].values()) == 36
    if callback:
        route = result["recipeExecutionRoute"]
        assert route["sourceDeclaration"] == "generic_python_full_history_recompute"
        assert route["boundedStepHelperQualified"] is False
    for profile in ("half", "negativeHalf"):
        assert result["columns"]["Native2 " + profile]["counts"]["differences"] == 0
        assert result["columns"]["Sum2 " + profile]["counts"]["differences"] == 31


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipes_generate_inputs_without_reading_native_oracles(suffix):
    source = (ROOT / "tests/workloads" / ("sma_overflow_update_order" + suffix)).read_text(encoding="utf-8")
    assert "tradingview" not in source and "read_text" not in source
    function, = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "inputs"]
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert names <= {"large", "half", "i", "float", "dict"}
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-order-inputs", "exec"), namespace)
    assert [namespace["inputs"](i) for i in range(32)] == [diagnostic.input_profiles(i) for i in range(32)]


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "rehash_input", "rehash_mask",
                                      "rehash_half_invariant", "rehash_sign", "qualification", "order"))
def test_corrupted_and_rehashed_native_evidence_fails(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "sma_arithmetic_diagnostic"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for name in ("sma_overflow_update_order", "sma_overflow_order_guard"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    name = "sma_overflow_order_guard" if mutation in ("logs", "rehash_mask", "rehash_half_invariant", "rehash_sign", "qualification") else "sma_overflow_update_order"
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    if mutation in ("source", "logs"):
        path = folder / (name + (".pine" if mutation == "source" else ".tradingview.txt"))
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        if mutation == "json":
            capture["rows"][2]["values"][0] = 42.
        elif mutation == "qualification":
            capture["diagnosticOnly"] = False
        elif mutation == "order":
            capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
        else:
            field, value = {"rehash_input": ("Input half", 42.),
                            "rehash_mask": ("IsNa Sum2 half", 0.),
                            "rehash_half_invariant": ("HalfInvariant Sum2 half", 1.),
                            "rehash_sign": ("Negative Sum3 negativeRotation", 0.)}[mutation]
            column = capture["columns"].index(field)
            capture["rows"][2]["values"][column] = value
            log_path = folder / (name + ".tradingview.txt")
            lines = log_path.read_text(encoding="utf-8").splitlines()
            pieces = lines[2].split("|")
            pieces[column + 2] = str(value)
            lines[2] = "|".join(pieces)
            raw = "\n".join(lines) + "\n"
            log_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
        path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
