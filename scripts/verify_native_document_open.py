"""Exact installed-wheel native OpenDoc6 receipts and public engineering chain.

Only this process owns the CAD fixtures. Independent native observations and
file hashes follow terminal durable jobs. Lost/unknown effects retain fixtures;
there is no COM cancellation, roster-delta adoption or automatic native retry.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

import pythoncom
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore
from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog
from verify_bounds_measurements import InlineSta
from verify_component_reads import native_identity
from verify_dimension_mcp import SessionCleanupGate, call, require_native_cleanup, succeeded
from verify_document_reads import native_snapshot
from verify_export_operations import activate_owned, application_preferences
from verify_geometry_reads import fixtures
from verify_installed_metadata import installed_identity, verify_metadata
from verify_native_document_save import physical_state
from verify_wheel_artifact import validate_wheel
from verifier_dimension_diagnostics import assert_non_stl_preferences
from verifier_lifecycle import ToolSpec, open_supervised_session
from verifier_native_open import released_open_guard, verified_open_native_steps
from verifier_native_open_acceptance import validate_internal_report


SPECS = {
    'document_list': ToolSpec('document.list', False),
    'document_prepare_open_native': ToolSpec('document.prepare_open_native', False,
        argument_defaults={'read_only': False}),
    'document_open_native': ToolSpec('document.open_native', True,
        argument_defaults={'read_only': False}, prewrite_failure_codes=frozenset({'stale_revision'})),
}
SHARED_LABELS = ['part_main_native_configuration', 'replay_no_second_native_open',
    'already_loaded_source_prewrite', 'missing_configuration_prewrite', 'stale_revision_prewrite',
    'assembly_borrowed_variant_geometry', 'drawing_borrowed_reference_chain',
    'assembly_new_resolved_dependency', 'drawing_new_reference_chain', 'part_variant_read_only']
INTERNAL_LABELS = SHARED_LABELS + ['normal_native_failure_no_effect', 'post_open_owned_clean_rollback',
    'owned_fixture_cleanup_baseline_restored']
PUBLIC_LABELS = SHARED_LABELS + ['owned_fixture_cleanup_baseline_restored']
HASH_FILES = ('verify_native_document_open.py', 'verify_geometry_reads.py', 'verify_native_document_save.py',
    'verify_document_reads.py', 'verify_export_operations.py', 'verify_dimension_mcp.py',
    'verifier_lifecycle.py', 'verifier_native_open.py', 'verifier_native_open_acceptance.py')


def disk_state(paths):
    result = {}
    for path in paths:
        data = Path(path).read_bytes()
        stat = Path(path).stat()
        result[str(path)] = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                            hashlib.sha256(data).hexdigest())
    return result


def window_state(sw, module):
    frame = binding.wrap(sw.Frame(), module.IFrame)
    windows = []
    for raw in frame.ModelWindows or ():
        window = binding.wrap(raw, module.IModelWindow)
        model = binding.wrap(window.ModelDoc, module.IModelDoc2)
        windows.append((window.HWndx64, native_identity(model), window.Title))
    assert len(windows) == frame.GetModelWindowCount()
    return tuple(sorted(windows, key=lambda row: row[0]))


def snapshot(sw, module):
    # In-memory canonical tokens never enter the JSON report.
    return native_snapshot(), physical_state(sw, module), window_state(sw, module)


def isometric_view_name(names):
    # Standard names are localized by the installed CAD application. Select
    # once from its passive inventory; never retry a failed CreateDrawView call.
    assert type(names) in (list, tuple) and 0 < len(names) <= 5000
    assert all(type(name) is str and name.strip() for name in names)
    matches = [name for name in names if name.casefold() in ('*isometric', '*изометрия')]
    assert len(matches) == 1, 'One exact native isometric view name required.'
    return matches[0]


def independent_graph(root, module):
    nodes, edges, queue = [], [], [root]
    while queue:
        model = queue.pop()
        if any(native_identity(model) == native_identity(item) for item in nodes):
            continue
        nodes.append(model)
        assert len(nodes) <= 5000
        if model.GetType() == 2:
            assembly = binding.wrap(model, module.IAssemblyDoc)
            components = [binding.wrap(raw, module.IComponent2) for raw in assembly.GetComponents(False) or ()]
            assert len(components) == assembly.GetComponentCount(False)
            references = []
            for component in components:
                assert component.GetSuppression2() in (2, 3) and component.IsVirtual is False and component.IsSpeedPak is False
                child = binding.wrap(component.GetModelDoc2(), module.IModelDoc2)
                assert child is not None and Path(child.GetPathName()).resolve() == Path(component.GetPathName()).resolve()
                assert component.ReferencedConfiguration in child.GetConfigurationNames()
                references.append((child, component.ReferencedConfiguration, 'component'))
        elif model.GetType() == 3:
            drawing = binding.wrap(model, module.IDrawingDoc)
            references = []
            for group in drawing.GetViews() or ():
                for raw in group:
                    view = binding.wrap(raw, module.IView)
                    if not view.GetReferencedModelName():
                        assert view.Type == 1
                        continue
                    child = binding.wrap(view.ReferencedDocument, module.IModelDoc2)
                    assert child is not None and Path(child.GetPathName()).resolve() == Path(view.GetReferencedModelName()).resolve()
                    assert view.ReferencedConfiguration in child.GetConfigurationNames()
                    references.append((child, view.ReferencedConfiguration, 'drawing_view'))
        else:
            assert model.GetType() == 1
            references = []
        for child, configuration, origin in references:
            edges.append(dict(parent_path=model.GetPathName(), path=child.GetPathName(), configuration=configuration, origin=origin))
            assert len(edges) <= 5000
            queue.append(child)
    return nodes, edges


def assert_variant_geometry(root, module, configuration):
    if root.GetType() == 1:
        bodies = binding.wrap(root, module.IPartDoc).GetBodies2(0, False) or ()
        expected = 1000. if configuration == 'Вариант' else 2000.
        assert len(bodies) == (1 if configuration == 'Вариант' else 2)
    elif root.GetType() == 2:
        raw = binding.wrap(root, module.IAssemblyDoc).GetComponents(False)
        assert len(raw) == 1
        component = binding.wrap(raw[0], module.IComponent2)
        assert component.ReferencedConfiguration == 'Вариант'
        result = component.GetBodies3(0)
        assert isinstance(result, tuple) and len(result) == 2
        bodies, _ = result
        assert len(bodies or ()) == 1
        expected = 1000.
    else:
        model = next(child for child in independent_graph(root, module)[0] if child.GetType() == 2)
        return assert_variant_geometry(model, module, 'Основная')
    volume = sum(binding.wrap(body, module.IBody2).GetMassProperties(1.)[3] * 1e9 for body in bodies)
    assert math.isclose(volume, expected, abs_tol=1e-5, rel_tol=1e-8), (volume, expected)
    return dict(solid_count=len(bodies), volume_mm3=volume)


def retire_owned(sw, module, root, retiring, owned, record):
    # Capture all canonical tokens before CloseDoc; never query retired handles.
    tokens = [native_identity(item) for item in retiring]
    pairs = [(item, native_identity(item)) for item in owned]
    previous_active = binding.wrap(sw.ActiveDoc, module.IModelDoc2)
    previous_token = None if previous_active is None else native_identity(previous_active)
    if previous_token is not None:
        assert any(previous_token == token for _, token in pairs)
    previous_title = None if previous_active is None else previous_active.GetTitle()
    title = root.GetTitle()
    current = [binding.wrap(raw, module.IModelDoc2) for raw in sw.GetDocuments() or ()]
    assert sum(model.GetTitle().casefold() == title.casefold() for model in current) == 1
    assert any(native_identity(model) == native_identity(root) for model in current)
    sw.CloseDoc(title)
    live = [native_identity(binding.wrap(raw, module.IModelDoc2)) for raw in sw.GetDocuments() or ()]
    assert not any(token in live for token in tokens)
    owned[:] = [item for item, token in pairs if token not in tokens]
    record(owned)
    # Native CloseDoc of an inactive drawing may activate its referenced
    # assembly. This is test-owner cleanup restoration, not v2 close acceptance.
    if previous_token is not None and previous_token not in tokens:
        assert previous_token in live
        active = binding.wrap(sw.ActiveDoc, module.IModelDoc2)
        if active is None or native_identity(active) != previous_token:
            survivors = [binding.wrap(raw, module.IModelDoc2) for raw in sw.GetDocuments() or ()]
            assert sum(model.GetTitle().casefold() == previous_title.casefold() for model in survivors) == 1
            activate_owned(sw, previous_active, previous_title)
            active = binding.wrap(sw.ActiveDoc, module.IModelDoc2)
            assert active is not None and native_identity(active) == previous_token


def setup(session, owned, state, sw, module, record):
    assert len(owned) == 2 and sw.CommandInProgress is True
    part, neighbor = owned
    activate_owned(sw, part, part.GetTitle())
    session._model = part
    assert part.ShowConfiguration2('Вариант')
    session.suppress_feature('Контрольный блок 2', True)
    assert part.ShowConfiguration2('Основная') and part.ForceRebuild3(False)
    session.save_part(str(state / 'Деталь открытия.SLDPRT'))
    record(owned)
    activate_owned(sw, neighbor, neighbor.GetTitle())
    session._model = neighbor
    session.save_part(str(state / 'Соседняя деталь.SLDPRT'))
    record(owned)
    session.new_assembly()
    assembly = session._model
    owned.append(assembly)
    record(owned)
    assert assembly.SetTitle2('Сборка открытия')
    configuration = binding.wrap(assembly.GetActiveConfiguration(), module.IConfiguration)
    configuration.Name = 'Основная'
    assert configuration.Name == 'Основная'
    session.insert_component(part.GetPathName(), fixed=False)
    component = binding.wrap(binding.wrap(assembly, module.IAssemblyDoc).GetComponents(False)[0], module.IComponent2)
    component.ReferencedConfiguration = 'Вариант'
    assert component.ReferencedConfiguration == 'Вариант' and assembly.ForceRebuild3(False)
    session.save_assembly(str(state / 'Сборка открытия.SLDASM'))
    record(owned)
    template = sw.GetUserPreferenceStringValue(10)
    assert template and Path(template).is_file()
    raw = sw.NewDocument(template, 0, 0, 0)
    assert raw is not None
    drawing = binding.wrap(raw, module.IModelDoc2)
    owned.append(drawing)
    record(owned)
    assert drawing.SetTitle2('Чертёж открытия')
    record(owned)
    model_view = isometric_view_name(assembly.GetModelViewNames())
    view = binding.wrap(binding.wrap(drawing, module.IDrawingDoc).CreateDrawViewFromModelView3(
        assembly.GetPathName(), model_view, .1, .1, 0.), module.IView)
    assert view is not None
    view.ReferencedConfiguration = 'Основная'
    assert view.ReferencedConfiguration == 'Основная'
    assert drawing.ForceRebuild3(False)
    assert drawing.SaveAs3(str(state / 'Чертёж открытия.SLDDRW'), 0, 1) == 0
    for model in owned:
        if model.GetSaveFlag():
            assert model.Save3(1, 0, 0) == (True, 0, 0)
    assert all(model.GetSaveFlag() is False for model in owned)
    paths = {kind: Path(model.GetPathName()).resolve() for kind, model in
             (('part', part), ('assembly', assembly), ('drawing', drawing), ('neighbor', neighbor))}
    activate_owned(sw, neighbor, neighbor.GetTitle())
    for model in (drawing, assembly, part):
        retire_owned(sw, module, model, [model], owned, record)
    assert len(owned) == 1 and owned[0] is neighbor
    assert neighbor.AddCustomInfo3('', 'Несохранённое контрольное свойство', 30, 'Сохранить исходное состояние')
    neighbor.SetSaveFlag()
    assert neighbor.GetSaveFlag() is True
    assert neighbor.Extension.SelectByID2('Контрольный чужой блок', 'BODYFEATURE', 0., 0., 0., False, 0, None, 0)
    record(owned)
    return paths, neighbor


async def cases(read, safe, sw, module, paths, neighbor, owned, report, persist, record, *, probe=None):
    disks = disk_state(paths.values())
    report['baseline_file_hashes'] = {path: facts[-1] for path, facts in disks.items()}
    persist()
    def add(label, result=None, **details):
        report['cases'].append(dict(label=label, passed=True, result=result, **details))
        persist()
    async def refuse(label, args, code, tool='document_prepare_open_native'):
        await safe()
        before = snapshot(sw, module)
        result = await read(tool, args)
        await safe()
        assert result['status'] == 'failed' and result['error']['code'] == code, result
        assert snapshot(sw, module) == before and disk_state(paths.values()) == disks
        add(label, result)
    async def opened(label, kind, cfg, read_only=False, borrowed_paths=(), keep=False):
        await safe()
        before = snapshot(sw, module)
        data = dict(filename=str(paths[kind]), document_type=kind, configuration=cfg, read_only=read_only)
        p = succeeded(await read('document_prepare_open_native', data))
        await safe()
        assert snapshot(sw, module) == before
        args = dict(document_id=p['application_id'], native_file_id=p['native_file_id'], configuration=cfg,
                    expected_revision=p['revision'], read_only=read_only, request_id=uuid.uuid4().hex)
        result = await read('document_open_native', args)
        await safe()
        value = succeeded(result)
        assert value['verified'] is True
        actual = value['value']
        assert actual['native_errors'] == actual['native_warnings'] == 0
        # The independently mapped root is adopted only after exact durable
        # new-return receipt/resolution proof; a roster delta grants nothing.
        root = binding.wrap(sw.GetOpenDocumentByName(str(paths[kind])), module.IModelDoc2)
        assert root is not None and root.GetType() == {'part': 1, 'assembly': 2, 'drawing': 3}[kind]
        assert not any(native_identity(root) == row[0] for row in before[1][0])
        nodes, edges = independent_graph(root, module)
        rows = succeeded(await read('document_list', {}))['documents']
        await safe()
        mapped = {row['document_id']: Path(row['path']).resolve() for row in rows if row['path']}
        assert mapped[actual['source_document_id']] == paths[kind]
        expected_new = {paths[kind], *(Path(edge['path']).resolve() for edge in edges)} - set(borrowed_paths)
        assert {mapped[did] for did in actual['new_document_ids']} == expected_new
        assert {mapped[did] for did in actual['borrowed_document_ids']} == set(borrowed_paths)
        assert sorted((Path(edge['path']).resolve(), edge['configuration'], edge['origin']) for edge in edges) == sorted(
            (Path(edge['path']).resolve(), edge['configuration'], edge['origin']) for edge in actual['references'])
        new = [model for model in nodes if Path(model.GetPathName()).resolve() in expected_new]
        assert len(new) == len(expected_new)
        assert all(not any(native_identity(model) == native_identity(old) for old in owned) for model in new)
        owned.extend(new)
        record(owned)
        report.setdefault('verified_open_ownership', []).append(dict(operation_id=result['operation_id'], paths=sorted(map(str, expected_new))))
        persist()
        active = binding.wrap(root.GetActiveConfiguration(), module.IConfiguration)
        assert (active.Name if active else '') == cfg
        assert root.IsOpenedReadOnly() is read_only
        # Compare baseline metadata, actual geometry/views/selections/windows
        # before independent geometry probing of the new/reference configuration.
        after = snapshot(sw, module)
        tokens = [row[0] for row in before[1][0]]
        assert before[0][:3] == after[0][:3] and before[0][3] == [row for row in after[0][3] if row[0] in tokens]
        assert before[1][0] == tuple(row for row in after[1][0] if row[0] in tokens) and before[1][1:] == after[1][1:]
        assert before[2] == tuple(row for row in after[2] if row[1] in tokens)
        assert neighbor.GetSaveFlag() is True and disk_state(paths.values()) == disks
        geometry = assert_variant_geometry(root, module, cfg)
        add(label, result, native_geometry=geometry, new_model_count=len(new), borrowed_model_count=len(borrowed_paths))
        if not keep:
            retire_owned(sw, module, root, new, owned, record)
            assert snapshot(sw, module) == before and disk_state(paths.values()) == disks
        return root, new, before, result, args

    part, group_part, baseline, first, replay_args = await opened(SHARED_LABELS[0], 'part', 'Основная', keep=True)
    before_replay = snapshot(sw, module)
    replay = await read('document_open_native', replay_args)
    await safe()
    assert replay['operation_id'] == first['operation_id'] and replay['data'] == first['data']
    assert snapshot(sw, module) == before_replay and disk_state(paths.values()) == disks
    add(SHARED_LABELS[1], replay)
    await refuse(SHARED_LABELS[2], dict(filename=str(paths['part']), document_type='part', configuration='Основная'), 'native_document_already_loaded')
    await refuse(SHARED_LABELS[3], dict(filename=str(paths['assembly']), document_type='assembly', configuration='Нет такой'), 'native_open_configuration_not_found')
    p = succeeded(await read('document_prepare_open_native', dict(filename=str(paths['assembly']), document_type='assembly', configuration='Основная')))
    await safe()
    await refuse(SHARED_LABELS[4], dict(document_id=p['application_id'], native_file_id=p['native_file_id'], configuration='Основная',
        expected_revision='rev_stale'), 'stale_revision', 'document_open_native')
    assembly, group_asm, before_asm, _, _ = await opened(SHARED_LABELS[5], 'assembly', 'Основная', borrowed_paths=[paths['part']], keep=True)
    await opened(SHARED_LABELS[6], 'drawing', '', borrowed_paths=[paths['assembly'], paths['part']])
    retire_owned(sw, module, assembly, group_asm, owned, record)
    assert snapshot(sw, module) == before_asm
    retire_owned(sw, module, part, group_part, owned, record)
    assert snapshot(sw, module) == baseline
    await opened(SHARED_LABELS[7], 'assembly', 'Основная')
    await opened(SHARED_LABELS[8], 'drawing', '')
    await opened(SHARED_LABELS[9], 'part', 'Вариант', read_only=True)
    if probe:
        for label, mode in ((INTERNAL_LABELS[10], 'missing'), (INTERNAL_LABELS[11], 'post_return')):
            await safe()
            before = snapshot(sw, module)
            result = await probe(mode, dict(filename=str(paths['part']), document_type='part', configuration='Основная'))
            await safe()
            assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back', result
            assert result['error']['requires_reconciliation'] is False
            verification = result['mutation']['verification']
            assert released_open_guard(verification['evidence']['execution_guard'], result['mutation']['before_state'])
            assert verified_open_native_steps(verification, result['mutation']['before_state'])
            assert snapshot(sw, module) == before and disk_state(paths.values()) == disks
            add(label, result, fault_probe=mode, simulated_com_exception=False)
    await safe()
    assert len(owned) == 1 and owned[0] is neighbor and neighbor.GetSaveFlag() is True
    assert disk_state(paths.values()) == disks
    # This exact owned dirty fixture is discarded by test-owner permission;
    # it is not public dirty-owned close or first-save acceptance.
    retire_owned(sw, module, neighbor, [neighbor], owned, record)
    assert not owned and not sw.GetDocuments() and sw.CommandInProgress is False


async def internal(state, sw, module, paths, neighbor, owned, report, persist, record):
    adapter = SolidWorksDocuments()
    docs = DocumentCatalog(adapter)
    store = JobStore(state / 'jobs.sqlite')
    runner = JobRunner(store, InlineSta())
    catalog = NativeDocumentOpenCatalog(docs, store, 'native-open-test')
    async def read(tool, args):
        args = dict(args)
        request = args.pop('request_id', uuid.uuid4().hex)
        spec = SPECS[tool]
        args = {**spec.argument_defaults, **args}
        method = {'document_list': docs.list, 'document_prepare_open_native': catalog.prepare_open, 'document_open_native': catalog.open}[tool]
        context = {key: args[key] for key in ('document_id', 'configuration', 'expected_revision') if key in args}
        job = runner.submit(request, spec.operation, args,
            lambda op: method(op, **args) if spec.mutates else method(**args), context=context,
            mutates=spec.mutates, pass_operation_id=True, verify=(lambda result: result['verified'] is True) if spec.mutates else None)
        return dict(status=job['status'], operation_id=job['operation_id'], data=job['result'], error=job['error'], mutation=job.get('mutation'))
    async def safe():
        for row in store.list(limit=200)['items']:
            assert row['status'] in ('succeeded', 'failed'), row
            if row['payload']['mutates'] and row.get('mutation'):
                mutation = row['mutation']
                assert mutation['phase'] in ('committed', 'rolled_back', 'not_started')
                assert released_open_guard(mutation['verification']['evidence']['execution_guard'], mutation['before_state'])
                if mutation['phase'] != 'not_started':
                    assert verified_open_native_steps(mutation['verification'], mutation['before_state'])
        assert not store.mutation_blockers('native-open-test', 'any', effect_scope='application')
    async def probe(mode, data):
        p = succeeded(await read('document_prepare_open_native', data))
        await safe()
        original = adapter.open_native_document
        def fault(receipt):
            if mode == 'missing':
                receipt.filename = str(state / 'Отсутствующий файл probe.SLDPRT')
            value = original(receipt)
            if mode == 'post_return':
                raise RuntimeError('Owned post-return Python fault after real native OpenDoc6, not a COM throw.')
            return value
        adapter.open_native_document = fault
        try:
            return await read('document_open_native', dict(document_id=p['application_id'], native_file_id=p['native_file_id'],
                configuration=data['configuration'], expected_revision=p['revision'], read_only=False))
        finally:
            adapter.open_native_document = original
    try:
        await cases(read, safe, sw, module, paths, neighbor, owned, report, persist, record, probe=probe)
    finally:
        docs.close()
        store.close()


async def public(entry, state, sw, module, paths, neighbor, owned, report, persist, record, gate):
    params = StdioServerParameters(command=str(entry), args=['--state-dir', str(state / 'server')],
        env={**os.environ, 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'})
    @asynccontextmanager
    async def factory():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as raw:
                await raw.initialize()
                info = succeeded(await call(raw, 'system_get_info'))
                report['metadata'] = verify_metadata((await raw.list_tools()).tools, info, report['wheel'])
                persist()
                yield raw
    async with open_supervised_session(factory, tool_specs=SPECS, journal_path=state / 'server/jobs.sqlite',
        on_hold=lambda decision: report.update(lifecycle_hold=True)) as client:
        gate.add(client)
        async def read(tool, args):
            return await call(client, tool, **args, timeout_s=0.)
        async def safe():
            await require_native_cleanup(client, gate)
        await read('document_list', {})
        await safe()
        await cases(read, safe, sw, module, paths, neighbor, owned, report, persist, record)
        await safe()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-solidworks', action='store_true')
    parser.add_argument('--public', action='store_true')
    parser.add_argument('--internal-report', type=Path)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_solidworks:
        parser.error('Explicit native opt-in required.')
    assert not os.environ.get('PYTHONPATH')
    wheel = validate_wheel(args.wheel, expected_version=args.expected_version, expected_git_sha=args.expected_git_sha)
    entry = installed_identity(wheel)
    hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in HASH_FILES}
    if args.public:
        assert args.internal_report
        prior = json.loads(args.internal_report.read_text(encoding='utf8'))
        validate_internal_report(prior, wheel, hashes, INTERNAL_LABELS)
    private = Path(__file__).resolve().parents[1] / 'work'
    state = args.state_dir.resolve()
    assert state.is_relative_to(private) and state != private and not state.exists()
    state.mkdir(parents=True)
    report = dict(accepted=False, scope=('public' if args.public else 'internal') + '_native_open_resolved_v1',
        wheel=wheel, cases=[], verifier_hashes=hashes, state_dir=str(state))
    def persist():
        (state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    def record(owned):
        report['owned_documents'] = [dict(title=model.GetTitle(), path=model.GetPathName(), type=model.GetType()) for model in owned]
        persist()
    start = time.perf_counter()
    pythoncom.CoInitialize()
    sw, owns_setup, gate = None, False, SessionCleanupGate()
    try:
        sw = binding.connect(show=False)
        module = binding.module()
        assert not sw.GetDocuments() and sw.CommandInProgress is False and sw.UserControl is True
        baseline, preferences = native_snapshot(), application_preferences(sw)
        app_baseline = SolidWorksDocuments().native_close_application_context()
        report['solidworks_revision'] = str(sw.RevisionNumber())
        persist()
        sw.CommandInProgress = True
        assert sw.CommandInProgress is True
        owns_setup = True
        with fixtures(cleanup_gate=lambda: report.get('cleanup_confirmed') is True, on_owned_change=record) as (session, owned, _):
            paths, neighbor = setup(session, owned, state, sw, module, record)
            sw.CommandInProgress = False
            assert sw.CommandInProgress is False
            owns_setup = False
            if args.public:
                asyncio.run(public(entry, state, sw, module, paths, neighbor, owned, report, persist, record, gate))
            else:
                asyncio.run(internal(state, sw, module, paths, neighbor, owned, report, persist, record))
            assert [case['label'] for case in report['cases']] == (PUBLIC_LABELS if args.public else INTERNAL_LABELS)[:-1]
            assert not args.public or gate.can_cleanup()
            assert not owned and not sw.GetDocuments() and sw.CommandInProgress is False
            assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'fixture_preferences')
            report['cleanup_confirmed'] = True
            persist()
        assert native_snapshot() == baseline and sw.CommandInProgress is False
        assert SolidWorksDocuments().native_close_application_context() == app_baseline
        assert_non_stl_preferences(lambda: application_preferences(sw), preferences, report, 'restored_preferences')
        report['cases'].append(dict(label=INTERNAL_LABELS[-1], passed=True, owned_only=True))
        report.update(fixtures_closed=True, baseline_restored=True, accepted=True)
    except BaseException as error:
        report.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        try:
            if owns_setup:
                assert sw.CommandInProgress is True
                sw.CommandInProgress = False
                assert sw.CommandInProgress is False
        finally:
            report['elapsed_seconds'] = time.perf_counter() - start
            persist()
            pythoncom.CoUninitialize()
    print(json.dumps(dict(accepted=report['accepted'], cases=len(report['cases']), scope=report['scope'])))


if __name__ == '__main__':
    main()
