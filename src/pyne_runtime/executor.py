"""Pyne execution strategies.

The process executor gives the host application a hard timeout boundary for
untrusted or buggy scripts: the worker is terminated after ``timeout_seconds``
plus ``process_grace_seconds``. It always starts the worker with the ``spawn``
multiprocessing start method.

Inline execution is the standalone default, preserving local execution and
long-lived ML/library state. No deadline is imposed unless configured. ``timeout_seconds`` is then a
best-effort Unix-main-thread timer (``SIGALRM``); Windows and non-main threads
do not receive a hard interrupt. Set ``require_hard_timeout=True`` only with
``executor_mode='process'``; inline plus a required hard timeout is rejected.
"""
from __future__ import annotations

import multiprocessing as mp
import pickle
import queue
import time
from dataclasses import replace
from typing import Any

from .errors import error_hint
from .request.provider import DataProvider
from .result import PyneResult
from .runtime import PyneRuntime
from .security import PyneSecurityPolicy
from .settings import PyneSettings, normalize_executor_mode


def execute_pyne_script(
    *,
    script: str,
    ohlcv: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    security_mode: str | None = None,
    executor_mode: str | None = None,
    timeout_seconds: float | None = None,
    settings: PyneSettings | None = None,
    data_provider: DataProvider | None = None,
    syminfo: Any = None,
    timeframe: Any = None,
    session: Any = None,
) -> PyneResult:
    """Execute a Pyne script using the configured strategy."""
    settings = settings or PyneSettings.from_env()
    if data_provider is not None:
        settings = replace(settings, data_provider=data_provider)
    if syminfo is not None:
        settings = replace(settings, syminfo=syminfo)
    if timeframe is not None:
        settings = replace(settings, timeframe=timeframe)
    if session is not None:
        settings = replace(settings, session=session)
    if timeout_seconds is not None:
        settings = replace(settings, timeout_seconds=timeout_seconds)
    mode = normalize_executor_mode(executor_mode or settings.executor_mode)
    if settings.require_hard_timeout and mode == "inline":
        raise ValueError(
            "require_hard_timeout=True cannot be delivered by executor_mode='inline'; "
            "use executor_mode='process' for hard timeout enforcement"
        )
    if mode == "inline":
        return PyneRuntime(settings=settings).execute(
            script=script,
            ohlcv=ohlcv,
            params=params or {},
            security_mode=security_mode,
        )
    return execute_pyne_script_in_process(
        script=script,
        ohlcv=ohlcv,
        params=params or {},
        security_mode=security_mode,
        timeout_seconds=timeout_seconds,
        settings=settings,
    )


def execute_pyne_script_in_process(
    *,
    script: str,
    ohlcv: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    security_mode: str | None = None,
    timeout_seconds: float | None = None,
    settings: PyneSettings | None = None,
) -> PyneResult:
    """Execute Pyne in a child process and terminate it on timeout."""
    settings = settings or PyneSettings.from_env()
    if timeout_seconds is not None:
        settings = replace(settings, timeout_seconds=timeout_seconds)
    policy = PyneSecurityPolicy.from_settings(settings, security_mode)
    timeout = policy.timeout_seconds
    grace = settings.process_grace_seconds
    serialization_error = _process_serialization_error(
        script,
        ohlcv,
        params or {},
        security_mode,
        settings,
    )
    if serialization_error is not None:
        return serialization_error

    result_queue = process = None
    started = received = False
    try:
        ctx = _multiprocessing_context()
        result_queue = ctx.Queue(maxsize=1)
        process = ctx.Process(
            target=_pyne_worker,
            args=(result_queue, script, ohlcv, params or {}, security_mode, settings),
            daemon=True,
        )
        process.start()
        started = True
        payload = _read_process_result(result_queue, process, timeout + grace if timeout is not None else None)
        received = payload is not None
        if payload is None:
            if process.is_alive():
                return PyneResult(ok=False, code="PYNE_TIMEOUT",
                                  error=f"Pyne script exceeded {timeout:g}s timeout",
                                  hint=error_hint("PYNE_TIMEOUT"))
            return _process_failed(f"Pyne executor process exited with code {process.exitcode}")
        return _decode_process_payload(payload)
    except Exception as exc:
        return _process_failed(f"Pyne executor process failed ({type(exc).__name__}): {exc}")
    finally:
        try:
            if process is not None:
                if started:
                    if received:
                        process.join(1)
                    if process.is_alive():
                        process.terminate()
                        process.join(1)
                    if process.is_alive():
                        process.kill()
                        process.join(1)
                process.close()
        finally:
            if result_queue is not None:
                result_queue.close()
                result_queue.join_thread()


