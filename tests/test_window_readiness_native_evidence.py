"""Full initial masks from retained native logs; legacy context conflicts stay counted."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime import utils
from pyne_runtime.incremental.ta import _StepExtremeBars, _StepMonotonic, _StepStoch
from pyne_runtime.ta import TaModule

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'tests/workloads'
NAMES = ('oscillator_formula', 'stoch_transitions', 'stoch_transitions_v5',
         'context_foundation', 'oscillator_flat', 'extrema_order', 'extrema_tie_confirmation',
         'window_readiness_holdout')
spec = importlib.util.spec_from_file_location('window_readiness_report', ROOT / 'scripts/official_alignment_report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def inputs(name, callback=True):
    capture = json.loads((FOLDER / f'{name}.tradingview.json').read_text(encoding='utf-8'))
    reporter.verify_evidence(FOLDER, name, capture)
    script = (FOLDER / f'{name}{"" if callback else "_batch"}.py').read_text(encoding='utf-8')
    return script, capture, reporter._bars(name, capture)


def assert_native(result, capture, bars, count, start=0):
    assert result.ok, result.error
    lines = {line['name']: {p['time']: p['value'] for p in line['data']} for line in result.lines}
    titles = [title for title in capture['columns'] if title.startswith(
        ('Highest', 'Lowest', 'Stoch', 'Donchian', 'highest', 'lowest', 'stoch'))]
    assert titles
    for title in titles:
        col = capture['columns'].index(title)
        expected = {bars[i]['time']: capture['rows'][i]['values'][col] for i in range(start, count)
                    if capture['rows'][i]['values'][col] is not None}
        actual = lines.get(title, {})
        assert actual.keys() == expected.keys(), title
        assert actual == pytest.approx(expected, abs=capture['tolerance'], rel=0), title


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('callback', (False, True))
@pytest.mark.parametrize('count', (1, 2, 3, 5, 13, 32))
def test_initial_and_later_native_prefixes(name, callback, count):
    script, capture, bars = inputs(name, callback)
    assert_native(pn.run(script, bars[:count], executor_mode='inline'), capture, bars, count)


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('mode', ('local', 'replay', 'state'))
@pytest.mark.parametrize('cut', (1, 2, 4))
def test_preview_and_continuation_across_initial_readiness(name, mode, cut):
    script, capture, bars = inputs(name)
    original = pn.PyneIncrementalSession(script=script, settings=pn.PyneSettings(executor_mode='inline'))
    original.seed(bars[:cut])
    before = original.snapshot_portable_state()
    preview = dict(bars[cut], high=bars[cut]['high'] + 100., low=bars[cut]['low'] - 100.,
                   close=bars[cut]['close'] + 50.)
    original.on_bar_updated(preview)
    assert original.snapshot_portable_state() == before
    assert_native(original.snapshot_result(), capture, bars, cut)
    restored = pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=script) if mode == 'local' else (
        pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable(mode=mode), script=script))
    restored_before = restored.snapshot_portable_state()
    restored.on_bar_updated(preview)
    assert restored.snapshot_portable_state() == restored_before
    for count, bar in enumerate(bars[cut:], cut + 1):
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(), capture, bars, count)


@pytest.mark.parametrize('name', NAMES)
def test_display_retention_does_not_restart_initial_clock(name):
    script, capture, bars = inputs(name)
    settings = pn.PyneSettings(executor_mode='inline', max_bars=2, incremental_retention_bars=3,
                               replay_history_bars=3)
    original = pn.PyneIncrementalSession(script=script, settings=settings)
    original.seed(bars[:2])
    for bar in bars[2:13]:
        original.on_bar_closed(bar)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(original.snapshot_portable_state(),
                                                               script=script, settings=settings)
    for count, bar in enumerate(bars[13:], 14):
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
        assert_native(restored.snapshot_result(), capture, bars, count, start=count - 3)


def test_holdout_source_controls_match_independent_native_inputs():
    script, capture, _ = inputs('window_readiness_holdout')
    function = next(node for node in ast.parse(script).body if isinstance(node, ast.FunctionDef)
                    and node.name == 'sources')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<holdout input generator>', 'exec'), namespace)
    for row in capture['rows']:
        generated = namespace['sources'](row['index'])
        for col, title in enumerate(capture['columns'][:5]):
            assert generated[title] == row['values'][col]


@pytest.mark.parametrize('callback', (False, True))
def test_holdout_all_outputs_all_64_bars(callback):
    script, capture, bars = inputs('window_readiness_holdout', callback)
    assert_native(pn.run(script, bars, executor_mode='inline'), capture, bars, 64)


@pytest.mark.parametrize('mode', ('replay', 'state'))
def test_real_v32_premature_outputs_rejected_before_construction(mode, monkeypatch):
    folder = ROOT / 'tests/golden/window_readiness_semantics_v32'
    provenance = json.loads((folder / 'provenance.json').read_text())
    assert (provenance['packageVersion'], provenance['semanticsVersion']) == ('0.4.1rc27', 32)
    assert provenance['wheelSha256'] == '3d579b29604dab8930f9767a1081f70bccffcb3bd824a8dbd31d7c48590b4455'
    for name, digest in provenance['sha256'].items():
        assert hashlib.sha256((folder / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest
    old = json.loads((folder / 'committed-result.json').read_text())
    assert all(len(line['data']) == 2 for line in old['lines'])
    script = (folder / 'indicator.pyne').read_text()
    bars = json.loads((folder / 'bars.json').read_text())
    current = pn.run(script, bars, executor_mode='inline')
    assert current.ok and all(not line['data'] for line in current.lines)

    def forbidden(*args, **kwargs):
        pytest.fail('Incompatible semantics must be rejected before execution')

    monkeypatch.setattr(pn.PyneIncrementalSession, '__init__', forbidden)
    with pytest.raises(pn.PynePortableSnapshotError, match='rebuild.*OHLCV') as error:
        pn.PyneIncrementalSession.from_portable_snapshot((folder / f'{mode}.json').read_bytes(), script=script)
    assert error.value.code == 'PYNE_SNAPSHOT_SEMANTICS_MISMATCH'


def naive_extreme(source, period, highest):
    values, offsets = np.full(len(source), np.nan), np.full(len(source), np.nan)
    last_missing = -1
    for i, value in enumerate(source):
        if np.isnan(value):
            last_missing = i
            if i >= period - 1:
                offsets[i] = 0.
        elif i >= period - 1:
            first = max(0, i - period + 1, last_missing + 1)
            window = list(source[first:i + 1])
            target = max(window) if highest else min(window)
            values[i], offsets[i] = target, first + window.index(target) - i
    return values, offsets


@pytest.mark.parametrize('period', (1, 2, 3, 5, 11, 17, 40))
@pytest.mark.parametrize('pattern', ('ties', 'leading', 'all_missing', 'gaps'))
def test_independent_scans_and_prefix_causality(period, pattern):
    source = np.array([float((i // 3) % 4) for i in range(70)])
    if pattern == 'leading':
        source[:8] = np.nan
    elif pattern == 'all_missing':
        source[:] = np.nan
    elif pattern == 'gaps':
        source[5:9], source[20:37], source[60] = np.nan, np.nan, np.nan
    for highest in (False, True):
        expected, offsets = naive_extreme(source, period, highest)
        fn = utils.highest if highest else utils.lowest
        offset_fn = utils.highestbars if highest else utils.lowestbars
        step, offset_step = _StepMonotonic(period, highest=highest), _StepExtremeBars(period, highest=highest)
        np.testing.assert_allclose(fn(source, period), expected, rtol=0, atol=0, equal_nan=True)
        np.testing.assert_allclose(offset_fn(source, period), offsets, rtol=0, atol=0, equal_nan=True)
        np.testing.assert_allclose(np.asarray([step.update(v) for v in source], dtype=float),
                                   expected, rtol=0, atol=0, equal_nan=True)
        np.testing.assert_allclose(np.asarray([offset_step.update(v) for v in source], dtype=float),
                                   offsets, rtol=0, atol=0, equal_nan=True)
        for cut in (1, 2, 5, 19, 38, 70):
            np.testing.assert_allclose(fn(source[:cut], period), expected[:cut], rtol=0, atol=0, equal_nan=True)
            changed = source.copy()
            changed[cut:] = 1e6
            np.testing.assert_allclose(fn(changed, period)[:cut], expected[:cut], rtol=0, atol=0, equal_nan=True)


@pytest.mark.parametrize('period', (1, 2, 3, 5, 11, 40))
@pytest.mark.parametrize('missing_input', ('source', 'high', 'low', 'none'))
def test_stochastic_independent_masks_flat_hold_and_gap_recovery(period, missing_input):
    source = np.array([float((i * 7) % 13 - 4) for i in range(70)])
    high, low = source + 1, source - 1
    source[50:], high[50:], low[50:] = 5., 5., 5.
    if missing_input != 'none':
        {'source': source, 'high': high, 'low': low}[missing_input][5:9] = np.nan
    hi, _ = naive_extreme(high, period, True)
    lo, _ = naive_extreme(low, period, False)
    expected, previous = [], np.nan
    for src, highest_value, lowest_value in zip(source, hi, lo):
        if np.isfinite(src) and np.isfinite(highest_value) and np.isfinite(lowest_value) and highest_value != lowest_value:
            previous = 100. * (src - lowest_value) / (highest_value - lowest_value)
        expected.append(previous)
    np.testing.assert_allclose(TaModule().stoch(source, high, low, period), expected,
                               rtol=0, atol=1e-12, equal_nan=True)
    step = _StepStoch(period)
    np.testing.assert_allclose(np.asarray([step.update(src, high_value, low_value)
                                          for src, high_value, low_value in zip(source, high, low)], dtype=float), expected,
                               rtol=0, atol=1e-12, equal_nan=True)
