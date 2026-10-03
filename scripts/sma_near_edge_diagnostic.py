"""Falsify unqualified overflow guards using independently selected ULP inputs."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
NAME = "sma_near_edge_discriminator"
TRIALS = (9, 24, 68, 444)
PERIODS = (7, 7, 3, 3)
WITNESS_INDICES = (30, 13, 13, 14)
TOKENS = ("0.", "ulp", "-ulp", "unit", "-unit", "unit - ulp", "unit + ulp",
          "-unit + ulp", "-unit - ulp", "2. * unit", "-2. * unit",
          "4. * unit - 4. * ulp", "-4. * unit + 4. * ulp")


def selected_codes():
    generator = random.Random(2026100352)
    selected = []
    for trial in range(TRIALS[-1] + 1):
        codes = tuple(generator.randrange(len(TOKENS)) for _ in range(32))
        if trial in TRIALS:
            selected.append(codes)
    return tuple(selected)


def vocabulary():
    unit = 2. ** 1021
    ulp = 2. ** 969
    return (0., ulp, -ulp, unit, -unit, unit - ulp, unit + ulp,
            -unit + ulp, -unit - ulp, 2. * unit, -2. * unit,
            4. * unit - 4. * ulp, -4. * unit + 4. * ulp)


def supplied_inputs():
    values = vocabulary()
    return {f"case{n}": [values[code] for code in codes] for n, codes in enumerate(selected_codes())}


def _modules(root):
    spec = importlib.util.spec_from_file_location("near_edge_masks", root / "scripts/sma_overflow_mask_diagnostic.py")
    masks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(masks)
    helpers, reporter = masks._modules(root)
    return masks, helpers, reporter


def build_diagnostic(root=ROOT):
    masks, helpers, reporter = _modules(root)
    capture, columns = helpers._load(root, reporter, NAME)
    expected_columns = [f"{field} case{n}" for n in range(4)
                        for field in ("Input", "Native", "Sum", "IsNaNative", "IsNaSum")]
    if (capture.get("diagnosticOnly") is not False or len(capture["rows"]) != 32
            or capture["columns"] != expected_columns or capture.get("sourceExpressionClass") != "series_array_lookup"):
        raise ValueError("Incomplete or incorrectly qualified native near-edge evidence")
    source = (root / "tests/workloads" / (NAME + ".pine")).read_text(encoding="utf-8")
    lines = source.splitlines()
    required = ["int i = bar_index", "float unit = math.pow(2., 1021)", "float ulp = math.pow(2., 969)"]
    inputs = supplied_inputs()
    checks, witnesses, bridges = [], [], []
    for n, (codes, period, witness_index) in enumerate(zip(selected_codes(), PERIODS, WITNESS_INDICES, strict=True)):
        profile = f"case{n}"
        values = inputs[profile]
        if columns["Input " + profile] != values or not all(math.isfinite(value) for value in values):
            raise ValueError("Independent finite near-edge input identity differs")
        required += [f"var supplied{n} = array.from(" + ", ".join(TOKENS[code] for code in codes) + ")",
                     f"float src{n} = array.get(supplied{n}, i % 32)",
                     f"float native{n} = ta.sma(src{n}, {period})", f"float sum{n} = math.sum(src{n}, {period})",
                     f"int missingNative{n} = na(native{n}) ? 1 : 0", f"int missingSum{n} = na(sum{n}) ? 1 : 0"]
        for field in ("Native", "Sum"):
            if columns["IsNa" + field + " " + profile] != [int(value is None) for value in columns[field + " " + profile]]:
                raise ValueError("Near-edge native state contradicts numeric log")
        bridge = reporter.compare_column(columns["Native " + profile],
                    [None if value is None else value / period for value in columns["Sum " + profile]], 0.)
        if bridge["counts"]["differences"]:
            raise ValueError("Selected near-edge native sum/mean bridge differs")
        bridges.append(dict(profile=profile, period=period, comparison=bridge))
        for model in masks.MODELS:
            predicted = masks.candidate_masks(values, period, model)
            for field in ("Native", "Sum"):
                indices = [i for i, (actual, candidate) in enumerate(zip(columns["IsNa" + field + " " + profile], predicted, strict=True))
                           if actual != candidate]
                checks.append(dict(profile=profile, period=period, model=model, field=field,
                                   cells=32, differences=len(indices), differingIndices=indices,
                                   qualifiedAsRuntimeReplacement=False))
        carry = masks.candidate_masks(values, period, "remove_add")
        kahan = masks.candidate_masks(values, period, "kahan_remove_add")
        if next(i for i in range(32) if carry[i] != kahan[i]) != witness_index:
            raise ValueError("Preselected independent model disagreement differs")
        observed = int(columns["Native " + profile][witness_index] is None)
        if observed != (1, 0, 0, 1)[n]:
            raise ValueError("Retained native near-edge falsification witness differs")
        witnesses.append(dict(profile=profile, period=period, index=witness_index,
            nativeSma=columns["Native " + profile][witness_index], nativeSum=columns["Sum " + profile][witness_index],
            nativeMissing=observed, removeAddMissing=carry[witness_index], kahanMissing=kahan[witness_index],
            rejectedModel="remove_add" if carry[witness_index] != observed else "kahan_remove_add",
            countedAsAdditionalRuntimeAgreement=False))
    if any(line not in lines for line in required):
        raise ValueError("Executed near-edge input/state formula differs")
    totals = {model: sum(c["differences"] for c in checks if c["model"] == model) for model in masks.MODELS}
    return dict(schema="pyne.native-near-edge-diagnostic/1", inputCellsVerified=128,
                nativeNumericOutputCells=256, nativeStateFlagCells=256,
                selection=dict(seed=2026100352, trials=list(TRIALS), periods=list(PERIODS),
                               nativeOutputsUsedAsInputs=False),
                candidateStateComparisons=checks, candidateStateDifferenceTotals=totals,
                falsificationWitnesses=witnesses, nativeMeanSumBridge=bridges,
                uniformRemoveAddGuardRejected=True, uniformKahanGuardRejected=True,
                piecewisePeriodGuardQualified=False, runtimeChanged=False,
                acceptanceProved=False, goalStatus="active",
                qualification="Inputs reproduce candidate-only preselection independently. Numeric outputs enter the separate canonical runtime comparison once per mode; state controls add no parity cells. Both uniform overflow guards have independent native counterexamples. A period-specific fit selected after these observations is not an independent replacement qualification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_diagnostic()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result["candidateStateDifferenceTotals"]))
    print(json.dumps(result["falsificationWitnesses"], allow_nan=False))


if __name__ == "__main__":
    main()
