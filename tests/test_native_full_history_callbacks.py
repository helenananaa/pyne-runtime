"""Full Python callbacks measured against complete retained TradingView logs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.capabilities import INCREMENTAL_TA_CAPABILITIES

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAMES = ('percentile_history_context', 'percentile_insertion_matrix', 'percentile_missing_sort',
         'percentile_confirmation', 'direction_missing', 'direction_transition_confirmation')
spec = importlib.util.spec_from_file_location('full_history_callback_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
CONTROLS = dict(reporter.WORKLOADS)


def inputs(name):
    capture = json.loads((FOLDER / f'{name}.tradingview.json').read_text(encoding='utf-8'))
    reporter.verify_evidence(FOLDER, name, capture)
    source = (FOLDER / f'{name}.py').read_text(encoding='utf-8')
    return source, capture, reporter._bars(name, capture)


def assert_native(name, result, capture, bars, count, start=0):
    assert result.ok, result.error
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    for column, title in enumerate(capture['columns']):
        if title in CONTROLS[name]:
            continue
        expected = {bars[i]['time']: capture['rows'][i]['values'][column] for i in range(start, count)
                    if capture['rows'][i]['values'][column] is not None}
        actual = lines.get(title, {})
        assert set(actual) == set(expected), title
        assert actual == pytest.approx(expected, abs=capture['tolerance'], rel=0), title


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('count', (1, 4, 8, 13))
def test_native_callback_prefixes_use_available_history(name, count):
    source, capture, bars = inputs(name)
    assert_native(name, pn.run(source, bars[:count], executor_mode='inline'), capture, bars, count)


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (4, 13))
def test_native_callback_preview_and_restore_full_continuation(name, mode, cut):
    source, capture, bars = inputs(name)
    original = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut], high=500., low=0., close=400.)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    assert_native(name, original.snapshot_result(), capture, bars, cut)
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source)
    assert restored.snapshot_state().context._states['history'].value == [bar['close'] for bar in bars[:cut]]
    rebound_before = restored.snapshot_portable_state()
    restored.on_bar_updated(preview)
    assert restored.snapshot_portable_state() == rebound_before
    assert_native(name, restored.snapshot_result(), capture, bars, cut)
    for count, bar in enumerate(bars[cut:], cut+1):
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
        assert_native(name, restored.snapshot_result(), capture, bars, count)


@pytest.mark.parametrize('name', NAMES)
def test_native_all_missing_callbacks_are_measured_by_executed_calls(name):
    source, capture, bars = inputs(name)
    result = reporter.workload_report(ROOT, name, CONTROLS[name], True)
    assert result['status'] == 'measured' and result['unmappedOutputColumns'] == []
    expected_titles = set(capture['columns']) - CONTROLS[name]
    assert set(result['columns']) == set(result['executedCallbackPlotCalls']) == expected_titles
    assert sum(col['counts']['differences'] for col in result['columns'].values()) == 0
    assert all(call['calls'] == len(bars) for call in result['executedCallbackPlotCalls'].values())
    assert result['recipeExecutionRoute'] == reporter.recipe_execution_route(source)
    assert result['recipeExecutionRoute']['boundedStepHelperQualified'] is False
    candidates = ['falling','rising'] if name.startswith('direction_') else ['percentile_linear_interpolation','percentile_nearest_rank']
    assert result['recipeExecutionRoute']['undeclaredDirectIncrementalMethodCandidates'] == candidates


def test_measured_callbacks_do_not_expand_declared_direct_incremental_api():
    assert not {'rising', 'falling', 'percentile_nearest_rank', 'percentile_linear_interpolation'} & set(INCREMENTAL_TA_CAPABILITIES)
    assert len(INCREMENTAL_TA_CAPABILITIES) == 39


@pytest.mark.parametrize('name', NAMES)
def test_callback_history_survives_explicit_display_and_replay_retention(name):
    source, capture, bars = inputs(name)
    settings = pn.PyneSettings(executor_mode='inline', max_bars=2,
                               incremental_retention_bars=3, replay_history_bars=3)
    original = pn.PyneIncrementalSession(script=source, settings=settings)
    original.seed(bars[:2])
    cut = len(bars)//2
    for bar in bars[2:cut]:
        original.on_bar_closed(bar)
    assert original.snapshot_state().context._states['history'].value == [bar['close'] for bar in bars[:cut]]
    assert_native(name, original.snapshot_result(), capture, bars, cut, cut-3)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable_state(),
                                                              script=source, settings=settings)
    original_before = original.snapshot_portable_state()
    before = restored.snapshot_portable_state()
    preview = dict(bars[cut],high=500.,low=0.,close=400.)
    original.on_bar_updated(preview)
    restored.on_bar_updated(preview)
    assert original.snapshot_portable_state() == original_before
    assert restored.snapshot_portable_state() == before
    for bar in bars[cut:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    assert restored.snapshot_state().context._states['history'].value == [bar['close'] for bar in bars]
    assert_native(name, restored.snapshot_result(), capture, bars, len(bars), len(bars)-3)


@pytest.mark.parametrize('value', ('"direct_streaming_helper"', 'compute_route()'))
def test_route_declaration_rejects_unproved_streaming_claims(value):
    with pytest.raises(ValueError, match='execution-route declaration'):
        reporter.recipe_execution_route('NATIVE_RECIPE_EXECUTION_ROUTE = '+value)
