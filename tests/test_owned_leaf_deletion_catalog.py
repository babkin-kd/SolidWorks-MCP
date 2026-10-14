"""Actual registry/SQLite/census/classifiers; artificial native getters only."""
from copy import deepcopy

import pytest

from solidworks_mcp.cad_deletion_context import SCOPE as CONTEXT_SCOPE
from solidworks_mcp.jobs import ExecutionFailure, _json
from solidworks_mcp.owned_leaf_deletion_catalog import OwnLeafDeletionCatalog, SCOPE
from solidworks_mcp.rectangle_construction import BlindRectangleExtrusion
from test_rectangle_extrusion_postconditions import proof
from test_cad_owned_suppression_snapshot import case
from test_feature_suppression_domain import domain
from test_owned_leaf_deletion_postconditions import current_depth


@pytest.fixture
def extrusion_proof(proof,request):
    """Both original captures retain full measured metadata before registration."""
    before,after,definition=deepcopy(proof)
    context=dict(scope=CONTEXT_SCOPE,
        equations=dict(enumerated_count=0,disabled_count=0,disabled_definitions_captured=True,
            properties=dict(linked_to_file=False,file_path='',automatic_rebuild=True,
                automatic_solve_order=True,angular_equation_units=0),rows=[]),
        external_references=dict(count=0,rows=[]),auxiliary_references=dict(count=0,rows=[]))
    for state in (before,after):
        data=state['snapshots']['target']['clone_state']
        data['equation_reference_inventory']=deepcopy(context)
        for dimension in data['dimensions']:
            dimension.update(parameter_type=0,values={'Основная':dimension['values_si']['Основная']*1000.},
                display_dimensions=[dict(type=2,linked=False,linked_text='')],tolerance=dict(type=0,values_si=[]))
    if request.node.callspec.params['case']=='display':
        # The reusable case rewrites its BASE primary anchor to this strategy.
        # Its original pre-creation SKETCH must use the same measured anchor;
        # do this before registration/SQLite publication, never rewrite history.
        old=before['snapshots']['target']
        owner_role=old['clone_state']['sketch']['feature_pid_hex']['reference_role']
        owner_pid=next(row['token'] for row in old['references']
            if row['kind']=='feature' and row['role']==owner_role)
        for reference in old['references']:
            if reference['kind']=='dimension':
                reference['token']=_json(dict(strategy='display_dimension_v1',
                    display_pid_hex=(reference['role']+'-display').encode().hex(),
                    owner_pid_hex=owner_pid,dimension_index=0,display_type=2))
    return before,after,definition


@pytest.fixture
def leaf(domain):
    state=domain
    c=state.c
    adapter=c.adapter
    state.children=[]
    state.child_reads=0
    state.context_reads=0
    state.snapshot_reads=0
    state.reference_reads=0
    state.complete_observations={}
    state.application=dict(user_control=True,visible=True,current_directory='C:/private/',search_folders='')
    state.mode=dict(blocking_state=0,read_only_state=0,editing_sketch=False,
        editing_component=False,view_only=False,drawing_state=None)
    def children():
        state.child_reads+=1
        return state.children
    state.binding.feature.GetChildren=children
    rows={row['document_id']:deepcopy(row) for row in state.semantic['documents']}
    for document_id,row in rows.items():
        row.pop('selection')
        row.pop('view')
        row.pop('mode')
        row.pop('visible')
        row.pop('dependencies')
        state.complete_observations[document_id]=row
    # The real close/open catalogs combine these native getters and validate
    # complete window/model membership, modes, application and reference arrays.
    def observe(entry):
        result=deepcopy(state.complete_observations[entry.document_id])
        if entry.document_id=='target':
            result.update(update_stamp=state.sequence,observation_sequence=state.sequence,
                observation_revision='obs_'+str(state.sequence))
        return result
    state.ownership.documents._observe=observe
    def close_context(model):
        state.context_reads+=1
        return dict(visible=True,dependencies=[],mode=deepcopy(state.mode))
    adapter.native_close_model_context=close_context
    adapter.document_view_snapshot=lambda model:dict(matrix=[1.,0.,0.],scale=1.)
    adapter.native_close_windows=lambda:[(entry.model,dict(hwnd=100+index,
        title=state.complete_observations[entry.document_id]['title'])) for index,entry in enumerate(state.entries)]
    adapter.native_close_application_context=lambda:deepcopy(state.application)
    def references(model):
        state.reference_reads+=1
        return []
    adapter.native_open_model_references=references
    original=adapter.rectangle_construction_snapshot
    def snapshot(model):
        state.snapshot_reads+=1
        return original(model)
    adapter.rectangle_construction_snapshot=snapshot
    state.leaf=OwnLeafDeletionCatalog(state.ownership.documents,state.store,'epoch',state.ownership)
    return state


