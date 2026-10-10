"""Public MCP single-edge fillet chain; parent supervises session and cleanup."""

import math
import uuid

from solidworks_mcp import binding
from solidworks_mcp.part_fillet_definition import cuboid_edge
from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec


TOOL_SPECS={
    'part_prepare_edge_fillet':ToolSpec('part.prepare_edge_fillet',False,float_arguments=frozenset({'radius_mm'}),
        argument_defaults={'feature_name':'Скругление ребра'}),
    'part_create_edge_fillet':ToolSpec('part.create_edge_fillet',True,float_arguments=frozenset({'radius_mm'}),
        argument_defaults={'feature_name':'Скругление ребра'},prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_fillet(client,context,sketch_id,base_preparation,model,module,record,report):
    observed=succeeded(await call(client,'document_get',**context))['observation_revision']
    read_context={**context,'expected_observation_revision':observed}
    bodies=succeeded(await call(client,'body_list',**read_context))['items'];assert len(bodies)==1
    edges=succeeded(await call(client,'edge_list',**read_context,body_id=bodies[0]['object_id']))['items']
    frame=base_preparation['plane_transform']
    base=dict(width_m=.04,height_m=.02,depth_m=.01,plane_transform=frame)
    selected=None
    for row in edges:
        points=tuple(tuple(v/1000. for v in row[key]) for key in ('start_mm','end_mm'))
        if cuboid_edge(points,base)==(2,(0,0)):
            selected=row['object_id'];break
    assert selected is not None
    args=dict(context,object_id=sketch_id,edge_id=selected,radius_mm=2.)
    prepared=succeeded(await call(client,'part_prepare_edge_fillet',**args))
    assert prepared['revision_scope']=='single_base_selected_edge_fillet_v1'
    request=dict(args,expected_revision=prepared['revision'],request_id='fillet-'+uuid.uuid4().hex,timeout_s=0.)
    result=await call(client,'part_create_edge_fillet',**request);proof=succeeded(result)
    assert proof['verified'] is True
    await record('public_native_selected_edge_fillet_r2',result)
    again=await call(client,'part_create_edge_fillet',**request)
    assert again['operation_id']==result['operation_id'] and again['data']==result['data']
    await record('same_request_does_not_create_second_fillet',again)
    body=binding.wrap((binding.wrap(model,module.IPartDoc).GetBodies2(-1,False) or ())[0],module.IBody2)
    values=body.GetMassProperties(1.)
    assert (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(10,15,7)
    assert math.isclose(float(values[3])*1e9,prepared['expected_geometry']['volume_mm3'],rel_tol=1e-10)
    assert math.isclose(float(values[4])*1e6,prepared['expected_geometry']['surface_area_mm2'],rel_tol=1e-10)
    report['fillet_volume_mm3']=float(values[3])*1e9;report['fillet_surface_area_mm2']=float(values[4])*1e6
    report['public_mcp_fillet_accepted']=True
