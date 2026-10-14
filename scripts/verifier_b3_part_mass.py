"""Finite B3-I07 prepare/guarded mass evidence; no CAD or fixture lifecycle.

The live owner supplies independent native producers and a B3Reader. Durable
job_get/SQLite/checkpoint binding belongs to that reader, not this oracle.
"""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _context, _proof

SCOPE = 'part_mass_selection_measurement_v1'


def _number(value, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (positive and value <= 0)):
        raise ValueError('Finite native numeric measurement required.')
    return value


def _near(value, expected, *, relative=0., absolute=1e-6):
    if not math.isclose(_number(value), expected, rel_tol=relative, abs_tol=absolute):
        raise ValueError('Mass measurement differs from independent native/analytic oracle.')


def _live_bodies(evidence, context):
    if (type(evidence) is not dict
            or evidence.get('scope') != 'bounded_b3_i02_geometry_evidence_v1'
            or evidence.get('accepted') is not False or evidence.get('native_acceptance') is not False
            or _canonical(evidence.get('before')) != _canonical(evidence.get('after'))):
        raise ValueError('Completed live I02 geometry evidence required.')
    _proof(evidence['before']); _proof(evidence['after'])
    listings = [row for row in evidence['rows']
                if row['tool'] == 'body_list' and row['journal']['status'] == 'succeeded']
    if len(listings) != 1:
        raise ValueError('One exact I02 body census required.')
    listing = listings[0]['journal']['result']
    if (listing.get('document_id') != context['document_id']
            or listing.get('configuration') != context['configuration']
            or listing.get('observation_revision') != context['expected_observation_revision']
            or type(listing.get('total_count')) is not int or listing['total_count'] != 3
            or listing.get('next_cursor') is not None):
        raise ValueError('I02 body context is stale or incomplete.')
    bodies = listing['items']
    ids = [body['object_id'] for body in bodies]
    solids = sorted((body for body in bodies if body['body_type'] == 'solid'),
                    key=lambda body: body['bounding_box_mm']['min_mm'][0])
    surfaces = [body for body in bodies if body['body_type'] == 'surface']
    if (len(ids) != 3 or len(solids) != 2 or len(surfaces) != 1 or len(set(ids)) != 3
            or any(type(value) is not str or not value for value in ids)):
        raise ValueError('Exact two-solid/one-surface I02 roster required.')
    references = evidence['native_references']
    native_ids = [row['object_id'] for row in references]
    if len(native_ids) != 44 or len(set(native_ids)) != 44 or not set(ids) <= set(native_ids):
        raise ValueError('Complete independent I02 reference receipts required.')
    for row in references:
        _proof(row['receipt'])
    return solids, surfaces


def _native_scope(value, *, context, body_id, solids, surfaces):
    value = _proof(value)
    if (_canonical(value.get('context')) != _canonical(context)
            or value.get('body_id') != body_id):
        raise ValueError('Independent native mass scope belongs to another context/body.')
    ids = [body['object_id'] for body in solids]
    expected = ids if body_id is None else [body_id]
    for key, roster in (('body_ids', expected),
                        ('excluded_surface_body_ids', [body['object_id'] for body in surfaces])):
        actual = value.get(key)
        if (type(actual) is not list or len(actual) != len(roster)
                or len(set(actual)) != len(actual) or set(actual) != set(roster)):
            raise ValueError('Independent solid/surface mass roster differs.')
    hidden = value.get('hidden_solid_body_ids')
    if (type(hidden) is not list or len(set(hidden)) != len(hidden)
            or not set(hidden) <= set(ids) or ids[1] not in hidden):
        raise ValueError('Second solid must independently be observed hidden and included.')
    if value.get('density_source') != 'independent_native_effective':
        raise ValueError('Density must be independently observed from native effective scope.')
    density = _number(value.get('effective_density_kg_m3'), positive=True)
    densities = value.get('solid_densities_kg_m3')
    if type(densities) is not dict or set(densities) != set(ids):
        raise ValueError('Independent effective densities of both solids required.')
    for actual in densities.values():
        _number(actual, positive=True)
        _near(actual, density, relative=1e-12, absolute=0.)
    overrides = value.get('overrides')
    if (type(overrides) is not dict or set(overrides) != {'document', *ids}
            or any(type(flags) is not dict or set(flags) != {'mass', 'center_of_mass'}
                   or flags['mass'] is not False or flags['center_of_mass'] is not False
                   for flags in overrides.values())):
        raise ValueError('Independent document/both-body no-overrides flags required.')
    # Ordered native identities/PIDs and marks are observed outside the result.
    selection = value.get('selection')
    if type(selection) is not list or not selection:
        raise ValueError('Independent nonempty foreign UI-body selection receipt required.')
    for item in selection:
        if (type(item) is not dict or type(item.get('mark')) is not int
                or type(item.get('native_identity')) is not int or item['native_identity'] <= 0
                or type(item.get('persistent_id')) is not str or not item['persistent_id']):
            raise ValueError('Exact native selected-object identities/PIDs/marks required.')
        try:
            canonical_pid = bytes.fromhex(item['persistent_id']).hex()
        except ValueError as exc:
            raise ValueError('Selected native PID must be canonical lowercase bytes.hex().') from exc
        if canonical_pid != item['persistent_id']:
            raise ValueError('Selected native PID must be canonical lowercase bytes.hex().')
    if not any(item.get('object_id') == ids[0] for item in selection):
        raise ValueError('First solid must be the independently selected foreign UI body.')
    _proof(value.get('native_receipt'))
    return value


