"""Native access boundary regressions; artificial COM objects, not CAD acceptance."""

from contextlib import nullcontext
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_part_pattern import CadPartPatternMixin
from solidworks_mcp.jobs import ExecutionFailure


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(binding,'wrap',lambda raw,cls:raw)
    initial=NS(identity=object(),pid=b'body',Name='Тело основания')
    replacement=NS(identity=object(),pid=b'body',Name='Тело основания',GetMassProperties=lambda density:(0.,0.,0.,1.,2.))
    seed=NS(identity=object());edge=NS(identity=object(),pid=b'edge')
    pattern=NS(identity=object(),GetID=lambda:30)
    data=NS(D1Axis=edge,PatternFeatureArray=[seed],D1TotalInstances=3,D1Spacing=.01,
        D1ReverseDirection=False,D1EndCondition=0,GeometryPattern=False,VarySketch=False,BodyPattern=False,
        IsDirection2Specified=lambda:False,GetSkippedItemCount=lambda:0,GetPatternFeatureCount=lambda:1)
    pattern.GetDefinition=lambda:data
    class Adapter(CadPartPatternMixin):
        _module=NS(ILinearPatternFeatureData=object,IEdge=object,IFeature=object)
        def __init__(self):self.current=initial;self.accessed=False
        def identity(self,obj):return obj.identity
        def _base_target(self,*args):pass
        def _base_selection(self,*args):return nullcontext()
        def features(self,model):return [pattern]
        def bodies(self,model,kind):return [self.current]
        def persistent_id(self,model,obj):return obj.pid
        def resolve_persistent_id(self,model,pid,kind):
            assert kind=='body' and pid==b'body'
            return replacement
        def same_persistent_id(self,model,a,b):return a==b
        def part_creation_controls(self,model):return {'add_to_db':False}
    adapter=Adapter()
    def access(model,component):adapter.accessed=True;return True
    def release():adapter.current=replacement
    data.AccessSelections=access;data.ReleaseSelectionAccess=release
    receipt=NS(pattern=pattern,pattern_identity=pattern.identity,seed_identity=seed.identity,
        direction_pid=b'edge',body=initial,body_identity=initial.identity,body_pid=b'body',
        pending_creation=False,selection_uncertain=False,restored=False)
    return adapter,receipt,replacement,data


def test_documented_rollback_body_wrapper_change_requires_persistent_round_trip(setup):
    adapter,receipt,replacement,_=setup
    old=receipt.body_identity
    evidence=adapter.linear_hole_pattern_evidence(object(),receipt)
    assert evidence['complete'] is True and evidence['parameters']['axis_matches'] is True
    assert receipt.body is replacement and receipt.body_identity!=old
    assert evidence['volume_mm3']==1e9


def test_same_mass_name_and_census_do_not_authorize_a_different_persistent_body(setup):
    adapter,receipt,replacement,_=setup
    replacement.pid=b'foreign-body'
    with pytest.raises(ExecutionFailure,match='Persistent resulting body'):
        adapter.linear_hole_pattern_evidence(object(),receipt)
    assert receipt.body is not replacement


def test_scalar_confirmation_does_not_open_native_rollback(setup):
    adapter,receipt,_,_=setup
    scalars=adapter.linear_hole_pattern_parameters(object(),receipt)
    assert scalars['count']==3 and adapter.accessed is False
