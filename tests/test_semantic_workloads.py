"""Whole-script acceptance, using only public package APIs and neutral data.

These are execution-contract checks, not a claim of exhaustive Pine parity.
Timestamped points are compared (not just compressed non-missing values).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.security import PyneSecurityError


ROOT = Path(__file__).parent / "workloads"
WORKLOADS = ("ta_chain", "requests", "state_cache", "drawings", "strategy")


def script(name):
    return (ROOT / f"{name}.py").read_text(encoding="utf-8")


def bars(count=40):
    closes = (10, 12, 14, 13, 11, 9, 8, 10, 13, 15, 12, 9)
    return [
        {
            "time": i * 10,
            "open": float(closes[i % 12]),
            "high": float(closes[i % 12] + 1),
            "low": float(closes[i % 12] - 1),
            "close": float(closes[i % 12]),
            "volume": 0.0 if i % 7 == 0 else 10.0,
        }
        for i in range(count)
    ]


class Provider:
    """Immutable source, sparse LTF slots and deliberately extreme future rows."""

    capabilities = {"request.security": True, "request.security_lower_tf": True}

    def __init__(self, future_from=None):
        self.future_from = future_from

    def get_ohlcv(self, symbol, timeframe, start, end):
        assert symbol == "TEST:ASSET"
        step = {"30S": 30, "5S": 5}[timeframe]
        rows = []
        for timestamp in range(-60, 3000, step):
            if timeframe == "5S" and timestamp % 40 == 5:
                continue
            close = float(20 + timestamp // step % 9)
            if self.future_from is not None and timestamp >= self.future_from:
                close += 10000
            if start <= timestamp <= end:
                rows.append(
                    {
                        "time": timestamp,
                        "open": close,
                        "high": close + 1,
                        "low": close - 1,
                        "close": close,
                        "volume": 10,
                    }
                )
        return rows


def settings():
    return pn.PyneSettings(
        executor_mode="inline",
        timeframe="10S",
        syminfo={"tickerid": "TEST:ASSET"},
        data_provider=Provider(),
    )


def points(result):
    assert result.ok, result.error
    return {line["name"]: line["data"] for line in result.lines}


def assert_execution_equal(actual, expected):
    assert actual.ok and expected.ok
    assert actual.lines == expected.lines
    assert actual.output == expected.output
    # Preview visitation changes isnew, not committed calculation semantics.
    left, right = copy.deepcopy(actual.meta), copy.deepcopy(expected.meta)
    for meta in (left, right):
        meta.get("barstate", {}).pop("isnew", None)
    assert left == right


@pytest.mark.parametrize("name", ("ta_chain", "requests", "strategy"))
def test_complete_batch_incremental_semantics(name):
    def view(result):
        return {"points": points(result), "strategy": result.output.get("strategy")}

    pn.run_incremental_parity(
        batch_script=script(name + "_batch"),
        incremental_script=script(name),
        bars=bars(),
        settings=settings(),
        normalizer=view,
    ).assert_ok()


@pytest.mark.parametrize("name", ("ta_chain", "ta_chain_batch"))
def test_ta_chain_matches_tradingview_whole_script_capture(name):
    capture = json.loads((ROOT / "ta_chain.tradingview.json").read_text(encoding="utf-8"))
    for filename, key in (
        ("ta_chain.pine", "scriptSha256"),
        ("ta_chain.tradingview.txt", "logSha256"),
    ):
        # Normalize checkout line endings; capture digests cover LF UTF-8 text.
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode()).hexdigest() == capture[key]
    rows = capture["rows"]
    assert [row["index"] for row in rows] == list(range(40))
    logs = (ROOT / "ta_chain.tradingview.txt").read_text(encoding="utf-8").splitlines()
    assert len(logs) == len(rows)
    for row, log in zip(rows, logs):
        index, *values = log.split("PYNE_ORACLE|")[1].split("|")
        assert int(index) == row["index"]
        assert [None if value == "NaN" else float(value) for value in values] == row["values"]
    data = bars()
    actual = points(pn.run(script(name), data, settings=settings()))
    for column, title in enumerate(capture["columns"][1:], 1):
        # Public plot transport rounds to 8 decimals in both modes; retain the
        # original 10-decimal Pine logs and compare at the declared wire precision.
        expected = {
            row["index"] * 10: round(row["values"][column], 8)
            for row in rows
            if row["values"][column] is not None
        }
        observed = {point["time"]: point["value"] for point in actual[title]}
        assert observed.keys() == expected.keys()
        assert observed == pytest.approx(expected, abs=capture["tolerance"], rel=0)
    assert [row["values"][0] for row in rows] == [row["close"] for row in data]


@pytest.mark.parametrize("name", WORKLOADS)
@pytest.mark.parametrize("restore_mode", ("local", "replay", "state"))
def test_complete_workload_preview_restore_and_retention(name, restore_mode):
    source = script(name)
    config = settings()
    control = pn.PyneIncrementalSession(script=source, settings=config, retention_bars=8)
    subject = pn.PyneIncrementalSession(script=source, settings=config, retention_bars=8)
    data = bars()
    control.seed(data[:2])
    subject.seed(data[:2])
    for index, bar in enumerate(data[2:], 2):
        committed = copy.deepcopy(subject.snapshot_result())
        for offset in (50, -5, 17):
            preview = dict(
                bar, close=bar["close"] + offset, high=bar["high"] + 50, low=bar["low"] - 5
            )
            assert subject.on_bar_updated(preview).ok
            assert subject.snapshot_result() == committed
        if index in (3, 6, 11, 23):
            if restore_mode == "local":
                subject = pn.PyneIncrementalSession.from_snapshot(
                    subject.snapshot_state(), script=source, settings=config
                )
            else:
                payload = subject.snapshot_portable(mode=restore_mode)
                subject = pn.PyneIncrementalSession.from_portable_snapshot(
                    payload, script=source, settings=config
                )
            assert_execution_equal(subject.snapshot_result(), committed)
        assert_execution_equal(subject.on_bar_closed(bar), control.on_bar_closed(bar))
        assert_execution_equal(subject.snapshot_result(), control.snapshot_result())
        assert subject.snapshot_result().meta["retainedBars"] == min(index + 1, 8)
        for series in points(subject.snapshot_result()).values():
            assert len(series) <= 8
            assert all(point["time"] >= data[max(0, index - 7)]["time"] for point in series)


@pytest.mark.parametrize("name", ("ta_chain", "requests", "strategy"))
def test_batch_prefix_is_independent_of_future_input(name):
    source = script(name + "_batch")
    for cut in (3, 7, 10, 19):
        data = bars()
        before = pn.run(source, data[:cut], settings=settings())
        for row in data[cut:]:
            for key in ("open", "high", "low", "close"):
                row[key] += 100
        config = settings()
        # A provider row opening at the chart prefix end is future information.
        config = replace(config, data_provider=Provider(future_from=cut * 10))
        after = pn.run(source, data, settings=config)
        prefix = {
            name: [p for p in series if p["time"] < cut * 10]
            for name, series in points(after).items()
        }
        assert prefix == points(before)


def test_state_cache_has_independent_arithmetic_oracle():
    data = bars()
    result = pn.run(script("state_cache"), data, settings=settings())
    actual = points(result)
    for index, row in enumerate(data):
        assert actual["Count"][index]["value"] == index + 1
        assert actual["Total"][index]["value"] == sum(x["close"] for x in data[: index + 1])
        assert actual["Tail sum"][index]["value"] == sum(
            x["close"] for x in data[max(0, index - 2) : index + 1]
        )


def test_drawing_lifecycle_has_independent_event_oracle():
    session = pn.PyneIncrementalSession(script=script("drawings"), settings=settings())
    for index, bar in enumerate(bars()):
        result = session.on_bar_closed(bar)
        events = result.output.get("object_events", [])
        expected = (
            (("create", "line"), ("create", "label"))
            if index % 4 == 0
            else (
                (("delete", "line"), ("delete", "label"))
                if index % 4 == 3
                else (("update", "line"), ("update", "label"), ("update", "label"))
            )
        )
        assert [(event["action"], event["kind"]) for event in events] == list(expected)
        assert all(event["time"] == bar["time"] and event["confirmed"] for event in events)
        if index % 4 == 3:
            assert not session.snapshot_result().output.get("objects")


def test_strategy_position_and_costs_have_independent_oracle():
    data = bars()
    result = pn.run(script("strategy"), data, settings=settings())
    actual = points(result)
    assert [p["value"] for p in actual["Position"]] == [0] * 2 + [4] * 3 + [3] * 4 + [0] * 31
    gross = data[5]["close"] - data[2]["close"] + 3 * (data[9]["close"] - data[2]["close"])
    assert actual["Net profit"][-1]["value"] == gross - 3
    assert actual["Equity"][-1]["value"] == 10000 + gross - 3


@pytest.mark.parametrize("mode", ("batch", "incremental"))
@pytest.mark.parametrize("gaps", ("on", "off"))
@pytest.mark.parametrize("lookahead", ("on", "off"))
def test_single_requested_bar_confirmation_uses_duration(mode, gaps, lookahead):
    expression = f'request.security("TEST:ASSET", "30S", ("close", "high"), gaps="{gaps}", lookahead="{lookahead}")'
    source = (
        f'indicator("Single"); a, b = {expression}; plot(a, "A"); plot(b, "B")'
        if mode == "batch"
        else 'indicator("Single", mode="incremental")\ndef on_bar(ctx, bar):\n'
        f'    a, b = {expression}\n    ctx.plot("A", a)\n    ctx.plot("B", b)'
    )
    # Only the requested candle at t=0 is returned before the first chart close.
    # Its final close cannot be visible at t=0 under lookahead_off.
    actual = points(pn.run(source, bars(1), settings=settings()))
    if lookahead == "off":
        # Incremental plots are created lazily on their first finite point.
        assert actual == ({"A": [], "B": []} if mode == "batch" else {})
    else:
        assert actual == {"A": [{"time": 0, "value": 20.0}], "B": [{"time": 0, "value": 21.0}]}


@pytest.mark.parametrize("name", WORKLOADS)
def test_long_workload_state_restore_preserves_tail(name):
    data = bars(256)
    config = settings()
    source = script(name)
    continuous = pn.PyneIncrementalSession(script=source, settings=config, retention_bars=16)
    recovered = pn.PyneIncrementalSession(script=source, settings=config, retention_bars=16)
    for index, bar in enumerate(data):
        assert recovered.on_bar_closed(bar) == continuous.on_bar_closed(bar)
        if index in (31, 63, 127, 191):
            recovered = pn.PyneIncrementalSession.from_portable_snapshot(
                recovered.snapshot_portable_state(), script=source, settings=config
            )
            assert recovered.snapshot_result() == continuous.snapshot_result()
    result = recovered.snapshot_result()
    assert result == continuous.snapshot_result()
    assert result.meta["totalCommittedBars"] == 256
    assert result.meta["retainedBars"] == 16
    assert all(len(series) <= 16 for series in points(result).values())


@pytest.mark.parametrize("name", WORKLOADS)
def test_failed_workload_recovers_from_last_committed_state(name):
    source = (
        script(name) + '\n    if bar.close > 900:\n        raise ValueError("workload failure")\n'
    )
    config = settings()
    session = pn.PyneIncrementalSession(script=source, settings=config)
    control = pn.PyneIncrementalSession(script=source, settings=config)
    data = bars()
    session.seed(data[:5])
    control.seed(data[:5])
    checkpoint = session.snapshot_portable_state()
    invalid = dict(data[5], open=999, high=1000, low=998, close=999)
    with pytest.raises(ValueError, match="workload failure"):
        session.on_bar_closed(invalid)
    with pytest.raises(PyneSecurityError, match="poisoned"):
        session.on_bar_closed(data[5])
    recovered = pn.PyneIncrementalSession.from_portable_snapshot(
        checkpoint, script=source, settings=config
    )
    assert recovered.snapshot_result() == control.snapshot_result()
    for bar in data[5:12]:
        assert recovered.on_bar_closed(bar) == control.on_bar_closed(bar)


def test_preview_sensitive_committed_state_requires_state_snapshot():
    source = """
indicator("Event-sensitive", mode="incremental")
def on_bar(ctx, bar):
    count = ctx.state("count", 0)
    if ctx.barstate.isnew:
        count.value += 1
    ctx.plot("Count", count.value)
"""
    config = settings()
    session = pn.PyneIncrementalSession(script=source, settings=config)
    data = bars()
    session.seed(data[:2])
    session.on_bar_updated(data[2])
    session.on_bar_closed(data[2])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        session.snapshot_portable_state(), script=source, settings=config
    )
    assert points(restored.snapshot_result())["Count"][-1]["value"] == 2
    assert restored.snapshot_result() == session.snapshot_result()
    assert restored.on_bar_closed(data[3]) == session.on_bar_closed(data[3])
