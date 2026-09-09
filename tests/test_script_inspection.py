from __future__ import annotations

import json
from pathlib import Path

import pyne_runtime as pn

from pyne_runtime.cli import main


def test_inspect_script_reports_mode_requirements_and_host_contracts() -> None:
    source = """
indicator("Demand", mode="incremental")

def on_preview(ctx, bar):
    ctx.trace.emit("preview")

def on_bar(ctx, bar):
    total = ctx.state("total", 0.0)
    total.value += bar.close
    ctx.plot("Fast", ctx.ta.ema("fast", 3).update(bar.close))
    ctx.plot("Remote", ctx.request.security("TEST", "1D", "close"))
    ctx.strategy.entry("L", ctx.strategy.long, qty=1)
    ctx.line_new(bar.bar_index, bar.low, bar.bar_index, bar.high)
"""

    report = pn.inspect_script(source)

    assert report["schemaVersion"] == pn.PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION
    assert report["runtimeMode"] == "incremental"
    assert report["declaration"] == {"kind": "indicator", "title": "Demand"}
    assert report["callbacks"] == ["on_bar", "on_preview"]
    assert report["requirements"]["ta"] == ["ema"]
    assert report["requirements"]["request"] == ["security"]
    assert report["requirements"]["strategy"] == ["entry"]
    assert report["requirements"]["drawings"] == ["line"]
    assert report["requirements"]["host"] == ["dataProvider"]
    assert report["resourceHints"]["usesState"] is True
    assert report["resourceHints"]["usesPreview"] is True
    assert report["resourceHints"]["usesTrace"] is True
    assert report["resourceHints"]["minimumHistoryBars"] == 3
    assert report["resourceHints"]["statefulTaInstances"] == 1
    assert report["providerRequirements"] == [
        {
            "api": "request.security",
            "symbol": "TEST",
            "timeframe": "1D",
            "dynamicSymbol": False,
            "dynamicTimeframe": False,
            "line": 11,
        }
    ]
    assert report["outputRequirements"]["outputSchemaVersion"] == pn.PYNE_OUTPUT_SCHEMA_VERSION
    assert report["outputRequirements"]["strategyReportSchemaVersion"] == (
        pn.PYNE_STRATEGY_REPORT_SCHEMA_VERSION
    )
    assert report["migration"]["batchToIncremental"]["eligible"] is True
    assert report["compatibility"]["supported"] is True
    assert source not in json.dumps(report)


def test_inspect_script_fails_closed_for_unsupported_and_dynamic_members() -> None:
    report = pn.inspect_script(
        """
indicator("Unsupported", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("TSI", ctx.ta.tsi("tsi", 13, 25).update(bar.close))
    helper = getattr(ctx.ta, params["helper"])
    ctx.plot("Dynamic", helper("x", 2).update(bar.close))
"""
    )

    assert report["compatibility"]["supported"] is False
    assert any("ta.tsi" in item["message"] for item in report["compatibility"]["diagnostics"])
    assert report["compatibility"]["dynamicAccesses"] == [
        {
            "namespace": "ta",
            "line": 5,
            "column": 14,
            "reason": "dynamic-member-name",
        }
    ]


def test_inspect_script_reports_pinned_library_members_and_mode_boundary() -> None:
    source = """
indicator("Library")
plot(pine_library("TradingView/ta/10").changePercent(close, open), "Change")
plot(pine_library("TradingView/ta/10").missing(close), "Missing")
"""
    report = pn.inspect_script(source)
    library = report["requirements"]["externalLibraries"][0]

    assert library["identifier"] == "TradingView/ta/10"
    assert library["supportedMembers"] == ["changePercent"]
    assert library["unsupportedMembers"] == ["missing"]
    assert report["compatibility"]["supported"] is False


def test_inspect_script_only_reports_host_data_for_members_that_need_it() -> None:
    pure = pn.inspect_script(
        'plot(pine_library("TradingView/ta/10").ema2(close, 3), "EMA")'
    )
    requested = pn.inspect_script(
        'plot(pine_library("TradingView/ta/10").requestVolumeDelta("1", "D"), "CVD")'
    )

    assert pure["requirements"]["externalLibraries"][0]["dataRequirements"] == []
    assert requested["requirements"]["externalLibraries"][0]["dataRequirements"] == [
        "request.security_lower_tf"
    ]


