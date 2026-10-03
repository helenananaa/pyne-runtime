"""Native scalar extraction text, defaults, and committed construction intent."""
from __future__ import annotations

import hashlib
import copy
import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneMap, PyneMatrix
from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError
from pyne_runtime.incremental.limits import _StateHistory, _STATE_HISTORY_TOKEN

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAME = 'collection_string_extraction'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('collection_text_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def assert_native(result, count):
    assert result.ok, result.error
    bars = reporter._bars(NAME, CAPTURE)
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    for col, title in enumerate(CAPTURE['columns']):
        if title == 'Case':
            continue
        expected = {bars[i]['time']: CAPTURE['rows'][i]['values'][col] for i in range(count)}
        assert lines[title] == expected, title
    actual = {}
    for label in result.output.get('objects', {}).get('labels', []):
        prefix, index, title, value = label['text'].split('|', 3)
        key = int(index), title
        assert prefix == 'JOIN' and key not in actual
        actual[key] = value
    expected = {(row['index'], title): value for row in CAPTURE['textRows'][:count]
                for title, value in zip(CAPTURE['textColumns'], row['values'], strict=True)}
    assert actual == expected


def test_native_numeric_and_exact_text_evidence_complete():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 16 and len(CAPTURE['columns']) == 9
    assert [r['values'] for r in CAPTURE['rows'][:8]] == [r['values'] for r in CAPTURE['rows'][8:]]
    text = reporter.native_collection_extraction_text_checks(ROOT)
    assert text['cells'] == 224 and text['differences'] == 0


@pytest.mark.parametrize('corruption', ('duplicate_index', 'missing_value', 'wrong_text'))
def test_native_text_json_disagreement_rejected_before_execution(tmp_path, monkeypatch, corruption):
    folder = tmp_path / 'tests/workloads'
    folder.mkdir(parents=True)
    for suffix in ('pine', 'tradingview.txt'):
        (folder / f'{NAME}.{suffix}').write_text((FOLDER / f'{NAME}.{suffix}').read_text(encoding='utf-8'), encoding='utf-8')
    capture = json.loads(json.dumps(CAPTURE))
    if corruption == 'duplicate_index':
        capture['textRows'][1]['index'] = 0
    elif corruption == 'missing_value':
        capture['textRows'][1]['values'].pop()
    else:
        capture['textRows'][1]['values'][0] = 'forged'
    (folder / f'{NAME}.tradingview.json').write_text(json.dumps(capture), encoding='utf-8')
    monkeypatch.setattr(reporter.pn, 'run', lambda *a, **k: pytest.fail('Unverified text must not execute'))
    with pytest.raises(ValueError, match='native collection extraction|Native collection extraction'):
        reporter.native_collection_extraction_text_checks(tmp_path)


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 3, 5, 7, 8, 9, 16))
def test_native_numeric_and_text_prefixes(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 4, 8))
def test_native_preview_restore_and_continue(mode, cut):
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
indicator("Persistent collection string intent", mode="incremental")

def on_bar(ctx, bar):
    mc = ctx.state("matrix", matrix.new_string(2,2))
    dc = ctx.state("map", map.from_values(0,"seed",1,"seed"))
    m, d = mc.value, dc.value
    map.put(d,0,None)
    map.put(d,1,None)
    ctx.plot("Matrix intent", int(array.join(matrix.row(m,0),"|") == "|" and
        array.join(matrix.col(m,1),"|") == "|" and
        array.join(matrix.row(matrix.copy(m),0),"|") == "|" and
        array.join(matrix.row(matrix.snapshot(m),0),"|") == "|" and
        array.join(matrix.row(matrix.transpose(m),0),"|") == "|"))
    ctx.plot("Map intent", int(array.join(map.values(d),"|") == "|" and
        array.join(map.values(map.copy(d)),"|") == "|" and
        array.join(map.values(map.snapshot(d)),"|") == "|"))
    previous_m, previous_d = mc[1], dc[1]
    ctx.plot("Previous matrix", int(array.join(matrix.row(previous_m,0),"|") == "|") if previous_m is not None else None)
    ctx.plot("Previous map", int(array.join(map.values(previous_d),"|") == "|") if previous_d is not None else None)
    matrix.fill(m,str(bar.close))
    map.put(d,0,str(bar.close))
    ctx.plot("History immutable", int(previous_m is None or (array.join(matrix.row(previous_m,0),"|") == "|" and array.join(map.values(previous_d),"|") == "|")))
    matrix.fill(m,None)
    map.clear(d)
    map.put(d,0,None)
    map.put(d,1,None)
