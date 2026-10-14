"""Finite positive/foreign/stale B3-I08 public route, without fixture edits.

Reflection input is rejected by the public typed schema before a durable job;
its internal domain rejection remains a separate manifest check. This route
records actual journal rows and analytic/full-state proofs, never accepts B3.
"""
from copy import deepcopy
import math
import uuid

from verifier_b3_bounds_oracle import BOXES, validate_bounds
from verifier_b3_part_geometry import _call, _canonical, _context, _proof


async def part_bounds_case(reader, *, context, foreign_context, cylinder_context,
                           geometry_evidence, capture_full, capture_cylinder):
    context = _context(context)
    foreign_context, cylinder_context = _context(foreign_context), _context(cylinder_context)
    if len({ctx['document_id'] for ctx in (context, foreign_context, cylinder_context)}) != 3:
        raise ValueError('Three distinct explicit owned part fixtures required.')
    if not callable(capture_full) or not callable(capture_cylinder):
        raise ValueError('Independent full-state and cylinder geometry observers required.')
    if (type(geometry_evidence) is not dict
            or geometry_evidence.get('scope') != 'bounded_b3_i02_geometry_evidence_v1'
            or geometry_evidence.get('accepted') is not False
            or geometry_evidence.get('native_acceptance') is not False
            or _canonical(geometry_evidence.get('before')) != _canonical(geometry_evidence.get('after'))):
        raise ValueError('Completed live I02 evidence required, not an old accepted wheel.')
    _proof(geometry_evidence['before']); _proof(geometry_evidence['after'])
    listings = [row for row in geometry_evidence['rows']
                if row['tool'] == 'body_list' and row['journal']['status'] == 'succeeded']
    if len(listings) != 1:
        raise ValueError('One exact complete I02 body listing required.')
    listing = listings[0]['journal']['result']
    if (listing['document_id'] != context['document_id']
            or listing['configuration'] != context['configuration']
            or listing['observation_revision'] != context['expected_observation_revision']
            or listing['total_count'] != 3 or listing['next_cursor'] is not None):
        raise ValueError('I02 reference context is stale or incomplete.')
    bodies = listing['items']
    solids = sorted((body for body in bodies if body['body_type'] == 'solid'),
                    key=lambda body: body['bounding_box_mm']['min_mm'][0])
    surfaces = [body for body in bodies if body['body_type'] == 'surface']
    ids = [body['object_id'] for body in bodies]
    if len(bodies) != 3 or len(solids) != 2 or len(surfaces) != 1 or len(set(ids)) != 3:
        raise ValueError('Exact I02 solid/surface body census required.')
    native_ids = [row['object_id'] for row in geometry_evidence['native_references']]
    for row in geometry_evidence['native_references']: _proof(row['receipt'])
    if len(native_ids) != 44 or len(set(native_ids)) != 44 or not set(ids) <= set(native_ids):
        raise ValueError('I02 independent native reference receipts incomplete.')
    before = _proof(await _call(capture_full))
    rows, expectations = [], []

    async def read(label, tool='measurement_get_bounds', *, ctx=None, error=None, **arguments):
        ctx = context if ctx is None else ctx
        payload = dict(request_id='b3-i08-' + uuid.uuid4().hex, **ctx, **arguments)
        row = await reader.read(tool, payload, expected_error=error)
        rows.append(dict(label=label, tool=tool, arguments=payload, journal=deepcopy(row)))
        if error is not None:
            if row['status'] != 'failed' or row['error']['code'] != error:
                raise ValueError('Finite bounds pre-read rejection missing.')
            return None
        if row['status'] != 'succeeded':
            raise ValueError('Nonterminal or failed bounds read.')
        return row['result']

    cylinder = await read('cylinder_body_census', 'body_list', ctx=cylinder_context)
    if (cylinder['document_id'] != cylinder_context['document_id']
            or cylinder['configuration'] != cylinder_context['configuration']
            or cylinder['observation_revision'] != cylinder_context['expected_observation_revision']
            or type(cylinder['total_count']) is not int or cylinder['total_count'] != 1
            or cylinder['coordinate_frame'] != 'model' or cylinder['length_unit'] != 'mm'
            or cylinder['area_unit'] != 'mm2' or cylinder['next_cursor'] is not None
            or len(cylinder['items']) != 1 or cylinder['items'][0]['body_type'] != 'solid'
            or cylinder['items'][0]['kind'] != 'body' or cylinder['items'][0]['body_id'] is not None):
        raise ValueError('Exact own single solid cylinder census required.')
    cylinder_id = cylinder['items'][0]['object_id']
    if type(cylinder_id) is not str or not cylinder_id:
        raise ValueError('Exact cylinder opaque body reference required.')
    # Producer independently proves radius6, length30 and model-Y direction,
    # native owner/current body membership; tool summary alone is not the oracle.
    cylinder_proof = _proof(await _call(capture_cylinder, deepcopy(cylinder_context),
                                       deepcopy(cylinder['items'][0])))
    c, s = math.cos(math.pi/6), math.sin(math.pi/6)
    rotated = dict(origin_mm=[10., -20., 3.],
                   axes_in_model=[[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])
    tilted = dict(origin_mm=[10., -20., 3.],
                  axes_in_model=[[c, 0., -s], [0., 1., 0.], [s, 0., c]])
    for label, ctx, query, oracle in (
        ('all_solids_and_surface', context, {}, dict(body_ids=ids)),
        ('second_rotated_shifted', context,
         dict(body_id=solids[1]['object_id'], coordinate_frame=rotated),
         dict(body_ids=[solids[1]['object_id']], body_id=solids[1]['object_id'],
              boxes=(BOXES[1],), frame=rotated)),
        ('planar_zero_extent', context, dict(body_id=surfaces[0]['object_id']),
         dict(body_ids=[surfaces[0]['object_id']], body_id=surfaces[0]['object_id'], boxes=(BOXES[2],))),
        ('cylinder_tilted_support', cylinder_context, dict(coordinate_frame=tilted),
         dict(body_ids=[cylinder_id], cylinder=True, frame=tilted))):
        value = await read(label, ctx=ctx, **query)
        expectation = validate_bounds(value, context=ctx, **oracle)
        expectations.append(dict(label=label, oracle=expectation))
    await read('foreign_body', ctx=foreign_context, body_id=solids[0]['object_id'],
               error='object_reference_not_found')
    await read('stale_observation', ctx={**context, 'expected_observation_revision': 'obsolete-b3-i08'},
               error='observation_revision_mismatch')
    after = _proof(await _call(capture_full))
    if _canonical(before) != _canonical(after):
        raise ValueError('Complete native parts/neighbor/session changed during bounds reads.')
    return dict(scope='bounded_b3_i08_public_bounds_evidence_v1', rows=rows,
                expectations=expectations, cylinder_proof=cylinder_proof,
                before=before, after=after, accepted=False, native_acceptance=False,
                cleanup_authorized=False)