def _validate_prepared(value, *, context, body_id, count):
    if (type(value) is not dict or value.get('document_id') != context['document_id']
            or value.get('configuration') != context['configuration'] or value.get('body_id') != body_id
            or type(value.get('revision')) is not str or not value['revision']
            or value.get('revision_scope') != SCOPE or type(value.get('body_count')) is not int
            or value['body_count'] != count or value.get('coordinate_frame') != 'model'
            or value.get('includes_hidden_bodies') is not True
            or value.get('model_geometry_modified') is not False
            or value.get('ui_effect') != 'temporary_selection_with_durable_application_guard'):
        raise ValueError('Public preparation differs from exact guarded mass contract.')


def _validate_mass(value, *, context, body_id, count, revision, native):
    if (type(value) is not dict or value.get('document_id') != context['document_id']
            or value.get('configuration') != context['configuration']
            or value.get('observation_revision') != context['expected_observation_revision']
            or value.get('body_id') != body_id or type(value.get('body_count')) is not int
            or value['body_count'] != count or value.get('measurement_revision') != revision
            or value.get('revision_scope') != SCOPE or value.get('verified') is not True
            or value.get('model_geometry_modified') is not False
            or value.get('includes_hidden_bodies') is not True or value.get('coordinate_frame') != 'model'
            or any(value.get(key) != unit for key, unit in
                   (('length_unit', 'mm'), ('area_unit', 'mm2'), ('volume_unit', 'mm3'), ('mass_unit', 'kg')))
            or value.get('density_source') != 'solidworks_effective'):
        raise ValueError('Public mass scope, units or guarded read postconditions differ.')
    guard = value.get('execution_guard') or {}
    if (type(guard) is not dict or guard.get('scope') != 'application_model_mutation_guard_v1'
            or guard.get('released') is not True or guard.get('acquired') is not True
            or guard.get('selection_preserved') is not True
            or guard.get('original_command_in_progress') is not False
            or _canonical(guard.get('model_guards')) !=
               _canonical([dict(original_state=0, locked_state=2, released_state=0)])):
        raise ValueError('Temporary application/selection guard was not confirmed released.')
    properties = value.get('mass_properties') or {}
    if type(properties) is not dict:
        raise ValueError('Complete mass properties object required.')
    volume, area = count * 1000., count * 700.
    center = properties.get('center_of_mass_mm')
    if type(center) is not list or len(center) != 3:
        raise ValueError('Three complete center-of-mass coordinates required.')
    for actual, expected in zip(center, [30. if count == 2 else 50., 5., 2.5]):
        _near(actual, expected)
    _near(properties.get('volume_mm3'), volume)
    _near(properties.get('surface_area_mm2'), area)
    density = native['effective_density_kg_m3']
    _near(properties.get('density_kg_m3'), density, relative=1e-6, absolute=0.)
    expected_mass = volume * density / 1e9
    _near(properties.get('mass_kg'), expected_mass, relative=1e-6, absolute=1e-12)
    return dict(volume_mm3=volume, surface_area_mm2=area, center_of_mass_mm=center,
                independent_density_kg_m3=density, expected_mass_kg=expected_mass,
                center_absolute_tolerance_mm=1e-6,
                area_absolute_tolerance_mm2=1e-6,
                volume_absolute_tolerance_mm3=1e-6, mass_relative_tolerance=1e-6,
                mass_absolute_tolerance_kg=1e-12)


