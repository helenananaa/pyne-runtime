"""Independent equal-window witnesses and explicit binary64 sum hypotheses."""
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
NAME = "sum_history_prefix_holdout"
SOURCE_SHA = "55bb74fa5b3e4691d405930e4b357c5bc52442cd8fc10dc49c361e9641d59221"
CSV_SHA = "9ba919729e2564ff4d8248b2079203925c7798cc1c18a8ad707beed21a7fad76"
PROFILES = ("high", "zero", "negative")
PERIODS = (2, 3)
STYLES = ("forward", "reverse", "ascending_magnitude", "descending_magnitude", "pairwise", "recursive_pairwise")


def explicit_fold(values, style="forward"):
    values = list(values)
    if style == "reverse":
        values.reverse()
    elif style == "ascending_magnitude":
        values.sort(key=abs)
    elif style == "descending_magnitude":
        values.sort(key=abs, reverse=True)
    if style == "pairwise":
        while len(values) > 1:
            values = [values[i] + values[i + 1] if i + 1 < len(values) else values[i]
                      for i in range(0, len(values), 2)]
        return values[0] if values else 0.
    if style == "recursive_pairwise":
        if len(values) < 2:
            return values[0] if values else 0.
        midpoint = len(values) // 2
        return explicit_fold(values[:midpoint], style) + explicit_fold(values[midpoint:], style)
    if style not in STYLES:
        raise ValueError("Unknown explicit addition tree")
    total = 0.
    for value in values:
        total = total + value
    return total


def candidate_sums(values, period, style):
    window = deque()
    total = 0.
    compensation = 0.
    result = []

    def add(value):
        nonlocal total, compensation
        delta = value - compensation
        next_value = total + delta
        compensation = (next_value - total) - delta
        total = next_value

    for value in values:
        if value is not None:
            if style == "kahan_remove_add":
                if len(window) == period:
                    add(-window.popleft())
                add(value)
                window.append(value)
            else:
                window.append(value)
                if len(window) > period:
                    window.popleft()
                total = explicit_fold(window, style)
        result.append(None if len(window) < period else total)
    return result


