"""Preserve rejected-formula counterexamples alongside native percentile controls."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from pyne_runtime.ta import TaModule

FOLDER = Path(__file__).parent / "workloads"


def capture(name):
    return json.loads((FOLDER / f"{name}.tradingview.json").read_text())


def test_independent_insertion_model_is_falsified_by_expanded_native_cases():
    data = capture("percentile_insertion_matrix")
    compared = differences = 0
    for row in data["rows"]:
        for column, title in enumerate(data["columns"]):
            if title.startswith("Formula Linear "):
                native = data["columns"].index(title.removeprefix("Formula "))
                compared += 1
                differences += row["values"][native] != row["values"][column]
    assert compared == 3680
    assert differences == 188  # Counterexamples invalidate the general rule.


def test_same_official_inputs_and_parameters_reproduce_across_three_probes():
    original = capture("percentile_confirmation")
    sorted_probe = capture("percentile_missing_sort")
    matrix = capture("percentile_insertion_matrix")
    for kind in ("Nearest", "Linear"):
        for pct in (25, 50, 75):
            old = original["columns"].index(f"{kind} holes {pct}")
            title = f"{kind} holes 4 {pct}"
            for other in (sorted_probe, matrix):
                new = other["columns"].index(title)
                assert [r["values"][old] for r in original["rows"]] == [
                    r["values"][new] for r in other["rows"][:24]]


def test_array_sort_missing_last_is_not_the_ta_missing_rank_rule():
    data = capture("percentile_missing_sort")
    for row in data["rows"]:
        i = row["index"]
        window = [np.nan if j < 0 else data["rows"][j]["values"][1]
                  for j in range(i - 3, i + 1)]
        wanted = np.sort(np.asarray(window, dtype=float))
        for order in ("newest", "oldest"):
            first = data["columns"].index(f"Sorted {order} 0")
            np.testing.assert_allclose(np.asarray(row["values"][first:first + 4], dtype=float),
                                       wanted, equal_nan=True, rtol=0, atol=0)
    row = data["rows"][10]
    assert row["values"][data["columns"].index("Sorted newest 1")] == 1.
    assert row["values"][data["columns"].index("Nearest holes 4 50")] is None


@pytest.mark.parametrize("kind", ("Nearest", "Linear"))
@pytest.mark.parametrize("name,period", [(name, period)
                                        for name in ("holes", "ties", "alternating", "multiple")
                                        for period in (1, 2, 3, 4, 7)] + [("leading", 3), ("leading", 4)])
def test_present_windows_match_native_without_claiming_missing_window_parity(kind, name, period):
    data = capture("percentile_insertion_matrix")
    source_col = data["columns"].index(name)
    source = np.asarray([row["values"][source_col] for row in data["rows"]], dtype=float)
    module = TaModule()
    fn = module.percentile_nearest_rank if kind == "Nearest" else module.percentile_linear_interpolation
    for pct in (0, 25, 50, 75, 100):
        column = data["columns"].index(f"{kind} {name} {period} {pct}")
        actual = fn(source, period, pct)
        ready = [i for i in range(period - 1, len(source))
                 if not np.isnan(source[i - period + 1:i + 1]).any()]
        expected = np.asarray([data["rows"][i]["values"][column] for i in ready], dtype=float)
        np.testing.assert_allclose(actual[ready], expected, equal_nan=True, rtol=0, atol=1e-8)
