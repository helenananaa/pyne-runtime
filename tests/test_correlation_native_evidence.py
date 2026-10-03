"""Native missing-window witnesses plus independent state and numerical controls."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.capabilities import INCREMENTAL_TA_CAPABILITIES
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'tests/workloads'
NAMES = ('correlation_missing_diagnostic','correlation_window_holdout')
spec = importlib.util.spec_from_file_location('correlation_native_report',ROOT/'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
CONTROLS = dict(reporter.WORKLOADS)


def inputs(name,callback):
    capture = json.loads((FOLDER/f'{name}.tradingview.json').read_text())
    reporter.verify_evidence(FOLDER,name,capture)
    source = (FOLDER/f'{name}{"" if callback else "_batch"}.py').read_text()
    return source,capture,reporter._bars(name,capture)


def qualified_title(title):
    # The complete canonical comparison still counts every holdout column.
    # Large-offset native arithmetic and the shifted period-3/7 roundoff
    # witnesses remain disclosed strict gaps, independently of state checks.
    return not title.startswith(('Native hugeA ','Native hugeHole ')) and title not in (
        'Native holes shifted 3','Native holes shifted 7')


def assert_native(result,capture,bars,count,start=0):
    assert result.ok,result.error
    lines = {line['name']:{p['time']:p['value'] for p in line['data']} for line in result.lines}
    for column,title in enumerate(capture['columns']):
        if not title.startswith('Native ') or not qualified_title(title):
            continue
        expected = {bars[i]['time']:capture['rows'][i]['values'][column] for i in range(start,count)
                    if capture['rows'][i]['values'][column] is not None}
        assert lines.get(title,{})==pytest.approx(expected,abs=1e-8,rel=0),title


@pytest.mark.parametrize('name',NAMES)
@pytest.mark.parametrize('callback',(False,True))
@pytest.mark.parametrize('count',(1,2,4,8,13,32))
def test_native_available_prefixes(name,callback,count):
    source,capture,bars = inputs(name,callback)
    assert_native(pn.run(source,bars[:count],executor_mode='inline'),capture,bars,count)


@pytest.mark.parametrize('name',NAMES)
@pytest.mark.parametrize('mode',('local','replay','state'))
@pytest.mark.parametrize('cut',(4,13))
def test_native_preview_isolation_and_restore_continuation(name,mode,cut):
    source,capture,bars = inputs(name,True)
    original = pn.PyneIncrementalSession(script=source,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut],high=500.,low=0.,close=400.)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state()==before
    assert_native(original.snapshot_result(),capture,bars,cut)
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(),script=source) if mode=='local' else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode),script=source))
    restored_before = restored.snapshot_portable_state()
    restored.on_bar_updated(preview)
    assert restored.snapshot_portable_state()==restored_before
    assert_native(restored.snapshot_result(),capture,bars,cut)
    for count,bar in enumerate(bars[cut:],cut+1):
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(),capture,bars,count)


@pytest.mark.parametrize('callback',(False,True))
def test_all_native_outputs_and_unresolved_conditions_are_counted(callback):
    diagnostic = reporter.workload_report(ROOT,NAMES[0],CONTROLS[NAMES[0]],callback)
    assert len(diagnostic['columns'])==10 and diagnostic['unmappedOutputColumns']==[]
    assert sum(c['counts']['cells'] for c in diagnostic['columns'].values())==320
    assert sum(c['counts']['differences'] for c in diagnostic['columns'].values())==0
    holdout = reporter.workload_report(ROOT,NAMES[1],CONTROLS[NAMES[1]],callback)
    assert len(holdout['columns'])==32 and holdout['unmappedOutputColumns']==[]
    assert sum(c['counts']['cells'] for c in holdout['columns'].values())==1024
    assert holdout['columns']['Native hugeA hugeB 3']['counts']['differences']>0
    assert holdout['columns']['Native holes shifted 3']['counts']['differences']>0
    assert holdout['comparisonTolerance']==1e-8
    for title,column in holdout['columns'].items():
        if qualified_title(title):
            assert column['counts']['differences']==0,title
    if callback:
        assert holdout['recipeExecutionRoute']['boundedStepHelperQualified'] is False
        assert holdout['recipeExecutionRoute']['undeclaredDirectIncrementalMethodCandidates']==['correlation']


@pytest.mark.parametrize('name',NAMES)
def test_retention_does_not_truncate_computation_history(name):
    source,capture,bars = inputs(name,True)
    original = pn.PyneIncrementalSession(script=source,settings=pn.PyneSettings(executor_mode='inline',max_bars=2,
        incremental_retention_bars=3,replay_history_bars=3))
    original.seed(bars[:2])
    for bar in bars[2:13]:
        original.on_bar_closed(bar)
    assert original.snapshot_state().context._states['history'].value==[b['close'] for b in bars[:13]]
    restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable_state(),script=source,
        settings=original.settings)
    for count,bar in enumerate(bars[13:],14):
        before = original.snapshot_portable_state()
        restored_before = restored.snapshot_portable_state()
        original.on_bar_updated(bar)
        restored.on_bar_updated(bar)
        assert original.snapshot_portable_state()==before
        assert restored.snapshot_portable_state()==restored_before
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(),capture,bars,count,start=count-3)
    assert len(restored.snapshot_state().context._states['history'].value)==32


@pytest.mark.parametrize('mode',('replay','state'))
def test_actual_old_correlation_state_rejected_before_construction(mode,monkeypatch):
    folder = ROOT/'tests/golden/correlation_semantics_v29'
    provenance = json.loads((folder/'provenance.json').read_text())
    assert provenance['packageVersion']=='0.4.1rc24' and provenance['semanticsVersion']==29
    for name,digest in provenance['sha256'].items():
        assert hashlib.sha256((folder/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==digest
    envelope = json.loads((folder/f'{mode}.json').read_text())
    assert envelope['payload']['semanticsVersion']==29
    def forbidden(*args,**kwargs):
        pytest.fail('Old computation state must be rejected before constructing a session')
    monkeypatch.setattr(pn.PyneIncrementalSession,'__init__',forbidden)
    with pytest.raises(pn.PynePortableSnapshotError,match='rebuild.*OHLCV'):
        pn.PyneIncrementalSession.from_portable_snapshot((folder/f'{mode}.json').read_bytes(),
            script=(folder/'indicator.pyne').read_text())


def test_zero_denominator_requires_zero_numerator_and_ready_observations():
    module = TaModule()
    np.testing.assert_allclose(module.correlation(np.array([1.,np.nan,2.,np.nan]),np.array([1.,3.,2.,2.]),1),
        [0.,np.nan,0.,0.],equal_nan=True)
    assert np.isnan(module.correlation(np.full(8,np.nan),np.arange(8.),1)).all()
    assert np.isnan(module.correlation(np.arange(8.),np.full(8,np.nan),3)).all()
    np.testing.assert_allclose(module.correlation(np.ones(8),np.arange(8.),3),[np.nan,np.nan,0.,0.,0.,0.,0.,0.],equal_nan=True)


def test_one_observation_variance_is_exact_across_batch_and_prefixes():
    index = np.arange(32)
    base = ((index*11)%17-6.).astype(float)
    a = np.where(np.isin(index%7,[1,2]),np.nan,base)
    b = np.where(index%5==3,np.nan,-3*base+5)
    whole = np.asarray(TaModule().correlation(a,b,1))
    prefixes = [TaModule().correlation(a[:i+1],b[:i+1],1)[-1] for i in range(len(a))]
    np.testing.assert_allclose(whole,prefixes,equal_nan=True)
    assert np.all(whole[np.isfinite(whole)]==0.)


@pytest.mark.parametrize('gap',(False,True))
def test_infinity_does_not_poison_later_coherent_windows(gap):
    a = np.array([1.,2.,np.inf,4.,5.,6.,7.])
    if gap:
        a[1]=np.nan
    result = np.asarray(TaModule().correlation(a,np.arange(1.,8.)*2,2))
    assert np.isnan(result[2:4]).all()
    np.testing.assert_allclose(result[4:],[1.,1.,1.])


def test_input_lengths_and_direct_api_boundary():
    result = TaModule().correlation(np.arange(8.),np.arange(3.),2)
    np.testing.assert_allclose(result,[np.nan,1.,1.],equal_nan=True)
    assert len(INCREMENTAL_TA_CAPABILITIES)==39 and 'correlation' not in INCREMENTAL_TA_CAPABILITIES
