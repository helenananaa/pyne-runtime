"""Keep legacy formula receipts and every raw difference visible."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("legacy_dmi_test_diagnostic", ROOT / "scripts/legacy_dmi_wrapper_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_native_legacy_reference_reproduction_is_not_additional_runtime_parity():
    result = diagnostic.build_diagnostic()
    assert result["importedDiPointsExactlyReproduced"] == 115
    assert result["strictFormulaDifferentPoints"] == 111
    assert result["countedAsAdditionalRuntimeAgreement"] is False
    assert result["historicalCaptureOriginProved"] is False
    assert result["acceptanceProved"] is False
    assert [case["rawFormulaDifferences"] for case in result["cases"]] == [16, 40, 55]


@pytest.mark.parametrize("mutation", ("source", "logs", "rehashed_source", "input", "captured_di", "witness", "missing_annotation"))
def test_altered_or_overbroad_legacy_wrapper_evidence_fails_closed(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests/golden").mkdir()
    shutil.copyfile(ROOT / "scripts/official_alignment_report.py", tmp_path / "scripts/official_alignment_report.py")
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
        shutil.copyfile(ROOT / "tests/workloads" / (diagnostic.NAME + suffix), folder / (diagnostic.NAME + suffix))
    for _, name, _, _ in diagnostic.CASES:
        shutil.copyfile(ROOT / "tests/golden" / (name + ".json"), tmp_path / "tests/golden" / (name + ".json"))
    path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(path.read_text())
    if mutation in ("source", "logs", "rehashed_source"):
        changed = folder / (diagnostic.NAME + (".tradingview.txt" if mutation == "logs" else ".pine"))
        changed.write_text(changed.read_text() + "\n", encoding="utf-8", newline="\n")
        if mutation == "rehashed_source":
            capture["scriptSha256"] = hashlib.sha256(changed.read_bytes()).hexdigest()
            path.write_text(json.dumps(capture), encoding="utf-8")
    else:
        changed = tmp_path / "tests/golden/ta_advanced_indicators.json"
        fixture = json.loads(changed.read_text())
        if mutation == "input":
            fixture["external_capture"]["bars"][0]["close"] += 1
        elif mutation == "captured_di":
            fixture["external_capture"]["series"]["Plus DI 3"][2]["value"] += 1
        elif mutation == "witness":
            fixture["external_capture"]["known_differences"][0]["wrapperWitness"]["historicalOriginProved"] = True
        else:
            fixture["external_capture"]["known_differences"].pop()
        changed.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
