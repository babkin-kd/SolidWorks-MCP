"""Installed parameter block: prewrite refusals, known restoration and folded shape."""

import uuid
from solidworks_mcp.sheet_profile import SheetProfileCatalog
from solidworks_mcp.sheet_parameters import SheetParameterCatalog
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_sheet_parameters(adapter,documents,dimensions,store,runner,gate,model,context,record,report):
    profile=SheetProfileCatalog(dimensions)
    plane=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='RefPlane' and r['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    args['expected_revision']=profile.prepare_l_profile(**args)['revision']
    created=guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_l_profile',args,
        lambda op:profile.create_l_profile(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
        mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    record('native_sheet_parameter_source_created',created)
    base=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    parameters=SheetParameterCatalog(dimensions)
    def run(t=2.5,r=3.5,k=.38,revision=None):
        args=dict(context,base_object_id=base['object_id'],thickness_mm=t,bend_radius_mm=r,k_factor=k)
        args['expected_revision']=revision or parameters.prepare_parameters(**args)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.set_parameters',args,
            lambda op:parameters.set_parameters(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    invalid=run(t=0.,revision='rev_unused');record('sheet_parameter_invalid_prewrite_rejected',invalid,'failed')
    assert invalid['error']['requires_reconciliation'] is False and invalid.get('mutation') is None
    stale=run(revision='rev_stale');record('sheet_parameter_stale_prewrite_rejected',stale,'failed')
    assert stale['error']['code']=='stale_revision' and stale.get('mutation') is None
    adapter.inject_sheet_parameters=True
    failed=run();record('sheet_parameter_known_failure_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    changed=run();record('native_sheet_parameters_changed',changed)
    restored=run(2.,2.,.42);record('native_sheet_parameters_original_restored',restored)
    definition=parameters._source(changed['result']['before'],context['configuration'],plane['object_id'])[0]
    assert parameters._parameter_transition(changed['result']['before'],restored['result']['after'],definition)
    report['sheet_parameter_suite_passed']=True
    report['changed_volume_mm3']=changed['result']['after']['evidence']['volume_mm3']
    report['changed_surface_area_mm2']=changed['result']['after']['evidence']['area_mm2']
