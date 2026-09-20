import inspect
from functools import partial, wraps
import pytest
from pyne_runtime.incremental import PyneIncrementalSession


def test_ordinary_functions_skip_reflection_and_observe_code_replacement(monkeypatch):
    calls=[]
    def noargs(): calls.append(())
    def one(bar): calls.append((bar,))
    def two(ctx,bar): calls.append((ctx,bar))
    def variadic(*args): calls.append(args)
    def forbidden(*args,**kwargs): raise AssertionError('ordinary callbacks need no reflection')
    monkeypatch.setattr(inspect,'signature',forbidden)
    invoke=PyneIncrementalSession._call_by_arity
    for callback in (noargs,one,two,variadic): invoke(None,callback,'ctx','bar')
    assert calls==[(),('bar',),('ctx','bar'),('ctx','bar')]
    one.__code__=two.__code__
    invoke(None,one,'ctx','bar')
    assert calls[-1]==('ctx','bar')


def test_signature_overrides_wrapped_and_callable_objects_keep_inspection(monkeypatch):
    calls=[]
    def base(ctx,bar): calls.append((ctx,bar))
    @wraps(base)
    def wrapped(*args): calls.append(args)
    def custom(*args): calls.append(args)
    custom.__signature__=inspect.Signature([inspect.Parameter('bar',inspect.Parameter.POSITIONAL_ONLY)])
    class Callback:
        def __call__(self,bar): calls.append((bar,))
    original=inspect.signature
    seen=[]
    def spy(func): seen.append(func); return original(func)
    monkeypatch.setattr(inspect,'signature',spy)
    for callback in (wrapped,custom,Callback(),partial(base,'bound')):
        PyneIncrementalSession._call_by_arity(None,callback,'ctx','bar')
    assert len(seen)==4
    assert calls==[('ctx','bar'),('bar',),('bar',),('bound','bar')]


def test_keyword_only_callback_retains_existing_positional_call_error():
    def callback(*,bar): pass
    with pytest.raises(TypeError):
        PyneIncrementalSession._call_by_arity(None,callback,'ctx','bar')


def test_bar_copy_preserves_nested_metadata_isolation_and_scalar_types():
    from pyne_runtime.incremental.bar import copy_bar_payload
    raw={'time':1,'open':2.0,'custom':'hello','flag':True,'missing':None}
    cloned=copy_bar_payload(raw)
    assert cloned==raw and cloned is not raw
    nested={**raw,'session':{'ismarket':True},'extra':[1,2]}
    cloned=copy_bar_payload(nested)
    nested['session']['ismarket']=False
    nested['extra'].append(3)
    assert cloned['session']=={'ismarket':True} and cloned['extra']==[1,2]
