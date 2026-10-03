"""Rectangular matrix results measured against retained native outputs."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneMatrix

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAME = 'matrix_rectangular_products'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('rectangular_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
REJECTIONS_FOLDER = ROOT / 'tests/golden/matrix_dimension_rejections'
REJECTIONS = json.loads((REJECTIONS_FOLDER / 'capture.json').read_text(encoding='utf-8'))['cases']


def assert_native(result, count):
    assert result.ok, result.error
    bars = reporter._bars(NAME, CAPTURE)
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    for col, title in enumerate(CAPTURE['columns']):
        if title == 'Case':
            continue
        expected = {bars[i]['time']: CAPTURE['rows'][i]['values'][col] for i in range(count)
                    if CAPTURE['rows'][i]['values'][col] is not None}
        assert lines.get(title, {}) == expected, title


def test_native_rectangular_evidence_complete():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 24 and len(CAPTURE['columns']) == 37
    assert [r['values'] for r in CAPTURE['rows'][:12]] == [r['values'] for r in CAPTURE['rows'][12:]]


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 24))
def test_native_rectangular_complete_prefixes(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 6, 8, 11, 12))
def test_native_rectangular_preview_restore_and_continue(mode, cut):
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


@pytest.mark.parametrize('case', REJECTIONS, ids=lambda c:c['name'])
def test_native_dimension_error_evidence(case):
    for suffix, key in (('pine', 'pineSha256'), ('native-error.txt', 'errorSha256')):
        raw = (REJECTIONS_FOLDER / f'{case["name"]}.{suffix}').read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(raw).hexdigest() == case[key]
    assert (REJECTIONS_FOLDER / f'{case["name"]}.native-error.txt').read_text(encoding='utf-8').strip() == case['message']
    assert case['message'].startswith('Error on bar 0:')


@pytest.mark.parametrize('field', ('leftShape', 'pyneOperation', 'message', 'nativeErrorCode', 'pineSha256', 'cases'))
def test_matrix_native_error_verifier_rejects_corrupted_provenance(tmp_path, field):
    folder = tmp_path / 'tests/golden/matrix_dimension_rejections'
    shutil.copytree(REJECTIONS_FOLDER, folder)
    capture = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
    if field == 'cases':
        capture['cases'].pop()
    else:
        capture['cases'][0][field] = [2, 2] if field == 'leftShape' else 'corrupted'
    (folder / 'capture.json').write_text(json.dumps(capture), encoding='utf-8')
    with pytest.raises(ValueError):
        reporter.native_matrix_dimension_error_checks(tmp_path)


@pytest.mark.parametrize('case', REJECTIONS, ids=lambda c:c['name'])
def test_dimension_rejection_preserves_both_operands(case):
    left = PyneMatrix(*case['leftShape'], 1.)
    right = PyneMatrix(*case['rightShape'], 2.)
    before = left.to_list(), right.to_list()
    with pytest.raises(ValueError, match='dimensions'):
        getattr(left, case['pyneOperation'])(right)
    assert (left.to_list(), right.to_list()) == before
    left.set(0, 0, 9.)
    assert left.get(0, 0) == 9.  # Independent Python error atomicity control.


@pytest.mark.parametrize('case', REJECTIONS, ids=lambda c:c['name'])
@pytest.mark.parametrize('callback', (False, True))
def test_native_dimension_errors_are_exposed_in_both_execution_modes(case, callback):
    h, w = case['rightShape']
    operation = f'matrix.{case["pyneOperation"]}(matrix.new_float(2,3,1.),matrix.new_float({h},{w},2.))'
    source = ('indicator("Dimension rejection",mode="incremental")\n'
              f'def on_bar(ctx,bar):\n    {operation}\n' if callback else
              f'indicator("Dimension rejection")\n{operation}\n')
    result = pn.run(source, reporter._bars(NAME, CAPTURE)[:1], executor_mode='inline')
    assert not result.ok and 'dimensions' in result.error.lower()


@pytest.mark.parametrize('case', REJECTIONS, ids=lambda c:c['name'])
@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
def test_caught_dimension_rejection_preserves_preview_history_and_continuation(case, mode):
    # Native execution aborts; these after-error checks qualify the Python contract.
    h, w = case['rightShape']
    source = f'''
indicator("Caught dimension rejection",mode="incremental")
def on_bar(ctx,bar):
    cell = ctx.state("matrix",matrix.new_float(2,3,1.))
    a = cell.value
    b = matrix.new_float({h},{w},2.)
    rejected = 0
    try:
        matrix.{case['pyneOperation']}(a,b)
    except ValueError:
        rejected = 1
    ctx.plot("Rejected",rejected)
    ctx.plot("Untouched",matrix.get(a,0,0))
    ctx.plot("Other",matrix.get(b,0,0))
    matrix.set(a,0,0,bar.close)
    ctx.plot("Healthy",matrix.get(a,0,0))
    ctx.plot("Previous",matrix.get(cell[1],0,0) if cell[1] is not None else None)
'''
    settings = pn.PyneSettings(executor_mode='inline', max_matrix_cells=6)
    bars = [dict(time=i*60, open=i+1, high=i+2, low=i, close=i+1, volume=10) for i in range(8)]
    original = pn.PyneIncrementalSession(script=source, settings=settings)
    original.seed(bars[:3])
    before = original.snapshot_portable_state()
    original.on_bar_updated(dict(bars[3], high=100, close=99))
    assert original.snapshot_portable_state() == before
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=source, settings=settings)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=source,
                                                                  settings=settings)
    restored.on_bar_updated(dict(bars[3], high=100, close=99))
    for bar in bars[3:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result.ok, result.error
    values = {line['name']: [p['value'] for p in line['data']] for line in result.lines}
    assert values['Rejected'] == [1]*8
    assert values['Untouched'] == [1, 1, 2, 3, 4, 5, 6, 7]
    assert values['Other'] == [2]*8
    assert values['Healthy'] == list(range(1,9))
    assert values['Previous'] == list(range(1,8))
