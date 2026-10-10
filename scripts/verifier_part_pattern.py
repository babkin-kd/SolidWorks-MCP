"""Engineering-only internal native pattern block, under the owning fixture gate."""

import math
import uuid

from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.part_pattern import PartPatternCatalog, pattern_axis
from solidworks_mcp.sketches import SketchCatalog
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_pattern(adapter,documents,dimensions,store,runner,gate,model,targets,seed_native_id,record,report):
    cfg=targets['configuration']
    features=dimensions.features.list(targets['document_id'],cfg)['items']
    seed_id=next(row['object_id'] for row in features if row['native_id']==seed_native_id)
    catalog=PartPatternCatalog(SketchCatalog(dimensions))
    hole=catalog.holes._capture(**targets)
    entry,identity=hole.circle.dimensions.state[:2]
    geometry=GeometryCatalog(documents)
    observation=documents.get(targets['document_id'],cfg)['observation_revision']
    bodies=geometry.list(targets['document_id'],cfg,observation,kind='body')['items']
    assert len(bodies)==1
    edges=geometry.list(targets['document_id'],cfg,observation,kind='edge',body_id=bodies[0]['object_id'])['items']
    direction=None
    for row in edges:
        if row['curve_type']!='line':continue
        edge,_=geometry._resolve(entry,row['object_id'],cfg,identity,'edge')
        try:axis,_=pattern_axis(adapter.pattern_edge_points(edge),hole.base_parameters)
        except Exception:continue
        if axis==0:
            direction=row['object_id']
            break
    assert direction is not None
    args={**targets,'seed_object_id':seed_id,'direction_edge_id':direction,'count':3,'spacing_mm':10.}
    def run(*,revision=None,**changes):
        values={**args,**changes}
        values['expected_revision']=revision or catalog.prepare_linear_hole_pattern(**values)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'part.create_linear_hole_pattern',values,
            lambda op:catalog.create_linear_hole_pattern(op,**values),
            context={key:values[key] for key in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    outside=run(revision='rev_explicit',count=4)
    assert outside['status']=='failed' and outside['error']['code']=='hole_outside_material'
    assert outside.get('mutation') is None or outside['mutation']['phase']=='not_started'
    record('pattern_material_prewrite_rejected',outside,'failed')
    stale=run(revision='rev_stale')
    assert stale['status']=='failed' and stale['error']['code']=='stale_revision'
    record('pattern_stale_prewrite_rejected',stale,'failed')
    adapter.inject_pattern=True
    failed=run()
    record('pattern_known_failure_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    assert len(dimensions.list(targets['document_id'],cfg)['items'])==6
    result=run()
    record('native_linear_hole_pattern_x3_step10',result)
    assert result['mutation']['phase']=='committed'
    circle=result['result']['after']['circle']['segments'][0]
    assert circle['key']=='circle:'+':'.join(map(str,circle['native_id']))
    assert circle['native_id']!=circle['periodic_endpoints'][0]['native_id']
    report['circle_native_id_metadata_fixed']=True
    body=adapter.bodies(model,'all')[0]
    values=body.GetMassProperties(1.)
    assert math.isclose(float(values[3])*1e9,8000.-3.*math.pi*3.**2*10.,rel_tol=1e-10)
    assert math.isclose(float(values[4])*1e6,2800.-6.*math.pi*3.**2+6.*math.pi*3.*10.,rel_tol=1e-10)
    assert (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(8,18,9)
    report['pattern_volume_mm3']=float(values[3])*1e9
    report['pattern_surface_area_mm2']=float(values[4])*1e6
    report['pattern_suite_passed']=True
