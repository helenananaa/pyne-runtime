"""Native same-ID order replacement, activation and OCA reassignment."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import pyne_runtime as pn

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"tests/workloads"
CASES=("stop_limit_order_repeat", "stop_limit_order_update_activated", "stop_limit_order_oca_reassign", "stop_limit_order_oca_same_group", "stop_limit_order_oca_new_id")
spec=importlib.util.spec_from_file_location("order_native_report", ROOT/"scripts/official_alignment_report.py")
reporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def capture(case):
    return json.loads((FOLDER/f"strategy_pending_pyramiding_{case}.tradingview.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES)
def test_native_order_timelines(case):
    data=capture(case)
    reporter.verify_evidence(FOLDER,f"strategy_pending_pyramiding_{case}",data)
    assert len(data["rows"])==32 and len(data["columns"])==15
    for index,row in enumerate(data["rows"]):
        expected=[0,0,0,None,0,0,0,0,0]
        if case in ("stop_limit_order_repeat", "stop_limit_order_oca_reassign") and index>=9:
            expected=[1,1,0,300,0,0,1,0,0]
        if case in ("stop_limit_order_oca_same_group", "stop_limit_order_oca_new_id") and index>=6:
            expected=[1,1,0,369,0,0,0,1,0]
        if case=="stop_limit_order_oca_new_id" and index>=9:
            expected=[2,2,0,334.5,0,0,0,1,1]
        assert row["values"][6:]==expected


def assert_native(result,case,count):
    assert result.ok,result.error
    data=capture(case)
    lines={line["name"]:{p["time"]:p["value"] for p in line["data"]} for line in result.lines}
    for column,title in enumerate(data["columns"][6:],6):
        expected={r["values"][0]:r["values"][column] for r in data["rows"][:count] if r["values"][column] is not None}
        assert lines.get(title,{}).keys()==expected.keys(),(case,title)
        assert lines.get(title,{})==pytest.approx(expected,abs=1e-8,rel=0),(case,title)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("callback", (False,True))
@pytest.mark.parametrize("count", (1,2,3,4,6,7,9,10,32))
def test_native_order_prefixes(case,callback,count):
    name=f"strategy_pending_pyramiding_{case}"
    script=(FOLDER/f"{name}{'' if callback else '_batch'}.py").read_text(encoding="utf-8")
    assert_native(pn.run(script,reporter._bars(name,capture(case))[:count],executor_mode="inline"),case,count)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("cut", (2,3,8))
@pytest.mark.parametrize("mode", ("local","replay","state"))
def test_order_update_preview_and_restored_continuation(case,cut,mode):
    name=f"strategy_pending_pyramiding_{case}"
    script=(FOLDER/f"{name}.py").read_text(encoding="utf-8")
    bars=reporter._bars(name,capture(case))
    settings=pn.PyneSettings(executor_mode="inline")
    session=pn.PyneIncrementalSession(script=script,settings=settings)
    session.seed(bars[:cut])
    before=session.snapshot_portable_state()
    session.on_bar_updated(dict(bars[cut],high=1500,low=1,close=700))
    assert session.snapshot_portable_state()==before
    if mode=="local":
        restored=pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(),script=script,settings=settings)
    else:
        restored=pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode),script=script,settings=settings)
    for bar in bars[cut:]:
        restored.on_bar_closed(bar)
    assert_native(restored.snapshot_result(),case,len(bars))
