"""Authentic v41 weighted-state rejection and v42 continuation."""
import hashlib
import json
from pathlib import Path

import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden/audit_semantics_v41"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_genuine_rc36_weighted_state_rejects_before_construction(mode, monkeypatch):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc36"
    assert provenance["semanticsVersion"] == 41
    assert provenance["sourceCommit"] == "039a0eaf99b2c3bc74d81bff6698e3940b83c123"
    assert provenance["wheelSha256"] == "4e46a035de038d834f1a8f8041631161cd112854f1f3335bc7f992600b4890dd"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((BASELINE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    original = json.loads((BASELINE / "committed-result.json").read_text())
    assert original["lines"][0]["data"][-1]["value"] == 2
    assert original["lines"][1]["data"][-1]["value"] == 0
    assert INCREMENTAL_SEMANTICS_VERSION == 42
    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible semantics must reject before session construction")
    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as caught:
        pn.PyneIncrementalSession.from_portable_snapshot(
            (BASELINE / f"{mode}.json").read_bytes(), script=SCRIPT)
    assert caught.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_current_weighted_restore_preview_and_continuation_are_exact(mode):
    original = pn.PyneIncrementalSession(script=SCRIPT)
    assert original.seed(BARS[:4]).ok
    assert all(line["data"][-1]["value"] == 1 for line in original.snapshot_result().lines)
    restored = (pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
        if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=SCRIPT))
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in BARS[4:]:
        before = original.snapshot_portable_state()
        restored_before = restored.snapshot_portable_state()
        assert original.on_bar_updated(bar) == restored.on_bar_updated(bar)
        assert original.snapshot_portable_state() == before
        assert restored.snapshot_portable_state() == restored_before
        assert original.on_bar_closed(bar) == restored.on_bar_closed(bar)
    assert all(line["data"][-1]["value"] == 1 for line in restored.snapshot_result().lines)
