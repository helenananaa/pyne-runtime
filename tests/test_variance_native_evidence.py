"""Complete variance capture, honest recipe qualification and evidence identity."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("native_variance_diagnostic", ROOT / "scripts/variance_native_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
spec = importlib.util.spec_from_file_location("native_variance_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def test_complete_native_inputs_and_download_are_independently_verified():
    result = diagnostic.build_diagnostic()
    assert result["inputCellsVerified"] == 256
    assert result["nativeCanonicalOutputCells"] == 3072
    assert result["nativeDiagnosticCells"] == 1536
    assert result["rawMomentHypothesis"]["differences"] == 141
    biased = [check for check in result["rawMomentHypothesis"]["checks"] if check["bias"] == "biased"]
    assert sum(check["counts"]["differences"] for check in biased) == 0
    assert result["sqrtNativeVarianceHypothesis"]["differences"] == 0
    assert not result["directSampleStdevParameterQualified"]
    assert not result["countedAsAdditionalRuntimeAgreement"]
    assert not result["acceptanceProved"]


@pytest.mark.parametrize("callback,differences", [(False, 1797), (True, 1946)])
def test_all_48_native_outputs_are_measured_without_erasing_discrepancies(callback, differences):
    controls = set(diagnostic.INPUTS + diagnostic.DIAGNOSTICS)
    result = reporter.workload_report(ROOT, diagnostic.NAME, controls, callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == set(diagnostic.OUTPUTS)
    assert sum(column["counts"]["cells"] for column in result["columns"].values()) == 3072
    assert sum(column["counts"]["activeCells"] for column in result["columns"].values()) == 2784
    assert sum(column["counts"]["bothMissingCells"] for column in result["columns"].values()) == 288
    assert sum(column["counts"]["differences"] for column in result["columns"].values()) == differences
    assert sum(column["counts"]["missingDifferences"] for column in result["columns"].values()) == 0


def test_native_expected_outputs_do_not_supply_runtime_input():
    capture = json.loads((FOLDER / (diagnostic.NAME + ".tradingview.json")).read_text())
    poisoned = json.loads(json.dumps(capture))
    for row in poisoned["rows"]:
        row["values"][4:] = [999999999.] * 72
    assert reporter._bars(diagnostic.NAME, capture) == reporter._bars(diagnostic.NAME, poisoned)
    for suffix in (".py", "_batch.py"):
        source = (FOLDER / (diagnostic.NAME + suffix)).read_text()
        assert "read_text" not in source and "tradingview" not in source
        assert diagnostic.recipe_inputs(source) == {
            profile: [row["values"][column] for row in capture["rows"]]
            for column, profile in enumerate(diagnostic.PROFILES)}


@pytest.mark.parametrize("corruption", ["pine", "log", "csv", "source_input", "batch_input", "tolerance", "diagnostic_only", "selection", "columns"])
def test_changed_or_rehashed_native_evidence_fails_closed(tmp_path, corruption):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/official_alignment_report.py", tmp_path / "scripts/official_alignment_report.py")
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json", ".tradingview.csv", ".py", "_batch.py"):
        shutil.copy(FOLDER / (diagnostic.NAME + suffix), folder / (diagnostic.NAME + suffix))
    capture_path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(capture_path.read_text())
    if corruption in ("pine", "log", "csv"):
        suffix, key = {"pine": (".pine", "scriptSha256"), "log": (".tradingview.txt", "logSha256"),
                       "csv": (".tradingview.csv", "downloadedCsvSha256")}[corruption]
        path = folder / (diagnostic.NAME + suffix)
        path.write_bytes(path.read_bytes() + b"\n")
        capture[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif corruption in ("source_input", "batch_input"):
        path = folder / (diagnostic.NAME + (".py" if corruption == "source_input" else "_batch.py"))
        path.write_text(path.read_text().replace("5.5, 4.0", "6.5, 4.0", 1))
    elif corruption == "tolerance":
        capture["tolerance"] = 1000000000.
    elif corruption == "diagnostic_only":
        capture["diagnosticOnly"] = True
    elif corruption == "selection":
        capture["selection"]["seed"] += 1
    else:
        capture["columns"][4] = "Wrong output"
    capture_path.write_text(json.dumps(capture))
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
