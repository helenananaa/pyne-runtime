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
        if ctx.strategy.opentrades.entry_id(j) == 'L0':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held L0', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'L1':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held L1', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'L2':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held L2', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'L3':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held L3', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'R':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held R', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'S5':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held S5', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'S6':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held S6', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'S7':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held S7', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'N9':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held N9', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'N10':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held N10', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'N11':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held N11', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'N12':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held N12', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'Order':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held Order', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'Blocked14':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held Blocked14', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'Repeated':
            quantity += ctx.strategy.opentrades.size(j) * (-1 if ctx.strategy.opentrades.side(j) == "short" else 1)
    ctx.plot('Held Repeated', quantity)
    ctx.strategy.entry('L0', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, price=bar.close)
    ctx.strategy.entry('L1', ctx.strategy.long, qty=1, when=ctx.bar_index == 1, price=bar.close)
    ctx.strategy.entry('L2', ctx.strategy.long, qty=1, when=ctx.bar_index == 2, price=bar.close)
    ctx.strategy.entry('L3', ctx.strategy.long, qty=1, when=ctx.bar_index == 3, price=bar.close)
    ctx.strategy.entry('R', ctx.strategy.short, qty=2, when=ctx.bar_index == 4, price=bar.close)
    ctx.strategy.entry('S5', ctx.strategy.short, qty=1, when=ctx.bar_index == 5, price=bar.close)
    ctx.strategy.entry('S6', ctx.strategy.short, qty=1, when=ctx.bar_index == 6, price=bar.close)
    ctx.strategy.entry('S7', ctx.strategy.short, qty=1, when=ctx.bar_index == 7, price=bar.close)
    ctx.strategy.close_all(when=ctx.bar_index == 8, price=bar.close)
    ctx.strategy.entry('N9', ctx.strategy.long, qty=1, when=ctx.bar_index == 9, price=bar.close)
    ctx.strategy.entry('N10', ctx.strategy.long, qty=1, when=ctx.bar_index == 10, price=bar.close)
    ctx.strategy.entry('N11', ctx.strategy.long, qty=1, when=ctx.bar_index == 11, price=bar.close)
    ctx.strategy.entry('N12', ctx.strategy.long, qty=1, when=ctx.bar_index == 12, price=bar.close)
    ctx.strategy.order('Order', ctx.strategy.long, qty=3, when=ctx.bar_index == 13, price=bar.close)
    ctx.strategy.entry('Blocked14', ctx.strategy.long, qty=1, when=ctx.bar_index == 14, price=bar.close)
    ctx.strategy.close_all(when=ctx.bar_index == 15, price=bar.close)
    ctx.strategy.entry('Repeated', ctx.strategy.long, qty=0.5, when=ctx.bar_index == 16, price=bar.close)
    ctx.strategy.entry('Repeated', ctx.strategy.long, qty=0.5, when=ctx.bar_index == 17, price=bar.close)
    ctx.strategy.entry('Repeated', ctx.strategy.long, qty=0.5, when=ctx.bar_index == 18, price=bar.close)
    ctx.strategy.entry('Repeated', ctx.strategy.long, qty=0.5, when=ctx.bar_index == 19, price=bar.close)
    ctx.strategy.close('Repeated', qty=0.5, when=ctx.bar_index == 18, price=bar.close)
    ctx.strategy.close_all(when=ctx.bar_index == 20, price=bar.close)
