"""Separate equal numeric inputs from native expression context and sampled history."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re

from pyne_runtime.incremental.ta import _StepSMA

ROOT = Path(__file__).resolve().parents[1]
ISOLATED = ("sum_constant_isolated", "sum_series_isolated", "sum_branch_isolated")
LONG = "sma_long_overflow_recovery_extended"


def sample_indices():
    return (list(range(24)) + [31, 63, 127, 255, 511, 1023, 2047, 3071] + list(range(4080, 4112))
            + list(range(4998, 5004)) + list(range(8190, 8194)) + list(range(9998, 10002))
            + list(range(16382, 16386)) + list(range(24998, 25002)))


def input_at(i):
    large = 160000000.0 * (10. ** 300)
    return large if i < 6 else float((i * 11) % 17 - 6) * .25


def _modules(root):
    spec = importlib.util.spec_from_file_location("sma_source_context_helpers", root / "scripts/sma_arithmetic_diagnostic.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers, helpers._reporter(root)


def build_diagnostic(root: Path = ROOT):
    helpers, reporter = _modules(root)
    captures = {}
    input_cells = guard_cells = 0
    half = 80000000.0 * (10. ** 300)
    for name, expression_class in zip(ISOLATED, ("constant", "series_arithmetic", "series_branch"), strict=True):
        capture, columns = helpers._load(root, reporter, name)
        if (len(capture["rows"]) != 32 or len(capture["columns"]) != 6 or capture.get("diagnosticOnly") is not False
                or capture.get("sourceExpressionClass") != expression_class):
            raise ValueError("Incomplete or incorrectly qualified isolated source-expression evidence")
        if columns["Input"] != [half] * 32 or columns["Native2"] != [None] + [half] * 31:
            raise ValueError("Independent isolated input/mean identity differs")
        input_cells += 32
        for field in ("Native2", "Sum2"):
            if columns["IsNa" + field] != [int(v is None) for v in columns[field]]:
                raise ValueError("Same-capture isolated missing state contradicts numeric log")
            guard_cells += 32
        if columns["HalfInvariantSum2"] != [0.] * 32:
            raise ValueError("Isolated nonfinite state requires additional qualification")
        guard_cells += 32
        captures[name] = columns
    constant = captures[ISOLATED[0]]
    series = captures[ISOLATED[1]]
    branch = captures[ISOLATED[2]]
    if series != branch:
        raise ValueError("Two independent series expressions disagree in the isolated capture")
    if series["Sum2"] != [None] + [half * 2] * 31:
        raise ValueError("Independent finite series sum identity differs")
    if constant["Sum2"] != [None] * 32:
        raise ValueError("Isolated constant-expression state witness differs")
    context_comparisons = [reporter.compare_column(constant["Sum2"], columns["Sum2"], 0.) for columns in (series, branch)]

    capture, columns = helpers._load(root, reporter, LONG)
    marks = sample_indices()
    if (len(capture["rows"]) != 86 or len(capture["columns"]) != 10 or capture.get("diagnosticOnly") is not False
            or capture.get("sourceExpressionClass") != "series_level_shift" or columns["ActualBarIndex"] != marks):
        raise ValueError("Incomplete or incorrectly qualified sampled native history")
    source = (root / "tests/workloads" / (LONG + ".pine")).read_text(encoding="utf-8")
    if "float src = i < 6 ? large : float((i * 11) % 17 - 6) * 0.25" not in source:
        raise ValueError("Unobserved native history input formula differs from independent supplied history")
    source_marks, = re.findall(r"var marks = array.from\(([^)]+)\)", source)
    if [int(v.strip()) for v in source_marks.split(",")] != marks:
        raise ValueError("Executed Pine sample selection differs from independently generated inputs")
    raw = (root / "tests/workloads" / (LONG + ".tradingview.txt")).read_text(encoding="utf-8")
    coverage, = re.findall(r"LONG_EXTENDED_COVERAGE49\|(\d+)\|(\d+);", raw)
    coverage = dict(lastConfirmedBarIndex=int(coverage[0]), emittedSamples=int(coverage[1]))
    if coverage != capture["executionCoverage"] or coverage["emittedSamples"] != 86 or coverage["lastConfirmedBarIndex"] < marks[-1]:
        raise ValueError("Native full-history execution receipt differs or is insufficient")
    if columns["Input"] != [input_at(i) for i in marks]:
        raise ValueError("Independent long-history sampled input differs")
    for field in ("Native2", "Native3", "Sum2", "Sum3"):
        if columns["IsNa" + field] != [int(v is None) for v in columns[field]]:
            raise ValueError("Long-history native missing state contradicts numeric log")
    if any(value is not None for field in ("Native2", "Native3", "Sum2", "Sum3") for value in columns[field]):
        raise ValueError("Recorded long-history missing persistence witness differs")
    direct_checks = []
    for period in (2, 3):
        helper = _StepSMA(period)
        observed = []
        selected = set(marks)
        for i in range(marks[-1] + 1):
            value = helper.update(input_at(i))
            if i in selected:
                observed.append(value)
        direct_checks.append(dict(period=period, comparison=reporter.compare_column(columns[f"Native{period}"], observed, 1e-8)))
    return reporter.json_safe_numbers(dict(schema="pyne.native-sma-sum-source-context/1",
        isolatedInputCellsVerified=input_cells, isolatedStateGuardCellsVerified=guard_cells,
        isolatedContextComparisons=context_comparisons, sameNumericInputsEstablishSameNativeContext=False,
        constantMissingAfterReadiness=31, seriesFiniteAfterReadiness=31,
        sourceExpressionQualification="Source-expression effect is observed independently with arithmetic and branch variants. Const/series labels follow documented type rules; hidden compiler mechanism is not established.",
        qualifierDocumentation="https://www.tradingview.com/pine-script-docs/language/type-system/",
        longHistory=dict(sampledRows=86, lastSampledBarIndex=marks[-1], suppliedObservations=marks[-1]+1,
                         independentlyVerifiedSampledInputs=86, nativeStateGuardCells=344, nativeMissingOutputCells=344,
                         executionCoverage=coverage, sampledDirectSmaComparisons=direct_checks,
                         countedAsAdditionalRuntimeAgreement=False,
                         qualification="All intervening Python inputs are independently supplied; only 86 native output samples are logged. Standalone step-helper comparisons do not qualify a full host execution contract."),
        canonicalNativeOutputs=10, excludedControls=18, runtimeChanged=False, acceptanceProved=False, goalStatus="active",
        limits=["Constant-expression differences remain in raw assessment counts; no Python compiler qualifier emulation is adopted.",
                "Equal numeric inputs alone do not qualify the same native execution context.",
                "Eighty-six sampled points through index 25001 do not prove every intervening native output or permanent poisoning.",
                "Full-prefix callback recipes do not qualify bounded streaming cost or a direct incremental sum API."]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    text = json.dumps(build_diagnostic(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
