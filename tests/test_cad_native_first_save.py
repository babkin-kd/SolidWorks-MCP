"""Fake native one-shot boundaries; these tests do not run SolidWorks."""
from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_native_first_save import CadNativeFirstSaveMixin
from solidworks_mcp.jobs import ExecutionFailure


class Model:
    def __init__(self, title='Контрольная деталь'):
        self.token, self.title = object(), title
        self.kind, self.filename, self.count, self.retired = 1, '', 0, False
        self.SelectionManager = SimpleNamespace(GetSelectedObjectCount2=lambda _: self.count)
    def GetType(self):
        assert not self.retired
        return self.kind
    def GetPathName(self):
        assert not self.retired
        return self.filename
    def GetTitle(self):
        assert not self.retired
        return self.title


class Adapter(CadNativeFirstSaveMixin):
    def __init__(self):
        self.model = Model()
        self.active, self.models = self.model, [self.model]
        self._module = SimpleNamespace(ISelectionMgr=object)
        self.metadata = dict(configurations=['Основная'], active_configuration='Основная', stamp=1)
        self.mode = dict(read_only_state=0, view_only=False, editing_sketch=False,
                         editing_component=False, blocking_state=0)
        self.rebuild, self.copy_result, self.copy_error, self.close_result, self.close_error = False, (True,0,0), None, None, None
        self.copy_calls, self.close_calls = [], []
        self._sw = SimpleNamespace(CloseDoc=self.close)
    def identity(self, model):return model.token
    def active_document(self):return self.active
    def documents(self):return self.models[:]
    def snapshot(self, model):return deepcopy(self.metadata)
    def native_save_context(self, model):return deepcopy(self.mode)
    def pending_rebuild(self, model):return self.rebuild
    def _extension(self, model):return SimpleNamespace(SaveAs3=self.copy)
    def copy(self, *args):
        self.copy_calls.append(args)
        if self.copy_error:raise self.copy_error
        return self.copy_result
    def close(self, title):
        self.close_calls.append(title)
        if self.close_error:raise self.close_error
        self.models.remove(self.model)
        self.model.retired=True
        return self.close_result


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(binding, 'wrap', lambda value, cls:value)
    return Adapter(), str(tmp_path / 'Первая запись.SLDPRT')


def receipt(env):
    a, path = env
    return a.new_native_first_save_copy_receipt(a.model,path,'Основная')


def test_typed_modern_copy_is_once_with_exact_arguments_and_raw_retention(env):
    a,path=env
    r=receipt(env)
    evidence=a.save_native_first_save_copy(r)
    assert a.copy_calls==[(path,0,3,None,None,0,0)]
    assert evidence==dict(native_call_attempted=True,pending_copy=False,native_call_returned=True,
                         acknowledgement_valid=True,success=True,errors=0,warnings=0)
    assert r.raw_return is a.copy_result
    with pytest.raises(ExecutionFailure):a.save_native_first_save_copy(r)
    assert len(a.copy_calls)==1


@pytest.mark.parametrize('raw',[(False,0,0),(True,1,0),(True,0,1),[True,0,0],(1,0,0),(True,False,0),(True,0,False),None,0,(True,0)])
def test_false_warning_and_malformed_returns_remain_evidence_not_retry_or_success(env,raw):
    a,_=env
    a.copy_result=raw
    r=receipt(env)
    evidence=a.save_native_first_save_copy(r)
    assert r.raw_return is raw and r.native_call_returned and not r.pending_copy
    assert evidence['acknowledgement_valid'] is (type(raw) is tuple and len(raw)==3 and type(raw[0]) is bool and type(raw[1]) is int and type(raw[2]) is int)
    with pytest.raises(ExecutionFailure):a.save_native_first_save_copy(r)
    assert len(a.copy_calls)==1


def test_throwing_copy_stays_pending_and_can_never_dispatch_again(env):
    a,_=env
    r=receipt(env)
    a.copy_error=RuntimeError('possible effect')
    with pytest.raises(RuntimeError):a.save_native_first_save_copy(r)
    assert r.pending_copy and r.native_call_attempted and not r.native_call_returned
    with pytest.raises(ExecutionFailure):a.save_native_first_save_copy(r)
    assert len(a.copy_calls)==1


@pytest.mark.parametrize('change',['active','identity','configuration','stamp','selection','saved','kind','readonly','edit','rebuild','destination'])
def test_context_race_is_refused_before_native_copy(env,change):
    a,path=env
    r=receipt(env)
    if change=='active':a.active=Model()
    elif change=='identity':a.model.token=object()
    elif change=='configuration':a.metadata['configurations'].append('Вариант')
    elif change=='stamp':a.metadata['stamp']=2
    elif change=='selection':a.model.count=1
    elif change=='saved':a.model.filename=path
    elif change=='kind':a.model.kind=True
    elif change=='readonly':a.mode['read_only_state']=True
    elif change=='edit':a.mode['editing_sketch']=True
    elif change=='rebuild':a.rebuild=True
    else:
        from pathlib import Path
        Path(path).write_bytes(b'foreign')
    with pytest.raises(ExecutionFailure):a.save_native_first_save_copy(r)
    assert not a.copy_calls and not r.native_call_attempted


@pytest.mark.parametrize('value',[None,False,1,'',' ','relative.sldprt','bad\x00name',pytest.param('x'*32768,id='too_long')])
def test_invalid_path_or_configuration_cannot_create_receipt(env,value):
    a,path=env
    with pytest.raises(ExecutionFailure):a.new_native_first_save_copy_receipt(a.model,value,'Основная')
    with pytest.raises(ExecutionFailure):a.new_native_first_save_copy_receipt(a.model,path,value)
    assert not a.copy_calls


def test_wrong_receipt_or_sta_never_calls_copy(env):
    a,_=env
    r=receipt(env)
    r.thread=threading.get_ident()+1
    for value in (r,object()):
        with pytest.raises(ExecutionFailure):a.save_native_first_save_copy(value)
    assert not a.copy_calls


def test_close_has_one_void_ack_without_querying_retired_handle(env):
    a,_=env
    r=a.new_native_first_save_close_receipt(a.model,a.model.GetTitle())
    value=a.close_native_first_save_document(r)
    assert value==dict(native_call_attempted=True,pending_close=False,native_call_returned=True,acknowledgement_valid=True)
    assert a.model.retired and a.close_calls==['Контрольная деталь']
    with pytest.raises(ExecutionFailure):a.close_native_first_save_document(r)
    assert len(a.close_calls)==1


def test_throwing_close_keeps_pending_receipt_and_never_repeats(env):
    a,_=env
    r=a.new_native_first_save_close_receipt(a.model,a.model.GetTitle())
    a.close_error=RuntimeError('possible retirement')
    with pytest.raises(RuntimeError):a.close_native_first_save_document(r)
    assert r.native_call_attempted and r.pending_close and not r.native_call_returned
    with pytest.raises(ExecutionFailure):a.close_native_first_save_document(r)
    assert len(a.close_calls)==1


@pytest.mark.parametrize('change',['name','identity','duplicate','missing','thread'])
def test_close_binding_race_or_wrong_sta_refuses_before_effect(env,change):
    a,_=env
    r=a.new_native_first_save_close_receipt(a.model,a.model.GetTitle())
    if change=='name':a.model.title='Другая деталь'
    elif change=='identity':a.model.token=object()
    elif change=='duplicate':a.models.append(Model())
    elif change=='missing':a.models=[]
    else:r.thread=threading.get_ident()+1
    with pytest.raises(ExecutionFailure):a.close_native_first_save_document(r)
    assert not a.close_calls and not r.native_call_attempted
