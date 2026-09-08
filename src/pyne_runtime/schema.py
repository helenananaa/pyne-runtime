"""Pyne input and output schema helpers."""
from __future__ import annotations

from typing import Any

from .capabilities import runtime_capabilities

from ._request_contract import (
    REQUEST_METADATA_KEY_ALIASES,
    REQUEST_API_VALUES,
    REQUEST_SECURITY_API,
    REQUEST_SECURITY_CAPABILITY_ALIASES,
    REQUEST_SECURITY_LOWER_TF_API,
    REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
)


PYNE_INPUT_SCHEMA_VERSION = 1
PYNE_OUTPUT_SCHEMA_VERSION = 2
PYNE_PARAM_SCHEMA_VERSION = 1
PYNE_REQUEST_PROVIDER_SCHEMA_VERSION = 10
PYNE_STRATEGY_REPORT_SCHEMA_VERSION = 1

OHLCV_FIELDS = ("time", "open", "high", "low", "close", "volume")
REQUEST_PROVIDER_SUPPORTED_APIS: tuple[dict[str, Any], ...] = (
    {
        "api": REQUEST_SECURITY_API,
        "providerMethod": "get_ohlcv",
        "capabilityAliases": list(REQUEST_SECURITY_CAPABILITY_ALIASES),
        "result": "chart-aligned series or tuple of chart-aligned series",
        "supportsIgnoreInvalidSymbol": True,
    },
    {
        "api": REQUEST_SECURITY_LOWER_TF_API,
        "providerMethod": "get_ohlcv",
        "capabilityAliases": list(REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES),
        "result": "lower-timeframe grouped arrays or tuple of grouped arrays",
        "supportsIgnoreInvalidSymbol": True,
        "supportsIgnoreInvalidTimeframe": True,
    },
)
OUTPUT_KEYS = (
    "lines",
    "candles",
    "histograms",
    "markers",
    "hlines",
    "fills",
    "bgcolors",
    "labels",
    "barcolors",
    "signals",
    "strategy",
    "objects",
    "object_events",
)

RENDERABLE_CONTRACT: dict[str, dict[str, list[str] | str]] = {
    "lines": {
        "collection": "lines",
        "required": ["id", "title", "color", "linewidth", "style", "pane", "data"],
        "optional": ["display", "format", "precision", "per_bar_color"],
        "pointRequired": ["time", "value"],
        "pointOptional": ["color"],
    },
    "candles": {
        "collection": "candles",
        "required": ["title", "pane", "data"],
        "optional": ["display", "format", "precision"],
        "pointRequired": ["time", "open", "high", "low", "close"],
        "pointOptional": ["color", "wickcolor", "bordercolor"],
    },
    "histograms": {
        "collection": "histograms",
        "required": ["title", "color_up", "color_down", "pane", "data"],
        "optional": ["display", "format", "precision"],
        "pointRequired": ["time", "value"],
        "pointOptional": ["color"],
    },
    "markers": {
        "collection": "markers",
        "required": ["shape", "text", "position", "size", "pane", "data"],
        "optional": [
            "title",
            "color",
            "color_up",
            "color_down",
            "char",
            "textcolor",
            "offset",
            "minheight",
            "maxheight",
            "display",
            "per_bar_color",
        ],
        "pointRequired": ["time", "shape", "color", "text", "position", "size", "pane"],
        "pointOptional": [
            "char",
            "textcolor",
            "direction",
            "value",
            "height",
        ],
    },
    "hlines": {
        "collection": "hlines",
        "required": ["price", "title", "color", "linestyle", "linewidth", "pane"],
        "optional": [],
    },
    "fills": {
        "collection": "fills",
        "required": ["plot1_id", "plot2_id", "color", "title", "pane"],
        "optional": [],
    },
    "bgcolors": {
        "collection": "bgcolors",
        "required": ["color", "pane", "title", "regions"],
        "optional": [],
        "regionRequired": ["time"],
    },
    "labels": {
        "collection": "labels",
        "required": ["text", "position", "color", "textcolor", "pane", "style"],
        "optional": [],
        "status": "legacy simple text labels; prefer objects.labels for drawing labels",
    },
    "barcolors": {
        "collection": "barcolors",
        "required": ["data"],
        "optional": [],
        "pointRequired": ["time", "color"],
    },
    "signals": {
        "collection": "signals",
        "required": ["name", "side", "message", "pane", "data"],
        "optional": [],
        "pointRequired": ["time", "side", "name", "message"],
        "pointOptional": ["strength", "price", "payload"],
    },
}

