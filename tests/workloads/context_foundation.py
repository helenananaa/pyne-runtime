# ruff: noqa: F821
import pyne_runtime as _nested_batch_runtime
indicator("Context foundation scalars", mode="incremental")


def init(ctx):
    ctx.ta.highest("_native_donchian_upper",3)
    ctx.ta.lowest("_native_donchian_lower",3)
    ctx.ta.adx("ADX 3", 3)
    ctx.ta.tr("True range")
    ctx.ta.sma("Volume SMA 3", 3)
    ctx.ta.sma("Volume SMA holes", 3)
    ctx.ta.vwap("VWAP anchor")


def on_bar(ctx, bar):
    ctx.plot("ADX 3", ctx.ta.adx("ADX 3").update(bar))
    ctx.plot("True range", ctx.ta.tr("True range").update(bar))
    ctx.plot("Volume SMA 3", ctx.ta.sma("Volume SMA 3").update(bar.volume))
    holes = None if ctx.bar_index in (1, 7, 8, 12, 23) else bar.volume
    ctx.plot("Volume SMA holes", ctx.ta.sma("Volume SMA holes").update(holes))
    ctx.plot("VWAP anchor", ctx.ta.vwap("VWAP anchor").update(
        (bar.high + bar.low + bar.close) / 3, bar.volume, anchor=ctx.bar_index % 8 == 0))
    _native_missing_outputs(ctx,bar)

NATIVE_RECIPE_EXECUTION_ROUTE = "generic_python_full_history_recompute"
_NATIVE_MISSING_OUTPUTS = ['Keltner lower', 'Keltner middle', 'Keltner upper', 'Native KC lower', 'Native KC middle', 'Native KC upper', 'OBV', 'OBV holes']
_NATIVE_BATCH_SOURCE = '# ruff: noqa: F821\nimport numpy as np\nindicator("Context foundation")\ni = np.arange(len(close))\nvolume_holes = np.where(np.isin(i, [1, 7, 8, 12, 23]), np.nan, volume)\nplot(ta.adx(period=3), "ADX 3")\nplot(ta.tr(), "True range")\nplot(ta.obv(), "OBV")\nplot(ta.volume_sma(period=3), "Volume SMA 3")\nplot(ta.vwap(hlc3, i % 8 == 0), "VWAP anchor")\nupper, middle, lower = ta.donchian(3)\nplot(upper, "Donchian upper")\nplot(middle, "Donchian middle")\nplot(lower, "Donchian lower")\nupper, middle, lower = ta.keltner(3, 1.5, width_smoothing="atr")\nplot(upper, "Keltner upper")\nplot(middle, "Keltner middle")\nplot(lower, "Keltner lower")\nplot(ta.obv(close, volume_holes), "OBV holes")\nplot(ta.volume_sma(volume_holes, 3), "Volume SMA holes")\n# Preserve the direct native KC comparison as well as the ATR-formula control.\nupper, middle, lower = ta.keltner(3, 1.5)\nplot(upper, "Native KC upper")\nplot(middle, "Native KC middle")\nplot(lower, "Native KC lower")\n'

def _native_missing_outputs(ctx,bar):
    history = ctx.state("_native_batch_ohlcv_history",[]).value
    history.append(dict(time=bar.time,open=bar.open,high=bar.high,low=bar.low,
                        close=bar.close,volume=bar.volume))
    result = _nested_batch_runtime.run(_NATIVE_BATCH_SOURCE,history,executor_mode="inline")
    if not result.ok:
        raise ValueError("Nested batch native recipe failed: "+str(result.error))
    values = {line["name"]:next((p["value"] for p in reversed(line["data"])
                               if p["time"]==bar.time),None) for line in result.lines}
    for title in _NATIVE_MISSING_OUTPUTS:
        ctx.plot(title,values.get(title))
    upper = ctx.ta.highest("_native_donchian_upper").update(bar.high)
    lower = ctx.ta.lowest("_native_donchian_lower").update(bar.low)
    middle = None if upper is None or lower is None else (upper+lower)/2
    ctx.plot("Donchian lower",lower)
    ctx.plot("Donchian middle",middle)
    ctx.plot("Donchian upper",upper)