def prepare(state,**overrides):
    context=dict(document_id='target',configuration='Основная',object_id=state.binding.object_id)
    return state.leaf.prepare(**{**context,**overrides})


def receipt_evidence(state):
    receipt=state.binding.receipt
    return (_json({key:value for key,value in vars(receipt).items()
        if type(value) in (str,int,float,bool,type(None))}),
        tuple((key,value) for key,value in vars(receipt).items()
            if type(value) not in (str,int,float,bool,type(None))))


@pytest.mark.parametrize('children',[None,[],()])
def test_read_only_preparation_uses_full_native_census_and_preserves_original_receipt(leaf,children):
    state=leaf
    state.children=children
    original=receipt_evidence(state)
    job=state.store.get(state.binding.creation_operation_id)
    result=prepare(state)
    assert result['scope']==result['revision_scope']==SCOPE
    assert result['object_id']==state.binding.object_id
    assert result['feature_native_id']==state.binding.native_id
    assert result['feature_pid_hex']==state.binding.persistent_id.hex()
    assert result['creation_operation_id']==state.binding.creation_operation_id
    assert result['current_definition']['depth_mm']==10.
    assert result['delete_authorized'] is False
    assert result['native_execution_available'] is True
    assert result['application_command_in_progress'] is False
    assert result['baseline']['semantic']['application']==state.application
    assert result['baseline']['semantic']['files']==[]
    assert all(set(row['mode'])==set(state.mode) and 'dependency_files' in row
        and 'selection' not in row for row in result['baseline']['semantic']['documents'])
    assert state.child_reads==2 and state.snapshot_reads>=8
    assert state.context_reads>=16 and state.reference_reads>=8
    assert receipt_evidence(state)==original and state.store.get(job['operation_id'])==job
    assert state.calls==[] and state.guard_count==state.releases==0 and state.name_writes==[]
    result['baseline']['snapshots']['target']['references'].clear()
    assert prepare(state)['baseline']['snapshots']['target']['references']


@pytest.mark.parametrize('depth_mm',[10.,12.])
@pytest.mark.parametrize('rename',[False,True])
def test_current_depth_and_russian_feature_body_names_are_measured_not_creation_filled(leaf,depth_mm,rename):
    state=leaf
    original=receipt_evidence(state)
    old=state.binding.creation_result['before']['definition']
    pair=(dict(snapshots={'target':state.c.baseline}),None,
          BlindRectangleExtrusion.validate(**old))
    current_depth(pair,depth_mm)
    state.c.baseline['clone_state']['dimensions'][2]['values']['Основная']=depth_mm
    if rename:
        state.binding.feature.row['name']='Собственное выдавливание'
        state.c.baseline['clone_state']['dimensions'][2]['owner']['name']='Собственное выдавливание'
        state.c.bodies[0]._name='Тело опоры'
        next(row for row in state.c.baseline['native_observations']['qualified_dimensions']
             if row['role']=='dimension:depth')['full_name']='Толщина@Собственное выдавливание@Контрольная деталь.Part'
    result=prepare(state)
    assert result['current_definition']['depth_mm']==depth_mm
    assert result['current_definition']['feature_name']==('Собственное выдавливание' if rename else old['feature_name'])
    assert result['current_definition']['body_name']==('Тело опоры' if rename else old['body_name'])
    assert state.binding.creation_result['before']['definition']==old
    assert receipt_evidence(state)==original and state.calls==[]


