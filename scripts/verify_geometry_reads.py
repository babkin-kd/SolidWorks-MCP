"""Native part-geometry acceptance using two disposable, unsaved test documents.

Run with the installed dev wheel and no PYTHONPATH. Setup/edit/cleanup use native
COM only on owned fixtures; MCP itself only reads. Original documents, active
target, visibility and the dimension-input preference are verified/restored.
The private journal and report belong in work/, never public CAD repositories.
"""

import argparse
import asyncio
from contextlib import contextmanager
from importlib import metadata
import json
from pathlib import Path
import sys
import uuid

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pythoncom

from solidworks_mcp import binding
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from solidworks_mcp.session import SolidWorksSession
import solidworks_mcp
from verify_document_reads import native_snapshot


@contextmanager
def fixtures():
    session = SolidWorksSession()
    session._sw = binding.connect(show=False)
    session._mod = binding.module()
    sw, module = session._sw, session._mod
    before = native_snapshot()
    original_active = binding.wrap(sw.ActiveDoc, module.IModelDoc2)
    original_title = original_active.GetTitle() if original_active is not None else None
    dimension_preference = sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    owned = []
    try:
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, False)
        for index in (1, 2):
            session.new_part()
            model = session._model
            owned.append(model)
            title = f'Проверка ссылок {index} ' + uuid.uuid4().hex[:8]
            assert model.SetTitle2(title)
            configuration = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            configuration.Name = 'Основная'
            assert configuration.Name == 'Основная'
            if index == 1:
                session.add_extruded_profile([[0, 0], [20, 0], [20, 10], [0, 10]], 5,
                                            name='Контрольный блок 1', merge=False)
                session.add_extruded_profile([[40, 0], [60, 0], [60, 10], [40, 10]], 5,
                                            name='Контрольный блок 2', merge=False)
                assert session._first_ref_plane().Select2(False, 0)
                sketch = binding.wrap(model.SketchManager, module.ISketchManager)
                session._sketch_closed_polygon(sketch, [[80, 0], [95, 0], [95, 10], [80, 10]])
                before_names = {feature.Name for feature in session._iter_features()}
                assert model.InsertPlanarRefSurface()
                new = [feature for feature in session._iter_features() if feature.Name not in before_names]
                assert len(new) == 1
                new[0].Name = 'Контрольная поверхность'
                assert new[0].Name == 'Контрольная поверхность'
                configuration = model.AddConfiguration3('Вариант', '', '', 128)  # swConfigOption_DontActivate
                assert configuration is not None
            else:
                session.add_box(5, 6, 7, name='Контрольный чужой блок')
            # Native fixture setup uses the legacy builders, never v2 mutations.
            # Name all created source sketches/planes/bodies in Russian and read
            # back the names; no original model is touched.
            sketch_number = plane_number = 0
            for feature in session._iter_features():
                kind = feature.GetTypeName2()
                if kind in ('ProfileFeature', '3DProfileFeature'):
                    sketch_number += 1
                    name = f'Контрольный эскиз {sketch_number}'
                elif kind == 'RefPlane':
                    plane_number += 1
                    name = f'Контрольная плоскость {plane_number}'
                else:
                    continue
                feature.Name = name
                assert feature.Name == name
            assert model.ForceRebuild3(False)
            for i, raw in enumerate(binding.wrap(model, module.IPartDoc).GetBodies2(-1, False) or ()):
                body = binding.wrap(raw, module.IBody2)
                name = f'Контрольное тело {i + 1}'
                body.Name = name
                assert body.Name == name
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        yield session, owned, before
    finally:
        # Close only exact owned documents; never a title pattern or all new docs.
        for model in reversed(owned):
            sw.CloseDoc(model.GetTitle())
        session._model = None
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE, dimension_preference)
        if original_title is not None:
            restored, _ = sw.ActivateDoc3(original_title, False, 1, 0)  # swDontRebuildActiveDoc
            assert restored is not None
        assert before == native_snapshot(), 'Original native document state was not restored.'
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) == dimension_preference


