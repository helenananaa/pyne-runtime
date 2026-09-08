"""Versioned, bounded, deterministic incremental replay checkpoints."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ..settings import PyneSettings


PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_VERSION = 1
PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_FORMAT = "pyne.incremental-session/1"
PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_VERSION = 2
PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_FORMAT = "pyne.incremental-state/2"
DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_PORTABLE_SNAPSHOT_MAX_DEPTH = 16
DEFAULT_PORTABLE_SNAPSHOT_MAX_NODES = 1_000_000

# Independent of package and wire-format versions. Bump when committed state or
# replay semantics change incompatibly; legacy unmarked checkpoints are unknown.
INCREMENTAL_SEMANTICS_VERSION = 2


class PynePortableSnapshotError(ValueError):
    """Portable checkpoint is unsupported, corrupt, mismatched, or over limit."""

    code: str | None = None


def validate_snapshot_semantics(version: Any) -> None:
    if type(version) is not int or version != INCREMENTAL_SEMANTICS_VERSION:
        error = PynePortableSnapshotError(
            "PYNE_SNAPSHOT_SEMANTICS_MISMATCH: snapshot semantics "
            f"{version!r} do not match runtime semantics {INCREMENTAL_SEMANTICS_VERSION}; "
            "rebuild the session from authoritative OHLCV under the current runtime. "
            "Do not relabel or reuse old state."
        )
        error.code = "PYNE_SNAPSHOT_SEMANTICS_MISMATCH"
        raise error


@dataclass(frozen=True)
class PortableCheckpoint:
    script_sha256: str
    params: dict[str, Any]
    settings: dict[str, Any]
    retention_bars: int
    bars: tuple[dict[str, Any], ...]
    seed_count: int
    provider_required: bool


@dataclass(frozen=True)
class PortableStateCheckpoint:
    script_sha256: str
    settings: dict[str, Any]
    provider_required: bool
    snapshot: Any


def encode_portable_checkpoint(
    checkpoint: PortableCheckpoint,
    *,
    max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    max_depth: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_DEPTH,
    max_nodes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_NODES,
) -> bytes:
    budget = _NodeBudget(max_nodes)
    payload = {
        "schemaVersion": PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_VERSION,
        "semanticsVersion": INCREMENTAL_SEMANTICS_VERSION,
        "scriptSha256": checkpoint.script_sha256,
        "params": _encode_value(checkpoint.params, depth=0, max_depth=max_depth, budget=budget),
        "settings": _encode_value(
            checkpoint.settings,
            depth=0,
            max_depth=max_depth,
            budget=budget,
        ),
        "retentionBars": int(checkpoint.retention_bars),
        "bars": _encode_value(
            list(checkpoint.bars),
            depth=0,
            max_depth=max_depth,
            budget=budget,
        ),
        "seedCount": int(checkpoint.seed_count),
        "providerRequired": bool(checkpoint.provider_required),
    }
    payload_bytes = _canonical_json(payload)
    envelope = {
        "format": PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_FORMAT,
        "checksum": f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}",
        "payload": payload,
    }
    encoded = _canonical_json(envelope)
    if len(encoded) > max(int(max_bytes), 1):
        raise PynePortableSnapshotError(
            f"Portable incremental snapshot exceeds {max(int(max_bytes), 1)} bytes"
        )
    return encoded


def decode_portable_checkpoint(
    value: bytes | bytearray | memoryview | str,
    *,
    max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    max_depth: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_DEPTH,
    max_nodes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_NODES,
) -> PortableCheckpoint:
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    limit = max(int(max_bytes), 1)
    if len(raw) > limit:
        raise PynePortableSnapshotError(
            f"Portable incremental snapshot exceeds {limit} bytes"
        )
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PynePortableSnapshotError("Portable incremental snapshot is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"format", "checksum", "payload"}:
        raise PynePortableSnapshotError("Portable incremental snapshot envelope is invalid")
    if envelope["format"] != PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_FORMAT:
        raise PynePortableSnapshotError(
            f"Unsupported portable incremental snapshot format {envelope['format']!r}"
        )
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise PynePortableSnapshotError("Portable incremental snapshot payload is invalid")
    expected = f"sha256:{hashlib.sha256(_canonical_json(payload)).hexdigest()}"
    if envelope["checksum"] != expected:
        raise PynePortableSnapshotError("Portable incremental snapshot checksum does not match")
    validate_snapshot_semantics(payload.get("semanticsVersion"))
    expected_keys = {
        "semanticsVersion",
        "schemaVersion",
        "scriptSha256",
        "params",
        "settings",
        "retentionBars",
        "bars",
        "seedCount",
        "providerRequired",
    }
    if set(payload) != expected_keys:
        raise PynePortableSnapshotError("Portable incremental snapshot payload fields are invalid")
    if payload["schemaVersion"] != PYNE_INCREMENTAL_PORTABLE_SNAPSHOT_VERSION:
        raise PynePortableSnapshotError(
            "Unsupported portable incremental snapshot version "
            f"{payload['schemaVersion']!r}"
        )
    budget = _NodeBudget(max_nodes)
    params = _decode_value(payload["params"], depth=0, max_depth=max_depth, budget=budget)
    settings = _decode_value(payload["settings"], depth=0, max_depth=max_depth, budget=budget)
    bars = _decode_value(payload["bars"], depth=0, max_depth=max_depth, budget=budget)
    if not isinstance(params, dict) or not isinstance(settings, dict):
        raise PynePortableSnapshotError("Portable snapshot params/settings must be mappings")
    if not isinstance(bars, list) or not all(isinstance(item, dict) for item in bars):
        raise PynePortableSnapshotError("Portable snapshot bars must be a list of mappings")
    retention_bars = _positive_int(payload["retentionBars"], "retentionBars")
    seed_count = _nonnegative_int(payload["seedCount"], "seedCount")
    if seed_count > len(bars):
        raise PynePortableSnapshotError("Portable snapshot seedCount exceeds bar count")
    script_sha256 = str(payload["scriptSha256"])
    if len(script_sha256) != 64 or any(char not in "0123456789abcdef" for char in script_sha256):
        raise PynePortableSnapshotError("Portable snapshot scriptSha256 is invalid")
    if not isinstance(payload["providerRequired"], bool):
        raise PynePortableSnapshotError("Portable snapshot providerRequired must be boolean")
    return PortableCheckpoint(
        script_sha256=script_sha256,
        params=params,
        settings=settings,
        retention_bars=retention_bars,
        bars=tuple(bars),
        seed_count=seed_count,
        provider_required=payload["providerRequired"],
    )


def encode_portable_state_checkpoint(
    checkpoint: PortableStateCheckpoint,
    *,
    max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    max_depth: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_DEPTH,
    max_nodes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_NODES,
) -> bytes:
    """Encode a native typed-state checkpoint without replay history."""
    from .state_codec import encode_typed_state_graph

    budget = _NodeBudget(max_nodes)
    payload = {
        "schemaVersion": PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_VERSION,
        "semanticsVersion": INCREMENTAL_SEMANTICS_VERSION,
        "scriptSha256": checkpoint.script_sha256,
        "settings": _encode_value(
            checkpoint.settings,
            depth=0,
            max_depth=max_depth,
            budget=budget,
        ),
        "providerRequired": bool(checkpoint.provider_required),
        "stateGraph": encode_typed_state_graph(
            checkpoint.snapshot,
            max_nodes=max_nodes,
            max_depth=max_depth,
        ),
    }
    payload_bytes = _canonical_json(payload)
    envelope = {
        "format": PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_FORMAT,
        "checksum": f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}",
        "payload": payload,
    }
    encoded = _canonical_json(envelope)
    if len(encoded) > max(int(max_bytes), 1):
        raise PynePortableSnapshotError(
            f"Portable incremental snapshot exceeds {max(int(max_bytes), 1)} bytes"
        )
    return encoded


def decode_portable_state_checkpoint(
    value: bytes | bytearray | memoryview | str,
    *,
    max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
    max_depth: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_DEPTH,
    max_nodes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_NODES,
) -> PortableStateCheckpoint:
    """Decode a native typed-state checkpoint using an exact runtime type allowlist."""
    from .state_codec import decode_typed_state_graph

    envelope = _decode_envelope(value, max_bytes=max_bytes)
    if envelope["format"] != PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_FORMAT:
        raise PynePortableSnapshotError(
            f"Unsupported portable incremental snapshot format {envelope['format']!r}"
        )
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise PynePortableSnapshotError("Portable incremental snapshot payload is invalid")
    expected = f"sha256:{hashlib.sha256(_canonical_json(payload)).hexdigest()}"
    if envelope["checksum"] != expected:
        raise PynePortableSnapshotError("Portable incremental snapshot checksum does not match")
    validate_snapshot_semantics(payload.get("semanticsVersion"))
    expected_keys = {
        "semanticsVersion",
        "schemaVersion",
        "scriptSha256",
        "settings",
        "providerRequired",
        "stateGraph",
    }
    if set(payload) != expected_keys:
        raise PynePortableSnapshotError("Portable incremental snapshot payload fields are invalid")
    if payload["schemaVersion"] != PYNE_INCREMENTAL_PORTABLE_STATE_SNAPSHOT_VERSION:
        raise PynePortableSnapshotError(
            "Unsupported portable incremental state snapshot version "
            f"{payload['schemaVersion']!r}"
        )
    budget = _NodeBudget(max_nodes)
    settings = _decode_value(
        payload["settings"],
        depth=0,
        max_depth=max_depth,
        budget=budget,
    )
    if not isinstance(settings, dict):
        raise PynePortableSnapshotError("Portable state snapshot settings must be a mapping")
    script_sha256 = _validate_script_sha256(payload["scriptSha256"])
    if not isinstance(payload["providerRequired"], bool):
        raise PynePortableSnapshotError("Portable snapshot providerRequired must be boolean")
    snapshot = decode_typed_state_graph(
        payload["stateGraph"],
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    return PortableStateCheckpoint(
        script_sha256=script_sha256,
        settings=settings,
        provider_required=payload["providerRequired"],
        snapshot=snapshot,
    )


def portable_snapshot_format(
    value: bytes | bytearray | memoryview | str,
    *,
    max_bytes: int = DEFAULT_PORTABLE_SNAPSHOT_MAX_BYTES,
) -> str:
    return str(_decode_envelope(value, max_bytes=max_bytes)["format"])


def _decode_envelope(
    value: bytes | bytearray | memoryview | str,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    limit = max(int(max_bytes), 1)
    if len(raw) > limit:
        raise PynePortableSnapshotError(f"Portable incremental snapshot exceeds {limit} bytes")
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PynePortableSnapshotError("Portable incremental snapshot is not valid JSON") from exc
    if not isinstance(envelope, dict) or set(envelope) != {"format", "checksum", "payload"}:
        raise PynePortableSnapshotError("Portable incremental snapshot envelope is invalid")
    return envelope


def _validate_script_sha256(value: Any) -> str:
    script_sha256 = str(value)
    if len(script_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in script_sha256
    ):
        raise PynePortableSnapshotError("Portable snapshot scriptSha256 is invalid")
    return script_sha256


def portable_settings_contract(settings: PyneSettings) -> dict[str, Any]:
    """Return only execution fields that determine replay semantics and limits."""
    return {
        "securityMode": settings.security_mode,
        "timeoutSeconds": settings.timeout_seconds,
        "maxBars": settings.max_bars,
        "maxOutputSeries": settings.max_output_series,
        "maxOutputPoints": settings.max_output_points,
        "maxDrawingObjects": settings.max_drawing_objects,
        "maxArraySize": settings.max_array_size,
        "maxMapSize": settings.max_map_size,
        "maxMatrixCells": settings.max_matrix_cells,
        "maxCollectionDepth": settings.max_collection_depth,
        "maxStrategyPendingOperations": settings.max_strategy_pending_operations,
        "cacheMaxItems": settings.cache_max_items,
        "allowedImports": list(settings.allowed_imports),
        "syminfo": asdict(settings.syminfo),
        "timeframe": asdict(settings.timeframe),
        "session": asdict(settings.session),
    }


def settings_from_portable_contract(contract: Mapping[str, Any]) -> PyneSettings:
    try:
        return PyneSettings(
            security_mode=str(contract["securityMode"]),
            executor_mode="inline",
            timeout_seconds=float(contract["timeoutSeconds"]),
            max_bars=int(contract["maxBars"]),
            max_output_series=int(contract["maxOutputSeries"]),
            max_output_points=int(contract["maxOutputPoints"]),
            max_drawing_objects=int(contract["maxDrawingObjects"]),
            max_array_size=int(contract["maxArraySize"]),
            max_map_size=int(contract["maxMapSize"]),
            max_matrix_cells=int(contract["maxMatrixCells"]),
            max_collection_depth=int(contract["maxCollectionDepth"]),
            max_strategy_pending_operations=int(contract["maxStrategyPendingOperations"]),
            cache_max_items=int(contract["cacheMaxItems"]),
            allowed_imports=tuple(str(item) for item in contract["allowedImports"]),
            syminfo=contract["syminfo"],
            timeframe=contract["timeframe"],
            session=contract["session"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PynePortableSnapshotError("Portable snapshot settings contract is invalid") from exc


class _NodeBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = max(int(maximum), 1)
        self.count = 0

    def consume(self) -> None:
        self.count += 1
        if self.count > self.maximum:
            raise PynePortableSnapshotError(
                f"Portable incremental snapshot exceeds {self.maximum} values"
            )


def _encode_value(value: Any, *, depth: int, max_depth: int, budget: _NodeBudget) -> Any:
    budget.consume()
    if depth > max(int(max_depth), 1):
        raise PynePortableSnapshotError(
            f"Portable incremental snapshot exceeds nesting depth {max(int(max_depth), 1)}"
        )
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PynePortableSnapshotError("Portable snapshot does not allow NaN or infinity")
        return value
    if isinstance(value, list):
        return [
            _encode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
            for item in value
        ]
    if isinstance(value, tuple):
        return {
            "$type": "tuple",
            "items": [
                _encode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
                for item in value
            ],
        }
    if isinstance(value, frozenset):
        encoded = [
            _encode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
            for item in value
        ]
        return {"$type": "frozenset", "items": sorted(encoded, key=_canonical_json)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise PynePortableSnapshotError("Portable snapshot mapping keys must be strings")
        if "$type" in value:
            raise PynePortableSnapshotError("Portable snapshot mappings reserve the '$type' key")
        return {
            key: _encode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
            for key, item in value.items()
        }
    raise PynePortableSnapshotError(
        f"Portable snapshot cannot encode {type(value).__qualname__}"
    )


def _decode_value(value: Any, *, depth: int, max_depth: int, budget: _NodeBudget) -> Any:
    budget.consume()
    if depth > max(int(max_depth), 1):
        raise PynePortableSnapshotError(
            f"Portable incremental snapshot exceeds nesting depth {max(int(max_depth), 1)}"
        )
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PynePortableSnapshotError("Portable snapshot does not allow NaN or infinity")
        return value
    if isinstance(value, list):
        return [
            _decode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
            for item in value
        ]
    if isinstance(value, dict):
        if "$type" in value:
            if set(value) != {"$type", "items"} or not isinstance(value["items"], list):
                raise PynePortableSnapshotError("Portable snapshot tagged value is invalid")
            decoded = [
                _decode_value(item, depth=depth + 1, max_depth=max_depth, budget=budget)
                for item in value["items"]
            ]
            if value["$type"] == "tuple":
                return tuple(decoded)
            if value["$type"] == "frozenset":
                return frozenset(decoded)
            raise PynePortableSnapshotError(
                f"Unsupported portable snapshot value tag {value['$type']!r}"
            )
        return {
            str(key): _decode_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                budget=budget,
            )
            for key, item in value.items()
        }
    raise PynePortableSnapshotError("Portable snapshot contains unsupported JSON values")


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PynePortableSnapshotError("Portable snapshot contains invalid JSON values") from exc


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise PynePortableSnapshotError(f"Portable snapshot {name} must be a positive integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise PynePortableSnapshotError(
            f"Portable snapshot {name} must be a positive integer"
        ) from exc
    if normalized <= 0 or normalized != value:
        raise PynePortableSnapshotError(f"Portable snapshot {name} must be a positive integer")
    return normalized


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise PynePortableSnapshotError(
            f"Portable snapshot {name} must be a non-negative integer"
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise PynePortableSnapshotError(
            f"Portable snapshot {name} must be a non-negative integer"
        ) from exc
    if normalized < 0 or normalized != value:
        raise PynePortableSnapshotError(
            f"Portable snapshot {name} must be a non-negative integer"
        )
    return normalized
