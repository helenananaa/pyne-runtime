from __future__ import annotations

import pytest

from pyne_runtime import PyneSettings


def test_settings_reject_invalid_security_mode() -> None:
    with pytest.raises(ValueError, match="security_mode"):
        PyneSettings(security_mode="surprise")


def test_settings_reject_unknown_executor_mode() -> None:
    with pytest.raises(ValueError, match="executor_mode must be 'inline' or 'process'"):
        PyneSettings(executor_mode="typo")


def test_settings_reject_undeliverable_hard_timeout() -> None:
    with pytest.raises(ValueError, match="require_hard_timeout"):
        PyneSettings(executor_mode="inline", require_hard_timeout=True)

    settings = PyneSettings(executor_mode="process", require_hard_timeout=True)
    assert settings.require_hard_timeout is True
    assert settings.executor_mode == "process"


def test_from_env_reads_collection_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYNE_MAX_ARRAY_SIZE", "11")
    monkeypatch.setenv("PYNE_MAX_MAP_SIZE", "12")
    monkeypatch.setenv("PYNE_MAX_MATRIX_CELLS", "13")
    monkeypatch.setenv("PYNE_MAX_COLLECTION_DEPTH", "3")
    monkeypatch.setenv("PYNE_MAX_STRATEGY_PENDING_OPERATIONS", "14")
    monkeypatch.setenv("PYNE_TRACE_ENABLED", "true")
    monkeypatch.setenv("PYNE_TRACE_MAX_EVENTS", "15")
    monkeypatch.setenv("PYNE_TRACE_SPAN_EVENTS", "true")

    settings = PyneSettings.from_env()

    assert settings.max_array_size == 11
    assert settings.max_map_size == 12
    assert settings.max_matrix_cells == 13
    assert settings.max_collection_depth == 3
    assert settings.max_strategy_pending_operations == 14
    assert settings.trace_enabled is True
    assert settings.trace_max_events == 15
    assert settings.trace_span_events is True


def test_with_security_mode_preserves_all_existing_fields() -> None:
    provider = object()
    settings = PyneSettings(
        security_mode="safe",
        cache_max_items=7,
        trace_enabled=True,
        trace_max_events=9,
        trace_span_events=True,
        data_provider=provider,
        syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.25},
        timeframe="1h",
        session={"ismarket": False},
    )

    updated = settings.with_security_mode("research")

    assert updated.security_mode == "research"
    assert updated.cache_max_items == 7
    assert updated.trace_enabled is True
    assert updated.trace_max_events == 9
    assert updated.trace_span_events is True
    assert updated.data_provider is provider
    assert updated.syminfo.mintick == 0.25
    assert updated.timeframe.period == "1h"
    assert updated.session.ismarket is False
