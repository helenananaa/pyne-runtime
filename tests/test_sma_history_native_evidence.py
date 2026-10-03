"""Native history residues remain separate from causal runtime state controls."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepSMA
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
NAME = "sma_history_arithmetic"
spec = importlib.util.spec_from_file_location("sma_native_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs(callback=True):
    capture = json.loads((FOLDER / f"{NAME}.tradingview.json").read_text())
    reporter.verify_evidence(FOLDER, NAME, capture)
    source = (FOLDER / f"{NAME}{'' if callback else '_batch'}.py").read_text()
    return source, capture, reporter._bars(NAME, capture)


def test_native_inputs_are_independently_generated():
    source, capture, _ = inputs(False)
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "values_at")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<independent history inputs>", "exec"), namespace)
    for row in capture["rows"]:
        generated = namespace["values_at"](row["index"])
        assert [generated[title] for title in capture["columns"][:6]] == row["values"][:6]
    assert len(capture["rows"]) == 96 and len(capture["columns"]) == 48


@pytest.mark.parametrize("callback", (False, True))
def test_every_native_output_is_counted_including_history_residues(callback):
    result = reporter.workload_report(ROOT, NAME, dict(reporter.WORKLOADS)[NAME], callback)
    assert len(result["columns"]) == 30 and result["unmappedOutputColumns"] == []
    assert sum(column["counts"]["cells"] for column in result["columns"].values()) == 2880
    assert result["comparisonTolerance"] == 1e-8
    assert result["columns"]["Native prefill 3"]["counts"]["differences"] > 0
    for title, column in result["columns"].items():
        if title.startswith(("Native base ", "Native holes ")) or title.endswith(" 1"):
            assert column["counts"]["differences"] == 0, title
        if callback and title.endswith(" 2") and title != "Native prefillHoles 2":
            assert column["counts"]["differences"] == 0, title
    if callback:
        # A large prefill followed by gaps keeps a native arithmetic residue
        # even at period two. Retain it in the strict canonical comparison.
        assert result["columns"]["Native prefillHoles 2"]["counts"]["differences"] == 78


@pytest.mark.parametrize("period", (1, 2, 3, 7, 11))
@pytest.mark.parametrize("scenario", ("large_prefix", "negative_prefix", "infinity", "tiny_future", "zeros_future"))
def test_batch_sma_fallback_admission_cannot_rewrite_available_history(period, scenario):
    index = np.arange(96)
    base = ((index * 11) % 17 - 6.).astype(float)
    source = 2.**80 + base * 2.**28
    if scenario == "large_prefix":
        source[16:] = base[16:]
    elif scenario == "negative_prefix":
        source = -source
        source[16:] = base[16:]
    elif scenario == "infinity":
        source[22] = np.inf
        source[32:] = base[32:]
    elif scenario == "tiny_future":
        source[23:] = base[23:] / 1e10
    else:
        source[23:] = 0.
    module = TaModule()
    whole = np.asarray(module.sma(source, period))
    for cut in (2, 4, 8, 16, 22, 32, 96):
        prefix = np.asarray(module.sma(source[:cut], period))
        np.testing.assert_array_equal(prefix, whole[:cut])


@pytest.mark.parametrize("period", (1, 2, 3, 7, 11, 200))
@pytest.mark.parametrize("scenario", ("large_then_small", "mixed_signs", "finite_sum_overflow", "infinity"))
def test_incremental_mean_uses_independent_exact_present_observation_reference(period, scenario):
    index = np.arange(500)
    source = ((index * 11) % 17 - 6.).astype(float)
    if scenario == "large_then_small":
        source[:16] = 2.**80 + source[:16] * 2.**28
    elif scenario == "mixed_signs":
        source[:16] = np.where(index[:16] % 2 == 0, 2.**80, -2.**80)
    elif scenario == "finite_sum_overflow":
        source[:210] = np.finfo(float).max
    else:
        source[5] = np.inf
        source[9] = -np.inf
    source[23:26] = np.nan
    helper = _StepSMA(period)
    present = []
    with localcontext() as context:
        context.prec = 800
        for value in source:
            if not np.isnan(value):
                present.append(float(value))
            window = present[-period:]
            if len(window) < period or (np.inf in window and -np.inf in window):
                expected = None
            elif np.inf in window:
                expected = np.inf
            elif -np.inf in window:
                expected = -np.inf
            else:
                expected = float(sum(Decimal.from_float(v) for v in window) / Decimal(period))
            actual = helper.update(value)
            assert actual == expected
            assert len(helper.window) <= period


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (16, 18, 32))
def test_same_version_preview_isolation_and_restore_continuation(mode, cut):
    source, _, bars = inputs()
    original = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(executor_mode="inline"))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    original.on_bar_updated(dict(bars[cut], open=300., close=300., high=301., low=299.))
    assert original.snapshot_portable_state() == before
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source) if mode == "local" else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source))
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in bars[cut:]:
        left, right = original.snapshot_portable_state(), restored.snapshot_portable_state()
        original.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == left
        assert restored.snapshot_portable_state() == right
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)


@pytest.mark.parametrize("mode", ("state", "replay"))
def test_actual_old_large_anchor_state_rejected_before_construction(mode, monkeypatch):
    folder = ROOT / "tests/golden/sma_history_semantics_v33"
    provenance = json.loads((folder / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc28" and provenance["semanticsVersion"] == 33
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    assert json.loads((folder / f"{mode}.json").read_text())["payload"]["semanticsVersion"] == 33
    script = (folder / "indicator.pyne").read_text()
    bars = json.loads((folder / "bars.json").read_text())
    result = pn.run(script, bars, executor_mode="inline")
    assert result.ok
    assert next(line for line in result.lines if line["name"] == "SMA2")["data"][-1]["value"] == 2.

    def forbidden(*args, **kwargs):
        pytest.fail("Old state must be rejected before constructing a session")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV"):
        pn.PyneIncrementalSession.from_portable_snapshot((folder / f"{mode}.json").read_bytes(), script=script)
