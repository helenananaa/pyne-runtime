"""Explain retained native arithmetic witnesses without claiming runtime parity."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CASES = (("base", "base", 3), ("holes", "shifted", 3), ("hugeA", "hugeB", 2),
         ("hugeA", "hugeB", 3), ("hugeA", "hugeB", 7), ("hugeHole", "hugeB", 3),
         ("hugeHole", "hugeB", 7), ("hugeA", "hugeA", 3))
MODELS = ("RawFormula", "StdevFormula", "ZeroGuardRaw", "ZeroGuardStdev",
          "ScaledRawFormula", "ZeroGuardScaledRaw")


def _reporter(root):
    spec = importlib.util.spec_from_file_location("native_arithmetic_reporter", root / "scripts/official_alignment_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(root, reporter, name, rows, columns):
    folder = root / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, name, capture)
    if len(capture["rows"]) != rows or len(capture["columns"]) != columns:
        raise ValueError(f"Incomplete diagnostic matrix: {name}")
    if len(set(capture["columns"])) != columns:
        raise ValueError(f"Duplicate diagnostic columns: {name}")
    values = {title: [row["values"][index] for row in capture["rows"]]
              for index, title in enumerate(capture["columns"])}
    return capture, values


def _array(values):
    # Synthetic whole-valued inputs must also use binary64: integer products
    # would silently overflow at the 1e12-scale witnesses.
    return np.array([np.nan if value is None else value for value in values], dtype=np.float64)


def _json_values(values):
    return [None if not np.isfinite(value) else float(value) for value in values]


def build_diagnostic(root: Path = ROOT):
    reporter = _reporter(root)
    name = "correlation_arithmetic_decomposition"
    capture, values = _load(root, reporter, name, 64, 206)
    formula_cases = []
    operand_checks = []
    for a, b, period in CASES:
        suffix = f"{a} {b} {period}"
        native = values[f"Native {suffix}"]
        comparisons = {model: reporter.compare_column(native, values[f"{model} {suffix}"], capture["tolerance"])
                       for model in MODELS}
        formula_cases.append(dict(case=suffix, models=comparisons))
        mean_a, mean_b = _array(values[f"MeanA {suffix}"]), _array(values[f"MeanB {suffix}"])
        recomposed = {
            "Numerator": _array(values[f"MeanXY {suffix}"]) - mean_a * mean_b,
            "RawVarianceA": _array(values[f"MeanXX {suffix}"]) - mean_a * mean_a,
            "RawVarianceB": _array(values[f"MeanYY {suffix}"]) - mean_b * mean_b,
        }
        for field, actual in recomposed.items():
            comparison = reporter.compare_column(values[f"{field} {suffix}"], _json_values(actual), 0)
            operand_checks.append(dict(case=suffix, field=field, comparison=comparison))

    reduction_name = "correlation_reduction_order"
    reduction, folds = _load(root, reporter, reduction_name, 64, 57)
    if reduction.get("diagnosticOnly") is not True or reduction_name in dict(reporter.WORKLOADS):
        raise ValueError("Native-to-native reduction controls must stay outside runtime agreement counts")
    fold_checks = []
    for title, actual in folds.items():
        if title.startswith(("Newest ", "Oldest ", "Kahan ", "Neumaier ", "Paired ")):
            comparison = reporter.compare_column(folds[f"Native {title.split(' ', 1)[1]}"], actual, 0)
            fold_checks.append(dict(title=title, comparison=comparison))
    primitive_checks = []
    for title, a, b in (("xx", "hugeA", "hugeA"), ("xy", "hugeA", "hugeB"), ("yy", "hugeB", "hugeB")):
        actual = _array(folds[a]) * _array(folds[b])
        primitive_checks.append(dict(title=title,
            comparison=reporter.compare_column(folds[title], _json_values(actual), 0)))
    totals = {model: sum(case["models"][model]["counts"]["differences"] for case in formula_cases)
              for model in MODELS}
    return dict(schema="pyne.native-correlation-diagnostic/1", candidateRuntimeQualified=False,
        diagnosticCells=512, formulaDifferenceCounts=totals, formulaCases=formula_cases,
        operandRoundtripChecks=operand_checks, primitiveProductChecks=primitive_checks,
        nativeReductionChecks=fold_checks,
        evidence={name: {key: capture[key] for key in ("scriptSha256", "logSha256", "capturedAt")},
                  reduction_name: {key: reduction[key] for key in ("scriptSha256", "logSha256", "capturedAt")}},
        qualification="Native formulas explain these finite cases; they are not executed Pyne agreement. "
        "Zero-numerator guards agree on all 512 native cells. Binary64 products and logged operands "
        "recompose exactly, but newest/oldest/Kahan/Neumaier/paired SMA folds have period-3/7 counterexamples. "
        "The native rolling reduction remains unreconstructed. Runtime differences and full-scope Goal stay open.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_diagnostic()
    raw = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8", newline="\n")
    print(json.dumps(dict(formulaDifferenceCounts=report["formulaDifferenceCounts"],
                         candidateRuntimeQualified=report["candidateRuntimeQualified"]), indent=2))


if __name__ == "__main__":
    main()
