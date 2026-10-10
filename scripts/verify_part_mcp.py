"""Installed public MCP plate construction and thickness edit on owned parts.

This proves only the bounded public engineering chain exercised by the report,
not arbitrary CAD capability or completion of a project stage. No user file saved.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sysconfig
import uuid
import math
import asyncio
from contextlib import asynccontextmanager
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import pythoncom
import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.build_info import source_digest
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.constants import SW_PREF_DEFAULT_TEMPLATE_PART
from verify_document_reads import native_snapshot
from verify_export_operations import application_preferences, activate_owned
from verify_mass_properties import source_state
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verify_wheel_artifact import validate_wheel
from verifier_lifecycle import ToolSpec, open_supervised_session
from verify_dimension_mcp import SessionCleanupGate, require_native_cleanup, call, succeeded


DEFAULT_NAMES = dict(sketch_name='Эскиз основания', feature_name='Основание', body_name='Тело основания')
FLOATS = frozenset({'width_mm', 'height_mm', 'depth_mm'})
TOOL_SPECS = {
    'document_list': ToolSpec('document.list', False),
    'feature_list': ToolSpec('feature.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'part_prepare_base_extrusion': ToolSpec('part.prepare_base_extrusion', False, argument_defaults=DEFAULT_NAMES, float_arguments=FLOATS),
    'part_create_base_extrusion': ToolSpec('part.create_base_extrusion', True, argument_defaults=DEFAULT_NAMES,
        float_arguments=FLOATS, prewrite_failure_codes=frozenset({'stale_revision'})),
    'dimension_list': ToolSpec('dimension.list', False, argument_defaults={'limit': 100, 'cursor': ''}),
    'dimension_set_value': ToolSpec('dimension.set_value', True, float_arguments=frozenset({'value'})),
}


async def exercise(state, sw, module, first, other, report, persist, gate):
    params = StdioServerParameters(command=str(Path(sys.executable).with_name('solidworks-mcp-v2.exe')),
                                   args=['--state-dir', str(state / 'mcp')])
    @asynccontextmanager
    async def session():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as raw:
                await raw.initialize()
                info = (await raw.call_tool('system_get_info')).structuredContent['data']
                assert info['build_matches_source'] is True and info['package_version'] == report['wheel']['package_version']
                assert info['build']['git_sha'] == report['wheel']['git_sha']
                assert info['source_digest'] == report['wheel']['source_digest']
                tools = (await raw.list_tools()).tools
                assert len(tools) == 20 and all(tool.outputSchema for tool in tools)
                assert {'part_prepare_base_extrusion', 'part_create_base_extrusion'} <= {tool.name for tool in tools}
                report['tool_count'] = len(tools)
                yield raw
    other_identity = other._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
    target_identity = first._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
    def state_of(token):
        snapshot, facts = source_state(sw, module)
        matches = [(row, fact) for row, fact in zip(snapshot[3], facts) if row[0] == token]
        assert len(matches) == 1
        return matches[0]
    other_baseline = state_of(other_identity)
    original_selection = state_of(target_identity)[1][0]
    assert len(original_selection) == 1 and original_selection[0][1] == 7
    async with open_supervised_session(session, tool_specs=TOOL_SPECS, journal_path=state / 'mcp' / 'jobs.sqlite') as client:
        gate.add(client)
        async def record(label, response):
            report['last_response'] = response
            persist()
            await require_native_cleanup(client, gate)
            assert state_of(other_identity) == other_baseline
            current_selection = state_of(target_identity)[1][0]
            assert current_selection == original_selection, 'Selection objects/marks changed.'
            assert_non_stl_preferences(lambda: application_preferences(sw), report['baseline']['preferences'], report, 'preferences_' + label)
            report['cases'].append({'label': label, 'passed': True, 'response': response})
            persist()
        docs = succeeded(await call(client, 'document_list'))['documents']
        doc = next(row for row in docs if row['title'] == first.GetTitle())
        context = dict(document_id=doc['document_id'], configuration='Основная')
        tree = succeeded(await call(client, 'feature_list', **context))
        plane = next(row for row in tree['items'] if row['feature_type'] == 'RefPlane' and row['object_id'])
        arguments = dict(context, plane_object_id=plane['object_id'], width_mm=40., height_mm=20., depth_mm=10.)
        prepared = succeeded(await call(client, 'part_prepare_base_extrusion', **arguments))
        assert prepared['revision_scope'] == 'empty_part_base_rectangle_v1' and prepared['native_creation_available'] is True
        stale = await call(client, 'part_create_base_extrusion', **arguments, expected_revision='rev_stale')
        assert stale['status'] == 'failed' and stale['error']['code'] == 'stale_revision', stale
        await record('stale_creation_prewrite_rejected', stale)
        write_args = dict(arguments, expected_revision=prepared['revision'], request_id='mcp-plate-' + uuid.uuid4().hex)
        created = await call(client, 'part_create_base_extrusion', **write_args, timeout_s=0.)
        proof = succeeded(created)
        assert proof['verified'] is True and proof['execution_guard'] == {'original_state': 0, 'locked_state': 2, 'released_state': 0}
        await record('public_plate_40_20_10', created)
        native_bodies = binding.wrap(first, module.IPartDoc).GetBodies2(-1, False) or ()
        assert len(native_bodies) == 1
        body = binding.wrap(native_bodies[0], module.IBody2)
        assert body.Name == 'Тело основания' and math.isclose(float(body.GetMassProperties(1.)[3]) * 1e9, 8000., rel_tol=1e-7)
        repeat = await call(client, 'part_create_base_extrusion', **write_args)
        assert repeat['operation_id'] == created['operation_id'] and succeeded(repeat) == proof
        await record('same_request_does_not_create_again', repeat)
        page = succeeded(await call(client, 'dimension_list', **context))
        assert page['total_count'] == 3 and {row['name'] for row in page['items']} == {'Ширина', 'Высота', 'Толщина'}
        thickness = next(row for row in page['items'] if row['name'] == 'Толщина')
        assert thickness['object_id'] and not thickness['write_blockers']
        edited = await call(client, 'dimension_set_value', **context, object_id=thickness['object_id'],
                            expected_revision=page['revision'], value=12., unit='mm', timeout_s=0.)
        assert succeeded(edited)['verified'] is True
        await record('public_thickness_edit_12', edited)
        native_bodies = binding.wrap(first, module.IPartDoc).GetBodies2(-1, False) or ()
        assert len(native_bodies) == 1
        volume = float(binding.wrap(native_bodies[0], module.IBody2).GetMassProperties(1.)[3]) * 1e9
        assert math.isclose(volume, 9600., rel_tol=1e-7)
        report['plate_volume_after_edit_mm3'] = volume
        await require_native_cleanup(client, gate)
    assert gate.can_cleanup(), 'SDK lifecycle shutdown was not proved.'
    report['public_mcp_creation_accepted'] = True
    report['part_creation_accepted'] = True
    report['core_suite_passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--internal-report', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_solidworks:
        parser.error('Native checks require explicit --run-solidworks; no connection attempted.')
    assert not os.environ.get('PYTHONPATH'), 'Source PYTHONPATH is prohibited.'
    package = Path(solidworks_mcp.__file__).resolve().parent
    assert package.is_relative_to(Path(sysconfig.get_path('purelib')).resolve())
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    assert solidworks_mcp.__version__ == importlib.metadata.version('solidworks-mcp') == args.expected_version
    assert source_digest(package) == wheel['source_digest']
    build = json.loads((package / 'build_info.json').read_text())
    assert build['git_sha'] == args.expected_git_sha and build['source_dirty'] is False
    internal = json.loads(args.internal_report.read_text(encoding='utf8'))
    assert internal['accepted'] is True and internal['part_creation_accepted'] is True
    assert internal['wheel'] == wheel, 'Requires native acceptance of exactly the same installed wheel.'
    assert {case['label'] for case in internal['cases']} == {'known_creation_failure_scoped_rollback', 'parametric_plate_40_20_10', 'thickness_edit_12'}
    state = args.state_dir.resolve()
    private = (Path(__file__).resolve().parents[1] / 'work').resolve()
    assert state.is_relative_to(private) and state != private
    state.mkdir(parents=True, exist_ok=False)
    report = {'accepted': False, 'scope': 'public_mcp_parametric_plate_construction_native_v1',
              'wheel': wheel, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': [], 'owned_documents': [], 'part_creation_accepted': False,
              'public_mcp_creation_accepted': False}
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    owned, adapter, documents, store = [], None, None, None
    gate = SessionCleanupGate()
    sw, owns_guard, creation_pending = None, False, False
    pythoncom.CoInitialize()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and not sw.CommandInProgress, 'Requires empty/free baseline; no documents closed.'
        baseline = native_snapshot()
        preferences = application_preferences(sw)
        report['baseline'] = {'empty_session': True, 'command_in_progress': False, 'preferences': preferences}
        template = sw.GetUserPreferenceStringValue(SW_PREF_DEFAULT_TEMPLATE_PART)
        assert template and Path(template).is_file(), 'A configured existing part template is required; no fallback creation.'
        report['pending_guard_acquisition'] = True
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress, 'Guard acquisition unconfirmed; no repeat.'
        owns_guard = True
        report['pending_guard_acquisition'] = False
        for index in range(2):
            report['pending_document_creation'] = True
            creation_pending = True
            persist()
            raw = sw.NewDocument(template, 0, 0, 0)  # Exactly once; never replay an unknown outcome.
            assert raw is not None, 'Native document creation returned no owned handle.'
            model = binding.wrap(raw, module.IModelDoc2)
            identity = model._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
            owned.append((model, identity))
            creation_pending = False
            report['pending_document_creation'] = False
            assert model.SetTitle2(f'Контрольная пластина {index + 1} ' + uuid.uuid4().hex[:8])
            config = binding.wrap(model.GetActiveConfiguration(), module.IConfiguration)
            config.Name = 'Основная'
            assert config.Name == 'Основная'
            report['owned_documents'] = [{'title': item.GetTitle(), 'path': item.GetPathName(),
                                         'type': item.GetType()} for item, _ in owned]
            persist()
        first, other = (row[0] for row in owned)
        activate_owned(sw, first, first.GetTitle())
        adapter = SolidWorksDocuments()
        planes = [item for item in adapter.features(first) if item.GetTypeName2() == 'RefPlane']
        assert len(planes) == 3
        assert planes[1].Select2(False, 7)  # Own fixture setup only.
        asyncio.run(exercise(state, sw, module, first, other, report, persist, gate))
    except BaseException as exc:
        report['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        persist()
        raise
    finally:
        try:
            if documents is not None: documents.close()
            elif adapter is not None: adapter.close()
            if store is not None: store.close()
            if sw is not None and owns_guard and not creation_pending and gate.can_cleanup():
                # Standing authorization: terminal read calls, exact own handles,
                # and an initially empty session. Never close a new/foreign model.
                current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                tokens = [item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) for item in current]
                assert len(current) == len(owned) and all(any(token == identity for _, identity in owned) for token in tokens)
                for model, identity in reversed(owned):
                    assert model._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity
                    assert not model.GetPathName() and model.GetType() == 1
                    title = model.GetTitle()
                    assert sum(item.GetTitle() == title for item in current) == 1
                    sw.CloseDoc(title)
                    current = [binding.wrap(raw, binding.module().IModelDoc2) for raw in sw.GetDocuments() or ()]
                    assert not any(item._oleobj_.QueryInterface(pythoncom.IID_IUnknown) == identity for item in current)
                assert native_snapshot() == baseline
                assert_non_stl_preferences(lambda: application_preferences(sw), preferences,
                                           report, 'preferences_after_cleanup')
                report['fixtures_closed'] = True
        except BaseException as exc:
            report['cleanup_failure'] = {'type': type(exc).__name__, 'message': str(exc)}
            report['accepted'] = False
            persist()
            raise
        finally:
            try:
                if sw is not None and owns_guard and not creation_pending:
                    # This process has completed its own native calls. Release
                    # only its acknowledged flag even if another check failed.
                    sw.CommandInProgress = False
                    assert not sw.CommandInProgress
                    owns_guard = False
                    report['guard_released'] = True
                report['accepted'] = (report.get('core_suite_passed') is True
                    and report.get('fixtures_closed') is True and report.get('guard_released') is True
                    and 'cleanup_failure' not in report)
                persist()
            finally:
                pythoncom.CoUninitialize()
    print(json.dumps({'accepted': report['accepted'], 'cases': len(report['cases']), 'report': str(state / 'report.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
