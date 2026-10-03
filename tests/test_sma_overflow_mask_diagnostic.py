"""Reject partial-state qualification and altered official input/state evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mask_diagnostic", ROOT / "scripts/sma_overflow_mask_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


@pytest.fixture(scope="module")
def report():
    return diagnostic.build_diagnostic()


def test_independent_masks_do_not_qualify_numerical_outputs(report):
    assert report["inputCellsVerified"] == 288
    assert report["nativeStateMaskCells"] == 2304
    assert report["nativeNumericOutputCells"] == 0
    assert report["countedAsAdditionalRuntimeAgreement"] is False
    assert {c["model"]: c["differences"] for c in report["candidateComparisons"]} == dict(
        remove_add=31, add_remove=153, window_recompute=519, sticky_window_recompute=31,
        exact_window_sum=561, kahan_remove_add=31)
    # A model fitting every bar-dependent mask still fails the independent numerical holdout.
    kahan = next(c for c in report["candidateComparisons"] if c["model"] == "kahan_remove_add")
    assert all(c["differences"] == 0 for c in kahan["checks"] if c["profile"] != "keywordHalf")
    assert report["kahanNumericHoldout"]["counts"] == dict(cells=2304, activeCells=2066,
        matchedActiveCells=1119, bothMissingCells=238, valueDifferences=947,
        missingDifferences=0, differences=947)
    assert all(c["qualifiedAsRuntimeReplacement"] is False for c in report["candidateComparisons"])
    assert report["runtimeChanged"] is report["acceptanceProved"] is False
    assert report["goalStatus"] == "active"
    json.dumps(report, allow_nan=False)


def test_explicit_series_keyword_does_not_establish_equivalent_native_context(report):
    context = report["explicitSeriesSourceContext"]
    assert context["equalInputCells"] == 64
    assert context["sumPeriodTwoMaskDifferences"] == 31
    assert context["differingIndices"] == list(range(1, 32))
    assert context["seriesKeywordEstablishesEquivalentContext"] is False
    bridge = report["nativeSmaSumStateBridge"]
    assert bridge["cells"] == 1152 and bridge["differences"] == 31
    assert bridge["universalIdentityQualified"] is False


def test_first_ready_exact_finite_window_does_not_clear_native_missing_state(report):
    columns = json.loads((ROOT / "tests/workloads/sma_overflow_mask_holdout.tradingview.json").read_text(encoding="utf-8"))
    values = [diagnostic.inputs(i)["preReadyRecover"] for i in range(32)]
    assert diagnostic.candidate_masks(values, 7, "exact_window_sum")[6] == 0
    index = columns["columns"].index("Missing SMA 7 preReadyRecover")
    assert columns["rows"][6]["values"][index] == 1
    assert report["preReadinessRecoveryMissing"]["SMA7"] == list(range(4, 32))


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "qualification", "order",
                                      "rehash_input", "rehash_flag", "rehash_bridge", "rehash_formula"))
def test_altered_or_rehashed_native_evidence_fails(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("sma_arithmetic_diagnostic", "official_alignment_report"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for name in (diagnostic.NAME, "sma_period_two_independent_holdout"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(path.read_text(encoding="utf-8"))
    if mutation in ("source", "logs"):
        changed = folder / (diagnostic.NAME + (".pine" if mutation == "source" else ".tradingview.txt"))
        changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif mutation == "qualification":
        capture["diagnosticOnly"] = False
    elif mutation == "order":
        capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
    elif mutation == "rehash_formula":
        changed = folder / (diagnostic.NAME + ".pine")
        source = changed.read_text(encoding="utf-8").replace("series float src_keywordHalf = half", "series float src_keywordHalf = large")
        changed.write_text(source, encoding="utf-8", newline="\n")
        capture["scriptSha256"] = hashlib.sha256(source.encode()).hexdigest()
    else:
        title, value = {"json": ("Input keywordHalf", 42.), "rehash_input": ("Input keywordHalf", 42.),
                        "rehash_flag": ("Missing SUM 2 keywordHalf", 2.),
                        "rehash_bridge": ("Missing SUM 2 branchHalf", 1.)}[mutation]
        column = capture["columns"].index(title)
        capture["rows"][2]["values"][column] = value
        if mutation != "json":
            raw_path = folder / (diagnostic.NAME + ".tradingview.txt")
            lines = raw_path.read_text(encoding="utf-8").splitlines()
            pieces = lines[2].split("|")
            pieces[column + 2] = str(value)
            lines[2] = "|".join(pieces)
            raw = "\n".join(lines) + "\n"
            raw_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
