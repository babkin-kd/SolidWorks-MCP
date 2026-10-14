"""Independent durable+filesystem proof of retained empty directories; no CAD."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verifier_export_artifacts import inspect_staging_cleanup, assert_output_inventory


@pytest.fixture
def artifact(tmp_path):
    root = tmp_path / 'exports'
    root.mkdir()
    directory = root / ('.mcp-export-' + 'a' * 32)
    directory.mkdir()
    info = directory.stat()
    cleanup = {'status': 'retained_empty_directory', 'directory': str(directory),
        'identity': [info.st_dev, info.st_ino], 'temporary_file_removed': True,
        'directory_empty_verified': True, 'reason': 'windows_sharing_violation', 'winerror': 32}
    manifest = {'staging_cleanup': deepcopy(cleanup)}
    mutation = {'phase': 'committed', 'before_state': {'staging_directory': str(directory),
        'temporary_path': str(directory / 'model.stl')}, 'verification': {'outcome': 'committed',
        'evidence': {'after': {'staging_cleanup': deepcopy(cleanup)}}}}
    return root, directory, manifest, mutation


def test_retained_directory_has_matching_durable_and_independent_proof(artifact):
    root, directory, manifest, mutation = artifact
    assert inspect_staging_cleanup(manifest, mutation, root) == directory
    info = directory.stat()
    assert_output_inventory(root, {}, {directory: (info.st_dev, info.st_ino)})


@pytest.mark.parametrize('field,value', [('status', 'pending'), ('winerror', '32'),
    ('winerror', 5), ('temporary_file_removed', 1), ('directory_empty_verified', False),
    ('identity', [True, 1]), ('identity', [0, 0]), ('reason', 'ignored_error')])
def test_bad_cleanup_claim_is_not_proof(artifact, field, value):
    root, _, manifest, mutation = artifact
    manifest['staging_cleanup'][field] = value
    mutation['verification']['evidence']['after']['staging_cleanup'][field] = deepcopy(value)
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)


def test_manifest_cannot_replace_durable_verification(artifact):
    root, _, manifest, mutation = artifact
    mutation['verification']['evidence']['after']['staging_cleanup']['identity'] = [0, 0]
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)


@pytest.mark.parametrize('filename', ['foreign.txt', 'model.stl'])
def test_retained_directory_must_be_empty(artifact, filename):
    root, directory, manifest, mutation = artifact
    (directory / filename).write_text('do not remove', encoding='utf8')
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)
    assert (directory / filename).read_text() == 'do not remove'


def test_removed_directory_claim_is_checked_on_filesystem(artifact):
    root, directory, manifest, mutation = artifact
    manifest['staging_cleanup'] = {'status': 'removed'}
    mutation['verification']['evidence']['after']['staging_cleanup'] = {'status': 'removed'}
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)
    directory.rmdir()
    assert inspect_staging_cleanup(manifest, mutation, root) is None


def test_inventory_does_not_hide_a_foreign_output(artifact):
    root, directory, _, _ = artifact
    foreign = root / 'foreign.txt'
    foreign.write_text('foreign', encoding='utf8')
    info = directory.stat()
    with pytest.raises(AssertionError):
        assert_output_inventory(root, {}, {directory: (info.st_dev, info.st_ino)})
    assert foreign.read_text() == 'foreign'


def test_inventory_rechecks_late_intrusion(artifact):
    root, directory, _, _ = artifact
    info = directory.stat()
    (directory / 'foreign.txt').write_text('foreign', encoding='utf8')
    with pytest.raises(AssertionError):
        assert_output_inventory(root, {}, {directory: (info.st_dev, info.st_ino)})


def test_manifest_directory_must_be_owned_checkpoint_path(artifact, tmp_path):
    root, _, manifest, mutation = artifact
    foreign = tmp_path / ('.mcp-export-' + 'b' * 32)
    foreign.mkdir()
    info = foreign.stat()
    manifest['staging_cleanup'].update(directory=str(foreign), identity=[info.st_dev, info.st_ino])
    mutation['verification']['evidence']['after']['staging_cleanup'] = deepcopy(manifest['staging_cleanup'])
    mutation['before_state'].update(staging_directory=str(foreign), temporary_path=str(foreign / 'model.stl'))
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)


def test_uncommitted_job_cannot_authorize_artifact_cleanup(artifact):
    root, _, manifest, mutation = artifact
    mutation['phase'] = 'unresolved'
    with pytest.raises(AssertionError):
        inspect_staging_cleanup(manifest, mutation, root)
