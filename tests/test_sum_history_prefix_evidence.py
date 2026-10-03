"""Equal-window native witnesses remain diagnostic and fail closed on mutation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("sum_history_prefix", ROOT / "scripts/sum_history_prefix_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_explicit_float_additions_do_not_use_builtin_sum():
    assert diagnostic.explicit_fold([1e16, 1., -1e16]) == 0.
    assert diagnostic.explicit_fold([1e16, -1e16, 1.]) == 1.
    assert diagnostic.explicit_fold([1e16, 1., -1e16], "ascending_magnitude") == 0.
    with pytest.raises(ValueError):
        diagnostic.explicit_fold([1.], "unknown")


def test_equal_windows_retain_native_prefix_dependency_and_prior_counterexamples():
    result = diagnostic.build_diagnostic()
    assert result["inputCellsVerified"] == 96 and result["nativeDiagnosticOutputCells"] == 384
    assert result["equalWindowPairedCells"] == result["equalWindowNativeDifferences"] == 228
    assert result["kahanRemoveAddHoldout"]["differences"] == 0
    assert [item["differences"] for item in result["priorNativeSumChecks"]] == [199, 205, 214, 203, 187, 203, 146]
    for case in result["equalCurrentWindowNativePairs"]:
        assert case["nativeIndices"][0] == case["period"] + 1
        assert len(case["differences"]) == case["counts"]["cells"]
    assert result["additionsExplicitlyDefined"]
    assert not result["nativeIndicatorValuesSuppliedToRuntime"]
    assert not result["countedAsAdditionalRuntimeAgreement"]
    assert not result["replacementAccumulatorQualified"]
    assert not result["privateImplementationProved"]
    assert not result["acceptanceProved"]
    assert not (FOLDER / (diagnostic.NAME + ".py")).exists()
    assert not (FOLDER / (diagnostic.NAME + "_batch.py")).exists()


@pytest.mark.parametrize("corruption", ["pine_rehash", "log_rehash", "csv_rehash", "output_json",
                                       "input_json", "columns", "tolerance", "selection", "diagnostic_only"])
def test_changed_or_rehashed_prefix_evidence_fails_closed(tmp_path, corruption):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for filename in ("official_alignment_report.py", "variance_native_diagnostic.py", "variance_source_operations_diagnostic.py"):
        shutil.copy(ROOT / "scripts" / filename, scripts / filename)
    for name in (diagnostic.NAME, "variance_independent_holdout", "variance_source_operations"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json", ".tradingview.csv"):
            shutil.copy(FOLDER / (name + suffix), folder / (name + suffix))
    for suffix in (".py", "_batch.py"):
        shutil.copy(FOLDER / ("variance_independent_holdout" + suffix), folder / ("variance_independent_holdout" + suffix))
    capture_path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(capture_path.read_text())
    if corruption.endswith("_rehash"):
        suffix, key = {"pine_rehash": (".pine", "scriptSha256"), "log_rehash": (".tradingview.txt", "logSha256"),
                       "csv_rehash": (".tradingview.csv", "downloadedCsvSha256")}[corruption]
        path = folder / (diagnostic.NAME + suffix)
        path.write_bytes(path.read_bytes() + b"\n")
        capture[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif corruption in ("output_json", "input_json"):
        capture["rows"][4]["values"][0 if corruption == "input_json" else 3] = 123456789.
    elif corruption == "columns":
        capture["columns"][3] = "Wrong mean"
    elif corruption == "tolerance":
        capture["tolerance"] = 1e9
    elif corruption == "selection":
        capture["selection"]["firstNativeBarIndex"] = 1
    else:
        capture["diagnosticOnly"] = False
    capture_path.write_text(json.dumps(capture))
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
