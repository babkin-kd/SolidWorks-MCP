"""B3-I01 feature/dimension list-to-get route; native ownership stays external."""
from copy import deepcopy
import math
import uuid

from verifier_b3_part_geometry import _call, _canonical, _proof

SCOPE = 'bounded_b3_i01_part_object_evidence_v1'
REFERENCE_FAILURES = {'persistent_reference_unavailable', 'persistent_reference_mismatch',
                      'object_reference_invalid', 'object_deleted', 'object_suppressed'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def summary(row):
    return {k: v for k, v in row.items() if k not in ('object_id', 'persistent_reference_supported',
                                                   'reference_error', 'native_incarnation')}


def dimension_units(row):
    unit = row['unit']
    require(type(row['parameter_type']) is int, 'Exact native dimension parameter type required.')
    require(type(row['values_si']) is dict and row['values_si']
            and set(row['values']) == set(row['values_si']), 'Full configuration dimension values required.')
    for cfg, si in row['values_si'].items():
        value = row['values'][cfg]
        require(type(si) in (int, float) and math.isfinite(si)
                and type(value) in (int, float) and math.isfinite(value), 'Finite native/user values required.')
        expected = si*1000. if unit == 'mm' else math.degrees(si) if unit == 'deg' else si
        require(math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-9), 'Dimension SI/user unit conversion differs.')
    require((unit == 'mm' and row['parameter_type'] == 0) or
            (unit == 'deg' and row['parameter_type'] == 1) or
            (unit is None and row['parameter_type'] not in (0, 1)), 'Native dimension type/unit differs.')


async def part_objects_case(reader, *, context, capture_full, capture_inventory):
    """Observe one active part's complete bounded feature and dimension inventories.

capture_inventory(context, family) independently reads the original current
native feature/dimension census (not tool rows), returning rows whose summary
contains actual native fields (including dimension reference_anchor), positive
native_identity ordinals, reference_supported and native_receipt. Generated
opaque IDs/native_incarnation are excluded from native summary. The trusted
owner proves original canonical/configuration/owner membership and PID/display
anchor facts, including truthful unsupported references. capture_full reads
the complete part, dirty neighbor and whole session before/after.

Sketch read on the separate same-wheel B1 rectangle remains a distinct I01 gate.
No fixture creation, mutation, COM connection, cleanup or acceptance here.
"""
    require(type(context) is dict and set(context) == {'document_id', 'configuration'}
            and all(type(x) is str and x for x in context.values()), 'Explicit part/configuration context required.')
    require(callable(capture_full) and callable(capture_inventory), 'Independent current native producers required.')
    context = deepcopy(context)
    before = _proof(await _call(capture_full))
    rows, inventories = [], []

    async def read(tool, **arguments):
        args = dict(request_id='b3-i01-objects-'+uuid.uuid4().hex, **context, **arguments)
        row = await reader.read(tool, args)
        require(row['status'] == 'succeeded' and row['error'] is None, 'Normally terminal object read required.')
        rows.append(dict(tool=tool, arguments=args, journal=deepcopy(row)))
        value = row['result']
        require(value['document_id'] == context['document_id'] and value['configuration'] == context['configuration'],
                'Exact original current part/configuration required.')
        return value

    for family, scope in (('feature', 'part_feature_tree_v1'), ('dimension', 'part_dimension_values_v1')):
        native = _proof(await _call(capture_inventory, deepcopy(context), family))
        require(type(native['rows']) is list and 0 < len(native['rows']) <= 100,
                'Complete finite nonempty native object census required.')
        page = await read(family+'_list', limit=100, cursor='')
        require(page['revision_scope'] == scope and type(page['total_count']) is int
                and page['total_count'] == len(native['rows']) and page['next_cursor'] is None
                and type(page['items']) is list and len(page['items']) == len(native['rows']),
                'Complete current object list required; no partial page acceptance.')
        require(type(page['revision']) is str and page['revision'].startswith('rev_'), 'Actual domain revision required.')
        seen_ids, seen_native = set(), set()
        for item, proof in zip(page['items'], native['rows']):
            _proof(proof)
            identity = proof['native_identity']
            require(type(identity) is int and identity > 0 and identity not in seen_native,
                    'Distinct retained native object incarnations required.')
            seen_native.add(identity)
            _proof(proof['native_receipt'])
            require(type(proof['reference_supported']) is bool
                    and proof['reference_supported'] is item['persistent_reference_supported']
                    and _canonical(summary(item)) == _canonical(proof['summary']),
                    'Independent actual native object/anchor facts differ.')
            if family == 'dimension': dimension_units(item)
            object_id = item['object_id']
            if not proof['reference_supported']:
                require(object_id is None and type(item['reference_error']) is dict
                        and item['reference_error']['code'] in REFERENCE_FAILURES,
                        'Unsupported native row must expose a declared reason and null ID.')
                continue
            require(type(object_id) is str and object_id and object_id not in seen_ids
                    and item['reference_error'] is None, 'Exact supported original reference required.')
            seen_ids.add(object_id)
            got = await read(family+'_get', object_id=object_id)
            require(got['revision_scope'] == scope and got['revision'] == page['revision']
                    and got[family]['object_id'] == object_id
                    and _canonical(summary(got[family])) == _canonical(summary(item)),
                    'Object list/get current revision or native facts differ.')
        closing = _proof(await _call(capture_inventory, deepcopy(context), family))
        require(_canonical(native) == _canonical(closing), 'Current native census/owner/anchors changed during reads.')
        inventories.append(dict(family=family, before=native, after=closing))
    after = _proof(await _call(capture_full))
    require(_canonical(before) == _canonical(after), 'Full original part/neighbor/session changed.')
    return dict(scope=SCOPE, rows=rows, inventories=inventories, before=before, after=after,
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['same_wheel_B1_sketch_read', 'actual_current_native_producers',
                    'exact_installed_B3_driver', 'terminal_owned_cleanup'])
