"""Public SDK/stdio existing-sheet flat/fold chain and exact request replay."""

import uuid

from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec

TOOL_SPECS={
    'sheet_prepare_flat_state':ToolSpec('sheet.prepare_flat_state',False),
    'sheet_set_flat_state':ToolSpec('sheet.set_flat_state',True,prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_sheet_flat(client,context,model,module,record,report):
    tree=succeeded(await call(client,'feature_list',**context))
    plane=next(row for row in tree['items'] if row['feature_type']=='RefPlane' and row['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    prepared=succeeded(await call(client,'sheet_prepare_l_profile',**args))
    source=await call(client,'sheet_create_l_profile',**args,expected_revision=prepared['revision'],timeout_s=0.)
    succeeded(source);await record('public_sheet_flat_source_created',source)
    tree=succeeded(await call(client,'feature_list',**context))
    base=next(row for row in tree['items'] if row['feature_type']=='SMBaseFlange' and row['object_id'])
    args=dict(context,base_object_id=base['object_id'],flattened=True)
    prepared=succeeded(await call(client,'sheet_prepare_flat_state',**args));assert prepared['revision_scope']=='single_l_sheet_flat_state_v1'
    request=dict(args,expected_revision=prepared['revision'],request_id='flat-'+uuid.uuid4().hex,timeout_s=0.)
    flat=await call(client,'sheet_set_flat_state',**request);proof=succeeded(flat);await record('public_native_sheet_flat_state',flat)
    replay=await call(client,'sheet_set_flat_state',**request)
    assert replay['operation_id']==flat['operation_id'] and replay['data']==flat['data']
    await record('same_request_does_not_repeat_sheet_flat_state',replay)
    args['flattened']=False;prepared=succeeded(await call(client,'sheet_prepare_flat_state',**args))
    fold=await call(client,'sheet_set_flat_state',**args,expected_revision=prepared['revision'],timeout_s=0.)
    restored=succeeded(fold);await record('public_native_sheet_folded_state',fold)
    from solidworks_mcp.sheet_flat_state import SheetFlatStateCatalog
    assert SheetFlatStateCatalog._transition(proof['before'],restored['after'],False)
    report['public_mcp_sheet_state_accepted']=True
    report['flat_volume_mm3']=proof['after']['evidence']['volume_mm3']
    report['flat_surface_area_mm2']=proof['after']['evidence']['area_mm2']
