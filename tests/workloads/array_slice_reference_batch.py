# ruff: noqa: F821
indicator("Array slice reference")

COLUMNS = [
    "Case",
    "Returned",
    "Parent size",
    "Parent 0",
    "Parent 1",
    "Parent 2",
    "Parent 3",
    "Parent 4",
    "Parent 5",
    "Parent 6",
    "Parent 7",
    "Parent 8",
    "Parent 9",
    "Slice size",
    "Slice 0",
    "Slice 1",
    "Slice 2",
    "Slice 3",
    "Slice 4",
    "Slice 5",
    "Nested size",
    "Nested 0",
    "Nested 1",
    "Nested 2",
    "Nested 3",
    "Nested 4",
    "Copy size",
    "Copy 0",
    "Copy 1",
    "Copy 2",
    "Copy 3",
]


def probe(i):
    a = array.from_values(1, 2, 3, 4, 5, 6, 7)
    w = array.slice(a, 1, 4)
    n = array.slice(w, 1, 3)
    cp = array.copy(w)
    c = i % 16
    returned = None
    if c == 0:
        array.set(w, 0, -1)
    elif c == 1:
        array.set(a, 2, 99)
    elif c == 2:
        array.push(w, 9)
    elif c == 3:
        returned = array.pop(w)
    elif c == 4:
        array.unshift(a, 0)
    elif c == 5:
        returned = array.remove(a, 2)
    elif c == 6:
        array.clear(w)
    elif c == 7:
        array.set(n, 0, -2)
        array.push(n, 8)
    elif c == 8:
        for _ in range(6):
            array.pop(a)
    elif c == 9:
        for _ in range(4):
            array.pop(a)
        array.push(a, 8)
        array.push(a, 9)
    elif c == 10:
        array.sort(w, order.descending)
    elif c == 11:
        array.reverse(w)
    elif c == 12:
        returned = array.shift(w)
    elif c == 13:
        array.unshift(w, 8)
    elif c == 14:
        array.insert(w, 1, 8)
    elif c == 15:
        array.set(cp, 0, 88)
    outputs = [c, returned]
    for value, capacity in ((a, 10), (w, 6), (n, 5), (cp, 4)):
        outputs += [array.size(value)] + [
            array.get(value, k) if k < array.size(value) else None for k in range(capacity)
        ]
    return outputs


outputs = [probe(i) for i in range(len(close))]
for column, title in enumerate(COLUMNS):
    plot([row[column] for row in outputs], title)
