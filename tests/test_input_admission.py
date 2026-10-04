"""Selected input budgets stop materialization before execution or copying."""
from pathlib import Path

import pytest

import pyne_runtime as pn
from pyne_runtime.cli import main
from pyne_runtime.data import coerce_ohlcv


def bar(time):
    return dict(time=time, open=1, high=1, low=1, close=1, volume=1)


@pytest.mark.parametrize("executor_mode", ["inline", "process"])
@pytest.mark.parametrize("incremental", [False, True])
def test_run_stops_unbounded_generator_before_execution(monkeypatch, executor_mode, incremental):
    consumed = []

    def source():
        for time in range(10000):
            consumed.append(time)
            yield bar(time)

    def forbidden(**kwargs):
        pytest.fail("Rejected data must not enter an executor or callback")

    monkeypatch.setattr("pyne_runtime.api.execute_pyne_script", forbidden)
    script = ('def on_bar(ctx, bar):\n    ctx.plot("x", bar.close)' if incremental
              else 'plot(close, "x")')
    result = pn.run(script, source(), settings=pn.PyneSettings(max_bars=2, executor_mode=executor_mode))
    assert consumed == [0, 1, 2]
    assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    assert not result.ok and "max 2" in result.error
    assert "max_bars" in result.hint


def test_environment_admission_and_explicit_unlimited_override(monkeypatch):
    monkeypatch.setenv("PYNE_MAX_BARS", "1")
    rows = [bar(time) for time in range(4)]
    assert pn.run('plot(close, "x")', iter(rows)).code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    accepted = pn.run('plot(close, "x")', iter(rows), settings=pn.PyneSettings(max_bars=None))
    assert accepted.ok and accepted.values("x") == [1.0] * 4


def test_existing_data_rejected_before_copy(monkeypatch):
    data = pn.PyneData.from_ohlcv([bar(time) for time in range(4)])
    monkeypatch.setattr(pn.PyneData, "to_ohlcv", lambda self: pytest.fail("Must reject before copying"))
    with pytest.raises(pn.PyneResourceLimitError, match="max 2"):
        coerce_ohlcv(data, max_bars=2)


def test_dataframe_rejected_before_record_materialization(monkeypatch):
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame([bar(time) for time in range(4)])
    monkeypatch.setattr(pd.DataFrame, "to_dict", lambda *a, **k: pytest.fail("Must reject before records"))
    result = pn.run("plot(close)", df, settings=pn.PyneSettings(max_bars=2))
    assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"


@pytest.mark.parametrize("loader", ["friendly", "container", "run"])
def test_csv_admission_stops_consumption_and_closes_handle(tmp_path: Path, monkeypatch, loader):
    import pyne_runtime.data as data_module

    path = tmp_path / "large.csv"
    path.write_text("time,open,high,low,close,volume\n" +
                    "".join(f"{time},1,1,1,1,1\n" for time in range(10000)), encoding="utf-8")
    consumed = []
    original_reader = data_module.csv.DictReader

    def reader(*args, **kwargs):
        for row in original_reader(*args, **kwargs):
            consumed.append(row["time"])
            yield row

    monkeypatch.setattr(data_module.csv, "DictReader", reader)
    if loader == "run":
        result = pn.run("plot(close)", path, settings=pn.PyneSettings(max_bars=2))
        assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    else:
        load = pn.read_ohlcv if loader == "friendly" else pn.PyneData.from_csv
        with pytest.raises(pn.PyneResourceLimitError, match="max 2"):
            load(path, max_bars=2)
    assert consumed == ["0", "1", "2"]
    # The handle is closed on rejection, including on Windows.
    path.unlink()


def test_cli_admission_returns_resource_error_without_overwriting_output(tmp_path, capsys):
    script = tmp_path / "script.py"
    script.write_text("plot(close)")
    data = tmp_path / "bars.csv"
    data.write_text("time,open,high,low,close,volume\n0,1,1,1,1,1\n1,1,1,1,1,1\n")
    output = tmp_path / "result.json"
    output.write_text("keep")
    assert main(["run", str(script), "--ohlcv", str(data), "--limit", "max_bars=1",
                 "--out", str(output)]) == 1
    assert "PYNE_RESOURCE_LIMIT_EXCEEDED" in capsys.readouterr().err
    assert output.read_text() == "keep"


def test_cli_json_resource_error_keeps_execution_exit_status(tmp_path, capsys):
    import json

    script = tmp_path / "script.py"
    script.write_text("plot(close)")
    data = tmp_path / "bars.csv"
    data.write_text("time,open,high,low,close,volume\n0,1,1,1,1,1\n1,1,1,1,1,1\n")
    assert main(["run", str(script), "--ohlcv", str(data), "--limit", "max_bars=1"]) == 1
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["code"] == "PYNE_RESOURCE_LIMIT_EXCEEDED"


def test_admission_at_limit_and_shape_errors_within_limit():
    accepted = pn.run('plot(close, "x")', (bar(time) for time in range(2)),
                      settings=pn.PyneSettings(max_bars=2))
    assert accepted.ok and accepted.values("x") == [1., 1.]
    invalid = pn.run("plot(close)", [None], settings=pn.PyneSettings(max_bars=2))
    assert invalid.code == "PYNE_INVALID_OHLCV"


@pytest.mark.parametrize("limit", [0, -1])
def test_standalone_loaders_reject_invalid_selected_budget(limit):
    with pytest.raises(ValueError, match="max_bars"):
        pn.PyneData.from_ohlcv([bar(0)], max_bars=limit)
