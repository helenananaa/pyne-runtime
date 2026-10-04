"""Reject real v40 shared-state artifacts and qualify v41 continuation."""
import hashlib
import json
from pathlib import Path

import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden/audit_semantics_v40"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_actual_rc35_shared_state_rejects_before_construction(mode, monkeypatch):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc35"
    assert provenance["semanticsVersion"] == 40
    assert provenance["wheelSha256"] == "6fd5bcbe3605e92e4818fba2857dd93ef6f3b2d1eb838c28610334df6b4a89f4"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((BASELINE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    original = json.loads((BASELINE / "committed-result.json").read_text())
    assert all(point["value"] == 0 for line in original["lines"] for point in line["data"])
    assert INCREMENTAL_SEMANTICS_VERSION == 41
    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible semantics must reject before session construction")
    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as caught:
        pn.PyneIncrementalSession.from_portable_snapshot(
            (BASELINE / f"{mode}.json").read_bytes(), script=SCRIPT)
    assert caught.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_current_shared_graph_history_survives_restore_preview_and_continuation(mode):
    original = pn.PyneIncrementalSession(script=SCRIPT)
    assert original.seed(BARS[:2]).ok
    assert all(point["value"] == 1 for line in original.snapshot_result().lines for point in line["data"])
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=SCRIPT)
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in BARS[2:]:
        before = original.snapshot_portable_state()
        restored_before = restored.snapshot_portable_state()
        assert original.on_bar_updated(bar) == restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == before
        assert restored.snapshot_portable_state() == restored_before
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)
    assert all(point["value"] == 1 for line in restored.snapshot_result().lines for point in line["data"])
