"""Guard against replacing numerical semantics with falsified overflow state."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("near_edge_diagnostic", ROOT / "scripts/sma_near_edge_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_two_uniform_guards_have_native_counterexamples_in_both_directions(report):
    assert report["inputCellsVerified"] == 128
    assert report["nativeNumericOutputCells"] == report["nativeStateFlagCells"] == 256
    assert report["candidateStateDifferenceTotals"] == dict(remove_add=40, add_remove=126,
        window_recompute=36, sticky_window_recompute=6, exact_window_sum=36, kahan_remove_add=42)
    witnesses = report["falsificationWitnesses"]
    assert [(w["period"], w["index"], w["nativeMissing"], w["rejectedModel"]) for w in witnesses] == [
        (7, 30, 1, "kahan_remove_add"), (7, 13, 0, "kahan_remove_add"),
        (3, 13, 0, "remove_add"), (3, 14, 1, "remove_add")]
    assert witnesses[1]["nativeSum"] == witnesses[2]["nativeSum"] == float.fromhex("0x1.fffffffffffffp+1023")
    assert report["uniformRemoveAddGuardRejected"] is report["uniformKahanGuardRejected"] is True
    assert report["piecewisePeriodGuardQualified"] is False
    assert all(w["countedAsAdditionalRuntimeAgreement"] is False for w in witnesses)
    assert all(c["qualifiedAsRuntimeReplacement"] is False for c in report["candidateStateComparisons"])
    assert all(c["comparison"]["counts"]["differences"] == 0 for c in report["nativeMeanSumBridge"])
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("callback,values,matched", ((False, 98, 86), (True, 105, 79)))
def test_all_eight_native_outputs_enter_both_execution_modes(callback, values, matched):
    _, _, reporter = diagnostic._modules(ROOT)
    result = reporter.workload_report(ROOT, diagnostic.NAME, dict(reporter.WORKLOADS)[diagnostic.NAME], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 8 and len(result["inputOrControlColumns"]) == 12
    totals = {key: sum(c["counts"][key] for c in result["columns"].values())
              for key in next(iter(result["columns"].values()))["counts"]}
    assert totals == dict(cells=256, activeCells=224, matchedActiveCells=matched,
        bothMissingCells=32, valueDifferences=values, missingDifferences=40, differences=values+40)
    if callback:
        assert result["recipeExecutionRoute"]["sourceDeclaration"] == "generic_python_full_history_recompute"
        assert result["recipeExecutionRoute"]["boundedStepHelperQualified"] is False


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipes_reconstruct_candidate_only_trials_without_reading_native_outputs(suffix):
    source = (ROOT / "tests/workloads" / (diagnostic.NAME + suffix)).read_text(encoding="utf-8")
    assert "tradingview" not in source and "read_text" not in source
    function, = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "inputs"]
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert names <= {"i", "unit", "ulp", "vocabulary", "codes", "n", "row", "enumerate"}
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-near-edge-input", "exec"), namespace)
    supplied = diagnostic.supplied_inputs()
    assert [namespace["inputs"](i) for i in range(32)] == [{name: values[i] for name, values in supplied.items()} for i in range(32)]


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "qualification", "order",
                                      "rehash_input", "rehash_state", "rehash_formula", "rehash_period"))
def test_altered_and_rehashed_native_near_edge_evidence_fails(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "sma_arithmetic_diagnostic", "sma_overflow_mask_diagnostic"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
        shutil.copyfile(ROOT / "tests/workloads" / (diagnostic.NAME + suffix), folder / (diagnostic.NAME + suffix))
    path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    if mutation in ("source", "logs"):
        changed = folder / (diagnostic.NAME + (".pine" if mutation == "source" else ".tradingview.txt"))
        changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif mutation == "qualification":
        capture["diagnosticOnly"] = True
    elif mutation == "order":
        capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
    elif mutation in ("rehash_formula", "rehash_period"):
        changed = folder / (diagnostic.NAME + ".pine")
        source = changed.read_text(encoding="utf-8")
        source = source.replace("math.pow(2., 969)", "math.pow(2., 968)") if mutation == "rehash_formula" else source.replace("ta.sma(src0, 7)", "ta.sma(src0, 3)")
        changed.write_text(source, encoding="utf-8", newline="\n")
        capture["scriptSha256"] = hashlib.sha256(source.encode()).hexdigest()
    else:
        title, value = {"json": ("Input case0", 42.), "rehash_input": ("Input case0", 42.),
                        "rehash_state": ("IsNaNative case0", 0.)}[mutation]
        column = capture["columns"].index(title)
        capture["rows"][30]["values"][column] = value
        if mutation != "json":
            raw_path = folder / (diagnostic.NAME + ".tradingview.txt")
            lines = raw_path.read_text(encoding="utf-8").splitlines()
            pieces = lines[30].split("|")
            pieces[column + 2] = str(value)
            lines[30] = "|".join(pieces)
            raw = "\n".join(lines) + "\n"
            raw_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
