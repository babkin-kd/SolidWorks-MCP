"""Installed U-source → unfold/refold with refusals and both restorations."""

import uuid

from solidworks_mcp.sheet_profile import SheetProfileCatalog
from solidworks_mcp.sheet_profile_definition import SheetLProfile
from solidworks_mcp.sheet_edge_flange import SheetEdgeFlangeCatalog
from solidworks_mcp.sheet_flange_flat_state import SheetFlangeFlatStateCatalog
from verifier_fixture_cleanup import guarded_inline_submit
from verifier_sheet_edge_flange_edges import flange_edge_candidate


def exercise_sheet_flange_flat(adapter,documents,dimensions,store,runner,gate,model,context,record,report):
    profile=SheetProfileCatalog(dimensions)
    plane=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='RefPlane' and r['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    args['expected_revision']=profile.prepare_l_profile(**args)['revision']
    source=guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_l_profile',args,
        lambda op:profile.create_l_profile(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
        mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    record('native_u_state_l_source_created',source)
    definition=SheetLProfile.validate(**{k:v for k,v in args.items() if k not in context and k!='expected_revision'})
    frame=source['result']['before']['plane_transform']
    base=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    flanges=SheetEdgeFlangeCatalog(dimensions)
    observation=documents.get(**context)['observation_revision']
    bodies=flanges.geometry.list(**context,expected_observation_revision=observation,kind='body')['items'];assert len(bodies)==1
    edges=flanges.geometry.list(**context,expected_observation_revision=observation,kind='edge',body_id=bodies[0]['object_id'])['items']
    selected=[r['object_id'] for r in edges if flange_edge_candidate(r,definition,frame)];assert len(selected)==1
    args=dict(context,base_object_id=base['object_id'],edge_id=selected[0],flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38)
    args['expected_revision']=flanges.prepare_edge_flange(**args)['revision']
    source=guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_edge_flange',args,
        lambda op:flanges.create_edge_flange(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
        mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    record('native_u_state_flange_source_created',source)
    flange=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='EdgeFlange' and r['object_id'])
    states=SheetFlangeFlatStateCatalog(dimensions)
    def run(flattened,revision=None):
        args=dict(context,base_object_id=base['object_id'],flange_object_id=flange['object_id'],flattened=flattened)
        args['expected_revision']=revision or states.prepare_flat_state(**args)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.set_flange_flat_state',args,
            lambda op:states.set_flat_state(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    stale=run(True,'rev_stale');record('u_state_stale_prewrite_rejected',stale,'failed');assert stale['error']['code']=='stale_revision'
    adapter.inject_u_state=True
    failed=run(True);record('u_unfold_known_failure_scoped_restoration',failed,'failed');assert failed['mutation']['phase']=='rolled_back'
    flat=run(True);record('native_u_sheet_flat_state',flat)
    adapter.inject_u_state=True
    failed=run(False);record('u_refold_known_failure_scoped_restoration',failed,'failed');assert failed['mutation']['phase']=='rolled_back'
    fold=run(False);record('native_u_sheet_folded_state_restored',fold)
    assert states._transition(flat['result']['before'],fold['result']['after'],False)
    report['u_state_suite_passed']=True
    report['flat_volume_mm3']=flat['result']['after']['evidence']['volume_mm3']
    report['flat_surface_area_mm2']=flat['result']['after']['evidence']['area_mm2']
