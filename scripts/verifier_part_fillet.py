"""Internal native engineering block; parent owns documents and cleanup gate."""

import math
import uuid

from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.part_fillet import PartFilletCatalog
from solidworks_mcp.part_fillet_definition import cuboid_edge
from solidworks_mcp.sketches import SketchCatalog,rectangle_parameters
from verifier_fixture_cleanup import guarded_inline_submit


def exercise_fillet(adapter,documents,dimensions,store,runner,gate,model,targets,record,report):
    catalog=PartFilletCatalog(SketchCatalog(dimensions));cfg=targets['configuration']
    base=catalog.sketches._capture(**targets);entry,identity=base.dimensions.state[:2]
    parameters=rectangle_parameters(base.snapshot,base.dimensions.state[3],cfg)
    geometry=GeometryCatalog(documents);observation=documents.get(targets['document_id'],cfg)['observation_revision']
    bodies=geometry.list(targets['document_id'],cfg,observation,kind='body')['items'];assert len(bodies)==1
    edges=geometry.list(targets['document_id'],cfg,observation,kind='edge',body_id=bodies[0]['object_id'])['items']
    selected=None
    for row in edges:
        edge,_=geometry._resolve(entry,row['object_id'],cfg,identity,'edge')
        if cuboid_edge(adapter.pattern_edge_points(edge),parameters)==(2,(0,0)):
            selected=row['object_id'];break
    assert selected is not None
    args={**targets,'edge_id':selected,'radius_mm':2.}
    def run(*,revision=None,**changes):
        values={**args,**changes};values['expected_revision']=revision or catalog.prepare_edge_fillet(**values)['revision']
        return guarded_inline_submit(gate,runner,store,uuid.uuid4().hex,'part.create_edge_fillet',values,
            lambda op:catalog.create_edge_fillet(op,**values),context={k:values[k] for k in ('document_id','configuration','expected_revision')},
            mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    outside=run(revision='rev_explicit',radius_mm=10.)
    record('fillet_material_prewrite_rejected',outside,'failed')
    assert outside['error']['code']=='fillet_radius_outside_material'
    stale=run(revision='rev_stale');record('fillet_stale_prewrite_rejected',stale,'failed')
    assert stale['error']['code']=='stale_revision'
    adapter.inject_fillet=True
    failed=run(radius_mm=1.5);record('fillet_known_failure_scoped_restoration',failed,'failed')
    assert failed['mutation']['phase']=='rolled_back'
    assert len(dimensions.list(targets['document_id'],cfg)['items'])==3
    result=run();record('native_selected_edge_fillet_r2',result)
    assert result['mutation']['phase']=='committed'
    body=adapter.bodies(model,'all')[0];values=body.GetMassProperties(1.)
    expected=result['result']['before']['expected_geometry']
    assert (body.GetVertexCount(),body.GetEdgeCount(),body.GetFaceCount())==(10,15,7)
    assert all(math.isclose(float(values[index])*scale,expected[key],rel_tol=1e-10)
        for index,scale,key in ((3,1e9,'volume_mm3'),(4,1e6,'surface_area_mm2')))
    report['fillet_volume_mm3']=float(values[3])*1e9;report['fillet_surface_area_mm2']=float(values[4])*1e6
    report['fillet_suite_passed']=True