async def check(state):
    assert 'site-packages' in solidworks_mcp.__file__, 'Verify installed wheel without PYTHONPATH.'
    with fixtures() as (session, owned, original):
        setup_state = native_snapshot()
        titles = [model.GetTitle() for model in owned]
        params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                       args=['--state-dir', str(state)])
        async def call(client, tool, **arguments):
            result = (await client.call_tool(tool, {'request_id': uuid.uuid4().hex, **arguments})).structuredContent
            while result['status'] in ('queued', 'running'):
                await asyncio.sleep(.25)
                job = (await client.call_tool('job_get', {'operation_id': result['operation_id']})).structuredContent
                result = {**job, 'data': job['data']['result']}
            return result
        def success(result):
            assert result['status'] == 'succeeded', result['error']
            return result['data']
        with anyio.fail_after(240):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    info = (await client.call_tool('system_get_info')).structuredContent['data']
                    tools = (await client.list_tools()).tools
                    assert len(tools) == 10 and all(tool.outputSchema for tool in tools)
                    assert info['build_matches_source'] is True and info['capabilities']['cad_mutations'] is False
                    documents = success(await call(client, 'document_list'))['documents']
                    a, b = [next(d for d in documents if d['title'] == title) for title in titles]
                    context = {'document_id': a['document_id'], 'configuration': 'Основная',
                               'expected_observation_revision': a['observation_revision']}
                    bodies = success(await call(client, 'body_list', **context))['items']
                    assert len(bodies) == 3
                    assert sorted(item['body_type'] for item in bodies) == ['solid', 'solid', 'surface']
                    surface = next(item for item in bodies if item['body_type'] == 'surface')
                    solids = [item for item in bodies if item['body_type'] == 'solid']
                    for body in solids:
                        assert body['face_count'] == 6 and body['edge_count'] == 12
                        bounds = body['bounding_box_mm']
                        size = [hi - lo for lo, hi in zip(bounds['min_mm'], bounds['max_mm'])]
                        assert all(abs(x - y) < 1e-5 for x, y in zip(size, [20, 10, 5]))
                    separation = abs(solids[0]['bounding_box_mm']['min_mm'][0] - solids[1]['bounding_box_mm']['min_mm'][0])
                    assert abs(separation - 40) < 1e-5
                    all_faces = []
                    cursor = ''
                    while True:
                        page = success(await call(client, 'face_list', **context, body_id=solids[0]['object_id'],
                                                  limit=2, cursor=cursor))
                        all_faces.extend(page['items'])
                        cursor = page['next_cursor']
                        if cursor is None:
                            break
                    assert len(all_faces) == len({face['object_id'] for face in all_faces}) == 6
                    assert abs(sum(face['area_mm2'] for face in all_faces) - 700) < 1e-5
                    edges = success(await call(client, 'edge_list', **context, body_id=solids[0]['object_id']))['items']
                    assert len(edges) == 12 and abs(sum(edge['length_mm'] for edge in edges) - 140) < 1e-5
                    surface_faces = success(await call(client, 'face_list', **context, body_id=surface['object_id']))['items']
                    assert len(surface_faces) == 1 and abs(surface_faces[0]['area_mm2'] - 150) < 1e-5
                    surface_edges = success(await call(client, 'edge_list', **context, body_id=surface['object_id']))['items']
                    assert len(surface_edges) == 4 and abs(sum(edge['length_mm'] for edge in surface_edges) - 50) < 1e-5
                    for item in (solids[0], all_faces[0], edges[0], surface, surface_faces[0], surface_edges[0]):
                        resolved = success(await call(client, 'geometry_get', **context, object_id=item['object_id']))['object']
                        assert resolved == item
                    foreign = {'document_id': b['document_id'], 'configuration': 'Основная',
                               'expected_observation_revision': b['observation_revision']}
                    invalid = await call(client, 'geometry_get', **foreign, object_id=solids[0]['object_id'])
                    assert invalid['error']['code'] == 'object_reference_not_found'
                    inactive = await call(client, 'body_list', **{**context, 'configuration': 'Вариант'})
                    assert inactive['error']['code'] == 'configuration_not_active'
                    assert native_snapshot() == setup_state, 'MCP read changed the fixture/user state.'
                    # Direct native edits to an owned fixture only. Old observation
                    # token must fail; even with a fresh token, its deleted face
                    # must fail persistent resolution instead of picking another.
                    session._model = owned[0]
                    session.suppress_feature('Контрольная поверхность', True)
                    suppressed_state = success(await call(client, 'document_get', document_id=a['document_id'], configuration='Основная'))
                    context['expected_observation_revision'] = suppressed_state['observation_revision']
                    suppressed = await call(client, 'geometry_get', **context, object_id=surface_faces[0]['object_id'])
                    assert suppressed['status'] == 'failed' and suppressed['error']['code'] in (
                        'object_suppressed', 'object_reference_invalid', 'object_not_in_active_configuration',
                        'object_not_in_current_body'), suppressed
                    session.suppress_feature('Контрольная поверхность', False)
                    restored_state = success(await call(client, 'document_get', document_id=a['document_id'], configuration='Основная'))
                    context['expected_observation_revision'] = restored_state['observation_revision']
                    restored_bodies = success(await call(client, 'body_list', **context))['items']
                    restored_surface = next(body for body in restored_bodies if body['body_type'] == 'surface')
                    restored_faces = success(await call(client, 'face_list', **context, body_id=restored_surface['object_id']))['items']
                    session.delete_feature('Контрольная поверхность', with_children=True)
                    stale = await call(client, 'body_list', **context)
                    assert stale['error']['code'] == 'observation_revision_mismatch'
                    fresh = success(await call(client, 'document_get', document_id=a['document_id'], configuration='Основная'))
                    context['expected_observation_revision'] = fresh['observation_revision']
                    deleted = await call(client, 'geometry_get', **context, object_id=restored_faces[0]['object_id'])
                    assert deleted['status'] == 'failed' and deleted['error']['code'] in ('object_deleted', 'object_reference_invalid')
                    remaining = success(await call(client, 'body_list', **context))['items']
                    assert len(remaining) == 2 and all(body['body_type'] == 'solid' for body in remaining)
        report = {'package_version': metadata.version('solidworks-mcp'), 'git_sha': info['build']['git_sha'],
                  'source_dirty': info['build']['source_dirty'], 'build_matches_source': True,
                  'solidworks_revision': original[0], 'tool_count': len(tools), 'owned_fixture_documents': 2,
                  'solid_bodies': 2, 'surface_bodies': 1, 'solid_faces': 6, 'solid_edges': 12,
                  'surface_area_mm2': 150, 'surface_edges': 4, 'pagination_verified': True, 'reference_roundtrips': 6,
                  'foreign_reference_rejected': True, 'inactive_configuration_rejected': True,
                  'stale_observation_rejected': True, 'deleted_surface_face_rejected': True,
                  'suppressed_surface_face_rejected': True,
                  'suppressed_reference_error': suppressed['error']['code'],
                  'deleted_reference_error': deleted['error']['code'],
                  'scope': 'part_geometry_reads; fixture setup/edit is native COM, not MCP mutation acceptance'}
    report['original_native_state_restored'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    pythoncom.CoInitialize()
    try:
        print(json.dumps(asyncio.run(check(args.state_dir.resolve())), ensure_ascii=True))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
