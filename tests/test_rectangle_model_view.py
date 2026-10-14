"""Native-shaped view side effects with artificial COM; no CAD acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pythoncom
import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_rectangle_model_view import capture_model_view, restore_model_view
from solidworks_mcp.jobs import ExecutionFailure


BASELINE = dict(orientation=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.],
    scale=1., translation=[.019,0.,0.])


class View:
    def __init__(self, adapter): self.adapter = adapter
    def __setattr__(self, name, value):
        if name == 'adapter': object.__setattr__(self, name, value); return
        adapter = self.adapter
        adapter.writes.append(name)
        if adapter.throw_at == name: raise RuntimeError('Artificial setter acknowledgement lost')
        if adapter.ignore_at == name: return
        key = {'Orientation3':'orientation', 'Scale2':'scale', 'Translation3':'translation'}[name]
        adapter.state[key] = value if name == 'Scale2' else list(value.ArrayData)
        if name == 'Orientation3':
            adapter.state['scale'] = 7.
            adapter.state['translation'] = [4.,5.,6.]


class Adapter:
    def __init__(self):
        self.state=deepcopy(BASELINE);self.writes=[];self.steps=[];self.arrays=[]
        self.throw_at=self.ignore_at=None;self.bad_math=False
        self._module=NS(IModelView=object,IMathUtility=object,IMathTransform=object,IMathVector=object)
        self.view=View(self);self.model=NS(ActiveView=self.view)
        self._sw=NS(GetMathUtility=lambda: NS(CreateTransform=self.math,CreateVector=self.math))
    def identity(self, obj):return id(obj)
    def document_view_snapshot(self, model):assert model is self.model;return deepcopy(self.state)
    def math(self, array):
        assert array.varianttype == pythoncom.VT_ARRAY | pythoncom.VT_R8
        self.arrays.append(tuple(array.value))
        return NS(ArrayData=list(array.value) if not self.bad_math else [0.]*len(array.value))
    def _rectangle_native_step(self, receipt, label, call, *args):
        assert receipt.pending_native_step is None
        receipt.pending_native_step=label;self.steps.append((label,'pending'))
        call(*args)
        self.steps.append((label,'returned'));receipt.pending_native_step=None
    def receipt(self):
        return NS(model_view=capture_model_view(self,self.model),view_state_uncertain=False,pending_native_step=None)


@pytest.fixture(autouse=True)
def wrappers(monkeypatch):monkeypatch.setattr(binding,'wrap',lambda raw,cls:raw)


def test_automatic_first_body_view_restores_exact_original_typed_data():
    a=Adapter();r=a.receipt()
    a.state=dict(orientation=[2.]*16,scale=7.,translation=[4.,5.,6.])
    restore_model_view(a,a.model,r)
    assert a.state==BASELINE and not r.view_state_uncertain
    assert a.writes==['Orientation3','Scale2','Translation3']
    assert a.arrays==[tuple(BASELINE['orientation']),tuple(BASELINE['translation'])]
    assert a.steps==[(label,phase) for label in ('restore_view_orientation','restore_view_scale','restore_view_translation')
        for phase in ('pending','returned')]


def test_unchanged_view_never_writes_or_allocates_math_objects():
    a=Adapter();r=a.receipt();restore_model_view(a,a.model,r)
    assert not a.steps and not a.arrays and a.state==BASELINE


def test_inverse_preserves_view_with_distinct_journal_names():
    a=Adapter();r=a.receipt();a.state['translation']=[1.,2.,3.]
    restore_model_view(a,a.model,r,inverse=True)
    assert a.state==BASELINE
    assert a.steps==[('inverse_restore_view_translation',phase) for phase in ('pending','returned')]


@pytest.mark.parametrize('fault',['model','view','missing','uncertain','math','ignored','lost_ack'])
def test_missing_foreign_or_unconfirmed_view_never_authorizes_repeat(fault):
    a=Adapter();r=a.receipt();model=a.model
    a.state['orientation']=[2.]*16
    if fault=='model':model=NS(ActiveView=a.view)
    elif fault=='view':a.model.ActiveView=NS()
    elif fault=='missing':r.model_view=None
    elif fault=='uncertain':r.view_state_uncertain=True
    elif fault=='math':a.bad_math=True
    elif fault=='ignored':a.ignore_at='Orientation3'
    elif fault=='lost_ack':a.throw_at='Orientation3'
    with pytest.raises((ExecutionFailure,RuntimeError)):restore_model_view(a,model,r)
    writes=list(a.writes)
    with pytest.raises((ExecutionFailure,RuntimeError)):restore_model_view(a,model,r)
    assert a.writes==writes
    if fault in ('model','view','missing','uncertain','math'):assert not a.writes
    if fault in ('ignored','lost_ack','math'):assert r.view_state_uncertain
    if fault=='lost_ack':assert r.pending_native_step=='restore_view_orientation'
