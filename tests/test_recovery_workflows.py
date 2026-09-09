"""Operator recovery flows: fresh-process event state and explicit OHLCV rebuild."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pyne_runtime as pn
import pytest


ROOT = Path(__file__).resolve().parents[1]
EVENT_SCRIPT = '''indicator("Event-sensitive", mode="incremental")
def on_bar(ctx, bar):
    count = ctx.state("count", 0)
    if ctx.barstate.isnew:
        count.value += 1
    ctx.plot("Count", count.value)
'''


def bar(i):
    return dict(time=i, open=float(i + 1), high=float(i + 2), low=float(i),
                close=float(i + 1), volume=10.)


def values(result, title):
    return [p["value"] for line in result.lines if line["name"] == title for p in line["data"]]


def test_event_sensitive_state_survives_process_restart_but_replay_loses_visits(tmp_path):
    live = pn.PyneIncrementalSession(
        script=EVENT_SCRIPT, settings=pn.PyneSettings(executor_mode="inline", timeframe="1S")
    )
    live.seed([bar(0), bar(1)])
    live.on_bar_updated(bar(2))
    live.on_bar_closed(bar(2))
    assert values(live.snapshot_result(), "Count") == [1., 2., 2.]

    replay = pn.PyneIncrementalSession.from_portable_snapshot(
        live.snapshot_portable(mode="replay"), script=EVENT_SCRIPT
    )
    # Replay contains three closes, not the preview visit that consumed isnew.
    assert values(replay.snapshot_result(), "Count") == [1., 2., 3.]
    assert values(replay.on_bar_closed(bar(3)), "Count") == [4.]

    payload_path = tmp_path / "state.json"
    script_path = tmp_path / "indicator.py"
    payload_path.write_bytes(live.snapshot_portable_state())
    script_path.write_text(EVENT_SCRIPT, encoding="utf-8")
    probe = '''import json, sys
from pathlib import Path
import pyne_runtime as pn
s = pn.PyneIncrementalSession.from_portable_snapshot(
    Path(sys.argv[1]).read_bytes(), script=Path(sys.argv[2]).read_text(encoding="utf-8"))
before = s.snapshot_result().output
s.on_bar_closed(json.loads(sys.argv[3]))
print(json.dumps({"before": before, "after": s.snapshot_result().output}))
'''
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    child = subprocess.run(
        [sys.executable, "-c", probe, str(payload_path), str(script_path), json.dumps(bar(3))],
        cwd=tmp_path, env=environment, check=True, text=True, capture_output=True, timeout=30,
    )
    observed = json.loads(child.stdout)
    assert observed["before"] == live.snapshot_result().output
    live.on_bar_closed(bar(3))
    assert values(live.snapshot_result(), "Count") == [1., 2., 2., 3.]
    assert observed["after"] == live.snapshot_result().output


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_real_incompatible_snapshot_rebuilds_from_authoritative_bars(mode):
    fixtures = ROOT / "tests" / "golden" / "snapshot_semantics"
    provenance = json.loads((fixtures / "provenance.json").read_text())
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((fixtures / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    source = (fixtures / "indicator.pyne").read_text(encoding="utf-8")
    original = (fixtures / f"{mode}.json").read_bytes()
    with pytest.raises(pn.PynePortableSnapshotError) as error:
        pn.PyneIncrementalSession.from_portable_snapshot(original, script=source)
    assert error.value.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"

    # These four bars are specified by the historical fixture provenance.
    rebuilt = pn.PyneIncrementalSession(
        script=source, settings=pn.PyneSettings(executor_mode="inline", timeframe="1S")
    )
    rebuilt.seed([bar(i) for i in range(4)])
    # Current captured semantics seed EMA(3) with three non-missing values.
    # See ta_boundary_acceptance_zh.md; the first-close seed is incompatible.
    expected = (1. + 2. + 3.) / 3.
    expected = .5 * 4. + .5 * expected
    assert values(rebuilt.snapshot_result(), "EMA")[-1] == expected
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        rebuilt.snapshot_portable_state(), script=source
    )
    for i in range(4, 12):
        expected = .5 * (i + 1) + .5 * expected
        assert values(rebuilt.on_bar_closed(bar(i)), "EMA") == [expected]
        assert values(restored.on_bar_closed(bar(i)), "EMA") == [expected]
    assert (fixtures / f"{mode}.json").read_bytes() == original
