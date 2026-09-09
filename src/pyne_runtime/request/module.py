"""Pine-like request namespace facade."""
from __future__ import annotations

import math
from typing import Any, Callable

from ..context import PyneContext
from ..series import PyneSeries
from ..ta import TaModule
from .alignment import (
    _GAPS_ALIASES,
    _LOOKAHEAD_ALIASES,
    _align_request_values,
    _normalize_request_option,
)
from .errors import (
    PyneInvalidSymbolError,
    PyneProviderError,
    PyneRequestError,
    RequestProviderErrorCategory,
)
from .eval import (
    RequestEvalContext,
    RequestValues,
    _field_expression_history_bars,
    _values_from_expression_result,
    _values_from_field_expression,
)
from .lower_tf import LowerTimeframeSeries, _group_lower_timeframe_values
from .provider import (
    REQUEST_SECURITY_API,
    REQUEST_SECURITY_CAPABILITY_ALIASES,
    REQUEST_SECURITY_LOWER_TF_API,
    REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
    DataProvider,
    _default_request_metadata,
    _provider_supports,
    _request_metadata,
)


_ADAPTIVE_WIDENING_FACTOR = 4
_MAX_ADAPTIVE_WIDENINGS = 6


class RequestModule:
    """Pine-like ``request`` namespace bound to one execution context."""

    def __init__(
        self,
        context: PyneContext,
        provider: DataProvider | None = None,
    ) -> None:
        self._context = context
        self._provider = provider
        self._evaluating = False
        self._requested_context_cache: dict[
            tuple[str, str, int, int],
            tuple[list[dict[str, Any]], PyneContext, int, int, bool],
        ] = {}
        self._requested_context_aliases: dict[
            tuple[str, str, int, int],
            tuple[str, str, int, int],
        ] = {}
        self._diagnostics: list[dict[str, Any]] = []

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        """Return host-facing diagnostics for request.* calls in this run."""
        return [dict(item) for item in self._diagnostics]

    def security(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        *,
        gaps: str = "off",
        lookahead: str = "off",
        ignore_invalid_symbol: bool = False,
    ) -> PyneSeries | tuple[PyneSeries, ...]:
        """Return a requested symbol/timeframe field aligned to chart bars.

        Field-like expressions such as ``close``, ``close[1]``, or ``"close"``
        remain supported. Callable thunks are evaluated in the requested
        symbol/timeframe context.
        """
        symbol_text = str(symbol)
        timeframe_text = str(timeframe)
        start, end = _request_provider_window(
            self._context,
            timeframe_text,
            warmup_bars=self._context.bar_count,
        )
        request_context = self._request_context_payload(
            REQUEST_SECURITY_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        if self._provider is None:
            raise PyneRequestError(
                "request.security() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category=RequestProviderErrorCategory.MISSING_PROVIDER,
                request_context=request_context,
            )
        try:
            supports_request = _provider_supports(
                self._provider,
                REQUEST_SECURITY_CAPABILITY_ALIASES,
            )
        except PyneRequestError as exc:
            raise exc.with_request_context(**request_context) from exc
        if not supports_request:
            raise PyneRequestError(
                "request.security() requires provider capability 'request.security'",
                code="PYNE_UNSUPPORTED_FEATURE",
                category=RequestProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                request_context=request_context,
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        normalized_gaps = _normalize_request_option(
            gaps,
            name="gaps",
            aliases=_GAPS_ALIASES,
        )
        normalized_lookahead = _normalize_request_option(
            lookahead,
            name="lookahead",
            aliases=_LOOKAHEAD_ALIASES,
        )

        direct_history = 0 if callable(expression) else _field_expression_history_bars(expression)
        warmup_bars = max(self._context.bar_count, direct_history)
        start, end = _request_provider_window(
            self._context,
            timeframe_text,
            warmup_bars=warmup_bars,
        )

        (
            requested,
            requested_ctx,
            cache_hit,
            ignored_invalid_symbol,
            start,
            end,
        ) = self._requested_context(
            REQUEST_SECURITY_API,
            symbol_text,
            timeframe_text,
            start,
            end,
            chart_start=int(self._context.times[0]),
            minimum_prechart_bars=warmup_bars,
            ignore_invalid_symbol=ignore_invalid_symbol,
        )
        request_context = self._request_context_payload(
            REQUEST_SECURITY_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        self._record_diagnostic(
            api=REQUEST_SECURITY_API,
            symbol=symbol_text,
            timeframe=timeframe_text,
            start=start,
            end=end,
            requested=requested,
            cache_hit=cache_hit,
            ignore_invalid_symbol=ignore_invalid_symbol,
            ignored_invalid_symbol=ignored_invalid_symbol,
        )
        if not requested:
            return self._empty_security_result(
                symbol=symbol_text,
                timeframe=timeframe_text,
                expression=expression,
                requested_ctx=requested_ctx,
                request_context=request_context,
                gaps=normalized_gaps,
                lookahead=normalized_lookahead,
            )

        requested_times = requested_ctx.times
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol_text,
                timeframe=timeframe_text,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _align_request_values(
            symbol=symbol_text,
            timeframe=timeframe_text,
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_times,
            requested_values=requested_values,
            gaps=normalized_gaps,
            lookahead=normalized_lookahead,
            chart_step_hint=_timeframe_seconds_from_text(self._context.timeframe.period),
            requested_step_hint=_timeframe_seconds_from_text(timeframe_text),
        )

    def security_lower_tf(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        *,
        ignore_invalid_symbol: bool = False,
        ignore_invalid_timeframe: bool = False,
    ) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
        """Return lower-timeframe arrays grouped by chart bar.

        The provider supplies lower-timeframe OHLCV. Pyne evaluates the
        expression in that requested context, then groups requested values into
        ``[chart_time, next_chart_time)`` buckets.
        """
        symbol_text = str(symbol)
        timeframe_text = str(timeframe)
        start, end = _request_provider_window(
            self._context,
            timeframe_text,
            warmup_bars=self._context.bar_count,
        )
        request_context = self._request_context_payload(
            REQUEST_SECURITY_LOWER_TF_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        if self._provider is None:
            raise PyneRequestError(
                "request.security_lower_tf() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category=RequestProviderErrorCategory.MISSING_PROVIDER,
                request_context=request_context,
            )
        try:
            supports_request = _provider_supports(
                self._provider,
                REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
            )
        except PyneRequestError as exc:
            raise exc.with_request_context(**request_context) from exc
        if not supports_request:
            raise PyneRequestError(
                "request.security_lower_tf() requires provider capability "
                "'request.security_lower_tf'",
                code="PYNE_UNSUPPORTED_FEATURE",
                category=RequestProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                request_context=request_context,
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security_lower_tf() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        ignored_invalid_timeframe = False
        if ignore_invalid_timeframe and _is_invalid_lower_timeframe(
            timeframe_text,
            self._context.times,
        ):
            ignored_invalid_timeframe = True
            requested_ctx = self._empty_requested_context(symbol_text, timeframe_text)
            self._record_diagnostic(
                api=REQUEST_SECURITY_LOWER_TF_API,
                symbol=symbol_text,
                timeframe=timeframe_text,
                start=start,
                end=end,
                requested=[],
                cache_hit=False,
                ignore_invalid_symbol=ignore_invalid_symbol,
                ignored_invalid_symbol=False,
                ignored_invalid_timeframe=True,
            )
            return self._empty_lower_tf_result(
                symbol=symbol_text,
                timeframe=timeframe_text,
                expression=expression,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )

        direct_history = 0 if callable(expression) else _field_expression_history_bars(expression)
        warmup_bars = max(self._context.bar_count, direct_history)
        start, end = _request_provider_window(
            self._context,
            timeframe_text,
            warmup_bars=warmup_bars,
        )

        (
            requested,
            requested_ctx,
            cache_hit,
            ignored_invalid_symbol,
            start,
            end,
        ) = self._requested_context(
            REQUEST_SECURITY_LOWER_TF_API,
            symbol_text,
            timeframe_text,
            start,
            end,
            chart_start=int(self._context.times[0]),
            minimum_prechart_bars=warmup_bars,
            ignore_invalid_symbol=ignore_invalid_symbol,
        )
        request_context = self._request_context_payload(
            REQUEST_SECURITY_LOWER_TF_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        self._record_diagnostic(
            api=REQUEST_SECURITY_LOWER_TF_API,
            symbol=symbol_text,
            timeframe=timeframe_text,
            start=start,
            end=end,
            requested=requested,
            cache_hit=cache_hit,
            ignore_invalid_symbol=ignore_invalid_symbol,
            ignored_invalid_symbol=ignored_invalid_symbol,
            ignored_invalid_timeframe=ignored_invalid_timeframe,
        )
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol_text,
                timeframe=timeframe_text,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _group_lower_timeframe_values(
            symbol=symbol_text,
            timeframe=timeframe_text,
            expression_name=expression_name,
            chart_times=self._context.times,
            chart_end=end,
            requested_times=requested_ctx.times,
            requested_values=requested_values,
        )

    def _requested_context(
        self,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        *,
        chart_start: int,
        minimum_prechart_bars: int,
        ignore_invalid_symbol: bool,
    ) -> tuple[list[dict[str, Any]], PyneContext, bool, bool, int, int]:
        if self._provider is None:
            request_context = self._request_context_payload(api, symbol, timeframe, start, end)
            raise PyneRequestError(
                "request context requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category=RequestProviderErrorCategory.MISSING_PROVIDER,
                request_context=request_context,
            )

        initial_key = (symbol, timeframe, int(start), int(end))
        cache_key = initial_key
        seen_aliases: set[tuple[str, str, int, int]] = set()
        while cache_key not in seen_aliases:
            seen_aliases.add(cache_key)
            aliased_key = self._requested_context_aliases.get(cache_key)
            if aliased_key is None or aliased_key == cache_key:
                break
            cache_key = aliased_key
        cached = self._requested_context_cache.get(cache_key)
        widenings = 0
        if cached is not None:
            (
                requested,
                requested_ctx,
                cached_prechart_bars,
                attempted_requirement,
                exhausted,
            ) = cached
            cached_span = chart_start - cache_key[2]
            if (
                not requested
                or cached_prechart_bars >= minimum_prechart_bars
                or cache_key[2] <= 0
                or cached_span <= 0
                or (exhausted and minimum_prechart_bars <= attempted_requirement)
            ):
                return requested, requested_ctx, True, False, cache_key[2], cache_key[3]
            start = max(
                0,
                chart_start - cached_span * _ADAPTIVE_WIDENING_FACTOR,
            )
            widenings = 1

        current_start = int(start)
        current_end = int(end)
        ignored_invalid_symbol = False
        exhausted = False
        while True:
            request_context = self._request_context_payload(
                api,
                symbol,
                timeframe,
                current_start,
                current_end,
            )
            try:
                requested = self._provider.get_ohlcv(
                    symbol,
                    timeframe,
                    current_start,
                    current_end,
                )
            except PyneInvalidSymbolError as exc:
                if ignore_invalid_symbol:
                    requested = []
                    ignored_invalid_symbol = True
                else:
                    raise PyneRequestError(
                        f"Invalid symbol for request.security(): {symbol}",
                        code="PYNE_INVALID_SYMBOL",
                        category=RequestProviderErrorCategory.INVALID_SYMBOL,
                        request_context=request_context,
                    ) from exc
            except PyneRequestError as exc:
                raise exc.with_request_context(**request_context) from exc
            except PyneProviderError as exc:
                raise PyneRequestError(
                    str(exc),
                    code=exc.code,
                    category=exc.category,
                    request_context=request_context,
                ) from exc
            except Exception as exc:
                raise PyneRequestError(
                    f"request data provider failed: {exc}",
                    code="PYNE_RUNTIME_ERROR",
                    category=RequestProviderErrorCategory.PROVIDER_FAILURE,
                    request_context=request_context,
                ) from exc

            if not isinstance(requested, list):
                raise PyneRequestError(
                    "request data provider must return a list of OHLCV bars",
                    code="PYNE_RUNTIME_ERROR",
                    category=RequestProviderErrorCategory.INVALID_RETURN_TYPE,
                    request_context=request_context,
                )
            for index, item in enumerate(requested):
                if not isinstance(item, dict):
                    raise PyneRequestError(
                        f"request data provider returned non-mapping bar at row {index}",
                        code="PYNE_RUNTIME_ERROR",
                        category=RequestProviderErrorCategory.INVALID_BAR_SHAPE,
                        request_context=request_context,
                    )
                if "time" not in item:
                    raise PyneRequestError(
                        f"request data provider returned OHLCV bar without time at row {index}",
                        code="PYNE_RUNTIME_ERROR",
                        category=RequestProviderErrorCategory.INVALID_BAR_SHAPE,
                        request_context=request_context,
                    )
            requested = sorted(requested, key=lambda item: int(item.get("time", 0)))
            prechart_bars = sum(
                1 for item in requested if int(item.get("time", 0)) < chart_start
            )
            if (
                ignored_invalid_symbol
                or not requested
                or prechart_bars >= minimum_prechart_bars
                or widenings >= _MAX_ADAPTIVE_WIDENINGS
                or current_start <= 0
            ):
                exhausted = (
                    bool(requested)
                    and not ignored_invalid_symbol
                    and prechart_bars < minimum_prechart_bars
                    and (
                        widenings >= _MAX_ADAPTIVE_WIDENINGS
                        or current_start <= 0
                    )
                )
                break
            current_span = chart_start - current_start
            if current_span <= 0:
                exhausted = True
                break
            next_start = max(
                0,
                chart_start - current_span * _ADAPTIVE_WIDENING_FACTOR,
            )
            if next_start >= current_start:
                exhausted = True
                break
            current_start = next_start
            widenings += 1

        request_context = self._request_context_payload(
            api,
            symbol,
            timeframe,
            current_start,
            current_end,
        )
        if ignored_invalid_symbol:
            request_metadata = _default_request_metadata(symbol, timeframe)
        else:
            try:
                request_metadata = _request_metadata(self._provider, symbol, timeframe)
            except PyneRequestError as exc:
                raise exc.with_request_context(**request_context) from exc
        try:
            requested_ctx = PyneContext.from_ohlcv(
                requested,
                syminfo=request_metadata["syminfo"],
                timeframe=request_metadata["timeframe"],
                session=request_metadata["session"],
                allow_empty=True,
                allow_missing_values=True,
                require_unique_times=False,
            )
        except (TypeError, ValueError) as exc:
            raise PyneRequestError(
                f"request data provider returned invalid OHLCV: {exc}",
                code="PYNE_RUNTIME_ERROR",
                category=RequestProviderErrorCategory.INVALID_BAR_SHAPE,
                request_context=request_context,
            ) from exc
        cached = (
            requested,
            requested_ctx,
            prechart_bars,
            minimum_prechart_bars,
            exhausted,
        )
        if not ignored_invalid_symbol:
            final_key = (symbol, timeframe, current_start, current_end)
            self._requested_context_cache[final_key] = cached
            if initial_key != final_key:
                self._requested_context_aliases[initial_key] = final_key
        return (
            requested,
            requested_ctx,
            False,
            ignored_invalid_symbol,
            current_start,
            current_end,
        )

    def _record_diagnostic(
        self,
        *,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        requested: list[dict[str, Any]],
        cache_hit: bool,
        ignore_invalid_symbol: bool,
        ignored_invalid_symbol: bool,
        ignored_invalid_timeframe: bool = False,
    ) -> None:
        status = "ok"
        if ignored_invalid_symbol:
            status = "ignoredInvalidSymbol"
        elif ignored_invalid_timeframe:
            status = "ignoredInvalidTimeframe"
        self._diagnostics.append({
            "api": api,
            "symbol": symbol,
            "timeframe": timeframe,
            "start": int(start),
            "end": int(end),
            "bars": len(requested),
            "cacheHit": cache_hit,
            "ignoreInvalidSymbol": ignore_invalid_symbol,
            **({"ignoreInvalidTimeframe": True} if ignored_invalid_timeframe else {}),
            "status": status,
        })

    def _request_context_payload(
        self,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> dict[str, Any]:
        return {
            "api": api,
            "symbol": symbol,
            "timeframe": timeframe,
            "start": int(start),
            "end": int(end),
        }

    def _evaluate_expression_thunk(
        self,
        expression: Callable[[RequestEvalContext], Any],
        *,
        symbol: str,
        timeframe: str,
        requested_ctx: PyneContext,
        request_context: dict[str, Any],
    ) -> tuple[RequestValues, str]:
        requested_ta = TaModule(requested_ctx)
        eval_ctx = RequestEvalContext(
            symbol=symbol,
            timeframe=timeframe,
            context=requested_ctx,
            ta=requested_ta,
        )
        try:
            self._evaluating = True
            result = expression(eval_ctx)
        except PyneRequestError:
            raise
        except Exception as exc:
            raise PyneRequestError(
                f"request.security() expression failed: {exc}",
                code="PYNE_RUNTIME_ERROR",
                category=RequestProviderErrorCategory.EXPRESSION_FAILURE,
                request_context=request_context,
            ) from exc
        finally:
            self._evaluating = False

        return _values_from_expression_result(result, requested_ctx), "expression"

    def _empty_requested_context(self, symbol: str, timeframe: str) -> PyneContext:
        request_metadata = _default_request_metadata(symbol, timeframe)
        return PyneContext.from_ohlcv(
            [],
            syminfo=request_metadata["syminfo"],
            timeframe=request_metadata["timeframe"],
            session=request_metadata["session"],
            allow_empty=True,
            require_unique_times=False,
        )

    def _empty_lower_tf_result(
        self,
        *,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        requested_ctx: PyneContext,
        request_context: dict[str, Any],
    ) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol,
                timeframe=timeframe,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                [],
                requested_ctx,
            )
        return _group_lower_timeframe_values(
            symbol=symbol,
            timeframe=timeframe,
            expression_name=expression_name,
            chart_times=self._context.times,
            chart_end=_chart_close_boundary(self._context),
            requested_times=requested_ctx.times,
            requested_values=requested_values,
        )

    def _empty_security_result(
        self,
        *,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        requested_ctx: PyneContext,
        request_context: dict[str, Any],
        gaps: str,
        lookahead: str,
    ) -> PyneSeries | tuple[PyneSeries, ...]:
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol,
                timeframe=timeframe,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                [],
                requested_ctx,
            )
        return _align_request_values(
            symbol=symbol,
            timeframe=timeframe,
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_ctx.times,
            requested_values=requested_values,
            gaps=gaps,
            lookahead=lookahead,
        )


def _is_invalid_lower_timeframe(timeframe: str, chart_times: list[int]) -> bool:
    requested_seconds = _timeframe_seconds_from_text(timeframe)
    chart_seconds = _chart_seconds_from_times(chart_times)
    if requested_seconds is None or chart_seconds is None:
        return False
    return requested_seconds >= chart_seconds


def _chart_seconds_from_times(chart_times: list[int]) -> int | None:
    if len(chart_times) < 2:
        return None
    intervals = [
        int(later) - int(earlier)
        for earlier, later in zip(chart_times, chart_times[1:])
        if int(later) > int(earlier)
    ]
    if not intervals:
        return None
    interval = min(intervals)
    return interval if interval >= 60 else None


def _request_provider_window(
    context: PyneContext,
    timeframe: str,
    *,
    warmup_bars: int,
) -> tuple[int, int]:
    """Return a bounded provider window with requested-context warmup history."""
    chart_start = int(context.times[0])
    chart_step = _last_positive_chart_step(context.times)
    requested_step = _timeframe_seconds_from_text(timeframe) or chart_step
    if requested_step is None:
        start = chart_start
    else:
        start = max(0, chart_start - max(int(warmup_bars), 0) * requested_step)
    return start, _chart_close_boundary(context, chart_step=chart_step)


def _chart_close_boundary(context: PyneContext, *, chart_step: int | None = None) -> int:
    """Return the exclusive close boundary of the last chart bar."""
    last_time = int(context.times[-1])
    time_close_values = context.time_close.to_numpy()
    if len(time_close_values):
        last_close = float(time_close_values[-1])
        explicit = bool(context._time_close_explicit and context._time_close_explicit[-1])
        if explicit and math.isfinite(last_close) and last_close > last_time:
            return int(last_close)

    step = chart_step if chart_step is not None else _last_positive_chart_step(context.times)
    if step is not None:
        return last_time + step
    if len(time_close_values):
        last_close = float(time_close_values[-1])
        if math.isfinite(last_close) and last_close > last_time:
            return int(last_close)
    return last_time


def _last_positive_chart_step(chart_times: list[int]) -> int | None:
    for index in range(len(chart_times) - 1, 0, -1):
        interval = int(chart_times[index]) - int(chart_times[index - 1])
        if interval > 0:
            return interval
    return None


def _timeframe_seconds_from_text(timeframe: str) -> int | None:
    from ..metadata import TimeframeInfo

    value = str(timeframe).strip()
    if not value:
        return None
    try:
        return int(TimeframeInfo.from_value(value).in_seconds())
    except (TypeError, ValueError):
        return None
