"""Native calculation precision, counted arithmetic debt, and portable state contracts."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepSMA
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'tests/workloads'
NAME = 'numeric_output_precision'
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
        observed = actual.get(title,{})
        if title == 'SMA3 large':
            # This column remains in the strict official denominator below.
            # Continuation checks its masks here and exact restored values.
            assert observed.keys() == expected.keys()
        else:
            assert observed == pytest.approx(expected,abs=1e-12,rel=0),title


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
        np.testing.assert_allclose(values[title],official,rtol=0,atol=1e-15,equal_nan=True)
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
    assert len(result['columns'])==32 and result['unmappedOutputColumns']==[]
    assert sum(c['counts']['cells'] for c in result['columns'].values())==1024
    expected_debt = 24 if callback else 22
    assert sum(c['counts']['differences'] for c in result['columns'].values()) == expected_debt
    assert result['columns']['SMA3 large']['counts']['differences'] == expected_debt
    assert all(c['counts']['differences'] == 0 for name,c in result['columns'].items()
               if name != 'SMA3 large')
    assert result['comparisonTolerance']==1e-12


def test_exact_sma_one_and_present_sum_on_every_prefix():
    from pyne_runtime.ta_kernels import _rolling_nonmissing_sum
    source = np.array([np.nan,100000.12345678912,100000.92345678912,
                       np.nan,1.e308,1.e-200,-1.e308,3.,np.inf,np.nan,-np.inf,7.])
    expected = np.array([np.nan,100000.12345678912,100000.92345678912,
                         100000.92345678912,1.e308,1.e-200,-1.e308,3.,np.inf,np.inf,-np.inf,7.])
    with np.errstate(over='ignore',invalid='ignore'):
        for operation in (lambda x: TaModule().sma(x,1),lambda x: _rolling_nonmissing_sum(x,1)):
            np.testing.assert_array_equal(operation(source),expected)
            np.testing.assert_array_equal([operation(source[:i+1])[-1] for i in range(len(source))],expected)
    helper = _StepSMA(1)
    np.testing.assert_array_equal([np.nan if (v := helper.update(x)) is None else v for x in source],expected)


@pytest.mark.parametrize('value',(1.e-10,-1.e-10,0.1234567891234567,1.e-200,1.e100))
def test_public_batch_outputs_preserve_binary64_and_json(value):
    script = f'''
indicator("Raw outputs", precision=2)
value = close*0+{value!r}
plot(value,"Line",precision=0)
plot(value,"Histogram",style="histogram",precision=2)
add_line(value,"Legacy",type="histogram")
bar(value,"Bar")
plotcandle(value,value,value,value,title="Candle",precision=2)
plotshape(value,title="Shape",location=location.absolute)
plotarrow(value,title="Arrow")
emit_signal(True,name="Signal",price=value)
line.new(0,value,1,value)
label.new(0,value,text="Raw")
hline({value!r},"Horizontal")
'''
    result = pn.run(script,[dict(time=0,open=1.,high=1.,low=1.,close=1.,volume=1.)],executor_mode='inline')
    assert result.ok,result.error
    output = json.loads(json.dumps(result.output,allow_nan=False))
    assert output['lines'][0]['data'][0]['value'] == value
    assert output['lines'][0]['precision'] == 0 and output['meta']['precision'] == 2
    assert all(h['data'][0]['value'] == value for h in output['histograms'])
    assert all(output['candles'][0]['data'][0][key] == value for key in ('open','high','low','close'))
    assert all(m['data'][0]['value'] == value for m in output['markers'])
    assert output['signals'][0]['data'][0]['price'] == value
    assert output['objects']['lines'][0]['y1'] == value
    assert output['objects']['lines'][0]['y2'] == value
    assert output['objects']['labels'][0]['y'] == value
    assert output['hlines'][0]['price'] == value


def test_genuine_old_rounding_and_current_json_output_are_distinct():
    folder = ROOT/'tests/golden/output_precision_semantics_v31'
    old = json.loads((folder/'committed-result.json').read_text())
    assert {p['value'] for p in old['lines'][0]['data']} == {0.12345679}
    result = pn.run((folder/'indicator.pyne').read_text(),json.loads((folder/'bars.json').read_text()),
                    executor_mode='inline')
    assert result.ok,result.error
    expected = [0.1234567891234567+i*1.e-10 for i in range(4)]
    assert result.values('Precise') == expected
    assert result.values('Histogram') == expected
    candle = result.output['candles'][0]['data'][0]
    assert candle['high'] > candle['close'] > candle['open'] > candle['low']


def test_incremental_strategy_calculation_properties_preserve_arithmetic(monkeypatch):
    from pyne_runtime.incremental.strategy import IncrementalStrategyNamespace
    strategy = object.__new__(IncrementalStrategyNamespace)
    monkeypatch.setattr(IncrementalStrategyNamespace,'_sync_risk_liquidation',lambda self: None)
    monkeypatch.setattr(IncrementalStrategyNamespace,'_current_price',lambda self: 0.1234567892234567)
    strategy._open_trades = [dict(qty=1.,entry_price=0.1234567891234567,side='long')]
    strategy._grossprofit = 1.2000000000000002
    strategy._grossloss = -0.1999999999999993
    strategy._commission = 0.1234567891234567
    strategy._initial_capital = 1000.1234567891234
    assert strategy.position_avg_price == 0.1234567891234567
    assert strategy.grossprofit == 1.2000000000000002
    assert strategy.grossloss == -0.1999999999999993
    expected_open = 0.1234567892234567-0.1234567891234567
    expected_net = 1.2000000000000002-0.1999999999999993-0.1234567891234567
    assert strategy.openprofit == expected_open != 0.
    assert strategy.netprofit == expected_net
    assert strategy.equity == 1000.1234567891234+expected_net+expected_open


@pytest.mark.parametrize('mode',('replay','state'))
def test_genuine_affected_semantics_31_state_rejected_before_construction(mode,monkeypatch):
    folder = ROOT/'tests/golden/output_precision_semantics_v31'
    provenance = json.loads((folder/'provenance.json').read_text())
    assert provenance['packageVersion']=='0.4.1rc26' and provenance['semanticsVersion']==31
    for name,digest in provenance['sha256'].items():
        assert hashlib.sha256((folder/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==digest
    assert json.loads((folder/f'{mode}.json').read_text())['payload']['semanticsVersion']==31
    def forbidden(*args,**kwargs):
        pytest.fail('Incompatible rounded output state must be rejected before constructing a session')
    monkeypatch.setattr(pn.PyneIncrementalSession,'__init__',forbidden)
    with pytest.raises(pn.PynePortableSnapshotError,match='rebuild.*OHLCV'):
        pn.PyneIncrementalSession.from_portable_snapshot((folder/f'{mode}.json').read_bytes(),
            script=(folder/'indicator.pyne').read_text())
