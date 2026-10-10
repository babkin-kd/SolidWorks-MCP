"""Durable sketch mutations with artificial CAD; never native acceptance."""

from copy import deepcopy
import math

import pytest

from solidworks_mcp.dimensions import DimensionCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.part_creation import PartCreationCatalog
from solidworks_mcp.sketches import SketchCatalog, rectangle_parameters
from test_document_catalog_v2 import model
from test_feature_domain_v2 import feature
from test_linear_sketch_v2 import Sketch, Relation
from test_part_construction_mutation_v2 import Adapter as ConstructionAdapter, Worker
from test_part_creation_v2 import IDENTITY
from solidworks_mcp.linear_sketch import LinearSketchReader


class Adapter(ConstructionAdapter):
    def __init__(self):
        super().__init__()
        self.sketch = Sketch()
        self.sketch_hook = None
        self.measure_fault = None
        self.restore_noise = False
    def sketch_snapshot(self, wrapper, feature):
        part = self.original(wrapper)
        for i, record in enumerate(part.dimensions[:2]):
            record.FullName = record.state['full_name']
            self.sketch.dimensions[i] = record
        result, members = LinearSketchReader(self.sketch,self.sketch.origin,
            wrap=lambda raw,name:raw, identity=lambda raw:getattr(raw,'identity',raw)).read()
        result.update(feature_native_id=10,feature_pid_hex=feature.pid.hex(),
            model_to_sketch=[float(x).hex() for x in IDENTITY],
            reference_plane={'native_id':1,'pid_hex':part.features[0].pid.hex(),'transform':[float(x).hex() for x in IDENTITY]},
            model_origin={'feature_native_id':2,'pid_hex':b'origin'.hex()})
        if self.sketch_hook:
            hook,self.sketch_hook = self.sketch_hook,None
            hook()
        return result,members
    def rebuild_dimension_document(self, wrapper):
        result = super().rebuild_dimension_document(wrapper)
        part = self.original(wrapper)
        w,h,d = [row.state['values_si']['Основная'] for row in part.dimensions]
        for point, xyz in zip(self.sketch.points,((0.,0.,0.),(w,0.,0.),(w,h,0.),(0.,h,0.))):
            point.X,point.Y,point.Z = xyz
        part.state['bodies'][0]['vertices'] = [[float(v).hex() for v in (x,y,z)] for x in (0.,w) for y in (0.,h) for z in (0.,d)]
        if self.restore_noise and len(self.dimension_writes)>1:
            self.sketch.points[2].Y=math.nextafter(h,1.)
            for point in part.state['bodies'][0]['vertices']:
                if float.fromhex(point[0])==w and float.fromhex(point[1])==h:
                    point[1]=self.sketch.points[2].Y.hex()
        return result
    def rectangle_body_measurements(self, wrapper):
        if self.measure_fault:
            hook,self.measure_fault = self.measure_fault,None
            hook()
        w,h,d = [row.state['values_si']['Основная'] for row in self.original(wrapper).dimensions]
        return {'volume_mm3':w*h*d*1e9,'surface_area_mm2':2*(w*h+w*d+h*d)*1e6}


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    part,other = model(title='Контрольная пластина',configurations=['Основная']),model(title='Другая деталь')
    for item in (part,other):
        item.features,item.dimensions,item.displays = [feature(1,'Передняя',kind='RefPlane')],[],[]
    adapter.models = [part,other]
    adapter.context['configuration_needs_rebuild'] = {'Основная':False}
    store = JobStore(tmp_path/'sketch.sqlite')
    documents = DocumentCatalog(adapter)
    doc = documents.list()['documents'][0]['document_id']
    dims = DimensionCatalog(documents,store,'sketch-test',mutation_guard=adapter.guard)
    parts = PartCreationCatalog(dims)
    plane = dims.features.list(doc,'Основная')['items'][0]['object_id']
    args = dict(document_id=doc,configuration='Основная',plane_object_id=plane,width_mm=40.,height_mm=20.,depth_mm=10.)
    args['expected_revision'] = parts.prepare_base_extrusion(**{k:v for k,v in args.items() if k!='expected_revision'})['revision']
    runner = JobRunner(store,Worker())
    job = runner.submit('build','part.create_base_extrusion',args,lambda op:parts.create_base_extrusion(op,**args),
        context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,pass_operation_id=True,
        verify=lambda result:result['verified'] is True)
    assert job['status']=='succeeded',job
    for row,owner in zip(part.dimensions,(part.features[1],part.features[1],part.features[2])):
        row.owner = owner
        if owner.state['feature_type']=='ProfileFeature': row.state['write_blockers'] = ['sketch_geometry_snapshot_not_implemented']
    adapter.rebuild_dimension_document(part)
    object_id = next(row['object_id'] for row in dims.features.list(doc,'Основная')['items'] if row['feature_type']=='ProfileFeature')
    ids = [row['object_id'] for row in dims.list(doc,'Основная')['items']]
    yield adapter,SketchCatalog(dims),store,runner,doc,object_id,ids
    documents.close()
    store.close()


