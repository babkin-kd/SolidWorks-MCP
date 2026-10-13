"""Actual ownership/SQLite/context graph; artificial handles, never native CAD."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_deletion_context import CadDeletionContextMixin
from solidworks_mcp.cad_features import CadFeaturesMixin
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.jobs import ExecutionFailure,_json
from test_owned_leaf_deletion_catalog import leaf,extrusion_proof,proof,case,domain,receipt_evidence
from test_planar_brep_v2 import POINTS,make_body

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:import verifier_b2_impact_fixture as helper
finally:sys.path.remove(str(scripts))


@pytest.fixture
def b2_private_dir():
    # Native verifiers deliberately bind fixture files to repo/work, independently
    # of pytest's temp root. Keep production guards intact in CI and locally.
    private=scripts.parent/'work'
    private.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='pure-b2-path-',dir=private))


@pytest.fixture
def b2_outside_dir(tmp_path):
    # Preserve outside-work refusal even when a local run places pytest temp in work.
    if not tmp_path.resolve().is_relative_to((scripts.parent/'work').resolve()):return tmp_path
    return Path(tempfile.mkdtemp(prefix='pure-b2-outside-'))


@pytest.fixture
def fixture(leaf):
    x=leaf;c=x.c;a=c.adapter;b=x.binding
    x.write_calls=[];x.fault=None;x.raw_plane=None
    x.ownership.documents.resolve('target','Основная')[0].features={}
    for feature in c.features:
        feature.parents=[];feature.children=[]
        feature.GetID=lambda current=feature:current.row['native_id']
        feature.GetParents=lambda current=feature:current.parents
        feature.GetChildren=lambda current=feature:current.children
        feature.GetOwnerFeature=lambda current=feature:next((obj for obj in c.features
            if obj.row['native_id']==current.row['owner_native_id']),None)
    for left,right in c.baseline['clone_state']['dependencies']['parent_links']:
        c.features[right].parents.append(c.features[left]);c.features[left].children.append(c.features[right])
    a.feature_dependencies=lambda features:CadFeaturesMixin.feature_dependencies(a,features)
    a.pending_rebuild=lambda model:False
    a.same_persistent_id=lambda model,left,right:left==right
    a.feature_external_references=lambda features:dict(scope='native_feature_external_references_v1',
        feature_count=len(features),total_reference_rows=0,
        features=[dict(native_id=obj.GetID(),count=0,rows=[]) for obj in features])
    a.dimension_geometry_snapshot=lambda model:deepcopy(c.baseline['clone_state']['geometry'])
    a._module=NS(IFeature=object)
    original_extension=a._extension
    def extension(model):
        native=original_extension(model)
        native.ListExternalFileReferencesCount=lambda:0
        native.ListExternalFileReferences2=lambda:tuple(None for _ in range(9))
        return native
    a._extension=extension
    a._wrap_equation_manager=lambda raw:raw
    a.feature_deletion_context=lambda model:CadDeletionContextMixin.feature_deletion_context(a,model)
    c.model.ListAuxiliaryExternalFileReferencesCount=lambda:0
    c.model.ListAuxiliaryExternalFileReferences=lambda:(None,None)
    class EquationManager:
        LinkToFile=False;FilePath='';AutomaticRebuild=True;AutomaticSolveOrder=True;AngularEquationUnits=0
        def __init__(self):self.rows=[]
        def GetCount(self):return len(self.rows)
        def GetDisabledEquationCount(self):return 0
        def Add2(self,index,expression,solve):
            x.write_calls.append('Add2')
            assert index==-1 and solve is False
            if x.fault=='equation_pending':raise RuntimeError('Artificial missing Add2 return')
            if x.fault=='equation_false':return -1
            self.rows.append(expression);return 0
        def Equation(self,index):return self.rows[index]
        def GlobalVariable(self,index):return True
        def Disabled(self,index):return False
        def GetConfigurationOption(self,index):return 1
    x.manager=EquationManager();c.model.GetEquationMgr=lambda:x.manager
    class Selection:
        def __init__(self):self.selected=[]
        def CreateSelectData(self):return NS(Mark=0)
        def GetSelectedObjectCount2(self,mark):assert mark==-1;return len(self.selected)
        def GetSelectedObject6(self,index,mark):assert index==1 and mark==-1;return self.selected[0]
    x.selection=Selection();c.model.SelectionManager=x.selection
    def clear(all):
        assert all is True;x.write_calls.append('ClearSelection2')
        x.selection.selected.clear()
    c.model.ClearSelection2=clear
    def rebuild():
        x.write_calls.append('EditRebuild3')
        if x.fault=='rebuild_pending':raise RuntimeError('Artificial missing rebuild acknowledgement')
        return x.fault!='rebuild_false'
    c.model.EditRebuild3=rebuild
    body=make_body(points=[tuple(v*s for v,s in zip(point,(.04,.02,.01))) for point in POINTS])
    body.identity=object();x.body=body
    for edge in body.edges:edge.identity=object()
    refs={row['role']:bytes.fromhex(row['token']) for row in c.baseline['references'] if row['kind']=='face'}
    for face in body.faces:
        face.identity=object()
        vertices=sorted({tuple(float(v).hex() for v in edge.GetStartVertex().GetPoint()) for edge in face.GetEdges()}
            |{tuple(float(v).hex() for v in edge.GetEndVertex().GetPoint()) for edge in face.GetEdges()})
        role='body:0/'+_json(vertices);face.pid=refs[role];c.raw_by_pid[face.pid]=face
        face.GetFeature=lambda:b.feature
        def select(append,data,current=face):
            x.write_calls.append('Select4');assert append is False and data.Mark==0
            if x.fault=='select_pending':raise RuntimeError('Artificial missing Select4 return')
            if x.fault=='select_false':return False
            x.selection.selected=[current];return True
        face.Select4=select
    a.body_is_current=lambda model,obj:obj is body
    a.topology_is_current=lambda current,obj,kind:current is body and obj in (body.faces if kind=='face' else body.edges)
    a.geometry_summary=lambda obj,kind:dict(surface_type='plane')
    class FeatureManager:
        def InsertRefPlane(self,*args):
            x.write_calls.append('InsertRefPlane')
            assert args==(helper.SW_REF_PLANE_DISTANCE,.005,0,0.,0,0.)
            if x.fault=='insert_pending':raise RuntimeError('Artificial missing InsertRefPlane return')
            if x.fault=='insert_null':return None
            specific=NS(identity=object())
            row=dict(native_id=100,name='Plane4',feature_type='RefPlane',suppressed=False,
                owner_native_id=None,error_code=0,is_warning=False)
            plane=NS(identity=object(),pid=b'own-child-plane',row=row,Name='Plane4',parents=[b.feature],children=[])
            plane.GetID=lambda:plane.row['native_id'];plane.GetTypeName2=lambda:'RefPlane'
            plane.GetSpecificFeature2=lambda:specific
            plane.GetParents=lambda:plane.parents;plane.GetChildren=lambda:plane.children
            plane.GetOwnerFeature=lambda:None;plane.IsSuppressed2=lambda *args:[False]
            c.features.append(plane);b.feature.children=[plane];c.raw_by_pid[plane.pid]=plane
            x.raw_plane=plane;x.specific=specific
            if x.fault=='foreign_plane_handle':return NS(identity=object())
            if x.fault=='missing_parent':plane.parents=[]
            if x.fault=='missing_child':b.feature.children=[]
            return specific
    c.model.FeatureManager=FeatureManager()
    def rename(feature,name):
        x.write_calls.append('rename');feature.Name=name;feature.row['name']=name;return name
    a.rename_feature=rename
    x.catalog=FeatureCatalog(x.ownership.documents,x.store,'epoch')
    args=dict(document_id='target',configuration='Основная',expected_revision='trusted_fixture_setup')
    job,_=x.store.create('impact_fixture','verifier.impact_fixture',args,args,mutates=True)
    x.operation_id=job['operation_id'];x.store.start(x.operation_id)
    x.store.prepare_mutation(x.operation_id,connection_epoch='epoch',document_id='target',configuration='Основная',
        expected_revision='trusted_fixture_setup',before_state={'fixture_only':True},effect_scope='application')
    def recorder(name,phase,evidence):
        if x.fault=='ledger_returned' and name.endswith('insert_plane') and phase=='returned':
            raise OSError('Artificial durable insertion acknowledgement loss')
        x.store.record_mutation_step(x.operation_id,name=name,phase=phase,evidence=evidence)
    def query(raw,interface):
        if interface=='IFeature':
            if any(raw is feature for feature in c.features):return raw
            error=RuntimeError('Artificial specific/foreign object has no IFeature interface')
            error.hresult=-2147467262
            raise error
        assert interface=='IRefPlane'
        return raw
    x.helper=helper.B2ImpactFixtures(x.ownership,b,x.catalog,recorder=recorder,
        wrap=lambda raw,interface:raw,query=query)
    return x


def ledger(x):return x.store.get(x.operation_id)['mutation']['verification']['native_steps']


def test_actual_original_registry_context_graph_and_paired_native_receipts_prepare_only_own_child_plane(fixture):
    x=fixture;original=receipt_evidence(x);creation=x.store.get(x.binding.creation_operation_id)
    result=x.helper.add_child_plane(x.c.baseline)
    assert result['fixture_prepared'] is True and result['plane_name']=='Контрольная дочерняя плоскость'
    assert result['plane_pid_hex']==x.raw_plane.pid.hex() and result['plane_object_id'].startswith('feat_')
    assert x.helper.created_plane is x.raw_plane and x.helper.retained_face in x.body.faces
    graph=result['after_deletion_context']['dependency_graph'];parent=next(row for row in graph['nodes'] if row['native_id']==5)
    child=next(row for row in graph['nodes'] if row['native_id']==100)
    edge=[parent['node_index'],child['node_index']]
    assert edge in graph['relations']['parent_links'] and edge in graph['relations']['child_links']
    assert x.selection.selected==[] and x.write_calls.count('InsertRefPlane')==1
    steps=ledger(x);assert len(steps)==12 and len({row['name'] for row in steps})==6
    assert [row['phase'] for row in steps]==['pending','returned']*6
    assert receipt_evidence(x)==original and x.store.get(creation['operation_id'])==creation
    assert result['accepted'] is result['native_b2_accepted'] is result['public_mcp_accepted'] is False
    assert result['full_refusal_context_available'] is result['deletion_authorized'] is False
    with pytest.raises(helper.FixtureGate,match='one-shot'):x.helper.add_child_plane(x.c.baseline)


@pytest.mark.parametrize('fault',['select_pending','insert_pending','ledger_returned','rebuild_pending'])
def test_pending_native_or_journal_acknowledgement_never_clears_interrupted_selection_or_retries(fixture,fault):
    x=fixture;x.fault=fault
    with pytest.raises((RuntimeError,OSError)):x.helper.add_child_plane(x.c.baseline)
    assert x.helper.evidence()['pending_native_step'] is not None
    steps=ledger(x)
    assert steps[-1]['phase']=='pending'
    if fault in ('insert_pending','ledger_returned'):
        assert len(x.selection.selected)==1 and 'ClearSelection2' not in x.write_calls
    calls=list(x.write_calls)
    with pytest.raises(helper.FixtureGate):x.helper.add_child_plane(x.c.baseline)
    assert x.write_calls==calls


def test_actual_return_is_retained_before_durable_return_receipt_failure(fixture):
    x=fixture;x.fault='ledger_returned'
    with pytest.raises(OSError):x.helper.add_child_plane(x.c.baseline)
    assert x.helper.returned_plane is x.specific
    assert x.helper.created_plane is None and x.helper.plane_birth_diagnostic=={}
    assert x.helper.evidence()['returned_plane_retained'] is True
    assert ledger(x)[-1]['phase']=='pending'
    assert 'ClearSelection2' not in x.write_calls and 'EditRebuild3' not in x.write_calls


def test_failed_birth_comparisons_remain_available_without_adopting_return_or_writing_again(fixture):
    x=fixture
    x.helper.query=lambda raw,interface:x.raw_plane
    with pytest.raises(ValueError,match='Queried feature'):x.helper.add_child_plane(x.c.baseline)
    assert x.helper.returned_plane is x.specific and x.helper.created_plane is None
    diagnostic=x.helper.evidence()['plane_birth_diagnostic']
    assert diagnostic['raw_equals_queried_feature'] is False
    assert diagnostic['queried_feature_equals_current_feature'] is True
    assert diagnostic['accepted'] is False
    diagnostic['phase']='caller_mutation'
    assert x.helper.plane_birth_diagnostic['phase']=='feature_comparison'
    assert ledger(x)[-1]['phase']=='returned'
    assert x.write_calls==['Select4','InsertRefPlane']


@pytest.mark.parametrize('fault',['select_false','insert_null','foreign_plane_handle','missing_parent','missing_child','rebuild_false'])
def test_normally_returned_false_or_unconfirmed_new_handle_graph_refuses_without_undo_or_delete(fixture,fault):
    x=fixture;x.fault=fault
    with pytest.raises((ValueError,ExecutionFailure)):x.helper.add_child_plane(x.c.baseline)
    assert x.helper.pending_native_step is None and x.helper.journal_failed is False
    if fault in ('insert_null','foreign_plane_handle'):
        assert len(x.selection.selected)==1
        assert 'ClearSelection2' not in x.write_calls and 'EditRebuild3' not in x.write_calls
    else:assert x.selection.selected==[]
    assert x.write_calls.count('InsertRefPlane')<=1


@pytest.mark.parametrize('fault',['foreign_role','missing_pid','nonplanar','foreign_face_owner','foreign_pid','stale_epoch',
                                'foreign_body','wrong_native_face_geometry'])
def test_unproven_face_pid_geometry_current_canonical_or_owner_refuses_before_native_selection(fixture,fault):
    x=fixture;snapshot=deepcopy(x.c.baseline)
    kwargs={}
    if fault=='foreign_role':kwargs['face_role']='body:0/foreign'
    elif fault=='missing_pid':snapshot['references']=[row for row in snapshot['references'] if row['kind']!='face']
    elif fault=='nonplanar':x.c.adapter.geometry_summary=lambda *args:dict(surface_type='cylinder')
    elif fault=='foreign_face_owner':
        for face in x.body.faces:face.GetFeature=lambda:NS(identity=object())
    elif fault=='foreign_pid':
        original=x.c.adapter.resolve_persistent_id
        x.c.adapter.resolve_persistent_id=lambda model,pid,kind:NS(identity=object(),pid=pid) if kind=='face' else original(model,pid,kind)
    elif fault=='stale_epoch':x.ownership.connection_epoch='reconnected'
    elif fault=='wrong_native_face_geometry':
        reference=helper.end_face_reference(snapshot);face=x.c.raw_by_pid[bytes.fromhex(reference['token'])]
        other=next(candidate for candidate in x.body.faces if candidate is not face)
        face.GetEdges=other.GetEdges
    else:x.c.adapter.body_is_current=lambda *args:False
    with pytest.raises((helper.FixtureGate,ExecutionFailure,KeyError)):x.helper.add_child_plane(snapshot,**kwargs)
    assert x.write_calls==[]


@pytest.mark.parametrize('linked',[False,True])
def test_unused_global_and_actual_file_link_are_distinct_verified_native_manager_context_fixtures(fixture,linked,b2_private_dir):
    x=fixture;original=receipt_evidence(x)
    if linked:
        path=b2_private_dir/'owned-equations.txt';path.write_text('"Контрольная независимая величина" = 3',encoding='utf8')
        raw=path.read_bytes();result=x.helper.link_equation_file(path,expected_sha256=hashlib.sha256(raw).hexdigest())
        assert path.read_bytes()==raw and x.manager.FilePath==str(path.resolve())
    else:result=x.helper.add_unused_equation()
    assert result['fixture_prepared'] is True and result['linked_equation_fixture'] is linked
    assert result['after_deletion_context']['native_context']['equations']['rows']==[
        dict(row_index=0,expression=result['expression'],disabled=False,global_variable=True,configuration_option=1)]
    assert x.manager.LinkToFile is linked and x.write_calls==['Add2','EditRebuild3']
    assert all(row['name'].startswith('impact_'+('linked_equation' if linked else 'unused_equation')+'_') for row in ledger(x))
    assert result['full_refusal_context_available'] is False and result['accepted'] is False
    assert receipt_evidence(x)==original
    with pytest.raises(helper.FixtureGate):x.helper.add_unused_equation()


@pytest.mark.parametrize('fault',['equation_pending','equation_false','existing_row','linked_already','file_hash','file_content'])
def test_equation_pending_existing_or_unowned_file_refuses_one_shot_without_row_recovery(fixture,fault,b2_private_dir):
    x=fixture;x.fault=fault
    if fault=='existing_row':x.manager.rows=['"Чужая величина" = 7']
    if fault=='linked_already':x.manager.LinkToFile=True
    if fault.startswith('file_'):
        path=b2_private_dir/'private.txt';path.write_text('"Контрольная независимая величина" = '+('4' if fault=='file_content' else '3'),encoding='utf8')
        digest='0'*64 if fault=='file_hash' else hashlib.sha256(path.read_bytes()).hexdigest()
        callback=lambda:x.helper.link_equation_file(path,expected_sha256=digest)
    else:callback=x.helper.add_unused_equation
    with pytest.raises((helper.FixtureGate,RuntimeError)) as failure:callback()
    if fault.startswith('file_'):assert 'Exact owned unused-equation file bytes/SHA' in str(failure.value)
    assert x.write_calls==(['Add2'] if fault in ('equation_pending','equation_false') else [])
    if fault=='equation_pending':assert ledger(x)[-1]['phase']=='pending'


def test_linked_equation_outside_work_refuses_before_any_native_fixture_write(fixture,b2_outside_dir):
    x=fixture;path=b2_outside_dir/'outside-equations.txt'
    path.write_text('"Контрольная независимая величина" = 3',encoding='utf8')
    assert not path.resolve().is_relative_to((scripts.parent/'work').resolve())
    with pytest.raises(helper.FixtureGate,match='private existing'):
        x.helper.link_equation_file(path,expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert x.write_calls==[]


def test_requirements_never_claim_extra_plane_equations_or_ancillary_complete_scope():
    result=helper.refusal_oracle_requirements()
    assert result['full_refusal_context_available'] is result['accepted'] is result['native_b2_accepted'] is False
    assert 'extra_plane_or_equations_target_outside_complete_BASE_oracle' in result['open_gates']
