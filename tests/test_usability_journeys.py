"""User-visible diagnostics, validation targets and CLI/API parity."""

import json
from pathlib import Path

import pytest
import pyne_runtime as pn
from pyne_runtime.cli import main


DATA = Path(__file__).parents[1] / "examples" / "sample_ohlcv.csv"
BARS = [dict(time=1, open=1, high=2, low=1, close=1.5, volume=1)]
CLASS_SCRIPT = """class Helper:
    value = 1

def on_bar(ctx, bar):
    ctx.plot("Value", Helper.value)
"""


def test_resource_diagnostics_offer_configuration_not_permission_changes():
    result = pn.run("array.new_float(3, 0)", BARS, settings=pn.PyneSettings(max_array_size=2))
    assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    assert "None" in result.hint
    assert "permission-mode change" in result.hint
    assert result.error_detail["docsUrl"].endswith("pyne-resource-limit-exceeded")
    result = pn.run("plot(close)", BARS, settings=pn.PyneSettings(max_bars=1))
    assert result.ok
    result = pn.run(
        "plot(close)", BARS + [dict(BARS[0], time=2)], settings=pn.PyneSettings(max_bars=1)
    )
    assert result.code == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    assert "max_bars" in result.hint


@pytest.mark.parametrize("target", ["preview", "snapshot"])
def test_target_validation_explains_module_class_without_banning_batch(target):
    assert pn.validate(CLASS_SCRIPT) == []
    assert pn.run(CLASS_SCRIPT, BARS).ok
    diagnostics = pn.validate(CLASS_SCRIPT, target=target)
    assert diagnostics[0]["code"] == "PYNE_STATE_CONTRACT_ERROR"
    assert diagnostics[0]["line"] == 1
    assert "ctx.state" in diagnostics[0]["hint"]
    corrected = "def on_bar(ctx, bar):\n    ctx.plot('Value', ctx.state('value', 1).value)"
    assert pn.validate(corrected, target=target) == []


def test_state_exception_has_actionable_code_and_hint():
    session = pn.PyneIncrementalSession(script=CLASS_SCRIPT)
    session.seed(BARS)
    with pytest.raises(pn.PyneStateContractError) as caught:
        session.snapshot_state()
    assert isinstance(caught.value, pn.PyneSecurityError)  # Existing catches remain valid.
    assert caught.value.code == "PYNE_STATE_CONTRACT_ERROR"
    assert "batch" in caught.value.hint


def test_explicit_incremental_validation_requires_callback_but_allows_dynamic_binding():
    diagnostics = pn.validate("plot(close)", runtime_mode="incremental")
    assert any("on_bar" in item["message"] for item in diagnostics)
    source = (
        "def factory():\n    return lambda ctx, bar: ctx.plot('C', bar.close)\non_bar = factory()"
    )
    assert pn.validate(source, runtime_mode="incremental") == []


def test_validation_never_executes_the_script(tmp_path):
    marker = tmp_path / "must-not-exist"
    source = f"open({str(marker)!r}, 'w').write('executed')\n" + CLASS_SCRIPT
    assert pn.validate(source, target="preview")
    assert not marker.exists()


def test_cli_validation_and_run_share_import_policy(tmp_path, capsys):
    script = tmp_path / "math.py"
    script.write_text("import math\nplot(close + math.sqrt(4))")
    assert main(["validate", str(script), "--security-mode", "safe"]) == 1
    assert json.loads(capsys.readouterr().out)["diagnostics"][0]["code"] == "PYNE_IMPORT_BLOCKED"
    policy = ["--security-mode", "research", "--allowed-import", "math"]
    assert main(["validate", str(script), *policy]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["run", str(script), "--ohlcv", str(DATA), *policy]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_cli_target_and_malformed_settings_are_structured(tmp_path, capsys):
    script = tmp_path / "state.py"
    script.write_text(CLASS_SCRIPT)
    assert main(["validate", str(script), "--target", "snapshot"]) == 1
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["code"] == "PYNE_STATE_CONTRACT_ERROR"
    )
    assert main(["validate", str(script), "--limit", "made_up=1"]) == 2
    detail = json.loads(capsys.readouterr().err)["error"]
    assert detail["code"] == "PYNE_CLI_INPUT_ERROR"
    assert "Available:" in detail["message"] and detail["hint"]


