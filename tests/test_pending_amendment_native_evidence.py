"""Independent market/order amendment and native runtime-error witnesses."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "tests/workloads"
CASES = ("stop_limit_to_market", "market_to_stop_limit_same_tick", "market_to_stop_limit_same_tick_p2", "stop_limit_order_repeat", "stop_limit_cancel_direction")
spec = importlib.util.spec_from_file_location("pending_amendment_report", ROOT / "scripts/official_alignment_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


@pytest.mark.parametrize("case,first,quantity,price", (
    ("stop_limit_to_market", 3, 2, 378),
    ("market_to_stop_limit_same_tick", 32, 0, None),
    ("market_to_stop_limit_same_tick_p2", 9, 2, 300),
    ("stop_limit_order_repeat", 9, 1, 300),
    ("stop_limit_cancel_direction", 6, -2, 398),
))
def test_native_amendment_timelines(case, first, quantity, price):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(FOLDER, name, capture)
    assert len(capture["rows"]) == 32 and len(capture["columns"]) == 15
    reference = json.loads((FOLDER / "strategy_pyramiding_1.tradingview.json").read_text(encoding="utf-8"))
    assert [r["values"][:6] for r in capture["rows"]] == [r["values"][:6] for r in reference["rows"]]
    for index, row in enumerate(capture["rows"]):
        expected = [quantity, 1, 0, price, 0, 0, quantity, 0, 0] if index >= first else [0, 0, 0, None, 0, 0, 0, 0, 0]
        assert row["values"][6:] == expected


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("incremental", (False, True))
def test_native_amendment_full_column_measurement(case, incremental):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    result = reporter.workload_report(ROOT, name, set(capture["columns"][:6]), incremental)
    assert result["status"] == "measured" and result["unmappedOutputColumns"] == []
    assert set(result["columns"]) == set(capture["columns"][6:])
    assert sum(c["counts"]["cells"] for c in result["columns"].values()) == 288
    for column in result["columns"].values():
        assert column["counts"]["differences"] == len(column["differences"])
        assert column["counts"]["differences"] == 0


def test_native_direction_error_is_a_separate_observable_contract():
    checks = reporter.native_runtime_error_checks(ROOT)
    assert {c["mode"] for c in checks} == {"batch", "incremental"}
    for check in checks:
        assert check["officialErrorBarIndex"] == 2 and check["officialErrorCode"] == "RE10028"
        assert "Cancel the existing 'A' order" in check["officialMessage"]
        assert check["errorPresenceDifference"] == check["pyneSucceeded"]
        assert not check["errorPresenceDifference"] and check["pyneDirectionChangeRejected"]
        assert "counts" not in check  # Errors cannot manufacture numeric cells.


@pytest.mark.parametrize("suffix", ("pine", "dom.txt", "snapshot.txt"))
def test_native_error_provenance_rejects_corruption(tmp_path, suffix):
    folder = tmp_path / "tests/workloads"
    folder.mkdir(parents=True)
    name = "strategy_pending_pyramiding_stop_limit_change_direction"
    for ext in ("native-error.json", "pine", "dom.txt", "snapshot.txt"):
        (folder / f"{name}.{ext}").write_bytes((FOLDER / f"{name}.{ext}").read_bytes())
    with (folder / f"{name}.{suffix}").open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        reporter.native_runtime_error_checks(tmp_path)
