"""Native array search/default/fill values and exact join text, separately."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAME = 'array_search_fill_join'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('array_join_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
TRANSPORT_COLUMNS = {'First', 'Filled first', 'Filled 0', 'Parent 0'}


def assert_native(result, count):
    assert result.ok, result.error
    bars = reporter._bars(NAME, CAPTURE)
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    for col, title in enumerate(CAPTURE['columns']):
        if title == 'Case':
            continue
        expected = {bars[i]['time']: CAPTURE['rows'][i]['values'][col] for i in range(count)
                    if CAPTURE['rows'][i]['values'][col] is not None}
        actual = lines.get(title, {})
        assert set(actual) == set(expected), title
        for i in range(count):
            time = bars[i]['time']
            if time not in expected:
                continue
            if i in (13, 29) and title in TRANSPORT_COLUMNS:
                # This retained witness formerly exposed output truncation.
                # Preserve the native fractional value without changing tolerance.
                assert expected[time] == 0.123456789
                assert actual[time] == expected[time]
            else:
                assert actual[time] == pytest.approx(expected[time], rel=0, abs=CAPTURE['tolerance']), title
    labels = result.output.get('objects', {}).get('labels', [])
    actual_text = {}
    for label in labels:
        prefix, index, title, value = label['text'].split('|', 3)
        key = int(index), title
        assert prefix == 'JOIN' and key not in actual_text
        actual_text[key] = value
    expected_text = {(row['index'], title): value for row in CAPTURE['textRows'][:count]
                     for title, value in zip(CAPTURE['textColumns'], row['values'], strict=True)}
    assert actual_text == expected_text


def test_native_array_numeric_and_exact_text_evidence_complete():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 32 and len(CAPTURE['columns']) == 28
    assert [r['values'] for r in CAPTURE['rows'][:16]] == [r['values'] for r in CAPTURE['rows'][16:]]
    texts = reporter.native_array_join_text_checks(ROOT)
    assert texts['cells'] == 256 and texts['differences'] == 0


@pytest.mark.parametrize('corruption', ('duplicate_index', 'missing_value', 'wrong_text'))
def test_native_text_verifier_rejects_json_disagreement_before_execution(tmp_path, monkeypatch, corruption):
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

    def forbidden(*args, **kwargs):
        pytest.fail('Disagreed native text must be rejected before running a recipe')

    monkeypatch.setattr(reporter.pn, 'run', forbidden)
    with pytest.raises(ValueError, match='native array join|Native array join'):
        reporter.native_array_join_text_checks(tmp_path)


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 4, 8, 12, 14, 16, 32))
def test_native_array_complete_numeric_and_text_prefixes(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 8, 16))
def test_native_array_preview_restore_and_continue(mode, cut):
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
indicator("Persistent string array intent", mode="incremental")

def on_bar(ctx, bar):
    cell = ctx.state("strings", array.new_string(2))
    strings = cell.value
    numeric = array.new_float(2)
    snapshot = array.snapshot(strings)
    copied = array.copy(strings)
    window = array.slice(strings, 0, 1)
    ctx.plot("String intent", int(array.join(strings, "|") == "|" and
        array.join(snapshot, "|") == "|" and array.join(copied, "|") == "|" and
        array.join(window, "|") == ""))
    ctx.plot("Numeric intent", int(array.join(numeric, "|") == "NaN|NaN"))
    ctx.plot("Bool default", array.first(array.new_bool(2)))
    previous = cell[1]
    ctx.plot("Previous intent", int(array.join(previous, "|") == "|") if previous is not None else None)
    array.set(strings, 0, str(bar.close))
    ctx.plot("Copy isolated", int(array.join(copied, "|") == "|"))
    ctx.plot("Slice connected", int(array.join(window) == str(bar.close)))
    array.fill(strings, None)
'''


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
def test_all_missing_string_intent_survives_copy_slice_history_preview_and_restore(mode):
    bars = [dict(time=i*60, open=i+1, high=i+2, low=i, close=i+1, volume=10) for i in range(8)]
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:3])
    before = original.snapshot_portable_state()
    preview = dict(bars[3], high=100, close=99)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    if mode == 'local':
        restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=PERSISTENT)
    else:
        restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=PERSISTENT)
    restored.on_bar_updated(preview)
    for bar in bars[3:]:
        assert restored.on_bar_updated(bar) == original.on_bar_updated(bar)
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert result.ok, result.error
    values = {line['name']: [p['value'] for p in line['data']] for line in result.lines}
    for title in ('String intent', 'Numeric intent', 'Copy isolated', 'Slice connected'):
        assert values[title] == [1] * 8, title
    assert values['Bool default'] == [0] * 8
    assert values['Previous intent'] == [1] * 7


@pytest.mark.parametrize('corruption', ('missing', 'wrong_type'))
def test_malformed_restored_string_intent_is_rejected_before_adoption(corruption):
    original = pn.PyneIncrementalSession(script=PERSISTENT, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed([dict(time=0, open=1, high=2, low=0, close=1, volume=10)])
    before = original.snapshot_portable_state()
    envelope = json.loads(before)
    nodes = envelope['payload']['stateGraph']['nodes']
    array = next(node for node in nodes if node.get('type') == 'pyne_runtime.collections:PyneArray')
    attribute = next(pair for pair in array['attributes'] if pair[0] == '_string_values')
    if corruption == 'missing':
        array['attributes'].remove(attribute)
    else:
        attribute[1] = 'string'
    payload = json.dumps(envelope['payload'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    envelope['checksum'] = 'sha256:' + hashlib.sha256(payload).hexdigest()
    with pytest.raises(pn.PynePortableSnapshotError, match='array string'):
        pn.PyneIncrementalSession.from_portable_snapshot(json.dumps(envelope), script=PERSISTENT)
    assert original.snapshot_portable_state() == before
    assert original.on_bar_closed(dict(time=60, open=2, high=3, low=1, close=2, volume=10)) is not None
