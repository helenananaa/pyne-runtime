"""Native cold-start DMI, independent data, preview and state qualification."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION
from pyne_runtime.incremental.ta import _StepATR, _StepDMI, _StepTrueRange

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("composition_native_inputs", ROOT / "scripts/recursive_composition_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
spec = importlib.util.spec_from_file_location("composition_native_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs(name):
    capture = json.loads((FOLDER / (name + ".tradingview.json")).read_text(encoding="utf-8"))
    reporter.verify_evidence(FOLDER, name, capture)
    return (FOLDER / (name + ".py")).read_text(), capture, reporter._bars(name, capture)


@pytest.mark.parametrize("name,timeframe", diagnostic.CASES)
@pytest.mark.parametrize("callback", (False, True))
def test_every_initial_native_composition_output_is_mapped_and_matches(name, timeframe, callback):
    assert diagnostic.build_diagnostic()["inputCellsVerified"] == 768
    result = reporter.workload_report(ROOT, name, set(diagnostic.INPUTS), callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == set(diagnostic.OUTPUTS)
    assert result["comparisonTolerance"] == 1e-8
    assert all(c["counts"]["differences"] == 0 for c in result["columns"].values())
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 832


@pytest.mark.parametrize("name,timeframe", diagnostic.CASES)
def test_native_indicator_outputs_never_supply_runtime_input(name, timeframe):
    source, capture, bars = inputs(name)
    poisoned = json.loads(json.dumps(capture))
    for row in poisoned["rows"]:
        row["values"][6:] = [123456789.] * 13
    assert reporter._bars(name, poisoned) == bars
    assert "read_text" not in source and "tradingview" not in source
    assert (bars[0]["high"] - bars[0]["low"]) == pytest.approx(capture["rows"][0]["values"][6])


def test_dmi_skips_origin_tr_while_atr_and_true_range_keep_origin_fallback():
    bar = dict(open=10., high=1000., low=0., close=10., volume=1.)
    direct, atr, dmi = _StepTrueRange(), _StepATR(3), _StepDMI(3, 3)
    assert direct.update(bar["high"], bar["low"], bar["close"]) == 1000.
    assert atr.update(bar["high"], bar["low"], bar["close"]) is None
    assert atr.count == 1 and atr.tr_sum == 1000.
    assert dmi.update(bar["high"], bar["low"], bar["close"]) == (None, None, None)
    assert dmi.atr.count == 0 and dmi.atr.tr_sum == 0.
    assert dmi.atr.prev_close == 10. and dmi.atr.handle_na is False


@pytest.mark.parametrize("name,timeframe", diagnostic.CASES)
@pytest.mark.parametrize("mode", ("local", "state", "replay"))
@pytest.mark.parametrize("cut", (0, 1, 3, 7, 9, 13))
def test_same_version_preview_and_restore_preserve_dmi_origin_readiness(name, timeframe, mode, cut):
    source, _, bars = inputs(name)
    settings = pn.PyneSettings(executor_mode="inline", timeframe=timeframe)
    original = pn.PyneIncrementalSession(script=source, settings=settings)
    assert original.seed(bars[:cut]).ok
    before = original.snapshot_portable_state()
    original.on_bar_updated(bars[cut])
    assert original.snapshot_portable_state() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source)
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in bars[cut:]:
        original_previous = original.snapshot_portable_state()
        previous = restored.snapshot_portable_state()
        original.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == original_previous
        assert restored.snapshot_portable_state() == previous
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)


@pytest.mark.parametrize("mode", ("state", "replay"))
def test_real_rc31_wrong_dmi_origin_snapshot_rejected_before_construction(mode, monkeypatch):
    folder = ROOT / "tests/golden/dmi_initial_tr_semantics_v36"
    provenance = json.loads((folder / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc31" and provenance["semanticsVersion"] == 36
    assert provenance["wheelSha256"] == "26013fafc495c85394efad343f59fbbc75d07deccb432cce6ed06c5f72189f6a"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    assert INCREMENTAL_SEMANTICS_VERSION == 41
    script = (folder / "indicator.pyne").read_text()
    current = pn.run(script, json.loads((folder / "bars.json").read_text()), executor_mode="inline")
    assert current.ok
    old = json.loads((folder / "committed-result.json").read_text())
    old_plus = next(line for line in old["lines"] if line["name"] == "plus3")["data"][0]["value"]
    new_plus = next(line for line in current.lines if line["name"] == "plus3")["data"][0]["value"]
    assert not np.isclose(old_plus, new_plus, rtol=0, atol=1e-8)

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible DMI seed state must be rejected before session construction")
    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot((folder / (mode + ".json")).read_bytes(), script=script)
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mutation", ("source", "logs", "rehashed_source", "rehashed_input", "selection", "missing_token"))
def test_altered_composition_evidence_fails_even_after_rehash(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/official_alignment_report.py", tmp_path / "scripts/official_alignment_report.py")
    for name, _ in diagnostic.CASES:
        for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
            shutil.copyfile(FOLDER / (name + suffix), folder / (name + suffix))
    name = diagnostic.CASES[0][0]
    path = folder / (name + ".tradingview.json")
    capture = json.loads(path.read_text())
    if mutation in ("source", "logs", "rehashed_source"):
        changed = folder / (name + (".tradingview.txt" if mutation == "logs" else ".pine"))
        changed.write_text(changed.read_text() + "\n", encoding="utf-8", newline="\n")
        if mutation == "rehashed_source":
            capture["scriptSha256"] = hashlib.sha256(changed.read_bytes()).hexdigest()
    elif mutation == "selection":
        capture["selection"]["firstNativeBarIndex"] = 1
    elif mutation == "missing_token":
        capture["missingValueToken"] = "UNKNOWN"
    else:
        capture["rows"][0]["values"][1] = 99999.
        raw_path = folder / (name + ".tradingview.txt")
        raw = raw_path.read_text().replace("4261.48000000000000000", "99999.00000000000000000", 1)
        raw_path.write_text(raw, encoding="utf-8", newline="\n")
        capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
