"""Authentic prior-wheel semantics-42 snapshots remain compatible."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION


BASELINE = Path(__file__).parent / "golden/replay_alma_semantics_v42"
SCRIPT = (BASELINE / "indicator.pyne").read_text(encoding="utf-8")
BARS = json.loads((BASELINE / "bars.json").read_text())


@pytest.fixture(scope="module")
def prior_wheel_reference(tmp_path_factory):
    """Execute the genuine prior release candidate with this platform's libm."""
    work = tmp_path_factory.mktemp("rc37-reference")
    wheel = BASELINE / "baseline/pyne_runtime-0.4.1rc37-py3-none-any.whl"
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == provenance["wheelSha256"]
    with zipfile.ZipFile(wheel) as archive:
        # The immutable, hash-checked first-party wheel contains package paths only.
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts
                   for name in archive.namelist())
        archive.extractall(work)
    probe = '''import json, sys
from dataclasses import asdict
from pathlib import Path
import pyne_runtime as pn
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION
assert Path(pn.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve())
assert pn.__version__ == "0.4.1rc37" and INCREMENTAL_SEMANTICS_VERSION == 42
base = Path(sys.argv[1])
script = (base/"indicator.pyne").read_text()
bars = json.loads((base/"bars.json").read_text())
count = json.loads((base/"provenance.json").read_text())["seedCount"]
records = {}
for mode in ("state", "replay"):
    session = pn.PyneIncrementalSession.from_portable_snapshot(
        (base/(mode+".json")).read_bytes(), script=script)
    before = asdict(session.snapshot_result())
    for bar in bars[count:]:
        session.on_bar_updated(bar)
        session.on_bar_closed(bar)
    records[mode] = dict(before=before, after=asdict(session.snapshot_result()))
print(json.dumps(records))
'''
    child = subprocess.run(
        [sys.executable, "-c", probe, str(BASELINE.resolve()), str(work)],
        cwd=work, env=dict(os.environ, PYTHONPATH=str(work)),
        capture_output=True, text=True, check=True, timeout=60,
    )
    records = json.loads(child.stdout)
    # Preserve captured-result checks in the original Windows Python 3.12 ABI.
    # Other platforms compare the old and new implementations exactly, without
    # introducing a tolerance for platform-dependent exp() weight construction.
    if sys.platform == "win32" and sys.version_info[:2] == (3, 12):
        for record in records.values():
            assert record["before"] == json.loads((BASELINE / "committed-result.json").read_text())
            assert record["after"] == json.loads((BASELINE / "continued-result.json").read_text())
    return records


@pytest.mark.parametrize("mode", ["state", "replay"])
def test_authentic_rc37_same_semantics_restores_previews_and_continues(mode, prior_wheel_reference):
    provenance = json.loads((BASELINE / "provenance.json").read_text())
    assert provenance["packageVersion"] == "0.4.1rc37"
    assert provenance["semanticsVersion"] == INCREMENTAL_SEMANTICS_VERSION == 42
    assert provenance["sourceWasUncommitted"] is True
    assert provenance["wheelSha256"] == "9dc58517602e6f79e1ecf74e627859a1a623275222bdcea32a81ca901474bd9c"
    for name, digest in provenance["sha256"].items():
        assert hashlib.sha256((BASELINE / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        (BASELINE / f"{mode}.json").read_bytes(), script=SCRIPT)
    assert asdict(restored.snapshot_result()) == prior_wheel_reference[mode]["before"]
    fresh = pn.PyneIncrementalSession(script=SCRIPT)
    assert fresh.seed(BARS[:provenance["seedCount"]]).ok
    for bar in BARS[provenance["seedCount"]:]:
        committed = restored.snapshot_portable_state()
        assert restored.on_bar_updated(bar) == fresh.on_bar_updated(bar)
        assert restored.snapshot_portable_state() == committed
        assert restored.on_bar_closed(bar) == fresh.on_bar_closed(bar)
    assert asdict(restored.snapshot_result()) == prior_wheel_reference[mode]["after"]
