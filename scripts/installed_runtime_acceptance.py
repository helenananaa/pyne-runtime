"""Run representative workflows with an independently installed wheel only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _require_installed_origin(expected_prefix: Path, repo_root: Path) -> Path:
    import pyne_runtime
    origin = Path(pyne_runtime.__file__).resolve()
    if not origin.is_relative_to(expected_prefix.resolve()):
        raise RuntimeError(f"acceptance import escaped expected prefix: {origin}")
    if origin.is_relative_to((repo_root / "src").resolve()):
        raise RuntimeError(f"acceptance imported repository source: {origin}")
    return origin


def verify_hash(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    require(actual == expected, f"fixture hash mismatch: {path.name}")


def plot_points(result: Any) -> dict[str, list[dict[str, Any]]]:
    require(result.ok, str(result.error))
    return {line["name"]: line["data"] for line in result.lines}


def compare_capture(result: Any, rows: list[dict[str, Any]]) -> int:
    actual = plot_points(result)
    count = 0
    for index, title in enumerate(("DI+", "DI-", "ADX")):
        expected = [{"time": row["time"], "value": round(row["values"][index], 8)}
                    for row in rows if row["values"][index] is not None]
        observed = actual.get(title, [])
        require([p["time"] for p in observed] == [p["time"] for p in expected],
                f"{title} timestamp/warmup mismatch")
        for point, wanted in zip(observed, expected):
            require(abs(point["value"] - wanted["value"]) <= 1e-9,
                    f"{title} mismatch at {wanted['time']}")
        count += len(expected)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--expected-prefix", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    origin = _require_installed_origin(args.expected_prefix, root)
    import pyne_runtime as pn
    from pyne_runtime.incremental.checkpoint import INCREMENTAL_SEMANTICS_VERSION

    directory = root / "tests" / "migrations" / "adx_di"
    capture = json.loads((directory / "tradingview.json").read_text(encoding="utf-8"))
    for name, digest in capture["sha256"].items():
        verify_hash(directory / name, digest)
    rows = capture["rows"]
    raw = (directory / "tradingview.txt").read_text(encoding="utf-8").splitlines()
    require(len(rows) == len(raw) == 80, "expected exactly 80 capture rows")
    for index, (row, line) in enumerate(zip(rows, raw)):
        fields = line.split("PYNE_ADX|")[1].split("|")
        require(row["index"] == int(fields[0]) == index, "capture row identity mismatch")
        require(row["time"] * 1000 == int(fields[1]), "capture timestamp mapping mismatch")
        values = [None if value == "NaN" else float(value) for value in fields[2:]]
        require(row["ohlcv"] + row["values"] == values, "raw capture differs from JSON")
    bars = [dict(time=row["time"], **dict(zip(capture["ohlcvColumns"], row["ohlcv"])))
            for row in rows]
    points = 0
    settings = pn.PyneSettings(executor_mode="inline", timeframe="15")
    for mode in ("batch", "incremental"):
        source = (directory / f"{mode}.py").read_text(encoding="utf-8")
        result = pn.run(source, bars, settings=settings)
        points += compare_capture(result, rows)
        report = pn.inspect_script(source)
        require(report["compatibility"]["supported"], f"{mode} unsupported")
        require(not report["migration"]["diagnostics"], f"{mode} has migration advice")
        if mode == "incremental":
            threshold = plot_points(result).get("Threshold", [])
            require(len(threshold) == 80 and all(p["value"] == 20 for p in threshold),
                    "threshold reference lost")
    naive = (directory / "naive.py").read_text(encoding="utf-8")
    advice = pn.inspect_script(naive)["migration"]["diagnostics"]
    require(any(item["code"] == "PYNE_MIGRATION_HINT" for item in advice),
            "Inspector omitted migration hints")
    require(not pn.run(naive, bars, settings=settings).ok, "naive migration unexpectedly succeeded")

    source = (directory / "incremental.py").read_text(encoding="utf-8")
    session = pn.PyneIncrementalSession(script=source, settings=settings, retention_bars=24)
    for index, bar in enumerate(bars):
        if index:
            before = copy.deepcopy(session.snapshot_result())
            preview = dict(bar, close=bar["close"] + 10, high=max(bar["high"], bar["close"] + 10))
            require(session.on_bar_updated(preview).ok, "preview failed")
            require(session.snapshot_result() == before, "preview changed committed state")
        session.on_bar_closed(bar)
        points += compare_capture(session.snapshot_result(), rows[max(0, index + 1 - 24):index + 1])
        if index in (12, 39):
            before = copy.deepcopy(session.snapshot_result())
            session = pn.PyneIncrementalSession.from_portable_snapshot(
                session.snapshot_portable_state(), script=source, settings=settings)
            require(session.snapshot_result() == before, "state restore changed committed result")

    legacy = root / "tests" / "golden" / "snapshot_semantics"
    provenance = json.loads((legacy / "provenance.json").read_text(encoding="utf-8"))
    for name, digest in provenance["sha256"].items():
        verify_hash(legacy / name, digest)
    legacy_script = (legacy / "indicator.pyne").read_text(encoding="utf-8")
    for folder in ("snapshot_semantics", "snapshot_semantics_v1", "snapshot_semantics_v2"):
        old = legacy.parent / folder
        old_provenance = json.loads((old / "provenance.json").read_text(encoding="utf-8"))
        for name, digest in old_provenance["sha256"].items():
            verify_hash(old / name, digest)
        old_script = (old / "indicator.pyne").read_text(encoding="utf-8")
        try:
            pn.PyneIncrementalSession.from_portable_snapshot(
                (old / "state.json").read_bytes(), script=old_script)
        except pn.PynePortableSnapshotError as error:
            require(error.code == "PYNE_SNAPSHOT_SEMANTICS_MISMATCH", "unexpected legacy rejection")
        else:
            raise RuntimeError(f"legacy snapshot accepted: {folder}")
    rebuilt = pn.PyneIncrementalSession(
        script=legacy_script, settings=pn.PyneSettings(executor_mode="inline", timeframe="1S"))
    rebuild_bars = [dict(time=i, open=float(i+1), high=float(i+2), low=float(i),
                         close=float(i+1), volume=10.) for i in range(5)]
    rebuilt.seed(rebuild_bars[:4])
    # Current declared EMA(3): mean of 1,2,3 seeds 2; 4 -> 3; 5 -> 4.
    require(plot_points(rebuilt.snapshot_result())["EMA"][-1]["value"] == 3., "rebuild seed mismatch")
    require(plot_points(rebuilt.on_bar_closed(rebuild_bars[4]))["EMA"][-1]["value"] == 4.,
            "rebuild continuation mismatch")
    print(json.dumps({"ok": True, "cases": 5, "pointsChecked": points,
                      "packageVersion": pn.__version__, "importPath": str(origin),
                      "semanticsIdentity": INCREMENTAL_SEMANTICS_VERSION}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
