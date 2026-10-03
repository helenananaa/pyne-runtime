"""Controlled official history evidence and qualified rolling-order semantics."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
spec = importlib.util.spec_from_file_location("history_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def capture():
    return json.loads((FOLDER / "percentile_history_context.tradingview.json").read_text())


def test_raw_capture_is_complete_and_proves_window_external_history_dependency():
    data = capture()
    reporter.verify_evidence(FOLDER, "percentile_history_context", data)
    assert len(data["rows"]) == 64
    assert len(data["columns"]) == 124
    result = reporter.native_percentile_history_check(FOLDER)
    assert result["comparedSameWindowGroups"] == 1340
    assert result["differingGroups"] == 16
    first = result["witnesses"][0]
    assert first == {"index": 19, "method": "Nearest", "period": 4, "percentage": 75,
                     "identicalWindow": [3., None, -2., 7.],
                     "outputs": {"baseline": None, "ascending": 7., "descending": None, "leading": None}}
    assert all(None in witness["identicalWindow"] for witness in result["witnesses"])


@pytest.mark.parametrize("source", ("baseline", "ascending", "descending", "leading"))
@pytest.mark.parametrize("period", (2, 4, 7))
def test_complete_finite_windows_match_native_for_each_history(source, period):
    data = capture()
    column = data["columns"].index(source)
    values = np.asarray([row["values"][column] for row in data["rows"]], dtype=float)
    module = TaModule()
    for kind, method in (("Nearest", module.percentile_nearest_rank),
                         ("Linear", module.percentile_linear_interpolation)):
        for percentage in (0, 25, 50, 75, 100):
            actual = method(values, period, percentage)
            output = data["columns"].index(f"{kind} {source} {period} {percentage}")
            for index in range(period-1, len(values)):
                if np.isfinite(values[index-period+1:index+1]).all():
                    assert actual[index] == pytest.approx(data["rows"][index]["values"][output],
                                                          abs=data["tolerance"], rel=0)


def test_every_official_output_including_missing_failures_is_measured():
    result = reporter.workload_report(ROOT, "percentile_history_context", set(capture()["columns"][:4]), False)
    assert len(result["columns"]) == 120
    assert result["unmappedOutputColumns"] == []
    assert sum(v["counts"]["cells"] for v in result["columns"].values()) == 7680
    assert sum(v["counts"]["differences"] for v in result["columns"].values()) == 0
