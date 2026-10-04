from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden" / "audit_semantics_v37"


@pytest.mark.parametrize("mode", ("state", "replay"))
def test_real_audit_baseline_snapshots_reject_before_session_construction(mode, monkeypatch):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc32"
    assert provenance["semanticsVersion"] == 37
    assert provenance["gitCommit"] == "45eb794"
    assert provenance["wheelSha256"] == (
        "0805557c50bac07ef963b2279ee45ac7dae62d0c9bb1924be3ad388c8c1c177e"
    )
    for name, digest in provenance["sha256"].items():
        contents = (BASELINE / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(contents).hexdigest() == digest
    payload = (BASELINE / f"{mode}.json").read_bytes()
    assert json.loads(payload)["payload"]["semanticsVersion"] == 37
    assert INCREMENTAL_SEMANTICS_VERSION == 41

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible state must fail before constructing a session")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot(
            payload, script=(BASELINE / "indicator.pyne").read_text()
        )
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mode", ("local", "state", "replay"))
def test_audit_semantics_same_version_preview_and_continuation(mode):
    script = (BASELINE / "indicator.pyne").read_text()
    bars = json.loads((BASELINE / "bars.json").read_text())
    original = pn.PyneIncrementalSession(script=script)
    original.seed(bars[:3])
    before = original.snapshot_portable_state()
    original.on_bar_updated(bars[3])
    assert original.snapshot_portable_state() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            original.snapshot_state(), script=script
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=script
        )
    assert restored.snapshot_result() == original.snapshot_result()
    # Active previews are intentionally excluded from committed snapshots.
    # Submit the same live event to both sessions before comparing close metadata.
    original.on_bar_updated(bars[3])
    restored.on_bar_updated(bars[3])
    actual = restored.on_bar_closed(bars[3])
    assert actual == original.on_bar_closed(bars[3])
    mfi = next(line for line in actual.lines if line["name"] == "mfi")
    assert mfi["data"][0]["value"] == pytest.approx(200 / 3)
