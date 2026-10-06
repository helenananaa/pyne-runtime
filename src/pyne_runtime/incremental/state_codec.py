"""Safe typed object-graph codec for portable incremental state checkpoints."""
from __future__ import annotations

import importlib
import math
import time
from collections import deque
from types import SimpleNamespace
from typing import Any

import numpy as np

from ..plot.linefill_store import LineFillStore
from .checkpoint import PynePortableSnapshotError


PYNE_TYPED_STATE_GRAPH_VERSION = 1
_MAX_TYPED_ARRAY_BYTES = 256 * 1024 * 1024
_RUNTIME_TYPE_MODULES = (
    "pyne_runtime.barstate",
    "pyne_runtime.cache",
    "pyne_runtime.collections",
    "pyne_runtime.incremental.bar",
    "pyne_runtime.incremental.context",
    "pyne_runtime.incremental.limits",
    "pyne_runtime.incremental.session",
    "pyne_runtime.incremental.strategy",
    "pyne_runtime.incremental.ta",
    "pyne_runtime.metadata",
    "pyne_runtime.plot.refs",
    "pyne_runtime.series",
    "pyne_runtime.state",
    "pyne_runtime.trace",
)


def encode_typed_state_graph(value: Any, *, max_nodes: int, max_depth: int) -> dict[str, Any]:
    encoder = _GraphEncoder(max_nodes=max_nodes, max_depth=max_depth)
    return {
        "schemaVersion": PYNE_TYPED_STATE_GRAPH_VERSION,
        "root": encoder.encode(value),
        "nodes": encoder.nodes,
    }


