"""Bounded long-session capacity harness for standalone pyne-runtime.

Measures sustained request, cyclic-trading, and TA sessions with repeated
preview and confirmed commits. One process advances sessions sequentially in
round-robin order; this is not parallel CPU throughput. Each configured session
count runs in a fresh child process so RSS is not accumulated across cases.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pyne_runtime as pn  # noqa: E402
from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION  # noqa: E402

WORKLOADS = ("requests", "strategy_cycles", "ta_chain")
ASSETS = ROOT / "tests" / "workloads"
SCHEMA = "pyne.runtime-capacity/1"
# Independent expected arithmetic from tests/test_semantic_workload_benchmark.py:
# each 12-bar cycle buys 4 at 14, sells 1 at 9, sells 3 at 15, three cash fees.
STRATEGY_NET_PER_CYCLE = -5
STRATEGY_COMMISSION_PER_CYCLE = 3
STRATEGY_INITIAL_CAPITAL = 10000
INVARIANTS = (
    "confirmed_prefix_retention",
    "preview_isolation",
    "typed_state_restore_committed",
    "typed_state_continuation_clone_vs_control",
    "measured_subject_not_advanced",
    "strategy_cycle_arithmetic",
    "strategy_active_position",
    "retained_bars_bounded",
    "request_cache_stats_observed",
)


def load_benchmark():
    path = Path(__file__).resolve().parent / "semantic_workload_benchmark.py"
    spec = importlib.util.spec_from_file_location("_pyne_semantic_workload_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BENCHMARK = load_benchmark()
_BAR_TEMPLATE = _BENCHMARK.bars(12)


def bar_at(index: int) -> dict[str, float | int]:
    """One chart bar; same close/volume formula as semantic_workload_benchmark.bars."""
    row = dict(_BAR_TEMPLATE[index % 12])
    row["time"] = index * 10
    row["volume"] = 0.0 if index % 7 == 0 else 10.0
    return row


def current_process_rss() -> dict[str, Any]:
    """Current RSS in bytes. Never labels ru_maxrss as current."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi")
        kernel32 = ctypes.WinDLL("kernel32")
        get_info = psapi.GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return {
            "bytes": int(counters.WorkingSetSize),
            "source": "windows.GetProcessMemoryInfo.WorkingSetSize",
            "supported": True,
        }
    if sys.platform.startswith("linux"):
        page = os.sysconf("SC_PAGE_SIZE")
        resident_pages = int(Path("/proc/self/statm").read_text(encoding="utf-8").split()[1])
        return {
            "bytes": int(resident_pages) * int(page),
            "source": "linux./proc/self/statm.residentPages*pageSize",
            "supported": True,
        }
    return {
        "bytes": None,
        "source": "unsupported",
        "supported": False,
        "detail": (
            f"no current-RSS sampler for platform {sys.platform!r}; "
            "resource.ru_maxrss is a peak and is not reported as current RSS"
        ),
    }


def positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check(name: str, passed: bool, **evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), **evidence}


def comparable_result(result: Any) -> dict[str, Any]:
    """Committed plots/strategy/retention. Trace omitted: harness sets trace_enabled=False."""
    meta = dict(result.meta)
    meta.pop("trace", None)
    return {
        "ok": result.ok,
        "error": result.error,
        "lines": result.lines,
        "output": result.output,
        "meta": {
            key: meta.get(key)
            for key in (
                "title",
                "retentionBars",
                "retainedBars",
                "totalCommittedBars",
                "requestDiagnosticsInfo",
            )
        },
        "requestDiagnostics": meta.get("requestDiagnostics"),
    }


def continuation_view(result: Any) -> dict[str, Any]:
    value = comparable_result(result)
    value.pop("requestDiagnostics", None)
    value["meta"].pop("requestDiagnosticsInfo", None)
    return value


def window_summary(samples: list[float]) -> dict[str, Any]:
    summary = _BENCHMARK.summarize(samples)
    summary.pop("samplesMs")  # Raw samples live only in the streamed JSONL.
    return summary


def plot_times(result: Any) -> list[int] | None:
    if not result.lines:
        return None
    series = [tuple(int(point["time"]) for point in line.get("data") or []) for line in result.lines]
    if not series:
        return None
    first = series[0]
    return list(first) if all(item == first for item in series) else list(first)


