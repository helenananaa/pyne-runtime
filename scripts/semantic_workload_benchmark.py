"""Whole-script local baseline; measurements, not production capacity promises.

Each workload/history/repetition runs in a fresh child process. Timing and
tracemalloc are separate passes; every raw latency sample is retained.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pyne_runtime as pn  # noqa: E402
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION  # noqa: E402

WORKLOADS = ("ta_chain", "requests", "state_cache", "drawings", "strategy", "strategy_cycles")
ASSETS = ROOT / "tests" / "workloads"


def bars(count):
    closes = (10, 12, 14, 13, 11, 9, 8, 10, 13, 15, 12, 9)
    return [dict(time=i * 10, open=float(closes[i % 12]), high=float(closes[i % 12] + 1),
                 low=float(closes[i % 12] - 1), close=float(closes[i % 12]),
                 volume=0.0 if i % 7 == 0 else 10.0) for i in range(count)]


class Provider:
    """Frozen arithmetic source, sparse LTF slots; no network or disk access.

    Same formula as semantic acceptance, extended to the measured stream horizon.
    Generate only the requested interval, rather than scanning a growing archive.
    """

    capabilities = {"request.security": True, "request.security_lower_tf": True}

    def __init__(self, horizon):
        self.horizon = horizon

    def get_ohlcv(self, symbol, timeframe, start, end):
        if symbol != "TEST:ASSET":
            raise ValueError(symbol)
        step = {"30S": 30, "5S": 5}[timeframe]
        rows = []
        for timestamp in range(max(-60, math.ceil(start / step) * step),
                               min(self.horizon, math.floor(end / step) * step + 1), step):
            if timeframe == "5S" and timestamp % 40 == 5:
                continue
            close = float(20 + timestamp // step % 9)
            rows.append(dict(time=timestamp, open=close, high=close + 1, low=close - 1,
                             close=close, volume=10))
        return rows


def checked(value):
    if hasattr(value, "ok") and not value.ok:
        raise RuntimeError(value.error)
    return value


def timed(callback):
    start = time.perf_counter_ns()
    value = callback()
    elapsed = (time.perf_counter_ns() - start) / 1e6
    return elapsed, checked(value)


def summarize(samples):
    ordered = sorted(samples)
    return {"samplesMs": samples, "medianMs": statistics.median(samples),
            "p95Ms": ordered[math.ceil(len(ordered) * .95) - 1],
            "maxMs": max(samples), "count": len(samples)}


def measure(name, history, samples, retention, max_bars):
    source = (ASSETS / f"{name}.py").read_text(encoding="utf-8")
    data = bars(history + samples + 1)
    settings = pn.PyneSettings(
        executor_mode="inline", timeframe="10S", syminfo={"tickerid": "TEST:ASSET"},
        data_provider=Provider((len(data) + 6) * 10), max_bars=max_bars, replay_history_bars=max_bars,
        trace_enabled=False,
    )

    def fresh():
        result = pn.PyneIncrementalSession(script=source, settings=settings,
                                          retention_bars=retention)
        result.seed(data[:16])
        for row in data[16:history]:
            checked(result.on_bar_closed(row))
        return result

    # Warm imports/code paths before collecting latency. Warmup is not a sample.
    warm = pn.PyneIncrementalSession(script=source, settings=settings, retention_bars=retention)
    warm.seed(data[:16])
    checked(warm.on_bar_updated(data[16]))
    checked(warm.on_bar_closed(data[16]))
    del warm
    gc.collect()
    subject = fresh()
    committed = subject.snapshot_result()
    local = subject.snapshot_state()
    oracle = pn.PyneIncrementalSession.from_snapshot(local, script=source, settings=settings)
    continuation = oracle.on_bar_closed(data[history])
    del oracle
    checkpoints = {}
    for mode in ("local", "state", "replay"):
        if mode == "replay" and history > max_bars:
            try:
                subject.snapshot_portable(mode=mode)
            except pn.PynePortableSnapshotError as exc:
                if "history exceeded replay_history_bars" not in str(exc):
                    raise
                checkpoints[mode] = {"available": False, "reason": str(exc)}
                continue
            raise AssertionError("Truncated history unexpectedly accepted replay snapshot")
        encode_samples, restore_samples = [], []
        size = None
        for _ in range(3):
            gc.collect()
            elapsed, payload = timed(
                subject.snapshot_state if mode == "local"
                else lambda: subject.snapshot_portable(mode=mode)
            )
            encode_samples.append(elapsed)
            if mode != "local":
                size = len(payload)
            elapsed, restored = timed(
                lambda: pn.PyneIncrementalSession.from_snapshot(payload, script=source,
                                                                settings=settings)
                if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
                    payload, script=source, settings=settings)
            )
            restore_samples.append(elapsed)
            assert restored.snapshot_result() == committed
            assert restored.on_bar_closed(data[history]) == continuation
            restored = payload = None
        checkpoints[mode] = {"available": True, "bytes": size,
                             "encode": summarize(encode_samples),
                             "restore": summarize(restore_samples)}
    del local, committed, continuation
    gc.collect()
    preview, confirmed = [], []
    for index, row in enumerate(data[history:history + samples]):
        before = subject.snapshot_result() if index == 0 else None
        for offset in (.5, -.5):
            update = dict(row, close=row["close"] + offset)
            elapsed, result = timed(lambda: subject.on_bar_updated(update))
            preview.append(elapsed)
            del result
        if index == 0:
            assert subject.snapshot_result() == before
        elapsed, result = timed(lambda: subject.on_bar_closed(row))
        confirmed.append(elapsed)
        del result
    subject = None
    gc.collect()

    # Fresh pass: retained Python allocations attributable to the live session;
    # input bars/provider are allocated before tracing and excluded. Not RSS.
    tracemalloc.start()
    try:
        memory_subject = fresh()
        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        del memory_subject
    finally:
        tracemalloc.stop()
    return {"workload": name, "historyBars": history, "preview": summarize(preview),
            "confirmed": summarize(confirmed), "checkpoints": checkpoints,
            "memory": {"retainedPythonBytes": retained, "peakPythonBytes": peak},
            "correctness": "restore/continuation and first-preview isolation passed"}


def positive(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--histories", nargs="+", type=positive, default=[64, 256, 1024])
    parser.add_argument("--samples", type=positive, default=32)
    parser.add_argument("--repeats", type=positive, default=3)
    parser.add_argument("--retention", type=positive, default=64)
    parser.add_argument("--max-bars", type=positive, default=256)
    parser.add_argument("--workloads", nargs="+", choices=WORKLOADS, default=list(WORKLOADS))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.histories) < 32 or args.max_bars < 16 or args.retention > args.max_bars:
        parser.error("histories >= 32, max-bars >= 16, retention <= max-bars required")
    if args.worker:
        print(json.dumps(measure(args.workloads[0], args.histories[0], args.samples,
                                 args.retention, args.max_bars), allow_nan=False))
        return 0
    if args.output is None:
        parser.error("--output is required to retain raw measurements")
    tracked = [Path(__file__).resolve(), *[ASSETS / f"{name}.py" for name in args.workloads]]
    report = {
        "schema": "pyne.semantic-workload-benchmark/1", "completed": False,
        "startedUtc": datetime.now(timezone.utc).isoformat(),
        "gitHead": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "gitStatus": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
        "sourceSha256": {str(p.relative_to(ROOT)): hashlib.sha256(
            p.read_text(encoding="utf-8").encode()).hexdigest() for p in tracked},
        "runtimeSourceSha256": hashlib.sha256("".join(
            str(p.relative_to(ROOT)) + hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src").rglob("*.py"))).encode()).hexdigest(),
        "python": sys.version, "platform": platform.platform(), "cpu": platform.processor(),
        "logicalCpus": os.cpu_count(), "semanticsVersion": INCREMENTAL_SEMANTICS_VERSION,
        "config": {k: v for k, v in vars(args).items() if k not in ("output", "worker")},
        "method": "fresh process per repetition; GC enabled; tracing only in separate memory pass; "
                  "nearest-rank p95; two previews per confirmation; single-session inline; "
                  "synthetic provider extended from acceptance formula; no network; no absolute gate",
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    cases = [(n, h) for n in args.workloads for h in args.histories]
    for repeat in range(args.repeats):
        for name, history in cases[::1 if repeat % 2 == 0 else -1]:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__)), "--worker", "--workloads", name,
                 "--histories", str(history), "--samples", str(args.samples),
                 "--retention", str(args.retention), "--max-bars", str(args.max_bars)],
                check=False, capture_output=True, text=True, cwd=ROOT,
            )
            if completed.returncode:
                report["failure"] = {"workload": name, "history": history, "repeat": repeat,
                                     "stderr": completed.stderr, "exitCode": completed.returncode}
                save()
                raise RuntimeError(completed.stderr)
            result = json.loads(completed.stdout)
            result["repeat"] = repeat
            report["results"].append(result)
            save()
            print(f"{name} history={history} repeat={repeat}: "
                  f"preview={result['preview']['medianMs']:.3f}ms "
                  f"confirmed={result['confirmed']['medianMs']:.3f}ms", flush=True)
    report["completed"] = True
    report["finishedUtc"] = datetime.now(timezone.utc).isoformat()
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
