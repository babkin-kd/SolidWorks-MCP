"""Artificial geometry/density/selection, real SQLite+job_get; never native CAD."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from test_b3_part_geometry import CONTEXT, Reader as GeometryReader, run as geometry_run
from test_b3_reader import Protocol, reader as durable_reader
from solidworks_mcp.jobs import JobStore

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_part_mass as helper
finally:
    sys.path.remove(scripts)


def artificial_result(tool, args):
    body_id = args.get('body_id')
    count = 2 if body_id is None else 1
    common = dict(document_id=args['document_id'], configuration=args['configuration'],
                  body_id=body_id, body_count=count, coordinate_frame='model',
                  includes_hidden_bodies=True, model_geometry_modified=False,
                  revision_scope=helper.SCOPE)
    if tool == 'measurement_prepare_mass':
        return dict(**common, revision='rev_' + ('all' if body_id is None else body_id),
                    ui_effect='temporary_selection_with_durable_application_guard')
    return dict(**common, observation_revision=args['expected_observation_revision'], verified=True,
        measurement_revision=args['expected_revision'], length_unit='mm', area_unit='mm2',
        volume_unit='mm3', mass_unit='kg', density_source='solidworks_effective',
        mass_properties=dict(volume_mm3=count * 1000., surface_area_mm2=count * 700.,
            mass_kg=count * 1000. * 7850. / 1e9, density_kg_m3=7850.,
            center_of_mass_mm=[30. if count == 2 else 50., 5., 2.5]),
        execution_guard=dict(scope='application_model_mutation_guard_v1', acquired=True,
            released=True, selection_preserved=True, original_command_in_progress=False,
            model_guards=[dict(original_state=0, locked_state=2, released_state=0)]))


def artificial_scope(context, body_id):
    return dict(context=deepcopy(context), body_id=body_id,
        body_ids=['body_0', 'body_1'] if body_id is None else [body_id],
        excluded_surface_body_ids=['body_2'], hidden_solid_body_ids=['body_1'],
        density_source='independent_native_effective', effective_density_kg_m3=7850.,
        solid_densities_kg_m3=dict(body_0=7850., body_1=7850.),
        overrides={key: dict(mass=False, center_of_mass=False)
                   for key in ('document', 'body_0', 'body_1')},
        selection=[dict(object_id='body_0', native_identity=1,
                        persistent_id='aa00', mark=7)],
        native_receipt=dict(artificial=True, actual_uniform_density_no_overrides=True))


class MassReader:
    def __init__(self, corrupt=None, unknown_at=None):
        self.calls, self.corrupt, self.unknown_at = [], corrupt, unknown_at

    async def read(self, tool, args):
        self.calls.append((tool, deepcopy(args)))
        if len(self.calls) == self.unknown_at:
            return dict(status='unknown', error=dict(code='restore_unconfirmed'), result=None)
        value = artificial_result(tool, args)
        if self.corrupt: self.corrupt(tool, value)
        return dict(status='succeeded', error=None, result=value)


@pytest.fixture
def evidence():
    return geometry_run(GeometryReader())[0]


def run(reader, evidence, *, scope_corrupt=None, changed=None, **overrides):
    captures, scopes = [], []
    def full():
        captures.append(True)
        return dict(artificial_full_native=dict(part_brep='complete', dirty_neighbor='complete',
            selection=[['native-body-0', 7]], visibility='hidden-second', session='complete'),
            changed=bool(changed == len(captures)))
    def scope(context, body_id):
        value = artificial_scope(context, body_id)
        scopes.append((deepcopy(context), body_id))
        if scope_corrupt: scope_corrupt(value, len(scopes))
        return value
    args = dict(context=CONTEXT, geometry_evidence=evidence,
                capture_full=full, capture_mass_scope=scope)
    args.update(overrides)
    result = asyncio.run(helper.part_mass_case(reader, **args))
    return result, captures, scopes


def test_two_finite_preparation_guarded_chains_over_artificial_native_producers(evidence):
    reader = MassReader()
    value, captures, scopes = run(reader, evidence)
    assert [tool for tool, _ in reader.calls] == ['measurement_prepare_mass', 'measurement_get_mass'] * 2
    assert [args['body_id'] for _, args in reader.calls] == [None, None, 'body_1', 'body_1']
    assert len({args['request_id'] for _, args in reader.calls}) == 4
    assert reader.calls[1][1]['expected_revision'] == 'rev_all'
    assert reader.calls[3][1]['expected_revision'] == 'rev_body_1'
    assert len(captures) == len(scopes) == 4
    assert value['accepted'] is value['native_acceptance'] is value['cleanup_authorized'] is False
    assert value['before'] == value['after']
    assert len(value['rows']) == 4 and len(value['chains']) == 2
    assert [row['oracle']['volume_mm3'] for row in value['chains']] == [2000., 1000.]
    assert [row['oracle']['center_of_mass_mm'] for row in value['chains']] == [[30., 5., 2.5], [50., 5., 2.5]]


@pytest.mark.parametrize('fault', ['short_center', 'wrong_density_consistent_mass', 'wrong_context',
    'wrong_body', 'wrong_revision', 'wrong_volume', 'wrong_area', 'wrong_center', 'bool_count',
    'bool_center', 'wrong_units', 'unreleased', 'selection_lost', 'unverified', 'hidden_excluded',
    'nonfinite', 'bool_mass', 'bad_prepare', 'prepare_body', 'wrong_guard_scope', 'bool_lock'])
def test_wrong_result_stops_without_repeated_dispatch(evidence, fault):
    def corrupt(tool, value):
        if tool == 'measurement_prepare_mass':
            if fault == 'bad_prepare': value['includes_hidden_bodies'] = 1
            if fault == 'prepare_body': value['body_id'] = 'body_2'
            return
        properties = value['mass_properties']
        if fault == 'short_center': properties['center_of_mass_mm'] = [30.]
        elif fault == 'wrong_density_consistent_mass':
            properties['density_kg_m3'] *= 2
            properties['mass_kg'] *= 2
        elif fault == 'wrong_context': value['observation_revision'] = 'obsolete'
        elif fault == 'wrong_body': value['body_id'] = 'body_2'
        elif fault == 'wrong_revision': value['measurement_revision'] = 'rev_wrong'
        elif fault == 'wrong_volume': properties['volume_mm3'] += 150.
        elif fault == 'wrong_area': properties['surface_area_mm2'] += 150.
        elif fault == 'wrong_center': properties['center_of_mass_mm'][2] += 1.
        elif fault == 'bool_count': value['body_count'] = True
        elif fault == 'bool_center': properties['center_of_mass_mm'][0] = True
        elif fault == 'wrong_units': value['volume_unit'] = 'm3'
        elif fault == 'unreleased': value['execution_guard']['released'] = False
        elif fault == 'selection_lost': value['execution_guard']['selection_preserved'] = False
        elif fault == 'unverified': value['verified'] = 1
        elif fault == 'hidden_excluded': value['includes_hidden_bodies'] = 1
        elif fault == 'nonfinite': properties['mass_kg'] = float('nan')
        elif fault == 'bool_mass': properties['mass_kg'] = True
        elif fault == 'wrong_guard_scope': value['execution_guard']['scope'] = 'other'
        elif fault == 'bool_lock': value['execution_guard']['model_guards'][0]['released_state'] = False
    reader = MassReader(corrupt)
    with pytest.raises(ValueError): run(reader, evidence)
    assert len(reader.calls) == (1 if fault in ('bad_prepare', 'prepare_body') else 2)


@pytest.mark.parametrize('fault', ['density_missing', 'density_from_result', 'nonuniform',
    'overrides', 'bool_override', 'body', 'surface', 'no_hidden', 'context', 'empty_selection',
    'wrong_selected_body', 'bool_mark', 'receipt', 'uppercase_pid', 'odd_pid', 'spaced_pid',
    'empty_pid', 'bool_identity', 'zero_identity', 'name_identity'])
def test_missing_or_wrong_independent_mass_scope_prevents_dispatch(evidence, fault):
    def corrupt(value, _):
        if fault == 'density_missing': value.pop('effective_density_kg_m3')
        elif fault == 'density_from_result': value['density_source'] = 'solidworks_effective'
        elif fault == 'nonuniform': value['solid_densities_kg_m3']['body_1'] = 1000.
        elif fault == 'overrides': value['overrides']['document']['mass'] = True
        elif fault == 'bool_override': value['overrides']['body_0']['center_of_mass'] = 0
        elif fault == 'body': value['body_ids'] = ['body_0']
        elif fault == 'surface': value['excluded_surface_body_ids'] = []
        elif fault == 'no_hidden': value['hidden_solid_body_ids'] = []
        elif fault == 'context': value['context']['document_id'] = 'other'
        elif fault == 'empty_selection': value['selection'] = []
        elif fault == 'wrong_selected_body': value['selection'][0]['object_id'] = 'body_1'
        elif fault == 'bool_mark': value['selection'][0]['mark'] = True
        elif fault == 'receipt': value['native_receipt'] = {}
        elif fault == 'uppercase_pid': value['selection'][0]['persistent_id'] = 'AA00'
        elif fault == 'odd_pid': value['selection'][0]['persistent_id'] = 'aa0'
        elif fault == 'spaced_pid': value['selection'][0]['persistent_id'] = 'aa 00'
        elif fault == 'empty_pid': value['selection'][0]['persistent_id'] = ''
        elif fault == 'bool_identity': value['selection'][0]['native_identity'] = True
        elif fault == 'zero_identity': value['selection'][0]['native_identity'] = 0
        elif fault == 'name_identity': value['selection'][0]['native_identity'] = 'Тело 0'
    reader = MassReader()
    with pytest.raises(ValueError): run(reader, evidence, scope_corrupt=corrupt)
    assert reader.calls == []


@pytest.mark.parametrize('at', [1, 2, 3, 4])
def test_unknown_receipt_never_runs_next_or_repeated_mass(evidence, at):
    reader = MassReader(unknown_at=at)
    with pytest.raises(ValueError, match='unknown'): run(reader, evidence)
    assert len(reader.calls) == at
    assert len({args['request_id'] for _, args in reader.calls}) == at


@pytest.mark.parametrize('fault', ['old_revision', 'wrong_document', 'incomplete_refs', 'no_proof',
                                   'changed_after', 'old_acceptance'])
def test_stale_or_incomplete_i02_never_dispatches(evidence, fault):
    if fault == 'old_revision': evidence['rows'][0]['journal']['result']['observation_revision'] = 'old'
    elif fault == 'wrong_document': evidence['rows'][0]['journal']['result']['document_id'] = 'other'
    elif fault == 'incomplete_refs': evidence['native_references'].pop()
    elif fault == 'no_proof': evidence['native_references'][0]['receipt'] = {}
    elif fault == 'changed_after': evidence['after']['change'] = True
    elif fault == 'old_acceptance': evidence['accepted'] = True
    reader = MassReader()
    with pytest.raises(ValueError): run(reader, evidence)
    assert reader.calls == []


@pytest.mark.parametrize('changed', [2, 3, 4])
def test_full_native_preservation_or_between_chain_drift_stops(evidence, changed):
    reader = MassReader()
    with pytest.raises(ValueError, match='native'): run(reader, evidence, changed=changed)
    assert len(reader.calls) == (4 if changed == 4 else 2)


@pytest.mark.parametrize('field', ['mark', 'persistent_id', 'native_identity'])
def test_exact_selection_drift_stops_before_second_chain(evidence, field):
    def corrupt(value, index):
        if index == 2:
            value['selection'][0][field] = 'aa01' if field == 'persistent_id' else 8
    reader = MassReader()
    with pytest.raises(ValueError, match='selection'): run(reader, evidence, scope_corrupt=corrupt)
    assert len(reader.calls) == 2


@pytest.mark.parametrize('overrides', [dict(capture_full=None), dict(capture_mass_scope=None), dict(context={})])
def test_required_callback_context_before_dispatch(evidence, overrides):
    reader = MassReader()
    with pytest.raises(ValueError): run(reader, evidence, **overrides)
    assert reader.calls == []


class MassProtocol(Protocol):
    """Only artificial domain output; inherited real JobStore/public job_get."""
    def finish(self, operation_id):
        job = self.store.get(operation_id)
        args = job['payload']['arguments']
        mass = job['operation'] == 'measurement.mass'
        tool = 'measurement_get_mass' if mass else 'measurement_prepare_mass'
        if mass:
            self.store.prepare_mutation(operation_id, connection_epoch='artificial-mass',
                document_id=args['document_id'], configuration=args['configuration'],
                expected_revision=args['expected_revision'],
                before_state=dict(artificial_domain=True), effect_scope='application')
            self.store.verify_mutation(operation_id, outcome='committed', evidence=dict(artificial=True))
        self.store.finish(operation_id, 'succeeded', result=artificial_result(tool, args))
        # The shared single-operation protocol's polling counter starts anew
        # for each of this route's four separate jobs.
        self.polls = 0


@pytest.mark.parametrize('late', [False, True])
def test_actual_reader_sqlite_job_get_mass_checkpoint_integration(tmp_path, evidence, late):
    path = tmp_path / 'mass.sqlite'
    store = JobStore(path)
    try:
        client = MassProtocol(store, late=late)
        reader, snapshots, _, _ = durable_reader(client, path)
        value, _, _ = run(reader, evidence)
        assert len(client.dispatches) == len(store.list()['items']) == 4
        rows = value['rows']
        assert [row['journal']['payload']['mutates'] for row in rows] == [False, True, False, True]
        for row in rows[1::2]:
            assert row['journal']['mutation']['phase'] == 'committed'
            assert row['journal']['mutation']['before_state']['_mutation_effect_scope'] == 'application'
            assert row['journal']['mutation']['expected_revision'] == row['arguments']['expected_revision']
        assert len([tool for tool, _ in client.calls if tool == 'job_get']) == (12 if late else 4)
        assert [tool for tool, _ in client.calls if tool != 'job_get'] == [
            'measurement_prepare_mass', 'measurement_get_mass'] * 2
        assert snapshots[-1][-1]['state'] == 'journal_bound' and not client.retained
        assert value['native_acceptance'] is False
    finally:
        store.close()


@pytest.mark.parametrize('fault', ['unknown_mass', 'missing_checkpoint'])
def test_actual_reader_retains_unknown_or_unbound_mass_without_next_dispatch(tmp_path, evidence, fault):
    class Unconfirmed(MassProtocol):
        def finish(self, operation_id):
            job = self.store.get(operation_id)
            if job['operation'] != 'measurement.mass':
                return super().finish(operation_id)
            if fault == 'unknown_mass':
                self.store.finish(operation_id, 'unknown', error=dict(code='mass_selection_restore_unconfirmed',
                    message='Artificial unconfirmed selection.', requires_reconciliation=True))
            else:
                self.store.finish(operation_id, 'succeeded',
                    result=artificial_result('measurement_get_mass', job['payload']['arguments']))
    path = tmp_path / 'unconfirmed-mass.sqlite'
    store = JobStore(path)
    try:
        client = Unconfirmed(store)
        reader, _, _, _ = durable_reader(client, path)
        with pytest.raises((ValueError, RuntimeError)): run(reader, evidence)
        assert len(client.dispatches) == 2 and client.retained
        assert [tool for tool, _ in client.calls if tool != 'job_get'] == [
            'measurement_prepare_mass', 'measurement_get_mass']
        with pytest.raises(RuntimeError, match='retained'):
            asyncio.run(reader.read('measurement_prepare_mass', dict(request_id='after-unknown', **CONTEXT)))
        assert len(client.dispatches) == 2
    finally:
        store.close()
