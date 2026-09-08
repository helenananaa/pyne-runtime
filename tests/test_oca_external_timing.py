"""TradingView order OCA effects, with reachable non-OCA and pending controls."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).parent / "workloads"
CAPTURE = json.loads((ROOT / "oca_timing.tradingview.json").read_text(encoding="utf-8"))


def _script(mode):
    incremental = mode == "incremental"
    if incremental:
        lines = [
            'indicator("OCA capture", mode="incremental")',
            "def init(ctx):",
            "    ctx.strategy.configure(initial_capital=1000000000, pyramiding=100)",
            "def on_bar(ctx, bar):",
        ]
        prefix, namespace, index, price = "    ", "ctx.strategy", "ctx.bar_index", "bar.close"
    else:
        lines = [
            'strategy("OCA capture", initial_capital=1000000000, pyramiding=100, process_orders_on_close=True)'
        ]
        prefix, namespace, index, price = "", "strategy", "bar_index", "close"
    for command in CAPTURE["orders"]:
        stop = command["stop"]
        stop_arg = "" if stop is None else f", stop={price + '-1' if stop == 'close-1' else stop}"
        lines.append(
            f"{prefix}{namespace}.order({command['id']!r}, {namespace}.long, "
            f"qty={command['qty']}, when={index} == 0, "
            f"oca_name={command['group']!r}, oca_type={namespace}.oca.{command['oca']}"
            f"{stop_arg})"
        )
    return "\n".join(lines)


def _assert_settled(result, capture_index):
    assert result.ok, result.error
    report = result.output["strategy"]
    expected_row = CAPTURE["rows"][capture_index]["values"]
    observed = {trade["entry_id"]: trade["qty"] for trade in report["opentrades"]}
    expected = {name: qty for name, qty in zip(CAPTURE["columns"][3:], expected_row[3:]) if qty}
    assert observed == expected
    assert len(observed) == expected_row[2]
    assert sum(observed.values()) == expected_row[1]
    lifecycle = {event["id"]: event for event in report["lifecycle"]}
    assert lifecycle["PC2"]["status"] == "canceled"
    assert lifecycle["PR1"]["status"] == "filled"
    assert lifecycle["PR2"]["status"] == "filled"


def test_oca_capture_identity_and_reachable_controls():
    for suffix, key in (("pine", "scriptSha256"), ("tradingview.txt", "logSha256")):
        content = (ROOT / f"oca_timing.{suffix}").read_text(encoding="utf-8")
        assert hashlib.sha256(content.encode()).hexdigest() == CAPTURE[key]
    raw = (ROOT / "oca_timing.tradingview.txt").read_text(encoding="utf-8")
    rows = [
        {"index": int(m[1]), "values": [float(v) for v in m[2].split("|")]}
        for m in re.finditer(r"PYNE_OCA\|(\d+)\|([^;]+);", raw)
    ]
    assert rows == CAPTURE["rows"]
    assert [r["index"] for r in rows] == list(range(4))
    assert [r["values"][0] for r in rows] == [bar["time"] for bar in CAPTURE["bars"]]
    assert CAPTURE["bars"][0]["high"] < 79400 < 79410 < CAPTURE["bars"][1]["high"]
    assert CAPTURE["rows"][1]["values"][-4:] == [1, 0, 1, 2]
    assert len(CAPTURE["orders"]) == len(set(CAPTURE["columns"][3:])) == 20
    trend = json.loads((ROOT / "trend_volume.tradingview.json").read_text(encoding="utf-8"))
    assert CAPTURE["bars"] == [
        dict(zip(trend["columns"][:6], row["values"][:6])) for row in trend["rows"][:4]
    ]
    pine = (ROOT / "oca_timing.pine").read_text(encoding="utf-8")
    for command in CAPTURE["orders"]:
        call = f'strategy.order("{command["id"]}", strategy.long, qty={command["qty"]}'
        if command["stop"] is not None:
            call += ", stop=" + {79400: "p", 79410: "p+10", "close-1": "close-1"}[command["stop"]]
        if command["group"]:
            call += f', oca_name="{command["group"]}", oca_type=strategy.oca.{command["oca"]}'
        assert call + ")" in pine


@pytest.mark.parametrize("mode", ("batch", "incremental"))
@pytest.mark.parametrize("count", (2, 3, 4))
def test_oca_settled_orders_match_pine(mode, count):
    result = pn.run(_script(mode), CAPTURE["bars"][:count], executor_mode="inline")
    _assert_settled(result, count - 1)


@pytest.mark.parametrize("mode", ("local", "replay", "state"))
@pytest.mark.parametrize("cut", (1, 2))
def test_oca_restore_before_and_after_pending_fills(mode, cut):
    source = _script("incremental")
    settings = pn.PyneSettings(executor_mode="inline", timeframe="15")
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(CAPTURE["bars"][:cut])
    committed = session.snapshot_result()
    session.on_bar_updated(CAPTURE["bars"][cut])
    assert session.snapshot_result() == committed
    if mode == "local":
        restored = pn.PyneIncrementalSession.from_snapshot(
            session.snapshot_state(), script=source, settings=settings
        )
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(
            session.snapshot_portable(mode=mode), script=source, settings=settings
        )
    assert restored.snapshot_result() == committed
    for bar in CAPTURE["bars"][cut:]:
        restored.on_bar_closed(bar)
    _assert_settled(restored.snapshot_result(), 3)
