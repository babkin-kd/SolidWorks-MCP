"""Installed internal flat/fold block; parent owns fixture lifecycle."""

import uuid

from solidworks_mcp.sheet_profile import SheetProfileCatalog
from solidworks_mcp.sheet_flat_state import SheetFlatStateCatalog
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_sheet_flat(adapter,documents,dimensions,store,runner,gate,model,context,record,report):
    profile=SheetProfileCatalog(dimensions)
    plane=next(row for row in dimensions.features.list(**context)['items'] if row['feature_type']=='RefPlane' and row['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    args['expected_revision']=profile.prepare_l_profile(**args)['revision']
    created=guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_l_profile',args,
        lambda op:profile.create_l_profile(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
        mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    record('native_sheet_flat_source_created',created)
    base=next(row for row in dimensions.features.list(**context)['items'] if row['feature_type']=='SMBaseFlange' and row['object_id'])
    states=SheetFlatStateCatalog(dimensions)
    def run(flattened,revision=None):
        args=dict(context,base_object_id=base['object_id'],flattened=flattened)
        args['expected_revision']=revision or states.prepare_flat_state(**args)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.set_flat_state',args,
            lambda op:states.set_flat_state(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    stale=run(True,'rev_stale');record('sheet_state_stale_prewrite_rejected',stale,'failed');assert stale['error']['code']=='stale_revision'
    adapter.inject_sheet_state=True
    failed=run(True);record('sheet_state_known_failure_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    flat=run(True);record('native_sheet_flat_state',flat)
    fold=run(False);record('native_sheet_folded_state_restored',fold)
    before=flat['result']['before'];after=fold['result']['after']
    assert states._transition(before,after,False)
    assert before['evidence']['body_name']==after['evidence']['body_name']
    assert next(r['name'] for r in after['evidence']['members'] if r['role']=='cut_list')=='Список вырезов'
    report['sheet_state_suite_passed']=True
    report['flat_volume_mm3']=flat['result']['after']['evidence']['volume_mm3']
    report['flat_surface_area_mm2']=flat['result']['after']['evidence']['area_mm2']
