"""Falsify overflow-state hypotheses without treating masks as numeric parity."""
from __future__ import annotations

import argparse
from collections import deque
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "sma_overflow_mask_holdout"
PROFILES = ("keywordHalf", "branchHalf", "edgeFinite", "edgeCancellation", "preReadyRecover",
            "rotation", "singleHuge", "recovery", "gapRecovery")
MODELS = ("remove_add", "add_remove", "window_recompute", "sticky_window_recompute",
          "exact_window_sum", "kahan_remove_add")


def inputs(i):
    half = 80000000.0 * (10. ** 300)
    large = 160000000.0 * (10. ** 300)
    ulp = 2. ** 970
    edge = 2. ** 1023 - ulp
    small = float((i * 11) % 17 - 6) * .25
    return dict(keywordHalf=half, branchHalf=half, edgeFinite=edge - float(i % 3) * ulp,
                edgeCancellation=edge if i % 4 < 2 else -edge,
                preReadyRecover=large if i < 2 else -large if i < 4 else small,
                rotation=-large if i % 3 == 1 else large,
                singleHuge=large if i == 0 else small, recovery=large if i < 6 else small,
                gapRecovery=large if i < 6 else None if i < 12 else small)


def candidate_masks(values, period, model):
    """Initialize only from supplied inputs; nonfinite=>missing is a hypothesis."""
    if model not in MODELS:
        raise ValueError("Unknown independent overflow model")
    window = deque()
    total = correction = 0.
    poisoned = False
    masks = []
    for value in values:
        if value is not None:
            outgoing = window.popleft() if len(window) == period else None
            if model == "kahan_remove_add":
                for operand in ((-outgoing,) if outgoing is not None else ()) + (value,):
                    adjusted = operand - correction
                    updated = total + adjusted
                    correction = (updated - total) - adjusted
                    total = updated
            elif model == "add_remove":
                total += value
                if outgoing is not None:
                    total -= outgoing
            elif model == "remove_add":
                if outgoing is not None:
                    total -= outgoing
                total += value
            window.append(value)
            if model in ("window_recompute", "sticky_window_recompute"):
                total = 0.
                for operand in window:
                    total += operand
            elif model == "exact_window_sum":
                try:
                    total = float(sum((Fraction(v) for v in window), Fraction()))
                except OverflowError:
                    total = math.inf
            poisoned |= not math.isfinite(total)
        # Period one retains the latest nonmissing input, independently of accumulator order.
        if period == 1:
            masks.append(int(not window))
        else:
            masks.append(int(len(window) < period or not math.isfinite(total)
                             or (model == "sticky_window_recompute" and poisoned)))
    return masks


