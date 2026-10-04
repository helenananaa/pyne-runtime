"""Actual rc34 request and Pivot state cannot cross the structural repair."""
import hashlib
import json
from pathlib import Path

import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden/audit_semantics_v39"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())
ROWS = json.loads((BASELINE / "provider-rows.json").read_text())


class Provider:
    def get_ohlcv(self, symbol, timeframe, start, end):
        return [dict(row) for row in ROWS if start <= row["time"] <= end]


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_actual_rc34_artifacts_reject_before_construction(mode, monkeypatch):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc34"
    assert provenance["semanticsVersion"] == 39
    assert provenance["wheelSha256"] == "eaa9ee7043b9556a8c045a957f672bc47aad7f402ea9d402d4d8c6566abf7362"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((BASELINE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    old_result = json.loads((BASELINE / "committed-result.json").read_text())
    old_lower = next(line for line in old_result["lines"] if line["name"] == "Lower count")
    assert [point["value"] for point in old_lower["data"]] == [2., 1.]
    assert INCREMENTAL_SEMANTICS_VERSION == 41

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible state must reject before session construction or provider access")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    monkeypatch.setattr(Provider, "get_ohlcv", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot(
            (BASELINE / f"{mode}.json").read_bytes(), script=SCRIPT,
            settings=pn.PyneSettings(data_provider=Provider(), timeframe="1"))
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_structural_same_version_restore_preview_and_continuation(mode):
    settings = pn.PyneSettings(data_provider=Provider(), timeframe="1")
    original = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    assert original.seed(BARS[:2]).ok
    lower = next(line for line in original.snapshot_result().lines if line["name"] == "Lower count")
    assert [point["value"] for point in lower["data"]] == [3., 2.]
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=SCRIPT, settings=settings)
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in BARS[2:]:
        before = original.snapshot_portable_state()
        restored_before = restored.snapshot_portable_state()
        assert original.on_bar_updated(bar) == restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == before
        assert restored.snapshot_portable_state() == restored_before
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)
