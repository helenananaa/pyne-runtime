"""Native sum composition plus independently calculated Python boundaries."""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.utils import sum_

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
spec = importlib.util.spec_from_file_location('sum_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


@pytest.mark.parametrize('mode', ('batch', 'incremental'))
def test_all_native_sum_and_formula_cells_are_measured(mode):
    case = reporter.workload_report(ROOT, 'oscillator_formula', {'holes'}, mode == 'incremental')
    assert case['unmappedOutputColumns'] == []
    assert len(case['columns']) == 12
    for title in ('Up sum', 'Down sum', 'CMO formula', 'CMO native'):
        assert case['columns'][title]['counts']['cells'] == 32
        assert case['columns'][title]['counts']['differences'] == 0
    # Initial masks are included; extrema/Stoch startup now aligns too.
    assert sum(column['counts']['differences'] for column in case['columns'].values()) == 0


@pytest.mark.parametrize('count', (1, 2, 3, 7, 8, 9, 13, 24, 32))
def test_public_math_sum_native_prefixes(count):
    capture = json.loads((FOLDER / 'oscillator_formula.tradingview.json').read_text())
    down = capture['columns'].index('Down')
    expected_col = capture['columns'].index('Down sum')
    values = [row['values'][down] for row in capture['rows'][:count]]
    source = 'import numpy as np\nplot(math.sum(np.array([' + ','.join('na' if value is None else repr(value) for value in values) + ']),3),"Sum")'
    bars = [dict(time=i*60, open=1, high=2, low=0, close=1, volume=10) for i in range(count)]
    result = pn.run(source, bars, executor_mode='inline')
    assert result.ok, result.error
    expected = {row['index']*60: row['values'][expected_col] for row in capture['rows'][:count]
                if row['values'][expected_col] is not None}
    line = next(line for line in result.lines if line['name'] == 'Sum')
    assert {point['time']: point['value'] for point in line['data']} == expected


@pytest.mark.parametrize('period', (1, 2, 3, 5, 17))
@pytest.mark.parametrize('values', ([None]*21, [None,None,1.,None,2.,None,3.,4.,None,5.],
                                   [1.,-2.,None,3.,None,None,4.,-5.]))
def test_python_sum_observation_windows_and_input_immutability(period, values):
    source = np.array([np.nan if value is None else value for value in values])
    original = source.copy()
    retained, expected = [], []
    for value in values:
        if value is not None:
            retained.append(value)
        expected.append(math.fsum(retained[-period:]) if len(retained) >= period else np.nan)
    np.testing.assert_allclose(sum_(source, period), expected, rtol=0, atol=0)
    np.testing.assert_array_equal(source, original)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (7, 8, 12, 23))
def test_generic_formula_preview_and_snapshot_continuation(mode, cut):
    source = (FOLDER / 'oscillator_formula.py').read_text()
    bars = [dict(time=i*60, open=1, high=2, low=0, close=1, volume=10) for i in range(32)]
    settings = pn.PyneSettings(executor_mode='inline')
    session = pn.PyneIncrementalSession(script=source, settings=settings)
    session.seed(bars[:cut])
    committed = session.snapshot_result()
    session.on_bar_updated(dict(bars[cut], close=100, high=101))
    assert session.snapshot_result() == committed
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(session.snapshot_portable(mode=mode), script=source, settings=settings)
    for bar in bars[cut:]:
        restored.on_bar_closed(bar)
    control = pn.run(source, bars, settings=settings)
    assert control.ok, control.error
    assert restored.snapshot_result().lines == control.lines