@pytest.mark.parametrize('fault',['foreign_doc','foreign_object','foreign_config','epoch',
    'feature_canonical','model_canonical','configuration_canonical','native_id','feature_pid',
    'sketch_canonical','sketch_missing','children','children_incomplete','suppressed'])
def test_stale_foreign_replaced_or_nonleaf_native_binding_refuses_without_write(leaf,fault):
    state=leaf
    args={}
    if fault=='foreign_doc': args['document_id']='foreign'
    elif fault=='foreign_object': args['object_id']='feat_'+'f'*32
    elif fault=='foreign_config': args['configuration']='Чужая'
    elif fault=='epoch': state.leaf.connection_epoch='foreign_epoch'
    elif fault=='feature_canonical': state.binding.feature.identity=object()
    elif fault=='model_canonical': state.binding.model.identity=object()
    elif fault=='configuration_canonical': state.c.configuration_identity=object()
    elif fault=='native_id': state.binding.feature.GetID=lambda:99
    elif fault=='feature_pid': state.binding.feature.pid=b'foreign'
    elif fault=='sketch_canonical': state.binding.receipt.borrowed_sketch.identity=object()
    elif fault=='sketch_missing': state.c.features.remove(state.binding.receipt.borrowed_sketch)
    elif fault=='children': state.children=[object()]
    elif fault=='children_incomplete': state.children=False
    elif fault=='suppressed': state.binding.feature.row['suppressed']=True
    with pytest.raises(ExecutionFailure): prepare(state,**args)
    assert state.calls==[] and state.guard_count==state.releases==0


@pytest.mark.parametrize('fault',['equation','linked_file','missing_properties','equation_rows',
    'aux_reference','attachment','external_feature','dependency','sketch_point',
    'neighbor_material','partial_neighbor','incomplete_mode','incomplete_app','incomplete_view',
    'multiple_cfg','readonly','hidden_neighbor'])
def test_complete_context_graph_and_neighbors_are_not_replaced_by_toy_counts(leaf,fault,monkeypatch):
    state=leaf
    data=state.c.baseline['clone_state']
    equations=data['equation_reference_inventory']['equations']
    if fault=='equation':
        equations['enumerated_count']=1
        equations['rows']=[dict(row_index=0,expression='"Ширина" = 40',disabled=False,global_variable=False,configuration_option=1)]
    elif fault=='linked_file': equations['properties'].update(linked_to_file=True,file_path='C:/private/equations.txt')
    elif fault=='missing_properties': equations.pop('properties')
    elif fault=='equation_rows': equations['rows'].append(dict(row_index=0))
    elif fault=='aux_reference':
        data['equation_reference_inventory']['auxiliary_references']=dict(count=1,
            rows=[dict(row_index=0,feature_name='Основание',file_path='C:/private/reference.sldprt')])
    elif fault=='attachment': data['auxiliary_data']['attachments']=1
    elif fault=='external_feature': data['feature_external_reference_inventory']['total_reference_rows']=1
    elif fault=='dependency':
        links=data['dependencies']
        for key in ('parent_links','child_links'): links[key].append([5,0])
        links['relations_read']+=2
    elif fault=='sketch_point': data['sketch']['points'][0]['coordinates_si'][0]=(.1).hex()
    elif fault=='neighbor_material':
        original=state.c.adapter.rectangle_construction_snapshot
        reads=[]
        def changing(model):
            result=original(model)
            if model is not state.c.model:
                reads.append(True)
                result['clone_state']['material']=['foreign'+str(len(reads)),'']
            return result
        monkeypatch.setattr(state.c.adapter,'rectangle_construction_snapshot',changing)
    elif fault=='partial_neighbor':
        original=state.c.adapter.rectangle_construction_snapshot
        monkeypatch.setattr(state.c.adapter,'rectangle_construction_snapshot',
            lambda model:original(model) if model is state.c.model else {'partial':True})
    elif fault=='incomplete_mode': state.mode.pop('drawing_state')
    elif fault=='incomplete_app': state.application.pop('search_folders')
    elif fault=='incomplete_view': state.c.adapter.document_view_snapshot=lambda model:{}
    elif fault=='multiple_cfg': state.complete_observations['target']['configurations'].append('Чужая')
    elif fault=='readonly': state.mode['read_only_state']=1
    elif fault=='hidden_neighbor':
        original=state.c.adapter.native_close_model_context
        state.c.adapter.native_close_model_context=lambda model:{**original(model),
            'visible':model is state.c.model}
    with pytest.raises(ExecutionFailure): prepare(state)
    assert state.calls==[] and state.guard_count==state.releases==0


