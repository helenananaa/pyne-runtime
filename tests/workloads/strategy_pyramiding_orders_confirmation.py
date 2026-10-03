# ruff: noqa: F821
indicator("Pyramiding 2 generic callback", mode="incremental")
def init(ctx):
    ctx.strategy.configure(process_orders_on_close=True, initial_capital=1000000000, pyramiding=2, margin_long=0, margin_short=0)
def on_bar(ctx, bar):
    ctx.plot('Position', ctx.strategy.position_size)
    ctx.plot('Open trades', ctx.strategy.opentrades)
    ctx.plot('Closed trades', ctx.strategy.closedtrades)
    ctx.plot('Average', ctx.strategy.position_avg_price)
    ctx.plot('Net profit', ctx.strategy.netprofit)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'A':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held A', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'B':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held B', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'C':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held C', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'D':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held D', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'E':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held E', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'F':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held F', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'G':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held G', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'H':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held H', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'I':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held I', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'J':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held J', quantity)
    ctx.strategy.entry('A', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, price=bar.close)
    ctx.strategy.order('B', ctx.strategy.long, qty=2, when=ctx.bar_index == 1, price=bar.close)
    ctx.strategy.entry('C', ctx.strategy.long, qty=1, when=ctx.bar_index == 2, price=bar.close)
    ctx.strategy.entry('D', ctx.strategy.long, qty=1, when=ctx.bar_index == 3, price=bar.close)
    ctx.strategy.close('A', when=ctx.bar_index == 4, price=bar.close)
    ctx.strategy.entry('E', ctx.strategy.long, qty=1, when=ctx.bar_index == 5, price=bar.close)
    ctx.strategy.close('B', when=ctx.bar_index == 6, price=bar.close)
    ctx.strategy.entry('F', ctx.strategy.long, qty=1, when=ctx.bar_index == 7, price=bar.close)
    ctx.strategy.close_all(when=ctx.bar_index == 8, price=bar.close)
    ctx.strategy.order('G', ctx.strategy.long, qty=1, when=ctx.bar_index == 9, price=bar.close)
    ctx.strategy.entry('H', ctx.strategy.long, qty=1, when=ctx.bar_index == 10, price=bar.close)
    ctx.strategy.order('I', ctx.strategy.long, qty=1, when=ctx.bar_index == 11, price=bar.close)
    ctx.strategy.entry('J', ctx.strategy.long, qty=1, when=ctx.bar_index == 12, price=bar.close)
    ctx.strategy.close_all(when=ctx.bar_index == 13, price=bar.close)
