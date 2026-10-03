"""Native same-calculation market amendment and after-command observations."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"tests/workloads"
CASES=("market_update_same_tick", "market_update_same_tick_p2", "stop_limit_to_market_same_tick", "stop_limit_to_market_same_tick_p2")
spec=importlib.util.spec_from_file_location("market_native_report",ROOT/"scripts/official_alignment_report.py")
reporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


@pytest.mark.parametrize("case",CASES)
def test_native_market_replacement_timeline(case):
    name=f"strategy_pending_pyramiding_{case}"
    data=json.loads((FOLDER/f"{name}.tradingview.json").read_text(encoding="utf-8"))
    reporter.verify_evidence(FOLDER,name,data)
    assert len(data["rows"])==32 and len(data["columns"])==15
    reference=json.loads((FOLDER/"strategy_pyramiding_1.tradingview.json").read_text(encoding="utf-8"))
    assert [r["values"][:6] for r in data["rows"]]==[r["values"][:6] for r in reference["rows"]]
    assert data["rows"][0]["values"][6:]==[0,0,0,None,0,0,0,0,0]
    for row in data["rows"][1:]:
        assert row["values"][6:]==[2,1,0,370,0,0,2,0,0]


@pytest.mark.parametrize("case",CASES)
@pytest.mark.parametrize("callback",(False,True))
def test_native_market_replacement_full_measurement(case,callback):
    name=f"strategy_pending_pyramiding_{case}"
    data=json.loads((FOLDER/f"{name}.tradingview.json").read_text(encoding="utf-8"))
    result=reporter.workload_report(ROOT,name,set(data["columns"][:6]),callback)
    assert result["status"]=="measured" and result["unmappedOutputColumns"]==[]
    assert set(result["columns"])==set(data["columns"][6:])
    assert sum(c["counts"]["cells"] for c in result["columns"].values())==288
    for c in result["columns"].values():
        assert c["counts"]["differences"]==len(c["differences"])
        assert c["counts"]["differences"] == 0


def test_after_command_visibility_is_independently_observed_and_not_inflated():
    checks=reporter.native_command_visibility_checks(ROOT)
    assert len(checks)==4
    for check in checks:
        assert check["pyneSucceeded"]
        assert not check["differences"]
        assert check["mode"]=="incremental_after_commands"
        assert check["officialState"]==dict(zip(("Position","Open trades","Closed trades","Average","Net profit","Held Seed","Held A","Held B","Held C"),[0,0,0,None,0,0,0,0,0],strict=True))
        assert "counts" not in check
        assert all(c["official"]==check["officialState"][title] and c["pyne"]==check["pyneState"][title] for title,c in check["differences"].items())


@pytest.mark.parametrize("inactive_calls", (1, 2, 3))
@pytest.mark.parametrize("case", CASES)
def test_batch_replay_is_invariant_under_inactive_commands(case, inactive_calls):
    name = f"strategy_pending_pyramiding_{case}"
    capture = json.loads((FOLDER / f"{name}.tradingview.json").read_text(encoding="utf-8"))
    source = (FOLDER / f"{name}_batch.py").read_text(encoding="utf-8")
    marker = "plot(strategy.position_size, 'Position')"
    assert marker in source
    altered = source.replace(marker, 'strategy.cancel("Unused", when=False)\n' * inactive_calls + marker)
    bars = reporter._bars(name, capture)
    baseline = reporter.pn.run(source, bars, executor_mode="inline")
    replayed = reporter.pn.run(altered, bars, executor_mode="inline")
    assert baseline.ok and replayed.ok
    assert replayed.lines == baseline.lines
    assert replayed.output["strategy"] == baseline.output["strategy"]
