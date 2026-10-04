"""Explicit output conversion boundaries detach mutable caller graphs."""
import json

import numpy as np
import pytest

from pyne_runtime import PyneResult
from pyne_runtime.plot import OutputCollector, create_plot_functions


def test_collector_export_is_detached_from_plots_metadata_objects_and_strategy():
    collector = OutputCollector([0, 10])
    functions = create_plot_functions(collector)
    functions["indicator"]("Snapshot", options={"labels": ["old"]})
    functions["plot"]([1, 2], "P")
    ref = functions["table"].new(columns=1, rows=1)
    functions["table"].cell(ref, 0, 0, "old")
    collector.strategy_position = {"details": [1]}
    collector.strategy_report = {"stats": {"values": [2]}}
    exported = collector.to_dict()
    exported["lines"][0]["data"][0]["value"] = 99
    exported["meta"]["options"]["labels"].append("new")
    exported["objects"]["tables"][0]["cells"][0]["text"] = "new"
    exported["strategy"]["position"]["details"].append(3)
    exported["strategy"]["stats"]["values"].append(4)
    original = collector.to_dict()
    assert original["lines"][0]["data"][0]["value"] == 1
    assert original["meta"]["options"]["labels"] == ["old"]
    assert original["objects"]["tables"][0]["cells"][0]["text"] == "old"
    assert original["strategy"]["position"]["details"] == [1]
    assert original["strategy"]["stats"]["values"] == [2]
    functions["plot"]([3, 4], "New")
    assert len(exported["lines"]) == 1


def test_result_import_export_and_get_series_detach_nested_values():
    source = dict(ok=True, lines=[dict(name="P", data=[dict(time=0, value=1)])],
                  output={"objects": {"tables": [{"cells": [{"text": "old"}]}]}},
                  meta={"labels": ["old"]}, param_schema=[{"options": [1]}])
    result = PyneResult.from_dict(source)
    source["lines"][0]["data"][0]["value"] = 99
    source["output"]["objects"]["tables"][0]["cells"][0]["text"] = "source edit"
    assert result.values("P") == [1]
    assert result.output["objects"]["tables"][0]["cells"][0]["text"] == "old"
    points = result.get_series("P")
    points[0]["value"] = 88
    exported = result.to_dict()
    exported["lines"][0]["data"][0]["value"] = 77
    exported["output"]["objects"]["tables"][0]["cells"][0]["text"] = "export edit"
    exported["meta"]["labels"].append("new")
    exported["param_schema"][0]["options"].append(2)
    assert result.values("P") == [1]
    assert result.output["objects"]["tables"][0]["cells"][0]["text"] == "old"
    assert result.meta == {"labels": ["old"]}
    assert result.param_schema == [{"options": [1]}]
    result.lines[0]["data"][0]["value"] = 3
    assert result.values("P") == [3]  # Direct fields remain ordinary mutable Python.
    assert json.loads(result.to_json())["lines"][0]["data"][0]["value"] == 3


def test_result_import_preserves_internal_sharing_and_ignores_unknown_fields():
    class Uncopyable:
        def __deepcopy__(self, memo):
            pytest.fail("Unknown result fields must remain ignored")

    points = [{"time": 0, "value": 1}]
    result = PyneResult.from_dict(dict(ok=True, lines=[{"name": "P", "data": points}],
                                     output={"points": points}, ignored=Uncopyable()))
    assert result.lines[0]["data"] is result.output["points"]
    assert result.lines[0]["data"] is not points


@pytest.mark.parametrize("size", [100, 10000])
def test_latest_reads_the_last_present_point_without_copying_history(size):
    class CountedPoints(list):
        reads = 0

        def __iter__(self):
            pytest.fail("latest() copied or iterated complete point history")

        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)

        def __reversed__(self):
            for index in range(len(self) - 1, -1, -1):
                yield self[index]

        def __deepcopy__(self, memo):
            pytest.fail("latest() deep-copied complete point history")

    points = CountedPoints([{"time": index, "value": index} for index in range(size)])
    points[-1] = {"time": size - 1, "value": None}
    result = PyneResult(lines=[{"name": "P", "data": points}])
    assert result.latest("P") == size - 2
    assert points.reads == 2


@pytest.mark.parametrize("value", [3.5, 2, True, np.nan])
def test_numpy_zero_dimensional_plots_match_scalar_broadcast(value):
    array_collector = OutputCollector([0, 10])
    scalar_collector = OutputCollector([0, 10])
    create_plot_functions(array_collector)["plot"](np.asarray(value), "P")
    create_plot_functions(scalar_collector)["plot"](value, "P")
    assert array_collector.to_dict() == scalar_collector.to_dict()


def test_numpy_zero_dimensional_drawing_coordinates_match_scalars():
    collector = OutputCollector([0, 10])
    line = create_plot_functions(collector)["line"]
    ref = line.new(np.asarray(0), np.asarray(1.), np.asarray(1), np.asarray(2.))
    line.set_xy1(ref, np.asarray(3), np.asarray(4.))
    assert line.get_x1(ref) == 3
    assert line.get_y1(ref) == 4.
    assert line.get_x2(ref) == 1
    assert line.get_y2(ref) == 2.
