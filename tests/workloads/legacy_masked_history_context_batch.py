# ruff: noqa: F821
import numpy as np
indicator("Legacy masked history contexts")
i = np.arange(len(close))
core_origin_c_values = np.asarray([73257.8, 73766.3, 73731.3, 73497.6, 73319.5, 73106.6, 72776.1, 72875.7, 72855.2, 72725.9], dtype=float)
core_origin_c = np.full(len(i), np.nan)
core_origin_c_valid = (i >= 0) & (i < 10)
core_origin_c[core_origin_c_valid] = core_origin_c_values[i[core_origin_c_valid] - 0]
core_origin_h_values = np.asarray([73890.0, 73865.0, 73998.8, 73815.9, 73507.9, 73339.3, 73177.8, 72907.8, 73084.0, 72878.1], dtype=float)
core_origin_h = np.full(len(i), np.nan)
core_origin_h_valid = (i >= 0) & (i < 10)
core_origin_h[core_origin_h_valid] = core_origin_h_values[i[core_origin_h_valid] - 0]
core_origin_l_values = np.asarray([73235.0, 73171.0, 73692.9, 73307.7, 73283.5, 72917.0, 72668.0, 72573.5, 72801.1, 72551.0], dtype=float)
core_origin_l = np.full(len(i), np.nan)
core_origin_l_valid = (i >= 0) & (i < 10)
core_origin_l[core_origin_l_valid] = core_origin_l_values[i[core_origin_l_valid] - 0]
plot(ta.highest(core_origin_c, 3), 'Native core origin Highest 3')
plot(ta.lowest(core_origin_c, 3), 'Native core origin Lowest 3')
plot(ta.highestbars(core_origin_c, 3), 'Native core origin Highest Bars 3')
plot(ta.lowestbars(core_origin_c, 3), 'Native core origin Lowest Bars 3')
core_leading_c_values = np.asarray([73257.8, 73766.3, 73731.3, 73497.6, 73319.5, 73106.6, 72776.1, 72875.7, 72855.2, 72725.9], dtype=float)
core_leading_c = np.full(len(i), np.nan)
core_leading_c_valid = (i >= 16) & (i < 26)
core_leading_c[core_leading_c_valid] = core_leading_c_values[i[core_leading_c_valid] - 16]
core_leading_h_values = np.asarray([73890.0, 73865.0, 73998.8, 73815.9, 73507.9, 73339.3, 73177.8, 72907.8, 73084.0, 72878.1], dtype=float)
core_leading_h = np.full(len(i), np.nan)
core_leading_h_valid = (i >= 16) & (i < 26)
core_leading_h[core_leading_h_valid] = core_leading_h_values[i[core_leading_h_valid] - 16]
core_leading_l_values = np.asarray([73235.0, 73171.0, 73692.9, 73307.7, 73283.5, 72917.0, 72668.0, 72573.5, 72801.1, 72551.0], dtype=float)
core_leading_l = np.full(len(i), np.nan)
core_leading_l_valid = (i >= 16) & (i < 26)
core_leading_l[core_leading_l_valid] = core_leading_l_values[i[core_leading_l_valid] - 16]
plot(ta.highest(core_leading_c, 3), 'Native core leading Highest 3')
plot(ta.lowest(core_leading_c, 3), 'Native core leading Lowest 3')
plot(ta.highestbars(core_leading_c, 3), 'Native core leading Highest Bars 3')
plot(ta.lowestbars(core_leading_c, 3), 'Native core leading Lowest Bars 3')
oscillator_origin_c_values = np.asarray([71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5, 71266.6, 70615.2, 70820.0, 70920.7, 70782.3, 70235.1, 70076.7], dtype=float)
oscillator_origin_c = np.full(len(i), np.nan)
oscillator_origin_c_valid = (i >= 0) & (i < 18)
oscillator_origin_c[oscillator_origin_c_valid] = oscillator_origin_c_values[i[oscillator_origin_c_valid] - 0]
oscillator_origin_h_values = np.asarray([72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0, 71397.0, 71357.2, 70855.9, 71022.4, 71022.7, 70820.8, 70414.9], dtype=float)
oscillator_origin_h = np.full(len(i), np.nan)
oscillator_origin_h_valid = (i >= 0) & (i < 18)
oscillator_origin_h[oscillator_origin_h_valid] = oscillator_origin_h_values[i[oscillator_origin_h_valid] - 0]
oscillator_origin_l_values = np.asarray([71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0, 71071.5, 70555.7, 70038.0, 70768.5, 70690.1, 70222.2, 69889.1], dtype=float)
oscillator_origin_l = np.full(len(i), np.nan)
oscillator_origin_l_valid = (i >= 0) & (i < 18)
oscillator_origin_l[oscillator_origin_l_valid] = oscillator_origin_l_values[i[oscillator_origin_l_valid] - 0]
plot(ta.stoch(oscillator_origin_c, oscillator_origin_h, oscillator_origin_l, 3), 'Native oscillator origin Stoch 3')
plot(ta.stoch(oscillator_origin_c, oscillator_origin_h, oscillator_origin_l, 6), 'Native oscillator origin Stoch 6')
oscillator_leading_c_values = np.asarray([71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5, 71266.6, 70615.2, 70820.0, 70920.7, 70782.3, 70235.1, 70076.7], dtype=float)
oscillator_leading_c = np.full(len(i), np.nan)
oscillator_leading_c_valid = (i >= 16) & (i < 34)
oscillator_leading_c[oscillator_leading_c_valid] = oscillator_leading_c_values[i[oscillator_leading_c_valid] - 16]
oscillator_leading_h_values = np.asarray([72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0, 71397.0, 71357.2, 70855.9, 71022.4, 71022.7, 70820.8, 70414.9], dtype=float)
oscillator_leading_h = np.full(len(i), np.nan)
oscillator_leading_h_valid = (i >= 16) & (i < 34)
oscillator_leading_h[oscillator_leading_h_valid] = oscillator_leading_h_values[i[oscillator_leading_h_valid] - 16]
oscillator_leading_l_values = np.asarray([71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0, 71071.5, 70555.7, 70038.0, 70768.5, 70690.1, 70222.2, 69889.1], dtype=float)
oscillator_leading_l = np.full(len(i), np.nan)
oscillator_leading_l_valid = (i >= 16) & (i < 34)
oscillator_leading_l[oscillator_leading_l_valid] = oscillator_leading_l_values[i[oscillator_leading_l_valid] - 16]
plot(ta.stoch(oscillator_leading_c, oscillator_leading_h, oscillator_leading_l, 3), 'Native oscillator leading Stoch 3')
plot(ta.stoch(oscillator_leading_c, oscillator_leading_h, oscillator_leading_l, 6), 'Native oscillator leading Stoch 6')
context_origin_c_values = np.asarray([72193.1, 71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5], dtype=float)
context_origin_c = np.full(len(i), np.nan)
context_origin_c_valid = (i >= 0) & (i < 12)
context_origin_c[context_origin_c_valid] = context_origin_c_values[i[context_origin_c_valid] - 0]
context_origin_h_values = np.asarray([72583.7, 72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0], dtype=float)
context_origin_h = np.full(len(i), np.nan)
context_origin_h_valid = (i >= 0) & (i < 12)
context_origin_h[context_origin_h_valid] = context_origin_h_values[i[context_origin_h_valid] - 0]
context_origin_l_values = np.asarray([71862.6, 71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0], dtype=float)
context_origin_l = np.full(len(i), np.nan)
context_origin_l_valid = (i >= 0) & (i < 12)
context_origin_l[context_origin_l_valid] = context_origin_l_values[i[context_origin_l_valid] - 0]
plot(ta.stoch(context_origin_c, context_origin_h, context_origin_l, 4), 'Native context origin Stoch 4')
context_leading_c_values = np.asarray([72193.1, 71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5], dtype=float)
context_leading_c = np.full(len(i), np.nan)
context_leading_c_valid = (i >= 16) & (i < 28)
context_leading_c[context_leading_c_valid] = context_leading_c_values[i[context_leading_c_valid] - 16]
context_leading_h_values = np.asarray([72583.7, 72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0], dtype=float)
context_leading_h = np.full(len(i), np.nan)
context_leading_h_valid = (i >= 16) & (i < 28)
context_leading_h[context_leading_h_valid] = context_leading_h_values[i[context_leading_h_valid] - 16]
context_leading_l_values = np.asarray([71862.6, 71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0], dtype=float)
context_leading_l = np.full(len(i), np.nan)
context_leading_l_valid = (i >= 16) & (i < 28)
context_leading_l[context_leading_l_valid] = context_leading_l_values[i[context_leading_l_valid] - 16]
plot(ta.stoch(context_leading_c, context_leading_h, context_leading_l, 4), 'Native context leading Stoch 4')
remaining_origin_c_values = np.asarray([72193.1, 71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5], dtype=float)
remaining_origin_c = np.full(len(i), np.nan)
remaining_origin_c_valid = (i >= 0) & (i < 12)
remaining_origin_c[remaining_origin_c_valid] = remaining_origin_c_values[i[remaining_origin_c_valid] - 0]
remaining_origin_h_values = np.asarray([72583.7, 72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0], dtype=float)
remaining_origin_h = np.full(len(i), np.nan)
remaining_origin_h_valid = (i >= 0) & (i < 12)
remaining_origin_h[remaining_origin_h_valid] = remaining_origin_h_values[i[remaining_origin_h_valid] - 0]
remaining_origin_l_values = np.asarray([71862.6, 71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0], dtype=float)
remaining_origin_l = np.full(len(i), np.nan)
remaining_origin_l_valid = (i >= 0) & (i < 12)
remaining_origin_l[remaining_origin_l_valid] = remaining_origin_l_values[i[remaining_origin_l_valid] - 0]
remaining_leading_c_values = np.asarray([72193.1, 71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5], dtype=float)
remaining_leading_c = np.full(len(i), np.nan)
remaining_leading_c_valid = (i >= 16) & (i < 28)
remaining_leading_c[remaining_leading_c_valid] = remaining_leading_c_values[i[remaining_leading_c_valid] - 16]
remaining_leading_h_values = np.asarray([72583.7, 72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0], dtype=float)
remaining_leading_h = np.full(len(i), np.nan)
remaining_leading_h_valid = (i >= 16) & (i < 28)
remaining_leading_h[remaining_leading_h_valid] = remaining_leading_h_values[i[remaining_leading_h_valid] - 16]
remaining_leading_l_values = np.asarray([71862.6, 71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0], dtype=float)
remaining_leading_l = np.full(len(i), np.nan)
remaining_leading_l_valid = (i >= 16) & (i < 28)
remaining_leading_l[remaining_leading_l_valid] = remaining_leading_l_values[i[remaining_leading_l_valid] - 16]
warmup_origin_c_values = np.asarray([71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5, 71266.6], dtype=float)
warmup_origin_c = np.full(len(i), np.nan)
warmup_origin_c_valid = (i >= 0) & (i < 12)
warmup_origin_c[warmup_origin_c_valid] = warmup_origin_c_values[i[warmup_origin_c_valid] - 0]
warmup_origin_h_values = np.asarray([72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0, 71397.0], dtype=float)
warmup_origin_h = np.full(len(i), np.nan)
warmup_origin_h_valid = (i >= 0) & (i < 12)
warmup_origin_h[warmup_origin_h_valid] = warmup_origin_h_values[i[warmup_origin_h_valid] - 0]
warmup_origin_l_values = np.asarray([71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0, 71071.5], dtype=float)
warmup_origin_l = np.full(len(i), np.nan)
warmup_origin_l_valid = (i >= 0) & (i < 12)
warmup_origin_l[warmup_origin_l_valid] = warmup_origin_l_values[i[warmup_origin_l_valid] - 0]
plot(ta.stoch(warmup_origin_c, warmup_origin_h, warmup_origin_l, 5), 'Native warmup origin Stoch 5')
warmup_leading_c_values = np.asarray([71698.7, 71548.5, 71099.4, 71537.7, 71617.9, 71470.1, 71571.0, 71419.8, 71004.6, 71376.6, 71391.5, 71266.6], dtype=float)
warmup_leading_c = np.full(len(i), np.nan)
warmup_leading_c_valid = (i >= 16) & (i < 28)
warmup_leading_c[warmup_leading_c_valid] = warmup_leading_c_values[i[warmup_leading_c_valid] - 16]
warmup_leading_h_values = np.asarray([72288.0, 71884.9, 71662.6, 71600.0, 71788.5, 71670.7, 71645.2, 71670.0, 71419.8, 71439.5, 71564.0, 71397.0], dtype=float)
warmup_leading_h = np.full(len(i), np.nan)
warmup_leading_h_valid = (i >= 16) & (i < 28)
warmup_leading_h[warmup_leading_h_valid] = warmup_leading_h_values[i[warmup_leading_h_valid] - 16]
warmup_leading_l_values = np.asarray([71350.0, 71387.6, 71035.3, 70650.9, 71438.9, 71350.1, 71358.0, 71383.8, 70911.0, 70806.0, 71199.0, 71071.5], dtype=float)
warmup_leading_l = np.full(len(i), np.nan)
warmup_leading_l_valid = (i >= 16) & (i < 28)
warmup_leading_l[warmup_leading_l_valid] = warmup_leading_l_values[i[warmup_leading_l_valid] - 16]
plot(ta.stoch(warmup_leading_c, warmup_leading_h, warmup_leading_l, 5), 'Native warmup leading Stoch 5')