'''


def bars():
    return [dict(time=i*60, open=i+1, high=i+2, low=i, close=i+1, volume=10) for i in range(8)]


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
def test_all_missing_collection_intent_survives_history_preview_and_restore(mode):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    before = original.snapshot_portable_state()
    preview = dict(bars()[3], high=100, close=99)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=PERSISTENT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=PERSISTENT)
    restored.on_bar_updated(preview)
    for bar in bars()[3:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result.ok, result.error
    values = {line['name']: [p['value'] for p in line['data']] for line in result.lines}
    for title in ('Matrix intent', 'Map intent', 'History immutable'):
        assert values[title] == [1] * 8, title
    for title in ('Previous matrix', 'Previous map'):
        assert values[title] == [1] * 7, title


@pytest.mark.parametrize('kind', ('PyneMap', 'PyneMatrix'))
@pytest.mark.parametrize('corruption', ('missing', 'wrong_type'))
def test_malformed_restored_intent_rejected_before_adoption(kind, corruption):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    before = original.snapshot_portable_state()
    envelope = json.loads(before)
    nodes = envelope['payload']['stateGraph']['nodes']
    collection = next(node for node in nodes if node.get('type') == 'pyne_runtime.collections:' + kind)
    attribute = next(pair for pair in collection['attributes'] if pair[0] == '_string_values')
    if corruption == 'missing':
        collection['attributes'].remove(attribute)
    else:
        attribute[1] = 'string'
    payload = json.dumps(envelope['payload'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    envelope['checksum'] = 'sha256:' + hashlib.sha256(payload).hexdigest()
    with pytest.raises(pn.PynePortableSnapshotError, match='string construction'):
        pn.PyneIncrementalSession.from_portable_snapshot(json.dumps(envelope), script=PERSISTENT)
    assert original.snapshot_portable_state() == before
    assert original.on_bar_closed(bars()[3]) is not None


@pytest.mark.parametrize('operation', ('map_put', 'map_merge', 'matrix_set', 'matrix_fill'))
def test_rejected_string_admission_does_not_change_conversion_intent(operation):
    # Numeric collections retain NaN conversion after a rejected string write.
    if operation.startswith('map'):
        collection = PyneMap({0: None}, max_size=1)
        with pytest.raises((PyneResourceLimitError, ValueError)):
            if operation == 'map_put':
                collection.put(1, 'string')
            else:
                collection.put_all(PyneMap({0: 'string', 1: 'overflow'}))
        assert collection.to_dict() == {0: None}
        assert collection.values().join() == 'NaN'
    else:
        collection = PyneMatrix(1, 1)
        with pytest.raises((IndexError, TypeError, ValueError, PyneStateContractError)):
            if operation == 'matrix_set':
                collection.set(1, 0, 'string')
            else:
                collection.fill(collection)
        assert collection.to_list() == [[None]]
        assert collection.row(0).join() == 'NaN'


def test_missing_string_map_bulk_transfer_and_matrix_inference():
    source = PyneMap({0: 'seed', 1: 'seed'})
    source.put(0, None)
    source.put(1, None)
    target = PyneMap()
    target.put_all(source)
    assert target.values().join('|') == '|'
    assert target.snapshot().values().join('|') == '|'
    m = PyneMatrix.from_rows([['seed', None], [None, None]])
    m.fill(None)
    m.reshape(1, 4)
    assert m.row(0).join('|') == '|||'
    assert m.snapshot().row(0).join('|') == '|||'


@pytest.mark.parametrize('kind', ('map', 'matrix'))
@pytest.mark.parametrize('location', ('current', 'history'))
@pytest.mark.parametrize('corruption', ('missing', 'wrong_type'))
def test_local_restore_rejects_invalid_current_or_shared_history_atomically(kind, location, corruption):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars()[:3])
    snapshot = original.snapshot_state()
    cell = snapshot.context._states[kind]
    if location == 'current':
        value = cell.value
    else:
        # StateCell deepcopy intentionally shares immutable historical values.
        # Replace this snapshot's history with independent values before forging it.
        history = object.__getattribute__(cell, '_StateCell__history')
        entries = copy.deepcopy(history._raw_slice(slice(None), _STATE_HISTORY_TOKEN))
        object.__setattr__(cell, '_StateCell__history', _StateHistory(maxlen=history.maxlen, values=entries))
        value = entries[0]
    if corruption == 'missing':
        del value._string_values
    else:
        value._string_values = 'invalid'
    preview = dict(bars()[3], high=100, close=99)
    original.on_bar_updated(preview)
    # The first realtime update reports isnew=True; subsequent updates do not.
    expected_preview = original.on_bar_updated(preview)
    before = original.snapshot_portable_state()
    with pytest.raises(pn.PynePortableSnapshotError, match=kind + ' string'):
        original.restore_state(snapshot)
    assert original.snapshot_portable_state() == before
    assert original.on_bar_updated(preview) == expected_preview
    assert original.on_bar_closed(bars()[3]) is not None
