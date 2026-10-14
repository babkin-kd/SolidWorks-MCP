"""Finite installed B1 public chain after exact-wheel internal acceptance.

Only this process owns its fixtures. Pending/unknown effects retain the process
and receipts; no cancellation, automatic retry or adoption by title/roster delta.
Native imports/connections and fixture creation follow the passive preflight.
"""
import argparse
import ast
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import uuid


POSITIVE_HELPERS = ('verify_rectangle_stages_positive.py', 'verifier_rectangle_stages.py',
    'probe_native_first_save_domain.py', 'verify_installed_metadata.py', 'verify_wheel_artifact.py',
    'verify_bounds_measurements.py', 'verify_export_operations.py', 'verify_native_document_open.py',
    'verify_native_first_save_rejections.py', 'verifier_dimension_diagnostics.py')
FAULT_HELPERS = ('verify_rectangle_stages_faults.py', 'verifier_rectangle_positive_acceptance.py',
    'verifier_rectangle_restoration.py', 'verifier_rectangle_prewrite.py', *POSITIVE_HELPERS)
HELPERS = ('verify_rectangle_stages_public.py', 'verifier_rectangle_internal_acceptance.py',
    'verifier_rectangle_public_contract.py', 'verifier_lifecycle.py', 'verifier_native_open.py',
    'verifier_native_part_activation.py', 'verifier_native_first_save.py', 'verify_dimension_mcp.py',
    'verify_component_reads.py', 'verify_document_reads.py', 'verify_geometry_reads.py',
    'verify_native_document_save.py', 'verifier_native_open_acceptance.py', *FAULT_HELPERS)
PUBLIC_LABELS = ('B1-public-exact-empty-document', 'B1-public-separate-sketch-and-replay',
    'B1-public-separate-extrusion-and-replay', 'B1-public-independent-base-and-neighbor',
    'B1-public-owned-cleanup-baseline')
FRAME = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def compare_stage_snapshot(observed, expected, *, previous=None):
    """Full cross-process comparison plus native local incarnation preservation.

    Annotation view av_UUID values belong to each capturing adapter. A complete
    bijection must preserve every full row and exact assigned axis partition;
    all other snapshot fields remain exact. Within this adapter, the old actual
    view IDs and borrowed axis links must survive each construction unchanged.
    """
    from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot, EMPTY, SKETCH, BASE
    from solidworks_mcp.rectangle_annotation_views import validated_view_bindings, verified_new_dimension_view
    def normal_form(value):
        snapshot = deepcopy(validated_rectangle_snapshot(value))
        profile = snapshot['clone_state']['profile']
        axes = {EMPTY: set(), SKETCH: {'width', 'height'}, BASE: {'width', 'height', 'depth'}}[profile]
        display = snapshot['clone_state']['display_data']
        binding = snapshot['native_observations']['annotation_view_bindings']
        validated_view_bindings(display, binding, axes)
        relations = [dict(view=deepcopy(row), axes=sorted(axis for axis, owner in binding['dimension_views'].items()
                                                       if owner == identifier))
                     for identifier, row in zip(binding['view_ids'], display['annotation_views'])]
        relations.sort(key=canonical)
        # This retains all rows, their multiplicity and complete edge partition.
        # Raw evidence, including both independent UUID namespaces, is preserved
        # in the private report; only the detached comparison uses this encoding.
        display['annotation_views'] = [row['view'] for row in relations]
        snapshot['native_observations']['annotation_view_bindings'] = dict(scope=binding['scope'], relations=relations)
        return snapshot
    require(canonical(normal_form(observed)) == canonical(normal_form(expected)),
        'Complete independent stage snapshot or annotation-view relation differs from durable evidence.')
    if previous is not None:
        old = validated_rectangle_snapshot(previous)
        new = validated_rectangle_snapshot(observed)
        profiles = old['clone_state']['profile'], new['clone_state']['profile']
        require(profiles in ((EMPTY, SKETCH), (SKETCH, BASE)), 'Only the finite owned stage transitions are allowed.')
        axes = {'width', 'height'} if profiles == (EMPTY, SKETCH) else {'depth'}
        require(verified_new_dimension_view(old['clone_state']['display_data'], new['clone_state']['display_data'],
            old['native_observations']['annotation_view_bindings'], new['native_observations']['annotation_view_bindings'],
            created_axes=axes), 'Independent local view incarnations or borrowed axis bindings changed.')
    return dict(complete_relation_bijection_verified=True, local_transition_verified=previous is not None)


