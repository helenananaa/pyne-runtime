"""Guard against misleading native-alignment claims and corrupted evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("official_alignment_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def test_missing_only_rows_do_not_inflate_agreement():
    result = reporter.compare_column([None] * 100 + [2., None, 3.], [None] * 100 + [2., 4., 7.], 1e-8)
    assert result["counts"] == {
        "cells": 103, "activeCells": 3, "matchedActiveCells": 1, "bothMissingCells": 100,
        "valueDifferences": 1, "missingDifferences": 1, "differences": 2,
    }
    assert [point["index"] for point in result["differences"]] == [101, 102]


def test_nonfinite_diagnostic_numbers_remain_distinct_from_missing_and_valid_json():
    raw = dict(values=[1., None, float("inf"), float("-inf"), float("nan")],
               metric=dict(maxAbsoluteError=float("inf")))
    encoded = reporter.json_safe_numbers(raw)
    assert encoded["values"] == [1., None, {"nonfiniteNumber": "positiveInfinity"},
                                 {"nonfiniteNumber": "negativeInfinity"}, {"nonfiniteNumber": "NaN"}]
    assert encoded["metric"]["maxAbsoluteError"] == {"nonfiniteNumber": "positiveInfinity"}
    assert json.loads(json.dumps(encoded, allow_nan=False)) == encoded
    assert raw["values"][2] == float("inf")  # Encoding does not mutate raw evidence.


def test_full_report_retains_overflow_gaps_in_strict_json(assessment):
    assert assessment["schema"] == "pyne.official-alignment-assessment/2"
    decoded = json.loads(json.dumps(assessment, allow_nan=False))
    cases = {case["mode"]: case for case in decoded["workloads"] if case["name"] == "sma_finite_overflow"}
    point, = [point for point in cases["batch"]["columns"]["Native2 positive"]["differences"] if point["index"] == 1]
    assert point["official"] is None and point["pyne"] == {"nonfiniteNumber": "positiveInfinity"}
    direct, = [point for point in cases["incremental"]["columns"]["Native2 positive"]["differences"] if point["index"] == 1]
    assert direct["official"] is None and isinstance(direct["pyne"], float)
    assert direct["pyne"] > 1e308
    assert cases["batch"]["columns"]["Native2 positive"]["counts"]["differences"] == 23


def test_native_expression_context_and_sampled_history_are_not_hidden(assessment):
    context = assessment["nativeSourceExpressionContext"]
    assert context["sameNumericInputsEstablishSameNativeContext"] is False
    assert context["countedAsAdditionalRuntimeAgreement"] is False
    assert context["constantMissingAfterReadiness"] == context["seriesFiniteAfterReadiness"] == 31
    assert context["longHistory"]["sampledRows"] == 86
    assert context["longHistory"]["lastSampledBarIndex"] == 25001
    assert context["longHistory"]["suppliedObservations"] == 25002
    assert context["longHistory"]["executionCoverage"]["lastConfirmedBarIndex"] >= 25001
    cases = [case for case in assessment["workloads"] if case["name"] == "sum_constant_isolated"]
    assert len(cases) == 2 and all(case["columns"]["Sum2"]["counts"]["differences"] == 31 for case in cases)


def test_preselected_overflow_counterexample_does_not_qualify_replacement(assessment):
    diagnostic = assessment["nativeOverflowDiscriminator"]
    assert diagnostic["inputCellsVerified"] == 32
    assert diagnostic["nativeNumericOutputCells"] == diagnostic["nativeStateFlagCells"] == 64
    assert diagnostic["countedAsAdditionalRuntimeAgreement"] is False
    witness = diagnostic["stickyWindowFalsification"]
    assert witness["index"] == 16 and witness["nativeMissing"] == 0
    assert witness["predictedMissing"] == 1 and witness["rejected"] is True
    assert all(c["qualifiedAsRuntimeReplacement"] is False for c in diagnostic["candidateMaskComparisons"])


def test_near_edge_falsifies_both_uniform_guards_without_qualifying_a_period_rule(assessment):
    diagnostic = assessment["nativeNearEdgeGuards"]
    assert diagnostic["inputCellsVerified"] == 128
    assert diagnostic["nativeNumericOutputCells"] == diagnostic["nativeStateFlagCells"] == 256
    assert diagnostic["uniformRemoveAddGuardRejected"] is diagnostic["uniformKahanGuardRejected"] is True
    assert diagnostic["piecewisePeriodGuardQualified"] is False
    assert {w["rejectedModel"] for w in diagnostic["falsificationWitnesses"]} == {"remove_add", "kahan_remove_add"}


def test_isolated_native_recaptures_stay_outside_runtime_parity_totals(assessment):
    diagnostic = assessment["nativeNearEdgeCallIsolation"]
    assert diagnostic["scriptCount"] == 4 and diagnostic["inputCellsVerified"] == 128
    assert diagnostic["nativeNumericRecaptureCells"] == diagnostic["nativeStateRecaptureCells"] == 256
    assert diagnostic["numericRecaptureDifferences"] == diagnostic["stateRecaptureDifferences"] == 0
    assert diagnostic["combinedCallInteractionRequiredForTheseWitnesses"] is False
    assert diagnostic["countedAsAdditionalRuntimeAgreement"] is False
    assert diagnostic["universalSourceContextInvarianceProved"] is diagnostic["replacementAccumulatorQualified"] is False
    assert all("sma_near_edge_isolated" not in case["name"] for case in assessment["workloads"])


def test_recursive_state_holdout_counts_all_outputs_and_missing_positions(assessment):
    diagnostic = assessment["nativeRecursiveStateInputs"]
    assert diagnostic["inputCellsVerified"] == 192 and diagnostic["nativeNumericOutputCells"] == 2880
    assert diagnostic["countedAsAdditionalRuntimeAgreement"] is False
    cases = [case for case in assessment["workloads"] if case["name"] == "recursive_state_holdout"]
    assert len(cases) == 2 and {case["mode"] for case in cases} == {"batch", "incremental"}
    for case in cases:
        assert len(case["columns"]) == 45 and not case["unmappedOutputColumns"]
        assert sum(column["counts"]["differences"] for column in case["columns"].values()) == 0
        assert sum(column["counts"]["cells"] for column in case["columns"].values()) == 2880


def test_matrix_rejection_witnesses_stay_outside_numeric_denominator(assessment):
    checks = assessment['nativeMatrixDimensionErrorChecks']
    assert len(checks) == 6
    assert {check['name'] for check in checks} == {'product', 'sum', 'diff'}
    assert {check['mode'] for check in checks} == {'batch', 'incremental'}
    assert all(not check['errorPresenceDifference'] and not check['pyneSucceeded'] for check in checks)
    assert all('atomicity' in check['qualification'] for check in checks)


def test_rectangular_matrix_native_numeric_denominator(assessment):
    cases = [case for case in assessment['workloads'] if case['name'] == 'matrix_rectangular_products']
    assert len(cases) == 2
    for case in cases:
        assert case['unmappedOutputColumns'] == [] and len(case['columns']) == 36
        counts = {key: sum(col['counts'][key] for col in case['columns'].values())
                  for key in ('cells', 'activeCells', 'bothMissingCells', 'differences')}
        assert counts == {'cells': 864, 'activeCells': 526, 'bothMissingCells': 338, 'differences': 0}


def test_tolerance_and_length_are_explicit():
    result = reporter.compare_column([1.0], [1.0 + 5e-9], 1e-8)
    assert result["counts"]["differences"] == 0
    # Native logs carry ten decimal places; transport carries eight. Rounding
    # both independently at a half-way value must not create a false failure.
    assert reporter.compare_column([326.622258865], [326.62225887], 1e-8)["counts"]["differences"] == 0
    with pytest.raises(ValueError):
        reporter.compare_column([1.], [], 1e-8)


@pytest.mark.parametrize("name", [name for name, _ in reporter.WORKLOADS])
def test_registered_evidence_is_verified_against_raw_logs(name):
    folder = ROOT / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, name, capture)
    corrupt = copy.deepcopy(capture)
    corrupt["rows"][0]["values"][0] = 999999.
    with pytest.raises(ValueError, match="differ from raw"):
        reporter.verify_evidence(folder, name, corrupt)
    corrupt = copy.deepcopy(capture)
    corrupt["logSha256"] = "0" * 64
    with pytest.raises(ValueError, match="identity mismatch"):
        reporter.verify_evidence(folder, name, corrupt)


@pytest.fixture(scope="module")
def assessment():
    return reporter.build_report()


def test_startup_reference_columns_and_dynamic_plots_are_counted(assessment):
    cases = {(case["name"], case["mode"]): case for case in assessment["workloads"]}
    extrema = cases["extrema_order", "batch"]["columns"]
    assert extrema["Highest ties"]["counts"]["cells"] == 32  # startup included
    assert extrema["Highest ties"]["counts"]["differences"] == 0
    percentiles = [column for title, column in extrema.items() if title.startswith(("Nearest", "Linear"))]
    assert percentiles and all(column["counts"]["cells"] == 32 for column in percentiles)
    assert all(column["counts"]["differences"] == 0 for column in percentiles)
    pivot = cases["pivot_isolated_confirmation", "batch"]["columns"]
    assert pivot["Pivot high repeated"]["counts"]["cells"] == 32
    assert pivot["Pivot high repeated"]["counts"]["differences"] == 0
    assert pivot["Rising holes"]["counts"]["differences"] == 0
    callback = cases["pivot_isolated_confirmation", "incremental"]
    assert callback["unmappedOutputColumns"] == []
    for title in ("Rising holes", "Rising native"):
        assert callback["columns"][title]["counts"]["cells"] == 32
        assert callback["columns"][title]["counts"]["differences"] == 0
    assert callback["recipeExecutionRoute"]["boundedStepHelperQualified"] is False


def test_oca_full_timeline_measures_trigger_bar_visibility(assessment):
    """Settled holdings cannot conceal a wrong intermediate native state."""
    cases = {case["mode"]: case for case in assessment["workloads"] if case["name"] == "oca_timing"}
    for case in cases.values():
        assert case["comparisonTolerance"] == 0
        assert case["unmappedOutputColumns"] == []
        assert len(case["columns"]) == 22
        assert sum(column["counts"]["cells"] for column in case["columns"].values()) == 88
    assert all(not column["differences"] for column in cases["incremental"]["columns"].values())
    batch = cases["batch"]["columns"]
    assert sum(column["counts"]["differences"] for column in batch.values()) == 0
    assert batch["position"]["counts"]["matchedActiveCells"] == 4
    assert batch["openCount"]["counts"]["matchedActiveCells"] == 4
    assert "oca_timing" not in assessment["unmeasuredNativeWorkloads"]


def test_oca_bar_mapping_rejects_misaligned_native_timestamps():
    capture = json.loads((ROOT / "tests/workloads/oca_timing.tradingview.json").read_text())
    assert reporter._bars("oca_timing", capture) == capture["bars"]
    corrupt = copy.deepcopy(capture)
    corrupt["bars"][1]["time"] += 1
    with pytest.raises(ValueError, match="timestamps"):
        reporter._bars("oca_timing", corrupt)


def test_previously_omitted_native_workloads_are_complete_without_hiding_startup(assessment):
    # Retained native-to-native arithmetic diagnostics have no Pyne recipes.
    # Keep them visible as unmeasured; formula matches never inflate parity.
    assert assessment["unmeasuredNativeWorkloads"] == [
        "correlation_reduction_order", "legacy_dmi_wrapper_discriminator", "sma_history_sources",
        "sma_near_edge_isolated_case0", "sma_near_edge_isolated_case1",
        "sma_near_edge_isolated_case2", "sma_near_edge_isolated_case3", "sma_overflow_mask_holdout",
        "sma_overflow_order_guard", "sma_overflow_state_guard",
        "sum_history_prefix_holdout",
        "variance_source_operations",
    ]
    masks = assessment["nativeOverflowStateMasks"]
    assert masks["inputCellsVerified"] == 288 and masks["nativeStateMaskCells"] == 2304
    assert masks["nativeNumericOutputCells"] == 0
    assert masks["countedAsAdditionalRuntimeAgreement"] is False
    assert masks["explicitSeriesSourceContext"]["seriesKeywordEstablishesEquivalentContext"] is False
    assert masks["kahanNumericHoldout"]["differences"] == 947
    assert all(c["qualifiedAsRuntimeReplacement"] is False for c in masks["candidateComparisons"])
    folder = ROOT / "tests/workloads"
    diagnostic = json.loads((folder / "correlation_reduction_order.tradingview.json").read_text())
    reporter.verify_evidence(folder, "correlation_reduction_order", diagnostic)
    assert diagnostic["diagnosticOnly"] is True
    history = json.loads((folder / "sma_history_sources.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, "sma_history_sources", history)
    assert history["diagnosticOnly"] is True
    cases = {(case["name"], case["mode"]): case for case in assessment["workloads"]}
    for mode in ("batch", "incremental"):
        weighted = cases["wma_gap_confirmation", mode]
        assert len(weighted["columns"]) == 6 and weighted["unmappedOutputColumns"] == []
        assert all(not col["differences"] for col in weighted["columns"].values())
        oscillator = cases["oscillator_formula", mode]
        assert len(oscillator["columns"]) == 12 and oscillator["unmappedOutputColumns"] == []
        assert sum(col["counts"]["differences"] for col in oscillator["columns"].values()) == 0
        version5 = cases["stoch_transitions_v5", mode]
        assert len(version5["columns"]) == 6 and version5["unmappedOutputColumns"] == []
        assert sum(col["counts"]["differences"] for col in version5["columns"].values()) == 0
    assert assessment["acceptance"]["smallDifferenceProved"] is False


def test_scope_denominator_comes_from_declarations_and_keeps_boolean_pipe_examples(assessment):
    inventory = assessment["declaredScopeInventory"]
    assert inventory["declaredCategoryCount"] == 31
    assert inventory["nativeComparableCategoryCount"] == 28
    assert inventory["pythonProductCategoryCount"] == 3
    categories = {entry["category"]: entry for entry in inventory["entries"]}
    assert "|" in categories["Series comparisons"]["declaredLimits"]
    assert categories["Collections"]["status"] == "Supported"
    assert categories["Strategy events"]["status"] == "Partial"
    assert all(entry["fullBehaviorAndParameterCoverageProved"] is False
               for entry in inventory["entries"] if entry["nativeComparisonApplicable"])
    assert {entry["category"] for entry in inventory["entries"] if not entry["nativeComparisonApplicable"]} == {
        "CLI", "Public package API", "Capability and trace contracts"}
    assert inventory["coverageFraction"] is None


@pytest.mark.parametrize("domain, fixtures, plots, points", (("strategy",27,168,497), ("request",21,240,1753)))
def test_imported_domain_captures_do_not_dilute_full_matrix_denominator(assessment, domain, fixtures, plots, points):
    diagnostic = assessment[f"{domain}CaptureFamilyDiagnostics"]
    counts = diagnostic["comparison"]["counts"]
    assert counts["captured_cases" if domain == "strategy" else "captured_fixtures"] == fixtures
    assert (counts["plots"], counts["points"]) == (plots, points)
    assert counts["differences"] == 0 and counts["runtime_errors"] == 0
    assert diagnostic["includedInMeasuredWorkloadTotals"] is False
    assert diagnostic["assertionFilter"] == "all"
    assert len(diagnostic["inventory"]) == fixtures
    assert all(len(entry["importedRecordSha256"]) == 64 for entry in diagnostic["inventory"])
    assert not any(entry["hasNativeScriptAndLogHashes"] for entry in diagnostic["inventory"])
    full_matrix_active = sum(column["counts"]["activeCells"]
                             for workload in assessment["workloads"]
                             for column in workload.get("columns", {}).values())
    assert assessment["measuredWorkloadTotals"]["activeCells"] == full_matrix_active


def test_recipe_presence_and_selected_cells_cannot_pass_goal_acceptance(assessment):
    corpus = assessment["workloadCoverage"]
    assert corpus["registeredRecipeCount"] == len(reporter.WORKLOADS)
    assert corpus["registeredModeCount"] == corpus["registeredRecipeCount"] * 2
    assert corpus["registeredModeCount"] == corpus["measuredModeCount"] + corpus["unmappedModeCount"]
    assert corpus["measuredModeCount"] == corpus["fullyMappedMeasuredModeCount"] + corpus["partiallyMappedMeasuredModeCount"]
    assert corpus["unmappedModeCount"] == 0 and corpus["partiallyMappedMeasuredModeCount"] == 0
    assert corpus["fullyMappedMeasuredModeCount"] == corpus["registeredModeCount"]
    assert all(not case["unmappedOutputColumns"] for case in assessment["workloads"])
    surface = assessment["taSurface"]
    assert surface["batchMethodCount"] == len(reporter.BATCH_TA_CAPABILITIES)
    assert set(surface["methodsPresentInCaptureRecipes"]) | set(surface["methodsWithoutRecipeEvidence"]) == set(surface["declaredBatchMethods"])
    counts = assessment["measuredWorkloadTotals"]
    assert counts["activeCells"] == counts["matchedActiveCells"] + counts["differences"]
    assert counts["cells"] == counts["activeCells"] + counts["bothMissingCells"]
    assert assessment["acceptance"] == {
        "smallDifferenceProved": False, "goalShouldRemainActive": True,
        "reasons": assessment["acceptance"]["reasons"],
    }


def test_window_holdout_keeps_full_masks_and_imported_conflicts(assessment):
    cases = [case for case in assessment['workloads'] if case['name'] == 'window_readiness_holdout']
    assert len(cases) == 2
    for case in cases:
        assert len(case['columns']) == 125 and case['unmappedOutputColumns'] == []
        assert case['comparisonTolerance'] == 1e-8
        assert sum(c['counts']['cells'] for c in case['columns'].values()) == 8000
        assert all(c['counts']['differences'] == 0 for c in case['columns'].values())
        assert case['columns']['highest base 11']['counts']['bothMissingCells'] == 10
    imported = assessment['taCaptureFamilyDiagnostics']
    assert imported['counts']['points'] == 1353
    assert imported['counts']['differences'] == 144
    assert imported['counts']['unexpected_differences'] == 0
    assert imported['counts']['known_differences'] == 144
    assert assessment['acceptance']['smallDifferenceProved'] is False


def test_acceptance_cli_fails_closed(monkeypatch, assessment):
    monkeypatch.setattr(reporter, "build_report", lambda: assessment)
    assert reporter.main(["--require-small-difference"]) == 1
    assert reporter.main([]) == 0  # diagnostic output alone is not a quality pass


def test_unused_calls_and_reassigned_series_do_not_claim_output_coverage():
    lineage = reporter.recipe_output_lineage('''
unused = ta.sma(close, 99)
value = ta.ema(close, 3)
plot(value, "EMA")
value = close
plot(value, "Raw")
upper, middle, lower = ta.keltner(3, 1.5)
plot(upper, "KC upper")
plot(lower, "KC lower")
''')
    assert lineage["outputCandidates"] == {
        "EMA": ["ema"], "Raw": [], "KC upper": ["keltner"], "KC lower": ["keltner"],
    }
    assert "ta.sma(close, 99)" in lineage["callExpressions"]["sma"]
    dynamic = reporter.recipe_output_lineage('''
for name in names:
    plot(ta.sma(close, 3), name)
''')
    assert dynamic["outputCandidates"] == {}


def test_method_evidence_discloses_real_comparison_without_claiming_parameter_coverage(assessment):
    evidence = assessment["taMethodEvidence"]
    assert set(evidence) == set(reporter.BATCH_TA_CAPABILITIES)
    assert all(not method["parameterCoverageProved"] for method in evidence.values())
    context = next(reference for reference in evidence["keltner"]["workloadReferences"]
                   if reference["workload"] == "context_foundation" and reference["mode"] == "batch")
    columns = context["candidateMeasuredColumns"]
    assert columns["Native KC upper"]["counts"]["differences"] == 0
    assert columns["Keltner upper"]["counts"]["differences"] == 0
    assert columns["Native KC upper"]["numericErrorSummary"]["maxAbsoluteError"] < 1e-8
    assert "ta.keltner(3, 1.5)" in context["callExpressions"]
    assert any("width_smoothing='atr'" in call for call in context["callExpressions"])
    # The existing dynamic callback plots remain explicitly unresolved.
    callbacks = [reference for method in evidence.values() for reference in method["workloadReferences"]
                 if reference["mode"] == "incremental"]
    assert callbacks and all(not reference["outputAssociationResolved"] for reference in callbacks)


def test_numeric_impact_keeps_missing_zero_and_sign_changes_distinct():
    result = reporter.compare_column([0., -2., 100., None], [3., 2., 99., 5.], 1e-8)
    assert result["numericErrorSummary"] == {
        "comparableCells": 3, "maxAbsoluteError": 4., "sumAbsoluteError": 8.,
        "maxRelativeErrorForNonzeroOfficial": 2.,
        "zeroOfficialNonzeroObservedCells": 1, "signDisagreementCells": 1,
    }
    assert result["counts"]["missingDifferences"] == 1
    missing = reporter.compare_column([None], [0.], 1e-8)
    assert missing["numericErrorSummary"]["comparableCells"] == 0
    assert missing["numericErrorSummary"]["maxAbsoluteError"] is None
    assert missing["numericErrorSummary"]["maxRelativeErrorForNonzeroOfficial"] is None


def test_raw_comparison_preserves_tolerance_and_discloses_output_rounding():
    within = reporter.compare_column([326.622258865], [326.62225887], 1e-8)
    assert within["counts"]["differences"] == 0
    tighter = reporter.compare_column([12.6666666667], [12.66666667], 1e-9)
    assert tighter["counts"]["valueDifferences"] == 1


def test_rejected_native_formula_is_disclosed_and_all_percentile_outputs_are_measured(assessment):
    hypothesis, = assessment["nativeHypothesisChecks"]
    assert hypothesis["rejected"] is True
    assert hypothesis["counts"]["cells"] == 3680
    assert hypothesis["counts"]["differences"] == 188
    matrix = next(case for case in assessment["workloads"]
                  if case["name"] == "percentile_insertion_matrix" and case["mode"] == "batch")
    assert len(matrix["columns"]) == 230
    assert matrix["unmappedOutputColumns"] == []
    assert all(not title.startswith("Formula ") for title in matrix["columns"])
    assert all(col["counts"]["differences"] == 0 for col in matrix["columns"].values())
    for mode in ("batch", "incremental"):
        holdout = next(case for case in assessment["workloads"]
                       if case["name"] == "percentile_state_holdout" and case["mode"] == mode)
        assert len(holdout["columns"]) == 168
        assert holdout["unmappedOutputColumns"] == []
        assert sum(column["counts"]["cells"] for column in holdout["columns"].values()) == 16128
        assert all(column["counts"]["differences"] == 0 for column in holdout["columns"].values())
