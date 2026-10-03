"""Keep a preselected native counterexample to sticky window recomputation."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "sma_overflow_discriminator"
COEFFICIENTS = (0, -2, 0, 4, -3, 3, 0, 0, None, -2, 0, 4, 2, 3, -3, None,
                -1, 3, 4, -3, None, -2, -1, -4, 0, -3, -3, None, -3, -1, -2, None)
SMALL = {8: .25, 15: .25, 20: -.5, 27: -.5, 31: -.5}


def input_at(i):
    index = i % 32
    return SMALL[index] if index in SMALL else COEFFICIENTS[index] * (2. ** 1021)


def _modules(root):
    spec = importlib.util.spec_from_file_location("overflow_discriminator_models", root / "scripts/sma_overflow_mask_diagnostic.py")
    masks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(masks)
    helpers, reporter = masks._modules(root)
    return masks, helpers, reporter


def build_diagnostic(root=ROOT):
    masks, helpers, reporter = _modules(root)
    capture, columns = helpers._load(root, reporter, NAME)
    if (capture.get("diagnosticOnly") is not False or len(capture["rows"]) != 32
            or capture["columns"] != ["Input", "Native7", "Sum7", "IsNaNative7", "IsNaSum7"]
            or capture.get("sourceExpressionClass") != "series_array_lookup"):
        raise ValueError("Incomplete or incorrectly qualified native discriminator")
    values = [input_at(i) for i in range(32)]
    if columns["Input"] != values:
        raise ValueError("Independent discriminator inputs differ")
    source = (root / "tests/workloads" / (NAME + ".pine")).read_text(encoding="utf-8")
    tokens = [str(SMALL[i]) if i in SMALL else "0." if coefficient == 0
              else "unit" if coefficient == 1 else "-unit" if coefficient == -1
              else f"{coefficient}. * unit" for i, coefficient in enumerate(COEFFICIENTS)]
    required = ("int i = bar_index", "float unit = math.pow(2., 1021)",
                "var supplied = array.from(" + ", ".join(tokens) + ")",
                "float src = array.get(supplied, i % 32)", "float native7 = ta.sma(src, 7)",
                "float sum7 = math.sum(src, 7)", "int missingNative7 = na(native7) ? 1 : 0",
                "int missingSum7 = na(sum7) ? 1 : 0")
    if any(line not in source.splitlines() for line in required):
        raise ValueError("Executed discriminator input or state formula differs")
    for field in ("Native7", "Sum7"):
        if columns["IsNa" + field] != [int(v is None) for v in columns[field]]:
            raise ValueError("Discriminator native state contradicts numeric log")
    bridge = reporter.compare_column(columns["Native7"],
                                    [None if value is None else value / 7 for value in columns["Sum7"]], 0.)
    if bridge["counts"]["differences"]:
        raise ValueError("Selected native sum/mean bridge differs")
    checks = []
    for model in masks.MODELS:
        predicted = masks.candidate_masks(values, 7, model)
        for field in ("Native7", "Sum7"):
            indices = [i for i, (native, candidate) in enumerate(zip(columns["IsNa" + field], predicted, strict=True))
                       if native != candidate]
            checks.append(dict(model=model, field=field, cells=32, differences=len(indices),
                               differingIndices=indices, qualifiedAsRuntimeReplacement=False))
    index = 16
    if columns["Native7"][index] is None or columns["Sum7"][index] is None:
        raise ValueError("Preselected finite native counterexample differs")
    sticky = masks.candidate_masks(values, 7, "sticky_window_recompute")
    if sticky[index] != 1:
        raise ValueError("Independent sticky-window counterexample prediction differs")
    return dict(schema="pyne.native-overflow-discriminator/1", inputCellsVerified=32,
                nativeNumericOutputCells=64, nativeStateFlagCells=64,
                selection="Candidate-only deterministic disagreement selected before native execution; native outputs were not supplied as recipe inputs.",
                candidateMaskComparisons=checks, nativeMeanSumBridge=bridge,
                stickyWindowFalsification=dict(index=index, period=7, nativeSma=columns["Native7"][index],
                    nativeSum=columns["Sum7"][index], predictedMissing=sticky[index], nativeMissing=0,
                    rejected=True, countedAsAdditionalRuntimeAgreement=False),
                runtimeChanged=False, acceptanceProved=False, goalStatus="active",
                qualification="The numeric outputs enter the separate canonical runtime assessment once per mode. State and candidate controls do not add numeric parity cells. One finite witness rejects sticky recomputation but cannot qualify another arithmetic kernel or a permanent-poison rule.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_diagnostic()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result["stickyWindowFalsification"], allow_nan=False))
    print(json.dumps({model: sum(c["differences"] for c in result["candidateMaskComparisons"] if c["model"] == model)
                      for model in dict.fromkeys(c["model"] for c in result["candidateMaskComparisons"])}))


if __name__ == "__main__":
    main()