DRAWING_OBJECT_CONTRACT: dict[str, Any] = {
    "groups": ["lines", "labels", "boxes", "tables", "linefills", "polylines"],
    "commonRequired": ["id", "pane"],
    "lines": {
        "required": [
            "id",
            "x1",
            "y1",
            "x2",
            "y2",
            "color",
            "width",
            "style",
            "extend",
            "xloc",
            "pane",
        ],
    },
    "labels": {
        "required": [
            "id",
            "x",
            "y",
            "text",
            "color",
            "textcolor",
            "style",
            "size",
            "xloc",
            "pane",
        ],
        "optional": ["yloc"],
    },
    "boxes": {
        "required": [
            "id",
            "left",
            "top",
            "right",
            "bottom",
            "bgcolor",
            "border_color",
            "border_width",
            "border_style",
            "xloc",
            "pane",
        ],
    },
    "tables": {
        "required": [
            "id",
            "position",
            "columns",
            "rows",
            "bgcolor",
            "frame_color",
            "frame_width",
            "border_color",
            "border_width",
            "pane",
            "cells",
            "merges",
        ],
        "cellRequired": [
            "column",
            "row",
            "text",
            "text_color",
            "bgcolor",
            "width",
            "height",
            "text_halign",
            "text_valign",
        ],
        "mergeRequired": [
            "start_column",
            "start_row",
            "end_column",
            "end_row",
        ],
    },
    "linefills": {
        "required": ["id", "line1_id", "line2_id", "color", "pane"],
    },
    "polylines": {
        "required": [
            "id",
            "points",
            "curved",
            "closed",
            "xloc",
            "line_color",
            "fill_color",
            "line_style",
            "line_width",
            "pane",
        ],
        "pointRequired": ["x", "y"],
    },
}

OBJECT_EVENT_CONTRACT: dict[str, Any] = {
    "outputKey": "object_events",
    "actions": ["create", "update", "delete"],
    "kinds": ["line", "label", "box", "table"],
    "required": ["action", "kind", "id", "object"],
    "optional": ["time", "bar_index", "confirmed", "realtime"],
    "semantics": "Incremental drawing object changes for the requested output window",
}

OUTPUT_SCHEMA_MIGRATION_POLICY: dict[str, Any] = {
    "schema": "output",
    "currentVersion": PYNE_OUTPUT_SCHEMA_VERSION,
    "breakingChangeRequires": [
        "schemaVersion bump",
        "migration note",
        "contract test",
        "host consumption fixture update when renderer output changes",
    ],
    "versions": [
        {
            "version": 1,
            "status": "supported",
            "breakingChanges": [],
            "notes": [
                "Initial versioned output contract.",
                "Structured renderer collections live under result.output.",
                "Top-level result.lines remains a backward-compatible flat plot view.",
                "Top-level output.labels is a legacy simple text label collection; "
                "prefer output.objects.labels for Pine-like drawing labels.",
            ],
        },
        {
            "version": 2,
            "status": "current",
            "breakingChanges": [
                "Hosts validating exact collection names must accept output.candles.",
                "Drawing hosts must accept linefills, polylines, and table merges.",
            ],
            "notes": [
                "Adds plotcandle output and the remaining high-value drawing groups.",
                "Version 1 remains a valid legacy host fallback for scripts using its surface.",
            ],
        },
    ],
}

