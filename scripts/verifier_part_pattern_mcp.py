"""Public MCP pattern chain helper; the parent supervises journal and cleanup."""

import math
import uuid

from solidworks_mcp import binding
from solidworks_mcp.part_pattern import pattern_axis
from verify_dimension_mcp import call, succeeded
from verifier_lifecycle import ToolSpec


TOOL_SPECS={
    'document_get':ToolSpec('document.get',False),
    'body_list':ToolSpec('geometry.list',False,constant_args={'kind':'body'},
        argument_defaults={'body_type':'all','limit':100,'cursor':''}),
    'edge_list':ToolSpec('geometry.list',False,constant_args={'kind':'edge'},
        argument_defaults={'limit':100,'cursor':''}),
    'part_prepare_linear_hole_pattern':ToolSpec('part.prepare_linear_hole_pattern',False,
        float_arguments=frozenset({'spacing_mm'}),argument_defaults={'feature_name':'Линейный массив отверстий'}),
    'part_create_linear_hole_pattern':ToolSpec('part.create_linear_hole_pattern',True,
        float_arguments=frozenset({'spacing_mm'}),argument_defaults={'feature_name':'Линейный массив отверстий'},
        prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_pattern(client,context,sketch_id,circle_id,cut_native_id,hole_expected,model,module,record,report):
    tree=succeeded(await call(client,'feature_list',**context))
    seed_id=next(row['object_id'] for row in tree['items'] if row['native_id']==cut_native_id)
    observed=succeeded(await call(client,'document_get',**context))['observation_revision']
    read_context={**context,'expected_observation_revision':observed}
    bodies=succeeded(await call(client,'body_list',**read_context))['items']
    assert len(bodies)==1
    edges=succeeded(await call(client,'edge_list',**read_context,body_id=bodies[0]['object_id']))['items']
    base=dict(zip(('width_m','height_m','depth_m'),map(float.fromhex,hole_expected['base_extents_si'])))
    base['plane_transform']=list(map(float.fromhex,hole_expected['plane_transform_si']))
    direction=None
    for row in edges:
        if row['curve_type']!='line':continue
        points=tuple(tuple(value/1000. for value in row[key]) for key in ('start_mm','end_mm'))
        try:axis,_=pattern_axis(points,base)
        except Exception:continue
        if axis==0:
            direction=row['object_id']
            break
    assert direction is not None
    args=dict(context,base_object_id=sketch_id,object_id=circle_id,seed_object_id=seed_id,
              direction_edge_id=direction,count=3,spacing_mm=10.)
    prepared=succeeded(await call(client,'part_prepare_linear_hole_pattern',**args))
    assert prepared['revision_scope']=='single_base_linear_through_hole_pattern_v1'
    request=dict(args,expected_revision=prepared['revision'],request_id='pattern-'+uuid.uuid4().hex,timeout_s=0.)
    result=await call(client,'part_create_linear_hole_pattern',**request)
    proof=succeeded(result)
    assert proof['verified'] is True
    await record('public_native_linear_hole_pattern_x3_step10',result)
    again=await call(client,'part_create_linear_hole_pattern',**request)
    assert again['operation_id']==result['operation_id'] and again['data']==result['data']
    await record('same_request_does_not_create_second_pattern',again)
    circle=proof['after']['circle']['segments'][0]
    assert circle['key']=='circle:'+':'.join(map(str,circle['native_id']))
    assert circle['native_id']!=circle['periodic_endpoints'][0]['native_id']
    report['circle_native_id_metadata_fixed']=True
    body=binding.wrap((binding.wrap(model,module.IPartDoc).GetBodies2(-1,False) or ())[0],module.IBody2)
    values=body.GetMassProperties(1.)
    assert math.isclose(float(values[3])*1e9,8000.-3.*math.pi*3.**2*10.,rel_tol=1e-10)
    assert math.isclose(float(values[4])*1e6,2800.-6.*math.pi*3.**2+6.*math.pi*3.*10.,rel_tol=1e-10)
    assert (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(8,18,9)
    report['pattern_volume_mm3']=float(values[3])*1e9
    report['pattern_surface_area_mm2']=float(values[4])*1e6
    report['public_mcp_pattern_accepted']=True
