"""Artificial public result fixtures; no installed-wheel or native acceptance."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_part_geometry import part_geometry_case
finally:
    sys.path.remove(scripts)


CONTEXT = dict(document_id='doc_a', configuration='Основная',
               expected_observation_revision='obs_a')
FOREIGN = dict(document_id='doc_b', configuration='Основная',
               expected_observation_revision='obs_b')


class Reader:
    def __init__(self, corrupt=None):
        self.calls, self.corrupt = [], corrupt
        self.bodies, self.objects, self.faces, self.edges = [], {}, {}, {}
        for index in range(3):
            body_id = f'body_{index}'
            solid = index < 2
            body = dict(object_id=body_id, kind='body', body_id=None,
                        body_type='solid' if solid else 'surface', name=f'Тело {index}',
                        face_count=6 if solid else 1, edge_count=12 if solid else 4,
                        bounding_box_mm=dict(min_mm=[40. * index, 0., 0.],
                                             max_mm=[40. * index + (20. if solid else 15.),
                                                     10., 5. if solid else 0.]))
            self.bodies.append(body); self.objects[body_id] = body
            faces = [dict(object_id=f'{body_id}_face_{n}', kind='face', body_id=body_id,
                          area_mm2=700./6 if solid else 150., surface_type='plane', edge_count=4)
                     for n in range(6 if solid else 1)]
            edges = [dict(object_id=f'{body_id}_edge_{n}', kind='edge', body_id=body_id,
                          length_mm=140./12 if solid else 12.5, curve_type='line',
                          start_mm=[0., 0., 0.], end_mm=[1., 0., 0.])
                     for n in range(12 if solid else 4)]
            self.faces[body_id], self.edges[body_id] = faces, edges
            self.objects.update({item['object_id']: item for item in (*faces, *edges)})

    async def read(self, tool, args, *, expected_error=None):
        self.calls.append((tool, deepcopy(args)))
        if expected_error:
            return dict(status='failed', error=dict(code=expected_error), result=None)
        result = dict(document_id=CONTEXT['document_id'], configuration=CONTEXT['configuration'],
                      observation_revision=CONTEXT['expected_observation_revision'],
                      coordinate_frame='model', length_unit='mm', area_unit='mm2')
        if tool == 'geometry_get':
            result['object'] = deepcopy(self.objects[args['object_id']])
        else:
            items = (self.bodies if tool == 'body_list' else
                     (self.faces if tool == 'face_list' else self.edges)[args['body_id']])
            offset = int(args['cursor'] or 0)
            result.update(items=deepcopy(items[offset:offset + args['limit']]),
                          total_count=len(items),
                          next_cursor=(str(offset + args['limit'])
                                       if offset + args['limit'] < len(items) else None))
        if self.corrupt: self.corrupt(tool, args, result)
        return dict(status='succeeded', error=None, result=result)


def run(reader, *, changed=False, reference_error=False, **overrides):
    captures, refs = [], []
    def full():
        captures.append(True)
        return dict(artificial_complete_fixture={'brep': 'full', 'neighbor': 'dirty',
                    'session': 'changed' if changed and len(captures) > 1 else 'same'})
    def reference(context, item):
        if reference_error: raise ValueError('Independent owner/membership differs.')
        refs.append(item['object_id'])
        assert context == CONTEXT
        assert item == reader.objects[item['object_id']]
        return dict(artificial_native_receipt=item['object_id'])
    args = dict(context=CONTEXT, foreign_context=FOREIGN,
                inactive_configuration='Вариант', capture_full=full,
                capture_reference=reference)
    args.update(overrides)
    return asyncio.run(part_geometry_case(reader, **args)), refs


def test_complete_finite_geometry_handler():
    reader = Reader()
    report, refs = run(reader)
    assert len(refs) == len(set(refs)) == 44
    assert len(report['roundtrip_ids']) == 7
    assert len([1 for tool, _ in reader.calls if tool == 'geometry_get']) == 8
    assert report['accepted'] is report['native_acceptance'] is report['cleanup_authorized'] is False
    assert report['before'] == report['after']
    assert len(report['rows']) == len(reader.calls)
    assert len({args['request_id'] for _, args in reader.calls}) == len(reader.calls)
    pages = [args for tool, args in reader.calls if tool == 'face_list' and args['body_id'] == 'body_0']
    assert [args['cursor'] for args in pages] == ['', '2', '4']
    assert all(args['limit'] == 2 for args in pages)
    assert [tool for tool, _ in reader.calls[-2:]] == ['geometry_get', 'body_list']


@pytest.mark.parametrize('fault', ['units', 'revision', 'count', 'short_box', 'duplicate',
                                  'empty_page', 'cyclic_cursor', 'owner', 'kind',
                                  'nonfinite_area', 'negative_length', 'roundtrip'])
def test_handler_rejects_incomplete_or_wrong_public_geometry(fault):
    def corrupt(tool, args, result):
        if fault == 'units': result['length_unit'] = 'm'
        elif fault == 'revision': result['observation_revision'] = 'other'
        elif fault == 'count' and tool == 'body_list': result['total_count'] = 4
        elif fault == 'short_box' and tool == 'body_list': result['items'][0]['bounding_box_mm']['min_mm'] = [0.]
        elif fault == 'duplicate' and tool == 'body_list': result['items'][1] = deepcopy(result['items'][0])
        elif fault == 'empty_page' and tool == 'face_list': result['items'] = []
        elif fault == 'cyclic_cursor' and tool == 'face_list': result['next_cursor'] = '2'
        elif fault == 'owner' and tool == 'edge_list': result['items'][0]['body_id'] = 'other'
        elif fault == 'kind' and tool == 'face_list': result['items'][0]['kind'] = 'edge'
        elif fault == 'nonfinite_area' and tool == 'face_list': result['items'][0]['area_mm2'] = float('nan')
        elif fault == 'negative_length' and tool == 'edge_list': result['items'][0]['length_mm'] = -1.
        elif fault == 'roundtrip' and tool == 'geometry_get': result['object']['name'] = 'Изменённое имя'
    reader = Reader(corrupt)
    with pytest.raises(ValueError): run(reader)
    assert len(reader.calls) < 100


@pytest.mark.parametrize('arguments', [dict(changed=True), dict(reference_error=True)])
def test_independent_native_or_preservation_difference_stops_handler(arguments):
    with pytest.raises(ValueError): run(Reader(), **arguments)


@pytest.mark.parametrize('overrides', [dict(context={}), dict(foreign_context=CONTEXT),
                                       dict(inactive_configuration='Основная'),
                                       dict(capture_reference=None), dict(capture_full=None)])
def test_missing_explicit_scope_or_oracle_prevents_dispatch(overrides):
    reader = Reader()
    with pytest.raises(ValueError): run(reader, **overrides)
    assert reader.calls == []


def test_native_observation_failure_never_dispatches_read():
    reader = Reader()
    def failure(): raise RuntimeError('Incomplete BREP proof')
    with pytest.raises(RuntimeError): run(reader, capture_full=failure)
    assert reader.calls == []
