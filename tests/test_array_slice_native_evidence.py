"""Native connected slice windows and independent runtime-state invariants."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneArray
from pyne_runtime.incremental.limits import _state_payload_items
from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'tests/workloads'
spec=importlib.util.spec_from_file_location('slice_native_report',ROOT/'scripts/official_alignment_report.py')
reporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
NAME='array_slice_reference'
CAPTURE=json.loads((FOLDER/f'{NAME}.tradingview.json').read_text(encoding='utf-8'))


def assert_native(result,count):
    assert result.ok,result.error
    bars=reporter._bars(NAME,CAPTURE)
    lines={line['name']:{p['time']:p['value'] for p in line['data']} for line in result.lines}
    for col,title in enumerate(CAPTURE['columns']):
        if title=='Case':
            continue
        expected={bars[i]['time']:CAPTURE['rows'][i]['values'][col] for i in range(count)
                  if CAPTURE['rows'][i]['values'][col] is not None}
        assert set(lines.get(title,{}))==set(expected),title
        assert lines.get(title,{})==pytest.approx(expected,abs=CAPTURE['tolerance']),title


def test_native_slice_complete_records_and_repeated_cycle():
    reporter.verify_evidence(FOLDER,NAME,CAPTURE)
    assert len(CAPTURE['rows'])==32 and len(CAPTURE['columns'])==31
    assert [r['values'] for r in CAPTURE['rows'][:16]]==[r['values'] for r in CAPTURE['rows'][16:]]


@pytest.mark.parametrize('callback',(False,True))
@pytest.mark.parametrize('count',(1,2,4,7,8,10,16,32))
def test_native_slice_complete_prefix_columns(callback,count):
    source=(FOLDER/f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source,reporter._bars(NAME,CAPTURE)[:count],executor_mode='inline'),count)


@pytest.mark.parametrize('mode',('local','replay','state'))
@pytest.mark.parametrize('cut',(1,8,16))
def test_native_slice_preview_restore_and_continue(mode,cut):
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


PERSISTENT='''
indicator("Persistent slice",mode="incremental")
def initialize():
    root=array.from_values(1,2,3,4,5,6,7)
    window=array.slice(root,1,4)
    nested=array.slice(window,1,3)
    return root,window,nested
def on_bar(ctx,bar):
    cell=ctx.state("arrays",initialize())
    root,window,nested=cell.value
    previous=cell[1]
    array.set(window,0,bar.close)
    array.set(nested,0,bar.close+10)
    ctx.plot("Root",array.get(root,1))
    ctx.plot("Window",array.get(window,0))
    ctx.plot("Root nested",array.get(root,2))
    ctx.plot("Nested",array.get(nested,0))
    ctx.plot("Previous root",array.get(previous[0],1) if previous is not None else None)
    ctx.plot("Previous window",array.get(previous[1],0) if previous is not None else None)
'''


@pytest.mark.parametrize('mode',('local','replay','state'))
def test_persistent_nested_slices_preserve_links_history_and_preview(mode):
    bars=[dict(time=i*60,open=i+1,high=i+2,low=i,close=i+1,volume=10) for i in range(8)]
    original=pn.PyneIncrementalSession(script=PERSISTENT,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:3])
    committed=original.snapshot_portable_state()
    preview=dict(bars[3],high=100,close=99)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state()==committed
    if mode=='local':
        restored=pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(),script=PERSISTENT)
    else:
        restored=pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode),script=PERSISTENT)
    restored.on_bar_updated(preview)
    for bar in bars[3:]:
        assert restored.on_bar_updated(bar)==original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
    result=restored.snapshot_result()
    assert result.ok,result.error
    values={line['name']:[p['value'] for p in line['data']] for line in result.lines}
    assert values['Root']==values['Window']==list(range(1,9))
    assert values['Root nested']==values['Nested']==list(range(11,19))
    assert values['Previous root']==values['Previous window']==list(range(1,8))


def test_view_mutation_cannot_bypass_parent_size_or_create_recursive_state():
    root=PyneArray(range(7),max_size=7)
    window=root.slice(1,4)
    nested=window.slice(1,3)
    before=(root.to_list(),window.to_list(),nested.to_list())
    with pytest.raises(PyneResourceLimitError):
        nested.push(8)
    assert (root.to_list(),window.to_list(),nested.to_list())==before
    with pytest.raises(PyneStateContractError):
        window.set(0,root)
    with pytest.raises(PyneStateContractError):
        root.set(0,window)
    assert (root.to_list(),window.to_list(),nested.to_list())==before
    window.set(0,88)
    assert root.get(1)==88


def test_small_view_payload_accounts_for_entire_retained_parent_once():
    root=PyneArray(["abcdefghij"]*7)
    window=root.slice(1,2)
    assert _state_payload_items(window)==_state_payload_items(root)+1


@pytest.mark.parametrize('mode',('local','replay','state'))
def test_restore_rebinds_hidden_parent_and_rejects_budget_below_parent_size(mode):
    script='''
indicator("View retained parent",mode="incremental")
def create():
    root=array.from_values(1,2,3,4,5,6,7)
    return array.slice(root,1,4)
def on_bar(ctx,bar):
    window=ctx.state("window",create()).value
    ctx.plot("Size",array.size(window))
'''
    original=pn.PyneIncrementalSession(script=script,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed([dict(time=0,open=1,high=2,low=0,close=1,volume=10)])
    before=original.snapshot_portable_state()
    if mode=='local':
        snapshot=original.snapshot_state()
        def restore(settings):
            return pn.PyneIncrementalSession.from_snapshot(snapshot,script=script,settings=settings)
    else:
        snapshot=original.snapshot_portable(mode=mode)
        def restore(settings):
            return pn.PyneIncrementalSession.from_portable_snapshot(snapshot,script=script,settings=settings)
    # Replay re-executes the recipe under its selected array admission policy;
    # local/state restore checks the retained object graph before adoption.
    error=PyneResourceLimitError if mode=='replay' else pn.PynePortableSnapshotError
    message='array size 7 exceeds limit 6' if mode=='replay' else 'collection size'
    with pytest.raises(error,match=message):
        restore(pn.PyneSettings(executor_mode='inline',max_array_size=6))
    assert original.snapshot_portable_state()==before
    fitted=restore(pn.PyneSettings(executor_mode='inline',max_array_size=7))
    window=fitted._ctx._states['window'].value
    with pytest.raises(PyneResourceLimitError):
        window.push(8)
    relaxed=restore(pn.PyneSettings(executor_mode='inline',max_array_size=8))
    relaxed._ctx._states['window'].value.push(8)
    assert relaxed._ctx._states['window'].value.to_list()==[2,3,4,8]


@pytest.mark.parametrize('corruption',('parent_type','negative_start','boolean_stop','reversed_bounds','parent_cycle','missing_parent'))
def test_malformed_slice_state_is_rejected_before_adoption(corruption):
    original=pn.PyneIncrementalSession(script=PERSISTENT,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed([dict(time=0,open=1,high=2,low=0,close=1,volume=10)])
    before=original.snapshot_portable_state()
    envelope=json.loads(before)
    nodes=envelope['payload']['stateGraph']['nodes']
    storage=next(node for node in nodes if node.get('type')=='pyne_runtime.collections:_ArraySliceStorage')
    attributes={pair[0]:pair for pair in storage['attributes']}
    if corruption=='parent_type':
        attributes['parent'][1]='abcdefghi'
    elif corruption=='negative_start':
        attributes['start'][1]=-1
    elif corruption=='boolean_stop':
        attributes['stop'][1]=True
    elif corruption=='reversed_bounds':
        attributes['stop'][1]=0
    elif corruption=='missing_parent':
        storage['attributes'].remove(attributes['parent'])
    else:
        parent=nodes[attributes['parent'][1]['$ref']]
        parent_values=next(pair for pair in parent['attributes'] if pair[0]=='_values')
        parent_values[1]={'$ref':nodes.index(storage)}
    payload=json.dumps(envelope['payload'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    envelope['checksum']='sha256:'+hashlib.sha256(payload).hexdigest()
    with pytest.raises(pn.PynePortableSnapshotError,match='array slice'):
        pn.PyneIncrementalSession.from_portable_snapshot(json.dumps(envelope),script=PERSISTENT)
    assert original.snapshot_portable_state()==before
    result=original.on_bar_closed(dict(time=60,open=2,high=3,low=1,close=2,volume=10))
    assert result is not None