def request_cache_stats(session: Any) -> dict[str, Any]:
    """Private IncrementalRequestModule.cache_stats, instrumentation only."""
    request = session._globals.get("request")
    if request is None or not hasattr(request, "cache_stats"):
        return {"available": False, "reason": "request module has no cache_stats"}
    stats = request.cache_stats()
    return {"available": True, **stats}


def script_cache_stats(session: Any) -> dict[str, Any]:
    helper = session._globals.get("cache_stats")
    if not callable(helper):
        return {"available": False, "reason": "script cache_stats helper missing"}
    return {"available": True, **helper()}


def strategy_summary(result: Any) -> dict[str, Any] | None:
    payload = result.output.get("strategy") if result.output else None
    if not payload:
        return None
    return payload.get("summary")


def last_plot_value(result: Any, title: str) -> float | None:
    line = next((item for item in result.lines if item.get("name") == title), None)
    if line is None or not line.get("data"):
        return None
    value = line["data"][-1].get("value")
    return None if value is None else float(value)


def expected_position(committed_bars: int) -> float:
    index = (committed_bars - 1) % 12
    if 2 <= index < 5:
        return 4.0
    if 5 <= index < 9:
        return 3.0
    return 0.0


def observe_cache_pressure(
    stats: dict[str, Any],
    *,
    applied_limit: int,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    bars = stats.get("bars")
    fetches = stats.get("fetches")
    eviction = False
    evidence = (
        "eviction is not inferred from the cache-bars setting; "
        "only an observed drop in cached bars with additional fetches counts"
    )
    if (
        previous is not None
        and previous.get("available")
        and stats.get("available")
        and isinstance(bars, int)
        and isinstance(previous.get("bars"), int)
        and isinstance(fetches, int)
        and isinstance(previous.get("fetches"), int)
        and bars < previous["bars"]
        and fetches > previous["fetches"]
    ):
        eviction = True
        evidence = "cached bars decreased while fetches increased"
    pressure = None
    if isinstance(bars, int) and applied_limit:
        pressure = bars / applied_limit
    return {
        "appliedLimit": applied_limit,
        "bars": bars,
        "coveredRanges": stats.get("coveredRanges"),
        "fetches": stats.get("fetches"),
        "series": stats.get("series"),
        "pressure": pressure,
        "evictionObserved": eviction,
        "evidence": evidence,
    }


def digest_paths(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def runtime_digest() -> str:
    pieces = "".join(
        str(path.relative_to(ROOT)) + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src").rglob("*.py"))
    )
    return hashlib.sha256(pieces.encode()).hexdigest()


def git_identity() -> tuple[str, str]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"<unavailable {exc}>", f"<unavailable {exc}>"
    return head, status


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def emit_event(stream: TextIO, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload, allow_nan=False) + "\n")
    stream.flush()


def output_point_budget(retention: int, cache_bars: int) -> int:
    # max_output_points is both request max_cached_bars and plot/strategy budget.
    return max(int(cache_bars), int(retention) * 32)


def build_settings(*, max_bars: int, cache_bars: int, retention: int, horizon: int):
    applied = output_point_budget(retention, cache_bars)
    return pn.PyneSettings(
        executor_mode="inline",
        timeframe="10S",
        syminfo={"tickerid": "TEST:ASSET"},
        data_provider=_BENCHMARK.Provider(horizon),
        max_bars=max_bars,
        max_output_points=applied,
        trace_enabled=False,
    ), applied


def make_session(name: str, settings, retention: int):
    source = (ASSETS / f"{name}.py").read_text(encoding="utf-8")
    session = pn.PyneIncrementalSession(
        script=source, settings=settings, retention_bars=retention
    )
    session.prepare()
    return source, session


def session_window_checks(
    *,
    session,
    source: str,
    settings,
    workload: str,
    committed_bars: int,
    retention: int,
    next_bar: dict[str, float | int],
    applied_cache_limit: int,
    previous_request_cache: dict[str, Any] | None,
) -> dict[str, Any]:
    timed = _BENCHMARK.timed
    checked = _BENCHMARK.checked
    committed = session.snapshot_result()
    meta = committed.meta
    retained = int(meta.get("retainedBars") or 0)
    total = int(meta.get("totalCommittedBars") or 0)
    times = plot_times(committed)
    expected_start = bar_at(max(0, committed_bars - min(retention, committed_bars)))["time"]
    expected_end = bar_at(committed_bars - 1)["time"]
    prefix_ok = (
        total == committed_bars
        and retained == min(retention, committed_bars)
        and times is not None
        and len(times) == retained
        and times[0] == expected_start
        and times[-1] == expected_end
    )
    encode_ms, payload = timed(lambda: session.snapshot_portable(mode="state"))
    typed_bytes = len(payload)
    restore_ms, restored = timed(
        lambda: pn.PyneIncrementalSession.from_portable_snapshot(
            payload, script=source, settings=settings
        )
    )
    restored_committed = comparable_result(restored.snapshot_result())
    original_committed = comparable_result(committed)
    restore_ok = restored_committed == original_committed
    continuation = continuation_view(checked(restored.on_bar_closed(next_bar)))
    still = comparable_result(session.snapshot_result())
    subject_held = still == original_committed
    request_stats = request_cache_stats(session)
    script_stats = script_cache_stats(session)
    pressure = observe_cache_pressure(
        request_stats, applied_limit=applied_cache_limit, previous=previous_request_cache
    )
    checks = [
        check(
            "confirmed_prefix_retention",
            prefix_ok,
            retainedBars=retained,
            totalCommittedBars=total,
            firstTime=None if times is None else times[0],
            lastTime=None if times is None else times[-1],
            expectedFirstTime=expected_start,
            expectedLastTime=expected_end,
        ),
        # Filled from actual measured events, never an extra cache-warming preview.
        check("preview_isolation", True, pendingMeasuredEvidence=True),
        check(
            "typed_state_restore_committed",
            restore_ok,
            compared="lines/output/retention meta; trace excluded because trace_enabled=False",
        ),
        check(
            "typed_state_continuation_clone_vs_control",
            False,
            pending=True,
            compared="restored next close vs next actual close of un-restored measured subject; request diagnostics excluded",
        ),
        check("measured_subject_not_advanced", subject_held),
        check("retained_bars_bounded", retained <= retention and retained == min(retention, total)),
        check(
            "request_cache_stats_observed",
            request_stats.get("available", False),
            **{key: value for key, value in request_stats.items() if key != "available"},
        ),
    ]
    if workload == "strategy_cycles":
        summary = strategy_summary(committed) or {}
        position = last_plot_value(committed, "Position")
        want_position = expected_position(committed_bars)
        active_ok = position == want_position
        if committed_bars % 12 == 0:
            cycles = committed_bars // 12
            want_net = STRATEGY_NET_PER_CYCLE * cycles
            want_commission = STRATEGY_COMMISSION_PER_CYCLE * cycles
            want_equity = STRATEGY_INITIAL_CAPITAL + want_net
            arithmetic_ok = (
                summary.get("netprofit") == want_net
                and summary.get("commission") == want_commission
                and summary.get("equity") == want_equity
            )
            checks.append(
                check(
                    "strategy_cycle_arithmetic",
                    arithmetic_ok,
                    cycles=cycles,
                    expected={"netprofit": want_net, "commission": want_commission, "equity": want_equity},
                    actual={
                        "netprofit": summary.get("netprofit"),
                        "commission": summary.get("commission"),
                        "equity": summary.get("equity"),
                    },
                    basis="known cycle arithmetic (net -5, commission 3 per 12 bars), not a runtime replay oracle",
                )
            )
        else:
            checks.append(
                check(
                    "strategy_cycle_arithmetic",
                    True,
                    applicable=False,
                    reason="complete-cycle arithmetic is checked only when committedBars % 12 == 0",
                )
            )
        checks.append(
            check(
                "strategy_active_position",
                active_ok,
                expected=want_position,
                actual=position,
                basis="bar_index % 12 lifecycle of strategy_cycles.py; non-zero while the cycle is in a trade",
            )
        )
    else:
        checks.append(
            check(
                "strategy_cycle_arithmetic",
                True,
                applicable=False,
                reason=f"{workload} is not strategy_cycles",
            )
        )
        checks.append(
            check(
                "strategy_active_position",
                True,
                applicable=False,
                reason=f"{workload} is not strategy_cycles",
            )
        )
    del restored
    return {
        "_continuationExpected": continuation,
        "workload": workload,
        "totalCommittedBars": total,
        "retainedBars": retained,
        "typedState": {
            "bytes": typed_bytes,
            "encodeMs": encode_ms,
            "restoreMs": restore_ms,
        },
        "requestCache": request_stats,
        "scriptCache": script_stats,
        "cachePressure": pressure,
        "checks": checks,
    }


def run_worker(args: argparse.Namespace) -> dict[str, Any]:
    sessions_count = int(args.sessions[0])
    bars = int(args.bars)
    previews_per_bar = int(args.previews_per_bar)
    sample_every = int(args.sample_every)
    retention = int(args.retention)
    max_bars = int(args.max_bars)
    cache_bars = int(args.cache_bars)
    deadline = time.monotonic() + float(args.timeout_seconds)
    horizon = (bars + 8) * 10
    settings, applied_cache_limit = build_settings(
        max_bars=max_bars, cache_bars=cache_bars, retention=retention, horizon=horizon
    )
    assignments = [WORKLOADS[index % len(WORKLOADS)] for index in range(sessions_count)]
    harness_rss = current_process_rss()
    prepared = [make_session(name, settings, retention) for name in assignments]
    sessions_rss = current_process_rss()
    events_path = args.events
    events_path.parent.mkdir(parents=True, exist_ok=True)
    case = {
        "sessions": sessions_count,
        "workloads": assignments,
        "appliedMaxOutputPoints": applied_cache_limit,
        "requestedCacheBars": cache_bars,
        "harnessBaselineRss": harness_rss,
        "sessionsCreatedRss": sessions_rss,
        "eventsPath": str(events_path.relative_to(ROOT)) if events_path.is_relative_to(ROOT) else str(events_path),
        "retainedMeasurementArrays": (
            "per-window preview/confirmed latency lists only; raw events streamed to JSONL; "
            "bars generated by index without a growing input array"
        ),
        "windows": [],
        "completed": False,
        "invariantFailures": [],
    }
    write_json(args.output, case)
    preview_window: list[float] = []
    confirmed_window: list[float] = []
    previous_request = [None] * sessions_count
    pending = [None] * sessions_count
    preview_checks = [True] * sessions_count
    prefix_checks = [True] * sessions_count
    offsets = tuple(
        (0.5 + 0.5 * (index // 2)) * (1 if index % 2 == 0 else -1)
        for index in range(previews_per_bar)
    )
    timed = _BENCHMARK.timed
    checked = _BENCHMARK.checked
    with events_path.open("w", encoding="utf-8") as events:
        for bar_index in range(bars):
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"worker wall-clock timeout after {args.timeout_seconds}s at bar {bar_index}"
                )
            row = bar_at(bar_index)
            for session_index, (source, session) in enumerate(prepared):
                # One sampled real bar per window; no synthetic visits added.
                sampled = bar_index % sample_every == 0
                before = session.snapshot_result() if sampled else None
                for offset in offsets:
                    elapsed, result = timed(
                        lambda update=dict(row, close=float(row["close"]) + offset),
                        live=session: live.on_bar_updated(update)
                    )
                    del result
                    emit_event(
                        events,
                        {
                            "utc": utc_now(),
                            "session": session_index,
                            "workload": assignments[session_index],
                            "barIndex": bar_index,
                            "kind": "preview",
                            "ms": elapsed,
                        },
                    )
                    preview_window.append(elapsed)
                if sampled:
                    preview_checks[session_index] &= session.snapshot_result() == before
                elapsed, result = timed(lambda live=session, item=row: live.on_bar_closed(item))
                checked(result)
                if pending[session_index] is not None:
                    evidence, wanted = pending[session_index]
                    evidence["passed"] = continuation_view(result) == wanted
                    evidence["pending"] = False
                    if not evidence["passed"]:
                        raise AssertionError("typed-state continuation differs from un-restored session")
                    pending[session_index] = None
                if sampled:
                    after = session.snapshot_result()
                    old = {(line["name"], p["time"]): p for line in before.lines for p in line["data"]}
                    new = {(line["name"], p["time"]): p for line in after.lines for p in line["data"]}
                    prefix_checks[session_index] &= all(new[key] == old[key] for key in old.keys() & new.keys())
                del result
                emit_event(
                    events,
                    {
                        "utc": utc_now(),
                        "session": session_index,
                        "workload": assignments[session_index],
                        "barIndex": bar_index,
                        "kind": "confirmed",
                        "ms": elapsed,
                    },
                )
                confirmed_window.append(elapsed)
            committed_bars = bar_index + 1
            if committed_bars % sample_every != 0 and committed_bars != bars:
                continue
            rss = current_process_rss()
            next_bar = bar_at(committed_bars)
            session_reports = []
            for session_index, (source, session) in enumerate(prepared):
                report = session_window_checks(
                    session=session,
                    source=source,
                    settings=settings,
                    workload=assignments[session_index],
                    committed_bars=committed_bars,
                    retention=retention,
                    next_bar=next_bar,
                    applied_cache_limit=applied_cache_limit,
                    previous_request_cache=previous_request[session_index],
                )
                report["index"] = session_index
                wanted = report.pop("_continuationExpected")
                for item in report["checks"]:
                    if item["name"] == "typed_state_continuation_clone_vs_control":
                        pending[session_index] = (item, wanted)
                    if item["name"] == "preview_isolation":
                        item.pop("pendingMeasuredEvidence")
                        item["passed"] = preview_checks[session_index]
                        item["scope"] = "first measured bar per window, all its actual previews"
                    if item["name"] == "confirmed_prefix_retention":
                        item["passed"] &= prefix_checks[session_index]
                        item["valuesScope"] = "retained overlap on first measured commit per window"
                previous_request[session_index] = report["requestCache"]
                session_reports.append(report)
                for item in report["checks"]:
                    if not item["passed"] and not item.get("pending"):
                        case["invariantFailures"].append(
                            {
                                "windowCommittedBars": committed_bars,
                                "session": session_index,
                                "workload": assignments[session_index],
                                "check": item["name"],
                            }
                        )
            window = {
                "utc": utc_now(),
                "committedBars": committed_bars,
                "processRss": rss,
                "harnessBaselineRssBytes": harness_rss.get("bytes"),
                "sessionsCreatedRssBytes": sessions_rss.get("bytes"),
                "rssNote": (
                    "current process WorkingSet/statm RSS, sampled outside event timings and "
                    "before typed-state encode; includes Python, harness, provider, and sessions. "
                    "Not tracemalloc and not ru_maxrss."
                ),
                "preview": window_summary(preview_window),
                "confirmed": window_summary(confirmed_window),
                "sessions": session_reports,
            }
            case["windows"].append(window)
            write_json(args.output, case)
            preview_window = []
            confirmed_window = []
            print(
                f"sessions={sessions_count} bars={committed_bars} "
                f"rss={rss.get('bytes')} previewMedian={window['preview']['medianMs']:.3f}ms "
                f"confirmedMedian={window['confirmed']['medianMs']:.3f}ms",
                flush=True,
            )
    # Resolve the last snapshot continuation on a real subject commit, outside
    # the measured event stream. Earlier checks resolve on normal measured bars.
    for index, (_, session) in enumerate(prepared):
        evidence, wanted = pending[index]
        observed = continuation_view(checked(session.on_bar_closed(bar_at(bars))))
        evidence["passed"] = observed == wanted
        evidence["pending"] = False
        if observed != wanted:
            case["invariantFailures"].append({"session": index, "check": evidence["name"]})
    case["finalContinuationProbe"] = {"barIndex": bars, "outsideMeasuredEvents": True}
    case["completed"] = not case["invariantFailures"]
    case["finishedUtc"] = utc_now()
    write_json(args.output, case)
    if case["invariantFailures"]:
        raise RuntimeError(f"invariant failures: {case['invariantFailures']}")
    return case


def identity_report(args: argparse.Namespace) -> dict[str, Any]:
    head, status = git_identity()
    tracked = [
        Path(__file__).resolve(),
        Path(__file__).resolve().parent / "semantic_workload_benchmark.py",
        *[ASSETS / f"{name}.py" for name in WORKLOADS],
    ]
    config = {key: value for key, value in vars(args).items() if key not in ("output", "worker", "events")}
    for key, value in list(config.items()):
        if isinstance(value, Path):
            config[key] = str(value)
    return {
        "schema": SCHEMA,
        "completed": False,
        "startedUtc": utc_now(),
        "gitHead": head,
        "gitStatus": status,
        "sourceSha256": digest_paths(tracked),
        "runtimeSourceSha256": runtime_digest(),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "logicalCpus": os.cpu_count(),
        "semanticsVersion": INCREMENTAL_SEMANTICS_VERSION,
        "config": config,
        "method": (
            "one process sequential round-robin over sessions cycling workloads "
            f"{list(WORKLOADS)}; not parallel CPU throughput; fresh child process per "
            "session-count case; raw preview/confirmed latency streamed to JSONL outside "
            "timed regions; current RSS via Windows GetProcessMemoryInfo WorkingSetSize or "
            "Linux /proc/self/statm; typed-state snapshot restore vs clone control without "
            "advancing the measured subject; no absolute performance gate"
        ),
        "invariantsDeclared": list(INVARIANTS),
        "rssMethod": current_process_rss(),
        "cases": [],
    }


def run_parent(args: argparse.Namespace) -> int:
    report = identity_report(args)
    write_json(args.output, report)
    script = str(Path(__file__).resolve())
    for sessions in args.sessions:
        case_path = args.output.with_name(f"{args.output.stem}.s{sessions}.json")
        events_path = args.output.with_name(f"{args.output.stem}.s{sessions}.events.jsonl")
        command = [
            sys.executable,
            script,
            "--worker",
            "--sessions",
            str(sessions),
            "--bars",
            str(args.bars),
            "--previews-per-bar",
            str(args.previews_per_bar),
            "--sample-every",
            str(args.sample_every),
            "--retention",
            str(args.retention),
            "--max-bars",
            str(args.max_bars),
            "--cache-bars",
            str(args.cache_bars),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--output",
            str(case_path),
            "--events",
            str(events_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(ROOT),
                timeout=float(args.process_timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            case = {}
            if case_path.exists():
                case = json.loads(case_path.read_text(encoding="utf-8"))
            report["cases"].append(case)
            report["failure"] = {
                "sessions": sessions,
                "reason": "process-timeout",
                "timeoutSeconds": args.process_timeout_seconds,
                "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            }
            write_json(args.output, report)
            return 1
        case = {}
        if case_path.exists():
            case = json.loads(case_path.read_text(encoding="utf-8"))
        report["cases"].append(case)
        if completed.returncode:
            report["failure"] = {
                "sessions": sessions,
                "exitCode": completed.returncode,
                "stderr": completed.stderr,
                "stdout": completed.stdout,
            }
            write_json(args.output, report)
            return 1
        write_json(args.output, report)
        print(completed.stdout, end="", flush=True)
    report["completed"] = True
    report["finishedUtc"] = utc_now()
    write_json(args.output, report)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", nargs="+", type=positive, default=[1])
    parser.add_argument("--bars", type=positive, default=4096)
    parser.add_argument("--previews-per-bar", type=positive, default=4)
    parser.add_argument("--sample-every", type=positive, default=256)
    parser.add_argument("--retention", type=positive, default=64)
    parser.add_argument("--max-bars", type=positive, default=256)
    parser.add_argument("--cache-bars", type=positive, default=2048)
    parser.add_argument("--timeout-seconds", type=positive_float, default=7200.0)
    parser.add_argument("--process-timeout-seconds", type=positive_float, default=7200.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.retention > args.max_bars:
        parser.error("retention must be <= max-bars")
    if args.worker and len(args.sessions) != 1:
        parser.error("worker mode accepts exactly one --sessions value")
    if args.output is None:
        parser.error("--output is required")
    if args.worker and args.events is None:
        parser.error("worker mode requires --events")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.worker:
        run_worker(args)
        return 0
    return run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