def build_diagnostic(root=ROOT):
    folder = root / "tests/workloads"
    spec = importlib.util.spec_from_file_location("sum_prefix_operations", root / "scripts/variance_source_operations_diagnostic.py")
    operations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(operations)
    operations.build_diagnostic(root)
    reporter = operations.load_script(root, "official_alignment_report.py", "sum_prefix_report")
    capture = json.loads((folder / (NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, NAME, capture)
    expected_columns = [f"Input {profile}" for profile in PROFILES]
    expected_columns += [f"{field} {profile} {period}" for profile in PROFILES
                         for period in PERIODS for field in ("Mean", "Sum")]
    if (capture.get("scriptSha256") != SOURCE_SHA or capture.get("columns") != expected_columns
            or len(capture["rows"]) != 32 or capture.get("diagnosticOnly") is not True
            or capture.get("sourceExpressionClass") != "native_supplied_sum_history_prefix_holdout"
            or capture.get("missingValueToken") != "NA" or capture.get("tolerance") != 1e-8
            or capture.get("selection") != dict(rows=32, firstNativeBarIndex=0,
                profiles=list(PROFILES), periods=list(PERIODS), sourceInputsOnly=True)):
        raise ValueError("Native prefix sum capture qualification differs")
    csv_path = folder / (NAME + ".tradingview.csv")
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != CSV_SHA or capture.get("downloadedCsvSha256") != CSV_SHA:
        raise ValueError("Native prefix sum UI download identity differs")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["Date", "Message"]:
            raise ValueError("Native prefix sum download columns differ")
        records = list(reader)
    if len(records) != 32 or "\n".join(row["Message"] for row in records) + "\n" != (
            folder / (NAME + ".tradingview.txt")).read_text(encoding="utf-8"):
        raise ValueError("Native prefix sum raw log differs from download")
    for index, row in enumerate(records):
        stamp = datetime.fromisoformat(row["Date"]).astimezone(timezone.utc)
        if (stamp.year * 12 + stamp.month != 2017 * 12 + 8 + index
                or (stamp.day, stamp.hour, stamp.minute, stamp.second) != (1, 0, 0, 0)):
            raise ValueError("Native prefix sum monthly selection differs")
    source = (folder / (NAME + ".pine")).read_text(encoding="utf-8")
    inputs = {profile: [None if token == "float(na)" else float(token) for token in values.split(", ")]
              for profile, values in re.findall(r"a_(\w+) = array.from\(([^\n]*)\)", source)}
    tail = [1., 2., 3., 4., None, 5., 6., 7., 8., None, 9., 10., 11., 12., 13., 14.,
            15., 16., None, 17., 18., 19., 20., 21., 22., 23., 24., 25., 26., 27.]
    if inputs != {profile: [prefix, prefix, *tail] for profile, prefix in zip(PROFILES, (1e18, 0., -1e18))}:
        raise ValueError("Native prefix sum frozen inputs differ")
    columns = {name: [row["values"][i] for row in capture["rows"]] for i, name in enumerate(expected_columns)}
    if any(columns[f"Input {profile}"] != inputs[profile] for profile in PROFILES):
        raise ValueError("Native prefix sum captured inputs differ")
    pair_checks = []
    for profile in ("high", "negative"):
        for period in PERIODS:
            left = deque()
            right = deque()
            indices = []
            for index, (a, b) in enumerate(zip(inputs[profile], inputs["zero"])):
                if a is not None:
                    left.append(a)
                    right.append(b)
                    if len(left) > period:
                        left.popleft()
                        right.popleft()
                if len(left) == period and left == right:
                    indices.append(index)
            for field in ("Mean", "Sum"):
                comparison = reporter.compare_column([columns[f"{field} zero {period}"][i] for i in indices],
                    [columns[f"{field} {profile} {period}"][i] for i in indices], 1e-8)
                pair_checks.append(dict(profile=profile, period=period, field=field, nativeIndices=indices,
                                        counts=comparison["counts"], differences=comparison["differences"]))
    candidate_checks = []
    for profile in PROFILES:
        for period in PERIODS:
            proposed = candidate_sums(inputs[profile], period, "kahan_remove_add")
            for field in ("Mean", "Sum"):
                values = proposed if field == "Sum" else [None if value is None else value / period for value in proposed]
                comparison = reporter.compare_column(columns[f"{field} {profile} {period}"], values, 1e-8)
                candidate_checks.append(dict(profile=profile, period=period, field=field,
                                             counts=comparison["counts"], differences=comparison["differences"]))
    old = json.loads((folder / "variance_source_operations.tradingview.json").read_text(encoding="utf-8"))
    old_columns = {name: [row["values"][i] for row in old["rows"]] for i, name in enumerate(old["columns"])}
    old_checks = []
    for style in (*STYLES, "kahan_remove_add"):
        cases = []
        for profile in operations.PROFILES:
            for period in operations.PERIODS:
                values = [None if value is None else value * value for value in old_columns[f"Input {profile}"]]
                proposed = candidate_sums(values, period, style)
                comparison = reporter.compare_column(old_columns[f"SumXX {profile} {period}"], proposed, 0.)
                cases.append(dict(profile=profile, period=period, counts=comparison["counts"],
                                  differences=comparison["differences"]))
        old_checks.append(dict(style=style, cells=768, cases=cases,
                               differences=sum(case["counts"]["differences"] for case in cases)))
    return dict(schema="pyne.native-sum-history-prefix-diagnostic/1", nativeRows=32,
        inputCellsVerified=96, nativeDiagnosticOutputCells=384, officialUiCsvSha256=CSV_SHA,
        equalCurrentWindowNativePairs=pair_checks,
        equalWindowPairedCells=sum(case["counts"]["cells"] for case in pair_checks),
        equalWindowNativeDifferences=sum(case["counts"]["differences"] for case in pair_checks),
        kahanRemoveAddHoldout=dict(checks=candidate_checks, comparedCells=384,
            differences=sum(case["counts"]["differences"] for case in candidate_checks)),
        priorNativeSumChecks=old_checks, additionsExplicitlyDefined=True,
        nativeIndicatorValuesSuppliedToRuntime=False, countedAsAdditionalRuntimeAgreement=False,
        privateImplementationProved=False, replacementAccumulatorQualified=False, acceptanceProved=False,
        qualification="Independent prefixes, identical current nonmissing windows and literal source inputs only. Prefix-dependent native witnesses refute pure window recomputation for these captures. Explicit addition trees avoid version-dependent built-in sum; compensated state can match a selected holdout while retaining prior counterexamples. No extra runtime agreement or universal implementation claim.")
