"""Source-edge interface refresh is scoped to the exact owned input phase."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_edge_flange_native_v2 import bridge,edge_bridge,flange
from test_sheet_profile_definition_v2 import folded_body
from test_arc_brep_v2 import read
from test_part_creation_v2 import IDENTITY


@pytest.fixture
def source_views(edge_bridge):
    a,_,old,body,receipt,refs,calls=edge_bridge
    a._module.ISketchManager=object
    model=NS(SketchManager=NS(ActiveSketch=None))
    native=NS(GetConstrainedStatus=lambda:3)
    profile=NS(GetID=lambda:60,GetTypeName2=lambda:'ProfileFeature',GetSpecificFeature2=lambda:native)
    base=NS(GetID=lambda:49)
    receipt.sketch=profile;receipt.sketch_identity=id(profile);receipt.sketch_pid=b'profile';receipt.native_sketch=native
    receipt.baseline_features=(base,);receipt.source_target.members=[];refs[b'profile']=profile
    a.features=lambda m:[base,profile];a.part_creation_controls=lambda m:receipt.controls
    a._sheet_flange_source_parameters=lambda m,t:receipt.original_parameters.copy()
    a.dimension_geometry_snapshot=lambda m:{'bodies':[read(folded_body())]}
    old.GetBody=lambda:body
    current=deepcopy(old);current.GetBody=lambda:body
    refs[b'edge']=current;body.GetEdges=lambda:[current]
    a.persistent_id=lambda m,f:b'body' if f is body else b'edge'
    a.pattern_edge_points=lambda e:tuple(tuple(getattr(e,g)().GetPoint()) for g in ('GetStartVertex','GetEndVertex'))
    return a,model,receipt,current,body,refs


def test_refreshed_pointer_requires_original_pid_full_source_and_current_topology(source_views,flange):
    a,model,receipt,current,_,_=source_views
    assert id(current)!=receipt.edge_identity
    assert a._sheet_flange_profile_edge_current(model,receipt,flange,IDENTITY) is current
    assert receipt.edge_identity==id(receipt.edge)  # No client-reference upgrade/cache.


@pytest.mark.parametrize('defect',['unknown','flange_exists','missing_sketch','controls','parameters','shape','extra_node',
    'retained_pid','wrong_side','foreign_owner','missing_current_edge','duplicate_current_edge','second_body',
    'retarget_on_close','underdefined','foreign_sketch','open_sketch'])
def test_same_endpoints_or_pid_do_not_authorize_an_unproved_refresh(source_views,flange,defect):
    a,model,receipt,current,body,refs=source_views
    if defect=='unknown':receipt.pending_creation=True
    elif defect=='flange_exists':receipt.flange=object()
    elif defect=='missing_sketch':receipt.sketch=None
    elif defect=='controls':a.part_creation_controls=lambda m:{'changed':True}
    elif defect=='parameters':a._sheet_flange_source_parameters=lambda *args:{'changed':True}
    elif defect=='shape':a.dimension_geometry_snapshot=lambda m:{'bodies':[]}
    elif defect=='extra_node':
        original=a.features(model);a.features=lambda m:[*original,NS(GetID=lambda:99)]
    elif defect=='retained_pid':a.persistent_id=lambda m,f:b'foreign' if f is receipt.edge else b'body' if f is body else b'edge'
    elif defect=='wrong_side':current.GetStartVertex=lambda:NS(GetPoint=lambda:[0.,.02,0.])
    elif defect=='foreign_owner':current.GetBody=lambda:object()
    elif defect=='missing_current_edge':body.GetEdges=lambda:[receipt.edge]
    elif defect=='duplicate_current_edge':body.GetEdges=lambda:[current,current]
    elif defect=='second_body':a.bodies=lambda m,k:[body,object()]
    elif defect=='retarget_on_close':
        original=a.resolve_persistent_id;count=[]
        def resolve(m,p,k):
            if p==b'edge':
                count.append(True)
                if len(count)>1:return receipt.edge
            return original(m,p,k)
        a.resolve_persistent_id=resolve
    elif defect=='underdefined':receipt.native_sketch.GetConstrainedStatus=lambda:2
    elif defect=='foreign_sketch':receipt.native_sketch=object()
    else:model.SketchManager.ActiveSketch=object()
    with pytest.raises(ExecutionFailure):a._sheet_flange_profile_edge_current(model,receipt,flange,IDENTITY)
