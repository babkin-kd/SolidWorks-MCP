"""Finite B3 scheduling and evidence recording, without native acceptance.

No COM, fixture creation or cleanup occurs here. The installed native driver
must supply its own exact ownership/supervisor gate and independent oracles.
Recording thirteen callbacks is never proof that their CAD assertions passed.
"""
from copy import deepcopy
from dataclasses import dataclass
import inspect
import json


@dataclass(frozen=True)
class Case:
    identifier: str
    condition: str
    fixture: str
    checks: tuple[str, ...]
    tools: tuple[str, ...]


MANIFEST = (
    Case('B3-I01', 'N1', 'part',
         ('two_documents', 'configuration_metadata_without_activation',
          'feature_dimension_membership', 'rectangle_sketch', 'native_units'),
         ('document_list', 'document_get', 'feature_list', 'feature_get',
          'dimension_list', 'dimension_get', 'sketch_get')),
    Case('B3-I02', 'N1', 'part',
         ('solid_surface_membership', 'complete_pagination', 'foreign_body',
          'inactive_configuration', 'analytic_area_length'),
         ('body_list', 'face_list', 'edge_list', 'geometry_get')),
    Case('B3-I03', 'N2', 'assembly',
         ('repeated_instances', 'referenced_configurations', 'nested_path',
          'independent_transform', 'foreign_instance_owner'),
         ('component_list', 'component_get', 'component_body_list',
          'component_body_get', 'component_face_list', 'component_edge_list',
          'component_topology_get')),
    Case('B3-I04', 'N3', 'assembly',
         ('feature_rename_same_identity', 'instance_rename_same_identity',
          'original_face_reference'), ('feature_get', 'component_topology_get')),
    Case('B3-I05', 'N3', 'assembly',
         ('deleted_instance_reference_rejected', 'same_file_new_incarnation',
          'retired_face_reference_rejected'), ('component_get', 'component_topology_get')),
    Case('B3-I06', 'N3', 'assembly',
         ('configuration_replacement_retires_refs', 'fresh_body_roster',
          'inactive_part_reference_rejected'),
         ('component_body_list', 'component_topology_get', 'geometry_get')),
    Case('B3-I07', 'N4', 'part',
         ('all_solid_mass', 'explicit_solid_mass', 'native_density',
          'hidden_included_surface_excluded', 'exact_selection_restore'),
         ('measurement_prepare_mass', 'measurement_get_mass')),
    Case('B3-I08', 'N4', 'part',
         ('rotated_shifted_bounds', 'planar_zero_extent', 'tilted_cylinder_support',
          'reflection_foreign_stale_rejected'), ('measurement_get_bounds',)),
    Case('B3-I09', 'N4', 'assembly',
         ('pair_15mm', 'nested_70mm', 'root_witnesses', 'complete_solid_census'),
         ('measurement_get_component_distance',)),
    Case('B3-I10', 'N4', 'assembly',
         ('point_trimmed_corner', 'axis_gap_and_intersection', 'explicit_frame',
          'native_original_witnesses'),
         ('measurement_get_component_point_distance', 'measurement_get_component_axis_distance')),
    Case('B3-I11', 'N4', 'assembly',
         ('part_subassembly_70mm', 'repeated_subassemblies_84mm',
          'complete_leaf_pairs', 'hidden_nearest', 'explicit_frame'),
         ('measurement_get_component_aggregate_distance',)),
    Case('B3-I12', 'N4', 'assembly',
         ('aggregate_point_inside_outside', 'aggregate_axis_gap_intersection',
          'complete_leaf_body_face_census', 'surface_only_rejected', 'explicit_frame'),
         ('measurement_get_component_aggregate_point_distance',
          'measurement_get_component_aggregate_axis_distance')),
    Case('B3-I13', 'N5', 'final',
         ('passive_replay_no_dispatch', 'guarded_mass_replay_no_dispatch',
          'all_cases_preserve_neighbor_and_ui', 'terminal_quiescence',
          'exact_owned_cleanup', 'full_baseline_restored'),
         ('geometry_get', 'measurement_get_mass')),
)


def manifest_rows():
    return [dict(identifier=case.identifier, condition=case.condition,
                 fixture=case.fixture, checks=list(case.checks), tools=list(case.tools))
            for case in MANIFEST]


def required_tools():
    return frozenset(tool for case in MANIFEST for tool in case.tools)


def execution_order():
    """Two fixture sessions; topology changes precede measurements of fresh refs.

    A concrete driver's assembly handlers must use independent controlled
    members for destructive reference tests, rather than alter metric fixtures.
    Replay receipts must be collected while each corresponding fixture/session
    is live. Final I13 validates these collected receipts and the two cleanups;
    it cannot send an old opaque reference into the next fixture session.
    """
    identifiers = ('B3-I01', 'B3-I02', 'B3-I07', 'B3-I08',
                   'B3-I03', 'B3-I04', 'B3-I05', 'B3-I06',
                   'B3-I09', 'B3-I10', 'B3-I11', 'B3-I12', 'B3-I13')
    cases = {case.identifier: case for case in MANIFEST}
    return tuple(cases[identifier] for identifier in identifiers)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':'))


def validate_handlers(handlers):
    identifiers = {case.identifier for case in MANIFEST}
    if type(handlers) is not dict or set(handlers) != identifiers:
        raise ValueError('All thirteen exact B3 handlers required; no selective or extra cases.')
    if not all(callable(handler) for handler in handlers.values()):
        raise ValueError('Each B3 handler must be callable.')


async def _call(callback, *arguments):
    value = callback(*arguments)
    return await value if inspect.isawaitable(value) else value


async def run_manifest(*, handlers, assert_dispatch_safe, persist, identity):
    """Record a finite run, leaving acceptance to independent report gates.

    assert_dispatch_safe must drain/check the concrete supervisor and journal
    before *each* handler and after it. An exception (including cancellation)
    retains the running row and prevents any later handler or automatic cleanup.
    Persist failure also stops scheduling; native effects cannot be retried here.
    Identity contains the driver-validated installed wheel/helper fingerprints.
    """
    validate_handlers(handlers)
    if not callable(assert_dispatch_safe) or not callable(persist):
        raise ValueError('Explicit safety and durable persistence callbacks required.')
    if type(identity) is not dict or not identity:
        raise ValueError('Validated installed candidate identity required.')
    _json(identity)
    report = dict(scope='bounded_b3_evidence_schedule_v1', identity=deepcopy(identity),
                  manifest=manifest_rows(), phase='prepared', rows=[],
                  schedule_completed=False, accepted=False, native_acceptance=False)
    await _call(persist, deepcopy(report))
    for case in execution_order():
        # Do not dispatch a second case while a previous call/hold is uncertain.
        await _call(assert_dispatch_safe)
        report['phase'] = case.identifier
        row = dict(identifier=case.identifier, state='running', evidence=None)
        report['rows'].append(row)
        await _call(persist, deepcopy(report))
        evidence = await _call(handlers[case.identifier], case)
        # Native-return alone is insufficient; callbacks can leave an unknown job.
        await _call(assert_dispatch_safe)
        if type(evidence) is not dict or not evidence:
            raise ValueError('A nonempty raw evidence object is required; no passed flag shortcut.')
        _json(evidence)
        row.update(state='recorded', evidence=deepcopy(evidence))
        await _call(persist, deepcopy(report))
    report.update(phase='awaiting_independent_acceptance', schedule_completed=True)
    await _call(persist, deepcopy(report))
    return deepcopy(report)
