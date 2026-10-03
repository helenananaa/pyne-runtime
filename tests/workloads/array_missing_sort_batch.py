# ruff: noqa: F821
indicator("Array missing sort")

CASES = [[3, 1, 2, 1, 3], [3, None, 1, None, 2], [None, 3, 1, 2, 4], [3, 1, 2, 4, None], [None, None, None, None, None], [], [-2], [None, -2, 0, -2, None]]
COLUMNS = ['Case', 'Size', 'Sum', 'Average', 'Minimum', 'Maximum', 'Original 0', 'Original 1', 'Original 2', 'Original 3', 'Original 4', 'Ascending 0', 'Ascending 1', 'Ascending 2', 'Ascending 3', 'Ascending 4', 'Descending 0', 'Descending 1', 'Descending 2', 'Descending 3', 'Descending 4', 'Ascending index 0', 'Ascending index 1', 'Ascending index 2', 'Ascending index 3', 'Ascending index 4', 'Descending index 0', 'Descending index 1', 'Descending index 2', 'Descending index 3', 'Descending index 4', 'Ascending success', 'Descending success', 'Ascending index success', 'Descending index success']

def probe(i):
    a = array.from_values(*CASES[i % 8])
    outputs = [i % 8, array.size(a), array.sum(a), array.avg(a), array.min(a), array.max(a)]
    outputs += [array.get(a,k) if k < array.size(a) else None for k in range(5)]
    success = []
    for direction in (order.ascending, order.descending):
        copy = array.copy(a)
        try:
            array.sort(copy, direction)
            success.append(1)
        except TypeError:
            success.append(0)
        outputs += [array.get(copy,k) if k < array.size(copy) else None for k in range(5)]
    for direction in (order.ascending, order.descending):
        try:
            indices = array.sort_indices(a, direction)
            success.append(1)
            outputs += [array.get(indices,k) if k < array.size(indices) else None for k in range(5)]
        except TypeError:
            success.append(0)
            outputs += [None] * 5
    return outputs + success

outputs = [probe(i) for i in range(len(close))]
for column, title in enumerate(COLUMNS):
    plot([row[column] for row in outputs], title)