@pytest.mark.parametrize('getter',['children','snapshot','application','references'])
def test_normally_returned_complete_getters_are_required_and_exceptions_do_not_write(leaf,getter,monkeypatch):
    state=leaf
    def failure(*args): raise RuntimeError('Artificial native getter did not return')
    if getter=='children': monkeypatch.setattr(state.binding.feature,'GetChildren',failure)
    elif getter=='snapshot': monkeypatch.setattr(state.c.adapter,'rectangle_construction_snapshot',failure)
    elif getter=='application': monkeypatch.setattr(state.c.adapter,'native_close_application_context',failure)
    else: monkeypatch.setattr(state.c.adapter,'native_open_model_references',failure)
    with pytest.raises(RuntimeError,match='did not return'): prepare(state)
    assert state.calls==[] and state.guard_count==state.releases==0


@pytest.mark.parametrize('fault',['busy_before','busy_after','model_event','session_race'])
def test_busy_and_event_or_full_session_races_refuse_read_only_preparation(leaf,fault):
    state=leaf
    if fault=='busy_before': state.busy=True
    elif fault=='busy_after':
        calls=[]
        def busy():
            calls.append(True)
            return len(calls)>1
        state.c.adapter.application_busy=busy
    elif fault=='model_event':
        original=state.binding.feature.GetChildren
        def children():
            result=original()
            state.c.events+=1
            return result
        state.binding.feature.GetChildren=children
    else:
        original=state.c.adapter.native_close_application_context
        calls=[]
        def application():
            calls.append(True)
            return {**original(),'current_directory':'C:/private/'+str(len(calls))}
        state.c.adapter.native_close_application_context=application
    with pytest.raises(ExecutionFailure): prepare(state)
    assert state.calls==[] and state.guard_count==state.releases==0


def test_current_full_neighbor_or_view_changes_produce_a_new_preview_revision(leaf):
    state=leaf
    first=prepare(state)
    state.c.adapter.document_view_snapshot=lambda model:dict(matrix=[0.,1.,0.],scale=2.)
    second=prepare(state)
    assert first['revision']!=second['revision']
    assert first['baseline']['semantic']['documents']!=second['baseline']['semantic']['documents']
    assert second['delete_authorized'] is False
    assert second['native_execution_available'] is True
    state.corrupt_neighbor=True
    third=prepare(state)
    assert second['revision']!=third['revision']
    assert third['baseline']['snapshots']['neighbor']['clone_state']['material']==['foreign','']


@pytest.mark.parametrize('status',['running','queued','failed','unknown'])
def test_original_creation_requires_actual_durable_succeeded_row_before_native_read(leaf,status):
    state=leaf
    state.store._db.execute('UPDATE jobs SET status=? WHERE operation_id=?',
        (status,state.binding.creation_operation_id))
    with pytest.raises(ExecutionFailure): prepare(state)
    assert state.child_reads==state.snapshot_reads==0 and state.calls==[]
