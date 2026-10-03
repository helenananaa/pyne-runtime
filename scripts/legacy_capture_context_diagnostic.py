"""Verify exact legacy startup context witnesses without suppressing differences."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("legacy_masked_history_context", "legacy_masked_history_context_v5")


def _module(root, name):
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_diagnostic(root: Path = ROOT):
    reporter = _module(root, "official_alignment_report")
    differ = _module(root, "ta_capture_diff")
    folder = root / "tests/workloads"
    captures = []
    for name in NAMES:
        capture = json.loads((folder / f"{name}.tradingview.json").read_text(encoding="utf-8"))
        reporter.verify_evidence(folder, name, capture)
        if len(capture["rows"]) != 40 or len(capture["columns"]) != 52:
            raise ValueError("Incomplete history context capture")
        captures.append(capture)
    if captures[0]["columns"] != captures[1]["columns"] or captures[0]["rows"] != captures[1]["rows"]:
        raise ValueError("Pine v5/v6 context evidence changed")
    context = captures[0]["inputContext"]
    baselines = {}
    current = {}
    for case, metadata in context["fixtures"].items():
        path = root / "tests/golden/legacy_capture_context_baseline" / (metadata["name"] + ".json")
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError("Legacy baseline identity changed")
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture["external_capture"]["bars"] != metadata["bars"]:
            raise ValueError("Legacy native input bars changed")
        baselines[case] = fixture
        current[case] = json.loads((root / "tests/golden" / path.name).read_text(encoding="utf-8"))
        clean_current = json.loads(json.dumps(current[case]))
        clean_current["external_capture"].pop("known_differences", None)
        if clean_current != fixture:
            raise ValueError("Legacy input, expected output, tolerance or script changed")
    columns = {title: [row["values"][index] for row in captures[0]["rows"]]
               for index, title in enumerate(captures[0]["columns"])}
    input_cells = 0
    for title, metadata in context["inputColumns"].items():
        bars = context["fixtures"][metadata["case"]]["bars"]
        expected = [bars[i - metadata["offset"]][metadata["field"]]
                    if metadata["offset"] <= i < metadata["offset"] + len(bars) else None
                    for i in range(40)]
        if columns[title] != expected:
            raise ValueError(f"Native independently supplied inputs differ: {title}")
        input_cells += len(expected)
    witnesses = []
    baseline_differences = 0
    for case, fixture in baselines.items():
        report = differ.diff_fixture(Path(context["fixtures"][case]["name"] + ".json"),
                                     fixture, fixture["external_capture"])
        if report["runtime_error"]:
            raise ValueError(report["runtime_error"])
        baseline_differences += report["difference_count"]
        bars = fixture["external_capture"]["bars"]
        times = {bar["time"]: i for i, bar in enumerate(bars)}
        for difference in report["differences"]:
            matching = [(title, metadata) for title, metadata in context["outputs"].items()
                        if metadata["case"] == case and metadata["offset"] == 16
                        and metadata["originalTitle"] == difference["plot"]]
            if len(matching) != 1:
                raise ValueError("Missing exact native startup witness")
            title, metadata = matching[0]
            index = times[difference["tradingview"]["time"]]
            observed = columns[title][16 + index]
            expected = difference["tradingview"]["value"]
            if observed is None or abs(observed - expected) > difference["tolerance"]:
                raise ValueError("Masked-history native output does not reproduce legacy capture")
            origin = columns[title.replace(" leading ", " origin ")][index]
            if origin is not None and abs(origin - observed) <= difference["tolerance"]:
                raise ValueError("Native context does not cause the alleged startup difference")
            if difference["pyne"] is not None:
                raise ValueError("Startup witness unexpectedly changed")
            witness = dict(fixture=report["fixture"], plot=difference["plot"],
                           tradingview=difference["tradingview"], pyne=None,
                           tolerance=difference["tolerance"], originalInputIndex=index,
                           nativeOrigin=origin, nativeLeading=observed,
                           nativeLeadingIndex=16 + index, outputKind=metadata["kind"])
            witnesses.append(witness)
    if baseline_differences != len(witnesses) or len(witnesses) != 32:
        raise ValueError("Not every legacy startup difference has an exact witness")
    annotations = []
    for case, fixture in current.items():
        for item in fixture["external_capture"].get("known_differences", []):
            matches = [w for w in witnesses if w["fixture"] == context["fixtures"][case]["name"] + ".json"
                       and w["plot"] == item["plot"] and w["tradingview"] == item["tradingview"]
                       and w["pyne"] == item["pyne"]]
            if len(matches) != 1 or item.get("contextWitness") != matches[0]:
                raise ValueError("Disclosed context annotation lacks its exact native witness")
            annotations.append(item)
    if len(annotations) != len(witnesses):
        raise ValueError("Not every disclosed context difference retains its exact witness")
    return dict(schema="pyne.legacy-context-diagnostic/1", witnesses=witnesses,
                witnessedDifferences=len(witnesses), disclosedDifferences=len(annotations),
                nativeBuiltinWitnesses=sum(w["outputKind"] == "native builtin" for w in witnesses),
                preparedHelperWitnesses=sum(w["outputKind"] == "prepared Pine helper" for w in witnesses),
                helperOriginZeroWitnesses=sum(w["outputKind"] == "prepared Pine helper"
                                             and w["nativeOrigin"] == 0 for w in witnesses),
                inputCellsVerifiedPerPineVersion=input_cells, pineVersions=[6, 5], runtimeChanged=False,
                nativeOutputComparisonQualification="Sixteen native outputs per version have separate runtime recipes; controls and six helper outputs are excluded.",
                legacyQualification="Thirty-two exact startup differences remain counted. Their captured values reproduce after missing source history; no missing historical prices are fabricated.",
                limits=["This is context attribution, not a runtime repair or complete original CSV provenance.",
                        "Prepared WPR helpers emit zero before readiness; they are not native built-in WPR evidence.",
                        "The unrelated disclosed Pivot difference and all numeric matrix gaps remain."],
                acceptanceProved=False, goalStatus="active")


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
