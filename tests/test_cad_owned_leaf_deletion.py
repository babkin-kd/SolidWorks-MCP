"""Independent one-shot receipt boundary tests; artificial handles, no CAD."""
from dataclasses import dataclass
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_owned_leaf_deletion import NativeOwnedLeafDeletion
from solidworks_mcp.cad_rectangle_construction import NativeRectangleStageReceipt
from solidworks_mcp.cad_rectangle_view_retirement import NativeView, RectangleViewReceipt
from solidworks_mcp.jobs import JobError


class Handle:
    def __deepcopy__(self,memo): raise AssertionError('Native handle must not be deep-copied.')


@dataclass
class View:
    token: object
    baseline: dict


def make():
    model,feature,sketch=Handle(),NS(),Handle()
    feature.IsSuppressed2=lambda *args:[False]
    feature.GetChildren=lambda:None
    receipt=NativeRectangleStageReceipt(model,Handle(),((sketch,{'name':'Эскиз основания'}),),{'auto_solve':True})
    receipt.attempted=receipt.native_call_returned=True
    receipt.extrusion=receipt.extrusion_identity=feature
    receipt.borrowed_sketch=receipt.borrowed_sketch_identity=sketch
    native_view=Handle()
    receipt.annotation_views=RectangleViewReceipt(model,(NativeView(native_view,native_view,{'metadata':[1]}),),
        owned=[NativeView(native_view,native_view,{'metadata':[2]})],bound=True)
    receipt.model_view=View(native_view,{'scale':1.})
    calls=[]
    def inverse(current,stage):
        calls.append(stage)
        stage.restore_attempted=True
        stage.annotation_views.retirement_attempted=stage.annotation_views.retired=True
        stage.annotation_views.owned[0].data['metadata'][0]=3
        stage.restored=True
    adapter=NS(identity=lambda obj:obj,active_document=lambda:model,
        features=lambda current:[sketch,feature],application_busy=lambda:True,
        restore_rectangle_extrusion=inverse)
    binding=NS(kind='extrusion',document_id='doc',configuration='Основная',object_id='obj',
        connection_epoch='epoch',model=model,model_identity=model,feature_identity=feature,receipt=receipt)
    registry=NS(adapter=adapter,resolve=lambda *args,**kwargs:(binding,feature))
    current_view=View(native_view,{'scale':4.})
    action=NativeOwnedLeafDeletion(registry,binding,recorder=lambda *args:None,capture_view=lambda model:current_view)
    return action,receipt,calls,feature,current_view


def test_new_receipt_retains_handles_but_separates_all_mutable_metadata():
    action,original,calls,feature,current_view=make()
    assert action.stage is not original
    assert action.stage.extrusion is feature
    assert action.stage.baseline_features[0][0] is original.baseline_features[0][0]
    assert action.stage.model_view is current_view and original.model_view.baseline=={'scale':1.}
    assert action.stage.annotation_views is not original.annotation_views
    assert action.stage.annotation_views.owned[0] is not original.annotation_views.owned[0]
    evidence=action.apply()
    assert evidence['bridge_returned'] and evidence['deletion_bridge_verified']
    assert calls==[action.stage]
    assert original.restored is original.restore_attempted is False
    assert original.annotation_views.retired is original.annotation_views.retirement_attempted is False
    assert original.annotation_views.owned[0].data=={'metadata':[2]}
    with pytest.raises(JobError): action.apply()
    assert len(calls)==1


@pytest.mark.parametrize('fault',['suppressed','children','bad_children','active','guard','sketch'])
def test_recheck_before_owned_delete(fault):
    action,original,calls,feature,_=make()
    if fault=='suppressed':feature.IsSuppressed2=lambda *args:[True]
    elif fault=='children':feature.GetChildren=lambda:[Handle()]
    elif fault=='bad_children':feature.GetChildren=lambda:'unavailable'
    elif fault=='active':action.adapter.active_document=lambda:Handle()
    elif fault=='guard':action.adapter.application_busy=lambda:False
    else:action.adapter.features=lambda model:[feature]
    with pytest.raises(JobError):action.apply()
    assert calls==[] and action.attempted is False and original.restore_attempted is False


@pytest.mark.parametrize('pending',['native','journal','view','selection','none'])
def test_exception_return_is_not_native_acknowledgement_or_retry(pending):
    action,original,calls,feature,_=make()
    def fail(model,stage):
        calls.append(stage);stage.restore_attempted=True
        if pending=='native':stage.pending_native_step='restore_delete_extrusion'
        elif pending=='journal':stage.native_step_journal_failed=True
        elif pending=='view':stage.view_state_uncertain=True
        elif pending=='selection':stage.selection_uncertain=True
        raise RuntimeError('injected bridge exception')
    action.adapter.restore_rectangle_extrusion=fail
    with pytest.raises(RuntimeError):action.apply()
    facts=action.evidence()
    assert facts['bridge_exception_returned'] and not facts['bridge_returned'] and not facts['pending_apply']
    assert facts['pending_native_step']==('restore_delete_extrusion' if pending=='native' else None)
    assert facts['journal_failed'] is (pending=='journal')
    assert facts['view_state_uncertain'] is (pending=='view')
    assert facts['selection_uncertain'] is (pending=='selection')
    assert original.restore_attempted is original.native_step_journal_failed is original.view_state_uncertain is False
    with pytest.raises(JobError):action.apply()
    assert len(calls)==1