def test_inspect_cli_prints_machine_readable_manifest(tmp_path: Path, capsys) -> None:
    script = tmp_path / "indicator.py"
    script.write_text('indicator("CLI")\nplot(ta.sma(close, 2), "SMA")\n', encoding="utf-8")

    exit_code = main(["inspect", str(script)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["runtimeMode"] == "batch"
    assert payload["requirements"]["ta"] == ["sma"]


def test_inspect_path_scans_directory_and_summarizes_migration_blockers(
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "first.py").write_text(
        'indicator("First")\nplot(ta.sma(close, 5), "SMA")\n',
        encoding="utf-8",
    )
    (tmp_path / "nested" / "second.py").write_text(
        'indicator("Second")\nplot(ta.tsi(close, 13, 25), "TSI")\n',
        encoding="utf-8",
    )

    report = pn.inspect_path(tmp_path, recursive=True)

    assert report["schemaVersion"] == pn.PYNE_SCRIPT_DIRECTORY_INSPECTION_SCHEMA_VERSION
    assert report["summary"]["scriptCount"] == 2
    assert report["summary"]["batchToIncrementalBlockerCount"] == 1
    assert [item["path"] for item in report["scripts"]] == ["first.py", "nested/second.py"]

    exit_code = main(["inspect", str(tmp_path), "--recursive"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["scriptCount"] == 2


def test_inspect_path_reports_per_file_inspector_v2_migration_surface(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text(
        'indicator("First")\nplot(ta.sma(close, 5), "SMA")\n',
        encoding="utf-8",
    )
    (tmp_path / "blocked.py").write_text(
        'indicator("Second", mode="incremental")\n'
        "def on_bar(ctx, bar):\n"
        '    ctx.plot("TSI", ctx.ta.tsi("tsi", 13, 25).update(bar.close))\n',
        encoding="utf-8",
    )

    report = pn.inspect_path(tmp_path, recursive=False, runtime_mode="incremental")
    serialized = json.dumps(report)

    assert report["summary"]["scriptCount"] == 2
    assert 'indicator("First")' not in serialized
    assert 'def on_bar(ctx, bar):' not in serialized
    by_path = {item["path"]: item["report"] for item in report["scripts"]}
    for item in by_path.values():
        assert "supported" in item["compatibility"]
        assert "dynamicAccesses" in item["compatibility"]
        assert "host" in item["requirements"]
        assert "externalLibraries" in item["requirements"]
        assert "minimumHistoryBars" in item["resourceHints"]
        assert "batchToIncremental" in item["migration"]
    assert by_path["ok.py"]["compatibility"]["supported"] is True
    assert by_path["blocked.py"]["compatibility"]["supported"] is False
    assert by_path["blocked.py"]["requirements"]["ta"] == ["tsi"]


def test_inspector_v2_marks_dynamic_history_and_provider_inputs_unknown() -> None:
    report = pn.inspect_script(
        """
indicator("Dynamic")
length = input.int(14)
symbol = input.symbol("TEST")
plot(ta.sma(close, length), "Dynamic SMA")
plot(request.security(symbol, timeframe.period, "close"), "Remote")
"""
    )

    assert report["resourceHints"]["historyIsDynamic"] is True
    assert report["providerRequirements"][0]["dynamicSymbol"] is True
    assert report["providerRequirements"][0]["dynamicTimeframe"] is True


def test_inspector_v2_uses_ta_signatures_for_history_hints() -> None:
    batch = pn.inspect_script(
        """
indicator("Signature lookbacks")
plot(ta.supertrend(2, 10)[0], "ST")
plot(ta.macd(close, 12, 26, 9)[0], "MACD")
plot(ta.stoch(close, high, low, 14), "Stoch")
plot(ta.adx(high, low, close, 20), "ADX")
plot(ta.dmi(14, 10)[2], "DMI")
"""
    )
    incremental = pn.inspect_script(
        """
indicator("Incremental signatures", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("ST", ctx.ta.supertrend("st", 2, 10).update(bar.high, bar.low, bar.close)[0])
    ctx.plot("MACD", ctx.ta.macd("macd", 12, 26, 9).update(bar.close)[0])
    ctx.plot("ADX", ctx.ta.adx("adx", 14, 10).update(bar.high, bar.low, bar.close))
"""
    )

    assert batch["resourceHints"]["minimumHistoryBars"] == 34
    assert batch["resourceHints"]["historyIsDynamic"] is False
    assert incremental["resourceHints"]["minimumHistoryBars"] == 34
    assert incremental["resourceHints"]["historyIsDynamic"] is False
    assert incremental["resourceHints"]["statefulTaInstances"] == 3


def test_inspect_script_exposes_advisory_series_ternary_without_blocking_compatibility() -> None:
    source = """
indicator("ADX")
dm_plus = high - high[1] if high - high[1] > low[1] - low else 0
"""
    expected = next(
        item
        for item in pn.validate(source)
        if item["code"] == "PYNE_MIGRATION_HINT"
    )
    report = pn.inspect_script(source)
    serialized = json.dumps(report)

    assert report["schemaVersion"] == 2
    assert report["compatibility"]["supported"] is True
    assert report["compatibility"]["diagnostics"] == []
    assert report["migration"]["batchToIncremental"]["eligible"] is True
    assert source not in serialized
    advisory = report["migration"]["diagnostics"]
    assert advisory
    assert advisory[0]["code"] == expected["code"]
    assert advisory[0]["message"] == expected["message"]
    assert advisory[0]["line"] == expected["line"]
    assert advisory[0]["hint"] == expected["hint"]


def test_inspect_script_does_not_advise_scalar_bar_close_or_when_expressions() -> None:
    scalar = pn.inspect_script(
        """
indicator("Scalar", mode="incremental")
def on_bar(ctx, bar):
    if bar.close > 0:
        ctx.plot("Close", bar.close)
"""
    )
    corrected = pn.inspect_script(
        """
indicator("When")
plot(when(close > open, high, low), "Range")
"""
    )

    assert scalar["compatibility"]["supported"] is True
    assert scalar["migration"]["diagnostics"] == []
    assert scalar["migration"]["batchToIncremental"]["eligible"] is True
    assert corrected["compatibility"]["supported"] is True
    assert corrected["migration"]["diagnostics"] == []


def test_advisory_does_not_block_legitimate_shadowed_series_name():
    source = 'indicator("Scalar")\nclose = 3\nif close > 0:\n    plot(1, "Scalar")\n'
    report = pn.inspect_script(source)
    assert report["migration"]["diagnostics"] == pn.validate(source)
    assert report["migration"]["diagnostics"]
    assert report["compatibility"]["supported"] is True
    assert report["migration"]["batchToIncremental"]["eligible"] is True
    result = pn.run(source, [{"time": 1, "open": 1, "high": 2, "low": 0, "close": 1,
                              "volume": 1}], executor_mode="inline")
    assert result.ok, result.error


def test_inspect_script_syntax_error_keeps_advisory_array_from_hint() -> None:
    source = "indicator('Broken')\nvalues = array.from(1, 2, 3)\n"
    expected = next(
        item
        for item in pn.validate(source)
        if item["code"] == "PYNE_MIGRATION_HINT"
    )
    report = pn.inspect_script(source)
    serialized = json.dumps(report)

    assert report["compatibility"]["supported"] is False
    assert any(item["code"] == "PYNE_SYNTAX_ERROR" for item in report["compatibility"]["diagnostics"])
    advisory = report["migration"]["diagnostics"]
    assert advisory
    assert advisory[0]["code"] == expected["code"]
    assert advisory[0]["message"] == expected["message"]
    assert advisory[0]["line"] == expected["line"]
    assert advisory[0]["hint"] == expected["hint"]
    assert source not in serialized
    assert "array.from(1, 2, 3)" not in serialized


def test_inspector_v2_marks_dynamic_signature_arguments_unknown() -> None:
    report = pn.inspect_script(
        """
indicator("Dynamic signature")
length = input.int(14)
plot(ta.supertrend(2, length)[0], "ST")
plot(ta.macd(close, 12, 26, length)[0], "MACD")
"""
    )

    assert report["resourceHints"]["historyIsDynamic"] is True
