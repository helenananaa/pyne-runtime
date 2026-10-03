# ruff: noqa: F821
import numpy as np
indicator("sma_long_overflow_recovery_extended batch")
SAMPLE_INDICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 31, 63, 127, 255, 511, 1023, 2047, 3071, 4080, 4081, 4082, 4083, 4084, 4085, 4086, 4087, 4088, 4089, 4090, 4091, 4092, 4093, 4094, 4095, 4096, 4097, 4098, 4099, 4100, 4101, 4102, 4103, 4104, 4105, 4106, 4107, 4108, 4109, 4110, 4111, 4998, 4999, 5000, 5001, 5002, 5003, 8190, 8191, 8192, 8193, 9998, 9999, 10000, 10001, 16382, 16383, 16384, 16385, 24998, 24999, 25000, 25001]

def input_at(i):
    large = 160000000.0 * (10. ** 300)
    return large if i < 6 else float((i * 11) % 17 - 6) * .25

values = np.asarray([input_at(i) for i in range(SAMPLE_INDICES[-1]+1)], dtype=np.float64)
plot(np.asarray(ta.sma(values, 2))[SAMPLE_INDICES], 'Native2')
plot(np.asarray(math.sum(values, 2))[SAMPLE_INDICES], 'Sum2')
plot(np.asarray(ta.sma(values, 3))[SAMPLE_INDICES], 'Native3')
plot(np.asarray(math.sum(values, 3))[SAMPLE_INDICES], 'Sum3')
