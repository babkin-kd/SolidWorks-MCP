"""Public SDK/stdio folded-sheet chain; parent supervises journal and cleanup."""

import math
import uuid

from solidworks_mcp import binding
from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec

TOOL_SPECS={
    'sheet_prepare_l_profile':ToolSpec('sheet.prepare_l_profile',False,
        float_arguments=frozenset({'leg_x_mm','leg_y_mm','length_mm','thickness_mm','bend_radius_mm','k_factor'}),
        argument_defaults={'sketch_name':'Эскиз листового профиля','feature_name':'Листовой уголок','body_name':'Тело листового уголка'}),
    'sheet_create_l_profile':ToolSpec('sheet.create_l_profile',True,
        float_arguments=frozenset({'leg_x_mm','leg_y_mm','length_mm','thickness_mm','bend_radius_mm','k_factor'}),
        argument_defaults={'sketch_name':'Эскиз листового профиля','feature_name':'Листовой уголок','body_name':'Тело листового уголка'},
        prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_sheet(client,context,model,module,record,report):
    tree=succeeded(await call(client,'feature_list',**context))
    plane=next(row for row in tree['items'] if row['feature_type']=='RefPlane' and row['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,
        thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    prepared=succeeded(await call(client,'sheet_prepare_l_profile',**args))
    assert prepared['revision_scope']=='empty_part_sheet_l_profile_v1'
    request=dict(args,expected_revision=prepared['revision'],request_id='sheet-'+uuid.uuid4().hex,timeout_s=0.)
    result=await call(client,'sheet_create_l_profile',**request);proof=succeeded(result)
    assert proof['verified'] is True
    await record('public_native_folded_sheet_l_profile',result)
    again=await call(client,'sheet_create_l_profile',**request)
    assert again['operation_id']==result['operation_id'] and again['data']==result['data']
    await record('same_request_does_not_create_second_sheet_profile',again)
    bodies=binding.wrap(model,module.IPartDoc).GetBodies2(-1,False) or ()
    assert len(bodies)==1;body=binding.wrap(bodies[0],module.IBody2);values=body.GetMassProperties(1.)
    assert body.IsSheetMetal() is True and (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(16,28,14)
    expected=prepared['expected_geometry']
    assert math.isclose(float(values[3])*1e9,expected['volume_mm3'],rel_tol=1e-10)
    assert math.isclose(float(values[4])*1e6,expected['surface_area_mm2'],rel_tol=1e-10)
    assert proof['after']['created']['sheet_parameters']['k_factor']==.42
    report['sheet_volume_mm3']=float(values[3])*1e9;report['sheet_surface_area_mm2']=float(values[4])*1e6
    report['public_mcp_sheet_profile_accepted']=True
