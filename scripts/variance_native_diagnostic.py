"""Verify supplied scalar inputs, UI-download identity and arithmetic witnesses."""
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAME = "variance_independent_holdout"
SOURCE_SHA = "26cd828b3ab424dd567d94d9dfafbfaf99b75592e7c5db34212923f12c381737"
CSV_SHA = "7727452b960037bc59fea1f21b7178db557355a9ac618b2f2df6d1c214485f1d"
PROFILES = ("base", "high", "negative", "regime")
PERIODS = (2, 3, 7)
INPUTS = tuple(f"Input {profile}" for profile in PROFILES)
DIAGNOSTICS = tuple(f"{field} {profile} {period}" for profile in PROFILES
                    for period in PERIODS for field in ("Mean", "MeanXX"))
OUTPUTS = tuple(f"{method} {profile} {period}" for profile in PROFILES for period in PERIODS
                for method in ("Variance biased", "Variance sample", "Stdev biased", "Stdev sample"))


def recipe_inputs(source):
    assignments = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "INPUTS" for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError("Variance recipe lacks unique supplied input declaration")
    return ast.literal_eval(assignments[0])


def build_diagnostic(root=ROOT):
    folder = root / "tests/workloads"
    capture = json.loads((folder / (NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("variance_evidence_report", root / "scripts/official_alignment_report.py")
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    reporter.verify_evidence(folder, NAME, capture)
    expected_columns = list(INPUTS)
    for profile in PROFILES:
        for period in PERIODS:
            expected_columns += [f"{method} {profile} {period}" for method in
                                 ("Variance biased", "Variance sample", "Stdev biased", "Stdev sample", "Mean", "MeanXX")]
    if (capture.get("scriptSha256") != SOURCE_SHA or capture.get("columns") != expected_columns
            or len(capture["rows"]) != 64 or capture.get("missingValueToken") != "NA"
            or capture.get("tolerance") != 1e-8 or capture.get("diagnosticOnly") is not False
            or capture.get("sourceExpressionClass") != "native_supplied_scalar_variance_holdout"
            or capture.get("selection") != dict(seed=2026100356, rows=64, firstNativeBarIndex=0,
                profiles=list(PROFILES), periods=list(PERIODS), nativeIndicatorOutputsSuppliedAsInputs=False)
            or capture.get("sourceInputColumns") != list(INPUTS)
            or capture.get("nativeCanonicalOutputColumns") != list(OUTPUTS)
            or capture.get("nativeDiagnosticColumns") != list(DIAGNOSTICS)):
        raise ValueError("Incomplete or incorrectly qualified native variance capture")
    csv_path = folder / (NAME + ".tradingview.csv")
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != CSV_SHA or capture.get("downloadedCsvSha256") != CSV_SHA:
        raise ValueError("Native variance UI download identity differs")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["Date", "Message"]:
            raise ValueError("Native variance UI download columns differ")
        messages = [row["Message"] for row in reader]
    if "\n".join(messages) + "\n" != (folder / (NAME + ".tradingview.txt")).read_text(encoding="utf-8"):
        raise ValueError("Native variance raw log differs from official download")
    source = (folder / (NAME + ".pine")).read_text(encoding="utf-8")
    source_inputs = {profile: [None if token == "float(na)" else float(token)
                    for token in values.split(", ")]
                    for profile, values in re.findall(r"a_(\w+) = array.from\(([^\n]*)\)", source)}
    if (tuple(source_inputs) != PROFILES or any(len(values) != 64 for values in source_inputs.values())
            or [[source_inputs[profile][i] for profile in PROFILES] for i in range(64)]
               != [row["values"][:4] for row in capture["rows"]]):
        raise ValueError("Native variance supplied inputs differ from frozen Pine source")
    for suffix in (".py", "_batch.py"):
        if recipe_inputs((folder / (NAME + suffix)).read_text(encoding="utf-8")) != source_inputs:
            raise ValueError("Runtime variance recipe inputs differ from native source")
    by_column = {name: [row["values"][i] for row in capture["rows"]]
                 for i, name in enumerate(capture["columns"])}
    raw_checks = []
    sqrt_checks = []
    for profile in PROFILES:
        for period in PERIODS:
            means = by_column[f"Mean {profile} {period}"]
            meanxx = by_column[f"MeanXX {profile} {period}"]
            raw = [None if a is None or b is None else max(0., b - a * a) for a, b in zip(means, meanxx)]
            for label, divisor in (("biased", period), ("sample", period - 1)):
                expected = by_column[f"Variance {label} {profile} {period}"]
                proposed = [None if value is None else value if label == "biased" else value * period / divisor
                            for value in raw]
                comparison = reporter.compare_column(expected, proposed, 1e-8)
                raw_checks.append(dict(profile=profile, period=period, bias=label, counts=comparison["counts"],
                                       differences=comparison["differences"]))
                sqrt_values = [None if value is None else math.sqrt(max(0., value)) for value in expected]
                comparison = reporter.compare_column(by_column[f"Stdev {label} {profile} {period}"], sqrt_values, 1e-8)
                sqrt_checks.append(dict(profile=profile, period=period, bias=label, counts=comparison["counts"],
                                        differences=comparison["differences"]))
    return dict(schema="pyne.native-variance-input-and-arithmetic-diagnostic/1", inputCellsVerified=256,
        nativeCanonicalOutputCells=3072, nativeDiagnosticCells=1536, nativeRows=64,
        officialUiCsvSha256=CSV_SHA, sourceInputsIndependentlyReconstructed=True,
        rawMomentHypothesis=dict(checks=raw_checks, differences=sum(x["counts"]["differences"] for x in raw_checks),
            countedAsRuntimeAgreement=False),
        sqrtNativeVarianceHypothesis=dict(checks=sqrt_checks,
            differences=sum(x["counts"]["differences"] for x in sqrt_checks), countedAsRuntimeAgreement=False),
        sampleStdevExecution="sqrt(sample variance) composition; public stdev has no biased parameter",
        directSampleStdevParameterQualified=False, countedAsAdditionalRuntimeAgreement=False,
        acceptanceProved=False,
        qualification="Complete native UI download and all frozen inputs verified. Native-to-native formula discrimination does not qualify private implementation or runtime parity. Selected supplied scalar profiles only; sample stdev is an explicit composition, not an absent public parameter.")