def change(setup,index=0,value=45.,request='change',revision=None):
    adapter,catalog,store,runner,doc,obj,ids = setup
    args = dict(document_id=doc,configuration='Основная',object_id=obj,dimension_id=ids[index],value_mm=value)
    args['expected_revision'] = revision or catalog.prepare_dimension_change(**args)['revision']
    return runner.submit(request,'sketch.set_dimension',args,lambda op:catalog.set_dimension(op,**args),
        context={k:args[k] for k in ('document_id','configuration','expected_revision')},mutates=True,
        pass_operation_id=True,verify=lambda result:result['verified'] is True)


def test_width_then_height_complete_geometry_and_original_blocker_preserved(setup):
    adapter,catalog,_,_,doc,obj,ids = setup
    other = deepcopy(adapter.models[1].state)
    old = catalog.get(doc,'Основная',obj)
    first = change(setup)
    assert first['status']=='succeeded',first
    assert first['result']['after']['native_body_measurements']['volume_mm3']==pytest.approx(9000.)
    second = change(setup,index=1,value=25.,request='height')
    assert second['status']=='succeeded',second
    assert second['result']['after']['native_body_measurements']['volume_mm3']==pytest.approx(11250.)
    assert old['revision']!=catalog.get(doc,'Основная',obj)['revision']
    assert adapter.models[1].state==other
    assert catalog.dimensions.get(doc,'Основная',ids[0])['dimension']['write_blockers']==['sketch_geometry_snapshot_not_implemented']


def test_stale_revision_and_wrong_owner_never_write(setup):
    assert change(setup,revision='rev_stale')['error']['code']=='stale_revision'
    assert setup[0].dimension_writes==[]
    with pytest.raises(ExecutionFailure): change(setup,index=2)
    assert setup[0].dimension_writes==[]


@pytest.mark.parametrize('fault',['exception','status','silent','bool','rebuild'])
def test_known_failure_restores_exact_original_geometry_and_constraints(setup,fault):
    adapter,catalog,_,_,doc,obj,_ = setup
    old = catalog.get(doc,'Основная',obj)['sketch']
    geometry = deepcopy(adapter.models[0].state['bodies'])
    if fault=='rebuild': adapter.rebuild_fault='fail'
    else: adapter.dimension_fault=fault
    job = change(setup)
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back',job
    assert catalog.get(doc,'Основная',obj)['sketch']==old
    assert adapter.models[0].state['bodies']==geometry


def test_unrelated_target_value_is_unknown_and_never_overwritten(setup):
    adapter = setup[0]
    def foreign(record):
        record.state['values_si']['Основная']=.049
        raise RuntimeError('Foreign third value discovered')
    adapter.dimension_fault=foreign
    job=change(setup)
    assert job['status']=='unknown',job
    assert len(adapter.dimension_writes)==1 and adapter.models[0].dimensions[0].state['values_si']['Основная']==.049


def test_native_solver_roundoff_after_restore_requires_full_bounded_shape_not_binary_equality(setup):
    adapter=setup[0]
    adapter.restore_noise=True
    adapter.dimension_fault='status'
    job=change(setup)
    assert job['status']=='failed' and job['mutation']['phase']=='rolled_back',job
    assert adapter.models[0].dimensions[0].state['values_si']['Основная']==.04


def test_horizontal_relations_tolerate_only_native_solver_coordinate_roundoff(setup):
    adapter,catalog,_,_,doc,obj,ids=setup
    adapter.sketch.points[2].Y=math.nextafter(.02,1.)
    assert catalog.prepare_dimension_change(doc,'Основная',obj,ids[0],45.)['axis']=='width'


