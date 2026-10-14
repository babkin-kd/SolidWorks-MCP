"""Artificial CAD effects with the real durable coordinator and full BREP reader."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure, JobRunner
from solidworks_mcp.part_pattern import PartPatternCatalog, pattern_axis
from test_part_hole_edit_v2 import setup as edit_setup, hole_setup, cut_setup, sketch_setup
from test_part_hole_mutation_v2 import native_shape
from test_part_construction_mutation_v2 import Worker
from test_feature_domain_v2 import feature
from test_dimension_domain_v2 import dimension


@pytest.fixture
def setup(edit_setup):
    adapter,edits,store,targets,_,_=edit_setup
    part=adapter.models[0]
    catalog=PartPatternCatalog(edits.sketches)
    entry,_=catalog.dimensions.documents.resolve(targets['document_id'],targets['configuration'])
    body=SimpleNamespace(identity=object(),pid=b'body')
    edge=SimpleNamespace(identity=object(),pid=b'edge')
    old_resolve=adapter.resolve_persistent_id
    adapter.resolve_persistent_id=lambda model,pid,kind: (body if kind=='body' else edge) if kind in ('body','edge') else old_resolve(model,pid,kind)
    adapter.bodies=lambda model,kind:[body]
    adapter.body_is_current=lambda model,obj:obj is body
    adapter.owner_body=lambda obj,kind:body
    adapter.topology_is_current=lambda parent,obj,kind:parent is body and obj is edge
    adapter.pattern_points=((0.,0.,0.),(.04,0.,0.))
    adapter.pattern_edge_points=lambda obj:adapter.pattern_points
    cfg=targets['configuration']
    identity=adapter.configuration_identity(entry.model,cfg)
    body_id=catalog.geometry._register(entry,body,'body',cfg,identity).object_id
    edge_id=catalog.geometry._register(entry,edge,'edge',cfg,identity,body_id).object_id
    features=catalog.dimensions.features.list(targets['document_id'],cfg)['items']
    seed=next(row['object_id'] for row in features if row['native_id']==21)
    args={**targets,'seed_object_id':seed,'direction_edge_id':edge_id,'count':3,'spacing_mm':10.}
    adapter.pattern_writes=adapter.pattern_restores=0
    adapter.pattern_fault=None
    adapter.pattern_receipts=[]
    def receipt(model,features,controls,seed,direction,reverse):
        value=SimpleNamespace(controls=controls,reverse=reverse,restored=False,complete=False,pending=False,seed=seed,direction=direction,
            original_geometry=deepcopy(part.state['bodies']),owned=None,baseline_body_name=edits.adapter.hole_edit_controls(model)['body_name'])
        adapter.pattern_receipts.append(value)
        return value
    def create(model,definition,value):
        assert store.list(limit=1)['items'][0]['mutation']['phase']=='prepared'
        adapter.pattern_writes+=1
        value.owned=feature(30,definition.feature_name,kind='LPattern')
        part.features.append(value.owned)
        row=dimension(60,value=definition.spacing_mm/1000.)
        row.owner=value.owned
        row.state.update(name='Шаг',full_name='Шаг@'+definition.feature_name,owner=deepcopy(value.owned.state))
        part.dimensions.append(row)
        value.parameters=dict(count=definition.count,spacing_m=definition.spacing_mm/1000.,reverse=value.reverse,
            end_condition=0,geometry_pattern=False,vary_sketch=False,body_pattern=False,direction_2=False,
            skipped_count=0,seed_count=1,seed_matches=True,axis_matches=True)
        seed_definition=adapter.cut_receipts[-1].definition
        centres=tuple((.01+i*.01,.01) for i in range(definition.count))
        part.state['bodies']=[native_shape(seed_definition,centres)]
        value.expected=definition.expected_geometry({'width_m':.04,'height_m':.02,'depth_m':.01,
            'plane_transform':[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.]},
            {'centre_x_m':.01,'centre_y_m':.01,'diameter_m':.006},0)
        value.complete=True
        part.state['update_stamp']+=1
        if adapter.pattern_fault=='dimension':part.dimensions[0].state['values_si'][cfg]=.041
        if adapter.pattern_fault=='foreign_feature':part.features.append(feature(99,'Чужая операция'))
        if adapter.pattern_fault=='geometry':part.state['bodies'][0]['vertices'][0][0]=(.001).hex()
        if adapter.pattern_fault=='seed':value.parameters['seed_matches']=False
        if adapter.pattern_fault=='axis':value.parameters['axis_matches']=False
        if adapter.pattern_fault=='unknown':value.pending=True
        if adapter.pattern_fault:raise RuntimeError('Artificial failure after native pattern.')
    def evidence(model,value):
        if value.pending:raise ExecutionFailure('pattern_effect_unconfirmed','Artificial uncertain pattern',uncertain=True)
        if value.restored:return dict(restored=True,complete=False)
        return dict(restored=False,complete=value.complete,pattern_native_id=30,parameters=value.parameters,
            controls=value.controls,body_name=value.baseline_body_name,
            volume_mm3=value.expected['volume_mm3'],surface_area_mm2=value.expected['surface_area_mm2'])
    def restore(model,value):
        adapter.pattern_restores+=1
        part.features=[item for item in part.features if item is not value.owned]
        part.dimensions=[row for row in part.dimensions if row.owner is not value.owned]
        part.state['bodies']=deepcopy(value.original_geometry)
        part.state['update_stamp']+=1
        value.restored=True
    adapter.new_linear_hole_pattern_receipt=receipt
    adapter.create_linear_hole_pattern=create
    adapter.linear_hole_pattern_evidence=evidence
    adapter.linear_hole_pattern_parameters=lambda model,value:None if value.restored else {
        key:val for key,val in value.parameters.items() if key not in ('axis_matches','seed_matches')}
    adapter.restore_linear_hole_pattern=restore
    revision=catalog.prepare_linear_hole_pattern(**args)['revision']
    runner=JobRunner(store,Worker())
    def run(request='pattern',expected_revision=revision,**changes):
        payload={**args,'expected_revision':expected_revision,**changes}
        return runner.submit(request,'part.create_linear_hole_pattern',payload,
            lambda op:catalog.create_linear_hole_pattern(op,**payload),mutates=True,pass_operation_id=True,
            context={key:payload[key] for key in ('document_id','configuration','expected_revision')},
            verify=lambda result:result['verified'] is True)
    return adapter,catalog,store,args,run


def test_native_array_commits_full_shape_and_same_request_is_never_repeated(setup):
    adapter,_,_,_,run=setup
    other=deepcopy(adapter.models[1].state)
    result=run()
    assert result['status']=='succeeded',result.get('error')
    assert result['mutation']['verification']['outcome']=='committed'
    assert len(adapter.models[0].state['bodies'][0]['faces'])==9
    assert len(adapter.models[0].dimensions)==7
    assert run()==result and adapter.pattern_writes==1 and adapter.pattern_restores==0
    assert adapter.models[1].state==other


def test_known_failure_deletes_only_pattern_preserving_seed_and_six_drivers(setup):
    adapter,_,_,_,run=setup
    before=deepcopy(adapter.models[0].state['bodies'])
    adapter.pattern_fault='known'
    job=run()
    assert job['status']=='failed' and job['mutation']['verification']['outcome']=='rolled_back',job.get('error')
    assert adapter.pattern_writes==adapter.pattern_restores==1
    assert adapter.models[0].state['bodies']==before and len(adapter.models[0].dimensions)==6
    assert any(row.state['native_id']==21 for row in adapter.models[0].features)


@pytest.mark.parametrize('fault',['unknown','dimension','foreign_feature','geometry','seed','axis'])
def test_foreign_or_unconfirmed_effect_is_held_not_deleted_or_replayed(setup,fault):
    adapter,_,store,args,run=setup
    adapter.pattern_fault=fault
    job=run()
    assert job['status']=='unknown',job.get('error')
    assert adapter.pattern_restores==0 and adapter.pattern_writes==1
    assert run()==job and store.mutation_blockers('sketch-test',args['document_id'])


def test_stale_is_prewrite(setup):
    adapter,_,_,_,run=setup
    job=run(expected_revision='rev_stale')
    assert job['status']=='failed' and job['error']['code']=='stale_revision'
    assert adapter.pattern_writes==adapter.pattern_restores==0


@pytest.mark.parametrize('changes',[dict(count=4),dict(spacing_mm=6.),dict(spacing_mm=30.)])
def test_invalid_remaining_material_is_prewrite(setup,changes):
    adapter,_,_,_,run=setup
    job=run(**changes)
    assert job['status']=='failed'
    assert job['error']['code'] in ('pattern_holes_overlap','hole_outside_material')
    assert adapter.pattern_writes==adapter.pattern_restores==0


def test_revision_binds_step_count_seed_edge_and_axis_sign(setup):
    adapter,catalog,_,args,_=setup
    old=catalog.prepare_linear_hole_pattern(**args)['revision']
    assert catalog.prepare_linear_hole_pattern(**{**args,'count':2})['revision']!=old
    assert catalog.prepare_linear_hole_pattern(**{**args,'spacing_mm':9.})['revision']!=old
    adapter.pattern_points=tuple(reversed(adapter.pattern_points))
    assert catalog.prepare_linear_hole_pattern(**args)['revision']!=old


def test_runtime_uses_pattern_catalog_and_releases_owned_handles(setup):
    import asyncio
    from solidworks_mcp.runtime_v2 import Runtime
    adapter,catalog,store,args,_=setup
    runtime=Runtime(store)
    runtime._catalog=catalog.dimensions.documents
    runtime._dimensions=catalog.dimensions
    runtime._connection_epoch='sketch-test'
    runtime._runner=JobRunner(store,Worker())
    async def exercise():
        prepared=await runtime.read('pattern-prep','part.prepare_linear_hole_pattern',args)
        assert prepared['status']=='succeeded',prepared.get('error')
        payload={**args,'expected_revision':prepared['result']['revision']}
        result=await runtime.mutate('pattern-runtime','part.create_linear_hole_pattern',payload)
        assert result['status']=='succeeded',result.get('error')
        assert await runtime.mutate('pattern-runtime','part.create_linear_hole_pattern',payload)==result
    asyncio.run(exercise())
    assert adapter.pattern_writes==1
    runtime._release_catalog()
    assert runtime._patterns is runtime._sketches is runtime._dimensions is None


@pytest.mark.parametrize('points,axis,reverse',[
    (((0.,0.,0.),(.04,0.,0.)),0,False),(((.04,.02,.01),(0.,.02,.01)),0,True),
    (((.04,0.,.01),(.04,.02,.01)),1,False)])
def test_axis_is_proved_from_exact_base_endpoints(points,axis,reverse):
    base=dict(width_m=.04,height_m=.02,depth_m=.01,
        plane_transform=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.])
    assert pattern_axis(points,base)==(axis,reverse)


@pytest.mark.parametrize('points',[
    ((0.,0.,0.),(0.,0.,.01)),((0.,0.,0.),(.04,.02,0.)),((0.,0.,0.),(.01,0.,0.)),
    ((0.,0.,0.),(0.,0.,0.)),((.01,.01,0.),(.04,.01,0.))])
def test_diagonal_thickness_partial_or_inner_edge_is_rejected(points):
    base=dict(width_m=.04,height_m=.02,depth_m=.01,
        plane_transform=[1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.])
    with pytest.raises(ExecutionFailure):pattern_axis(points,base)
