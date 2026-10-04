"""Shared incremental session manager."""
from __future__ import annotations

import copy
import math
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from .bar import IncrementalBar
from .result import IncrementalPyneResult
from .session import PyneIncrementalSession


@dataclass
class SharedPyneIncrementalSession:
    key: str
    session: PyneIncrementalSession
    ref_count: int = 0
    seeded: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)
    last_event_key: tuple[Any, ...] | None = None
    last_event_result: IncrementalPyneResult | None = None
    created_at: float = 0.0
    last_access_at: float = 0.0
    idle_since: float | None = None
    _lease_token: object = field(default_factory=object, repr=False, compare=False)


class PyneIncrementalSessionCapacityError(RuntimeError):
    """Raised when all bounded manager slots are actively referenced."""


class PyneIncrementalSessionManager:
    """Reference-counted in-process session cache for incremental Pyne."""

    def __init__(
        self,
        *,
        max_sessions: int = 64,
        idle_ttl_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, SharedPyneIncrementalSession] = {}
        self._pending_creations: dict[str, threading.Event] = {}
        self._creation_owners: dict[str, int] = {}
        # Tokens/counts retain no forced-closed session objects. Key-only
        # releases after replacement cannot identify an incarnation, so keep
        # their attribution unresolved until balanced returns settle it.
        self._ambiguous_leases: dict[str, dict[object, int]] = {}
        self._legacy_releases: dict[str, int] = {}
        self.max_sessions = max(int(max_sessions), 1)
        self.idle_ttl_seconds = max(float(idle_ttl_seconds), 0.0)
        self._clock = clock or time.monotonic

    def acquire(
        self,
        key: str,
        factory: Callable[[], PyneIncrementalSession],
    ) -> SharedPyneIncrementalSession:
        while True:
            with self._lock:
                now = self._clock()
                self._collect_expired_locked(now)
                shared = self._sessions.get(key)
                if shared is not None:
                    counts = self._ambiguous_leases.get(key)
                    if counts is None:
                        shared.ref_count += 1
                    else:
                        counts[shared._lease_token] = counts.get(shared._lease_token, 0) + 1
                        shared.ref_count = self._reference_bound_locked(key, shared)
                    shared.last_access_at = now
                    shared.idle_since = None
                    return shared
                pending = self._pending_creations.get(key)
                if pending is None:
                    if len(self._sessions) >= self.max_sessions:
                        idle = [item for item in self._sessions.values() if item.ref_count == 0]
                        if not idle:
                            raise PyneIncrementalSessionCapacityError(
                                f"Incremental session capacity reached ({self.max_sessions})"
                            )
                    pending = threading.Event()
                    self._pending_creations[key] = pending
                    self._creation_owners[key] = threading.get_ident()
                    break
                if self._creation_owners.get(key) == threading.get_ident():
                    raise RuntimeError(f"Reentrant acquisition of incremental session key: {key}")
            pending.wait()

        try:
            session = factory()
        except BaseException:
            with self._lock:
                self._pending_creations.pop(key, None)
                self._creation_owners.pop(key, None)
                pending.set()
            raise

        with self._lock:
            now = self._clock()
            self._collect_expired_locked(now)
            try:
                self._ensure_slot_locked(now)
                shared = SharedPyneIncrementalSession(
                    key=key,
                    session=session,
                    ref_count=1,
                    created_at=now,
                    last_access_at=now,
                )
                self._sessions[key] = shared
                counts = self._ambiguous_leases.get(key)
                if counts is not None:
                    counts[shared._lease_token] = 1
                return shared
            finally:
                self._pending_creations.pop(key, None)
                self._creation_owners.pop(key, None)
                pending.set()

    def release(self, key: str, *, shared: SharedPyneIncrementalSession | None = None) -> None:
        """Return one acquisition, optionally identifying its exact incarnation.

        Pair every acquire with one release. ``shared=lease`` identifies old
        acquisitions even after force-close and same-key replacement. Legacy
        key-only releases remain valid; after replacement their unresolved
        attribution may keep a current session until older leases return.
        """
        if shared is not None and shared.key != key:
            raise ValueError("shared session key does not match release key")
        with self._lock:
            current = self._sessions.get(key)
            counts = self._ambiguous_leases.get(key)
            if counts is None:
                if current is None or shared is not None and current is not shared:
                    return
                current.ref_count = max(current.ref_count - 1, 0)
            else:
                if shared is None:
                    if sum(counts.values()) <= self._legacy_releases.get(key, 0):
                        return
                    self._legacy_releases[key] = self._legacy_releases.get(key, 0) + 1
                else:
                    remaining = counts.get(shared._lease_token, 0)
                    if remaining <= 0:
                        return
                    if remaining == 1:
                        counts.pop(shared._lease_token)
                    else:
                        counts[shared._lease_token] = remaining - 1
                total = sum(counts.values()) - self._legacy_releases.get(key, 0)
                if current is not None:
                    current.ref_count = self._reference_bound_locked(key, current)
                if shared is not None and shared is not current:
                    shared.ref_count = min(counts.get(shared._lease_token, 0), max(total, 0))
                if total <= 0:
                    self._ambiguous_leases.pop(key, None)
                    self._legacy_releases.pop(key, None)
            if current is not None and current.ref_count <= 0:
                if self.idle_ttl_seconds <= 0:
                    self._sessions.pop(key, None)
                else:
                    now = self._clock()
                    current.idle_since = now
                    current.last_access_at = now

    def _reference_bound_locked(self, key: str, shared: SharedPyneIncrementalSession) -> int:
        counts = self._ambiguous_leases[key]
        total = sum(counts.values()) - self._legacy_releases.get(key, 0)
        return min(counts.get(shared._lease_token, 0), max(total, 0))

    def collect_expired(self) -> list[str]:
        """Remove idle sessions whose TTL elapsed and return their keys."""

        with self._lock:
            return self._collect_expired_locked(self._clock())

    def close(self, key: str, *, force: bool = False) -> bool:
        """Explicitly remove one session; active sessions require ``force``."""

        with self._lock:
            shared = self._sessions.get(key)
            if shared is None or (shared.ref_count > 0 and not force):
                return False
            if shared.ref_count > 0:
                counts = self._ambiguous_leases.setdefault(key, {})
                counts.setdefault(shared._lease_token, shared.ref_count)
            self._sessions.pop(key, None)
            return True

    def _collect_expired_locked(self, now: float) -> list[str]:
        expired = [
            key
            for key, shared in self._sessions.items()
            if shared.ref_count == 0
            and shared.idle_since is not None
            and now - shared.idle_since >= self.idle_ttl_seconds
        ]
        for key in expired:
            self._sessions.pop(key, None)
        return expired

    def _ensure_slot_locked(self, now: float) -> None:
        if len(self._sessions) < self.max_sessions:
            return
        idle = [shared for shared in self._sessions.values() if shared.ref_count == 0]
        if not idle:
            raise PyneIncrementalSessionCapacityError(
                f"Incremental session capacity reached ({self.max_sessions})"
            )
        victim = min(idle, key=lambda shared: (shared.last_access_at, shared.created_at))
        self._sessions.pop(victim.key, None)

    def seed_or_snapshot(
        self,
        shared: SharedPyneIncrementalSession,
        ohlcv: list[dict[str, Any]],
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        with shared.lock:
            self._touch(shared)
            if not shared.seeded:
                result = shared.session.seed(ohlcv, start_s=start_s, end_s=end_s)
                shared.seeded = True
                return copy.deepcopy(result)
            return copy.deepcopy(shared.session.snapshot_result(start_s=start_s, end_s=end_s))

    def process_bar(
        self,
        shared: SharedPyneIncrementalSession,
        bar: dict[str, Any],
        *,
        preview: bool,
    ) -> IncrementalPyneResult:
        normalized_bar = IncrementalBar.from_dict(bar, is_confirmed=not preview).raw
        event_key = ("preview" if preview else "closed", _freeze_event_value(normalized_bar))
        with shared.lock:
            self._touch(shared)
            if shared.last_event_key == event_key and shared.last_event_result is not None:
                return copy.deepcopy(shared.last_event_result)
            result = (
                shared.session.on_bar_updated(bar)
                if preview
                else shared.session.on_bar_closed(bar)
            )
            shared.last_event_key = event_key
            shared.last_event_result = copy.deepcopy(result)
            return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            self._collect_expired_locked(now)
            return {
                "sessions": len(self._sessions),
                "maxSessions": self.max_sessions,
                "idleTtlSeconds": self.idle_ttl_seconds,
                "keys": {
                    key: {
                        "refCount": shared.ref_count,
                        "seeded": shared.seeded,
                        "idle": shared.ref_count == 0,
                        "idleSeconds": (
                            None
                            if shared.idle_since is None
                            else max(now - shared.idle_since, 0.0)
                        ),
                    }
                    for key, shared in self._sessions.items()
                },
            }

    def _touch(self, shared: SharedPyneIncrementalSession) -> None:
        with self._lock:
            now = self._clock()
            shared.last_access_at = now
            if shared.ref_count > 0:
                shared.idle_since = None


def _freeze_event_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        items = [
            (_freeze_event_value(key), _freeze_event_value(item))
            for key, item in value.items()
        ]
        return ("mapping", tuple(sorted(items, key=repr)))
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze_event_value(item) for item in value))
    if isinstance(value, (set, frozenset)):
        items = (_freeze_event_value(item) for item in value)
        return ("set", tuple(sorted(items, key=repr)))
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan")
        if math.isinf(value):
            return ("float", "inf" if value > 0 else "-inf")
        return ("float", value)
    if isinstance(value, (str, int, bool, bytes, type(None))):
        return (type(value).__name__, value)
    return (type(value).__qualname__, repr(value))
