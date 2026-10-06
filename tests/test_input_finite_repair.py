"""Non-finite scalar parameters cannot bypass input admission."""
import json

import pytest

import pyne_runtime as pn
from pyne_runtime.input import InputModule, PyneInputError


BARS = [dict(time=1, open=1, high=1, low=1, close=1, volume=1)]


@pytest.mark.parametrize("kind", ["float", "price"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "nan", "inf", "-inf", "1e999", 10**400])
def test_nonfinite_override_is_rejected_by_public_run(kind, value):
    bounds = ', minval=0, maxval=2' if kind == 'float' else ''
    result = pn.run(f'x = input.{kind}(1, "Value"{bounds})\nplot(close * x)', BARS,
                    params={"Value": value}, executor_mode="inline")
    assert not result.ok
    assert result.code == "PYNE_INVALID_PARAM"


@pytest.mark.parametrize("kind", ["float", "price"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_invalid_default_is_rejected(kind, value):
    module = InputModule()
    with pytest.raises(PyneInputError, match="finite"):
        getattr(module, kind)(value, "Value")


@pytest.mark.parametrize("value", [0, 1.5, " 1.5 ", 2])
def test_valid_override_keeps_bounds_and_json_safe_schema(value):
    result = pn.run('x = input.float(1, "Value", minval=0, maxval=2)\nplot(close * x, "X")',
                    BARS, params={"Value": value}, executor_mode="inline")
    assert result.ok, result.error
    assert result.values("X") == [float(value)]
    json.dumps(result.param_schema, allow_nan=False)


@pytest.mark.parametrize("field", ["defval", "minval", "maxval", "step"])
def test_nonfinite_declaration_cannot_leak_into_success_schema(field):
    module = InputModule({"Value": 1})
    with pytest.raises(PyneInputError, match="finite"):
        module.float(title="Value", **{field: float("nan")})


def test_invalid_input_recovery_does_not_publish_a_current_value():
    module = InputModule({"Bad": "nan", "Good": 1.25})
    with pytest.raises(PyneInputError):
        module.float(1, "Bad", minval=0, maxval=2)
    assert not module.schema
    assert module.float(1, "Good", minval=0, maxval=2) == 1.25


@pytest.mark.parametrize("kind,default,invalid,valid,options", [
    ("int", 1, "bad", 2, {}),
    ("float", 1, "nan", 1.25, {"minval": 0, "maxval": 2}),
    ("price", 1, float("inf"), 1.25, {}),
    ("bool", True, "bad", False, {}),
    ("string", "x", 1, "y", {}),
    ("color", "blue", 1, "red", {}),
    ("timeframe", "60", "bad", "120", {"options": ["60", "120"]}),
    ("symbol", "A", "bad", "B", {"options": ["A", "B"]}),
    ("enum", "dark", "bad", "light", {"options": ["dark", "light"]}),
    ("time", 0, -1, 10, {}),
    ("text_area", "x", 1, "y", {}),
])
def test_failed_declaration_does_not_consume_key_or_bypass_override(kind, default, invalid, valid, options):
    params = {"P": invalid}
    module = InputModule(params)
    for _ in range(2):
        with pytest.raises(PyneInputError):
            getattr(module, kind)(default, "P", **options)
        assert module.schema == []
    params["P"] = valid
    assert getattr(module, kind)(default, "P", **options) == valid
    assert [entry["key"] for entry in module.schema] == ["P"]
