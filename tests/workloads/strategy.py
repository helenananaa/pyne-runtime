# ruff: noqa: F821
"""First-party workload: cancelled stop, entry, partial reduction, final close."""

indicator("Strategy lifecycle", mode="incremental")


def init(ctx):
    ctx.strategy.configure(
        initial_capital=10000, commission_type="cash_per_order", commission_value=1
    )


def on_bar(ctx, bar):
    index = ctx.bar_index
    ctx.strategy.entry("Never", ctx.strategy.long, qty=1, stop=1000, when=index == 0)
    ctx.strategy.cancel("Never", when=index == 1)
    ctx.strategy.entry("Long", ctx.strategy.long, qty=4, price=bar.close, when=index == 2)
    ctx.strategy.order("Reduce", ctx.strategy.short, qty=1, price=bar.close, when=index == 5)
    ctx.strategy.close("Long", price=bar.close, when=index == 9)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net profit", ctx.strategy.netprofit)