def _process_failed(message: str) -> PyneResult:
    return PyneResult(ok=False, code="PYNE_PROCESS_FAILED", error=message,
                      hint=error_hint("PYNE_PROCESS_FAILED"))


def _decode_process_payload(payload: Any) -> PyneResult:
    if isinstance(payload, bytes):
        payload = pickle.loads(payload)
    if not isinstance(payload, dict):
        return _process_failed("Pyne executor returned an invalid payload")
    if payload.get("kind") == "result" and isinstance(payload.get("result"), dict):
        return PyneResult.from_dict(payload["result"])
    code = payload.get("code") or "PYNE_PROCESS_FAILED"
    return PyneResult(ok=False, code=code,
                      error=payload.get("error") or "Pyne executor process failed",
                      hint=payload.get("hint") or error_hint(code))


def _read_process_result(result_queue, process, timeout_seconds: float | None) -> Any:
    """Read the worker result while the process is still running.

    Large indicator payloads can block a child process in ``Queue.put()`` until
    the parent drains the pipe. Polling the queue before ``join()`` avoids a
    false timeout for scripts that finished computing but are returning many
    points.
    """
    deadline = None
    if timeout_seconds is not None:
        deadline = time.monotonic() + max(float(timeout_seconds), 0.0)

    while True:
        try:
            return result_queue.get(timeout=0.05)
        except queue.Empty:
            pass

        if not process.is_alive():
            try:
                return result_queue.get_nowait()
            except queue.Empty:
                return None

        if deadline is not None and time.monotonic() >= deadline:
            return None


def _process_serialization_error(*payloads: Any) -> PyneResult | None:
    try:
        pickle.dumps(payloads)
    except Exception as exc:
        code = "PYNE_PROCESS_SERIALIZATION_ERROR"
        return PyneResult(
            ok=False,
            code=code,
            error=(
                "Pyne process executor arguments must be pickle-serializable "
                f"({type(exc).__name__})"
            ),
            hint=error_hint(code),
        )
    return None


def _multiprocessing_context():
    """Return a multiprocessing context that always uses ``spawn``.

    ``spawn`` is available on every supported platform, does not inherit the
    parent address space or file descriptors, and is the only start method that
    this executor promises. Unix ``fork`` is intentionally not used: it can
    deadlock a multithreaded host and is not a security boundary.
    """
    return mp.get_context("spawn")


def _pyne_worker(
    result_queue,
    script: str,
    ohlcv: list[dict[str, Any]],
    params: dict[str, Any],
    security_mode: str | None,
    settings: PyneSettings,
) -> None:
    try:
        result = PyneRuntime(settings=settings).execute(
            script=script,
            ohlcv=ohlcv,
            params=params,
            security_mode=security_mode,
        )
        payload = {"kind": "result", "result": result.to_dict()}
    except BaseException as exc:
        payload = {
            "kind": "error",
            "code": "PYNE_PROCESS_FAILED",
            "error": f"Pyne executor process failed: {exc}",
        }
    # Queue's background feeder otherwise drops unpickleable results after
    # put() has returned, leaving the parent with an unexplained clean exit.
    # Serialize exactly once in the worker and only enqueue transport bytes.
    try:
        encoded = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        encoded = pickle.dumps({
            "kind": "error", "code": "PYNE_PROCESS_SERIALIZATION_ERROR",
            "error": f"Pyne process executor result must be pickle-serializable ({type(exc).__name__})",
            "hint": error_hint("PYNE_PROCESS_SERIALIZATION_ERROR"),
        }, protocol=pickle.HIGHEST_PROTOCOL)
    result_queue.put(encoded)
