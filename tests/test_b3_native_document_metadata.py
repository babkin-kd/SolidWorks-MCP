"""API-shaped raw getters; these are pure tests, never native acceptance."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verifier_b3_native_document_metadata import (
    RetainedConfiguration, RetainedDocument, capture_native_document_metadata)


@pytest.fixture
def world():
    x = NS(sequence=0, calls=[], safe_calls=[], stamp=7, dirty=True, title='Контрольная деталь', path='', kind=1)
    cfgs = [NS(Name=name, canonical=object()) for name in ('Основная', 'Вариант')]
    x.cfgs, x.active, x.roster = cfgs, cfgs[0], [c.Name for c in cfgs]
    def getter(name, value):
        def get(*args):
            x.calls.append(name)
            return value(*args)
        return get
    x.model = NS(canonical=object(),
        GetUpdateStamp=getter('stamp', lambda: x.stamp),
        GetConfigurationNames=getter('roster', lambda: x.roster),
        GetConfigurationByName=getter('named', lambda name: next(c for c in x.cfgs if c.Name == name)),
        GetActiveConfiguration=getter('active', lambda: x.active),
        GetTitle=getter('title', lambda: x.title), GetPathName=getter('path', lambda: x.path),
        GetType=getter('kind', lambda: x.kind), GetSaveFlag=getter('dirty', lambda: x.dirty))
    x.binding = RetainedDocument('original-doc', x.model, x.model.canonical,
        tuple(RetainedConfiguration(c.Name, c, c.canonical) for c in cfgs))
    anchors = [x.model.canonical, *(c.canonical for c in cfgs)]
    x.ordinal = lambda token: next(i+1 for i, original in enumerate(anchors) if token == original)
    x.safe = lambda context: x.safe_calls.append(context)
    x.identity = lambda obj: obj.canonical
    return x


def run(x, **overrides):
    args = dict(document_id='original-doc', configuration='Вариант', binding=x.binding,
        wrap=lambda raw, interface: raw, identity=x.identity, ordinal=x.ordinal,
        watch=NS(poll=lambda: x.sequence), assert_safe=x.safe)
    args.update(overrides)
    return capture_native_document_metadata(**args)


@pytest.mark.parametrize('configuration', ['Основная', 'Вариант'])
def test_active_and_inactive_metadata_from_raw_retained_handles(world, configuration):
    x = world
    result = run(x, configuration=configuration)
    assert result['metadata'] == dict(title=x.title, path='', document_type='part', needs_save=True,
        configurations=['Основная', 'Вариант'], active_configuration='Основная', update_stamp=7,
        configuration=configuration, configuration_is_active=configuration == 'Основная',
        revision_scope='update_stamp_and_document_metadata')
    assert result['native_identity'] == 1
    assert result['configuration_identity'] == (2 if configuration == 'Основная' else 3)
    receipt = result['native_receipt']
    assert receipt['before'] == receipt['after']
    assert receipt['accepted'] is receipt['native_acceptance'] is receipt['cleanup_authorized'] is False
    assert len(x.safe_calls) == 2 and x.active is x.cfgs[0]


@pytest.mark.parametrize('fault', ['model', 'config', 'active', 'roster', 'dirty', 'stamp', 'kind', 'title', 'path'])
def test_replacement_incomplete_or_untyped_native_scope_fails(world, fault):
    x = world
    if fault == 'model': x.model.canonical = object()
    elif fault == 'config': x.cfgs[1] = NS(Name='Вариант', canonical=object())
    elif fault == 'active': x.active = NS(Name='Основная', canonical=object())
    elif fault == 'roster': x.roster = ['Основная']
    elif fault == 'dirty': x.dirty = 1
    elif fault == 'stamp': x.stamp = True
    elif fault == 'kind': x.kind = True
    elif fault == 'title': x.title = None
    else: x.path = None
    with pytest.raises(ValueError): run(x)


@pytest.mark.parametrize('fault', ['ordinal_event', 'ordinal_config', 'ordinal_dirty', 'getter_aba', 'closing_gate_aba'])
def test_changes_and_aba_inside_complete_observer_envelope_fail(world, fault):
    x = world
    if fault.startswith('ordinal'):
        original = x.ordinal
        def ordinal(token):
            value = original(token)
            if fault == 'ordinal_event': x.sequence += 1
            elif fault == 'ordinal_config': x.cfgs[1] = NS(Name='Вариант', canonical=object())
            else: x.dirty = False
            return value
        x.ordinal = ordinal
    elif fault == 'getter_aba':
        original = x.model.GetTitle
        def title():
            x.sequence += 1
            return original()
        x.model.GetTitle = title
    else:
        def safe(context):
            x.safe_calls.append(context)
            if len(x.safe_calls) == 2: x.sequence += 1
        x.safe = safe
    with pytest.raises(ValueError): run(x)


def test_owner_gate_precedes_getters_and_native_canonical_comparisons(world):
    x = world
    def forbidden(*args): raise AssertionError('native access before ownership admission')
    def reject(context): raise ValueError('not owned')
    with pytest.raises(ValueError, match='not owned'):
        run(x, identity=forbidden, assert_safe=reject)
    assert x.calls == []


@pytest.mark.parametrize('overrides', [dict(document_id='foreign'), dict(configuration='missing'),
    dict(configuration=''), dict(ordinal=lambda token: True), dict(watch=NS(poll=lambda: True))])
def test_invalid_request_or_observation_proof_rejected(world, overrides):
    with pytest.raises(ValueError): run(world, **overrides)
