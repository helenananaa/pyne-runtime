"""Command-line interface for Pyne."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from ._version import __version__
from .api import read_ohlcv, run, validate
from .inspection import inspect_path, inspect_script
from .errors import error_detail
from .settings import OPTIONAL_BUDGET_FIELDS, PyneSettings


_TEMPLATES = ("trend", "volatility", "state")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pyne")
    parser.add_argument("--version", action="version", version=f"pyne {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create a script for CSV and realtime use")
    new_parser.add_argument("script")
    new_parser.add_argument("--template", choices=_TEMPLATES, default="trend")

    run_parser = subparsers.add_parser("run", help="Run a Pyne script against OHLCV CSV data")
    run_parser.add_argument("script")
    run_parser.add_argument("--ohlcv", required=True)
    run_parser.add_argument("--out")
    run_parser.add_argument("--format", choices=("json", "csv"), default="json")
    run_parser.add_argument("--series", action="append", default=[], metavar="NAME",
                            help="Select plotted series for CSV output; repeat for more columns")
    run_parser.add_argument("--time-unit", choices=("s", "ms"), default="s")
    run_parser.add_argument("--column", action="append", default=[], metavar="FIELD=COLUMN",
                            help="Map an OHLCV field to a CSV header, e.g. time=timestamp")
    _add_policy_options(run_parser)
    run_parser.add_argument("--executor-mode")
    run_parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override an input.* parameter. May be used multiple times.",
    )
    run_parser.add_argument(
        "--params-json",
        help="Parameter overrides as a JSON object or a path to a JSON file.",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a Pyne script")
    validate_parser.add_argument("script")
    _add_policy_options(validate_parser)
    validate_parser.add_argument("--runtime-mode", choices=("batch", "incremental"))
    validate_parser.add_argument("--target", choices=("preview", "snapshot"),
                                 help="Check statically visible incremental state boundaries")

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Print a static runtime requirement manifest for a Pyne script",
    )
    inspect_parser.add_argument("script")
    inspect_parser.add_argument("--runtime-mode", choices=("batch", "incremental"))
    inspect_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Inspect matching scripts recursively when the path is a directory",
    )
    inspect_parser.add_argument(
        "--pattern",
        default="*.py",
        help="Directory scan glob pattern (default: *.py)",
    )

    schema_parser = subparsers.add_parser("schema", help="Print the Pyne input/output schema")
    schema_parser.set_defaults(schema=True)

    args = parser.parse_args(argv)

    if args.command == "new":
        try:
            source = files("pyne_runtime").joinpath(
                "templates", f"{args.template}.py.txt").read_text(encoding="utf-8")
            with Path(args.script).open("x", encoding="utf-8") as handle:
                handle.write(source)
        except (OSError, UnicodeError) as exc:
            return _emit_cli_error("PYNE_CLI_INPUT_ERROR", str(exc))
        print(json.dumps({"ok": True, "script": args.script, "template": args.template}))
        return 0

    if args.command == "run":
        try:
            settings = _cli_settings(args)
            params = _load_params(args.param, args.params_json)
            if args.series and args.format != "csv":
                raise ValueError("--series requires --format csv")
            data = read_ohlcv(args.ohlcv, time_unit=args.time_unit,
                             columns=_load_columns(args.column))
            result = run(
                Path(args.script),
                data,
                params=params,
                settings=settings,
                executor_mode=args.executor_mode,
            )
            payload = result.to_dict()
            if not result.ok and (args.format == "csv" or args.out):
                print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
                return 1
            rendered = (_series_csv(result, args.series) if args.format == "csv"
                        else json.dumps(payload, ensure_ascii=False, indent=2))
            if args.out:
                Path(args.out).write_text(
                    rendered, encoding="utf-8", newline="",
                )
            else:
                print(rendered, end="" if args.format == "csv" else "\n")
        except Exception as exc:
            return _emit_cli_error("PYNE_CLI_INPUT_ERROR", str(exc))
        return 0 if result.ok else 1

    if args.command == "validate":
        try:
            diagnostics = validate(Path(args.script), settings=_cli_settings(args),
                                   runtime_mode=args.runtime_mode, target=args.target)
        except (OSError, UnicodeError, ValueError) as exc:
            return _emit_cli_error("PYNE_CLI_INPUT_ERROR", str(exc))
        print(json.dumps({"ok": not diagnostics, "diagnostics": diagnostics}, indent=2))
        return 0 if not diagnostics else 1

    if args.command == "inspect":
        try:
            path = Path(args.script)
            if path.is_dir():
                report = inspect_path(
                    path,
                    runtime_mode=args.runtime_mode,
                    recursive=args.recursive,
                    pattern=args.pattern,
                )
                supported = report["summary"]["unsupportedCount"] == 0
            else:
                source = path.read_text(encoding="utf-8")
                report = inspect_script(source, runtime_mode=args.runtime_mode)
                supported = report["compatibility"]["supported"]
        except (OSError, UnicodeError, ValueError) as exc:
            return _emit_cli_error("PYNE_CLI_INPUT_ERROR", str(exc))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if supported else 1

    if args.command == "schema":
        from .api import schema

        print(json.dumps(schema(), indent=2))
        return 0

    parser.error("unknown command")
    return 2


def _add_policy_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--security-mode", choices=("unsafe", "safe", "research"),
                        help="Import policy; standalone default is full Python (unsafe)")
    parser.add_argument("--allowed-import", action="append", default=None, metavar="MODULE",
                        help="Research allowlist (repeat); replaces the configured list")
    parser.add_argument("--timeout-seconds", default=argparse.SUPPRESS, metavar="SECONDS|none",
                        help="Execution deadline; none disables it (standalone default)")
    parser.add_argument("--limit", action="append", default=[], metavar="NAME=VALUE",
                        help="Set a PyneSettings resource budget; use none for unlimited")


def _cli_settings(args: argparse.Namespace) -> PyneSettings:
    overrides: dict[str, Any] = {}
    if args.security_mode is not None:
        overrides["security_mode"] = args.security_mode
    if args.allowed_import is not None:
        overrides["allowed_imports"] = tuple(args.allowed_import)
    if hasattr(args, "timeout_seconds"):
        overrides["timeout_seconds"] = args.timeout_seconds
    allowed = {*OPTIONAL_BUDGET_FIELDS, "cache_max_items", "request_cache_max_bars"}
    for item in args.limit:
        name, separator, raw = item.partition("=")
        name, raw = name.strip(), raw.strip()
        if not separator or name not in allowed:
            raise ValueError(f"Unknown resource limit: {item}. Available: {', '.join(sorted(allowed))}")
        if name in overrides:
            raise ValueError(f"Duplicate resource limit: {name}")
        overrides[name] = None if raw.lower() in {"none", "unlimited"} else int(raw)
    return replace(PyneSettings.from_env(), **overrides)


def _load_columns(items: list[str]) -> dict[str, str]:
    columns: dict[str, str] = {}
    for item in items:
        key, separator, header = item.partition("=")
        key, header = key.strip(), header.strip()
        if (not separator or not header
                or key not in {"time", "time_close", "open", "high", "low", "close", "volume"}):
            raise ValueError(f"--column must use a known OHLCV FIELD=COLUMN: {item}")
        if key in columns:
            raise ValueError(f"Duplicate --column field: {key}")
        columns[key] = header
    return columns


def _series_csv(result: Any, selected: list[str]) -> str:
    lines = result.lines
    names = [str(line.get("name") or line.get("id") or "value") for line in lines]
    wanted = selected or names
    if not wanted:
        raise ValueError("No plotted series to export. Add plot(...), or use --format json for other outputs.")
    if len(wanted) != len(set(wanted)):
        raise ValueError("Duplicate --series selection")
    unknown = set(wanted) - set(names)
    if unknown:
        raise ValueError(f"Unknown plotted series: {', '.join(sorted(unknown))}. "
                         f"Available: {', '.join(names) or '(none)'}")
    if any(names.count(name) != 1 or name == "time" for name in wanted):
        raise ValueError("Selected CSV plots need unique names distinct from 'time'; rename those plots")
    rows: dict[int, dict[str, Any]] = {}
    for name, line in zip(names, lines):
        if name not in wanted:
            continue
        for point in line.get("data", []):
            timestamp = point["time"]
            rows.setdefault(timestamp, {"time": timestamp})[name] = point.get("value")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["time", *wanted], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows[time] for time in sorted(rows))
    return stream.getvalue()


def _load_params(param_items: list[str], params_json: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {}

    if params_json:
        params.update(_load_params_json(params_json))

    for item in param_items:
        if "=" not in item:
            raise ValueError(f"--param must use KEY=VALUE format: {item}")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--param key cannot be empty")
        params[key] = _parse_param_value(raw_value)

    return params


def _load_params_json(value: str) -> dict[str, Any]:
    path = Path(value)
    raw = value
    if not value.lstrip().startswith(("{", "[")):
        raw = path.read_text(encoding="utf-8") if path.exists() else value
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--params-json must be a JSON object: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("--params-json must be a JSON object")
    return payload


def _parse_param_value(value: str) -> Any:
    raw = value.strip()
    if raw == "":
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return value


def _emit_cli_error(code: str, message: str) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "error": error_detail(code, message),
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
