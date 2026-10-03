# ruff: noqa: F821
import numpy as np
strategy("Stop-limit", initial_capital=1000000000, pyramiding=1, process_orders_on_close=True, margin_long=0, margin_short=0)
strategy.entry("A", strategy.short, qty=1, stop=369, limit=380, when=bar_index == 0)
strategy.entry("B", strategy.short, qty=2, stop=369, limit=380, when=bar_index == 0)
strategy.entry("C", strategy.short, qty=3, stop=369, limit=380, when=bar_index == 0)
plot(strategy.position_size, 'Position')
plot(strategy.opentrades, 'Open trades')
plot(strategy.closedtrades, 'Closed trades')
plot(strategy.position_avg_price, 'Average')
plot(strategy.netprofit, 'Net profit')
# This probe only appends lots of one direction, with no exits or slot reordering.
count = int(np.max(np.asarray(strategy.opentrades.count)))
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'Seed':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0) * (-1 if strategy.opentrades.side(j) == "short" else 1)
plot(quantity, "Held Seed")
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'A':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0) * (-1 if strategy.opentrades.side(j) == "short" else 1)
plot(quantity, "Held A")
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'B':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0) * (-1 if strategy.opentrades.side(j) == "short" else 1)
plot(quantity, "Held B")
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'C':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0) * (-1 if strategy.opentrades.side(j) == "short" else 1)
plot(quantity, "Held C")
