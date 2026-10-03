# ruff: noqa: F821
indicator("Array search fill join", mode="incremental")
COLUMNS = [
    "Case",
    "Size",
    "First",
    "Last",
    "Includes Missing",
    "Index Missing",
    "Last index Missing",
    "Includes Two",
    "Index Two",
    "Last index Two",
    "Includes Absent",
    "Index Absent",
    "Last index Absent",
    "Filled size",
    "Filled first",
    "Filled last",
    "Filled 0",
    "Filled 1",
    "Filled 2",
    "Filled 3",
    "Filled 4",
    "Parent 0",
    "Parent 1",
    "Parent 2",
    "Parent 3",
    "Parent 4",
    "Bool first",
    "Bool last",
]
TEXT_COLUMNS = ["Float default", "Float pipe", "String default", "String pipe"]


def probe(i):
    c = i % 16
    originals = [
        [3.0, 1.0, 2.0, 1.0, 3.0],
        [None, 2.0, None, 3.0, 2.0],
        [2.0, 3.0, 1.0, 2.0, None],
        [1.0, None, 2.0, None, 3.0],
        [None] * 5,
        [],
        [2.0],
        [-2.0, 0.0, 2.0, -2.0, 2.0],
    ]
    if c < 8:
        a = array.from_list(originals[c])
    elif c == 13:
        a = array.from_values(0.123456789, 1.23456789, -0.00005, 123456789.0, -0.0)
    elif c == 14:
        a = array.from_values(1.23445, 1.23455, -1.23445, -1.23455, 0.00001)
    elif c == 15:
        a = array.from_values(0.000001, 1000000000000.1234, -1000000000000.1234, 0.0, -0.0)
    else:
        a = array.from_values(1.0, 2.0, 3.0, 4.0, 5.0)
    b = array.copy(a)
    outputs = [
        c,
        array.size(a),
        array.first(a) if array.size(a) else None,
        array.last(a) if array.size(a) else None,
    ]
    for query in (None, 2.0, 99.0):
        outputs += [
            int(array.includes(a, query)),
            array.indexof(a, query),
            array.lastindexof(a, query),
        ]
    if c == 8:
        array.fill(b, 9.0)
    elif c == 9:
        array.fill(b, 9.0, 1, 4)
    elif c == 10:
        array.fill(b, None, 1, 4)
    elif c == 11:
        array.fill(b, 8.0, 2, 2)
    elif c == 12:
        w = array.slice(a, 1, 4)
        array.fill(w, 8.0, 0, 2)
    flags = array.from_values(True, False, True) if c % 2 == 0 else array.new_bool(3)
    outputs += [
        array.size(b),
        array.first(b) if array.size(b) else None,
        array.last(b) if array.size(b) else None,
    ]
    for value in (b, a):
        outputs += [array.get(value, k) if k < array.size(value) else None for k in range(5)]
    outputs += [array.first(flags), array.last(flags)]
    strings = [
        ["alpha", "", "beta", "alpha"],
        [],
        ["alpha"],
        ["alpha", None, "beta"],
        ["NaN", "na", "true", "false"],
        ["猫", "α", "🙂"],
        ['a"b', "a,b", ""],
        [None] * 3,
    ]
    s = array.new_string(3) if c % 8 == 7 else array.from_list(strings[c % 8])
    text_outputs = [array.join(a), array.join(a, "|"), array.join(s), array.join(s, "|")]
    return outputs, text_outputs


def on_bar(ctx, bar):
    outputs, texts = probe(ctx.bar_index)
    for title, value in zip(COLUMNS, outputs, strict=True):
        ctx.plot(title, value)
    for title, text in zip(TEXT_COLUMNS, texts, strict=True):
        label.new(ctx.bar_index, 0, text="JOIN|" + str(ctx.bar_index) + "|" + title + "|" + text)
