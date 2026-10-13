"""Current original refs after artificial renames; actual catalogs and SQLite."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_topology import ComponentTopologyCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.features import FeatureCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.server_v2 import response
from test_component_topology_v2 import TopologyAdapter
from test_document_catalog_v2 import model
from test_feature_domain_v2 import Adapter as FeatureAdapter, feature
from test_feature_suppression_domain import InlineWorker

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_rename_references import rename_references_case
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world(tmp_path):
    a = TopologyAdapter(); assembly_docs = DocumentCatalog(a)
    topology = ComponentTopologyCatalog(assembly_docs)
    fa = FeatureAdapter(); part = model(path='C:/one.sldprt'); part.identity = a.part
    f = feature(1, 'Контрольный блок'); part.features = [f]; fa.models = [part]
    part_docs = DocumentCatalog(fa); store = JobStore(tmp_path/'jobs.sqlite')
    features = FeatureCatalog(part_docs, store, 'epoch')
    pd = part_docs.list()['documents'][0]
    pc = dict(document_id=pd['document_id'], configuration='Основная')
    feature_id = features.list(**pc)['items'][0]['object_id']
    ad = assembly_docs.list()['documents'][0]
    ac = dict(document_id=ad['document_id'], configuration='Основная', expected_observation_revision=ad['observation_revision'])
    c = a.instances[0]
    component = next(row for row in topology.list(**ac)['items'] if row['component_path'] == c.info['component_path'])
    body = topology.bodies(**ac, component_id=component['component_id'])['items'][0]
    face = topology.list_topology(**ac, component_id=component['component_id'], body_id=body['body_id'], kind='face')['items'][0]
    native_body = c.bodies[0]
    native_face = a.registry[topology._topology_state(
        assembly_docs.resolve(ac['document_id'], ac['configuration'])[0])['refs'][face['object_id']].persistent_id]
    refs = dict(feature_id=feature_id, component_id=component['component_id'], body_id=body['body_id'], face_id=face['object_id'])
    objects = dict(feature=f, component=c, body=native_body, face=native_face)
    originals = {role: dict(identity=obj.identity, pid=obj.pid if role == 'feature' else obj.persistent_id) for role, obj in objects.items()}
    # Owner-prepared artificial rename phase. Helper never executes a setter.
    f.state['name'] = 'Переименованный блок'
    c.info['component_path'] = 'Переименованный экземпляр-1'
    a.models[0].state['update_stamp'] += 1
    ac['expected_observation_revision'] = assembly_docs.list()['documents'][0]['observation_revision']
    runner = JobRunner(store, InlineWorker())
    x = NS(a=a, fa=fa, part=part, f=f, component=c, body=native_body, face=native_face, features=features,
        topology=topology, store=store, pc=pc, ac=ac, refs=refs, corrupt=None, native_corrupt=None,
        calls=[], retained=[], full_calls=0)
    class Client:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get': job = store.get(args['operation_id']); data = job
            else:
                spec = SPECS[tool]; payload = spec.payload(args)
                method = {'feature_get': features.get, 'component_get': topology.get,
                          'component_topology_get': topology.get_topology}[tool]
                def execute():
                    value = method(**payload['arguments'])
                    if x.corrupt: x.corrupt(tool, value)
                    return value
                job = runner.submit(args['request_id'], spec.operation, payload['arguments'], execute,
                                    context=payload['context'], mutates=False)
                data = job['result']
            return NS(isError=False, structuredContent=response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=data, error=job['error']).model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self): return NS(child_can_close=not x.retained, fixture_can_cleanup=not x.retained)
    x.reader = B3Reader(Client(), store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    anchors = []
    def ordinal(identity):
        if identity not in anchors: anchors.append(identity)
        return anchors.index(identity)+1
    def native(pc, ac, explicit):
        assert explicit == refs
        proof = {}
        for role, obj in objects.items():
            old = originals[role]
            pid = obj.pid if role == 'feature' else obj.persistent_id
            if role == 'feature': raw = fa.resolve_persistent_id(part, old['pid'], 'feature'); summary = deepcopy(obj.state)
            else:
                raw = a.resolve_persistent_id(a.models[0], old['pid'], role if role != 'component' else 'component')
                summary = a.component_info(obj)[0] if role == 'component' else a.geometry_summary(obj, role)
                if role != 'component': summary['kind'] = obj.kind
            context = pc if role == 'feature' else ac
            proof[role] = dict(document_id=context['document_id'], configuration=context['configuration'],
                original_object_id=explicit[dict(feature='feature_id', component='component_id', body='body_id', face='face_id')[role]],
                original_native_identity=ordinal(old['identity']), current_native_identity=ordinal(obj.identity),
                original_pid_hex=old['pid'].hex(), current_pid_hex=pid.hex(), summary=summary,
                original_pid_resolution=dict(native_state=0, resolved_native_identity=ordinal(raw.identity), returned_pid_hex=pid.hex()),
                native_receipt=dict(artificial_original_current=True))
        proof['feature']['owner_model_native_identity'] = ordinal(part.identity)
        proof['component']['referenced_model_native_identity'] = ordinal(a.part)
        proof['body']['owner_component_native_identity'] = ordinal(c.identity)
        proof['face'].update(owner_component_native_identity=ordinal(c.identity), owner_body_native_identity=ordinal(native_body.identity))
        if x.native_corrupt: x.native_corrupt(proof)
        return proof
    def full():
        x.full_calls += 1
        return dict(artificial_part=deepcopy(part.state), feature=deepcopy(f.state),
            assembly=deepcopy(a.models[0].state), instances=[deepcopy(item.info) for item in a.instances],
            original_body_faces=[(item.persistent_id.hex(), a.geometry_summary(item, 'face')) for item in native_body.faces],
            ui=dict(selected=[], active='original', command_in_progress=False))
    x.native, x.full = native, full
    yield x
    part_docs.close(); assembly_docs.close(); store.close()


def run(x, **overrides):
    args = dict(part_context=x.pc, assembly_context=x.ac, original_refs=x.refs,
        expected_names=dict(feature='Переименованный блок', component='Переименованный экземпляр-1'),
        capture_full=x.full, capture_references=x.native)
    args.update(overrides)
    return asyncio.run(rename_references_case(x.reader, **args))


def test_original_refs_after_renames_resolve_same_native_objects_actual_journal(world):
    x = world; result = run(x)
    assert len(result['rows']) == len(x.store.list(limit=100)['items']) == 3
    assert result['before'] == result['after'] and x.full_calls == 2
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert all(row['journal']['mutation'] is None for row in result['rows'])


def test_native_pid_alias_and_new_enumeration_id_do_not_retire_original_feature_ref(world):
    x = world
    original_pid = x.f.pid
    x.f.pid = b'new-feature-pid-alias'
    original_resolve = x.fa.resolve_persistent_id
    def resolve(model, pid, kind):
        if pid == original_pid: return x.f
        return original_resolve(model, pid, kind)
    x.fa.resolve_persistent_id = resolve
    fresh = x.features.list(**x.pc)['items'][0]['object_id']
    assert fresh != x.refs['feature_id']
    value = run(x)
    assert value['rows'][0]['journal']['result']['feature']['object_id'] == x.refs['feature_id']
    assert value['native_before']['feature']['original_pid_hex'] != value['native_before']['feature']['current_pid_hex']


@pytest.mark.parametrize('role', ['feature', 'component', 'body', 'face'])
def test_identical_looking_replacement_is_never_adopted_by_the_original_identity_producer(world, role):
    x = world
    getattr(x, dict(feature='f', component='component', body='body', face='face')[role]).identity = object()
    with pytest.raises(ValueError): run(x)
    assert x.calls == []


@pytest.mark.parametrize('fault', ['new_identity', 'old_pid', 'foreign_owner', 'wrong_model', 'name', 'scope', 'face', 'session'])
def test_current_original_membership_and_whole_scope_differences_reject(world, fault):
    x = world
    def bad(proof):
        if fault == 'new_identity': proof['component']['current_native_identity'] = 999
        elif fault == 'old_pid': proof['face']['original_pid_resolution']['native_state'] = 1
        elif fault == 'foreign_owner': proof['face']['owner_body_native_identity'] = 999
        elif fault == 'wrong_model': proof['component']['referenced_model_native_identity'] = 999
        elif fault == 'name': proof['feature']['summary']['name'] = 'Другое имя'
    x.native_corrupt = bad
    if fault in ('scope', 'face'):
        def corrupt(tool, value):
            if fault == 'scope' and tool == 'component_get': value['observation_revision'] = 'other'
            if fault == 'face' and tool == 'component_topology_get': value['object']['area_mm2'] = 999.
        x.corrupt = corrupt
    if fault == 'session':
        original = x.full
        def full():
            value = original()
            if x.full_calls == 2: value['ui']['selected'] = ['other']
            return value
        x.full = full
    with pytest.raises(ValueError): run(x)
