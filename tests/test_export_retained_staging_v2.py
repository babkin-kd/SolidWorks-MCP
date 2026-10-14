"""Verified publication with retained EMPTY owned directory; uncertainty stays held."""
from pathlib import Path

import pytest

from test_exports_v2 import setup, export


def lock_staging_directory(monkeypatch, *, winerror=32, before_failure=None):
    original = Path.rmdir
    def locked(path):
        if path.name.startswith('.mcp-export-'):
            if before_failure:
                before_failure(path)
            error = PermissionError(13, 'Injected directory sharing violation')
            error.winerror = winerror
            raise error
        return original(path)
    monkeypatch.setattr(Path, 'rmdir', locked)


def test_empty_owned_directory_can_be_retained_after_verified_publication(setup, monkeypatch):
    adapter, _, _, store, document_id, output = setup
    lock_staging_directory(monkeypatch)
    job = export(setup)
    assert job['status'] == 'succeeded' and job['mutation']['phase'] == 'committed', job
    assert not store.mutation_blockers('connection_1', document_id)
    cleanup = job['result']['value']['staging_cleanup']
    assert cleanup['status'] == 'retained_empty_directory'
    directory = Path(cleanup['directory'])
    assert directory.parent == output and list(directory.iterdir()) == []
    assert cleanup['identity'] == [directory.stat().st_dev, directory.stat().st_ino]
    assert cleanup['temporary_file_removed'] is True and cleanup['directory_empty_verified'] is True
    evidence = job['mutation']['verification']['evidence']['after']
    assert evidence['staging_clean'] is False
    assert evidence['staging_cleanup'] == cleanup
    assert evidence['preferences'] == job['mutation']['before_state']['preferences']
    retry = export(setup, revision=job['payload']['arguments']['expected_revision'])
    assert retry['operation_id'] == job['operation_id'] and retry['result'] == job['result']
    assert adapter.writes == 1 and (output / 'Кронштейн.stl').is_file()


@pytest.mark.parametrize('winerror', [5, 33, None, '32'])
def test_other_cleanup_errors_remain_unknown(setup, monkeypatch, winerror):
    _, _, _, store, document_id, output = setup
    lock_staging_directory(monkeypatch, winerror=winerror)
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert store.mutation_blockers('connection_1', document_id)
    assert (output / 'Кронштейн.stl').exists()


def test_directory_sharing_violation_cannot_hide_failed_native_export(setup, monkeypatch):
    adapter, _, _, store, document_id, _ = setup
    adapter.fault = 'false'
    lock_staging_directory(monkeypatch)
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert store.mutation_blockers('connection_1', document_id)


def test_nonempty_directory_is_not_deferred_or_recursively_removed(setup, monkeypatch):
    _, _, _, store, document_id, output = setup
    lock_staging_directory(monkeypatch,
        before_failure=lambda directory: (directory / 'foreign.txt').write_text('foreign', encoding='utf8'))
    job = export(setup)
    assert job['status'] == 'unknown' and store.mutation_blockers('connection_1', document_id), job
    assert next(output.glob('.mcp-export-*/foreign.txt')).read_text() == 'foreign'


def test_directory_identity_swap_is_not_deferred(setup, monkeypatch):
    _, _, _, store, document_id, output = setup
    changed = []
    def replace(directory):
        if not changed:
            original = directory.with_name(directory.name + '-original')
            directory.rename(original)
            directory.mkdir()
            (directory / 'foreign.txt').write_text('foreign', encoding='utf8')
            changed.append(original)
    lock_staging_directory(monkeypatch, before_failure=replace)
    job = export(setup)
    assert job['status'] == 'unknown' and store.mutation_blockers('connection_1', document_id), job
    assert changed[0].is_dir() and next(output.glob('.mcp-export-*/foreign.txt')).read_text() == 'foreign'


def test_deferred_directory_rechecked_after_native_inspection(setup, monkeypatch):
    adapter, _, _, store, document_id, output = setup
    lock_staging_directory(monkeypatch)
    original_snapshot = adapter.export_source_snapshot
    def changed_after_publication(model):
        if (output / 'Кронштейн.stl').exists():
            for directory in output.glob('.mcp-export-*'):
                if not list(directory.iterdir()):
                    (directory / 'foreign.txt').write_text('late change', encoding='utf8')
        return original_snapshot(model)
    monkeypatch.setattr(adapter, 'export_source_snapshot', changed_after_publication)
    job = export(setup)
    assert job['status'] == 'unknown' and store.mutation_blockers('connection_1', document_id), job
    assert next(output.glob('.mcp-export-*/foreign.txt')).read_text() == 'late change'
