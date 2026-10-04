"""MFI keeps independent non-missing money-flow windows across restore."""

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.ta import _StepMFI
from pyne_runtime.ta import TaModule


@pytest.mark.parametrize("period", [1, 2, 3])
@pytest.mark.parametrize("volume", [
    [1, 1, 1, np.nan, 1, 1, 1],
    [1, np.nan, 1, 1, np.nan, 1, 1],
    [np.nan, 1, 1, 1, 1, 1, 1],
])
def test_mfi_missing_volume_matches_batch_independent_flow_windows(volume, period):
    source = np.array([1, 2, 1, 2, 1, 3, 2], dtype=float)
    weights = np.asarray(volume, dtype=float)
    expected = TaModule().mfi(source, period, volume=weights)
    helper = _StepMFI(period)
    actual = np.asarray([helper.update(price, weight)
                         for price, weight in zip(source, weights)], dtype=float)
    np.testing.assert_allclose(actual, expected, equal_nan=True)


SCRIPT = '''indicator("MFI missing", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("MFI", ctx.ta.mfi("mfi", 2).update(
        bar.close, None if ctx.bar_index == 3 else bar.volume))
'''


def test_mfi_missing_volume_survives_same_version_portable_restore():
    bars = [dict(time=i * 10, open=v, high=v, low=v, close=v, volume=1)
            for i, v in enumerate([1, 2, 1, 2, 1, 3])]
    settings = pn.PyneSettings(executor_mode="inline", timeframe="10S")
    original = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    original.seed(bars[:4])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(), script=SCRIPT, settings=settings)
    for bar in bars[4:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)


def test_public_mfi_missing_volume_batch_incremental_parity():
    bars = [dict(time=i * 10, open=v, high=v, low=v, close=v, volume=1)
            for i, v in enumerate([1, 2, 1, 2])]
    report = pn.run_incremental_parity(
        batch_script='''indicator("MFI missing")
plot(ta.mfi(close, 2, volume=when(bar_index == 3, na, volume)), "MFI")
''',
        incremental_script=SCRIPT,
        bars=bars,
        normalizer=lambda result: result.values("MFI"),
    )
    report.assert_ok()
    assert report.incremental_result.values("MFI")[-1] == pytest.approx(200 / 3)