SCRIPT_NAMESPACE_CONTRACT: dict[str, Any] = {
    "purpose": "Top-level names injected into Pyne scripts for editor autocomplete",
    "categories": {
        "data": [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "time",
            "dayofweek",
            "time_close",
            "bar_index",
            "last_bar_index",
            "barstate",
            "bar_count",
            "syminfo",
            "timeframe",
            "session",
            "hl2",
            "hlc3",
            "ohlc4",
            "hlcc4",
        ],
        "modules": [
            "ta",
            "input",
            "request",
            "pine_library",
            "runtime",
            "barmerge",
            "strategy",
            "trace",
            "array",
            "map",
            "matrix",
            "order",
            "str",
            "ticker",
            "color",
            "math",
            "chart",
            "pyne",
            "cache",
            "cache_clear",
            "cache_stats",
        ],
        "plot": [
            "indicator",
            "study",
            "plot",
            "plotcandle",
            "bar",
            "hline",
            "fill",
            "bgcolor",
            "marker",
            "plotshape",
            "plotchar",
            "plotarrow",
            "barcolor",
            "emit_signal",
            "alertcondition",
            "line",
            "linefill",
            "polyline",
            "label",
            "box",
            "table",
            "add_line",
            "shape",
            "location",
            "position",
            "size",
            "display",
            "format",
            "scale",
            "xloc",
            "yloc",
            "extend",
            "text",
        ],
        "utility": [
            "crossover",
            "cross",
            "crossunder",
            "when",
            "iff",
            "where",
            "switch",
            "ref",
            "highest",
            "highestbars",
            "lowest",
            "lowestbars",
            "change",
            "roc",
            "barssince",
            "valuewhen",
            "shift",
            "na",
            "nz",
            "fixnan",
            "na_check",
            "cum",
            "rising",
            "falling",
            "true",
            "false",
            "var",
            "state",
            "sma",
            "ema",
            "wma",
            "rma",
            "vwma",
            "vwap",
            "rsi",
            "macd",
            "atr",
            "bb",
            "cci",
            "linreg",
            "mfi",
            "mom",
            "pivothigh",
            "pivotlow",
            "security",
            "stdev",
            "stoch",
            "tostring",
            "heikinashi",
            "timestamp",
            "year",
            "month",
            "dayofmonth",
            "hour",
            "minute",
            "second",
            "abs",
            "avg",
            "ceil",
            "cos",
            "exp",
            "floor",
            "log",
            "log10",
            "max",
            "min",
            "pow",
            "round",
            "sign",
            "sin",
            "sqrt",
            "sum",
            "tan",
        ],
        "compat": ["np", "numpy", "params"],
        "builtins": "Policy-controlled Python builtins depend on PyneSettings.security_mode",
    },
}

REQUEST_PROVIDER_ERROR_CATEGORIES: dict[str, dict[str, Any]] = {
    "missingProvider": {
        "code": "PYNE_UNSUPPORTED_FEATURE",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "No host data provider is configured for a request.* call.",
        "beforeGetOhlcv": True,
        "ignoreInvalidSymbol": "not applicable",
        "classification": "RequestProviderErrorCategory.MISSING_PROVIDER",
    },
    "unsupportedCapability": {
        "code": "PYNE_UNSUPPORTED_FEATURE",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "Provider capabilities explicitly omit or disable the requested API.",
        "beforeGetOhlcv": True,
        "ignoreInvalidSymbol": "not applicable",
        "classification": "RequestProviderErrorCategory.UNSUPPORTED_CAPABILITY",
    },
    "capabilityFailure": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "capabilities() or capabilities attribute evaluation raises unexpectedly.",
        "beforeGetOhlcv": True,
        "ignoreInvalidSymbol": "not applicable",
        "classification": "RequestProviderErrorCategory.CAPABILITY_FAILURE",
    },
    "invalidSymbol": {
        "code": "PYNE_INVALID_SYMBOL",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "Provider raises PyneInvalidSymbolError for the requested symbol.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": (
            "request.security returns na values; request.security_lower_tf returns empty groups"
        ),
        "classification": "RequestProviderErrorCategory.INVALID_SYMBOL",
        "providerSignal": "PyneInvalidSymbolError",
    },
    "providerFailure": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "get_ohlcv raises an unexpected exception.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "not ignored",
        "classification": "RequestProviderErrorCategory.PROVIDER_FAILURE",
        "providerSignal": "PyneProviderDataError",
    },
    "invalidReturnType": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "get_ohlcv returns None or a non-list value.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "does not apply; invalid provider return types remain errors",
        "classification": "RequestProviderErrorCategory.INVALID_RETURN_TYPE",
    },
    "invalidBarShape": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "A returned OHLCV bar is not a mapping or lacks required fields.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "not ignored",
        "classification": "RequestProviderErrorCategory.INVALID_BAR_SHAPE",
    },
    "invalidMetadata": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "Requested-context metadata is not a mapping.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "metadata is skipped for ignored invalid symbols",
        "classification": "RequestProviderErrorCategory.INVALID_METADATA",
    },
    "metadataFailure": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "get_request_metadata() or request_metadata(...) raises unexpectedly.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "metadata is skipped for ignored invalid symbols",
        "classification": "RequestProviderErrorCategory.METADATA_FAILURE",
        "providerSignal": "PyneProviderMetadataError",
    },
    "expressionFailure": {
        "code": "PYNE_RUNTIME_ERROR",
        "appliesTo": list(REQUEST_API_VALUES),
        "condition": "A callable request expression raises unexpectedly.",
        "beforeGetOhlcv": False,
        "ignoreInvalidSymbol": "not applicable after expression evaluation starts",
        "classification": "RequestProviderErrorCategory.EXPRESSION_FAILURE",
    },
}

