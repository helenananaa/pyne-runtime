"""Protect native explanation, counterexamples and the numeric denominator."""
from __future__ import annotations

import importlib.util
import ast
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("correlation_arithmetic_diagnostic", ROOT / "scripts/correlation_arithmetic_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_native_formula_explanations_preserve_rejected_alternatives(report):
    assert report["diagnosticCells"] == 512
    assert report["formulaDifferenceCounts"] == {
        "RawFormula": 91, "StdevFormula": 91, "ZeroGuardRaw": 0,
        "ZeroGuardStdev": 0, "ScaledRawFormula": 146, "ZeroGuardScaledRaw": 95,
    }
    assert report["candidateRuntimeQualified"] is False
    assert len(report["formulaCases"]) == 8


def test_logged_operands_recompose_and_products_are_binary64(report):
    checks = report["operandRoundtripChecks"] + report["primitiveProductChecks"]
    assert len(checks) == 27
    assert sum(check["comparison"]["counts"]["cells"] for check in checks) == 1728
    assert all(check["comparison"]["counts"]["differences"] == 0 for check in checks)
    assert diagnostic._array([1_000_000_000_000]).dtype == np.float64


@pytest.mark.parametrize("source", ("xx", "xy", "yy"))
@pytest.mark.parametrize("method", ("Newest", "Oldest", "Kahan", "Neumaier", "Paired"))
@pytest.mark.parametrize("period", (3, 7))
def test_native_sma_reduction_hypotheses_have_retained_counterexamples(report, source, method, period):
    title = f"{method} {source} {period}"
    check = next(check for check in report["nativeReductionChecks"] if check["title"] == title)
    assert check["comparison"]["counts"]["cells"] == 64
    assert check["comparison"]["counts"]["differences"] > 0


@pytest.mark.parametrize("callback", (False, True))
def test_only_independently_executed_runtime_correlation_enters_agreement(callback):
    reporter = diagnostic._reporter(ROOT)
    name = "correlation_arithmetic_decomposition"
    controls = dict(reporter.WORKLOADS)[name]
    result = reporter.workload_report(ROOT, name, controls, callback)
    assert len(controls) == 198
    assert len(result["columns"]) == 8
    assert result["unmappedOutputColumns"] == []
    counts = {key: sum(column["counts"][key] for column in result["columns"].values())
              for key in ("cells", "activeCells", "bothMissingCells", "valueDifferences", "missingDifferences", "differences")}
    assert counts == dict(cells=512, activeCells=480, bothMissingCells=32,
                         valueDifferences=135, missingDifferences=182, differences=317)
    assert result["comparisonTolerance"] == 1e-8
    if callback:
        assert result["recipeExecutionRoute"]["boundedStepHelperQualified"] is False
        assert result["recipeExecutionRoute"]["undeclaredDirectIncrementalMethodCandidates"] == ["correlation"]


def test_inputs_do_not_depend_on_expected_native_results():
    reporter = diagnostic._reporter(ROOT)
    name = "correlation_arithmetic_decomposition"
    folder = ROOT / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text())
    source = (folder / f"{name}_batch.py").read_text()
    reporter.verify_evidence(folder, name, capture)
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "sources")
    namespace = {"np": np}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<independent input generator>", "exec"), namespace)
    values = namespace["sources"](64)
    for index, title in enumerate(capture["columns"][:6]):
        expected = diagnostic._array([row["values"][index] for row in capture["rows"]])
        np.testing.assert_array_equal(values[title], expected)


def test_new_probe_reproduces_previous_native_history():
    folder = ROOT / "tests/workloads"
    new = json.loads((folder / "correlation_arithmetic_decomposition.tradingview.json").read_text())
    old = json.loads((folder / "correlation_window_holdout.tradingview.json").read_text())
    reporter = diagnostic._reporter(ROOT)
    repeated = 0
    for title in new["columns"]:
        if title.startswith("Native ") and title in old["columns"]:
            expected = [row["values"][old["columns"].index(title)] for row in old["rows"]]
            actual = [row["values"][new["columns"].index(title)] for row in new["rows"][:32]]
            assert reporter.compare_column(expected, actual, 1e-8)["counts"]["differences"] == 0
            repeated += 1
    assert repeated == 7
