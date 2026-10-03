# ruff: noqa: F821
indicator("Map scalar mutation", mode="incremental")
COLUMNS = [
    "Case",
    "Returned",
    "Contains 10",
    "Contains 99",
    "Get 10",
    "Get 99",
    "Map size",
    "Map key 0",
    "Map key 1",
    "Map key 2",
    "Map key 3",
    "Map key 4",
    "Map value 0",
    "Map value 1",
    "Map value 2",
    "Map value 3",
    "Map value 4",
    "Copy size",
    "Copy key 0",
    "Copy key 1",
    "Copy key 2",
    "Copy key 3",
    "Copy key 4",
    "Copy value 0",
    "Copy value 1",
    "Copy value 2",
    "Copy value 3",
    "Copy value 4",
    "Keys size",
    "Keys 0",
    "Keys 1",
    "Keys 2",
    "Keys 3",
    "Keys 4",
    "Values size",
    "Values 0",
    "Values 1",
    "Values 2",
    "Values 3",
    "Values 4",
]


def probe(i):
    c = i % 16
    m = map.from_values(20, 2.0, 10, 1.0, 30, 3.0)
    cp = map.copy(m)
    ks = map.keys(m)
    vs = map.values(m)
    returned = None
    if c == 1:
        map.put(m, 20, 8.0)
    elif c == 2:
        returned = map.remove(m, 10)
    elif c == 3:
        returned = map.remove(m, 99)
    elif c == 4:
        map.remove(m, 20)
        map.put(m, 20, 8.0)
    elif c == 5:
        map.put(cp, 20, 8.0)
    elif c == 6:
        array.set(ks, 0, 99)
        array.push(ks, 77)
    elif c == 7:
        array.set(vs, 0, 99.0)
        array.push(vs, 77.0)
    elif c == 8:
        other = map.from_values(10, 11.0, 40, 4.0, 20, 22.0)
        map.put_all(m, other)
    elif c == 9:
        map.put_all(m, m)
    elif c == 10:
        map.clear(m)
        map.put(m, 30, 9.0)
    elif c == 11:
        map.put(m, 10, None)
    elif c == 12:
        map.clear(cp)
    elif c == 13:
        map.remove(m, 20)
        map.remove(m, 10)
        map.remove(m, 30)
    elif c == 14:
        map.put(m, 20, -2.5)
        map.put(m, 10, 0.0)
        map.put(m, 30, None)
    elif c == 15:
        map.put(m, 30, 3.0)
    outputs = [
        c,
        returned,
        int(map.contains(m, 10)),
        int(map.contains(m, 99)),
        map.get(m, 10),
        map.get(m, 99),
    ]
    for value in (m, cp):
        keys = map.keys(value)
        values = map.values(value)
        outputs += [map.size(value)]
        outputs += [array.get(keys, k) if k < array.size(keys) else None for k in range(5)]
        outputs += [array.get(values, k) if k < array.size(values) else None for k in range(5)]
    for value in (ks, vs):
        outputs += [array.size(value)]
        outputs += [array.get(value, k) if k < array.size(value) else None for k in range(5)]
    return outputs


def on_bar(ctx, bar):
    for title, value in zip(COLUMNS, probe(ctx.bar_index), strict=True):
        ctx.plot(title, value)
