"""Public driver contract/preflight/transport and artificial CAD ownership only."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from test_rectangle_snapshot import adapter as empty_adapter
from test_rectangle_native_verifier import configured, execution, sketch_proof, extrusion_proof, proof_job


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
# Cache the passive public contracts; native dependencies are never instantiated.
sys.path.insert(0, str(SCRIPTS))
try:
    import verifier_rectangle_public_contract
    import verify_dimension_mcp
finally:
    sys.path.remove(str(SCRIPTS))
spec = importlib.util.spec_from_file_location('_rectangle_public_driver_test', SCRIPTS / 'verify_rectangle_stages_public.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def preflight_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    work = tmp_path / 'work'
    work.mkdir()
    paths = []
    for key in ('positive', 'faults'):
        path = work / (key + '.json')
        path.write_text(json.dumps({'scope': key}), encoding='utf8')
        paths.append(path)
    args = NS(internal_positive_report=paths[0], internal_faults_report=paths[1])
    package = dict(wheel={'wheel_sha256': 'a' * 64}, package_origin_verified=True,
        metadata_catalog=dict(public_tool_count=79, output_schemas_verified=True, build_matches_installed_wheel=True))
    return args, package


def test_preflight_exact_metadata_and_reports_precedes_any_native_connection(preflight_input):
    args, package = preflight_input
    events = []
    def provider(received, *, installed):
        assert received is args and installed is True
        events.append('metadata')
        return package
    def validator(reports, wheel, hashes):
        assert set(reports) == set(hashes) == {'positive', 'faults'}
        assert wheel == package['wheel'] and all(len(digest) == 64 for rows in hashes.values() for digest in rows.values())
        events.append('internal')
        return dict(accepted=True, native_b1_accepted=False)
    result = helper.preflight(args, package_provider=provider, internal_validator=validator)
    assert events == ['metadata', 'internal']
    assert result['metadata_mutation_count'] == 25 and result['internal_preflight']['native_b1_accepted'] is False
    assert set(result['internal_report_sha256']) == {'positive', 'faults'}


@pytest.mark.parametrize('fault', ['origin', 'catalog', 'schemas', 'build', 'outside', 'rejected', 'premature_native'])
def test_preflight_rejects_before_native_setup(preflight_input, fault):
    args, package = preflight_input
    if fault == 'origin': package['package_origin_verified'] = False
    elif fault == 'catalog': package['metadata_catalog']['public_tool_count'] = 26
    elif fault == 'schemas': package['metadata_catalog']['output_schemas_verified'] = False
    elif fault == 'build': package['metadata_catalog']['build_matches_installed_wheel'] = False
    elif fault == 'outside': args.internal_faults_report = args.internal_faults_report.parent.parent / 'outside.json'
    proof = dict(accepted=fault != 'rejected', native_b1_accepted=fault == 'premature_native')
    with pytest.raises(ValueError):
        helper.preflight(args, package_provider=lambda *args, **kwargs: package,
            internal_validator=lambda *args: proof)


def test_helper_manifests_expand_stars_without_executing_drivers(tmp_path):
    (tmp_path / 'driver.py').write_text("raise RuntimeError('must never execute')\nBASE=('a.py',)\nHELPERS=('driver.py',*BASE)\n", encoding='utf8')
    (tmp_path / 'a.py').write_text('data', encoding='utf8')
    assert set(helper.helper_hashes('driver.py', tmp_path)) == {'driver.py', 'a.py'}


def test_main_never_enters_native_run_on_rejected_preflight(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'work').mkdir()
    monkeypatch.setattr(sys, 'argv', ['driver', '--run-solidworks', '--state-dir', str(tmp_path / 'work/state'),
        '--wheel', 'candidate.whl', '--expected-version', '2.0.0.dev93', '--expected-git-sha', 'a' * 40,
        '--internal-positive-report', 'positive.json', '--internal-faults-report', 'faults.json'])
    monkeypatch.setattr(helper, 'preflight', lambda args: (_ for _ in ()).throw(ValueError('wrong exact wheel')))
    monkeypatch.setattr(helper, '_native_run', lambda *args: pytest.fail('Native run must not start'))
    with pytest.raises(ValueError, match='wrong exact wheel'):
        helper.main()
    report = json.loads((tmp_path / 'work/state/report.json').read_text(encoding='utf8'))
    assert report['phase'] == 'preflight_failed' and report['native_calls_live'] is False


@pytest.fixture
def bridge_evidence(empty_adapter):
    target = 'doc_' + 'a' * 32
    descriptor = dict(title='Контрольная деталь', path='', document_type='part', needs_save=True,
        configurations=['Основная'], active_configuration='Основная', update_stamp=1,
        document_id=target, observation_sequence=1, observation_revision='obs_exact',
        view=dict(orientation=list(helper.FRAME), translation=[0., 0., 0.], scale=1.))
    neighbor = {**deepcopy(descriptor), 'document_id': 'doc_' + 'b' * 32, 'title': 'Сосед'}
    before = dict(scope='new_empty_part_document_v1', semantic=dict(documents=[neighbor], active_document_id=neighbor['document_id'], visible=True))
    guard = dict(scope='application_document_create_guard_v1', original_command_in_progress=False, acquired=True,
        released=True, selection_preserved=True, model_guards=[dict(original_state=0, locked_state=2, released_state=0)])
    after = dict(created_document_id=target, semantic=dict(documents=[neighbor, descriptor], active_document_id=target, visible=True),
        created=dict(restored=False, complete=True, title=descriptor['title'], configuration='Основная', empty_part=True, active=True, unsaved=True))
    job = dict(operation='document.create_part', status='succeeded', error=None,
        payload=dict(arguments=dict(document_id='app_exact', configuration='', name=descriptor['title'])),
        result=dict(verified=True, before=deepcopy(before), after=deepcopy(after), execution_guard=deepcopy(guard)),
        mutation=dict(phase='committed', connection_epoch='same', document_id='app_exact', configuration='',
            before_state={**deepcopy(before), '_mutation_effect_scope': 'application'},
            verification=dict(outcome='committed', evidence=dict(after=deepcopy(after), execution_guard=deepcopy(guard)))))
    prepared = dict(connection_epoch='same', document_id=target, configuration='Основная',
        scope='empty_part_rectangle_sketch_v1', revision_scope='empty_part_rectangle_sketch_v1',
        native_execution_available=True, plane_transform=list(helper.FRAME), reference_persistent_id_hex='aa',
        baseline=dict(semantic=dict(documents=[deepcopy(neighbor), deepcopy(descriptor)], active_document_id=target,
            windows=[dict(document_id=target, hwnd=123), dict(document_id=neighbor['document_id'], hwnd=456)]),
            snapshots={target: empty_adapter.rectangle_construction_snapshot(empty_adapter.model)}))
    return job, prepared


def test_complete_same_connection_creation_bridge_binds_id_and_unique_hwnd(bridge_evidence):
    result = helper.creation_bridge(*bridge_evidence)
    assert result['document_id'] == bridge_evidence[1]['document_id'] and result['hwnd'] == 123


@pytest.mark.parametrize('fault', ['unknown', 'pending', 'not_verified', 'guard', 'partial_receipt', 'epoch',
    'foreign_id', 'stale_stamp', 'dirty_change', 'view_change', 'multiple_windows', 'boolean_hwnd', 'duplicate_hwnd',
    'missing_window', 'active', 'guard_census', 'neighbor_change', 'after_mismatch'])
def test_later_read_never_grants_ownership_without_complete_original_bridge(bridge_evidence, fault):
    job, prepared = bridge_evidence
    if fault == 'unknown': job['status'] = 'unknown'
    elif fault == 'pending': job['status'] = 'running'
    elif fault == 'not_verified': job['result']['verified'] = False
    elif fault == 'guard': job['result']['execution_guard']['released'] = False
    elif fault == 'partial_receipt': job['result']['after']['created']['complete'] = False
    elif fault == 'epoch': prepared['connection_epoch'] = 'reopened'
    elif fault == 'foreign_id': prepared['document_id'] = 'doc_' + 'c' * 32
    elif fault == 'stale_stamp': prepared['baseline']['semantic']['documents'][1]['update_stamp'] += 1
    elif fault == 'dirty_change': prepared['baseline']['semantic']['documents'][1]['needs_save'] = False
    elif fault == 'view_change': prepared['baseline']['semantic']['documents'][1]['view']['scale'] = 2.
    elif fault == 'multiple_windows': prepared['baseline']['semantic']['windows'].append(deepcopy(prepared['baseline']['semantic']['windows'][0]))
    elif fault == 'boolean_hwnd': prepared['baseline']['semantic']['windows'][0]['hwnd'] = True
    elif fault == 'duplicate_hwnd': prepared['baseline']['semantic']['windows'][1]['hwnd'] = 123
    elif fault == 'missing_window': prepared['baseline']['semantic']['windows'].pop(0)
    elif fault == 'active': prepared['baseline']['semantic']['active_document_id'] = 'foreign'
    elif fault == 'guard_census': job['result']['execution_guard']['model_guards'] = []
    elif fault == 'neighbor_change': job['result']['after']['semantic']['documents'][0]['needs_save'] = False
    else: job['mutation']['verification']['evidence']['after']['created']['active'] = False
    with pytest.raises(ValueError):
        helper.creation_bridge(job, prepared)


@pytest.fixture
def fake_canonical(bridge_evidence):
    bridge = helper.creation_bridge(*bridge_evidence)
    target, neighbor = object(), object()
    metadata = {key: val for key, val in bridge['descriptor'].items()
        if key not in ('document_id', 'observation_revision', 'observation_sequence', 'view')}
    view = deepcopy(bridge['descriptor']['view'])
    adapter = NS(identity=id, native_close_windows=lambda: [(target, {'hwnd': 123})],
        snapshot=lambda model: deepcopy(metadata), document_view_snapshot=lambda model: deepcopy(view))
    return adapter, bridge, target, neighbor, metadata, view


def test_artificial_native_hwnd_and_canonical_metadata_bind_exact_target(fake_canonical):
    adapter, bridge, target, neighbor, metadata, view = fake_canonical
    assert helper.bind_canonical_model(adapter, bridge, neighbor, active_model=target) == (target, id(target))
    helper.assert_owned_current(adapter, target, id(target), bridge, metadata, view)


@pytest.mark.parametrize('fault', ['replaced', 'neighbor', 'inactive', 'stamp', 'view', 'window', 'duplicate'])
def test_same_name_or_roster_change_never_authorizes_native_owned_cleanup(fake_canonical, fault):
    adapter, bridge, target, neighbor, metadata, view = fake_canonical
    active = target
    if fault == 'replaced': adapter.native_close_windows = lambda: [(object(), {'hwnd': 123})]
    elif fault == 'neighbor': adapter.native_close_windows = lambda: [(neighbor, {'hwnd': 123})]
    elif fault == 'inactive': active = neighbor
    elif fault == 'stamp': metadata['update_stamp'] += 1
    elif fault == 'view': view['scale'] = 2.
    elif fault == 'window': adapter.native_close_windows = lambda: [(target, {'hwnd': 999})]
    else: adapter.native_close_windows = lambda: [(target, {'hwnd': 123}), (target, {'hwnd': 123})]
    with pytest.raises(ValueError):
        helper.bind_canonical_model(adapter, bridge, neighbor, active_model=active)


@pytest.mark.parametrize('mode', ['positive', 'unknown', 'lost_ack'])
def test_transport_polls_terminal_once_and_never_retries_or_clears_unknown_hold(mode):
    calls, observations = [], []
    class Client:
        async def call_tool(self, name, args):
            calls.append((name, deepcopy(args)))
            if mode == 'lost_ack': raise OSError('lost acknowledgement')
            if name != 'job_get': value = dict(status='running', operation_id='op', data=None)
            else: value = dict(status='unknown' if mode == 'unknown' else 'succeeded', operation_id='op',
                              data={'result': {'verified': True}})
            return NS(isError=False, structuredContent=value)
        async def observe_once(self):
            observations.append(True)
            return NS(child_can_close=True)
    gate = NS(can_cleanup=lambda: mode == 'positive')
    report = {}
    async def exercise():
        return await helper.public_invoke(Client(), gate, report, lambda: None,
            'sketch_create_rectangle', request_id='exact-request', document_id='doc', configuration='Основная')
    if mode == 'positive':
        assert asyncio.run(exercise())['status'] == 'succeeded'
        assert report['native_calls_live'] is False and len(observations) == 1
    else:
        with pytest.raises(OSError if mode == 'lost_ack' else RuntimeError): asyncio.run(exercise())
        assert report['native_calls_live'] is True
    assert sum(name == 'sketch_create_rectangle' for name, _ in calls) == 1
    assert calls[0][1]['request_id'] == 'exact-request' and calls[0][1]['timeout_s'] == 0.


def test_public_module_load_is_passive_and_does_not_import_com():
    code = '''
import importlib.util, sys
before = list(sys.path)
spec = importlib.util.spec_from_file_location('_public_passive', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert sys.path == before
assert 'pythoncom' not in sys.modules
assert 'solidworks_mcp.binding' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS / 'verify_rectangle_stages_public.py')],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('fault', ['none', 'dto_mismatch', 'missing', 'duplicate', 'digest', 'transport', 'unsafe'])
def test_public_job_dto_must_match_one_real_coherent_journal_row(proof_job, configured, monkeypatch, fault):
    import verifier_lifecycle
    original_read = verifier_lifecycle.read_journal
    reads, calls, retained = [], [], []
    dto = deepcopy(proof_job)
    if fault == 'dto_mismatch':
        dto['result']['value']['created_native_id'] += 1

    def read(path):
        reads.append(path)
        rows = original_read(path)
        if fault == 'missing': return []
        if fault == 'duplicate': return [*rows, deepcopy(rows[0])]
        if fault == 'digest': rows[0]['digest'] = '0' * 64
        return rows
    monkeypatch.setattr(verifier_lifecycle, 'read_journal', read)

    class Client:
        async def observe_once(self):
            return NS(child_can_close=True)
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            assert name == 'job_get' and arguments == {'operation_id': proof_job['operation_id']}
            if fault == 'transport': raise OSError('DTO acknowledgement lost')
            return NS(isError=False, structuredContent=dict(status='succeeded', data=dto))
        def retain(self, reason):
            retained.append(reason)
    gate = NS(can_cleanup=lambda: fault != 'unsafe')
    async def exercise():
        return await helper.durable_job(Client(), gate, configured.store.path, proof_job['operation_id'])
    if fault == 'none':
        persisted = asyncio.run(exercise())
        assert {key: value for key, value in persisted.items() if key != 'digest'} == proof_job
        assert len(persisted['digest']) == 64 and persisted is not dto
        assert len(reads) == len(calls) == 1 and not retained
    else:
        with pytest.raises(OSError if fault == 'transport' else RuntimeError if fault == 'unsafe' else ValueError):
            asyncio.run(exercise())
        assert len(reads) <= 1 and len(calls) <= 1
        if fault == 'unsafe':
            assert not calls and not reads
        else:
            assert retained == ['public job DTO/durable journal proof unconfirmed']


def independent_view_namespace(snapshot):
    result = deepcopy(snapshot)
    binding = result['native_observations']['annotation_view_bindings']
    remap = {identifier: 'av_' + f'{index + 1:032x}' for index, identifier in enumerate(binding['view_ids'])}
    binding['view_ids'] = [remap[identifier] for identifier in binding['view_ids']]
    binding['dimension_views'] = {axis: remap[identifier] for axis, identifier in binding['dimension_views'].items()}
    return result


def test_complete_view_relation_bijection_accepts_independent_process_uuid_namespace(extrusion_proof):
    expected = extrusion_proof[1]['snapshots']['target']
    observed = independent_view_namespace(expected)
    assert observed['native_observations']['annotation_view_bindings'] != expected['native_observations']['annotation_view_bindings']
    assert helper.compare_stage_snapshot(observed, expected)['complete_relation_bijection_verified'] is True


@pytest.mark.parametrize('fault', ['rebind', 'missing', 'shared_identity', 'row', 'nonbinding_data'])
def test_bijection_requires_complete_rows_and_exact_axis_partition(extrusion_proof, fault):
    from solidworks_mcp.jobs import ExecutionFailure
    expected = extrusion_proof[1]['snapshots']['target']
    observed = independent_view_namespace(expected)
    binding = observed['native_observations']['annotation_view_bindings']
    if fault == 'rebind': binding['dimension_views']['height'] = binding['dimension_views']['depth']
    elif fault == 'missing': binding['view_ids'].pop()
    elif fault == 'shared_identity': binding['view_ids'][0] = binding['view_ids'][1]
    elif fault == 'row': observed['clone_state']['display_data']['annotation_views'][0]['shown'] = False
    else: observed['clone_state']['material'][0] = 'foreign'
    with pytest.raises((ValueError, ExecutionFailure)):
        helper.compare_stage_snapshot(observed, expected)


def test_root_local_chain_preserves_borrowed_view_ids_across_extrusion(extrusion_proof):
    previous = independent_view_namespace(extrusion_proof[0]['snapshots']['target'])
    expected = extrusion_proof[1]['snapshots']['target']
    observed = independent_view_namespace(expected)
    assert helper.compare_stage_snapshot(observed, expected, previous=previous)['local_transition_verified'] is True


@pytest.mark.parametrize('fault', ['borrowed_rebind', 'reopened_incarnation'])
def test_cross_process_equivalent_relations_cannot_override_local_ownership_drift(extrusion_proof, fault):
    previous = independent_view_namespace(extrusion_proof[0]['snapshots']['target'])
    expected = extrusion_proof[1]['snapshots']['target']
    observed = independent_view_namespace(expected)
    binding = observed['native_observations']['annotation_view_bindings']
    if fault == 'borrowed_rebind':
        width, depth = binding['dimension_views']['width'], binding['dimension_views']['depth']
        binding['dimension_views'].update(width=depth, height=depth, depth=width)
    else:
        binding['view_ids'][0] = 'av_' + 'f' * 32
    # Row/axis graph equivalence alone cannot establish native ownership; the
    # same-process old->new incarnation proof is separately indispensable.
    helper.compare_stage_snapshot(observed, expected)
    with pytest.raises(ValueError, match='local view incarnations'):
        helper.compare_stage_snapshot(observed, expected, previous=previous)