def decode_typed_state_graph(
    graph: Any,
    *,
    max_nodes: int,
    max_depth: int,
) -> Any:
    if not isinstance(graph, dict) or set(graph) != {"schemaVersion", "root", "nodes"}:
        raise PynePortableSnapshotError("Portable typed state graph envelope is invalid")
    if graph["schemaVersion"] != PYNE_TYPED_STATE_GRAPH_VERSION:
        raise PynePortableSnapshotError(
            f"Unsupported portable typed state graph version {graph['schemaVersion']!r}"
        )
    nodes = graph["nodes"]
    if not isinstance(nodes, list) or len(nodes) > max(int(max_nodes), 1):
        raise PynePortableSnapshotError("Portable typed state graph node budget is invalid")
    decoder = _GraphDecoder(
        nodes,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    result = decoder.decode(graph["root"])
    decoder.finish_linefill_stores()
    return result


class _GraphEncoder:
    def __init__(self, *, max_nodes: int, max_depth: int) -> None:
        self.maximum = max(int(max_nodes), 1)
        self.max_depth = max(int(max_depth), 1)
        self.nodes: list[dict[str, Any]] = []
        self._memo: dict[int, int] = {}
        self._memo_values: list[Any] = []
        self._runtime_types = _runtime_type_registry()

    def encode(self, value: Any, *, depth: int = 0) -> Any:
        if depth > self.max_depth:
            raise PynePortableSnapshotError(
                f"Portable typed state exceeds nesting depth {self.max_depth}"
            )
        scalar = _encode_scalar(value)
        if scalar is not _NOT_SCALAR:
            return scalar
        if isinstance(value, np.generic):
            if type(value) is not np.generic.dtype.__get__(value, type(value)).type:
                raise PynePortableSnapshotError(
                    f"Portable typed state cannot encode {type(value).__module__}."
                    f"{type(value).__qualname__}"
                )
            return self.encode(value.item(), depth=depth)
        oid = id(value)
        if oid in self._memo:
            return {"$ref": self._memo[oid]}
        node_id = len(self.nodes)
        if node_id >= self.maximum:
            raise PynePortableSnapshotError(
                f"Portable typed state exceeds {self.maximum} object nodes"
            )
        self._memo[oid] = node_id
        self._memo_values.append(value)
        self.nodes.append({})
        node = self._encode_node(value, depth=depth + 1)
        self.nodes[node_id] = node
        return {"$ref": node_id}

    def _encode_node(self, value: Any, *, depth: int) -> dict[str, Any]:
        if isinstance(value, list):
            return {"kind": "list", "items": [self.encode(item, depth=depth) for item in value]}
        if isinstance(value, tuple):
            return {"kind": "tuple", "items": [self.encode(item, depth=depth) for item in value]}
        if isinstance(value, deque):
            return {
                "kind": "deque",
                "maxlen": value.maxlen,
                "items": [self.encode(item, depth=depth) for item in value],
            }
        if isinstance(value, dict):
            return {
                "kind": "linefill-store" if type(value) is LineFillStore else "dict",
                "items": [
                    [self.encode(key, depth=depth), self.encode(item, depth=depth)]
                    for key, item in value.items()
                ],
            }
        if isinstance(value, (set, frozenset)):
            ordered = sorted(value, key=_stable_set_key)
            return {
                "kind": "frozenset" if isinstance(value, frozenset) else "set",
                "items": [self.encode(item, depth=depth) for item in ordered],
            }
        if isinstance(value, np.ndarray):
            if value.dtype.kind not in "biufUS":
                raise PynePortableSnapshotError(
                    f"Portable typed state cannot encode ndarray dtype {value.dtype}"
                )
            return {
                "kind": "ndarray",
                "dtype": value.dtype.str,
                "shape": list(value.shape),
                "items": self.encode(value.tolist(), depth=depth),
            }
        if isinstance(value, SimpleNamespace):
            return {
                "kind": "namespace",
                "attributes": self._encode_attributes(vars(value), depth=depth),
            }
        type_name = _type_name(type(value))
        if type_name not in self._runtime_types:
            raise PynePortableSnapshotError(
                f"Portable typed state cannot encode {type(value).__module__}."
                f"{type(value).__qualname__}"
            )
        attributes = _object_attributes(value)
        if type_name == "pyne_runtime.trace:PyneTraceRecorder":
            attributes.pop("_clock", None)
        return {
            "kind": "object",
            "type": type_name,
            "attributes": self._encode_attributes(attributes, depth=depth),
        }

    def _encode_attributes(self, values: dict[str, Any], *, depth: int) -> list[list[Any]]:
        return [
            [name, self.encode(values[name], depth=depth)]
            for name in sorted(values)
        ]


class _GraphDecoder:
    def __init__(self, nodes: list[Any], *, max_depth: int, max_nodes: int) -> None:
        self.nodes = nodes
        self.max_depth = max(int(max_depth), 1)
        self.max_nodes = max(int(max_nodes), 1)
        self._values: dict[int, Any] = {}
        self._building: set[int] = set()
        self._runtime_types = _runtime_type_registry()
        self._linefill_nodes: list[tuple[LineFillStore, list[tuple[str, Any]]]] = []

    def decode(self, value: Any, *, depth: int = 0) -> Any:
        if depth > self.max_depth:
            raise PynePortableSnapshotError(
                f"Portable typed state exceeds nesting depth {self.max_depth}"
            )
        scalar = _decode_scalar(value)
        if scalar is not _NOT_SCALAR:
            return scalar
        if not isinstance(value, dict) or set(value) != {"$ref"}:
            raise PynePortableSnapshotError("Portable typed state value is invalid")
        node_id = value["$ref"]
        if isinstance(node_id, bool) or not isinstance(node_id, int):
            raise PynePortableSnapshotError("Portable typed state reference is invalid")
        if node_id < 0 or node_id >= len(self.nodes):
            raise PynePortableSnapshotError("Portable typed state reference is out of range")
        if node_id in self._values:
            return self._values[node_id]
        if node_id in self._building:
            raise PynePortableSnapshotError("Portable typed state contains an immutable cycle")
        return self._decode_node(node_id, depth=depth + 1)

    def _decode_node(self, node_id: int, *, depth: int) -> Any:
        node = self.nodes[node_id]
        if not isinstance(node, dict) or not isinstance(node.get("kind"), str):
            raise PynePortableSnapshotError("Portable typed state node is invalid")
        kind = node["kind"]
        _validate_node_fields(node, kind)
        self._building.add(node_id)
        try:
            if kind == "list":
                result: Any = []
                self._values[node_id] = result
                result.extend(self._decode_items(node, depth=depth))
                return result
            if kind in {"dict", "linefill-store"}:
                result = LineFillStore() if kind == "linefill-store" else {}
                self._values[node_id] = result
                linefill_pairs: list[tuple[str, Any]] = []
                linefill_keys: set[str] = set()
                for pair in _node_list(node, "items"):
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise PynePortableSnapshotError("Portable typed state mapping item is invalid")
                    key = self.decode(pair[0], depth=depth)
                    item = self.decode(pair[1], depth=depth)
                    if kind == "linefill-store":
                        if type(key) is not str or not key:
                            raise PynePortableSnapshotError("Portable typed linefill key is invalid")
                        if key in linefill_keys:
                            raise PynePortableSnapshotError(
                                "Portable typed linefill store contains duplicate keys"
                            )
                        linefill_keys.add(key)
                        linefill_pairs.append((key, item))
                        continue
                    try:
                        if key in result:
                            raise PynePortableSnapshotError(
                                "Portable typed state mapping contains duplicate keys"
                            )
                        result[key] = item
                    except (TypeError, ValueError) as exc:
                        raise PynePortableSnapshotError(
                            "Portable typed state mapping key is invalid"
                        ) from exc
                if kind == "linefill-store":
                    self._linefill_nodes.append((result, linefill_pairs))
                return result
            if kind == "deque":
                maxlen = node.get("maxlen")
                if maxlen is not None and (isinstance(maxlen, bool) or not isinstance(maxlen, int) or maxlen < 0):
                    raise PynePortableSnapshotError("Portable typed state deque maxlen is invalid")
                result = deque(maxlen=maxlen)
                self._values[node_id] = result
                result.extend(self._decode_items(node, depth=depth))
                return result
            if kind == "set":
                result = set()
                self._values[node_id] = result
                try:
                    result.update(self._decode_items(node, depth=depth))
                except (TypeError, ValueError) as exc:
                    raise PynePortableSnapshotError(
                        "Portable typed state set item is invalid"
                    ) from exc
                return result
            if kind in {"tuple", "frozenset"}:
                items = self._decode_items(node, depth=depth)
                try:
                    result = tuple(items) if kind == "tuple" else frozenset(items)
                except (TypeError, ValueError) as exc:
                    raise PynePortableSnapshotError(
                        "Portable typed state frozenset item is invalid"
                    ) from exc
                self._values[node_id] = result
                return result
            if kind == "ndarray":
                dtype = node.get("dtype")
                shape = node.get("shape")
                if not isinstance(dtype, str) or not isinstance(shape, list):
                    raise PynePortableSnapshotError("Portable typed ndarray contract is invalid")
                try:
                    resolved_dtype = np.dtype(dtype)
                except TypeError as exc:
                    raise PynePortableSnapshotError("Portable typed ndarray dtype is invalid") from exc
                if resolved_dtype.kind not in "biufUS":
                    raise PynePortableSnapshotError("Portable typed ndarray dtype is unsupported")
                if not all(
                    not isinstance(item, bool) and isinstance(item, int) and item >= 0
                    for item in shape
                ):
                    raise PynePortableSnapshotError("Portable typed ndarray shape is invalid")
                element_count = math.prod(shape)
                if element_count > self.max_nodes:
                    raise PynePortableSnapshotError(
                        "Portable typed ndarray exceeds the element budget"
                    )
                if resolved_dtype.itemsize * element_count > _MAX_TYPED_ARRAY_BYTES:
                    raise PynePortableSnapshotError(
                        "Portable typed ndarray exceeds the byte budget"
                    )
                items = self.decode(node.get("items"), depth=depth)
                try:
                    result = np.asarray(items, dtype=resolved_dtype).reshape(tuple(shape))
                except (TypeError, ValueError) as exc:
                    raise PynePortableSnapshotError("Portable typed ndarray shape is invalid") from exc
                self._values[node_id] = result
                return result
            if kind == "namespace":
                result = SimpleNamespace()
                self._values[node_id] = result
                self._restore_attributes(result, node, depth=depth)
                return result
            if kind == "object":
                type_name = node.get("type")
                if not isinstance(type_name, str) or type_name not in self._runtime_types:
                    raise PynePortableSnapshotError(
                        f"Portable typed state object type {type_name!r} is not allowed"
                    )
                cls = self._runtime_types[type_name]
                try:
                    result = object.__new__(cls)
                except TypeError as exc:
                    raise PynePortableSnapshotError(
                        f"Portable typed state cannot allocate {type_name}"
                    ) from exc
                self._values[node_id] = result
                self._restore_attributes(result, node, depth=depth)
                if type_name == "pyne_runtime.trace:PyneTraceRecorder":
                    object.__setattr__(result, "_clock", time.perf_counter)
                    if not hasattr(result, "span_events"):
                        object.__setattr__(result, "span_events", False)
                return result
            raise PynePortableSnapshotError(f"Unsupported portable typed state node {kind!r}")
        finally:
            self._building.discard(node_id)

    def _decode_items(self, node: dict[str, Any], *, depth: int) -> list[Any]:
        return [self.decode(item, depth=depth) for item in _node_list(node, "items")]

    def finish_linefill_stores(self) -> None:
        """Validate completed entry graphs, then rebuild only the private index.

        An entry may be an ancestor of its own store in a valid cycle. Filling a
        store while that dictionary is still decoding would mistake unfinished
        fields for a malformed entry. Every authority is allocated and memoized
        first; publication uses its normal setter after all dictionaries finish.
        """
        for _, pairs in self._linefill_nodes:
            for key, item in pairs:
                if (type(item) is not dict or type(item.get("id")) is not str or item["id"] != key
                        or type(item.get("line1_id")) is not str or not item["line1_id"]
                        or type(item.get("line2_id")) is not str or not item["line2_id"]):
                    raise PynePortableSnapshotError("Portable typed linefill entry is invalid")
        for store, pairs in self._linefill_nodes:
            for key, item in pairs:
                store[key] = item
        self._linefill_nodes.clear()

    def _restore_attributes(self, target: Any, node: dict[str, Any], *, depth: int) -> None:
        attributes = _node_list(node, "attributes")
        for pair in attributes:
            if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
                raise PynePortableSnapshotError("Portable typed state object attribute is invalid")
            attribute_name = pair[0]
            class_attribute = getattr(type(target), attribute_name, None)
            if attribute_name.startswith("__") or callable(class_attribute):
                raise PynePortableSnapshotError(
                    f"Portable typed state cannot shadow runtime attribute {attribute_name!r}"
                )
            try:
                object.__setattr__(target, attribute_name, self.decode(pair[1], depth=depth))
            except (AttributeError, TypeError, ValueError) as exc:
                raise PynePortableSnapshotError(
                    f"Portable typed state cannot restore attribute {pair[0]!r}"
                ) from exc


class _NotScalar:
    pass


_NOT_SCALAR = _NotScalar()


def _encode_scalar(value: Any) -> Any:
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if math.isnan(value):
            return {"$float": "nan"}
        if math.isinf(value):
            return {"$float": "inf" if value > 0 else "-inf"}
        return value
    return _NOT_SCALAR


def _decode_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise PynePortableSnapshotError("Portable typed state contains non-finite JSON")
        return value
    if isinstance(value, dict) and set(value) == {"$float"}:
        tagged = value["$float"]
        if tagged == "nan":
            return float("nan")
        if tagged == "inf":
            return float("inf")
        if tagged == "-inf":
            return float("-inf")
        raise PynePortableSnapshotError("Portable typed state float tag is invalid")
    return _NOT_SCALAR


def _runtime_type_registry() -> dict[str, type[Any]]:
    result: dict[str, type[Any]] = {}
    for module_name in _RUNTIME_TYPE_MODULES:
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if isinstance(value, type) and value.__module__ == module_name:
                result[_type_name(value)] = value
    return result


def _type_name(value: type[Any]) -> str:
    return f"{value.__module__}:{value.__qualname__}"


def _object_attributes(value: Any) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    try:
        attributes.update(vars(value))
    except TypeError:
        pass
    for cls in type(value).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if slot in {"__dict__", "__weakref__"}:
                continue
            storage_name = _slot_storage_name(cls, slot)
            try:
                attributes[storage_name] = object.__getattribute__(value, storage_name)
            except AttributeError:
                continue
    return attributes


def _slot_storage_name(cls: type[Any], slot: str) -> str:
    if slot.startswith("__") and not slot.endswith("__"):
        return f"_{cls.__name__.lstrip('_')}{slot}"
    return slot


def _node_list(node: dict[str, Any], key: str) -> list[Any]:
    values = node.get(key)
    if not isinstance(values, list):
        raise PynePortableSnapshotError(f"Portable typed state node {key} is invalid")
    return values


def _validate_node_fields(node: dict[str, Any], kind: str) -> None:
    expected = {
        "list": {"kind", "items"},
        "tuple": {"kind", "items"},
        "deque": {"kind", "maxlen", "items"},
        "dict": {"kind", "items"},
        "linefill-store": {"kind", "items"},
        "set": {"kind", "items"},
        "frozenset": {"kind", "items"},
        "ndarray": {"kind", "dtype", "shape", "items"},
        "namespace": {"kind", "attributes"},
        "object": {"kind", "type", "attributes"},
    }.get(kind)
    if expected is not None and set(node) != expected:
        raise PynePortableSnapshotError(
            f"Portable typed state {kind} node fields are invalid"
        )


def _stable_set_key(value: Any) -> tuple[str, str]:
    if value is None or isinstance(value, (bool, int, float, str)):
        return (type(value).__qualname__, repr(value))
    raise PynePortableSnapshotError(
        "Portable typed state sets may contain only scalar values"
    )
