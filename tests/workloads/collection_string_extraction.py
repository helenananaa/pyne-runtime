# ruff: noqa: F821
indicator("Collection string extraction", mode="incremental")
COLUMNS = ['Case', 'Bool first', 'Bool last', 'Rows', 'Columns', 'Row detached', 'Col detached', 'Map detached', 'Copy detached']
TEXT_COLUMNS = ['Matrix row', 'Matrix col', 'Matrix copy', 'Matrix transpose', 'Matrix reshape', 'Map values', 'Map copy']

def probe(i):
    c = i % 8
    m = matrix.new_string(2,2)
    if c == 1:
        matrix.fill(m,"alpha")
        matrix.fill(m,None)
    elif c == 2:
        matrix.set(m,0,0,"alpha")
        matrix.set(m,0,0,None)
    elif c == 3:
        matrix.fill(m,"猫")
    elif c == 4:
        matrix.set(m,0,0,'a"b')
        matrix.set(m,1,1,"β")
    elif c == 5:
        matrix.fill(m,"")
    elif c == 6:
        matrix.set(m,0,1,"NaN")
    elif c == 7:
        matrix.fill(m,"x")
        matrix.fill(m,None)
    r = matrix.row(m,0)
    k = matrix.col(m,1)
    copied = matrix.copy(m)
    transposed = matrix.transpose(m)
    texts = [array.join(r,"|"),array.join(k,"|"),array.join(matrix.row(copied,0),"|"),array.join(matrix.row(transposed,1),"|")]
    matrix.reshape(copied,1,4)
    texts.append(array.join(matrix.row(copied,0),"|"))
    array.set(r,0,"row edit")
    array.set(k,0,"col edit")
    row_detached = matrix.get(m,0,0) != "row edit"
    col_detached = matrix.get(m,0,1) != "col edit"
    matrix.set(copied,0,0,"copy edit")
    copy_detached = matrix.get(m,0,0) != "copy edit"
    d = map.new()
    map.put(d,0,"seed")
    map.put(d,1,"other")
    if c == 7:
        map.clear(d)
    map.put(d,0,"猫" if c == 3 else 'a"b' if c == 4 else "" if c == 5 else None)
    map.put(d,1,"猫" if c == 3 else "β" if c == 4 else "" if c == 5 else "NaN" if c == 6 else None)
    dc = map.copy(d)
    values = map.values(d)
    texts += [array.join(values,"|"),array.join(map.values(dc),"|")]
    array.set(values,0,"map edit")
    map_detached = map.get(d,0) != "map edit"
    flags = matrix.new_bool(2,2) if c % 2 == 0 else matrix.new_bool(2,2,True)
    outputs = [c,matrix.get(flags,0,0),matrix.get(flags,1,1),matrix.rows(m),matrix.columns(m),int(row_detached),int(col_detached),int(map_detached),int(copy_detached)]
    return outputs,texts

def on_bar(ctx, bar):
    outputs,texts = probe(ctx.bar_index)
    for title,value in zip(COLUMNS,outputs,strict=True):
        ctx.plot(title,value)
    for title,text in zip(TEXT_COLUMNS,texts,strict=True):
        label.new(ctx.bar_index,0,text="JOIN|"+str(ctx.bar_index)+"|"+title+"|"+text)
