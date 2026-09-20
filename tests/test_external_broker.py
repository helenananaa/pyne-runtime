import pytest
from pyne_runtime.external import run_external

BARS = [{"time": i * 60, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1} for i in range(3)]
ACCOUNTS = [{"time": i * 60, "position_size": qty, "position_avg_price": 10 if qty else None,
             "equity": 1000, "initial_capital": 1000, "netprofit": 0, "openprofit": 0} for i, qty in enumerate([0, 1, 0])]


@pytest.mark.parametrize("source", ['''strategy("External")
strategy.entry_when(strategy.position_size == 0, "L", strategy.long)
strategy.close_when(strategy.position_size > 0, "L")
plot(strategy.equity)
''', '''def init(ctx):
    ctx.strategy.configure()
def on_bar(ctx, bar):
    if ctx.strategy.position_size == 0:
        ctx.strategy.entry("L", ctx.strategy.long)
    else:
        ctx.strategy.close("L")
'''])
def test_host_feedback_drives_real_script_without_native_fills(source):
    result = run_external(source, BARS, ACCOUNTS)
    assert [row["action"] for row in result["intents"]] == ["entry", "close", "entry"]
    assert "strategy" not in result["output"]


def test_unsupported_order_is_rejected():
    with pytest.raises(ValueError, match="unsupported entry"):
        run_external('strategy("x")\nstrategy.entry("L", comment="unsupported")', BARS, ACCOUNTS)


def test_inconsistent_feedback_is_rejected():
    with pytest.raises(ValueError, match="count"):
        run_external('strategy("x")', BARS, ACCOUNTS[:1])


def test_batch_series_prices_and_partial_brackets():
    source = '''strategy("Orders")
strategy.entry("L", strategy.long, qty=close/5, limit=close, stop=close+1)
strategy.exit("X", "L", qty_percent=50, limit=close+2, stop=close-2)
strategy.cancel("X")
strategy.cancel_all()
'''
    result = run_external(source, BARS, ACCOUNTS)
    first = result["intents"][:4]
    assert [row["action"] for row in first] == ["entry", "exit", "cancel", "cancel_all"]
    assert first[0]["limit"] == 10 and first[0]["qty"] == 2
    assert first[1]["qty_percent"] == 50 and first[1]["from_entry"] == "L"
    assert "strategy" not in result["output"]



def test_fill_callback_passes_preserve_one_bar_and_external_account():
    from pyne_runtime.external import run_external
    bars = [dict(time=i*60, open=10, high=11, low=9, close=10, volume=100) for i in range(2)]
    frames = [dict(time=i*60, position_size=0, position_avg_price=None, equity=1000,
        initial_capital=1000, netprofit=0, openprofit=0) for i in range(2)]
    groups = [[dict(bar=bars[0], account=frames[0], event_time_ms=59999, confirmed=True)],
        [dict(bar={**bars[1], "high":10, "low":10, "volume":25},
            account={**frames[1], "position_size":1, "position_avg_price":10}, event_time_ms=60000, confirmed=False),
         dict(bar=bars[1], account=frames[1], event_time_ms=119999, confirmed=True)]]
    source = """def init(ctx):
    ctx.strategy.configure(calc_on_order_fills=True)
def on_bar(ctx, bar):
    if ctx.bar_index == 0:
        ctx.strategy.entry("L", qty=1)
def on_fill(ctx, bar):
    if ctx.strategy.position_size > 0 and bar.high == 10:
        ctx.strategy.close("L")
"""
    result = run_external(source, bars, frames, execution_passes=groups)
    assert [(row["bar_index"], row["pass_index"], row["action"]) for row in result["intents"]] == [(0,0,"entry"),(1,0,"close")]
    assert not result["output"].get("strategy")
    groups[1].reverse()
    with pytest.raises(ValueError, match="invalid execution pass"):
        run_external(source, bars, frames, execution_passes=groups)


def test_external_opt_in_request_provider_stays_host_neutral():
    from pyne_runtime.settings import PyneSettings
    from pyne_runtime.metadata import SymbolInfo, TimeframeInfo
    class Provider:
        def get_ohlcv(self, symbol, timeframe, start, end):
            assert symbol == "X:OTHER"
            return [{**bar, "open":100, "high":101, "low":99, "close":100} for bar in BARS]
    settings = PyneSettings(data_provider=Provider(), syminfo=SymbolInfo.from_value("X:MAIN"),
                            timeframe=TimeframeInfo.from_value("1"))
    source = 'strategy("Requests")\nremote=request.security("X:OTHER", "1", "close")\nstrategy.entry_when(remote > 50, "L", strategy.long)'
    result = run_external(source, BARS, ACCOUNTS, settings=settings, allow_requests=True)
    assert len(result["intents"]) == 3
    assert not result["output"].get("strategy")
    with pytest.raises(ValueError, match="request data"):
        run_external(source, BARS, ACCOUNTS, settings=settings)


def test_external_pyramiding_and_tick_exit_intents_are_host_neutral():
    source = '''strategy("Intents", pyramiding=3)
strategy.entry("A", strategy.long, qty=2)
strategy.entry("B", strategy.long, qty=1)
strategy.exit("X", "A", profit=4, loss=2)
strategy.exit("T", "B", trail_points=3, trail_offset=1)
'''
    result = run_external(source, BARS[:1], ACCOUNTS[:1])
    assert result["pyramiding"] == 3
    assert [row["id"] for row in result["intents"]] == ["A","B","X","T"]
    assert result["intents"][2]["profit"] == 4
    assert result["intents"][3]["trail_offset"] == 1
    assert not result["output"].get("strategy")


def test_pass_request_cache_and_init_alias_follow_supplied_data():
    from pyne_runtime.settings import PyneSettings
    from pyne_runtime.metadata import TimeframeInfo
    empty = [{"symbol":"X:OTHER","timeframe":"2","bars":[]}]
    full = [{**empty[0],"bars":[dict(time=0,open=100,high=101,low=99,close=100,volume=1)]}]
    groups = [[dict(bar=BARS[0],account=ACCOUNTS[0],event_time_ms=59999,confirmed=True,request_data=empty)],
        [dict(bar=BARS[1],account=ACCOUNTS[1],event_time_ms=60000,confirmed=False,request_data=empty),
         dict(bar=BARS[1],account=ACCOUNTS[1],event_time_ms=119999,confirmed=True,request_data=full)]]
    source = '''def init(ctx):
    ctx.strategy.configure(calc_on_order_fills=True)
    ctx.alias = request

def decide(ctx):
    remote = ctx.alias.security("X:OTHER", "2", "close")
    if remote is None or remote != remote:
        ctx.strategy.entry("L")
    else:
        ctx.strategy.close_all()

def on_bar(ctx, bar):
    decide(ctx)

def on_fill(ctx, bar):
    decide(ctx)
'''
    result = run_external(source,BARS[:2],ACCOUNTS[:2],execution_passes=groups,allow_requests=True,
                          settings=PyneSettings(timeframe=TimeframeInfo.from_value("1")))
    assert [(row["bar_index"],row["pass_index"],row["action"]) for row in result["intents"]] == [(0,0,"entry"),(1,0,"entry"),(1,1,"close_all")]
