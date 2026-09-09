"""
Pyne Runtime — script execution engine.

The runtime is responsible for:
  1. Building the data context (OHLCV arrays + derived fields)
  2. Constructing the execution namespace (ta, input, plot, color, etc.)
  3. Executing the user script
  4. Collecting and returning all outputs (lines, markers, fills, etc.)

Usage::

    runtime = PyneRuntime()
    result = runtime.execute(script_code, ohlcv_data, user_params)
    # result.lines  → list of line dicts for frontend
    # result.output → full structured output (histograms, markers, etc.)
    # result.param_schema → collected parameter schemas for UI
"""
from __future__ import annotations

from typing import Any

from .context import PyneContext
from .data import PyneOhlcvError
from .input import InputModule, PyneInputError
from .plot import OutputCollector
from .request import PyneRequestError
from .incremental import IncrementalPyneResult, PyneIncrementalSession, is_incremental_pyne_script
from .cache import PyneExecutionScope
from .errors import classify_security_error, error_hint
from .namespace import RuntimeServices, build_script_namespace
from .result import PyneResult
from .security import (
    PyneSecurityError,
    PyneSecurityPolicy,
    PyneTimeoutError,
    enforce_output_limits,
    execution_timeout,
    validate_script_security,
)
from .settings import PyneSettings
from .trace import PyneTraceRecorder