def helper_hashes(driver, directory=None):
    """Read finite tuple manifests without importing a native driver."""
    directory = Path(directory or Path(__file__).parent)
    tree = ast.parse((directory / driver).read_text(encoding='utf8'))
    values = {}
    def literal(node):
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, (ast.Tuple, ast.List)):
            rows = []
            for item in node.elts:
                rows.extend(literal(item.value)) if isinstance(item, ast.Starred) else rows.append(literal(item))
            return tuple(rows)
        return ast.literal_eval(node)
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Tuple, ast.List)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = literal(node.value)
    names = values['HELPERS']
    require(bool(names) and all(type(name) is str and Path(name).name == name for name in names),
        'A bounded local helper manifest is required.')
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


def preflight(args, *, package_provider=None, internal_validator=None):
    """Reject foreign/partial reports before CoInitialize, COM or fixture setup."""
    if package_provider is None:
        from probe_native_first_save_domain import package_evidence
        package_provider = package_evidence
    if internal_validator is None:
        from verifier_rectangle_internal_acceptance import validate_internal_reports
        internal_validator = validate_internal_reports
    package = package_provider(args, installed=True)
    catalog = package['metadata_catalog']
    require(package['package_origin_verified'] is True and catalog['public_tool_count'] == 79
        and catalog['output_schemas_verified'] is True and catalog['build_matches_installed_wheel'] is True,
        'Exact installed metadata79/25 catalog is required.')
    reports, trusted = {}, {}
    for key, driver in (('positive', 'verify_rectangle_stages_positive.py'),
                        ('faults', 'verify_rectangle_stages_faults.py')):
        path = getattr(args, 'internal_' + key + '_report').resolve()
        require(path.is_relative_to(Path.cwd() / 'work'), 'Internal reports must remain in private work/.')
        reports[key] = json.loads(path.read_text(encoding='utf8'))
        trusted[key] = helper_hashes(driver)
    proof = internal_validator(reports, package['wheel'], trusted)
    require(proof['accepted'] is True and proof['native_b1_accepted'] is False,
        'Internal preflight cannot substitute native B1 acceptance.')
    return {**package, 'internal_preflight': proof,
        'internal_report_sha256': {key: hashlib.sha256(getattr(args, 'internal_' + key + '_report').read_bytes()).hexdigest()
                                   for key in reports}, 'metadata_mutation_count': 25}


