"""Raw evidence fingerprints must survive Git checkout policies."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("autocrlf", ["true", "false"])
def test_original_evidence_bytes_survive_git_checkout(tmp_path, autocrlf):
    capture = json.loads((ROOT / "tests/workloads/legacy_masked_history_context.tradingview.json")
                         .read_text(encoding="utf-8"))
    expected = {"tests/workloads/variance_independent_holdout.tradingview.csv":
                "7727452b960037bc59fea1f21b7178db557355a9ac618b2f2df6d1c214485f1d"}
    for item in capture["inputContext"]["fixtures"].values():
        expected["tests/golden/legacy_capture_context_baseline/" + item["name"] + ".json"] = item["sha256"]
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copyfile(ROOT / ".gitattributes", repository / ".gitattributes")
    for name in expected:
        destination = repository / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    def git(*args):
        subprocess.run(["git", "-c", "core.safecrlf=false", *args], cwd=repository,
                       check=True, capture_output=True)
    git("init")
    git("config", "core.autocrlf", autocrlf)
    git("add", ".gitattributes", *expected)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git("checkout-index", "--prefix=" + str(checkout.resolve()) + "/", "--", *expected)
    for name, digest in expected.items():
        assert hashlib.sha256((checkout / name).read_bytes()).hexdigest() == digest
