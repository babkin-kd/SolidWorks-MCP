"""Artificial native handles; actual catalog/JobRunner/SQLite/public observer."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.component_topology import ComponentTopologyCatalog
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.geometry import GeometryCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.server_v2 import response
from test_component_topology_v2 import TopologyAdapter
from test_feature_suppression_domain import InlineWorker
from test_document_catalog_v2 import model

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_component_membership as helper
    from verifier_b3_reader import B3Reader
    from verifier_b3_public_contract import SPECS
finally:
    sys.path.remove(scripts)


def transform(origin, axes=None):
    axes = axes or [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    return dict(origin_mm=list(origin), axes_in_assembly=deepcopy(axes),
                parity='right_handed', scale=1., includes_presentation_transform=False)


@pytest.fixture
def world(tmp_path):
    a = TopologyAdapter()
    a.models[1].state['document_type'] = 'assembly'
    part = model(title='Отдельная контрольная деталь')
    a.models.append(part)
    a.objects[part.identity] = []
    for name in part.state['configurations']: a.configurations[part.identity, name] = object()
    shared = a.part
    main, variant = a.instances
    main.info['component_path'] = 'Повторная деталь-1'
    variant.info['component_path'] = 'Повторная деталь-2'
    main.info['transform'] = transform([0., 0., 0.])
    variant.info['transform'] = transform([50., 10., 20.], [[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
    for native, count in ((main, 3), (variant, 2)):
        native.bodies = [a.body(surface=i == count-1) for i in range(count)]
        native.model_identity = shared
    def instance(role, path, cfg, origin, parent=None, assembly=False):
        native = NS(identity=object(), persistent_id=role.encode(), parent=parent, bodies=[], cfg=cfg,
                    model_identity=object() if assembly or role == 'cylinder' else shared)
        native.info = dict(component_path=path, referenced_path='C:/sub.sldasm' if assembly else
            ('C:/cylinder.sldprt' if role == 'cylinder' else 'C:/one.sldprt'),
            referenced_configuration=cfg, referenced_document_type='assembly' if assembly else 'part',
            suppression_state='resolved', native_suppression_state=2, hidden=False, transform=transform(origin))
        if not assembly: native.bodies = [a.body(surface=i == 2) for i in range(3 if role == 'nested' else 1)]
        a.registry[native.persistent_id] = native
        a.instances.append(native)
        return native
    parent = instance('parent', 'Подсборка-1', 'Основная', [100., 0., 0.], assembly=True)
    nested = instance('nested', 'Подсборка-1/Вложенная деталь-1', 'Основная', [130., 0., 0.], parent=parent)
    cylinder = instance('cylinder', 'Цилиндр-1', 'Основная', [150., 0., 0.])
    originals = dict(main=main, variant=variant, nested=nested, parent=parent, cylinder=cylinder)
    # Canonical model/config anchors are actual artificial retained objects.
    cfg_anchors = {(native.model_identity, native.cfg): object() for native in a.instances}
    original_component_info = a.component_info
    def component_info(native):
        original_component_info(native)  # Keep the real artificial resolved-state gate.
        return deepcopy(native.info), (native.model_identity,
            cfg_anchors[native.model_identity, native.info['referenced_configuration']])
    a.component_info = component_info
    for native in a.instances:
        t = native.info['transform']
        native.raw_total_transform = [v for axis in t['axes_in_assembly'] for v in axis] + [v/1000. for v in t['origin_mm']] + [1., 0., 0., 0.]
    old_summary = a.geometry_summary
    def summary(obj, kind):
        if kind == 'body':
            return dict(body_type=obj.body_type, face_count=len(obj.faces), edge_count=len(obj.edges),
                name='Искусственное тело', bounding_box_mm=dict(min_mm=[0., 0., 0.], max_mm=[20., 10., 5.], approximate=True))
        return old_summary(obj, kind)
    a.geometry_summary = summary
    docs = DocumentCatalog(a); catalog = ComponentTopologyCatalog(docs)
    listed = docs.list()['documents']
    def context(index):
        row = listed[index]
        return dict(document_id=row['document_id'], configuration=row['active_configuration'],
                    expected_observation_revision=row['observation_revision'])
    root, foreign, part_context = context(0), context(1), context(2)
    rows = catalog.list(**root)['items']
    entry, _ = docs.resolve(root['document_id'], root['configuration'])
    state = catalog._state(entry)
    ids = {role: next(row['component_id'] for row in rows
                     if state['refs'][row['component_id']].native_identity == native.identity)
           for role, native in originals.items()}
    a.body(document_index=2)
    part_body = GeometryCatalog(docs).list(**part_context)['items'][0]['object_id']
    store = JobStore(tmp_path/'jobs.sqlite'); runner = JobRunner(store, InlineWorker())
    x = NS(a=a, docs=docs, catalog=catalog, entry=entry, ids=ids, originals=originals,
           context=root, foreign=foreign, part_context=part_context, part_body=part_body,
           store=store, runner=runner, corrupt=None, native_corrupt=None, unknown=False,
           calls=[], retained=[], full_calls=0, instance_calls=0, reference_calls=0)
    class Protocol:
        async def call_tool(self, tool, args):
            x.calls.append((tool, deepcopy(args)))
            if tool == 'job_get': job = store.get(args['operation_id'])
            else:
                spec = SPECS[tool]
                payload = spec.payload(args)
                method = {'component.list': catalog.list, 'component.get': catalog.get,
                    'component.bodies': catalog.bodies, 'component.topology_list': catalog.list_topology,
                    'component.topology_get': catalog.get_topology}[spec.operation]
                def call():
                    if x.unknown: raise RuntimeError('Artificial uncertain native observation')
                    value = method(**payload['arguments'])
                    if x.corrupt: x.corrupt(tool, args, value)
                    return value
                job = runner.submit(args['request_id'], spec.operation, payload['arguments'], call,
                                    context=payload['context'], mutates=False)
            value = response(status=job['status'], operation_id=job['operation_id'],
                context=job['payload']['context'], data=job['result'], error=job['error'])
            # job_get publishes actual full DTO as production does.
            if tool == 'job_get':
                value = response(status=job['status'], operation_id=job['operation_id'], data=job,
                    context=job['payload']['context'], error=job['error'])
            return NS(isError=False, structuredContent=value.model_dump(mode='json'))
        def retain(self, reason): x.retained.append(reason)
        async def observe_once(self):
            safe = not x.retained and all(job['status'] in ('succeeded', 'failed') for job in store.list(limit=100)['items'])
            return NS(child_can_close=safe, fixture_can_cleanup=safe)
    x.client = Protocol()
    x.reader = B3Reader(x.client, store.path, assert_before_dispatch=lambda: None, persist=lambda rows: None)
    ordinals = []
    def ordinal(identity):
        for i, anchor in enumerate(ordinals):
            if anchor == identity: return i+1
        ordinals.append(identity); return len(ordinals)
    def full():
        x.full_calls += 1
        # Full current fake model state, bodies, native topology, all transforms,
        # referenced config anchors and UI metadata, no reused source baseline.
        return dict(artificial_native_full_session=dict(
            models=[dict(identity=ordinal(m.identity), metadata=deepcopy(m.state)) for m in a.models],
            instances=[dict(identity=ordinal(n.identity), pid=n.persistent_id.hex(), info=deepcopy(n.info),
                raw_transform=n.raw_total_transform, parent=None if n.parent is None else ordinal(n.parent.identity),
                bodies=[dict(identity=ordinal(b.identity), pid=b.persistent_id.hex(), summary=summary(b, 'body'),
                    faces=[(ordinal(f.identity), f.persistent_id.hex(), ordinal(f.body.identity), summary(f, 'face')) for f in b.faces],
                    edges=[(ordinal(e.identity), e.persistent_id.hex(), ordinal(e.body.identity), summary(e, 'edge')) for e in b.edges]) for b in n.bodies]) for n in a.instances]))
    def instance_capture(ctx, item):
        x.instance_calls += 1
        assert ctx == root
        ref = state['refs'][item['component_id']]
        native = a.resolve_persistent_id(a.models[0], ref.persistent_id, 'component')
        assert native is originals[next(role for role, key in ids.items() if key == item['component_id'])]
        assert native.identity == ref.native_identity and native in a.instances
        info, anchors = a.component_info(native)
        value = dict(component_info=info, total_transform=list(native.raw_total_transform),
            persistent_id=native.persistent_id.hex(), native_identity=ordinal(native.identity),
            model_identity=ordinal(anchors[0]), configuration_identity=ordinal(anchors[1]),
            parent_native_identity=None if native.parent is None else ordinal(native.parent.identity),
            native_receipt={'artificial_retained_handles': True})
        if x.native_corrupt: x.native_corrupt('instance', item, value)
        return value
    def reference_capture(ctx, component, item):
        x.reference_calls += 1
        assert ctx == root
        native_component = a.registry[state['refs'][component['component_id']].persistent_id]
        kind = item.get('kind', 'body')
        ref = (state['bodies'][item['body_id']] if kind == 'body' else catalog._topology_state(entry)['refs'][item['object_id']])
        native = a.resolve_persistent_id(a.models[0], ref.persistent_id, kind)
        assert native.identity == ref.native_identity
        body = native if kind == 'body' else native.body
        assert body in native_component.bodies
        if kind != 'body': assert native in (body.faces if kind == 'face' else body.edges)
        value = dict(summary=summary(native, kind), persistent_id=native.persistent_id.hex(),
            native_identity=ordinal(native.identity), owner_component_native_identity=ordinal(native_component.identity),
            owner_body_native_identity=ordinal(body.identity), native_receipt={'artificial_current_membership': True})
        if kind != 'body': value['summary']['kind'] = kind
        if x.native_corrupt: x.native_corrupt('reference', item, value)
        return value
    x.full, x.instance_capture, x.reference_capture = full, instance_capture, reference_capture
    yield x
    docs.close(); store.close()


def run(x, **overrides):
    args = dict(context=x.context, foreign_root_context=x.foreign, part_context=x.part_context,
        instance_ids=x.ids, part_body_id=x.part_body, capture_full=x.full,
        capture_instance=x.instance_capture, capture_reference=x.reference_capture)
    args.update(overrides)
    return asyncio.run(helper.component_membership_case(x.reader, **args))


def test_exact_repeated_native_instances_current_membership_and_sql_roundtrips(world):
    x = world; result = run(x)
    assert x.full_calls == 2 and x.instance_calls == 5 and x.reference_calls == 29
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    jobs = x.store.list(limit=100)['items']
    assert len(jobs) == len(result['rows']) == 34
    assert all(job['payload']['mutates'] is False and 'mutation' not in job for job in jobs)
    assert sum(job['status'] == 'failed' for job in jobs) == 5
    assert all(job['error']['requires_reconciliation'] is False for job in jobs if job['status'] == 'failed')
    assert x.retained == []
    assert {tool for tool, _ in x.calls if tool != 'job_get'} == {
        'component_list', 'component_get', 'component_body_list', 'component_body_get',
        'component_face_list', 'component_edge_list', 'component_topology_get'}


@pytest.mark.parametrize('fault', ['cfg', 'raw_transform', 'raw_short', 'scaled', 'mirrored',
    'native_identity', 'native_model', 'native_cfg', 'native_parent', 'pid', 'native_summary', 'owner_component', 'owner_body'])
def test_independent_current_native_pid_canonical_config_transform_or_owner_mismatch_stops(world, fault):
    x = world
    def corrupt(kind, item, value):
        if kind == 'instance':
            if fault == 'cfg': value['component_info']['referenced_configuration'] = 'Другая'
            elif fault == 'raw_transform': value['total_transform'][9] += .001
            elif fault == 'raw_short': value['total_transform'].pop()
            elif fault == 'scaled': value['total_transform'][12] = 2.
            elif fault == 'mirrored': value['total_transform'][0] *= -1.
            elif fault == 'native_identity': value['native_identity'] = 1
            elif fault == 'native_model': value['model_identity'] += x.instance_calls
            elif fault == 'native_cfg': value['configuration_identity'] = 99
            elif fault == 'native_parent' and item['component_id'] == x.ids['nested']: value['parent_native_identity'] = 999
            elif fault == 'pid': value['persistent_id'] = 'FF'
        elif kind == 'reference':
            if fault == 'native_summary': value['summary']['foreign_fact'] = True
            elif fault == 'owner_component': value['owner_component_native_identity'] = 999
            elif fault == 'owner_body': value['owner_body_native_identity'] = 999
    x.native_corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1 and len(x.calls) < 100


@pytest.mark.parametrize('fault', ['scope', 'revision', 'cfg', 'frame', 'census', 'missing_id',
    'component_roundtrip', 'body_count', 'body_owner', 'body_roundtrip', 'topology_owner', 'topology_count', 'topology_roundtrip'])
def test_actual_durable_success_does_not_override_wrong_public_membership_facts(world, fault):
    x = world
    def corrupt(tool, args, value):
        if fault == 'scope': value['scope'] = 'foreign'
        elif fault == 'revision': value['observation_revision'] = 'stale'
        elif fault == 'cfg': value['configuration'] = 'Другая'
        elif fault == 'frame': value['transform_target_frame'] = 'component_model'
        elif fault == 'census' and tool == 'component_list': value['total_count'] = 6
        elif fault == 'missing_id' and tool == 'component_list': value['items'][0]['component_id'] = 'unheld'
        elif fault == 'component_roundtrip' and tool == 'component_get': value['component']['hidden'] = True
        elif fault == 'body_count' and tool == 'component_body_list': value['total_count'] = 99
        elif fault == 'body_owner' and tool == 'component_body_list': value['items'][0]['component_id'] = x.ids['cylinder']
        elif fault == 'body_roundtrip' and tool == 'component_body_get': value['items'][0]['name'] = 'Другое'
        elif fault == 'topology_owner' and tool == 'component_face_list': value['items'][0]['body_id'] = 'foreign'
        elif fault == 'topology_count' and tool == 'component_edge_list': value['total_count'] = True
        elif fault == 'topology_roundtrip' and tool == 'component_topology_get': value['object']['area_mm2'] = 99.
    x.corrupt = corrupt
    with pytest.raises(ValueError): run(x)
    assert x.full_calls == 1


@pytest.mark.parametrize('fault', ['stale', 'inactive', 'replaced', 'load', 'unknown'])
def test_real_catalog_or_runner_refusal_never_becomes_success_or_after_capture(world, fault):
    x = world
    if fault == 'stale': x.context['expected_observation_revision'] = 'stale'
    elif fault == 'inactive': x.context['configuration'] = 'Вариант'
    elif fault == 'replaced': x.originals['main'].identity = object()
    elif fault == 'load': x.originals['main'].info['native_suppression_state'] = 1
    else: x.unknown = True
    with pytest.raises((ValueError, AssertionError)): run(x)
    assert x.full_calls == 1
    if fault == 'replaced':
        # Enumeration creates a fresh public ID, which the exact original-ID
        # census gate rejects. It never adopts that otherwise valid row.
        assert len([tool for tool, _ in x.calls if tool != 'job_get']) == 1
        return
    assert x.retained
    sends = len(x.calls)
    with pytest.raises(RuntimeError): asyncio.run(x.reader.read('component_get', dict(
        request_id='never-retry', **x.context, component_id=x.ids['main'])))
    assert len(x.calls) == sends


def test_full_current_part_configuration_and_session_preservation_difference_rejects(world):
    x = world; original = x.full
    def full():
        value = original()
        if x.full_calls == 2: value['artificial_native_full_session']['models'][2]['metadata']['active_configuration'] = 'Вариант'
        return value
    with pytest.raises(ValueError): run(x, capture_full=full)
    assert x.full_calls == 2


@pytest.mark.parametrize('override', ['duplicate_ids', 'adopted_id', 'same_root', 'missing_capture', 'incomplete_capture'])
def test_no_original_explicit_owner_scope_or_full_producer_means_no_dispatch(world, override):
    x = world; args = {}
    if override == 'duplicate_ids': args['instance_ids'] = dict(x.ids, variant=x.ids['main'])
    elif override == 'adopted_id': args['instance_ids'] = {'main': x.ids['main']}
    elif override == 'same_root': args['foreign_root_context'] = x.context
    elif override == 'missing_capture': args['capture_instance'] = None
    else: args['capture_full'] = lambda: (_ for _ in ()).throw(ValueError('Actual full native capture unavailable'))
    with pytest.raises(ValueError): run(x, **args)
    assert x.calls == []
