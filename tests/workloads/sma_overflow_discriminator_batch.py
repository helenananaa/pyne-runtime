# ruff: noqa: F821
import numpy as np
indicator("sma_overflow_discriminator batch")

def input_at(i):
    coefficients = (0, -2, 0, 4, -3, 3, 0, 0, None, -2, 0, 4, 2, 3, -3, None, -1, 3, 4, -3, None, -2, -1, -4, 0, -3, -3, None, -3, -1, -2, None)
    small = {8: .25, 15: .25, 20: -.5, 27: -.5, 31: -.5}
    index = i % 32
    return small[index] if index in small else coefficients[index] * (2. ** 1021)

values = np.asarray([input_at(i) for i in range(len(close))], dtype=np.float64)
plot(ta.sma(values, 7), 'Native7')
plot(math.sum(values, 7), 'Sum7')
