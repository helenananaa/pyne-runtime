"""Retain preselected native falsification and independently supplied recipes."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("overflow_discriminator", ROOT / "scripts/sma_overflow_discriminator_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_native_finite_witness_rejects_sticky_window_recomputation(report):
    assert report["inputCellsVerified"] == 32
    assert report["nativeNumericOutputCells"] == report["nativeStateFlagCells"] == 64
    witness = report["stickyWindowFalsification"]
    assert witness["index"] == 16 and witness["period"] == 7
    assert witness["nativeSum"] == 5 * (2. ** 1021)
    assert witness["nativeSma"] == witness["nativeSum"] / 7
    assert witness["predictedMissing"] == 1 and witness["nativeMissing"] == 0
    assert witness["rejected"] is True and witness["countedAsAdditionalRuntimeAgreement"] is False
    differences = {model: sum(c["differences"] for c in report["candidateMaskComparisons"] if c["model"] == model)
                   for model in {c["model"] for c in report["candidateMaskComparisons"]}}
    assert differences == dict(remove_add=0, add_remove=0, window_recompute=14,
        sticky_window_recompute=2, exact_window_sum=12, kahan_remove_add=0)
    assert all(c["qualifiedAsRuntimeReplacement"] is False for c in report["candidateMaskComparisons"])
    assert report["nativeMeanSumBridge"]["counts"]["differences"] == 0
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    json.dumps(report, allow_nan=False)


def test_selected_recipe_reproduces_candidate_only_seed_and_trial():
    unit = 2. ** 1021
    vocabulary = (0., .25, -.5, unit, -unit, 2 * unit, -2 * unit,
                  3 * unit, -3 * unit, 4 * unit, -4 * unit)
    generator = random.Random(2026100351)
    selected = None
    for _ in range(3):
        selected = [vocabulary[generator.randrange(len(vocabulary))] for _ in range(32)]
    assert selected == [diagnostic.input_at(i) for i in range(32)]
    models, _, _ = diagnostic._modules(ROOT)
    carry = models.candidate_masks(selected, 7, "remove_add")
    sticky = models.candidate_masks(selected, 7, "sticky_window_recompute")
    assert next(i for i in range(32) if carry[i] != sticky[i]) == 16


@pytest.mark.parametrize("callback", (False, True))
def test_new_numeric_outputs_are_measured_in_both_modes(callback):
    _, _, reporter = diagnostic._modules(ROOT)
    result = reporter.workload_report(ROOT, diagnostic.NAME, dict(reporter.WORKLOADS)[diagnostic.NAME], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == {"Native7", "Sum7"}
    assert set(result["inputOrControlColumns"]) == {"Input", "IsNaNative7", "IsNaSum7"}
    assert all(c["counts"] == dict(cells=32, activeCells=26, matchedActiveCells=11,
        bothMissingCells=6, valueDifferences=0, missingDifferences=15, differences=15)
        for c in result["columns"].values())
    if callback:
        assert result["recipeExecutionRoute"]["sourceDeclaration"] == "generic_python_full_history_recompute"
        assert result["recipeExecutionRoute"]["boundedStepHelperQualified"] is False


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipes_generate_inputs_independently_of_native_outputs(suffix):
    source = (ROOT / "tests/workloads" / (diagnostic.NAME + suffix)).read_text(encoding="utf-8")
    assert "tradingview" not in source and "read_text" not in source
    function, = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "input_at"]
    names = {n.id for n in ast.walk(function) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert names <= {"i", "index", "coefficients", "small"}
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-discriminator-input", "exec"), namespace)
    assert [namespace["input_at"](i) for i in range(32)] == [diagnostic.input_at(i) for i in range(32)]


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "qualification", "order",
                                      "rehash_input", "rehash_state", "rehash_formula"))
def test_corrupted_or_rehashed_native_discriminator_fails(tmp_path, mutation):
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
    elif mutation == "rehash_formula":
        changed = folder / (diagnostic.NAME + ".pine")
        source = changed.read_text(encoding="utf-8").replace("math.pow(2., 1021)", "math.pow(2., 1020)")
        changed.write_text(source, encoding="utf-8", newline="\n")
        capture["scriptSha256"] = hashlib.sha256(source.encode()).hexdigest()
    else:
        title, value = {"json": ("Input", 42.), "rehash_input": ("Input", 42.),
                        "rehash_state": ("IsNaNative7", 1.)}[mutation]
        index = capture["columns"].index(title)
        capture["rows"][16]["values"][index] = value
        if mutation != "json":
            raw_path = folder / (diagnostic.NAME + ".tradingview.txt")
            lines = raw_path.read_text(encoding="utf-8").splitlines()
            parts = lines[16].split("|")
            parts[index + 2] = str(value)
            lines[16] = "|".join(parts)
            raw = "\n".join(lines) + "\n"
            raw_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