def _modules(root):
    spec = importlib.util.spec_from_file_location("mask_diagnostic_helpers", root / "scripts/sma_arithmetic_diagnostic.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers, helpers._reporter(root)


def build_diagnostic(root=ROOT):
    helpers, reporter = _modules(root)
    capture, columns = helpers._load(root, reporter, NAME)
    expected_columns = [title for profile in PROFILES for title in
                        ["Input " + profile] + [f"Missing {kind} {period} {profile}"
                         for period in (1, 2, 3, 7) for kind in ("SMA", "SUM")]]
    if (capture.get("diagnosticOnly") is not True or len(capture["rows"]) != 32
            or capture["columns"] != expected_columns):
        raise ValueError("Incomplete or incorrectly qualified native state-mask evidence")
    generated = [inputs(i) for i in range(32)]
    for profile in PROFILES:
        if columns["Input " + profile] != [row[profile] for row in generated]:
            raise ValueError("Independent overflow input identity differs")
    for title, values in columns.items():
        if title.startswith("Missing ") and any(v not in (0., 1.) for v in values):
            raise ValueError("Native missing-state flag is not binary")
    source = (root / "tests/workloads" / (NAME + ".pine")).read_text(encoding="utf-8")
    required = ("int i = bar_index", "float half = 80000000.0 * math.pow(10., 300)",
                "float large = 160000000.0 * math.pow(10., 300)", "float ulp = math.pow(2., 970)",
                "float edge = math.pow(2., 1023) - ulp", "float small = float((i * 11) % 17 - 6) * 0.25",
                "series float src_keywordHalf = half", "series float src_branchHalf = i >= 0 ? half : 0.",
                "series float src_edgeFinite = edge - float(i % 3) * ulp",
                "series float src_edgeCancellation = i % 4 < 2 ? edge : -edge",
                "series float src_preReadyRecover = i < 2 ? large : i < 4 ? -large : small",
                "series float src_rotation = i % 3 == 1 ? -large : large",
                "series float src_singleHuge = i == 0 ? large : small",
                "series float src_recovery = i < 6 ? large : small",
                "series float src_gapRecovery = i < 6 ? large : i < 12 ? na : small")
    if any(line not in source.splitlines() for line in required):
        raise ValueError("Executed native input formula differs from supplied inputs")
    for profile in PROFILES:
        for period in (1, 2, 3, 7):
            for kind, function in (("SMA", "ta.sma"), ("SUM", "math.sum")):
                variable = f"{kind}{period}_{profile}"
                if (f"float {variable} = {function}(src_{profile}, {period})" not in source.splitlines()
                        or f"int Missing_{variable} = na({variable}) ? 1 : 0" not in source.splitlines()):
                    raise ValueError("Native state operation differs")
    comparisons = []
    for model in MODELS:
        checks = []
        for profile in PROFILES:
            values = [row[profile] for row in generated]
            for period in (1, 2, 3, 7):
                predicted = candidate_masks(values, period, model)
                for kind in ("SMA", "SUM"):
                    actual = columns[f"Missing {kind} {period} {profile}"]
                    differences = [i for i, (a, p) in enumerate(zip(actual, predicted, strict=True)) if a != p]
                    checks.append(dict(profile=profile, period=period, kind=kind, cells=32,
                                       differences=len(differences), differingIndices=differences))
        comparisons.append(dict(model=model, cells=2304, differences=sum(c["differences"] for c in checks),
                                qualifiedAsRuntimeReplacement=False, checks=checks))
    context = [i for i in range(32) if columns["Missing SUM 2 keywordHalf"][i]
               != columns["Missing SUM 2 branchHalf"][i]]
    # These are state witnesses, independently observed; neither specifies a hidden implementation.
    if context != list(range(1, 32)):
        raise ValueError("Explicit-series source-expression witness differs")
    bridges = []
    for profile in PROFILES:
        for period in (1, 2, 3, 7):
            indices = [i for i, (a, b) in enumerate(zip(columns[f"Missing SMA {period} {profile}"],
                       columns[f"Missing SUM {period} {profile}"], strict=True)) if a != b]
            if indices and (profile != "keywordHalf" or period != 2):
                raise ValueError("Same-capture native state bridge differs")
            bridges.append(dict(profile=profile, period=period, cells=32, differences=len(indices)))
    _, numeric_columns = helpers._load(root, reporter, "sma_period_two_independent_holdout")
    numeric_checks = []
    for profile in helpers.input_profiles(0):
        values = [helpers.input_profiles(i)[profile] for i in range(96)]
        for period in (2, 3):
            comparison = reporter.compare_column(numeric_columns[f"Native{period} {profile}"],
                helpers.kahan_remove_add(values, period), 1e-8)
            numeric_checks.append(dict(profile=profile, period=period, comparison=comparison))
    numeric_counts = {key: sum(c["comparison"]["counts"][key] for c in numeric_checks)
                      for key in numeric_checks[0]["comparison"]["counts"]}
    recovery = {f"{kind}{period}": [i for i in range(4, 32)
                if columns[f"Missing {kind} {period} preReadyRecover"][i] == 1]
                for kind in ("SMA", "SUM") for period in (3, 7)}
    return dict(schema="pyne.native-overflow-mask-diagnostic/1", inputCellsVerified=288,
                nativeStateMaskCells=2304, nativeNumericOutputCells=0,
                countedAsAdditionalRuntimeAgreement=False, candidateComparisons=comparisons,
                nativeSmaSumStateBridge=dict(cells=1152, differences=sum(c["differences"] for c in bridges),
                                             checks=bridges, universalIdentityQualified=False),
                kahanNumericHoldout=dict(counts=numeric_counts, checks=numeric_checks,
                    qualification="Independent 96-row numerical holdout is separate from the new mask denominator. A mask fit cannot qualify the model's numerical values or a runtime replacement."),
                explicitSeriesSourceContext=dict(equalInputCells=64, sumPeriodTwoMaskDifferences=len(context),
                    differingIndices=context, seriesKeywordEstablishesEquivalentContext=False),
                preReadinessRecoveryMissing=recovery,
                qualification="Each model starts from independently supplied inputs. Candidate nonfinite-to-missing mapping is a hypothesis; actual Pyne infinities remain distinct from missing. Masks do not qualify numeric values, permanent poisoning, a compiler rule or a runtime replacement.",
                runtimeChanged=False, acceptanceProved=False, goalStatus="active")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = build_diagnostic()
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.json:
        args.json.write_text(encoded, encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("inputCellsVerified", "nativeStateMaskCells", "nativeNumericOutputCells")}))
    print(json.dumps({c["model"]: c["differences"] for c in result["candidateComparisons"]}))


if __name__ == "__main__":
    main()
