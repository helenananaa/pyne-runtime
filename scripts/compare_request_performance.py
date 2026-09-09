"""Paired old/new source comparison using the existing whole-script harness."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/semantic_workload_benchmark.py"
WORKER = '''
import sys, pathlib, runpy, hashlib, json, tracemalloc
source = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source))
import pyne_runtime as pn
assert pathlib.Path(pn.__file__).resolve().is_relative_to(source)
module = runpy.run_path(sys.argv[2])
measure = module["measure"]
original = measure.__globals__["checked"]
digest = hashlib.sha256()
def checked(value):
    value = original(value)
    if hasattr(value, "output") and not tracemalloc.is_tracing():
        digest.update(json.dumps(dict(lines=value.lines, output=value.output, meta=value.meta),
                                 sort_keys=True, separators=(",", ":")).encode())
    return value
measure.__globals__["checked"] = checked
result = measure("requests", int(sys.argv[3]), 32, 64, 256)
result["semanticDigest"] = digest.hexdigest()
result["importedRuntime"] = str(pathlib.Path(pn.__file__).resolve())
print(json.dumps(result, allow_nan=False))
'''


def source_digest(root):
    return hashlib.sha256("".join(
        p.relative_to(root).as_posix() + hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
        for p in sorted(root.rglob("*.py"))
    ).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    roots = {"before": args.baseline_src.resolve(), "after": ROOT / "src"}
    if args.repeats < 1 or roots["before"] == roots["after"] or any(
        not (p / "pyne_runtime/__init__.py").is_file() for p in roots.values()
    ):
        parser.error("distinct valid source roots and positive repeats required")
    report = {
        "schema": "pyne.paired-request-performance/1", "completed": False,
        "startedUtc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "sourceRoots": {k: str(v) for k, v in roots.items()},
        "sourceSha256": {k: source_digest(v) for k, v in roots.items()},
        "harnessSha256": hashlib.sha256(HARNESS.read_text(encoding="utf-8").encode()).hexdigest(),
        "comparatorSha256": hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode()).hexdigest(),
        "method": "alternating before/after fresh processes; histories 64/256/1024; samples 32; "
                  "retention 64; max_bars 256; output hashing outside timed/traced sections; "
                  "same source scripts and provider; per-case semantic digest equality required",
        "repeats": args.repeats, "pairs": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    for repeat in range(args.repeats):
        for history in ([64, 256, 1024] if repeat % 2 == 0 else [1024, 256, 64]):
            pair = {"repeat": repeat, "history": history}
            for label in (["before", "after"] if repeat % 2 == 0 else ["after", "before"]):
                child = subprocess.run([sys.executable, "-c", WORKER, str(roots[label]),
                                        str(HARNESS), str(history)], cwd=ROOT,
                                       capture_output=True, text=True)
                if child.returncode:
                    report["failure"] = {"variant": label, "history": history,
                                         "repeat": repeat, "stderr": child.stderr}
                    save()
                    raise RuntimeError(child.stderr)
                pair[label] = json.loads(child.stdout)
            report["pairs"].append(pair)
            pair["equalOutputs"] = pair["before"]["semanticDigest"] == pair["after"]["semanticDigest"]
            save()
            if not pair["equalOutputs"]:
                raise AssertionError("before/after output mismatch")
            print(f"history={history} repeat={repeat}: preview "
                  f"{pair['before']['preview']['medianMs']:.3f} -> "
                  f"{pair['after']['preview']['medianMs']:.3f} ms", flush=True)
    report["completed"] = True
    report["finishedUtc"] = datetime.now(timezone.utc).isoformat()
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
