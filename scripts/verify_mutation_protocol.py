"""Installed-wheel native checkpoint protocol check on disposable owned parts.

This is NOT MCP mutation acceptance or a full document revision/rollback test.
Only a feature-name field is written through server-owned callbacks on the STA.
Failures after the actual COM write are deliberately injected. Geometry and the
original user-document baseline are checked; no user model is saved or edited.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import threading
import uuid

import pythoncom

import solidworks_mcp
from solidworks_mcp import binding
from solidworks_mcp.cad_documents import SolidWorksDocuments
from solidworks_mcp.com_worker import ComWorker
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore, _json
from solidworks_mcp.mutations import MutationCoordinator, PreparedMutation
from solidworks_mcp.server_v2 import create_app
from verify_document_reads import native_snapshot
from verify_geometry_reads import fixtures


def check(state_dir):
    assert 'site-packages' in solidworks_mcp.__file__, 'Use the installed wheel, without PYTHONPATH.'
    original = native_snapshot()
    report = {}
    with fixtures() as (_, owned, _):
        titles = [str(model.GetTitle()) for model in owned]  # Only plain strings cross apartments.
        store = JobStore(state_dir / 'jobs.sqlite')
        runner = JobRunner(store, ComWorker())
        epoch = 'connection_' + uuid.uuid4().hex
        coordinator = MutationCoordinator(store, epoch)
        native = {}  # Accessed and cleared ONLY on the owning STA.
        try:
            assert not store.list()['items'], 'Use a fresh private directory for this native fixture run.'
            def initialize():
                catalog = DocumentCatalog(SolidWorksDocuments())
                native['catalog'] = catalog
                documents = catalog.list()['documents']
                targets = []
                for title, feature_name in zip(titles, ('Контрольный блок 1', 'Контрольный чужой блок')):
                    doc = next(item for item in documents if item['title'] == title)
                    entry, _ = catalog.resolve(doc['document_id'], 'Основная')
                    feature = binding.wrap(entry.model.FirstFeature(), binding.module().IFeature)
                    while feature is not None and str(feature.Name) != feature_name:
                        feature = binding.wrap(feature.GetNextFeature(), binding.module().IFeature)
                    assert feature is not None
                    native[doc['document_id']] = (entry.model, feature)
                    targets.append(doc['document_id'])
                return targets
            ids = runner.worker.submit(initialize).result(timeout=45)

            def snapshot(document_id):
                model, feature = native[document_id]
                entry, observed = native['catalog'].resolve(document_id, 'Основная')
                assert native['catalog'].adapter.identity(entry.model) == native['catalog'].adapter.identity(model)
                assert observed['active_configuration'] == 'Основная'
                bodies = binding.wrap(model, binding.module().IPartDoc).GetBodies2(-1, False) or ()
                geometry = []
                for raw in bodies:
                    body = binding.wrap(raw, binding.module().IBody2)
                    geometry.append({'type': int(body.GetType()), 'box_m': list(body.GetBodyBox()),
                                     'faces': int(body.GetFaceCount()), 'edges': int(body.GetEdgeCount())})
                scoped = {'name': str(feature.Name), 'configuration': 'Основная', 'geometry': geometry}
                # Fixture-scoped token, not a published universal document revision.
                token = 'fixture_' + hashlib.sha256(_json({'document_id': document_id,
                    'observed': observed, 'scoped': scoped}).encode('utf-8')).hexdigest()
                return token, scoped

            def command(request, document_id, name, *, fault=False, fail_restore=False, expected=None):
                revision = expected or runner.worker.submit(lambda: snapshot(document_id)[0]).result(timeout=45)
                context = {'document_id': document_id, 'configuration': 'Основная', 'expected_revision': revision}
                ready = threading.Event()
                operation = {}
                def apply(prepared):
                    native[document_id][1].Name = name
                    assert str(native[document_id][1].Name) == name
                    if fault:
                        raise RuntimeError('Injected failure AFTER the native name write.')
                    return {'name': name}
                def restore(before, prepared):
                    if fail_restore:
                        raise RuntimeError('Injected restoration failure.')
                    native[document_id][1].Name = before['name']
                def execute():
                    assert ready.wait(5)
                    def prepare():
                        token, before = snapshot(document_id)
                        return PreparedMutation(token, before)
                    return coordinator.execute(operation['id'], **context, prepare=prepare,
                        validate=lambda p: snapshot(document_id)[0] == p.revision,
                        apply=apply, inspect=lambda p: snapshot(document_id)[1],
                        verify=lambda b, a, v: a == {**b, 'name': name}, restore=restore,
                        verify_restored=lambda b, a: b == a)
                job = runner.submit(request, 'fixture.feature.rename', {'name': name}, execute,
                                    context=context, mutates=True, verify=lambda r: r['verified'] is True)
                operation['id'] = job['operation_id']
                ready.set()
                result = asyncio.run(runner.wait(job['operation_id'], 45))
                assert result['status'] not in ('queued', 'running')
                return result

            first, second = ids
            stale = runner.worker.submit(lambda: snapshot(first)[0]).result(timeout=45)
            succeeded = command('success', first, 'Проверенное русское имя')
            assert succeeded['status'] == 'succeeded' and succeeded['mutation']['phase'] == 'committed'
            wrong = command('stale', first, 'Это имя не применяется', expected=stale)
            assert wrong['status'] == 'failed' and wrong['error']['code'] == 'stale_revision'
            assert 'mutation' not in wrong
            rolled_back = command('rollback', first, 'Временное русское имя', fault=True)
            assert rolled_back['status'] == 'failed' and rolled_back['mutation']['phase'] == 'rolled_back'
            assert runner.worker.submit(lambda: snapshot(first)[1]['name']).result(timeout=45) == 'Проверенное русское имя'
            uncertain = command('uncertain', first, 'Имя после неподтверждённой операции', fault=True, fail_restore=True)
            assert uncertain['status'] == 'unknown' and uncertain['mutation']['phase'] == 'unresolved'
            blocked = command('blocked', first, 'Заблокированное имя')
            assert blocked['status'] == 'failed' and blocked['error']['code'] == 'document_mutation_blocked'
            assert runner.worker.submit(lambda: snapshot(first)[1]['name']).result(timeout=45) == 'Имя после неподтверждённой операции'
            assert command('other', second, 'Проверенное имя второго документа')['status'] == 'succeeded'
            assert store.mutation_blockers('another_connection', second)
            def reconcile():
                token, observed = snapshot(first)
                assert observed['name'] == 'Имя после неподтверждённой операции'
                store.reconcile_mutation(uncertain['operation_id'], resolution='accept_current_state',
                                         evidence={'observed_revision': token, 'observed_state': observed})
            runner.worker.submit(reconcile).result(timeout=45)
            assert store.get(uncertain['operation_id'])['status'] == 'unknown'
            assert store.mutation_blockers(epoch, first) == []
            assert command('after-reconcile', first, 'Имя после согласования состояния')['status'] == 'succeeded'

            async def info():
                _, response = await create_app(store).call_tool('system_get_info', {})
                return response['data']
            build = asyncio.run(info())
            assert build['build_matches_source'] is True
            assert build['capabilities']['cad_mutations'] is False
            report = {'package_version': build['package_version'], 'git_sha': build['build']['git_sha'],
                'source_dirty': build['build']['source_dirty'], 'build_matches_source': True,
                'journal_schema_version': build['journal_schema_version'], 'solidworks_revision': original[0],
                'owned_fixture_documents': 2, 'native_protocol_not_mcp_mutation_acceptance': True,
                'native_name_write_readback': True, 'scoped_name_restoration_after_injected_failure': True,
                'fixture_scoped_stale_revision_rejected': True, 'unconfirmed_restoration_blocks_same_document': True,
                'other_document_available_in_same_connection': True, 'reconnect_cannot_bypass_hold': True,
                'native_state_observed_before_reconciliation': True, 'historical_unknown_preserved': True}
        finally:
            def release():
                if native.get('catalog') is not None:
                    native['catalog'].close()
                native.clear()
            try:
                runner.worker.submit(release).result(timeout=45)
            finally:
                assert runner.shutdown(timeout_s=45)
    assert native_snapshot() == original
    report['original_document_baseline_restored'] = True
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    pythoncom.CoInitialize()
    try:
        print(json.dumps(check(args.state_dir), ensure_ascii=True, indent=2))
    finally:
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    main()
