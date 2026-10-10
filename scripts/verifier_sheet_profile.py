"""One installed native sheet block; parent owns documents and cleanup gate."""

import math
import uuid

from solidworks_mcp.sheet_profile import SheetProfileCatalog
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_sheet(adapter,documents,dimensions,store,runner,gate,model,context,record,report):
    catalog=SheetProfileCatalog(dimensions)
    plane=next(row for row in dimensions.features.list(**context)['items'] if row['feature_type']=='RefPlane' and row['object_id'])
    parameters=dict(plane_object_id=plane['object_id'],leg_x_mm=40.,leg_y_mm=20.,length_mm=30.,thickness_mm=2.,bend_radius_mm=2.,k_factor=.42)
    def run(*,revision=None,**changes):
        args=dict(context,**{**parameters,**changes})
        args['expected_revision']=revision or catalog.prepare_l_profile(**args)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'sheet.create_l_profile',args,
            lambda op:catalog.create_l_profile(op,**args),context={k:args[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    invalid=run(revision='rev_explicit',leg_y_mm=4.)
    record('sheet_short_leg_prewrite_rejected',invalid,'failed')
    assert invalid['error']['code']=='sheet_profile_no_straight_leg'
    stale=run(revision='rev_stale');record('sheet_stale_prewrite_rejected',stale,'failed')
    assert stale['error']['code']=='stale_revision'
    adapter.inject_sheet=True
    failed=run();record('sheet_known_failure_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    assert not dimensions.list(**context)['items'] and not adapter.bodies(model,'all')
    assert adapter.sheet_profile_empty_state(model)==dict(sheet_folder_present=False,flat_folder_present=False)
    created=run();record('native_folded_sheet_l_profile',created)
    assert created['mutation']['phase']=='committed'
    body=adapter.bodies(model,'all')[0];values=body.GetMassProperties(1.)
    expected=created['result']['before']['expected_geometry']
    assert body.IsSheetMetal() is True and (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(16,28,14)
    assert all(math.isclose(float(values[i])*scale,expected[key],rel_tol=1e-10)
        for i,scale,key in ((3,1e9,'volume_mm3'),(4,1e6,'surface_area_mm2')))
    report['sheet_volume_mm3']=float(values[3])*1e9;report['sheet_surface_area_mm2']=float(values[4])*1e6
    report['sheet_profile_suite_passed']=True
