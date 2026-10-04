"""Native recursive-TA gaps, causal state, preview and snapshot compatibility."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION
from pyne_runtime.incremental.ta import _StepATR, _StepDMI, _StepRMA
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("recursive_native_inputs", ROOT / "scripts/recursive_state_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
spec = importlib.util.spec_from_file_location("recursive_native_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs():
    capture = json.loads((FOLDER / (diagnostic.NAME + ".tradingview.json")).read_text())
    reporter.verify_evidence(FOLDER, diagnostic.NAME, capture)
    return (FOLDER / (diagnostic.NAME + ".py")).read_text(), capture, reporter._bars(diagnostic.NAME, capture)


@pytest.mark.parametrize("suffix", (".py", "_batch.py"))
def test_recipes_independently_reconstruct_seeded_inputs(suffix):
    result = diagnostic.build_diagnostic()
    assert result["inputCellsVerified"] == 192 and result["nativeNumericOutputCells"] == 2880
    assert result["nativeOutputColumns"] == 45 and result["countedAsAdditionalRuntimeAgreement"] is False
    source = (FOLDER / (diagnostic.NAME + suffix)).read_text()
    assert "tradingview" not in source and "read_text" not in source
    function, = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "inputs"]
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "independent-recursive-inputs", "exec"), namespace)
    assert [namespace["inputs"](i) for i in range(64)] == [diagnostic.supplied_inputs(i) for i in range(64)]


@pytest.mark.parametrize("callback", (False, True))
def test_every_native_output_matches_including_missing_positions(callback):
    result = reporter.workload_report(ROOT, diagnostic.NAME, dict(reporter.WORKLOADS)[diagnostic.NAME], callback)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert len(result["columns"]) == 45 and len(result["inputOrControlColumns"]) == 3
    assert result["comparisonTolerance"] == 1e-8
    totals = {key:sum(c["counts"][key] for c in result["columns"].values())
              for key in next(iter(result["columns"].values()))["counts"]}
    assert totals == dict(cells=2880, activeCells=2044, matchedActiveCells=2044,
                         bothMissingCells=836, valueDifferences=0, missingDifferences=0, differences=0)


@pytest.mark.parametrize("period", diagnostic.PERIODS)
def test_rma_missing_output_preserves_state_and_does_not_reseed(period):
    source = np.array([np.nan, 1., np.nan, 3., np.nan, 5., 7., np.nan, 9., 11., 13., 15., 17., 19., np.nan, 21.])
    step = _StepRMA(period)
    actual = []
    for value in source:
        before = dict(step.__dict__)
        actual.append(step.update(value))
        if np.isnan(value):
            assert actual[-1] is None and step.__dict__ == before
    batch = np.asarray(TaModule().rma(source, period))
    np.testing.assert_array_equal(batch, np.asarray(actual, dtype=np.float64))
    compact = np.asarray(TaModule().rma(source[~np.isnan(source)], period))
    np.testing.assert_array_equal(batch[~np.isnan(source)], compact)
    for cut in range(1, len(source)+1):
        np.testing.assert_array_equal(TaModule().rma(source[:cut], period), batch[:cut])


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (5, 8, 10, 16, 22, 24, 48))
def test_same_version_preview_isolation_and_restore_through_gaps(mode, cut):
    source, _, bars = inputs()
    original = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(executor_mode="inline"))
    assert original.seed(bars[:cut]).ok
    before = original.snapshot_portable_state()
    assert original.on_bar_updated(bars[cut]).ok
    assert original.snapshot_portable_state() == before
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source) if mode == "local" else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source))
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in bars[cut:]:
        left, right = original.snapshot_portable_state(), restored.snapshot_portable_state()
        original.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == left and restored.snapshot_portable_state() == right
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)


@pytest.mark.parametrize("mode", ("state", "replay"))
def test_real_rc29_rma_gap_snapshot_rejected_before_construction(mode, monkeypatch):
    folder = ROOT / "tests/golden/rma_missing_semantics_v34"
    provenance = json.loads((folder / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc29" and provenance["semanticsVersion"] == 34
    assert provenance["wheelSha256"] == "533e9b4dfacc61d49bd4ac6e0ee436d5af76e25c319162064b2541d4065e920e"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    assert json.loads((folder / (mode + ".json")).read_text())["payload"]["semanticsVersion"] == 34
    assert INCREMENTAL_SEMANTICS_VERSION == 41
    script = (folder / "indicator.pyne").read_text()
    result = pn.run(script, json.loads((folder / "bars.json").read_text()), executor_mode="inline")
    assert result.ok
    points = {point["time"]:point["value"] for point in result.lines[0]["data"]}
    assert 120 not in points and 180 not in points and points[240] == 3.5

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible state must fail before constructing a session")
    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot((folder / (mode + ".json")).read_bytes(), script=script)
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


def test_compositions_preserve_real_rc29_baseline_outside_native_rma_scope():
    """Controlled compatibility only: this fixture is not a native DMI oracle."""
    fixture = ROOT / "tests/golden/rma_composition_baseline_v34"
    expected = json.loads((fixture / "values.json").read_text())
    provenance = json.loads((fixture / "provenance.json").read_text())
    assert hashlib.sha256((fixture / "values.json").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == provenance["sha256"]
    assert provenance["packageVersion"] == "0.4.1rc29" and provenance["semanticsVersion"] == 34
    high = np.arange(16, dtype=float) + 4.
    low, close = high - 2., high - 1.
    high[7:9] = np.nan
    module, atr_step, dmi_step = TaModule(), _StepATR(3), _StepDMI(3, 3)
    steps = [dmi_step.update(h, low_value, c) for h, low_value, c in zip(high, low, close)]
    actual = dict(atrBatch=module.atr(3, high, low, close),
                  atrStep=[atr_step.update(h, low_value, c) for h, low_value, c in zip(high, low, close)],
                  dmiBatch=module.dmi(period=3, adx_period=3, high=high, low=low, close=close),
                  dmiStep=list(zip(*steps)))
    for name, values in actual.items():
        np.testing.assert_array_equal(np.asarray(values, dtype=float), np.asarray(expected[name], dtype=float))


@pytest.mark.parametrize("mode", ("state", "replay"))
def test_real_intermediate_rc30_composition_snapshot_rejected_before_construction(mode, monkeypatch):
    folder = ROOT / "tests/golden/dmi_composition_semantics_v35"
    provenance = json.loads((folder / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc30" and provenance["semanticsVersion"] == 35
    assert provenance["wheelSha256"] == "a455e6da19cc193221d6072c208c3a832f001804d9172f982ecf43adc8114325"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    script = (folder / "indicator.pyne").read_text()

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible intermediate state must fail before session construction")
    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot((folder / (mode + ".json")).read_bytes(), script=script)
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mutation", ("source", "logs", "qualification", "rehash_input", "rehash_formula", "rehash_period"))
def test_altered_recursive_native_evidence_fails_even_after_rehash(tmp_path, mutation):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/official_alignment_report.py", tmp_path / "scripts/official_alignment_report.py")
    for suffix in (".pine", ".tradingview.txt", ".tradingview.json"):
        shutil.copyfile(FOLDER / (diagnostic.NAME + suffix), folder / (diagnostic.NAME + suffix))
    path = folder / (diagnostic.NAME + ".tradingview.json")
    capture = json.loads(path.read_text())
    if mutation in ("source", "logs"):
        changed = folder / (diagnostic.NAME + (".pine" if mutation == "source" else ".tradingview.txt"))
        changed.write_text(changed.read_text() + "\n", encoding="utf-8")
    elif mutation == "qualification":
        capture["diagnosticOnly"] = True
    elif mutation in ("rehash_formula", "rehash_period"):
        changed = folder / (diagnostic.NAME + ".pine")
        source = changed.read_text()
        source = source.replace("10000. + base", "1000. + base") if mutation == "rehash_formula" else source.replace("ta.rma(leading, 7)", "ta.rma(leading, 3)")
        changed.write_text(source, encoding="utf-8", newline="\n")
        capture["scriptSha256"] = hashlib.sha256(source.encode()).hexdigest()
    else:
        column = capture["columns"].index("Input regime")
        capture["rows"][20]["values"][column] = 42.
        raw_path = folder / (diagnostic.NAME + ".tradingview.txt")
        lines = raw_path.read_text().splitlines()
        pieces = lines[20].split("|")
        pieces[column+2] = "42."
        lines[20] = "|".join(pieces)
        raw = "\n".join(lines) + "\n"
        raw_path.write_text(raw, encoding="utf-8", newline="\n")
        capture["logSha256"] = hashlib.sha256(raw.encode()).hexdigest()
    path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ValueError):
        diagnostic.build_diagnostic(tmp_path)
