# ruff: noqa: F821
strategy(
    "Strategy lifecycle",
    initial_capital=10000,
    commission_type="cash_per_order",
    commission_value=1,
)
strategy.entry("Never", strategy.long, qty=1, stop=1000, when=bar_index == 0)
strategy.cancel("Never", when=bar_index == 1)
strategy.entry_when(bar_index == 2, "Long", strategy.long, qty=4, price=close)
strategy.order_when(bar_index == 5, "Reduce", strategy.short, qty=1, price=close)
strategy.close_when(bar_index == 9, "Long", price=close)
plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net profit")
