"""Authentic prior-wheel semantics-42 snapshots remain compatible."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden/replay_alma_semantics_v42"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_authentic_rc37_same_semantics_restores_previews_and_continues(mode):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc37"
    assert provenance["semanticsVersion"] == INCREMENTAL_SEMANTICS_VERSION == 42
    assert provenance["sourceWasUncommitted"] is True
    assert provenance["wheelSha256"] == "9dc58517602e6f79e1ecf74e627859a1a623275222bdcea32a81ca901474bd9c"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((BASELINE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        (BASELINE / f"{mode}.json").read_bytes(), script=SCRIPT)
    assert asdict(restored.snapshot_result()) == json.loads((BASELINE / "committed-result.json").read_text())
    fresh = pn.PyneIncrementalSession(script=SCRIPT)
    assert fresh.seed(BARS[:provenance["seedCount"]]).ok
    for bar in BARS[provenance["seedCount"]:]:
        committed = restored.snapshot_portable_state()
        assert restored.on_bar_updated(bar) == fresh.on_bar_updated(bar)
        assert restored.snapshot_portable_state() == committed
        assert restored.on_bar_closed(bar) == fresh.on_bar_closed(bar)
    assert asdict(restored.snapshot_result()) == json.loads((BASELINE / "continued-result.json").read_text())
