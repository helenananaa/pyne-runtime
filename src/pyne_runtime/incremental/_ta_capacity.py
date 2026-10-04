"""One window-capacity contract for TA admission and restored state validation."""
from __future__ import annotations

import math
from collections import deque
from types import SimpleNamespace
from typing import Any


def window_capacity(kind: str, *, period: Any = None, left: Any = None,
                    right: Any = None, occurrence: Any = None) -> int:
    if kind == "pivot":
        return max(int(left), 0) + max(int(right), 0) + 1
    if kind == "occurrence":
        return max(int(occurrence), 0) + 1
    size = max(int(period), 1)
    if kind == "double":
        return size * 2
    if kind == "change":
        return size + 1
    if kind == "hma":
        return max(int(size / 2), 1) + size + max(int(math.sqrt(size)), 1)
    if kind == "period":
        return size
    raise ValueError(f"Unknown TA window capacity: {kind}")


def _positive_period(helper: Any) -> int:
    value = helper.period
    if type(value) is not int or value < 1:
        raise ValueError("Incremental snapshot TA period is invalid")
    return value


def _check_buffer(value: Any, capacity: int, *, maxlen: int | None = None) -> None:
    if type(value) is not deque or len(value) > capacity or value.maxlen != maxlen:
        raise ValueError("Incremental snapshot TA window storage is invalid")


def _check_period_buffers(helper: Any, ta: Any) -> None:
    period = _positive_period(helper)
    if type(helper) is ta._StepVWMA:
        _check_buffer(helper.products, period)
        _check_buffer(helper.weights, period)
    else:
        bounded = type(helper) in {ta._StepALMA, ta._StepDev}
        _check_buffer(helper.window, period, maxlen=period if bounded else None)
        if type(helper) is ta._StepALMA and (type(helper.weights) is not tuple or len(helper.weights) != period):
            raise ValueError("Incremental snapshot TA ALMA weights are invalid")


def ta_reserved_window_sizes(namespace: Any) -> tuple[int, ...]:
    # The owning namespace supplies its exact built-in types. The utility never
    # imports its owner, keeping capacity validation a one-way dependency.
    ta = SimpleNamespace(**namespace._capacity_types)

    helpers = namespace._helpers
    if type(helpers) is not dict:
        raise ValueError("Incremental snapshot TA helper registry is invalid")
    period_types = {ta._StepSMA, ta._StepWMA, ta._StepVWMA, ta._StepVariance,
                    ta._StepStdev, ta._StepExtremeBars, ta._StepALMA, ta._StepDev,
                    ta._StepBOLL, ta._StepBB, ta._StepMonotonic, ta._StepCCI}
    scalar_types = {ta._StepEMA, ta._StepRMA, ta._StepTrueRange, ta._StepCum,
                    ta._StepMACD, ta._StepRSI, ta._StepATR, ta._StepBarsSince,
                    ta._StepCross, ta._StepVWAP, ta._StepDMI, ta._StepADX,
                    ta._StepSupertrend, ta._StepPivotPointLevels}
    sizes = []
    for name, helper in helpers.items():
        if type(name) is not str:
            raise ValueError("Incremental snapshot TA helper key is invalid")
        kind = type(helper)
        if kind in period_types:
            size = window_capacity("period", period=_positive_period(helper))
            _check_period_buffers(helper, ta)
        elif kind is ta._StepChange:
            size = window_capacity("change", period=_positive_period(helper))
            _check_buffer(helper.window, size, maxlen=size)
        elif kind is ta._StepMFI:
            size = window_capacity("double", period=_positive_period(helper))
            _check_buffer(helper.positive, helper.period)
            _check_buffer(helper.negative, helper.period)
        elif kind is ta._StepStoch:
            if type(helper.highest) is not ta._StepMonotonic or type(helper.lowest) is not ta._StepMonotonic:
                raise ValueError("Incremental snapshot TA stochastic helper type is invalid")
            period = _positive_period(helper.highest)
            if _positive_period(helper.lowest) != period:
                raise ValueError("Incremental snapshot TA stochastic periods are inconsistent")
            size = window_capacity("double", period=period)
            _check_period_buffers(helper.highest, ta)
            _check_period_buffers(helper.lowest, ta)
        elif kind is ta._StepHMA:
            if any(type(item) is not ta._StepWMA for item in (helper.fast, helper.slow, helper.result)):
                raise ValueError("Incremental snapshot TA HMA helper type is invalid")
            period = _positive_period(helper)
            expected = (max(int(period / 2), 1), period, max(int(math.sqrt(period)), 1))
            actual = tuple(_positive_period(item) for item in (helper.fast, helper.slow, helper.result))
            if actual != expected:
                raise ValueError("Incremental snapshot TA HMA periods are inconsistent")
            size = window_capacity("hma", period=period)
            for item in (helper.fast, helper.slow, helper.result):
                _check_period_buffers(item, ta)
        elif kind is ta._StepPivot:
            if any(type(value) is not int or value < 0 for value in (helper.left, helper.right)):
                raise ValueError("Incremental snapshot TA pivot flanks are invalid")
            size = window_capacity("pivot", left=helper.left, right=helper.right)
            if helper.window_size != size:
                raise ValueError("Incremental snapshot TA pivot capacity is inconsistent")
            _check_buffer(helper.pending, helper.right)
            if type(helper.segments) is not deque or len(helper.segments) > helper.right + 1:
                raise ValueError("Incremental snapshot TA pivot segments are invalid")
            candidate_count = 0
            for segment in helper.segments:
                if type(segment) is not list or len(segment) != 3:
                    raise ValueError("Incremental snapshot TA pivot segment is invalid")
                _check_buffer(segment[2], size)
                candidate_count += len(segment[2])
            if candidate_count > size:
                raise ValueError("Incremental snapshot TA pivot retained candidates are invalid")
        elif kind is ta._StepValueWhen:
            if type(helper.occurrence) is not int or helper.occurrence < 0:
                raise ValueError("Incremental snapshot TA occurrence is invalid")
            size = window_capacity("occurrence", occurrence=helper.occurrence)
            _check_buffer(helper.values, size, maxlen=size)
        elif kind in {ta._StepSWMA, ta._StepSAR}:
            size = 4
            if kind is ta._StepSWMA:
                _check_buffer(helper.window, 4, maxlen=4)
            else:
                _check_buffer(helper.previous_highs, 2, maxlen=2)
                _check_buffer(helper.previous_lows, 2, maxlen=2)
        elif kind in scalar_types:
            children = ()
            if kind is ta._StepMACD:
                children = ((helper.fast, ta._StepEMA), (helper.slow, ta._StepEMA), (helper.signal, ta._StepEMA))
            elif kind in {ta._StepDMI, ta._StepADX}:
                children = ((helper.atr, ta._StepATR), (helper.plus, ta._StepRMA),
                            (helper.minus, ta._StepRMA), (helper.adx, ta._StepRMA))
            elif kind is ta._StepSupertrend:
                children = ((helper.atr, ta._StepATR),)
            for child, expected_type in children:
                if type(child) is not expected_type:
                    raise ValueError("Incremental snapshot TA scalar helper type is invalid")
                _positive_period(child)
            continue
        else:
            raise ValueError("Incremental snapshot TA helper type is invalid")
        sizes.append(size)
    return tuple(sizes)
