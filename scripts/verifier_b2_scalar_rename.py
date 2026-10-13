"""Bounded independent N1/N2 snapshot oracles; no native calls or dispatch.

The native owner separately validates the original durable B1 creation and live
canonical membership. Original SKETCH is only a comparison operand, never a fill
for current observations. Both current BASEs require the full production BREP
oracle. Unknown annotation/native observation deltas remain unsupported gates.
"""
from copy import deepcopy
import math

from solidworks_mcp.jobs import _json
from solidworks_mcp.owned_leaf_deletion_postconditions import validated_leaf_target
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from solidworks_mcp.rectangle_extrusion_postconditions import verified_rectangle_extrusion
from solidworks_mcp.rectangle_postconditions import same_unmodified_session


SCOPE='b2_scalar_rename_candidate_v1'
GEOMETRY_REFS=frozenset({'body','face','edge','vertex'})


def _require(condition):
    if not condition: raise ValueError('Unsupported/incomplete finite B2 scalar/rename evidence.')


def _same(left,right):
    return _json(left)==_json(right)


def _bound(before,after,extrusion_job,document_id,configuration,object_id,
           feature_native_id,feature_pid_hex,old_definition,new_definition):
    _require(type(old_definition) is type(new_definition) is BlindRectangleExtrusion
        and BlindRectangleExtrusion.validate(**vars(old_definition))==old_definition
        and BlindRectangleExtrusion.validate(**vars(new_definition))==new_definition
        and same_unmodified_session(before,after,document_id))
    result=extrusion_job['result']
    value=result['value']
    _require(extrusion_job['operation']=='part.extrude_rectangle' and extrusion_job['status']=='succeeded'
        and extrusion_job['error'] is None and extrusion_job['mutation']['phase']=='committed'
        and result['verified'] is True and result['before']['scope']=='closed_rectangle_blind_extrusion_v1'
        and value['document_id']==document_id and value['configuration']==configuration
        and value['kind']=='extrusion' and value['object_id']==value['feature_object_id']==object_id
        and type(value['created_native_id']) is int and value['created_native_id']==feature_native_id)
    scope=dict(document_id=document_id,configuration=configuration,object_id=object_id,
               feature_native_id=feature_native_id,feature_pid_hex=feature_pid_hex)
    states=[validated_leaf_target(state,**scope) for state in (before,after)]
    original=result['before']['baseline']
    original_after=result['after']['state']
    creation_definition=BlindRectangleExtrusion.validate(**result['before']['definition'])
    _require(verified_rectangle_extrusion(original,original_after,document_id,creation_definition,feature_native_id))
    validated_leaf_target(original_after,**scope)
    for current,definition in zip(states,(old_definition,new_definition)):
        projected=deepcopy(current)
        projected['snapshots'][document_id]=deepcopy(original['snapshots'][document_id])
        _require(verified_rectangle_extrusion(projected,current,document_id,definition,feature_native_id))
    snapshots=[state['snapshots'][document_id] for state in states]
    _require(set(snapshots[0])==set(snapshots[1])
        and all(_same(snapshots[0][key],snapshots[1][key]) for key in snapshots[0]
                if key not in ('clone_state','references','native_observations')))
    return snapshots


def _depth(data,feature_native_id):
    found=[row for row in data['dimensions'] if row['full_name']=={'reference_role':'dimension:depth'}]
    _require(len(found)==1 and found[0]['name']=='Толщина' and found[0]['unit']=='mm'
        and found[0]['owner']['native_id']==feature_native_id)
    return found[0]


def verified_b2_depth_change(before,after,extrusion_job,*,document_id,configuration,object_id,
                             feature_native_id,feature_pid_hex,old_definition,new_definition):
    """Only 40×20×10→40×20×12 mm, full native BREP 8000→9600 mm³.

Exactly the depth values, forward blind depth, depth parameter and geometry
anchors may change. All existing dimension/annotation/sketch/feature anchors,
complete annotation data and raw native observations remain exact. A measured
annotation relocation/text change needs a separate proven owner-bound profile.
"""
    try:
        old,current=_bound(before,after,extrusion_job,document_id,configuration,object_id,
            feature_native_id,feature_pid_hex,old_definition,new_definition)
        _require(old_definition.depth_mm==10. and new_definition.depth_mm==12.
            and _same(vars(new_definition),{**vars(old_definition),'depth_mm':12.}))
        a,b=old['clone_state'],current['clone_state']
        for data,depth,volume in ((a,.01,8000.),(b,.012,9600.)):
            parameters=data['parameters']
            _require(parameters['width_m']==.04 and parameters['height_m']==.02 and parameters['depth_m']==depth
                and math.isclose(math.prod(parameters[key]*1000. for key in ('width_m','height_m','depth_m')),
                                 volume,rel_tol=0.,abs_tol=1e-8))
        _require(_same(old['native_observations'],current['native_observations']))
        refs=lambda snapshot:[row for row in snapshot['references'] if row['kind'] not in GEOMETRY_REFS]
        _require(_same(refs(old),refs(current)))
        expected=deepcopy(a)
        _depth(expected,feature_native_id)['values_si'][configuration]=new_definition.depth_m
        if 'values' in _depth(expected,feature_native_id):
            _require(_same(_depth(a,feature_native_id)['values'],{configuration:10.}))
            _depth(expected,feature_native_id)['values'][configuration]=12.
        expected['parameters']['depth_m']=new_definition.depth_m
        directions=expected['extrusion']['directions']
        _require(len(directions)==2 and directions[0]['forward'] is True and directions[1]['forward'] is False)
        directions[0]['depth']=new_definition.depth_m.hex()
        # Actual b geometry is independently checked against native line/plane/
        # trimmed/coedge/incidence/shell data by _bound's full production oracle.
        _require(set(expected)==set(b) and all(_same(expected[key],b[key]) for key in expected if key!='geometry'))
        return True
    except Exception:
        return False


def verified_b2_feature_rename(before,after,extrusion_job,*,document_id,configuration,object_id,
                               feature_native_id,feature_pid_hex,old_definition,new_definition):
    """Only the requested Russian feature name, same object/native ID/PID.

Depth DIM owner name and its fully qualified native name follow the observed
feature rename. Body/sketch/depth, all refs/BREP/other metadata/native fields
stay exact. No annotation/name/GetID addressing or metadata normalization.
"""
    try:
        old,current=_bound(before,after,extrusion_job,document_id,configuration,object_id,
            feature_native_id,feature_pid_hex,old_definition,new_definition)
        _require(new_definition.feature_name!=old_definition.feature_name
            and _same(vars(new_definition),{**vars(old_definition),'feature_name':new_definition.feature_name})
            and _same(old['references'],current['references']))
        expected=deepcopy(old['clone_state'])
        found=[row for row in expected['features'] if row['native_id']==feature_native_id]
        _require(len(found)==1 and found[0]['name']==old_definition.feature_name)
        found[0]['name']=new_definition.feature_name
        _depth(expected,feature_native_id)['owner']['name']=new_definition.feature_name
        _require(_same(expected,current['clone_state']))
        native=deepcopy(old['native_observations'])
        found=[row for row in native['qualified_dimensions'] if row['role']=='dimension:depth']
        _require(len(found)==1 and found[0]['name']=='Толщина')
        found[0]['full_name']='Толщина@'+new_definition.feature_name+'@'+native['document_dimension_namespace']+'.Part'
        _require(_same(native,current['native_observations']))
        return True
    except Exception:
        return False
