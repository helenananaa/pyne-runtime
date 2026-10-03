"""Retain falsified rolling-sum models and an exact native sum/mean bridge."""
from __future__ import annotations

import argparse
from collections import deque
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "sma_period_two_independent_holdout"


def input_profiles(index):
    base = float((index * 13) % 23 - 10) * .25
    power = 2.**80 + base * 2.**28
    return dict(base=base, offset=1.e12 + base, power=power,
                prefill=power if index < 13 else base,
                negative=-power if index < 13 else base,
                mixed=power if index % 4 == 0 else -power if index % 4 == 1 else base,
                holes=None if index >= 13 and index % 9 in (1, 4, 5)
                else power if index < 13 else base,
                leading=None if index < 5 else 1.e12 + base, empty=None,
                singleGap=None if index == 17 else 1.e12 + base if index < 25 else base,
                alternate=power if index % 2 == 0 else None,
                regime=power if index < 24 else base if index < 48 else -power if index < 72 else base)


def kahan_remove_add(values, period):
    total = correction = 0.
    window = deque()
    outputs = []
    for value in values:
        if value is not None:
            if len(window) == period:
                adjusted = -window.popleft() - correction
                updated = total + adjusted
                correction = (updated - total) - adjusted
                total = updated
            adjusted = float(value) - correction
            updated = total + adjusted
            correction = (updated - total) - adjusted
            total = updated
            window.append(float(value))
        outputs.append(total / period if len(window) == period else None)
    return outputs


def pair_mean(values):
    previous = latest = None
    outputs = []
    for value in values:
        if value is not None:
            if previous is not None:
                latest = (previous + float(value)) / 2.
            previous = float(value)
        outputs.append(latest)
    return outputs


def _reporter(root):
    spec = importlib.util.spec_from_file_location("sma_diagnostic_reporter", root / "scripts/official_alignment_report.py")
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    return reporter


def _load(root, reporter, name):
    folder = root / "tests/workloads"
    capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, name, capture)
    columns = {title: [row["values"][index] for row in capture["rows"]]
               for index, title in enumerate(capture["columns"])}
    if len(columns) != len(capture["columns"]):
        raise ValueError("Duplicate native arithmetic column")
    return capture, columns


def history_source_checks(root, reporter, previous):
    capture, columns = _load(root, reporter, "sma_history_sources")
    if len(capture["rows"]) != 40 or len(capture["columns"]) != 48 or capture.get("diagnosticOnly") is not True:
        raise ValueError("Incomplete or incorrectly qualified native source-history diagnostic")
    generated = [input_profiles(i) for i in range(40)]
    checks = {name: [] for name in ("inputAndHistoryIdentity", "independentPairArithmetic",
                                   "nativeMeanSumDivision", "independentNativeRecapture", "nativeDyadicScaling")}
    for profile in ("power", "prefill", "holes", "regime"):
        values = [row[profile] for row in generated]
        for field, offset in (("Input", 0), ("History1", 1), ("History2", 2), ("Array1", 1), ("Array2", 2)):
            expected = [None if i < offset else values[i-offset] for i in range(40)]
            comparison = reporter.compare_column(expected, columns[field + " " + profile], 0.)
            if comparison["counts"]["differences"]:
                raise ValueError(f"Independent source/history input differs: {field} {profile}")
            checks["inputAndHistoryIdentity"].append(dict(title=field + " " + profile, comparison=comparison))
        pair = [None if i == 0 or values[i] is None or values[i-1] is None
                else (values[i] + values[i-1]) / 2. for i in range(40)]
        for field in ("PairHistory", "PairArray"):
            checks["independentPairArithmetic"].append(dict(title=field + " " + profile,
                comparison=reporter.compare_column(pair, columns[field + " " + profile], 0.)))
        for period in (2, 3):
            title = f"Native{period} {profile}"
            native = columns[title]
            sums = [None if value is None else value / period for value in columns[f"Sum{period} {profile}"]]
            checks["nativeMeanSumDivision"].append(dict(title=title, comparison=reporter.compare_column(native, sums, 0.)))
            checks["independentNativeRecapture"].append(dict(title=title,
                comparison=reporter.compare_column(previous[title][:40], native, 0.)))
        checks["nativeDyadicScaling"].append(dict(title=profile,
            comparison=reporter.compare_column(columns["Native2 " + profile], columns["Scaled2 " + profile], 0.)))
    summaries = {name: dict(cells=sum(item["comparison"]["counts"]["cells"] for item in entries),
                            differences=sum(item["comparison"]["counts"]["differences"] for item in entries),
                            checks=entries) for name, entries in checks.items()}
    return dict(**summaries, countedAsRuntimeAgreement=False,
                qualification="New authenticated native recapture checks observable history, array and pair arithmetic; repeated profiles and native sum/scaling identities do not add runtime agreement.")


