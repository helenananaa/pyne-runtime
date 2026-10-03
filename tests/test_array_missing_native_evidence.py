"""Native numeric array order, missing placement and continuation evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneArray

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'tests/workloads'
spec=importlib.util.spec_from_file_location('array_native_report',ROOT/'scripts/official_alignment_report.py')
reporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
NAME='array_missing_sort'
CAPTURE=json.loads((FOLDER/f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
CONTROLS={'Case',*(f'Original {i}' for i in range(5))}


def assert_native(result,count):
    assert result.ok,result.error
    bars=reporter._bars(NAME,CAPTURE)
    lines={line['name']:{point['time']:point['value'] for point in line['data']} for line in result.lines}
    for col,title in enumerate(CAPTURE['columns']):
        if title in CONTROLS:
            continue
        expected={bars[i]['time']:CAPTURE['rows'][i]['values'][col] for i in range(count) if CAPTURE['rows'][i]['values'][col] is not None}
        assert set(lines.get(title,{}))==set(expected),title
        assert lines.get(title,{})==pytest.approx(expected,abs=CAPTURE['tolerance']),title


def test_native_array_rows_and_hashes_are_complete():
    reporter.verify_evidence(FOLDER,NAME,CAPTURE)
    assert len(CAPTURE['rows'])==16 and len(CAPTURE['columns'])==35
    assert [r['values'] for r in CAPTURE['rows'][:8]]==[r['values'] for r in CAPTURE['rows'][8:]]
    for row in CAPTURE['rows']:
        assert row['values'][-4:]==[1,1,1,1]
        ascending=row['values'][21:26]
        descending=row['values'][26:31]
        size=int(row['values'][1])
        assert descending[:size]==list(reversed(ascending[:size]))


@pytest.mark.parametrize('callback',(False,True))
@pytest.mark.parametrize('count',(1,2,3,5,6,8,16))
def test_native_array_complete_prefix_columns(callback,count):
    source=(FOLDER/f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source,reporter._bars(NAME,CAPTURE)[:count],executor_mode='inline'),count)


@pytest.mark.parametrize('mode',('local','replay','state'))
@pytest.mark.parametrize('cut',(1,4,8))
def test_native_array_preview_restore_and_continue(mode,cut):
    source=(FOLDER/f'{NAME}.py').read_text(encoding='utf-8')
    bars=reporter._bars(NAME,CAPTURE)
    original=pn.PyneIncrementalSession(script=source,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before=original.snapshot_portable_state()
    preview=dict(bars[cut],high=500,low=0,close=400)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state()==before
    if mode=='local':
        restored=pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(),script=source)
    else:
        restored=pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode),script=source)
    restored.on_bar_updated(preview)
    for count,bar in enumerate(bars[cut:],cut+1):
        assert restored.on_bar_updated(bar)==original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(),count)


@pytest.mark.parametrize('values',([3,'x',2,1],[3,None,'x',2]))
def test_incomparable_sort_failure_preserves_original_array(values):
    array=PyneArray(values)
    before=array.to_list()
    with pytest.raises(TypeError):
        array.sort()
    assert array.to_list()==before


@pytest.mark.parametrize('descending',(False,True))
def test_none_and_nan_use_same_missing_sort_policy(descending):
    values=PyneArray([3,None,1,float('nan'),2])
    indices=values.sort_indices(reverse=descending).to_list()
    assert indices==([3,1,0,4,2] if descending else [2,4,0,1,3])
    values.sort(reverse=descending)
    numeric=[value for value in values if value is not None and value==value]
    assert numeric==([3,2,1] if descending else [1,2,3])