async def part_mass_case(reader, *, context, geometry_evidence, capture_full, capture_mass_scope):
    """Two preparation+guarded mass chains: all solids and explicit second solid.

capture_full() MUST independently prove the complete part BREP/rosters,
dirty neighbor, files/config/active/visibility, ordered selection identities
and marks, view, CIP/locks and session. It raises for incomplete native scope.
capture_mass_scope(context, body_id) MUST independently resolve I02 refs,
prove the actual block positions/dimensions, hidden second solid, excluded
surface, unambiguous effective native density (no overrides), and nonempty
    first-solid UI selection (foreign to explicit second-solid measurement,
    within the same part, not a neighboring document's selection); raw evidence
    is returned under native_receipt.
Its typed fields are context, body_id, body_ids, excluded_surface_body_ids,
hidden_solid_body_ids, density_source='independent_native_effective',
    effective_density_kg_m3 and selection=[{native_identity,persistent_id,mark}].
    solid_densities_kg_m3 maps both solid IDs to independently observed native
    densities, equal to the effective scope density. overrides maps 'document'
    and both solid IDs to {mass:false,center_of_mass:false}. Selection includes
    the first solid under object_id, independently resolved from its native PID.
    persistent_id is nonempty canonical lowercase bytes.hex(). native_identity
    is a positive, stable capture-local ordinal, assigned by the owner using
    held IUnknown equality throughout both chains; never a name, Python id,
    pointer or pointer repr. Density uniformity tolerance is relative 1e-12.
The density observer cannot derive density from the returned tool mass result.
Both callbacks run before/after each chain; no selection edits occur here.
"""
    context = _context(context)
    if not callable(capture_full) or not callable(capture_mass_scope):
        raise ValueError('Independent complete state and effective native density producers required.')
    solids, surfaces = _live_bodies(geometry_evidence, context)
    rows, chains = [], []

    async def read(label, tool, **arguments):
        payload = dict(request_id='b3-i07-' + uuid.uuid4().hex, **context, **arguments)
        row = await reader.read(tool, payload)
        rows.append(dict(label=label, tool=tool, arguments=payload, journal=deepcopy(row)))
        if row.get('status') != 'succeeded' or row.get('error') is not None:
            raise ValueError('Nonterminal, unknown or failed mass route; never redispatch.')
        return row['result']

    for label, body_id, count in (('all_solids', None, 2),
                                  ('explicit_second_solid', solids[1]['object_id'], 1)):
        before = _proof(await _call(capture_full))
        if chains and _canonical(chains[-1]['after']) != _canonical(before):
            raise ValueError('Full native baseline changed between mass chains.')
        native_before = _native_scope(await _call(capture_mass_scope, deepcopy(context), body_id),
                                      context=context, body_id=body_id, solids=solids, surfaces=surfaces)
        prepared = await read(label + '_prepare', 'measurement_prepare_mass', body_id=body_id)
        _validate_prepared(prepared, context=context, body_id=body_id, count=count)
        value = await read(label + '_mass', 'measurement_get_mass', body_id=body_id,
                           expected_revision=prepared['revision'])
        expectation = _validate_mass(value, context=context, body_id=body_id, count=count,
                                     revision=prepared['revision'], native=native_before)
        native_after = _native_scope(await _call(capture_mass_scope, deepcopy(context), body_id),
                                     context=context, body_id=body_id, solids=solids, surfaces=surfaces)
        after = _proof(await _call(capture_full))
        if (_canonical(before) != _canonical(after)
                or _canonical(native_before) != _canonical(native_after)):
            raise ValueError('Full native part/dirty-neighbor/session/density/selection changed.')
        chains.append(dict(label=label, before=before, after=after,
                           native_before=native_before, native_after=native_after, oracle=expectation))
    return dict(scope='bounded_b3_i07_public_mass_evidence_v1', rows=rows, chains=chains,
                before=chains[0]['before'], after=chains[-1]['after'],
                accepted=False, native_acceptance=False, cleanup_authorized=False)
