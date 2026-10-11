"""Registered close bridge failures; fake dispatch only, no CAD connection."""
from types import SimpleNamespace
import pytest
from solidworks_mcp.cad_native_document_close import CadNativeDocumentCloseMixin
from solidworks_mcp.constants import SW_DONT_REBUILD_ACTIVE_DOC


@pytest.fixture
def bridge(monkeypatch):
    from solidworks_mcp import cad_native_document_close as native
    monkeypatch.setattr(native.binding, 'wrap', lambda value, interface: value)
    a=CadNativeDocumentCloseMixin()
    a._module=SimpleNamespace(IModelDoc2=object,IFrame=object,IModelWindow=object,IModelDocExtension=object)
    a.identity=lambda model:model.token
    one=SimpleNamespace(token='one',GetTitle=lambda:'Деталь 1',Visible=True)
    two=SimpleNamespace(token='two',GetTitle=lambda:'Деталь 2',Visible=True)
    one.GetNext=lambda:two;two.GetNext=lambda:None
    windows=[SimpleNamespace(ModelDoc=one,HWndx64=2**40,Title='Окно 1'),
             SimpleNamespace(ModelDoc=two,HWndx64=2**40+1,Title='Окно 2')]
    frame=SimpleNamespace(ModelWindows=windows,GetModelWindowCount=lambda:len(windows))
    a._sw=SimpleNamespace(GetFirstDocument=lambda:one,Frame=lambda:frame,UserControl=True,Visible=True,
                         GetCurrentWorkingDirectory=lambda:'C:/Работа',GetSearchFolders=lambda mode:'C:/Библиотека' if mode==0 else None)
    a.documents=lambda:[one,two];a.active_document=lambda:two
    return a,one,two,frame


def test_full_models_and_64bit_windows_agree(bridge):
    a,one,two,_=bridge
    assert a.native_close_windows()==[(one,dict(hwnd=2**40,title='Окно 1')),(two,dict(hwnd=2**40+1,title='Окно 2'))]


@pytest.mark.parametrize('fault',['cycle','missing_model','duplicate_model','window_count','duplicate_hwnd','foreign_window','bool_hwnd'])
def test_incomplete_or_ambiguous_window_census_rejected(bridge,fault):
    a,one,two,frame=bridge
    if fault=='cycle':two.GetNext=lambda:one
    if fault=='missing_model':a.documents=lambda:[one]
    if fault=='duplicate_model':a.documents=lambda:[one,one,two]
    if fault=='window_count':frame.GetModelWindowCount=lambda:3
    if fault=='duplicate_hwnd':frame.ModelWindows[1].HWndx64=2**40
    if fault=='foreign_window':frame.ModelWindows[1].ModelDoc=SimpleNamespace(token='foreign')
    if fault=='bool_hwnd':frame.ModelWindows[1].HWndx64=True
    with pytest.raises(Exception) as error:a.native_close_windows()
    assert error.value.code=='native_close_census_invalid'


def test_dependency_pairs_transitive_no_search_and_strict_application(bridge,tmp_path):
    a,one,_,_=bridge;path=str(tmp_path/'Деталь.SLDPRT');seen=[]
    one.Extension=SimpleNamespace(GetDependencies=lambda *args:seen.append(args) or ['Деталь',path])
    a.native_save_context=lambda model:{'blocking_state':0}
    assert a.native_close_model_context(one)==dict(visible=True,dependencies=[path],mode={'blocking_state':0})
    assert seen==[(True,False,False,True,False)]
    assert a.native_close_application_context()==dict(user_control=True,visible=True,current_directory='C:/Работа',search_folders='C:/Библиотека')
    a._sw.UserControl=1
    with pytest.raises(Exception):a.native_close_application_context()


@pytest.mark.parametrize('raw',[True,['name'],['name',''],['name','relative.SLDPRT'],['name',42]])
def test_unresolved_dependency_pair_rejected(bridge,raw):
    a,one,_,_=bridge;one.Extension=SimpleNamespace(GetDependencies=lambda *args:raw)
    with pytest.raises(Exception) as error:a.native_close_model_context(one)
    assert error.value.code=='native_close_dependencies_unavailable'


def test_close_calls_once_without_access_to_retired_model(bridge):
    a,_,_,_=bridge;calls=[];a._sw.CloseDoc=lambda name:calls.append(name)
    class Retired:
        def __getattribute__(self,name):raise AssertionError('Retired target getter forbidden')
    assert a.close_native_document(Retired(),'Деталь 1')=={'native_call_returned':True}
    assert calls==['Деталь 1']
    with pytest.raises(Exception):a.close_native_document(Retired(),'')
    assert calls==['Деталь 1']


def test_survivor_activation_uses_registered_handle_and_no_rebuild(bridge):
    a,_,two,_=bridge;calls=[]
    a._sw.ActivateDoc3=lambda *args:calls.append(args) or (two,0)
    assert a.activate_native_close_survivor(two) is None
    assert calls==[('Деталь 2',False,SW_DONT_REBUILD_ACTIVE_DOC,0)]


@pytest.mark.parametrize('result',[None,True,(None,0),('bad',5),(SimpleNamespace(token='foreign'),0)])
def test_unconfirmed_activation_refused(bridge,result):
    a,_,two,_=bridge;a._sw.ActivateDoc3=lambda *args:result
    with pytest.raises(Exception) as error:a.activate_native_close_survivor(two)
    assert error.value.code=='native_close_activation_unconfirmed'
