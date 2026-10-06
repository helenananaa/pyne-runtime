"""Authoritative linefill entries with a recoverable dependency index.

Portable snapshots encode the authority's type and dictionary entries. Typed
decoding retains graph identity and reconstructs the derived index. A plain
fallback bucket is indexed on first use. Index contents are never serialized.
"""
from __future__ import annotations

import copy
from typing import Any


_MISSING = object()


class LineFillStore(dict[str, dict[str, Any]]):
    def __init__(self, entries=()):
        super().__init__()
        self._by_line: dict[str, dict[str, None]] = {}
        self.update(entries)

    def __setitem__(self, key: str, entry: dict[str, Any]) -> None:
        if key in self:
            self._unindex(key, self[key])
        super().__setitem__(key, entry)
        for line_id in dict.fromkeys((entry["line1_id"], entry["line2_id"])):
            self._by_line.setdefault(line_id, {})[key] = None

    def _unindex(self, key: str, entry: dict[str, Any]) -> None:
        for line_id in dict.fromkeys((entry["line1_id"], entry["line2_id"])):
            dependencies = self._by_line[line_id]
            dependencies.pop(key)
            if not dependencies:
                self._by_line.pop(line_id)

    def __delitem__(self, key: str) -> None:
        self._unindex(key, self[key])
        super().__delitem__(key)

    def pop(self, key: str, default=_MISSING):
        if key not in self:
            if default is _MISSING:
                raise KeyError(key)
            return default
        entry = self[key]
        del self[key]
        return entry

    def clear(self) -> None:
        super().clear()
        self._by_line.clear()

    def update(self, entries=(), **kwargs) -> None:
        pairs = entries.items() if hasattr(entries, "items") else entries
        for key, entry in pairs:
            self[key] = entry
        for key, entry in kwargs.items():
            self[key] = entry

    def dependent_ids(self, line_id: str) -> tuple[str, ...]:
        return tuple(self._by_line.get(line_id, ()))

    def __deepcopy__(self, memo):
        result = type(self)()
        memo[id(self)] = result
        for key, entry in self.items():
            result[copy.deepcopy(key, memo)] = copy.deepcopy(entry, memo)
        return result


def linefill_store(owner: Any) -> LineFillStore:
    entries = owner._object_linefills
    if not isinstance(entries, LineFillStore):
        entries = LineFillStore(entries)
        owner._object_linefills = entries
    return entries
