"""Native singleton dispersion plus independent numerical and state contracts."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepSMA, _StepStdev, _StepVariance
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'tests/workloads'
NAME = 'dispersion_single_observation'
spec = importlib.util.spec_from_file_location('single_dispersion_report',ROOT/'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs(callback):
    capture = json.loads((FOLDER/f'{NAME}.tradingview.json').read_text())
    reporter.verify_evidence(FOLDER,NAME,capture)
    script = (FOLDER/f'{NAME}{"" if callback else "_batch"}.py').read_text()
    return script,capture,reporter._bars(NAME,capture)


def assert_native(result,capture,bars,count,start=0):
    assert result.ok,result.error
    actual = {line['name']:{p['time']:p['value'] for p in line['data']} for line in result.lines}
    for index,title in enumerate(capture['columns'][8:],8):
        expected = {bars[i]['time']:capture['rows'][i]['values'][index] for i in range(start,count)
                    if capture['rows'][i]['values'][index] is not None}
        assert actual.get(title,{})==pytest.approx(expected,abs=1e-8,rel=0),title


def test_native_inputs_are_independently_generated():
    script,capture,_ = inputs(False)
    tree = ast.parse(script)
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='sources')
    namespace = {'np':np}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<input generator>','exec'),namespace)
    values = namespace['sources'](32)
    assert len(values)==8
    for index,title in enumerate(capture['columns'][:8]):
        official = np.array([np.nan if row['values'][index] is None else row['values'][index]
                             for row in capture['rows']])
        np.testing.assert_allclose(values[title],official,rtol=0,atol=1e-14,equal_nan=True)
    # Official sample variance with a zero degrees-of-freedom denominator is
    # never fabricated as zero, even where population dispersion is ready.
    for index,title in enumerate(capture['columns']):
        if title.startswith('Sample '):
            assert all(row['values'][index] is None for row in capture['rows'])


@pytest.mark.parametrize('callback',(False,True))
@pytest.mark.parametrize('count',(1,2,6,8,13,32))
def test_every_native_output_on_available_prefixes(callback,count):
    script,capture,bars = inputs(callback)
    assert_native(pn.run(script,bars[:count],executor_mode='inline'),capture,bars,count)


@pytest.mark.parametrize('mode',('local','replay','state'))
@pytest.mark.parametrize('cut',(4,13))
def test_native_restore_continuation_and_preview_isolation(mode,cut):
    script,capture,bars = inputs(True)
    original = pn.PyneIncrementalSession(script=script,settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut],high=500.,low=-500.,close=400.)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state()==before
    assert_native(original.snapshot_result(),capture,bars,cut)
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(),script=script) if mode=='local' else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode),script=script))
    restored_before = restored.snapshot_portable_state()
    restored.on_bar_updated(preview)
    assert restored.snapshot_portable_state()==restored_before
    for count,bar in enumerate(bars[cut:],cut+1):
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(),capture,bars,count)


def test_retention_does_not_reset_single_observation_helpers():
    script,capture,bars = inputs(True)
    settings = pn.PyneSettings(executor_mode='inline',max_bars=2,incremental_retention_bars=3,replay_history_bars=3)
    original = pn.PyneIncrementalSession(script=script,settings=settings)
    original.seed(bars[:2])
    for bar in bars[2:13]:
        original.on_bar_closed(bar)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable_state(),script=script,
        settings=settings)
    for count,bar in enumerate(bars[13:],14):
        assert restored.on_bar_closed(bar)==original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(),capture,bars,count,start=count-3)


@pytest.mark.parametrize('callback',(False,True))
def test_all_native_columns_are_counted(callback):
    result = reporter.workload_report(ROOT,NAME,dict(reporter.WORKLOADS)[NAME],callback)
    assert len(result['columns'])==48 and result['unmappedOutputColumns']==[]
    assert sum(c['counts']['cells'] for c in result['columns'].values())==1536
    assert sum(c['counts']['differences'] for c in result['columns'].values())==0
    assert result['comparisonTolerance']==1e-8


@pytest.mark.parametrize('mode',('replay','state'))
def test_genuine_affected_semantics_30_state_rejected_before_construction(mode,monkeypatch):
    folder = ROOT/'tests/golden/dispersion_semantics_v30'
    provenance = json.loads((folder/'provenance.json').read_text())
    assert provenance['packageVersion']=='0.4.1rc25' and provenance['semanticsVersion']==30
    for name,digest in provenance['sha256'].items():
        assert hashlib.sha256((folder/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==digest
    assert json.loads((folder/f'{mode}.json').read_text())['payload']['semanticsVersion']==30
    def forbidden(*args,**kwargs):
        pytest.fail('Incompatible dispersion state must be rejected before constructing a session')
    monkeypatch.setattr(pn.PyneIncrementalSession,'__init__',forbidden)
    with pytest.raises(pn.PynePortableSnapshotError,match='rebuild.*OHLCV'):
        pn.PyneIncrementalSession.from_portable_snapshot((folder/f'{mode}.json').read_bytes(),
            script=(folder/'indicator.pyne').read_text())


def test_exact_singletons_match_every_batch_prefix_and_step():
    # Signed exponent transitions stress accumulated anchors and squared
    # moments. This is Python numerical evidence, not native infinity parity.
    source = np.array([np.nan,1.e308,-1.e308,1.e-200,np.nan,7.,np.inf,np.nan,-np.inf,3.])
    expected = np.array([np.nan,0.,0.,0.,0.,0.,np.nan,np.nan,np.nan,0.])
    module = TaModule()
    with np.errstate(over='ignore',invalid='ignore'):
        for function in (module.stdev,module.variance):
            whole = np.asarray(function(source,1))
            prefixes = [function(source[:i+1],1)[-1] for i in range(len(source))]
            np.testing.assert_array_equal(whole,expected)
            np.testing.assert_array_equal(whole,prefixes)
        for helper in (_StepStdev(1),_StepVariance(1)):
            actual = [helper.update(value) for value in source]
            np.testing.assert_array_equal([np.nan if v is None else v for v in actual],expected)
        assert np.isnan(module.variance(source,1,False)).all()
    sma = _StepSMA(1)
    observed = [sma.update(value) for value in (1.e308,1.e-200,-1.e308,3.)]
    assert observed==[1.e308,1.e-200,-1.e308,3.]


@pytest.mark.parametrize('period',(0,-1,20))
def test_invalid_or_unready_windows_do_not_become_zero(period):
    source = np.array([np.nan,3.,4.])
    assert np.isnan(TaModule().stdev(source,period)).all()
    assert np.isnan(TaModule().variance(source,period)).all()
