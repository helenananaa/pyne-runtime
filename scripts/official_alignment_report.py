"""Measure native differences without treating recipe presence as qualification."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import tomllib
from unittest.mock import patch

import pyne_runtime as pn
from pyne_runtime.capabilities import BATCH_TA_CAPABILITIES, INCREMENTAL_TA_CAPABILITIES
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION
from pyne_runtime.incremental.context import IncrementalContext

ROOT = Path(__file__).resolve().parents[1]
_DIRECTION_CASES = (("holes", 3), ("empty", 3), ("leading", 3), ("alternating", 3),
                    ("flat", 3), ("descending", 3), ("empty", 1), ("alternating", 1),
                    ("holes", 7), ("leading", 7))
_DIRECTION_INPUTS = {"holes", "empty", "leading", "alternating", "flat", "descending"}
_CORRELATION_DIAGNOSTIC_CASES = (
    ("source", "source", 1), ("source", "source", 2), ("source", "source", 3), ("source", "source", 5),
    ("holes", "source", 3), ("holes", "holes", 3), ("holes", "other", 3), ("leading", "source", 3),
    ("flat", "source", 3), ("source", "holes", 3),
)
_CORRELATION_HOLDOUT_PAIRS = (("base", "base"), ("holes", "base"), ("holes", "other"), ("holes", "shifted"),
    ("leading", "base"), ("flat", "base"), ("hugeA", "hugeB"), ("hugeHole", "hugeB"))
WORKLOADS = (
    ("variance_independent_holdout", {f"Input {profile}" for profile in ("base", "high", "negative", "regime")} | {
        f"{field} {profile} {period}" for field in ("Mean", "MeanXX")
        for profile in ("base", "high", "negative", "regime") for period in (2, 3, 7)}),
    ("recursive_composition_ohlcv_holdout", {"time", "open", "high", "low", "close", "volume"}),
    ("recursive_composition_weekly_holdout", {"time", "open", "high", "low", "close", "volume"}),
    ("recursive_state_holdout", {f"Input {profile}" for profile in ("leading", "flat_runs", "regime")}),
    ("sma_near_edge_discriminator", {f"{field} case{n}" for field in ("Input", "IsNaNative", "IsNaSum") for n in range(4)}),
    ("sma_overflow_discriminator", {"Input", "IsNaNative7", "IsNaSum7"}),
    *((name, {"Input", "IsNaNative2", "IsNaSum2", "HalfInvariantSum2"})
      for name in ("sum_constant_isolated", "sum_series_isolated", "sum_branch_isolated")),
    ("sma_long_overflow_recovery_extended", {
        "ActualBarIndex", "Input", "IsNaNative2", "IsNaNative3", "IsNaSum2", "IsNaSum3",
    }),
    ("sma_overflow_update_order", {
        f"{field} {profile}" for field in ("Input", "IsNa2", "IsNa3")
        for profile in ("half", "negativeHalf", "rotation", "negativeRotation", "recovery", "gapRecovery")
    }),
    ("sma_finite_overflow", {
        f"{field} {profile}" for field in ("Input", "Sum2", "Sum3", "Safe2", "Safe3")
        for profile in ("positive", "negative", "mixed", "recovery")
    }),
    ("sma_period_two_independent_holdout", {
        f"{field} {profile}" for field in ("Input", "Candidate2", "Candidate3", "Pair2")
        for profile in ("base", "offset", "power", "prefill", "negative", "mixed", "holes",
                        "leading", "empty", "singleGap", "alternate", "regime")
    }),
    ("legacy_masked_history_context_v5", {
        f"Input {case} {context} {field}" for case in ("core", "oscillator", "context", "remaining", "warmup")
        for context in ("origin", "leading") for field in ("close", "high", "low")
    } | {
        f"Legacy helper {case} {context} WPR {period}"
        for case, period in (("oscillator", 3), ("oscillator", 6), ("remaining", 4))
        for context in ("origin", "leading")
    }),
    ("legacy_masked_history_context", {
        f"Input {case} {context} {field}" for case in ("core", "oscillator", "context", "remaining", "warmup")
        for context in ("origin", "leading") for field in ("close", "high", "low")
    } | {
        f"Legacy helper {case} {context} WPR {period}"
        for case, period in (("oscillator", 3), ("oscillator", 6), ("remaining", 4))
        for context in ("origin", "leading")
    }),
    ("sma_history_arithmetic", {"base", "power", "prefill", "negativePrefill", "holes", "prefillHoles"} | {
        f"{method} power {p}" for method in ("AddRemove", "RemoveAdd", "Delta", "Kahan") for p in (3, 7, 11)}),
    ("correlation_arithmetic_decomposition", {"base", "holes", "shifted", "hugeA", "hugeB", "hugeHole"} | {
        f"{field} {a} {b} {p}"
        for a, b, p in (("base", "base", 3), ("holes", "shifted", 3), ("hugeA", "hugeB", 2),
                        ("hugeA", "hugeB", 3), ("hugeA", "hugeB", 7), ("hugeHole", "hugeB", 3),
                        ("hugeHole", "hugeB", 7), ("hugeA", "hugeA", 3))
        for field in ("MeanA", "MeanB", "MeanXY", "MeanXX", "MeanYY", "Numerator", "RawVarianceA",
                      "RawVarianceB", "StdevA", "StdevB", "RawFormula", "StdevFormula", "ZeroGuardRaw",
                      "ZeroGuardStdev", "SumA", "SumB", "SumXY", "SumXX", "SumYY", "ScaledNumerator",
                      "ScaledVarianceA", "ScaledVarianceB", "ScaledRawFormula", "ZeroGuardScaledRaw")}),
    ("window_readiness_holdout", {"base", "holes", "leading", "flat", "missing"}),
    ("numeric_output_precision", {"tiny", "fractional", "negative", "holes", "leading", "flat", "missing", "large"}),
    ("dispersion_single_observation", {"base", "holes", "leading", "flat", "missing", "fractional", "huge", "hugeHole"}),
    ("correlation_missing_diagnostic", {"source", "holes", "other", "leading", "flat"} | {
        f"Independent moment formula {a} {b} {p}" for a, b, p in _CORRELATION_DIAGNOSTIC_CASES}),
    ("correlation_window_holdout", {"base", "holes", "other", "shifted", "leading", "flat", "hugeA", "hugeB", "hugeHole"} | {
        f"Independent moment formula {a} {b} {p}" for a, b in _CORRELATION_HOLDOUT_PAIRS for p in (1, 2, 3, 7)}),
    ("matrix_rectangular_products", {"Case"}),
    ("matrix_empty_shapes", {"Case"}),
    ("collection_string_extraction", {"Case"}),
    ("array_search_fill_join", {"Case"}),
    ("map_scalar_mutation", {"Case"}),
    ("array_slice_reference", {"Case"}),
    ("matrix_missing_reshape", {"Case", "Scalar", *(f"Original {i}" for i in range(4)), *(f"Other {i}" for i in range(4))}),
    ("array_missing_sort", {"Case", *(f"Original {i}" for i in range(5))}),
    *((f"strategy_pending_pyramiding_{case}", {"time", "open", "high", "low", "close", "volume"})
      for case in ("stop_same_tick", "limit_same_tick", "stop_limit_same_tick", "stop_existing_full",
                   "stop_staggered", "market_same_tick_control", "stop_seed_same_tick",
                   "stop_favorable_same_tick", "stop_seed_favorable_same_tick")),
    *((f"strategy_pending_pyramiding_{case}", {"time", "open", "high", "low", "close", "volume"})
      for case in ("stop_limit_wait_369", "stop_limit_wait_300", "stop_limit_never_activated",
                   "stop_limit_gap_then_limit", "stop_limit_short_prior_high", "stop_limit_short_activated_close",
                   "stop_limit_long_prior_low", "stop_limit_short_later_high",
                   "stop_limit_update_activated", "stop_limit_cancel_resubmit", "stop_limit_repeat_identical",
                   "stop_limit_to_market", "market_to_stop_limit_same_tick", "market_to_stop_limit_same_tick_p2",
                   "stop_limit_order_repeat", "stop_limit_cancel_direction", "stop_limit_order_update_activated",
                   "stop_limit_order_oca_reassign", "stop_limit_order_oca_same_group", "stop_limit_order_oca_new_id",
                   "market_update_same_tick", "market_update_same_tick_p2",
                   "stop_limit_to_market_same_tick", "stop_limit_to_market_same_tick_p2")),
    ("wma_gap_confirmation", {"holes", "filled"}),
    ("oscillator_formula", {"holes"}),
    ("stoch_transitions_v5", set()),
    ("oca_timing", {"time"}),
    ("strategy_pyramiding_0", {"time", "open", "high", "low", "close", "volume"}),
    ("strategy_pyramiding_1", {"time", "open", "high", "low", "close", "volume"}),
    ("strategy_pyramiding_2", {"time", "open", "high", "low", "close", "volume"}),
    ("strategy_pyramiding_3", {"time", "open", "high", "low", "close", "volume"}),
    ("strategy_pyramiding_orders_confirmation", {"time", "open", "high", "low", "close", "volume"}),
    ("percentile_state_holdout", {"base", "holes", "ties", "leading", "empty"}),
    ("percentile_history_context", {"baseline", "ascending", "descending", "leading"}),
    ("keltner_width_matrix", {"time", "open", "high", "low", "close", "volume", "holes", "leading", "empty"} | {
        f"Formula KC case{case} {side}" for case in range(15) for side in ("upper", "middle", "lower")}),
    ("percentile_insertion_matrix", {"holes", "leading", "ties", "alternating", "multiple", "empty"} | {
        f"Formula Linear {name} {period} {pct}"
        for name, periods in (("holes", (1, 2, 3, 4, 7)), ("ties", (1, 2, 3, 4, 7)),
                              ("alternating", (1, 2, 3, 4, 7)), ("multiple", (1, 2, 3, 4, 7)),
                              ("leading", (3, 4)), ("empty", (4,)))
        for period in periods for pct in (0, 25, 50, 75, 100)}),
    ("percentile_missing_sort", {"source", "holes", "leading", "empty"} | {
        f"Sorted {order} {index}" for order in ("newest", "oldest") for index in range(4)}),
    ("percentile_confirmation", {"source", "holes"}),
    ("context_foundation", {"time", "open", "high", "low", "close", "volume", "volume holes"}),
    ("cross_confirmation", {"source", "holes", "leading", "empty", "other", "other holes", "zeros"} | {
        f"Formula {method} case {case}" for case in range(6) for method in ("cross", "crossover", "crossunder")}),
    ("foundation", {"source", "holes", "leading", "empty", "other", "other holes", "zeros"}),
    ("weighted_boundaries", {"source", "holes", "leading"}),
    ("oscillator_flat", {"source", "holes"}),
    ("stoch_transitions", set()),
    ("extrema_order", {"source", "holes", "ties", "leading"}),
    ("extrema_tie_confirmation", {"gap"}),
    ("ema_rsi", {"source", "leading", "holes"}),
    ("rolling_statistics", {"source", "holes", "leading"}),
    ("smoothing", set()),
    ("trend_volume", {"time", "open", "high", "low", "close", "volume", "VWMA formula"}),
    ("ta_chain", {"source"}),
    ("conditions_pivot", {"source", "holes", "ties"}),
    ("pivot_isolated_confirmation", {"left high", "right high", "ties", "wave", "holes",
                                     "Rising strict formula", "Rising record formula"}),
    ("pivot_formula_confirmation", {"source", "Formula high 3 2", "Formula low 3 2",
                                    "Formula high 0 2", "Formula low 0 2",
                                    "Formula high 2 0", "Formula low 2 0"}),
    ("direction_missing", _DIRECTION_INPUTS | {
        f"Neutral {side} {name} {period}" for name, period in _DIRECTION_CASES for side in ("rising", "falling")}),
    ("direction_transition_confirmation", _DIRECTION_INPUTS | {
        f"Formula {side} {name} {period}" for name, period in _DIRECTION_CASES for side in ("rising", "falling")}),
)


def recipe_methods(source: str) -> set[str]:
    """Presence in source is an evidence lead, never behavior qualification."""
    methods = set()
    declared = set(BATCH_TA_CAPABILITIES)
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id in declared:
            methods.add(fn.id)
        elif isinstance(fn, ast.Attribute) and fn.attr in declared:
            owner = fn.value
            if (isinstance(owner, ast.Name) and owner.id == "ta") or (
                isinstance(owner, ast.Attribute) and owner.attr == "ta"
            ):
                methods.add(fn.attr)
    return methods


def recipe_execution_route(source: str) -> dict | None:
    """Disclose an explicit recipe declaration without certifying streaming cost."""
    tree = ast.parse(source)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                and target.id == 'NATIVE_RECIPE_EXECUTION_ROUTE' for target in node.targets)):
            if not isinstance(node.value, ast.Constant) or node.value.value != 'generic_python_full_history_recompute':
                raise ValueError('Invalid native recipe execution-route declaration')
            candidates = sorted({call.func.attr for call in ast.walk(tree)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name) and call.func.value.id == 'module'
                and call.func.attr in BATCH_TA_CAPABILITIES})
            return dict(sourceDeclaration=node.value.value, boundedStepHelperQualified=False,
                        batchMethodCandidates=candidates,
                        undeclaredDirectIncrementalMethodCandidates=sorted(set(candidates)-set(INCREMENTAL_TA_CAPABILITIES)),
                        qualification='Executed numeric comparisons qualify this Python callback recipe; the source declaration does not prove a direct incremental API or bounded streaming cost')
    return None


def plot_names(source: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "plot":
            args = node.args[1:]
        elif isinstance(fn, ast.Attribute) and fn.attr == "plot":
            args = node.args[:1]
        else:
            continue
        names.update(arg.value for arg in args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return names


def recipe_output_lineage(source: str) -> dict:
    """Conservative static leads; never certify dynamic Python dataflow."""
    declared = set(BATCH_TA_CAPABILITIES)
    bindings: dict[str, set[str]] = {}
    outputs: dict[str, set[str]] = {}
    sites: dict[str, set[str]] = {}

    def dependencies(node):
        result = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                result.update(bindings.get(child.id, set()))
            if not isinstance(child, ast.Call):
                continue
            fn = child.func
            method = None
            if isinstance(fn, ast.Name) and fn.id in declared:
                method = fn.id
            elif isinstance(fn, ast.Attribute) and fn.attr in declared:
                owner = fn.value
                if (isinstance(owner, ast.Name) and owner.id == "ta") or (
                    isinstance(owner, ast.Attribute) and owner.attr == "ta"
                ):
                    method = fn.attr
            if method:
                result.add(method)
                sites.setdefault(method, set()).add(ast.unparse(child))
        return result

    for statement in ast.parse(source).body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            if statement.value is None:
                continue
            methods = dependencies(statement.value)
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                        bindings[name.id] = set(methods)
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            methods = dependencies(call)
            fn = call.func
            if isinstance(fn, ast.Name) and fn.id == "plot" and len(call.args) >= 2:
                title = call.args[1]
                if isinstance(title, ast.Constant) and isinstance(title.value, str):
                    outputs.setdefault(title.value, set()).update(methods)
        # Loops, functions, aliases, mutation and dynamic titles are deliberately
        # unresolved: ordinary Python execution cannot be proven by this scan.
    return {"outputCandidates": {key: sorted(value) for key, value in outputs.items()},
            "callExpressions": {key: sorted(value) for key, value in sites.items()},
            "qualification": "static_dependency_candidates_only_no_dynamic_dataflow_proof"}


def compare_column(expected, actual, tolerance):
    """Count startup/reference differences, with missing-only cells separated."""
    counts = {"cells": len(expected), "activeCells": 0, "matchedActiveCells": 0,
              "bothMissingCells": 0, "valueDifferences": 0, "missingDifferences": 0}
    differences = []
    numeric = {"comparableCells": 0, "maxAbsoluteError": None, "sumAbsoluteError": 0.0,
               "maxRelativeErrorForNonzeroOfficial": None,
               "zeroOfficialNonzeroObservedCells": 0, "signDisagreementCells": 0}
    for index, (wanted, observed) in enumerate(zip(expected, actual, strict=True)):
        if wanted is not None and observed is not None:
            error = abs(wanted - observed)
            numeric["comparableCells"] += 1
            numeric["maxAbsoluteError"] = max(numeric["maxAbsoluteError"] or 0.0, error)
            numeric["sumAbsoluteError"] += error
            if wanted != 0:
                numeric["maxRelativeErrorForNonzeroOfficial"] = max(
                    numeric["maxRelativeErrorForNonzeroOfficial"] or 0.0, error / abs(wanted))
            elif observed != 0:
                numeric["zeroOfficialNonzeroObservedCells"] += 1
            if wanted * observed < 0:
                numeric["signDisagreementCells"] += 1
        if wanted is None and observed is None:
            counts["bothMissingCells"] += 1
            continue
        counts["activeCells"] += 1
        if wanted is None or observed is None:
            kind = "missing"
            counts["missingDifferences"] += 1
        elif not math.isclose(wanted, observed, rel_tol=0, abs_tol=tolerance):
            kind = "value"
            counts["valueDifferences"] += 1
        else:
            counts["matchedActiveCells"] += 1
            continue
        differences.append({"index": index, "kind": kind, "official": wanted, "pyne": observed})
    counts["differences"] = counts["valueDifferences"] + counts["missingDifferences"]
    return {"counts": counts, "differences": differences, "numericErrorSummary": numeric}


def verify_evidence(folder: Path, name: str, capture: dict) -> None:
    texts = {}
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        raw = (folder / f"{name}.{suffix}").read_text(encoding="utf-8")
        texts[suffix] = raw
        if hashlib.sha256(raw.encode()).hexdigest() != capture[key]:
            raise ValueError(f"Official evidence identity mismatch: {name}.{suffix}")
    rows = capture["rows"]
    if [row["index"] for row in rows] != list(range(len(rows))):
        raise ValueError(f"Incomplete or reordered official rows: {name}")
    if any(len(row["values"]) != len(capture["columns"]) for row in rows):
        raise ValueError(f"Incomplete official columns: {name}")
    missing_token = capture.get("missingValueToken", "NaN")
    if missing_token not in ("NaN", "NA"):
        raise ValueError(f"Unsupported official missing-value token: {name}")
    parsed = []
    for match in re.finditer(r"(PYNE_[A-Z_][A-Z0-9_]*)\|(\d+)\|([^;\r\n]+)", texts["tradingview.txt"]):
        if match[1] not in texts["pine"]:
            raise ValueError(f"Official log marker absent from Pine source: {name}")
        parsed.append({"index": int(match[2]),
                       "values": [None if value == missing_token else float(value)
                                  for value in match[3].split("|")]})
    if not parsed or parsed != rows:
        raise ValueError(f"Official JSON rows differ from raw Pine Logs: {name}")


def json_safe_numbers(value):
    """Retain nonfinite evidence explicitly without emitting nonstandard JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        kind = "NaN" if math.isnan(value) else "positiveInfinity" if value > 0 else "negativeInfinity"
        return {"nonfiniteNumber": kind}
    if isinstance(value, dict):
        return {key: json_safe_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_numbers(item) for item in value]
    return value


