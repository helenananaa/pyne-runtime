# ruff: noqa: F821
indicator("Matrix missing reshape")

CASES = [[[1, 2, 3, 4], [2, 0, 1, 2], 2], [[1, None, 3, 4], [2, 0, 1, 2], 2], [[None, None, None, None], [2, 0, 1, 2], 2], [[0, -2, 0, 5], [None, 1, 2, 0], 2], [[1, 2, 3, 4], [2, 0, 1, 2], None], [[0.5, -1.5, 2, -3], [1, 2, -2, 1], 0], [[None, 2, 3, None], [2, None, 1, 2], -2], [[0, 0, 0, 0], [1, 0, 0, 1], -1]]
COLUMNS = ['Case', 'Original 0', 'Original 1', 'Original 2', 'Original 3', 'Other 0', 'Other 1', 'Other 2', 'Other 3', 'Scalar', 'Average', 'Minimum', 'Maximum', 'Add scalar 0', 'Add scalar 1', 'Add scalar 2', 'Add scalar 3', 'Add scalar success', 'Subtract scalar 0', 'Subtract scalar 1', 'Subtract scalar 2', 'Subtract scalar 3', 'Subtract scalar success', 'Scale 0', 'Scale 1', 'Scale 2', 'Scale 3', 'Scale success', 'Add matrix 0', 'Add matrix 1', 'Add matrix 2', 'Add matrix 3', 'Add matrix success', 'Subtract matrix 0', 'Subtract matrix 1', 'Subtract matrix 2', 'Subtract matrix 3', 'Subtract matrix success', 'Product 0', 'Product 1', 'Product 2', 'Product 3', 'Product success', 'Transpose 0', 'Transpose 1', 'Transpose 2', 'Transpose 3', 'Reshape rows', 'Reshape columns', 'Reshape 0', 'Reshape 1', 'Reshape 2', 'Reshape 3', 'Alias rows', 'Alias columns', 'Alias last', 'Second reshape rows', 'Second reshape columns', 'Second reshape last', 'Row source after write', 'Column source after write', 'Original after copy write']

def flat(m,k):
    return matrix.get(m,k // matrix.columns(m),k % matrix.columns(m)) if k < matrix.elements_count(m) else None

def probe(i):
    av,bv,s = CASES[i % 8]
    a = matrix.from_rows([av[:2],av[2:]])
    b = matrix.from_rows([bv[:2],bv[2:]])
    outputs = [i % 8,*av,*bv,s,matrix.avg(a),matrix.min(a),matrix.max(a)]
    for operation in (lambda:matrix.add(a,s),lambda:matrix.sub(a,s),lambda:matrix.mult(a,s),
                      lambda:matrix.add(a,b),lambda:matrix.sub(a,b),lambda:matrix.mult(a,b)):
        try:
            result=operation()
            outputs += [flat(result,k) for k in range(4)] + [1]
        except TypeError:
            outputs += [None]*4 + [0]
    t = matrix.transpose(a)
    outputs += [flat(t,k) for k in range(4)]
    r = matrix.copy(a)
    alias = r
    matrix.reshape(r,1,4)
    outputs += [matrix.rows(r),matrix.columns(r),*[flat(r,k) for k in range(4)]]
    outputs += [matrix.rows(alias),matrix.columns(alias),flat(alias,3)]
    matrix.reshape(r,4,1)
    outputs += [matrix.rows(r),matrix.columns(r),flat(r,3)]
    row0 = matrix.row(a,0)
    col0 = matrix.col(a,0)
    array.set(row0,0,1000)
    outputs.append(matrix.get(a,0,0))
    array.set(col0,0,2000)
    outputs.append(matrix.get(a,0,0))
    matrix.set(r,0,0,3000)
    outputs.append(matrix.get(a,0,0))
    return outputs

outputs=[probe(i) for i in range(len(close))]
for column,title in enumerate(COLUMNS):
    plot([row[column] for row in outputs],title)
