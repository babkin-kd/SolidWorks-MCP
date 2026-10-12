"""Concrete finite B3-I02 public reads; fixture and CAD ownership stay external.

The driver supplies fresh explicit contexts and independent full/native proofs.
This handler never creates, mutates, closes or adopts a document. Its evidence
must still pass the final exact-wheel B3 acceptance gate.
"""
from copy import deepcopy
import inspect
import json
import math
import uuid


async def _call(callback, *args):
    result = callback(*args)
    return await result if inspect.isawaitable(result) else result


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _context(value):
    keys = {'document_id', 'configuration', 'expected_observation_revision'}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('Exact explicit observation context required.')
    if any(type(value[key]) is not str or not value[key] for key in keys):
        raise ValueError('Nonempty explicit context required.')
    return deepcopy(value)


def _proof(value):
    if type(value) is not dict or not value:
        raise ValueError('Complete independent raw proof required.')
    _canonical(value)
    return deepcopy(value)


def _near(actual, expected):
    if (type(actual) not in (int, float) or not math.isfinite(actual)
            or not math.isclose(actual, expected, rel_tol=0., abs_tol=1e-5)):
        raise ValueError('Native analytic geometry differs from the fixed fixture.')


async def part_geometry_case(reader, *, context, foreign_context,
                             inactive_configuration, capture_full, capture_reference):
    """Read two 20x10x5 solids and a 15x10 planar surface, without edits.

capture_full observes the complete owned part, dirty neighbor and session; it
must raise on incomplete/unsupported scope. capture_reference(context, item)
independently resolves the returned opaque reference and proves exact native
owner/current membership and the item's facts, raising on any mismatch. Neither
callback may merely repeat tool summaries. Both raw receipts are retained.
The handler does not authorize dispatch/cleanup; B3Reader and the owner do.
"""
    context, foreign_context = _context(context), _context(foreign_context)
    if foreign_context['document_id'] == context['document_id']:
        raise ValueError('A distinct owned foreign document required.')
    if (type(inactive_configuration) is not str or not inactive_configuration
            or inactive_configuration == context['configuration']):
        raise ValueError('Explicit existing inactive configuration required.')
    if not callable(capture_full) or not callable(capture_reference):
        raise ValueError('Independent complete and reference observers required.')
    before = _proof(await _call(capture_full))
    rows, native = [], []

    async def read(tool, *, ctx=None, error=None, **arguments):
        payload = dict(request_id='b3-i02-' + uuid.uuid4().hex,
                       **(context if ctx is None else ctx), **arguments)
        row = await reader.read(tool, payload, expected_error=error)
        rows.append(dict(tool=tool, arguments=payload, journal=deepcopy(row)))
        if error is not None:
            if row['status'] != 'failed' or row['error']['code'] != error:
                raise ValueError('Expected finite pre-read rejection missing.')
            return None
        if row['status'] != 'succeeded':
            raise ValueError('Nonterminal or failed geometry read.')
        result = row['result']
        if (result['document_id'] != context['document_id']
                or result['configuration'] != context['configuration']
                or result['observation_revision'] != context['expected_observation_revision']
                or result['coordinate_frame'] != 'model'
                or result['length_unit'] != 'mm' or result['area_unit'] != 'mm2'):
            raise ValueError('Geometry response context or native units differ.')
        return result

    async def pages(tool, count, *, limit=100, **arguments):
        items, seen, cursors, cursor = [], set(), set(), ''
        # A fixed census bounds the calls; even a cyclic/empty cursor cannot loop.
        for _ in range(count + 1):
            page = await read(tool, limit=limit, cursor=cursor, **arguments)
            if (type(page['total_count']) is not int or page['total_count'] != count
                    or type(page['items']) is not list):
                raise ValueError('Unexpected complete topology census.')
            if not 0 < len(page['items']) <= limit:
                raise ValueError('Empty or oversized topology page.')
            for item in page['items']:
                object_id = item.get('object_id')
                if type(object_id) is not str or not object_id or object_id in seen:
                    raise ValueError('Missing or repeated native object reference.')
                if tool != 'body_list' and item.get('body_id') != arguments['body_id']:
                    raise ValueError('Topology page belongs to another body.')
                if tool == 'body_list' and item.get('body_id') is not None:
                    raise ValueError('Body list unexpectedly claims a parent body.')
                expected_kind = {'body_list': 'body', 'face_list': 'face', 'edge_list': 'edge'}[tool]
                if item.get('kind') != expected_kind:
                    raise ValueError('Topology kind differs.')
                seen.add(object_id); items.append(item)
                if len(items) > count:
                    raise ValueError('Topology exceeds its exact census.')
            next_cursor = page['next_cursor']
            if next_cursor is None:
                if len(items) != count:
                    raise ValueError('Topology pagination is incomplete.')
                return items
            if type(next_cursor) is not str or not next_cursor or next_cursor in cursors:
                raise ValueError('Invalid or repeated topology cursor.')
            cursors.add(next_cursor); cursor = next_cursor
        raise ValueError('Finite topology page budget exceeded.')

    bodies = await pages('body_list', 3)
    solids = [body for body in bodies if body['body_type'] == 'solid']
    surfaces = [body for body in bodies if body['body_type'] == 'surface']
    if len(solids) != 2 or len(surfaces) != 1:
        raise ValueError('Exactly two solid bodies and one surface required.')
    surfaces = surfaces[0]
    # Approximate boxes are descriptive only; independent reference observers
    # bind actual identity/BREP. They never authorize mutation from these boxes.
    for body in solids:
        if body['face_count'] != 6 or body['edge_count'] != 12:
            raise ValueError('Solid body census differs from the fixture.')
        box = body['bounding_box_mm']
        if (type(box['min_mm']) is not list or type(box['max_mm']) is not list
                or len(box['min_mm']) != 3 or len(box['max_mm']) != 3):
            raise ValueError('Three complete body box coordinates required.')
        for low, high, size in zip(box['min_mm'], box['max_mm'], (20., 10., 5.)):
            _near(low, low); _near(high, high)
            _near(high - low, size)
    _near(abs(solids[0]['bounding_box_mm']['min_mm'][0]
              - solids[1]['bounding_box_mm']['min_mm'][0]), 40.)
    objects = list(bodies)
    roundtrips = {item['object_id'] for item in bodies}
    for index, body in enumerate((*solids, surfaces)):
        count_f, count_e, area, length = ((6, 12, 700., 140.) if index < 2
                                         else (1, 4, 150., 50.))
        faces = await pages('face_list', count_f, body_id=body['object_id'],
                            limit=2 if index == 0 else 100)
        edges = await pages('edge_list', count_e, body_id=body['object_id'])
        for item in faces:
            _near(item['area_mm2'], item['area_mm2'])
            if item['area_mm2'] <= 0: raise ValueError('Positive face area required.')
        for item in edges:
            _near(item['length_mm'], item['length_mm'])
            if item['length_mm'] <= 0: raise ValueError('Positive edge length required.')
        _near(sum(item['area_mm2'] for item in faces), area)
        _near(sum(item['length_mm'] for item in edges), length)
        objects.extend(faces); objects.extend(edges)
        if index in (0, 2):
            roundtrips.update((faces[0]['object_id'], edges[0]['object_id']))
    for item in objects:
        # Seven representative roundtrips cover all bodies and solid/surface
        # face/edge kinds. Every listed reference still has an independent
        # native membership receipt; repeating all 44 public gets adds no case.
        if item['object_id'] in roundtrips:
            resolved = await read('geometry_get', object_id=item['object_id'])
            if _canonical(resolved['object']) != _canonical(item):
                raise ValueError('List/get reference roundtrip differs.')
        receipt = _proof(await _call(capture_reference, deepcopy(context), deepcopy(item)))
        native.append(dict(object_id=item['object_id'], kind=item['kind'], receipt=receipt))
    await read('geometry_get', ctx=foreign_context,
               object_id=solids[0]['object_id'], error='object_reference_not_found')
    await read('body_list', ctx={**context, 'configuration': inactive_configuration},
               error='configuration_not_active')
    after = _proof(await _call(capture_full))
    if _canonical(before) != _canonical(after):
        raise ValueError('Complete part/neighbor/session proof changed during reads.')
    return dict(scope='bounded_b3_i02_geometry_evidence_v1', rows=rows,
                native_references=native, roundtrip_ids=sorted(roundtrips),
                before=before, after=after,
                accepted=False, native_acceptance=False,
                cleanup_authorized=False)
