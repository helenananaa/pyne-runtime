"""Native empty shapes, arithmetic, extraction and durable matrix dimensions."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneMatrix
from pyne_runtime.incremental.limits import _StateHistory, _STATE_HISTORY_TOKEN
from pyne_runtime.security import PyneResourceLimitError

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAME = 'matrix_empty_shapes'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('empty_matrix_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


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


def test_native_empty_matrix_evidence_complete():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 16 and len(CAPTURE['columns']) == 37
    assert [r['values'] for r in CAPTURE['rows'][:8]] == [r['values'] for r in CAPTURE['rows'][8:]]


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 3, 4, 6, 8, 9, 16))
def test_native_empty_matrix_complete_prefixes(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 4, 8))
def test_native_empty_matrix_preview_restore_and_continue(mode, cut):
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


PERSISTENT = '''
indicator("Persistent empty matrix",mode="incremental")

def on_bar(ctx,bar):
    cell = ctx.state("matrix",matrix.new_string(0,3))
    current,previous = cell.value,cell[1]
    if ctx.bar_index % 2 == 0:
        matrix.reshape(current,0,3)
    else:
        matrix.reshape(current,3,0)
    copied = matrix.copy(current)
    snap = matrix.snapshot(current)
    transposed = matrix.transpose(current)
    ctx.plot("Rows",matrix.rows(current))
    ctx.plot("Columns",matrix.columns(current))
    ctx.plot("Copy rows",matrix.rows(copied))
    ctx.plot("Copy columns",matrix.columns(copied))
    ctx.plot("Snapshot columns",matrix.columns(snap))
    ctx.plot("Transpose rows",matrix.rows(transposed))
    ctx.plot("Transpose columns",matrix.columns(transposed))
    ctx.plot("Previous rows",matrix.rows(previous) if previous is not None else None)
    ctx.plot("Previous columns",matrix.columns(previous) if previous is not None else None)
'''


def bars():
    return [dict(time=i*60, open=i+1, high=i+2, low=i, close=i+1, volume=10) for i in range(8)]


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('rebind_budget', (False, True))
def test_empty_matrix_dimensions_survive_preview_history_restore_and_budget_rebind(mode, rebind_budget):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    before = original.snapshot_portable_state()
    preview = dict(bars()[3], high=100, close=99)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    options = {'settings': pn.PyneSettings(executor_mode='inline', max_matrix_cells=1)} if rebind_budget else {}
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=PERSISTENT, **options)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=PERSISTENT, **options)
    restored.on_bar_updated(preview)
    for bar in bars()[3:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result.ok, result.error
    values = {line['name']: [p['value'] for p in line['data']] for line in result.lines}
    for title in ('Rows', 'Copy rows', 'Transpose columns'):
        assert values[title] == [0, 3]*4, title
    for title in ('Columns', 'Copy columns', 'Snapshot columns', 'Transpose rows'):
        assert values[title] == [3, 0]*4, title
    assert values['Previous rows'] == [0,3,0,3,0,3,0]
    assert values['Previous columns'] == [3,0,3,0,3,0,3]
    if rebind_budget:
        current = restored._ctx._states['matrix'].value
        assert current._max_cells == 1
        with pytest.raises(PyneResourceLimitError):
            current.mult(PyneMatrix(0,2))
        assert (current.rows(), current.columns()) == (3,0)


@pytest.mark.parametrize('shape', ((1,1), (-1,3), (0,-1)))
def test_rejected_empty_reshape_preserves_dimensions_and_alias(shape):
    matrix = PyneMatrix(0,3)
    alias = matrix
    with pytest.raises(ValueError):
        matrix.reshape(*shape)
    assert matrix is alias and (alias.rows(), alias.columns()) == (0,3)
    assert matrix.reshape(3,0) is alias
    assert (alias.rows(), alias.columns()) == (3,0)


def corrupt(value, corruption):
    if corruption == 'missing':
        del value._column_count
    elif corruption == 'boolean':
        value._column_count = True
    elif corruption == 'negative':
        value._column_count = -1
    elif corruption == 'wrong_type':
        value._column_count = '3'
    else:
        value._values = [[None]]


@pytest.mark.parametrize('location', ('current', 'history'))
@pytest.mark.parametrize('corruption', ('missing', 'boolean', 'negative', 'wrong_type', 'ragged'))
def test_invalid_local_matrix_shape_is_rejected_atomically(location, corruption):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    snapshot = original.snapshot_state()
    cell = snapshot.context._states['matrix']
    if location == 'current':
        value = cell.value
    else:
        history = object.__getattribute__(cell, '_StateCell__history')
        entries = copy.deepcopy(history._raw_slice(slice(None), _STATE_HISTORY_TOKEN))
        object.__setattr__(cell, '_StateCell__history', _StateHistory(maxlen=history.maxlen, values=entries))
        value = entries[0]
    corrupt(value, corruption)
    preview = dict(bars()[3], high=100, close=99)
    original.on_bar_updated(preview)
    expected = original.on_bar_updated(preview)
    before = original.snapshot_portable_state()
    with pytest.raises(pn.PynePortableSnapshotError, match='matrix shape'):
        original.restore_state(snapshot)
    assert original.snapshot_portable_state() == before
    assert original.on_bar_updated(preview) == expected
    assert original.on_bar_closed(bars()[3]) is not None


@pytest.mark.parametrize('corruption', ('missing', 'boolean', 'negative', 'wrong_type'))
def test_invalid_portable_shape_rejected_before_adoption(corruption):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    before = original.snapshot_portable_state()
    envelope = json.loads(before)
    matrix = next(node for node in envelope['payload']['stateGraph']['nodes']
                  if node.get('type') == 'pyne_runtime.collections:PyneMatrix')
    attribute = next(pair for pair in matrix['attributes'] if pair[0] == '_column_count')
    if corruption == 'missing':
        matrix['attributes'].remove(attribute)
    else:
        attribute[1] = {'boolean': True, 'negative': -1, 'wrong_type': '3'}[corruption]
    payload = json.dumps(envelope['payload'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    envelope['checksum'] = 'sha256:' + hashlib.sha256(payload).hexdigest()
    with pytest.raises(pn.PynePortableSnapshotError, match='matrix shape'):
        pn.PyneIncrementalSession.from_portable_snapshot(json.dumps(envelope), script=PERSISTENT)
    assert original.snapshot_portable_state() == before
    assert original.on_bar_closed(bars()[3]) is not None
