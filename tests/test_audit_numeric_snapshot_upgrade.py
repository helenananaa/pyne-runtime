"""Real rc33 checkpoints cannot carry pre-repair dispersion into semantics 39."""

import hashlib
import json
from pathlib import Path

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden" / "audit_semantics_v38"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_real_rc33_numeric_snapshots_reject_before_construction(mode, monkeypatch):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc33"
    assert provenance["semanticsVersion"] == 38
    assert provenance["wheelSha256"] == (
        "490adb9337b805f3239b6e1f84a7a10525c880e7a009660c2426d44227549004"
    )
    for name, digest in provenance["sha256"].items():
        raw = (BASELINE / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == digest
    payload = (BASELINE / f"{mode}.json").read_bytes()
    assert json.loads(payload)["payload"]["semanticsVersion"] == 38
    old = json.loads((BASELINE / "committed-result.json").read_text())
    stdev = next(line for line in old["lines"] if line["name"] == "stdev")
    assert stdev["data"] == [{"time": 20, "value": 0.0}]
    assert INCREMENTAL_SEMANTICS_VERSION == 41

    def forbidden(*args, **kwargs):
        pytest.fail("Incompatible numeric state must fail before constructing a session")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot(payload, script=SCRIPT)
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_numeric_same_version_preview_restore_and_continuation(mode):
    original = pn.PyneIncrementalSession(script=SCRIPT)
    original.seed(BARS[:2])
    stdev = next(line for line in original.snapshot_result().lines if line["name"] == "stdev")
    assert stdev["data"][0]["value"] == pytest.approx(1e-200, rel=1e-14, abs=0)
    before = original.snapshot_portable_state()
    original.on_bar_updated(BARS[2])
    assert original.snapshot_portable_state() == before
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=SCRIPT)
    assert restored.snapshot_result() == original.snapshot_result()
    # Snapshots exclude active events. Give the restored session the preview
    # that the original already saw before comparing subsequent event metadata.
    restored_before = restored.snapshot_portable_state()
    first_preview = restored.on_bar_updated(BARS[2])
    assert first_preview.meta["barstate"]["isnew"] is True
    assert restored.snapshot_portable_state() == restored_before
    for bar in BARS[2:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    stdev = next(line for line in original.snapshot_result().lines if line["name"] == "stdev")
    values = {point["time"]: point["value"] for point in stdev["data"]}
    assert values[40] == pytest.approx(1e200, rel=1e-14, abs=0)
    assert values[60] == pytest.approx(0.5)
