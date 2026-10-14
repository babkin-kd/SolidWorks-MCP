"""Public parameter change, request replay, physical flat/fold and original values."""

import uuid
from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec

TOOL_SPECS={
    'sheet_prepare_parameters':ToolSpec('sheet.prepare_parameters',False,float_arguments=frozenset({'thickness_mm','bend_radius_mm','k_factor'})),
    'sheet_set_parameters':ToolSpec('sheet.set_parameters',True,float_arguments=frozenset({'thickness_mm','bend_radius_mm','k_factor'}),
        prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_sheet_parameters(client,context,model,module,record,report):
    tree=succeeded(await call(client,'feature_list',**context))
    plane=next(r for r in tree['items'] if r['feature_type']=='RefPlane' and r['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    prepared=succeeded(await call(client,'sheet_prepare_l_profile',**args))
    created=await call(client,'sheet_create_l_profile',**args,expected_revision=prepared['revision'],timeout_s=0.)
    succeeded(created);await record('public_sheet_parameter_source_created',created)
    tree=succeeded(await call(client,'feature_list',**context))
    base=next(r for r in tree['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    args=dict(context,base_object_id=base['object_id'],thickness_mm=2.5,bend_radius_mm=3.5,k_factor=.38)
    prepared=succeeded(await call(client,'sheet_prepare_parameters',**args));assert prepared['revision_scope']=='single_l_sheet_parameters_v1'
    request=dict(args,expected_revision=prepared['revision'],request_id='params-'+uuid.uuid4().hex,timeout_s=0.)
    changed=await call(client,'sheet_set_parameters',**request);proof=succeeded(changed)
    await record('public_native_sheet_parameters_changed',changed)
    replay=await call(client,'sheet_set_parameters',**request)
    assert replay['operation_id']==changed['operation_id'] and replay['data']==changed['data']
    await record('same_request_does_not_repeat_sheet_parameters',replay)
    for flattened,label in ((True,'public_new_sheet_parameters_flat'),(False,'public_new_sheet_parameters_fold')):
        state=dict(context,base_object_id=base['object_id'],flattened=flattened)
        prepared=succeeded(await call(client,'sheet_prepare_flat_state',**state))
        response=await call(client,'sheet_set_flat_state',**state,expected_revision=prepared['revision'],timeout_s=0.)
        value=succeeded(response);await record(label,response)
        if flattened:
            report['changed_flat_volume_mm3']=value['after']['evidence']['volume_mm3']
            report['changed_flat_surface_area_mm2']=value['after']['evidence']['area_mm2']
    args.update(thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    prepared=succeeded(await call(client,'sheet_prepare_parameters',**args))
    restored=await call(client,'sheet_set_parameters',**args,expected_revision=prepared['revision'],timeout_s=0.)
    original=succeeded(restored);await record('public_native_sheet_parameters_original_restored',restored)
    from solidworks_mcp.sheet_parameters import SheetParameterCatalog
    definition=SheetParameterCatalog._source(proof['before'],context['configuration'],plane['object_id'])[0]
    assert SheetParameterCatalog._parameter_transition(proof['before'],original['after'],definition)
    report['public_mcp_sheet_parameters_accepted']=True