REQUEST_PROVIDER_SCHEMA_MIGRATION_POLICY: dict[str, Any] = {
    "schema": "requestProvider",
    "currentVersion": PYNE_REQUEST_PROVIDER_SCHEMA_VERSION,
    "breakingChangeRequires": [
        "schemaVersion bump",
        "migration note",
        "contract test",
        "request API documentation update",
    ],
    "versions": [
        {
            "version": 10,
            "status": "current",
            "breakingChanges": [
                "Removes messageContains from error categories; consumers must use "
                "the typed category value and serialized requestProviderCategory.",
            ],
            "notes": [
                "Exports RequestProviderErrorCategory and typed provider-side errors.",
                "Publishes a test-runner-independent provider conformance kit.",
            ],
        },
        {
            "version": 9,
            "status": "previous",
            "breakingChanges": [
                "Provider start/end coordinates now describe a warmup-expanded "
                "fetch window ending at the last chart close boundary instead of "
                "the raw first/last chart opening-time range.",
            ],
            "notes": [
                "Keeps the inclusive get_ohlcv(symbol, timeframe, start, end) "
                "signature and requested-context cache key.",
                "Adds bounded adaptive warmup widening and complete final "
                "lower-timeframe chart-bucket retrieval.",
            ],
        },
        {
            "version": 8,
            "status": "previous",
            "breakingChanges": [],
            "notes": [
                "Adds request.security_lower_tf ignore_invalid_timeframe support "
                "metadata and ignoredInvalidTimeframe diagnostics.",
                "Keeps supportedApis and errorDetail.requestProviderRequest from "
                "earlier request provider schema versions.",
            ],
        },
        {
            "version": 6,
            "status": "previous",
            "breakingChanges": [],
            "notes": [
                "Adds errorDetail.requestProviderRequest for failed request.* calls.",
                "Keeps meta.requestDiagnostics from version 5.",
            ],
        },
        {
            "version": 5,
            "status": "previous",
            "breakingChanges": [],
            "notes": [
                "Adds meta.requestDiagnostics entries for successful request.* calls.",
                "Keeps requestProvider errorCategories from version 4.",
            ],
        },
        {
            "version": 4,
            "status": "previous",
            "breakingChanges": [],
            "notes": [
                "Adds structured errorCategories for host-facing request diagnostics.",
                "Keeps the legacy errors mapping for existing host checks.",
            ],
        },
        {
            "version": 3,
            "status": "previous",
            "breakingChanges": [],
            "notes": [
                "Defines provider capabilities, metadata, cache semantics, and "
                "legacy error code mapping.",
            ],
        },
    ],
}