def creation_bridge(job, prepared):
    """Bind the exact returned creation to its still-live same-connection entry.

    Creation's actual DTO has no HWND. Its committed ID/complete receipt and
    unchanged descriptor must first bind a preparation on that same connection.
    Only then does its unique ID-bound HWND permit independent canonical lookup.
    A later window read by itself never grants ownership.
    """
    from verifier_rectangle_public_contract import created_part_id
    from verifier_lifecycle import released_execution_guard
    from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot, EMPTY
    target_id = created_part_id(job)
    result, mutation = job['result'], job['mutation']
    guard = result['execution_guard']
    require(released_execution_guard(guard) and guard['scope'] == 'application_document_create_guard_v1'
        and mutation['before_state']['_mutation_effect_scope'] == 'application'
        and mutation['before_state']['scope'] == 'new_empty_part_document_v1'
        and mutation['document_id'] == job['payload']['arguments']['document_id']
        and mutation['configuration'] == job['payload']['arguments']['configuration'] == ''
        and mutation['verification']['outcome'] == 'committed'
        and canonical(result['before']) == canonical({key: value for key, value in mutation['before_state'].items()
                                                       if key != '_mutation_effect_scope'})
        and canonical(result['after']) == canonical(mutation['verification']['evidence']['after'])
        and canonical(mutation['verification']['evidence']['execution_guard']) == canonical(guard),
        'Exact committed creation with released application guard is required.')
    after = result['after']
    baseline = result['before']['semantic']['documents']
    require(len(guard['model_guards']) == len(baseline)
        and all(item['document_id'] != target_id for item in baseline)
        and canonical([item for item in after['semantic']['documents'] if item['document_id'] != target_id]) == canonical(baseline),
        'Complete creation baseline and all existing released model guards required.')
    created = after['created']
    require(set(created) == {'restored', 'complete', 'title', 'configuration', 'empty_part', 'active', 'unsaved'}
        and all(created[key] is True for key in ('complete', 'empty_part', 'active', 'unsaved'))
        and created['restored'] is False and created['configuration'] == 'Основная',
        'Complete exact normal returned empty-document receipt required.')
    rows = [row for row in after['semantic']['documents'] if row['document_id'] == target_id]
    require(len(rows) == 1 and after['semantic']['active_document_id'] == target_id,
        'Creation must name exactly one active returned catalog entry.')
    row = rows[0]
    require(row['title'] == created['title'] == job['payload']['arguments']['name']
        and row['path'] == '' and row['document_type'] == 'part'
        and row['active_configuration'] == 'Основная' and row['configurations'] == ['Основная']
        and type(row['update_stamp']) is int and type(row['needs_save']) is bool,
        'Exact Russian one-configuration unsaved creation metadata required.')
    require(prepared['connection_epoch'] == mutation['connection_epoch']
        and prepared['document_id'] == target_id and prepared['configuration'] == 'Основная'
        and prepared['scope'] == prepared['revision_scope'] == 'empty_part_rectangle_sketch_v1'
        and prepared['native_execution_available'] is True and tuple(prepared['plane_transform']) == FRAME,
        'Preparation must resolve the original live entry and exact reference plane.')
    semantic = prepared['baseline']['semantic']
    current = [item for item in semantic['documents'] if item['document_id'] == target_id]
    require(len(current) == 1 and semantic['active_document_id'] == target_id
        and all(key in current[0] and canonical(current[0][key]) == canonical(value) for key, value in row.items()),
        'Creation metadata/view/stamp changed before the window bridge.')
    windows = [item for item in semantic['windows'] if item['document_id'] == target_id]
    require(len(windows) == 1 and type(windows[0]['hwnd']) is int and 0 < windows[0]['hwnd'] < 2**63
        and len({item['hwnd'] for item in semantic['windows']}) == len(semantic['windows']),
        'Exactly one unique current window must bind the created document ID.')
    empty = validated_rectangle_snapshot(prepared['baseline']['snapshots'][target_id])
    require(empty['clone_state']['profile'] == EMPTY and empty['solid_body_count'] == 0,
        'The exact returned document must remain an independently captured empty part.')
    return dict(document_id=target_id, hwnd=windows[0]['hwnd'], descriptor=row,
        reference_persistent_id_hex=prepared['reference_persistent_id_hex'])


def bind_canonical_model(adapter, bridge, neighbor, *, active_model):
    """Independent native HWND lookup, strict metadata and canonical identity."""
    matches = [(model, window) for model, window in adapter.native_close_windows()
               if window['hwnd'] == bridge['hwnd']]
    require(len(matches) == 1, 'Owned window has disappeared or become ambiguous.')
    model = matches[0][0]
    token = adapter.identity(model)
    require(token != adapter.identity(neighbor) and token == adapter.identity(active_model),
        'Returned target must be the exact active canonical model, distinct from the neighbor.')
    expected = {key: value for key, value in bridge['descriptor'].items()
                if key not in ('document_id', 'observation_revision', 'observation_sequence', 'view')}
    require(canonical(adapter.snapshot(model)) == canonical(expected)
        and canonical(adapter.document_view_snapshot(model)) == canonical(bridge['descriptor']['view']),
        'Native creation metadata/view does not match the same-connection durable descriptor.')
    return model, token


