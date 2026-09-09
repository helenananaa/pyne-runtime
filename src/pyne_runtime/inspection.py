"""Static, source-free script requirement inspection for hosts and tooling."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from .capabilities import (
    BATCH_STRATEGY_CAPABILITIES,
    BATCH_TA_CAPABILITIES,
    DRAWING_CAPABILITIES,
    INCREMENTAL_STRATEGY_CAPABILITIES,
    INCREMENTAL_TA_CAPABILITIES,
    REQUEST_CAPABILITIES,
    _detect_runtime_mode,
    capability_diagnostics,
)
from .errors import error_detail
from .migration_diagnostics import migration_diagnostics, syntax_migration_diagnostics
from .pine_libraries import SUPPORTED_PINE_LIBRARIES
from .schema import PYNE_OUTPUT_SCHEMA_VERSION, PYNE_STRATEGY_REPORT_SCHEMA_VERSION


PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION = 2
PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION = 1
_DRAWING_NAMESPACES = frozenset(DRAWING_CAPABILITIES)
_KNOWN_DYNAMIC_NAMESPACES = frozenset({"ta", "request", "strategy", *_DRAWING_NAMESPACES})
_PLOT_COLLECTIONS = {
    "plot": "lines",
    "bar": "histograms",
    "plotbar": "candles",
    "plotcandle": "candles",
    "plotshape": "markers",
    "plotchar": "markers",
    "hline": "hlines",
    "fill": "fills",
    "bgcolor": "bgcolors",
    "barcolor": "barcolors",
    "emit_signal": "signals",
}
_FIXED_LOOKBACKS = {"swma": 4}
_DEFAULT_LOOKBACKS = {
    "atr": 14,
    "cci": 20,
    "change": 1,
    "macd": 26,
    "mfi": 14,
    "rsi": 14,
    "stoch": 14,
    "supertrend": 10,
    "tsi": 25,
    "wpr": 14,
}
_PERIOD_MEMBERS = frozenset(
    {
        "adx",
        "alma",
        "atr",
        "bb",
        "boll",
        "cci",
        "change",
        "cmo",
        "correlation",
        "dev",
        "dmi",
        "donchian",
        "ema",
        "falling",
        "highest",
        "highestbars",
        "hma",
        "keltner",
        "linreg",
        "lowest",
        "lowestbars",
        "macd",
        "mfi",
        "mom",
        "percentile_linear_interpolation",
        "percentile_nearest_rank",
        "rising",
        "rma",
        "roc",
        "rsi",
        "sma",
        "stdev",
        "stoch",
        "supertrend",
        "tsi",
        "variance",
        "volume_sma",
        "vwma",
        "wma",
        "wpr",
    }
)


def inspect_script(script: str, *, runtime_mode: str | None = None) -> dict[str, Any]:
    """Return a deterministic manifest of statically discoverable script requirements.

    The report never executes the script and never includes source text. Dynamic
    attribute construction is disclosed as an uncertainty instead of being
    treated as compatible.
    """
    source = str(script)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        diagnostics = [
            error_detail(
                "PYNE_SYNTAX_ERROR",
                str(exc.msg or exc),
                line=exc.lineno,
                column=exc.offset,
            )
        ]
        return {
            "schemaVersion": PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION,
            "scriptSha256": digest,
            "runtimeMode": _normalize_mode(runtime_mode) or "unknown",
            "declaration": None,
            "callbacks": [],
            "requirements": _empty_requirements(),
            "compatibility": {
                "supported": False,
                "diagnostics": diagnostics,
                "dynamicAccesses": [],
            },
            "resourceHints": _resource_hints(ast.Module(body=[], type_ignores=[])),
            "providerRequirements": [],
            "outputRequirements": _output_requirements(ast.Module(body=[], type_ignores=[]), {}),
            "migration": _migration_report(
                {},
                [],
                [],
                mode="unknown",
                diagnostics=syntax_migration_diagnostics(source),
            ),
        }

    mode = _normalize_mode(runtime_mode) or _detect_runtime_mode(tree)
    requirements: dict[str, set[str]] = {
        "ta": set(),
        "request": set(),
        "strategy": set(),
        "drawings": set(),
    }
    libraries: dict[str, set[str]] = {}
    dynamic_accesses: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node)
        if resolved is not None:
            namespace, member = resolved
            if namespace in requirements:
                requirements[namespace].add(member)
            elif namespace in _DRAWING_NAMESPACES:
                requirements["drawings"].add(namespace)
        library_call = _resolve_library_call(node)
        if library_call is not None:
            identifier, member = library_call
            libraries.setdefault(identifier, set()).add(member)
        dynamic = _dynamic_access(node)
        if dynamic is not None:
            dynamic_accesses.append(dynamic)

    supported = _mode_capabilities(mode)
    diagnostics = capability_diagnostics(source, runtime_mode=mode)
    diagnostics.extend(_requirement_diagnostics(requirements, supported, mode=mode))
    external_libraries = _library_requirements(libraries, mode=mode)
    for library in external_libraries:
        for member in library["unsupportedMembers"]:
            diagnostics.append(
                error_detail(
                    "PYNE_UNSUPPORTED_FEATURE",
                    f"Runtime mode {mode!r} does not support "
                    f"{library['identifier']}#{member}",
                    hint="Use a declared pinned adapter member or port the dependency explicitly.",
                )
            )

    host_requirements: set[str] = set()
    if requirements["request"]:
        host_requirements.add("dataProvider")
    if any(item["dataRequirements"] for item in external_libraries):
        host_requirements.add("dataProvider")
    hints = _resource_hints(tree)
    if hints["emitsSignals"]:
        host_requirements.add("signalDelivery")
    if hints["usesMarketMetadata"]:
        host_requirements.add("marketMetadata")

    provider_requirements = _provider_requirements(tree, external_libraries)
    output_requirements = _output_requirements(tree, requirements)
    migration = _migration_report(
        requirements,
        external_libraries,
        dynamic_accesses,
        mode=mode,
        diagnostics=migration_diagnostics(source),
    )

    return {
        "schemaVersion": PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION,
        "scriptSha256": digest,
        "runtimeMode": mode,
        "declaration": _declaration(tree),
        "callbacks": sorted(
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"init", "on_bar", "on_preview"}
        ),
        "requirements": {
            "ta": sorted(requirements["ta"]),
            "request": sorted(requirements["request"]),
            "strategy": sorted(requirements["strategy"]),
            "drawings": sorted(requirements["drawings"]),
            "externalLibraries": external_libraries,
            "host": sorted(host_requirements),
        },
        "compatibility": {
            "supported": not diagnostics and not dynamic_accesses,
            "diagnostics": _unique_diagnostics(diagnostics),
            "dynamicAccesses": sorted(
                dynamic_accesses,
                key=lambda item: (item["line"], item["column"], item["namespace"]),
            ),
        },
        "resourceHints": hints,
        "providerRequirements": provider_requirements,
        "outputRequirements": output_requirements,
        "migration": migration,
    }


def inspect_path(
    path: str | Path,
    *,
    runtime_mode: str | None = None,
    recursive: bool = True,
    pattern: str = "*.py",
) -> dict[str, Any]:
    """Inspect a file or a directory without returning source text."""
    root = Path(path)
    if root.is_file():
        report = inspect_script(root.read_text(encoding="utf-8"), runtime_mode=runtime_mode)
        return {
            "schemaVersion": PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION,
            "root": str(root.parent.resolve()),
            "pattern": pattern,
            "recursive": False,
            "summary": _inspection_summary([report]),
            "scripts": [{"path": root.name, "report": report}],
        }
    if not root.is_dir():
        raise ValueError(f"Inspection path does not exist or is not a file/directory: {root}")
    files = sorted(root.rglob(pattern) if recursive else root.glob(pattern))
    scripts = []
    for candidate in files:
        if not candidate.is_file():
            continue
        report = inspect_script(candidate.read_text(encoding="utf-8"), runtime_mode=runtime_mode)
        scripts.append(
            {
                "path": candidate.relative_to(root).as_posix(),
                "report": report,
            }
        )
    return {
        "schemaVersion": PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION,
        "root": str(root.resolve()),
        "pattern": pattern,
        "recursive": bool(recursive),
        "summary": _inspection_summary([item["report"] for item in scripts]),
        "scripts": scripts,
    }


def _inspection_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    supported = sum(bool(item["compatibility"]["supported"]) for item in reports)
    modes: dict[str, int] = {}
    provider_apis: set[str] = set()
    migration_blockers = 0
    for report in reports:
        mode = str(report.get("runtimeMode") or "unknown")
        modes[mode] = modes.get(mode, 0) + 1
        provider_apis.update(
            str(item["api"])
            for item in report.get("providerRequirements", [])
            if item.get("api")
        )
        migration_blockers += len(
            report.get("migration", {}).get("batchToIncremental", {}).get("blockers", [])
        )
    return {
        "scriptCount": len(reports),
        "supportedCount": supported,
        "unsupportedCount": len(reports) - supported,
        "runtimeModes": {key: modes[key] for key in sorted(modes)},
        "providerApis": sorted(provider_apis),
        "batchToIncrementalBlockerCount": migration_blockers,
    }


def _provider_requirements(
    tree: ast.AST,
    external_libraries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _resolve_call(node) not in {
            ("request", "security"),
            ("request", "security_lower_tf"),
        }:
            continue
        namespace, member = _resolve_call(node) or ("request", "")
        del namespace
        symbol = _constant_string(node.args[0]) if node.args else None
        timeframe = _constant_string(node.args[1]) if len(node.args) > 1 else None
        item = {
            "api": f"request.{member}",
            "symbol": symbol,
            "timeframe": timeframe,
            "dynamicSymbol": symbol is None,
            "dynamicTimeframe": timeframe is None,
            "line": int(node.lineno),
        }
        key = tuple(item.values())
        if key not in seen:
            seen.add(key)
            requirements.append(item)
    for library in external_libraries:
        for api in library["dataRequirements"]:
            item = {
                "api": api,
                "symbol": None,
                "timeframe": None,
                "dynamicSymbol": True,
                "dynamicTimeframe": True,
                "line": None,
                "source": library["identifier"],
            }
            key = tuple(item.values())
            if key not in seen:
                seen.add(key)
                requirements.append(item)
    return sorted(
        requirements,
        key=lambda item: (str(item["api"]), item.get("line") or -1, str(item.get("source") or "")),
    )


def _output_requirements(
    tree: ast.AST,
    requirements: dict[str, set[str]],
) -> dict[str, Any]:
    collections: set[str] = set()
    dynamic_titles = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_member_name(node)
        collection = _PLOT_COLLECTIONS.get(name)
        if collection is None:
            continue
        collections.add(collection)
        title = _call_title_argument(node, name)
        if title is not None and not isinstance(title, ast.Constant):
            dynamic_titles = True
    drawings = requirements.get("drawings", set())
    strategy = requirements.get("strategy", set())
    if drawings:
        collections.update({"objects", "object_events"})
    if strategy:
        collections.add("strategy")
    return {
        "outputSchemaVersion": PYNE_OUTPUT_SCHEMA_VERSION,
        "strategyReportSchemaVersion": (
            PYNE_STRATEGY_REPORT_SCHEMA_VERSION if strategy else None
        ),
        "collections": sorted(collections),
        "dynamicTitles": dynamic_titles,
    }


def _migration_report(
    requirements: dict[str, set[str]],
    external_libraries: list[dict[str, Any]],
    dynamic_accesses: list[dict[str, Any]],
    *,
    mode: str,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    for member in sorted(requirements.get("ta", set()) - set(INCREMENTAL_TA_CAPABILITIES)):
        blockers.append({"category": "ta", "requirement": f"ta.{member}"})
    for member in sorted(
        requirements.get("strategy", set()) - set(INCREMENTAL_STRATEGY_CAPABILITIES)
    ):
        blockers.append({"category": "strategy", "requirement": f"strategy.{member}"})
    for library in external_libraries:
        if library["members"]:
            blockers.append(
                {
                    "category": "externalLibrary",
                    "requirement": library["identifier"],
                    "members": list(library["members"]),
                }
            )
    for access in dynamic_accesses:
        blockers.append(
            {
                "category": "dynamicAccess",
                "requirement": access["namespace"],
                "line": access["line"],
            }
        )
    return {
        "batchToIncremental": {
            "applicable": mode == "batch",
            "eligible": not blockers,
            "blockers": blockers,
        },
        "diagnostics": list(diagnostics or []),
    }


def _call_member_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _call_title_argument(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg in {"title", "name"}:
            return keyword.value
    positional = {
        "plot": 1,
        "bar": 1,
        "plotbar": 4,
        "plotcandle": 4,
        "plotshape": 1,
        "plotchar": 1,
        "hline": 1,
        "emit_signal": 0,
    }.get(name)
    if positional is not None and len(node.args) > positional:
        return node.args[positional]
    return None


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _empty_requirements() -> dict[str, Any]:
    return {
        "ta": [],
        "request": [],
        "strategy": [],
        "drawings": [],
        "externalLibraries": [],
        "host": [],
    }


def _normalize_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized not in {"batch", "incremental"}:
        raise ValueError("runtime_mode must be 'batch' or 'incremental'")
    return normalized


def _resolve_call(node: ast.Call) -> tuple[str, str] | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if isinstance(owner, ast.Name):
        if owner.id == "ctx":
            drawing = node.func.attr.split("_", 1)[0]
            if drawing in _DRAWING_NAMESPACES:
                return "drawings", drawing
        return owner.id, node.func.attr
    if (
        isinstance(owner, ast.Attribute)
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "ctx"
    ):
        return owner.attr, node.func.attr
    return None


def _resolve_library_call(node: ast.Call) -> tuple[str, str] | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if not isinstance(owner, ast.Call) or not isinstance(owner.func, ast.Name):
        return None
    if owner.func.id != "pine_library" or not owner.args:
        return None
    identifier = owner.args[0]
    if not isinstance(identifier, ast.Constant) or not isinstance(identifier.value, str):
        return None
    return identifier.value, node.func.attr


def _dynamic_access(node: ast.Call) -> dict[str, Any] | None:
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr" or len(node.args) < 2:
        return None
    namespace = _attribute_path(node.args[0])
    if namespace.startswith("ctx."):
        namespace = namespace.removeprefix("ctx.")
    if namespace not in _KNOWN_DYNAMIC_NAMESPACES:
        return None
    member = node.args[1]
    if isinstance(member, ast.Constant) and isinstance(member.value, str):
        return None
    return {
        "namespace": namespace,
        "line": int(node.lineno),
        "column": int(node.col_offset) + 1,
        "reason": "dynamic-member-name",
    }


def _attribute_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_path(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _mode_capabilities(mode: str) -> dict[str, set[str]]:
    return {
        "ta": set(INCREMENTAL_TA_CAPABILITIES if mode == "incremental" else BATCH_TA_CAPABILITIES),
        "request": set(REQUEST_CAPABILITIES),
        "strategy": set(
            INCREMENTAL_STRATEGY_CAPABILITIES
            if mode == "incremental"
            else BATCH_STRATEGY_CAPABILITIES
        ),
        "drawings": set(DRAWING_CAPABILITIES),
    }


def _requirement_diagnostics(
    requirements: dict[str, set[str]],
    supported: dict[str, set[str]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for namespace in ("ta", "request", "strategy", "drawings"):
        for member in sorted(requirements[namespace] - supported[namespace]):
            diagnostics.append(
                error_detail(
                    "PYNE_UNSUPPORTED_FEATURE",
                    f"Runtime mode {mode!r} does not support {namespace}.{member}()",
                    hint="Use pn.runtime_capabilities() to select a supported API or mode.",
                )
            )
    return diagnostics


def _unique_diagnostics(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in values:
        key = (item.get("code"), item.get("message"), item.get("line"), item.get("column"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _library_requirements(
    libraries: dict[str, set[str]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    descriptors = {item.identifier: item for item in SUPPORTED_PINE_LIBRARIES}
    result: list[dict[str, Any]] = []
    for identifier, members in sorted(libraries.items()):
        descriptor = descriptors.get(identifier)
        supported_members = (
            set(descriptor.members) if descriptor is not None and mode == "batch" else set()
        )
        selected_supported = members & supported_members
        result.append(
            {
                "identifier": identifier,
                "members": sorted(members),
                "supportedMembers": sorted(selected_supported),
                "unsupportedMembers": sorted(members - supported_members),
                "dataRequirements": (
                    list(descriptor.requirements_for(selected_supported))
                    if descriptor is not None
                    else []
                ),
            }
        )
    return result


def _declaration(tree: ast.Module) -> dict[str, Any] | None:
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id not in {"indicator", "strategy", "study"}:
            continue
        title = None
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            title = call.args[0].value
        return {"kind": call.func.id, "title": title}
    return None


def _resource_hints(tree: ast.AST) -> dict[str, Any]:
    paths = {_attribute_path(node) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    callbacks = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    history_bars, history_dynamic, helper_count = _history_hints(tree)
    return {
        "usesState": bool({"state", "var"} & names or any(path.endswith(".state") for path in paths)),
        "usesVarip": "varip" in names or any(path.endswith(".varip") for path in paths),
        "usesPreview": "on_preview" in callbacks,
        "usesTrace": "trace" in names or any(path.startswith("ctx.trace") for path in paths),
        "usesStrategy": "strategy" in names or any("strategy" in path.split(".") for path in paths),
        "emitsSignals": "emit_signal" in names,
        "usesMarketMetadata": bool({"syminfo", "timeframe", "session"} & names),
        "minimumHistoryBars": history_bars,
        "historyIsDynamic": history_dynamic,
        "statefulTaInstances": helper_count,
    }


def _history_hints(tree: ast.AST) -> tuple[int, bool, int]:
    maximum = 0
    dynamic = False
    helper_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node)
        if resolved is None or resolved[0] != "ta":
            continue
        member = resolved[1]
        helper_count += int(_is_incremental_ta_call(node))
        if member in _FIXED_LOOKBACKS:
            maximum = max(maximum, _FIXED_LOOKBACKS[member])
            continue
        if member in {"pivothigh", "pivotlow"}:
            left, left_dynamic = _numeric_parameter(node, ("left",), 1)
            right, right_dynamic = _numeric_parameter(
                node,
                ("right",),
                2,
                default=left,
            )
            if left_dynamic or right_dynamic or left is None or right is None:
                dynamic = True
            else:
                maximum = max(maximum, int(left) + int(right) + 1)
            continue
        if member not in _PERIOD_MEMBERS:
            continue
        lookback, is_dynamic = _ta_lookback(node, member, _is_incremental_ta_call(node))
        dynamic = dynamic or is_dynamic
        if lookback is not None:
            maximum = max(maximum, max(int(lookback), 0))
    return maximum, dynamic, helper_count


def _ta_lookback(node: ast.Call, member: str, incremental: bool) -> tuple[float | None, bool]:
    if member == "macd":
        fast, fast_dynamic = _numeric_parameter(node, ("fast",), 1, default=12)
        slow, slow_dynamic = _numeric_parameter(node, ("slow",), 2, default=26)
        signal, signal_dynamic = _numeric_parameter(node, ("signal",), 3, default=9)
        if fast_dynamic or slow_dynamic or signal_dynamic:
            return None, True
        assert fast is not None and slow is not None and signal is not None
        return max(fast, slow) + signal - 1, False

    if member == "supertrend":
        position = 2 if incremental else 1
        return _numeric_parameter(
            node,
            ("atr_period", "period"),
            position,
            default=10,
        )

    if member == "stoch":
        position = 1 if incremental else 3
        return _numeric_parameter(node, ("period", "k_period", "length"), position, default=14)

    if member == "adx":
        if incremental:
            period, period_dynamic = _numeric_parameter(node, ("period",), 1)
            smoothing, smoothing_dynamic = _numeric_parameter(
                node,
                ("adx_period", "adx_smoothing"),
                2,
                default=period,
            )
            if period_dynamic or smoothing_dynamic or period is None or smoothing is None:
                return None, True
            return period + smoothing - 1, False
        return _numeric_parameter(node, ("period",), 3, default=14)

    if member == "dmi":
        period_position = 1 if incremental else 0
        smoothing_position = 2 if incremental else 1
        period, period_dynamic = _numeric_parameter(
            node,
            ("period", "di_period", "di_length"),
            period_position,
            default=None if incremental else 14,
        )
        smoothing, smoothing_dynamic = _numeric_parameter(
            node,
            ("adx_period", "adx_smoothing"),
            smoothing_position,
            default=14,
        )
        if period_dynamic or smoothing_dynamic or period is None or smoothing is None:
            return None, True
        return period + smoothing - 1, False

    if member == "tsi":
        short, short_dynamic = _numeric_parameter(node, ("short",), 1, default=13)
        long, long_dynamic = _numeric_parameter(node, ("long",), 2, default=25)
        if short_dynamic or long_dynamic or short is None or long is None:
            return None, True
        return long + short - 1, False

    batch_period_zero = {"atr", "donchian", "keltner", "wpr"}
    position = 1 if incremental or member not in batch_period_zero else 0
    default = _DEFAULT_LOOKBACKS.get(member, _MISSING)
    return _numeric_parameter(node, ("period", "length"), position, default=default)


def _is_incremental_ta_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    owner = node.func.value
    return (
        isinstance(owner, ast.Attribute)
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "ctx"
        and owner.attr == "ta"
    )


def _numeric_argument(node: ast.Call, keyword_name: str, position: int) -> float | None:
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return _constant_number(keyword.value)
    if position >= 0 and len(node.args) > position:
        return _constant_number(node.args[position])
    return None


_MISSING = object()


def _numeric_parameter(
    node: ast.Call,
    keyword_names: tuple[str, ...],
    position: int,
    *,
    default: object = _MISSING,
) -> tuple[float | None, bool]:
    for keyword in node.keywords:
        if keyword.arg in keyword_names:
            value = _constant_number(keyword.value)
            return value, value is None
    if position >= 0 and len(node.args) > position:
        value = _constant_number(node.args[position])
        return value, value is None
    if default is _MISSING:
        return None, True
    if default is None:
        return None, False
    assert isinstance(default, int | float)
    return float(default), False


def _constant_number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return float(node.value)
    return None
