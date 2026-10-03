# ruff: noqa: F821
import numpy as np
strategy("Native OCA timing batch", initial_capital=1000000000, pyramiding=100, process_orders_on_close=True)
strategy.order('S1', strategy.long, qty=1, when=bar_index == 0, oca_name='same', oca_type=strategy.oca.cancel)
strategy.order('S2', strategy.long, qty=2, when=bar_index == 0, oca_name='same', oca_type=strategy.oca.cancel)
strategy.order('CB', strategy.long, qty=2, when=bar_index == 0, oca_name='before', oca_type=strategy.oca.cancel, stop=79400)
strategy.order('CA', strategy.long, qty=1, when=bar_index == 0, oca_name='before', oca_type=strategy.oca.cancel)
strategy.order('AA', strategy.long, qty=1, when=bar_index == 0, oca_name='after', oca_type=strategy.oca.cancel)
strategy.order('AB', strategy.long, qty=2, when=bar_index == 0, oca_name='after', oca_type=strategy.oca.cancel, stop=79400)
strategy.order('NB', strategy.long, qty=2, when=bar_index == 0, oca_name='', oca_type=strategy.oca.none, stop=79400)
strategy.order('NA', strategy.long, qty=1, when=bar_index == 0, oca_name='', oca_type=strategy.oca.none)
strategy.order('R1', strategy.long, qty=1, when=bar_index == 0, oca_name='same_reduce', oca_type=strategy.oca.reduce)
strategy.order('R2', strategy.long, qty=2, when=bar_index == 0, oca_name='same_reduce', oca_type=strategy.oca.reduce)
strategy.order('RB', strategy.long, qty=3, when=bar_index == 0, oca_name='reduce_before', oca_type=strategy.oca.reduce, stop=79400)
strategy.order('RA', strategy.long, qty=1, when=bar_index == 0, oca_name='reduce_before', oca_type=strategy.oca.reduce)
strategy.order('QA', strategy.long, qty=1, when=bar_index == 0, oca_name='reduce_after', oca_type=strategy.oca.reduce)
strategy.order('QB', strategy.long, qty=3, when=bar_index == 0, oca_name='reduce_after', oca_type=strategy.oca.reduce, stop=79400)
strategy.order('TB', strategy.long, qty=2, when=bar_index == 0, oca_name='triggered', oca_type=strategy.oca.cancel, stop=close-1)
strategy.order('TA', strategy.long, qty=1, when=bar_index == 0, oca_name='triggered', oca_type=strategy.oca.cancel)
strategy.order('PC1', strategy.long, qty=1, when=bar_index == 0, oca_name='pending_cancel', oca_type=strategy.oca.cancel, stop=79400)
strategy.order('PC2', strategy.long, qty=2, when=bar_index == 0, oca_name='pending_cancel', oca_type=strategy.oca.cancel, stop=79410)
strategy.order('PR1', strategy.long, qty=1, when=bar_index == 0, oca_name='pending_reduce', oca_type=strategy.oca.reduce, stop=79400)
strategy.order('PR2', strategy.long, qty=3, when=bar_index == 0, oca_name='pending_reduce', oca_type=strategy.oca.reduce, stop=79410)
plot(strategy.position_size, "position")
plot(strategy.opentrades, "openCount")
# This capture only appends long lots; it has no exits or ID reordering.
# Public scalar IDs identify stable slots; sizes supply their per-bar history.
count = int(np.max(np.asarray(strategy.opentrades.count)))
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'S1':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'S1')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'S2':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'S2')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'CB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'CB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'CA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'CA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'AA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'AA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'AB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'AB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'NB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'NB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'NA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'NA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'R1':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'R1')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'R2':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'R2')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'RB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'RB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'RA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'RA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'QA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'QA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'QB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'QB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'TB':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'TB')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'TA':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'TA')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'PC1':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'PC1')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'PC2':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'PC2')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'PR1':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'PR1')
quantity = np.zeros(len(close))
for j in range(count):
    if strategy.opentrades.entry_id(j) == 'PR2':
        quantity += np.nan_to_num(np.asarray(strategy.opentrades.size(j)), nan=0.0)
plot(quantity, 'PR2')
