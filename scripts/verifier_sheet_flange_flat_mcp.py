"""Public stdio two-bend U flat/fold state and exact request replay."""

import uuid

from verify_dimension_mcp import call,succeeded
from verifier_lifecycle import ToolSpec
from verifier_sheet_edge_flange_mcp import exercise_sheet_edge_flange


TOOL_SPECS={
    'sheet_prepare_flange_flat_state':ToolSpec('sheet.prepare_flange_flat_state',False),
    'sheet_set_flange_flat_state':ToolSpec('sheet.set_flange_flat_state',True,prewrite_failure_codes=frozenset({'stale_revision'}))}


async def exercise_sheet_flange_flat(client,context,model,module,record,report):
    # Reuse creation/replay setup; it does not duplicate restoration CAD runs.
    await exercise_sheet_edge_flange(client,context,model,module,record,report)
    tree=succeeded(await call(client,'feature_list',**context))
    base=next(r for r in tree['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    flange=next(r for r in tree['items'] if r['feature_type']=='EdgeFlange' and r['object_id'])
    args=dict(context,base_object_id=base['object_id'],flange_object_id=flange['object_id'],flattened=True)
    prepared=succeeded(await call(client,'sheet_prepare_flange_flat_state',**args))
    assert prepared['revision_scope']=='single_u_sheet_flat_state_v1' and prepared['k_factors']==[.42,.38]
    request=dict(args,expected_revision=prepared['revision'],request_id='u-flat-'+uuid.uuid4().hex,timeout_s=0.)
    flat=await call(client,'sheet_set_flange_flat_state',**request);proof=succeeded(flat)
    await record('public_native_u_sheet_flat_state',flat)
    replay=await call(client,'sheet_set_flange_flat_state',**request)
    assert replay['operation_id']==flat['operation_id'] and replay['data']==flat['data']
    await record('same_request_does_not_repeat_u_flat_state',replay)
    args['flattened']=False;prepared=succeeded(await call(client,'sheet_prepare_flange_flat_state',**args))
    fold=await call(client,'sheet_set_flange_flat_state',**args,expected_revision=prepared['revision'],timeout_s=0.)
    restored=succeeded(fold);await record('public_native_u_sheet_folded_state',fold)
    from solidworks_mcp.sheet_flange_flat_state import SheetFlangeFlatStateCatalog
    assert SheetFlangeFlatStateCatalog._transition(proof['before'],restored['after'],False)
    report['public_mcp_u_state_accepted']=True
    report['flat_volume_mm3']=proof['after']['evidence']['volume_mm3']
    report['flat_surface_area_mm2']=proof['after']['evidence']['area_mm2']