def test_foreign_constraint_after_write_is_not_restored(setup):
    adapter=setup[0]
    def foreign():
        adapter.sketch.relations[0].Suppressed=True
        raise RuntimeError('Foreign relation changed')
    adapter.measure_fault=foreign
    job=change(setup)
    assert job['status']=='unknown',job
    assert len(adapter.dimension_writes)==1


def test_late_sketch_getter_event_invalidates_read(setup):
    adapter,catalog,_,_,doc,obj,_=setup
    adapter.sketch_hook=lambda:setattr(adapter.watches[id(adapter.models[0].identity)],'sequence',17)
    with pytest.raises(ExecutionFailure):catalog.get(doc,'Основная',obj)


def test_fresh_relation_interfaces_do_not_invalidate_identical_complete_native_semantics(setup):
    adapter,catalog,_,_,doc,obj,_=setup
    original=catalog.get(doc,'Основная',obj)
    def fresh():
        adapter.sketch.relations=[Relation(row.kind,row.types,row.entities,row.definitions,row.display)
                                 for row in adapter.sketch.relations]
    adapter.sketch_hook=fresh
    assert catalog.get(doc,'Основная',obj)==original


def test_changed_relation_semantics_between_native_captures_is_rejected(setup):
    adapter,catalog,_,_,doc,obj,_=setup
    adapter.sketch_hook=lambda:setattr(adapter.sketch.relations[0],'Suppressed',True)
    with pytest.raises(ExecutionFailure):catalog.get(doc,'Основная',obj)


@pytest.mark.parametrize('fault',['point','body'])
def test_foreign_geometry_after_write_is_not_overwritten(setup,fault):
    adapter=setup[0]
    def foreign():
        if fault=='point':adapter.sketch.points[2].X=.048
        else:adapter.models[0].state['bodies'][0]['vertices'][0][0]=(.001).hex()
        raise RuntimeError('Foreign geometric edit discovered')
    adapter.measure_fault=foreign
    job=change(setup)
    assert job['status']=='unknown',job
    assert len(adapter.dimension_writes)==1


def test_identical_request_is_not_dispatched_again(setup):
    adapter,catalog,_,_,doc,obj,ids=setup
    revision=catalog.prepare_dimension_change(doc,'Основная',obj,ids[0],45.)['revision']
    first=change(setup,revision=revision)
    assert change(setup,revision=revision)==first
    assert len(adapter.dimension_writes)==1


@pytest.mark.parametrize('value',[True,0.,-.001,float('nan'),float('inf'),10000001.])
def test_invalid_requested_size_rejected_before_native_capture(setup,value,monkeypatch):
    _,catalog,_,_,doc,obj,ids=setup
    monkeypatch.setattr(catalog,'_paired',lambda *args:pytest.fail('Unexpected CAD access'))
    with pytest.raises(ExecutionFailure):catalog.prepare_dimension_change(doc,'Основная',obj,ids[0],value)


def test_axis_is_bound_by_type2_and_native_relations_not_russian_name(setup):
    adapter,catalog,_,_,doc,obj,ids=setup
    adapter.models[0].dimensions[0].state['name']='Высота'
    prepared=catalog.prepare_dimension_change(doc,'Основная',obj,ids[0],45.)
    assert prepared['axis']=='width'


@pytest.mark.parametrize('fault',['underdefined','missing_origin','construction','wrong_axis','body','negative','relation'])
def test_unsupported_structure_never_reaches_setter(setup,fault):
    adapter=setup[0]
    if fault=='underdefined':adapter.sketch.GetConstrainedStatus=lambda:2
    if fault=='missing_origin':adapter.sketch.relations[0].definitions[0]=adapter.sketch.projected
    if fault=='construction':adapter.sketch.lines[0].ConstructionGeometry=True
    if fault=='wrong_axis':adapter.sketch.relations[-1].display.Type2=2
    if fault=='body':adapter.models[0].state['bodies'][0]['vertices'][0][0]=(.001).hex()
    if fault=='negative':adapter.sketch.points[1].X=-.04
    if fault=='relation':adapter.sketch.relations.pop()
    with pytest.raises(ExecutionFailure):change(setup)
    assert adapter.dimension_writes==[]
