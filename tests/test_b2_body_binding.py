"""Artificial original/current body bridge only; no COM or CAD acceptance."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_body_binding import NativeBodyBridge, bind_current_body
finally:
    sys.path.remove(scripts)


@pytest.fixture
def body_binding():
    x = NS(original=NS(canonical=object()), body=NS(canonical=object()),
           owner=NS(canonical=object()), pid=b'original-body', calls=[], hook=None)
    x.original_canonical = x.original.canonical
    x.owner_canonical = x.owner.canonical
    x.bodies = [x.body]
    x.faces = [NS(canonical=object()) for _ in range(6)]

    def call(name, args, result):
        x.calls.append((name, args))
        if x.hook is not None:
            changed = x.hook(name, args, result)
            if changed is not None:
                return changed
        return result

    x.identity = lambda obj: call('identity', (obj,), obj.canonical if obj is not None else None)
    x.census = lambda: call('census', (), list(x.bodies))
    x.persistent_id = lambda obj: call('pid', (obj,), x.pid)
    x.resolve_body = lambda pid: call('resolve', (pid,), x.body)
    x.query = lambda obj, interface: call('query', (obj, interface), obj)
    x.is_same = lambda old, new: call('same', (old, new), 1)
    x.owner.GetFaces = lambda: call('faces', (), list(x.faces))
    for face in x.faces:
        face.GetBody = lambda face=face: call('face_body', (face,), x.body)
    return x


def bind(x, **changes):
    args = dict(original_body=x.original, original_canonical=x.original_canonical,
                original_pid=b'original-body', owner_feature=x.owner,
                owner_canonical=x.owner_canonical, identity=x.identity,
                persistent_id=x.persistent_id, resolve_body=x.resolve_body,
                census=x.census, bridge=NativeBodyBridge(x.query, x.is_same))
    args.update(changes)
    return bind_current_body(**args)


@pytest.mark.parametrize('same_canonical', [False, True])
def test_exact_original_pid_native_equality_and_all_owner_faces_bind_current_handle(body_binding, same_canonical):
    x = body_binding
    if same_canonical:
        x.body.canonical = x.original_canonical
    assert bind(x) is x.body
    names = [name for name, _ in x.calls]
    assert names.count('same') == 2
    assert names.count('faces') == 2
    assert names.count('face_body') == 12
    assert names.count('census') >= 5
    assert names.count('pid') >= 5 and names.count('resolve') >= 4
    assert all(args == (x.original, x.body) for name, args in x.calls if name == 'same')


@pytest.mark.parametrize('value', [False, True, 0, 2, 1.0, '1', None])
def test_native_same_requires_exact_int_one(body_binding, value):
    x = body_binding
    x.is_same = lambda *args: value
    with pytest.raises(ValueError, match='exact int1'):
        bind(x)
    assert not any(name == 'faces' for name, _ in x.calls)


@pytest.mark.parametrize('value', [b'', b'foreign', bytearray(b'original-body'), 'original-body', None])
def test_current_pid_requires_original_nonempty_bytes(body_binding, value):
    x = body_binding
    x.persistent_id = lambda obj: value
    with pytest.raises(ValueError, match='exact original nonempty bytes PID'):
        bind(x)
    assert not any(name == 'same' for name, _ in x.calls)


@pytest.mark.parametrize('value', [b'', bytearray(b'original-body'), None])
def test_original_pid_rejected_before_native_reads(body_binding, value):
    x = body_binding
    with pytest.raises(ValueError, match='Original retained body/PID/feature'):
        bind(x, original_pid=value)
    assert x.calls == []


@pytest.mark.parametrize('fault', ['query_body', 'resolve', 'query_face', 'owner_body',
                                 'foreign_face_query', 'original_handle', 'owner_handle'])
def test_foreign_native_handles_never_adopted(body_binding, fault):
    x = body_binding
    foreign = NS(canonical=object())
    if fault == 'query_body':
        x.query = lambda obj, interface: foreign if obj is x.body else obj
    elif fault == 'resolve':
        x.resolve_body = lambda pid: foreign
    elif fault == 'query_face':
        x.query = lambda obj, interface: None if interface == 'IFace2' else obj
    elif fault == 'foreign_face_query':
        foreign.GetBody = lambda: x.body
        x.query = lambda obj, interface: foreign if obj is x.faces[-1] else obj
    elif fault == 'owner_body':
        x.faces[-1].GetBody = lambda: foreign
    elif fault == 'original_handle':
        x.original.canonical = object()
    else:
        x.owner.canonical = object()
    with pytest.raises(ValueError):
        bind(x)


@pytest.mark.parametrize('fault', ['zero_bodies', 'duplicate_body', 'foreign_second_boundary',
                                 'five_faces', 'seven_faces', 'duplicate_face'])
def test_complete_single_body_and_six_distinct_owner_faces_required(body_binding, fault):
    x = body_binding
    if fault == 'zero_bodies':
        x.bodies = []
    elif fault == 'duplicate_body':
        x.bodies *= 2
    elif fault == 'five_faces':
        x.faces.pop()
    elif fault == 'seven_faces':
        x.faces.append(x.faces[0])
    elif fault == 'duplicate_face':
        x.faces[-1] = x.faces[0]
    else:
        def hook(name, args, result):
            if name == 'census' and sum(n == 'census' for n, _ in x.calls) == 3:
                return [NS(canonical=object())]
        x.hook = hook
    with pytest.raises(ValueError):
        bind(x)


@pytest.mark.parametrize('change', ['original', 'owner', 'body_census', 'pid'])
def test_last_owner_face_callback_changes_are_detected(body_binding, change):
    x = body_binding
    def hook(name, args, result):
        if name == 'face_body' and args[0] is x.faces[-1]:
            if change == 'original':
                x.original.canonical = object()
            elif change == 'owner':
                x.owner.canonical = object()
            elif change == 'body_census':
                x.bodies = []
            else:
                x.pid = b'changed'
    x.hook = hook
    with pytest.raises(ValueError):
        bind(x)


@pytest.mark.parametrize('change', ['original', 'owner', 'body_census', 'pid'])
def test_final_pid_resolution_callback_cannot_change_binding_after_last_boundary(body_binding, change):
    x = body_binding
    def hook(name, args, result):
        if name == 'resolve' and sum(n == 'resolve' for n, _ in x.calls) == 4:
            if change == 'original':
                x.original.canonical = object()
            elif change == 'owner':
                x.owner.canonical = object()
            elif change == 'body_census':
                x.bodies = []
            else:
                x.pid = b'changed'
    x.hook = hook
    with pytest.raises(ValueError):
        bind(x)


@pytest.mark.parametrize('where', ['identity', 'census', 'query', 'pid', 'resolve',
                                 'same', 'faces', 'face_body'])
def test_native_exception_propagates_once_without_retry(body_binding, where):
    x = body_binding
    error = RuntimeError('returned native exception')
    def hook(name, args, result):
        if name == where:
            raise error
    x.hook = hook
    with pytest.raises(RuntimeError) as caught:
        bind(x)
    assert caught.value is error
    assert sum(name == where for name, _ in x.calls) == 1
