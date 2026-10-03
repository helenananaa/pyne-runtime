# ruff: noqa: F821
indicator("Matrix empty shapes", mode="batch")
COLUMNS = ['Case', 'Original rows', 'Original columns', 'Original cells', 'Copy rows', 'Copy columns', 'Copy cells', 'Transpose rows', 'Transpose columns', 'Transpose cells', 'Reshape rows', 'Reshape columns', 'Reshape cells', 'Alias rows', 'Alias columns', 'Alias cells', 'Copy preserved rows', 'Copy preserved columns', 'Copy preserved cells', 'Add scalar rows', 'Add scalar columns', 'Add scalar cells', 'Subtract scalar rows', 'Subtract scalar columns', 'Subtract scalar cells', 'Multiply scalar rows', 'Multiply scalar columns', 'Multiply scalar cells', 'Product rows', 'Product columns', 'Product cells', 'Product first', 'Product success', 'Row size', 'Column size', 'Row extraction success', 'Column extraction success']

def shape(m):
    return [matrix.rows(m),matrix.columns(m),matrix.elements_count(m)]

def probe(i):
    c = i % 8
    dimensions = [(0,0),(0,3),(3,0),(1,0),(0,3),(3,0),(1,0),(2,2)]
    targets = [(0,0),(3,0),(0,3),(0,1),(0,3),(3,0),(1,0),(1,4)]
    h,w = dimensions[c]
    m = matrix.new_float(h,w,2.0)
    alias = m
    cp = matrix.copy(m)
    tr = matrix.transpose(m)
    row_size = array.size(matrix.row(m,0)) if h > 0 else None
    col_success = 0
    col_size = None
    if w > 0:
        try:
            col_size = array.size(matrix.col(m,w-1))
            col_success = 1
        except IndexError:
            pass
    outputs = [c]+shape(m)+shape(cp)+shape(tr)
    rh,rw = targets[c]
    arithmetic = shape(matrix.add(m,2.0))+shape(matrix.sub(m,2.0))+shape(matrix.mult(m,2.0))
    try:
        product = matrix.mult(m,matrix.new_float(w,2,1.0))
        arithmetic += shape(product)+[matrix.get(product,0,0) if h > 0 and matrix.columns(product) > 0 else None,1]
    except ValueError:
        arithmetic += [None,None,None,None,0]
    matrix.reshape(m,rh,rw)
    return outputs+shape(m)+shape(alias)+shape(cp)+arithmetic+[row_size,col_size,int(h > 0),col_success]

outputs = [probe(i) for i in range(len(close))]
for column,title in enumerate(COLUMNS):
    plot([row[column] for row in outputs],title)