class PyneRuntime:
    """Pyne script execution engine.

    Stateless — each ``execute()`` call creates fresh context objects.
    Can be reused across multiple executions safely.
    """

    def __init__(
        self,
        settings: PyneSettings | None = None,
        *,
        execution_scope: PyneExecutionScope | None = None,
    ) -> None:
        self.settings = settings or PyneSettings.from_env()
        self.execution_scope = execution_scope

    def execute(
        self,
        script: str,
        ohlcv: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
        security_mode: str | None = None,
    ) -> PyneResult:
        """Execute a Pyne/Python indicator script.

        Args:
            script: The Python script code.
            ohlcv: List of OHLCV bar dicts (time, open, high, low, close, volume).
            params: User-provided parameter overrides.

        Returns:
            PyneResult with all computed outputs.
        """
        trace = PyneTraceRecorder(
            enabled=self.settings.trace_enabled,
            max_events=self.settings.trace_max_events,
            timings_enabled=self.settings.trace_timings_enabled,
            span_events=self.settings.trace_span_events,
            slow_span_ms=self.settings.trace_slow_span_ms,
            redacted_fields=self.settings.trace_redacted_fields,
        )
        runtime_mode = "incremental" if is_incremental_pyne_script(script) else "batch"
        trace.emit("execution.start", mode=runtime_mode, bars=len(ohlcv))

        def finish(result: PyneResult, *, status: str) -> PyneResult:
            return self._finalize_trace(result, trace, status=status)

        if not ohlcv:
            return finish(PyneResult(
                ok=False,
                code="PYNE_INVALID_OHLCV",
                error="No OHLCV data provided",
                hint=error_hint("PYNE_INVALID_OHLCV"),
            ), status="error")

        params = params or {}
        execution_scope = self.execution_scope or PyneExecutionScope.fresh(
            max_items=self.settings.cache_max_items,
        )

        try:
            policy = PyneSecurityPolicy.from_settings(self.settings, security_mode)

            if len(ohlcv) > policy.max_bars:
                return finish(PyneResult(
                    ok=False,
                    code="PYNE_INVALID_OHLCV",
                    error=f"Too many data points (max {policy.max_bars})",
                    hint="Reduce the history window or increase max_bars for trusted workloads.",
                ), status="error")

            with trace.span("security.validate", category="security"):
                validate_script_security(script, policy)

            if is_incremental_pyne_script(script):
                incremental = PyneIncrementalSession(
                    script=script,
                    params=params,
                    policy=policy,
                    settings=self.settings,
                    execution_scope=execution_scope,
                    trace=trace,
                )
                with trace.span("incremental.seed", category="incremental", bars=len(ohlcv)):
                    result = self._collect_incremental_result(incremental.seed(ohlcv))
                result.meta = {**result.meta, "securityMode": policy.mode}
                enforce_output_limits(result.output, policy)
                return finish(result, status="ok")

            # 1. Build data context
            ctx = PyneContext.from_ohlcv(
                ohlcv,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
            )

            # 2. Create runtime services bound to this context
            services = RuntimeServices(
                ctx=ctx,
                settings=self.settings,
                params=params,
                policy=policy,
                execution_scope=execution_scope,
                trace=trace,
            )

            # 3. Build script execution namespace
            script_globals = self._build_namespace(services)

            # 4. Execute
            with trace.span("script.execute", category="script"):
                with execution_timeout(policy.timeout_seconds):
                    exec(script, script_globals)  # noqa: S102

            # 5. Collect outputs
            with trace.span("output.collect", category="output"):
                result = self._collect_result(services.collector, services.input)
                enforce_output_limits(result.output, policy)
            result.meta = {**result.meta, "securityMode": policy.mode}
            if services.request.diagnostics:
                result.meta["requestDiagnostics"] = services.request.diagnostics
                for item in services.request.diagnostics:
                    trace.emit("request.complete", **item)
            strategy = result.output.get("strategy") or {}
            if strategy:
                trace.emit(
                    "strategy.complete",
                    orders=len(strategy.get("orders") or []),
                    closedTrades=len(strategy.get("closedtrades") or []),
                    position=(strategy.get("position") or {}).get("size"),
                )
            return finish(result, status="ok")

        except SyntaxError as exc:
            return finish(PyneResult(
                ok=False,
                code="PYNE_SYNTAX_ERROR",
                error=str(exc.msg or exc),
                line=exc.lineno,
                column=exc.offset,
                hint=error_hint("PYNE_SYNTAX_ERROR"),
            ), status="error")

        except PyneTimeoutError as exc:
            return finish(PyneResult(
                ok=False,
                code="PYNE_TIMEOUT",
                error=str(exc),
                hint=error_hint("PYNE_TIMEOUT"),
            ), status="error")
        except PyneSecurityError as exc:
            message = str(exc)
            code = classify_security_error(message)
            return finish(
                PyneResult(ok=False, code=code, error=message, hint=error_hint(code)),
                status="error",
            )
        except PyneRequestError as exc:
            code = exc.code
            context = (
                {"requestProviderCategory": exc.category}
                if exc.category
                else {}
            )
            if exc.request_context:
                context["requestProviderRequest"] = exc.request_context
            return finish(PyneResult(
                ok=False,
                code=code,
                error=str(exc),
                hint=error_hint(code),
                error_context=context,
            ), status="error")
        except PyneInputError as exc:
            code = exc.code
            return finish(
                PyneResult(ok=False, code=code, error=str(exc), hint=error_hint(code)),
                status="error",
            )
        except PyneOhlcvError as exc:
            return finish(PyneResult(
                ok=False,
                code="PYNE_INVALID_OHLCV",
                error=str(exc),
                hint=error_hint("PYNE_INVALID_OHLCV"),
            ), status="error")
        except Exception as exc:
            error_msg = f"Script error: {exc}"
            return finish(PyneResult(
                ok=False,
                code="PYNE_RUNTIME_ERROR",
                error=error_msg,
                hint=error_hint("PYNE_RUNTIME_ERROR"),
            ), status="error")

    @staticmethod
    def _finalize_trace(
        result: PyneResult,
        trace: PyneTraceRecorder,
        *,
        status: str,
    ) -> PyneResult:
        trace.emit(
            "execution.complete",
            status=status,
            code=result.code,
            outputKeys=sorted(result.output),
            lineCount=len(result.lines),
        )
        snapshot = trace.snapshot()
        if snapshot is not None:
            result.meta = {**result.meta, "trace": snapshot}
        return result

    def _collect_incremental_result(self, result: IncrementalPyneResult) -> PyneResult:
        return PyneResult(
            ok=result.ok,
            error=result.error,
            code=result.code,
            line=result.line,
            column=result.column,
            hint=result.hint,
            lines=result.lines,
            output=result.output,
            param_schema=result.param_schema,
            meta=result.meta,
        )

    def _build_namespace(
        self,
        services: RuntimeServices,
    ) -> dict[str, Any]:
        """Build the global namespace injected into user scripts."""
        return build_script_namespace(services)

    def _collect_result(
        self,
        collector: OutputCollector,
        input_mod: InputModule,
    ) -> PyneResult:
        """Collect all outputs from the execution into a PyneResult."""
        output = collector.to_dict()

        # Build flat lines list for backward compatibility
        # The frontend expects [{name, color, type, pane, data}, ...]
        flat_lines: list[dict[str, Any]] = []

        for line in collector.lines:
            entry: dict[str, Any] = {
                "name": line.get("title", ""),
                "color": line.get("color", "#f59e0b"),
                "type": "line",
                "pane": line.get("pane", "main"),
                "lineWidth": line.get("linewidth", 2),
                "lineStyle": _style_to_int(line.get("style", "solid")),
                "data": line.get("data", []),
            }
            # Include plot id for fill() cross-referencing
            if "id" in line:
                entry["id"] = line["id"]
            # Per-bar color flag
            if line.get("per_bar_color"):
                entry["per_bar_color"] = True
            flat_lines.append(entry)

        for hist in collector.histograms:
            flat_lines.append({
                "name": hist.get("title", ""),
                "color": hist.get("color_up", "#26a69a"),
                "type": "histogram",
                "pane": hist.get("pane", "separate"),
                "lineWidth": 2,
                "lineStyle": 0,
                "data": hist.get("data", []),
            })

        return PyneResult(
            ok=True,
            error=None,
            lines=flat_lines,
            output=output,
            param_schema=input_mod.schema,
            meta=collector.indicator_meta,
        )


def _style_to_int(style: str) -> int:
    """Convert line style string to lightweight-charts integer."""
    if isinstance(style, int):
        return style
    mapping = {
        "solid": 0,
        "line": 0,
        "dashed": 2,
        "dotted": 1,
    }
    return mapping.get(style, 0)
