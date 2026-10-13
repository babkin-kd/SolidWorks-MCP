"""Direct artificial CAD getters, actual geometry registration, no native CAD."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.geometry import GeometryCatalog
from test_geometry_v2 import GeometryAdapter

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_native_part_reference import RetainedPartReference, capture_native_part_reference
finally:
    sys.path.remove(scripts)


@pytest.fixture
def world():
    a = GeometryAdapter(); body = a.body(faces=6)
    model = a.models[0]; cfg = NS(identity=a.configurations[model.identity, 'Основная'], Name='Основная')
    model.GetActiveConfiguration = lambda: cfg
    model.GetUpdateStamp = lambda: model.state['update_stamp']
    model.GetSaveFlag = lambda: model.state['needs_save']
    model.GetBodies2 = lambda code, hidden: list(a.objects[model.identity])
    model.Extension = NS(GetPersistReference3=lambda obj: tuple(obj.persistent_id),
        GetObjectByPersistReference3=lambda pid: (a.registry[bytes(pid)], 0))
    body.GetType = lambda: 0
    body.GetBodyBox = lambda: [0., 0., 0., .02, .01, .005]
    body.Name = 'Контрольное тело'
    body.GetFaces = lambda: list(body.faces); body.GetEdges = lambda: list(body.edges)
    body.GetFaceCount = lambda: len(body.faces); body.GetEdgeCount = lambda: len(body.edges)
    for face in body.faces:
        face.GetBody = lambda: body; face.GetSurface = lambda: NS(IsPlane=lambda: True)
        face.GetArea = lambda: 25e-6; face.GetEdges = lambda: list(body.edges)
    for edge in body.edges:
        edge.GetBody = lambda: body
        edge.GetCurve = lambda: NS(Identity=lambda: 3001, GetLength3=lambda start, end: .005)
        edge.GetCurveParams2 = lambda: [0., 0., 0., .005, 0., 0., 0., 1.]
    def summary(obj, kind):
        if kind == 'body': return dict(body_type='solid', name='Контрольное тело', face_count=6, edge_count=4,
            bounding_box_mm=dict(min_mm=[0., 0., 0.], max_mm=[20., 10., 5.], approximate=True))
        if kind == 'face': return dict(area_mm2=25., surface_type='plane', edge_count=4)
        return dict(curve_type='line', length_mm=5., start_mm=[0., 0., 0.], end_mm=[5., 0., 0.])
    a.geometry_summary = summary
    docs = DocumentCatalog(a); catalog = GeometryCatalog(docs)
    row = docs.list()['documents'][0]
    context = dict(document_id=row['document_id'], configuration='Основная', expected_observation_revision=row['observation_revision'])
    b = catalog.list(**context)['items'][0]
    f = catalog.list(**context, kind='face', body_id=b['object_id'])['items'][0]
    e = catalog.list(**context, kind='edge', body_id=b['object_id'])['items'][0]
    refs = docs.resolve(context['document_id'], context['configuration'])[0].geometry['references']
    items = dict(body=b, face=f, edge=e)
    bindings = {}
    for kind, item in items.items():
        ref = refs[item['object_id']]; obj = a.registry[ref.persistent_id]
        bindings[kind] = RetainedPartReference(item['object_id'], kind, obj, obj.identity, ref.persistent_id)
    x = NS(a=a, model=model, cfg=cfg, context=context, items=items, bindings=bindings,
           sequence=0, safe_calls=[], identity_calls=0)
    identities = []
    def identity(obj):
        x.identity_calls += 1
        return obj.identity
    def ordinal(value):
        if value not in identities: identities.append(value)
        return identities.index(value)+1
    def safe(context): x.safe_calls.append(deepcopy(context))
    x.identity, x.ordinal, x.safe = identity, ordinal, safe
    x.docs=docs
    return x


def run(x, kind='body', **overrides):
    args = dict(context=x.context, item=x.items[kind], model=x.model,
        model_canonical=x.model.identity, configuration_canonical=x.cfg.identity,
        binding=x.bindings[kind], owner_body=x.bindings['body'], wrap=lambda raw, interface: raw,
        identity=x.identity, ordinal=x.ordinal, persistent_variant=lambda pid: pid,
        original_body_census=[x.bindings['body'].canonical],
        watch=NS(poll=lambda: x.sequence), assert_safe=x.safe)
    args.update(overrides)
    return capture_native_part_reference(**args)


@pytest.mark.parametrize('kind', ['body', 'face', 'edge'])
def test_direct_getters_current_membership_and_registered_original_native_refs(world, kind):
    x = world; result = run(x, kind)
    assert result['persistent_id'] == x.bindings[kind].persistent_id.hex()
    assert len(x.safe_calls) == 2 and x.identity_calls > 0
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False


@pytest.mark.parametrize('fault', ['replaced', 'pid_state', 'different_pid', 'foreign_body', 'removed_face',
    'nonplane', 'nonline', 'nan', 'wrong_count', 'wrong_summary', 'configuration', 'metadata', 'aba', 'ordinal_aba', 'extra_body'])
def test_raw_native_difference_or_aba_never_receives_replacement_data(world, fault):
    x = world; kind = 'body'
    if fault == 'replaced': x.bindings['body'].handle.identity = object()
    elif fault == 'pid_state': x.model.Extension.GetObjectByPersistReference3 = lambda pid: (None, 4)
    elif fault == 'different_pid': x.model.Extension.GetPersistReference3 = lambda obj: b'other'
    elif fault == 'foreign_body': x.model.GetBodies2 = lambda *args: []
    elif fault == 'extra_body': x.a.body()
    elif fault == 'removed_face': kind = 'face'; x.bindings['body'].handle.GetFaces = lambda: []
    elif fault == 'nonplane': kind = 'face'; x.bindings['face'].handle.GetSurface = lambda: NS(IsPlane=lambda: False)
    elif fault == 'nonline': kind = 'edge'; x.bindings['edge'].handle.GetCurve = lambda: NS(Identity=lambda: 3002)
    elif fault == 'nan': x.bindings['body'].handle.GetBodyBox = lambda: [float('nan')]*6
    elif fault == 'wrong_count': x.bindings['body'].handle.GetFaceCount = lambda: 99
    elif fault == 'wrong_summary': x.items['body']['name'] = 'Подмена'
    elif fault == 'configuration': x.cfg.identity = object()
    elif fault == 'metadata': x.model.GetSaveFlag = lambda: 'true'
    elif fault == 'ordinal_aba':
        def ordinal(value): x.sequence += 2; return 1
        x.ordinal = ordinal
    else:
        original = x.bindings['body'].handle.GetBodyBox
        def box(): x.sequence += 2; return original()
        x.bindings['body'].handle.GetBodyBox = box
    overrides = dict(configuration_canonical=object()) if fault == 'configuration' else {}
    with pytest.raises(ValueError): run(x, kind, **overrides)


def test_owner_gate_failure_prevents_native_getters(world):
    x = world
    def unsafe(context): raise RuntimeError('Owner not quiescent')
    with pytest.raises(RuntimeError): run(x, assert_safe=unsafe)
    assert x.identity_calls == 0


def test_owner_gate_precedes_even_native_canonical_equality(world):
    x = world
    class NativeCanonical:
        def __eq__(self, other): raise AssertionError('Native comparison before owner admission')
    def unsafe(context): raise RuntimeError('Owner not quiescent')
    with pytest.raises(RuntimeError): run(x, original_body_census=[NativeCanonical()], assert_safe=unsafe)
    assert x.identity_calls == 0


def test_closing_owner_admission_is_inside_metadata_and_event_envelope(world):
    x=world;calls=[]
    def safe(context):
        calls.append(True)
        if len(calls)==2:x.sequence+=2
    with pytest.raises(ValueError,match='events'):run(x,assert_safe=safe)
