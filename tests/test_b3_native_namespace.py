"""Actual document/geometry registrations, artificial native window getters."""
from copy import copy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.geometry import GeometryCatalog
from test_geometry_v2 import GeometryAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verifier_b3_native_namespace import capture_native_namespace


@pytest.fixture
def world():
    a = GeometryAdapter(); a.body(faces=2)
    docs = DocumentCatalog(a); listed = docs.list()['documents']
    geometry = GeometryCatalog(docs)
    context = dict(document_id=listed[0]['document_id'], configuration='Основная',
                   expected_observation_revision=listed[0]['observation_revision'])
    geometry.list(**context)
    x = NS(a=a, docs=docs, events=[0, 0], calls=[], safe_calls=0, hook=None,
           windows=[(model, dict(hwnd=101+i, title='Одинаковое имя')) for i, model in enumerate(a.models)])
    def windows():
        x.calls.append('windows')
        if x.hook: x.hook(len(x.calls))
        return x.windows[:]
    a.native_close_windows = windows
    def safe(): x.safe_calls += 1
    x.safe = safe
    yield x
    docs.close()


def run(x, **overrides):
    args = dict(expected_window_hwnds=(101, 102), watch_poll=lambda: x.events[:], assert_safe=x.safe)
    args.update(overrides)
    return capture_native_namespace(x.docs, **args)


def test_uuid_pid_export_and_native_hwnd_association_ignore_titles_and_paths(world):
    x = world; r = run(x)
    assert r['document_bindings'] == [dict(document_id=e.document_id, hwnd=101+i) for i, e in enumerate(x.docs._entries)]
    assert len(x.calls) == 2 and x.safe_calls >= 2
    assert r['registered_references'][0]['rows'][0]['family'] == 'part_geometry'
    assert r['registered_references'][1]['rows'] == []
    assert r['accepted'] is r['native_acceptance'] is r['cleanup_authorized'] is False
    assert r['original_birth_ownership_verified'] is r['current_object_membership_verified'] is False


@pytest.mark.parametrize('fault', ['foreign', 'missing_model', 'duplicate_model', 'window_missing',
    'extra_window', 'other_hwnd', 'duplicate_hwnd', 'window_model_replaced', 'entry_replaced',
    'entry_reordered', 'window_swap', 'watch_aba', 'ref_changed'])
def test_census_identity_namespace_or_event_change_fails(world, fault):
    x = world
    if fault == 'foreign': x.a.models.append(NS(identity=object(), state={}))
    elif fault == 'missing_model': x.a.models.pop()
    elif fault == 'duplicate_model': x.a.models[1] = x.a.models[0]
    elif fault == 'window_missing': x.windows.pop()
    elif fault == 'extra_window': x.windows.append((x.a.models[0], dict(hwnd=103, title='x')))
    elif fault == 'other_hwnd': x.windows[0][1]['hwnd'] = 103
    elif fault == 'duplicate_hwnd': x.windows[1][1]['hwnd'] = 101
    elif fault == 'window_model_replaced': x.windows[0] = (NS(identity=object()), x.windows[0][1])
    else:
        def hook(n):
            if n != 2: return
            if fault == 'entry_replaced': x.docs._entries[0] = copy(x.docs._entries[0])
            elif fault == 'entry_reordered': x.docs._entries.reverse()
            elif fault == 'window_swap':
                first, second = x.windows
                x.windows[:] = [(first[0], second[1]), (second[0], first[1])]
            elif fault == 'watch_aba': x.events[0] += 1
            else:
                ref = next(iter(x.docs._entries[0].geometry['references'].values()))
                ref.persistent_id = b'changed'
        x.hook = hook
    with pytest.raises(ValueError): run(x)


def test_owner_admission_precedes_all_catalog_or_native_access(world):
    x = world
    def forbidden(*args): raise AssertionError('native call before admission')
    def reject(): raise ValueError('not owned')
    x.a.identity = forbidden
    x.a.documents = forbidden
    with pytest.raises(ValueError, match='not owned'): run(x, assert_safe=reject)
    assert x.calls == []


@pytest.mark.parametrize('overrides', [dict(expected_window_hwnds=(True, 102)),
    dict(expected_window_hwnds=(101, 101)), dict(watch_poll=lambda: [True, 0]),
    dict(watch_poll=lambda: [0]), dict(expected_window_hwnds=())])
def test_incomplete_or_untyped_original_window_watcher_admission_fails(world, overrides):
    with pytest.raises(ValueError): run(world, **overrides)


def test_final_owner_admission_is_inside_event_envelope(world):
    x = world
    def safe():
        x.safe_calls += 1
        if x.safe_calls == 10: x.events[1] += 1
    # Initial + two per export twice for two entries + final = ten.
    with pytest.raises(ValueError): run(x, assert_safe=safe)