def native_source_expression_context_check(root):
    """Qualify native source context separately from raw output agreement."""
    spec = importlib.util.spec_from_file_location("native_source_context_diagnostic", root / "scripts/sma_sum_source_context_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    result = diagnostic.build_diagnostic(root)
    history = result["longHistory"]
    return dict(isolatedInputCellsVerified=result["isolatedInputCellsVerified"],
                isolatedStateGuardCellsVerified=result["isolatedStateGuardCellsVerified"],
                sameNumericInputsEstablishSameNativeContext=False,
                constantMissingAfterReadiness=result["constantMissingAfterReadiness"],
                seriesFiniteAfterReadiness=result["seriesFiniteAfterReadiness"],
                sourceExpressionQualification=result["sourceExpressionQualification"],
                longHistory=dict(sampledRows=history["sampledRows"],
                    lastSampledBarIndex=history["lastSampledBarIndex"],
                    suppliedObservations=history["suppliedObservations"],
                    executionCoverage=history["executionCoverage"],
                    qualification=history["qualification"]),
                countedAsAdditionalRuntimeAgreement=False,
                qualification="Constant-expression gaps remain in raw counts. Source expression context and sampled-history boundaries must be independently qualified; compiler emulation and permanent-poison rules are not established.")


def native_overflow_state_mask_check(root):
    """Keep independently observed state masks outside numeric agreement totals."""
    spec = importlib.util.spec_from_file_location("native_mask_diagnostic", root / "scripts/sma_overflow_mask_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    result = diagnostic.build_diagnostic(root)
    return dict(inputCellsVerified=result["inputCellsVerified"],
                nativeStateMaskCells=result["nativeStateMaskCells"],
                nativeNumericOutputCells=0, countedAsAdditionalRuntimeAgreement=False,
                explicitSeriesSourceContext=result["explicitSeriesSourceContext"],
                candidateComparisons=[{key: item[key] for key in
                    ("model", "cells", "differences", "qualifiedAsRuntimeReplacement")}
                    for item in result["candidateComparisons"]],
                kahanNumericHoldout=result["kahanNumericHoldout"]["counts"],
                qualification=result["qualification"])


def native_overflow_discriminator_check(root):
    """Disclose an independent counterexample without qualifying another kernel."""
    spec = importlib.util.spec_from_file_location("native_discriminator_diagnostic", root / "scripts/sma_overflow_discriminator_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    result = diagnostic.build_diagnostic(root)
    return dict(inputCellsVerified=result["inputCellsVerified"],
                nativeNumericOutputCells=result["nativeNumericOutputCells"],
                nativeStateFlagCells=result["nativeStateFlagCells"],
                selection=result["selection"],
                stickyWindowFalsification=result["stickyWindowFalsification"],
                candidateMaskComparisons=result["candidateMaskComparisons"],
                countedAsAdditionalRuntimeAgreement=False, qualification=result["qualification"])


def native_near_edge_check(root):
    """Retain guard falsifications separately from measured numerical agreement."""
    spec = importlib.util.spec_from_file_location("native_near_edge_diagnostic", root / "scripts/sma_near_edge_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    result = diagnostic.build_diagnostic(root)
    return {key: result[key] for key in ("inputCellsVerified", "nativeNumericOutputCells", "nativeStateFlagCells",
        "selection", "candidateStateDifferenceTotals", "falsificationWitnesses",
        "uniformRemoveAddGuardRejected", "uniformKahanGuardRejected", "piecewisePeriodGuardQualified", "qualification")}


def native_near_edge_isolation_check(root):
    """Expose repeated-input native recaptures outside runtime agreement totals."""
    spec = importlib.util.spec_from_file_location("native_near_edge_isolation", root / "scripts/sma_near_edge_isolation_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    result = diagnostic.build_diagnostic(root)
    return {key: result[key] for key in ("scriptCount", "inputCellsVerified", "nativeNumericRecaptureCells",
        "nativeStateRecaptureCells", "independentInputDifferences", "numericRecaptureDifferences",
        "stateRecaptureDifferences", "combinedCallInteractionRequiredForTheseWitnesses",
        "countedAsAdditionalRuntimeAgreement", "universalSourceContextInvarianceProved",
        "replacementAccumulatorQualified", "qualification")}


def native_variance_input_check(root):
    spec = importlib.util.spec_from_file_location("native_variance_inputs", root / "scripts/variance_native_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def native_variance_source_operations_check(root):
    spec = importlib.util.spec_from_file_location("native_variance_operations", root / "scripts/variance_source_operations_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def native_sum_history_prefix_check(root):
    spec = importlib.util.spec_from_file_location("native_sum_history_prefix", root / "scripts/sum_history_prefix_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def native_recursive_state_input_check(root):
    """Validate held-out native inputs without adding comparison cells."""
    spec = importlib.util.spec_from_file_location("native_recursive_state_inputs", root / "scripts/recursive_state_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def native_recursive_composition_input_check(root):
    spec = importlib.util.spec_from_file_location("recursive_composition_inputs", root / "scripts/recursive_composition_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def native_legacy_dmi_wrapper_check(root):
    spec = importlib.util.spec_from_file_location("legacy_dmi_wrapper", root / "scripts/legacy_dmi_wrapper_diagnostic.py")
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    return diagnostic.build_diagnostic(root)


def _bars(name, capture):
    if name == "oca_timing":
        bars = capture["bars"]
        if len(bars) != len(capture["rows"]) or any(
            bar["time"] != row["values"][0] for bar, row in zip(bars, capture["rows"], strict=True)
        ):
            raise ValueError("OCA native bar timestamps differ from log rows")
        return [dict(bar) for bar in bars]
    bars = []
    sequence = (1, 4, 2, 5, 3, 6, 2, 4)
    for i, row in enumerate(capture["rows"]):
        if name in ("trend_volume", "context_foundation", "keltner_width_matrix", "recursive_composition_ohlcv_holdout", "recursive_composition_weekly_holdout") or name.startswith(("strategy_pyramiding_", "strategy_pending_pyramiding_")):
            bars.append(dict(zip(("time", "open", "high", "low", "close", "volume"), row["values"][:6], strict=True)))
            continue
        close = row["values"][0] if name in ("ta_chain", "percentile_state_holdout") else sequence[i % 8]
        bars.append(dict(time=i * (10 if name == "ta_chain" else 60), open=close,
                         high=close + 1, low=close - 1, close=close, volume=10))
    return bars


def _native_join_text_checks(root: Path, name: str, marker: str, column_count: int, cell_count: int, description: str) -> dict:
    """Compare emitted label text exactly, independently of numeric plot cells."""
    folder = root / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    verify_evidence(folder, name, capture)
    native = {}
    raw = (folder / f"{name}.tradingview.txt").read_text(encoding="utf-8")
    for match in re.finditer(rf"{re.escape(marker)}\|(\d+)\|([^|]+)\|([^;\r\n]*);", raw):
        key = (int(match[1]), match[2])
        if key in native:
            raise ValueError(f"Duplicate native {description} text cell")
        native[key] = match[3]
    if ([row["index"] for row in capture["textRows"]] != list(range(len(capture["rows"]))) or
            len(set(capture["textColumns"])) != column_count or
            any(len(row["values"]) != column_count for row in capture["textRows"])):
        raise ValueError(f"Incomplete or reordered native {description} text records")
    declared = {(row["index"], title): value for row in capture["textRows"]
                for title, value in zip(capture["textColumns"], row["values"], strict=True)}
    if native != declared or len(native) != cell_count:
        raise ValueError(f"Native {description} JSON differs from complete raw text")
    modes = []
    for incremental in (False, True):
        source = (folder / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")
        result = pn.run(source, _bars(name, capture), executor_mode="inline")
        if not result.ok:
            raise RuntimeError(result.error)
        actual = {}
        for label in result.output.get("objects", {}).get("labels", []):
            prefix, index, title, value = label["text"].split("|", 3)
            key = (int(index), title)
            if prefix != "JOIN" or key in actual:
                raise ValueError(f"Invalid or repeated {description} label")
            actual[key] = value
        if set(actual) != set(native):
            raise ValueError(f"Incomplete executed {description} label coverage")
        differences = [{"index": index, "title": title, "official": expected, "pyne": actual[index, title]}
                       for (index, title), expected in native.items() if actual[index, title] != expected]
        modes.append({"mode": "incremental" if incremental else "batch", "cells": len(native),
                      "differenceCount": len(differences), "differences": differences,
                      "recipeSha256": hashlib.sha256(source.encode()).hexdigest()})
    return {"workload": name, "modes": modes,
            "cells": sum(mode["cells"] for mode in modes),
            "differences": sum(mode["differenceCount"] for mode in modes),
            "oracleScriptSha256": capture["scriptSha256"], "oracleLogSha256": capture["logSha256"],
            "qualification": "exact strings from executed labels, separate from numeric cells; fixed types and profiles only"}


def native_array_join_text_checks(root: Path) -> dict:
    return _native_join_text_checks(root, "array_search_fill_join", "TV_ARRAY_JOIN", 4, 128, "array join")


def native_collection_extraction_text_checks(root: Path) -> dict:
    return _native_join_text_checks(root, "collection_string_extraction", "TV_COLLECTION_TEXT", 7, 112, "collection extraction")


def run_with_plot_observations(source: str, bars: list[dict]):
    """Observe successful callback plot calls without changing their results.

    Inline execution and the scoped patch are intentionally sequential. The
    native oracle is never involved in this observation. All-missing callbacks
    can omit a retained curve, so curve presence alone is insufficient evidence
    that a recipe actually invoked its plot.
    """
    observations = {}
    original = IncrementalContext.plot

    def observed_plot(context, name_or_value, value=None, **kwargs):
        original(context, name_or_value, value, **kwargs)
        if context.current_bar is None:
            return
        name = (kwargs.get("title") or name_or_value) if isinstance(name_or_value, str) else (kwargs.get("title") or "plot")
        point_value = value if isinstance(name_or_value, str) else name_or_value
        if point_value is None:
            missing = True
        else:
            try:
                missing = math.isnan(float(point_value))
            except (TypeError, ValueError):
                return  # The public plot rejected this value without creating a point.
        calls = observations.setdefault(str(name), {"calls": 0, "missingCalls": 0})
        calls["calls"] += 1
        calls["missingCalls"] += int(missing)

    with patch.object(IncrementalContext, "plot", observed_plot):
        result = pn.run(source, bars, executor_mode="inline")
    return result, observations


def workload_report(root: Path, name: str, inputs: set[str], incremental: bool):
    folder = root / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    verify_evidence(folder, name, capture)
    script_path = folder / f"{name}{'' if incremental else '_batch'}.py"
    if not script_path.is_file():
        batch_path = folder / f"{name}_batch.py"
        method_leads = recipe_methods(batch_path.read_text(encoding="utf-8")) if batch_path.is_file() else set()
        return {"name": name, "mode": "incremental" if incremental else "batch", "status": "unmapped",
                "unmappedReason": "execution recipe absent; this is not proof of an unsupported behavior",
                "batchMethodCandidates": sorted(method_leads),
                "undeclaredIncrementalMethodCandidates": sorted(method_leads - set(INCREMENTAL_TA_CAPABILITIES)) if incremental else [],
                "scopeQualification": "static recipe leads compared with declared direct APIs; no execution or parameter coverage claim"}
    source = script_path.read_text(encoding="utf-8")
    columns = set(capture["columns"]) - inputs
    result, plot_calls = run_with_plot_observations(source, _bars(name, capture))
    if not result.ok:
        raise RuntimeError(f"{script_path.name}: {result.error}")
    lines = {line["name"]: {point["time"]: point["value"] for point in line["data"]} for line in result.lines}
    names = set(lines) | set(plot_calls)
    mapped = sorted(columns & names)
    batch_path = folder / f"{name}_batch.py"
    batch_lineage = recipe_output_lineage(batch_path.read_text(encoding="utf-8")) if batch_path.is_file() else {"outputCandidates": {}}
    unmapped_leads = {}
    for title in sorted(columns - names):
        candidates = batch_lineage["outputCandidates"].get(title, [])
        unmapped_leads[title] = {"batchMethodCandidates": candidates,
                                 "undeclaredIncrementalMethodCandidates": sorted(set(candidates) - set(INCREMENTAL_TA_CAPABILITIES)) if incremental else [],
                                 "qualification": "static dependency lead, not proof of complete per-output dataflow or capability"}
    time_key = {i: bar["time"] for i, bar in enumerate(_bars(name, capture))}
    comparisons = {}
    for title in mapped:
        column = capture["columns"].index(title)
        expected = [row["values"][column] for row in capture["rows"]]
        actual = [lines.get(title, {}).get(time_key[i]) for i in range(len(expected))]
        # The older OCA capture records integer counts and quantities, so use
        # exact comparison explicitly rather than changing its native metadata.
        tolerance = 0.0 if name == "oca_timing" else capture["tolerance"]
        comparisons[title] = compare_column(expected, actual, tolerance)
    route = recipe_execution_route(source)
    return {"name": name, "mode": "incremental" if incremental else "batch", "status": "measured",
            **({"recipeExecutionRoute": route} if route is not None else {}),
            "recipeMethods": sorted(recipe_methods(source)), "columns": comparisons,
            "staticLineage": recipe_output_lineage(source),
            "inputOrControlColumns": sorted(inputs),
            "unmappedOutputColumns": sorted(columns - names),
            "executedCallbackPlotCalls": plot_calls,
            "outputObservationQualification": "retained curves or successfully executed callback plot calls; static plot mentions are not execution evidence",
            "unmappedOutputScopeLeads": unmapped_leads,
            "comparisonTolerance": 0.0 if name == "oca_timing" else capture["tolerance"],
            "scriptSha256": hashlib.sha256(source.encode()).hexdigest(),
            "oracleScriptSha256": capture["scriptSha256"], "oracleLogSha256": capture["logSha256"]}


def native_percentile_history_check(folder: Path) -> dict:
    """Controlled native outputs isolate history outside identical windows."""
    capture = json.loads((folder / "percentile_history_context.tradingview.json").read_text(encoding="utf-8"))
    verify_evidence(folder, "percentile_history_context", capture)
    sources = ("baseline", "ascending", "descending", "leading")
    source_columns = [capture["columns"].index(name) for name in sources]
    witnesses = []
    compared = 0
    for period in (2, 4, 7):
        for kind in ("Nearest", "Linear"):
            for percentage in (0, 25, 50, 75, 100):
                columns = [capture["columns"].index(f"{kind} {name} {period} {percentage}") for name in sources]
                for index in range(16 + period - 1, len(capture["rows"])):
                    windows = [[row["values"][column] for row in capture["rows"][index-period+1:index+1]]
                               for column in source_columns]
                    if any(window != windows[0] for window in windows[1:]):
                        raise ValueError("Native history control contains unequal windows")
                    values = [capture["rows"][index]["values"][column] for column in columns]
                    compared += 1
                    if any(value != values[0] for value in values[1:]):
                        witnesses.append({"index": index, "method": kind, "period": period,
                                          "percentage": percentage, "identicalWindow": windows[0],
                                          "outputs": dict(zip(sources, values, strict=True))})
    return {"workload": "percentile_history_context", "comparedSameWindowGroups": compared,
            "differingGroups": len(witnesses), "witnesses": witnesses,
            "oracleScriptSha256": capture["scriptSha256"], "oracleLogSha256": capture["logSha256"],
            "qualification": "controlled_native_history_dependency_not_a_replacement_algorithm"}


def imported_capture_diagnostics(root: Path, domain: str) -> dict:
    """Inspect every legacy assertion mode without mixing sparse point counts."""
    spec = importlib.util.spec_from_file_location(f"{domain}_capture_diagnostics", root / f"scripts/{domain}_capture_diff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pattern = module.STRATEGY_FIXTURE_GLOB if domain == "strategy" else module.REQUEST_FIXTURE_GLOB
    paths = sorted((root / "tests/golden").glob(pattern))
    report = module.build_report(paths, set(), "all")
    inventory = []
    for path in paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        cases = fixture.get("cases", []) if domain == "strategy" else [fixture]
        for case in cases:
            capture = case.get("external_capture", {})
            # These are current imported-record hashes, not independently
            # verified hashes of original CSV exports or native Pine source.
            canonical = json.dumps(capture, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            inventory.append({
                "fixture": str(path.relative_to(root)).replace("\\", "/"),
                "case": case.get("name", path.name), "captureStatus": capture.get("status", "missing"),
                "assertion": capture.get("assertion", "parity"),
                "importedRecordSha256": hashlib.sha256(canonical).hexdigest(),
                "recipeSha256": hashlib.sha256(case["script"].encode()).hexdigest(),
                "hasNativeScriptAndLogHashes": bool(capture.get("scriptSha256") and capture.get("logSha256")),
                "originalRawEvidenceVerified": False,
                "notes": capture.get("notes", []),
            })
    return {"comparison": report, "inventory": inventory,
            "countingBasis": "legacy_sparse_plot_points_not_full_bar_output_cells",
            "assertionFilter": "all", "includedInMeasuredWorkloadTotals": False,
            "qualification": "imported_capture_diagnostics_not_original_raw_provenance_or_complete_domain_qualification"}


def declared_scope_inventory(root: Path) -> dict:
    """Use the current product declaration as the scope denominator, not tests."""
    path = root / "docs/reference/pine_like_api_matrix.md"
    raw = path.read_text(encoding="utf-8")
    python_only = {"Public package API", "Capability and trace contracts", "CLI"}
    entries = []
    for line in raw.splitlines():
        if not line.startswith("| "):
            continue
        # Boolean examples contain literal pipes inside inline code. Those
        # belong to the declaration and must not silently drop an entire row.
        fields, chunk, in_code = [], [], False
        for character in line:
            if character == "`":
                in_code = not in_code
            if character == "|" and not in_code:
                fields.append("".join(chunk).strip())
                chunk = []
            else:
                chunk.append(character)
        fields = fields[1:]
        if len(fields) != 6 or fields[2] not in {"Supported", "Partial", "Planned", "Unsupported"}:
            continue
        native = fields[0] not in python_only
        entries.append({"category": fields[0], "status": fields[2], "declaredExamples": fields[1],
                        "declaredLimits": fields[3], "declaredTests": fields[4], "declaredDocs": fields[5],
                        "nativeComparisonApplicable": native,
                        "fullBehaviorAndParameterCoverageProved": False if native else None,
                        "qualification": "native_scope_not_systematically_qualified" if native else "standalone_python_product_contract"})
    return {"source": str(path.relative_to(root)).replace("\\", "/"),
            "declarationSha256": hashlib.sha256(raw.encode()).hexdigest(),
            "declaredCategoryCount": len(entries),
            "nativeComparableCategoryCount": sum(entry["nativeComparisonApplicable"] for entry in entries),
            "pythonProductCategoryCount": sum(not entry["nativeComparisonApplicable"] for entry in entries),
            "entries": entries, "coverageFraction": None,
            "qualification": "category_inventory_not_api_count_parameter_denominator_or_coverage_percentage"}


def native_runtime_error_checks(root: Path):
    """Keep error witnesses separate from numeric-cell denominators."""
    folder = root / "tests/workloads"
    name = "strategy_pending_pyramiding_stop_limit_change_direction"
    witness = json.loads((folder / f"{name}.native-error.json").read_text(encoding="utf-8"))
    for suffix, key in (("pine", "pineSha256"), ("dom.txt", "domSha256"), ("snapshot.txt", "snapshotSha256")):
        raw = (folder / f"{name}.{suffix}").read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != witness[key]:
            raise ValueError(f"Native error evidence hash mismatch: {name}.{suffix}")
    dom = (folder / f"{name}.dom.txt").read_text(encoding="utf-8")
    snapshot = (folder / f"{name}.snapshot.txt").read_text(encoding="utf-8")
    if witness["message"] not in dom or witness["nativeErrorCode"] not in snapshot:
        raise ValueError("Native runtime error is absent from captured visible DOM")
    input_name = "strategy_pending_pyramiding_stop_limit_to_market"
    inputs = json.loads((folder / f"{input_name}.tradingview.json").read_text(encoding="utf-8"))
    verify_evidence(folder, input_name, inputs)
    bars = _bars(input_name, inputs)[:witness["barIndex"] + 1]
    checks = []
    for incremental in (False, True):
        source = (folder / f"{name}{'' if incremental else '_batch'}.py").read_text(encoding="utf-8")
        result = pn.run(source, bars, executor_mode="inline")
        checks.append({"name": name, "mode": "incremental" if incremental else "batch",
                       "officialErrorBarIndex": witness["barIndex"], "officialErrorCode": witness["nativeErrorCode"],
                       "officialMessage": witness["message"], "officialScriptSha256": witness["pineSha256"],
                       "officialDomSha256": witness["domSha256"], "recipeSha256": hashlib.sha256(source.encode()).hexdigest(),
                       "officialSnapshotSha256": witness["snapshotSha256"],
                       "pyneSucceeded": result.ok, "pyneError": str(result.error) if result.error else None,
                       "pyneDirectionChangeRejected": not result.ok and "PYNE_STRATEGY_PENDING_DIRECTION_CHANGE" in str(result.error),
                       "errorPresenceDifference": bool(result.ok),
                       "qualification": "selected native error-presence witness; rejection cause and atomicity need separate validation"})
    return checks


def native_matrix_dimension_error_checks(root: Path):
    """Verify three native rejection witnesses, outside the numeric denominator."""
    folder = root / "tests/golden/matrix_dimension_rejections"
    capture = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
    if capture.get("schema") != "pyne.matrix-native-dimension-error/1" or capture.get("provider") != "tradingview":
        raise ValueError("Invalid matrix rejection provenance")
    cases = capture["cases"]
    expected_cases = {"product": ("mult", "mult", "RE10082"),
                      "sum": ("add", "sum", "RE10081"), "diff": ("sub", "diff", "RE10081")}
    if [case["name"] for case in cases] != list(expected_cases):
        raise ValueError("Incomplete native matrix rejection witnesses")
    checks = []
    for case in cases:
        name = case["name"]
        operation, native_operation, code = expected_cases[name]
        if case["pyneOperation"] != operation or case["nativeErrorCode"] != code:
            raise ValueError("Matrix rejection operation identity mismatch")
        for suffix, key in (("pine", "pineSha256"), ("native-error.txt", "errorSha256"), ("dom.txt", "domSha256")):
            raw = (folder / f"{name}.{suffix}").read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(raw).hexdigest() != case[key]:
                raise ValueError(f"Matrix rejection evidence hash mismatch: {name}.{suffix}")
        pine = (folder / f"{name}.pine").read_text(encoding="utf-8")
        dom = (folder / f"{name}.dom.txt").read_text(encoding="utf-8")
        error = (folder / f"{name}.native-error.txt").read_text(encoding="utf-8").strip()
        prefix = f"Error on bar 0: In the 'matrix.{native_operation}()' function."
        if (case["message"] != error or not error.startswith(prefix) or error not in dom
                or f"Runtime error: {code}" not in dom or "No data" not in dom):
            raise ValueError("Matrix native runtime error absent from captured visible DOM")
        for variable, key, initial in (("a", "leftShape", "1.0"), ("b", "rightShape", "2.0")):
            match = re.search(rf"matrix<float> {variable} = matrix.new<float>\((\d+),(\d+),{re.escape(initial)}\)", pine)
            if match is None or list(map(int, match.groups())) != case[key]:
                raise ValueError("Matrix rejection input dimensions differ from native script")
        if f"matrix.{native_operation}(a,b)" not in pine:
            raise ValueError("Matrix rejection operation absent from native script")
        h, w = case["rightShape"]
        expression = f"matrix.{operation}(matrix.new_float(2,3,1.),matrix.new_float({h},{w},2.))"
        for incremental in (False, True):
            source = ("indicator('Dimension rejection',mode='incremental')\n"
                      f"def on_bar(ctx,bar):\n    {expression}\n" if incremental else
                      f"indicator('Dimension rejection')\n{expression}\n")
            result = pn.run(source, [dict(time=0, open=1., high=2., low=0., close=1., volume=10.)], executor_mode="inline")
            checks.append(dict(name=name, mode="incremental" if incremental else "batch",
                officialErrorBarIndex=0, officialErrorCode=code, officialMessage=error,
                officialScriptSha256=case["pineSha256"], officialDomSha256=case["domSha256"],
                officialErrorSha256=case["errorSha256"], recipeSha256=hashlib.sha256(source.encode()).hexdigest(),
                pyneSucceeded=result.ok, pyneError=str(result.error) if result.error else None,
                errorPresenceDifference=bool(result.ok),
                qualification="three fixed native rejections; native post-error atomicity and Python exception/message equivalence not proved"))
    return checks


def native_command_visibility_checks(root: Path):
    """Observe state after submitted commands, as the captured Pine Logs do."""
    folder = root / "tests/workloads"
    checks = []
    for case in ("market_update_same_tick", "market_update_same_tick_p2", "stop_limit_to_market_same_tick", "stop_limit_to_market_same_tick_p2"):
        name = f"strategy_pending_pyramiding_{case}"
        capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
        verify_evidence(folder, name, capture)
        original = (folder / f"{name}.py").read_text(encoding="utf-8")
        lines = original.splitlines()
        commands = [line for line in lines if "ctx.strategy.entry(" in line]
        lines = [line for line in lines if line not in commands]
        index = lines.index("def on_bar(ctx, bar):") + 1
        lines[index:index] = commands
        source = "\n".join(lines) + "\n"
        result = pn.run(source, _bars(name, capture)[:1], executor_mode="inline")
        observed = {line["name"]: line["data"][0]["value"] if line["data"] else None for line in result.lines}
        expected = dict(zip(capture["columns"][6:], capture["rows"][0]["values"][6:], strict=True))
        differences = {title: {"official": value, "pyne": observed.get(title)}
                       for title, value in expected.items() if observed.get(title) != value}
        checks.append({"name": name, "mode": "incremental_after_commands", "pyneSucceeded": result.ok,
                       "officialState": expected, "pyneState": {title: observed.get(title) for title in expected},
                       "differences": differences, "oracleScriptSha256": capture["scriptSha256"],
                       "oracleLogSha256": capture["logSha256"], "recipeSha256": hashlib.sha256(source.encode()).hexdigest(),
                       "qualification": "first-bar after-command visibility witness; separate from numeric workload denominator"})
    return checks


def build_report(root: Path = ROOT):
    spec = importlib.util.spec_from_file_location("ta_capture_diff", root / "scripts/ta_capture_diff.py")
    capture_diff = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture_diff)
    capture_families = capture_diff.build_report(sorted((root / "tests/golden").glob("ta_*_indicators.json")), set(), "all")
    recipes = {}
    for path in sorted((root / "tests/golden").glob("ta_*_indicators.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture.get("external_capture", {}).get("status") == "captured":
            recipes[str(path.relative_to(root))] = sorted(recipe_methods(fixture["script"]))
    workloads = [workload_report(root, name, inputs, incremental)
                 for name, inputs in WORKLOADS for incremental in (False, True)]
    for workload in workloads:
        if workload["status"] == "measured":
            recipes[f"workload:{workload['name']}:{workload['mode']}"] = workload["recipeMethods"]
    mentioned = set().union(*(set(values) for values in recipes.values()))
    declared = set(BATCH_TA_CAPABILITIES)
    totals = {}
    for workload in workloads:
        for comparison in workload.get("columns", {}).values():
            for key, count in comparison["counts"].items():
                totals[key] = totals.get(key, 0) + count
    source_hash = hashlib.sha256()
    runtime_folder = Path(pn.__file__).resolve().parent
    for path in sorted(runtime_folder.rglob("*.py")):
        source_hash.update(("src/pyne_runtime/" + path.relative_to(runtime_folder).as_posix()).encode() + b"\0")
        source_hash.update(path.read_bytes().replace(b"\r\n", b"\n"))
    registered = {name for name, _ in WORKLOADS}
    hypothesis_capture = json.loads((root / "tests/workloads/percentile_insertion_matrix.tradingview.json").read_text())
    hypothesis_expected, hypothesis_observed = [], []
    for c, title in enumerate(hypothesis_capture["columns"]):
        if title.startswith("Formula Linear "):
            native = hypothesis_capture["columns"].index(title.removeprefix("Formula "))
            hypothesis_expected.extend(row["values"][native] for row in hypothesis_capture["rows"])
            hypothesis_observed.extend(row["values"][c] for row in hypothesis_capture["rows"])
    hypothesis = compare_column(hypothesis_expected, hypothesis_observed, hypothesis_capture["tolerance"])
    method_evidence = {}
    for method in sorted(declared):
        references = []
        for workload in workloads:
            lineage = workload.get("staticLineage", {})
            candidates = lineage.get("outputCandidates", {})
            columns = {title: {"counts": comparison["counts"],
                               "numericErrorSummary": comparison["numericErrorSummary"]}
                       for title, comparison in workload.get("columns", {}).items()
                       if method in candidates.get(title, [])}
            if method in workload.get("recipeMethods", []):
                references.append({"workload": workload["name"], "mode": workload["mode"],
                                   "callExpressions": lineage.get("callExpressions", {}).get(method, []),
                                   "candidateMeasuredColumns": columns,
                                   "outputAssociationResolved": bool(columns)})
        method_evidence[method] = {
            "workloadReferences": references,
            "importedFixtureRecipes": [name for name, methods in recipes.items()
                                       if not name.startswith("workload:") and method in methods],
            "parameterCoverageProved": False,
            "qualification": "static_candidates_not_method_specific_parity_or_complete_coverage",
        }
    unmeasured = sorted(path.name.removesuffix(".tradingview.json")
                        for path in (root / "tests/workloads").glob("*.tradingview.json")
                        if path.name.removesuffix(".tradingview.json") not in registered)
    return json_safe_numbers({
        "schema": "pyne.official-alignment-assessment/2",
        "numericValueEncoding": {
            "finiteNumbers": "JSON numbers",
            "nonfiniteNumbers": "objects with nonfiniteNumber: positiveInfinity, negativeInfinity or NaN",
            "missingValues": "null; distinct from nonfinite numbers",
        },
        "packageCandidate": tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "runtimeDistributionVersion": pn.__version__,
        "runtimeIdentityQualification": "packageCandidate is checkout metadata; semantics and tree hash identify the loaded runtime; source-only distribution metadata may be absent or stale",
        "semanticsIdentity": INCREMENTAL_SEMANTICS_VERSION, "sourceTreeSha256": source_hash.hexdigest(),
        "runtimeImportPath": pn.__file__,
        "taSurface": {"declaredBatchMethods": sorted(declared), "batchMethodCount": len(declared),
                      "declaredIncrementalMethods": list(INCREMENTAL_TA_CAPABILITIES),
                      "incrementalMethodCount": len(INCREMENTAL_TA_CAPABILITIES),
                      "methodsPresentInCaptureRecipes": sorted(mentioned & declared),
                      "methodsWithoutRecipeEvidence": sorted(declared - mentioned),
                      "qualification": "recipe_presence_only_not_per_api_behavior_or_parameter_coverage"},
        "measuredWorkloadTotals": totals,
        "workloadCoverage": {
            "registeredRecipeCount": len({case["name"] for case in workloads}),
            "registeredModeCount": len(workloads),
            "measuredModeCount": sum(case["status"] == "measured" for case in workloads),
            "unmappedModeCount": sum(case["status"] == "unmapped" for case in workloads),
            "fullyMappedMeasuredModeCount": sum(case["status"] == "measured" and not case["unmappedOutputColumns"] for case in workloads),
            "partiallyMappedMeasuredModeCount": sum(case["status"] == "measured" and bool(case["unmappedOutputColumns"]) for case in workloads),
            "qualification": "registered evidence corpus only; neither declared API nor parameter coverage",
        },
        "activeCellDifferenceRate": totals["differences"] / totals["activeCells"] if totals.get("activeCells") else None,
        "workloads": workloads, "unmeasuredNativeWorkloads": unmeasured,
        "taCaptureFamilyDiagnostics": capture_families,
        "strategyCaptureFamilyDiagnostics": imported_capture_diagnostics(root, "strategy"),
        "requestCaptureFamilyDiagnostics": imported_capture_diagnostics(root, "request"),
        "declaredScopeInventory": declared_scope_inventory(root),
        "recipeEvidence": recipes,
        "taMethodEvidence": method_evidence,
        "nativeStateChecks": [native_percentile_history_check(root / "tests/workloads")],
        "nativeSourceExpressionContext": native_source_expression_context_check(root),
        "nativeOverflowStateMasks": native_overflow_state_mask_check(root),
        "nativeOverflowDiscriminator": native_overflow_discriminator_check(root),
        "nativeNearEdgeGuards": native_near_edge_check(root),
        "nativeNearEdgeCallIsolation": native_near_edge_isolation_check(root),
        "nativeVarianceInputs": native_variance_input_check(root),
        "nativeVarianceSourceOperations": native_variance_source_operations_check(root),
        "nativeSumHistoryPrefix": native_sum_history_prefix_check(root),
        "nativeRecursiveStateInputs": native_recursive_state_input_check(root),
        "nativeRecursiveCompositionInputs": native_recursive_composition_input_check(root),
        "nativeLegacyDmiWrapper": native_legacy_dmi_wrapper_check(root),
        "nativeRuntimeErrorChecks": native_runtime_error_checks(root),
        "nativeMatrixDimensionErrorChecks": native_matrix_dimension_error_checks(root),
        "nativeCommandVisibilityChecks": native_command_visibility_checks(root),
        "nativeTextChecks": native_array_join_text_checks(root),
        "nativeCollectionTextChecks": native_collection_extraction_text_checks(root),
        "nativeHypothesisChecks": [{"name": "linear_insertion_rolling_percentile",
                                    "workload": "percentile_insertion_matrix",
                                    "counts": hypothesis["counts"],
                                    "rejected": bool(hypothesis["counts"]["differences"]),
                                    "qualification": "independent_formula_falsification_not_runtime_parity"}],
        "acceptance": {"smallDifferenceProved": False, "goalShouldRemainActive": True,
                       "reasons": ["TA recipe presence is not systematic per-behavior coverage",
                                   "equal numeric source values alone do not establish equivalent native expression context",
                                   "native missing-state mask agreement does not qualify numerical outputs or replacement algorithms",
                                   "finite selected workloads do not establish workload representativeness",
                                   "request/strategy/collections/time/realtime domains need separate full-scope assessment",
                                   "legacy sparse plot diagnostics lack independently verified raw provenance in this assessment",
                                   "declared category inventory does not establish API or parameter coverage",
                                   "startup and reference-only differences are counted, not silently excluded"]},
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-small-difference", action="store_true",
                        help="Fail unless the assessment actually proves the acceptance condition.")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        surface = report["taSurface"]
        totals = report["measuredWorkloadTotals"]
        corpus = report["workloadCoverage"]
        print(f"Registered evidence: {corpus['registeredRecipeCount']} recipes; "
              f"{corpus['measuredModeCount']}/{corpus['registeredModeCount']} modes measured, "
              f"{corpus['unmappedModeCount']} modes unmapped, "
              f"{corpus['partiallyMappedMeasuredModeCount']} measured modes partially mapped; not API coverage")
        print(f"Unmeasured retained native workloads: {len(report['unmeasuredNativeWorkloads'])}; "
              f"{', '.join(report['unmeasuredNativeWorkloads']) or 'none'}; excluded from runtime numeric agreement")
        print(f"TA recipe presence: {len(surface['methodsPresentInCaptureRecipes'])}/{surface['batchMethodCount']}; not qualification")
        print(f"Measured active cells: {totals['activeCells']}; differences: {totals['differences']}; "
              f"rate: {report['activeCellDifferenceRate']:.3%}; both-missing cells separately: {totals['bothMissingCells']}")
        imported = report['taCaptureFamilyDiagnostics']['counts']
        print(f"Imported sparse TA diagnostics: {imported['differences']}/{imported['points']} differences, "
              f"{imported['unexpected_differences']} unexpected; separate from native matrix totals")
        checks = report["nativeRuntimeErrorChecks"]
        print(f"Native error-presence gaps: {sum(c['errorPresenceDifference'] for c in checks)}/{len(checks)}; separate from numeric cells")
        matrix_errors = report["nativeMatrixDimensionErrorChecks"]
        print(f"Native matrix dimension error-presence gaps: {sum(c['errorPresenceDifference'] for c in matrix_errors)}/{len(matrix_errors)} "
              "mode comparisons across 3 fixed native witnesses; separate from numeric cells")
        visibility = report["nativeCommandVisibilityChecks"]
        print(f"Native after-command state gaps: {sum(len(c['differences']) for c in visibility)} "
              f"across {len(visibility)} witnesses; separate from numeric cells")
        texts = report["nativeTextChecks"]
        print(f"Native exact-text gaps: {texts['differences']}/{texts['cells']}; separate from numeric cells")
        collection_text = report["nativeCollectionTextChecks"]
        print(f"Native collection extraction text gaps: {collection_text['differences']}/{collection_text['cells']}; separate from numeric cells")
        print("Acceptance NOT PROVED; Goal must remain active.")
    return int(args.require_small_difference and not report["acceptance"]["smallDifferenceProved"])


if __name__ == "__main__":
    raise SystemExit(main())
