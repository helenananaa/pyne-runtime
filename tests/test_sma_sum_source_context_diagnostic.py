"""Preserve expression-context differences and sampled native-history boundaries."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sma_sum_context", ROOT / "scripts/sma_sum_source_context_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
NAMES = diagnostic.ISOLATED + (diagnostic.LONG,)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_equal_numeric_inputs_do_not_qualify_equal_native_context(report):
    assert report["isolatedInputCellsVerified"] == 96
    assert report["isolatedStateGuardCellsVerified"] == 288
    assert report["sameNumericInputsEstablishSameNativeContext"] is False
    assert report["constantMissingAfterReadiness"] == report["seriesFiniteAfterReadiness"] == 31
    assert [case["counts"]["differences"] for case in report["isolatedContextComparisons"]] == [31, 31]
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    json.dumps(report, allow_nan=False)


def test_long_native_samples_do_not_claim_contiguous_outputs_or_permanence(report):
    history = report["longHistory"]
    assert history["sampledRows"] == 86 and history["lastSampledBarIndex"] == 25001
    assert history["suppliedObservations"] == 25002
    assert history["nativeMissingOutputCells"] == history["nativeStateGuardCells"] == 344
    assert history["executionCoverage"]["emittedSamples"] == 86
    assert history["executionCoverage"]["lastConfirmedBarIndex"] >= 25001
    assert history["countedAsAdditionalRuntimeAgreement"] is False
    assert [case["comparison"]["counts"]["differences"] for case in history["sampledDirectSmaComparisons"]] == [85, 84]
    assert len(diagnostic.sample_indices()) == len(set(diagnostic.sample_indices())) == 86


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("callback", (False, True))
def test_every_original_native_output_and_mask_enters_comparison(name, callback):
    _, reporter = diagnostic._modules(ROOT)
    result = reporter.workload_report(ROOT, name, dict(reporter.WORKLOADS)[name], callback)
    long = name == diagnostic.LONG
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == (4 if long else 2)
    assert len(result["inputOrControlColumns"]) == (6 if long else 4)
    assert result["comparisonTolerance"] == 1e-8
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == (344 if long else 64)
    assert sum(c["counts"]["activeCells"] for c in result["columns"].values()) == (338 if long else 62)
    assert sum(c["counts"]["differences"] for c in result["columns"].values()) == (338 if long else 31 if name == NAMES[0] else 0)
    if callback:
        assert result["recipeExecutionRoute"]["boundedStepHelperQualified"] is False


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipe_supplies_all_intervening_inputs_independently(name, suffix):
    source = (ROOT / "tests/workloads" / (name + suffix)).read_text(encoding="utf-8")
    assert "tradingview" not in source and "read_text" not in source
    tree = ast.parse(source)
    function, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "input_at"]
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    assert names <= {"i", "float", "large", "half"}
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-supplied-inputs", "exec"), namespace)
    if name == diagnostic.LONG:
        samples, = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "SAMPLE_INDICES" for t in node.targets)]
        assert samples == diagnostic.sample_indices()
        assert [namespace["input_at"](i) for i in range(25002)] == [diagnostic.input_at(i) for i in range(25002)]
    else:
        assert [namespace["input_at"](i) for i in range(32)] == [80000000.0 * (10. ** 300)] * 32


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "qualification", "order", "rehash_input",
                                      "rehash_state", "rehash_branch_sum", "rehash_sample_index", "rehash_long_input",
                                      "rehash_coverage", "rehash_history_formula"))
def test_corrupted_and_rehashed_context_evidence_is_rejected(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "sma_arithmetic_diagnostic"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for name in NAMES:
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    name = diagnostic.LONG if mutation in ("rehash_sample_index", "rehash_long_input", "rehash_coverage", "rehash_history_formula") else (
        NAMES[2] if mutation == "rehash_branch_sum" else NAMES[1])
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    if mutation in ("source", "logs"):
        path = folder / (name + (".pine" if mutation == "source" else ".tradingview.txt"))
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    else:
        if mutation == "json":
            capture["rows"][2]["values"][0] = 42.
        elif mutation == "qualification":
            capture["sourceExpressionClass"] = "constant"
        elif mutation == "order":
            capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
        elif mutation == "rehash_history_formula":
            pine_path = folder / (name + ".pine")
            pine = pine_path.read_text(encoding="utf-8").replace('i < 6 ? large', 'i < 7 ? large')
            pine_path.write_text(pine, encoding="utf-8", newline="\n")
            capture["scriptSha256"] = hashlib.sha256(pine.encode()).hexdigest()
        else:
            log_path = folder / (name + ".tradingview.txt")
            lines = log_path.read_text(encoding="utf-8").splitlines()
            if mutation == "rehash_coverage":
                lines[-1] = re.sub(r'LONG_EXTENDED_COVERAGE49\|\d+', 'LONG_EXTENDED_COVERAGE49|32', lines[-1])
                capture["executionCoverage"]["lastConfirmedBarIndex"] = 32
            else:
                field, value = {"rehash_input": ("Input", 42.), "rehash_state": ("IsNaSum2", 1.),
                                "rehash_branch_sum": ("Sum2", -1.), "rehash_sample_index": ("ActualBarIndex", 42.),
                                "rehash_long_input": ("Input", 42.)}[mutation]
                column = capture["columns"].index(field)
                capture["rows"][2]["values"][column] = value
                pieces = lines[2].split("|")
                pieces[column + 2] = str(value)
                lines[2] = "|".join(pieces)
            raw = "\n".join(lines) + "\n"
            log_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
        path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
