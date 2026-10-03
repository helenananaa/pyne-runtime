"""Ensure isolated native observations cannot inflate or conceal parity evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("near_edge_isolation", ROOT / "scripts/sma_near_edge_isolation_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_separate_native_calls_reproduce_both_uniform_guard_falsifications():
    result = diagnostic.build_diagnostic()
    assert result["scriptCount"] == 4 and result["inputCellsVerified"] == 128
    assert result["nativeNumericRecaptureCells"] == result["nativeStateRecaptureCells"] == 256
    assert result["independentInputDifferences"] == result["numericRecaptureDifferences"] == result["stateRecaptureDifferences"] == 0
    assert result["combinedCallInteractionRequiredForTheseWitnesses"] is False
    assert result["uniformRemoveAddGuardRejected"] is result["uniformKahanGuardRejected"] is True
    assert [(w["index"], w["nativeMissing"]) for w in result["priorFalsificationWitnesses"]] == [(30, 1), (13, 0), (13, 0), (14, 1)]
    for key in ("countedAsAdditionalRuntimeAgreement", "universalSourceContextInvarianceProved",
                "replacementAccumulatorQualified", "runtimeChanged", "acceptanceProved"):
        assert result[key] is False
    assert result["goalStatus"] == "active"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mutation", ("source", "logs", "json", "qualification", "order", "period_metadata",
    "rehash_input", "rehash_state", "rehash_formula", "rehash_period", "rehash_extra_call"))
def test_changed_isolated_capture_is_rejected_even_after_rehashing(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    for name in ("official_alignment_report", "sma_arithmetic_diagnostic", "sma_overflow_mask_diagnostic", "sma_near_edge_diagnostic"):
        shutil.copyfile(ROOT / "scripts" / (name + ".py"), tmp_path / "scripts" / (name + ".py"))
    for name in (*diagnostic.NAMES, "sma_near_edge_discriminator"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(ROOT / "tests/workloads" / (name + suffix), folder / (name + suffix))
    name = diagnostic.NAMES[0]
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text())
    if mutation in ("source", "logs"):
        changed = folder / (name + (".pine" if mutation == "source" else ".tradingview.txt"))
        changed.write_text(changed.read_text() + "\n", encoding="utf-8")
    elif mutation == "qualification":
        capture["countedAsAdditionalRuntimeAgreement"] = True
    elif mutation == "order":
        capture["rows"][1], capture["rows"][2] = capture["rows"][2], capture["rows"][1]
    elif mutation == "period_metadata":
        capture["period"] = 3
    elif mutation in ("rehash_formula", "rehash_period", "rehash_extra_call"):
        changed = folder / (name + ".pine")
        source = changed.read_text(encoding="utf-8")
        if mutation == "rehash_formula":
            source = source.replace("math.pow(2., 969)", "math.pow(2., 968)")
        elif mutation == "rehash_period":
            source = source.replace("ta.sma(src, 7)", "ta.sma(src, 3)")
        else:
            source += "float extra = ta.sma(src, 3)\n"
        changed.write_text(source, encoding="utf-8", newline="\n")
        capture["scriptSha256"] = hashlib.sha256(source.encode()).hexdigest()
    else:
        column, value = (0, 42.) if mutation != "rehash_state" else (3, 0.)
        capture["rows"][30]["values"][column] = value
        if mutation != "json":
            raw_path = folder / (name + ".tradingview.txt")
            lines = raw_path.read_text(encoding="utf-8").splitlines()
            pieces = lines[30].split("|")
            pieces[column + 2] = str(value)
            lines[30] = "|".join(pieces)
            raw = "\n".join(lines) + "\n"
            raw_path.write_text(raw, encoding="utf-8", newline="\n")
            capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
