"""Small in-process cache exposed to Pyne scripts."""
from __future__ import annotations

import threading
import time
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass
class _CacheEntry:
    value: Any
    created_at: float
    last_access: float
    ttl: float | None

    def expired(self, now: float) -> bool:
        return self.ttl is not None and (self.ttl <= 0 or now - self.created_at > self.ttl)


@dataclass(frozen=True)
class PyneCacheSnapshotEntry:
    key: str
    value: Any
    remaining_ttl: float | None
    last_access_age: float


@dataclass(frozen=True)
class PyneCacheSnapshot:
    """Opaque process-local snapshot of one execution-scope cache."""

    max_items: int
    entries: tuple[PyneCacheSnapshotEntry, ...]


class PyneCache:
    """Thread-safe process-local cache for expensive user objects."""

    def __init__(self, max_items: int = 32) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, _CacheEntry] = {}
        self._max_items = max(int(max_items), 1)

    def configure(self, *, max_items: int | None = None) -> None:
        with self._lock:
            if max_items is not None:
                self._max_items = max(int(max_items), 1)
                self._enforce_limit()

    def get_or_load(self, key: str, loader: Callable[[], Any], ttl: float | None = None) -> Any:
        if not callable(loader):
            raise TypeError("pyne.cache loader must be callable")
        normalized_key = str(key)
        now = time.time()
        with self._lock:
            entry = self._items.get(normalized_key)
            if entry is not None and not entry.expired(now):
                entry.last_access = now
                return entry.value
            if entry is not None:
                self._items.pop(normalized_key, None)

        value = loader()

        with self._lock:
            now = time.time()
            self._items[normalized_key] = _CacheEntry(
                value=value,
                created_at=now,
                last_access=now,
                ttl=float(ttl) if ttl is not None else None,
            )
            self._enforce_limit()
        return value

    def clear(self, key: str | None = None) -> int:
        with self._lock:
            if key is None:
                count = len(self._items)
                self._items.clear()
                return count
            return 1 if self._items.pop(str(key), None) is not None else 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._items),
                "maxItems": self._max_items,
                "keys": list(self._items.keys()),
            }

    def snapshot_state(self, *, memo: dict[int, Any] | None = None) -> PyneCacheSnapshot:
        """Copy live entries for process-local incremental recovery."""

        now = time.time()
        entries: list[PyneCacheSnapshotEntry] = []
        with self._lock:
            for key, entry in self._items.items():
                if entry.expired(now):
                    continue
                remaining_ttl = (
                    None
                    if entry.ttl is None
                    else max(entry.ttl - (now - entry.created_at), 0.0)
                )
                entries.append(
                    PyneCacheSnapshotEntry(
                        key=key,
                        value=copy.deepcopy(entry.value, memo),
                        remaining_ttl=remaining_ttl,
                        last_access_age=max(now - entry.last_access, 0.0),
                    )
                )
            return PyneCacheSnapshot(max_items=self._max_items, entries=tuple(entries))

    def restore_state(
        self,
        snapshot: PyneCacheSnapshot,
        *,
        memo: dict[int, Any] | None = None,
    ) -> None:
        """Replace cache contents from a process-local snapshot."""

        if not isinstance(snapshot, PyneCacheSnapshot):
            raise TypeError("snapshot must be a PyneCacheSnapshot")
        now = time.time()
        restored: dict[str, _CacheEntry] = {}
        for item in snapshot.entries:
            ttl = item.remaining_ttl
            if ttl is not None and ttl <= 0:
                continue
            restored[item.key] = _CacheEntry(
                value=copy.deepcopy(item.value, memo),
                created_at=now,
                last_access=now - max(item.last_access_age, 0.0),
                ttl=ttl,
            )
        with self._lock:
            self._max_items = max(int(snapshot.max_items), 1)
            self._items = restored
            self._enforce_limit()

    def adopt_state(self, other: "PyneCache") -> None:
        """Replace live contents with another cache's already-materialized state."""
        if not isinstance(other, PyneCache):
            raise TypeError("other must be a PyneCache")
        with self._lock:
            with other._lock:
                self._max_items = other._max_items
                self._items = other._items

    def _enforce_limit(self) -> None:
        while len(self._items) > self._max_items:
            oldest_key = min(
                self._items,
                key=lambda key: self._items[key].last_access,
            )
            self._items.pop(oldest_key, None)


pyne_cache = PyneCache()


@dataclass(frozen=True)
class PyneExecutionScope:
    """Cache and other mutable services owned by one execution scope.

    Runtimes create a fresh scope for every batch execution and every
    incremental session unless a host explicitly supplies a shared scope.
    """

    cache: PyneCache

    @classmethod
    def fresh(cls, *, max_items: int = 32) -> "PyneExecutionScope":
        return cls(cache=PyneCache(max_items=max_items))


class PyneCacheNamespace:
    """Namespace injected as ``pyne`` inside user scripts."""

    def __init__(self, cache: PyneCache | None = None) -> None:
        self._cache = cache or pyne_cache
        self._cache_override: ContextVar[PyneCache | None] = ContextVar(
            f"pyne_cache_override_{id(self)}",
            default=None,
        )

    def _active_cache(self) -> PyneCache:
        return self._cache_override.get() or self._cache

    @contextmanager
    def _using_cache(self, cache: PyneCache) -> Iterator[None]:
        """Temporarily route every bound helper alias to ``cache`` in this context."""
        token = self._cache_override.set(cache)
        try:
            yield
        finally:
            self._cache_override.reset(token)

    def cache(self, key: str, loader: Callable[[], Any], ttl: float | None = None) -> Any:
        return self._active_cache().get_or_load(key, loader, ttl=ttl)

    def cache_clear(self, key: str | None = None) -> int:
        return self._active_cache().clear(key)

    def cache_stats(self) -> dict[str, Any]:
        return self._active_cache().stats()


pyne = PyneCacheNamespace(pyne_cache)
