from __future__ import annotations

import copy
import csv
import io
import json
import math
from pathlib import Path

import pytest

import pyne_runtime as pn
from pyne_runtime.cli import main


def _bars():
    return [dict(time=i + 1, open=v, high=v + 1, low=v - 1, close=v, volume=100)
            for i in range(64) for v in [100 + math.sin(i / 3) * 4 + i / 10]]


def _series(result):
    lines = result.lines if hasattr(result, "lines") else result["lines"]
    return {line["name"]: line["data"] for line in lines}


def _ema(values, period):
    value = sum(values[:period]) / period
    result = [None] * (period - 1) + [value]
    for close in values[period:]:
        value = 2 / (period + 1) * close + (1 - 2 / (period + 1)) * value
        result.append(value)
    return result


@pytest.mark.parametrize("template", ["trend", "volatility", "state"])
def test_one_authored_script_history_preview_restore_and_independent_values(tmp_path, template):
    path = tmp_path / "indicator.py"
    assert main(["new", str(path), "--template", template]) == 0
    source = path.read_text(encoding="utf-8")
    assert pn.inspect_script(source)["compatibility"]["supported"]
    bars = _bars()
    closes = [bar["close"] for bar in bars]
    expected = {}
    if template == "trend":
        fast, slow = _ema(closes, 3), _ema(closes, 5)
        expected = {"Fast EMA": fast, "Slow EMA": slow,
                    "Trend": [None if s is None else 1 if f > s else -1 if f < s else 0
                              for f, s in zip(fast, slow)]}
    elif template == "volatility":
        middle, upper, lower = [None] * 4, [None] * 4, [None] * 4
        for i in range(4, len(closes)):
            window = closes[i-4:i+1]
            mean = sum(window) / 5
            deviation = math.sqrt(sum((x - mean) ** 2 for x in window) / 5)
            middle.append(mean)
            upper.append(mean + 2 * deviation)
            lower.append(mean - 2 * deviation)
        expected = {"Middle": middle, "Upper": upper, "Lower": lower}
    else:
        expected = {"Change": [0.] + [b-a for a, b in zip(closes, closes[1:])],
                    "Cumulative change": [value-closes[0] for value in closes]}
    historical = pn.run(source, bars, executor_mode="inline")
    assert historical.ok, historical.error
    actual = _series(historical)
    for name, values in expected.items():
        points = {p["time"]: p["value"] for p in actual[name]}
        for i, value in enumerate(values):
            assert points.get(i+1) == (pytest.approx(value, abs=1e-7) if value is not None else None)
    session = pn.PyneIncrementalSession(script=source, retention_bars=16)
    for index, bar in enumerate(bars):
        committed = copy.deepcopy(session.snapshot_result())
        for offset in (0.5, -0.5):
            assert session.on_bar_updated(dict(bar, close=bar["close"]+offset)).ok
            assert session.snapshot_result() == committed
        assert session.on_bar_closed(bar).ok
        if index in (1, 3, 4, 31):
            session = pn.PyneIncrementalSession.from_portable_snapshot(
                session.snapshot_portable_state(), script=source)
        current = _series(session.snapshot_result())
        for name in expected:
            target = [p for p in actual[name] if max(1, index-14) <= p["time"] <= index+1]
            assert current.get(name, []) == target


def test_csv_mapping_milliseconds_selection_and_no_pandas(tmp_path):
    script = tmp_path / "script.py"
    script.write_text('plot(close, "Close, value")\nplot(close[1], "Previous")\n')
    data = tmp_path / "input.csv"
    data.write_text("timestamp,O,H,L,C,V\n1000,1,2,0,1,10\n2000,2,3,1,2,20\n")
    target = tmp_path / "out.csv"
    args = ["run", str(script), "--ohlcv", str(data), "--time-unit", "ms",
            "--format", "csv", "--series", "Previous", "--series", "Close, value",
            "--out", str(target), "--executor-mode", "inline"]
    for field, column in zip(("time", "open", "high", "low", "close", "volume"),
                             ("timestamp", "O", "H", "L", "C", "V")):
        args.extend(["--column", f"{field}={column}"])
    assert main(args) == 0
    rows = list(csv.DictReader(io.StringIO(target.read_text())))
    assert list(rows[0]) == ["time", "Previous", "Close, value"]
    assert rows == [{"time": "1", "Previous": "", "Close, value": "1.0"},
                    {"time": "2", "Previous": "1.0", "Close, value": "2.0"}]


def test_new_never_overwrites_and_csv_failure_preserves_previous_file(tmp_path, capsys):
    script = tmp_path / "script.py"
    assert main(["new", str(script)]) == 0
    original = script.read_bytes()
    assert main(["new", str(script), "--template", "state"]) == 2
    assert script.read_bytes() == original
    data = Path(__file__).parents[1] / "examples" / "sample_ohlcv.csv"
    out = tmp_path / "result.csv"
    out.write_text("previous result")
    assert main(["run", str(script), "--ohlcv", str(data), "--format", "csv",
                 "--out", str(out), "--param", "Fast=0", "--executor-mode", "inline"]) == 1
    assert out.read_text() == "previous result"
    assert 'Require 1 <= Fast < Slow' in capsys.readouterr().err


def test_author_diagnostic_then_corrected_scalar_script(tmp_path):
    bad = 'indicator("Wrong")\nif close > open:\n    plot(close, "Close")\n'
    assert pn.inspect_script(bad)["migration"]["diagnostics"]
    assert not pn.run(bad, _bars(), executor_mode="inline").ok
    path = tmp_path / "corrected.py"
    assert main(["new", str(path), "--template", "trend"]) == 0
    assert pn.run(path, _bars(), executor_mode="inline").ok


@pytest.mark.parametrize("extra", [
    ["--column", "typo=close"], ["--column", "close=C", "--column", "close=D"],
    ["--series", "Close"], ["--format", "csv", "--series", "missing"],
])
def test_cli_invalid_selection_and_mapping_are_actionable(tmp_path, capsys, extra):
    script = tmp_path / "script.py"
    script.write_text('plot(close, "Close")\n')
    data = Path(__file__).parents[1] / "examples" / "sample_ohlcv.csv"
    assert main(["run", str(script), "--ohlcv", str(data),
                 "--executor-mode", "inline", *extra]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "PYNE_CLI_INPUT_ERROR"
