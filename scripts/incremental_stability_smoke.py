"""Deterministic multi-session durability smoke gate for incremental Pyne."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pyne_runtime as pn  # noqa: E402


SCRIPT = """
indicator("Stability", mode="incremental")
def on_bar(ctx, bar):
    total = ctx.state("total", params["offset"])
    total.value += bar.close
    ctx.plot("Total", total.value)
"""


def _bar(index: int, offset: float = 0.0) -> dict[str, float | int]:
    close = float(index) + offset
    return {
        "time": index,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 1.0,
    }


def _check(name: str, passed: bool, **evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), **evidence}


def _values(result: Any, title: str) -> list[float]:
    line = next(item for item in result.lines if item.get("name") == title)
    return [float(point["value"]) for point in line["data"]]


def build_report(*, session_count: int = 16, bar_count: int = 256) -> dict[str, Any]:
    count = max(int(session_count), 2)
    bars = max(int(bar_count), 8)
    settings = pn.PyneSettings(executor_mode="inline", max_bars=max(bars, 512), replay_history_bars=max(bars, 512))
    sessions = [
        pn.PyneIncrementalSession(
            script=SCRIPT,
            params={"offset": index * 1_000},
            settings=settings,
            retention_bars=32,
        )
        for index in range(count)
    ]
    for index, session in enumerate(sessions):
        session.seed([_bar(item, float(index)) for item in range(1, bars + 1)])

    tails = [_values(session.snapshot_result(), "Total")[-1] for session in sessions]
    isolation = len(set(tails)) == count
    retention = all(
        session.snapshot_result().meta["retainedBars"] == 32
        and len(_values(session.snapshot_result(), "Total")) == 32
        for session in sessions
    )
    payloads = [session.snapshot_portable() for session in sessions[:4]]
    deterministic = all(
        payload == sessions[index].snapshot_portable()
        for index, payload in enumerate(payloads)
    )
    restored = [
        pn.PyneIncrementalSession.from_portable_snapshot(
            payload,
            script=SCRIPT,
            settings=settings,
        )
        for payload in payloads
    ]
    recovery = all(
        item.snapshot_result() == sessions[index].snapshot_result()
        for index, item in enumerate(restored)
    )
    preview = sessions[0].on_bar_updated(_bar(bars + 1, 99.0))
    after_preview = sessions[0].snapshot_result()
    preview_isolated = (
        _values(preview, "Total")[-1] != _values(after_preview, "Total")[-1]
        and len(_values(after_preview, "Total")) == 32
    )
    checks = [
        _check("multi_session_isolation", isolation, sessions=count),
        _check("rolling_retention_bounds", retention, retentionBars=32),
        _check("portable_snapshot_determinism", deterministic, snapshots=len(payloads)),
        _check("portable_restore_equivalence", recovery, restored=len(restored)),
        _check("preview_state_isolation", preview_isolated),
    ]
    return {
        "schema": "pyne.incremental-stability-smoke.v1",
        "sessions": count,
        "barsPerSession": bars,
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sessions", type=int, default=16)
    parser.add_argument("--bars", type=int, default=256)
    args = parser.parse_args()
    report = build_report(session_count=args.sessions, bar_count=args.bars)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["checks"]:
            print(f"{'PASS' if item['passed'] else 'FAIL'} {item['name']}")
        print("PASS" if report["passed"] else "FAIL")
    return 1 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