def test_cli_can_remove_environment_budgets_without_switching_permissions(
    tmp_path, capsys, monkeypatch
):
    script = tmp_path / "close.py"
    script.write_text("plot(close)")
    monkeypatch.setenv("PYNE_MAX_BARS", "1")
    assert main(["run", str(script), "--ohlcv", str(DATA)]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "PYNE_RESOURCE_LIMIT_EXCEEDED"
    assert (
        main(
            [
                "run",
                str(script),
                "--ohlcv",
                str(DATA),
                "--limit",
                "max_bars=none",
                "--timeout-seconds",
                "none",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"]


def test_csv_selection_ignores_unselected_duplicate_names(tmp_path, capsys):
    script = tmp_path / "plots.py"
    script.write_text("plot(close, 'Keep')\nplot(open, 'Other')\nplot(high, 'Other')")
    assert (
        main(["run", str(script), "--ohlcv", str(DATA), "--format", "csv", "--series", "Keep"]) == 0
    )
    assert capsys.readouterr().out.startswith("time,Keep\n")
    assert (
        main(["run", str(script), "--ohlcv", str(DATA), "--format", "csv", "--series", "Other"])
        == 2
    )
    assert "unique" in json.loads(capsys.readouterr().err)["error"]["message"]
    assert (
        main(["run", str(script), "--ohlcv", str(DATA), "--format", "csv", "--series", "Missing"])
        == 2
    )
    assert "Available: Keep" in json.loads(capsys.readouterr().err)["error"]["message"]


def test_failed_json_run_preserves_last_successful_file(tmp_path, capsys):
    script = tmp_path / "bad.py"
    script.write_text("raise ValueError('fix this')")
    output = tmp_path / "result.json"
    output.write_text('{"previous": true}')
    assert main(["run", str(script), "--ohlcv", str(DATA), "--out", str(output)]) == 1
    assert output.read_text() == '{"previous": true}'
    assert json.loads(capsys.readouterr().err)["code"] == "PYNE_RUNTIME_ERROR"


def test_long_inline_script_and_json_params_are_not_mistaken_for_paths(tmp_path, capsys):
    assert pn.validate("x = 1; " * 100 + "plot(close)") == []
    script = tmp_path / "long.py"
    script.write_text("plot(close)")
    assert (
        main(
            [
                "run",
                str(script),
                "--ohlcv",
                str(DATA),
                "--params-json",
                json.dumps({"long_name": "x" * 1000}),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"]


@pytest.mark.parametrize("replacement", ["del Helper", "Helper = 1"])
def test_preflight_does_not_block_discarded_classes(replacement):
    source = (
        "class Helper: pass\n" + replacement + "\ndef on_bar(ctx, bar): ctx.plot('C', bar.close)"
    )
    assert pn.validate(source, target="snapshot") == []
    session = pn.PyneIncrementalSession(script=source)
    session.seed(BARS)
    assert session.snapshot_portable_state()


def test_preflight_tracks_class_aliases_and_leaves_dynamic_bindings_to_runtime():
    source = "class Helper: pass\nAlias = Helper\ndel Helper\ndef on_bar(ctx, bar): pass"
    assert "Alias" in pn.validate(source, target="preview")[0]["message"]
    source = "from somewhere import on_bar"
    assert pn.validate(source, runtime_mode="incremental") == []
    assert pn.validate("globals()['on_bar'] = lambda ctx, bar: None", target="preview") == []


def test_error_documentation_contains_every_linked_anchor():
    from pyne_runtime.errors import ERROR_DOCS
    docs = (Path(__file__).parents[1] / "docs" / "reference" / "error_codes.md").read_text(encoding="utf-8")
    for url in ERROR_DOCS.values():
        anchor = url.split("#", 1)[1]
        assert f'id="{anchor}"' in docs