def assert_owned_current(adapter, model, token, bridge, expected_snapshot, expected_view):
    require(adapter.identity(model) == token
        and sum(adapter.identity(current) == token and window['hwnd'] == bridge['hwnd']
                for current, window in adapter.native_close_windows()) == 1
        and canonical(adapter.snapshot(model)) == canonical(expected_snapshot)
        and canonical(adapter.document_view_snapshot(model)) == canonical(expected_view),
        'Owned canonical window/metadata/view changed before fixture retirement.')


async def public_invoke(client, gate, report, persist, tool, **arguments):
    from verify_dimension_mcp import call, require_native_cleanup
    report['native_calls_live'] = True
    persist()
    result = await call(client, tool, **arguments, timeout_s=0.)
    report['last_response'] = result
    persist()
    await require_native_cleanup(client, gate)
    report['native_calls_live'] = False
    persist()
    return result


async def durable_job(client, gate, path, operation_id):
    """One coherent independent SQL snapshot must equal the public job DTO."""
    from verify_dimension_mcp import require_native_cleanup
    from verifier_lifecycle import read_journal
    await require_native_cleanup(client, gate)
    try:
        raw = await client.call_tool('job_get', {'operation_id': operation_id})
        require(raw.isError is False and raw.structuredContent['status'] == 'succeeded',
            'Full public job DTO was not returned.')
        dto = raw.structuredContent['data']
        rows = read_journal(path)
        matches = [row for row in rows if row['operation_id'] == operation_id]
        require(len(matches) == 1, 'One exact coherent durable mutation row required.')
        persisted = matches[0]
        # JobStore._decode deliberately removes the private digest column from
        # the public DTO. Verify that column independently, then compare every
        # published field exactly; never silently discard any other SQL field.
        digest = hashlib.sha256((persisted['operation'] + '\n' + canonical(persisted['payload'])).encode('utf8')).hexdigest()
        require(persisted['digest'] == digest
            and canonical({key: value for key, value in persisted.items() if key != 'digest'}) == canonical(dto),
            'Public job DTO differs from its exact independent durable journal row.')
        return persisted
    except BaseException:
        client.retain('public job DTO/durable journal proof unconfirmed')
        raise