def input_schema() -> dict[str, Any]:
    """Return the stable Pyne OHLCV input contract."""
    return {
        "schemaVersion": PYNE_INPUT_SCHEMA_VERSION,
        "type": "ohlcv",
        "required": list(OHLCV_FIELDS),
        "timeUnit": "seconds",
        "bar": {
            "time": "Unix timestamp in seconds",
            "open": "Open price as float",
            "high": "High price as float",
            "low": "Low price as float",
            "close": "Close price as float",
            "volume": "Volume as float",
        },
    }


def output_schema() -> dict[str, Any]:
    """Return the stable Pyne result/output contract."""
    return {
        "schemaVersion": PYNE_OUTPUT_SCHEMA_VERSION,
        "result": {
            "ok": "Whether execution succeeded",
            "error": "Error message when execution failed",
            "code": "Stable error code when execution failed",
            "errorDetail": (
                "Structured error detail when execution failed; request provider "
                "failures may include requestProviderCategory"
            ),
            "lines": "Backward-compatible flat plotted series",
            "output": "Structured output collections",
            "param_schema": "Input parameter declarations collected from scripts",
            "paramSchemaVersion": "Parameter schema version for param_schema entries",
            "meta": "Indicator metadata collected from indicator()",
        },
        "outputKeys": list(OUTPUT_KEYS),
        "point": {
            "time": "Unix timestamp in seconds",
            "value": "Numeric point value",
        },
        "paneValues": ["main", "separate"],
        "renderables": RENDERABLE_CONTRACT,
        "objects": DRAWING_OBJECT_CONTRACT,
        "objectEvents": OBJECT_EVENT_CONTRACT,
        "migration": OUTPUT_SCHEMA_MIGRATION_POLICY,
    }


def param_schema() -> dict[str, Any]:
    """Return the stable Pyne script parameter schema contract."""
    return {
        "schemaVersion": PYNE_PARAM_SCHEMA_VERSION,
        "entry": {
            "id": "Stable parameter id; currently matches key",
            "key": "Override key; by default this is the input title",
            "type": "Parameter type",
            "default": "Declared default value",
            "current": "Value used for the current run",
            "title": "Display title",
            "tooltip": "Optional UI tooltip",
            "group": "Optional UI group",
            "inline": "Optional same-line UI grouping hint",
            "confirm": "Whether a host should require explicit confirmation",
            "display": "Optional Pine-like host display hint",
            "active": "Whether a host should allow editing the input",
            "options": "Optional enumerated choices",
            "minval": "Optional numeric lower bound",
            "maxval": "Optional numeric upper bound",
            "step": "Optional numeric increment",
        },
        "types": [
            "int",
            "float",
            "bool",
            "string",
            "color",
            "source",
            "timeframe",
            "symbol",
            "session",
            "time",
            "text_area",
            "price",
            "enum",
        ],
    }


