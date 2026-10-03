"""Separate native source arithmetic and normalization from runtime agreement."""
from __future__ import annotations

from collections import deque
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAME = "variance_source_operations"
SOURCE_SHA = "d29ca750cb5245e20e9ad07618fb6158672193cf9bfd9516dce84f9b85b4b5d9"
CSV_SHA = "6ecc44170efac627e70310736c20793e66a192a35ef8d45e2d040adaccead79d"
PROFILES = ("base", "high", "negative", "regime")
PERIODS = (2, 3, 7)
FORMS = {
    "separate_quotients": lambda a, b, n, d: b / d - (a / n) * (a / d),
    "square_separate_quotient": lambda a, b, n, d: b / d - a * a / (n * d),
    "subtract_then_divide": lambda a, b, n, d: (b - a * a / n) / d,
    "mean_product_subtract_then_divide": lambda a, b, n, d: (b - (a / n) * a) / d,
    "mean_square_scaled": lambda a, b, n, d: b / d - ((a / n) * (a / n)) * n / d,
    "mean_square_factor": lambda a, b, n, d: b / d - ((a / n) * (a / n)) * (n / d),
    "biased_then_scale": lambda a, b, n, d: (b / n - (a / n) * (a / n)) * n / d,
    "mean_first_divide": lambda a, b, n, d: b / d - (a / n) * a / d,
}


