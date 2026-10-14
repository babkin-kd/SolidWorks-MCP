"""Offline artifact gates; synthetic ZIPs are not installed/CAD evidence."""
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('wheel_checks', ROOT / 'scripts/verify_wheel_artifact.py')
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)
VERSION, SHA = '2.0.0.dev42', 'a' * 40
DIST = f'solidworks_mcp-{VERSION}.dist-info'


@pytest.fixture
def candidate(tmp_path):
    source = tmp_path / 'solidworks_mcp'
    source.mkdir()
    (source / '__init__.py').write_text(f'__version__ = "{VERSION}"\n', encoding='utf8')
    (source / 'server_v2.py').write_text('def main():\n    pass\n', encoding='utf8')
    (source / 'guide_v2.md').write_text('Development fixture.\n', encoding='utf8')
    from solidworks_mcp.build_info import source_digest
    build = {'git_sha': SHA, 'source_dirty': False, 'source_digest': source_digest(source),
             'package_version': VERSION, 'api_version': 2}
    files = {'solidworks_mcp/' + p.name: p.read_bytes() for p in source.iterdir()}
    files.update({'solidworks_mcp/build_info.json': json.dumps(build).encode(),
        DIST + '/METADATA': f'Metadata-Version: 2.4\nName: solidworks-mcp\nVersion: {VERSION}\nProject-URL: Repository, {checks.FORK_REPOSITORY}\n\n'.encode(),
        DIST + '/entry_points.txt': b'[console_scripts]\nsolidworks-mcp-v2 = solidworks_mcp.server_v2:main\n'})
    path = tmp_path / 'candidate.whl'
    write_zip(path, files)
    return path, files


def write_zip(path, files):
    with ZipFile(path, 'w') as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def validate(path, **arguments):
    return checks.validate_wheel(path, expected_version=arguments.get('version', VERSION),
                                 expected_git_sha=arguments.get('sha', SHA))


def test_consistent_fork_artifact_is_not_native_or_publication_proof(candidate):
    path, _ = candidate
    result = validate(path)
    assert result['accepted'] is True and result['git_sha'] == SHA
    assert result['native_acceptance'] is result['public_registry_publication_verified'] is False


@pytest.mark.parametrize('field,value,message', [
    ('source_dirty', True, 'Dirty'), ('source_dirty', 0, 'Dirty'),
    ('git_sha', 'b' * 40, 'SHA'), ('api_version', True, 'API/version'),
    ('api_version', 1, 'API/version'), ('package_version', 'wrong', 'API/version'),
    ('source_digest', '0' * 64, 'digest'),
])
def test_inconsistent_or_untyped_build_metadata_fails(candidate, field, value, message):
    path, files = candidate
    build = json.loads(files['solidworks_mcp/build_info.json'])
    build[field] = value
    files['solidworks_mcp/build_info.json'] = json.dumps(build).encode()
    write_zip(path, files)
    with pytest.raises(ValueError, match=message):
        validate(path)


@pytest.mark.parametrize('name', ['../bad.py', 'solidworks_mcp/../bad.py', 'solidworks_mcp//bad.py',
                                   'solidworks_mcp/./bad.py', 'C:/bad.py', 'solidworks_mcp\\bad.py'])
def test_unsafe_wheel_members_fail_before_any_extraction(candidate, name):
    path, files = candidate
    files[name] = b'not executed'
    write_zip(path, files)
    if '\\' in name:
        # ZipInfo normalises Windows separators when writing; preserve an
        # actual raw backslash in both ZIP headers for the negative fixture.
        path.write_bytes(path.read_bytes().replace(name.replace('\\', '/').encode(), name.encode()))
    with pytest.raises(ValueError, match='Unsafe'):
        validate(path)


@pytest.mark.parametrize('name', ['solidworks_mcp/private.SLDPRT', 'solidworks_mcp/jobs.sqlite',
                                   'solidworks_mcp/trace.jsonl', 'foreign/other.py'])
def test_cad_journal_or_foreign_package_is_not_a_release_artifact(candidate, name):
    path, files = candidate
    files[name] = b'private fixture'
    write_zip(path, files)
    with pytest.raises(ValueError, match='CAD or private|Unexpected files'):
        validate(path)


def test_changed_source_and_guide_do_not_match_the_build_digest(candidate):
    path, files = candidate
    files['solidworks_mcp/guide_v2.md'] += b'changed'
    write_zip(path, files)
    with pytest.raises(ValueError, match='digest'):
        validate(path)


def test_crlf_normalisation_matches_the_existing_package_digest_contract(candidate):
    path, files = candidate
    for name in ('solidworks_mcp/__init__.py', 'solidworks_mcp/server_v2.py', 'solidworks_mcp/guide_v2.md'):
        files[name] = files[name].replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    write_zip(path, files)
    assert validate(path)['accepted'] is True


def test_upstream_url_or_legacy_console_alias_is_not_our_v2_artifact(candidate):
    path, files = candidate
    files[DIST + '/METADATA'] = files[DIST + '/METADATA'].replace(b'babkin-kd', b'hjbaard')
    write_zip(path, files)
    with pytest.raises(ValueError, match='our fork'):
        validate(path)
    files[DIST + '/METADATA'] = files[DIST + '/METADATA'].replace(b'hjbaard', b'babkin-kd')
    files[DIST + '/entry_points.txt'] += b'solidworks-mcp = solidworks_mcp.server:main\n'
    write_zip(path, files)
    with pytest.raises(ValueError, match='entry point'):
        validate(path)


def test_console_metadata_without_its_module_is_rejected(candidate):
    path, files = candidate
    del files['solidworks_mcp/server_v2.py']
    write_zip(path, files)
    with pytest.raises(ValueError, match='module is absent'):
        validate(path)


def test_duplicate_member_and_symbolic_member_are_rejected(candidate):
    path, files = candidate
    with ZipFile(path, 'a') as archive:
        with pytest.warns(UserWarning, match='Duplicate'):
            archive.writestr('solidworks_mcp/__init__.py', b'bad')
    with pytest.raises(ValueError, match='Duplicate'):
        validate(path)
    write_zip(path, files)
    link = ZipInfo('solidworks_mcp/link.py')
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    with ZipFile(path, 'a') as archive:
        archive.writestr(link, b'/outside')
    with pytest.raises(ValueError, match='Symbolic'):
        validate(path)


def test_expected_commit_and_version_must_match_the_artifact(candidate):
    path, _ = candidate
    with pytest.raises(ValueError, match='full Git SHA'):
        validate(path, sha='main')
    with pytest.raises(ValueError, match='SHA mismatch'):
        validate(path, sha='b' * 40)
    with pytest.raises(ValueError, match='version mismatch'):
        validate(path, version='2.0.0.dev43')