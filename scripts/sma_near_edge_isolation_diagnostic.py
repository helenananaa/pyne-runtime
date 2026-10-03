"""Verify native recaptures after separating the four near-edge call sites."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAMES = tuple(f"sma_near_edge_isolated_case{n}" for n in range(4))
FIELDS = ("Input", "Native", "Sum", "IsNaNative", "IsNaSum")


def _previous(root):
    spec = importlib.util.spec_from_file_location("near_edge_isolation_previous", root / "scripts/sma_near_edge_diagnostic.py")
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    return previous


def build_diagnostic(root=ROOT):
    previous = _previous(root)
    baseline_diagnostic = previous.build_diagnostic(root)
    _, helpers, reporter = previous._modules(root)
    _, combined = helpers._load(root, reporter, previous.NAME)
    inputs = previous.supplied_inputs()
    checks = []
    for n, (name, codes, period) in enumerate(zip(NAMES, previous.selected_codes(), previous.PERIODS, strict=True)):
        capture, columns = helpers._load(root, reporter, name)
        if (capture.get("diagnosticOnly") is not True or capture.get("countedAsAdditionalRuntimeAgreement") is not False
                or capture.get("sourceExpressionClass") != "series_array_lookup_isolated_calls"
                or capture.get("period") != period or len(capture["rows"]) != 32
                or capture["columns"] != list(FIELDS) or capture.get("tolerance") != 0.):
            raise ValueError("Incomplete or incorrectly qualified isolated near-edge capture")
        source = (root / "tests/workloads" / (name + ".pine")).read_text(encoding="utf-8")
        required = ["int i = bar_index", "float unit = math.pow(2., 1021)", "float ulp = math.pow(2., 969)",
            "var supplied = array.from(" + ", ".join(previous.TOKENS[code] for code in codes) + ")",
            "float src = array.get(supplied, i % 32)", f"float native = ta.sma(src, {period})",
            f"float summed = math.sum(src, {period})", "int missingNative = na(native) ? 1 : 0",
            "int missingSum = na(summed) ? 1 : 0"]
        lines = source.splitlines()
        if any(line not in lines for line in required) or len(re.findall(r"\b(?:ta\.sma|math\.sum)\s*\(", source)) != 2:
            raise ValueError("Independent isolated input/call formula differs")
        if columns["Input"] != inputs[f"case{n}"]:
            raise ValueError("Independent isolated input identity differs")
        for field in ("Native", "Sum"):
            if columns["IsNa" + field] != [int(value is None) for value in columns[field]]:
                raise ValueError("Isolated native state contradicts numeric log")
        comparisons = {field: reporter.compare_column(combined[f"{field} case{n}"], columns[field], 0.) for field in FIELDS}
        checks.append(dict(profile=f"case{n}", period=period, comparisons=comparisons))
    input_differences = sum(c["comparisons"]["Input"]["counts"]["differences"] for c in checks)
    if input_differences:
        raise ValueError("Combined and isolated supplied inputs differ")
    numeric_differences = sum(c["comparisons"][field]["counts"]["differences"] for c in checks for field in ("Native", "Sum"))
    state_differences = sum(c["comparisons"][field]["counts"]["differences"] for c in checks for field in ("IsNaNative", "IsNaSum"))
    return dict(schema="pyne.native-near-edge-isolation-diagnostic/1", scriptCount=4,
        inputCellsVerified=128, nativeNumericRecaptureCells=256, nativeStateRecaptureCells=256,
        independentInputDifferences=input_differences, numericRecaptureDifferences=numeric_differences,
        stateRecaptureDifferences=state_differences, comparisons=checks,
        priorFalsificationWitnesses=baseline_diagnostic["falsificationWitnesses"],
        combinedCallInteractionRequiredForTheseWitnesses=bool(numeric_differences or state_differences),
        uniformRemoveAddGuardRejected=baseline_diagnostic["uniformRemoveAddGuardRejected"],
        uniformKahanGuardRejected=baseline_diagnostic["uniformKahanGuardRejected"],
        countedAsAdditionalRuntimeAgreement=False, universalSourceContextInvarianceProved=False,
        replacementAccumulatorQualified=False, runtimeChanged=False, acceptanceProved=False, goalStatus="active",
        qualification="Four separately executed scripts compare 256 numeric outputs and 256 state flags with the combined-script capture at zero tolerance. Consult difference counts before inferring witness reproducibility. This repeated-input native comparison does not add runtime parity cells, prove universal context invariance, reveal a private algorithm, or qualify a period-specific replacement.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_diagnostic()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("scriptCount", "numericRecaptureDifferences", "stateRecaptureDifferences")}))


if __name__ == "__main__":
    main()
