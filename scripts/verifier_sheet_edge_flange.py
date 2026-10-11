"""Installed flange domain: refusals, unconsumed/completed restoration and U."""

import uuid

from solidworks_mcp.sheet_profile import SheetProfileCatalog
from solidworks_mcp.sheet_edge_flange import SheetEdgeFlangeCatalog
from solidworks_mcp.sheet_edge_flange_definition import l_flange_edge_points
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_sheet_edge_flange(adapter,documents,dimensions,store,runner,gate,model,context,record,report):
    profile=SheetProfileCatalog(dimensions)
    plane=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='RefPlane' and r['object_id'])
    args=dict(context,plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    args['expected_revision']=profile.prepare_l_profile(**args)['revision']
    created=guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_l_profile',args,
        lambda op:profile.create_l_profile(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
        mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    record('native_flange_source_created',created)
    base=next(r for r in dimensions.features.list(**context)['items'] if r['feature_type']=='SMBaseFlange' and r['object_id'])
    catalog=SheetEdgeFlangeCatalog(dimensions)
    def arguments():
        captured=catalog._capture(**context,base_object_id=base['object_id'])
        entry,identity=captured[0].state[:2]
        observation=documents.get(**context)['observation_revision']
        bodies=catalog.geometry.list(**context,expected_observation_revision=observation,kind='body')['items']
        assert len(bodies)==1
        edges=catalog.geometry.list(**context,expected_observation_revision=observation,kind='edge',body_id=bodies[0]['object_id'])['items']
        selected=[]
        for row in edges:
            edge,_=catalog.geometry._resolve(entry,row['object_id'],context['configuration'],identity,'edge')
            if l_flange_edge_points(adapter.pattern_edge_points(edge),captured[4],captured[2]['evidence']['plane_transform']):selected.append(row['object_id'])
        assert len(selected)==1
        return dict(context,base_object_id=base['object_id'],edge_id=selected[0],flange_length_mm=15.,bend_radius_mm=2.5,k_factor=.38)
    def run(*,revision=None,**changes):
        args={**arguments(),**changes};args['expected_revision']=revision or catalog.prepare_edge_flange(**args)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_edge_flange',args,
            lambda op:catalog.create_edge_flange(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda v:v['verified'] is True)
    invalid=run(revision='rev_unused',flange_length_mm=0.);record('flange_invalid_prewrite_rejected',invalid,'failed')
    assert invalid['error']['requires_reconciliation'] is False and invalid.get('mutation') is None
    stale=run(revision='rev_stale');record('flange_stale_prewrite_rejected',stale,'failed')
    assert stale['error']['code']=='stale_revision' and stale.get('mutation') is None
    adapter.inject_flange_input=True
    partial=run();record('flange_input_scoped_restoration',partial,'failed')
    assert partial['mutation']['phase']=='rolled_back'
    adapter.inject_flange=True
    failed=run();record('flange_completed_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    changed=run();record('native_full_edge_flange_u',changed)
    assert changed['mutation']['phase']=='committed' and changed['result']['after']['phase']=='completed'
    report['sheet_flange_suite_passed']=True
