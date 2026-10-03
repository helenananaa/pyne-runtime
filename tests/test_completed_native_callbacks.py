"""Previously missing native outputs through public Python execution contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.capabilities import INCREMENTAL_TA_CAPABILITIES

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'tests/workloads'
MAPPED = {
    'context_foundation': ['Donchian lower','Donchian middle','Donchian upper','Keltner lower','Keltner middle',
        'Keltner upper','Native KC lower','Native KC middle','Native KC upper','OBV','OBV holes'],
    'foundation': ['Momentum holes 3','NZ holes','NZ leading','ROC 1','ROC holes 3','ROC zeros 3',
        'Shift holes 3','Shift leading 2'],
    'oscillator_flat': ['CMO flat','CMO holes'],
    'extrema_order': ['Linear holes','Linreg holes','Nearest holes'],
    'smoothing': ['TSI'],
    'conditions_pivot': ['Falling 1','Falling 3','Falling holes','Rising 1','Rising 3','Rising holes'],
    'pivot_isolated_confirmation': ['Rising holes','Rising native'],
}
spec = importlib.util.spec_from_file_location('completed_callback_report',ROOT/'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs(name):
    capture = json.loads((FOLDER/f'{name}.tradingview.json').read_text(encoding='utf-8'))
    reporter.verify_evidence(FOLDER,name,capture)
    return (FOLDER/f'{name}.py').read_text(encoding='utf-8'),capture,reporter._bars(name,capture)


def assert_new_native(name,result,capture,bars,count,start=0):
    assert result.ok,result.error
    lines = {line['name']:{p['time']:p['value'] for p in line['data']} for line in result.lines}
    for title in MAPPED[name]:
        column = capture['columns'].index(title)
        expected = {bars[i]['time']:capture['rows'][i]['values'][column] for i in range(start,count)
                    if capture['rows'][i]['values'][column] is not None}
        assert lines.get(title,{})==pytest.approx(expected,abs=capture['tolerance'],rel=0),title


@pytest.mark.parametrize('name',MAPPED)
@pytest.mark.parametrize('count',(1,4,8,13))
def test_new_outputs_on_native_available_prefixes(name,count):
    script,capture,bars = inputs(name)
    assert_new_native(name,pn.run(script,bars[:count],executor_mode='inline'),capture,bars,count)


@pytest.mark.parametrize('name',MAPPED)
@pytest.mark.parametrize('mode',('local','replay','state'))
@pytest.mark.parametrize('cut',(4,13))
def test_native_preview_history_and_restore_continuation(name,mode,cut):
    script,capture,bars = inputs(name)
    original = pn.PyneIncrementalSession(script=script,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut],high=bars[cut]['high']+50.,low=bars[cut]['low']-50.,close=bars[cut]['close']+20.)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state()==before
    assert_new_native(name,original.snapshot_result(),capture,bars,cut)
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(),script=script) if mode=='local' else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode),script=script))
    assert restored.snapshot_state().context._states['_native_batch_ohlcv_history'].value==bars[:cut]
    restored_before = restored.snapshot_portable_state()
    restored.on_bar_updated(preview)
    assert restored.snapshot_portable_state()==restored_before
    for count,bar in enumerate(bars[cut:],cut+1):
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_new_native(name,restored.snapshot_result(),capture,bars,count)
    assert restored.snapshot_state().context._states['_native_batch_ohlcv_history'].value==bars


@pytest.mark.parametrize('name',MAPPED)
def test_retention_keeps_full_calculation_history(name):
    script,capture,bars = inputs(name)
    settings = pn.PyneSettings(executor_mode='inline',max_bars=2,incremental_retention_bars=3,replay_history_bars=3)
    original = pn.PyneIncrementalSession(script=script,settings=settings)
    original.seed(bars[:2])
    for bar in bars[2:13]:
        original.on_bar_closed(bar)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable_state(),script=script,
        settings=settings)
    for count,bar in enumerate(bars[13:],14):
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_new_native(name,restored.snapshot_result(),capture,bars,count,start=count-3)
    assert restored.snapshot_state().context._states['_native_batch_ohlcv_history'].value==bars


@pytest.mark.parametrize('name',MAPPED)
def test_all_added_outputs_are_measured_without_expanding_direct_api(name):
    result = reporter.workload_report(ROOT,name,dict(reporter.WORKLOADS)[name],True)
    assert result['unmappedOutputColumns']==[]
    assert result['recipeExecutionRoute']['sourceDeclaration']=='generic_python_full_history_recompute'
    assert result['recipeExecutionRoute']['boundedStepHelperQualified'] is False
    for title in MAPPED[name]:
        assert result['columns'][title]['counts']['cells']>0
        assert result['columns'][title]['counts']['differences']==0
    assert len(INCREMENTAL_TA_CAPABILITIES)==39
