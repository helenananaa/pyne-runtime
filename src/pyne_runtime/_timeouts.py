"""Compose a local deadline with the caller's existing POSIX alarm."""
from __future__ import annotations

import math
import signal
from contextlib import contextmanager
from time import monotonic


@contextmanager
def alarm_timeout(seconds: float, error_type: type[Exception]):
    required = ("SIGALRM", "ITIMER_REAL", "setitimer", "getitimer")
    if not all(hasattr(signal, name) for name in required):
        yield
        return
    try:
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    except (AttributeError, ValueError, OSError):
        yield
        return
    started = monotonic()
    deadline = started + seconds
    previous_deadline = started + previous_delay if previous_delay > 0 else None

    def arm():
        earliest = min(deadline, previous_deadline) if previous_deadline is not None else deadline
        signal.setitimer(signal.ITIMER_REAL, max(earliest - monotonic(), 1e-6))

    def restore():
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        delay = 0 if previous_deadline is None else max(previous_deadline - monotonic(), 1e-6)
        signal.setitimer(signal.ITIMER_REAL, delay, previous_interval)

    def handler(signum, frame):
        nonlocal previous_deadline
        now = monotonic()
        if previous_deadline is not None and previous_deadline <= now:
            if previous_interval > 0:
                skipped = math.floor((now - previous_deadline) / previous_interval) + 1
                previous_deadline += skipped * previous_interval
            else:
                previous_deadline = None
            if callable(previous_handler):
                previous_handler(signum, frame)
            elif previous_handler != signal.SIG_IGN:
                # Preserve an explicitly selected default signal disposition.
                signal.signal(signal.SIGALRM, previous_handler)
                signal.raise_signal(signum)
                signal.signal(signal.SIGALRM, handler)
        if monotonic() >= deadline:
            raise error_type(f"Pyne script exceeded {seconds:g}s timeout")
        arm()

    installed = False
    try:
        signal.signal(signal.SIGALRM, handler)
        installed = True
        arm()
    except (AttributeError, ValueError, OSError):
        if installed:
            signal.signal(signal.SIGALRM, previous_handler)
        yield
        return
    try:
        yield
    finally:
        restore()
