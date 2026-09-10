"""Friendly top-level API for Pyne."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .authoring_checks import VALIDATION_TARGETS, target_diagnostics
from .capabilities import capability_diagnostics
from .data import PyneData, PyneOhlcvError, coerce_ohlcv
from .errors import classify_security_error, error_detail, error_hint
from .executor import execute_pyne_script
from .migration_diagnostics import migration_diagnostics, syntax_migration_diagnostics
from .request.provider import DataProvider
from .result import PyneResult
from .schema import schema as schema_bundle
from .security import PyneSecurityPolicy, validate_script_security
from .settings import PyneSettings


def run(
    script: str | Path,
    data: Any,
    params: dict[str, Any] | None = None,
    *,
    settings: PyneSettings | None = None,
    security_mode: str | None = None,
    executor_mode: str | None = None,
    data_provider: DataProvider | None = None,
    syminfo: Any = None,
    timeframe: Any = None,
    session: Any = None,
) -> PyneResult:
    """Run a Pyne script against OHLCV data."""
    script_text = _read_script(script)
    try:
        ohlcv = coerce_ohlcv(data)
    except PyneOhlcvError as exc:
        return PyneResult(
            ok=False,
            code="PYNE_INVALID_OHLCV",
            error=str(exc),
            hint=error_hint("PYNE_INVALID_OHLCV"),
        )
    return execute_pyne_script(
        script=script_text,
        ohlcv=ohlcv,
        params=params or {},
        security_mode=security_mode,
        executor_mode=executor_mode,
        settings=settings,
        data_provider=data_provider,
        syminfo=syminfo,
        timeframe=timeframe,
        session=session,
    )


def read_ohlcv(
    path: str | Path,
    *,
    time_unit: str = "s",
    columns: dict[str, str] | None = None,
) -> PyneData:
    return PyneData.from_csv(path, time_unit=time_unit, columns=columns)


def from_pandas(df: Any, **columns: Any) -> PyneData:
    return PyneData.from_pandas(df, **columns)


def validate(
    script: str | Path,
    *,
    settings: PyneSettings | None = None,
    runtime_mode: str | None = None,
    target: str | None = None,
) -> list[dict[str, Any]]:
    """Check syntax, selected policy and optional incremental target without execution.

    target='preview' or 'snapshot' enables conservative static readiness checks.
    An empty result does not certify dynamic object graphs or provider behavior.
    """
    if target is not None:
        if target not in VALIDATION_TARGETS:
            raise ValueError("target must be 'preview' or 'snapshot'")
        if runtime_mode not in (None, "incremental"):
            raise ValueError("preview/snapshot targets require runtime_mode='incremental'")
        runtime_mode = "incremental"
    if runtime_mode not in (None, "batch", "incremental"):
        raise ValueError("runtime_mode must be 'batch' or 'incremental'")
    script_text = _read_script(script)
    diagnostics: list[dict[str, Any]] = []
    try:
        compile(script_text, "<pyne>", "exec")
    except SyntaxError as exc:
        diagnostics.append(error_detail(
            "PYNE_SYNTAX_ERROR",
            str(exc.msg or exc),
            line=exc.lineno,
            column=exc.offset,
        ))
        diagnostics.extend(syntax_migration_diagnostics(script_text))
        return diagnostics

    diagnostics.extend(migration_diagnostics(script_text))
    diagnostics.extend(capability_diagnostics(script_text, runtime_mode=runtime_mode))
    diagnostics.extend(target_diagnostics(script_text, runtime_mode=runtime_mode, target=target))

    policy = PyneSecurityPolicy.from_settings(settings or PyneSettings.from_env())
    try:
        validate_script_security(script_text, policy)
    except Exception as exc:
        code = classify_security_error(str(exc))
        diagnostics.append(error_detail(code, str(exc)))
    return diagnostics


def schema() -> dict[str, Any]:
    return schema_bundle()


def _read_script(script: str | Path) -> str:
    if isinstance(script, Path):
        return script.read_text(encoding="utf-8")
    if isinstance(script, str):
        path = Path(script)
        if "\n" not in script:
            try:
                is_file = path.is_file()
            except OSError:
                is_file = False  # A long one-line Python program is not a filesystem path.
            if is_file:
                return path.read_text(encoding="utf-8")
        return script
    raise TypeError("script must be a string or path")
