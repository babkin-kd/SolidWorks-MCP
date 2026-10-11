"""Public new part → L sheet → explicit edge flange, journal and request replay."""

import uuid

from solidworks_mcp.sheet_profile_definition import SheetLProfile
from solidworks_mcp.sheet_edge_flange_definition import l_flange_edge_points
from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec


DEFAULTS={'sketch_name':'Эскиз отбортовки','feature_name':'Отбортовка'}
FLOATS=frozenset({'flange_length_mm','bend_radius_mm','k_factor'})
TOOL_SPECS={
    'sheet_prepare_edge_flange':ToolSpec('sheet.prepare_edge_flange',False,float_arguments=FLOATS,argument_defaults=DEFAULTS),
    'sheet_create_edge_flange':ToolSpec('sheet.create_edge_flange',True,float_arguments=FLOATS,argument_defaults=DEFAULTS,
        prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_sheet_edge_flange(client,context,model,module,record,report):
    tree=succeeded(await call(client,'feature_list',**context))
    plane=next(r for r in tree['items'] if r['feature_type']=='RefPlane' and r['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    prepared=succeeded(await call(client,'sheet_prepare_l_profile',**args))
    created=await call(client,'sheet_create_l_profile',**args,expected_revision=prepared['revision'],timeout_s=0.)
    succeeded(created);await record('public_flange_source_created',created)
    definition=SheetLProfile.validate(**{k:v for k,v in args.items() if k not in context})
    tree=succeeded(await call(client,'feature_list',**context))
    base=next(r for r in tree['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    observed=succeeded(await call(client,'document_get',**context))['observation_revision']
    read_context=dict(context,expected_observation_revision=observed)
    bodies=succeeded(await call(client,'body_list',**read_context))['items'];assert len(bodies)==1
    edges=succeeded(await call(client,'edge_list',**read_context,body_id=bodies[0]['object_id']))['items']
    selected=[r['object_id'] for r in edges if r.get('start_mm') is not None and r.get('end_mm') is not None
        and l_flange_edge_points(tuple(tuple(v/1000. for v in r[k]) for k in ('start_mm','end_mm')),definition,prepared['plane_transform'])]
    assert len(selected)==1
    args=dict(context,base_object_id=base['object_id'],edge_id=selected[0],flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38)
    prepared=succeeded(await call(client,'sheet_prepare_edge_flange',**args))
    assert prepared['revision_scope']=='single_l_sheet_edge_flange_v1' and prepared['native_change_available'] is True
    request=dict(args,expected_revision=prepared['revision'],request_id='flange-'+uuid.uuid4().hex,timeout_s=0.)
    changed=await call(client,'sheet_create_edge_flange',**request);proof=succeeded(changed)
    await record('public_native_full_edge_flange_u',changed)
    assert proof['verified'] is True and proof['after']['phase']=='completed'
    replay=await call(client,'sheet_create_edge_flange',**request)
    assert replay['operation_id']==changed['operation_id'] and replay['data']==changed['data']
    await record('same_request_does_not_repeat_flange',replay)
    tree=succeeded(await call(client,'feature_list',**context))
    assert len([r for r in tree['items'] if r['feature_type']=='EdgeFlange'])==1
    report['public_mcp_sheet_flange_accepted']=True
