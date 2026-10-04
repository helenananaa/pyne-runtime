"""Current-bar projection for validated fields, with ordinary thunk fallback."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..series import PyneSeries
from ._indexed import LazyRequestedContext, SequenceWindow
from .alignment import _aligned_value, _infer_step
from .errors import PyneRequestError
from .eval import _field_value, _resolve_requested_field
from .lower_tf import _group_lower_timeframe_values


class _FieldValues(Sequence):
    def __init__(self, rows, field, offset):
        self.rows, self.field, self.offset = rows, field, offset

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [_FieldValues.__getitem__(self, i) for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return np.nan if index < self.offset else _field_value(self.rows[index - self.offset], self.field)


class _ShiftedTimes(Sequence):
    def __init__(self, times, shift):
        self.times, self.shift = times, shift

    def __len__(self):
        return len(self.times)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return SequenceWindow(self)[index]
        return self.times[index] + self.shift


def current_field_values(expression, requested, requested_ctx):
    """Return lazy field sequences only while no Python-visible context exists."""
    if not isinstance(requested_ctx, LazyRequestedContext) or requested_ctx.full_context is not None:
        return None
    # Preserve explicit floating error callbacks, exceptions and output, and
    # the eager helper's default overflow warnings on extreme valid prices.
    policy = np.geterr()
    if (requested.unsafe_derived or policy["under"] != "ignore"
            or any(value in {"raise", "call", "log", "print"} for value in policy.values())):
        return None
    items = expression if isinstance(expression, (tuple, list)) else (expression,)
    if (type(expression) not in (str, tuple, list)
            or any(type(item) is not str for item in items)):
        return None
    if not items:
        raise PyneRequestError("request.security() multi-return expression cannot be empty",
                               code="PYNE_UNSUPPORTED_FEATURE")
    try:
        resolved = [_resolve_requested_field(item) for item in items]
    except PyneRequestError:
        # A provider can mutate a list expression after its initial history
        # check. Let the ordinary helper retain its sequential error effects.
        return None
    if any(field == "time_close" for field, _ in resolved):
        return None
    requested_ctx.field_values_read = True
    if requested_ctx.field_error_policy is None:
        requested_ctx.field_error_policy = dict(policy)
    names = [field if offset <= 0 else f"{field}[{offset}]" for field, offset in resolved]
    values = [_FieldValues(requested, field, offset) for field, offset in resolved]
    return (tuple(values) if isinstance(expression, (tuple, list)) else values[0], ",".join(names))


def current_security_result(*, context, requested_ctx, requested_values, symbol, timeframe,
                            expression_name, gaps, lookahead, chart_step_hint, requested_step_hint,
                            requested_times=None):
    chart_times = context.times
    requested_times = requested_ctx.times if requested_times is None else requested_times
    chart_step = (chart_times.minimum_positive_step if hasattr(chart_times, "minimum_positive_step")
                  else _infer_step(chart_times)) or chart_step_hint
    if (isinstance(requested_ctx, LazyRequestedContext) and requested_ctx.full_context is None
            and requested_ctx.rows.fast_step_known):
        requested_step = requested_ctx.rows.minimum_positive_step or requested_step_hint
    else:
        requested_step = _infer_step(requested_times) or requested_step_hint
    shift = (requested_step - chart_step if chart_step is not None and requested_step is not None
             and requested_step > chart_step else 0)
    confirmation_times = _ShiftedTimes(requested_times, shift)

    def project(values, name):
        value = _aligned_value(chart_times[-1], requested_times, confirmation_times, values,
                               gaps=gaps, lookahead=lookahead)
        return PyneSeries(np.asarray([value], dtype=np.float64),
                          name=f"request.security({symbol},{timeframe},{name})")

    if isinstance(requested_values, tuple):
        return tuple(project(values, f"{expression_name}[{index}]")
                     for index, values in enumerate(requested_values))
    return project(requested_values, expression_name)


def current_lower_tf_result(*, context, requested_ctx, requested_values, symbol, timeframe,
                           expression_name, chart_end, max_group_size=None):
    return _group_lower_timeframe_values(
        symbol=symbol, timeframe=timeframe, expression_name=expression_name,
        chart_times=[context.times[-1]], chart_end=chart_end,
        requested_times=requested_ctx.times, requested_values=requested_values,
        max_group_size=max_group_size)
