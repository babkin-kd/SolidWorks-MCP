from types import SimpleNamespace
import pytest
from solidworks_mcp.cad_native_document_save import CadNativeDocumentSaveMixin


class Model:
    def GetBlockingState(self):return 0
    def IsOpenedReadOnly(self):return False
    def IsOpenedViewOnly(self):return False
    def GetActiveSketch2(self):return None
    def GetType(self):return 1
    def Save3(self,*args):self.arguments=args;return self.result


def test_save3_uses_exact_silent_options_and_registered_tuple():
    m=Model();m.result=(True,0,0);adapter=CadNativeDocumentSaveMixin()
    assert adapter.native_save_context(m)==dict(blocking_state=0,read_only_state=0,view_only=False,editing_component=False,editing_sketch=False,drawing_state=None)
    assert adapter.save_native_current_file(m)==dict(success=True,errors=0,warnings=0) and m.arguments==(1,0,0)


@pytest.mark.parametrize('result',[True,(True,0),(True,0,0,0)])
def test_nonregistered_native_return_rejected(result):
    m=Model();m.result=result
    with pytest.raises(RuntimeError):CadNativeDocumentSaveMixin().save_native_current_file(m)


def test_non_native_readonly_flag_refused():
    m=Model();m.IsOpenedReadOnly=lambda:1
    with pytest.raises(Exception) as error:CadNativeDocumentSaveMixin().native_save_context(m)
    assert error.value.code=='native_save_context_unavailable'


def mode_adapter(monkeypatch):
    from solidworks_mcp import cad_native_document_save as native
    monkeypatch.setattr(native.binding, 'wrap', lambda value, interface:value)
    adapter=CadNativeDocumentSaveMixin()
    adapter._module=SimpleNamespace(IAssemblyDoc=object,IComponent2=object,IDrawingDoc=object,IView=object,ISheet=object)
    adapter.identity=lambda value:value.identity
    return adapter


@pytest.mark.parametrize('root,editing',[(True,False),(False,True)])
def test_assembly_root_is_normal_but_nested_edit_is_blocked(monkeypatch,root,editing):
    adapter=mode_adapter(monkeypatch);m=Model();m.GetType=lambda:2
    m.GetEditTargetComponent=lambda:SimpleNamespace(IsRoot=lambda:root)
    assert adapter.native_save_context(m)['editing_component'] is editing


def test_untyped_assembly_root_state_rejected(monkeypatch):
    adapter=mode_adapter(monkeypatch);m=Model();m.GetType=lambda:2
    m.GetEditTargetComponent=lambda:SimpleNamespace(IsRoot=lambda:1)
    with pytest.raises(Exception) as error:adapter.native_save_context(m)
    assert error.value.code=='native_save_context_unavailable'


@pytest.mark.parametrize('edit_sheet,active_identity,sheet_identity,editing',[
    (True,'sheet','sheet',False), (False,'sheet','sheet',True),
    (True,'view','sheet',True), (True,None,'sheet',True), (True,'sheet',None,True)])
def test_drawing_normal_sheet_sketch_uses_exact_identity(monkeypatch,edit_sheet,active_identity,sheet_identity,editing):
    adapter=mode_adapter(monkeypatch);m=Model();m.GetType=lambda:3
    m.GetEditSheet=lambda:edit_sheet
    m.GetActiveSketch2=lambda:None if active_identity is None else SimpleNamespace(identity=active_identity)
    m.GetFirstView=lambda:SimpleNamespace(GetSketch=lambda:None if sheet_identity is None else SimpleNamespace(identity=sheet_identity))
    m.GetCurrentSheet=lambda:SimpleNamespace(GetName=lambda:'Лист после изменения')
    m.GetSheetNames=lambda:['Лист после изменения']
    m.GetPathName=lambda:'C:/Контрольный чертёж.SLDDRW'
    assert adapter.native_save_context(m)['editing_sketch'] is editing


def test_drawing_title_expectation_bound_to_path_and_native_current_sheet(monkeypatch):
    adapter=mode_adapter(monkeypatch);m=Model();m.GetType=lambda:3;m.GetEditSheet=lambda:True
    m.GetCurrentSheet=lambda:SimpleNamespace(GetName=lambda:'Лист после изменения')
    m.GetSheetNames=lambda:['Лист после изменения','Второй лист']
    m.GetPathName=lambda:'C:/Контрольный чертёж.SLDDRW'
    m.GetFirstView=lambda:None
    state=adapter.native_save_context(m)['drawing_state']
    assert state==dict(sheet_names=['Лист после изменения','Второй лист'],current_sheet='Лист после изменения',saved_display_title='Контрольный чертёж - Лист после изменения')


def test_untyped_drawing_edit_state_rejected(monkeypatch):
    adapter=mode_adapter(monkeypatch);m=Model();m.GetType=lambda:3;m.GetEditSheet=lambda:1
    with pytest.raises(Exception) as error:adapter.native_save_context(m)
    assert error.value.code=='native_save_context_unavailable'
