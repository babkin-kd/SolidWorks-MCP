"""Artificial CAD effects with real durable coordinator; not native acceptance."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure,JobRunner
from solidworks_mcp.part_fillet import PartFilletCatalog
from test_sketch_dimensions_v2 import setup as sketch_setup
from test_part_construction_mutation_v2 import Worker
from test_feature_domain_v2 import feature
from test_dimension_domain_v2 import dimension
from test_arc_brep_v2 import rounded_body,read
from test_planar_brep_v2 import make_body,snapshot


@pytest.fixture
def setup(sketch_setup):
    adapter,sketches,store,_,doc,obj,_=sketch_setup
    part=adapter.models[0];catalog=PartFilletCatalog(sketches);cfg='Основная'
    part.state['bodies']=[snapshot(make_body(points=[(x,y,z) for z in (0.,.01) for y,x in ((0.,0.),(0.,.04),(.02,.04),(.02,0.))]))]
    entry,_=catalog.dimensions.documents.resolve(doc,cfg)
    body=SimpleNamespace(identity=object(),pid=b'body');edge=SimpleNamespace(identity=object(),pid=b'edge')
    old=adapter.resolve_persistent_id
    adapter.resolve_persistent_id=lambda model,pid,kind: (body if kind=='body' else edge) if kind in ('body','edge') else old(model,pid,kind)
    adapter.bodies=lambda model,kind:[body]
    adapter.body_is_current=lambda model,obj:obj is body
    adapter.owner_body=lambda obj,kind:body
    adapter.topology_is_current=lambda parent,obj,kind:parent is body and obj is edge
    adapter.pattern_points=((0.,0.,0.),(0.,0.,.01))
    adapter.pattern_edge_points=lambda obj:adapter.pattern_points
    identity=adapter.configuration_identity(entry.model,cfg)
    bid=catalog.geometry._register(entry,body,'body',cfg,identity).object_id
    eid=catalog.geometry._register(entry,edge,'edge',cfg,identity,bid).object_id
    args=dict(document_id=doc,configuration=cfg,object_id=obj,edge_id=eid,radius_mm=2.)
    adapter.fillet_writes=adapter.fillet_restores=0;adapter.fillet_fault=None
    def receipt(model,features,controls,edge):
        return SimpleNamespace(controls=controls,edge=edge,restored=False,complete=False,pending=False,
            original_geometry=deepcopy(part.state['bodies']),owned=None,baseline_body_name='Тело основания')
    def create(model,definition,value):
        assert store.get(store.list(limit=1)['items'][0]['operation_id'])['mutation']['phase']=='prepared'
        adapter.fillet_writes+=1
        value.owned=feature(30,definition.feature_name,kind='Fillet');part.features.append(value.owned)
        row=dimension(60,value=definition.radius_mm/1000.);row.owner=value.owned
        row.state.update(name='Радиус',full_name='Радиус@'+definition.feature_name,owner=deepcopy(value.owned.state))
        part.dimensions.append(row)
        value.parameters=dict(type=0,radius_m=definition.radius_mm/1000.,edge_count=1,items_count=1,
            feature_count=0,loop_count=0,hold_line_count=0,multiple_radius=False,propagate=False,
            partial=False,asymmetric=False,curvature_continuous=False,conic_type=0,edge_matches=True)
        part.state['bodies']=[read(rounded_body(radius=definition.radius_mm/1000.))]
        value.expected=definition.expected_geometry(dict(width_m=.04,height_m=.02,depth_m=.01,
            plane_transform=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]),2,(0,0))
        value.complete=True;part.state['update_stamp']+=1
        if adapter.fillet_fault=='dimension':part.dimensions[0].state['values_si'][cfg]=.041
        if adapter.fillet_fault=='foreign_feature':part.features.append(feature(99,'Чужая операция'))
        if adapter.fillet_fault=='geometry':part.state['bodies'][0]['vertices'][0][0]=(.001).hex()
        if adapter.fillet_fault=='edge':value.parameters['edge_matches']=False
        if adapter.fillet_fault=='unknown':value.pending=True
        if adapter.fillet_fault:raise RuntimeError('Artificial failure after native fillet.')
    def evidence(model,value):
        if value.pending:raise ExecutionFailure('fillet_effect_unconfirmed','Artificial uncertain fillet',uncertain=True)
        if value.restored:return dict(restored=True,complete=False)
        return dict(restored=False,complete=value.complete,fillet_native_id=30,parameters=value.parameters,
            controls=value.controls,body_name=value.baseline_body_name,
            volume_mm3=value.expected['volume_mm3'],surface_area_mm2=value.expected['surface_area_mm2'])
    def restore(model,value):
        adapter.fillet_restores+=1
        part.features=[f for f in part.features if f is not value.owned]
        part.dimensions=[d for d in part.dimensions if d.owner is not value.owned]
        part.state['bodies']=deepcopy(value.original_geometry);part.state['update_stamp']+=1;value.restored=True
    adapter.new_edge_fillet_receipt=receipt;adapter.create_edge_fillet=create
    adapter.edge_fillet_evidence=evidence;adapter.restore_edge_fillet=restore
    adapter.edge_fillet_parameters=lambda model,value:None if value.restored else {k:v for k,v in value.parameters.items() if k!='edge_matches'}
    revision=catalog.prepare_edge_fillet(**args)['revision'];runner=JobRunner(store,Worker())
    def run(request='fillet',expected_revision=revision,**changes):
        payload={**args,'expected_revision':expected_revision,**changes}
        return runner.submit(request,'part.create_edge_fillet',payload,lambda op:catalog.create_edge_fillet(op,**payload),
            mutates=True,pass_operation_id=True,context={k:payload[k] for k in ('document_id','configuration','expected_revision')},
            verify=lambda result:result['verified'] is True)
    return adapter,catalog,store,args,run


def test_full_shape_commits_and_idempotent_request_does_not_repeat(setup):
    adapter,_,_,_,run=setup;other=deepcopy(adapter.models[1].state)
    result=run()
    assert result['status']=='succeeded',result.get('error')
    assert result['mutation']['verification']['outcome']=='committed'
    assert run()==result and adapter.fillet_writes==1 and adapter.fillet_restores==0
    assert len(adapter.models[0].dimensions)==4 and adapter.models[1].state==other


def test_attributable_known_failure_restores_only_own_fillet_and_keeps_three_drivers(setup):
    adapter,_,_,_,run=setup;before=deepcopy(adapter.models[0].state['bodies']);adapter.fillet_fault='known'
    result=run()
    assert result['status']=='failed',result
    assert result['mutation']['verification']['outcome']=='rolled_back'
    assert adapter.fillet_restores==1 and adapter.models[0].state['bodies']==before
    assert len(adapter.models[0].dimensions)==3


@pytest.mark.parametrize('fault',['dimension','foreign_feature','geometry','edge','unknown'])
def test_foreign_or_unreadable_effects_never_delete_or_claim_restoration(setup,fault):
    adapter,_,store,_,run=setup;adapter.fillet_fault=fault
    result=run()
    assert result['status']=='unknown',result
    assert adapter.fillet_restores==0
    assert run()==result and adapter.fillet_writes==1


def test_stale_revision_has_no_native_write(setup):
    adapter,_,_,_,run=setup
    result=run(expected_revision='rev_stale')
    assert result['status']=='failed' and adapter.fillet_writes==adapter.fillet_restores==0
