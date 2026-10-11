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
    assert adapter.native_save_context(m)==dict(blocking_state=0,read_only_state=0,view_only=False,editing_component=False,editing_sketch=False)
    assert adapter.save_native_current_file(m)==dict(success=True,errors=0,warnings=0) and m.arguments==(1,0,0)


@pytest.mark.parametrize('result',[True,(True,0),(True,0,0,0)])
def test_nonregistered_native_return_rejected(result):
    m=Model();m.result=result
    with pytest.raises(RuntimeError):CadNativeDocumentSaveMixin().save_native_current_file(m)


def test_non_native_readonly_flag_refused():
    m=Model();m.IsOpenedReadOnly=lambda:1
    with pytest.raises(Exception) as error:CadNativeDocumentSaveMixin().native_save_context(m)
    assert error.value.code=='native_save_context_unavailable'
