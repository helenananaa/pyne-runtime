"""Verify independently supplied recursive-TA inputs and native call identities."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
NAME = "recursive_state_holdout"
PROFILES = ("leading", "flat_runs", "regime")
PERIODS = (1, 2, 3, 7, 11)
METHODS = ("ema", "rma", "rsi")


def input_codes():
    generator = random.Random(2026100354)
    return tuple(generator.randrange(-40, 41) for _ in range(64))


def supplied_inputs(i):
    base = float(input_codes()[i % 64]) * .25
    return dict(leading=None if i < 5 or i % 13 in (8, 9) else base,
        flat_runs=None if 6 <= i % 17 <= 9 else 0. if i < 12 else 3. if i % 12 < 6 else -3.,
        regime=None if i % 19 in (3, 4) else 10000. + base if i < 16 else base if i < 48 else -10000. + base)


def build_diagnostic(root=ROOT):
    spec = importlib.util.spec_from_file_location("recursive_state_reporter", root / "scripts/official_alignment_report.py")
    reporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reporter)
    folder = root / "tests/workloads"
    capture = json.loads((folder / (NAME + ".tradingview.json")).read_text(encoding="utf-8"))
    reporter.verify_evidence(folder, NAME, capture)
    expected = [title for profile in PROFILES for title in
                ["Input " + profile] + [f"{method.upper()}{period} {profile}" for method in METHODS for period in PERIODS]]
    if (capture["columns"] != expected or len(capture["rows"]) != 64 or capture.get("diagnosticOnly") is not False
            or capture.get("tolerance") != 1e-8 or capture.get("sourceExpressionClass") != "independent_recursive_state_holdout"
            or capture.get("selection") != dict(seed=2026100354, periods=list(PERIODS), profiles=list(PROFILES), nativeOutputsSuppliedAsInputs=False)):
        raise ValueError("Incomplete or incorrectly qualified recursive-state native evidence")
    columns = {title: [row["values"][n] for row in capture["rows"]] for n, title in enumerate(expected)}
    for profile in PROFILES:
        if columns["Input " + profile] != [supplied_inputs(i)[profile] for i in range(64)]:
            raise ValueError("Independently generated recursive-state input differs")
    source = (folder / (NAME + ".pine")).read_text(encoding="utf-8")
    required = ["int i = bar_index", "var codes = array.from(" + ", ".join(str(code) for code in input_codes()) + ")",
        "float base = float(array.get(codes, i % 64)) * 0.25",
        "float leading = i < 5 or i % 13 == 8 or i % 13 == 9 ? na : base",
        "float flat_runs = i % 17 >= 6 and i % 17 <= 9 ? na : i < 12 ? 0. : i % 12 < 6 ? 3. : -3.",
        "float regime = i % 19 == 3 or i % 19 == 4 ? na : i < 16 ? 10000. + base : i < 48 ? base : -10000. + base"]
    required += [f"float {method}{period}_{n} = ta.{method}({profile}, {period})"
                 for n, profile in enumerate(PROFILES) for method in METHODS for period in PERIODS]
    if any(line not in source.splitlines() for line in required):
        raise ValueError("Executed recursive-state source/input/call identity differs")
    missing_rma = sum(value is None for profile in PROFILES for period in PERIODS
                      for value in columns[f"RMA{period} {profile}"])
    return dict(schema="pyne.native-recursive-state-input-diagnostic/1", seed=2026100354,
        inputCellsVerified=192, nativeNumericOutputCells=2880, nativeOutputColumns=45,
        profiles=list(PROFILES), periods=list(PERIODS), methods=list(METHODS),
        nativeRmaMissingCells=missing_rma, countedAsAdditionalRuntimeAgreement=False,
        acceptanceProved=False, qualification="Inputs and unconditional call identities are independently verified. All 45 outputs enter canonical batch and callback comparisons; input validation does not add parity cells. Fixed profiles and periods do not prove whole API coverage.")
