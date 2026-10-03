from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _diff_module():
    spec = importlib.util.spec_from_file_location("ta_capture_diff", ROOT / "scripts/ta_capture_diff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_sparse_point_does_not_shift_later_comparisons(tmp_path):
    path = _write_fixture(tmp_path, [10., 11.])
    fixture = json.loads(path.read_text())
    fixture["script"] = 'plot(np.where(bar_index == 0, np.nan, close), "Close")'
    # Write the changed source while preserving both native points.
    path.write_text(json.dumps(fixture), encoding="utf-8")
    report = _diff_module().build_report([path], set(), "parity")
    assert report["counts"]["differences"] == 1
    assert report["differences"][0]["tradingview"] == {"time": 1, "value": 10.}
    assert report["differences"][0]["pyne"] is None


def test_exact_disclosure_preserves_raw_difference_and_fails_if_obsolete(tmp_path):
    path = _write_fixture(tmp_path, [10., 11.])
    fixture = json.loads(path.read_text())
    fixture["script"] = 'plot(np.where(bar_index == 0, np.nan, close), "Close")'
    fixture["external_capture"]["known_differences"] = [{"plot": "Close", "tradingview": {"time": 1, "value": 10.},
        "pyne": None, "reason": "test context boundary", "evidence": "independent test control"}]
    path.write_text(json.dumps(fixture), encoding="utf-8")
    report = _diff_module().build_report([path], set(), "parity")
    assert report["counts"]["differences"] == report["counts"]["known_differences"] == 1
    assert report["counts"]["unexpected_differences"] == 0
    fixture["script"] = 'plot(close, "Close")'
    path.write_text(json.dumps(fixture), encoding="utf-8")
    report = _diff_module().build_report([path], set(), "parity")
    assert report["counts"]["unexpected_differences"] == 1
    assert report["differences"][0]["kind"] == "known_difference_not_observed"


def test_ta_capture_diff_reports_zero_for_matching_capture(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, [10.0, 11.0])

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_diff.py"),
            "--assertion",
            "parity",
            str(fixture),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["counts"]["captured_fixtures"] == 1
    assert report["counts"]["differences"] == 0


def test_ta_capture_diff_fails_for_mismatch(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, [10.0, 12.0])

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_diff.py"),
            "--assertion",
            "parity",
            str(fixture),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["counts"]["differences"] == 1


def test_ta_capture_diff_allows_plot_specific_tolerance(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, [10.0, 11.00001])
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["external_capture"]["plot_tolerances"] = {"Close": 1e-4}
    fixture.write_text(json.dumps(data) + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_diff.py"),
            "--assertion",
            "parity",
            str(fixture),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["counts"]["differences"] == 0


def _write_fixture(tmp_path: Path, values: list[float]) -> Path:
    fixture = tmp_path / "ta_sample_indicators.json"
    fixture.write_text(
        json.dumps(
            {
                "name": "ta_sample_indicators",
                "chart_bars": [
                    {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
                    {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 200},
                ],
                "script": 'plot(close, "Close")\n',
                "expected_series": {
                    "Close": [
                        {"time": 1, "value": 10},
                        {"time": 2, "value": 11},
                    ]
                },
                "external_capture": {
                    "provider": "tradingview",
                    "status": "captured",
                    "assertion": "parity",
                    "tolerance": 1e-9,
                    "series": {
                        "Close": [
                            {"time": 1, "value": values[0]},
                            {"time": 2, "value": values[1]},
                        ]
                    },
                    "bars": [
                        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
                        {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 200},
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture
