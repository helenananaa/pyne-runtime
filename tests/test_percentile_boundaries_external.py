"""Native missing-order fixtures, prefix isolation and portable continuation."""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.ta import TaModule

FOLDER = Path(__file__).parent / "workloads"
CAPTURES = ("percentile_insertion_matrix", "percentile_missing_sort",
            "percentile_confirmation", "percentile_history_context", "percentile_state_holdout")


@pytest.mark.parametrize("name", CAPTURES)
@pytest.mark.parametrize("count", (1, 2, 4, 7, 13, 17, 19, 24, 32, 45, 58, 96))
def test_every_native_output_at_prefix_boundaries(name, count):
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text())
    rows = np.asarray([row["values"] for row in capture["rows"][:count]], dtype=float)
    module = TaModule()
    for column, title in enumerate(capture["columns"]):
        tokens = title.split()
        if tokens[0] not in ("Nearest", "Linear"):
            continue
        if len(tokens) == 2:
            source, period, percentage = "source", 4, float(tokens[1])
        elif len(tokens) == 3:
            source, period, percentage = tokens[1], 4, float(tokens[2])
        else:
            source, period, percentage = tokens[1], int(tokens[2]), float(tokens[3])
        function = (module.percentile_nearest_rank if tokens[0] == "Nearest"
                    else module.percentile_linear_interpolation)
        values = rows[:, capture["columns"].index(source)]
        original = values.copy()
        actual = function(values, period, percentage)
        np.testing.assert_array_equal(np.isnan(actual), np.isnan(rows[:, column]), err_msg=title)
        np.testing.assert_allclose(actual, rows[:, column], atol=capture["tolerance"], rtol=0,
                                   equal_nan=True, err_msg=title)
        np.testing.assert_array_equal(values, original)


def holdout():
    return json.loads((FOLDER / "percentile_state_holdout.tradingview.json").read_text())


def test_frozen_model_identity_and_independent_holdout():
    folder = FOLDER.parent / "golden/percentile_state_model"
    freeze = json.loads((folder / "freeze.json").read_text())
    raw = (folder / "frozen_model.py.txt").read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == freeze["modelSha256"] == holdout()["frozenModelSha256"]
    assert freeze["holdoutUsedForSelection"] is False
    assert freeze["selectionEvidenceCells"] == 16512
    assert freeze["selectionEvidenceDifferences"] == 0
    # Execute only the frozen order function, independent of runtime kernels.
    node = next(node for node in ast.parse(raw.decode()).body
                if isinstance(node, ast.FunctionDef) and node.name == "adjusted_orderings")
    namespace = {"math": math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "frozen_model", "exec"), namespace)
    capture = holdout()
    cache = {}
    for column, title in enumerate(capture["columns"][5:], 5):
        kind, source, period, pct = title.split()
        period, pct = int(period), float(pct)
        if (source, period) not in cache:
            source_index = capture["columns"].index(source)
            values = [row["values"][source_index] for row in capture["rows"]]
            cache[source, period] = namespace["adjusted_orderings"](values, period, True, "left", "last", "id", False, True)
        for index, ordered in enumerate(cache[source, period]):
            if index < period-1:
                actual = math.nan
            elif kind == "Nearest":
                actual = ordered[max(0, math.ceil(period*pct/100)-1)]
            else:
                virtual = max(0, min(period-1, period*pct/100-.5))
                lower, upper = math.floor(virtual), min(math.floor(virtual)+1, period-1)
                actual = ordered[lower] + (ordered[upper]-ordered[lower])*(virtual-lower)
            expected = capture["rows"][index]["values"][column]
            if expected is None:
                assert math.isnan(actual), (title, index)
            else:
                assert actual == pytest.approx(expected, abs=capture["tolerance"], rel=0), (title, index)


def bars(count=96):
    return [dict(time=i*60, open=row["values"][0], high=row["values"][0]+1,
                 low=row["values"][0]-1, close=row["values"][0], volume=1)
            for i, row in enumerate(holdout()["rows"][:count])]


def assert_native(result, count=96):
    assert result.ok, result.error
    capture = holdout()
    for column, title in enumerate(capture["columns"][5:], 5):
        expected = {i*60: row["values"][column] for i, row in enumerate(capture["rows"][:count])
                    if row["values"][column] is not None}
        line = next((line for line in result.lines if line.get("title") == title or line.get("name") == title), {})
        actual = {point["time"]: point["value"] for point in line.get("data", [])}
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=capture["tolerance"], rel=0), title


@pytest.mark.parametrize("count", (1, 13, 17, 19, 24, 45, 58, 80, 96))
def test_holdout_generic_python_callback(count):
    source = (FOLDER / "percentile_state_holdout.py").read_text()
    assert_native(pn.run(source, bars(count), executor_mode="inline"), count)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (13, 44, 58))
def test_holdout_preview_isolation_and_snapshot_continuation(mode, cut):
    script = (FOLDER / "percentile_state_holdout.py").read_text()
    settings = pn.PyneSettings(executor_mode="inline")
    session = pn.PyneIncrementalSession(script=script, settings=settings)
    session.seed(bars(cut))
    committed = session.snapshot_result()
    next_bar = bars(cut+1)[-1]
    session.on_bar_updated(dict(next_bar, close=next_bar["close"]+100, high=next_bar["high"]+100))
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=script, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),
                                                                   script=script, settings=settings)
    for bar in bars()[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result())
