"""Native diagnostic integrity, recapture and excluded parity denominators."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("variance_source_operations", ROOT / "scripts/variance_source_operations_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_native_operations_and_prior_capture_are_exact_without_extra_parity():
    result = diagnostic.build_diagnostic()
    assert result["inputCellsVerified"] == 256
    assert result["nativeOutputCells"] == 5120
    assert result["recapturedNativeOutputCells"] == 3072
    assert result["newDiagnosticCells"] == 2048
    assert result["exactCheckDifferences"] == 0
    expected = {"sourceSquare": 256, "nativePowerEqualsSquare": 256,
                "nativeSumDivPeriodEqualsMeanXX": 768, "nativePowMeanEqualsMeanXX": 768,
                "priorNativeRecapture": 3072}
    for kind, cells in expected.items():
        checks = [check for check in result["exactChecks"] if check["kind"] == kind]
        assert sum(check["counts"]["cells"] for check in checks) == cells
        assert all(check["counts"]["differences"] == 0 for check in checks)
    assert not result["nativeIndicatorValuesSuppliedToRuntime"]
    assert not result["countedAsAdditionalRuntimeAgreement"]
    assert not result["privateImplementationProved"]
    assert not result["replacementAccumulatorQualified"]
    assert not result["acceptanceProved"]
    reporter = diagnostic.load_script(ROOT, "official_alignment_report.py", "variance_operations_test_report")
    assert diagnostic.NAME not in {name for name, _ in reporter.WORKLOADS}
    assert not (FOLDER / (diagnostic.NAME + ".py")).exists()
    assert not (FOLDER / (diagnostic.NAME + "_batch.py")).exists()


def test_native_sum_normalization_hypotheses_keep_all_counterexamples():
    result = diagnostic.build_diagnostic()["nativeSumScalingHypotheses"]
    assert result["nativeSumUsedAsDiagnosticOnly"]
    assert not result["countedAsRuntimeAgreement"]
    assert [check["differences"] for check in result["checks"]] == [38, 131, 234, 208, 76, 52, 145, 69]
    assert result["minimumDifferences"] == 38
    for check in result["checks"]:
        assert sum(case["counts"]["cells"] for case in check["cases"]) == 1536
        assert sum(len(case["differences"]) for case in check["cases"]) == check["differences"]


@pytest.mark.parametrize("corruption", ["pine_rehash", "log_rehash", "csv_rehash", "output_json",
                                       "input_json", "columns", "tolerance", "selection", "diagnostic_only",
                                       "prior_recipe", "prior_csv"])
def test_corrupted_or_rehashed_diagnostics_fail_closed(tmp_path, corruption):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for filename in ("official_alignment_report.py", "variance_native_diagnostic.py"):
        shutil.copy(ROOT / "scripts" / filename, scripts / filename)
    for name in (diagnostic.NAME, "variance_independent_holdout"):
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json", ".tradingview.csv"):
            shutil.copy(FOLDER / (name + suffix), folder / (name + suffix))
    for suffix in (".py", "_batch.py"):
        shutil.copy(FOLDER / ("variance_independent_holdout" + suffix), folder / ("variance_independent_holdout" + suffix))
    capture_path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(capture_path.read_text())
    if corruption.endswith("_rehash"):
        suffix, key = {"pine_rehash": (".pine", "scriptSha256"),
                       "log_rehash": (".tradingview.txt", "logSha256"),
                       "csv_rehash": (".tradingview.csv", "downloadedCsvSha256")}[corruption]
        path = folder / (diagnostic.NAME + suffix)
        path.write_bytes(path.read_bytes() + b"\n")
        capture[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif corruption in ("output_json", "input_json"):
        capture["rows"][4]["values"][0 if corruption == "input_json" else 12] = 123456789.
    elif corruption == "columns":
        capture["columns"][12] = "Wrong mean"
    elif corruption == "tolerance":
        capture["tolerance"] = 1e9
    elif corruption == "selection":
        capture["selection"]["firstNativeBarIndex"] = 1
    elif corruption == "diagnostic_only":
        capture["diagnosticOnly"] = False
    elif corruption == "prior_recipe":
        path = folder / "variance_independent_holdout.py"
        path.write_text(path.read_text().replace("5.5, 4.0", "6.5, 4.0", 1))
    else:
        path = folder / "variance_independent_holdout.tradingview.csv"
        path.write_bytes(path.read_bytes() + b"\n")
    capture_path.write_text(json.dumps(capture))
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
