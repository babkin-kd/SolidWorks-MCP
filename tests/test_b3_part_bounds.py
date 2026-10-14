"""Finite public route over artificial results, not native B3 acceptance."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from test_b3_part_geometry import Reader, CONTEXT, FOREIGN, run as geometry_run

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    import verifier_b3_part_bounds as helper
    from verifier_b3_bounds_oracle import support_bounds
finally:
    sys.path.remove(scripts)

CYLINDER = dict(document_id='doc_cylinder', configuration='Основная',
                expected_observation_revision='obs_cylinder')


class BoundsReader:
    def __init__(self, fault=None):
        self.calls, self.fault = [], fault

    async def read(self, tool, args, *, expected_error=None):
        self.calls.append((tool, deepcopy(args)))
        if expected_error:
            code = 'unexpected' if self.fault == 'rejection' else expected_error
            return dict(status='failed', error=dict(code=code), result=None)
        context = CYLINDER if args['document_id'] == CYLINDER['document_id'] else CONTEXT
        if tool == 'body_list':
            value = dict(document_id=context['document_id'], configuration=context['configuration'],
                         observation_revision=context['expected_observation_revision'], total_count=1,
                         next_cursor=None, coordinate_frame='model', length_unit='mm', area_unit='mm2',
                         items=[dict(object_id='cylinder_body', kind='body', body_id=None, body_type='solid')])
            if self.fault == 'cylinder_census': value['total_count'] = True
            if self.fault == 'cylinder_units': value['length_unit'] = 'm'
        else:
            frame = args.get('coordinate_frame')
            cylinder = args['document_id'] == CYLINDER['document_id']
            body_id = args.get('body_id')
            ids = ['cylinder_body'] if cylinder else ([body_id] if body_id else ['body_0', 'body_1', 'body_2'])
            boxes = helper.BOXES if body_id is None else (helper.BOXES[int(body_id[-1])],)
            expected = support_bounds(boxes=boxes, cylinder=cylinder, frame=frame)
            value = dict(document_id=context['document_id'], configuration=context['configuration'],
                observation_revision=context['expected_observation_revision'], body_id=body_id,
                body_type='all', body_ids=ids, body_count=len(ids), length_unit='mm',
                measurement_scope='part_native_support_bounds_v1', method='native_extreme_points',
                includes_hidden_bodies=True, approximate_body_box_used=False, model_geometry_modified=False,
                read_postconditions=dict(body_membership_confirmed=True, repeated_extrema_confirmed=True),
                coordinate_frame=dict(kind='model' if frame is None else 'explicit_rigid',
                    **(frame or dict(origin_mm=[0., 0., 0.],
                       axes_in_model=[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]))),
                bounding_box_mm=expected)
            if self.fault == 'short_vector': value['bounding_box_mm']['size_mm'] = []
            if self.fault == 'wrong_support': value['bounding_box_mm']['max_mm'][0] += 1.
            if self.fault == 'wrong_frame': value['coordinate_frame']['kind'] = 'other'
        return dict(status='succeeded', error=None, result=value)


@pytest.fixture
def evidence():
    return geometry_run(Reader())[0]


def run(reader, evidence, *, changed=False, cylinder_failure=False):
    captures = []
    def capture():
        captures.append(True)
        return {'artificial_full_native': 'changed' if changed and len(captures) > 1 else 'same'}
    def cylinder(context, body):
        if cylinder_failure: raise ValueError('Cylinder is not the independently owned radius6/length30 fixture')
        assert context == CYLINDER and body['object_id'] == 'cylinder_body'
        return dict(artificial_cylinder_geometry=dict(radius_mm=6., length_mm=30.))
    return asyncio.run(helper.part_bounds_case(reader, context=CONTEXT, foreign_context=FOREIGN,
        cylinder_context=CYLINDER, geometry_evidence=evidence, capture_full=capture,
        capture_cylinder=cylinder))


def test_finite_bounds_reads_share_live_geometry_receipts(evidence):
    reader = BoundsReader()
    result = run(reader, evidence)
    assert len(reader.calls) == len(result['rows']) == 7
    assert len(result['expectations']) == 4
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    assert len({args['request_id'] for _, args in reader.calls}) == 7
    labels = [row['label'] for row in result['rows']]
    assert labels == ['cylinder_body_census', 'all_solids_and_surface', 'second_rotated_shifted',
                      'planar_zero_extent', 'cylinder_tilted_support', 'foreign_body', 'stale_observation']


@pytest.mark.parametrize('fault', ['cylinder_census', 'cylinder_units', 'short_vector',
                                  'wrong_support', 'wrong_frame', 'rejection'])
def test_invalid_public_evidence_stops_finite_route(evidence, fault):
    reader = BoundsReader(fault)
    with pytest.raises(ValueError): run(reader, evidence)
    assert len(reader.calls) <= 7


@pytest.mark.parametrize('change', ['old_revision', 'wrong_document', 'incomplete_refs',
                                   'missing_native_receipt', 'changed_before_after'])
def test_wrong_or_stale_prior_geometry_never_dispatches(evidence, change):
    if change == 'old_revision': evidence['rows'][0]['journal']['result']['observation_revision'] = 'old'
    elif change == 'wrong_document': evidence['rows'][0]['journal']['result']['document_id'] = 'foreign'
    elif change == 'incomplete_refs': evidence['native_references'].pop()
    elif change == 'missing_native_receipt': evidence['native_references'][0]['receipt'] = {}
    elif change == 'changed_before_after': evidence['after']['extra'] = 'changed'
    reader = BoundsReader()
    with pytest.raises(ValueError): run(reader, evidence)
    assert reader.calls == []


@pytest.mark.parametrize('arguments', [dict(changed=True), dict(cylinder_failure=True)])
def test_native_proof_mismatch_cannot_publish_success(evidence, arguments):
    with pytest.raises(ValueError): run(BoundsReader(), evidence, **arguments)
