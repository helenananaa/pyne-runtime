# ruff: noqa: F821
indicator("Rectangular matrix products", mode="incremental")
COLUMNS = ['Case', 'Product rows', 'Product columns', 'Product 0', 'Product 1', 'Product 2', 'Product 3', 'Product 4', 'Product 5', 'Product 6', 'Product 7', 'Product 8', 'Reverse transpose product rows', 'Reverse transpose product columns', 'Reverse transpose product 0', 'Reverse transpose product 1', 'Reverse transpose product 2', 'Reverse transpose product 3', 'Reverse transpose product 4', 'Reverse transpose product 5', 'Reverse transpose product 6', 'Reverse transpose product 7', 'Reverse transpose product 8', 'A before', 'B before', 'A after product write', 'B after product write', 'A after reverse write', 'B after reverse write', 'Reshape rows', 'Reshape columns', 'Alias rows', 'Alias columns', 'Alias first', 'Alias last', 'Copy first', 'Copy last']

def flat(m,k):
    return matrix.get(m,k // matrix.columns(m),k % matrix.columns(m)) if k < matrix.elements_count(m) else None

def probe(i):
    c = i % 12
    h,w,u = [(2,3,2),(3,2,3),(1,3,1),(3,1,3),(2,2,1),(1,2,3)][c] if c < 6 else (2,3,2)
    a = matrix.new_float(h,w,0.)
    b = matrix.new_float(w,u,0.)
    for r in range(h):
        for k in range(w):
            v = 0. if c == 9 else ((r*w+k) % 7-3) / 2.
            if c == 8 or (c in (6,10) and r == k == 0) or (c == 11 and r == 1 and k == 2):
                v = None
            matrix.set(a,r,k,v)
    for r in range(w):
        for k in range(u):
            v = 0. if c == 10 else ((r*u+k) % 5-2) * 2.
            if c == 8 or (c in (7,9) and r == k == 0) or (c == 11 and r == 2 and k == 1):
                v = None
            matrix.set(b,r,k,v)
    p = matrix.mult(a,b)
    reverse = matrix.mult(matrix.transpose(b),matrix.transpose(a))
    outputs = [c,matrix.rows(p),matrix.columns(p),*[flat(p,k) for k in range(9)],
               matrix.rows(reverse),matrix.columns(reverse),*[flat(reverse,k) for k in range(9)],flat(a,0),flat(b,0)]
    cp = matrix.copy(p)
    alias = p
    matrix.set(p,0,0,100.+c)
    outputs += [flat(a,0),flat(b,0)]
    matrix.set(reverse,0,0,200.+c)
    outputs += [flat(a,0),flat(b,0)]
    matrix.reshape(p,1,h*u)
    return outputs+[matrix.rows(p),matrix.columns(p),matrix.rows(alias),matrix.columns(alias),
                    flat(alias,0),flat(alias,h*u-1),flat(cp,0),flat(cp,h*u-1)]

def on_bar(ctx,bar):
    for title,value in zip(COLUMNS,probe(ctx.bar_index),strict=True):
        ctx.plot(title,value)
