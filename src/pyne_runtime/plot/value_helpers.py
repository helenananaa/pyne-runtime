"""Value normalization helpers shared by plot function factories."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..series import PyneSeries
from ..state import PyneVar
from ..values import is_na_value
from .collector import OutputCollector


class PlotValueAdapter:
    """Normalize batch plot inputs against one output collector."""

    def __init__(self, collector: OutputCollector) -> None:
        self._collector = collector

    def from_data(self, data: PyneSeries | np.ndarray | list | Any) -> list:
        if isinstance(data, PyneVar):
            data = data.get()
        if isinstance(data, PyneSeries):
            return data.to_numpy().tolist()
        if isinstance(data, np.ndarray):
            return data.tolist()
        if isinstance(data, list):
            return data
        if hasattr(data, "to_numpy"):
            return np.asarray(data.to_numpy()).tolist()
        return [data] * len(self._collector.times)

    @staticmethod
    def color_for_index(color_data: Any, idx: int, timestamp: int) -> str | None:
        if color_data is None:
            return None
        if isinstance(color_data, PyneVar):
            color_data = color_data.get()
        if isinstance(color_data, PyneSeries):
            color_data = color_data.to_numpy()
        if isinstance(color_data, np.ndarray):
            if color_data.ndim == 0:
                return serialize_color(color_data.item())
            if idx < len(color_data):
                return serialize_color(color_data[idx])
            return None
        if isinstance(color_data, list):
            if idx >= len(color_data):
                return None
            item = color_data[idx]
            if isinstance(item, dict):
                if item.get("time") == timestamp or "time" not in item:
                    return serialize_color(item.get("color"))
                return None
            return serialize_color(item)
        return serialize_color(color_data)

    @staticmethod
    def is_valid(value: Any) -> bool:
        return not is_na_value(value)

    @staticmethod
    def condition_is_true(value: Any) -> bool:
        return False if is_na_value(value) else bool(value)

    @staticmethod
    def scalar(value: Any) -> Any:
        if isinstance(value, PyneVar):
            value = value.get()
        if isinstance(value, PyneSeries):
            values = value.to_numpy().tolist()
        elif isinstance(value, np.ndarray):
            values = value.tolist()
        elif isinstance(value, list):
            values = value
        else:
            return serialize_scalar(value)

        for item in reversed(values):
            if not is_na_value(item):
                return serialize_scalar(item)
        return None


def serialize_color(value: Any) -> str | None:
    """Serialize one plot color; missing and non-scalar values become None."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict, np.ndarray, PyneSeries, PyneVar)):
        return None
    if isinstance(value, np.generic):
        value = value.item()
        if isinstance(value, (list, tuple, dict)):
            return None
    if is_na_value(value) or value == "":
        return None
    text = str(value)
    if not text or text.lower() == "nan":
        return None
    return text


def is_color_series(value: Any) -> bool:
    if isinstance(value, PyneVar):
        value = value.get()
    return isinstance(value, (np.ndarray, PyneSeries, list, tuple))


def collector_color(value: Any, *, default: str = "#f59e0b") -> str:
    """Collector-level color: classify scalar vs series, then serialize_color."""
    if isinstance(value, PyneVar):
        value = value.get()
    if isinstance(value, PyneSeries):
        value = value.to_numpy()
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return serialize_color(value.item()) or default
        for item in value:
            text = serialize_color(item)
            if text:
                return text
        return default
    if isinstance(value, (list, tuple)):
        for item in value:
            text = (
                serialize_color(item.get("color"))
                if isinstance(item, dict)
                else serialize_color(item)
            )
            if text:
                return text
        return default
    return serialize_color(value) or default


def serialize_scalar(value: Any) -> Any:
    if is_na_value(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return round(value, 8)
    return value


def display_options(
    *,
    display: str | None,
    format: str | None,
    precision: int | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if display is not None:
        options["display"] = str(display)
    if format is not None:
        options["format"] = str(format)
    if precision is not None:
        options["precision"] = int(precision)
    return options
