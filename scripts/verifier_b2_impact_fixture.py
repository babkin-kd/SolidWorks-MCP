"""One-shot owner-invoked N5 native fixture prep; never acceptance or recovery.

No connection/CoInitialize/CLI is provided. The native owner supplies the live
construction registry, exact retained binding, FeatureCatalog and durable ledger.
The extra plane/equations remain OUTSIDE the complete BASE snapshot profile.
Official contracts: IFeatureManager.InsertRefPlane (selected reference mark 0),
IEquationMgr.Add2(-1, expression, False), FilePath before LinkToFile.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from solidworks_mcp.constants import SW_REF_PLANE_DISTANCE
from solidworks_mcp.features import russian_name
from solidworks_mcp.jobs import _json
from solidworks_mcp.rectangle_snapshot import BASE, validated_rectangle_snapshot
from verifier_b2_plane_birth import OriginalFeature,NativePlaneBridge,bind_returned_plane


SCOPE='owned_b2_impact_fixture_preparation_v1'
FULL_REFUSAL_GATES=(
    'extra_plane_or_equations_target_outside_complete_BASE_oracle',
    'full_target_annotations_views_configuration_material_units_auxiliary_after_fixture',
    'complete_session_neighbor_BREP_dimension_sketch_metadata_view_and_file_census',
    'before_after_refusal_read_only_identity_events_and_complete_data_equality',
)


class FixtureGate(ValueError):
    pass


def require(condition,message):
    if not condition:raise FixtureGate(message)


def _array(value):
    # Existing native relation capture explicitly accepts normally returned None
    # as an empty collection. A getter exception never reaches this conversion.
    if value is None:return []
    require(type(value) in (tuple,list) and len(value)<=5000,'Complete bounded native array required.')
    return list(value)


def _number(value):
    require(type(value) in (int,float) and math.isfinite(value),'Strict finite native number required.')
    return float(value)


def end_face_reference(snapshot):
    """Exact declared planar end face, from its complete BREP/plane frame/PID.

No enumeration index or face name selects a native object. The returned role is
the analytical incidence role already used by the production _topology binder.
"""
    snapshot=validated_rectangle_snapshot(snapshot)
    state=snapshot['clone_state']
    require(state['profile']==BASE and snapshot['solid_body_count']==1,'Current unsuppressed BASE required.')
    geometry=state['geometry']
    require(geometry['representation']=='planar_polyhedral_brep_v1' and len(geometry['bodies'])==1,
            'One complete planar BREP body required.')
    frame=[float.fromhex(value) for value in state['sketch']['reference_plane']['transform']]
    require(len(frame)==16,'Complete native reference frame required.')
    normal=frame[6:9];origin=frame[9:12]
    depth=float.fromhex(state['extrusion']['directions'][0]['depth'])
    require(depth>0 and state['extrusion']['ReverseDirection'] is False,'Positive blind extrusion required.')
    body=geometry['bodies'][0];matches=[]
    for face in body['faces']:
        vertices=sorted({tuple(body['vertices'][coedge['start']])
                         for loop in face['loops'] for coedge in loop['coedges']})
        values=[[float.fromhex(value) for value in point] for point in vertices]
        if len(values)==4 and all(math.isclose(math.fsum((point[i]-origin[i])*normal[i] for i in range(3)),
                    depth,rel_tol=0.,abs_tol=1e-10) for point in values):
            role='body:0/'+_json(vertices)
            refs=[row for row in snapshot['references'] if row['kind']=='face' and row['role']==role]
            require(len(refs)==1,'Expected end face lacks one exact declared PID role.')
            matches.append(deepcopy(refs[0]))
    require(len(matches)==1,'Expected positive-depth planar end face is missing or ambiguous.')
    return matches[0]


class B2ImpactFixtures:
    """Trusted STA callbacks; each instance prepares exactly one fixture case.