def load_script(root, filename, name):
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_diagnostic(root=ROOT):
    folder = root / "tests/workloads"
    reporter = load_script(root, "official_alignment_report.py", "variance_operation_report")
    previous = load_script(root, "variance_native_diagnostic.py", "variance_operation_previous")
    previous.build_diagnostic(root)
    prior_capture = json.loads((folder / (previous.NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    inputs = previous.recipe_inputs((folder / (previous.NAME + ".py")).read_text(encoding="utf-8"))
    capture = json.loads((folder / (NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, NAME, capture)
    expected_columns = [f"{field} {profile}" for profile in PROFILES for field in ("Input", "Square", "Power")]
    expected_columns += [f"{field} {profile} {period}" for profile in PROFILES for period in PERIODS
                         for field in ("Mean", "MeanXX", "MeanPow", "SumXX", "Variance biased", "Variance sample")]
    if (capture.get("scriptSha256") != SOURCE_SHA or capture.get("columns") != expected_columns
            or len(capture["rows"]) != 64 or capture.get("diagnosticOnly") is not True
            or capture.get("sourceExpressionClass") != "native_variance_source_operation_discriminator"
            or capture.get("missingValueToken") != "NA" or capture.get("tolerance") != 1e-8
            or capture.get("selection") != dict(rows=64, firstNativeBarIndex=0,
                profiles=list(PROFILES), periods=list(PERIODS), sourceInputsOnly=True)):
        raise ValueError("Native variance operation capture qualification differs")
    csv_path = folder / (NAME + ".tradingview.csv")
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != CSV_SHA or capture.get("downloadedCsvSha256") != CSV_SHA:
        raise ValueError("Native variance operation UI download identity differs")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["Date", "Message"]:
            raise ValueError("Native variance operation download columns differ")
        records = list(reader)
    if len(records) != 64 or "\n".join(row["Message"] for row in records) + "\n" != (
            folder / (NAME + ".tradingview.txt")).read_text(encoding="utf-8"):
        raise ValueError("Native variance operation raw log differs from download")
    for index, row in enumerate(records):
        stamp = datetime.fromisoformat(row["Date"]).astimezone(timezone.utc)
        if (stamp.year * 12 + stamp.month != 2017 * 12 + 8 + index
                or (stamp.day, stamp.hour, stamp.minute, stamp.second) != (1, 0, 0, 0)):
            raise ValueError("Native variance operation monthly selection differs")
    source = (folder / (NAME + ".pine")).read_text(encoding="utf-8")
    supplied = {profile: [None if token == "float(na)" else float(token) for token in values.split(", ")]
                for profile, values in re.findall(r"a_(\w+) = array.from\(([^\n]*)\)", source)}
    if tuple(supplied) != PROFILES or supplied != inputs:
        raise ValueError("Native variance operation frozen source inputs differ")
    columns = {name: [row["values"][i] for row in capture["rows"]] for i, name in enumerate(expected_columns)}
    if any(columns[f"Input {profile}"] != inputs[profile] for profile in PROFILES):
        raise ValueError("Native variance operation captured inputs differ")
    prior_columns = {name: [row["values"][i] for row in prior_capture["rows"]]
                     for i, name in enumerate(prior_capture["columns"])}
    checks = []

    def check(kind, name, native, proposed, tolerance=0.):
        result = reporter.compare_column(native, proposed, tolerance)
        checks.append(dict(kind=kind, column=name, counts=result["counts"], differences=result["differences"]))

    for profile in PROFILES:
        check("sourceSquare", profile, columns[f"Square {profile}"],
              [None if value is None else value * value for value in inputs[profile]])
        check("nativePowerEqualsSquare", profile, columns[f"Power {profile}"], columns[f"Square {profile}"])
        for period in PERIODS:
            suffix = f"{profile} {period}"
            check("nativeSumDivPeriodEqualsMeanXX", suffix, columns[f"MeanXX {suffix}"],
                  [None if value is None else value / period for value in columns[f"SumXX {suffix}"]])
            check("nativePowMeanEqualsMeanXX", suffix, columns[f"MeanPow {suffix}"], columns[f"MeanXX {suffix}"])
            for field in ("Mean", "MeanXX", "Variance biased", "Variance sample"):
                name = f"{field} {suffix}"
                check("priorNativeRecapture", name, prior_columns[name], columns[name])
    scaling = []
    for name, formula in FORMS.items():
        cases = []
        for profile in PROFILES:
            for period in PERIODS:
                window = deque()
                sums = []
                for value in inputs[profile]:
                    if value is not None:
                        window.append(value)
                        if len(window) > period:
                            window.popleft()
                    sums.append(None if len(window) < period else sum(window))
                for bias in ("biased", "sample"):
                    denominator = period if bias == "biased" else period - 1
                    suffix = f"{profile} {period}"
                    proposed = [None if a is None or b is None else max(0., formula(a, b, period, denominator))
                                for a, b in zip(sums, columns[f"SumXX {suffix}"])]
                    result = reporter.compare_column(columns[f"Variance {bias} {suffix}"], proposed, 1e-8)
                    cases.append(dict(profile=profile, period=period, bias=bias,
                                      counts=result["counts"], differences=result["differences"]))
        scaling.append(dict(formula=name, cases=cases,
                            differences=sum(case["counts"]["differences"] for case in cases)))
    return dict(schema="pyne.native-variance-source-operations-diagnostic/1", nativeRows=64,
        inputCellsVerified=256, nativeOutputCells=5120, recapturedNativeOutputCells=3072,
        newDiagnosticCells=2048, officialUiCsvSha256=CSV_SHA, sourceInputsIndependentlyReconstructed=True,
        exactChecks=checks, exactCheckDifferences=sum(check["counts"]["differences"] for check in checks),
        nativeSumScalingHypotheses=dict(checks=scaling, nativeSumUsedAsDiagnosticOnly=True,
            minimumDifferences=min(check["differences"] for check in scaling), comparedCellsPerFormula=1536,
            countedAsRuntimeAgreement=False),
        nativeIndicatorValuesSuppliedToRuntime=False, countedAsAdditionalRuntimeAgreement=False,
        privateImplementationProved=False, replacementAccumulatorQualified=False, acceptanceProved=False,
        qualification="Frozen supplied inputs only. Source multiplication and native power, mean and sum recapture are diagnostic witnesses. Native sums are used only to discriminate arithmetic ordering, never supplied to the runtime. No general source-context invariance or private implementation is proved; no runtime parity cells are added.")
