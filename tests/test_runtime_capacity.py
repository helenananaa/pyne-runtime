"""Capacity harness contracts: RSS, CLI, partial failure, output integrity."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_harness():
    path = ROOT / "scripts" / "runtime_capacity.py"
    spec = importlib.util.spec_from_file_location("pyne_runtime_capacity_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rss_positive_on_windows():
    module = load_harness()
    sample = module.current_process_rss()
    assert "ru_maxrss" not in json.dumps(sample)
    if sys.platform == "win32":
        assert sample["supported"] is True
        assert sample["source"] == "windows.GetProcessMemoryInfo.WorkingSetSize"
        assert isinstance(sample["bytes"], int) and sample["bytes"] > 0
    elif sys.platform.startswith("linux"):
        assert sample["supported"] is True
        assert sample["bytes"] > 0
        assert "statm" in sample["source"]
    else:
        assert sample["supported"] is False
        assert sample["bytes"] is None


def test_invalid_args_rejected():
    module = load_harness()
    with pytest.raises(SystemExit):
        module.parse_args(["--sessions", "0", "--output", "out.json"])
    with pytest.raises(SystemExit):
        module.parse_args(["--sessions", "1", "--bars", "-3", "--output", "out.json"])
    with pytest.raises(SystemExit):
        module.parse_args(["--sessions", "1"])
    with pytest.raises(SystemExit):
        module.parse_args(
            ["--sessions", "1", "--retention", "32", "--max-bars", "16", "--output", "out.json"]
        )
    with pytest.raises(SystemExit):
        module.parse_args(["--worker", "--sessions", "1", "2", "--output", "out.json"])
    for value in ("nan", "inf"):
        with pytest.raises(SystemExit):
            module.parse_args(["--output", "out.json", "--timeout-seconds", value])


def test_parent_records_partial_failure_and_preserves_windows(tmp_path, monkeypatch):
    module = load_harness()
    output = tmp_path / "capacity.json"
    original_run = module.subprocess.run

    def fake_run(command, **kwargs):
        if "--worker" not in command:
            return original_run(command, **kwargs)
        case_path = Path(command[command.index("--output") + 1])
        case_path.write_text(
            json.dumps(
                {
                    "sessions": 2,
                    "completed": False,
                    "windows": [{"committedBars": 24, "processRss": {"bytes": 1}}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="worker exploded")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    args = SimpleNamespace(
        sessions=[2],
        bars=48,
        previews_per_bar=2,
        sample_every=24,
        retention=64,
        max_bars=256,
        cache_bars=2048,
        timeout_seconds=30.0,
        process_timeout_seconds=30.0,
        output=output,
        events=None,
        worker=False,
    )
    assert module.run_parent(args) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["completed"] is False
    assert report["failure"]["exitCode"] == 7
    assert "worker exploded" in report["failure"]["stderr"]
    assert report["cases"][0]["windows"][0]["committedBars"] == 24
    assert "finishedUtc" not in report


def test_output_and_event_stream_integrity(tmp_path):
    module = load_harness()
    output = tmp_path / "case.json"
    events = tmp_path / "case.events.jsonl"
    args = module.parse_args(
        [
            "--worker",
            "--sessions",
            "1",
            "--bars",
            "12",
            "--previews-per-bar",
            "1",
            "--sample-every",
            "12",
            "--retention",
            "8",
            "--max-bars",
            "16",
            "--cache-bars",
            "64",
            "--timeout-seconds",
            "120",
            "--output",
            str(output),
            "--events",
            str(events),
        ]
    )
    case = module.run_worker(args)
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["completed"] is True
    assert saved["windows"]
    event_lines = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line]
    assert len(event_lines) == 12 * 2
    kinds = {item["kind"] for item in event_lines}
    assert kinds == {"preview", "confirmed"}
    assert all("ms" in item and "utc" in item for item in event_lines)
    window = saved["windows"][-1]
    assert "samplesMs" not in window["preview"]
    assert "samplesMs" not in window["confirmed"]
    assert window["committedBars"] == 12
    rss = window["processRss"]
    assert rss.get("source") != "ru_maxrss"
    assert "maxrss" not in rss.get("source", "").lower()
    if rss.get("supported"):
        assert rss["bytes"] > 0
    session = window["sessions"][0]
    names = [item["name"] for item in session["checks"]]
    assert set(names) == set(module.INVARIANTS)
    assert all("passed" in item for item in session["checks"])
    assert session["typedState"]["bytes"] > 0
    assert case["retainedMeasurementArrays"]
    assert saved["appliedMaxOutputPoints"] >= 64


def test_continuation_check_detects_restore_only_transition_defect(tmp_path, monkeypatch):
    module = load_harness()
    factory = module.pn.PyneIncrementalSession.from_portable_snapshot

    def broken_restore(*args, **kwargs):
        restored = factory(*args, **kwargs)
        real_close = restored.on_bar_closed

        def broken_close(bar):
            result = real_close(bar)
            result.lines[0]["data"][-1]["value"] += 123
            return result

        restored.on_bar_closed = broken_close
        return restored

    monkeypatch.setattr(module.pn.PyneIncrementalSession, "from_portable_snapshot", broken_restore)
    args = module.parse_args([
        "--worker", "--sessions", "1", "--bars", "24", "--sample-every", "12",
        "--previews-per-bar", "1", "--output", str(tmp_path / "case.json"),
        "--events", str(tmp_path / "events.jsonl"),
    ])
    with pytest.raises(AssertionError, match="un-restored"):
        module.run_worker(args)
    saved = json.loads(args.output.read_text())
    assert saved["completed"] is False
