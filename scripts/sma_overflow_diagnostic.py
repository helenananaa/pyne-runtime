"""Confirm native missing states separately from finite safe-mean controls."""
from __future__ import annotations

import argparse
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("positive", "negative", "mixed", "recovery")


def input_profiles(index):
    large = 160000000.0 * (10. ** 300)
    return dict(positive=large, negative=-large, mixed=large if index % 2 == 0 else -large,
                recovery=large if index < 6 else float((index * 11) % 17 - 6) * .25)


def _modules(root):
    spec = importlib.util.spec_from_file_location("sma_overflow_helpers", root / "scripts/sma_arithmetic_diagnostic.py")
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers, helpers._reporter(root)


def safe_mean(values, period):
    outputs = []
    for i in range(len(values)):
        if i < period - 1:
            outputs.append(None)
            continue
        total = 0.
        for value in values[i-period+1:i+1]:
            total += value / period
        outputs.append(total)
    return outputs


def build_diagnostic(root: Path = ROOT):
    helpers, reporter = _modules(root)
    capture, columns = helpers._load(root, reporter, "sma_finite_overflow")
    guard, states = helpers._load(root, reporter, "sma_overflow_state_guard")
    if (len(capture["rows"]) != 24 or len(capture["columns"]) != 32 or
            len(guard["rows"]) != 24 or len(guard["columns"]) != 64 or guard.get("diagnosticOnly") is not True):
        raise ValueError("Incomplete or incorrectly qualified native overflow evidence")
    supplied = [input_profiles(i) for i in range(24)]
    controls = []
    guard_cells = finite_reference_missing = fully_small_tail_missing = 0
    missing_profiles = []
    for profile in PROFILES:
        values = [row[profile] for row in supplied]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Overflow probe must supply finite inputs")
        if columns["Input " + profile] != values or states["Input " + profile] != values:
            raise ValueError("Independent finite input identity differs")
        for field in ("Native1", "Native2", "Native3", "Sum2", "Sum3"):
            native = columns[field + " " + profile]
            for index, value in enumerate(native):
                missing = int(value is None)
                if states[f"IsNa {field} {profile}"][index] != missing:
                    raise ValueError("Native na() state contradicts separately captured numeric log")
                # Nonzero halving invariance would reveal a state not represented by these finite/NA logs.
                if states[f"HalfInvariant {field} {profile}"][index] != 0:
                    raise ValueError("Native halving state requires separate nonfinite qualification")
                if states[f"Negative {field} {profile}"][index] != int(value is not None and value < 0):
                    raise ValueError("Native sign state contradicts separately captured numeric log")
                guard_cells += 3
        if columns["Native1 " + profile] != values:
            raise ValueError("Native period-one output differs from supplied finite input")
        for period in (2, 3):
            calculated = safe_mean(values, period)
            control = reporter.compare_column(columns[f"Safe{period} {profile}"], calculated, 0.)
            if control["counts"]["differences"]:
                raise ValueError("Independent Python safe mean differs from separately executed Pine control")
            controls.append(dict(title=f"Safe{period} {profile}", comparison=control))
            native = columns[f"Native{period} {profile}"]
            missing_count = tail_count = 0
            for index in range(period-1, 24):
                window = values[index-period+1:index+1]
                exact = float(sum((Fraction.from_float(value) for value in window), Fraction()) / period)
                if not math.isfinite(exact):
                    raise ValueError("Exact supplied-window mean unexpectedly nonfinite")
                if native[index] is None:
                    finite_reference_missing += 1
                    missing_count += 1
                    if profile == "recovery" and index >= 6 + period - 1:
                        fully_small_tail_missing += 1
                        tail_count += 1
            missing_profiles.append(dict(profile=profile, period=period,
                                         nativeMissingAfterFullWindow=missing_count, fullySmallTailMissing=tail_count))
    return dict(schema="pyne.native-sma-finite-overflow-diagnostic/1", inputCellsVerified=192,
                nativeStateGuardCellsVerified=guard_cells,
                pythonPineSafeControls=dict(cells=sum(c["comparison"]["counts"]["cells"] for c in controls), differences=0),
                finiteExactMeanNativeMissing=finite_reference_missing, fullySmallTailNativeMissing=fully_small_tail_missing,
                missingProfiles=missing_profiles, canonicalNativeOutputs=12, excludedControls=20,
                runtimeChanged=False, acceptanceProved=False, goalStatus="active",
                qualification="Native missing masks are confirmed by a separately executed na()/halving/sign probe. Exact and scaled means are references, not native agreement. All 12 original native SMA outputs enter the separate canonical runtime assessment.",
                limits=["Four fixed extreme-finite profiles do not establish general native overflow recovery.",
                        "Native missing values after overflow do not qualify a guessed permanent poison implementation.",
                        "No runtime finite-mean or snapshot contract is changed by this diagnostic."])


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
