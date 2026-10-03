"""Falsify overflow update orders without substituting a guessed native kernel."""
from __future__ import annotations

import argparse
from collections import deque
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("half", "negativeHalf", "rotation", "negativeRotation", "recovery", "gapRecovery")


def input_profiles(i):
    large = 160000000.0 * (10. ** 300)
    half = 80000000.0 * (10. ** 300)
    return dict(half=half, negativeHalf=-half,
                rotation=-large if i % 3 == 1 else large,
                negativeRotation=large if i % 3 == 1 else -large,
                recovery=large if i < 6 else float((i * 11) % 17 - 6) * .25,
                gapRecovery=large if i < 6 else None if i < 12 else float((i * 11) % 17 - 6) * .25)


def rolling_mean(values, period, order):
    """An independently initialized uncompensated sum candidate, not native state."""
    window = deque()
    total = 0.
    outputs = []
    for value in values:
        if value is not None:
            outgoing = window.popleft() if len(window) == period else 0.
            if order == "remove_then_add":
                total = (total - outgoing) + value
            elif order == "add_then_remove":
                total = (total + value) - outgoing
            else:
                raise ValueError("Unknown candidate update order")
            window.append(value)
        outputs.append(total / period if len(window) == period else None)
    return outputs


def _modules(root):
    spec = importlib.util.spec_from_file_location("sma_update_helpers", root / "scripts/sma_arithmetic_diagnostic.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers, helpers._reporter(root)


def build_diagnostic(root: Path = ROOT):
    helpers, reporter = _modules(root)
    capture, columns = helpers._load(root, reporter, "sma_overflow_update_order")
    guard, states = helpers._load(root, reporter, "sma_overflow_order_guard")
    if (len(capture["rows"]) != 32 or len(capture["columns"]) != 42 or capture.get("diagnosticOnly") is not False
            or len(guard["rows"]) != 32 or len(guard["columns"]) != 48 or guard.get("diagnosticOnly") is not True):
        raise ValueError("Incomplete or incorrectly qualified native update-order evidence")
    supplied = [input_profiles(i) for i in range(32)]
    guard_cells = input_cells = 0
    bridge = []
    models = []
    witnesses = []
    recovery_missing = []
    for profile in PROFILES:
        values = [row[profile] for row in supplied]
        if columns["Input " + profile] != values or any(v is not None and not math.isfinite(v) for v in values):
            raise ValueError("Independent finite/missing input identity differs")
        input_cells += len(values)
        for field in ("Native2", "Native3", "Sum2", "Sum3"):
            native = columns[field + " " + profile]
            for index, value in enumerate(native):
                if states[f"IsNa {field} {profile}"][index] != int(value is None):
                    raise ValueError("Independent native na() state contradicts numeric log")
                guard_cells += 1
                if field.startswith("Sum"):
                    if states[f"HalfInvariant {field} {profile}"][index] != 0:
                        raise ValueError("Native nonfinite state requires separate qualification")
                    if states[f"Negative {field} {profile}"][index] != int(value is not None and value < 0):
                        raise ValueError("Independent native sign state contradicts numeric log")
                    guard_cells += 2
        for period in (2, 3):
            native = columns[f"Native{period} {profile}"]
            if columns[f"IsNa{period} {profile}"] != [int(v is None) for v in native]:
                raise ValueError("Same-capture na() state contradicts numeric log")
            sum_mean = [None if v is None else v / period for v in columns[f"Sum{period} {profile}"]]
            bridge.append(dict(profile=profile, period=period, comparison=reporter.compare_column(native, sum_mean, 0.)))
            for order in ("remove_then_add", "add_then_remove"):
                calculated = rolling_mean(values, period, order)
                models.append(dict(profile=profile, period=period, order=order,
                                   comparison=reporter.compare_column(native, calculated, 0.)))
            if (profile in ("half", "negativeHalf") and period == 2
                    or profile in ("rotation", "negativeRotation") and period == 3):
                index = 2 if period == 2 else 3
                add = rolling_mean(values, period, "add_then_remove")[index]
                remove = rolling_mean(values, period, "remove_then_add")[index]
                if math.isfinite(add) or not math.isfinite(remove) or native[index] != remove:
                    raise ValueError("Independent ordered-overflow witness differs")
                witnesses.append(dict(profile=profile, period=period, index=index, native=native[index],
                                      addThenRemove=add, removeThenAdd=remove))
            if profile in ("recovery", "gapRecovery"):
                first_small = 6 if profile == "recovery" else 12
                indices = [i for i in range(first_small + period - 1, 32) if native[i] is None]
                recovery_missing.append(dict(profile=profile, period=period, fullySmallWindowMissingIndices=indices))
    bridge_counts = {key: sum(item["comparison"]["counts"][key] for item in bridge)
                     for key in bridge[0]["comparison"]["counts"]}
    return reporter.json_safe_numbers(dict(schema="pyne.native-sma-update-order-diagnostic/1",
        inputCellsVerified=input_cells, nativeStateGuardCellsVerified=guard_cells,
        nativeMeanSumBridge=dict(counts=bridge_counts, checks=bridge, universalIdentityQualified=False),
        addBeforeRemoveFalsification=dict(cells=len(witnesses), witnesses=witnesses, countedAsRuntimeAgreement=False),
        candidateComparisons=models, recoveryMissing=recovery_missing,
        canonicalNativeOutputs=24, excludedControls=18, runtimeChanged=False, acceptanceProved=False, goalStatus="active",
        qualification="Independent initial-state arithmetic candidates and separate native guards constrain update order. Candidate matches and native-to-native bridges are not Pyne agreement. All 24 native SMA/sum outputs enter the separate canonical assessment; callback sums recompute supplied history.",
        limits=["Finite native outputs reject simple add-before-remove; they do not reconstruct compensated state.",
                "Thirty-two observed rows do not establish permanent poisoning or long-history recovery.",
                "These six profiles do not isolate native optimizer, qualifier or multi-length call interactions.",
                "The earlier finite-data SMA=sum/length bridge is not universal at extreme finite magnitudes."]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_diagnostic()
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