def build_diagnostic(root: Path = ROOT):
    reporter = _reporter(root)
    capture, columns = _load(root, reporter, NAME)
    if len(capture["rows"]) != 96 or len(capture["columns"]) != 72:
        raise ValueError("Incomplete independent SMA holdout")
    generated = [input_profiles(i) for i in range(96)]
    profiles = list(generated[0])
    for profile in profiles:
        if columns[f"Input {profile}"] != [row[profile] for row in generated]:
            raise ValueError(f"Independent input identity differs: {profile}")
    controls = []
    models = []
    for kind, period, function in (("Candidate2", 2, kahan_remove_add),
                                  ("Candidate3", 3, kahan_remove_add), ("Pair2", 2, None)):
        comparisons = {}
        for profile in profiles:
            values = [row[profile] for row in generated]
            calculated = function(values, period) if function is not None else pair_mean(values)
            control = reporter.compare_column(columns[f"{kind} {profile}"], calculated, 0.)
            if control["counts"]["differences"]:
                raise ValueError("Python candidate does not reproduce its separately executed Pine control")
            controls.append(dict(title=f"{kind} {profile}", comparison=control))
            comparisons[profile] = reporter.compare_column(columns[f"Native{period} {profile}"], calculated, 0.)
        models.append(dict(name=kind, cells=1152,
                           differences=sum(c["counts"]["differences"] for c in comparisons.values()),
                           profiles=comparisons))
    previous_fit = []
    for name, sources in (("correlation_reduction_order", ("xx", "xy", "yy")),
                          ("sma_history_arithmetic", ("base", "power", "prefill", "negativePrefill", "holes", "prefillHoles"))):
        _, old_columns = _load(root, reporter, name)
        for profile in sources:
            comparison = reporter.compare_column(old_columns[f"Native {profile} 2"],
                                                   kahan_remove_add(old_columns[profile], 2), 0.)
            previous_fit.append(dict(capture=name, profile=profile, comparison=comparison))
    arithmetic, moments = _load(root, reporter, "correlation_arithmetic_decomposition")
    mean_sum_checks = []
    for title in arithmetic["columns"]:
        prefix = title.split(" ", 1)[0]
        suffix = title[len(prefix):]
        pairs = {"MeanA": "SumA", "MeanB": "SumB", "MeanXX": "SumXX", "MeanYY": "SumYY", "MeanXY": "SumXY"}
        if prefix not in pairs:
            continue
        period = int(title.rsplit(" ", 1)[1])
        divided = [None if value is None else value / period for value in moments[pairs[prefix] + suffix]]
        comparison = reporter.compare_column(moments[title], divided, 0.)
        mean_sum_checks.append(dict(title=title, comparison=comparison))
    return dict(schema="pyne.sma-arithmetic-diagnostic/1", inputCellsVerified=1152,
                nativeSourceHistoryChecks=history_source_checks(root, reporter, columns),
                pythonPineControls=dict(cells=sum(c["comparison"]["counts"]["cells"] for c in controls),
                                        differences=sum(c["comparison"]["counts"]["differences"] for c in controls)),
                olderFiniteFit=dict(profiles=previous_fit,
                    cells=sum(p["comparison"]["counts"]["cells"] for p in previous_fit),
                    differences=sum(p["comparison"]["counts"]["differences"] for p in previous_fit)),
                independentHoldout=models,
                nativeMeanSumDivision=dict(checks=mean_sum_checks,
                    cells=sum(p["comparison"]["counts"]["cells"] for p in mean_sum_checks),
                    differences=sum(p["comparison"]["counts"]["differences"] for p in mean_sum_checks)),
                canonicalNativeOutputs=24, excludedInputAndFormulaControls=48,
                runtimeChanged=False, acceptanceProved=False, goalStatus="active",
                qualification="Python/Pine formula controls and native mean/sum identities explain or falsify models; none count as runtime numeric agreement. All 24 actual native outputs enter the separate canonical assessment.",
                limits=["768 older exact candidate cells do not qualify the failing independent holdout.",
                        "Native SMA equals captured native math.sum / length on these 2560 fields; the rolling-sum implementation remains unreconstructed.",
                        "No unobserved source values, native moment outputs or expected means are injected into runtime recipes."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_diagnostic()
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
