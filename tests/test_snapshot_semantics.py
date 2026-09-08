"""Upgrade rejection uses real pre-fix artifacts plus unchanged-state controls."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


FIXTURES = Path(__file__).parent / "golden" / "snapshot_semantics"
SCRIPT = (FIXTURES / "indicator.pyne").read_text(encoding="utf-8")


def bar(i):
    return dict(time=i, open=float(i + 1), high=float(i + 2), low=float(i),
                close=float(i + 1), volume=10.)


def session():
    result = pn.PyneIncrementalSession(
        script=SCRIPT, settings=pn.PyneSettings(executor_mode="inline", timeframe="1S")
    )
    result.seed([bar(i) for i in range(4)])
    return result


def seal(envelope):
    payload = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    envelope["checksum"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return json.dumps(envelope)


@pytest.mark.parametrize("mode", ["replay", "state"])
@pytest.mark.parametrize("folder", ["snapshot_semantics", "snapshot_semantics_v1"])
def test_real_legacy_snapshot_rejected_before_session_construction(mode, folder, monkeypatch):
    fixtures = FIXTURES.parent / folder
    provenance = json.loads((fixtures / "provenance.json").read_text())
    for name, digest in provenance["sha256"].items():
        # Text fixtures are normalized to LF by Git on all platforms.
        raw = (fixtures / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == digest

    def forbidden(*args, **kwargs):
        pytest.fail("An incompatible checkpoint must not construct or run a session")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="rebuild.*OHLCV") as error:
        pn.PyneIncrementalSession.from_portable_snapshot(
            (fixtures / f"{mode}.json").read_bytes(), script=SCRIPT
        )
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"


@pytest.mark.parametrize("version", [None, 0, 1, INCREMENTAL_SEMANTICS_VERSION + 1, True, "2", 2.0])
@pytest.mark.parametrize("mode", ["replay", "state"])
def test_unknown_or_malformed_portable_semantics_rejected(mode, version):
    original = session()
    envelope = json.loads(original.snapshot_portable(mode=mode))
    envelope["payload"]["semanticsVersion"] = version
    with pytest.raises(pn.PynePortableSnapshotError, match="SEMANTICS_MISMATCH"):
        pn.PyneIncrementalSession.from_portable_snapshot(seal(envelope), script=SCRIPT)


@pytest.mark.parametrize("version", [None, 0, 1, INCREMENTAL_SEMANTICS_VERSION + 1, True, "2", 2.0])
def test_local_rejection_preserves_committed_and_preview_state(version):
    original = session()
    control = session()
    original.on_bar_updated(bar(4))
    control.on_bar_updated(bar(4))
    before = original.snapshot_portable_state()
    with pytest.raises(pn.PynePortableSnapshotError, match="SEMANTICS_MISMATCH"):
        original.restore_state(replace(original.snapshot_state(), semantics_version=version))
    assert original.snapshot_portable_state() == before
    assert original.on_bar_closed(bar(4)) == control.on_bar_closed(bar(4))


def test_local_factory_rejects_legacy_before_construction(monkeypatch):
    legacy = replace(session().snapshot_state(), semantics_version=None)

    def forbidden(*args, **kwargs):
        pytest.fail("Legacy snapshot must be rejected before construction")

    monkeypatch.setattr(pn.PyneIncrementalSession, "__init__", forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match="SEMANTICS_MISMATCH"):
        pn.PyneIncrementalSession.from_snapshot(legacy, script=SCRIPT)


def test_relabeling_legacy_envelope_does_not_upgrade_typed_state():
    envelope = json.loads((FIXTURES / "state.json").read_text())
    envelope["payload"]["semanticsVersion"] = INCREMENTAL_SEMANTICS_VERSION
    with pytest.raises(pn.PynePortableSnapshotError, match="SEMANTICS_MISMATCH"):
        pn.PyneIncrementalSession.from_portable_snapshot(seal(envelope), script=SCRIPT)


@pytest.mark.parametrize("mode", ["local", "replay", "state"])
def test_current_semantics_restore_and_continue(mode):
    original = session()
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
    else:
        payload = original.snapshot_portable(mode=mode)
        assert json.loads(payload)["payload"]["semanticsVersion"] == INCREMENTAL_SEMANTICS_VERSION
        restored = pn.PyneIncrementalSession.from_portable_snapshot(payload, script=SCRIPT)
    assert restored.snapshot_result() == original.snapshot_result()
    for i in range(4, 12):
        assert restored.on_bar_updated(bar(i)) == original.on_bar_updated(bar(i))
        assert restored.on_bar_closed(bar(i)) == original.on_bar_closed(bar(i))