def _native_run(args, report, persist, *, after_base=None, tool_specs=None, terminal_acceptance=True):
    import pythoncom
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from solidworks_mcp import binding
    from solidworks_mcp.cad_documents import SolidWorksDocuments
    from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
    from solidworks_mcp.native_first_save import validated_part_snapshot
    from solidworks_mcp.part_creation import BaseRectangle, validated_plane_transform
    from solidworks_mcp.rectangle_snapshot import validated_rectangle_snapshot, EMPTY, SKETCH, BASE
    from solidworks_mcp.session import SolidWorksSession
    from verifier_rectangle_public_contract import SPECS
    from verifier_rectangle_stages import verified_rectangle_job
    from verifier_lifecycle import open_supervised_session
    from verify_dimension_mcp import SessionCleanupGate, require_native_cleanup, succeeded
    from verify_export_operations import application_preferences
    from verify_native_document_open import retire_owned, snapshot
    from verify_native_first_save_rejections import owned_document_rows
    from verifier_dimension_diagnostics import assert_non_stl_preferences
    from verify_installed_metadata import verify_metadata

    owned, gate = [], SessionCleanupGate()
    def record(models):
        report['owned_documents'] = owned_document_rows(models)
        persist()
    class Observed(SolidWorksDocuments):
        def rectangle_construction_snapshot(self, model):
            row = dict(status='running', title=model.GetTitle())
            report['captures'].append(row)
            report['native_calls_live'] = True
            persist()
            try:
                result = super().rectangle_construction_snapshot(model)
                row['status'] = 'returned'
                report['native_calls_live'] = False
                return result
            finally:
                persist()
    pythoncom.CoInitialize()
    try:
        sw, module = binding.connect(show=False), binding.module()
        require(not sw.GetDocuments() and sw.ActiveDoc is None and sw.CommandInProgress is False
            and sw.UserControl is True, 'Use an empty quiescent owned native session.')
        adapter = Observed()
        original, application, preferences = snapshot(sw, module), adapter.native_close_application_context(), application_preferences(sw)
        report.update(original_baseline=original, original_application=application, original_preferences=preferences)
        require(sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False,
            'Disable interactive dimension entry before this owned scenario.')
        sw.CommandInProgress = True
        require(sw.CommandInProgress is True, 'Owned setup flag acquisition failed.')
        session = SolidWorksSession()
        session._sw, session._mod = sw, module
        report.update(phase='owned_neighbor_setup', native_calls_live=True)
        persist()
        created = session.new_part()
        neighbor = session._model
        require(type(created) is dict and created.get('ok') is True and neighbor is not None,
            'Only a normal exact fixture return grants neighbor ownership.')
        owned.append(neighbor)
        report['native_calls_live'] = False
        record(owned)
        require(neighbor.SetTitle2('Рабочий сосед публичных стадий'), 'Neighbor title was not acknowledged.')
        binding.wrap(neighbor.GetActiveConfiguration(), module.IConfiguration).Name = 'Основная'
        features = adapter.features(neighbor)
        planes = [feature for feature in features if feature.GetTypeName2() == 'RefPlane'
                  and tuple(validated_plane_transform(adapter.reference_plane_transform(feature))) == FRAME]
        require(len(planes) == 1, 'Unique exact fixture plane required.')
        definition = BaseRectangle.validate(plane_object_id='feat_' + uuid.uuid4().hex, width_mm=5., height_mm=6., depth_mm=7.)
        receipt = adapter.new_base_receipt(neighbor, features, adapter.part_creation_controls(neighbor))
        report['native_calls_live'] = True
        persist()
        adapter.create_base_rectangle(neighbor, planes[0], definition, receipt)
        report['native_calls_live'] = False
        require(neighbor.ForceRebuild3(False) and neighbor.GetSaveFlag() is True, 'Dirty neighbor fixture required.')
        neighbor.ClearSelection2(True)
        neighbor_identity = adapter.identity(neighbor)
        neighbor_before = validated_part_snapshot(adapter.first_save_part_snapshot(neighbor))
        report['independent_neighbor'] = neighbor_before
        sw.CommandInProgress = False
        require(sw.CommandInProgress is False, 'Owned setup flag release failed.')
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'solidworks_mcp.server_v2', '--state-dir', str(args.state_dir / 'server')],
            env={**os.environ, 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'})
        @asynccontextmanager
        async def factory():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as raw:
                    await raw.initialize()
                    tools = (await raw.list_tools()).tools
                    metadata = await raw.call_tool('system_get_info', {})
                    require(metadata.isError is False and metadata.structuredContent['status'] == 'succeeded',
                        'Live public metadata response failed.')
                    report['public_metadata_catalog'] = verify_metadata(tools, metadata.structuredContent['data'], report['wheel'])
                    persist()
                    yield raw
        async def exercise():
            async with open_supervised_session(factory, tool_specs=SPECS if tool_specs is None else tool_specs,
                journal_path=args.state_dir / 'server/jobs.sqlite',
                on_hold=lambda decision: (report.update(lifecycle_hold=True), persist())) as client:
                gate.add(client)
                async def invoke(tool, **arguments):
                    return await public_invoke(client, gate, report, persist, tool, **arguments)
                templates = succeeded(await invoke('document_list_templates', request_id='templates'))
                require(templates['native_creation_available'] is True and len(templates['templates']) == 1,
                    'One configured exact empty-part template required.')
                template = templates['templates'][0]
                require(template['document_type'] == 'part' and template['source'] == 'solidworks_configured_default',
                    'Configured native part template required.')
                create_inputs = dict(template_id=template['template_id'], name='Контрольная деталь публичных стадий',
                    configuration_name='Основная')
                prepared = succeeded(await invoke('document_prepare_create_part', request_id='prepare-create', **create_inputs))
                create_args = dict(**create_inputs, application_id=prepared['application_id'], expected_revision=prepared['revision'])
                report['phase'] = 'public_document_create'
                creation = await invoke('document_create_part', request_id='create', **create_args)
                require(creation['status'] == 'succeeded', 'Public document creation failed.')
                journal_path = args.state_dir / 'server/jobs.sqlite'
                creation_job = await durable_job(client, gate, journal_path, creation['operation_id'])
                report['creation_job'] = creation_job
                from verifier_rectangle_public_contract import created_part_id
                target_id = created_part_id(creation_job)
                context = dict(document_id=target_id, configuration='Основная')
                listing = succeeded(await invoke('feature_list', request_id='features-empty', **context))
                require(listing['next_cursor'] is None and listing['total_count'] == len(listing['items']),
                    'Complete bounded feature listing required.')
                candidates = [row for row in listing['items'] if row['feature_type'] == 'RefPlane'
                    and row['persistent_reference_supported'] is True and row['object_id']]
                require(len(candidates) == 3, 'Exactly three existing referenced template planes required.')
                matches = []
                for index, plane in enumerate(candidates):
                    arguments = dict(**context, plane_object_id=plane['object_id'], width_mm=40., height_mm=20., sketch_name='Эскиз основания')
                    candidate = succeeded(await invoke('sketch_prepare_rectangle', request_id=f'prepare-plane-{index}', **arguments))
                    if tuple(validated_plane_transform(candidate['plane_transform'])) == FRAME:
                        matches.append((plane, arguments, candidate))
                require(len(matches) == 1, 'The exact persistent identity reference plane must be unique.')
                plane, sketch_args, sketch_prepared = matches[0]
                bridge = creation_bridge(creation_job, sketch_prepared)
                await require_native_cleanup(client, gate)
                target, target_identity = bind_canonical_model(adapter, bridge, neighbor, active_model=adapter.active_document())
                native_plane = [feature for feature in adapter.features(target)
                    if adapter.feature_summary(feature)['native_id'] == plane['native_id']
                    and adapter.persistent_id(target, feature).hex() == bridge['reference_persistent_id_hex']]
                require(len(native_plane) == 1 and tuple(validated_plane_transform(adapter.reference_plane_transform(native_plane[0]))) == FRAME,
                    'Exact independently resolved persistent plane required.')
                owned.append(target)
                record(owned)
                report['ownership_bridge'] = bridge
                report['cases'].append(dict(label=PUBLIC_LABELS[0], passed=True))
                previous_native = None
                async def independent(profile, count, expected):
                    nonlocal previous_native
                    await require_native_cleanup(client, gate)
                    try:
                        require(sw.CommandInProgress is False and adapter.identity(target) == target_identity
                            and adapter.identity(neighbor) == neighbor_identity, 'Owned canonical identities/flags changed.')
                        sw.CommandInProgress = True
                        require(sw.CommandInProgress is True, 'Owned observer flag acquisition failed.')
                        observed = validated_rectangle_snapshot(adapter.rectangle_construction_snapshot(target))
                        require(observed['clone_state']['profile'] == profile and observed['solid_body_count'] == count,
                            'Independent public stage geometry/profile differs.')
                        relation = compare_stage_snapshot(observed, expected, previous=previous_native)
                        report.setdefault('independent_view_chain', []).append(relation)
                        previous_native = deepcopy(observed)
                        require(validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == neighbor_before
                            and neighbor.GetSaveFlag() is True, 'Dirty borrowed neighbor changed.')
                        sw.CommandInProgress = False
                        require(sw.CommandInProgress is False, 'Owned observer flag release failed.')
                        return observed
                    except BaseException:
                        client.retain('independent public stage proof failed')
                        raise
                report['independent_empty'] = await independent(EMPTY, 0,
                    sketch_prepared['baseline']['snapshots'][target_id])
                sketch_args['expected_revision'] = sketch_prepared['revision']
                built = await invoke('sketch_create_rectangle', request_id='sketch', **sketch_args)
                require(built['status'] == 'succeeded', 'Separate sketch creation failed.')
                sketch_job = await durable_job(client, gate, journal_path, built['operation_id'])
                require(verified_rectangle_job(sketch_job), 'Exact sketch journal proof required.')
                report['sketch_job'] = sketch_job
                require(await invoke('sketch_create_rectangle', request_id='sketch', **sketch_args) == built,
                    'Sketch replay must return the same exact operation/result.')
                report['independent_sketch'] = await independent(SKETCH, 0,
                    sketch_job['result']['after']['state']['snapshots'][target_id])
                report['cases'].append(dict(label=PUBLIC_LABELS[1], passed=True))
                extrusion_args = dict(**context, sketch_object_id=sketch_job['result']['value']['sketch_object_id'],
                    depth_mm=10., feature_name='Основание', body_name='Тело основания')
                prepared = succeeded(await invoke('part_prepare_rectangle_extrusion', request_id='prepare-extrusion', **extrusion_args))
                extrusion_args['expected_revision'] = prepared['revision']
                built = await invoke('part_extrude_rectangle', request_id='extrusion', **extrusion_args)
                require(built['status'] == 'succeeded', 'Separate blind extrusion failed.')
                extrusion_job = await durable_job(client, gate, journal_path, built['operation_id'])
                require(verified_rectangle_job(extrusion_job), 'Exact extrusion journal proof required.')
                report['extrusion_job'] = extrusion_job
                require(await invoke('part_extrude_rectangle', request_id='extrusion', **extrusion_args) == built,
                    'Extrusion replay must return the same exact operation/result.')
                report['cases'].append(dict(label=PUBLIC_LABELS[2], passed=True))
                report['independent_base'] = await independent(BASE, 1,
                    extrusion_job['result']['after']['state']['snapshots'][target_id])
                await require_native_cleanup(client, gate)
                bodies = adapter.bodies(target, 'all')
                require(len(bodies) == 1 and bodies[0].Name == 'Тело основания', 'One exactly named owned base body required.')
                volume = float(bodies[0].GetMassProperties(1.)[3]) * 1e9
                require(math.isclose(volume, 8000., rel_tol=1e-8, abs_tol=1e-6), 'Independent 40x20x10 mm volume required.')
                report['independent_volume_mm3'] = volume
                report['independent_native_readback_verified'] = True
                final_semantic = extrusion_job['result']['after']['state']['semantic']
                if after_base is not None:
                    # The exact server-owned B1 context and supervisor remain
                    # live. A later workflow must independently validate its
                    # final committed job before changing cleanup expectations.
                    from verifier_b2_public_route import extension_final_state,compare_b2_observed_state
                    await require_native_cleanup(client, gate)
                    extension = await after_base(client=client, gate=gate,
                        journal_path=journal_path, context=context, adapter=adapter,
                        target=target, target_identity=target_identity,
                        neighbor=neighbor, neighbor_identity=neighbor_identity,
                        neighbor_before=neighbor_before, bridge=bridge,
                        sketch_job=sketch_job, extrusion_job=extrusion_job,
                        independent_sketch=report['independent_sketch'],
                        independent_base=report['independent_base'],
                        report=report, persist=persist)
                    final_state = extension_final_state(extension, extrusion_job,
                                                        compare_state=compare_b2_observed_state)
                    report['after_base_extension'] = extension
                    final_semantic = final_state['semantic']
                    await require_native_cleanup(client, gate)
                # Fresh current metadata plus the original HWND/canonical token
                # must still authorize the target we will eventually retire.
                current = succeeded(await invoke('document_get', request_id='target-final', **context))
                final_snapshot = adapter.snapshot(target)
                final_view = adapter.document_view_snapshot(target)
                require(canonical(final_snapshot) == canonical({key: current[key] for key in final_snapshot}),
                    'Final public/native target metadata differs.')
                after_rows = [row for row in final_semantic['documents']
                              if row['document_id'] == target_id]
                require(len(after_rows) == 1
                    and canonical(final_snapshot) == canonical({key: after_rows[0][key] for key in final_snapshot})
                    and canonical(final_view) == canonical(after_rows[0]['view']),
                    'Target metadata/view changed after the exact committed final stage.')
                assert_owned_current(adapter, target, target_identity, bridge, final_snapshot, final_view)
                report['final_target_metadata'] = final_snapshot
                report['final_target_view'] = final_view
                report['cases'].append(dict(label=PUBLIC_LABELS[3], passed=True))
                await require_native_cleanup(client, gate)
            require(gate.can_cleanup(), 'SDK shutdown or terminal jobs did not authorize fixture cleanup.')
            return target, target_identity, bridge
        target, target_identity, bridge = asyncio.run(exercise())
        require(gate.can_cleanup() and report['native_calls_live'] is False,
            'No native cleanup is allowed while calls/effects remain uncertain.')
        assert_owned_current(adapter, target, target_identity, bridge,
            report['final_target_metadata'], report['final_target_view'])
        sw.CommandInProgress = True
        require(sw.CommandInProgress is True, 'Owned cleanup flag acquisition failed.')
        report['phase'] = 'owned_cleanup'
        retire_owned(sw, module, target, [target], owned, record)
        require(validated_part_snapshot(adapter.first_save_part_snapshot(neighbor)) == neighbor_before,
            'Neighbor changed while the exact owned target was retired.')
        retire_owned(sw, module, neighbor, [neighbor], owned, record)
        sw.CommandInProgress = False
        restored = snapshot(sw, module)
        require(restored == original and adapter.native_close_application_context() == application,
            'Full original session/application baseline was not restored.')
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report.update(phase='terminal', accepted=terminal_acceptance, public_rectangle_passed=True, native_b1_accepted=False,
            own_cleanup_verified=True, baseline_restored=True, restored_baseline=restored,
            restored_application=adapter.native_close_application_context(), supervised_cleanup_verified=gate.can_cleanup())
        report['cases'].append(dict(label=PUBLIC_LABELS[4], passed=True))
        persist()
    except BaseException as error:
        report.update(phase='failed', accepted=False, error=str(error), traceback=traceback.format_exc())
        persist()
        if owned or report['native_calls_live'] is not False:
            report['retained_process'] = True
            persist()
            while True:
                pythoncom.PumpWaitingMessages()
                time.sleep(.5)
        raise
    finally:
        persist()
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    for key in ('positive', 'faults'):
        parser.add_argument('--internal-' + key + '-report', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    args = parser.parse_args()
    require(args.run_solidworks, 'Explicit --run-solidworks is required.')
    args.state_dir = args.state_dir.resolve()
    require(args.state_dir.is_relative_to(Path.cwd() / 'work') and not args.state_dir.exists(),
        'Use a fresh private work/ directory.')
    args.state_dir.mkdir()
    started = time.perf_counter()
    report = dict(scope='installed_rectangle_stages_public_v1', accepted=False, public_rectangle_passed=False,
        native_b1_accepted=False, phase='preflight', cases=[], captures=[], owned_documents=[], native_calls_live=False,
        verifier_hashes=helper_hashes(Path(__file__).name))
    def persist():
        report['elapsed_seconds'] = time.perf_counter() - started
        (args.state_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')
    try:
        report.update(preflight(args))
    except BaseException as error:
        report.update(phase='preflight_failed', error=str(error))
        persist()
        raise
    _native_run(args, report, persist)
    print(json.dumps(dict(scope=report['scope'], public_rectangle_passed=report['public_rectangle_passed'],
        native_b1_accepted=False, elapsed_seconds=report['elapsed_seconds'])), flush=True)


if __name__ == '__main__':
    main()