def request_provider_schema() -> dict[str, Any]:
    """Return the stable host data-provider contract for request.* calls."""
    return {
        "schemaVersion": PYNE_REQUEST_PROVIDER_SCHEMA_VERSION,
        "method": "get_ohlcv(symbol, timeframe, start, end) -> list[OHLCV bar]",
        "supportedApis": [dict(item) for item in REQUEST_PROVIDER_SUPPORTED_APIS],
        "requiredBarFields": list(OHLCV_FIELDS),
        "range": {
            "start": (
                "Warmup-expanded current request start time as Unix seconds, "
                "clamped to 0"
            ),
            "end": "Last chart bar close boundary as Unix seconds",
            "semantics": "Provider should return bars relevant to inclusive [start, end]",
            "warmup": (
                "initially max(chart bar count, direct field history offset) "
                "requested-timeframe bars; unknown requested timeframes fall back "
                "to observed chart spacing"
            ),
            "adaptiveWidening": {
                "condition": (
                    "a non-empty provider result contains fewer actual bars before "
                    "chart_start than the warmup requirement"
                ),
                "factor": 4,
                "maxWidenings": 6,
                "stopConditions": [
                    "warmup requirement satisfied",
                    "valid empty provider result",
                    "start reaches 0",
                    "maximum widening count reached",
                ],
                "guarantee": (
                    "bounded best effort only; gaps longer than the widening budget "
                    "can still leave requested history unavailable"
                ),
            },
            "lowerTimeframeBoundary": (
                "request.security_lower_tf groups the final chart bar as [last open, end), "
                "using explicit final time_close or the last positive chart interval; "
                "a provider bar opening exactly at end is not included in that group"
            ),
        },
        "capabilities": {
            "declaredBy": "optional capabilities attribute or capabilities() method",
            "securityAliases": list(REQUEST_SECURITY_CAPABILITY_ALIASES),
            "lowerTimeframeAliases": list(REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES),
            "missingDeclaration": "supported",
            "dictSemantics": "at least one matching alias must be present and truthy",
            "sequenceSemantics": "at least one matching alias must be present",
        },
        "metadata": {
            "declaredBy": (
                "optional get_request_metadata(symbol, timeframe), "
                "request_metadata(symbol, timeframe), or request_metadata mapping"
            ),
            "acceptedKeys": {
                key: list(value) for key, value in REQUEST_METADATA_KEY_ALIASES.items()
            },
            "defaults": (
                "requested symbol is used for syminfo ticker/tickerid; requested "
                "timeframe is used for timeframe.period; session defaults are inferred"
            ),
        },
        "cache": {
            "scope": "one script run",
            "key": ["symbol", "timeframe", "start", "end"],
            "reusedFor": [
                *REQUEST_API_VALUES,
                "requested metadata",
            ],
            "separateRuns": "provider data is not cached across pn.run() executions",
            "exhaustedWarmup": (
                "an exhausted adaptive window is reused for the same or a smaller "
                "warmup requirement; only a larger requirement resumes widening"
            ),
            "emptyResults": (
                "valid empty provider results are cached and reported as status=ok with bars=0"
            ),
            "ignoredInvalidSymbol": (
                "PyneInvalidSymbolError ignored by ignore_invalid_symbol=True is not cached "
                "and reports status=ignoredInvalidSymbol"
            ),
            "ignoredInvalidTimeframe": (
                "request.security_lower_tf ignored by ignore_invalid_timeframe=True is not "
                "cached and reports status=ignoredInvalidTimeframe"
            ),
        },
        "diagnostics": {
            "resultLocation": "meta.requestDiagnostics",
            "incrementalRetention": {
                "scope": "current_bar",
                "infoLocation": "meta.requestDiagnosticsInfo",
                "infoFields": ["scope", "barTime", "retained", "dropped", "truncated"],
                "semantics": (
                    "All calls in the current bar remain visible; prior-bar entries are "
                    "discarded at the next bar. dropped counts prior entries, including "
                    "successful calls; preview counts do not modify committed counts. "
                    "No-request bars expose an empty list when history was discarded. "
                    "This bounds history growth, not calls within a single bar."
                ),
            },
            "entryRequired": [
                "api",
                "symbol",
                "timeframe",
                "start",
                "end",
                "bars",
                "cacheHit",
                "ignoreInvalidSymbol",
                "status",
            ],
            "apiValues": list(REQUEST_API_VALUES),
            "statusValues": ["ok", "ignoredInvalidSymbol", "ignoredInvalidTimeframe"],
            "semantics": (
                "One entry is appended for each successful request.* call; repeated "
                "symbol/timeframe/range contexts set cacheHit=true, and start/end "
                "report the final actual provider range after adaptive widening."
            ),
        },
        "errorDetail": {
            "categoryField": "requestProviderCategory",
            "requestField": "requestProviderRequest",
            "requestRequired": ["api", "symbol", "timeframe", "start", "end"],
            "semantics": (
                "Failed host-backed request.* calls include requestProviderCategory "
                "and requestProviderRequest in result.errorDetail; provider failures "
                "during adaptive widening report the final attempted range."
            ),
        },
        "typedErrors": {
            "categoryEnum": "RequestProviderErrorCategory",
            "runtimeError": "PyneRequestError",
            "providerBaseError": "PyneProviderError",
            "providerSignals": {
                "invalidSymbol": "PyneInvalidSymbolError",
                "capabilityFailure": "PyneProviderCapabilityError",
                "providerFailure": "PyneProviderDataError",
                "metadataFailure": "PyneProviderMetadataError",
            },
            "classification": (
                "Branch on exception category or errorDetail.requestProviderCategory; "
                "human-readable messages are not a compatibility contract."
            ),
        },
        "errors": {
            "invalidSymbol": "raise PyneInvalidSymbolError to support ignore_invalid_symbol",
            "unsupportedCapability": "PYNE_UNSUPPORTED_FEATURE before get_ohlcv is called",
            "capabilityFailure": "PYNE_RUNTIME_ERROR",
            "invalidOhlcv": "PYNE_RUNTIME_ERROR",
            "providerFailure": "PYNE_RUNTIME_ERROR",
        },
        "errorCategories": REQUEST_PROVIDER_ERROR_CATEGORIES,
        "migration": REQUEST_PROVIDER_SCHEMA_MIGRATION_POLICY,
    }


