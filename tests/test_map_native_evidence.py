"""Native scalar map operations plus independent atomic admission controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyne_runtime as pn
import pytest
from pyne_runtime.collections import PyneArray, PyneMap
from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
spec = importlib.util.spec_from_file_location('map_native_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
NAME = 'map_scalar_mutation'
CAPTURE = json.loads((FOLDER / f'{NAME}.tradingview.json').read_text(encoding='utf-8'))


def assert_native(result, count):
    assert result.ok, result.error
    bars = reporter._bars(NAME, CAPTURE)
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    for column, title in enumerate(CAPTURE['columns']):
        if title == 'Case':
            continue
        expected = {bars[i]['time']: CAPTURE['rows'][i]['values'][column] for i in range(count)
                    if CAPTURE['rows'][i]['values'][column] is not None}
        assert lines.get(title, {}) == expected, title


def test_native_map_complete_records_and_repeated_cycle():
    reporter.verify_evidence(FOLDER, NAME, CAPTURE)
    assert len(CAPTURE['rows']) == 32 and len(CAPTURE['columns']) == 40
    assert [r['values'] for r in CAPTURE['rows'][:16]] == [r['values'] for r in CAPTURE['rows'][16:]]


@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 4, 8, 10, 16, 24, 32))
def test_native_map_complete_prefix_columns(callback, count):
    source = (FOLDER / f'{NAME}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    assert_native(pn.run(source, reporter._bars(NAME, CAPTURE)[:count], executor_mode='inline'), count)


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 8, 16))
def test_native_map_preview_restore_and_continue(mode, cut):
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


@pytest.mark.parametrize('reason', ('capacity', 'recursive', 'depth'))
def test_bulk_merge_rejects_every_item_before_mutation(reason):
    target = PyneMap({'a': 1}, max_size=2 if reason == 'capacity' else None,
                     max_depth=1 if reason == 'depth' else None)
    payload = target if reason == 'recursive' else PyneArray([2])
    source = PyneMap({'a': 9, 'b': 2, 'c': 3}) if reason == 'capacity' else PyneMap({'a': 9, 'bad': payload})
    before = target.to_dict()
    source_before = source.to_dict()
    error = PyneStateContractError if reason == 'recursive' else PyneResourceLimitError
    with pytest.raises(error):
        target.put_all(source)
    assert target.to_dict() == before
    assert source.to_dict() == source_before
    target.put_all(PyneMap({'a': 7, 'healthy': 4}))
    assert target.keys().to_list() == ['a', 'healthy']
    assert target.values().to_list() == [7, 4]


PERSISTENT = '''
indicator("Atomic persistent maps", mode="incremental")

def on_bar(ctx, bar):
    from pyne_runtime.security import PyneResourceLimitError, PyneStateContractError
    from pyne_runtime.collections import PyneMap, PyneArray
    cell = ctx.state("map", map.from_values("a", 1))
    value = cell.value
    if REASON == "capacity":
        incoming = PyneMap({"a": 9, "b": 2, "c": 3})
    elif REASON == "recursive":
        incoming = PyneMap({"a": 9, "bad": value})
    else:
        incoming = PyneMap({"a": 9, "bad": PyneArray([2])})
    rejected = 0
    try:
        map.put_all(value, incoming)
    except (PyneResourceLimitError, PyneStateContractError):
        rejected = 1
    ctx.plot("Rejected", rejected)
    ctx.plot("Untouched", map.get(value, "a"))
    ctx.plot("Size before", map.size(value))
    map.put_all(value, map.from_values("a", bar.close))
    ctx.plot("Healthy", map.get(value, "a"))
    previous = cell[1]
    ctx.plot("Previous", map.get(previous, "a") if previous is not None else None)
'''


@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('reason', ('capacity', 'recursive', 'depth'))
def test_caught_rejected_merge_preserves_state_preview_history_and_continuation(mode, reason):
    source = PERSISTENT.replace('REASON', repr(reason))
    settings = pn.PyneSettings(executor_mode='inline', max_map_size=2 if reason == 'capacity' else None,
                               max_collection_depth=1 if reason == 'depth' else None)
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
    assert values['Rejected'] == values['Size before'] == [1] * 8
    assert values['Untouched'] == [1, 1, 2, 3, 4, 5, 6, 7]
    assert values['Healthy'] == list(range(1, 9))
    assert values['Previous'] == list(range(1, 8))
