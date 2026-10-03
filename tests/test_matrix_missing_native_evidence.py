"""Native numeric matrix arithmetic, reshape aliases and continuation evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneMatrix

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
spec = importlib.util.spec_from_file_location('matrix_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
NAME = 'matrix_missing_reshape'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
CONTROLS = {'Case', 'Scalar', *(f'Original {i}' for i in range(4)), *(f'Other {i}' for i in range(4))}


def assert_native(result, count):
    assert result.ok, result.error
    bars = reporter._bars(NAME, CAPTURE)
    lines = {line['name']: {point['time']: point['value'] for point in line['data']} for line in result.lines}
    for col, title in enumerate(CAPTURE['columns']):
        if title in CONTROLS:
            continue
        expected = {bars[i]['time']: CAPTURE['rows'][i]['values'][col] for i in range(count)
                    if CAPTURE['rows'][i]['values'][col] is not None}
        assert set(lines.get(title, {})) == set(expected), title
        assert lines.get(title, {}) == pytest.approx(expected, abs=CAPTURE['tolerance']), title


def test_native_matrix_capture_complete_with_operation_and_alias_witnesses():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 16 and len(CAPTURE['columns']) == 62
    assert [r['values'] for r in CAPTURE['rows'][:8]] == [r['values'] for r in CAPTURE['rows'][8:]]
    for row in CAPTURE['rows']:
        values = dict(zip(CAPTURE['columns'], row['values'], strict=True))
        assert all(value == 1 for title, value in values.items() if title.endswith(' success'))
        assert values['Reshape rows'] == values['Alias rows'] == 1
        assert values['Reshape columns'] == values['Alias columns'] == 4
        assert values['Second reshape rows'] == 4 and values['Second reshape columns'] == 1


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 3, 5, 6, 8, 16))
def test_native_matrix_complete_prefix_columns(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 4, 8))
def test_native_matrix_preview_restore_and_continue(mode, cut):
    source = (FOLDER / f'{NAME}.py').read_text(encoding='utf-8')
    bars = reporter._bars(NAME, CAPTURE)
    original = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut], high=500, low=0, close=400)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source)
    restored.on_bar_updated(preview)
    for count, bar in enumerate(bars[cut:], cut + 1):
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(), count)


@pytest.mark.parametrize('shape', ((3, 3), (-1, 4), (4, -1)))
def test_failed_reshape_preserves_original_and_alias(shape):
    matrix = PyneMatrix.from_rows([[1, 2], [3, 4]])
    alias = matrix
    before = matrix.to_list()
    with pytest.raises(ValueError):
        matrix.reshape(*shape)
    assert alias is matrix and alias.to_list() == before
    assert matrix.reshape(1, 4) is matrix
    assert alias.to_list() == [[1, 2, 3, 4]]


@pytest.mark.parametrize('missing', (None, float('nan')))
def test_missing_matrix_arithmetic_preserves_unaffected_product_cells(missing):
    left = PyneMatrix.from_rows([[1, missing], [3, 4]])
    right = PyneMatrix.from_rows([[2, 0], [1, 2]])
    assert left.mult(right).to_list() == [[None, None], [10.0, 8.0]]
    assert left.add(2).to_list() == [[3, None], [5, 6]]
    assert left.sub(2).to_list() == [[-1, None], [1, 2]]
    assert left.mult(missing).to_list() == [[None, None], [None, None]]


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
def test_committed_matrix_reshape_history_and_preview_are_isolated(mode):
    # Runtime state contract, separate from the fixed-case native denominator.
    source = '''
indicator("Persistent matrix",mode="incremental")
def on_bar(ctx,bar):
    cell = ctx.state("matrix",matrix.from_rows([[1,None],[3,4]]))
    prior = cell[1]
    current = cell.value
    matrix.reshape(current,1,4) if ctx.bar_index % 2 == 0 else matrix.reshape(current,4,1)
    matrix.set(current,0,0,bar.close)
    ctx.plot("Rows",matrix.rows(current))
    ctx.plot("Columns",matrix.columns(current))
    ctx.plot("Value",matrix.get(current,0,0))
    ctx.plot("Previous Value",matrix.get(prior,0,0) if prior is not None else None)
    ctx.plot("Previous Rows",matrix.rows(prior) if prior is not None else None)
'''
    bars = [dict(time=i*60, open=i+1, high=i+2, low=i, close=i+1, volume=10) for i in range(8)]
    original = pn.PyneIncrementalSession(script=source, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:3])
    committed = original.snapshot_portable_state()
    preview = dict(bars[3], high=100, close=99)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == committed
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source)
    restored.on_bar_updated(preview)
    for bar in bars[3:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result.ok, result.error
    values = {line['name']: [point['value'] for point in line['data']] for line in result.lines}
    assert values['Rows'] == [1, 4]*4
    assert values['Columns'] == [4, 1]*4
    assert values['Value'] == list(range(1, 9))
    assert values['Previous Value'] == list(range(1, 8))
    assert values['Previous Rows'] == [1, 4, 1, 4, 1, 4, 1]
