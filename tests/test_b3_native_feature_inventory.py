"""Artificial API-shaped tree/PID getters; no SolidWorks connection."""
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from test_b3_native_document_metadata import world

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verifier_b3_native_feature_inventory import RetainedFeature, capture_native_feature_inventory


@pytest.fixture
def tree(world):
    x = world
    x.features = []
    for i, (name, kind) in enumerate((('Плоскость', 'RefPlane'), ('Основание', 'Boss'), ('Эскиз основания', 'ProfileFeature'))):
        f = NS(canonical=object(), Name=name, kind=kind, native_id=i+1, owner=None,
               pid=b'' if i == 0 else bytes([i]), next=None, first_sub=None, next_sub=None,
               suppression=[False], error=(0, False))
        f.GetID = lambda f=f: f.native_id
        f.GetTypeName2 = lambda f=f: f.kind
        f.GetOwnerFeature = lambda f=f: f.owner
        f.GetErrorCode2 = lambda f=f: f.error
        f.IsSuppressed2 = lambda scope, configs, f=f: f.suppression
        f.GetNextFeature = lambda f=f: f.next
        f.GetFirstSubFeature = lambda f=f: f.first_sub
        f.GetNextSubFeature = lambda f=f: f.next_sub
        x.features.append(f)
    a, b, c = x.features
    a.next = b; b.first_sub = c; c.owner = b
    x.model.FirstFeature = lambda: a
    x.originals = tuple(RetainedFeature(f, f.canonical, f.pid,
                        None if f.owner is None else f.owner.canonical) for f in x.features)
    x.pid_state = 0; x.resolved_override = None
    x.model.Extension = NS(GetPersistReference3=lambda f: f.pid,
        GetObjectByPersistReference3=lambda pid: (
            x.resolved_override if x.resolved_override is not None else next(f for f in x.features if f.pid == pid), x.pid_state))
    anchors = [x.model.canonical, *(c.canonical for c in x.cfgs), *(f.canonical for f in x.features)]
    x.ordinal = lambda token: next(i+1 for i, original in enumerate(anchors) if token == original)
    return x


def run(x, **overrides):
    args = dict(context=dict(document_id='original-doc', configuration='Основная'), document=x.binding,
        originals=x.originals, wrap=lambda raw, interface: raw, identity=x.identity,
        ordinal=x.ordinal, persistent_variant=lambda pid: pid,
        watch=NS(poll=lambda: x.sequence), assert_safe=x.safe)
    args.update(overrides)
    return capture_native_feature_inventory(**args)


def test_complete_original_tree_including_absorbed_and_unsupported_rows(tree):
    x = tree; r = run(x)
    assert [row['summary']['name'] for row in r['rows']] == [f.Name for f in x.features]
    assert [row['reference_supported'] for row in r['rows']] == [False, True, True]
    assert [row['summary']['owner_native_id'] for row in r['rows']] == [None, None, 2]
    assert r['before'] == r['after']
    assert r['accepted'] is r['native_acceptance'] is r['cleanup_authorized'] is False
    assert r['rows'][1]['native_receipt']['resolution_state'] == 0
    assert r['rows'][0]['native_receipt']['resolution_state'] is None


@pytest.mark.parametrize('fault', ['extra', 'missing', 'replacement', 'pid', 'resolution', 'state', 'owner',
    'id_collision', 'untyped_id', 'error', 'suppression', 'inactive', 'metadata'])
def test_native_scope_or_reference_difference_fails(tree, fault):
    x = tree; a, b, c = x.features
    if fault == 'extra':
        foreign = NS(**vars(c)); foreign.canonical = object(); foreign.native_id = 9
        foreign.GetID = lambda: 9
        c.next_sub = foreign
    elif fault == 'missing': b.first_sub = None
    elif fault == 'replacement': c.canonical = object()
    elif fault == 'pid': c.pid = b'other'
    elif fault == 'resolution': x.resolved_override = a
    elif fault == 'state': x.pid_state = 4
    elif fault == 'owner': c.owner = a
    elif fault == 'id_collision': c.native_id = 2
    elif fault == 'untyped_id': c.native_id = True
    elif fault == 'error': b.error = (True, False)
    elif fault == 'suppression': b.suppression = [0]
    elif fault == 'inactive': x.active = x.cfgs[1]
    else: x.kind = 2
    with pytest.raises(ValueError): run(x)


@pytest.mark.parametrize('fault', ['pid', 'name', 'owner', 'event_aba', 'dirty'])
def test_closing_checks_cover_mutation_inside_ordinal_callback(tree, fault):
    x = tree; original = x.ordinal
    def ordinal(token):
        value = original(token)
        if token == x.features[1].canonical:
            if fault == 'pid': x.features[2].pid = b'changed'
            elif fault == 'name': x.features[1].Name = 'Другое имя'
            elif fault == 'owner': x.features[2].owner = x.features[0]
            elif fault == 'event_aba': x.sequence += 1
            else: x.dirty = False
        return value
    with pytest.raises(ValueError): run(x, ordinal=ordinal)


def test_birth_owner_admission_precedes_all_native_comparisons(tree):
    x = tree
    def forbidden(*args): raise AssertionError('native access before admission')
    def reject(context): raise ValueError('not owned')
    with pytest.raises(ValueError, match='not owned'):
        run(x, identity=forbidden, assert_safe=reject)
    assert x.calls == []


def test_original_canonical_duplicates_refused(tree):
    x = tree
    refs = (x.originals[0], replace(x.originals[1], canonical=x.originals[0].canonical), x.originals[2])
    with pytest.raises(ValueError): run(x, originals=refs)
