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
    for folder in ("snapshot_semantics", "snapshot_semantics_v1", "snapshot_semantics_v2",
                   "snapshot_semantics_v3", "snapshot_semantics_v4"):
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
    # Exercise standalone defaults in the actual installed wheel.
    defaults = pn.PyneSettings()
    require(defaults.executor_mode == "inline" and defaults.security_mode == "unsafe",
            "standalone execution defaults are not active")
    require(defaults.timeout_seconds is None and defaults.max_bars is None,
            "standalone limits unexpectedly enabled")
    large_bars = [dict(time=i, open=1., high=2., low=1., close=1.5, volume=1.)
                  for i in range(50_001)]
    standalone = pn.run("import math\nplot(close + math.sqrt(4))", large_bars)
    require(standalone.ok, str(standalone.error))
    require(len(standalone.lines[0]["data"]) == 50_001, "standalone input/output was capped")
    points += len(standalone.lines[0]["data"])
    source = "def on_bar(ctx, bar):\n    ctx.plot('Close', bar.close)"
    subject = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(max_output_points=1))
    subject.seed(large_bars[:1])
    subject = pn.PyneIncrementalSession.from_portable_snapshot(subject.snapshot_portable_state(),
        script=source, settings=pn.PyneSettings(timeout_seconds=30, cache_max_items=64))
    require(subject.on_bar_closed(large_bars[1]).ok, "restored budget was not relaxed")
    require(len(subject.snapshot_result().lines[0]["data"]) == 2, "restored output was capped")
    # Verify user-facing diagnostics and CLI parsing from the installed package.
    import io
    from contextlib import redirect_stdout, redirect_stderr
    from pyne_runtime.cli import main as cli_main

    class_source = "class Helper: pass\ndef on_bar(ctx, bar): ctx.plot('C', bar.close)"
    require(not pn.validate(class_source), "ordinary classes were blocked")
    require(pn.validate(class_source, target="snapshot")[0]["code"] == "PYNE_STATE_CONTRACT_ERROR",
            "snapshot preflight omitted retained class")
    quota = pn.run("array.new_float(3, 0)", large_bars[:1], settings=pn.PyneSettings(max_array_size=2))
    require(quota.code == "PYNE_RESOURCE_LIMIT_EXCEEDED" and "None" in quota.hint,
            "resource diagnostic is not actionable")
    feedback_script = Path.cwd() / "feedback-workflow.py"
    feedback_script.write_text("import math\nplot(close, 'Keep')\nplot(open, 'Other')\nplot(high, 'Other')",
                               encoding="utf-8")
    stdout, stderr = io.StringIO(), io.StringIO()
    policy_args = ["--security-mode", "research", "--allowed-import", "math"]
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli_main(["validate", str(feedback_script), *policy_args])
    require(code == 0 and json.loads(stdout.getvalue())["ok"], "CLI policy validation failed")
    stdout = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli_main(["run", str(feedback_script), "--ohlcv",
            str(root / "examples" / "sample_ohlcv.csv"), *policy_args,
            "--limit", "max_bars=none", "--timeout-seconds", "none",
            "--format", "csv", "--series", "Keep"])
    require(code == 0 and stdout.getvalue().startswith("time,Keep\n"), "selected CSV export failed")
    print(json.dumps({"ok": True, "cases": 9, "pointsChecked": points,
                      "packageVersion": pn.__version__, "importPath": str(origin),
                      "semanticsIdentity": INCREMENTAL_SEMANTICS_VERSION}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
