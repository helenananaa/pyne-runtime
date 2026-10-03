# ruff: noqa: F821
indicator("Pending stop_limit_wait_300 generic callback", mode="incremental")

def init(ctx):
    ctx.strategy.configure(process_orders_on_close=True, initial_capital=1000000000, pyramiding=1, margin_long=0, margin_short=0)

def on_bar(ctx, bar):
    ctx.plot('Position', ctx.strategy.position_size)
    ctx.plot('Open trades', ctx.strategy.opentrades)
    ctx.plot('Closed trades', ctx.strategy.closedtrades)
    ctx.plot('Average', ctx.strategy.position_avg_price)
    ctx.plot('Net profit', ctx.strategy.netprofit)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'Seed':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot("Held Seed", quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'A':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot("Held A", quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'B':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot("Held B", quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'C':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot("Held C", quantity)
    ctx.strategy.entry("A", ctx.strategy.long, qty=1, stop=371, limit=300, when=ctx.bar_index == 0)
    ctx.strategy.cancel("A", when=ctx.bar_index == 2)
    ctx.strategy.entry("A", ctx.strategy.short, qty=2, stop=1000, limit=380, when=ctx.bar_index == 2)
