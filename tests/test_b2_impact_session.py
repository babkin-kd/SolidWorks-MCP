"""Actual two-model census/SQLite fixtures; artificial target native handles."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest
from solidworks_mcp.jobs import ExecutionFailure
from test_b2_impact_target import target, fixture, leaf, extrusion_proof, proof, case, domain

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b2_impact_session import B2ImpactSession, same_refused_session, equation_file_facts
    from verifier_b2_impact_fixture import FixtureGate
finally:
    sys.path.remove(scripts)


@pytest.fixture
def observer(target):
    x = target
    neighbor = next(entry for entry in x.entries if entry.document_id == 'neighbor')
    before = x.c.adapter.rectangle_construction_snapshot(neighbor.model)
    x.session_collector = B2ImpactSession(x.collector, neighbor, before)
    x.helper.add_unused_equation()
    return x


def test_actual_complete_session_capture_reads_original_neighbor_twice_and_preserves_all_data(observer):
    x = observer
    writes = list(x.write_calls)
    first = x.session_collector.capture()
    second = x.session_collector.capture()
    assert same_refused_session(first, second) is True
    assert set(first['semantic']) == {'documents', 'windows', 'files', 'application',
                                    'active_document_id', 'reference_graph'}
    assert len(first['semantic']['documents']) == 2
    assert first['target']['deletion_context']['native_context']['equations']['enumerated_count'] == 1
    assert all(first[key] is False for key in ('accepted', 'native_b2_accepted',
        'cleanup_authorized', 'full_refusal_context_available'))
    assert x.write_calls == writes
    second['target']['geometry']['foreign'] = True
    with pytest.raises(FixtureGate): same_refused_session(first, second)


@pytest.mark.parametrize('fault', ['neighbor_data', 'neighbor_configuration', 'window',
    'application', 'model', 'target_failure', 'neighbor_midread'])
def test_changed_neighbor_session_or_current_target_is_not_hidden(observer, fault):
    x = observer
    a = x.c.adapter
    neighbor = x.session_collector.neighbor
    if fault == 'neighbor_data': x.corrupt_neighbor = True
    elif fault == 'neighbor_configuration':
        x.complete_observations['neighbor']['active_configuration'] = 'Чужая'
    elif fault == 'window': a.native_close_windows = lambda: []
    elif fault == 'application':
        original = x.collector.capture
        def read(*args, **kwargs):
            actual = original(*args, **kwargs)
            x.application['current_directory'] = 'C:/changed/'
            return actual
        x.collector.capture = read
    elif fault == 'model': neighbor.model.identity = object()
    elif fault == 'target_failure': x.helper.pending_native_step = 'unreturned'
    elif fault == 'neighbor_midread':
        original = a.rectangle_construction_snapshot
        calls = []
        def read(model):
            result = original(model)
            if model is neighbor.model:
                calls.append(True)
                if len(calls) == 2: result['clone_state']['material'] = ['changed', '']
            return result
        a.rectangle_construction_snapshot = read
    writes = list(x.write_calls)
    with pytest.raises((FixtureGate, ExecutionFailure, ValueError)):
        x.session_collector.capture()
    assert x.write_calls == writes


def test_session_comparator_rejects_partial_or_authority_claim(observer):
    value = observer.session_collector.capture()
    for bad in ({'scope': value['scope']}, {**value, 'accepted': True}):
        with pytest.raises(FixtureGate): same_refused_session(value, bad)


def test_actual_linked_equation_file_is_fingerprinted_and_never_inferred_empty(target, tmp_path):
    x = target
    path = (tmp_path / 'owned-equations.txt').resolve()
    path.write_text('"Контрольная независимая величина" = 3', encoding='utf8')
    binding = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    x.helper.link_equation_file(path, expected_sha256=binding['sha256'])
    neighbor = next(entry for entry in x.entries if entry.document_id == 'neighbor')
    before = x.c.adapter.rectangle_construction_snapshot(neighbor.model)
    omitted = B2ImpactSession(x.collector, neighbor, before)
    with pytest.raises(FixtureGate, match='equation link'): omitted.capture()
    collector = B2ImpactSession(x.collector, neighbor, before, equation_file=binding)
    value = collector.capture()
    assert value['equation_file'] == equation_file_facts(binding)
    assert same_refused_session(value, collector.capture()) is True
    path.write_text('"Контрольная независимая величина" = 4', encoding='utf8')
    with pytest.raises(FixtureGate, match='changed'): collector.capture()


def test_bound_equation_file_must_match_observed_link_and_original_bytes(observer, tmp_path):
    path = (tmp_path / 'private.txt').resolve()
    path.write_text('Owned fixture', encoding='utf8')
    binding = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    x = observer
    x.session_collector.equation_file = binding
    with pytest.raises(FixtureGate, match='equation link'): x.session_collector.capture()
    for bad in ({**binding, 'sha256': '0' * 64}, {**binding, 'path': path.name}):
        with pytest.raises(FixtureGate): equation_file_facts(bad)