def strategy_report_schema() -> dict[str, Any]:
    """Return the stable strategy report contract."""
    return {
        "schemaVersion": PYNE_STRATEGY_REPORT_SCHEMA_VERSION,
        "outputKey": "strategy",
        "sections": [
            "orders",
            "position",
            "summary",
            "risk",
            "closedtrades",
            "opentrades",
            "lifecycle",
        ],
        "orders": {
            "required": ["time", "id", "type", "side", "qty", "price", "position_after"],
            "optional": [
                "from_entry",
                "reason",
                "comment",
                "limit",
                "stop",
                "commission",
                "oca_name",
                "oca_type",
                "canceled",
            ],
        },
        "position": {
            "required": ["size", "side", "avg_price"],
            "sideValues": ["long", "short", "flat"],
        },
        "summary": {
            "required": [
                "initial_capital",
                "currency",
                "equity",
                "netprofit",
                "openprofit",
                "grossprofit",
                "grossloss",
                "commission",
                "backtest_fill_limits_assumption",
                "same_bar_fill_priority",
                "intrabar_path",
                "margin_long",
                "margin_short",
            ],
        },
        "risk": {
            "required": [
                "locked",
                "max_drawdown",
                "max_drawdown_type",
                "max_intraday_loss",
                "max_intraday_loss_type",
                "max_position_size",
                "max_intraday_filled_orders",
            ],
        },
        "trades": {
            "closedRequired": [
                "entry_time",
                "exit_time",
                "entry_id",
                "exit_id",
                "side",
                "qty",
                "entry_price",
                "exit_price",
                "profit",
                "commission",
                "net_profit",
            ],
            "openRequired": [
                "entry_time",
                "entry_id",
                "side",
                "qty",
                "entry_price",
                "profit",
            ],
            "openOptional": ["commission", "entry_comment"],
            "closedOptional": ["entry_comment", "exit_comment"],
            "privateFields": "Internal fields beginning with '_' are not part of the public report",
        },
        "lifecycle": {
            "required": [
                "id",
                "type",
                "status",
                "phase",
                "submitted_time",
                "filled_time",
                "canceled_time",
                "rejected_time",
            ],
            "optional": [
                "side",
                "qty",
                "price",
                "position_after",
                "reason",
                "comment",
                "commission",
                "from_entry",
                "target_qty",
                "requested_qty",
                "filled_qty",
                "qty_percent",
                "oca_name",
                "oca_type",
                "canceled",
                "rejected_reason",
            ],
            "statusValues": ["pending", "filled", "canceled", "rejected", "submitted"],
        },
    }


def script_namespace_schema() -> dict[str, Any]:
    """Return the script top-level namespace contract."""
    categories = SCRIPT_NAMESPACE_CONTRACT["categories"]
    names: list[str] = []
    for entries in categories.values():
        if isinstance(entries, list):
            names.extend(entries)
    return {
        **SCRIPT_NAMESPACE_CONTRACT,
        "names": sorted(names),
    }


def schema() -> dict[str, Any]:
    """Return the public Pyne input/output schema bundle."""
    return {
        "input": input_schema(),
        "output": output_schema(),
        "params": param_schema(),
        "requestProvider": request_provider_schema(),
        "strategyReport": strategy_report_schema(),
        "scriptNamespace": script_namespace_schema(),
        "runtimeCapabilities": runtime_capabilities(),
    }

