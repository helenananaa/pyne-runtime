# ruff: noqa: F821
indicator("Native OCA timing callback", mode="incremental")
def init(ctx):
    ctx.strategy.configure(initial_capital=1000000000, pyramiding=100)
def on_bar(ctx, bar):
    ctx.plot("position", ctx.strategy.position_size)
    ctx.plot("openCount", ctx.strategy.opentrades)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'S1':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('S1', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'S2':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('S2', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'CB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('CB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'CA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('CA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'AA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('AA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'AB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('AB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'NB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('NB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'NA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('NA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'R1':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('R1', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'R2':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('R2', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'RB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('RB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'RA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('RA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'QA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('QA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'QB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('QB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'TB':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('TB', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'TA':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('TA', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'PC1':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('PC1', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'PC2':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('PC2', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'PR1':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('PR1', quantity)
    quantity = 0.0
    for j in range(int(ctx.strategy.opentrades)):
        if ctx.strategy.opentrades.entry_id(j) == 'PR2':
            quantity += ctx.strategy.opentrades.size(j)
    ctx.plot('PR2', quantity)
    ctx.strategy.order('S1', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='same', oca_type=ctx.strategy.oca.cancel)
    ctx.strategy.order('S2', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='same', oca_type=ctx.strategy.oca.cancel)
    ctx.strategy.order('CB', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='before', oca_type=ctx.strategy.oca.cancel, stop=79400)
    ctx.strategy.order('CA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='before', oca_type=ctx.strategy.oca.cancel)
    ctx.strategy.order('AA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='after', oca_type=ctx.strategy.oca.cancel)
    ctx.strategy.order('AB', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='after', oca_type=ctx.strategy.oca.cancel, stop=79400)
    ctx.strategy.order('NB', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='', oca_type=ctx.strategy.oca.none, stop=79400)
    ctx.strategy.order('NA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='', oca_type=ctx.strategy.oca.none)
    ctx.strategy.order('R1', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='same_reduce', oca_type=ctx.strategy.oca.reduce)
    ctx.strategy.order('R2', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='same_reduce', oca_type=ctx.strategy.oca.reduce)
    ctx.strategy.order('RB', ctx.strategy.long, qty=3, when=ctx.bar_index == 0, oca_name='reduce_before', oca_type=ctx.strategy.oca.reduce, stop=79400)
    ctx.strategy.order('RA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='reduce_before', oca_type=ctx.strategy.oca.reduce)
    ctx.strategy.order('QA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='reduce_after', oca_type=ctx.strategy.oca.reduce)
    ctx.strategy.order('QB', ctx.strategy.long, qty=3, when=ctx.bar_index == 0, oca_name='reduce_after', oca_type=ctx.strategy.oca.reduce, stop=79400)
    ctx.strategy.order('TB', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='triggered', oca_type=ctx.strategy.oca.cancel, stop=bar.close-1)
    ctx.strategy.order('TA', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='triggered', oca_type=ctx.strategy.oca.cancel)
    ctx.strategy.order('PC1', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='pending_cancel', oca_type=ctx.strategy.oca.cancel, stop=79400)
    ctx.strategy.order('PC2', ctx.strategy.long, qty=2, when=ctx.bar_index == 0, oca_name='pending_cancel', oca_type=ctx.strategy.oca.cancel, stop=79410)
    ctx.strategy.order('PR1', ctx.strategy.long, qty=1, when=ctx.bar_index == 0, oca_name='pending_reduce', oca_type=ctx.strategy.oca.reduce, stop=79400)
    ctx.strategy.order('PR2', ctx.strategy.long, qty=3, when=ctx.bar_index == 0, oca_name='pending_reduce', oca_type=ctx.strategy.oca.reduce, stop=79410)