recorder(name, phase, evidence) must persist nonempty pending/returned receipts.
A native exception or returned-ledger loss leaves pending/journal flags intact;
no subsequent cleanup/getter/mutation is dispatched by this helper.
"""
    def __init__(self,ownership,binding,feature_catalog,*,recorder,wrap=None,query=None):
        require(callable(recorder),'Explicit owner-issued durable recorder required.')
        require(feature_catalog.documents is ownership.documents and feature_catalog.store is ownership.store
            and feature_catalog.connection_epoch==ownership.connection_epoch==binding.connection_epoch,
            'Reuse the exact live construction owner/catalog/journal/epoch.')
        self.ownership,self.binding,self.catalog=ownership,binding,feature_catalog
        self.adapter=ownership.adapter
        self.recorder,self.wrapper=recorder,wrap
        self.query=query
        self.used=False;self.case=None;self.pending_native_step=None;self.journal_failed=False
        self.created_plane=None;self.created_plane_identity=None;self.created_plane_pid=None
        self.returned_plane=None;self.plane_birth_diagnostic={}
        self.retained_face=None;self.retained_face_identity=None

    def _wrap(self,raw,interface):
        if raw is None:return None
        if self.wrapper is not None:return self.wrapper(raw,interface)
        from solidworks_mcp import binding
        return binding.wrap(raw,getattr(self.adapter._module,interface))

    def _query(self,raw,interface):
        if self.query is not None:return self.query(raw,interface)
        from solidworks_mcp import binding
        return binding.queried(raw,getattr(self.adapter._module,interface))

    def _owner(self):
        binding,feature=self.ownership.resolve(self.binding.document_id,self.binding.configuration,
            self.binding.object_id,connection_epoch=self.binding.connection_epoch)
        require(binding is self.binding and binding.kind=='extrusion'
            and self.adapter.identity(feature)==binding.feature_identity,'Exact retained B1 extrusion required.')
        suppressed=_array(feature.IsSuppressed2(1,None))
        require(suppressed==[False] and type(suppressed[0]) is bool,'Current unsuppressed owner required.')
        return feature

    def _claim(self,kind):
        require(not self.used,'Fixture callback is one-shot; no retry after any outcome.')
        self.used=True;self.case=kind
        return self._owner()

    def _step(self,label,callback,evidence,result_evidence):
        require(self.pending_native_step is None and not self.journal_failed,'Pending native/journal receipt prohibits dispatch.')
        label='impact_'+self.case+'_'+label
        self.pending_native_step=label;self.journal_failed=True
        self.recorder(label,'pending',deepcopy(evidence));self.journal_failed=False
        result=callback()
        self.journal_failed=True
        self.recorder(label,'returned',result_evidence(result));self.journal_failed=False
        self.pending_native_step=None
        return result

    def evidence(self):
        return dict(scope=SCOPE,fixture_case=self.case,one_shot_started=self.used,
            pending_native_step=self.pending_native_step,journal_failed=self.journal_failed,
            returned_plane_retained=self.returned_plane is not None,
            plane_birth_diagnostic=deepcopy(self.plane_birth_diagnostic),
            accepted=False,native_b2_accepted=False,public_mcp_accepted=False,
            deletion_authorized=False,full_refusal_context_available=False,
            open_gates=list(FULL_REFUSAL_GATES))

    def _context(self):
        b=self.binding
        result=self.catalog.deletion_context(b.document_id,b.configuration)
        graph=result['dependency_graph']
        require(result['native_inventory_capture_closed'] is True
            and graph['all_reported_native_relations_captured'] is True
            and result['deletion_authorized'] is False and result['deletion_impact_complete'] is False,
            'Complete native-reported dependency/context capture required.')
        _json(result)
        return result

    def _pid(self,obj,kind):
        b=self.binding;pid=self.adapter.persistent_id(b.model,obj)
        require(type(pid) is bytes and bool(pid),'Exact current native PID required.')
        current=self.adapter.resolve_persistent_id(b.model,pid,kind)
        require(current is not None and self.adapter.identity(current)==self.adapter.identity(obj)
            and self.adapter.persistent_id(b.model,current)==pid,'Exact PID/canonical roundtrip required.')
        return pid

    def _count_selection(self,manager):
        count=manager.GetSelectedObjectCount2(-1)
        require(type(count) is int and count in (0,1),'Exact finite fixture selection count required.')
        return count

    def _face_incidence_role(self,face,body):
        edges=_array(face.GetEdges())
        require(len(edges)==4,'Native rectangular end face must expose four complete edges.')
        points=set()
        for raw in edges:
            edge=self._wrap(raw,'IEdge')
            require(self.adapter.topology_is_current(body,edge,'edge') is True
                and self.adapter.identity(self._wrap(edge.GetBody(),'IBody2'))==self.adapter.identity(body),
                'Every selected-face edge must belong to the exact current body.')
            for getter in ('GetStartVertex','GetEndVertex'):
                vertex=self._wrap(getattr(edge,getter)(),'IVertex')
                require(vertex is not None,'Complete face endpoint vertex required.')
                values=vertex.GetPoint()
                require(type(values) in (tuple,list) and len(values)==3,'Full native face endpoint coordinates required.')
                points.add(tuple(_number(value).hex() for value in values))
        require(len(points)==4,'Selected face incidence must have exactly four distinct corners.')
        return 'body:0/'+_json(sorted(points))

    def _graph_delta(self,before,after,parent_id,child_id):
        old=before['dependency_graph'];new=after['dependency_graph']
        old_rows={row['native_id']:row for row in old['nodes']}
        new_rows={row['native_id']:row for row in new['nodes']}
        require(set(new_rows)==set(old_rows)|{child_id},'Complete graph may add only the one declared plane.')
        for identifier,row in old_rows.items():
            require(_json({key:value for key,value in row.items() if key!='node_index'})==
                _json({key:value for key,value in new_rows[identifier].items() if key!='node_index'}),
                'Original full dependency nodes changed during fixture prep.')
        def edges(graph,key):
            nodes={row['node_index']:row['native_id'] for row in graph['nodes']}
            return {(nodes[left],nodes[right]) for left,right in graph['relations'][key]}
        for key in ('parent_links','child_links','absorbed_links'):
            allowed={(parent_id,child_id)} if key!='absorbed_links' else set()
            require(edges(new,key)==edges(old,key)|allowed,'Unrelated or missing native graph relation delta.')

    def add_child_plane(self,parent_snapshot,*,face_role=None,name='Контрольная дочерняя плоскость',offset_mm=5.):
        name=russian_name(name);offset=_number(offset_mm)
        require(0<offset<=100,'Fixture positive offset is limited to 100 mm.')
        reference=end_face_reference(parent_snapshot)
        require(face_role is None or face_role==reference['role'],'Declared face role is not the positive-depth end face.')
        owner=self._claim('child_plane');b=self.binding;a=self.adapter
        require(not _array(owner.GetChildren()),'Fixture starts with normally returned empty owner children.')
        before=self._context()
        original_members=a.features(b.model);original_identities=[a.identity(obj) for obj in original_members]
        require(_json(a.dimension_geometry_snapshot(b.model))==_json(parent_snapshot['clone_state']['geometry']),
                'Current native BREP differs from the proven parent snapshot.')
        pid=bytes.fromhex(reference['token']);face=a.resolve_persistent_id(b.model,pid,'face')
        require(face is not None and self._pid(face,'face')==pid,'Exact declared current face PID required.')
        require(a.geometry_summary(face,'face')['surface_type']=='plane','Selected end face must be native planar.')
        body=self._wrap(face.GetBody(),'IBody2')
        require(a.body_is_current(b.model,body) is True and a.topology_is_current(body,face,'face') is True,
                'Exact current face/body census membership required.')
        require(self._face_incidence_role(face,body)==reference['role'],
                'Actual selected face incidence is not the declared geometric end-face role.')
        face_owner=self._wrap(face.GetFeature(),'IFeature')
        require(face_owner is not None and a.identity(face_owner)==b.feature_identity,
                'The declared end face must belong to the original extrusion canonical identity.')
        self.retained_face=face;self.retained_face_identity=a.identity(face)
        selection=self._wrap(b.model.SelectionManager,'ISelectionMgr')
        require(self._count_selection(selection)==0,'Fixture requires empty selection; no borrowed UI selection.')
        select_data=self._wrap(selection.CreateSelectData(),'ISelectData')
        self._step('set_first_reference_mark',lambda:setattr(select_data,'Mark',0),
            dict(mark=0),lambda value:dict(readback_mark=select_data.Mark))
        require(type(select_data.Mark) is int and select_data.Mark==0,'Exact first-reference selection mark required.')
        entity=self._wrap(face,'IEntity')
        selected=self._step('select_face',lambda:entity.Select4(False,select_data),
            dict(face_pid_hex=pid.hex(),mark=0,append=False),lambda value:dict(returned=value is True))
        if selected is not True:
            self._clear_selection(selection)
            raise FixtureGate('Native Select4 did not normally confirm the exact face.')
        require(self._count_selection(selection)==1
            and a.identity(selection.GetSelectedObject6(1,-1))==self.retained_face_identity,
            'Actual selected native object differs from the retained exact face.')
        manager=self._wrap(b.model.FeatureManager,'IFeatureManager')
        def insert_plane():
            plane=manager.InsertRefPlane(SW_REF_PLANE_DISTANCE,offset/1000.,0,0.,0,0.)
            # Retain the actual normally returned handle before journal I/O or
            # any interface/census checks. Retention grants no adoption/cleanup.
            self.returned_plane=plane
            return plane
        plane=self._step('insert_plane',insert_plane,
            dict(face_pid_hex=pid.hex(),constraint=SW_REF_PLANE_DISTANCE,offset_m=(offset/1000.).hex()),
            lambda value:dict(native_handle_returned=value is not None))
        require(plane is not None,'Normally returned plane handle is required; effects remain unconfirmed.')
        birth=bind_returned_plane(plane,
            [OriginalFeature(obj,canonical) for obj,canonical in zip(original_members,original_identities)],
            a.features(b.model),self._query,self._wrap,a.identity,diagnostic=self.plane_birth_diagnostic,
            native_bridge=NativePlaneBridge(lambda obj:a.persistent_id(b.model,obj),
                lambda pid:a.resolve_persistent_id(b.model,pid,'feature'),a._sw.IsSame))
        created=birth.feature
        self.created_plane=created;self.created_plane_identity=birth.feature_canonical
        # Only a normally returned insertion and durable acknowledgement permit
        # clearing our selection. An exception/pending ledger cannot reach here.
        self._clear_selection(selection)
        require(plane is not None,'Normally returned plane handle is required; effects remain unconfirmed.')
        rebuilt=self._step('rebuild',lambda:b.model.EditRebuild3(),dict(fixture_only=True),lambda value:dict(returned=value is True))
        require(rebuilt is True,'Child plane fixture rebuild was not confirmed.')
        members=a.features(b.model)
        additions=[obj for obj in members if not any(a.identity(obj)==old for old in original_identities)]
        require(len(additions)==1 and len(members)==len(original_members)+1
            and all(sum(a.identity(obj)==old for obj in members)==1 for old in original_identities),
            'One exact new feature with every original canonical member preserved required.')
        require(a.identity(additions[0])==self.created_plane_identity,
                'Retained normally returned feature changed during selection clear/rebuild.')
        require(created.GetTypeName2()=='RefPlane','Only a native reference plane may be created.')
        specific=self._wrap(created.GetSpecificFeature2(),'IRefPlane')
        require(specific is not None,'Retained feature must still expose its current plane interface.')
        self.created_plane_pid=self._pid(created,'feature')
        self._step('rename_plane',lambda:a.rename_feature(created,name),dict(requested_russian_name=name),
                   lambda value:dict(readback_name=value))
        require(str(created.Name)==name,'Exact Russian plane name readback required.')
        children=[self._wrap(raw,'IFeature') for raw in _array(owner.GetChildren())]
        parents=[self._wrap(raw,'IFeature') for raw in _array(created.GetParents())]
        require(len(children)==len(parents)==1 and a.identity(children[0])==self.created_plane_identity
            and a.identity(parents[0])==b.feature_identity,
            'Both native parent/child canonical links must confirm the retained original extrusion.')
        require(self._pid(owner,'feature')==b.persistent_id and self._pid(created,'feature')==self.created_plane_pid,
                'Original/new current PID bindings changed during dependency confirmation.')
        after=self._context();graph=after['dependency_graph'];nodes=graph['nodes']
        parent_nodes=[row for row in nodes if row['native_id']==b.native_id]
        child_nodes=[row for row in nodes if row['native_id']==created.GetID()]
        require(len(parent_nodes)==len(child_nodes)==1 and child_nodes[0]['persistent_reference_supported'] is True,
                'Complete dependency graph must bind exact persistent parent/child members.')
        edge=[parent_nodes[0]['node_index'],child_nodes[0]['node_index']]
        require(edge in graph['relations']['parent_links'] and edge in graph['relations']['child_links']
            and not graph['relations']['parent_links_without_child_confirmation']
            and not graph['relations']['child_links_without_parent_confirmation'],
            'Complete graph must independently agree with native parent/child getters.')
        self._graph_delta(before,after,b.native_id,created.GetID())
        require(_json(a.dimension_geometry_snapshot(b.model))==_json(parent_snapshot['clone_state']['geometry']),
                'Child fixture changed original full native BREP.')
        return dict(**self.evidence(),fixture_prepared=True,face_reference=reference,
            plane_birth_binding=birth.evidence,
            plane_pid_hex=self.created_plane_pid.hex(),plane_object_id=child_nodes[0]['object_id'],
            plane_name=name,before_deletion_context=before,after_deletion_context=after)

    def _clear_selection(self,manager):
        self._step('clear_owned_selection',lambda:self.binding.model.ClearSelection2(True),
            dict(only_fixture_selection=True),lambda value:dict(normally_returned=True))
        require(self._count_selection(manager)==0,'Owned fixture selection was not cleared.')

    def _equation(self,name,value,kind):
        name=russian_name(name);value=_number(value)
        require(value==3.,'Only the unused constant global-variable fixture value 3 is supported.')
        self._claim(kind);b=self.binding
        manager=self._wrap(b.model.GetEquationMgr(),'IEquationMgr')
        require(manager is not None and type(manager.GetCount()) is int and manager.GetCount()==0
            and type(manager.GetDisabledEquationCount()) is int and manager.GetDisabledEquationCount()==0
            and manager.LinkToFile is False and manager.FilePath=='',
            'Equation fixture requires a genuinely empty unlinked manager.')
        before=self._context();expression='"'+name+'" = 3'
        index=self._step('add_unused_global',lambda:manager.Add2(-1,expression,False),
            dict(expression=expression,solve=False,index=-1),lambda value:dict(returned_index=value))
        require(type(index) is int and index==0 and manager.Equation(index)==expression
            and manager.GlobalVariable(index) is True and manager.Disabled(index) is False,
            'Normally returned Add2 must bind exactly the new unused global-variable row.')
        return manager,expression,before

    def add_unused_equation(self,*,name='Контрольная независимая величина',value=3.):
        manager,expression,before=self._equation(name,value,'unused_equation')
        rebuilt=self._step('rebuild',lambda:self.binding.model.EditRebuild3(),dict(fixture_only=True),
                           lambda value:dict(returned=value is True))
        require(rebuilt is True,'Equation fixture rebuild was not confirmed.')
        return self._equation_result(manager,expression,before,linked=False)

    def link_equation_file(self,path,*,expected_sha256,name='Контрольная независимая величина',value=3.):
        path=Path(path).resolve(strict=True)
        require(path.is_relative_to((Path.cwd()/'work').resolve()) and path.suffix.lower()=='.txt' and path.is_file(),
                'Only an explicitly supplied private existing fixture equation file is allowed.')
        original=path.read_bytes()
        expression='"'+russian_name(name)+'" = 3'
        require(type(expected_sha256) is str and hashlib.sha256(original).hexdigest()==expected_sha256
            and original.decode('utf8').strip()==expression,'Exact owned unused-equation file bytes/SHA required.')
        manager,expression,before=self._equation(name,value,'linked_equation')
        self._step('set_file_path',lambda:setattr(manager,'FilePath',str(path)),dict(private_file=str(path),sha256=expected_sha256),
                   lambda value:dict(normally_returned=True))
        require(Path(manager.FilePath).resolve()==path,'Native equation file-path readback differs.')
        self._step('link_file',lambda:setattr(manager,'LinkToFile',True),dict(linked=True),
                   lambda value:dict(normally_returned=True))
        require(manager.LinkToFile is True,'Actual native LinkToFile=True readback required.')
        rebuilt=self._step('rebuild',lambda:self.binding.model.EditRebuild3(),dict(fixture_only=True),
                           lambda value:dict(returned=value is True))
        require(rebuilt is True and path.read_bytes()==original,'Linked fixture rebuild/file preservation is unconfirmed.')
        return dict(**self._equation_result(manager,expression,before,linked=True),
                    equation_file=dict(path=str(path),sha256=expected_sha256,bytes=len(original)))

    def _equation_result(self,manager,expression,before,*,linked):
        after=self._context();equations=after['native_context']['equations']
        require(type(manager.GetCount()) is int and manager.GetCount()==1 and manager.GetDisabledEquationCount()==0
            and manager.Equation(0)==expression and manager.GlobalVariable(0) is True and manager.Disabled(0) is False
            and equations['enumerated_count']==1 and equations['disabled_count']==0
            and equations['properties']['linked_to_file'] is linked
            and equations['properties']['file_path']==manager.FilePath
            and len(equations['rows'])==1 and equations['rows'][0]['expression']==expression
            and equations['rows'][0]['global_variable'] is True and equations['rows'][0]['disabled'] is False,
            'Native manager and complete independently enumerated equation context disagree.')
        return dict(**self.evidence(),fixture_prepared=True,unused_global_variable=True,
            linked_equation_fixture=linked,expression=expression,
            before_deletion_context=before,after_deletion_context=after)


def refusal_oracle_requirements():
    """Concrete native-owner collector contract, NOT a complete-scope assertion.

Bracket two FeatureCatalog.deletion_context reads and target getters with two
NativeDocumentOpenCatalog._capture_session captures (all live identities/events,
files/windows/application/UI/neighbor data). Require exact equality immediately
before/after each refused public mutation and no mutation checkpoint/native step.
Target getters: dimension_geometry_snapshot full BREP, dimensions+summary+PID
roundtrips, retained sketch_snapshot, document_view_snapshot, extrusion getter,
all planes/configuration/units/properties/material/body/display/annotations and
auxiliary inventories. Existing BASE/first-save excludes fourth plane/equations;
do not replace missing current observations with the original creation snapshot.
Disabled equations, foreign annotation views or missing native arrays fail closed.
The future collector must separately prove all these gates; this file prepares
only the finite fixture and reported dependency/equation context.
"""
    return dict(scope=SCOPE,full_refusal_context_available=False,accepted=False,
                native_b2_accepted=False,public_mcp_accepted=False,open_gates=list(FULL_REFUSAL_GATES))
